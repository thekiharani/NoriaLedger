"""Noria Ledger service API (called only by the practice hub broker).

Each endpoint uses ERPNext document controllers for validation, posting and
reversal. Nothing here writes ledger tables (GL Entry etc.) directly.
"""
