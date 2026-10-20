app_name = "noria_practice"
app_title = "Noria Practice"
app_publisher = "Noria Technologies Ltd"
app_description = "Noria Ledger practice hub: firms, clients, assignments, tasks, entitlements and client-site brokering"
app_email = "engineering@noria.co.ke"
app_license = "Proprietary"

# Installed only on the hub (practice-management) site. Client business books live
# on separate sites running noria_ledger; this app never touches ERPNext tables.

after_install = "noria_practice.install.after_install"
after_migrate = "noria_practice.install.after_migrate"

scheduler_events = {
	"daily": [
		"noria_practice.practice.tasks.generate_recurring_tasks_for_current_period",
	],
	"hourly_long": [
		"noria_practice.api.ledger.refresh_all_client_stats",
	],
}

before_request = ["noria_practice.utils.before_request"]
