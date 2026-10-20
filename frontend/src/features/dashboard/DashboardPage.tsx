import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AlertTriangle, ArrowRight } from "lucide-react";
import { PageHeader } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, Stat } from "@/components/ui/card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/feedback";
import { hub } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Task } from "@/lib/types";

interface Dashboard {
  period: string;
  clients: number;
  active_clients: number;
  tasks: { open: number; overdue: number; due_this_week: number; in_review: number; tax_filings_due: number; mine: number };
  reconciliation: { unreconciled_lines: number; clients_with_unreconciled: number };
  monthly_reports: { completed: number; pending: number; in_review: number };
  documents: { outstanding_requests: number; awaiting_review: number };
  billing: { monthly_retainers: number; engagements: number };
  attention: { client: string; business_name: string; unreconciled: number; drafts: number; overdue_invoices: number; provisioning_status: string }[];
}

export function DashboardPage() {
  const { firm, session } = useSession();
  const dash = useQuery({ queryKey: ["dashboard", firm?.firm], queryFn: () => hub.get<Dashboard>("dashboard.practice", { firm: firm?.firm }), enabled: !!firm });
  const myTasks = useQuery({ queryKey: ["tasks", "mine"], queryFn: () => hub.get<Task[]>("tasks.list_tasks", { assigned_to: "me" }) });

  if (!firm) return <EmptyState title="You are not a member of any firm yet" description="Ask your firm administrator to add you." />;
  if (dash.isLoading) return <Spinner />;
  if (dash.error) return <ErrorState error={dash.error} />;
  const d = dash.data!;

  return (
    <div>
      <PageHeader title={`Good day, ${session.full_name?.split(" ")[0] ?? ""}`} description={`${firm.firm_name} · practice overview · close period ${d.period}`} />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Active clients" value={d.active_clients} hint={`${d.clients} total in your access`} />
        <Stat label="Tasks overdue" value={d.tasks.overdue} tone={d.tasks.overdue ? "bad" : "good"} hint={`${d.tasks.due_this_week} due within 7 days · ${d.tasks.open} open`} />
        <Stat label="Unreconciled bank lines" value={d.reconciliation.unreconciled_lines} tone={d.reconciliation.unreconciled_lines ? "warn" : "good"} hint={`${d.reconciliation.clients_with_unreconciled} clients affected`} />
        <Stat label={`Reports pending · ${d.period}`} value={d.monthly_reports.pending} tone={d.monthly_reports.pending ? "warn" : "good"} hint={`${d.monthly_reports.completed} approved/published · ${d.monthly_reports.in_review} in review`} />
        <Stat label="Tax filings open" value={d.tasks.tax_filings_due} hint="Statutory tasks from templates" />
        <Stat label="Documents outstanding" value={d.documents.outstanding_requests} hint={`${d.documents.awaiting_review} uploads awaiting review`} />
        <Stat label="Tasks in review" value={d.tasks.in_review} />
        <Stat label="Monthly retainers" value={money(d.billing.monthly_retainers)} hint={`${d.billing.engagements} active engagements`} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader title="Clients needing attention" description="From cached workspace statistics (refreshed after every change and hourly)." />
          {d.attention.length === 0 ? (
            <EmptyState title="All clear" description="No unreconciled lines, drafts or provisioning issues." />
          ) : (
            <ul className="divide-y divide-border">
              {d.attention.map((c) => (
                <li key={c.client}>
                  <Link to="/clients/$clientId" params={{ clientId: c.client }} className="flex items-center gap-3 px-5 py-3 hover:bg-canvas">
                    <AlertTriangle className="size-4 text-amber-500" />
                    <span className="flex-1 text-sm font-medium">{c.business_name}</span>
                    {c.provisioning_status !== "Ready" && <Badge>{c.provisioning_status}</Badge>}
                    {c.unreconciled > 0 && <Badge tone="amber">{c.unreconciled} unreconciled</Badge>}
                    {c.drafts > 0 && <Badge>{c.drafts} drafts</Badge>}
                    {c.overdue_invoices > 0 && <Badge tone="red">{c.overdue_invoices} overdue invoices</Badge>}
                    <ArrowRight className="size-4 text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader title="My work" description="Open tasks assigned to you" actions={<Link to="/tasks" className="text-xs font-medium text-brand-700">View all</Link>} />
          {myTasks.isLoading ? (
            <Spinner />
          ) : !myTasks.data?.length ? (
            <EmptyState title="No open tasks" />
          ) : (
            <ul className="divide-y divide-border">
              {myTasks.data.slice(0, 8).map((t) => (
                <li key={t.name} className="px-5 py-3">
                  <Link to="/clients/$clientId" params={{ clientId: t.client }} search={{ tab: "tasks" }} className="block">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{t.title}</span>
                      <Badge tone={t.overdue ? "red" : undefined}>{t.overdue ? "Overdue" : t.status}</Badge>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {t.client_name} · due {date(t.due_date)}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
