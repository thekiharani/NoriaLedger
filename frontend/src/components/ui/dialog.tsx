import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  title,
  description,
  children,
  className,
  wide,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  wide?: boolean;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/30" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-[8vh] z-50 max-h-[84vh] w-[calc(100vw-2rem)] -translate-x-1/2 overflow-y-auto rounded-lg border border-border bg-white shadow-xl",
          wide ? "max-w-4xl" : "max-w-lg",
          className,
        )}
      >
        <div className="flex items-start justify-between border-b border-border px-5 py-4">
          <div>
            <DialogPrimitive.Title className="text-base font-semibold">{title}</DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="mt-0.5 text-xs text-muted">{description}</DialogPrimitive.Description>
            ) : (
              <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
            )}
          </div>
          <DialogPrimitive.Close className="rounded p-1 text-muted hover:bg-canvas" aria-label="Close">
            <X className="size-4" />
          </DialogPrimitive.Close>
        </div>
        <div className="p-5">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
