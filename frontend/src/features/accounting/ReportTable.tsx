import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/feedback";
import { amount, date, downloadText, toCsv } from "@/lib/format";
import type { ReportResult } from "@/lib/types";
import { cn } from "@/lib/utils";

const NUMERIC = new Set(["Currency", "Float", "Int", "Percent"]);
const HIDDEN = new Set(["parent_account", "indent", "is_group_account", "has_value", "currency", "acc_name", "acc_number", "from_date", "to_date", "account_type", "opening_balance", "include_in_gross"]);

export function ReportTable({ result, fileName, maxColumns = 12 }: { result: ReportResult; fileName?: string; maxColumns?: number }) {
  const columns = result.columns.filter((c) => c.fieldname && !HIDDEN.has(c.fieldname)).slice(0, maxColumns);
  if (!result.rows.length) return <EmptyState title="No data for this period" />;
  const label = (row: Record<string, unknown>) => String(row.account_name ?? row.account ?? "").replace(/^'+|'+$/g, "");
  return (
    <div>
      {fileName && (
        <div className="flex justify-end px-4 py-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              downloadText(
                `${fileName}.csv`,
                toCsv(columns.map((c) => ({ key: c.fieldname, label: c.label })), result.rows.map((r) => ({ ...r, account: label(r) || r.account }))),
              )
            }
          >
            <Download /> CSV
          </Button>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-canvas/60 text-xs uppercase tracking-wide text-muted">
            <tr>
              {columns.map((c) => (
                <th key={c.fieldname} className={cn("px-3 py-2 font-medium", NUMERIC.has(c.fieldname === "account" ? "" : c.fieldtype) ? "text-right" : "text-left")}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, i) => {
              const indent = Number(row.indent ?? 0);
              const isTotal = typeof row.account === "string" && row.account.startsWith("'");
              const isGroup = !!row.is_group_account || isTotal;
              return (
                <tr key={i} className={cn("border-t border-border", isTotal && "bg-canvas/60")}>
                  {columns.map((c, j) => {
                    const v = row[c.fieldname];
                    const numeric = NUMERIC.has(c.fieldtype);
                    let text: string;
                    if ((c.fieldname === "account" || c.fieldname === "account_name") && j === 0) text = label(row);
                    else if (numeric) text = v === null || v === undefined || v === "" ? "" : amount(v as number);
                    else if (c.fieldtype === "Date") text = date(v as string);
                    else text = v === null || v === undefined ? "" : String(v);
                    return (
                      <td
                        key={c.fieldname}
                        className={cn("px-3 py-1.5", numeric && "num", isGroup && "font-semibold")}
                        style={j === 0 ? { paddingLeft: 12 + indent * 16 } : undefined}
                      >
                        {text}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
