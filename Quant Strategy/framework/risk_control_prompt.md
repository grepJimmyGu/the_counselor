# Risk-Level Adjustment — What It Controls and How It's Computed

> **Source question**: "What does the risk level adjustment actually control, and how is that executed in the computation?"
>
> Context: Retail Strategy Picker Framework. The wizard's Q5 asks "How much temporary loss can you sit through?" with answers `low / medium / high`. This doc explains what that answer should actually do under the hood.

---

The "risk level" slider in the picker is, under the hood, a coordinated knob that pre-populates **four** engine parameters in the strategy's `StrategyJSON`. Right now it only acts as a strategy *filter* (hides high-drawdown templates from low-tolerance users) — but to make it actually adjust risk, it should also adjust the recommended strategy's parameters. Here's what each control does and the math.

## The four levers

| Risk level | `position_sizing.target_vol_annual` | `risk_management.max_drawdown_stop` | `risk_management.stop_loss_pct` | Strategy filter |
|---|---|---|---|---|
| **Low** (sleep-easy) | `0.08` (8% annual vol target) | `0.15` (exit at −15% portfolio DD) | `0.08` (per-position stop) | only `drawdown: 'low'` templates |
| **Medium** | `0.12` | `0.25` | `0.12` | low + medium |
| **High** | not set (full position) | `0.40` or none | not set | all templates |

These four are the load-bearing risk controls in Livermore's existing schema. None require new fields.

## How each is computed in the engine

### 1. `target_vol_annual` — the sizing scale

After the strategy generates raw weights, the engine computes the trailing realized vol of the resulting portfolio and scales the weights down to hit the target.

```python
# In engine._generate_weights, after per-strategy logic produces `weights`
portfolio_returns_raw = (weights.shift(1).fillna(0) * asset_returns).sum(axis=1)
realized_vol = portfolio_returns_raw.rolling(21).std() * np.sqrt(252)
scale = (target_vol_annual / realized_vol).clip(upper=1.0)  # long-only cap
weights = weights.mul(scale, axis=0)
```

Key detail: `clip(upper=1.0)` enforces no-leverage. The scale can only shrink positions, never grow them. So vol-targeting in retail = automatic de-risking when realized vol spikes. A user who picks "low" gets, mechanically, *less skin in the game* when the market gets noisy.

### 2. `max_drawdown_stop` — the portfolio kill switch

Equity curve is tracked tick by tick; if peak-to-trough decline exceeds the threshold, the engine forces all weights to zero for the rest of the backtest (or until a user-defined reset).

```python
equity = (1 + portfolio_returns).cumprod()
running_max = equity.cummax()
drawdown = equity / running_max - 1.0
killed = drawdown.lt(-max_drawdown_stop).cummax()  # latch ON, never resets
weights.loc[killed] = 0.0
```

The `.cummax()` on the boolean is the latch — once you're stopped out, you stay out. For "low" risk this is the seatbelt that prevents 2008-style ruin; for "high" risk it's removed entirely.

### 3. `stop_loss_pct` — the per-position kill switch

For each open position, track entry price; exit when price drops by `stop_loss_pct` from entry. Applies only to signal-driven entries (not to cross-sectional rebalances, where the next rebalance is the exit).

```python
for symbol in close_matrix.columns:
    in_position = False
    for dt, price in close_matrix[symbol].items():
        if not in_position and weights.loc[dt, symbol] > 0:
            entry_price = price
            in_position = True
        elif in_position and price < entry_price * (1 - stop_loss_pct):
            weights.loc[dt:, symbol] = 0  # stop out for the rest of the trade
            in_position = False
```

### 4. Strategy filter (no engine code — it's a recommendation filter)

The picker's recommend function already does this:

```js
if (answers.dd === 'low' && s.drawdown === 'high') return -1;       // disqualify
if (answers.dd === 'low' && s.drawdown === 'medium') score -= 0.5;  // discount
```

This is purely UI-side; doesn't touch the engine.

## How the levers compose

These four don't override the strategy — they constrain it. A "Cross-Sectional Momentum" strategy with `target_vol_annual=0.08` and `max_drawdown_stop=0.15` is still cross-sectional momentum, but it now has half the historical drawdown profile because the vol-target shrinks positions in turbulent regimes and the DD stop pulls the plug if the regime breaks anyway.

The user's `behavior + asset` answers determine *what* strategy is recommended; the `drawdown tolerance` answer determines *how it's parameterized*.

## What's missing in Livermore today

The picker passes `dd` only to the strategy filter. To make risk level actually adjust risk, you need one additional step in the recommendation pipeline: after picking the top strategy, populate its `risk_management` and `position_sizing` blocks from the table above before handing the `StrategyJSON` to the backtester.

That's about 20 lines of code in the picker's "Apply template" handler and zero engine changes — `vol_target`, `max_drawdown_stop`, and `stop_loss_pct` are already implemented in `apps/api/app/services/backtester/engine.py`.

## Implementation prompt (paste into coding agent when ready)

```
Goal: When the Retail Strategy Picker recommends a template, populate its
risk_management and position_sizing fields based on the user's answer to
Q5 (drawdown tolerance: low / medium / high).

File: apps/web/src/components/strategy-picker/recommend.ts (or wherever the
picker recommendation handler lives in Next.js)

After the top strategy is selected, mutate its StrategyJSON before sending
to backend:

  function applyRiskLevel(strategy: StrategyJSON, dd: 'low'|'medium'|'high') {
    const profile = {
      low:    { target_vol: 0.08, max_dd: 0.15, stop_loss: 0.08 },
      medium: { target_vol: 0.12, max_dd: 0.25, stop_loss: 0.12 },
      high:   { target_vol: null, max_dd: 0.40, stop_loss: null },
    }[dd];

    if (profile.target_vol !== null) {
      strategy.position_sizing.method = 'vol_target';
      strategy.position_sizing.target_vol_annual = profile.target_vol;
    }
    strategy.risk_management.max_drawdown_stop = profile.max_dd;
    if (profile.stop_loss !== null) {
      strategy.risk_management.stop_loss_pct = profile.stop_loss;
    }
    return strategy;
  }

Backend engine code is unchanged — vol_target overlay and DD stop are already
implemented (see commits a6127c9 and 3524446).

Acceptance:
- Backtest run from picker with 'low' has realized vol within ±30% of 8%.
- Backtest run from picker with 'low' never has equity curve that drops more
  than 15% from peak (DD stop catches it before).
- Backtest run from picker with 'high' has no DD stop firing and no vol scaling.
- Existing tests in test_vol_target.py still pass.
```

## Cross-references

- Wizard logic: `Retail_Strategy_Picker_Framework.html` §1
- Engine implementation: `apps/api/app/services/backtester/engine.py` (commits `a6127c9`, `3524446`)
- Strategy schema: `apps/api/app/schemas/strategy.py` (`PositionSizing`, `RiskManagement`)
- Tests: `apps/api/tests/test_vol_target.py`, `test_engine_cross_sectional.py`
