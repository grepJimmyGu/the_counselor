"use client";

/**
 * <PortfolioSave> — PRD-13b adapter brick.
 *
 * Terminal step of portfolio_mode. Uses the existing `saveStrategy`
 * API helper to persist the backtest result. Requires an authenticated
 * session (backendToken via next-auth).
 *
 * Sprint 1 behavior: a name input + save button. Strategy is saved
 * public by default (matches the modal's Scout-tier behavior).
 * Anonymous / unauthenticated users see a sign-in nudge.
 *
 * Sprint 2 cleanup: this could be folded into a generic <SaveStep>
 * brick once Mode 1 also migrates to the flow runtime. Until then a
 * portfolio_mode-specific adapter is the right minimum.
 */

import * as React from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { saveStrategy, UpgradeRequiredError } from "@/lib/api";
import type { BacktestResult } from "@/lib/contracts";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";

registerModeCopy("portfolio_mode", {
  save_title: "Save this overlay",
  save_subtitle: "Give it a name; we'll add it to your saved strategies.",
  save_label: "Strategy name",
  save_signin: "Sign in to save this strategy.",
  save_error: "Couldn't save. Try again.",
  save_done: "Saved! Redirecting…",
});

interface PortfolioSaveContext extends PortfolioModeContext {
  backtestResult?: BacktestResult;
  savedSlug?: string;
}

export function PortfolioSave({
  context,
  updateContext,
  advance,
}: FlowStepProps<PortfolioSaveContext>) {
  const title = useFlowCopy("portfolio_mode", "save_title");
  const subtitle = useFlowCopy("portfolio_mode", "save_subtitle");
  const label = useFlowCopy("portfolio_mode", "save_label");
  const signinNudge = useFlowCopy("portfolio_mode", "save_signin");
  const errorMsg = useFlowCopy("portfolio_mode", "save_error");
  const doneMsg = useFlowCopy("portfolio_mode", "save_done");
  const saveLabel = useFlowCopy("portfolio_mode", "save_button");

  const { data: session } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)?.backendToken;

  const defaultName = context.strategyJson?.strategy_name ?? "Portfolio overlay";
  const [name, setName] = React.useState(defaultName);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const result = context.backtestResult;
  const sj = context.strategyJson;

  const onSave = async () => {
    if (!backendToken) {
      setError(signinNudge);
      return;
    }
    if (!result || !sj) {
      setError("Missing backtest result or strategy.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const { slug } = await saveStrategy(
        backendToken,
        result.backtest_id,
        name.trim() || defaultName,
        /* isPublic */ true,
        result as unknown as object,
        sj.strategy_type,
      );
      updateContext({ savedSlug: slug } as Partial<PortfolioSaveContext>);
      // Terminal step — `advance()` fires onComplete which navigates
      // away from /flow/portfolio_mode to the saved-strategies surface.
      advance();
    } catch (err: unknown) {
      if (err instanceof UpgradeRequiredError) {
        setError(err.entitlement.detail);
      } else {
        setError(errorMsg);
      }
      setSaving(false);
    }
  };

  if (!result || !sj) {
    return (
      <section className="space-y-3" data-testid="portfolio-save-empty">
        <p className="text-sm text-red-600">No backtest result to save.</p>
      </section>
    );
  }

  return (
    <section className="space-y-6" data-testid="portfolio-save">
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <div className="grid gap-2">
        <label className="text-xs font-medium text-muted-foreground">{label}</label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Defensive overlay on my book"
          data-testid="portfolio-save-name"
        />
      </div>

      {error ? (
        <p className="text-sm text-red-600" data-testid="portfolio-save-error">
          {error}
        </p>
      ) : null}

      {context.savedSlug ? (
        <p className="text-sm text-green-700" data-testid="portfolio-save-done">
          {doneMsg}
        </p>
      ) : null}

      <div>
        <Button
          onClick={onSave}
          disabled={saving || !name.trim() || !!context.savedSlug}
          data-testid="portfolio-save-submit"
        >
          {saveLabel}
        </Button>
      </div>
    </section>
  );
}
