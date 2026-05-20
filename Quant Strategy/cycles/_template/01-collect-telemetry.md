# Step 1 — Collect Livermore Telemetry

**Purpose**: Snapshot how the existing template library is being used so we can spot what's working, what's neglected, and what needs to retire.

**DoD**: A populated `Findings` section with every production template scored on the four dimensions below.

## How to run

### Option A — Manual (one-off)

```sql
-- Run against Livermore Postgres (or local SQLite)
-- See ../../framework/sql-schema.sql for table refs

-- 1. Backtests per strategy_type in the last 90 days
SELECT strategy_type,
       COUNT(*) AS backtests_90d,
       COUNT(DISTINCT user_id) AS unique_users_90d
FROM backtest_runs
WHERE created_at >= NOW() - INTERVAL '90 days'
GROUP BY strategy_type
ORDER BY backtests_90d DESC;

-- 2. Save / fork rate per strategy_type
SELECT s.strategy_type,
       COUNT(*) FILTER (WHERE sv.saved_at IS NOT NULL) AS saved_count,
       COUNT(*) FILTER (WHERE sv.forked_from IS NOT NULL) AS forked_count
FROM strategy_versions sv
JOIN strategies s ON sv.strategy_id = s.id
WHERE sv.created_at >= NOW() - INTERVAL '90 days'
GROUP BY s.strategy_type;

-- 3. Sandbox / explainer thumbs-down rate per template
-- (Wire if not present — see runbook §1.3 for the events to log.)
```

### Option B — Scheduled (preferred)

The Cowork scheduled task `livermore-telemetry-monthly` runs the above queries on the 1st of each month and posts results to `telemetry-snapshots/<yyyymm>.csv` in this folder.

## Findings

### Template performance scorecard

| Template | Backtests (90d) | Save rate | Sandbox thumbs-down | User comments | Verdict |
|---|---|---|---|---|---|
| `moving_average_filter` |  |  |  |  | keep / iterate / deprecate |
| `moving_average_crossover` |  |  |  |  | |
| `momentum_rotation` |  |  |  |  | |
| `rsi_mean_reversion` |  |  |  |  | |
| `breakout` |  |  |  |  | |
| `static_allocation` |  |  |  |  | |

*Add a row per template in mvp/ and production/.*

## Patterns to watch

- **Cold templates** (< 5 backtests in 90d): candidates for either better UX or retirement.
- **Hot templates** (≥ 25% of all backtests): candidates for tighter docs, more variants.
- **High thumbs-down %** (> 20% sandbox negative): something is misleading in the explainer or default params.

## Comments synthesized from user feedback

- *paste 5–10 representative quotes from in-app feedback / Slack / support tickets here*

## Carry-over to Step 2

What questions does this telemetry raise that the research scan should answer?

- ...
