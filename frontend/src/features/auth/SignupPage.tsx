import { useForm } from "@tanstack/react-form";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/input";
import { hub, login } from "@/lib/api";
import { AuthLayout } from "./LoginPage";

const schema = z.object({
  firm_name: z.string().trim().min(2, "Enter your firm's name"),
  firm_type: z.enum(["Accounting Firm", "Independent Accountant"]),
  full_name: z.string().trim().min(2, "Enter your name"),
  email: z.email("Enter a valid email"),
  password: z.string().min(10, "At least 10 characters"),
  kra_pin: z.string().trim().regex(/^$|^[A-Z]\d{9}[A-Z]$/i, "KRA PIN format: A123456789B"),
});

export function SignupPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const form = useForm({
    defaultValues: { firm_name: "", firm_type: "Accounting Firm" as "Accounting Firm" | "Independent Accountant", full_name: "", email: "", password: "", kra_pin: "" },
    validators: { onSubmit: schema },
    onSubmit: async ({ value }) => {
      setError(null);
      try {
        await hub.post("session.signup_firm", { ...value, kra_pin: value.kra_pin || undefined });
        await login(value.email, value.password);
        await qc.invalidateQueries({ queryKey: ["session"] });
        navigate({ to: "/" });
      } catch (e) {
        setError(e);
      }
    },
  });
  const text = (name: "firm_name" | "full_name" | "email" | "password" | "kra_pin", label: string, type = "text", autoComplete?: string) => (
    <form.Field name={name}>
      {(f) => (
        <Field label={label} htmlFor={name} error={f.state.meta.errors[0]?.message}>
          <Input id={name} type={type} autoComplete={autoComplete} value={f.state.value} onChange={(e) => f.handleChange(e.target.value)} onBlur={f.handleBlur} />
        </Field>
      )}
    </form.Field>
  );
  return (
    <AuthLayout title="Create your firm account" subtitle="Independent accountants and accounting firms.">
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          form.handleSubmit();
        }}
      >
        {error ? <ErrorState error={error} /> : null}
        {text("firm_name", "Firm name")}
        <form.Field name="firm_type">
          {(f) => (
            <Field label="Practice type" htmlFor="firm_type">
              <Select id="firm_type" value={f.state.value} onChange={(e) => f.handleChange(e.target.value as typeof f.state.value)}>
                <option>Accounting Firm</option>
                <option>Independent Accountant</option>
              </Select>
            </Field>
          )}
        </form.Field>
        {text("kra_pin", "Firm KRA PIN (optional)")}
        {text("full_name", "Your name", "text", "name")}
        {text("email", "Work email", "email", "username")}
        {text("password", "Password", "password", "new-password")}
        <form.Subscribe selector={(s) => s.isSubmitting}>
          {(submitting) => (
            <Button type="submit" className="w-full" loading={submitting}>
              Create account
            </Button>
          )}
        </form.Subscribe>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-brand-700 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
