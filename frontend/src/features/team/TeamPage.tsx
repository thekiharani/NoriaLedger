import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createColumnHelper } from "@tanstack/react-table";
import { UserPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/input";
import { hub } from "@/lib/api";
import { useSession } from "@/lib/session";

interface Member {
  name: string;
  user: string;
  full_name: string;
  firm_role: string;
  department?: string;
  status: string;
  open_tasks: number;
  assigned_clients: number;
}

const col = createColumnHelper<Member>();

export function TeamPage() {
  const { firm } = useSession();
  const qc = useQueryClient();
  const isAdmin = firm?.firm_role === "Firm Admin";
  const q = useQuery({ queryKey: ["members", firm?.firm], queryFn: () => hub.get<Member[]>("firm.members", { firm: firm?.firm }), enabled: !!firm });
  const [open, setOpen] = useState(false);
  const update = useMutation({
    mutationFn: (a: { member: string; status?: string; firm_role?: string }) => hub.post("firm.update_member", { firm: firm?.firm, ...a }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members"] }),
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });
  const columns = useMemo(
    () => [
      col.accessor("full_name", { header: "Name", cell: (c) => <div><div className="font-medium">{c.getValue()}</div><div className="text-xs text-muted">{c.row.original.user}</div></div> }),
      col.accessor("firm_role", {
        header: "Role",
        cell: (c) =>
          isAdmin ? (
            <Select className="h-8 w-36 text-xs" value={c.getValue()} onChange={(e) => update.mutate({ member: c.row.original.name, firm_role: e.target.value })} aria-label="Role">
              {["Firm Admin", "Accountant", "Reviewer", "Staff"].map((r) => <option key={r}>{r}</option>)}
            </Select>
          ) : (
            c.getValue()
          ),
      }),
      col.accessor("department", { header: "Department" }),
      col.accessor("assigned_clients", { header: "Clients", meta: { numeric: true } }),
      col.accessor("open_tasks", { header: "Open tasks", meta: { numeric: true } }),
      col.accessor("status", { header: "Status", cell: (c) => <Badge>{c.getValue()}</Badge> }),
      col.display({
        id: "actions",
        cell: ({ row }) =>
          isAdmin ? (
            <Button size="sm" variant="ghost" onClick={() => update.mutate({ member: row.original.name, status: row.original.status === "Active" ? "Inactive" : "Active" })}>
              {row.original.status === "Active" ? "Deactivate" : "Reactivate"}
            </Button>
          ) : null,
      }),
    ],
    [isAdmin, update],
  );
  return (
    <div>
      <PageHeader
        title="Team"
        description="Firm members, roles and workload. Deactivating a member removes their client access immediately."
        actions={isAdmin && firm?.firm_type !== "Independent Accountant" && <Button onClick={() => setOpen(true)}><UserPlus /> Add member</Button>}
      />
      <Card>{q.isLoading ? <Spinner /> : q.error ? <ErrorState error={q.error} /> : <DataTable data={q.data ?? []} columns={columns} exportName="team" />}</Card>
      {open && firm && <AddMemberDialog firm={firm.firm} onClose={() => setOpen(false)} />}
    </div>
  );
}

function AddMemberDialog({ firm, onClose }: { firm: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [v, setV] = useState({ email: "", full_name: "", firm_role: "Accountant", department: "" });
  const m = useMutation({
    mutationFn: () => hub.post("firm.add_member", { firm, ...v }),
    onSuccess: () => {
      toast.success("Member added; they will receive an email to set a password");
      qc.invalidateQueries({ queryKey: ["members"] });
      onClose();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Add team member">
        {m.error ? <ErrorState error={m.error} /> : null}
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label="Full name" htmlFor="fn"><Input id="fn" required value={v.full_name} onChange={(e) => setV({ ...v, full_name: e.target.value })} /></Field>
          <Field label="Email" htmlFor="em"><Input id="em" type="email" required value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Role" htmlFor="rl">
              <Select id="rl" value={v.firm_role} onChange={(e) => setV({ ...v, firm_role: e.target.value })}>
                {["Firm Admin", "Accountant", "Reviewer", "Staff"].map((r) => <option key={r}>{r}</option>)}
              </Select>
            </Field>
            <Field label="Department" htmlFor="dp"><Input id="dp" value={v.department} onChange={(e) => setV({ ...v, department: e.target.value })} /></Field>
          </div>
          <div className="flex justify-end"><Button type="submit" loading={m.isPending}>Add</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
