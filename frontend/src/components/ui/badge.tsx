import { cn } from "@/lib/utils";

const tones: Record<string, string> = {
  gray: "bg-gray-100 text-gray-700",
  green: "bg-brand-50 text-brand-700",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-red-50 text-red-700",
  blue: "bg-blue-50 text-blue-700",
  purple: "bg-violet-50 text-violet-700",
};

const STATUS_TONES: Record<string, keyof typeof tones> = {
  Active: "green", Ready: "green", Paid: "green", Reconciled: "green", Done: "green", Published: "green", Accepted: "green", Submitted: "green", Approved: "blue",
  Onboarding: "blue", "In Progress": "blue", Queued: "blue", Provisioning: "blue", Uploaded: "blue",
  "In Review": "purple", "Pending Review": "purple",
  Draft: "gray", Open: "gray", Requested: "gray", Saved: "gray", Withdrawn: "gray", Inactive: "gray", Archived: "gray", Cancelled: "gray",
  Unpaid: "amber", "Partly Paid": "amber", Unreconciled: "amber", Suspended: "amber", Return: "amber",
  Overdue: "red", Failed: "red", Rejected: "red",
};

export function Badge({ children, tone, className }: { children: React.ReactNode; tone?: keyof typeof tones; className?: string }) {
  const t = tone ?? (typeof children === "string" ? STATUS_TONES[children] : undefined) ?? "gray";
  return <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", tones[t], className)}>{children}</span>;
}
