"use client";

/**
 * /test/flows/portfolio — PRD-13b dev smoke surface.
 *
 * Bare-bones launcher that triggers `portfolio_mode` with a
 * "test/start" fromTrigger. Lets us validate the full flow
 * end-to-end (upload → diagnose → overlay → summary → backtest →
 * review → save) without waiting for PRD-11 to wire the Home CTA.
 *
 * Sprint 2: when PRD-11 lands its Home picker UI, this test page can
 * be kept as a smoke target or deleted — it's intentionally side-effect-
 * only and has no other consumers.
 */

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import "@/lib/flows/portfolio-mode";   // self-registers `portfolio_mode`
import { startFlow } from "@/lib/flows/runtime";

export default function PortfolioFlowTestPage() {
  // If a previous session is still in sessionStorage, jump directly
  // into the shell — saves a click during repeated smoke runs.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const existing = window.sessionStorage.getItem("livermore_flow_portfolio_mode");
    if (existing) {
      window.location.assign("/flow/portfolio_mode");
    }
  }, []);

  const launch = () => {
    startFlow("portfolio_mode", {
      initialContext: { fromTrigger: "test/start" },
    });
  };

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 px-4 py-12">
      <h1 className="text-2xl font-bold">Portfolio Mode — smoke test</h1>
      <p className="text-sm text-muted-foreground">
        Dev surface. Click below to launch <code>portfolio_mode</code>;
        the flow runtime will hand off to <code>/flow/portfolio_mode</code>.
      </p>
      <Button onClick={launch} data-testid="portfolio-test-launch">
        Launch portfolio_mode
      </Button>
    </main>
  );
}
