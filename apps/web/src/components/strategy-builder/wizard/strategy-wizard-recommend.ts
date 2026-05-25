/**
 * 5-question wizard scoring + recommendation engine.
 *
 * Direct TypeScript port of `recommend()`, `scoreStrategy()`, and
 * `buildWhy()` from `Quant Strategy/framework/Retail_Strategy_Picker_Framework.html`
 * (lines 822–857). Pure functions — unit-tested in
 * `strategy-wizard-recommend.test.ts`.
 *
 * Scoring weights (mirror the HTML):
 *   asset    × 2.0  (strongest signal — incompatibility = hard fail)
 *   behavior × 1.5
 *   goal     × 1.0
 *   cadence  × 1.0
 *
 * Hard disqualifiers (`scoreStrategy` returns -1):
 *   1. `requiresFundamentals` + asset in (single_commodity, pair)
 *   2. dd: 'low' + drawdown: 'high'
 *   3. asset[answer] === 0 (asset incompatible)
 *
 * Soft penalties (subtracted from score):
 *   dd: 'low'  + drawdown: 'medium' → -0.5
 *   dd: 'high' + drawdown: 'low'    → -0.3
 */

import type {
  WizardAnswers,
  WizardStrategy,
} from "./strategy-wizard-data";

export interface ScoredStrategy extends WizardStrategy {
  /** Computed score; -1 means disqualified and will be filtered. */
  _score: number;
}

/** Are all 5 answer fields present? Type-narrows `answers` to a
 *  fully-populated shape so the caller can read each field without
 *  a null check. */
export function isComplete(
  answers: WizardAnswers,
): answers is Required<{ [K in keyof WizardAnswers]: NonNullable<WizardAnswers[K]> }> {
  return (
    answers.asset !== null &&
    answers.goal !== null &&
    answers.cadence !== null &&
    answers.behavior !== null &&
    answers.dd !== null
  );
}

export function scoreStrategy(
  s: WizardStrategy,
  ans: Required<{ [K in keyof WizardAnswers]: NonNullable<WizardAnswers[K]> }>,
): number {
  // Hard disqualifiers
  if ((ans.asset === "single_commodity" || ans.asset === "pair") && s.requiresFundamentals) {
    return -1;
  }
  if (ans.dd === "low" && s.drawdown === "high") return -1;
  if (s.asset[ans.asset] === 0) return -1;

  let score = 0;
  score += 2 * s.asset[ans.asset];
  score += 1.5 * s.behavior[ans.behavior];
  score += 1 * s.goals[ans.goal];
  score += 1 * s.cadence[ans.cadence];

  // Soft drawdown adjustments
  if (ans.dd === "low" && s.drawdown === "medium") score -= 0.5;
  if (ans.dd === "high" && s.drawdown === "low") score -= 0.3;

  return score;
}

export function recommend(
  strategies: WizardStrategy[],
  answers: WizardAnswers,
  topK: number = 3,
): ScoredStrategy[] {
  if (!isComplete(answers)) return [];
  const full = answers as Required<{ [K in keyof WizardAnswers]: NonNullable<WizardAnswers[K]> }>;

  return strategies
    .map((s) => ({ ...s, _score: scoreStrategy(s, full) }))
    .filter((s) => s._score >= 0)
    .sort((a, b) => b._score - a._score)
    .slice(0, topK);
}

/** Plain-English reasons explaining why a strategy was recommended,
 *  per the same logic as the HTML's `buildWhy()`. Returned as an
 *  array so the UI can render each reason as its own bullet. */
export function buildWhy(s: WizardStrategy, answers: WizardAnswers): string[] {
  if (!isComplete(answers)) return [];
  const ans = answers as Required<{ [K in keyof WizardAnswers]: NonNullable<WizardAnswers[K]> }>;
  const reasons: string[] = [];

  if (s.asset[ans.asset] === 2) {
    reasons.push("Strong fit for your asset type");
  } else if (s.asset[ans.asset] === 1) {
    reasons.push("Works on your asset, though not its first choice");
  }

  if (s.behavior[ans.behavior] === 2) {
    const behaviorLabel =
      ans.behavior === "trend" ? "trend" :
      ans.behavior === "mean" ? "mean-revert" :
      "have mixed behavior";
    reasons.push(`Designed for assets that ${behaviorLabel}`);
  }

  if (s.goals[ans.goal] === 2) reasons.push("Matches your goal");
  if (s.cadence[ans.cadence] === 2) reasons.push("Fits your check-in rhythm");

  if (s.drawdown === "low" && ans.dd === "low") {
    reasons.push("Historically modest drawdowns — sleep-friendly");
  }
  if (s.evidence === "A") {
    reasons.push("Tier-A evidence (decades of replication)");
  }

  return reasons;
}
