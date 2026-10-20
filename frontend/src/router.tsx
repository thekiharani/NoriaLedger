import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, createRoute, createRouter, Outlet, redirect } from "@tanstack/react-router";
import { Toaster } from "sonner";
import { z } from "zod";
import { AppShell } from "@/components/layout/AppShell";
import { ErrorState, Spinner } from "@/components/ui/feedback";
import { hub, setCsrfToken } from "@/lib/api";
import { SessionProvider, useSessionQuery } from "@/lib/session";
import type { Session } from "@/lib/types";
import { LoginPage } from "@/features/auth/LoginPage";
import { SignupPage } from "@/features/auth/SignupPage";
import { ClientsPage } from "@/features/clients/ClientsPage";
import { ClientWorkspace } from "@/features/clients/ClientWorkspace";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { PortalClient, PortalHome, PortalReport, PortalShell } from "@/features/portal/Portal";
import { MonthlyReportsPage, ReportDetailPage } from "@/features/reports/MonthlyReports";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { TasksPage } from "@/features/tasks/Tasks";
import { TeamPage } from "@/features/team/TeamPage";

interface RouterContext {
  queryClient: QueryClient;
}

const sessionQuery = {
  queryKey: ["session"],
  queryFn: async () => {
    const s = await hub.get<Session>("session.bootstrap");
    setCsrfToken(s.csrf_token ?? null);
    return s;
  },
  staleTime: 5 * 60_000,
};

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: () => (
    <>
      <Outlet />
      <Toaster richColors position="top-right" />
    </>
  ),
});

function WithSession({ children }: { children: React.ReactNode }) {
  const q = useSessionQuery();
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorState error={q.error} />;
  return <SessionProvider session={q.data}>{children}</SessionProvider>;
}

const loginRoute = createRoute({ getParentRoute: () => rootRoute, path: "/login", component: LoginPage });
const signupRoute = createRoute({ getParentRoute: () => rootRoute, path: "/signup", component: SignupPage });

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  beforeLoad: async ({ context }) => {
    const s = await context.queryClient.ensureQueryData(sessionQuery);
    if (!s.user) throw redirect({ to: "/login" });
    if (!s.firms?.length && s.portal_clients?.length) throw redirect({ to: "/portal" });
  },
  component: () => (
    <WithSession>
      <AppShell />
    </WithSession>
  ),
});

const dashboardRoute = createRoute({ getParentRoute: () => appRoute, path: "/", component: DashboardPage });
const clientsRoute = createRoute({ getParentRoute: () => appRoute, path: "/clients", component: ClientsPage });
const clientRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/clients/$clientId",
  validateSearch: z.object({ tab: z.string().optional() }),
  component: function ClientRouteComponent() {
    const { clientId } = clientRoute.useParams();
    const { tab } = clientRoute.useSearch();
    return <ClientWorkspace clientId={clientId} tab={tab ?? "overview"} />;
  },
});
const tasksRoute = createRoute({ getParentRoute: () => appRoute, path: "/tasks", component: TasksPage });
const reportsRoute = createRoute({ getParentRoute: () => appRoute, path: "/reports", component: MonthlyReportsPage });
const reportRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/reports/$reportId",
  component: function ReportRouteComponent() {
    const { reportId } = reportRoute.useParams();
    return <ReportDetailPage reportId={reportId} />;
  },
});
const teamRoute = createRoute({ getParentRoute: () => appRoute, path: "/team", component: TeamPage });
const settingsRoute = createRoute({ getParentRoute: () => appRoute, path: "/settings", component: SettingsPage });

const portalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/portal",
  beforeLoad: async ({ context }) => {
    const s = await context.queryClient.ensureQueryData(sessionQuery);
    if (!s.user) throw redirect({ to: "/login" });
    if (!s.portal_clients?.length) throw redirect({ to: "/" });
  },
  component: () => (
    <WithSession>
      <PortalShell />
    </WithSession>
  ),
});
const portalHomeRoute = createRoute({ getParentRoute: () => portalRoute, path: "/", component: PortalHome });
const portalClientRoute = createRoute({
  getParentRoute: () => portalRoute,
  path: "/$clientId",
  component: function PortalClientRoute() {
    const { clientId } = portalClientRoute.useParams();
    return <PortalClient clientId={clientId} />;
  },
});
const portalReportRoute = createRoute({
  getParentRoute: () => portalRoute,
  path: "/reports/$reportId",
  component: function PortalReportRoute() {
    const { reportId } = portalReportRoute.useParams();
    return <PortalReport reportId={reportId} />;
  },
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  signupRoute,
  appRoute.addChildren([dashboardRoute, clientsRoute, clientRoute, tasksRoute, reportsRoute, reportRoute, teamRoute, settingsRoute]),
  portalRoute.addChildren([portalHomeRoute, portalClientRoute, portalReportRoute]),
]);

export function makeRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient }, defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof makeRouter>;
  }
}
