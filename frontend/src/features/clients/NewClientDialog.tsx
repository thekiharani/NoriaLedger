import { useForm } from "@tanstack/react-form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { ErrorState } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/input";
import { hub } from "@/lib/api";
import { MODULE_LABELS } from "@/lib/session";

const schema = z.object({
  business_name: z.string().trim().min(2, "Required"),
  kra_pin: z.string().trim().regex(/^$|^[A-Z]\d{9}[A-Z]$/i, "Format: P051234567X"),
  business_type: z.string(),
  industry: z.string(),
  email: z.union([z.literal(""), z.email("Invalid email")]),
  phone: z.string(),
  fiscal_year_start: z.iso.date("Pick a date"),
  chart_of_accounts: z.enum(["Standard with Numbers", "Standard"]),
  vat_registered: z.boolean(),
  monthly_retainer: z.string().regex(/^$|^\d+(\.\d{1,2})?$/, "Amount, e.g. 25000"),
  services: z.array(z.string()),
});

export function NewClientDialog({ open, onOpenChange, firm, modules }: { open: boolean; onOpenChange: (v: boolean) => void; firm: string; modules: string[] }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const year = new Date().getFullYear();
  const create = useMutation({
    mutationFn: (v: z.infer<typeof schema>) =>
      hub.post<{ name: string }>("clients.create", {
        firm,
        ...v,
        kra_pin: v.kra_pin || undefined,
        monthly_retainer: v.monthly_retainer ? Number(v.monthly_retainer) : 0,
        provision: true,
      }),
    onSuccess: (r) => {
      toast.success("Client created. Its accounting workspace is being provisioned.");
      qc.invalidateQueries({ queryKey: ["clients"] });
      onOpenChange(false);
      navigate({ to: "/clients/$clientId", params: { clientId: r.name } });
    },
  });
  const optional = modules.filter((m) => m !== "core_accounting");
  const form = useForm({
    defaultValues: {
      business_name: "",
      kra_pin: "",
      business_type: "Limited Company",
      industry: "",
      email: "",
      phone: "",
      fiscal_year_start: `${year}-01-01`,
      chart_of_accounts: "Standard with Numbers" as "Standard with Numbers" | "Standard",
      vat_registered: false,
      monthly_retainer: "",
      services: optional,
    },
    validators: { onSubmit: schema },
    onSubmit: ({ value }) => create.mutate(value),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New client" description="Creates the client record, engagement and an isolated ERPNext accounting workspace." wide>
        <form
          className="grid gap-4 sm:grid-cols-2"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            form.handleSubmit();
          }}
        >
          {create.error ? (
            <div className="sm:col-span-2">
              <ErrorState error={create.error} />
            </div>
          ) : null}
          <form.Field name="business_name">
            {(f) => (
              <Field label="Business name" htmlFor="bn" error={f.state.meta.errors[0]?.message} className="sm:col-span-2">
                <Input id="bn" value={f.state.value} onChange={(e) => f.handleChange(e.target.value)} autoFocus />
              </Field>
            )}
          </form.Field>
          <form.Field name="kra_pin">
            {(f) => (
              <Field label="KRA PIN" htmlFor="pin" error={f.state.meta.errors[0]?.message}>
                <Input id="pin" value={f.state.value} onChange={(e) => f.handleChange(e.target.value.toUpperCase())} placeholder="P051234567X" />
              </Field>
            )}
          </form.Field>
          <form.Field name="business_type">
            {(f) => (
              <Field label="Business type" htmlFor="bt">
                <Select id="bt" value={f.state.value} onChange={(e) => f.handleChange(e.target.value)}>
                  {["Limited Company", "Sole Proprietor", "Partnership", "NGO / Non-profit", "Other"].map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </Select>
              </Field>
            )}
          </form.Field>
          <form.Field name="industry">
            {(f) => (
              <Field label="Industry" htmlFor="ind">
                <Input id="ind" value={f.state.value} onChange={(e) => f.handleChange(e.target.value)} />
              </Field>
            )}
          </form.Field>
          <form.Field name="email">
            {(f) => (
              <Field label="Contact email" htmlFor="em" error={f.state.meta.errors[0]?.message}>
                <Input id="em" type="email" value={f.state.value} onChange={(e) => f.handleChange(e.target.value)} />
              </Field>
            )}
          </form.Field>
          <form.Field name="fiscal_year_start">
            {(f) => (
              <Field label="Fiscal year starts" htmlFor="fy" error={f.state.meta.errors[0]?.message}>
                <Input id="fy" type="date" value={f.state.value} onChange={(e) => f.handleChange(e.target.value)} />
              </Field>
            )}
          </form.Field>
          <form.Field name="chart_of_accounts">
            {(f) => (
              <Field label="Chart of accounts" htmlFor="coa" hint="ERPNext standard chart template">
                <Select id="coa" value={f.state.value} onChange={(e) => f.handleChange(e.target.value as typeof f.state.value)}>
                  <option>Standard with Numbers</option>
                  <option>Standard</option>
                </Select>
              </Field>
            )}
          </form.Field>
          <form.Field name="monthly_retainer">
            {(f) => (
              <Field label="Monthly retainer (KES)" htmlFor="ret" error={f.state.meta.errors[0]?.message}>
                <Input id="ret" inputMode="decimal" value={f.state.value} onChange={(e) => f.handleChange(e.target.value)} />
              </Field>
            )}
          </form.Field>
          <form.Field name="vat_registered">
            {(f) => (
              <label className="flex items-center gap-2 self-end pb-2 text-sm">
                <input type="checkbox" checked={f.state.value} onChange={(e) => f.handleChange(e.target.checked)} /> VAT registered
              </label>
            )}
          </form.Field>
          <form.Field name="services">
            {(f) => (
              <fieldset className="sm:col-span-2">
                <legend className="mb-2 text-xs font-medium text-ink/80">Services (core accounting is always included)</legend>
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  {optional.map((m) => (
                    <label key={m} className="flex items-center gap-1.5 text-sm">
                      <input
                        type="checkbox"
                        checked={f.state.value.includes(m)}
                        onChange={(e) => f.handleChange(e.target.checked ? [...f.state.value, m] : f.state.value.filter((x) => x !== m))}
                      />
                      {MODULE_LABELS[m] ?? m}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
          </form.Field>
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create client
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
