/**
 * PRD-16b-2 — CustomBuildCanvas.
 *
 * The compose-signals step in the `custom_build_mode` flow. Three-pane
 * layout:
 *   - Left: <SignalCatalogBrowser /> (PRD-16a) for picking primitives.
 *     Clicking a card appends a `BuildRule` to context.rules.
 *   - Center: the user's rules list with `<CustomBuildRuleCard>` +
 *     `<CustomBuildRuleComposer>` (AND/OR) between them, plus the
 *     `<CustomBuildActiveExecutionScaffold>` (pitfall B placeholder).
 *   - Right: <RecommendedDefaultsPanel /> placeholder. PRD-16b-3
 *     wraps PRD-16a's <TemplateMatchSuggestion> here.
 *
 * State lives in the flow context (mutated via `updateContext`). Auto-
 * save / draft sync is a future polish item — for now the runtime
 * already persists context to sessionStorage with a 250ms debounce, so
 * a quick tab-close-then-reopen restores work.
 */
"use client";

import { useCallback, useMemo, useState } from "react";

import { SignalCatalogBrowser } from "@/components/signal-library/signal-catalog-browser";
import { TemplateMatchSuggestion } from "@/components/signal-library/template-match-suggestion";
import type {
  SignalPrimitive,
  StrategyJson,
  TemplateMatch,
} from "@/lib/contracts";
import {
  activeExecutionNeedsExitLadder,
  applyTemplateThresholdsToRules,
  buildCustomBuildStrategyJson,
} from "@/lib/flows/custom-build-strategy-json";
import type {
  BuildRule,
  CustomBuildModeContext,
} from "@/lib/flows/custom-build-mode-context";
import type { FlowStepProps } from "@/lib/flows/types";
import { useFlowCopy } from "@/lib/flows/copy";
import { cn } from "@/lib/utils";
import { validateExitLadder } from "./exit-ladder-editor";

import { BarResolutionPicker } from "./bar-resolution-picker";
import { CustomBuildActiveExecutionScaffold } from "./custom-build-active-execution-scaffold";
import { CustomBuildRuleCard } from "./custom-build-rule-card";
import { CustomBuildRuleComposer } from "./custom-build-rule-composer";
import { ExitLadderEditor } from "./exit-ladder-editor";
import { ScreenMatchCount } from "./screen-match-count";
import { UniverseSelector, isStandingUniverse } from "./universe-selector";

// Default threshold for a freshly added rule. The primitive's
// `default_thresholds` may have keys like "upper" / "lower" / "min_yield";
// for v1 we keep the threshold field unset on add and let the user fill
// it in — that surfaces the choice instead of pretending we know it.
function newBuildRule(primitive: SignalPrimitive): BuildRule {
  return {
    uid: `${primitive.id}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    primitive_id: primitive.id,
    primitive,
    primitive_params: {},
    operator: "gt",
    threshold: undefined,
    logic_with_prior: null,
  };
}

export function CustomBuildCanvas({
  context,
  updateContext,
  advance,
}: FlowStepProps<CustomBuildModeContext>) {
  const [runError, setRunError] = useState<string | null>(null);
  const runBacktestLabel = useFlowCopy(
    "custom_build_mode",
    "compose_run_backtest",
  );

  const selectedIds = useMemo(
    () => new Set(context.rules.map((r) => r.primitive_id)),
    [context.rules],
  );

  const handlePick = useCallback(
    (primitive: SignalPrimitive) => {
      const isFirst = context.rules.length === 0;
      const next = newBuildRule(primitive);
      if (!isFirst) next.logic_with_prior = "AND";
      updateContext({ rules: [...context.rules, next] });
    },
    [context.rules, updateContext],
  );

  const updateRule = useCallback(
    (uid: string, patch: BuildRule) => {
      updateContext({
        rules: context.rules.map((r) => (r.uid === uid ? patch : r)),
      });
    },
    [context.rules, updateContext],
  );

  const removeRule = useCallback(
    (uid: string) => {
      const nextRules = context.rules.filter((r) => r.uid !== uid);
      // After removal, the new rules[0] must have logic_with_prior=null
      // (backend validator enforces this).
      if (nextRules.length > 0 && nextRules[0].logic_with_prior !== null) {
        nextRules[0] = { ...nextRules[0], logic_with_prior: null };
      }
      updateContext({ rules: nextRules });
    },
    [context.rules, updateContext],
  );

  const setComposerForIndex = useCallback(
    (index: number, value: "AND" | "OR") => {
      const nextRules = [...context.rules];
      nextRules[index] = { ...nextRules[index], logic_with_prior: value };
      updateContext({ rules: nextRules });
    },
    [context.rules, updateContext],
  );

  const handleUseTemplateDefaults = useCallback(
    (match: TemplateMatch) => {
      const nextRules = applyTemplateThresholdsToRules(
        context.rules,
        match.thresholds_for_user_primitives,
      );
      updateContext({ rules: nextRules });
    },
    [context.rules, updateContext],
  );

  const primitiveIds = useMemo(
    () => context.rules.map((r) => r.primitive_id),
    [context.rules],
  );

  // PRD-16c live-tracking guard. A non-daily active-execution strategy
  // saved with an empty exit ladder is a silent dead-end: the backend
  // bridge `_maybe_create_saved_strategy_for_active_execution` only
  // creates the SavedStrategy (which powers /account/strategies + the
  // live dashboard + the monitor cron) when bar_resolution != 'daily'
  // AND the exit ladder is non-empty. Block the advance and surface an
  // inline warning so the user wires a ladder before save. Daily
  // strategies never trip this — they take the standard backtest path.
  const needsExitLadder = activeExecutionNeedsExitLadder(context);

  return (
    <div className="flex flex-col gap-4">
      {/* PRD-23b — universe selector (replaces the bare symbol input). A single
          symbol is a universe of size 1; standing universes (sp500/sector)
          screen the market via scan→rank, with a live match-count funnel. */}
      <section
        data-testid="custom-build-symbol-picker"
        className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4"
      >
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Universe
        </span>
        <UniverseSelector
          universeId={context.universe_id}
          enteredSymbols={context.entered_symbols}
          onChange={({ universe_id, entered_symbols }) => {
            const patch: Partial<CustomBuildModeContext> = {
              universe_id,
              entered_symbols,
            };
            // Mirror the first entered symbol into `symbol` so the existing
            // single-asset backtest path (non-standing) is unchanged.
            if (!isStandingUniverse(universe_id)) {
              patch.symbol = entered_symbols[0] ?? null;
            }
            updateContext(patch);
          }}
        />
        {isStandingUniverse(context.universe_id) && (
          <ScreenMatchCount
            universeId={context.universe_id}
            rules={context.rules}
          />
        )}
      </section>

      {/* Stack vertically until xl (1280px viewport) because the
          catalog browser's internal 180-px-sidebar + 2-column primitive
          grid only fits comfortably once the left column is ~600px+.
          Below xl, stacked is far cleaner than half-collapsed 3-pane. */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.3fr_1fr_300px]">
      {/* Left — catalog browser */}
      <section
        data-testid="custom-build-catalog"
        className="rounded-lg border border-slate-200 bg-white p-4"
      >
        <header className="mb-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Pick primitives
          </p>
          <h2 className="text-sm font-semibold text-slate-900">
            Drag any signal from the catalog
          </h2>
        </header>
        <SignalCatalogBrowser onPick={handlePick} selectedIds={selectedIds} />
      </section>

      {/* Center — composer canvas */}
      <section
        data-testid="custom-build-rules"
        className="flex flex-col gap-3"
      >
        <header>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Your rules
          </p>
          <h2 className="text-sm font-semibold text-slate-900">
            Compose your strategy
          </h2>
        </header>

        {context.rules.length === 0 ? (
          <p
            data-testid="custom-build-empty"
            className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-6 text-center text-[13px] text-slate-500"
          >
            Pick a primitive from the catalog on the left to add your first
            rule.
          </p>
        ) : (
          <div className="flex flex-col gap-0">
            {context.rules.map((rule, index) => (
              <div key={rule.uid} className="flex flex-col gap-0">
                {index > 0 ? (
                  <CustomBuildRuleComposer
                    value={rule.logic_with_prior === "OR" ? "OR" : "AND"}
                    onChange={(next) => setComposerForIndex(index, next)}
                  />
                ) : null}
                <CustomBuildRuleCard
                  rule={rule}
                  index={index}
                  onChange={(next) => updateRule(rule.uid, next)}
                  onRemove={() => removeRule(rule.uid)}
                />
              </div>
            ))}
          </div>
        )}

        <CustomBuildActiveExecutionScaffold
          value={context.active_execution_enabled}
          onChange={(next) =>
            updateContext({ active_execution_enabled: next })
          }
          // PRD-16c flips this from `true` (PRD-16b shipped disabled) to
          // `false` so the toggle is live. The bar-resolution picker and
          // exit-ladder editor reveal below when the toggle is on.
          disabled={false}
        />
        {context.active_execution_enabled && (
          <div
            data-testid="active-execution-controls"
            className="space-y-4 rounded-lg border border-emerald-100 bg-emerald-50/30 p-4"
          >
            <BarResolutionPicker
              value={context.bar_resolution}
              onChange={(next) => updateContext({ bar_resolution: next })}
            />
            <ExitLadderEditor
              value={context.exit_ladder}
              onChange={(next) => updateContext({ exit_ladder: next })}
            />
            {needsExitLadder && (
              <p
                data-testid="active-execution-ladder-required"
                role="alert"
                className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] font-medium leading-snug text-amber-800"
              >
                Active execution needs at least one exit tier — add a
                take-profit or stop to track this live.
              </p>
            )}
          </div>
        )}

        {/* Run backtest CTA. PRD-16 UX wire-up: synthesizes the
            StrategyJson from the canvas state, writes it onto the
            flow context, then calls advance() — the runtime hands off
            to FlowBacktest → FlowReview → FlowSave. */}
        <div
          data-testid="custom-build-run-backtest-row"
          className="mt-2 flex flex-col gap-2"
        >
          <button
            type="button"
            data-testid="custom-build-run-backtest"
            disabled={
              context.rules.length === 0 ||
              // Non-standing (entered symbols) keeps the existing guards: a
              // symbol + a valid exit ladder when active execution is on.
              (!isStandingUniverse(context.universe_id) &&
                (!context.symbol ||
                  (context.active_execution_enabled &&
                    !validateExitLadder(context.exit_ladder).ok) ||
                  needsExitLadder))
            }
            onClick={() => {
              try {
                setRunError(null);
                // Standing universe (sp500/sector) → the screener path: advance
                // to ScreenResults, which runs scan→rank. No StrategyJson is
                // built here (the rank step builds it per-survivor).
                if (isStandingUniverse(context.universe_id)) {
                  advance();
                  return;
                }
                // Entered symbols → the existing direct-backtest path.
                const strategyJson: StrategyJson = buildCustomBuildStrategyJson(
                  context,
                );
                updateContext({
                  strategyJson,
                } as Partial<CustomBuildModeContext>);
                advance();
              } catch (e) {
                setRunError(
                  (e as Error).message ?? "Couldn't build the strategy.",
                );
              }
            }}
            className="self-end rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isStandingUniverse(context.universe_id)
              ? "Screen the market →"
              : runBacktestLabel}
          </button>
          {runError && (
            <p
              data-testid="custom-build-run-backtest-error"
              className="self-end rounded-md border border-rose-200 bg-rose-50 px-3 py-1.5 text-[12px] text-rose-700"
            >
              {runError}
            </p>
          )}
        </div>
      </section>

      {/* Right — recommended defaults */}
      <aside data-testid="custom-build-recommendations">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Suggestions
        </p>
        <TemplateMatchSuggestion
          primitiveIds={primitiveIds}
          onPickTemplate={handleUseTemplateDefaults}
        />
      </aside>
      </div>
    </div>
  );
}
