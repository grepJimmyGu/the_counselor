"use client";

import { Suspense } from "react";
import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import { BarChart2 } from "lucide-react";
import { Button } from "@/components/ui/button";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

function SignInContent() {
  const searchParams = useSearchParams();
  // Validate callbackUrl — must be a relative path to prevent open redirect
  const raw = searchParams.get("callbackUrl") ?? "/";
  const callbackUrl = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        {/* Logo */}
        <div className="text-center">
          <div className="mx-auto mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
            <BarChart2 className="h-6 w-6 text-primary" />
          </div>
          <h1 className="font-heading text-2xl font-bold">Sign in to Livermore</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Save watchlists, track strategies, and join the community
          </p>
        </div>

        {/* Sign-in card */}
        <div className="rounded-xl border border-border bg-white p-6 shadow-sm space-y-4">
          <Button
            onClick={() => signIn("google", { callbackUrl })}
            variant="outline"
            size="lg"
            className="w-full gap-3"
          >
            <GoogleIcon />
            Continue with Google
          </Button>

          <div className="text-center text-xs text-muted-foreground">
            All research features — screener, company analysis,
            sentiment — work without signing in.
          </div>
        </div>

        {/* Trust note */}
        <p className="text-center text-xs text-muted-foreground">
          By signing in you agree to our research-only terms.
          No live trading, no financial advice.
        </p>
      </div>
    </main>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" /></div>}>
      <SignInContent />
    </Suspense>
  );
}
