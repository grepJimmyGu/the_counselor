"use client";

/**
 * /flow/[flowId] — the universal flow shell route.
 *
 * Every entry mode (Portfolio, Thesis, Custom Build…) lands here when
 * launched via `startFlow(flowId, …)`. The page is intentionally thin:
 * it pulls the dynamic param, hands it to <FlowProvider>, and renders
 * whatever <FlowShell /> resolves from the current step.
 *
 * PRD-13b ships the first real flow (`portfolio_mode`); until then the
 * mock flow below is what dev smokes against at `/flow/mock_flow`.
 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { FlowProvider, FlowShell } from "@/lib/flows/runtime";
import { getFlow, registerFlow } from "@/lib/flows/registry";
import type { FlowEvent } from "@/lib/flows/types";
import { MockFlow } from "@/lib/flows/__tests__/fixtures/mock-flow";

// Idempotent registration of the PRD-13a mock flow so /flow/mock_flow
// works in dev. PRD-13b adds `import "@/lib/flows/portfolio-mode"` (a
// self-registering module) right here, and any future mode the same way.
if (!getFlow(MockFlow.id)) {
  registerFlow(MockFlow);
}

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

  return (
    <FlowProvider flowId={flowId} onEvent={handleEvent}>
      <main className="mx-auto max-w-3xl px-4 py-10">
        <FlowShell />
      </main>
    </FlowProvider>
  );
}
