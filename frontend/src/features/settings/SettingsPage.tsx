import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Textarea } from "@/components/ui/input";
import { hub } from "@/lib/api";
import { money } from "@/lib/format";
import { useSession } from "@/lib/session";

interface Firm {
  name: string;
  firm_name: string;
  firm_type: string;
  status: string;
  kra_pin?: string;
  registration_number?: string;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  my_role: string;
  max_clients?: number;
  active_clients: number;
  monthly_retainers: number;
  modules: { name: string; title: string; description: string; is_core: number; enabled: boolean }[];
}

export function SettingsPage() {
  const { firm } = useSession();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["firm", firm?.firm], queryFn: () => hub.get<Firm>("firm.get", { firm: firm?.firm }), enabled: !!firm });
  const [v, setV] = useState<Partial<Firm>>({});
  useEffect(() => {
    if (q.data) setV(q.data);
  }, [q.data]);
  const save = useMutation({
    mutationFn: () => hub.post("firm.update", { firm: firm?.firm, firm_name: v.firm_name, kra_pin: v.kra_pin, registration_number: v.registration_number, email: v.email, phone: v.phone, address: v.address, city: v.city }),
    onSuccess: () => {
      toast.success("Saved");
      qc.invalidateQueries({ queryKey: ["firm"] });
      qc.invalidateQueries({ queryKey: ["session"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorState error={q.error} />;
  const f = q.data!;
  const admin = f.my_role === "Firm Admin";
  const text = (key: keyof Firm, label: string) => (
    <Field label={label} htmlFor={key}>
      <Input id={key} disabled={!admin} value={(v[key] as string) ?? ""} onChange={(e) => setV({ ...v, [key]: e.target.value })} />
    </Field>
  );
  return (
    <div>
      <PageHeader title="Settings" description={`${f.firm_type} · ${f.active_clients} active clients · retainers ${money(f.monthly_retainers)}/month`} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Firm details" />
          <CardBody className="grid gap-3 sm:grid-cols-2">
            {text("firm_name", "Firm name")}
            {text("kra_pin", "KRA PIN")}
            {text("registration_number", "Registration number")}
            {text("email", "Email")}
            {text("phone", "Phone")}
            {text("city", "City")}
            <Field label="Address" htmlFor="address" className="sm:col-span-2">
              <Textarea id="address" disabled={!admin} value={v.address ?? ""} onChange={(e) => setV({ ...v, address: e.target.value })} />
            </Field>
            {admin && (
              <div className="flex justify-end sm:col-span-2">
                <Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button>
              </div>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Subscription modules" description="Entitlements are enforced by the server for every request. Contact Noria to change your plan." />
          <ul className="divide-y divide-border">
            {f.modules.map((m) => (
              <li key={m.name} className="flex items-start gap-3 px-5 py-3">
                <div className="flex-1">
                  <div className="text-sm font-medium">{m.title}</div>
                  <div className="text-xs text-muted">{m.description}</div>
                </div>
                <Badge tone={m.enabled ? "green" : "gray"}>{m.is_core ? "Included" : m.enabled ? "Enabled" : "Not in plan"}</Badge>
              </li>
            ))}
          </ul>
          {f.max_clients ? <p className="px-5 pb-4 text-xs text-muted">Plan limit: {f.max_clients} active clients</p> : null}
        </Card>
      </div>
    </div>
  );
}
