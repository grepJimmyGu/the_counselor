"use client";

/**
 * /account/rules — the rules you've decided to follow.
 *
 * PRD-43e §3.3. A finding that lives only on the page that produced it
 * evaporates when the tab closes; this is where one goes to survive. For many
 * users this page IS the product's endpoint — a short list of things they've
 * decided about how they trade — and constraint 6 means nothing here pushes
 * them toward a Playbook they didn't ask for.
 *
 * Trap #19: reads `backendToken` off `useSession()` and waits for the session
 * to resolve before fetching, so a signed-in user never fires the first
 * request anonymously during NextAuth's loading window.
 */

import { useSession } from "next-auth/react";
import { Loader2 } from "lucide-react";

import { MyRules } from "@/components/rules/my-rules";

export default function RulesPage() {
  const { data: session, status } = useSession();
  const backendToken = (session as { backendToken?: string } | null)?.backendToken;

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight text-foreground">
        My rules
      </h1>
      <p className="mt-2 max-w-prose text-sm text-muted-foreground">
        Things you&rsquo;ve decided about how you trade. Some come from what
        your own record showed; some you wrote yourself. They stay here whether
        or not you ever build anything on top of them.
      </p>

      <div className="mt-8">
        {status === "loading" ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : backendToken ? (
          <MyRules backendToken={backendToken} />
        ) : (
          <p className="text-[13px] text-muted-foreground" data-testid="rules-signed-out">
            Sign in to see your rules.
          </p>
        )}
      </div>
    </main>
  );
}
