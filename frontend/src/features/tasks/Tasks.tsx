import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { createColumnHelper } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { hub } from "@/lib/api";
import { date, previousPeriod } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Task, TeamMember } from "@/lib/types";

const NEXT: Record<string, string[]> = {
  Open: ["In Progress"],
  "In Progress": ["In Review", "Done"],
  "In Review": ["Done", "In Progress"],
  Done: [],
  Cancelled: [],
};
const col = createColumnHelper<Task>();

export function TasksTable({ client, showClient = true }: { client?: string; showClient?: boolean }) {
  const qc = useQueryClient();
  const [scope, setScope] = useState<"open" | "mine" | "all">("open");
  const q = useQuery({
    queryKey: ["tasks", client ?? "all", scope],
    queryFn: () => hub.get<Task[]>("tasks.list_tasks", { client, assigned_to: scope === "mine" ? "me" : undefined, include_done: scope === "all" }),
  });
  const update = useMutation({
    mutationFn: (args: { task: string; status: string }) => hub.post<Task>("tasks.update", args),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });
  const columns = useMemo(
    () => [
      col.accessor("title", { header: "Task", cell: (c) => <span className="font-medium">{c.getValue()}</span> }),
      ...(showClient
        ? [
            col.accessor("client_name", {
              header: "Client",
              cell: (c) => (
                <Link to="/clients/$clientId" params={{ clientId: c.row.original.client }} className="text-brand-700 hover:underline">
                  {c.getValue()}
                </Link>
              ),
            }),
          ]
        : []),
      col.accessor("task_type", { header: "Type" }),
      col.accessor("assigned_to_name", { header: "Assignee", cell: (c) => c.getValue() ?? <span className="text-muted">Unassigned</span> }),
      col.accessor("reviewer_name", { header: "Reviewer" }),
      col.accessor("priority", { header: "Priority", cell: (c) => <Badge tone={c.getValue() === "Urgent" || c.getValue() === "High" ? "red" : "gray"}>{c.getValue()}</Badge> }),
      col.accessor("due_date", {
        header: "Due",
        cell: (c) => <span className={c.row.original.overdue ? "font-medium text-red-600" : ""}>{date(c.getValue())}</span>,
      }),
      col.accessor("status", { header: "Status", cell: (c) => <Badge>{c.getValue()}</Badge> }),
      col.display({
        id: "actions",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            {NEXT[row.original.status]?.map((s) => (
              <Button key={s} size="sm" variant="secondary" onClick={() => update.mutate({ task: row.original.name, status: s })}>
                {s === "Done" ? "Complete" : s === "In Review" ? "Send to review" : s === "In Progress" ? "Start" : s}
              </Button>
            ))}
          </div>
        ),
      }),
    ],
    [showClient, update],
  );
  return (
    <>
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        <DataTable
          data={q.data ?? []}
          columns={columns}
          exportName="tasks"
          toolbar={
            <Select value={scope} onChange={(e) => setScope(e.target.value as typeof scope)} className="h-8 w-36 text-xs" aria-label="Task scope">
              <option value="open">Open tasks</option>
              <option value="mine">Assigned to me</option>
              <option value="all">Including done</option>
            </Select>
          }
          empty={{ title: "No tasks", description: "Recurring work is generated monthly from task templates." }}
        />
      )}
    </>
  );
}

export function TasksPage() {
  const { firm } = useSession();
  const qc = useQueryClient();
  const workload = useQuery({
    queryKey: ["workload", firm?.firm],
    queryFn: () => hub.get<{ user: string; full_name: string; Open: number; "In Progress": number; "In Review": number; overdue: number }[]>("tasks.workload", { firm: firm?.firm }),
    enabled: !!firm && ["Firm Admin", "Reviewer"].includes(firm.firm_role),
  });
  const generate = useMutation({
    mutationFn: () => hub.post<{ created: number }>("tasks.generate", { firm: firm?.firm, period: previousPeriod() }),
    onSuccess: (r) => {
      toast.success(`${r.created} tasks created for ${previousPeriod()}`);
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });
  return (
    <div>
      <PageHeader
        title="Work queue"
        description="Recurring bookkeeping, reconciliation, reporting and statutory work across clients."
        actions={
          firm?.firm_role === "Firm Admin" && (
            <Button variant="secondary" loading={generate.isPending} onClick={() => generate.mutate()}>
              Generate {previousPeriod()} tasks
            </Button>
          )
        }
      />
      {workload.data && workload.data.length > 0 && (
        <Card className="mb-6">
          <CardHeader title="Team workload" description="Open tasks per person" />
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
            {workload.data.map((w) => (
              <div key={w.user ?? "none"} className="rounded-md border border-border p-3">
                <div className="text-sm font-medium">{w.full_name}</div>
                <div className="mt-1 text-xs text-muted">
                  {w.Open} open · {w["In Progress"]} in progress · {w["In Review"]} in review
                </div>
                {w.overdue > 0 && <Badge tone="red" className="mt-2">{w.overdue} overdue</Badge>}
              </div>
            ))}
          </div>
        </Card>
      )}
      <Card>
        <TasksTable />
      </Card>
    </div>
  );
}

export function NewTaskDialog({ client, team, onClose }: { client: string; team: TeamMember[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [v, setV] = useState({ title: "", task_type: "Other", due_date: "", assigned_to: "", reviewer: "", priority: "Medium", period: "", description: "" });
  const m = useMutation({
    mutationFn: () => hub.post("tasks.create", { client, ...v, assigned_to: v.assigned_to || undefined, reviewer: v.reviewer || undefined, period: v.period || undefined, due_date: v.due_date || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      toast.success("Task created");
      onClose();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="New task">
        {m.error ? <ErrorState error={m.error} /> : null}
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate();
          }}
        >
          <Field label="Title" htmlFor="t" className="sm:col-span-2">
            <Input id="t" required value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} />
          </Field>
          <Field label="Type" htmlFor="ty">
            <Select id="ty" value={v.task_type} onChange={(e) => setV({ ...v, task_type: e.target.value })}>
              {["Bookkeeping", "Bank Reconciliation", "Tax Filing", "Payroll", "Monthly Report", "Year End", "Other"].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </Select>
          </Field>
          <Field label="Priority" htmlFor="pr">
            <Select id="pr" value={v.priority} onChange={(e) => setV({ ...v, priority: e.target.value })}>
              {["Low", "Medium", "High", "Urgent"].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </Select>
          </Field>
          <Field label="Assignee" htmlFor="as">
            <Select id="as" value={v.assigned_to} onChange={(e) => setV({ ...v, assigned_to: e.target.value })}>
              <option value="">Unassigned</option>
              {team.map((m) => (
                <option key={m.user} value={m.user}>
                  {m.full_name ?? m.user}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Reviewer" htmlFor="rv">
            <Select id="rv" value={v.reviewer} onChange={(e) => setV({ ...v, reviewer: e.target.value })}>
              <option value="">None</option>
              {team.map((m) => (
                <option key={m.user} value={m.user}>
                  {m.full_name ?? m.user}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Due date" htmlFor="dd">
            <Input id="dd" type="date" value={v.due_date} onChange={(e) => setV({ ...v, due_date: e.target.value })} />
          </Field>
          <Field label="Period" htmlFor="pe">
            <Input id="pe" type="month" value={v.period} onChange={(e) => setV({ ...v, period: e.target.value })} />
          </Field>
          <Field label="Description" htmlFor="ds" className="sm:col-span-2">
            <Textarea id="ds" value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} />
          </Field>
          <div className="flex justify-end sm:col-span-2">
            <Button type="submit" loading={m.isPending}>
              Create
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ClientTasksPanel({ client, team, canWrite }: { client: string; team: TeamMember[]; canWrite: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeader
        title="Tasks"
        actions={
          canWrite && (
            <Button size="sm" onClick={() => setOpen(true)}>
              <Plus /> Task
            </Button>
          )
        }
      />
      <TasksTable client={client} showClient={false} />
      {open && <NewTaskDialog client={client} team={team} onClose={() => setOpen(false)} />}
    </Card>
  );
}
