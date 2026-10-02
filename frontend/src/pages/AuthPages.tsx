/** Authentication screens (sections 62, 68). */

import { motion } from "framer-motion";
import { ArrowRight, CheckCircle, Database, Network, Route, Zap } from "lucide-react";
import * as React from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { itemVariants, listVariants, transition } from "@/animations";
import { Mark } from "@/components/layout/AppShell";
import { Alert, Button, Card, CardBody, Field, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useSession } from "@/stores/session";

function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-ground px-4 py-10">
      <div className="pointer-events-none absolute inset-0 grid-field opacity-40" />

      <motion.div
        variants={listVariants}
        initial="initial"
        animate="animate"
        className="relative grid w-full max-w-4xl gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)] lg:items-center"
      >
        {/* The product thesis, stated where a new reader will actually see it. */}
        <motion.div variants={itemVariants} className="hidden lg:block">
          <div className="flex items-center gap-2.5">
            <Mark className="size-7" />
            <span className="text-lg font-semibold tracking-[-0.01em] text-ink">SerpFlow</span>
          </div>
          <h1 className="mt-6 max-w-md text-2xl font-semibold leading-tight tracking-[-0.015em] text-ink text-balance">
            A search control plane for SerpApi
          </h1>
          <p className="mt-3 max-w-md text-[13px] leading-relaxed text-ink-muted text-pretty">
            SerpFlow does not merely cache search results. It generates several valid plans for
            an intent, inspects what is already warm, computes each plan's marginal cost, and
            re-ranks on that. The plan it executes is often not the plan it would have chosen
            cold.
          </p>

          <ul className="mt-7 space-y-3">
            <Point
              icon={Network}
              title="Routes across the whole catalog"
              body="Typed dependency edges make multi-hop chains computable instead of guessed, so engines nobody chains by hand become reachable."
            />
            <Point
              icon={Database}
              title="Four cache layers"
              body="Exact, semantic with a deterministic entity guard, the SerpApi Searches Archive, then live. Only the last one spends."
            />
            <Point
              icon={Zap}
              title="Re-plans on cache state"
              body="Marginal cost, not cold cost. Warm steps change which plan wins."
            />
          </ul>
        </motion.div>

        <motion.div variants={itemVariants}>
          <Card className="shadow-[var(--shadow-float)]">
            <CardBody className="space-y-5 p-6">
              <div className="lg:hidden">
                <Mark className="size-7" />
              </div>
              <div>
                <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
                <p className="mt-1 text-[12px] text-ink-subtle text-pretty">{subtitle}</p>
              </div>
              {children}
            </CardBody>
          </Card>
          {footer ? (
            <p className="mt-4 text-center text-[12px] text-ink-subtle">{footer}</p>
          ) : null}
        </motion.div>
      </motion.div>
    </div>
  );
}

function Point({
  icon: Icon,
  title,
  body,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <li className="flex gap-3">
      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-line bg-surface">
        <Icon className="size-3.5 text-accent" />
      </span>
      <div>
        <p className="text-[13px] font-medium text-ink">{title}</p>
        <p className="mt-0.5 text-[12px] leading-relaxed text-ink-subtle text-pretty">{body}</p>
      </div>
    </li>
  );
}

// ------------------------------------------------------------- login
export function LoginPage() {
  const { login, status } = useSession();
  const navigate = useNavigate();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  if (status === "authenticated") return <Navigate to="/app" replace />;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate("/app");
    } catch (loginError) {
      setError(
        loginError instanceof ApiError ? loginError.message : "Could not sign in.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Use the account you created, or the seeded demo owner."
      footer={
        <>
          No account yet?{" "}
          <Link to="/register" className="text-accent hover:underline">
            Create one
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <Field label="Email">
          <Input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="owner@serpflow.dev"
            autoComplete="username"
            required
          />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </Field>
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
          {busy ? "Signing in" : "Sign in"}
          <ArrowRight />
        </Button>
        <p className="text-center text-[12px]">
          <Link to="/forgot-password" className="text-ink-subtle hover:text-accent">
            Forgot your password?
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}

// ---------------------------------------------------------- register
export function RegisterPage() {
  const { register, status } = useSession();
  const navigate = useNavigate();
  const [form, setForm] = React.useState({
    email: "",
    password: "",
    full_name: "",
    organization_name: "",
  });
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  if (status === "authenticated") return <Navigate to="/app" replace />;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register(form);
      navigate("/app");
    } catch (registerError) {
      setError(
        registerError instanceof ApiError
          ? registerError.message
          : "Could not create the account.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Create an account"
      subtitle="You get an organization, a first project, and a 250-credit guard matching the SerpApi free tier."
      footer={
        <>
          Already have one?{" "}
          <Link to="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <Field label="Full name">
          <Input
            value={form.full_name}
            onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            autoComplete="name"
          />
        </Field>
        <Field label="Email">
          <Input
            type="email"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
            autoComplete="username"
            required
          />
        </Field>
        <Field
          label="Password"
          hint="At least ten characters, mixing letters with digits or symbols. Hashed with Argon2id."
        >
          <Input
            type="password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
            autoComplete="new-password"
            minLength={10}
            required
          />
        </Field>
        <Field label="Organization">
          <Input
            value={form.organization_name}
            onChange={(event) => setForm({ ...form, organization_name: event.target.value })}
            placeholder="Acme Research"
          />
        </Field>
        <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
          {busy ? "Creating" : "Create account"}
          <ArrowRight />
        </Button>
      </form>
    </AuthLayout>
  );
}

// --------------------------------------------------- forgot password
export function ForgotPasswordPage() {
  const [email, setEmail] = React.useState("");
  const [sent, setSent] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await api.forgotPassword(email);
    } catch {
      /* the response is identical either way */
    }
    setSent(true);
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="We send a link if the address has an account."
      footer={
        <Link to="/login" className="text-accent hover:underline">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <Alert tone="accent" icon={CheckCircle}>
          If that address has an account, a reset link has been sent. The response is the same
          either way, so this page cannot be used to discover who has an account.
        </Alert>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email">
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </Field>
          <Button type="submit" variant="primary" size="lg" className="w-full">
            Send reset link
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}

// ---------------------------------------------------- reset password
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const token = params.get("token") ?? "";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api.resetPassword(token, password);
      toast.success(result.message);
      navigate("/login");
    } catch (error) {
      toast.error("Could not reset the password", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle="Every existing session is revoked when the password changes."
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="New password" hint="At least ten characters.">
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={10}
            required
          />
        </Field>
        <Button
          type="submit"
          variant="primary"
          size="lg"
          className="w-full"
          disabled={busy || !token}
        >
          Update password
        </Button>
        {!token ? (
          <Alert tone="caution">
            This page needs the token from your reset link.
          </Alert>
        ) : null}
      </form>
    </AuthLayout>
  );
}

// ------------------------------------------------------ verify email
export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const [state, setState] = React.useState<"pending" | "ok" | "error">("pending");
  const token = params.get("token");

  React.useEffect(() => {
    if (!token) {
      setState("error");
      return;
    }
    api
      .verifyEmail(token)
      .then(() => setState("ok"))
      .catch(() => setState("error"));
  }, [token]);

  return (
    <AuthLayout
      title="Verify your email"
      subtitle="This confirms the address on your account."
      footer={
        <Link to="/login" className="text-accent hover:underline">
          Continue to sign in
        </Link>
      }
    >
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={transition()}>
        {state === "pending" ? (
          <p className="text-[13px] text-ink-muted">Verifying.</p>
        ) : state === "ok" ? (
          <Alert tone="warm" icon={CheckCircle} title="Email verified">
            You can sign in now.
          </Alert>
        ) : (
          <Alert tone="danger" icon={Route} title="That link did not work">
            It may have already been used, or the token is missing.
          </Alert>
        )}
      </motion.div>
    </AuthLayout>
  );
}
