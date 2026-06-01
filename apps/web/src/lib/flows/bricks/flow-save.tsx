"use client";

/**
 * <FlowSave> — mode-agnostic adapter brick (Sprint 2 / Mode 1 refactor).
 *
 * Terminal save step shared by every mode. Wraps the existing
 * `saveStrategy` API helper and updates `context.savedSlug` so the
 * mode's `onComplete` can navigate to the saved-strategy detail page.
 *
 * Replaces PRD-13b's `<PortfolioSave>`. Behaviour matches the previous
 * brick: a name input + save button, public by default, sign-in nudge
 * when the user is unauthenticated.
 */

import * as React from "react";
import { useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { saveStrategy, UpgradeRequiredError } from "@/lib/api";
import type { BacktestResult, StrategyJson } from "@/lib/contracts";
import type { FlowContextBase, FlowStepProps } from "../types";
import { useFlowCopy } from "../copy";
import { useFlowState } from "../runtime";

export interface FlowSaveContext extends FlowContextBase {
  strategyJson?: StrategyJson;
  backtestResult?: BacktestResult;
  savedSlug?: string;
}

export function FlowSave({
  context,
  updateContext,
  advance,
}: FlowStepProps<FlowSaveContext>) {
  const { flow } = useFlowState();
  const modeId = flow.id;

  const title = useFlowCopy(modeId, "save_title");
  const subtitle = useFlowCopy(modeId, "save_subtitle");
  const labelCopy = useFlowCopy(modeId, "save_label");
  const placeholder = useFlowCopy(modeId, "save_placeholder");
  const signinNudge = useFlowCopy(modeId, "save_signin");
  const errorMsg = useFlowCopy(modeId, "save_error");
  const doneMsg = useFlowCopy(modeId, "save_done");
  const saveLabel = useFlowCopy(modeId, "save_button");

  const { data: session } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)?.backendToken;

  const defaultName = context.strategyJson?.strategy_name ?? "Saved strategy";
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
      updateContext({ savedSlug: slug } as Partial<FlowSaveContext>);
      // Terminal step — `advance()` fires onComplete which navigates
      // away from /flow/<modeId> to the saved-strategy detail page.
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
      <section className="space-y-3" data-testid="flow-save-empty">
        <p className="text-sm text-red-600">No backtest result to save.</p>
      </section>
    );
  }

  return (
    <section className="space-y-6" data-testid="flow-save">
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <div className="grid gap-2">
        <label className="text-xs font-medium text-muted-foreground">{labelCopy}</label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={placeholder}
          data-testid="flow-save-name"
        />
      </div>

      {error ? (
        <p className="text-sm text-red-600" data-testid="flow-save-error">
          {error}
        </p>
      ) : null}

      {context.savedSlug ? (
        <p className="text-sm text-green-700" data-testid="flow-save-done">
          {doneMsg}
        </p>
      ) : null}

      <div>
        <Button
          onClick={onSave}
          disabled={saving || !name.trim() || !!context.savedSlug}
          data-testid="flow-save-submit"
        >
          {saveLabel}
        </Button>
      </div>
    </section>
  );
}
