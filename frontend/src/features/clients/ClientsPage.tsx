import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { createColumnHelper } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { ErrorState, Spinner } from "@/components/ui/feedback";
import { Select } from "@/components/ui/input";
import { hub } from "@/lib/api";
import { date, money } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { ClientRow } from "@/lib/types";
import { NewClientDialog } from "./NewClientDialog";

const col = createColumnHelper<ClientRow>();
const columns = [
  col.accessor("business_name", {
    header: "Client",
    cell: (c) => (
      <div>
        <div className="font-medium">{c.getValue()}</div>
        <div className="text-xs text-muted">
          {c.row.original.name} · {c.row.original.kra_pin ?? "no KRA PIN"}
        </div>
      </div>
    ),
  }),
  col.accessor("status", { header: "Status", cell: (c) => <Badge>{c.getValue()}</Badge> }),
  col.accessor((r) => r.team.map((t) => t.full_name ?? t.user).join(", "), {
    id: "team",
    header: "Team",
    cell: (c) => <span className="text-xs">{c.getValue() || <span className="text-muted">Unassigned</span>}</span>,
  }),
  col.accessor("open_tasks", { header: "Open tasks", meta: { numeric: true } }),
  col.accessor((r) => r.stat_unreconciled ?? 0, {
    id: "unreconciled",
    header: "Unreconciled",
    meta: { numeric: true },
    cell: (c) => (c.getValue() ? <Badge tone="amber">{c.getValue()}</Badge> : <span className="text-muted">0</span>),
  }),
  col.accessor((r) => r.stat_cash_and_bank ?? 0, { id: "cash", header: "Cash & bank", meta: { numeric: true }, cell: (c) => money(c.getValue(), c.row.original.currency) }),
  col.accessor((r) => r.stat_last_posting_date ?? "", { id: "last_posting", header: "Last posting", cell: (c) => date(c.getValue()) }),
  col.accessor("provisioning_status", { header: "Workspace", cell: (c) => <Badge>{c.getValue()}</Badge> }),
];

export function ClientsPage() {
  const { firm } = useSession();
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["clients", firm?.firm, status],
    queryFn: () => hub.get<ClientRow[]>("clients.list_clients", { firm: firm?.firm, status }),
    enabled: !!firm,
  });
  const canCreate = firm && ["Firm Admin", "Accountant"].includes(firm.firm_role);

  return (
    <div>
      <PageHeader
        title="Clients"
        description="Every business you keep books for. Each client's books live in an isolated workspace."
        actions={
          canCreate && (
            <Button onClick={() => setOpen(true)}>
              <Plus /> New client
            </Button>
          )
        }
      />
      <Card>
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : (
          <DataTable
            data={q.data ?? []}
            columns={columns}
            searchPlaceholder="Search name, KRA PIN…"
            exportName="clients"
            onRowClick={(r) => navigate({ to: "/clients/$clientId", params: { clientId: r.name } })}
            toolbar={
              <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 w-36 text-xs" aria-label="Filter by status">
                <option value="">All statuses</option>
                <option>Onboarding</option>
                <option>Active</option>
                <option>Suspended</option>
                <option>Archived</option>
              </Select>
            }
            empty={{ title: "No clients yet", description: "Create your first client to provision its accounting workspace." }}
          />
        )}
      </Card>
      {firm && <NewClientDialog open={open} onOpenChange={setOpen} firm={firm.firm} modules={firm.modules} />}
    </div>
  );
}
