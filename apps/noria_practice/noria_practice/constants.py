PRACTICE_ROLE = "Noria Practice User"
CLIENT_ROLE = "Noria Client User"

# Firm-level roles (Firm Member.firm_role)
FIRM_ADMIN = "Firm Admin"

# Client-level access (Client Assignment.assignment_role), ordered by privilege.
ACCESS_LEVELS = {"Read Only": 1, "Reviewer": 2, "Accountant": 3, "Lead Accountant": 4}
READ, REVIEW, WRITE, LEAD = 1, 2, 3, 4

# (code, title, description, is_core)
MODULES = (
	("core_accounting", "Core Accounting", "Chart of accounts, journals, invoices, bills, payments, core reports", 1),
	("bank_reconciliation", "Bank Reconciliation", "Statement import (CSV, M-PESA), matching and reconciliation", 0),
	("tax_compliance", "Tax & Compliance", "Tax calendar, statutory filing tasks and evidence", 0),
	("payroll", "Payroll", "Payroll processing (requires Frappe HRMS; not yet available)", 0),
	("document_management", "Document Management", "Document requests, uploads and review", 0),
	("practice_management", "Practice Management", "Work queues, recurring tasks, reviews, workload", 0),
	("client_portal", "Client Portal", "Client access to reports, requests and approvals", 0),
	("advanced_reporting", "Advanced Reporting", "Monthly management packs, comparisons, exports", 0),
	("ai_assistance", "AI Assistance", "Suggestion-only AI helpers (not yet available)", 0),
)

# Default templates. Statutory due dates are configuration that each firm must
# verify against current KRA guidance; they are not hard-coded rules.
TASK_TEMPLATES = (
	{
		"template_name": "Monthly Bookkeeping",
		"task_type": "Bookkeeping",
		"frequency": "Monthly",
		"due_days_after_period_end": 10,
		"default_priority": "Medium",
		"required_module": "core_accounting",
		"description": "Record sales, purchases, receipts and payments for the period.",
	},
	{
		"template_name": "Monthly Bank Reconciliation",
		"task_type": "Bank Reconciliation",
		"frequency": "Monthly",
		"due_days_after_period_end": 12,
		"default_priority": "Medium",
		"required_module": "bank_reconciliation",
		"description": "Import statements (bank and M-PESA) and reconcile all lines.",
	},
	{
		"template_name": "Monthly Management Report",
		"task_type": "Monthly Report",
		"frequency": "Monthly",
		"due_days_after_period_end": 15,
		"default_priority": "Medium",
		"required_module": "core_accounting",
		"description": "Prepare trial balance and P&L, submit for review, publish to the client.",
	},
	{
		"template_name": "VAT Return",
		"task_type": "Tax Filing",
		"frequency": "Monthly",
		"due_days_after_period_end": 20,
		"default_priority": "High",
		"required_module": "tax_compliance",
		"is_statutory": 1,
		"statutory_note": "Default offset only. Verify the current VAT filing deadline with KRA before relying on it.",
		"description": "Prepare VAT return working papers from posted invoices; file on iTax; attach evidence.",
	},
	{
		"template_name": "PAYE Return",
		"task_type": "Tax Filing",
		"frequency": "Monthly",
		"due_days_after_period_end": 9,
		"default_priority": "High",
		"required_module": "tax_compliance",
		"is_statutory": 1,
		"statutory_note": "Default offset only. Verify the current PAYE deadline with KRA before relying on it.",
		"description": "Prepare PAYE return from payroll records; file on iTax; attach evidence.",
	},
	{
		"template_name": "Year-End Closing",
		"task_type": "Year End",
		"frequency": "Annual",
		"due_days_after_period_end": 90,
		"default_priority": "High",
		"required_module": "core_accounting",
		"description": "Close the fiscal year: adjustments, period closing voucher, final statements.",
	},
)
