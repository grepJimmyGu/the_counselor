"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";
import type { Route } from "next";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

// Resetting a forgotten password: ask for a 6-digit code by email, then type
// the code and a new password. The backend decides everything, including the
// password rules; this page only relays its answers.
export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function sendCode(e?: React.FormEvent) {
    e?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/password/reset/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (res.status === 422) {
        setError("Enter a valid email address.");
      } else if (!res.ok) {
        setError("Something went wrong. Please try again.");
      } else {
        setCode("");
        setStep("code");
      }
    } catch {
      setError("Could not connect to the server.");
    } finally {
      setLoading(false);
    }
  }

  async function resetPassword(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirmation) {
      setError("The two passwords don't match.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/password/reset/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code, new_password: password }),
      });
      if (res.status === 400) {
        // A wrong or expired code, or a password that broke a rule: the
        // backend says which, in words written for the user.
        const body = await res.json().catch(() => null);
        setError(typeof body?.detail === "string" ? body.detail : "That didn't work. Try again.");
        return;
      }
      if (!res.ok) {
        setError("Something went wrong. Please try again.");
        return;
      }
      // The reset is done. Start the site's own session with the new password.
      const result = await signIn("credentials", { email, password, redirect: false });
      router.push((result?.error ? "/login" : "/account") as Route);
    } catch {
      setError("Could not connect to the server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="font-heading text-2xl font-bold">Reset password</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Remembered it?{" "}
            <Link href={"/login" as Route} className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </div>

        {step === "email" ? (
          <form onSubmit={sendCode} className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="email" className="text-sm font-medium">Email</label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
              <p className="text-xs text-muted-foreground">
                We&apos;ll email a 6-digit code to this address. Typing it back lets you choose a new password.
              </p>
            </div>
            <ErrorNote error={error} />
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Email me a code"}
            </Button>
          </form>
        ) : (
          <form onSubmit={resetPassword} className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="code" className="text-sm font-medium">Code from the email</label>
              <Input
                id="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                maxLength={6}
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="6-digit code"
              />
              <p className="text-xs text-muted-foreground">
                If {email} has a Livermore account, a code is on its way. It works for 15 minutes.
                Check the spam folder if it has not arrived.
              </p>
            </div>
            <div className="space-y-1">
              <label htmlFor="new-password" className="text-sm font-medium">New password</label>
              <Input
                id="new-password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={64}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="12 or more characters"
              />
              <p className="text-xs text-muted-foreground">
                12 to 64 characters with an uppercase letter, a lowercase letter, a number and a symbol.
              </p>
            </div>
            <div className="space-y-1">
              <label htmlFor="confirm-password" className="text-sm font-medium">Type it again</label>
              <Input
                id="confirm-password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                required
                value={confirmation}
                onChange={e => setConfirmation(e.target.value)}
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={showPassword}
                onChange={e => setShowPassword(e.target.checked)}
              />
              Show password
            </label>
            <ErrorNote error={error} />
            <Button type="submit" className="w-full" disabled={loading || code.length !== 6}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Set new password"}
            </Button>
            <Button type="button" variant="outline" className="w-full" disabled={loading} onClick={() => sendCode()}>
              Send a new code
            </Button>
          </form>
        )}
      </div>
    </main>
  );
}

function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {error}
    </p>
  );
}
