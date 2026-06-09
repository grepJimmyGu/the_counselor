/**
 * PRD-16c-5 — ExitLadderEditor.
 *
 * Lets the user assemble a multi-tier exit ladder for their
 * active-execution strategy. Each tier has:
 *
 *   - trigger_pct: signed % from entry (negative = stop, positive = TP)
 *   - action: 'sell_all' (close position) or 'sell_fraction' (partial)
 *   - fraction: required for sell_fraction (0 < f < 1)
 *   - label: optional plain-English label (Stop / TP1 / TP2)
 *
 * The editor enforces the backend validator's constraints inline so the
 * user never sees a 422:
 *   - ≥ 1 stop tier (negative trigger + sell_all)
 *   - tiers ordered ascending by trigger_pct
 *   - sell_fraction tiers have fraction in (0, 1)
 *
 * When inline-invalid, the parent canvas grays out the Continue CTA;
 * the editor surfaces the specific reason in a small badge.
 *
 * Default ladder (when the user enables Active Execution for the first
 * time) is the canonical SpaceX 3-tier:
 *   { Stop: -10%, sell_all }
 *   { TP1: +15%, sell_fraction 0.33 }
 *   { TP2: +30%, sell_all }
 */
"use client";

import { useMemo } from "react";

import type { ExitTier } from "@/lib/flows/custom-build-mode-context";
import { cn } from "@/lib/utils";

interface Props {
  value: ExitTier[];
  onChange: (next: ExitTier[]) => void;
  disabled?: boolean;
  className?: string;
}

export const SPACEX_DEFAULT_LADDER: ExitTier[] = [
  { trigger_pct: -0.1, action: "sell_all", label: "Stop" },
  { trigger_pct: 0.15, action: "sell_fraction", fraction: 0.33, label: "TP1" },
  { trigger_pct: 0.3, action: "sell_all", label: "TP2" },
];

interface ValidationResult {
  ok: boolean;
  reasons: string[];
}

export function validateExitLadder(tiers: ExitTier[]): ValidationResult {
  const reasons: string[] = [];
  if (tiers.length === 0) {
    // Empty is technically "no ladder" — caller branches on length before
    // invoking this. Treat as ok at the editor's tier level.
    return { ok: true, reasons };
  }
  const triggers = tiers.map((t) => t.trigger_pct);
  for (let i = 1; i < triggers.length; i++) {
    if (triggers[i] < triggers[i - 1]) {
      reasons.push("Tiers must be ordered ascending by trigger %.");
      break;
    }
  }
  const hasStop = tiers.some(
    (t) => t.trigger_pct < 0 && t.action === "sell_all",
  );
  if (!hasStop) {
    reasons.push("Need at least one stop tier (negative % + sell all).");
  }
  for (const t of tiers) {
    if (t.action === "sell_fraction") {
      if (t.fraction === undefined || t.fraction <= 0 || t.fraction >= 1) {
        reasons.push("Partial-out fraction must be between 0 and 1.");
        break;
      }
    }
  }
  return { ok: reasons.length === 0, reasons };
}

export function ExitLadderEditor({
  value,
  onChange,
  disabled = false,
  className,
}: Props) {
  const validation = useMemo(() => validateExitLadder(value), [value]);

  const addTier = () => {
    // New tier defaults: stop-like if the ladder is empty, otherwise
    // a +5% TP1 placeholder the user can edit.
    const next: ExitTier =
      value.length === 0
        ? { trigger_pct: -0.1, action: "sell_all", label: "Stop" }
        : {
            trigger_pct: 0.1,
            action: "sell_fraction",
            fraction: 0.33,
            label: `TP${value.length}`,
          };
    onChange([...value, next]);
  };

  const updateTier = (idx: number, patch: Partial<ExitTier>) => {
    onChange(value.map((t, i) => (i === idx ? { ...t, ...patch } : t)));
  };

  const removeTier = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx));
  };

  const useSpaceXDefaults = () => onChange([...SPACEX_DEFAULT_LADDER]);

  return (
    <div
      data-testid="exit-ladder-editor"
      className={cn("space-y-3", disabled && "opacity-50", className)}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Exit ladder
          </p>
          <p className="mt-0.5 text-[12px] leading-snug text-slate-500">
            Tiers fire in order from the lowest trigger %. Each tier
            fires at most once per entry.
          </p>
        </div>
        {value.length === 0 && (
          <button
            type="button"
            onClick={useSpaceXDefaults}
            disabled={disabled}
            data-testid="ladder-use-spacex-defaults"
            className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 hover:bg-emerald-100"
          >
            Use SpaceX defaults
          </button>
        )}
      </div>

      <div className="space-y-2" data-testid="ladder-tiers">
        {value.map((tier, idx) => {
          const pctDisplay = (tier.trigger_pct * 100).toFixed(1);
          return (
            <div
              key={idx}
              data-testid={`ladder-tier-${idx}`}
              className="rounded-md border border-slate-200 bg-white p-2.5"
            >
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="text"
                  value={tier.label ?? ""}
                  onChange={(e) => updateTier(idx, { label: e.target.value })}
                  disabled={disabled}
                  placeholder={idx === 0 ? "Stop" : `TP${idx}`}
                  data-testid={`ladder-tier-${idx}-label`}
                  className="w-20 rounded border border-slate-200 px-2 py-1 text-xs"
                />
                <label className="text-[11px] text-slate-500">Trigger %</label>
                <input
                  type="number"
                  step="0.1"
                  value={pctDisplay}
                  onChange={(e) =>
                    updateTier(idx, {
                      trigger_pct: Number(e.target.value) / 100,
                    })
                  }
                  disabled={disabled}
                  data-testid={`ladder-tier-${idx}-trigger`}
                  className="w-20 rounded border border-slate-200 px-2 py-1 text-xs"
                />
                <span className="text-[11px] text-slate-500">%</span>
                <label className="text-[11px] text-slate-500">Action</label>
                <select
                  value={tier.action}
                  onChange={(e) => {
                    const action = e.target.value as ExitTier["action"];
                    const patch: Partial<ExitTier> = { action };
                    // Reset fraction when toggling actions: sell_all
                    // strips fraction, sell_fraction defaults to 0.33.
                    if (action === "sell_all") patch.fraction = undefined;
                    else if (tier.fraction === undefined) patch.fraction = 0.33;
                    updateTier(idx, patch);
                  }}
                  disabled={disabled}
                  data-testid={`ladder-tier-${idx}-action`}
                  className="rounded border border-slate-200 px-2 py-1 text-xs"
                >
                  <option value="sell_all">Sell all</option>
                  <option value="sell_fraction">Sell fraction</option>
                </select>
                {tier.action === "sell_fraction" && (
                  <>
                    <label className="text-[11px] text-slate-500">
                      Fraction
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      max="0.99"
                      value={tier.fraction ?? 0.33}
                      onChange={(e) =>
                        updateTier(idx, { fraction: Number(e.target.value) })
                      }
                      disabled={disabled}
                      data-testid={`ladder-tier-${idx}-fraction`}
                      className="w-16 rounded border border-slate-200 px-2 py-1 text-xs"
                    />
                  </>
                )}
                <button
                  type="button"
                  onClick={() => removeTier(idx)}
                  disabled={disabled}
                  data-testid={`ladder-tier-${idx}-remove`}
                  className="ml-auto text-[11px] font-medium text-slate-500 hover:text-rose-600"
                >
                  Remove
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={addTier}
        disabled={disabled}
        data-testid="ladder-add-tier"
        className="w-full rounded-md border border-dashed border-slate-300 bg-slate-50 py-1.5 text-[12px] font-semibold text-slate-600 hover:bg-slate-100"
      >
        + Add exit tier
      </button>

      {value.length > 0 && !validation.ok && (
        <ul
          data-testid="ladder-validation-reasons"
          className="space-y-1 rounded-md border border-rose-200 bg-rose-50 p-2 text-[12px] text-rose-700"
        >
          {validation.reasons.map((r, i) => (
            <li key={i}>· {r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
