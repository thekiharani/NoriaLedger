import { createColumnHelper } from "@tanstack/react-table";
import { Plus, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/input";
import { fileToBase64 } from "@/lib/api";
import { amount, date } from "@/lib/format";
import { newIdempotencyKey, useLedger, useLedgerMutation, usePostableAccounts } from "./hooks";

interface BankAccount {
  name: string;
  account_name: string;
  bank: string;
  account: string;
  bank_account_no?: string;
  unreconciled: number;
  gl_balance: number;
}

interface BankTxn {
  name: string;
  date: string;
  bank_account: string;
  description?: string;
  reference_number?: string;
  deposit: number;
  withdrawal: number;
  unallocated_amount: number;
  status: string;
  bank_party_name?: string;
}

interface Suggestion {
  rank: number;
  doctype: string;
  name: string;
  paid_amount: number;
  reference_no?: string;
  party?: string;
  posting_date?: string;
}

interface ImportResult {
  parsed: number;
  created: number;
  duplicates: number;
  dry_run: boolean;
  rows: { line: number; date: string; deposit?: string; withdrawal?: string; description?: string }[];
}

const col = createColumnHelper<BankTxn>();

export function BankingTab({ client, level, enabled }: { client: string; level: number; enabled: boolean }) {
  const accounts = useLedger<BankAccount[]>(client, "bank_accounts");
  const [status, setStatus] = useState("Unreconciled");
  const txns = useLedger<BankTxn[]>(client, "bank_transactions", { status: status || undefined, limit: 1000 }, enabled);
  const [importing, setImporting] = useState(false);
  const [adding, setAdding] = useState(false);
  const [matching, setMatching] = useState<BankTxn | null>(null);

  const columns = useMemo(
    () => [
      col.accessor("date", { header: "Date", cell: (c) => date(c.getValue()) }),
      col.accessor("bank_account", { header: "Account", cell: (c) => <span className="text-xs">{c.getValue()}</span> }),
      col.accessor("description", { header: "Description", cell: (c) => <span className="line-clamp-1 text-xs">{c.getValue()}</span> }),
      col.accessor("reference_number", { header: "Reference", cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> }),
      col.accessor("deposit", { header: "In", meta: { numeric: true }, cell: (c) => (c.getValue() ? amount(c.getValue()) : "") }),
      col.accessor("withdrawal", { header: "Out", meta: { numeric: true }, cell: (c) => (c.getValue() ? amount(c.getValue()) : "") }),
      col.accessor("status", { header: "Status", cell: (c) => <Badge>{c.getValue()}</Badge> }),
      col.display({
        id: "actions",
        cell: ({ row }) =>
          row.original.status === "Unreconciled" && level >= 3 ? (
            <Button size="sm" variant="secondary" onClick={() => setMatching(row.original)}>
              Match
            </Button>
          ) : null,
      }),
    ],
    [level],
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Bank & cash accounts"
          actions={
            level >= 3 && (
              <>
                <Button size="sm" variant="secondary" onClick={() => setAdding(true)}>
                  <Plus /> Bank account
                </Button>
                {enabled && (
                  <Button size="sm" onClick={() => setImporting(true)} disabled={!accounts.data?.length}>
                    <Upload /> Import statement
                  </Button>
                )}
              </>
            )
          }
        />
        {accounts.isLoading ? (
          <Spinner />
        ) : accounts.error ? (
          <ErrorState error={accounts.error} />
        ) : !accounts.data?.length ? (
          <EmptyState title="No bank accounts" description="Add the client's bank and M-PESA accounts to import statements." />
        ) : (
          <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
            {accounts.data.map((a) => (
              <div key={a.name} className="rounded-md border border-border p-4">
                <div className="text-sm font-medium">{a.bank}</div>
                <div className="text-xs text-muted">
                  {a.account_name} {a.bank_account_no ? `· ${a.bank_account_no}` : ""}
                </div>
                <div className="mt-3 flex items-end justify-between">
                  <div>
                    <div className="text-xs text-muted">Ledger balance</div>
                    <div className="text-lg font-semibold tabular-nums">{amount(a.gl_balance)}</div>
                  </div>
                  {a.unreconciled > 0 ? <Badge tone="amber">{a.unreconciled} to reconcile</Badge> : <Badge tone="green">Reconciled</Badge>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      {enabled ? (
        <Card>
          <CardHeader title="Bank transactions" description="Imported statement lines. Matching uses ERPNext's reconciliation rules." />
          {txns.isLoading ? (
            <Spinner />
          ) : txns.error ? (
            <ErrorState error={txns.error} />
          ) : (
            <DataTable
              data={txns.data ?? []}
              columns={columns}
              exportName={`bank-transactions-${client}`}
              toolbar={
                <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 w-40 text-xs" aria-label="Status filter">
                  <option value="Unreconciled">Unreconciled</option>
                  <option value="Reconciled">Reconciled</option>
                  <option value="">All</option>
                </Select>
              }
              empty={{ title: status === "Unreconciled" ? "Everything is reconciled" : "No transactions" }}
            />
          )}
        </Card>
      ) : (
        <Card>
          <EmptyState title="Bank reconciliation is not enabled for this client" description="A firm admin can enable the Bank Reconciliation service." />
        </Card>
      )}
      {adding && <NewBankAccountDialog client={client} onClose={() => setAdding(false)} />}
      {importing && accounts.data && <ImportDialog client={client} accounts={accounts.data} onClose={() => setImporting(false)} />}
      {matching && <MatchDialog client={client} txn={matching} onClose={() => setMatching(null)} />}
    </div>
  );
}

function NewBankAccountDialog({ client, onClose }: { client: string; onClose: () => void }) {
  const create = useLedgerMutation(client, "create_bank_account", "Bank account added");
  const [v, setV] = useState({ bank_name: "", account_name: "", account_number: "" });
  const [key] = useState(() => newIdempotencyKey("bank"));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Add bank account" description="Creates the ERPNext Bank Account and its GL account under Bank Accounts.">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate({ ...v, idempotency_key: key }, { onSuccess: onClose });
          }}
        >
          <Field label="Bank" htmlFor="bk" hint="e.g. Equity Bank, KCB Bank, Safaricom M-PESA">
            <Input id="bk" required value={v.bank_name} onChange={(e) => setV({ ...v, bank_name: e.target.value })} />
          </Field>
          <Field label="Account name" htmlFor="an">
            <Input id="an" required value={v.account_name} onChange={(e) => setV({ ...v, account_name: e.target.value })} />
          </Field>
          <Field label="Account / till number" htmlFor="no">
            <Input id="no" value={v.account_number} onChange={(e) => setV({ ...v, account_number: e.target.value })} />
          </Field>
          <div className="flex justify-end">
            <Button type="submit" loading={create.isPending}>
              Add
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ImportDialog({ client, accounts, onClose }: { client: string; accounts: BankAccount[]; onClose: () => void }) {
  const formats = useLedger<{ code: string; label: string }[]>(client, "statement_formats");
  const run = useLedgerMutation<ImportResult>(client, "import_statement");
  const [bankAccount, setBankAccount] = useState(accounts[0]?.name ?? "");
  const [format, setFormat] = useState("generic_csv");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [key] = useState(() => newIdempotencyKey("stmt"));

  const submit = async (dryRun: boolean) => {
    if (!file) return;
    const content = await fileToBase64(file);
    run.mutate(
      { bank_account: bankAccount, format, content, encoding: "base64", dry_run: dryRun, idempotency_key: dryRun ? undefined : key },
      {
        onSuccess: (r) => {
          if (dryRun) setPreview(r);
          else {
            toast.success(`Imported ${r.created} lines (${r.duplicates} duplicates skipped)`);
            onClose();
          }
        },
      },
    );
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Import bank statement" description="CSV statements from banks or M-PESA. Duplicates are detected and skipped." wide>
        {run.error ? <ErrorState error={run.error} /> : null}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Bank account" htmlFor="ba">
            <Select id="ba" value={bankAccount} onChange={(e) => setBankAccount(e.target.value)}>
              {accounts.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Format" htmlFor="fmt">
            <Select id="fmt" value={format} onChange={(e) => setFormat(e.target.value)}>
              {formats.data?.map((f) => (
                <option key={f.code} value={f.code}>
                  {f.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="File (.csv, max 5 MB)" htmlFor="file">
            <Input id="file" type="file" accept=".csv,text/csv" className="pt-1.5" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); }} />
          </Field>
        </div>
        {preview && (
          <div className="mt-4 rounded-md border border-border">
            <div className="flex gap-4 border-b border-border px-4 py-2 text-sm">
              <span>Parsed {preview.parsed}</span>
              <span className="text-brand-700">New {preview.created}</span>
              <span className="text-amber-600">Duplicates {preview.duplicates}</span>
            </div>
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-xs">
                <tbody>
                  {preview.rows.map((r) => (
                    <tr key={r.line} className="border-t border-border">
                      <td className="px-3 py-1">{r.date}</td>
                      <td className="px-3 py-1">{r.description}</td>
                      <td className="num px-3 py-1">{r.deposit !== "0" ? r.deposit : ""}</td>
                      <td className="num px-3 py-1">{r.withdrawal !== "0" ? `-${r.withdrawal}` : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" disabled={!file} loading={run.isPending} onClick={() => submit(true)}>
            Preview
          </Button>
          <Button disabled={!file || !preview} loading={run.isPending} onClick={() => submit(false)}>
            Import {preview ? preview.created : ""} lines
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function MatchDialog({ client, txn, onClose }: { client: string; txn: BankTxn; onClose: () => void }) {
  const suggestions = useLedger<Suggestion[]>(client, "match_suggestions", { bank_transaction: txn.name });
  const reconcile = useLedgerMutation(client, "reconcile", "Reconciled");
  const categorize = useLedgerMutation(client, "categorize", "Categorised and reconciled");
  const accounts = usePostableAccounts(client);
  const [account, setAccount] = useState("");
  const [remark, setRemark] = useState("");
  const value = txn.deposit || txn.withdrawal;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Reconcile bank line" description={`${date(txn.date)} · ${txn.description ?? ""} · ${txn.deposit ? "in" : "out"} ${amount(value)}`} wide>
        <h3 className="text-sm font-semibold">Suggested matches</h3>
        {suggestions.isLoading ? (
          <Spinner />
        ) : suggestions.error ? (
          <ErrorState error={suggestions.error} />
        ) : !suggestions.data?.length ? (
          <p className="py-3 text-sm text-muted">No matching vouchers within 60 days. Categorise it below instead.</p>
        ) : (
          <table className="mt-2 w-full text-sm">
            <tbody>
              {suggestions.data.map((s) => (
                <tr key={`${s.doctype}-${s.name}`} className="border-t border-border">
                  <td className="py-2">
                    <Badge tone={s.rank >= 3 ? "green" : s.rank === 2 ? "blue" : "gray"}>{s.rank >= 3 ? "Strong" : s.rank === 2 ? "Good" : "Weak"}</Badge>
                  </td>
                  <td className="py-2 text-xs">
                    {s.doctype} <span className="font-mono">{s.name}</span>
                  </td>
                  <td className="py-2 text-xs">{s.party}</td>
                  <td className="py-2 text-xs">{s.reference_no}</td>
                  <td className="num py-2">{amount(s.paid_amount)}</td>
                  <td className="py-2 text-right">
                    <Button
                      size="sm"
                      loading={reconcile.isPending}
                      onClick={() =>
                        reconcile.mutate(
                          { bank_transaction: txn.name, vouchers: [{ payment_doctype: s.doctype, payment_name: s.name, amount: Math.min(s.paid_amount, txn.unallocated_amount) }] },
                          { onSuccess: onClose },
                        )
                      }
                    >
                      Match
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <h3 className="mt-6 text-sm font-semibold">Or categorise</h3>
        <p className="text-xs text-muted">Posts a bank journal entry against the chosen account and reconciles this line.</p>
        <div className="mt-2 grid gap-3 sm:grid-cols-3">
          <Field label="Account" htmlFor="cat" className="sm:col-span-2">
            <Select id="cat" value={account} onChange={(e) => setAccount(e.target.value)}>
              <option value="">Select…</option>
              {accounts.data
                ?.filter((a) => a.account_type !== "Bank")
                .map((a) => (
                  <option key={a.name}>{a.name}</option>
                ))}
            </Select>
          </Field>
          <Field label="Note" htmlFor="nt">
            <Input id="nt" value={remark} onChange={(e) => setRemark(e.target.value)} />
          </Field>
        </div>
        <div className="mt-4 flex justify-end">
          <Button disabled={!account} loading={categorize.isPending} onClick={() => categorize.mutate({ bank_transaction: txn.name, account, remark }, { onSuccess: onClose })}>
            Categorise & reconcile
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
