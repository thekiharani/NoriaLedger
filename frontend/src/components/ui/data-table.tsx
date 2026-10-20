import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, Download, Search } from "lucide-react";
import { useState } from "react";
import { downloadText, toCsv } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "./button";
import { EmptyState } from "./feedback";
import { Input } from "./input";

export type { ColumnDef };

interface Props<T> {
  data: T[];
  columns: ColumnDef<T, any>[];
  searchPlaceholder?: string;
  empty?: { title: string; description?: string; action?: React.ReactNode };
  onRowClick?: (row: T) => void;
  toolbar?: React.ReactNode;
  exportName?: string;
  pageSize?: number;
  dense?: boolean;
}

/** Sortable, searchable, paginated table with CSV export. */
export function DataTable<T>({ data, columns, searchPlaceholder = "Search…", empty, onRowClick, toolbar, exportName, pageSize = 25, dense }: Props<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });

  const exportCsv = () => {
    const cols = table
      .getAllLeafColumns()
      .filter((c) => c.id !== "actions")
      .map((c) => ({ key: c.id, label: typeof c.columnDef.header === "string" ? c.columnDef.header : c.id }));
    const rows = table.getFilteredRowModel().rows.map((r) => Object.fromEntries(cols.map((c) => [c.key, r.getValue(c.key)])));
    downloadText(`${exportName ?? "export"}.csv`, toCsv(cols, rows));
  };

  const rows = table.getRowModel().rows;
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted" />
          <Input value={globalFilter} onChange={(e) => setGlobalFilter(e.target.value)} placeholder={searchPlaceholder} className="pl-8" aria-label="Search table" />
        </div>
        <div className="ml-auto flex items-center gap-2">
          {toolbar}
          {exportName && data.length > 0 && (
            <Button variant="secondary" size="sm" onClick={exportCsv}>
              <Download /> CSV
            </Button>
          )}
        </div>
      </div>
      {rows.length === 0 ? (
        <EmptyState title={empty?.title ?? "Nothing here yet"} description={empty?.description} action={empty?.action} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-canvas/60 text-left text-xs uppercase tracking-wide text-muted">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => {
                    const sorted = h.column.getIsSorted();
                    const meta = h.column.columnDef.meta as { numeric?: boolean } | undefined;
                    return (
                      <th key={h.id} className={cn("px-4 py-2 font-medium", meta?.numeric && "text-right")}>
                        {h.isPlaceholder ? null : h.column.getCanSort() ? (
                          <button className="inline-flex items-center gap-1 hover:text-ink" onClick={h.column.getToggleSortingHandler()}>
                            {flexRender(h.column.columnDef.header, h.getContext())}
                            {sorted === "asc" ? <ArrowUp className="size-3" /> : sorted === "desc" ? <ArrowDown className="size-3" /> : null}
                          </button>
                        ) : (
                          flexRender(h.column.columnDef.header, h.getContext())
                        )}
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className={cn("border-t border-border", onRowClick && "cursor-pointer hover:bg-brand-50/40")}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(row.original) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                >
                  {row.getVisibleCells().map((cell) => {
                    const meta = cell.column.columnDef.meta as { numeric?: boolean } | undefined;
                    return (
                      <td key={cell.id} className={cn("px-4", dense ? "py-1.5" : "py-2.5", meta?.numeric && "num")}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {table.getPageCount() > 1 && (
        <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-2 text-xs text-muted">
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()} · {table.getFilteredRowModel().rows.length} rows
          </span>
          <Button variant="secondary" size="sm" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
            Previous
          </Button>
          <Button variant="secondary" size="sm" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
