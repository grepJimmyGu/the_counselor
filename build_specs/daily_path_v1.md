# The daily path — build spec

**Status:** pre-build. Architecture settled, awaiting go.
**Date:** 2026-08-18
**Supersedes:** the intraday portions of `trade_execution_v1.md`. The defect
register there still stands as the record of why this path replaced that one.

## Decisions taken

| | |
|---|---|
| Interval | **Daily only.** `5min`/`15min`/`30min`/`60min` retired from the picker |
| Aggregator | **SnapTrade** — reads holdings and can place orders, so step 4c stays open without a re-integration |
| Order surface | **Ship 4a (ticket) + 4b (deep link).** 4c (1-click) gated on counsel |
| Entries | **In scope.** Not just exits |
| "Best model quality" | **The quant modelling** — sizing, honest backtests, no lookahead |

---

## 1. The organizing principle

> **The backtest and the live monitor must call the same evaluation function.**

Every divergence found in the audit exists because there are two implementations
of the same rule:

| | Backtest | Live monitor |
|---|---|---|
| Scale-out convention | fraction of *remaining* | fraction of *initial* |
| Tier identity | keyed on ladder index | keyed on a shared `"stop_hit"` string |
| Bar interval | always daily | intraday |
| Trigger field | bar close | bar close (proposed daily: bar low) |

None of these are hard problems. They are all the same problem: two codebases
expressing one rule, kept in agreement by discipline, and discipline lost.

**So the first build task is not a feature.** It is to extract one
`evaluate_ladder(position, bar) -> [TierFire]` that both the backtester and the
daily monitor import. After that, consistency is structural — a divergence
becomes impossible rather than merely discouraged.

This is the founder's own consistency principle, enforced by construction.

---

## 2. Quant modelling — the quality bar

Audited today. The foundations are better than expected; the defaults are not.

### What is already right

- **No lookahead.** `weights.shift(1)` before returns are applied
  (`engine.py:1143`, `:1505`); rolling breakout levels use `.shift(1)`
  (`:579-580`); volatility estimates are explicitly lagged (`:1141`).
- **`adjusted_close`** drives the price matrix — splits and dividends handled.
- **Cost machinery exists and is wired** —
  `strategy.transaction_cost_bps + strategy.slippage_bps` feeds turnover costs.

### What must change

**Q1 · Costs default to zero.** `transaction_cost_bps: float = Field(0.0)` and
`slippage_bps: float = Field(0.0)` (`schemas/strategy.py:303-304`). Every
backtest in the product today is **gross of costs**, and a daily strategy that
turns over weekly can be entirely an artifact of that. Set defensible retail
defaults, show them on the result, and let the user raise them but not silently
zero them.

**Q2 · Exits fill at the signal bar's close — live cannot.** The backtest zeroes
the weight on the bar where the tier triggers, so it effectively exits at that
day's close. In live daily execution the user learns after the close and fills
at **the next open**. That overnight gap is unmodelled, and for stops it is
systematically adverse — stops trigger on bad news, and bad news gaps down.

Fix: the backtest fills exits at the **next session's open**. This will make
every stopped strategy look worse. That is the point; the current number is not
achievable by the user the system is built for.

**Q3 · Trigger field must match on both sides.** If the live monitor tests the
day's **low** for stops (which it should — the data is there and it catches real
breaches), then the backtest must test the low too. Testing the close in one and
the low in the other means live fires more often than the backtest promised.
Decide once, apply in the shared evaluator from §1.

**Q4 · Survivorship.** `resolve_universe` maps `sp500` / `russell3000` to
**today's** membership. A three-year backtest on today's Russell 3000 never sees
the names that were delisted or dropped — the exact names a strategy would have
been hurt by. Point-in-time membership is a real data project; **for slice 1,
state the limitation on the result rather than pretending it away**, and scope
the fix separately.

**Q5 · Sample size.** Surface trade count and per-trade dispersion. A ladder with
six fills is not evidence, and today nothing says so.

**Q6 · Position sizing — with a boundary.** Sizing is where retail quant actually
lives, and it splits cleanly on §11:

- Sizing as a **strategy property** — "risk 1% of the position per trade",
  ATR-scaled, fixed fractional — is impersonal. Ships.
- Sizing off the **user's account value** — "buy 37 shares given your $40k" — is
  personalization. Does not ship, connected account or not.

The connection makes the second one *technically* trivial, which is exactly why
the boundary needs to be written down before the data is available.

---

## 3. The path

### Stage 1 — Build (mostly exists)
Composer, 110-primitive catalog, exit ladders, backtester. One change: `daily`
becomes the only resolution, so the backtest and the monitor read the same bars
by construction rather than by luck.

### Stage 2 — Connect (new)
SnapTrade OAuth. Read holdings, cost basis, cash. Replaces hand-declared
positions.

**This is the correctness fix, not a convenience.** Every wrong-number defect in
the audit traces to one cause: Livermore asks the user what they hold and they
do not answer. Stale `shares_remaining`, tiers disarmed by unconfirmed alerts,
share counts computed from numbers nobody updated. Reading holdings deletes the
class.

### Stage 3 — Watch (new, replaces the intraday cron)
One job after the close.

- **Entries:** the daily snapshot already evaluates every primitive. A strategy
  the user tracks but is not in produces an entry signal.
- **Exits:** tiers evaluated through the shared evaluator (§1) against the day's
  actual high and low.
- One price-bar fetch per tracked symbol per day — against ~78 per position per
  day on the intraday path.

### Stage 4 — Act
- **4a Order ticket.** Structured, copyable. Ships.
- **4b Broker deep link.** Symbol only — no prefilled side or quantity. Ships.
- **4c One-click.** Order submitted through the connected account with per-order
  confirmation. **Gated on counsel.** Transmitting orders is not publishing; it
  is a different regulatory question, and the usual answer is a registered
  partner. SnapTrade keeps this reachable without re-integration.

### Stage 5 — Reconcile
Next morning's holdings sync confirms the fill. No "mark as executed" paperwork.
This is what closes the loop that has never closed.

---

## 4. Slices

**Slice 1 — one rule engine.** Extract the shared evaluator. Pick the scale-out
convention (open decision A) and make both sides use it. Fix the tier-identity
bug. Turn costs on. Fill exits at next open. No user-facing change except that
backtest numbers move — and they should be *announced* as moving, with the
reason.

**Slice 2 — daily monitoring.** Lift the `bar_resolution == 'daily'` block. Daily
exit check. Entry signals. Delivery with a persistence guarantee: a
non-dismissible unresolved row, so a missed alert becomes late rather than lost.

**Slice 3 — SnapTrade read-only.** OAuth, holdings sync, reconciliation,
auto-confirmation of fills. Retires manual declaration.

**Slice 4 — order surface.** Ticket + deep link, on numbers that are now correct
and holdings that are now real.

**4c** runs on the legal track in parallel and lands when it lands.

---

## 5. Open decisions

**A · Scale-out convention.** Fraction of original, or of remaining? Still
unresolved, and slice 1 cannot start without it. Recommendation unchanged:
**fraction of original** — path-independent, matches trader usage, and immune to
the confirmation drift that a connected account only *mostly* eliminates.

**B · Trigger field.** Stops on the day's low and targets on the day's high
(catches real breaches, fires more often), or both on the close (quieter, misses
intraday breaches that recover)? Whichever, both engines use it. Recommendation:
**low/high** — it is what a stop means.

**C · Retail cost defaults.** What bps for commission and slippage on daily
retail equities? This number changes every backtest in the product, so it should
be yours, stated on the result.

**D · Announcing the backtest change.** Slice 1 makes existing strategies' past
results worse — costs on, exits at next open. Silently better numbers are a bug;
silently worse ones are a support incident. Do published/community strategies get
re-run and re-labelled, or annotated?
