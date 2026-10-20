import { useForm } from "@tanstack/react-form";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { z } from "zod";
import { Logo } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/input";
import { login } from "@/lib/api";
import { useSessionQuery } from "@/lib/session";

const schema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});

export function AuthLayout({ children, title, subtitle }: { children: React.ReactNode; title: string; subtitle?: string }) {
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <Logo className="mb-8 justify-center" />
        <Card className="p-6">
          <h1 className="text-lg font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </Card>
        <p className="mt-6 text-center text-xs text-muted">Noria Technologies Ltd</p>
      </div>
    </div>
  );
}

export function LoginPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const session = useSessionQuery();
  const [error, setError] = useState<unknown>(null);
  const [otp, setOtp] = useState<{ tmpId: string; prompt: string } | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [busy, setBusy] = useState(false);

  const finish = async () => {
    await qc.invalidateQueries({ queryKey: ["session"] });
    navigate({ to: "/" });
  };

  const form = useForm({
    defaultValues: { email: "", password: "" },
    validators: { onSubmit: schema },
    onSubmit: async ({ value }) => {
      setError(null);
      try {
        const res = await login(value.email.trim(), value.password);
        if (res.needsOtp) setOtp({ tmpId: res.tmpId, prompt: res.prompt });
        else await finish();
      } catch (e) {
        setError(e);
      }
    },
  });

  if (otp) {
    return (
      <AuthLayout title="Verification code" subtitle={otp.prompt || "Enter the code from your authenticator app."}>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await login("", "", { tmp_id: otp.tmpId, otp: otpCode });
              await finish();
            } catch (err) {
              setError(err);
            } finally {
              setBusy(false);
            }
          }}
        >
          {error ? <ErrorState error={error} /> : null}
          <Field label="Code" htmlFor="otp">
            <Input id="otp" inputMode="numeric" autoComplete="one-time-code" value={otpCode} onChange={(e) => setOtpCode(e.target.value)} autoFocus />
          </Field>
          <Button type="submit" className="w-full" loading={busy}>
            Verify
          </Button>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Sign in" subtitle="Accounting and practice management for Kenyan firms.">
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          form.handleSubmit();
        }}
      >
        {error ? <ErrorState error={error} /> : null}
        <form.Field name="email">
          {(f) => (
            <Field label="Email" htmlFor="email" error={f.state.meta.errors[0]?.message}>
              <Input id="email" type="email" autoComplete="username" value={f.state.value} onChange={(e) => f.handleChange(e.target.value)} onBlur={f.handleBlur} autoFocus />
            </Field>
          )}
        </form.Field>
        <form.Field name="password">
          {(f) => (
            <Field label="Password" htmlFor="password" error={f.state.meta.errors[0]?.message}>
              <Input id="password" type="password" autoComplete="current-password" value={f.state.value} onChange={(e) => f.handleChange(e.target.value)} onBlur={f.handleBlur} />
            </Field>
          )}
        </form.Field>
        <form.Subscribe selector={(s) => s.isSubmitting}>
          {(submitting) => (
            <Button type="submit" className="w-full" loading={submitting}>
              Sign in
            </Button>
          )}
        </form.Subscribe>
      </form>
      {session.data?.allow_signup && (
        <p className="mt-6 text-center text-sm text-muted">
          New practice?{" "}
          <Link to="/signup" className="font-medium text-brand-700 hover:underline">
            Create a firm account
          </Link>
        </p>
      )}
    </AuthLayout>
  );
}
