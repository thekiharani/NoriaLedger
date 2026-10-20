"""Client-site provisioning and offboarding (runs on the `noria_provisioning` queue).

Only the `provisioner` container consumes that queue and holds the MariaDB root
password (file path in NORIA_DB_ROOT_PASSWORD_FILE). Every step is idempotent so
a failed job can simply be retried.
"""

import json
import os
import re
import secrets
import subprocess

import frappe
from frappe import _
from frappe.utils import get_bench_path, now_datetime

QUEUE = "noria_provisioning"
SITE_LABEL_RE = re.compile(r"[^a-z0-9]+")


def client_site_name(client: str, business_name: str) -> str:
	suffix = (frappe.conf.get("noria_client_site_suffix") or "ledger.internal").strip(".")
	slug = SITE_LABEL_RE.sub("-", business_name.lower()).strip("-")[:30].strip("-") or "client"
	return f"{slug}-{client.lower()}.{suffix}"


def company_abbr(business_name: str) -> str:
	words = [w for w in re.split(r"\W+", business_name) if w]
	abbr = "".join(w[0] for w in words[:4]).upper()
	return abbr or "CO"


def enqueue_provisioning(client: str):
	doc = frappe.get_doc("Client Business", client)
	if doc.provisioning_status in ("Queued", "Provisioning", "Ready"):
		return doc.provisioning_status
	doc.db_set({"provisioning_status": "Queued", "provisioning_error": None})
	frappe.enqueue(
		"noria_practice.provisioning.provision_client_site",
		queue=QUEUE,
		timeout=3600,
		job_id=f"noria-provision::{frappe.local.site}::{client}",
		deduplicate=True,
		enqueue_after_commit=True,
		client=client,
	)
	return "Queued"


def _bench(*args: str, secret_input: bool = False, timeout: int = 1800) -> str:
	"""Run a bench command; never echo arguments (they may contain secrets)."""
	result = subprocess.run(
		["bench", *args],
		cwd=get_bench_path(),
		capture_output=True,
		text=True,
		timeout=timeout,
		check=False,
	)
	if result.returncode != 0:
		tail = "\n".join((result.stdout + "\n" + result.stderr).strip().splitlines()[-15:])
		# Redact anything that looks like a password argument echoed back.
		tail = re.sub(r"(password[\"'=:\s]+)\S+", r"\1***", tail, flags=re.I)
		raise RuntimeError(f"bench {args[0] if args else ''} {args[1] if len(args) > 1 else ''} failed:\n{tail}")
	return result.stdout


def _root_password() -> str:
	path = os.environ.get("NORIA_DB_ROOT_PASSWORD_FILE")
	if not path or not os.path.exists(path):
		raise RuntimeError("NORIA_DB_ROOT_PASSWORD_FILE is not available; provisioning must run on the provisioner worker")
	with open(path) as fh:
		return fh.read().strip()


def _site_exists(site_name: str) -> bool:
	return os.path.isdir(os.path.join(get_bench_path(), "sites", site_name))


def provision_client_site(client: str):
	doc = frappe.get_doc("Client Business", client)
	doc.db_set({"provisioning_status": "Provisioning", "provisioning_error": None})
	frappe.db.commit()
	try:
		site_name = doc.site_name or client_site_name(client, doc.business_name)
		admin_password = None
		if not _site_exists(site_name):
			admin_password = secrets.token_urlsafe(24)
			_bench(
				"new-site",
				site_name,
				"--mariadb-user-host-login-scope=%",
				"--db-root-password",
				_root_password(),
				"--admin-password",
				admin_password,
				"--install-app",
				"erpnext",
				"--install-app",
				"noria_ledger",
			)
		doc.db_set("site_name", site_name)
		frappe.db.commit()

		abbr = doc.company_abbr or company_abbr(doc.business_name)
		output = _bench(
			"--site",
			site_name,
			"execute",
			"noria_ledger.provisioning.bootstrap",
			"--kwargs",
			json.dumps(
				{
					"company_name": doc.legal_name or doc.business_name,
					"company_abbr": abbr,
					"fy_start_date": str(doc.fiscal_year_start),
					"chart_of_accounts": doc.chart_of_accounts or "Standard with Numbers",
					"country": doc.country or "Kenya",
					"currency": doc.currency or "KES",
				}
			),
		)
		creds = _last_json_line(output)
		_bench("--site", site_name, "enable-scheduler")

		site = frappe.get_doc("Client Site", client) if frappe.db.exists("Client Site", client) else frappe.new_doc("Client Site")
		site.client = client
		site.site_name = site_name
		site.status = "Active"
		site.service_user = creds["service_user"]
		site.api_key = creds["api_key"]
		site.api_secret = creds["api_secret"]
		if admin_password:
			site.admin_password = admin_password
		site.provisioned_on = site.provisioned_on or now_datetime()
		site.save(ignore_permissions=True)

		doc.reload()
		doc.db_set(
			{
				"provisioning_status": "Ready",
				"provisioning_error": None,
				"company_name": creds["company"],
				"company_abbr": creds.get("company_abbr") or abbr,
				"status": "Active" if doc.status == "Onboarding" else doc.status,
			}
		)
		frappe.db.commit()
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Provisioning failed for {client}")
		frappe.db.set_value(
			"Client Business",
			client,
			{"provisioning_status": "Failed", "provisioning_error": str(e)[:1000]},
		)
		frappe.db.commit()
		raise


def _last_json_line(output: str) -> dict:
	for line in reversed(output.strip().splitlines()):
		line = line.strip()
		if line.startswith("{") and line.endswith("}"):
			data = json.loads(line)
			if {"service_user", "api_key", "api_secret", "company"} <= set(data):
				return data
	raise RuntimeError("Bootstrap did not return service credentials")


def enqueue_offboarding_backup(client: str):
	frappe.enqueue(
		"noria_practice.provisioning.backup_client_site",
		queue=QUEUE,
		timeout=3600,
		enqueue_after_commit=True,
		client=client,
	)


def backup_client_site(client: str):
	"""Full backup (DB + files) of a client site, e.g. at offboarding.

	Databases are never dropped automatically; deletion after the retention
	period is an explicit operator procedure (docs/BACKUP_AND_RECOVERY.md).
	"""
	site_name = frappe.db.get_value("Client Site", client, "site_name")
	if not site_name:
		frappe.throw(_("No site for client {0}").format(client))
	_bench("--site", site_name, "backup", "--with-files")
