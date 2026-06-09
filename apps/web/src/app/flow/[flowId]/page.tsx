"use client";

/**
 * /flow/[flowId] — the universal flow shell route.
 *
 * Every entry mode (Portfolio, One-Asset, Custom Build, …) lands here
 * when launched via `startFlow(flowId, …)`. The page is intentionally
 * thin: it pulls the dynamic param, hands it to <FlowProvider>, and
 * renders whatever <FlowShell /> resolves from the current step.
 *
 * **CRITICAL — every registered FlowDefinition module MUST be imported
 * here as a side-effect.** The registry is populated only when the
 * module's top-level `registerFlow(...)` call runs, which only happens
 * when something `import`s the module. The Home picker and other
 * triggers side-effect-import their target modules too, but a user
 * landing on `/flow/<id>` via deep link / browser refresh / direct URL
 * paste goes through this page ALONE — without these imports the
 * registry is empty and the "Flow not found" branch fires.
 *
 * A regression test in `__tests__/flow-shell-registration.test.tsx`
 * pins this list against the actual files in `lib/flows/`. If you add
 * a new mode module, add it here AND update that test.
 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { FlowProvider, FlowShell } from "@/lib/flows/runtime";
import { getFlow } from "@/lib/flows/registry";
import type { FlowEvent } from "@/lib/flows/types";

// Self-registering FlowDefinition modules. Each import has the
// side-effect of `registerFlow(...)` at module load. New modes append
// to this list (e.g. PRD-15 thesis_mode).
import "@/lib/flows/portfolio-mode";    // PRD-13b
import "@/lib/flows/one-asset-mode";    // Sprint 2 — Mode 1 refactor
import "@/lib/flows/custom-build-mode"; // PRD-16 — Custom Build composer

function handleEvent(event: FlowEvent): void {
  if (process.env.NODE_ENV !== "production") {
    // eslint-disable-next-line no-console
    console.debug("[flow]", event);
  }
  // PostHog wiring lives in a follow-up PRD per PRD-13a non-goals.
}

export default function FlowShellPage() {
  const params = useParams<{ flowId: string }>();
  const flowId = params?.flowId ?? "";
  const flow = flowId ? getFlow(flowId) : undefined;

  if (!flowId) {
    return null;
  }

  if (!flow) {
    return (
      <main className="mx-auto flex max-w-xl flex-col gap-3 px-4 py-16 text-sm">
        <h1 className="text-lg font-semibold">Flow not found</h1>
        <p className="text-muted-foreground">
          No flow is registered for id <code>{flowId}</code>. If you reached
          this page from a CTA, the responsible mode module may not be
          imported yet.
        </p>
        <Link href="/" className="text-primary underline underline-offset-2">
          Back to home
        </Link>
      </main>
    );
  }

  // Default container: 768px (max-w-3xl) — sized for the vertical
  // wizard pattern that one_asset_mode + portfolio_mode use. Flows
  // with a wider canvas (custom_build's 3-pane composer) can override
  // via `FlowDefinition.shellMaxWidthClass`.
  const shellMaxWidthClass = flow.shellMaxWidthClass ?? "max-w-3xl";
  return (
    <FlowProvider flowId={flowId} onEvent={handleEvent}>
      <main className={`mx-auto ${shellMaxWidthClass} px-4 py-10`}>
        <FlowShell />
      </main>
    </FlowProvider>
  );
}
