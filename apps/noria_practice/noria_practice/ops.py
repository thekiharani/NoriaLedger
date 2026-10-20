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
