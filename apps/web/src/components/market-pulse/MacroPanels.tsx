"use client";

import type { MacroCard } from "@/lib/contracts";
import { MacroPanel } from "./MacroPanel";

/**
 * Section 2 — Macro Pulse (themed panels).
 *
 * Replaces the previous single-row MacroStrip per Jimmy's 2026-05-21
 * feedback ("can we build richer macro pulse number insights"). The new
 * shape groups the 6 macro indicators into 4 thematic panels with
 * plain-English interpretation chips so retail readers can read a
 * story instead of decoding raw numbers:
 *
 *   - Rates       — TLT (long bonds), HYG (credit)
 *   - Volatility  — VXX (VIX proxy)
 *   - FX (Dollar) — UUP (USD index proxy)
 *   - Commodities — GOLD_SPOT (gold), WTI_SPOT (oil)
 *
 * Layout: 2×2 grid on desktop, 1-column stack on mobile.
 *
 * Interpretation rules live in this file as small pure functions per
 * panel. Thresholds tuned conservatively to avoid noise — most of the
 * time the chip says "Calm" / "Balanced" / "Mixed" rather than a
 * bold call.
 */

export function MacroPanels({ macro }: { macro: MacroCard[] }) {
  if (!macro?.length) return null;

  // Index by symbol so panel rules don't have to scan the array.
  const bySymbol: Record<string, MacroCard> = Object.fromEntries(
    macro.map((m) => [m.symbol, m]),
  );
  const pick = (...symbols: string[]) =>
    symbols.map((s) => bySymbol[s]).filter(Boolean) as MacroCard[];

  const tlt = bySymbol["TLT"];
  const hyg = bySymbol["HYG"];
  const vxx = bySymbol["VXX"];
  const uup = bySymbol["UUP"];
  const gold = bySymbol["GOLD_SPOT"] ?? bySymbol["GLD"];
  const wti = bySymbol["WTI_SPOT"] ?? bySymbol["USO"];

  return (
    <section
      id="macro"
      aria-labelledby="macro-heading"
      className="space-y-3"
    >
      <h2
        id="macro-heading"
        className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Macro pulse
      </h2>

      <div className="grid gap-3 md:grid-cols-2">
        <MacroPanel
          title="Rates"
          summary="Long bonds & high-yield credit — risk-on / risk-off read."
          cards={pick("TLT", "HYG")}
          {...interpretRates(tlt, hyg)}
        />
        <MacroPanel
          title="Volatility"
          summary="Vol regime — quiet, normal, or stressed."
          cards={pick("VXX")}
          {...interpretVol(vxx)}
        />
        <MacroPanel
          title="Dollar"
          summary="USD strength vs the major basket."
          cards={pick("UUP")}
          {...interpretFx(uup)}
        />
        <MacroPanel
          title="Commodities"
          summary="Safe-haven (gold) and growth (oil) reads."
          cards={pick(gold?.symbol ?? "GOLD_SPOT", wti?.symbol ?? "WTI_SPOT")}
          {...interpretCommodities(gold, wti)}
        />
      </div>
    </section>
  );
}

// ── Interpretation rules ────────────────────────────────────────────────────
//
// Each helper takes the cards relevant to its panel and returns
// `{ interpretation, interpretationTone }` for the MacroPanel chip.
// Thresholds are deliberately conservative — Phase 1 backend may swap
// these out for an LLM-driven sentence per panel.

type Read = {
  interpretation: string;
  interpretationTone: "up" | "down" | "neutral";
};

function interpretRates(tlt?: MacroCard, hyg?: MacroCard): Read {
  const tltPerf = tlt?.perf_1d ?? 0;
  const hygPerf = hyg?.perf_1d ?? 0;
  if (tltPerf > 0.003 && hygPerf > 0.001)
    return { interpretation: "Rates easing, credit firm", interpretationTone: "up" };
  if (tltPerf < -0.003 && hygPerf < -0.001)
    return { interpretation: "Rates rising, credit soft", interpretationTone: "down" };
  if (tltPerf > 0.003)
    return { interpretation: "Rates rallying", interpretationTone: "up" };
  if (tltPerf < -0.003)
    return { interpretation: "Rates rising", interpretationTone: "down" };
  if (hygPerf < -0.005)
    return { interpretation: "Credit widening", interpretationTone: "down" };
  return { interpretation: "Calm", interpretationTone: "neutral" };
}

function interpretVol(vxx?: MacroCard): Read {
  const perf = vxx?.perf_1d ?? 0;
  if (perf > 0.05)
    return { interpretation: "Vol spiking", interpretationTone: "down" };
  if (perf > 0.02)
    return { interpretation: "Vol firming", interpretationTone: "down" };
  if (perf < -0.03)
    return { interpretation: "Vol crushed", interpretationTone: "up" };
  return { interpretation: "Calm", interpretationTone: "neutral" };
}

function interpretFx(uup?: MacroCard): Read {
  const perf = uup?.perf_1d ?? 0;
  if (perf > 0.003)
    return { interpretation: "Dollar bid", interpretationTone: "up" };
  if (perf < -0.003)
    return { interpretation: "Dollar soft", interpretationTone: "down" };
  return { interpretation: "Balanced", interpretationTone: "neutral" };
}

function interpretCommodities(gold?: MacroCard, wti?: MacroCard): Read {
  const goldPerf = gold?.perf_1d ?? 0;
  const wtiPerf = wti?.perf_1d ?? 0;
  if (goldPerf > 0.005 && wtiPerf < -0.005)
    return { interpretation: "Haven bid", interpretationTone: "down" };
  if (wtiPerf > 0.01)
    return { interpretation: "Growth-on, energy bid", interpretationTone: "up" };
  if (wtiPerf < -0.015)
    return { interpretation: "Energy lagging", interpretationTone: "down" };
  if (goldPerf > 0.01)
    return { interpretation: "Gold bid", interpretationTone: "up" };
  return { interpretation: "Mixed", interpretationTone: "neutral" };
}
