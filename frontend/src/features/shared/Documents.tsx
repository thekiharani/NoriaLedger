import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createColumnHelper } from "@tanstack/react-table";
import { Download, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { downloadBase64, fileToBase64, hub } from "@/lib/api";
import { date, dateTime } from "@/lib/format";

export interface DocRow {
  name: string;
  title: string;
  category: string;
  period?: string;
  status: string;
  file_name?: string;
  file_size?: number;
  content_hash?: string;
  uploaded_by_name?: string;
  uploaded_by_side?: string;
  creation: string;
  document_request?: string;
  review_note?: string;
}

export interface RequestRow {
  name: string;
  title: string;
  category: string;
  period?: string;
  status: string;
  due_date?: string;
  notes?: string;
  response_note?: string;
}

const CATEGORIES = ["Bank Statement", "Receipt", "Invoice", "Tax Document", "Payroll", "Engagement Letter", "Report", "Other"];
const MAX_MB = 20;

/** side="firm" uses documents.*; side="portal" uses portal.* (client users). */
export function DocumentsPanel({ client, side, canWrite = true }: { client: string; side: "firm" | "portal"; canWrite?: boolean }) {
  const qc = useQueryClient();
  const api = side === "firm" ? "documents" : "portal";
  const docs = useQuery({ queryKey: ["documents", client], queryFn: () => hub.get<DocRow[]>(`${api}.documents`, { client }) });
  const requests = useQuery({
    queryKey: ["doc-requests", client],
    queryFn: () => (side === "firm" ? hub.get<RequestRow[]>("documents.requests", { client, open_only: false }) : hub.get<{ open_requests: RequestRow[] }>("portal.overview", { client }).then((o) => o.open_requests)),
  });
  const [uploadFor, setUploadFor] = useState<RequestRow | "new" | null>(null);
  const [requesting, setRequesting] = useState(false);
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["documents", client] });
    qc.invalidateQueries({ queryKey: ["doc-requests", client] });
  };
  const review = useMutation({
    mutationFn: (a: { document: string; status: string }) => hub.post("documents.review", a),
    onSuccess: invalidate,
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });
  const download = useMutation({
    mutationFn: (document: string) => hub.post<{ file_name: string; content_type: string; content: string }>(`${api}.download`, { document }),
    onSuccess: (d) => downloadBase64(d.file_name, d.content_type, d.content),
    onError: (e) => toast.error(e instanceof Error ? e.message : "Download failed"),
  });

  const col = createColumnHelper<DocRow>();
  const columns = useMemo(
    () => [
      col.accessor("title", { header: "Document", cell: (c) => <div><div className="font-medium">{c.getValue()}</div><div className="text-xs text-muted">{c.row.original.file_name}</div></div> }),
      col.accessor("category", { header: "Category" }),
      col.accessor("period", { header: "Period" }),
      col.accessor("uploaded_by_name", { header: "Uploaded by", cell: (c) => <span className="text-xs">{c.getValue()} ({c.row.original.uploaded_by_side})</span> }),
      col.accessor("creation", { header: "When", cell: (c) => dateTime(c.getValue()) }),
      col.accessor("status", { header: "Status", cell: (c) => <Badge>{c.getValue()}</Badge> }),
      col.display({
        id: "actions",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button size="sm" variant="ghost" aria-label="Download" onClick={() => download.mutate(row.original.name)}>
              <Download />
            </Button>
            {side === "firm" && canWrite && row.original.status === "Pending Review" && (
              <>
                <Button size="sm" variant="secondary" onClick={() => review.mutate({ document: row.original.name, status: "Accepted" })}>
                  Accept
                </Button>
                <Button size="sm" variant="ghost" onClick={() => review.mutate({ document: row.original.name, status: "Rejected" })}>
                  Reject
                </Button>
              </>
            )}
          </div>
        ),
      }),
    ],
    [col, side, canWrite, download, review],
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Document requests"
          description={side === "firm" ? "Ask the client for what you need to close the books." : "Your accountant needs these documents."}
          actions={
            side === "firm" &&
            canWrite && (
              <Button size="sm" onClick={() => setRequesting(true)}>
                Request document
              </Button>
            )
          }
        />
        {requests.isLoading ? (
          <Spinner />
        ) : requests.error ? (
          <ErrorState error={requests.error} />
        ) : !requests.data?.length ? (
          <EmptyState title="No document requests" />
        ) : (
          <ul className="divide-y divide-border">
            {requests.data.map((r) => (
              <li key={r.name} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <div className="mr-auto">
                  <div className="text-sm font-medium">{r.title}</div>
                  <div className="text-xs text-muted">
                    {r.category}
                    {r.period ? ` · ${r.period}` : ""} · due {date(r.due_date)}
                    {r.notes ? ` · ${r.notes}` : ""}
                  </div>
                </div>
                <Badge>{r.status}</Badge>
                {["Requested", "Rejected"].includes(r.status) && (
                  <Button size="sm" variant="secondary" onClick={() => setUploadFor(r)}>
                    <Upload /> Upload
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <CardHeader
          title="Documents"
          description="Stored privately in this client's own workspace. Every download is logged."
          actions={
            <Button size="sm" variant="secondary" onClick={() => setUploadFor("new")}>
              <Upload /> Upload
            </Button>
          }
        />
        {docs.isLoading ? <Spinner /> : docs.error ? <ErrorState error={docs.error} /> : <DataTable data={docs.data ?? []} columns={columns} empty={{ title: "No documents yet" }} />}
      </Card>
      {uploadFor && <UploadDialog client={client} api={api} request={uploadFor === "new" ? undefined : uploadFor} onClose={() => setUploadFor(null)} onDone={invalidate} />}
      {requesting && <RequestDialog client={client} onClose={() => setRequesting(false)} onDone={invalidate} />}
    </div>
  );
}

function UploadDialog({ client, api, request, onClose, onDone }: { client: string; api: string; request?: RequestRow; onClose: () => void; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState(request?.title ?? "");
  const [category, setCategory] = useState(request?.category ?? "Other");
  const [period, setPeriod] = useState(request?.period ?? "");
  const m = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a file");
      if (file.size > MAX_MB * 1024 * 1024) throw new Error(`Files are limited to ${MAX_MB} MB`);
      const content = await fileToBase64(file);
      return hub.post(`${api}.upload`, { client, title: title || file.name, filename: file.name, content, category, period: period || undefined, document_request: request?.name });
    },
    onSuccess: () => {
      toast.success("Uploaded");
      onDone();
      onClose();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={request ? `Upload: ${request.title}` : "Upload document"} description="PDF, images, CSV, Excel or Word · max 20 MB">
        {m.error ? <ErrorState error={m.error} /> : null}
        <div className="space-y-3">
          <Field label="File" htmlFor="f">
            <Input id="f" type="file" className="pt-1.5" accept=".pdf,.png,.jpg,.jpeg,.csv,.xlsx,.xls,.doc,.docx,.txt,.zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
          <Field label="Title" htmlFor="ti">
            <Input id="ti" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Category" htmlFor="ca">
              <Select id="ca" value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </Select>
            </Field>
            <Field label="Period" htmlFor="pe">
              <Input id="pe" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
            </Field>
          </div>
          <div className="flex justify-end">
            <Button disabled={!file} loading={m.isPending} onClick={() => m.mutate()}>
              Upload
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RequestDialog({ client, onClose, onDone }: { client: string; onClose: () => void; onDone: () => void }) {
  const [v, setV] = useState({ title: "", category: "Bank Statement", period: "", due_date: "", notes: "" });
  const m = useMutation({
    mutationFn: () => hub.post("documents.create_request", { client, ...v, period: v.period || undefined, due_date: v.due_date || undefined }),
    onSuccess: () => {
      toast.success("Request sent to the client portal");
      onDone();
      onClose();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Request a document">
        {m.error ? <ErrorState error={m.error} /> : null}
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label="What do you need?" htmlFor="t" className="sm:col-span-2">
            <Input id="t" required value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} />
          </Field>
          <Field label="Category" htmlFor="c">
            <Select id="c" value={v.category} onChange={(e) => setV({ ...v, category: e.target.value })}>
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </Select>
          </Field>
          <Field label="Period" htmlFor="p">
            <Input id="p" type="month" value={v.period} onChange={(e) => setV({ ...v, period: e.target.value })} />
          </Field>
          <Field label="Due" htmlFor="d">
            <Input id="d" type="date" value={v.due_date} onChange={(e) => setV({ ...v, due_date: e.target.value })} />
          </Field>
          <Field label="Note to client" htmlFor="n" className="sm:col-span-2">
            <Textarea id="n" value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} />
          </Field>
          <div className="flex justify-end sm:col-span-2">
            <Button type="submit" loading={m.isPending}>Send request</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
