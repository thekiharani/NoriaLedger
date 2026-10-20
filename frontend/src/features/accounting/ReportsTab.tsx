import { useQuery } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/input";
import { ledger } from "@/lib/api";
import { periodBounds, previousPeriod } from "@/lib/format";
import type { ReportResult } from "@/lib/types";
import { ReportTable } from "./ReportTable";

const REPORTS = [
  "Trial Balance",
  "Profit and Loss Statement",
  "Balance Sheet",
  "Cash Flow",
  "General Ledger",
  "Accounts Receivable",
  "Accounts Payable",
];

export function ReportsTab({ client }: { client: string }) {
  const bounds = periodBounds(previousPeriod());
  const [params, setParams] = useState({ report: "Trial Balance", from_date: bounds.from, to_date: bounds.to, periodicity: "Monthly" });
  const [submitted, setSubmitted] = useState(params);
  const q = useQuery({
    queryKey: ["ledger", client, "report", submitted],
    queryFn: () =>
      ledger<ReportResult>(client, "report", {
        report: submitted.report,
        from_date: submitted.from_date,
        to_date: submitted.to_date,
        options: { periodicity: submitted.periodicity },
      }),
  });

  return (
    <Card>
      <CardHeader title="Financial reports" description="Generated live by ERPNext's report engine from the client's ledger." actions={<Button size="sm" variant="secondary" onClick={() => window.print()}><Printer /> Print / PDF</Button>} />
      <form
        className="grid gap-3 border-b border-border p-4 sm:grid-cols-5"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(params);
        }}
      >
        <Field label="Report" htmlFor="rep" className="sm:col-span-2">
          <Select id="rep" value={params.report} onChange={(e) => setParams({ ...params, report: e.target.value })}>
            {REPORTS.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </Select>
        </Field>
        <Field label="From" htmlFor="fd">
          <Input id="fd" type="date" value={params.from_date} onChange={(e) => setParams({ ...params, from_date: e.target.value })} />
        </Field>
        <Field label="To" htmlFor="td">
          <Input id="td" type="date" value={params.to_date} onChange={(e) => setParams({ ...params, to_date: e.target.value })} />
        </Field>
        <div className="flex items-end gap-2">
          {["Profit and Loss Statement", "Balance Sheet", "Cash Flow"].includes(params.report) && (
            <Select aria-label="Periodicity" value={params.periodicity} onChange={(e) => setParams({ ...params, periodicity: e.target.value })}>
              <option>Monthly</option>
              <option>Quarterly</option>
              <option>Yearly</option>
            </Select>
          )}
          <Button type="submit">Run</Button>
        </div>
      </form>
      {q.isLoading ? <Spinner label="Running report…" /> : q.error ? <ErrorState error={q.error} /> : q.data ? <ReportTable result={q.data} fileName={`${submitted.report}-${submitted.from_date}-${submitted.to_date}`} /> : null}
    </Card>
  );
}
