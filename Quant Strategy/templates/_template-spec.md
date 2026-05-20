---
# REQUIRED
slug: ""                            # e.g. "cross-sectional-momentum"
name: ""                            # human-readable
livermore_strategy_type: ""         # matches the StrategyType Literal in apps/api/app/schemas/strategy.py
status: candidate | mvp | production | deprecated
introduced_in_cycle: ""             # e.g. "Q2-2026"
evidence_tier: A | B | C
capacity_tag: retail | prosumer | institutional

# CLASSIFICATION (must match KB tag vocabulary)
edge_type: technical | fundamental | event-driven | sentiment | composite-ml
horizon: intraday | swing | position | multi-quarter
asset_class: equity | etf | sector-etf | futures | options | fx | multi-asset
universe_shape: single-name | pair | basket | full-universe
directionality: long-only | long-cash | long-short | pair-neutral

# EVIDENCE TRAIL
source_ids: []                      # KB entry filenames, e.g. ["books/stefanini-...-2006.md"]
reference_sharpe_range: ""          # e.g. "0.4–0.8 long-only"
reference_drawdown_range: ""        # e.g. "20–35% in momentum crashes"
sample_window: ""                   # e.g. "1976–1996 in original Jegadeesh-Titman"

# LIFECYCLE
last_reviewed_at: YYYY-MM-DD
deprecation_reason: ""
superseded_by: ""                   # slug of replacement template
---

# {{Strategy Name}}

## Plain-English Description
*1–2 sentences a Starter-tier user would understand.*

## Thesis
*The economic or behavioral inefficiency being captured. Why does this work?*

## Signal
*The precise rule that turns data into a decision. Be explicit about entry, exit, ranking.*

## Default Parameters

| Parameter | Default | Notes |
|---|---|---|
| `formation_period_days` | 252 | |
| `rebalance_frequency` | monthly | |

## Livermore JSON Shape

```json
{
  "strategy_type": "...",
  "universe": [...],
  "benchmark": "SPY",
  "rebalance_frequency": "monthly",
  "rules": [{ }],
  "position_sizing": { "method": "equal_weight" }
}
```

## Engine Implementation Notes

- Branch in `apps/api/app/services/backtester/engine.py` → `_generate_weights`
- Lookback bump in `_compute_lookback`
- Special handling: ...

## Risk & Caveats

- Capacity: ...
- Regime sensitivity: ...
- Cost sensitivity: ...
- Data requirements: ...

## Evidence

- Reference Sharpe: ...
- Reference drawdown: ...
- Sample window: ...
- Replicated by: list of KB entries that confirm this

## QA Checklist (before promoting)

- [ ] Schema additive change merged (StrategyType + StrategyRule fields)
- [ ] Engine branch + unit test merged
- [ ] Strategy parser keyword patterns added
- [ ] Frontend template card with evidence + capacity tags
- [ ] Default parameters smoke-tested on a 5-year synthetic backtest
- [ ] Docs section in `docs/` or `README.md`
- [ ] Lifecycle row inserted into `strategy_template_lifecycle`

## Promotion Log

- **YYYY-MM-DD** — created as candidate in cycle {{cycle}}.
- **YYYY-MM-DD** — promoted to mvp; shipped to <X%> of users.
- **YYYY-MM-DD** — promoted to production.
