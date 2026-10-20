"""Static configuration of the accounting-only client site.

Nothing here is deleted from ERPNext: modules are blocked per user (Module Profile)
and workspaces/desktop icons are hidden. Authorization is enforced by roles and by
the service API, never by menu visibility.
"""

SERVICE_ROLE = "Noria Service"
ACCOUNTANT_ROLE = "Noria Accountant"
MODULE_PROFILE = "Noria Accounting"

# Roles granted to the hub's service user on each client site. ERPNext's own
# document permissions then apply to every operation.
SERVICE_USER_ROLES = (
	SERVICE_ROLE,
	"Accounts Manager",
	"Accounts User",
	"Sales User",
	"Purchase User",
	# Customer/Supplier masters are created by the *Master Manager roles in ERPNext.
	"Sales Master Manager",
	"Purchase Master Manager",
)

# ERPNext/Frappe modules that accounting users keep. Every other module of the
# installed apps is blocked in the "Noria Accounting" module profile.
ALLOWED_MODULES = (
	"Accounts",
	"Selling",
	"Buying",
	"Setup",
	"Core",
	"Desk",
	"Contacts",
	"Regional",
	"Utilities",
	"Noria Ledger",
)

# Workspaces that remain visible on the (operator-only) desk.
VISIBLE_WORKSPACES = (
	"Accounting",
	"Invoicing",
	"Payments",
	"Financial Reports",
)

# Reports the hub may run through the service API.
ALLOWED_REPORTS = (
	"Trial Balance",
	"Profit and Loss Statement",
	"Balance Sheet",
	"Cash Flow",
	"General Ledger",
	"Accounts Receivable",
	"Accounts Payable",
	"Bank Reconciliation Statement",
)
