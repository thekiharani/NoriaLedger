import { createColumnHelper } from "@tanstack/react-table";
import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/input";
import { amount, centsToString, date, sumCents, toCents, today } from "@/lib/format";
import type { DocSummary } from "@/lib/types";
import { newIdempotencyKey, useLedger, useLedgerMutation, usePostableAccounts } from "./hooks";

interface JournalRow {
  name: string;
  posting_date: string;
  voucher_type: string;
  total_debit: number;
  user_remark?: string;
  docstatus: number;
  reversal_of?: string;
  noria_acting_user?: string;
}

const col = createColumnHelper<JournalRow>();
const STATUS = ["Draft", "Posted", "Cancelled"];

export function JournalsTab({ client, level }: { client: string; level: number }) {
  const q = useLedger<JournalRow[]>(client, "journals", { limit: 500 });
  const submit = useLedgerMutation(client, "submit_journal", "Journal posted");
  const reverse = useLedgerMutation<DocSummary>(client, "reverse_journal", "Reversing entry posted");
  const remove = useLedgerMutation(client, "delete_draft_journal", "Draft deleted");
  const [open, setOpen] = useState<null | "journal" | "income" | "expense">(null);

  const columns = useMemo(
    () => [
      col.accessor("name", { header: "Entry", cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> }),
      col.accessor("posting_date", { header: "Date", cell: (c) => date(c.getValue()) }),
      col.accessor("voucher_type", { header: "Type" }),
      col.accessor("user_remark", { header: "Narration", cell: (c) => <span className="line-clamp-1 text-xs">{c.getValue()}</span> }),
      col.accessor("total_debit", { header: "Amount", meta: { numeric: true }, cell: (c) => amount(c.getValue()) }),
      col.accessor((r) => (r.reversal_of ? "Reversal" : STATUS[r.docstatus]), { id: "status", header: "Status", cell: (c) => <Badge tone={c.getValue() === "Posted" ? "green" : undefined}>{c.getValue()}</Badge> }),
      col.accessor("noria_acting_user", { header: "By", cell: (c) => <span className="text-xs text-muted">{c.getValue()}</span> }),
      col.display({
        id: "actions",
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
              {r.docstatus === 0 && level >= 3 && (
                <>
                  <Button size="sm" variant="secondary" loading={submit.isPending} onClick={() => submit.mutate({ name: r.name })}>
                    Post
                  </Button>
                  <Button size="sm" variant="ghost" aria-label="Delete draft" onClick={() => remove.mutate({ name: r.name })}>
                    <Trash2 />
                  </Button>
                </>
              )}
              {r.docstatus === 1 && !r.reversal_of && level >= 4 && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    if (confirm(`Post a reversing entry for ${r.name} dated today?`)) reverse.mutate({ name: r.name, posting_date: today(), idempotency_key: newIdempotencyKey("rev") });
                  }}
                >
                  Reverse
                </Button>
              )}
            </div>
          );
        },
      }),
    ],
    [level, submit, reverse, remove],
  );

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  return (
    <Card>
      <CardHeader
        title="Journal entries"
        description="Posted entries are immutable; corrections are made with reversing entries."
        actions={
          level >= 3 && (
            <>
              <Button size="sm" variant="secondary" onClick={() => setOpen("income")}>
                Record income
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setOpen("expense")}>
                Record expense
              </Button>
              <Button size="sm" onClick={() => setOpen("journal")}>
                <Plus /> Journal
              </Button>
            </>
          )
        }
      />
      <DataTable data={q.data ?? []} columns={columns} exportName={`journals-${client}`} searchPlaceholder="Search entries…" />
      <JournalDialog client={client} open={open === "journal"} onOpenChange={(v) => setOpen(v ? "journal" : null)} />
      {(open === "income" || open === "expense") && <SimpleEntryDialog client={client} kind={open} onClose={() => setOpen(null)} />}
    </Card>
  );
}

interface Line {
  account: string;
  debit: string;
  credit: string;
  remark: string;
}

const emptyLine = (): Line => ({ account: "", debit: "", credit: "", remark: "" });

function JournalDialog({ client, open, onOpenChange }: { client: string; open: boolean; onOpenChange: (v: boolean) => void }) {
  const accounts = usePostableAccounts(client);
  const create = useLedgerMutation<DocSummary>(client, "create_journal", "Journal saved");
  const [postingDate, setPostingDate] = useState(today());
  const [remark, setRemark] = useState("");
  const [lines, setLines] = useState<Line[]>([emptyLine(), emptyLine()]);
  const [key, setKey] = useState(() => newIdempotencyKey("je"));

  const dr = sumCents(lines.map((l) => l.debit));
  const cr = sumCents(lines.map((l) => l.credit));
  const invalid = Number.isNaN(dr) || Number.isNaN(cr) || lines.some((l) => l.account && !!l.debit === !!l.credit);
  const balanced = !invalid && dr === cr && dr > 0;
  const update = (i: number, patch: Partial<Line>) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  const save = (submit: boolean) =>
    create.mutate(
      {
        posting_date: postingDate,
        user_remark: remark,
        submit,
        idempotency_key: key,
        lines: lines.filter((l) => l.account).map((l) => ({ account: l.account, debit: l.debit || "0", credit: l.credit || "0", remark: l.remark })),
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setLines([emptyLine(), emptyLine()]);
          setRemark("");
          setKey(newIdempotencyKey("je"));
        },
      },
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New journal entry" description="Double-entry: total debits must equal total credits." wide>
        {create.error ? <ErrorState error={create.error} /> : null}
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Field label="Posting date" htmlFor="pd">
            <Input id="pd" type="date" value={postingDate} onChange={(e) => setPostingDate(e.target.value)} />
          </Field>
          <Field label="Narration" htmlFor="rm" className="sm:col-span-2">
            <Input id="rm" value={remark} onChange={(e) => setRemark(e.target.value)} />
          </Field>
        </div>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="pb-1">Account</th>
              <th className="w-32 pb-1 text-right">Debit</th>
              <th className="w-32 pb-1 text-right">Credit</th>
              <th className="pb-1">Line note</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={i}>
                <td className="py-1 pr-2">
                  <Select aria-label={`Line ${i + 1} account`} value={l.account} onChange={(e) => update(i, { account: e.target.value })}>
                    <option value="">Select account…</option>
                    {accounts.data?.map((a) => (
                      <option key={a.name} value={a.name}>
                        {a.name}
                      </option>
                    ))}
                  </Select>
                </td>
                <td className="py-1 pr-2">
                  <Input aria-label={`Line ${i + 1} debit`} inputMode="decimal" className="text-right" value={l.debit} onChange={(e) => update(i, { debit: e.target.value, credit: e.target.value ? "" : l.credit })} />
                </td>
                <td className="py-1 pr-2">
                  <Input aria-label={`Line ${i + 1} credit`} inputMode="decimal" className="text-right" value={l.credit} onChange={(e) => update(i, { credit: e.target.value, debit: e.target.value ? "" : l.debit })} />
                </td>
                <td className="py-1 pr-2">
                  <Input aria-label={`Line ${i + 1} note`} value={l.remark} onChange={(e) => update(i, { remark: e.target.value })} />
                </td>
                <td>
                  {lines.length > 2 && (
                    <Button variant="ghost" size="icon" aria-label="Remove line" onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>
                      <Trash2 />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-border font-medium">
              <td className="py-2">
                <Button variant="link" size="sm" onClick={() => setLines((ls) => [...ls, emptyLine()])}>
                  + Add line
                </Button>
              </td>
              <td className="num py-2 pr-4">{Number.isNaN(dr) ? "—" : centsToString(dr)}</td>
              <td className="num py-2 pr-4">{Number.isNaN(cr) ? "—" : centsToString(cr)}</td>
              <td colSpan={2} className="py-2 text-xs">
                {invalid ? (
                  <span className="text-red-600">Each line needs either a debit or a credit (max 2 decimals)</span>
                ) : balanced ? (
                  <Badge tone="green">Balanced</Badge>
                ) : (
                  <span className="text-amber-600">Difference {centsToString(Math.abs(dr - cr))}</span>
                )}
              </td>
            </tr>
          </tfoot>
        </table>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" disabled={!balanced} loading={create.isPending} onClick={() => save(false)}>
            Save draft
          </Button>
          <Button disabled={!balanced} loading={create.isPending} onClick={() => save(true)}>
            Post
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SimpleEntryDialog({ client, kind, onClose }: { client: string; kind: "income" | "expense"; onClose: () => void }) {
  const cash = usePostableAccounts(client, { account_type: "Cash,Bank" });
  const categories = usePostableAccounts(client, { root_type: kind === "income" ? "Income" : "Expense" });
  const record = useLedgerMutation(client, "record_simple", kind === "income" ? "Income recorded" : "Expense recorded");
  const [v, setV] = useState({ posting_date: today(), amount: "", cash_account: "", category_account: "", description: "", reference: "" });
  const [key] = useState(() => newIdempotencyKey(kind));
  const valid = toCents(v.amount) > 0 && v.cash_account && v.category_account;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={kind === "income" ? "Record income" : "Record expense"} description="Posts a balanced cash/bank journal entry.">
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            record.mutate({ kind, ...v, submit: true, idempotency_key: key }, { onSuccess: onClose });
          }}
        >
          <Field label="Date" htmlFor="d">
            <Input id="d" type="date" value={v.posting_date} onChange={(e) => setV({ ...v, posting_date: e.target.value })} />
          </Field>
          <Field label="Amount" htmlFor="a">
            <Input id="a" inputMode="decimal" value={v.amount} onChange={(e) => setV({ ...v, amount: e.target.value })} />
          </Field>
          <Field label={kind === "income" ? "Received into" : "Paid from"} htmlFor="c">
            <Select id="c" value={v.cash_account} onChange={(e) => setV({ ...v, cash_account: e.target.value })}>
              <option value="">Select…</option>
              {cash.data?.map((a) => <option key={a.name}>{a.name}</option>)}
            </Select>
          </Field>
          <Field label="Category" htmlFor="cat">
            <Select id="cat" value={v.category_account} onChange={(e) => setV({ ...v, category_account: e.target.value })}>
              <option value="">Select…</option>
              {categories.data?.map((a) => <option key={a.name}>{a.name}</option>)}
            </Select>
          </Field>
          <Field label="Description" htmlFor="ds" className="sm:col-span-2">
            <Input id="ds" value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} />
          </Field>
          <Field label="Reference" htmlFor="rf">
            <Input id="rf" value={v.reference} onChange={(e) => setV({ ...v, reference: e.target.value })} />
          </Field>
          <div className="flex items-end justify-end sm:col-span-1">
            <Button type="submit" disabled={!valid} loading={record.isPending}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
