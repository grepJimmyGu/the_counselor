"use client";

/**
 * <OneAssetTemplatePick> — Mode 1's template picker step.
 *
 * Reuses the existing 5-question `<StrategyWizard>` from
 * `components/strategy-builder/wizard/strategy-wizard.tsx`. The wizard
 * already takes an `initialAsset` (we always set `single_stock` here
 * because Mode 1 is by definition one ticker) and returns a
 * ResearchTemplate + the wizard answers — exactly the shape the next
 * step (`<OneAssetSummary>`) needs.
 *
 * Why reuse rather than replace: the wizard is the canonical UI for
 * picking a strategy template across every surface. Sprint 1's PRD-13b
 * deliberately *didn't* extract it as a flow brick because Mode 1 had
 * not yet migrated to the runtime; this PRD is that migration, and the
 * cleanest path is to wrap the existing component rather than fork it.
 * The wizard component lives outside `lib/flows/bricks/`, but that's
 * fine — the brick file lives here and the composition layer is what
 * matters.
 *
 * If the user picks an unmapped strategy (no `template`), the brick
 * advances *without* setting `context.template` — the summary step will
 * surface an error rather than crash. Same fallback the legacy
 * StrategyBuilderModal uses for that path; a richer "Custom build"
 * landing is Sprint 2 PRD-16's scope, not this PR.
 */

import * as React from "react";
import { StrategyWizard } from "@/components/strategy-builder/wizard/strategy-wizard";
import type {
  WizardAnswers,
  WizardStrategy,
} from "@/components/strategy-builder/wizard/strategy-wizard-data";
import type { ResearchTemplate } from "@/lib/contracts";
import type { RiskPreset } from "@/components/strategy-builder/summary-step";
import type { FlowStepProps } from "../types";
import type { OneAssetModeContext } from "../one-asset-mode-context";

export function OneAssetTemplatePick({
  context,
  updateContext,
  advance,
}: FlowStepProps<OneAssetModeContext>) {
  // Stable callback identities so the wizard's internal effects don't
  // resubscribe on every render of this brick.
  const handlePickTemplate = React.useCallback(
    (payload: {
      template: ResearchTemplate;
      answers: WizardAnswers;
      strategy: WizardStrategy;
    }) => {
      // Mirror StrategyBuilderModal's handleWizardPickTemplate (PR-C,
      // 2026-05-24): seed the risk preset from the wizard's `dd` answer
      // per `risk_control_prompt.md`'s mapping table; the summary step
      // applies it to position_sizing + risk_management before the
      // backtest runs.
      updateContext({
        template: payload.template,
        riskPreset: (payload.answers.dd ?? "medium") as RiskPreset,
      });
      advance();
    },
    [updateContext, advance],
  );

  const handlePickCustom = React.useCallback(() => {
    // No template mapping — advance without `context.template`. The
    // summary brick renders an error-with-back-button state when this
    // happens, which is the lowest-disruption Sprint 2 path. PRD-16
    // (Custom Build) introduces a proper handler for this branch.
    advance();
  }, [advance]);

  const handleDescribeIdea = React.useCallback(() => {
    // Same fallback as handlePickCustom — Mode 1 doesn't carry a
    // "describe your idea" pivot inside the flow. PRD-16 (Custom Build)
    // is the proper home for this branch.
    advance();
  }, [advance]);

  return (
    <section data-testid="one-asset-template-pick" data-ticker={context.ticker}>
      <StrategyWizard
        initialAsset="single_stock"
        onPickTemplate={handlePickTemplate}
        onPickCustom={handlePickCustom}
        onDescribeIdea={handleDescribeIdea}
      />
    </section>
  );
}
