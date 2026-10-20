import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function Spinner({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 p-6 text-sm text-muted", className)} role="status">
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <Inbox className="size-8 text-muted/60" />
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="max-w-md text-xs text-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div className="m-4 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <span className="whitespace-pre-line">{message}</span>
    </div>
  );
}
