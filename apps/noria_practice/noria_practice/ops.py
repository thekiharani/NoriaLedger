"""Operational probes (used by tests/infra and monitoring)."""

import frappe


def enqueue_probe(marker: str, queue: str = "short") -> str:
	"""Enqueue a no-op job that records `marker` in the cache when a worker runs it."""
	frappe.enqueue("noria_practice.ops.write_probe", queue=queue, marker=marker)
	return "queued"


def write_probe(marker: str):
	frappe.cache.set_value(f"noria-probe:{marker}", "done", expires_in_sec=600)


def read_probe(marker: str) -> str:
	return frappe.cache.get_value(f"noria-probe:{marker}") or "pending"


def register_benchmark_client(firm: str, site_name: str, service_user: str, api_key: str, api_secret: str) -> str:
	"""Attach an already-created client site to the hub (benchmarks only).

	Used by tests/perf/scale_sites.sh, which clones sites from a template for
	scale measurements. Refused on production configurations.
	"""
	if frappe.conf.get("noria_environment") == "production":
		frappe.throw("Not available in production")
	if frappe.db.exists("Client Site", {"site_name": site_name}):
		return frappe.db.get_value("Client Site", {"site_name": site_name}, "client")
	client = frappe.get_doc(
		{
			"doctype": "Client Business",
			"business_name": f"Benchmark {site_name.split('.')[0]}",
			"fiscal_year_start": "2026-01-01",
			"status": "Active",
			"provisioning_status": "Ready",
			"site_name": site_name,
			"company_name": "Bench Template Co",
			"created_by_firm": firm,
		}
	).insert(ignore_permissions=True)
	frappe.get_doc({"doctype": "Client Engagement", "client": client.name, "firm": firm, "status": "Active"}).insert(
		ignore_permissions=True
	)
	frappe.get_doc(
		{
			"doctype": "Client Site",
			"client": client.name,
			"site_name": site_name,
			"status": "Active",
			"service_user": service_user,
			"api_key": api_key,
			"api_secret": api_secret,
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()
	return client.name
