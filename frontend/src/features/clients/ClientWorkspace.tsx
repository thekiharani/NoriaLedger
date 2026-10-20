import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Check, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { hub } from "@/lib/api";
import { date, dateTime, money } from "@/lib/format";
import { MODULE_LABELS, useSession } from "@/lib/session";
import type { ClientDetail } from "@/lib/types";
import { AccountsTab } from "../accounting/AccountsTab";
import { BankingTab } from "../accounting/BankingTab";
import { useLedger } from "../accounting/hooks";
import { InvoicesTab } from "../accounting/InvoicesTab";
import { JournalsTab } from "../accounting/JournalsTab";
import { ReportsTab } from "../accounting/ReportsTab";
import { MonthlyReportsList } from "../reports/MonthlyReports";
import { DocumentsPanel } from "../shared/Documents";
import { MessagesPanel } from "../shared/Messages";
import { ClientTasksPanel } from "../tasks/Tasks";

const TABS = [
  ["overview", "Overview"],
  ["accounts", "Chart of accounts"],
  ["journals", "Journals"],
  ["sales", "Sales"],
  ["bills", "Bills"],
  ["banking", "Banking"],
  ["reports", "Reports"],
  ["monthly", "Monthly reports"],
  ["documents", "Documents"],
  ["tasks", "Tasks"],
  ["messages", "Messages"],
  ["team", "Team & access"],
] as const;

interface Overview {
  company: string;
  currency: string;
  fiscal_year?: { name: string; from_date: string; to_date: string };
  cash_and_bank: number;
  receivables: number;
  payables: number;
  income_mtd: number;
  expense_mtd: number;
  unreconciled_bank_transactions: number;
  draft_documents: number;
  overdue_sales_invoices: number;
  last_posting_date?: string;
}

export function ClientWorkspace({ clientId, tab }: { clientId: string; tab: string }) {
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ["client", clientId],
    queryFn: () => hub.get<ClientDetail>("clients.get", { client: clientId }),
    refetchInterval: (query) => (["Queued", "Provisioning"].includes(query.state.data?.provisioning_status ?? "") ? 5000 : false),
  });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const c = q.data!;
  const ready = c.provisioning_status === "Ready";
  const level = c.access_level;
  const has = (m: string) => c.modules.includes(m);
  const active = TABS.some(([k]) => k === tab) ? tab : "overview";

  return (
    <div>
      <PageHeader
        breadcrumb={
          <Link to="/clients" className="hover:underline">
            Clients
          </Link>
        }
        title={
          <span className="flex items-center gap-3">
            {c.business_name} <Badge>{c.status}</Badge>
          </span>
        }
        description={`${c.name} · KRA PIN ${c.kra_pin ?? "—"} · ${c.company_name ?? "workspace pending"} · your access: ${c.access_role}`}
      />
      {!ready ? (
        <ProvisioningCard client={c} />
      ) : (
        <Tabs value={active} onValueChange={(v) => navigate({ to: "/clients/$clientId", params: { clientId }, search: { tab: v } })}>
          <TabsList className="mb-6">
            {TABS.map(([k, label]) => (
              <TabsTrigger key={k} value={k}>
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="overview">
            <OverviewTab client={c} />
          </TabsContent>
          <TabsContent value="accounts">{active === "accounts" && <AccountsTab client={clientId} canWrite={level >= 3} />}</TabsContent>
          <TabsContent value="journals">{active === "journals" && <JournalsTab client={clientId} level={level} />}</TabsContent>
          <TabsContent value="sales">{active === "sales" && <InvoicesTab client={clientId} kind="sales" level={level} />}</TabsContent>
          <TabsContent value="bills">{active === "bills" && <InvoicesTab client={clientId} kind="purchase" level={level} />}</TabsContent>
          <TabsContent value="banking">{active === "banking" && <BankingTab client={clientId} level={level} enabled={has("bank_reconciliation")} />}</TabsContent>
          <TabsContent value="reports">{active === "reports" && <ReportsTab client={clientId} />}</TabsContent>
          <TabsContent value="monthly">{active === "monthly" && <MonthlyReportsList client={clientId} canPrepare={level >= 3} />}</TabsContent>
          <TabsContent value="documents">
            {active === "documents" &&
              (has("document_management") ? (
                <DocumentsPanel client={clientId} side="firm" canWrite={level >= 3} />
              ) : (
                <Card>
                  <EmptyState title="Document management is not enabled for this client" />
                </Card>
              ))}
          </TabsContent>
          <TabsContent value="tasks">{active === "tasks" && <ClientTasksPanel client={clientId} team={c.team.filter((t) => t.status === "Active")} canWrite={level >= 3 && has("practice_management")} />}</TabsContent>
          <TabsContent value="messages">{active === "messages" && <MessagesPanel client={clientId} mySide="Firm" />}</TabsContent>
          <TabsContent value="team">{active === "team" && <TeamTab client={c} />}</TabsContent>
        </Tabs>
      )}
    </div>
  );
}

function ProvisioningCard({ client }: { client: ClientDetail }) {
  const qc = useQueryClient();
  const retry = useMutation({
    mutationFn: () => hub.post("clients.provision", { client: client.name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["client", client.name] }),
  });
  const failed = client.provisioning_status === "Failed";
  return (
    <Card>
      <CardBody className="flex flex-col items-center gap-3 py-12 text-center">
        {failed ? <Badge tone="red">Provisioning failed</Badge> : <Spinner label={`Accounting workspace: ${client.provisioning_status}…`} />}
        <p className="max-w-lg text-sm text-muted">
          Each client gets an isolated ERPNext site and database with its own chart of accounts, fiscal year and tax templates. This usually takes about two minutes.
        </p>
        {failed && (
          <>
            <pre className="max-w-xl whitespace-pre-wrap text-left text-xs text-red-700">{client.provisioning_error}</pre>
            {client.access_level >= 4 && (
              <Button loading={retry.isPending} onClick={() => retry.mutate()}>
                <RefreshCw /> Retry
              </Button>
            )}
          </>
        )}
        {client.provisioning_status === "Not Provisioned" && client.access_level >= 4 && (
          <Button loading={retry.isPending} onClick={() => retry.mutate()}>
            Provision workspace
          </Button>
        )}
      </CardBody>
    </Card>
  );
}

function OverviewTab({ client }: { client: ClientDetail }) {
  const qc = useQueryClient();
  const ov = useLedger<Overview>(client.name, "overview");
  const toggle = useMutation({
    mutationFn: (a: { idx: number; done: boolean }) => hub.post("clients.toggle_checklist", { client: client.name, ...a }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["client", client.name] }),
  });
  const cur = ov.data?.currency ?? client.currency;
  return (
    <div className="space-y-6">
      {ov.isLoading ? (
        <Spinner label="Reading the ledger…" />
      ) : ov.error ? (
        <ErrorState error={ov.error} />
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label="Cash & bank" value={money(ov.data!.cash_and_bank, cur)} />
          <Stat label="Receivables" value={money(ov.data!.receivables, cur)} hint={`${ov.data!.overdue_sales_invoices} overdue invoices`} tone={ov.data!.overdue_sales_invoices ? "warn" : "default"} />
          <Stat label="Payables" value={money(ov.data!.payables, cur)} />
          <Stat label="Unreconciled lines" value={ov.data!.unreconciled_bank_transactions} tone={ov.data!.unreconciled_bank_transactions ? "warn" : "good"} />
          <Stat label="Income this month" value={money(ov.data!.income_mtd, cur)} />
          <Stat label="Expenses this month" value={money(ov.data!.expense_mtd, cur)} />
          <Stat label="Drafts" value={ov.data!.draft_documents} />
          <Stat label="Last posting" value={<span className="text-lg">{date(ov.data!.last_posting_date)}</span>} hint={ov.data!.fiscal_year ? `FY ${ov.data!.fiscal_year.name}` : undefined} />
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Onboarding checklist" />
          <ul className="divide-y divide-border">
            {client.onboarding_checklist.map((i) => (
              <li key={i.idx} className="flex items-center gap-3 px-5 py-2.5">
                <button
                  className={`grid size-5 place-items-center rounded border ${i.done ? "border-brand-600 bg-brand-600 text-white" : "border-border"}`}
                  aria-label={`${i.done ? "Uncheck" : "Check"} ${i.item}`}
                  disabled={client.access_level < 3}
                  onClick={() => toggle.mutate({ idx: i.idx, done: !i.done })}
                >
                  {i.done ? <Check className="size-3.5" /> : null}
                </button>
                <span className={`flex-1 text-sm ${i.done ? "text-muted line-through" : ""}`}>{i.item}</span>
                {i.done_on && <span className="text-xs text-muted">{dateTime(i.done_on)}</span>}
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Engagement" />
          <CardBody className="space-y-2 text-sm">
            <div>
              Since {date(client.engagement.start_date)} · retainer {money(client.engagement.monthly_retainer)}/month
            </div>
            <div className="flex flex-wrap gap-1.5">
              {client.modules.map((m) => (
                <Badge key={m} tone="green">
                  {MODULE_LABELS[m] ?? m}
                </Badge>
              ))}
            </div>
            <div className="text-xs text-muted">
              Fiscal year starts {date(client.fiscal_year_start)} · chart: {client.chart_of_accounts}
              {client.other_firms ? ` · also served by ${client.other_firms} other firm(s)` : ""}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function TeamTab({ client }: { client: ClientDetail }) {
  const qc = useQueryClient();
  const { firm } = useSession();
  const lead = client.access_level >= 4;
  const candidates = useQuery({ queryKey: ["team-candidates", client.name], queryFn: () => hub.get<{ user: string; full_name: string; firm_role: string }[]>("clients.team_candidates", { client: client.name }), enabled: lead });
  const [assign, setAssign] = useState({ user: "", assignment_role: "Accountant" });
  const [invite, setInvite] = useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: ["client", client.name] });
  const onError = (e: unknown) => toast.error(e instanceof Error ? e.message : "Failed");
  const doAssign = useMutation({ mutationFn: () => hub.post("clients.assign", { client: client.name, ...assign }), onSuccess: () => { toast.success("Assigned"); refresh(); }, onError });
  const unassign = useMutation({ mutationFn: (a: string) => hub.post("clients.unassign", { client: client.name, assignment: a }), onSuccess: refresh, onError });
  const revoke = useMutation({ mutationFn: (p: string) => hub.post("clients.revoke_portal_user", { client: client.name, portal_user: p }), onSuccess: refresh, onError });
  const archive = useMutation({
    mutationFn: () => hub.post<{ client_archived: boolean }>("clients.archive", { client: client.name, reason: "Offboarded from workspace" }),
    onSuccess: (r) => {
      toast.success(r.client_archived ? "Client archived; a full backup was queued" : "Engagement ended");
      refresh();
    },
    onError,
  });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader title="Firm team" description="Firm admins always have full access. Others need an assignment." />
        <ul className="divide-y divide-border">
          {client.team.map((t) => (
            <li key={t.name} className="flex items-center gap-3 px-5 py-2.5 text-sm">
              <span className="flex-1">
                {t.full_name ?? t.user} <span className="text-xs text-muted">{t.user}</span>
              </span>
              <Badge tone={t.status === "Active" ? "blue" : "gray"}>{t.status === "Active" ? t.assignment_role : "Inactive"}</Badge>
              {lead && t.status === "Active" && (
                <Button size="sm" variant="ghost" onClick={() => unassign.mutate(t.name!)}>
                  Remove
                </Button>
              )}
            </li>
          ))}
        </ul>
        {lead && (
          <form className="flex flex-wrap gap-2 border-t border-border p-4" onSubmit={(e) => { e.preventDefault(); doAssign.mutate(); }}>
            <Select aria-label="Team member" className="flex-1" value={assign.user} onChange={(e) => setAssign({ ...assign, user: e.target.value })}>
              <option value="">Add team member…</option>
              {candidates.data?.map((m) => (
                <option key={m.user} value={m.user}>
                  {m.full_name} ({m.firm_role})
                </option>
              ))}
            </Select>
            <Select aria-label="Role" className="w-40" value={assign.assignment_role} onChange={(e) => setAssign({ ...assign, assignment_role: e.target.value })}>
              {["Lead Accountant", "Accountant", "Reviewer", "Read Only"].map((r) => <option key={r}>{r}</option>)}
            </Select>
            <Button type="submit" disabled={!assign.user} loading={doAssign.isPending}>Assign</Button>
          </form>
        )}
      </Card>
      <Card>
        <CardHeader
          title="Client portal users"
          description="Business owners and finance contacts. They see only published reports, requests and messages."
          actions={lead && client.modules.includes("client_portal") && <Button size="sm" onClick={() => setInvite(true)}>Invite</Button>}
        />
        {client.portal_users.length === 0 ? (
          <EmptyState title="No portal users" />
        ) : (
          <ul className="divide-y divide-border">
            {client.portal_users.map((p) => (
              <li key={p.name} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                <span className="flex-1">{p.full_name ?? p.user} <span className="text-xs text-muted">{p.user}</span></span>
                <Badge>{p.status === "Active" ? p.contact_role : "Inactive"}</Badge>
                {p.can_approve ? <Badge tone="purple">Approver</Badge> : null}
                {lead && p.status === "Active" && <Button size="sm" variant="ghost" onClick={() => revoke.mutate(p.name!)}>Revoke</Button>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {firm?.firm_role === "Firm Admin" && client.status !== "Archived" && (
        <Card className="lg:col-span-2">
          <CardHeader title="Offboarding" description="Ends your firm's engagement. If no other firm serves the client it is archived and its workspace backed up. Financial data is retained." />
          <CardBody>
            <Button variant="destructive" loading={archive.isPending} onClick={() => confirm(`End the engagement with ${client.business_name}?`) && archive.mutate()}>
              End engagement
            </Button>
          </CardBody>
        </Card>
      )}
      {invite && <InviteDialog client={client.name} onClose={() => setInvite(false)} onDone={refresh} />}
    </div>
  );
}

function InviteDialog({ client, onClose, onDone }: { client: string; onClose: () => void; onDone: () => void }) {
  const [v, setV] = useState({ email: "", full_name: "", contact_role: "Owner", can_approve: true });
  const m = useMutation({
    mutationFn: () => hub.post("clients.invite_portal_user", { client, ...v }),
    onSuccess: () => {
      toast.success("Invitation sent");
      onDone();
      onClose();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Invite to client portal" description="The user receives an email to set their password.">
        {m.error ? <ErrorState error={m.error} /> : null}
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label="Full name" htmlFor="fn"><Input id="fn" required value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} /></Field>
          <Field label="Email" htmlFor="em"><Input id="em" type="email" required value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} /></Field>
          <Field label="Role" htmlFor="cr">
            <Select id="cr" value={v.contact_role} onChange={(e) => setV({ ...v, contact_role: e.target.value })}>
              <option>Owner</option><option>Finance Contact</option><option>Viewer</option>
            </Select>
          </Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={v.can_approve} onChange={(e) => setV({ ...v, can_approve: e.target.checked })} /> Can approve published reports</label>
          <div className="flex justify-end"><Button type="submit" loading={m.isPending}>Invite</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
