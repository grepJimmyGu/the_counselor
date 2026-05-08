# Good / Bad UI Examples — Investment Analytics Tool

These examples define the product taste for the Investment Analytics UI/UX Agent.

The product should feel analytical, calm, trustworthy, and clear. It should help users test investment hypotheses without overtrusting historical results.

---

## Example 1: Backtest Result Card

### Bad Version

Card title:

> Your strategy crushed the market

Metrics:

- Return: +86%
- Win rate: 72%
- AI confidence: High

CTA:

> Start trading smarter

### Why It Is Bad

- Uses hype language.
- Frames historical performance as future opportunity.
- Does not show date range.
- Does not show benchmark comparison.
- Does not show max drawdown.
- Does not show transaction cost assumptions.
- "AI confidence" creates false trust.
- CTA sounds like trading advice.

### Good Version

Card title:

> Historical Backtest Result

Subtitle:

> AAPL · Jan 2018 – Dec 2024 · Daily price data

Metrics:

- Strategy return: +42.3%
- Benchmark return: +61.8%
- Max drawdown: -24.6%
- Trades: 18
- Transaction cost assumption: 0.1% per trade

Interpretation:

> This strategy reduced exposure during some downside periods but underperformed buy-and-hold over the tested period. Review the sandbox risk check before drawing conclusions.

CTA:

> Review risk check

### Why It Is Good

- Uses neutral historical framing.
- Shows ticker and test period.
- Pairs return with risk.
- Includes benchmark context.
- Shows trade count and cost assumption.
- Encourages review instead of action.
- Avoids implying future performance.

### Design Rule

Always pair performance with risk, assumptions, and tested period. Never make backtest results sound like investment recommendations.

---

## Example 2: Ticker Input

### Bad Version

Input label:

> Find your next winner

Placeholder:

> Enter stock

Error state:

> API error: 404

### Why It Is Bad

- Suggests the product finds winning stocks.
- Input label is vague.
- Does not tell users what format to use.
- Error message is technical and not recoverable.
- Creates a stock-picking / gambling feeling.

### Good Version

Input label:

> Enter a stock ticker to load historical price data

Placeholder:

> Try AAPL, MSFT, NVDA, or SPY

Helper text:

> The backtest will use available historical price data for the selected ticker.

Invalid ticker error:

> We could not find historical data for this ticker. Check the symbol or try a widely traded ticker such as AAPL, MSFT, or SPY.

### Why It Is Good

- Makes the user action clear.
- Gives examples.
- Explains what happens next.
- Helps recovery from errors.
- Avoids hype or prediction language.

### Design Rule

Ticker selection should feel like data loading, not stock picking.

---

## Example 3: Strategy Builder

### Bad Version

Section title:

> AI Strategy

AI output:

> Buy when the market looks strong and sell when momentum weakens.

CTA:

> Run it

### Why It Is Bad

- Strategy rules are vague.
- "Market looks strong" is not testable.
- "Momentum weakens" is undefined.
- User cannot verify what will be backtested.
- CTA is too generic.
- Creates risk that the backtest logic differs from what the user expects.

### Good Version

Section title:

> Strategy Rules

Strategy name:

> 50-day / 200-day Moving Average Crossover

Entry rule:

> Buy when the 50-day moving average crosses above the 200-day moving average.

Exit rule:

> Sell when the 50-day moving average crosses below the 200-day moving average.

Test settings:

- Price frequency: Daily close
- Position: Long only
- Transaction cost assumption: 0.1% per trade
- Date range: Jan 2018 – Dec 2024

CTA:

> Run historical backtest

### Why It Is Good

- Strategy is deterministic.
- Entry and exit rules are clear.
- User can understand what is being tested.
- Assumptions are visible before backtest.
- CTA clearly states the action.

### Design Rule

AI-generated strategy must be translated into explicit, testable rules before backtesting.

---

## Example 4: AI Explanation

### Bad Version

Title:

> AI Says This Is a Strong Strategy

Explanation:

> This strategy performed well and could help investors capture upside while avoiding losses. It is a strong signal for future opportunities.

### Why It Is Bad

- Sounds promotional.
- Suggests future performance.
- Does not explain why the strategy worked or failed.
- Does not mention risk.
- Could be interpreted as financial advice.
- Overstates AI authority.

### Good Version

Title:

> AI Explanation

Structure:

**What the strategy tested**
This strategy bought the stock when short-term momentum moved above long-term momentum and exited when that signal reversed.

**What the backtest showed**
Over the tested period, the strategy produced lower total return than buy-and-hold but had fewer periods of market exposure.

**What to watch**
The strategy may lag during sideways markets and can be sensitive to transaction costs if signals occur frequently.

**Next validation**
Test the same rules across different tickers and market periods before relying on the result.

### Why It Is Good

- Explains the actual tested logic.
- Separates result from interpretation.
- Includes weaknesses.
- Suggests validation.
- Avoids advice language.
- Does not overclaim.

### Design Rule

AI explanation should behave like an analyst memo, not a sales pitch.

---

## Example 5: Sandbox Review

### Bad Version

Title:

> AI Confirmation

Text:

> The backtest confirms this strategy is effective. The result supports the AI's recommendation.

### Why It Is Bad

- Sandbox layer is not independent.
- It blindly agrees with the original AI.
- It uses confirmation language.
- It does not challenge assumptions.
- It increases false confidence.

### Good Version

Title:

> Sandbox Review

Subtitle:

> A second opinion that challenges the strategy before you trust the result.

Review sections:

**Main concern**
The strategy was tested during a period where large-cap technology stocks had strong upward trends. Results may weaken in sideways or declining markets.

**Overfitting risk**
Moderate. The strategy uses common moving-average rules, but the selected period may still favor trend-following approaches.

**Cost sensitivity**
If trades become frequent, transaction costs could materially reduce returns.

**Required next test**
Run the same strategy across multiple tickers and separate market regimes.

### Why It Is Good

- Clearly acts as a second opinion.
- Challenges the result.
- Mentions regime risk.
- Mentions overfitting.
- Mentions transaction cost sensitivity.
- Recommends next validation.

### Design Rule

Sandbox review must challenge the strategy, not confirm it.

---

## Example 6: Loading State

### Bad Version

Loading message:

> Finding alpha…

### Why It Is Bad

- Hype-driven.
- Suggests the product can discover guaranteed opportunity.
- Does not explain what is happening.
- Weakens trust.

### Good Version

Loading messages by step:

Ticker data:

> Loading historical price data…

Strategy generation:

> Translating your idea into testable strategy rules…

Backtest:

> Running the strategy across the selected historical period…

Sandbox review:

> Checking assumptions, risks, and possible overfitting…

### Why It Is Good

- Explains the current process.
- Sets realistic expectations.
- Reinforces trust.
- Makes longer waits feel purposeful.

### Design Rule

Loading states should explain the actual analytical process, not create magic.

---

## Example 7: Error State

### Bad Version

Error:

> Failed. Try again.

### Why It Is Bad

- Too vague.
- Does not explain what failed.
- Does not help user recover.
- Makes the product feel unreliable.

### Good Version

Error title:

> Backtest could not be completed

Error body:

> We loaded the ticker data, but the selected strategy rules could not be tested. This may happen if the rules reference an unsupported indicator or if there is not enough historical data.

Recovery actions:

- Review strategy rules
- Try a longer date range
- Choose a simpler price-based strategy

### Why It Is Good

- Names the failed step.
- Explains likely causes.
- Gives recovery options.
- Keeps the user in the flow.

### Design Rule

Every error state should explain what failed, why it may have failed, and what the user can do next.

---

## Example 8: Performance Chart

### Bad Version

Chart:

- One unlabeled green line going up
- No axis labels
- No date range
- No benchmark
- No drawdown context
- Title: "Profit curve"

### Why It Is Bad

- Visually implies success without context.
- No clear date range.
- No benchmark comparison.
- No risk context.
- "Profit" may be misleading.
- Users cannot interpret the result.

### Good Version

Chart title:

> Strategy vs Benchmark

Chart elements:

- Strategy equity curve
- Buy-and-hold benchmark
- Date range shown above chart
- Y-axis labeled "Portfolio value"
- X-axis labeled by year
- Legend clearly visible
- Nearby max drawdown metric

Helper text:

> This chart shows historical portfolio value under the tested assumptions. It does not account for future market conditions.

### Why It Is Good

- Clear comparison.
- Labels what is being shown.
- Shows time context.
- Avoids overstating profit.
- Pairs chart with risk context.

### Design Rule

Charts must explain what is being measured and should never visually exaggerate confidence.

---

## Example 9: First-Time Empty State

### Bad Version

Empty state:

> No results yet.

### Why It Is Bad

- Does not guide the user.
- Misses chance to explain the product flow.
- Creates dead space.
- Makes the product feel unfinished.

### Good Version

Empty state title:

> Start with a ticker and a testable strategy

Body:

> Choose a stock ticker, then describe a price-based strategy you want to test. The tool will convert your idea into explicit rules, run a historical backtest, and show a sandbox review of the risks.

Example prompt:

> Example: Test whether buying AAPL when the 50-day moving average crosses above the 200-day moving average would have outperformed buy-and-hold.

CTA:

> Choose a ticker

### Why It Is Good

- Explains what to do next.
- Teaches the product flow.
- Gives a concrete example.
- Sets expectations around historical testing and risk review.

### Design Rule

Empty states should teach users how to reach the product's first "aha" moment.

---

## Example 10: Risk Disclosure Placement

### Bad Version

Backtest page:

- Return metric at top
- Big chart in middle
- Risk disclaimer hidden at bottom in small gray text

### Why It Is Bad

- Risk appears after the user has already formed an impression.
- Small disclaimer feels like legal cleanup, not product guidance.
- User may overtrust the result.
- Risk is disconnected from performance.

### Good Version

Backtest page:

Top result card includes:

- Strategy return
- Benchmark return
- Max drawdown
- Date range
- Assumption summary

Directly below metrics:

> Historical analysis only. This result depends on the selected period, price data, and strategy assumptions. It should not be treated as a prediction or recommendation.

Sandbox review appears immediately after the result card.

### Why It Is Good

- Risk appears near the result.
- User sees limitations before interpretation.
- Sandbox review reinforces healthy skepticism.
- Trust is built into the product, not hidden in legal copy.

### Design Rule

Risk context should live next to performance, not at the bottom of the page.

---

## Example 11: Button Labels and CTAs

### Bad

| Bad | Good |
|---|---|
| Go | Run Backtest |
| Continue | Review Strategy Rules |
| Optimize | Adjust Parameters |
| Unlock alpha | Test Another Strategy |
| Trade smarter | Load Historical Data |
| Submit | Generate Strategy |

### Design Rule

CTA labels should name the analytical action, not sell an outcome.

---

## Example 12: Demo Picker Cards

### Bad Version

Card label:

> 🚀 AAPL Momentum Crusher
> AI-powered alpha capture strategy

### Why It Is Bad

- Hype language undermines trust.
- "Alpha capture" implies the product guarantees outperformance.
- No description of what is being tested.

### Good Version

Card label:

> AAPL · 12-Month Momentum
> Buy when 12-month return is positive. Monthly rebalance. Benchmark: SPY.

Commodity card:

> GLD / SLV Rotation
> Rotate monthly into the commodity ETF with the higher 3-month return. Benchmark: DBC.

### Design Rule

Demo cards should describe what is being tested, not sell what users might gain.

---

## Example 13: Robustness Tab

### Bad Version

Header:

> Robustness Score: 72
> Your strategy is robust.

### Why It Is Bad

- A single score implies precision that does not exist.
- "Your strategy is robust" is a conclusion the user should draw, not the tool.
- Anchors the user on a number rather than guiding interpretation.

### Good Version

Header:

> Robustness Analysis

Description:

> This table shows how backtest performance changes as key parameters vary. Stable results across a range of inputs suggest the strategy is less sensitive to parameter choices. Large performance swings suggest overfitting.

Heatmap label:

> Total Return by Lookback Period × Rebalance Frequency
> Darker cells indicate higher returns under that parameter combination.

### Design Rule

Robustness analysis should help users draw their own conclusions, not deliver a score that replaces critical thinking.

---

## Example 14: Strategy Comparison

### Bad Version

```
Winner: Strategy B (+142%)
```

### Why It Is Bad

- Declares a winner based on return alone.
- Ignores drawdown, Sharpe ratio, and trade count.
- Encourages the user to pick without understanding risk.

### Good Version

```
Strategy A vs Strategy B — AAPL · Jan 2018 – Dec 2023

                  Strategy A    Strategy B    SPY (benchmark)
Total return        +89.4%        +142.1%         +107.3%
Max drawdown        −22.1%        −38.7%          −19.6%
Sharpe ratio          0.91          1.14             0.87
Win rate             58.3%         61.2%              —
Trades                 18            42               —

Note: Higher return in Strategy B is accompanied by significantly higher drawdown.
Review risk metrics alongside return before drawing conclusions.
```

### Design Rule

Comparison views should surface trade-offs, not declare winners.
