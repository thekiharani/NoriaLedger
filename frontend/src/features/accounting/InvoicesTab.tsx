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
import { amount, centsToString, date, toCents, today } from "@/lib/format";
import type { DocSummary } from "@/lib/types";
import { newIdempotencyKey, useLedger, useLedgerMutation, usePostableAccounts } from "./hooks";

type Kind = "sales" | "purchase";

interface InvoiceRow {
  name: string;
  party: string;
  posting_date: string;
  due_date?: string;
  grand_total: number;
  outstanding_amount: number;
  currency: string;
  status: string;
  docstatus: number;
  is_return: number;
  return_against?: string;
  bill_no?: string;
}

const col = createColumnHelper<InvoiceRow>();
const LABELS = {
  sales: { title: "Sales invoices", party: "Customer", noun: "invoice", returnLabel: "Credit note", payLabel: "Record receipt" },
  purchase: { title: "Bills", party: "Supplier", noun: "bill", returnLabel: "Debit note", payLabel: "Record payment" },
};

export function InvoicesTab({ client, kind, level }: { client: string; kind: Kind; level: number }) {
  const L = LABELS[kind];
  const q = useLedger<InvoiceRow[]>(client, "invoices", { kind, limit: 500 });
  const submit = useLedgerMutation(client, "submit_invoice", `${L.noun} posted`);
  const makeReturn = useLedgerMutation<DocSummary>(client, "make_return", `${L.returnLabel} posted`);
  const [creating, setCreating] = useState(false);
  const [paying, setPaying] = useState<InvoiceRow | null>(null);

  const columns = useMemo(
    () => [
      col.accessor("name", { header: kind === "sales" ? "Invoice" : "Bill", cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> }),
      ...(kind === "purchase" ? [col.accessor("bill_no", { header: "Supplier ref" })] : []),
      col.accessor("party", { header: L.party }),
      col.accessor("posting_date", { header: "Date", cell: (c) => date(c.getValue()) }),
      col.accessor("due_date", { header: "Due", cell: (c) => date(c.getValue()) }),
      col.accessor("grand_total", { header: "Total", meta: { numeric: true }, cell: (c) => amount(c.getValue()) }),
      col.accessor("outstanding_amount", { header: "Outstanding", meta: { numeric: true }, cell: (c) => amount(c.getValue()) }),
      col.accessor((r) => (r.is_return ? "Return" : r.status), { id: "status", header: "Status", cell: (c) => <Badge>{c.getValue()}</Badge> }),
      col.display({
        id: "actions",
        cell: ({ row }) => {
          const r = row.original;
          if (level < 3) return null;
          return (
            <div className="flex justify-end gap-1">
              {r.docstatus === 0 && (
                <Button size="sm" variant="secondary" onClick={() => submit.mutate({ kind, name: r.name })}>
                  Post
                </Button>
              )}
              {r.docstatus === 1 && r.outstanding_amount > 0 && !r.is_return && (
                <Button size="sm" variant="secondary" onClick={() => setPaying(r)}>
                  {L.payLabel}
                </Button>
              )}
              {r.docstatus === 1 && !r.is_return && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    if (confirm(`Post a full ${L.returnLabel.toLowerCase()} against ${r.name}?`))
                      makeReturn.mutate({ kind, name: r.name, posting_date: today(), idempotency_key: newIdempotencyKey("ret") });
                  }}
                >
                  {L.returnLabel}
                </Button>
              )}
            </div>
          );
        },
      }),
    ],
    [kind, L, level, submit, makeReturn],
  );

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  return (
    <Card>
      <CardHeader
        title={L.title}
        description="Posted through ERPNext: tax, receivable/payable and GL entries are computed by the accounting engine."
        actions={
          level >= 3 && (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus /> New {L.noun}
            </Button>
          )
        }
      />
      <DataTable data={q.data ?? []} columns={columns} exportName={`${kind}-invoices-${client}`} />
      {creating && <InvoiceDialog client={client} kind={kind} onClose={() => setCreating(false)} />}
      {paying && <PaymentDialog client={client} kind={kind} invoice={paying} onClose={() => setPaying(null)} />}
    </Card>
  );
}

interface Item {
  item_name: string;
  qty: string;
  rate: string;
  account: string;
}

function InvoiceDialog({ client, kind, onClose }: { client: string; kind: Kind; onClose: () => void }) {
  const L = LABELS[kind];
  const parties = useLedger<{ name: string; party_name: string }[]>(client, "parties", { party_type: L.party });
  const accounts = usePostableAccounts(client, { root_type: kind === "sales" ? "Income" : "Expense" });
  const taxes = useLedger<{ name: string; title: string; taxes: { rate: number }[] }[]>(client, "tax_templates", { kind });
  const create = useLedgerMutation<DocSummary>(client, "create_invoice", `${L.noun} saved`);
  const createParty = useLedgerMutation<DocSummary>(client, "create_party", `${L.party} created`);
  const [key] = useState(() => newIdempotencyKey(kind));
  const [head, setHead] = useState({ party: "", posting_date: today(), due_date: "", bill_no: "", taxes_and_charges: "" });
  const [items, setItems] = useState<Item[]>([{ item_name: "", qty: "1", rate: "", account: "" }]);
  const [newParty, setNewParty] = useState("");

  const lineCents = items.map((i) => {
    const q = toCents(i.qty);
    const r = toCents(i.rate);
    return Number.isNaN(q) || Number.isNaN(r) ? Number.NaN : Math.round((q * r) / 100);
  });
  const net = lineCents.reduce((a, b) => a + b, 0);
  const valid = head.party && items.every((i) => i.item_name && toCents(i.rate) >= 0 && toCents(i.qty) > 0) && !Number.isNaN(net);
  const update = (i: number, patch: Partial<Item>) => setItems((xs) => xs.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  const save = (submit: boolean) =>
    create.mutate(
      {
        kind,
        party: head.party,
        posting_date: head.posting_date,
        due_date: head.due_date || undefined,
        bill_no: kind === "purchase" ? head.bill_no : undefined,
        taxes_and_charges: head.taxes_and_charges || undefined,
        items: items.map((i) => ({ item_name: i.item_name, qty: i.qty, rate: i.rate, account: i.account || undefined })),
        submit,
        idempotency_key: key,
      },
      { onSuccess: onClose },
    );

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`New ${L.noun}`} wide>
        {create.error ? <ErrorState error={create.error} /> : null}
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label={L.party} htmlFor="party" className="sm:col-span-2">
            <div className="flex gap-2">
              <Select id="party" value={head.party} onChange={(e) => setHead({ ...head, party: e.target.value })}>
                <option value="">Select…</option>
                {parties.data?.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.party_name}
                  </option>
                ))}
              </Select>
            </div>
          </Field>
          <Field label={`Or add a new ${L.party.toLowerCase()}`} htmlFor="np" className="sm:col-span-2">
            <div className="flex gap-2">
              <Input id="np" value={newParty} onChange={(e) => setNewParty(e.target.value)} />
              <Button
                variant="secondary"
                disabled={!newParty.trim()}
                loading={createParty.isPending}
                onClick={() =>
                  createParty.mutate(
                    { party_type: L.party, party_name: newParty.trim() },
                    {
                      onSuccess: (r) => {
                        setHead((h) => ({ ...h, party: r.name }));
                        setNewParty("");
                        parties.refetch();
                      },
                    },
                  )
                }
              >
                Add
              </Button>
            </div>
          </Field>
          <Field label="Date" htmlFor="pd">
            <Input id="pd" type="date" value={head.posting_date} onChange={(e) => setHead({ ...head, posting_date: e.target.value })} />
          </Field>
          <Field label="Due date" htmlFor="dd">
            <Input id="dd" type="date" value={head.due_date} onChange={(e) => setHead({ ...head, due_date: e.target.value })} />
          </Field>
          {kind === "purchase" && (
            <Field label="Supplier invoice no." htmlFor="bn">
              <Input id="bn" value={head.bill_no} onChange={(e) => setHead({ ...head, bill_no: e.target.value })} />
            </Field>
          )}
          <Field label="Tax template" htmlFor="tx" hint="From the client's ERPNext tax templates">
            <Select id="tx" value={head.taxes_and_charges} onChange={(e) => setHead({ ...head, taxes_and_charges: e.target.value })}>
              <option value="">No tax</option>
              {taxes.data?.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.title} ({t.taxes.map((x) => `${x.rate}%`).join(" + ")})
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <table className="mt-4 w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="pb-1">Description</th>
              <th className="w-20 pb-1 text-right">Qty</th>
              <th className="w-32 pb-1 text-right">Rate</th>
              <th className="pb-1">{kind === "sales" ? "Income account" : "Expense account"}</th>
              <th className="w-28 pb-1 text-right">Amount</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={i}>
                <td className="py-1 pr-2">
                  <Input aria-label="Description" value={it.item_name} onChange={(e) => update(i, { item_name: e.target.value })} />
                </td>
                <td className="py-1 pr-2">
                  <Input aria-label="Quantity" className="text-right" inputMode="decimal" value={it.qty} onChange={(e) => update(i, { qty: e.target.value })} />
                </td>
                <td className="py-1 pr-2">
                  <Input aria-label="Rate" className="text-right" inputMode="decimal" value={it.rate} onChange={(e) => update(i, { rate: e.target.value })} />
                </td>
                <td className="py-1 pr-2">
                  <Select aria-label="Account" value={it.account} onChange={(e) => update(i, { account: e.target.value })}>
                    <option value="">Company default</option>
                    {accounts.data?.map((a) => (
                      <option key={a.name} value={a.name}>
                        {a.name}
                      </option>
                    ))}
                  </Select>
                </td>
                <td className="num py-1 pr-2">{Number.isNaN(lineCents[i]) ? "—" : centsToString(lineCents[i])}</td>
                <td>
                  {items.length > 1 && (
                    <Button variant="ghost" size="icon" aria-label="Remove" onClick={() => setItems((xs) => xs.filter((_, j) => j !== i))}>
                      <Trash2 />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-2 flex items-center justify-between">
          <Button variant="link" size="sm" onClick={() => setItems((xs) => [...xs, { item_name: "", qty: "1", rate: "", account: "" }])}>
            + Add line
          </Button>
          <div className="text-sm">
            Net total <span className="ml-2 font-semibold tabular-nums">{Number.isNaN(net) ? "—" : centsToString(net)}</span>
            <span className="ml-2 text-xs text-muted">(taxes computed by ERPNext)</span>
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" disabled={!valid} loading={create.isPending} onClick={() => save(false)}>
            Save draft
          </Button>
          <Button disabled={!valid} loading={create.isPending} onClick={() => save(true)}>
            Post {L.noun}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PaymentDialog({ client, kind, invoice, onClose }: { client: string; kind: Kind; invoice: InvoiceRow; onClose: () => void }) {
  const accounts = usePostableAccounts(client, { account_type: "Cash,Bank" });
  const pay = useLedgerMutation<DocSummary>(client, "pay_invoice", kind === "sales" ? "Receipt recorded" : "Payment recorded");
  const [key] = useState(() => newIdempotencyKey("pay"));
  const [v, setV] = useState({ account: "", posting_date: today(), amount: String(invoice.outstanding_amount.toFixed(2)), reference_no: "", reference_date: today() });
  const cents = toCents(v.amount);
  const valid = v.account && cents > 0 && cents <= Math.round(invoice.outstanding_amount * 100);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`${LABELS[kind].payLabel} · ${invoice.name}`} description={`${invoice.party} · outstanding ${amount(invoice.outstanding_amount)}`}>
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            pay.mutate({ kind, invoice: invoice.name, ...v, idempotency_key: key }, { onSuccess: onClose });
          }}
        >
          {pay.error ? (
            <div className="sm:col-span-2">
              <ErrorState error={pay.error} />
            </div>
          ) : null}
          <Field label="Cash / bank account" htmlFor="acc" className="sm:col-span-2">
            <Select id="acc" value={v.account} onChange={(e) => setV({ ...v, account: e.target.value })}>
              <option value="">Select…</option>
              {accounts.data?.map((a) => (
                <option key={a.name}>{a.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Date" htmlFor="pdt">
            <Input id="pdt" type="date" value={v.posting_date} onChange={(e) => setV({ ...v, posting_date: e.target.value })} />
          </Field>
          <Field label="Amount" htmlFor="amt" error={cents > Math.round(invoice.outstanding_amount * 100) ? "Exceeds outstanding" : undefined}>
            <Input id="amt" inputMode="decimal" value={v.amount} onChange={(e) => setV({ ...v, amount: e.target.value })} />
          </Field>
          <Field label="Reference (cheque / EFT / M-PESA code)" htmlFor="ref">
            <Input id="ref" value={v.reference_no} onChange={(e) => setV({ ...v, reference_no: e.target.value })} />
          </Field>
          <Field label="Reference date" htmlFor="rd">
            <Input id="rd" type="date" value={v.reference_date} onChange={(e) => setV({ ...v, reference_date: e.target.value })} />
          </Field>
          <div className="flex justify-end sm:col-span-2">
            <Button type="submit" disabled={!valid} loading={pay.isPending}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
