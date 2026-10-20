import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ledger } from "@/lib/api";
import type { Account } from "@/lib/types";

export function useLedger<T>(client: string, op: string, args: Record<string, unknown> = {}, enabled = true) {
  return useQuery({ queryKey: ["ledger", client, op, args], queryFn: () => ledger<T>(client, op, args), enabled });
}

/** Write operation; refreshes all ledger queries for the client on success. */
export function useLedgerMutation<T = unknown>(client: string, op: string, success?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: Record<string, unknown>) => ledger<T>(client, op, args),
    onSuccess: () => {
      if (success) toast.success(success);
      qc.invalidateQueries({ queryKey: ["ledger", client] });
      qc.invalidateQueries({ queryKey: ["client", client] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });
}

export function usePostableAccounts(client: string, filter: { root_type?: string; account_type?: string } = {}) {
  return useLedger<Account[]>(client, "postable_accounts", filter);
}

export function newIdempotencyKey(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}
