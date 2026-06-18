/**
 * Recommended-template registry (PRD-24a §5 / §6) — the "lego-brick".
 *
 * One data-only registry of starting points the user can pick from the
 * "Screen the market" gallery (and that Home theme cards reference).
 * Adding a template later = ONE entry here; no component changes.
 *
 * Two kinds, matching §5.4's routing fork:
 *   - "composer"  → pre-loads `rules` into custom_build_mode (fully
 *                   reproducible; the rules also drive the PRD-23
 *                   /api/screen/scan match count). primitive_id-based.
 *   - "sentiment" → routes to /sentiment?toolkit=… (LLM-mediated scoring,
 *                   not expressible as StrategyRule compositions).
 *
 * IMPORTANT — composer rules use `primitive_id` (the field the scan +
 * buildScreenRules key on), NOT `indicator`, and every primitive_id below
 * is verified present in the daily signal_snapshot scan vocabulary.
 */
import type { ScreenUniverseId, StrategyRule } from "@/lib/contracts";

export type TemplateCategory = "momentum" | "quality" | "catalyst" | "event";

interface BaseTemplate {
  id: string;
  /** 1–3 word display name (Tier-1 vocabulary). */
  name: string;
  category: TemplateCategory;
  /** One-line plain-English tagline. */
  tagline: string;
}

export interface ComposerTemplate extends BaseTemplate {
  kind: "composer";
  universe_id: ScreenUniverseId;
  /** primitive_id-based rules — scan match-count + composer pre-load. */
  rules: StrategyRule[];
  /** Plain primitive list for the "What this finds" drawer. */
  primitives: string[];
  /** Primitives intentionally omitted from v1 (not yet scannable / encoding
   *  follow-up), surfaced for transparency rather than silently dropped. */
  deferred?: string[];
}

export interface SentimentTemplate extends BaseTemplate {
  kind: "sentiment";
  /** The /api/sentiment toolkit this routes to. */
  toolkit_id: string;
  /** Optional `?display=` label override (§8.1) so the UI label can differ
   *  from the underlying toolkit name without touching the Sentiment Hub. */
  display_label?: string;
}

export type RecommendedTemplate = ComposerTemplate | SentimentTemplate;

export const RECOMMENDED_TEMPLATES: RecommendedTemplate[] = [
  {
    kind: "composer",
    id: "best_momentum",
    name: "Best Momentum Pick",
    category: "momentum",
    tagline:
      "Top-quintile 6-month momentum in a leading sector, confirmed by a strong, above-trend price.",
    universe_id: "sp500",
    // §6.1 — CORRECTED against the live snapshot scan (the PRD spec was wrong
    // on three counts, all caught by curling /api/screen/scan):
    //   1. `rank_composite_score` is unpopulated (always 0) → it poisoned the
    //      whole AND → 0 matches. Dropped.
    //   2. `rank_return_6m` is a 0–1 percentile, NOT 0–100 → threshold 85 never
    //      matched; 0.80 ≈ top-quintile.
    //   3. rules 2+ MUST carry logic_with_prior ("AND"/"OR") or the scan 500s.
    // `adx_rising` + `rvol` each over-tighten the basket to ~2 names (and rvol
    // is today's-volume-dependent), so they're deferred as optional tighteners.
    // This set returns ~10–15 SP500 names (verified live 2026-06-17).
    rules: [
      { primitive_id: "rank_return_6m", operator: "gte", threshold: 0.8 },
      {
        primitive_id: "time_series_momentum",
        operator: "gt",
        threshold: 0.15,
        logic_with_prior: "AND",
      },
      { primitive_id: "adx", operator: "gte", threshold: 25, logic_with_prior: "AND" },
      {
        primitive_id: "price_above_ma",
        operator: "is_true",
        primitive_params: { period: 200 },
        logic_with_prior: "AND",
      },
      {
        primitive_id: "price_above_ma",
        operator: "is_true",
        primitive_params: { period: 50 },
        logic_with_prior: "AND",
      },
      {
        primitive_id: "sector_rotation_rank",
        operator: "lte",
        threshold: 3,
        logic_with_prior: "AND",
      },
    ],
    primitives: [
      "rank_return_6m",
      "time_series_momentum",
      "adx",
      "price_above_ma",
      "sector_rotation_rank",
    ],
    deferred: [
      "rank_composite_score (not populated in the daily snapshot — always 0)",
      "adx_rising + rvol (optional tighteners — they cut the basket to ~2 names; rvol is today's-volume-dependent)",
      "f_score (Piotroski — fundamental; arrives with the fundamentals slice)",
      "supertrend (encoding follow-up; trend already gated by ADX + the MA filters)",
    ],
  },
  {
    kind: "sentiment",
    id: "rising_attention",
    name: "Rising Attention",
    category: "catalyst",
    tagline:
      "Stocks with unusually high attention volume right now — an early-interest signal.",
    toolkit_id: "rising_attention",
  },
];

export function getRecommendedTemplate(
  id: string,
): RecommendedTemplate | undefined {
  return RECOMMENDED_TEMPLATES.find((t) => t.id === id);
}
