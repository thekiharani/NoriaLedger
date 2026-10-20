import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/feedback";
import { Textarea } from "@/components/ui/input";
import { hub } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Message {
  name: string;
  sender: string;
  sender_name?: string;
  sender_side: "Firm" | "Client";
  message: string;
  creation: string;
}

export function MessagesPanel({ client, mySide }: { client: string; mySide: "Firm" | "Client" }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["messages", client], queryFn: () => hub.get<Message[]>("messages.list_messages", { client }), refetchInterval: 30_000 });
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: () => hub.post("messages.send", { client, message: text }),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: ["messages", client] });
    },
  });
  return (
    <Card>
      <CardHeader title="Messages" description={mySide === "Firm" ? "Conversation with the client (visible on their portal)." : "Talk to your accountant."} />
      <div className="max-h-[28rem] space-y-3 overflow-y-auto p-5">
        {q.isLoading ? (
          <Spinner />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : !q.data?.length ? (
          <EmptyState title="No messages yet" />
        ) : (
          q.data.map((m) => (
            <div key={m.name} className={cn("max-w-[80%] rounded-lg px-3 py-2 text-sm", m.sender_side === mySide ? "ml-auto bg-brand-50" : "bg-canvas")}>
              <div className="whitespace-pre-line">{m.message}</div>
              <div className="mt-1 text-[11px] text-muted">
                {m.sender_name ?? m.sender} · {dateTime(m.creation)}
              </div>
            </div>
          ))
        )}
      </div>
      <form
        className="flex gap-2 border-t border-border p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) send.mutate();
        }}
      >
        <Textarea className="min-h-10" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write a message…" aria-label="Message" />
        <Button type="submit" loading={send.isPending} disabled={!text.trim()} aria-label="Send">
          <Send />
        </Button>
      </form>
      {send.error ? <ErrorState error={send.error} /> : null}
    </Card>
  );
}
