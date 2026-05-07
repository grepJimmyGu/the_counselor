# Research Templates — Specification

Received 2026-05-07. Five templates to be implemented as structured quantitative research frameworks.

## Data feasibility
| # | Template | Data available | Status |
|---|---|---|---|
| 1 | Trend Following | Price only (Alpha Vantage) | ✓ Full |
| 2 | Cross-Sectional Momentum | Price only | ✓ Full |
| 3 | ETF Rotation | Price only + static ETF metadata | ✓ Full |
| 4 | Value + Momentum Multi-Factor | Fundamentals required | ⚠️ Partial |
| 5 | Commodity Carry / Roll Yield | Futures curve required | ⚠️ ETF proxy only |

## Shared output schema (all 5 templates)
- `metrics` — extended BacktestMetrics (adds CAGR, monthly_win_rate, best/worst month, Calmar, information_ratio, beta, correlation)
- `benchmark_metrics` — same fields for benchmark
- `timeseries` — dates, portfolio_value, benchmark_value, daily_returns, drawdown
- `rebalance_history` — per-rebalance: selected assets, scores/weights
- `holdings` — daily weights per asset
- `trades` — trade log
- `risk_analysis` — named sub-objects per template (see below)
- `warnings` — list of flagged issues

## Shared new infrastructure needed
- Extended metrics: CAGR, monthly_win_rate, best_month, worst_month, Calmar, information_ratio
- Regime analysis: calendar year split vs benchmark
- Concentration analysis: asset-level return contribution
- Turnover/cost drag calculation
- Benchmark mismatch detection
- Whipsaw detection (Template 1)
- Inverse volatility weighting (Templates 3, 5)
- `rebalance_history` output (Templates 2–5)

---

## Template 1 — Trend Following (Moving Average Filter)

**Strategy:** Buy when price > N-day MA, hold cash when price ≤ MA. Single asset.

**Inputs:**
- ticker (e.g. SPY, QQQ, GLD, USO)
- lookback_days (default 200)
- start_date, end_date
- benchmark_ticker (default SPY or same as ticker)
- rebalance_frequency: daily / weekly / monthly
- transaction_cost_bps (default 10), slippage_bps (default 5)
- initial_capital (default 100000)
- execution_timing: next_open or next_close

**Key calculation:**
- signal[t] = 1 if close[t] > MA(lookback)[t], else 0
- target_position[t+1] = signal[t]  (no lookahead)
- portfolio_return[t] = signal[t-1] × asset_return[t] − cost_impact[t]

**New vs existing engine:**
- execution_timing: next_open (open price path — new)
- Whipsaw detection: trades that reverse within 20 days
- monthly_win_rate, best_month, worst_month

**Risk analysis sub-objects:**
- drawdown_risk (flag if max_drawdown < -30%)
- whipsaw_risk (high trade count relative to backtest length; short-lived reversals)
- parameter_sensitivity (recommend testing lookback 100, 150, 200, 250)
- benchmark_comparison (flag if CAGR < benchmark but drawdown not improved)
- time_in_market (flag if too much cash + still underperforms)
- cost_sensitivity (flag if high turnover)
- regime_analysis (per year vs benchmark)

**Output additions:**
- position_history timeseries
- risk_analysis with above sub-objects

---

## Template 2 — Cross-Sectional Momentum

**Strategy:** Rank a list of stocks/ETFs by N-day return, buy top N, equal weight, rebalance periodically.

**Inputs:**
- ticker_list
- lookback_days (default 63)
- top_n (default 3)
- rebalance_frequency: weekly / monthly / quarterly (default monthly)
- benchmark_ticker (default SPY or QQQ)
- transaction_cost_bps (default 10), slippage_bps (default 5)
- initial_capital (default 100000)
- execution_timing: next_open or next_close

**Key calculation:**
- momentum_score[ticker, t] = close[t] / close[t − lookback_days] − 1
- rank descending, select top_n
- trade at next execution date after signal date

**New vs existing engine:**
- rebalance_history output (per-rebalance: selected assets, momentum scores, weights)
- Concentration risk: return contribution per asset, flag if one asset > 40% of total profit
- Universe hindsight bias warning (static)
- Benchmark mismatch: tech-heavy universe → suggest QQQ
- Momentum crash detection: months of sharp relative underperformance
- information_ratio
- Data availability risk: per-asset start date vs backtest start

**Risk analysis sub-objects:**
- concentration (asset contribution, flag >40%)
- universe_hindsight_bias (static warning)
- benchmark_mismatch
- momentum_crash_risk
- parameter_sensitivity (lookback 42, 63, 126, 252; top_n 3, 5, 10)
- turnover_cost_risk
- regime_dependence (per year)
- drawdown_risk
- data_availability_risk

---

## Template 3 — ETF Rotation

**Strategy:** Rank ETF basket by momentum, hold top N, equal weight or inverse-vol weight, rebalance periodically.

**Inputs:**
- etf_list (SPY/QQQ/IWM equities, TLT/IEF bonds, GLD/SLV metals, USO/UNG energy, VNQ real estate, UUP dollar, sector ETFs)
- lookback_days (default 126)
- top_n (default 3)
- rebalance_frequency (default monthly)
- weighting_method: equal_weight or inverse_volatility
- volatility_lookback_days (default 63, required if inverse_vol)
- benchmark_ticker (default SPY or blended)
- start_date, end_date
- transaction_cost_bps (default 10), slippage_bps (default 5)
- initial_capital (default 100000)

**Key calculation:**
- momentum_score[etf, t] = close[t] / close[t − lookback_days] − 1
- inverse_vol_weight: realized_vol over vol_lookback → 1/vol → normalize to sum=1 → optional cap
- Drifted weights tracked between rebalances

**New vs existing engine:**
- inverse_volatility weighting (new engine capability)
- Static ETF asset class metadata: equities / bonds / metals / energy / real estate / currency / sector
- Asset class concentration analysis
- Asset class exposure output
- Benchmark mismatch: multi-asset ETF list → suggest equal-weight basket vs SPY
- ETF structure risk: commodity ETF roll cost warning (USO, UNG)
- Drifted vs target weights tracking

**Risk analysis sub-objects:**
- asset_concentration (one ETF > 50% of time; one ETF > 40% of profit)
- asset_class_concentration (one class dominating)
- benchmark_mismatch (multi-asset → suggest basket benchmark)
- turnover_cost_risk
- regime_dependence (per year; identify crisis/inflation/bull winners)
- etf_structure_warnings (commodity ETF roll cost flags)
- volatility_weighting_risk (low-vol assets dominating if inv-vol)

---

## Template 4 — Value + Momentum Multi-Factor

**Strategy:** Rank stocks by combined value + momentum score, buy top N, equal weight, rebalance quarterly.

**Inputs:**
- stock_universe (custom list or large-cap US)
- value_metrics: earnings_yield, FCF_yield, book_to_price, sales_to_price (default: EY + FCF_yield)
- momentum_lookback_days (default 252)
- skip_recent_days (default 21 — avoids short-term reversal)
- factor_weights (default 50% value / 50% momentum)
- top_n or top_percentile (default top 50 or top 20%)
- rebalance_frequency (default quarterly)
- benchmark_ticker (default SPY)
- start_date, end_date
- transaction_cost_bps (default 10), slippage_bps (default 5)
- initial_capital (default 100000)
- max_position_weight (optional)

**Data requirements (critical):**
- Fundamental data MUST be point-in-time or conservatively lagged (90 days after fiscal quarter end / 120 days after fiscal year end)
- Requires: EPS/net income, FCF, book value, sales, shares outstanding, market cap, sector classification
- Alpha Vantage insufficient — needs Financial Modeling Prep, Polygon.io, or similar

**Key calculation:**
- momentum = close[t − skip] / close[t − skip − momentum_lookback] − 1
- value_score = average percentile rank across available value metrics
- momentum_score = percentile rank of momentum
- combined_score = weight_value × value_score + weight_momentum × momentum_score
- Select top_n by combined_score

**New vs existing engine:**
- Fundamental data pipeline (new — requires new data provider)
- Point-in-time data handling / reporting lag
- Factor scoring: cross-sectional percentile ranking, composite score
- Momentum with skip period
- Sector classification metadata
- factor_scores output (per-ticker, per-date: value/momentum/combined score + selected flag)
- Factor dominance detection (correlation of each factor vs composite)
- Value trap flagging (cheap + negative momentum)
- Survivorship bias warning

**Risk analysis sub-objects:**
- lookahead_bias (fundamental data lag verification)
- sector_bias (any sector > 35%)
- value_trap_risk
- factor_dominance (which factor drives the composite)
- concentration (top 10 holdings return contribution)
- turnover_cost_risk
- regime_dependence (per year; value years vs momentum years)
- benchmark_mismatch
- data_quality (missing fundamentals; survivorship bias warning)
- universe_bias (today's index constituents used for history)

**MVP scope:** Phase 1 = price momentum + static fundamental estimates; Phase 2 = full fundamental data pipeline via new provider.

---

## Template 5 — Commodity Carry / Roll Yield

**Strategy:** Rank commodities by futures carry (backwardation preference), hold top N, rebalance monthly.

**Inputs:**
- commodity_universe (WTI crude, natural gas, gold, silver, copper, corn, wheat, soybeans)
- futures_contract_mapping (front month, second month, optional third)
- carry_method: front_vs_second / annualized_curve_slope / constant_maturity_roll_yield
- top_n (default 2 or top 30%)
- rebalance_frequency (default monthly)
- benchmark_ticker (DBC, GSG, or equal-weight basket)
- start_date, end_date
- transaction_cost_bps, slippage_bps
- initial_capital
- weighting_method: equal_weight or inverse_volatility
- volatility_lookback_days (default 63)

**Data requirements (critical):**
- Futures settlement prices: front month AND second month, daily
- Contract expiration dates and roll schedule
- Continuous futures methodology
- Alpha Vantage does NOT provide this data
- ETF proxy fallback: GLD, SLV, USO, UNG, CPER, DBA, SOYB — momentum as carry approximation with prominent warnings

**Key calculation:**
- carry_raw = second_price / front_price − 1
- carry_score = −carry_raw (backwardation = positive, contango = negative)
- annualized_carry = −((second/front − 1) × 365 / days_between_contracts)
- Rank by carry_score descending, select top_n

**New vs existing engine:**
- Futures curve data pipeline (new — no current provider)
- Carry score calculation
- Roll mechanics and contract roll cost
- `data_methodology` output block (what data was actually used)
- `carry_scores` output (per-commodity, per-date: front/second prices, annualized carry, rank, selected)
- Commodity sector breakdown (energy / metals / agriculture / precious metals)
- Regime analysis by macro period (inflation, deflation, crisis, normal)

**Risk analysis sub-objects:**
- data_methodology_risk (incomplete futures curve; ETF proxy caveat)
- roll_methodology_risk (simplified roll assumptions)
- commodity_concentration (mostly energy)
- volatility_risk (flag if vol >> benchmark)
- drawdown_risk
- regime_dependence (per year; macro period if tags available)
- benchmark_mismatch (DBC/GSG better than SPY)

**MVP scope:** ETF proxy version only (commodity momentum ranked by price return), with prominent warnings that this is not true futures carry.
