# Quant Engine — blueprint coverage map

> **What this file is.** The canonical map from the *Personalized Entry & Exit
> Optimization Engine* blueprint (1,792 lines, 27 Aug 2026, §1–§40) to the
> PRD-43 packet and to what actually ships. It answers three questions in one
> place: **what did the blueprint ask for, what exists today, and what is still
> unanswered.**
>
> **This is a REFERENCE, not a log.** State goes in
> [`agent-system/WORK_LOG.md`](../agent-system/WORK_LOG.md); history goes in
> [`project_log.md`](../project_log.md). Update this file when a blueprint
> section changes status or an open question closes — not on every PR.
>
> Rendered page (same content, easier to scan):
> https://claude.ai/code/artifact/0c034151-b9a5-4e85-b0f8-9ec0bfe899db
>
> Blueprint source: `~/Downloads/Product Spec — Personalized Entry & Exit
> Optimization Engine.md` — **not in git**, and the only copy. Worth committing
> somewhere durable.
>
> *Mapped 2026-09-09 against `da6bb7b`; refreshed 2026-09-10 against `172c2ca` (#362–#365).*

---

## Scoreboard

| | |
|---|---|
| Blueprint §37 P0 items shipped | **9 / 10** — the gap is item 9, the trade-detail page |
| Rule-discovery sections built (§16–22, §35) | **0 / 8** — the counterfactual engine is untouched |
| Episodes measurable on the live account | **33 / 57** (58%) — `price_bars` holds no ETFs or ADRs |
| Timing classifications shipped vs asked | **12 / 7** |
| Merged through | **#365** — #362 fixed the leak serialisation, #363–#365 reworked the portfolio/Home entry surfaces |

---

## The chain a user walks today

Connect a broker and steps 1–7 run end to end. Steps 8 and 9 do not exist.

| # | Step | Status |
|---|---|---|
| 1 | Connect a brokerage account (SnapTrade, read-only) | ✅ |
| 2 | See the raw record — holdings, performance, account value, orders | ✅ |
| 3 | See what the habits cost | ✅ |
| 4 | See *when* the money leaks — markouts, MAE/MFE, setups, habits with trades | ✅ |
| 5 | Set a fix — exit-plan card → `POST /api/mirror/exit-plan` | ✅ |
| 6 | Keep the finding — `/account/rules` | ✅ |
| 7 | Have the position watched — `daily_position_jobs` → notification → ticket | ✅ |
| 8 | **Drill into a single trade** — blueprint §27 | ❌ |
| 9 | **Find out whether the rule is any good** — blueprint §22 | ❌ |

Step 9 is why `Rule.status` can never reach `tested`.

---

## Blueprint → spec → status

Grouped by the blueprint's own three phases (§3). The § number is the join key.

### P0 — Entry / Exit Analysis (describe the record)

| § | Blueprint asks for | PRD | Status | Note |
|---|---|---|---|---|
| §4 | Broker execution record + daily bars | 43a | ✅ | Market-data coverage is the weak leg |
| §5 | Trade reconstruction, weighted average | 43a §3.8 | ✅ | **Diverged** — runs backwards from `/positions` |
| §6 | Asset filtering, nine classes | 43a | ⚠️ | Binary `is_cash_equivalent` only |
| §7–8 | Entry analysis + markout 1/3/5/10/20D | 43b P0 | ✅ | Exactly the spec's horizons |
| §9–10 | MAE / MFE | 43b P0 | ✅ | Same-day episodes fall out — no intraday |
| §11 | Profit capture ratio | 43b P0 | ✅ | `median_capture` |
| §12 | Exit markout | 43b P0 | ✅ | Negated |
| §13–14 | Entry & exit timing classification | 43b P0 | ✅ | **Exceeds spec** — 5 setups + 7 outcomes |
| §15 | Technical feature snapshot | 43b P0 | ✅ | `snapshot.py` |
| §27 | Individual trade page | 43b P0 | ❌ | **Last open item on P0's DoD** |
| §29–30 | Entry & exit analysis screens | 43b | ✅ | "After you buy" / "After you sell" |
| §32 | Separation of concepts | all | ✅ | The `setup_type` / `timing_outcome` boundary |
| §33–34 | Architecture + core data objects | 43a/43b | ✅ | Module layout matches |

### P1 — Rule Discovery (test what would have worked better)

| § | Blueprint asks for | PRD | Status | Note |
|---|---|---|---|---|
| §16 | Personalized pattern discovery | 43b P1 | ❌ | |
| §17–18 | Counterfactual entry testing + rule evaluation | 43b P1 | ❌ | **This is the actual engine** |
| §19 | Counterfactual exit testing | 43b P1 | ❌ | |
| §20 | Rule comparison | 43b P1 | ❌ | |
| §21 | Rule robustness | 43e | ⚠️ | `_is_round` ships; sample/stability floors do not |
| §22 | Validation — 70/30, walk-forward, confidence labels | 43d | ❌ | Why `tested` is unreachable |
| §35 | Rule discovery object | 43b P1 | ❌ | |

### P2 — Strategy Generation (turn a rule into something that runs)

| § | Blueprint asks for | PRD | Status | Note |
|---|---|---|---|---|
| §23 | Strategy recommendation output | 43a v3 | ✅ | The exit plan |
| §24 | Strategy editing | existing | ✅ | Pre-existing framework |
| §25 | Strategy persistence | 43e | ✅ | `SavedStrategy` + `Rule` |
| §26 | Continuous strategy runner | 43a | ✅ | `daily_position_jobs` |
| §28 | Portfolio-level analytics | 43c | ❌ | The whole HOW MUCH dimension |
| §31 | Strategy discovery page | 43d | ❌ | |
| §36 | Strategy conversion | 43a v3 | ⚠️ | One path converts; nothing general |

---

## Where we deliberately left the blueprint

1. **Reconstruction runs backwards.** §5 describes executions → episodes. A forward
   walk over the same 416 activity rows produced five phantom open positions against
   a broker holding no equities. Backwards gives zero negative holdings across 731
   daily snapshots.
2. **§8's worked example does not reproduce.** The blueprint shows a clean markout
   shape and reads a diagnosis off it. On the live account both profiles are noise —
   quartiles straddle zero at every horizon — so `has_consistent_pattern` exists to
   say that rather than narrate meaningless medians.
3. **The classification set grew, and split.** Seven labels asked for, twelve shipped,
   divided by something the blueprint never names: `setup_type` is known at decision
   time and may compile into a rule; `timing_outcome` is retrospective and never can.

---

## Problems settled

All found by running against a real account, not fixtures. **This packet's failure
mode is not a broken page — it is a plausible number.**

- **Giveback was overstated 2.4×** — priced on episode total units instead of units
  held at the MFE date. $10,535 → $4,349, collapsing its lead over `panic_exit` from
  3.2× to 1.3×. A slightly different record would have named the wrong habit.
- **The exit gap is a net** — $35,816 is +$73,770 early against −$37,954 well-timed,
  NVDA alone about half. The residual alone is an accusation.
- **The stop belongs to the user** — no server-derived stop, ever.
- **Two habits are one habit** — they converge on a single ladder.
- **An empty read is not an empty account** — `SnapTradeReadFailed`.
- **Behavioural rules are terminal at `saved`** — no sample floor, so no `tested`.
- **Same-day netting** — day deltas net per symbol, buys settle first.
- **The Mirror now has a Home entry** — #363 added "Connect your brokerage" to
  the Quant Rules block. Closed what this map listed as open question 10 on the
  day it was written; check `git log` before trusting any open item here.
- **A view model that drops a field is a dead page** — `LeakView` computed `trades`
  and never serialised them; the client's TS type declared the field required, so
  `tsc` stayed silent and `/account/brokerage` died behind Next's error boundary.
  Guarded now by `tests/test_mirror_view_serialisation.py`, which fails when any
  service field is neither serialised nor declared internal.

---

## Still open, ranked

| # | Question | Blocks | Owner |
|---|---|---|---|
| 1 | **Is rule discovery statistically possible on this sample?** 33 measured episodes; §22 wants 70/30 then walk-forward on that. The blueprint never says what "enough trades" means | 43b P1 entirely | undecided |
| 2 | **What makes a rule `validated`?** Split method, confidence label, sample floor | 43d, 43e Playbooks | undecided |
| 3 | Free / paid boundary | 43c, 43d, paid 43e | **Jimmy** |
| 4 | Stripe — four price IDs on Railway in test mode | as above | **Jimmy** |
| 5 | 43c or 43d next | next sprint | undecided |
| 6 | The 43f blueprint — not yet written | 43f | **Jimmy** |
| 7 | ETF/ADR price bars — caps coverage at 58% | quality of every 43b output | deferred |
| 8 | §6's nine-class asset taxonomy | correctness of exclusions beyond cash | undecided |
| 9 | Intraday bars | same-day episodes unmeasurable | deferred in spec |

### The fork worth deciding first

Questions 1 and 2 are the same question wearing different hats, and they sit
upstream of the entire right-hand half of the blueprint.

We have built a very good **description** engine. §17–22 — test an alternative rule,
prove it holds out of sample — is where "personalized optimization" actually lives,
and we have neither started it nor established that a 33-episode record can support
it. The blueprint itself warns a low-sample insight "should not automatically become
a recommended strategy," and there is currently no mechanism to tell the difference.

That is a larger fork than 43c-versus-43d, and answering it may change what 43b P1
is even for.

---

## Sequence of record

1. **43c P0 — Allocation Lens** (~1.5 wk) — the HOW MUCH question
2. **43b P0's trade page** — blueprint §27, the last open P0 item
3. **43d — Strategy Lab** — where `validated` becomes reachable
4. **43b P1**, then **43c P1** (43c P1 never waits on 43d)
5. **43e Playbooks** — needs 43d

Items 1 and 2 are contested by the fork above.
