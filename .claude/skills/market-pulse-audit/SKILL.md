---
name: market-pulse-audit
description: Run a calculation accuracy + data latency audit on the Livermore Market Pulse page (`/stocks`). Use when the user says "audit market pulse", "check market data accuracy", "verify market pulse calculations", "is the market data current", or after deploying changes to any market-pulse service (`market_pulse_service.py`, `sector_comparison_service.py`, `macro_signals_service.py`, `macro_similarity_service.py`, `screener_presets.py`). Reports cross-market leaks, sort regressions, math drift, freshness gaps, and benchmark-identity issues against the live API. Read-only.
---

## Overview

Livermore's Market Pulse page (`/stocks`) is the front-of-store data
surface — six sections (MarketBrief / MacroPulse / SectorRotation /
HistoryRhymes / TopMovers / Screener) pulling from four backend
services plus three external data providers (Alpha Vantage, FMP, the
LLM gateway). Each section has narrow correctness invariants:

- US Top Movers must not contain `.SH` / `.SZ` / `.HK` listings
- Sort dropdown options must produce meaningfully different orderings
- Sector comparison should benchmark against `^GSPC`, not `SPY`
- Macro Inflation + Rates rows must be real Alpha Vantage data (not
  silent-mock fallbacks)
- CN toggle must not leak A-shares into the response
- Every data group should be fresh (latest bar ≤ 4 calendar days old)

This skill audits those invariants by walking the live API + the
in-DB freshness report.

## When to Use

- After deploying changes to `apps/api/app/services/market_pulse*.py`,
  `sector_comparison_service.py`, `macro_signals_service.py`, or
  `screener_presets.py`
- After any `price_bars` ingestion / backfill (Alpha Vantage warmup,
  the `^GSPC` backfill, etc.)
- Before / after flipping `GATING_ENABLED` or similar production flags
- On user-reported "market data looks wrong" tickets — runs the audit
  first to localize the issue
- As a scheduled regression net (future: nightly cron)

## Prerequisites

- Python 3.9+ (uses standard library only — `urllib` for HTTP)
- Network access to the API base URL being audited
- The repo's `apps/api/scripts/audit_market_pulse.py` script (ships
  with the codebase; no install needed)

No API keys or DB credentials required — the audit is HTTP-only and
reads from the public REST surface.

## Workflow

### Step 1: Pick the base URL

Determine which environment to audit:

| Environment | URL | When to use |
|---|---|---|
| Local dev | `http://localhost:8001` | After backend edits during development |
| Production | `https://thecounselor-production.up.railway.app` | Default; after a deploy or on-demand sanity check |

If the user doesn't specify, ask which environment, or default to
production.

### Step 2: Run the audit script

```bash
cd /Users/jimmygu/the_counselor/apps/api
python3 scripts/audit_market_pulse.py --base-url <BASE_URL>
```

The script emits a markdown report to stdout. Exit code is non-zero
if any ERROR findings — `OK` and `WARN` together return 0.

For machine-readable output (e.g. CI integration):

```bash
python3 scripts/audit_market_pulse.py --base-url <BASE_URL> --output audit.md
```

### Step 3: Interpret the findings

The report groups findings by section:

- **Freshness** — overall data age + per-group breakdown. `fresh`
  = ≤ 4 calendar days; `stale` = 5–10 days; `very_stale` / `missing`
  = ERROR.
- **Region integrity** — US `top_assets` containing `.SH` / `.SZ` /
  `.HK` symbols is an ERROR (the May 22 `510300.SH` bug).
- **Sort sanity** — pool must contain BOTH gainers and losers so the
  client-side losers-sort has data to work with. Zero losers in the
  pool is a WARN (could be a one-sided day or a PR-2 regression).
- **Math spot-check** — verifies `sector-comparison/XLK series[0]`
  normalizes to 0 at the window start.
- **Macro signals reality** — Inflation + Rates must have
  `source='alpha_vantage'`. A silent fallback to mock signals
  (AV key missing / rate-limited) is an ERROR. Growth + Stress
  reporting `mock_pending_fred` is EXPECTED and shows as OK
  until `FRED_API_KEY` lands on Railway.
- **CN scope** — `market=CN` must not contain A-shares;
  `history-rhymes` must return the "US-only" caveat.
- **Benchmark identity** — verifies the sector chart is reading
  `^GSPC` (not the SPY fallback). If WARN, run
  `apps/api/scripts/backfill_gspc.py` against the prod DB.

### Step 4: Triage ERRORs and WARNs

For each finding:

1. **ERROR** — triage immediately. Most ERRORs trace to a recent
   deploy or a backend service falling through to a defensive
   fallback. Read the message + detail; the recipe usually points
   at the file to fix.
2. **WARN** — log it. WARNs are advisory; they're not necessarily
   bugs (e.g. a one-sided market day legitimately has only gainers).
   If the same WARN persists across multiple audits, escalate.
3. **OK** — confirm the invariant is holding.

When reporting to the user, surface ERRORs prominently with the
specific file + line ranges from each check's docstring. WARNs go in
a secondary list. OKs can be summarized as a count.

### Step 5: Suggest fixes when relevant

Each error has a known recipe — link the user to the relevant
remediation:

| Error pattern | Recipe |
|---|---|
| Region leak (`.SH` in US top_assets) | `apps/api/app/services/market_pulse_service.py` — verify the region filter (lines ~360-385) is on the deployed branch |
| Macro Inflation/Rates mocked | Check `ALPHA_VANTAGE_API_KEY` on Railway + look for AV rate-limit logs |
| ^GSPC missing | Run `python apps/api/scripts/backfill_gspc.py` with prod DB + FMP creds |
| Stale freshness | Look at `apps/api/app/jobs/qa_jobs.py` daily warmup logs |

## Examples

### Example 1: Post-deploy sanity check

```
User: I just merged PRs #68-#74. Audit market pulse.

You: [Run script against production]
→ 9 OK, 1 WARN, 1 ERROR
  ERROR: /api/market/data-latency 404 (PR-6 not deployed yet)
  WARN: ^GSPC missing — run backfill_gspc.py

Recommendation: wait for Railway redeploy (~5 min), then rerun.
After ^GSPC backfill, both findings clear.
```

### Example 2: User report

```
User: someone says the market pulse is showing wrong sector returns.

You: [Run script]
→ Math spot-check ERROR — XLK series[0].sector = 0.012 (should be 0)

This means the sector comparison service isn't normalizing the
windowed slice correctly. Check `sector_comparison_service._cum_returns()`
recent edits.
```

## Notes

- The audit doesn't touch the database directly — it's HTTP-only. The
  in-DB freshness numbers come via `/api/market/data-latency`.
- Read-only by construction. Cannot mutate state.
- Companion tests live at `apps/api/tests/test_market_pulse_*.py` and
  `apps/api/tests/test_data_latency.py` — they cover the same
  invariants at unit-test granularity. The audit is the integration-
  level mirror.
- The audit shipped 2026-05-23 in PR-7 of the Market Pulse accuracy
  + latency sprint. Initial run against production: 9 OK + 1 WARN
  (^GSPC pending backfill) + 1 ERROR (data-latency endpoint pre-
  deploy).
