/**
 * PRD-16b-2 — RuleCard.
 *
 * Renders one rule in the composer's center pane. Three sub-sections:
 *   1. Primitive name + family (read-only — the user picked it via the
 *      catalog browser; to change the primitive they remove and re-pick).
 *   2. Parameter editors — one input per parameter in
 *      `rule.primitive.parameters`. Numeric inputs for now; sliders are
 *      a polish item.
 *   3. Threshold editor — operator dropdown + numeric input. Hidden if
 *      the primitive returns binary (`donchian_breakout` etc.) — those
 *      have `threshold: undefined` and operate as a 0/1 signal.
 *
 * No drag-and-drop on the v1 card; ordering is via add-to-end. Re-order
 * is a polish item that wires into PRD-16b's `logic_with_prior`
 * left-to-right contract.
 */
"use client";

import type { BuildRule } from "@/lib/flows/custom-build-mode-context";
import { RuleKindEditor } from "@/lib/flows/bricks/custom-build-rule-kind-editor";
import { cn } from "@/lib/utils";

interface Props {
  rule: BuildRule;
  /** Position in the list — index 0 has no leading composer. */
  index: number;
  onChange: (next: BuildRule) => void;
  onRemove: () => void;
  className?: string;
}

export function CustomBuildRuleCard({
  rule,
  index,
  onChange,
  onRemove,
  className,
}: Props) {

  return (
    <article
      data-testid={`rule-card-${rule.uid}`}
      className={cn(
        "rounded-lg border border-slate-200 bg-white p-4 shadow-sm",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Rule {index + 1}
          </p>
          <h3 className="mt-0.5 text-sm font-semibold text-slate-900">
            {rule.primitive.name}
          </h3>
          <p className="text-[12px] text-slate-500 line-clamp-2">
            {rule.primitive.description}
          </p>
        </div>
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove rule"
          data-testid={`rule-remove-${rule.uid}`}
          className="text-[11px] font-medium text-slate-400 hover:text-rose-600"
        >
          Remove
        </button>
      </header>

      {/* Parameter editors */}
      {rule.primitive.parameters.length > 0 ? (
        <fieldset className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
          {rule.primitive.parameters.map((param) => {
            const currentValue =
              rule.primitive_params[param.name] ?? param.default;
            return (
              <label
                key={param.name}
                className="flex flex-col gap-0.5"
                title={param.description}
              >
                <span className="text-[11px] font-medium text-slate-600">
                  {param.name}
                </span>
                <input
                  type={typeof param.default === "number" ? "number" : "text"}
                  value={String(currentValue)}
                  min={param.min_value ?? undefined}
                  max={param.max_value ?? undefined}
                  step={typeof param.default === "number" ? "any" : undefined}
                  onChange={(e) => {
                    const raw = e.target.value;
                    let next: number | string;
                    if (typeof param.default === "number") {
                      const parsed = parseFloat(raw);
                      next = Number.isFinite(parsed) ? parsed : Number(param.default);
                    } else {
                      next = raw;
                    }
                    onChange({
                      ...rule,
                      primitive_params: {
                        ...rule.primitive_params,
                        [param.name]: next,
                      },
                    });
                  }}
                  data-testid={`rule-param-${rule.uid}-${param.name}`}
                  className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[13px] focus:border-slate-400 focus:outline-none"
                />
              </label>
            );
          })}
        </fieldset>
      ) : null}

      {/* Kind-dispatch editor (PRD-22c) — the right input for the
          primitive's output_kind (value threshold / event / level / cross
          direction / regime / distance range / divergence). */}
      <RuleKindEditor rule={rule} onChange={onChange} />
    </article>
  );
}
