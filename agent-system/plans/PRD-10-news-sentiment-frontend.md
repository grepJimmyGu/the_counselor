# PRD-10: News & Community Sentiment Module — Frontend

**Status:** Not started  
**Date:** 2026-05-11  
**Depends on:** PRD-09 (all backend services + API endpoints)  
**Branch naming:** `feat/prd-10-news-sentiment-frontend`

---

## Goal

Build the News & Community Sentiment tab under Stock Picker with:
- 7 pre-built toolkit cards as the entry point
- Result cards with all labels, scores, and takeaway
- Deep-dive page with four visual sections
- Provider status panel showing which data sources are active

---

## Navigation

Add "Sentiment" to the main nav and Stock Picker section:

```
Nav: Home · Workspace · Templates · Stocks (new) · Sentiment (new)
```

Route structure:
```
/sentiment                    → Sentiment hub page (7 toolkit cards)
/sentiment/[toolkit_id]       → Toolkit results (ranked candidates)
/sentiment/stock/[ticker]     → Deep-dive page (4 sections)
```

---

## Page 1: Sentiment Hub (`/sentiment`)

### Layout

```
[Page header]
  "News & Community Sentiment"
  "Discover stocks with real catalysts, rising community attention, or emerging risks."

[Provider status strip]
  ● Alpha Vantage News   active
  ● Reddit               not configured  [Configure →]
  ● X                    not configured  (requires $100/mo API)
  ● Internal Community   coming soon     (Phase 3)

[Disclaimer banner]
  "Research candidates only — not financial advice. Data may be delayed or incomplete."

[7 Toolkit cards — 2-col grid on desktop, 1-col on mobile]
```

### Toolkit card design

```
┌─ Positive Catalyst Watchlist ───────────────────────────┐
│ Find stocks with strong recent positive news catalysts   │
│                                                          │
│ Sources: Alpha Vantage News                             │
│ Updates: every 3 hours                                  │
│                                                          │
│ [Run Toolkit →]                    Last run: 2h ago     │
└──────────────────────────────────────────────────────────┘
```

Each toolkit card shows:
- Name + description
- Source types used (badges: AV News, Reddit, X, Internal)
- Cache freshness ("Last run: 2h ago" / "No results yet")
- "Run Toolkit →" button → `/sentiment/[toolkit_id]`

---

## Page 2: Toolkit Results (`/sentiment/[toolkit_id]`)

### Header

```
[← Back to Sentiment Hub]
Positive Catalyst Watchlist
12 candidates · Sources: Alpha Vantage News · Updated 45 min ago
[Refresh]
```

### Result cards

Each candidate gets a card:

```
┌──────────────────────────────────────────────────────────┐
│  NVDA   NVIDIA Corporation                               │
│  Score: 84/100  ●  Strong Positive Catalyst              │
│                                                          │
│  "Strong AI infrastructure demand cycle with earnings    │
│   beat driving institutional sentiment higher."          │
│                                                          │
│  [Earnings Catalyst] [Highly Material] [High-Quality Sources]  │
│  [Strong Positive] [Rising Attention] [High Quality Catalyst]  │
│                                                          │
│  ▲ Bullish themes: Data centre growth · Blackwell demand │
│  ▼ Bearish themes: Export controls · Valuation premium  │
│                                                          │
│  Suggested action: Add to watchlist — watch for revenue  │
│  growth confirmation in next earnings print.             │
│                                                          │
│  Sources: [AV News] [Confidence: High]                   │
│  [View Full Analysis →]  [Publish to Community ·disabled]│
└──────────────────────────────────────────────────────────┘
```

**Card fields:**
- Ticker + company name
- Overall score (0–100) + overall label
- One-sentence takeaway summary
- Label row: catalyst type · materiality · source quality · sentiment · signal quality
- Top 3 bullish themes (▲) + top 3 bearish themes (▼)
- Suggested user action (never says buy/sell)
- Active source badges + confidence label
- "View Full Analysis →" → `/sentiment/stock/[ticker]`
- "Publish to Community" → disabled until Phase 3

### Loading state
Skeleton cards while toolkit runs. If running takes > 5s, show progress:
```
Analysing 150 candidates...  [▓▓▓▓░░░░░░]  62 / 150
```

---

## Page 3: Sentiment Deep-Dive (`/sentiment/stock/[ticker]`)

### Page header

```
[← Back to results]
NVDA   NVIDIA Corporation
Sentiment Analysis · Updated 45 min ago · [Refresh]

Overall: 84/100  Strong Positive Catalyst
"AI infrastructure demand cycle with earnings beat driving institutional sentiment."
Suggested action: Add to watchlist — verify revenue growth in next earnings print.

[Sources: AV News ●active  Reddit ○not configured  X ○not configured]
[Disclaimer]
```

### Section 1: News Catalyst

```
┌─ News Catalyst ─────────────────────────────────────────────┐
│                                                              │
│  [Earnings Catalyst]  [Company-Specific]  [Medium-Term]     │
│                                                              │
│  NVIDIA beat Q1 estimates with $26B revenue, driven by     │
│  Blackwell GPU shipments to hyperscalers. Management         │
│  guided Q2 above consensus on AI data centre demand.        │
│                                                              │
│  Expected business impact:                                   │
│  Revenue and margins likely to expand over next 2 quarters   │
│  if AI capital expenditure cycle continues.                  │
│                                                              │
│  ┌─────────────────────┐  ┌─────────────────────────────┐  │
│  │ Catalyst Materiality │  │ Information Source Quality   │  │
│  │ ████████████ 90/100  │  │ ██████████░░ 85/100          │  │
│  │ Highly Material      │  │ High-Quality Sources         │  │
│  └─────────────────────┘  └─────────────────────────────┘  │
│                                                              │
│  Key headlines:                                              │
│  · "NVDA Q1 2026 Earnings Beat: Revenue $26B" — Bloomberg   │
│  · "Blackwell Ramp Accelerating..." — Reuters · 2h ago      │
│  · "Data Centre Revenue Doubles YoY" — WSJ · 4h ago        │
│                                                              │
│  Confidence: High  ·  Source: Alpha Vantage News            │
└──────────────────────────────────────────────────────────────┘
```

### Section 2: News Sentiment

```
┌─ News Sentiment ────────────────────────────────────────────┐
│                                                              │
│  [Strong Positive]  [Improving]  [Diverse Sources]          │
│                                                              │
│  ┌─ Sentiment Gauge ─────────────────────────────────────┐  │
│  │  Bearish ────────────────────────●──── Bullish        │  │
│  │                                 82%                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ▲ Bullish themes              ▼ Bearish themes            │
│  · Data centre demand          · Export control risk        │
│  · Blackwell ramp              · Valuation premium          │
│  · Earnings beat               · Competition from AMD       │
│                                                              │
│  ⚡ Conflicting signals:                                     │
│  Some analysts flag margin sustainability risk if           │
│  hyperscaler spending slows in H2 2026.                    │
│                                                              │
│  Source diversity: High (Bloomberg, Reuters, WSJ, FT, CNBC) │
│  Confidence: High                                           │
└──────────────────────────────────────────────────────────────┘
```

### Section 3: Community Pulse

```
┌─ Community Pulse ───────────────────────────────────────────┐
│                                                              │
│  [Reddit ○ not configured]  [X ○ not configured]           │
│  [Internal Platform ○ coming soon]                          │
│                                                              │
│  Community data not yet configured for this platform.       │
│  News signal only.                                          │
│                                                              │
│  ┌─ Configure Reddit →  ┐                                   │
│  │ Add REDDIT_CLIENT_ID │                                   │
│  │ to activate          │                                   │
│  └──────────────────────┘                                   │
└──────────────────────────────────────────────────────────────┘
```

*(When Reddit is configured, this section shows: attention trend, bullish/bearish community themes, representative discussions, engagement stats)*

### Section 4: Signal Quality & Risk

```
┌─ Signal Quality & Risk ─────────────────────────────────────┐
│                                                              │
│  [High Quality Catalyst]  [News-Only Signal]               │
│                                                              │
│  ┌─ News vs Community Alignment ──────────────────────────┐ │
│  │  News:      ████████████  Strong Positive             │ │
│  │  Community: ── Not configured ──                      │ │
│  │  Alignment: news_only (community data unavailable)    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Crowding risk: Moderate — widely covered, watch for        │
│  consensus crowding as institutional positioning rises.     │
│                                                              │
│  ⚠ Headline risks:                                          │
│  · Export restrictions could disrupt H2 guidance            │
│  · Hyperscaler spending slowdown would hit revenue          │
│                                                              │
│  ✓ Required next checks:                                    │
│  · Verify guidance credibility via earnings transcript      │
│  · Compare gross margin trend vs AMD/Intel                  │
│  · Check institutional ownership changes (13F)             │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Final Takeaway: Real Catalyst, Positive Signal             │
│  "Strong AI infrastructure catalyst confirmed by earnings.  │
│   Sentiment is broadly bullish but crowding risk is rising. │
│   Add to watchlist — verify revenue growth and watch for    │
│   export control escalation."                               │
│                                                              │
│  [Run Sandbox Review →]  (uses Sonnet, ~10s)               │
│                                                              │
│  Confidence: High  ·  Sources: Alpha Vantage News           │
└──────────────────────────────────────────────────────────────┘
```

---

## Sandbox Review Result (on-demand, Sonnet)

Triggered when user clicks "Run Sandbox Review →":

```
┌─ Sandbox Review ─────────────────────────────────────────────┐
│  Trust Score: 71/100  ·  Verdict: Mostly Credible           │
│                                                              │
│  Key concerns:                                               │
│  · Catalyst is real but already heavily priced in           │
│  · Source quality is high but coverage is concentrated      │
│    — limited independent analysis beyond earnings call      │
│                                                              │
│  Missing data:                                               │
│  · No community sentiment to confirm or contradict          │
│  · No independent analyst checks vs consensus              │
│                                                              │
│  ⚠ Final warning: High-quality signal but crowded trade.    │
│  Institutional positioning may already reflect the upside.  │
│  Wait for a price pullback or further revenue confirmation. │
└──────────────────────────────────────────────────────────────┘
```

---

## Provider Status Panel (visible on hub + deep-dive pages)

```
Data Sources
──────────────────────────────────────────────────────
● Alpha Vantage News     active          Last sync: 12min ago
○ Reddit                 not configured  [How to configure →]
○ X                      not configured  Requires $100/mo API
○ Internal Community     coming soon     Activates in Phase 3
```

When Reddit is `not_configured`, show a non-intrusive setup prompt:
- One-line: "Add Reddit API credentials to unlock community signals"
- Link to documentation, not a modal

---

## New Components

```
apps/web/src/components/sentiment/
├── toolkit-card.tsx               # Individual toolkit card
├── result-card.tsx                # Candidate result card in toolkit results
├── provider-status-strip.tsx      # Active/not_configured status row
├── sentiment-gauge.tsx            # Visual gauge for sentiment score
├── catalyst-materiality-meter.tsx # Progress bar for materiality score
├── signal-alignment-card.tsx      # News vs community alignment visual
├── themes-split-card.tsx          # Bullish vs bearish themes side-by-side
├── headline-timeline.tsx          # Key articles sorted by time
└── sandbox-review-panel.tsx       # On-demand Sonnet review output
```

---

## i18n Keys to Add

Add EN + ZH translations for:
- All section names and label strings (catalyst types, materiality labels, signal quality labels)
- Toolkit names and descriptions
- Provider status strings
- Suggested user action phrases (never "buy" or "sell")
- Disclaimer text

---

## Skills to Activate During Build

| Skill | When |
|---|---|
| `ui-ux-pro-max` | Design of toolkit cards, result cards, deep-dive page — run `--design-system` |
| `market-news-analyst` | Reference for news catalyst card design patterns |
| `playwright-runner` | Add workflow `.md` for: run toolkit → view result → open deep-dive → run sandbox |

---

## Acceptance Criteria

- [ ] `/sentiment` hub page renders 7 toolkit cards with correct descriptions
- [ ] Provider status strip shows Alpha Vantage as `active`, others as `not_configured`
- [ ] Toolkit "Run" button triggers `POST /api/sentiment/analyze` and shows loading state
- [ ] Result cards render all label rows, themes, takeaway, suggested action
- [ ] "Publish to Community" and "Add to Watchlist" disabled with tooltip on result cards
- [ ] `/sentiment/stock/NVDA` deep-dive renders all 4 sections
- [ ] Community Pulse section shows "not configured" state gracefully — no blank card, clear next step
- [ ] "Run Sandbox Review →" triggers on-demand Sonnet review, shows result inline
- [ ] Cache timestamp visible ("Updated 45 min ago") on result cards and deep-dive
- [ ] Manual refresh button triggers `refresh: true` param on `POST /api/sentiment/analyze`
- [ ] Disclaimer visible on hub page, toolkit results, and deep-dive
- [ ] All new strings in i18n.ts with EN + ZH translations
- [ ] `npm run build` clean
- [ ] playwright-runner workflow file added for sentiment user journey
