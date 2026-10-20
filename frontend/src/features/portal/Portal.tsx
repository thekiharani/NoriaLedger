import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Outlet } from "@tanstack/react-router";
import { LogOut } from "lucide-react";
import { toast } from "sonner";
import { Logo } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/feedback";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { hub, logout } from "@/lib/api";
import { date, dateTime, money } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { MonthlyReport } from "@/lib/types";
import { ReportDetail } from "../reports/MonthlyReports";
import { DocumentsPanel } from "../shared/Documents";
import { MessagesPanel } from "../shared/Messages";

interface PortalOverview {
  client: string;
  business_name: string;
  kra_pin?: string;
  status: string;
  my_role: string;
  can_approve: number;
  firms: string[];
  accountants: { full_name: string; role: string }[];
  published_reports: MonthlyReport[];
  work_in_progress: { name: string; title: string; status: string; due_date?: string }[];
  open_requests: unknown[];
}

export function PortalShell() {
  const { session } = useSession();
  return (
    <div className="min-h-full">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Logo />
          <div className="flex items-center gap-3 text-sm">
            <span className="text-muted">{session.full_name}</span>
            <Button variant="ghost" size="sm" onClick={async () => { await logout(); window.location.href = "/login"; }}>
              <LogOut /> Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}

export function PortalHome() {
  const { session } = useSession();
  const clients = session.portal_clients ?? [];
  if (clients.length === 0) return <EmptyState title="No business is linked to your account" />;
  if (clients.length === 1) return <PortalClient clientId={clients[0].client} />;
  return (
    <div>
      <PageHeader title="Your businesses" />
      <div className="grid gap-4 sm:grid-cols-2">
        {clients.map((c) => (
          <Link key={c.client} to="/portal/$clientId" params={{ clientId: c.client }}>
            <Card className="p-5 hover:border-brand-500">
              <div className="font-medium">{c.business_name}</div>
              <div className="text-xs text-muted">{c.contact_role}</div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function PortalClient({ clientId }: { clientId: string }) {
  const q = useQuery({ queryKey: ["portal", clientId], queryFn: () => hub.get<PortalOverview>("portal.overview", { client: clientId }) });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const o = q.data!;
  return (
    <div>
      <PageHeader title={o.business_name} description={`Accounting by ${o.firms.join(", ")} · ${o.accountants.map((a) => a.full_name).join(", ")}`} />
      <Tabs defaultValue="reports">
        <TabsList className="mb-6">
          <TabsTrigger value="reports">Reports</TabsTrigger>
          <TabsTrigger value="documents">Documents ({o.open_requests.length} requested)</TabsTrigger>
          <TabsTrigger value="status">Status</TabsTrigger>
          <TabsTrigger value="messages">Messages</TabsTrigger>
        </TabsList>
        <TabsContent value="reports">
          <Card>
            <CardHeader title="Published reports" description="Monthly management accounts prepared and reviewed by your accountants." />
            {o.published_reports.length === 0 ? (
              <EmptyState title="No reports published yet" />
            ) : (
              <ul className="divide-y divide-border">
                {o.published_reports.map((r) => (
                  <li key={r.name}>
                    <Link to="/portal/reports/$reportId" params={{ reportId: r.name }} className="flex items-center gap-4 px-5 py-3 hover:bg-canvas">
                      <span className="flex-1 font-medium">Management accounts · {r.period}</span>
                      <span className="text-sm tabular-nums">Net profit {money(r.net_profit, r.currency ?? "KES")}</span>
                      {r.client_acknowledged_on ? <Badge tone="green">Approved</Badge> : <Badge tone="amber">Awaiting your review</Badge>}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </TabsContent>
        <TabsContent value="documents">
          <DocumentsPanel client={clientId} side="portal" />
        </TabsContent>
        <TabsContent value="status">
          <Card>
            <CardHeader title="Work in progress" description="What your accountants are working on." />
            {o.work_in_progress.length === 0 ? (
              <EmptyState title="Nothing outstanding" />
            ) : (
              <ul className="divide-y divide-border">
                {o.work_in_progress.map((t) => (
                  <li key={t.name} className="flex items-center gap-3 px-5 py-3 text-sm">
                    <span className="flex-1">{t.title}</span>
                    <span className="text-xs text-muted">due {date(t.due_date)}</span>
                    <Badge>{t.status}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </TabsContent>
        <TabsContent value="messages">
          <MessagesPanel client={clientId} mySide="Client" />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export function PortalReport({ reportId }: { reportId: string }) {
  const qc = useQueryClient();
  const { session } = useSession();
  const q = useQuery({ queryKey: ["portal-report", reportId], queryFn: () => hub.get<MonthlyReport>("portal.report", { report: reportId }) });
  const ack = useMutation({
    mutationFn: () => hub.post("portal.acknowledge_report", { report: reportId }),
    onSuccess: () => {
      toast.success("Thank you — report approved");
      qc.invalidateQueries({ queryKey: ["portal-report", reportId] });
      qc.invalidateQueries({ queryKey: ["portal"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const r = q.data!;
  const canApprove = session.portal_clients?.some((p) => p.client === r.client && p.can_approve);
  return (
    <div>
      <PageHeader
        breadcrumb={<Link to="/portal" className="hover:underline">{r.client_name}</Link>}
        title={`Management accounts · ${r.period}`}
        actions={
          r.client_acknowledged_on ? (
            <Badge tone="green">Approved {dateTime(r.client_acknowledged_on)}</Badge>
          ) : canApprove ? (
            <Button loading={ack.isPending} onClick={() => ack.mutate()}>Approve report</Button>
          ) : null
        }
      />
      <ReportDetail report={r} portal />
    </div>
  );
}
