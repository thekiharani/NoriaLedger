const moneyFormatters = new Map<string, Intl.NumberFormat>();

export function money(value: number | string | null | undefined, currency = "KES"): string {
  const n = typeof value === "string" ? Number(value) : value ?? 0;
  if (!Number.isFinite(n)) return "—";
  let f = moneyFormatters.get(currency);
  if (!f) {
    f = new Intl.NumberFormat("en-KE", { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2 });
    moneyFormatters.set(currency, f);
  }
  return f.format(n);
}

export function amount(value: number | string | null | undefined): string {
  const n = typeof value === "string" ? Number(value) : value ?? 0;
  if (!Number.isFinite(n) || n === 0) return n === 0 ? "0.00" : "—";
  return new Intl.NumberFormat("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
}

export function date(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-KE", { day: "2-digit", month: "short", year: "numeric" });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-KE", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Previous calendar month as YYYY-MM. */
export function previousPeriod(ref = new Date()): string {
  const d = new Date(ref.getFullYear(), ref.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function periodBounds(period: string): { from: string; to: string } {
  const [y, m] = period.split("-").map(Number);
  const last = new Date(y, m, 0).getDate();
  return { from: `${period}-01`, to: `${period}-${String(last).padStart(2, "0")}` };
}

/** Sum decimal strings exactly at 2dp using integer cents. */
export function sumCents(values: Array<string | number | undefined>): number {
  return values.reduce<number>((acc, v) => acc + toCents(v), 0);
}

export function toCents(v: string | number | undefined | null): number {
  if (v === undefined || v === null || v === "") return 0;
  const s = String(v).trim().replace(/,/g, "");
  if (!/^-?\d+(\.\d{1,2})?$/.test(s)) return Number.NaN;
  const negative = s.startsWith("-");
  const [whole, frac = ""] = s.replace("-", "").split(".");
  const cents = Number(whole) * 100 + Number((frac + "00").slice(0, 2));
  return negative ? -cents : cents;
}

export function centsToString(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

export function toCsv(columns: { key: string; label: string }[], rows: Record<string, unknown>[]): string {
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    // Neutralise spreadsheet formula injection.
    const safe = /^[=+\-@\t\r]/.test(s) && !/^-?\d/.test(s) ? `'${s}` : s;
    return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
  };
  return [columns.map((c) => esc(c.label)).join(","), ...rows.map((r) => columns.map((c) => esc(r[c.key])).join(","))].join("\n");
}

export function downloadText(fileName: string, text: string, type = "text/csv") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
