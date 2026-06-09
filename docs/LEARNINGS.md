# Livermore Learnings

A growing reference of **patterns, principles, and gotchas** distilled
from real Livermore work. Different from the other in-repo docs:

| Doc | What it's for |
|---|---|
| `docs/KNOWN_ISSUES.md` | Production crash post-mortems — what broke, what fixed it |
| `docs/BUILDING_LIVERMORE_JOURNAL.md` | Episodic narrative — "this is what it felt like to build that day" |
| `apps/api/CLAUDE.md` (traps) | Code-level traps that bite repeatedly — load before editing backend |
| **`docs/LEARNINGS.md`** (this file) | **Abstracted lessons — patterns to apply on the NEXT problem, not narratives of past ones** |

> **How to use this file:** Read the topic that matches the problem
> you're working on RIGHT NOW. Each entry tells you the lesson in one
> line, gives concrete reasoning, and links to the original work so you
> can audit the claim.
>
> When you finish a meaningful chunk of work and notice a transferable
> pattern, add it here. Put new entries at the top of their topic
> section. Each entry follows the template:
>
> ```
> ### Title — short, imperative
> **TL;DR:** one-line takeaway.
>
> Full explanation.
>
> **When to apply:** specific signals that say "this lesson is relevant."
>
> **See also:** in-repo links + commit/PR refs.
> ```

---

## Topics

- [Performance](#performance)
- [Diagnostic methodology](#diagnostic-methodology)
- [Database](#database)
- [Frontend](#frontend)
- [Operations](#operations)
- [Documentation + process](#documentation--process)

---

## Performance

### Cold paths are invisible in dev — measure them explicitly in production
**TL;DR:** if you never `curl bypass_cache=true` against prod, you have no idea what the first user of the morning is experiencing.

In dev you load a page constantly, so the cache is always warm. You see
the 2-second warm response, never the 80-second cold one. Cold-cache
pain only becomes visible at production scale where requests are sparse
enough that the cache regularly expires between users.

The Market Pulse cold path was 80–110 seconds for 6+ weeks before
anyone noticed. It wasn't noticed because every dev cycle hit the warm
cache. Jimmy only saw it because he visited the CN page (low ambient
traffic → frequent cold hits) one morning and went "wtf this is slow."

**When to apply:** any endpoint that has a server-side cache, especially
if you've added one recently without measuring the cold path. Before
shipping a feature with a cache, the diagnostic ritual is:

```bash
# Time cold (forces recompute):
curl -s -o /dev/null -w "%{time_total}s\n" \
  "https://your-api/endpoint?bypass_cache=true"

# Then time warm:
curl -s -o /dev/null -w "%{time_total}s\n" \
  "https://your-api/endpoint"
```

If cold > 5s, decide whether to fix the cold path or pre-warm.

**See also:** PR #138 (the pre-warm fix), commit `0cdecb9`.

---

### Pre-warming hides cost without fixing it — sometimes that's the right tradeoff
**TL;DR:** the user never waits, but the server still pays. Make sure that's the deal you want.

When a cold computation costs 80 seconds, you have two distinct moves:

1. **Make the computation faster** (e.g., fix N+1 queries, batch external
   calls). User AND server win, but it's deeper work with bug surface.
2. **Pre-warm a cache on a schedule** so the cost is paid in the background
   instead of in the user's request. User wins immediately; server pays
   the same total cost — just at a predictable cadence instead of
   sporadically when traffic happens to land cold.

Pre-warm is the right first move when (a) the cost is bounded and you
can afford to pay it every N minutes, (b) the computation is structurally
safe to run in the background, and (c) you want a small surgical change.
Move to the deeper fix when (a) compute cost matters to the bill, (b)
the pre-warm interval forces an awkward staleness window, or (c) you
add a new caller that can't benefit from pre-warm.

**When to apply:** any expensive computation that produces data that
doesn't change every second (i.e., reasonable to cache for minutes).

**See also:** `_warmup_market_pulse_loop` in `apps/api/app/main.py`, PR #138.

---

### Skip the upstream call when the upstream doesn't have the data
**TL;DR:** silent-empty responses from an external API still cost a network round-trip per symbol. Stop calling them.

The CN Market Pulse path was firing `live_quote_service.get_quotes(...)`
against the full CN universe (`.SZ` / `.SS` tickers). FMP doesn't carry
A-shares; every call returned empty / 404 after a real network round-trip.
For 50+ CN symbols, that was 15–25 seconds of pure latency producing
zero enrichment. The bug existed for weeks; nobody noticed because the
overlay's try/except-shaped failure looked like "we tried; got nothing"
instead of "we should have skipped this entirely."

This is the same family as `apps/api/CLAUDE.md` trap #14 ("LLMs
confidently generate calls to APIs that don't exist; failure is silent
if you wrap it in try/except"). Wrap-and-pray on a known-empty upstream
is an anti-pattern — it makes the cost invisible but doesn't remove it.

**When to apply:** any code path that calls an external API and gets
mostly-empty responses. If 80%+ of calls return empty, ask whether the
calling condition can be checked upfront. For us, "`if market == 'CN':
return base`" deleted 15–25s of waste.

**See also:** `get_live_pulse` CN early-return in `market_pulse_service.py`,
trap #14 in `apps/api/CLAUDE.md`, PR #138.

---

### Optimize what actually costs money — read the bill BEFORE writing code
**TL;DR:** on Railway, memory is usually 90%+ of the cost; CPU is rounding error. Optimizing CPU on a memory-bound workload changes nothing.

Day-one mental model: "expensive compute = expensive bill." Real Railway
billing on the $5 Hobby plan as of 2026-06-05:

| Resource | Usage (5 days into cycle) | Cost | % of bill |
|---|---|---|---|
| Memory | 11,913 GB-min | $2.76 | **93%** |
| CPU | 91.7 vCPU-min | $0.04 | 1% |
| Egress | 0.52 GB | $0.03 | 1% |

The pre-warm I added to Market Pulse runs an expensive computation
every 4 minutes — CPU cost was the obvious mental concern when
considering follow-up optimization work. The actual bill said CPU is
free; memory is what matters. The follow-up CPU optimization wouldn't
have saved a dollar.

**When to apply:** every time you're about to do "cost-driven" perf
work, look at the actual bill breakdown first. Railway dashboard →
Project → Usage → "View Cost by Service." Match what you're about to
optimize against the column that dominates the bill.

This is the empirical version of "premature optimization is the root of
all evil" — refined to "wrong-axis optimization is also evil." If memory
is 93% of the bill, drop heavy imports, shrink object graphs, or move
to a smaller container. Don't batch SQL queries.

**See also:** the 2026-06-05 cost analysis in this session's WORK_LOG entry.

---

### N+1 queries are the dominant slow path for list-rendering APIs
**TL;DR:** if a list endpoint loads each item's details in a separate query, that's the bottleneck. Batch into one query.

`_build_cn_top_assets` and `_build_top_assets` in
`apps/api/app/services/market_pulse_service.py` do this:

```python
rows = db.execute(text("SELECT ... FROM symbols WHERE ..."))   # 1 query
for row in rows:                                                # ~500 rows
    bars = _load_bars(row.symbol, db)                          # 1 query each
    # ...compute CMF, build card...
```

That's 501 queries per cold computation, and the per-symbol query is the
dominant time cost. The same shape exists across `_build_sector_card`,
`_build_index_card`, `_build_macro_card`. Each one was fine when the
universe was 10 stocks; at 500+ stocks it's the dominant cost.

The right pattern:

```python
symbol_to_bars = _batch_load_bars(symbols, db)   # 1 query for all
for row in rows:
    bars = symbol_to_bars[row.symbol]
    # ...
```

Not yet done in this codebase — filed as backlog item §5 with trigger
"only do when pre-warm cost shows up in the bill OR a new caller can't
benefit from pre-warm."

**When to apply:** any service builder that iterates a list and calls
the DB inside the loop. Easy to spot: grep for `for ... in ...:` inside
a service function and look for `db.execute` / `db.query` in the body.

**See also:** `_build_cn_top_assets` (lines ~464–517 of
`market_pulse_service.py`), `_build_top_assets` (~356–461), PR #138
deferred follow-up.

---

## Diagnostic methodology

### When two data models share a UI surface, place the action on the model that owns the data
**TL;DR:** if model A has the field your action needs but the spec puts the action on model B, move the action — don't thread A's field through B's page.

PRD-19's spec said "Mark-as-Executed button on the strategy detail page." Reasonable on the surface. The detail page at `/strategies/[slug]` serves **legacy `BacktestRecord`** rows (slug-based). The mark-executed endpoint takes **`SavedStrategy.id`** (a different table). Two ID surfaces, two data models, one PRD asking them to meet on the same page.

Two ways out:
1. **Thread `SavedStrategy.id` through `BacktestRecord`** — denormalize, add a slug→id resolver call on page load, or stuff the id into the URL. Each option leaks the new model into the legacy surface; future PRs touching the detail page have to know about both.
2. **Move the action to a surface that already owns `SavedStrategy.id`.** The in-app banner already carries it (per Step 3b's `dispatch_in_app_banner`, `strategy_slug=strat.id`). Inlining `MarkAsExecutedButton` on each banner row closes the loop without touching the detail page.

We chose (2). Same user behavior (the click happens on the surface where the notification is); cleaner code (the legacy detail page stays a `BacktestRecord` page); no schema denormalization. The trick was noticing that "the spec says X" and "X is the right architecture" aren't always the same — when the data model fights the spec, the model wins.

**When to apply:** any spec asking you to render or act on data from one model on a UI surface owned by a different model. Before threading the ID through, ask: "is there another surface where the data already lives?" The notification banner, the email body, the in-app inbox, the user's saved list — these are all places where the right ID surface might already be available.

**See also:** PR #157 (PRD-19 Step 5+6) — `apps/web/src/components/notifications/notification-banner.tsx` inlines `MarkAsExecutedButton`. PR spec was [`agent-system/plans/PRD-19-phase-b-reshape.md`](../agent-system/plans/PRD-19-phase-b-reshape.md) §"Strategy detail page extension" (the architecture we deliberately departed from).

---

### Template literals that look like substituted strings — grep them BEFORE shipping
**TL;DR:** if your email body contains `{{unsubscribe_url}}` and you never wrote substitution code for it, the recipient gets `{{unsubscribe_url}}` in their inbox. Tests that snapshot the rendered html catch it; tests that snapshot the template don't.

PRD-19 Step 3b's signal-change email body had `<a href="{{unsubscribe_url}}">` in its compliance footer. The pattern was inherited from `welcome.py` — but `welcome.py` actually built `unsub_url` with `make_unsub_token(...)` and interpolated it via an f-string at render time. The signal-change render forgot the f-string + the token mint. The literal `{{unsubscribe_url}}` shipped to recipients (would have, if PRD-19 hadn't been paused for reshape first).

Same bug class hit Step 4b's digest renderer (`{{base_url}}/strategies`, `{{settings_url}}`). Same class hit Step 4c's unsub endpoint, where the switch ladder didn't know about `daily_digest` or `signal_alerts_<id>` so the signed token (correctly minted upstream) fell through to "expired or invalid."

The cross-cutting pattern: when a feature defines NEW categories / templates / token shapes, every GATE / SWITCH / RENDER that handled the OLD shapes has to grow a new branch. If the new branch is missing, the new shapes silently fall through to a no-op or a default — and "no-op" looks identical to "shipped" until a user clicks.

**Audit step before shipping a feature with new categories:**

1. Grep for the new category name in the codebase. Every render / switch / dispatch must mention it.
2. Render the actual rendered output (not the template source) in a test. Look for `{{` and `}}` — those are unsubstituted placeholders.
3. If your CAN-SPAM webhook has a switch ladder, the new category must appear in it. Default-to-friendly-page anti-enumeration hides bugs here — silence looks identical to success.

```python
# In your render test:
rendered = render_signal_change(user, payload)
assert "{{" not in rendered["html"], "unsubstituted placeholder in html"
assert "{{" not in rendered["text"], "unsubstituted placeholder in text"
```

**When to apply:** any PR that adds a new template / email category / signed-token kind / switch arm. Especially when porting / extending an existing renderer — the inherited code may have `{{...}}` placeholders that the original render path handled via inline f-string substitution; if you copy the template but forget the substitution, the placeholder ships verbatim.

**See also:** PR #152 (Step 3b — caught + fixed), PR #154 (Step 4b — same pattern with `{{base_url}}`), PR #155 (Step 4c — switch-ladder fall-through). Originated from PR #88's reshape — three latent bugs all sharing the same shape.

---

### Tests in CI containers (UTC) silently pass code that breaks in local TZ — and vice versa
**TL;DR:** if `today` is local-TZ but `utcnow()` is UTC, the test catches the bug at the local-vs-UTC boundary. Run your test in the worktree's TZ before merging.

The 2026-06-08 throttle test in PRD-19 Step 3b passed in CI (containers run UTC) but failed the moment Step 4a's worktree opened in local TZ. The throttle-seeding query computed a window from `date.today()` (local) but read events with `email_dispatched_at = datetime.utcnow()` (UTC) — at 23:42 UTC the events fell INTO the previous local day's window AND OUT of the current local day's window, so the seeding query returned 0 rows and the throttle silently reset across cron ticks.

This is trap #16's mirror image: trap #16 is about a verification script computing today wrong; this one is the application code itself computing two different "today"s. The same fix applies: compute `today` in the TZ the data was written in.

```python
# WRONG — local-TZ today vs UTC writes
today = date.today()
events_today = db.execute(
    select(SignalEvent).where(
        SignalEvent.email_dispatched_at >= datetime(today.year, today.month, today.day)
    )
).all()

# RIGHT — UTC today AND UTC writes
today = datetime.utcnow().date()
events_today = db.execute(
    select(SignalEvent).where(
        SignalEvent.email_dispatched_at >= datetime(today.year, today.month, today.day)
    )
).all()
```

**The test-catching-its-own-regression property:** the throttle test's premise was "second same-day flip should be throttled." With local TZ ahead of UTC, the test's first-tick events were dispatched at "today-1 UTC," but the test computed "today local" for the throttle window. The window missed the events, the throttle didn't seed, the second tick fired. The test failed — but only because it actually exercised the cross-tick path. Tests that only run inside a single cron tick (and thus only check the in-memory dict, not the seeded version) would have passed silently.

**When to apply:** any cron / scheduled job whose state straddles ticks via the DB. Audit any `date.today()` against any `datetime.utcnow()` writes that the same code path later reads. Either pick one TZ for both, or pass `today` in explicitly as a function argument so tests can vary it.

**See also:** PR #153 fix in `app/jobs/signal_cron.py`, trap #16 in `apps/api/CLAUDE.md`, the 2026-05-26 SP500 verification false-alarm that originally codified trap #16.

---

### Single-user post-deploy verification can't catch concurrency bugs by design
**TL;DR:** "I curled it once after deploy and it returned 200" is necessary but not sufficient. Concurrency bugs need concurrent load to manifest.

The 2026-06-07 outage walked through this directly. PR #138 introduced a recurring background warmup that called a singleton holding `asyncio.Lock` instances. The lock-collision bug only fires when:
1. The warmup is mid-flight (lock acquired) on event loop A
2. A user request lands on event loop B and tries to acquire the same lock

A single sequential curl after deploy — one user, no concurrency — cannot create those conditions. PR #138's "verified live in production" curl returned 200 in 2s and looked perfect. The bug detonated 48 hours later when concurrent US traffic finally hit the lock-contention pattern, taking the page down for 28+ minutes.

The lesson is not "write a load test for every PR" — that's overkill. It's "**if your change interacts with locks, queues, connection pools, or any shared mutable state across event loops or threads, your post-deploy verification has to be concurrent**." Two browser tabs hammering refresh, or:

```bash
# Cheapest "real concurrency" check — 10 parallel curls:
for i in $(seq 1 10); do curl -s -o /dev/null -w "%{time_total}s | %{http_code}\n" "$URL" & done; wait
```

If any of them hangs, your sequential curl was lying to you.

**When to apply:** any PR that touches an `asyncio.Lock`, `asyncio.Queue`, `asyncio.Semaphore`, `asyncio.Event`, DB connection pool, thread-bridge warmup, or a service singleton that holds any of the above.

**See also:** PR #140 hotfix, trap #22 in `apps/api/CLAUDE.md`, Episode 34 in `docs/BUILDING_LIVERMORE_JOURNAL.md`.

---

### Time cold + warm separately to see what your users actually pay
**TL;DR:** "the page is slow" is not measurable. Cold latency, warm latency, and cache hit rate are.

When Jimmy said "Market Pulse is slow, especially for CN," the first
honest diagnostic move was a table of measured numbers:

| Call | Cold | Warm |
|---|---|---|
| `/api/market/pulse?market=CN` | 78.6s | 1.75s |
| `/api/market/pulse?market=US` | 108.7s | 1.78s |
| `/api/market/pulse?market=CN&bypass_cache=true` | 110s | — |
| `/api/market/history-rhymes?market=CN` | 2.0s | — |
| `/api/market/data-latency` | 1.5s | — |

That table immediately resolved three things:
1. The slowness is NOT CN-specific; both markets have a 80–110s cold path
2. CN feels worse only because lower traffic = more frequent cold hits
3. The slow endpoint is `/pulse`, not `/history-rhymes` or `/data-latency`

The fix scope crystallized from "make CN faster" (vague) to "kill the
80s cold path on `/pulse`" (actionable).

**When to apply:** any "X is slow" complaint. Before opening any code,
generate the cold/warm/cache-state matrix for every endpoint X touches.

```bash
# Cold (worst case):
curl -s -o /dev/null -w "TTFB: %{time_starttransfer}s | total: %{time_total}s\n" \
  "https://your-api/endpoint?bypass_cache=true"

# Warm (immediately after):
curl -s -o /dev/null -w "TTFB: %{time_starttransfer}s | total: %{time_total}s\n" \
  "https://your-api/endpoint"
```

**See also:** the 2026-06-05 diagnostic transcript (see this session's commit).

---

### Read the cost dashboard before you size the fix
**TL;DR:** the right fix depends on the constraint. The constraint is whatever shows up on the bill.

Before today I would have recommended fixes #3 + #4 (batch SQL queries,
limit candidate pool) as the "right" follow-up to Market Pulse perf
work. Reading the Railway bill changed that:

- Pre-warm added background compute → "uses CPU/memory" was the worry
- Bill shows CPU is 1% of the cost; memory is 93%
- Pre-warm's memory footprint is ~220 KB per cached response vs 1.5 GB
  baseline → also negligible
- → Fixes #3+#4 would optimize the wrong axis. Don't do them.

If the same diagnosis had shown "CPU is 60% of the bill," the answer
would have flipped. The fix's value is conditional on the cost shape.

**When to apply:** any time you're choosing between optimization
strategies. The dashboard takes 30 seconds to check; it makes the
decision for you.

**See also:** PR #138 thread, the cost analysis on 2026-06-05.

---

### Karpathy: think first, simplicity, surgical, goal-driven
**TL;DR:** four principles that consistently produce better code than "just start writing."

1. **Think before coding** — describe the problem in one paragraph before
   any keystroke. If you can't, you don't understand it yet.
2. **Simplicity first** — the smallest change that produces the desired
   outcome is the right change. Over-engineering today is regret tomorrow.
3. **Surgical changes** — every changed line traces directly to the
   request. If you can't justify a line, delete it.
4. **Goal-driven execution** — define what success looks like (a
   measurable criterion) before starting. "Make it faster" is not a goal;
   "warm CN page loads in <5s" is.

Applied to today's perf work:
- Goal: defined upfront as "CN cold path → <5s"
- Surgical: pre-warm + CN-skip, 50 lines of production code
- Simplicity: didn't touch the N+1 pattern, didn't restructure the
  service singleton, didn't add new infra
- Think first: measured cold/warm before writing any fix; cost analysis
  before recommending follow-ups

**When to apply:** every non-trivial change. The four principles are in
`feedback_karpathy_coding_principles.md` (user memory) and apply by
default. Source: https://github.com/multica-ai/andrej-karpathy-skills.

---

## Database

*(empty — add entries as we accumulate them)*

For Postgres / SQLAlchemy-specific traps that bite repeatedly, see
**[`apps/api/CLAUDE.md`](../apps/api/CLAUDE.md)** — that file has 21
traps with examples and audit recipes, loaded automatically by Claude
Code sessions. This section is for higher-level abstractions, not
trap-level rules.

---

## Frontend

*(empty — add entries as we accumulate them)*

For Next.js 16 specifics that diverge from training data, see
**[`apps/web/AGENTS.md`](../apps/web/AGENTS.md)**.

---

## Operations

### Logs you don't watch aren't observability — surface to `/health`
**TL;DR:** `logger.exception(...)` is necessary but not sufficient. If nobody scrapes the log, the failure is invisible.

Trap #20 (in `apps/api/CLAUDE.md`) gave us "use `logger.exception` not `logger.warning` so the traceback survives." We followed it correctly in PR #138. Result: when the warmup started failing every 4 minutes on 2026-06-07, the tracebacks were present in Railway logs — and **nobody read them**. The failure ran silently for 28+ minutes before Jimmy noticed users hitting a broken page.

The fix isn't more logging; it's surfacing the same signal somewhere a one-minute external scraper can poll. PR #141 (`/health` warmup freshness) does this: the same warmup failure that wrote a traceback ALSO updates `_pulse_warmup_state["consecutive_failures"]`, which flips `/health` to `status: degraded` within ~12 minutes. A cron / monitor / external uptime checker sees the change immediately.

**Pattern:** for every background task whose silent failure would degrade users, expose its health on `/health` (or a similar always-on programmatic surface). Not just logs.

**When to apply:** any new cron, warmup loop, periodic refresh, or background poller. Add a "last success at" timestamp + a "consecutive failures" counter, expose both on a route an external monitor can hit.

**See also:** PR #141, `_pulse_warmup_state` in `apps/api/app/main.py`, the A+B+C+D arc on 2026-06-07.

---

### The reliability stack pattern: detect → cushion → notify → guide
**TL;DR:** Four distinct layers, each cheap, each independently shippable. Don't skip the cheap layers because you're worried about the expensive ones.

When the 2026-06-07 outage exposed how brittle the previous "we'll notice when users complain" model was, the natural temptation was to leap straight to auto-remediation. Instead we shipped four narrower PRs that each solve one layer:

| Layer | What | Cost | Risk if absent |
|---|---|---|---|
| **A. Detect** | `/health` exposes warmup freshness as a programmatic signal | ~1h, read-only | Silent failures stay silent |
| **B. Cushion** | Frontend renders cached fallback + banner when backend fails | ~2-3h, UX-only | Users see broken pages during incidents |
| **C. Notify** | Cron polls `/health`, emails on degraded | ~2-3h, opt-in | You learn from users, not telemetry |
| **D. Guide** | Triage bundle endpoint returns markdown ready to paste into Claude | ~3-4h, low risk | The 3 AM incident response is slow because nobody has context |

Each layer is cheap individually. Together they convert outage UX from "broken page, panicked debugging" to "stale snapshot, paged within 12 min, agent diagnosing within a click." We explicitly did NOT do auto-remediation (rollback / restart on alert) because the false-positive cost outweighs the time saved at this traffic scale.

**When to apply:** any critical surface that doesn't yet have a detect/cushion/notify/guide stack. New product surfaces (PRD-15 Thesis Builder, PRD-16 Custom Build) should consider all four layers before shipping if they touch external APIs or DB heavily.

**See also:** PRs #141, #142, #143, #144 — each one is the canonical reference for its layer.

---

### Env-var-gated rollout: ship the wiring, gate the activation
**TL;DR:** Let the code land in production with the behavior change defaulting OFF. Flip the env var when you're ready, no redeploy needed.

PR-C (email alerter) was a perfect example. Landing the cron + email pipeline meant the wiring was complete — code reviewed, tests pinning the state machine, route registered, Railway deployed. But the actual notification only fires when `OPS_HEALTH_ALERTS_ENABLED=true` AND `OPS_ALERT_RECIPIENT` is set.

Benefits:
- **Decouple "code shipped" from "behavior changed"** — landing is low-stakes; flipping is the high-stakes moment, but it's a 30-second Railway dashboard click, not a redeploy.
- **PR review focuses on what changed** — the cron logic and the email template, not "did we accidentally break something downstream."
- **Easy rollback without revert** — if the alerter misbehaves, set the env var to false. Code stays as-is.

Anti-pattern: shipping the wiring + flipping the switch in the same PR. That bundles two distinct risks (does the code work? does the behavior change make sense?) into one verification step.

**When to apply:** any new notification, scheduled job, or behavior-changing background task. The default for a fresh env var should be the previous behavior (off / disabled / no-op).

**See also:** PR #143 (`ops_health_alerts_enabled`), PR #144 (`ops_triage_token`), and earlier examples like `GATING_ENABLED` (Stage 1) and `signal_alerts_enabled` (Stage 8).

---

For production post-mortems and Railway/Postgres operational gotchas,
see **[`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md)**.

---

## Documentation + process

### When you finish a meaningful chunk, write down the transferable lesson — not just the narrative
**TL;DR:** Episodic recall fades; abstracted patterns travel. Write the abstraction here, the narrative in the journal.

When a piece of work finishes, two things are worth capturing:

1. **The narrative** — what happened, what it felt like, what surprised
   you. This goes in `docs/BUILDING_LIVERMORE_JOURNAL.md`. It's how
   future-you re-lives the day.
2. **The transferable lesson** — the rule that would have shortcut the
   work if you'd known it on day one. This goes here. It's how
   future-you doesn't re-walk the same path.

Don't conflate them. The journal entry "Pre-warm fixed Market Pulse"
doesn't help future-you on the next perf bug. The lesson "Cold paths
are invisible in dev — measure them explicitly in production" does.

After every meaningful chunk: ask "what would I tell my past self before
they started this?" The answer goes here.

**When to apply:** any time you finish work that taught you something
non-obvious. If the answer to "what did I learn?" is concrete enough to
put a title on, add an entry.

---

*This file was created 2026-06-05. The pattern is meant to outlast any
particular session — if you find an entry that's been wrong for a while,
fix it. If you find a topic missing, add the section header even if you
have nothing to fill it with yet — the empty slot is an invitation.*
