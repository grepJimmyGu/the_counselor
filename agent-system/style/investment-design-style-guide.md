# Investment Analytics Design Style Guide

## Product Design North Star

The product should help users turn an investment hypothesis into a testable strategy, understand the historical result, and see the risks before trusting the output.

The UI should make users feel:

> "This is a serious analytical tool. It helps me think clearly, not trade impulsively."

---

## Desired Product Feeling

The interface should feel:

- Calm
- Analytical
- Trustworthy
- Modern
- Precise
- Guided
- Evidence-based
- Serious but approachable

The interface should not feel:

- Hype-driven
- Gamified
- Casino-like
- Meme-stock oriented
- Overly institutional
- Visually noisy
- Like a generic AI chatbot

---

## Visual Inspiration

Use these as directional references:

### Stripe

Use for:
- Trust polish
- Clean hierarchy
- Professional SaaS feel
- Clear cards and sections

Avoid:
- Overly decorative gradients if they distract from data

### Linear

Use for:
- Focused workflows
- Clean spacing
- Minimal visual noise
- Clear task progression

Avoid:
- Being too sparse or abstract for financial data

### Notion

Use for:
- Readable content blocks
- Approachable structure
- Simple explanations

Avoid:
- Looking too document-like when users need analytical confidence

### Robinhood

Use for:
- Simple entry points
- Low-friction onboarding
- Easy-to-understand financial flows

Avoid:
- Trading/gambling energy
- Emotional green/red reinforcement
- "Act now" behavior

### Bloomberg / Institutional Tools

Use for:
- Analytical seriousness
- Data credibility
- Multi-metric thinking

Avoid:
- Dense dashboards
- Overwhelming tables
- Expert-only interfaces

---

## Layout Principles

### 1. Use a guided workflow

The product should feel step-by-step:

1. Choose ticker
2. Define strategy
3. Review assumptions
4. Run backtest
5. Interpret result
6. Read sandbox review
7. Decide what to test next

Users should always know where they are in the process.

---

### 2. One primary action per screen

Every screen or major section should have one obvious primary action.

Examples:

Good:
- "Load historical data"
- "Generate strategy"
- "Run backtest"
- "Review risk"
- "Test another strategy"

Bad:
- "Go"
- "Continue"
- "Optimize"
- "Trade smarter"
- "Unlock alpha"

---

### 3. Performance and risk must be visually paired

Do not show return without nearby risk context.

If you show:

- Total return
- Annualized return
- Win rate
- Strategy performance

You should also show nearby:

- Max drawdown
- Benchmark comparison
- Date range
- Number of trades
- Transaction cost assumption
- Data limitations, if relevant

---

### 4. Separate calculated results from AI commentary

The UI should make a clear distinction between:

- Deterministic calculation
- AI-generated explanation
- Sandbox skeptical review

Recommended section labels:

- "Strategy Rules"
- "Backtest Results"
- "AI Explanation"
- "Sandbox Review"
- "Assumptions"
- "Risk Notes"

Avoid mixing these into one undifferentiated AI response.

---

## Component Guidelines

## 1. Ticker Selection

Ticker selection should feel reliable and low-friction.

Must include:

- Clear input label
- Example tickers
- Loading state
- Invalid ticker state
- Unsupported ticker state
- Data source note where appropriate

Good copy:

> Enter a stock ticker to load historical price data.

Good examples:

> Try AAPL, MSFT, NVDA, SPY

Bad copy:

> Find your next winner.

---

## 2. Strategy Builder

The strategy builder should guide users from vague idea to testable logic.

Must show:

- Strategy name
- Entry rule
- Exit rule
- Time horizon
- Indicators used
- Assumptions
- Unsupported logic warning, if needed

Good section title:

> Strategy Rules

Good helper text:

> These rules define what will be tested against historical price data.

Bad helper text:

> AI found a high-performing strategy for you.

---

## 3. Backtest Results

Backtest results should be clear, grounded, and not promotional.

Must show:

- Ticker
- Date range
- Strategy tested
- Benchmark, if available
- Total return
- Max drawdown
- Number of trades
- Transaction cost assumption
- Data freshness note, if needed

Good interpretation copy:

> This result describes historical performance over the selected period. It does not predict future returns.

Bad interpretation copy:

> This strategy can help you outperform the market.

---

## 4. Charts

Charts should help users understand, not impress them.

Chart rules:

- Label axes clearly
- Show date range
- Avoid unlabeled lines
- Avoid too many chart series
- Avoid emotional green/red overload
- Pair performance charts with drawdown or benchmark context
- Make chart legends readable on mobile

Preferred chart types:

- Equity curve
- Strategy vs benchmark
- Drawdown chart
- Trade markers, only if not visually noisy

Avoid:

- 3D charts
- Decorative charts
- Overcrowded dashboards
- Unexplained technical indicators

---

## 5. AI Explanation

AI explanation should feel like an analyst memo, not a salesperson.

Recommended structure:

1. What the strategy does
2. What the backtest showed
3. Why it may have worked or failed
4. What risks to consider
5. What to test next

Good tone:

> The strategy performed better during trending periods but struggled during sideways markets.

Bad tone:

> This strategy is a powerful way to capture gains.

---

## 6. Sandbox Review

Sandbox review should feel like a second opinion.

It should be visually distinct from the AI explanation.

Recommended labels:

- "Sandbox Review"
- "Skeptical Review"
- "Risk Check"
- "Second Opinion"

Sandbox review should check:

- Overfitting risk
- Regime dependency
- Transaction cost sensitivity
- Data limitations
- Sample period bias
- Whether the strategy logic makes economic sense
- What validation is needed next

Good copy:

> This review challenges the strategy before you rely on the result.

Bad copy:

> The AI confirms this strategy is strong.

---

## 7. Empty States

Empty states should guide action.

Good empty state:

> No strategy has been tested yet. Start by choosing a ticker and defining a rule-based strategy.

Bad empty state:

> Nothing here.

---

## 8. Loading States

Loading states should explain what is happening.

Good loading states:

> Loading historical price data…
> Generating testable strategy rules…
> Running backtest…
> Reviewing strategy assumptions…

Bad loading states:

> Thinking…
> Working magic…
> Finding alpha…

---

## 9. Error States

Error states should help recovery.

Good error state:

> We could not load historical data for this ticker. Check the symbol or try a widely traded ticker such as AAPL, MSFT, or SPY.

Bad error state:

> API error: 429.

Required error states:

- Invalid ticker
- Unsupported ticker
- API rate limit
- No historical data
- Failed strategy generation
- Failed backtest
- Failed sandbox review

---

## Copy Style

Use language that is:

- Clear
- Calm
- Specific
- Plain-English
- Evidence-based
- Non-promotional

Prefer:

- "Historical result"
- "Tested period"
- "Strategy assumptions"
- "Risk check"
- "May indicate"
- "Could be sensitive to"
- "Needs further validation"

Avoid:

- "Winning strategy"
- "Guaranteed"
- "Best stock"
- "Beat the market"
- "Unlock alpha"
- "Crush the market"
- "Trade smarter now"
- "AI-approved"
- "Sure thing"

---

## Trust Rules

The product should always make these visible when relevant:

1. This is historical analysis, not future prediction.
2. The tool does not execute trades.
3. Backtests depend on assumptions.
4. Data may be incomplete or delayed.
5. High return without risk context is misleading.
6. AI explanation may be wrong and should be challenged.
7. Sandbox review is a risk check, not a guarantee.

---

## Mobile Design Rules

On mobile:

- Use stacked cards
- Keep charts readable
- Avoid dense side-by-side tables
- Keep primary action sticky only if helpful
- Make warning text readable
- Collapse advanced details by default
- Keep strategy rules easy to scan

---

## Design Quality Bar

A page is good if:

1. A user understands the purpose within 5 seconds.
2. The next action is obvious.
3. The result is paired with assumptions and risk.
4. AI-generated text is clearly labeled.
5. The sandbox review feels independent.
6. Users can recover from errors.
7. The page works on mobile.
8. The UI does not encourage impulsive trading.

---

## Implementation Reference

### Color Tokens (globals.css — OKLCH, dark-only)

| Token | Value | Use |
|---|---|---|
| `background` | oklch(0.16 0.01 240) | Page background — deep blue-gray |
| `foreground` | oklch(0.96 0.01 255) | Primary text |
| `card` | oklch(0.20 0.015 235) | Card / panel surface |
| `muted` | oklch(0.24 0.015 235) | Subtle surface (inputs, tags) |
| `muted-foreground` | oklch(0.72 0.015 250) | Secondary text, labels, placeholders |
| `border` | oklch(0.31 0.016 235) | Borders on cards, inputs, dividers |
| `primary` | oklch(0.70 0.13 162) | Green-teal — CTA buttons, focus rings |
| `destructive` | oklch(0.66 0.20 24) | Error states |
| `input` | oklch(0.24 0.012 236) | Form input backgrounds |

### Chart Color Sequence

| Token | Value | Role |
|---|---|---|
| `chart-1` | oklch(0.72 0.13 162) | Strategy equity curve |
| `chart-2` | oklch(0.73 0.13 235) | Benchmark |
| `chart-3` | oklch(0.78 0.15 82) | Secondary series |
| `chart-4` | oklch(0.68 0.18 28) | Drawdown / risk |
| `chart-5` | oklch(0.78 0.09 200) | Neutral reference |

### Status Badge Classes

| State | Tailwind classes |
|---|---|
| Success / Low severity | `border-emerald-500/70 text-emerald-400 bg-emerald-500/10` |
| Warning / Medium severity | `border-yellow-500/70 text-yellow-400 bg-yellow-500/10` |
| Error / High severity | `border-rose-500/70 text-rose-400 bg-rose-500/10` |
| Info / Neutral | `border-blue-500/70 text-blue-400 bg-blue-500/10` |
| Primary accent | `bg-primary/15 text-primary` |

### Typography Scale

| Role | Classes |
|---|---|
| Page title | `text-3xl font-semibold tracking-tight` |
| Section header | `text-sm font-medium` |
| Field label | `text-xs uppercase tracking-wide text-muted-foreground` |
| Body | `text-sm leading-6 text-foreground` |
| Secondary body | `text-sm leading-5 text-muted-foreground` |
| Caption / footnote | `text-xs text-muted-foreground` |
| Data / ticker | `font-mono text-xs` |

Fonts: `Geist` (sans), `SFMono-Regular / Menlo` (mono).

### Card Variants

```tsx
// Standard card
<div className="rounded-lg border border-border bg-background p-4 space-y-2">

// Elevated card (verdict, summary)
<div className="rounded-lg border border-border bg-card/70 p-5 space-y-4">

// Primary-accented card (recommendation, design brief)
<div className="rounded-lg border border-primary/30 bg-primary/5 p-5 space-y-4">

// Warning card (credibility warning, defaults callout)
<div className="rounded-md border border-yellow-500/20 bg-yellow-500/5 px-4 py-2.5 text-xs text-yellow-300/80">

// Disclaimer banner
<div className="rounded-md border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
```

### List Markers

| Context | Marker |
|---|---|
| Ordered recommendation | `A. B. C.` in `text-primary font-medium` |
| Directional change | `→` in `text-primary` |
| Checklist item | `☐` in `text-muted-foreground/40` |
| Confirmed / preserved | `✓` in `text-emerald-400` |
| Bullet | `•` in `text-muted-foreground` |
