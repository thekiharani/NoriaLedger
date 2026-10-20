import { useState } from "react";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/input";
import { amount } from "@/lib/format";
import type { Account } from "@/lib/types";
import { newIdempotencyKey, useLedger, useLedgerMutation } from "./hooks";

export function AccountsTab({ client, canWrite }: { client: string; canWrite: boolean }) {
  const q = useLedger<{ company: string; accounts: Account[] }>(client, "chart");
  const [open, setOpen] = useState(false);
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const accounts = q.data!.accounts;
  const depth = new Map<string, number>();
  for (const a of accounts) depth.set(a.name, a.parent_account ? (depth.get(a.parent_account) ?? 0) + 1 : 0);

  return (
    <Card>
      <CardHeader
        title="Chart of accounts"
        description={`${q.data!.company} · balances from ERPNext's general ledger (debit positive)`}
        actions={
          canWrite && (
            <Button size="sm" onClick={() => setOpen(true)}>
              <Plus /> Account
            </Button>
          )
        }
      />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-canvas/60 text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-4 py-2">Account</th>
              <th className="px-4 py-2">Type</th>
              <th className="px-4 py-2 text-right">Balance</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr key={a.name} className="border-t border-border">
                <td className="px-4 py-1.5" style={{ paddingLeft: 16 + (depth.get(a.name) ?? 0) * 18 }}>
                  <span className={a.is_group ? "font-semibold" : ""}>
                    {a.account_number ? <span className="mr-2 font-mono text-xs text-muted">{a.account_number}</span> : null}
                    {a.account_name}
                  </span>
                </td>
                <td className="px-4 py-1.5 text-xs text-muted">
                  {a.root_type}
                  {a.account_type ? ` · ${a.account_type}` : ""}
                </td>
                <td className={`num px-4 py-1.5 ${a.is_group ? "font-semibold" : ""}`}>{amount(a.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <NewAccountDialog client={client} open={open} onOpenChange={setOpen} groups={accounts.filter((a) => a.is_group)} />
    </Card>
  );
}

function NewAccountDialog({ client, open, onOpenChange, groups }: { client: string; open: boolean; onOpenChange: (v: boolean) => void; groups: Account[] }) {
  const create = useLedgerMutation(client, "create_account", "Account created");
  const [form, setForm] = useState({ parent_account: "", account_name: "", account_number: "", account_type: "" });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New account">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate({ ...form, idempotency_key: newIdempotencyKey("acc") }, { onSuccess: () => onOpenChange(false) });
          }}
        >
          <Field label="Parent group" htmlFor="pa">
            <Select id="pa" required value={form.parent_account} onChange={(e) => setForm({ ...form, parent_account: e.target.value })}>
              <option value="">Select…</option>
              {groups.map((g) => (
                <option key={g.name} value={g.name}>
                  {g.name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Number" htmlFor="an">
              <Input id="an" value={form.account_number} onChange={(e) => setForm({ ...form, account_number: e.target.value })} />
            </Field>
            <Field label="Name" htmlFor="nm" className="col-span-2">
              <Input id="nm" required value={form.account_name} onChange={(e) => setForm({ ...form, account_name: e.target.value })} />
            </Field>
          </div>
          <Field label="Account type" htmlFor="at" hint="Leave blank for ordinary income/expense/asset accounts">
            <Select id="at" value={form.account_type} onChange={(e) => setForm({ ...form, account_type: e.target.value })}>
              {["", "Bank", "Cash", "Receivable", "Payable", "Tax", "Fixed Asset", "Equity", "Income Account", "Expense Account"].map((t) => (
                <option key={t} value={t}>
                  {t || "—"}
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex justify-end">
            <Button type="submit" loading={create.isPending}>
              Create
            </Button>
          </div>
        </form>
        <p className="mt-3 text-xs text-muted">
          <Badge tone="blue">ERPNext</Badge> validates the account against the company's chart.
        </p>
      </DialogContent>
    </Dialog>
  );
}
