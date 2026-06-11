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

### Two providers, two entitlements — one being healthy says nothing about the other
**TL;DR:** when a "live data" surface lags but another looks fine, find out which provider each uses before theorizing. Different providers have independent plans, entitlements, and freshness.

2026-06-11: the active-execution chart was ~1 day stale while Market Pulse's Top Movers looked current. Tempting conclusion: "our cron is broken." Reality: Market Pulse pulls **FMP** `/stable/quote` (daily-granularity live overlay), while the intraday monitor pulls **AlphaVantage** `TIME_SERIES_INTRADAY`. Two providers. Market Pulse's health was no evidence about AV. The actual cause was an AV *entitlement* gap (see KNOWN_ISSUES 2026-06-11). The 30-second move that cracked it: curl the provider directly with the prod key.

**When to apply:** any "why is X stale but Y fresh?" question where X and Y are different surfaces — map each to its provider+endpoint first. Grep the service that builds the surface for which client it calls.

**See also:** `market_pulse_service.py` (FMP overlay) vs `intraday_bar_service.py` (AV); KNOWN_ISSUES.md 2026-06-11.

### Test the external API directly with the prod key — and never state a guess as fact
**TL;DR:** before blaming your code (or the provider's plan), reproduce against the real endpoint with the real key. And if you haven't, say "likely," not "is."

2026-06-11: I first told the user the intraday lag was "free-tier rate-limiting." That was a guess stated as fact — and wrong. A direct `TIME_SERIES_INTRADAY` call with the prod key (printing only timestamps, never the key) showed the latest bar was the previous session with *no* rate-limit note. Adding `&entitlement=realtime` returned the real cause verbatim: *"You are not yet entitled to realtime US market data access."* The provider will often tell you the exact problem if you ask it directly. Same family as the 2026-05-26 FMP saga (KNOWN_ISSUES "external API endpoints: don't hallucinate, verify") — but the failure mode here was *premature certainty*, not a wrong path.

**When to apply:** any data-freshness / "why is this empty" question involving a third-party API. Curl it with the prod env (`railway run bash -lc 'curl …$KEY…'`), parse only the safe fields, and read the provider's own error/note text before forming a theory.

**See also:** AV entitlement params (`realtime` / `delayed`); `apps/api/CLAUDE.md` trap #14.

### Per-slice tests verify the brick renders; end-to-end audit verifies a user can reach it
**TL;DR:** if the work crosses many bricks, the integration layer between them is its own surface area. Before declaring a feature done, ask "how does the user reach this?" — and answer it by tracing the route, not by trusting that the bricks compose.

PRD-16c shipped 8 backend + frontend slices over one continuous session. Each slice had its own tests; each brick rendered correctly; the backend tests went 1334 → 1431 with zero regressions. Technically complete after PR #178.

Then the wrap-up question:

> "How does the user enter Custom Mode?"

Two reachability gaps the per-slice tests couldn't catch:

1. **No Home tile.** `<EntryModePicker>` had three CTAs (Pick asset / Upload portfolio / Chat builder). Custom Build wasn't one of them. The flow definition's `triggers` array referenced `"strategy_builders/custom_build_cta"` but `grep -rn "startFlow.*custom_build_mode"` returned zero matches. The only way to reach the composer was typing the URL by hand. And even then, the flow's `compose_signals → null` terminal step would drop the user on the floor with a `"completed (v1 no-op)"` console log.

2. **`<ActiveExecutionDashboard>` had tests but no page imported it.** Strategy detail page didn't render it.

Same pattern bit PRD-19 Step 5/6: the `<MarkAsExecutedButton>` brick rendered correctly, but on the wrong surface — until the audit caught that the banner had to deep-link to the settings page for the round-trip to work. The lesson is symmetric.

**The discipline:** after the last brick PR but before declaring done, write the user journey end-to-end in plain English. Trace each click. For every "the user clicks X" sentence, `grep` for the call site. Missing call sites = reachability gaps. Wrong call sites = integration mismatches. This audit is cheap (~10 minutes) and catches a category of bug that no unit test can.

**When to apply:** any multi-PR feature that crosses brick + page + flow boundaries. Especially when the bricks are wired through a runtime indirection layer (FlowDefinition, FlowShell, event bus, etc.) where the integration is "trigger fires → flow advances" rather than "component imports component."

**See also:** PRs #179 + #180 (the two PRs that closed the gaps for PRD-16c); same pattern at PRD-19's banner→settings deep-link in PR #157; `agent-system/WORK_LOG.md` Current Session "Reachability audit caught two gaps before they shipped."

---

### The right small backend field can save a whole frontend page
**TL;DR:** when a feature spans two backend surfaces with different identity keys, don't build a parallel frontend page — extend one of the response shapes with the bridging id, gate the render on its presence.

PRD-16c-6's `<ActiveExecutionDashboard>` polls three owner-only endpoints under `/api/saved-strategies/{id}/…`. The id is the SavedStrategy UUID. The natural place to render the dashboard is the strategy-detail page at `/strategies/[slug]` — which fetches `/api/strategies/{slug}` and gets back a `BacktestRecord` keyed by slug, not by UUID. There's no UUID anywhere on the page.

Two paths to bridge it:

(a) **Backend field.** Add `saved_strategy_id: Optional[str] = None` to the `SavedStrategyResponse`. Look up the matching `SavedStrategy` row by `backtest_record_id` FK. Frontend conditionally renders the dashboard when the field is non-null. Non-owners hitting the dashboard's polls get 404 → the brick's built-in error state. ~10 lines total.

(b) **New page.** Build `/saved-strategies/[id]/` as an owner-only surface that fetches via the UUID-keyed route. Duplicate the strategy-detail page's layout. Build a new route, new auth check, new layout. ~80 lines.

(a) won. The right small backend field saved a whole frontend page. The contract is: "if a SavedStrategy exists for this BacktestRecord, give us a UUID we can probe" — the response surfaces existence + probe-ability without revealing ownership. Non-owners get the same 404 they'd get on the parallel page; owners get the dashboard. No leakage, no duplication.

**When to apply:** when a brick or component needs an id that lives on a parallel data model, and you're considering a new page. Check whether a single optional bridging field can defer the page until a real reason emerges. The parallel page often turns out to never be needed.

**See also:** PR #180 (`SavedStrategyResponse.saved_strategy_id`); `apps/api/app/api/routes/strategy_storage.py::get_saved_strategy`; the strategy-detail page's conditional render gate.

---

### Additive schema changes must be verified by re-running every existing test, not by reading the diff
**TL;DR:** if a PR adds a new field that existing code doesn't set, "the existing code is unaffected" is a hypothesis until proven by 1000+ green tests. Don't ship the assumption; prove it.

PRD-16b-1 added 3 new optional fields to `StrategyRule` (`primitive_id`, `primitive_params`, `logic_with_prior`) plus a new `"custom_build"` strategy_type. The HANDOFF pitfall C said: *"existing 22 strategy_types must continue backtest-identical after PRD-16b ships."* Every reasonable reading of the diff said "this is additive — existing code doesn't reference these fields, so it can't be affected."

But the validators on `StrategyJSON` could affect existing strategies. The `logic_with_prior` contract says "first rule has no logic_with_prior" — applied universally, that would actually be fine for the 22 templates (they all set `logic_with_prior` to None implicitly via the default). But what about the "subsequent rules must have logic_with_prior" check? Several existing templates have 2-rule blocks (rsi_mean_reversion has `buy_rule + sell_rule`). If I applied the contract universally, those templates would break.

The fix was to scope the contract to `custom_build` only:

```python
if i > 0 and rule.logic_with_prior is None and self.strategy_type == "custom_build":
    raise ValueError(...)
```

I knew the answer was right because **the existing tests caught the wrong version**. Run the full suite (1316 tests) — if all green, additivity is proven; if any red, the diff isn't actually additive. The mental shortcut "I added optional fields, so it must be additive" is wrong when the fields participate in validators or dispatch.

**When to apply:** any PR claiming an "additive change" to a load-bearing schema or interface. Run the full test suite as the proof, not just the new tests. If your test count goes from N → N + K and all N + K pass, the change is genuinely additive. If anything in the original N breaks, the change isn't.

**See also:** PR #167 (`apps/api/app/schemas/strategy.py` validator gated to `custom_build`); test_legacy_template_with_2_rule_block_still_validates pins the contract; full suite at 1316 passed before commit, 1334 after.

---

### When the editorial product IS the code, the editorial rules should be CI tests
**TL;DR:** if a 55-row catalog of plain-English descriptions is the load-bearing UX of the feature, encode the voice rules ("descriptive, not prescriptive") as parametrized tests that fail CI on drift — not as PR-review checklists.

PRD-16a-1 shipped a 55-row signal-primitive catalog where each entry is a 1-line plain-English description. Pitfall A in the spec was *"no prescriptive language — `Measures X` not `Buy when Y`."* The cost of a prescriptive description slipping through is a compliance problem (Livermore signaling "Buy at threshold Z") + a UX problem (the catalog primes the user toward a specific strategy, not a building block).

Two ways to enforce the rule:

1. **PR review only.** Reviewer reads every catalog entry on every PR. Works for ~5 entries; breaks at 55.
2. **PR review + CI tests** that grep descriptions for trigger phrases.

The CI test is one parametrized check:

```python
@pytest.mark.parametrize("primitive", SIGNAL_PRIMITIVES, ids=lambda p: p.id)
def test_no_prescriptive_language_in_description(primitive):
    triggers = {"buy when", "sell when", "long when", "exit when", "enter when"}
    matches = [w for w in triggers if w in primitive.description.lower()]
    assert not matches, f"Primitive {primitive.id} uses {matches}"
```

It's 10 lines and runs in milliseconds. PR review now spot-checks **voice and accuracy**; the test enforces the **rule that's mechanical**. Each catches what the other can't: tests can't tell if "Measures the ratio of fast EMA to slow EMA" describes MACD accurately (a reviewer can), but PR review can't reliably catch a `buy when` slipping in on PR #163 of a 12-month build (the test always does).

**When to apply:** any feature where content is the product — catalog metadata, email templates, copy strings, error messages, glossaries. If a rule about the content can be expressed as a grep / format check / length constraint, it should be a CI test. The reviewer's attention is the scarce resource; spend it on what tests can't catch.

**See also:** PR #161 — `tests/test_signal_catalog.py` enforces voice + length + parameter presence + asset-class non-emptiness across all 55 entries. PR-G (May 2026) was the precedent: `whenInCopy`/`whenOutCopy` review at the PR layer caught half the issues; parametrized tests caught the other half.

---

### Lazy registration breaks circular imports — module-load side effects are the pattern, not bugs
**TL;DR:** when module A imports module B and B needs to register back into A, defer the registration to first use, not module load. Set a flag, run on first call, idempotent afterward.

PRD-16a-2 needed `signal_provider.py:_REGISTRY` (the existing 9 providers) to grow by ~46 entries from a new `technical_signal_providers.py` module. The natural shape — register at module load — broke immediately:

```python
# signal_provider.py
class SignalProvider: ...
_REGISTRY = {...}
from .technical_signal_providers import get_technical_providers  # ← imports A
_REGISTRY.update(get_technical_providers())

# technical_signal_providers.py
from .signal_provider import SignalProvider  # ← imports B
class SmaSignalProvider(SignalProvider): ...
def get_technical_providers(): return {...}
```

When Python first loads `signal_provider.py`, it tries to import `technical_signal_providers`, which tries to import `signal_provider` back — getting a half-initialized module. Result: `ImportError: cannot import name 'SignalProvider' from partially initialized module`.

The fix is to **defer the registration** until something actually needs the registry:

```python
# signal_provider.py
_TECHNICAL_PROVIDERS_REGISTERED = False

def _ensure_technical_providers_registered() -> None:
    global _TECHNICAL_PROVIDERS_REGISTERED
    if _TECHNICAL_PROVIDERS_REGISTERED:
        return
    _TECHNICAL_PROVIDERS_REGISTERED = True  # set BEFORE the import
    from .technical_signal_providers import get_technical_providers
    for name, provider in get_technical_providers().items():
        if name not in _REGISTRY:
            _REGISTRY[name] = provider

def get_signal_provider(name):
    _ensure_technical_providers_registered()
    return _REGISTRY[name]
```

Three things make this robust:
1. **Flag set BEFORE the import.** Defense for the same kind of re-entry the cycle was trying to cause.
2. **Idempotent.** Subsequent calls are O(1) flag check + dict lookup.
3. **Lazy.** Module load is fast; the cost only materializes on first use, and only once.

**When to apply:** any module that builds a runtime registry / dispatcher / plugin table where the entries live in a sibling module that needs to import the base class. The same pattern works for: event handler registries, schema validators, frontend route resolvers, ORM model auto-discovery.

**See also:** PR #163 (`apps/api/app/services/backtester/signal_provider.py:_ensure_technical_providers_registered`). The trap is documented as a Python idiom in `PEP 328`-ish discussions of import-time side effects but rarely flagged as a *design pattern*. It IS the pattern.

---

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

### Preview the EXACT rows before any prod backfill write — same WHERE, run as a SELECT first
**TL;DR:** a backfill is a prod mutation. Run the INSERT's predicate as a SELECT, show the matched rows, get a human OK, then write inside a transaction with an inline verification SELECT before COMMIT.

2026-06-11: backfilling the missing `SavedStrategy` rows (saves that predated the #191 bridge). Flow that worked: (1) `AskUserQuestion` to authorize the prod write + scope; (2) a preview SELECT with the *identical* WHERE the INSERT would use → exactly 1 candidate row, shown to the user; (3) `BEGIN; INSERT … SELECT … WHERE <same>; SELECT <verify>; COMMIT;`. No surprises, fully auditable, idempotent (`NOT EXISTS` guard so re-runs are safe).

**Gotcha that bit twice:** Postgres does **not** short-circuit a `json_typeof(x)='array'` guard before evaluating `json_array_length(x)` in the same WHERE — a scalar/`null` value throws `cannot get array length of a scalar`. Wrap the value so the length fn only ever sees an array: `json_array_length(CASE WHEN json_typeof(x)='array' THEN x ELSE '[]'::json END)`, ideally inside a `WITH … AS MATERIALIZED` CTE so the planner can't reorder it.

**When to apply:** any one-off data repair against production. Never `INSERT … SELECT` blind; the SELECT-preview is the cheap insurance.

**See also:** the 2026-06-11 backfill (KNOWN_ISSUES / project_log); `apps/api/CLAUDE.md` trap #12 (the `:bind::type` cast cousin).

For Postgres / SQLAlchemy-specific traps that bite repeatedly, see
**[`apps/api/CLAUDE.md`](../apps/api/CLAUDE.md)** — that file has 21
traps with examples and audit recipes, loaded automatically by Claude
Code sessions. This section is for higher-level abstractions, not
trap-level rules.

---

## Frontend

### Multi-day intraday belongs on an INDEX axis, not a real-time axis
**TL;DR:** plotting intraday bars by their real timestamp interpolates a misleading straight line across closed-market gaps and shows time-only labels you can't tell apart across days. Use an evenly-spaced bar-index x-axis (gaps collapse) with date-aware tick labels — what every brokerage chart does.

2026-06-11: the live chart used `XAxis type="number" scale="time"`. Two days of 30min bars rendered with overnight gaps drawn as slow price drift, and `09:30` appeared twice with no date. Fix (#197): map bars to ordinals `0..n-1`, draw the line on the index, label ticks with the **date at each new trading day** + time otherwise (ET), and snap event markers (`ReferenceDot`) to the nearest bar ordinal. Extracted the date/tick/gap logic into a pure helper (`intraday-chart-axis.ts`) so it's unit-testable apart from the recharts SVG (which jsdom can't size).

**When to apply:** any intraday/irregular time-series chart that spans more than one session. If the data has gaps (nights, weekends, halts), a real-time axis lies.

**See also:** `apps/web/src/components/active-execution/intraday-chart-axis.ts`, PR #197.

### Unify timezone bases BEFORE plotting — and force the display zone, don't rely on the browser
**TL;DR:** if two series on the same chart come from different tz bases, normalize them to one tz-aware instant on the backend first; then format the axis with an explicit `timeZone`, because `toLocaleTimeString()` defaults to the viewer's locale.

2026-06-11: intraday **bars** are stored naive US/Eastern (the AV wrapper parses ET strings naive), but **entry/trigger events** are `datetime.utcnow()` (naive UTC). On one axis the trigger dots would land ~4–5h off the price line. Fix (#196): backend converts bars via `.replace(tzinfo=ET)` and events via `utc.astimezone(ET)` so all timestamps are one ET-aware basis; frontend formats with `timeZone: "America/New_York"` so it reads ET for *every* viewer (Mr Gu is on +08 — browser-local would have shown China time). `zoneinfo` handles EST/EDT automatically; never hand-roll a fixed offset.

**When to apply:** any chart/table combining timestamps from more than one source, or any "this should show market time" requirement. Audit each source's tz at the model layer; pick one tz-aware basis; pass the display zone explicitly.

**See also:** `_bar_time_to_et` / `_utc_to_et` in `saved_strategies.py`, `fmtTime` in `intraday-chart.tsx`, PR #196.

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
