# Quarterly Library Refresh — Runbook

> Owner: Jimmy. Roughly **2 working days of effort per cycle**, spread over 3–4 weeks.
> Cadence: quarterly. Schedule the next cycle's kickoff at the close of the current cycle.

## At a glance

```
Week 1   Step 1 (Collect)   ─── pull Livermore telemetry, score templates
Week 2   Step 2 (KB scan)   ─── refresh knowledge base, write regime note
Week 2   Step 3 (Propose)   ─── pick 2–3 candidate templates
Week 3-4 Step 4 (Refresh)   ─── implement, promote, retire, sync
         Close              ─── cycle-summary.md, schedule next kickoff
```

---

## 0. Cycle kickoff (Day 0)

```bash
# From the workspace root
CYCLE="Q3-2026"   # change me
cp -r "/Users/jimmygu/the_counselor/Quant Strategy/cycles/_template" \
      "/Users/jimmygu/the_counselor/Quant Strategy/cycles/${CYCLE}"
```

Open the new folder; you'll work through `01-*.md` → `04-*.md` → `cycle-summary.md`.

---

## 1. Collect Livermore telemetry (Step 1)

### 1.1 Pull the data

The **scheduled task `livermore-telemetry-monthly`** writes a CSV snapshot to
`Quant Strategy/cycles/_telemetry-snapshots/<yyyymm>.csv` on the 1st of each
month. At cycle kickoff, just copy the most recent snapshot into your cycle
folder:

```bash
cp "/Users/jimmygu/the_counselor/Quant Strategy/cycles/_telemetry-snapshots/$(date +%Y%m).csv" \
   "/Users/jimmygu/the_counselor/Quant Strategy/cycles/${CYCLE}/telemetry.csv"
```

If you're running this manually before scheduled tasks exist, run the queries
from `01-collect-telemetry.md` against your Livermore DB:

```bash
# Postgres
psql "$DATABASE_URL" -f - <<'SQL'
SELECT * FROM v_template_gallery ORDER BY backtests_90d DESC;
SELECT * FROM v_cold_templates;
SQL
```

### 1.2 Score the templates

Fill in the scorecard in `01-collect-telemetry.md`. Score each template
**keep / iterate / deprecate** based on:

- **keep**: backtests_90d ≥ p50 of all templates, thumbs_down_rate < 15%.
- **iterate**: usage moderate but thumbs_down_rate high, OR usage low but
  recent (introduced in last 1–2 cycles — give it time).
- **deprecate**: backtests_90d < 5 AND template > 2 cycles old AND no recent
  positive feedback.

### 1.3 Carry-over

End the file with a short list of **questions for Step 2**: e.g. "users keep
asking about news-driven entries — does new research support a sentiment
template?"

---

## 2. Knowledge-base scan (Step 2)

### 2.1 Three parallel searches

Run these three queries via the chat agent (`Step 2.2` prompts in
`02-research-scan.md`):

1. **Academic** — new SSRN / arXiv-q-fin / NBER WP / journal papers since
   the previous cycle's end date.
2. **Practitioner** — AQR, Robeco, Two Sigma, GMO, Bridgewater letters
   from the last 90 days.
3. **Replication** — any factor-replication or out-of-sample papers
   challenging existing tier-A evidence.

### 2.2 Add KB entries

For every notable source:

```bash
cd "/Users/jimmygu/the_counselor/Quant Strategy/knowledge-base/papers"
cp ../_kb-entry-template.md "<first-author>-<short-title>-<year>.md"
# fill in front-matter and body
```

If a source supersedes an older one (e.g. a 2026 replication update for a 2014
paper), set `superseded_by` in the older file's front-matter and add a note in
the older file's Reviewer Notes section.

### 2.3 Write the regime note

End the file with **1 paragraph** answering: what regime are we in, what
flipped recently, what does that imply for which existing templates are
likely to be hot vs cold in the next 90 days?

### 2.4 Themes for Step 3

End with 2–3 **themes** — short phrases like "earnings revisions revival" or
"low-vol underperformance challenges defensive premise". These are the seeds
for candidate templates.

---

## 3. Propose 2–3 new templates (Step 3)

### 3.1 Brainstorm wide, pick narrow

In `03-template-proposals.md` list every candidate that crossed your desk in
Steps 1+2 — usually 6–12 ideas. Then score them on the five-question rubric
(Demand / Evidence / Fit / Capacity / Differentiation, 1–5 each).

Top 2–3 by total score advance. Auto-defer anything with `Evidence ≤ 2`.

### 3.2 Create candidate template files

For each chosen candidate:

```bash
SLUG="news-sentiment-momentum"   # change me
cp "/Users/jimmygu/the_counselor/Quant Strategy/templates/_template-spec.md" \
   "/Users/jimmygu/the_counselor/Quant Strategy/templates/candidate/${SLUG}.md"
# fill in front-matter and body
```

Front-matter fields that must be set in this step:

- `slug`, `name`, `livermore_strategy_type`
- `status: candidate`
- `introduced_in_cycle: ${CYCLE}`
- `evidence_tier`, `capacity_tag`
- `edge_type`, `horizon`, `asset_class`, `universe_shape`, `directionality`
- `source_ids: [<kb-entry-paths>]`

### 3.3 Deferred candidates

Keep a short list of deferred ideas in the same file — these become the
backlog for next cycle.

---

## 4. Implementation & refresh (Step 4)

### 4.1 Write coding-agent prompts

In `04-implementation-plan.md`, write one prompt per new candidate template,
following the format from the v2 strategy library doc (file paths, additive
schema changes, engine branch, test plan, acceptance criteria).

Paste each prompt into your coding agent in order. Wait for green tests
before moving to the next prompt.

### 4.2 Promotions

After implementation lands and the QA checklist in the template file is fully
checked off, move the template forward:

```bash
git mv "templates/candidate/${SLUG}.md" "templates/mvp/${SLUG}.md"
# update front-matter: status, last_reviewed_at, Promotion Log
```

When mvp templates have been live a cycle with no regressions, promote again:

```bash
git mv "templates/mvp/${SLUG}.md" "templates/production/${SLUG}.md"
```

### 4.3 Deprecations

From Step 1's `deprecate` verdicts:

```bash
git mv "templates/production/${SLUG}.md" "templates/deprecated/${SLUG}.md"
# update front-matter: status, deprecation_reason, superseded_by
```

Open a Livermore ticket to:

- Hide the template card in the gallery
- Add a deprecation notice for existing users with saved strategies of this
  type, pointing at `superseded_by`

### 4.4 Sync to Livermore

After all `mv` operations are committed to the repo:

```bash
# Dry run first
python apps/api/app/scripts/sync_knowledge_sources.py --plan
python apps/api/app/scripts/sync_template_lifecycle.py --plan

# Apply
python apps/api/app/scripts/sync_knowledge_sources.py --apply
python apps/api/app/scripts/sync_template_lifecycle.py --apply
```

These two scripts walk the markdown tree and upsert into the two tables
defined in `sql-schema.sql`. They are idempotent.

### 4.5 Close the cycle

Fill in `cycle-summary.md`. Headline + 3 bullets: what shipped, what deferred,
what we learned about process.

Schedule the next cycle kickoff (calendar invite, ~80 days out).

---

## Scheduled tasks (Cowork)

The framework relies on two scheduled tasks. Set them up once.

### Task 1 — `livermore-telemetry-monthly`

Frequency: **1st of every month, 09:00 local.**

Prompt:

```
You are running the Livermore template telemetry snapshot. Tasks:

1. Connect to the Livermore database (DATABASE_URL env var).
2. Run the queries in /Quant Strategy/cycles/_template/01-collect-telemetry.md
   §1.1 (backtests, save/fork counts, thumbs-down rate per template).
3. Write the results to /Quant Strategy/cycles/_telemetry-snapshots/<YYYYMM>.csv.
4. If any production template has backtests_90d < 5 OR thumbs_down_rate > 25%,
   open a short flag in /Quant Strategy/cycles/_telemetry-snapshots/<YYYYMM>-flags.md
   summarizing which templates and why.

Output: confirm files written, list any flags raised.
```

### Task 2 — `livermore-quarterly-kickoff`

Frequency: **First Monday of Jan, Apr, Jul, Oct, 09:00 local.**

Prompt:

```
Kick off the next Livermore template library refresh cycle.

1. Determine the next cycle id (e.g. Q3-2026).
2. Copy /Quant Strategy/cycles/_template/ to /Quant Strategy/cycles/<cycle>/.
3. Read the most recent telemetry snapshot in /cycles/_telemetry-snapshots/
   and pre-fill the scorecard in 01-collect-telemetry.md.
4. Run a web search for "best new quantitative equity strategies 2026"
   (adjust year) and "AQR / Robeco / Two Sigma research letters last 90 days".
   Save raw results to /Quant Strategy/cycles/<cycle>/_research-raw.md.
5. Notify the owner that the cycle is ready for manual review.

Stop. Do not modify templates/.
```

---

## Gates (don't skip)

- **Schema gate** — any new template must be expressible inside the current
  `StrategyJSON` schema, or the schema change has to be merged first. See the
  v2 strategy library doc's Prompt 1 for the additive-change pattern.
- **Evidence gate** — Tier-C templates ship behind a Pro-tier flag with a
  visible "evidence: mixed" badge. Never in the Starter gallery.
- **Capacity gate** — institutional-capacity templates ship behind a
  "Pro / requires data plan upgrade" lock with explanation.
- **Cost gate** — high-turnover templates (`short_term_reversal`,
  `news_sentiment_momentum`) must default to `slippage_bps ≥ 10` and warn the
  user if they edit lower.

---

## Anti-patterns to watch (revisit each cycle)

- **Library bloat.** If the gallery has > 20 templates, every new one needs a
  retire. Cap is 25.
- **Stale evidence.** Any template not reviewed in 4 cycles auto-flags for
  review.
- **Cycle drift.** If a cycle slips past 100 days, close it as-is and start
  the next one. Better cadence than perfect output.
