/**
 * PRD-22c slice (c) — kind-dispatch rule editor.
 *
 * The composer's rule card used to render ONE shape (operator dropdown +
 * threshold input), wrong for 6 of the 7 output kinds. `<RuleKindEditor>`
 * dispatches on the primitive's `output_kind` to a kind-appropriate editor,
 * each serializing to the `StrategyRule` operator the engine learned in
 * slice (a):
 *   value      → ValueRule      ([> | < | …] + threshold)
 *   event      → EventRule      ("fires", no input)
 *   level      → LevelRule      ("is_true", no input)
 *   cross      → CrossRule      ("crosses_up" | "crosses_down")
 *   regime     → RegimeRule     ("equals" 1 | 0)
 *   distance   → DistanceRule   ("in_range" {min,max})
 *   divergence → DivergenceRule ("divergence_bullish" | "divergence_bearish")
 *
 * Each non-VALUE editor ensures the rule's operator matches its kind via a
 * guarded effect — so a primitive arriving with a stale VALUE operator (or no
 * operator) is normalized to the kind default, idempotently.
 */
"use client";

import { useEffect } from "react";
import type { BuildRule } from "@/lib/flows/custom-build-mode-context";
import type { SignalOutputKind } from "@/lib/contracts";
import { cn } from "@/lib/utils";

type Op = NonNullable<BuildRule["operator"]>;

export interface RuleKindEditorProps {
  rule: BuildRule;
  onChange: (next: BuildRule) => void;
}

const VALUE_OPS: ReadonlyArray<{ value: Op; label: string }> = [
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
];
const VALUE_OP_SET = new Set<string>(["gt", "gte", "lt", "lte"]);

// ── Shared bits ──────────────────────────────────────────────────────────────

function Segment({
  value,
  options,
  onSelect,
  ariaLabel,
}: {
  value: string;
  options: ReadonlyArray<{ value: string; label: string }>;
  onSelect: (v: string) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-flex overflow-hidden rounded-md border border-slate-200"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onSelect(o.value)}
          className={cn(
            "px-2.5 py-1 text-[12px] transition-colors",
            value === o.value
              ? "bg-slate-800 text-white"
              : "bg-white text-slate-600 hover:bg-slate-50",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const wrap = "mt-3 flex flex-wrap items-center gap-2 text-[13px] text-slate-700";

/** Normalize the rule's operator to `def` once, when it isn't one of the
 *  kind's `allowed` operators. Guarded so it never loops. */
function useOperatorDefault(
  rule: BuildRule,
  onChange: (next: BuildRule) => void,
  allowed: ReadonlyArray<Op>,
  def: Op,
  threshold: BuildRule["threshold"],
) {
  const current = rule.operator;
  useEffect(() => {
    if (!current || !allowed.includes(current as Op)) {
      onChange({ ...rule, operator: def, threshold });
    }
    // Only resync when the operator changes; guarded above against loops.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current]);
}

// ── Per-kind editors ─────────────────────────────────────────────────────────

function ValueRule({ rule, onChange }: RuleKindEditorProps) {
  const op = typeof rule.operator === "string" && VALUE_OP_SET.has(rule.operator)
    ? rule.operator
    : "gt";
  return (
    <div data-testid="value-rule" className="mt-3 flex items-end gap-2">
      <label className="flex flex-1 flex-col gap-0.5">
        <span className="text-[11px] font-medium text-slate-600">Operator</span>
        <select
          value={op}
          onChange={(e) => onChange({ ...rule, operator: e.target.value as Op })}
          data-testid={`rule-operator-${rule.uid}`}
          className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[13px]"
        >
          {VALUE_OPS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </label>
      <label className="flex flex-1 flex-col gap-0.5">
        <span className="text-[11px] font-medium text-slate-600">Threshold</span>
        <input
          type="number"
          step="any"
          value={typeof rule.threshold === "number" ? rule.threshold : ""}
          onChange={(e) => {
            const parsed = parseFloat(e.target.value);
            onChange({ ...rule, threshold: Number.isFinite(parsed) ? parsed : undefined });
          }}
          data-testid={`rule-threshold-${rule.uid}`}
          placeholder="0"
          className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[13px]"
        />
      </label>
    </div>
  );
}

function EventRule({ rule, onChange }: RuleKindEditorProps) {
  useOperatorDefault(rule, onChange, ["fires"], "fires", undefined);
  return (
    <p data-testid="event-rule" className={wrap}>
      Fires when <strong>{rule.primitive.name}</strong> triggers this bar.
    </p>
  );
}

function LevelRule({ rule, onChange }: RuleKindEditorProps) {
  useOperatorDefault(rule, onChange, ["is_true"], "is_true", undefined);
  return (
    <p data-testid="level-rule" className={wrap}>
      While <strong>{rule.primitive.name}</strong> holds true.
    </p>
  );
}

function CrossRule({ rule, onChange }: RuleKindEditorProps) {
  useOperatorDefault(rule, onChange, ["crosses_up", "crosses_down"], "crosses_up", undefined);
  const dir = rule.operator === "crosses_down" ? "crosses_down" : "crosses_up";
  return (
    <div data-testid="cross-rule" className={wrap}>
      <span>When <strong>{rule.primitive.name}</strong> crosses</span>
      <Segment
        ariaLabel="Cross direction"
        value={dir}
        options={[{ value: "crosses_up", label: "Up" }, { value: "crosses_down", label: "Down" }]}
        onSelect={(v) => onChange({ ...rule, operator: v as Op, threshold: undefined })}
      />
    </div>
  );
}

function RegimeRule({ rule, onChange }: RuleKindEditorProps) {
  useOperatorDefault(rule, onChange, ["equals"], "equals", 1);
  const state = rule.threshold === 0 ? "off" : "on";
  return (
    <div data-testid="regime-rule" className={wrap}>
      <span>When regime is</span>
      <Segment
        ariaLabel="Regime state"
        value={state}
        options={[{ value: "on", label: "On" }, { value: "off", label: "Off" }]}
        onSelect={(v) => onChange({ ...rule, operator: "equals", threshold: v === "on" ? 1 : 0 })}
      />
    </div>
  );
}

function DistanceRule({ rule, onChange }: RuleKindEditorProps) {
  useOperatorDefault(rule, onChange, ["in_range"], "in_range", { min: 0, max: 0 });
  const range =
    rule.threshold && typeof rule.threshold === "object" ? rule.threshold : { min: 0, max: 0 };
  const setBound = (key: "min" | "max", raw: string) => {
    const parsed = parseFloat(raw);
    onChange({
      ...rule,
      operator: "in_range",
      threshold: { ...range, [key]: Number.isFinite(parsed) ? parsed : 0 },
    });
  };
  return (
    <div data-testid="distance-rule" className={wrap}>
      <strong>{rule.primitive.name}</strong>
      <span>between</span>
      <input
        type="number"
        step="any"
        aria-label="min"
        value={range.min}
        onChange={(e) => setBound("min", e.target.value)}
        className="w-16 rounded-md border border-slate-200 bg-white px-2 py-1 text-[13px]"
      />
      <span>%</span>
      <span>and</span>
      <input
        type="number"
        step="any"
        aria-label="max"
        value={range.max}
        onChange={(e) => setBound("max", e.target.value)}
        className="w-16 rounded-md border border-slate-200 bg-white px-2 py-1 text-[13px]"
      />
      <span>%</span>
    </div>
  );
}

function DivergenceRule({ rule, onChange }: RuleKindEditorProps) {
  useOperatorDefault(
    rule, onChange,
    ["divergence_bullish", "divergence_bearish"], "divergence_bullish", undefined,
  );
  const dir = rule.operator === "divergence_bearish" ? "divergence_bearish" : "divergence_bullish";
  return (
    <div data-testid="divergence-rule" className={wrap}>
      <Segment
        ariaLabel="Divergence direction"
        value={dir}
        options={[
          { value: "divergence_bullish", label: "Bullish" },
          { value: "divergence_bearish", label: "Bearish" },
        ]}
        onSelect={(v) => onChange({ ...rule, operator: v as Op, threshold: undefined })}
      />
      <span>divergence on <strong>{rule.primitive.name}</strong></span>
    </div>
  );
}

// ── Dispatch ─────────────────────────────────────────────────────────────────

const KIND_TO_EDITOR: Record<SignalOutputKind, React.FC<RuleKindEditorProps>> = {
  value: ValueRule,
  event: EventRule,
  level: LevelRule,
  cross: CrossRule,
  regime: RegimeRule,
  distance: DistanceRule,
  divergence: DivergenceRule,
};

export function RuleKindEditor({ rule, onChange }: RuleKindEditorProps) {
  const Editor = KIND_TO_EDITOR[rule.primitive.output_kind] ?? ValueRule;
  return <Editor rule={rule} onChange={onChange} />;
}
