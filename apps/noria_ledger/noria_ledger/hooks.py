app_name = "noria_ledger"
app_title = "Noria Ledger"
app_publisher = "Noria Technologies Ltd"
app_description = "Noria Ledger client-site app: accounting service API, restrictions and Kenya configuration on top of ERPNext"
app_email = "engineering@noria.co.ke"
app_license = "Proprietary"

# Installed on every client-business site, never on the hub site.
required_apps = ["erpnext"]

after_install = "noria_ledger.install.after_install"
# Standard workspaces are re-synced from ERPNext on migrate, so re-apply the
# accounting-only presentation after every migration.
after_migrate = "noria_ledger.install.after_migrate"

doc_events = {
	"*": {
		"before_insert": "noria_ledger.service.stamp_acting_user",
	}
}
