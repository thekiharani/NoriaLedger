import re
import uuid
from calendar import monthrange
from datetime import date

import frappe
from frappe import _

from noria_practice.constants import CLIENT_ROLE, PRACTICE_ROLE

PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def before_request():
	"""Correlation id for audit rows and hub->client-site calls."""
	incoming = frappe.get_request_header("X-Request-Id") or ""
	frappe.local.noria_request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex


def period_bounds(period: str) -> tuple[date, date]:
	m = PERIOD_RE.match(period or "")
	if not m:
		frappe.throw(_("Period must be in YYYY-MM format"))
	year, month = int(m.group(1)), int(m.group(2))
	return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def touch_client(client: str):
	"""Record client activity and refresh its cached statistics.

	Volatile Client Business fields (last_activity, stat_*) have exactly one
	writer: this deduplicated background job. Writing them inside user requests
	would race with the job and, under MariaDB 11.8's innodb_snapshot_isolation,
	fail the request with "Record has changed since last read".
	"""
	frappe.enqueue(
		"noria_practice.api.ledger.refresh_client_stats",
		queue="short",
		enqueue_after_commit=True,
		deduplicate=True,
		job_id=f"noria-stats::{frappe.local.site}::{client}",
		client=client,
		touched=True,
	)


def ensure_user(email: str, full_name: str, role: str, password: str | None = None, send_welcome: bool = False) -> str:
	"""Create (or reuse) a Website User carrying a Noria role.

	Noria users never get desk access: they are Website Users whose only entry
	point is the Noria frontend, backed by whitelisted noria_practice.api methods.
	"""
	if role not in (PRACTICE_ROLE, CLIENT_ROLE):
		frappe.throw(_("Unsupported role"))
	email = (email or "").strip().lower()
	frappe.utils.validate_email_address(email, throw=True)
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		if user.user_type == "System User" and not frappe.flags.in_test:
			# Do not silently attach product roles to platform operators.
			frappe.throw(_("{0} is an operator account and cannot be added here").format(email))
		if role not in {r.role for r in user.roles}:
			user.append("roles", {"role": role})
			user.save(ignore_permissions=True)
		return user.name

	first, _sep, last = (full_name or email.split("@")[0]).strip().partition(" ")
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first,
			"last_name": last or None,
			"user_type": "Website User",
			"send_welcome_email": 1 if send_welcome and not password else 0,
			"roles": [{"role": role}],
		}
	)
	user.flags.no_welcome_mail = not (send_welcome and not password)
	user.insert(ignore_permissions=True)
	if password:
		from frappe.utils.password import update_password

		_check_password_strength(password, email)
		update_password(email, password)
	return user.name


def _check_password_strength(password: str, email: str):
	if len(password) < 10:
		frappe.throw(_("Password must be at least 10 characters"))
	from frappe.core.doctype.user.user import test_password_strength

	result = test_password_strength(password, user_data=(email,))
	feedback = (result or {}).get("feedback") or {}
	if feedback.get("password_policy_validation_passed") is False:
		frappe.throw(_("Password is too weak"))


def user_names(users: list[str]) -> dict[str, str]:
	users = [u for u in set(users) if u]
	if not users:
		return {}
	return dict(frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"], as_list=True))
