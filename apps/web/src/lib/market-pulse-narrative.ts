/**
 * Deterministic Market Pulse narrative — Layer A fallback.
 *
 * This generator runs entirely client-side from the same
 * `MarketPulseResponse` the page already loads. No LLM dependency,
 * no API call, no failure modes. Used:
 *   - In Phase 0 (preview) as the only narrative source so Jimmy can
 *     review layout without LLM cost.
 *   - In Phase 1+ as the fallback when `data.narrative` is null
 *     (LLM unconfigured or backend returned no narrative).
 *
 * The output is formulaic by design — that's the tradeoff for being
 * always-available. The LLM-generated narrative in Phase 1 will produce
 * the higher-quality version per Jimmy's "key is quality" feedback.
 */
import type { MarketPulseResponse, IndexCard, MacroCard, SectorCard } from "@/lib/contracts";

import { fmtPct } from "@/lib/market-pulse-format";

export interface PillStat {
  label: string;
  value: string;
  /** Optional decimal perf for color coding (positive = emerald, negative = red). */
  perf?: number | null;
  /** Optional click target (e.g. `/stocks/SPY`). */
  href?: string;
}

export interface Narrative {
  /** Sentences, 2-3 of them. Each rendered as its own paragraph block. */
  headline: string[];
  /** 3 inline pills (SPY 1D, lead sector, 10Y move). */
  pills: PillStat[];
  /** Single-line interpretation for the sector-rotation section. */
  sectorRotation: string;
}

// ── Public entry point ────────────────────────────────────────────────────────

export function buildNarrative(data: MarketPulseResponse): Narrative {
  const headline = [
    sentenceLeadIndex(data.indices),
    sentenceSectorRotation(data.sectors),
    sentenceMacroSignal(data.macro),
  ].filter((s): s is string => Boolean(s));

  return {
    headline,
    pills: buildPills(data),
    sectorRotation: sectorRotationOneLiner(data.sectors),
  };
}

// ── Sentence helpers ──────────────────────────────────────────────────────────

function sentenceLeadIndex(indices: IndexCard[]): string {
  if (!indices?.length) return "";
  // Pick the index with the largest absolute 1d move.
  const lead = [...indices]
    .filter((c) => c.perf_1d != null)
    .sort((a, b) => Math.abs(b.perf_1d ?? 0) - Math.abs(a.perf_1d ?? 0))[0];
  if (!lead || lead.perf_1d == null) return "";
  const up = lead.perf_1d >= 0;
  return `${lead.name} ${up ? "led" : "dragged"} the tape, ${
    up ? "up" : "down"
  } ${fmtPct(lead.perf_1d, 1)} on the day.`;
}

function sentenceSectorRotation(sectors: SectorCard[]): string {
  if (!sectors?.length) return "";
  // sectors arrive sorted by CMF descending (backend), so first/last is the
  // leader/laggard pair.
  const lead = sectors[0];
  const lag = sectors[sectors.length - 1];
  if (!lead || !lag || lead.perf_1d == null || lag.perf_1d == null) return "";
  return `${lead.name} ${
    lead.perf_1d >= 0 ? "led" : "rallied"
  } (${fmtPct(lead.perf_1d, 1)}); ${lag.name} lagged (${fmtPct(
    lag.perf_1d,
    1,
  )}).`;
}

function sentenceMacroSignal(macro: MacroCard[]): string {
  if (!macro?.length) return "";
  // Only call out a macro signal if the magnitude is meaningful (>0.75%).
  const significant = macro
    .filter((m) => m.perf_1d != null && Math.abs(m.perf_1d) > 0.0075)
    .sort((a, b) => Math.abs(b.perf_1d ?? 0) - Math.abs(a.perf_1d ?? 0))[0];
  if (!significant || significant.perf_1d == null) return "";
  return `${macro_subject(significant)} — ${
    significant.label ?? significant.symbol
  } ${fmtPct(significant.perf_1d, 1)}.`;
}

function macro_subject(card: MacroCard): string {
  const sym = card.symbol.toUpperCase();
  if (sym.includes("VIX") || sym.includes("VXX"))
    return card.perf_1d && card.perf_1d > 0 ? "Vol surged" : "Vol eased";
  if (sym.includes("TLT") || sym.includes("TNX"))
    return card.perf_1d && card.perf_1d > 0 ? "Rates eased" : "Rates moved up";
  if (sym.includes("UUP") || sym.includes("DXY"))
    return card.perf_1d && card.perf_1d > 0
      ? "Dollar strengthened"
      : "Dollar weakened";
  if (sym.includes("GOLD") || sym.includes("GLD")) return "Gold moved";
  if (sym.includes("WTI") || sym.includes("USO")) return "Oil moved";
  if (sym.includes("HYG")) return "Credit moved";
  return "Macro moved";
}

// ── Sector rotation one-liner ────────────────────────────────────────────────

function sectorRotationOneLiner(sectors: SectorCard[]): string {
  if (!sectors?.length) return "";
  const lead = sectors[0];
  const lag = sectors[sectors.length - 1];
  if (!lead || !lag) return "";

  // Classify the rotation directionally.
  const cyclical = new Set(["XLK", "XLC", "XLY", "XLF", "XLI"]);
  const defensive = new Set(["XLP", "XLV", "XLU", "XLRE"]);
  const leadKind = cyclical.has(lead.symbol)
    ? "growth"
    : defensive.has(lead.symbol)
      ? "defensive"
      : "mixed";
  const lagKind = cyclical.has(lag.symbol)
    ? "growth"
    : defensive.has(lag.symbol)
      ? "defensive"
      : "mixed";

  const tail =
    leadKind === "growth" && lagKind === "defensive"
      ? " — risk-on rotation"
      : leadKind === "defensive" && lagKind === "growth"
        ? " — risk-off rotation"
        : "";
  return `${lead.name} leading; ${lag.name} lagging${tail}.`;
}

// ── Pills ─────────────────────────────────────────────────────────────────────

function buildPills(data: MarketPulseResponse): PillStat[] {
  const pills: PillStat[] = [];

  const spy = data.indices.find((c) => c.symbol === "SPY") ?? data.indices[0];
  if (spy && spy.perf_1d != null) {
    pills.push({
      label: spy.symbol,
      value: fmtPct(spy.perf_1d, 2),
      perf: spy.perf_1d,
      href: `/stocks/${spy.symbol}`,
    });
  }

  const leadSector = data.sectors?.[0];
  if (leadSector && leadSector.perf_1d != null) {
    pills.push({
      label: leadSector.symbol,
      value: fmtPct(leadSector.perf_1d, 2),
      perf: leadSector.perf_1d,
      href: `/stocks/${leadSector.symbol}`,
    });
  }

  // 10Y proxy — TLT's perf_1d. Inverted view ("rates move opposite to TLT")
  // is left to the headline copy, not the pill itself.
  const rates =
    data.macro.find((m) => m.symbol.toUpperCase() === "TLT") ??
    data.macro.find((m) => m.symbol.toUpperCase().includes("TNX"));
  if (rates && rates.perf_1d != null) {
    pills.push({
      label: rates.label ?? rates.symbol,
      value: fmtPct(rates.perf_1d, 2),
      perf: rates.perf_1d,
    });
  }

  return pills;
}
