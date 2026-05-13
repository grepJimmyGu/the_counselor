"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Route } from "next";

const ERROR_MESSAGES: Record<string, string> = {
  OAuthSignin: "Error starting sign-in. Please try again.",
  OAuthCallback: "Error during sign-in callback. Please try again.",
  OAuthCreateAccount: "Could not create account. Please try a different method.",
  EmailCreateAccount: "Could not create account with this email.",
  Callback: "An error occurred during authentication.",
  Default: "An unexpected error occurred. Please try again.",
};

function AuthErrorContent() {
  const searchParams = useSearchParams();
  const errorCode = searchParams.get("error") ?? "Default";
  const message = ERROR_MESSAGES[errorCode] ?? ERROR_MESSAGES.Default;

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className="mx-auto inline-flex h-12 w-12 items-center justify-center rounded-xl bg-destructive/10">
          <AlertTriangle className="h-6 w-6 text-destructive" />
        </div>
        <div>
          <h1 className="font-heading text-xl font-bold">Sign-in failed</h1>
          <p className="mt-2 text-sm text-muted-foreground">{message}</p>
        </div>
        <div className="flex flex-col gap-2">
          <Button asChild variant="default">
            <Link href={"/auth/signin" as Route}>Try again</Link>
          </Button>
          <Button asChild variant="ghost">
            <Link href={"/" as Route}>Continue without signing in</Link>
          </Button>
        </div>
      </div>
    </main>
  );
}

export default function AuthErrorPage() {
  return (
    <Suspense fallback={null}>
      <AuthErrorContent />
    </Suspense>
  );
}
