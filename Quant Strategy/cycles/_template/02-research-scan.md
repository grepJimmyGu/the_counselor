# Step 2 — Knowledge Base Scan & Market Trend Review

**Purpose**: Refresh the KB with new academic + practitioner sources released this quarter, and form a view on the prevailing market regime.

**DoD**: At least one new `knowledge-base/<type>/*.md` entry created or updated, and a 1-paragraph regime note below.

## How to run

### 2.1 KB refresh checklist

For each source category, scan and decide what (if anything) to add:

- [ ] **Books** — any new finance/quant releases since last cycle? (Check Wiley Finance, Packt, Pearson lists.)
- [ ] **Papers** — SSRN, arXiv-q-fin, NBER WP, Journal of Finance, RFS, JFE.
- [ ] **Practitioner research** — AQR Insights, Robeco Insights, Quantpedia new strategies, Alpha Architect blog.
- [ ] **Replication studies** — any factor-replication papers worth tracking.

For each new source: `cp knowledge-base/_kb-entry-template.md knowledge-base/<type>/<slug>.md` and fill it in.

### 2.2 Targeted search prompts (copy-paste into chat)

```
Search the web for the most cited or most widely discussed new quantitative
equity research published since <prev_cycle_end_date>. For each notable paper:
1) one-paragraph summary,
2) the strategy or factor it tests,
3) the reported Sharpe / drawdown,
4) whether the result has been replicated.
Return JSON with the fields needed by knowledge-base/_kb-entry-template.md.
```

```
Survey current practitioner letters from AQR, Robeco, Two Sigma, GMO, and Bridgewater
published in the last 90 days. Summarize: (a) which factors they say are working,
(b) which they say are broken, (c) what regime they think we are in.
```

### 2.3 Regime note

A 1-paragraph synthesis at the end of this file: what regime are we in (growth / value / momentum / low-vol / risk-off), what flipped recently, what does that imply for which templates are likely to be hot vs cold in the next 90 days?

## New KB entries this cycle

- `knowledge-base/papers/...`
- `knowledge-base/market-research/...`
- `knowledge-base/strategies/...`

## Updated entries this cycle

- ...

## Regime note

> *...*

## Themes carried into Step 3

- Theme A: ...
- Theme B: ...
- Theme C: ...
