import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { createColumnHelper } from "@tanstack/react-table";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { hub } from "@/lib/api";
import { date, dateTime, money, previousPeriod } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { MonthlyReport } from "@/lib/types";
import { ReportTable } from "../accounting/ReportTable";

const col = createColumnHelper<MonthlyReport>();
const columns = [
  col.accessor("client_name", { header: "Client" }),
  col.accessor("period", { header: "Period" }),
  col.accessor("status", { header: "Status", cell: (c) => <Badge>{c.getValue()}</Badge> }),
  col.accessor("net_profit", { header: "Net profit", meta: { numeric: true }, cell: (c) => money(c.getValue(), c.row.original.currency ?? "KES") }),
  col.accessor("prepared_by_name", { header: "Prepared by" }),
  col.accessor("published_on", { header: "Published", cell: (c) => dateTime(c.getValue()) }),
];

export function MonthlyReportsList({ client, canPrepare }: { client?: string; canPrepare?: boolean }) {
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["monthly-reports", client ?? "all"], queryFn: () => hub.get<MonthlyReport[]>("monthly_reports.list_reports", { client }) });
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeader
        title="Monthly management reports"
        description="Prepare from ERPNext → internal review → approve → publish to the client portal."
        actions={
          client && canPrepare ? (
            <Button size="sm" onClick={() => setOpen(true)}>
              Prepare report
            </Button>
          ) : null
        }
      />
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        <DataTable
          data={q.data ?? []}
          columns={columns}
          onRowClick={(r) => navigate({ to: "/reports/$reportId", params: { reportId: r.name } })}
          empty={{ title: "No monthly reports yet" }}
          exportName="monthly-reports"
        />
      )}
      {open && client && <PrepareDialog client={client} onClose={() => setOpen(false)} />}
    </Card>
  );
}

function PrepareDialog({ client, onClose }: { client: string; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [period, setPeriod] = useState(previousPeriod());
  const [notes, setNotes] = useState("");
  const m = useMutation({
    mutationFn: () => hub.post<MonthlyReport>("monthly_reports.prepare", { client, period, accountant_notes: notes }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["monthly-reports"] });
      toast.success("Report prepared from the current ledger");
      navigate({ to: "/reports/$reportId", params: { reportId: r.name } });
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Prepare monthly report" description="Snapshots ERPNext's Trial Balance, P&L and Balance Sheet for the period.">
        {m.error ? <ErrorState error={m.error} /> : null}
        <div className="space-y-3">
          <Field label="Period" htmlFor="per">
            <Input id="per" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          </Field>
          <Field label="Accountant notes (visible to the client when published)" htmlFor="nt">
            <Textarea id="nt" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          <div className="flex justify-end">
            <Button loading={m.isPending} onClick={() => m.mutate()}>
              Prepare
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function MonthlyReportsPage() {
  return (
    <div>
      <PageHeader title="Monthly reports" description="All management reports across your clients." />
      <MonthlyReportsList />
    </div>
  );
}

export function ReportDetail({ report, portal = false, actions }: { report: MonthlyReport; portal?: boolean; actions?: React.ReactNode }) {
  const cur = report.currency ?? "KES";
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Total income" value={money(report.total_income, cur)} />
        <Stat label="Total expenses" value={money(report.total_expense, cur)} />
        <Stat label="Net profit" value={money(report.net_profit, cur)} tone={report.net_profit >= 0 ? "good" : "bad"} />
      </div>
      {actions}
      {report.accountant_notes && (
        <Card>
          <CardHeader title="Accountant's notes" />
          <CardBody className="whitespace-pre-line text-sm">{report.accountant_notes}</CardBody>
        </Card>
      )}
      {!portal && report.review_notes && (
        <Card>
          <CardHeader title="Review notes (internal)" />
          <CardBody className="whitespace-pre-line text-sm">{report.review_notes}</CardBody>
        </Card>
      )}
      <Card>
        <Tabs defaultValue="pl">
          <div className="px-4 pt-2">
            <TabsList>
              <TabsTrigger value="pl">Profit & loss</TabsTrigger>
              <TabsTrigger value="bs">Balance sheet</TabsTrigger>
              <TabsTrigger value="tb">Trial balance</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="pl">{report.profit_and_loss && <ReportTable result={report.profit_and_loss} fileName={`pl-${report.client}-${report.period}`} />}</TabsContent>
          <TabsContent value="bs">{report.balance_sheet && <ReportTable result={report.balance_sheet} fileName={`bs-${report.client}-${report.period}`} />}</TabsContent>
          <TabsContent value="tb">{report.trial_balance && <ReportTable result={report.trial_balance} fileName={`tb-${report.client}-${report.period}`} />}</TabsContent>
        </Tabs>
      </Card>
      <p className="text-xs text-muted">
        Snapshot of ERPNext reports taken {dateTime(report.snapshot_taken_on)} for {date(report.from_date)} – {date(report.to_date)}.
      </p>
    </div>
  );
}

export function ReportDetailPage({ reportId }: { reportId: string }) {
  const qc = useQueryClient();
  const { session } = useSession();
  const q = useQuery({ queryKey: ["monthly-report", reportId], queryFn: () => hub.get<MonthlyReport>("monthly_reports.get", { report: reportId }) });
  const [notes, setNotes] = useState("");
  const act = useMutation({
    mutationFn: ({ method, ...args }: { method: string } & Record<string, unknown>) => hub.post<MonthlyReport>(`monthly_reports.${method}`, { report: reportId, ...args }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["monthly-report", reportId] });
      qc.invalidateQueries({ queryKey: ["monthly-reports"] });
      setNotes("");
      toast.success("Report updated");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const r = q.data!;
  const mine = r.prepared_by === session.user;

  const workflow = (
    <Card>
      <CardBody className="flex flex-wrap items-center gap-3">
        <div className="mr-auto text-sm">
          Status <Badge className="ml-1">{r.status}</Badge>
          <span className="ml-3 text-xs text-muted">
            Prepared by {r.prepared_by_name ?? r.prepared_by}
            {r.reviewed_by ? ` · reviewed by ${r.reviewed_by_name ?? r.reviewed_by}` : ""}
            {r.client_acknowledged_on ? ` · client approved ${dateTime(r.client_acknowledged_on)}` : ""}
          </span>
        </div>
        {(r.status === "In Review" || r.status === "Draft") && (
          <Input placeholder={r.status === "In Review" ? "Review notes" : "Notes"} value={notes} onChange={(e) => setNotes(e.target.value)} className="max-w-xs" aria-label="Notes" />
        )}
        {r.status === "Draft" && (
          <Button loading={act.isPending} onClick={() => act.mutate({ method: "submit_for_review", accountant_notes: notes || undefined })}>
            Submit for review
          </Button>
        )}
        {r.status === "In Review" && (
          <>
            <Button variant="secondary" loading={act.isPending} onClick={() => act.mutate({ method: "request_changes", review_notes: notes || "Changes requested" })}>
              Request changes
            </Button>
            <Button loading={act.isPending} onClick={() => act.mutate({ method: "approve", review_notes: notes })} title={mine ? "Reviewer must differ from preparer (except independent accountants)" : undefined}>
              Approve
            </Button>
          </>
        )}
        {r.status === "Approved" && (
          <Button loading={act.isPending} onClick={() => act.mutate({ method: "publish" })}>
            Publish to client portal
          </Button>
        )}
        {["In Review", "Approved", "Published"].includes(r.status) && (
          <Button variant="ghost" loading={act.isPending} onClick={() => confirm("Withdraw this report?") && act.mutate({ method: "withdraw" })}>
            Withdraw
          </Button>
        )}
      </CardBody>
    </Card>
  );

  return (
    <div>
      <PageHeader
        breadcrumb={
          <Link to="/clients/$clientId" params={{ clientId: r.client }} search={{ tab: "monthly" }} className="hover:underline">
            {r.client_name}
          </Link>
        }
        title={`Management report · ${r.period}`}
      />
      <ReportDetail report={r} actions={workflow} />
    </div>
  );
}
