# Investment concept reference

Curated, plain-English definitions for the `concept_explainer` chat tool.
Each entry is 1–2 sentences — no jargon-stacking, no formula derivations.
The chat tool reads this file at runtime (no rebuild on edit).

**Convention:** one concept per `##` heading. The heading text is the
canonical name; the paragraph immediately below is the explanation. Aliases
go in parentheses after the name, e.g. `## CAGR (Annualized Return)`.

Concepts are organized by section for human scanning; the chat tool ignores
the `###` section markers and indexes only `##` entries.

---

### Performance metrics

## Sharpe Ratio
Annualized return divided by annualized volatility. Above 1.0 is good for an equity-like strategy; above 2.0 is unusual. Limitation: treats upside and downside volatility equally, so it penalizes lumpy outperformance.

## Sortino Ratio
Like Sharpe but only counts *downside* volatility. Preferred when the return distribution is skewed (e.g., trend-following with rare big winners) because it doesn't punish the winners.

## Calmar Ratio
Annualized return divided by max drawdown. A "pain-adjusted" return — how much you earned per unit of worst-case loss. Above 1.0 means you earned more annually than you ever lost peak-to-trough.

## Max Drawdown
The largest peak-to-trough percentage decline in equity over the backtest period. The single most-quoted risk number — investors emotionally tolerate volatility but bail at large drawdowns.

## Total Return
The cumulative percentage return over the full backtest window. Useful as a headline but pair with annualized return and Sharpe for context — a 200% return over 20 years is mediocre.

## CAGR (Annualized Return)
Compound Annual Growth Rate — the constant annual return that would produce the observed total return. Lets you compare strategies tested over different windows on an apples-to-apples basis.

## Volatility
Annualized standard deviation of returns. The denominator of Sharpe. Equity strategies typically run 12–25% annualized vol; below that suggests low exposure or aggressive position sizing throttle.

## Beta
Sensitivity of the strategy's returns to the benchmark's returns. Beta of 1.0 moves with the market; 0.5 moves half as much; negative betas hedge. A pure-alpha strategy targets beta near zero.

## Alpha
The portion of return *not* explained by market exposure (beta). After-the-fact alpha is interesting but unreliable on small samples — most apparent alpha is statistical noise.

## Win Rate
Fraction of trades that closed profitable. Useful but misleading alone — a strategy with a 30% win rate can still print great returns if winners are 4x the size of losers (look at profit factor instead).

## Profit Factor
Sum of all winning trade $ divided by sum of all losing trade $. Above 1.5 is healthy; above 2.0 is excellent. More informative than win rate because it accounts for magnitude.

---

### Strategy concepts

## Momentum
The empirical tendency for recent past returns to predict near-future returns. The strongest documented anomaly in finance — works at 1–12-month lookbacks, fails at short and long horizons.

## Mean Reversion
The opposite premise: that prices oscillate around a fair value, so deviations are temporary. Works best on stable instruments (ETFs, large caps) over short windows; fails in trending regimes.

## Breakout
Enter when price crosses a recent high (or volatility expansion threshold), exit on opposite signal or stop. A momentum-family strategy — captures trend continuation while limiting downside.

## Trend Following
Hold a position as long as the trend persists (typically defined by moving averages or channel breakouts), exit when it reverses. Pays off in fat-tailed regimes (crashes, manias); flat in choppy markets.

## Cross-Sectional Momentum
Rank a universe by recent return, hold the top N performers, rotate periodically. Captures relative strength across assets rather than absolute trend.

## Sector Rotation
Move capital between sector ETFs based on a signal (momentum, macro, valuation). Lower turnover than stock-level rotation but captures regime shifts cleanly.

## Pairs Trading
Long one asset and short a correlated one, profiting from convergence of the spread. Market-neutral by construction; works when the cointegration is real and stable, breaks when it's not.

## Carry / Roll Yield
The return earned from holding a position when the forward curve is favorable (e.g., commodity futures in backwardation). Important caveat for ETF-based commodity backtests, which often miss the roll cost.

---

### Risk + portfolio

## Position Sizing
The rule that determines how much capital each position gets. Equal-weight is the default; alternatives include volatility-target, Kelly fractional, or risk-parity weighting.

## Rebalance Frequency
How often the portfolio resets to target weights. More frequent = lower deviation from target but higher transaction cost; weekly to monthly is the sweet spot for most strategies.

## Stop Loss
A protective exit at a predefined loss threshold. Helpful for trend-following (caps the downside on bad entries) but harmful for mean-reversion (exits exactly when reversion is about to fire).

## Universe Selection
The set of tickers the strategy is allowed to trade. Smaller universes lead to overfitting; larger universes dilute alpha if the signal is concentrated. Sector ETFs are a common starting point.

## Benchmark
The reference series the strategy is compared against (typically SPY for US equity). Sharpe and alpha are only meaningful relative to a benchmark — without one, "12% annualized" doesn't tell you much.

---

### Backtest pitfalls

## Overfitting (Curve Fitting)
Tuning parameters until the backtest looks great on historical data — at the cost of out-of-sample performance. Symptoms: very high Sharpe, suspiciously specific parameter values, no robustness to small parameter changes.

## Look-Ahead Bias
Using information at time T that wasn't actually available until later (e.g., using an earnings figure on the announcement date when it wasn't released until the next morning). Silently inflates backtest returns; hard to spot without careful timestamp discipline.

## Survivorship Bias
Testing only on assets that exist today, ignoring those that delisted/went bankrupt. Makes any strategy look better than it would have lived through. Standard fix: use a delisted-companies-included universe.

## In-Sample vs Out-of-Sample
The backtest period is split: parameters are tuned on in-sample, then evaluated on out-of-sample. Honest out-of-sample performance is the best single signal of forward viability.

## Transaction Cost
The friction of trading — commissions, bid-ask spread, exchange fees. Modeled in basis points (bps). Active strategies that look great at 0 bps often go negative at 10 bps; always include realistic costs.

## Slippage
The gap between the price you expected and the price you actually got. Worse for illiquid names, large orders, and fast-moving markets. Typically modeled as an additional bps charge on top of transaction cost.

## Walk-Forward Analysis
Repeatedly re-tune parameters on a rolling window and evaluate on the next out-of-sample period. The most realistic stress test — simulates how the strategy would adapt in live use. Robust strategies pass; overfit ones fall apart.
