#!/usr/bin/env python3
"""HTTP load benchmark through the public edge (stdlib only).

Logs in as several demo users (Frappe limits simultaneous sessions per user, so
virtual users share sessions round-robin) and runs fixed-duration scenarios at
increasing concurrency. Prints and optionally writes JSON with throughput,
latency percentiles and error rates.

    NORIA_DEMO_PASSWORD=... python3 tests/perf/load.py --duration 20 --levels 1,5,10,25
"""

import argparse
import http.cookiejar
import json
import os
import platform
import random
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class Session:
	def __init__(self, base, user, pwd):
		self.base = base
		jar = http.cookiejar.CookieJar()
		self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
		self._call("POST", "login", {"usr": user, "pwd": pwd})
		self.csrf = self._call("GET", "noria_practice.api.session.bootstrap")["csrf_token"]

	def _call(self, method, path, payload=None):
		url = f"{self.base}/api/method/{path}"
		data, headers = None, {"Accept": "application/json"}
		if method == "GET" and payload:
			url += "?" + urllib.parse.urlencode(payload)
		elif method == "POST":
			data = json.dumps(payload or {}).encode()
			headers["Content-Type"] = "application/json"
			if getattr(self, "csrf", None):
				headers["X-Frappe-CSRF-Token"] = self.csrf
		req = urllib.request.Request(url, data=data, headers=headers, method=method)
		with self.opener.open(req, timeout=120) as r:
			return json.loads(r.read()).get("message")

	def hub(self, method, payload=None, get=False):
		return self._call("GET" if get else "POST", f"noria_practice.api.{method}", payload)


def scenarios(firm, period_from, period_to):
	def dashboard(s):
		s.hub("dashboard.practice", {"firm": firm}, get=True)

	def client_list(s):
		s.hub("clients.list_clients", {"firm": firm}, get=True)

	def ledger_overview(s):
		s.hub("ledger.call", {"client": random.choice(s.clients), "op": "overview"})

	def journal_list(s):
		s.hub("ledger.call", {"client": random.choice(s.clients), "op": "journals", "args": {"limit": 50}})

	def trial_balance(s):
		s.hub("ledger.call", {"client": random.choice(s.clients), "op": "report",
		                      "args": {"report": "Trial Balance", "from_date": period_from, "to_date": period_to}})

	def profit_and_loss(s):
		s.hub("ledger.call", {"client": random.choice(s.clients), "op": "report",
		                      "args": {"report": "Profit and Loss Statement", "from_date": period_from, "to_date": period_to}})

	return {
		"dashboard": dashboard,
		"client_list": client_list,
		"ledger_overview": ledger_overview,
		"journal_list": journal_list,
		"trial_balance": trial_balance,
		"profit_and_loss": profit_and_loss,
	}


def pct(values, p):
	if not values:
		return None
	values = sorted(values)
	k = max(0, min(len(values) - 1, round(p / 100 * (len(values) - 1))))
	return round(values[k] * 1000, 1)


def run_level(sessions, fn, concurrency, duration):
	latencies, errors = [], []
	lock = threading.Lock()
	stop = time.time() + duration

	def worker(i):
		s = sessions[i % len(sessions)]
		while time.time() < stop:
			t0 = time.perf_counter()
			try:
				fn(s)
				dt = time.perf_counter() - t0
				with lock:
					latencies.append(dt)
			except Exception as e:  # noqa: BLE001 - recorded as an error sample
				with lock:
					errors.append(type(e).__name__ + ": " + str(e)[:120])

	threads = [threading.Thread(target=worker, args=(i,)) for i in range(concurrency)]
	t_start = time.time()
	for t in threads:
		t.start()
	for t in threads:
		t.join()
	elapsed = time.time() - t_start
	total = len(latencies) + len(errors)
	return {
		"concurrency": concurrency,
		"requests": total,
		"rps": round(len(latencies) / elapsed, 2),
		"error_rate": round(len(errors) / total, 4) if total else None,
		"p50_ms": pct(latencies, 50),
		"p95_ms": pct(latencies, 95),
		"p99_ms": pct(latencies, 99),
		"mean_ms": round(statistics.mean(latencies) * 1000, 1) if latencies else None,
		"sample_errors": sorted(set(errors))[:3],
	}


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--base-url", default="http://localhost:8080")
	ap.add_argument("--users", default="amina@wanjiru.demo,brian@wanjiru.demo,cate@wanjiru.demo,david@wanjiru.demo")
	ap.add_argument("--levels", default="1,5,10,25")
	ap.add_argument("--duration", type=int, default=20)
	ap.add_argument("--scenarios", default="dashboard,client_list,ledger_overview,journal_list,trial_balance,profit_and_loss")
	ap.add_argument("--from-date", default="2026-09-01")
	ap.add_argument("--to-date", default="2026-09-30")
	ap.add_argument("--clients", default="", help="comma-separated client ids (default: all visible to the first user)")
	ap.add_argument("--out")
	args = ap.parse_args()
	pwd = os.environ["NORIA_DEMO_PASSWORD"]

	sessions = [Session(args.base_url, u, pwd) for u in args.users.split(",")]
	boot = sessions[0].hub("session.bootstrap", get=True)
	firm = boot["firms"][0]["firm"]
	visible = [c["name"] for c in sessions[0].hub("clients.list_clients", {"firm": firm}, get=True) if c["provisioning_status"] == "Ready"]
	clients = args.clients.split(",") if args.clients else visible
	# Warm up each client site once (first request per site initialises caches).
	for c in clients:
		sessions[0].hub("ledger.call", {"client": c, "op": "overview"})

	# Each virtual user only targets clients its own user may access (others are
	# correctly refused with 403 by the hub's authorization).
	for s in sessions:
		mine = {c["name"] for c in s.hub("clients.list_clients", {"firm": firm}, get=True)}
		s.clients = [c for c in clients if c in mine]
		if not s.clients:
			raise SystemExit(f"session has no accessible target clients")
	fns = scenarios(firm, args.from_date, args.to_date)
	results = {"environment": {"cpus": os.cpu_count(), "platform": platform.platform(), "python": platform.python_version(),
	                           "users": len(sessions), "clients_targeted": len(clients), "duration_s": args.duration},
	           "scenarios": {}}
	for name in args.scenarios.split(","):
		results["scenarios"][name] = []
		for level in [int(x) for x in args.levels.split(",")]:
			r = run_level(sessions, fns[name], level, args.duration)
			results["scenarios"][name].append(r)
			print(f"{name:16s} c={level:<3d} rps={r['rps']:<7} p50={r['p50_ms']}ms p95={r['p95_ms']}ms p99={r['p99_ms']}ms err={r['error_rate']}")
	if args.out:
		with open(args.out, "w") as fh:
			json.dump(results, fh, indent=2)


if __name__ == "__main__":
	main()
