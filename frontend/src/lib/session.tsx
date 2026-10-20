import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { hub, setCsrfToken } from "./api";
import type { FirmMembership, Session } from "./types";

const FIRM_KEY = "noria.activeFirm";

function readStoredFirm(): string | null {
  try {
    return localStorage.getItem(FIRM_KEY);
  } catch {
    return null;
  }
}

export function useSessionQuery() {
  return useQuery({
    queryKey: ["session"],
    queryFn: async () => {
      const s = await hub.get<Session>("session.bootstrap");
      setCsrfToken(s.csrf_token ?? null);
      return s;
    },
    staleTime: 5 * 60_000,
  });
}

interface Ctx {
  session: Session;
  firm: FirmMembership | null;
  setFirm: (firm: string) => void;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<Ctx | null>(null);

export function SessionProvider({ session, children }: { session: Session; children: React.ReactNode }) {
  const qc = useQueryClient();
  const [firmId, setFirmId] = useState<string | null>(readStoredFirm());
  const firm = useMemo(() => {
    const firms = session.firms ?? [];
    return firms.find((f) => f.firm === firmId) ?? firms[0] ?? null;
  }, [session.firms, firmId]);

  useEffect(() => {
    if (firm) {
      try {
        localStorage.setItem(FIRM_KEY, firm.firm);
      } catch {
        /* storage unavailable */
      }
    }
  }, [firm]);

  const value = useMemo<Ctx>(
    () => ({
      session,
      firm,
      setFirm: (f) => {
        setFirmId(f);
        qc.invalidateQueries();
      },
      refresh: async () => {
        await qc.invalidateQueries({ queryKey: ["session"] });
      },
    }),
    [session, firm, qc],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}

export const MODULE_LABELS: Record<string, string> = {
  core_accounting: "Core Accounting",
  bank_reconciliation: "Bank Reconciliation",
  tax_compliance: "Tax & Compliance",
  payroll: "Payroll",
  document_management: "Documents",
  practice_management: "Practice Management",
  client_portal: "Client Portal",
  advanced_reporting: "Advanced Reporting",
  ai_assistance: "AI Assistance",
};
