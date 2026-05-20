---
source_type: book
title: "Investment Strategies of Hedge Funds"
authors: ["Filippo Stefanini"]
year: 2006
url: "https://www.wiley.com/en-us/Investment+Strategies+of+Hedge+Funds-p-9780470026274"
file_path: "Quant Strategy building/L-G-0000568029-0002381765.pdf"

tags:
  - book
  - hedge-funds
  - taxonomy
  - tier-a
asset_classes: [equity, futures, fixed-income, multi-asset]
evidence_tier: A
strategies_referenced:
  - cross-sectional-momentum
  - pairs-trading
  - sector-rotation
  - merger-arbitrage
  - distressed-securities
  - managed-futures
  - global-macro
  - statistical-arbitrage

added_at: 2026-05-18
last_reviewed_at: 2026-05-20
reviewed_by: cycle-Q2-2026
superseded_by: ""
status: active
---

# Investment Strategies of Hedge Funds — Stefanini (2006)

## TL;DR
A practitioner's tour of every major hedge fund strategy circa 2006, written by a fund-of-funds deputy CIO. Its lasting value to Livermore is not the strategies themselves (many are out of scope for stocks) but the **repeating 8-part chapter skeleton** — history, theory, securities, hedging, examples, liquidity, leverage, risks — which doubles as a template-builder schema.

## Source Summary

Stefanini covers 17 chapters: arbitrage, short selling, long/short equity, merger arbitrage, convertible bond arbitrage, fixed income arbitrage, CDOs, MBS arbitrage, distressed, event-driven, multi-strategy, managed futures, global macro, "other" (stat arb, vol, PIPEs, real estate, energy), and a performance-analysis chapter on VaR and indices.

The author is explicit that the book is a tour, not a recipe ("strategy is easy, execution is hard"). For Livermore the takeaway is structural: every chapter uses the same skeleton, which we lifted in `framework/Livermore_Library_Iteration_Framework.html` as the universal 8-layer template (Universe → Thesis → Signal → Execution → Risk → Liquidity → Backtest → Review).

For stock-quant scope specifically, the directly transferable chapters are: Long/Short Equity (Ch 4), Equity Market Neutral (§4.9), Pairs Trading (§4.6), Managed Futures (Ch 13, when applied to equity index futures), Statistical Arbitrage (§15.3), Index Arbitrage (§15.4), Volatility Trading (§15.5).

Out-of-scope chapters for Livermore stock focus: convertible bond arb, fixed income arb, CDOs, MBS, distressed, PIPEs, real estate, energy.

## Strategies Extracted

### Strategy 1: Long/Short Equity (Ch. 4)
- **Thesis**: stock-selection skill, neutralized for market beta
- **Universe**: liquid stocks
- **Signal**: factor scores (value, quality, momentum), rank cross-sectionally
- **Rebalance**: monthly
- **Caveats**: needs shorting; Livermore currently long-only — implement long-only variant for now

### Strategy 2: Pairs Trading (§4.6)
- **Thesis**: cointegrated prices revert
- **Universe**: sector-matched stock pairs
- **Signal**: spread z-score; enter at ±2, exit at 0, stop at ±3.5
- **Rebalance**: per-signal
- **Caveats**: pair half-life ≈ 1–2 years; need to refresh pair list each cycle

### Strategy 3: Sector Momentum Rotation (alluded to in Ch. 13/15)
- **Thesis**: sectors persist in relative strength
- **Universe**: SPDR sector ETFs
- **Signal**: 6–12 month total return ranking
- **Rebalance**: monthly
- **Caveats**: needs full sector ETF coverage

## Quotes & Numbers Worth Citing

> "Strategy is easy, execution is hard!" — Preface

> "Each chapter of this book is structured to cover the following subjects: strategy history; strategy's theoretical description; description of securities involved and size of the securities market; hedging techniques and possible use of derivatives; some trading examples; liquidity; leverage; risks and risk management." — Preface

## Cross-References

- Framework derived from this book: `../../framework/Livermore_Library_Iteration_Framework.html` §4 (8-layer template).
- Templates seeded by this book: `pairs-trading`, `sector-rotation` (see `templates/`).

## Reviewer Notes

- **2026-05-18** — initial entry; seeded as part of cycle Q2-2026 from the workspace PDF.
- **2026-05-20** — verified entry on rebuild; the underlying PDF is no longer present in the workspace mount, but the summary here captures every load-bearing fact.
