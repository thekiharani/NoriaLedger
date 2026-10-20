/**
 * Noria hub API client.
 *
 * All calls go to /api/method/noria_practice.* on the same origin (the edge pins
 * them to the hub site). Session auth uses Frappe's HttpOnly `sid` cookie; state
 * changing requests carry the CSRF token obtained from session.bootstrap.
 */

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

export class ApiError extends Error {
  status: number;
  type?: string;
  constructor(message: string, status: number, type?: string) {
    super(message);
    this.status = status;
    this.type = type;
  }
}

function extractMessage(body: Record<string, unknown>, fallback: string): string {
  const raw = body?._server_messages;
  if (typeof raw === "string") {
    try {
      const msgs = (JSON.parse(raw) as string[])
        .map((m) => {
          try {
            return (JSON.parse(m) as { message?: string }).message ?? "";
          } catch {
            return m;
          }
        })
        .map(stripHtml)
        .filter(Boolean);
      if (msgs.length) return msgs.join("\n");
    } catch {
      /* fall through */
    }
  }
  if (typeof body?.message === "string") return stripHtml(body.message);
  if (typeof body?.exception === "string") {
    const text = body.exception.split(":").slice(1).join(":").trim();
    if (text) return stripHtml(text);
  }
  return fallback;
}

export function stripHtml(s: string) {
  const doc = new DOMParser().parseFromString(s, "text/html");
  return (doc.body.textContent ?? "").trim();
}

async function request<T>(method: "GET" | "POST", path: string, params?: Record<string, unknown>): Promise<T> {
  let url = `/api/method/${path}`;
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: string | undefined;
  if (method === "GET" && params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === "") continue;
      qs.set(k, typeof v === "object" ? JSON.stringify(v) : String(v));
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  } else if (method === "POST") {
    headers["Content-Type"] = "application/json";
    if (csrfToken) headers["X-Frappe-CSRF-Token"] = csrfToken;
    body = JSON.stringify(params ?? {});
  }
  const res = await fetch(url, { method, headers, body, credentials: "same-origin" });
  let data: Record<string, unknown> = {};
  try {
    data = await res.json();
  } catch {
    /* non-JSON */
  }
  if (!res.ok) {
    const fallback =
      res.status === 403 ? "You do not have access to this." : res.status === 429 ? "Too many attempts. Try again later." : "Request failed.";
    throw new ApiError(extractMessage(data, fallback), res.status, data?.exc_type as string | undefined);
  }
  return data.message as T;
}

export const hub = {
  get: <T>(method: string, params?: Record<string, unknown>) => request<T>("GET", `noria_practice.api.${method}`, params),
  post: <T>(method: string, params?: Record<string, unknown>) => request<T>("POST", `noria_practice.api.${method}`, params),
};

/** Accounting operation on a client's books (brokered to the client site). */
export function ledger<T>(client: string, op: string, args: Record<string, unknown> = {}) {
  return hub.post<T>("ledger.call", { client, op, args });
}

export async function login(usr: string, pwd: string, otp?: { tmp_id: string; otp: string }) {
  const payload: Record<string, string> = otp ? { tmp_id: otp.tmp_id, otp: otp.otp, cmd: "login" } : { usr, pwd };
  const res = await fetch("/api/method/login", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
    credentials: "same-origin",
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) throw new ApiError(extractMessage(data, "Invalid email or password."), res.status);
  // Frappe two-factor flow: first response asks for a verification code.
  if (data.verification) {
    return { needsOtp: true as const, tmpId: String(data.tmp_id), prompt: String((data.verification as { prompt?: string }).prompt ?? "") };
  }
  return { needsOtp: false as const };
}

export async function logout() {
  await fetch("/api/method/logout", { method: "POST", credentials: "same-origin" });
  setCsrfToken(null);
}

export async function fileToBase64(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(buf);
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  return btoa(binary);
}

export function downloadBase64(fileName: string, contentType: string, content: string) {
  const bytes = Uint8Array.from(atob(content), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: contentType }));
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
