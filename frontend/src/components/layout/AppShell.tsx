import { Link, Outlet, useNavigate } from "@tanstack/react-router";
import { Building2, ClipboardList, FileBarChart, LayoutDashboard, LogOut, Settings, Users } from "lucide-react";
import { logout } from "@/lib/api";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { to: "/clients", label: "Clients", icon: Building2 },
  { to: "/tasks", label: "Work queue", icon: ClipboardList },
  { to: "/reports", label: "Monthly reports", icon: FileBarChart },
  { to: "/team", label: "Team", icon: Users },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="grid size-8 place-items-center rounded-lg bg-brand-700 text-sm font-bold text-white">N</div>
      <div className="leading-tight">
        <div className="text-sm font-semibold">Noria Ledger</div>
      </div>
    </div>
  );
}

export function AppShell() {
  const { session, firm, setFirm } = useSession();
  const navigate = useNavigate();
  const firms = session.firms ?? [];

  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-white md:flex">
        <div className="px-4 py-4">
          <Logo />
        </div>
        {firms.length > 0 && (
          <div className="px-3 pb-3">
            {firms.length > 1 ? (
              <select
                className="w-full rounded-md border border-border bg-canvas px-2 py-1.5 text-xs"
                value={firm?.firm}
                onChange={(e) => setFirm(e.target.value)}
                aria-label="Active firm"
              >
                {firms.map((f) => (
                  <option key={f.firm} value={f.firm}>
                    {f.firm_name}
                  </option>
                ))}
              </select>
            ) : (
              <div className="rounded-md bg-canvas px-2 py-1.5 text-xs">
                <div className="font-medium">{firm?.firm_name}</div>
                <div className="text-muted">{firm?.firm_role}</div>
              </div>
            )}
          </div>
        )}
        <nav className="flex-1 space-y-0.5 px-2" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, ...rest }) => (
            <Link
              key={to}
              to={to}
              activeOptions={{ exact: "exact" in rest }}
              className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-ink/80 hover:bg-canvas"
              activeProps={{ className: "bg-brand-50 font-medium text-brand-800 hover:bg-brand-50" }}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-border p-3">
          <div className="truncate text-xs font-medium">{session.full_name}</div>
          <div className="truncate text-xs text-muted">{session.user}</div>
          <button
            className="mt-2 flex items-center gap-1.5 text-xs text-muted hover:text-ink"
            onClick={async () => {
              await logout();
              window.location.href = "/login";
            }}
          >
            <LogOut className="size-3.5" /> Sign out
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-border bg-white px-4 py-2 md:hidden">
          <Logo />
          <select className="rounded border border-border px-2 py-1 text-xs" onChange={(e) => navigate({ to: e.target.value })} aria-label="Navigate">
            {NAV.map((n) => (
              <option key={n.to} value={n.to}>
                {n.label}
              </option>
            ))}
          </select>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl px-4 py-6 md:px-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
