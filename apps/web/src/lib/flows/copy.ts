/**
 * Central label lexicon for flow bricks.
 *
 * Rule (Sprint 1+): no hardcoded user-facing labels inside bricks. All
 * copy flows through `useFlowCopy(modeId, key)`.
 *
 * The 2-arg signature is Sprint-2-ready by design: Mode 3 (Thesis) and
 * Mode 4 (Custom Build) will have mode-specific labels that differ from
 * Mode 2 (Portfolio) — they disambiguate via `modeId`. The framework-
 * level labels (Backtest, Save, Risk preset…) resolve the same across
 * modes via the `FRAMEWORK_COPY` fallback.
 *
 * Lookup order:
 *   1. MODE_COPY[modeId][key]   — mode-specific override
 *   2. FRAMEWORK_COPY[key]      — shared default across modes
 *   3. key                      — fallback (warns in dev)
 *
 * NOTE: `useFlowCopy` is named with the `use` prefix to match the
 * `useXxx` convention bricks expect, but the implementation is a plain
 * lookup — safe to call from any context, including outside React.
 */

interface CopyMap {
  [key: string]: string;
}

const FRAMEWORK_COPY: CopyMap = {
  backtest_button: "Run backtest →",
  save_button: "Save strategy",
  risk_preset_low: "Conservative",
  risk_preset_medium: "Balanced",
  risk_preset_high: "Aggressive",
  what_block_title: "WHAT",
  when_in_block_title: "WHEN IN",
  how_much_block_title: "HOW MUCH",
  when_out_block_title: "WHEN OUT",
  next_button: "Next",
  back_button: "Back",
  abort_button: "Cancel",
};

const MODE_COPY: { [modeId: string]: CopyMap } = {};

/**
 * Register copy for a mode. Each mode's FlowDefinition file calls this
 * once on module load:
 *
 *   registerModeCopy("portfolio_mode", {
 *     upload_title: "Upload your portfolio",
 *     ...
 *   });
 *
 * Idempotent: calling twice with overlapping keys merges (later wins).
 */
export function registerModeCopy(modeId: string, copy: CopyMap): void {
  if (MODE_COPY[modeId]) {
    Object.assign(MODE_COPY[modeId], copy);
  } else {
    MODE_COPY[modeId] = { ...copy };
  }
}

export function useFlowCopy(modeId: string, key: string): string {
  const modeValue = MODE_COPY[modeId]?.[key];
  if (modeValue !== undefined) return modeValue;
  const fwValue = FRAMEWORK_COPY[key];
  if (fwValue !== undefined) return fwValue;
  if (process.env.NODE_ENV !== "production") {
    // eslint-disable-next-line no-console
    console.warn(
      `[useFlowCopy] missing copy for "${modeId}.${key}" — returning key as fallback`
    );
  }
  return key;
}

/**
 * Test-only escape hatch. Resets the mode-copy registry between tests.
 */
export function __resetCopyForTests(): void {
  for (const k of Object.keys(MODE_COPY)) {
    delete MODE_COPY[k];
  }
}
