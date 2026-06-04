# Video Creatives Batch 1 — Livermore Short-Form Launch Set

**Date:** 2026-05-21
**Status:** Production-ready creative scripts. Five videos, one per style from [`research_video_creatives.md`](research_video_creatives.md).
**Author:** Claude (creative + production)
**Channels:** YouTube Shorts, Instagram Reels, TikTok (9:16, 30–60s)
**Target launch:** Week 1 of the GTM video flywheel — matches the "Suggested first batch" table in the research doc.

---

## How to read this doc

Each creative below has:

1. **Style + slot** — which of the five styles it executes (matches research doc §3)
2. **One-line pitch** — what the viewer takes away
3. **Production surface** — the exact Livermore URL(s) the producer screen-records, so the equity curve, sandbox reviewer warning, etc. are real and not mocked. All references are verified live on `livermorealpha.com` as of 2026-05-21.
4. **Shot-by-shot script** — timecodes, on-screen text, voiceover (max 8 words/line per the brand guardrail)
5. **Production notes** — trending-sound posture, caption-safe-zone reminders, stock B-roll suggestions
6. **Caption + description copy** — the platform-side copy, with disclaimer text
7. **TO VERIFY before recording** — any number that must be confirmed by actually running the backtest on Livermore (we never fabricate returns)

Every video respects the brand guardrails in research doc §2: skeptical-not-bearish, show-don't-claim, no predictions, no specific buy/sell calls to the viewer, hypothetical-results disclaimer in the description and at least once on-screen.

---

## Creative 1 — "I tested that" (Style 1)

**One-line pitch:** A viral "easy money" finance claim gets backtested live on Livermore. The number comes back smaller than the hype, and the sandbox reviewer surfaces what the original tweet hid.

**Production surface:**
- `livermorealpha.com/workspace` (Strategy Builder) — natural-language input + Run
- Template used: **Trend Following** (visible on `/templates`, evidence-tier-untagged but on the homepage carousel)
- Sandbox reviewer panel appears below results post-run

**Length:** 45 seconds.

### Shot-by-shot

| Time  | Shot                                                                                                        | On-screen text                                                       | Voiceover (≤8 words)                                |
| ----- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------- |
| 0:00  | Screenshot of a finfluencer tweet: *"200-day MA on NVDA = easy 80% last year. I've been saying this."*      | "Eighty percent. Really?"                                            | "Eighty percent? Let's check."                      |
| 0:03  | Cut to `/workspace`. Cursor types into the strategy input.                                                  | "Strategy: 200-day MA on NVDA"                                       | "Plain English. Type the strategy."                 |
| 0:08  | Date range field updated to "last 12 months." Click **Run**.                                                | "Period: last 12 months"                                             | "One year. Hit Run."                                |
| 0:11  | Equity curve animates in.                                                                                   | "Return: [TO VERIFY]%"                                               | "Real return: [TO VERIFY] percent."                 |
| 0:17  | Side-by-side comparison row: NVDA buy-and-hold vs MA strategy.                                              | "Buy-and-hold: [TO VERIFY]%"                                         | "Buy-and-hold beat it."                             |
| 0:22  | Scroll to drawdown panel. Highlight peak drawdown number.                                                   | "Max drawdown: [TO VERIFY]%"                                         | "Here's what they didn't show you."                 |
| 0:30  | Sandbox reviewer panel: warning text appears (paraphrase real output).                                      | "Reviewer: 'short window — results may be noise'"                    | "Even the sandbox flags it."                        |
| 0:38  | Zoom out to Livermore logo + URL.                                                                           | "livermorealpha.com — free, no signup"                               | "Backtest the claims. Free."                        |
| 0:42  | End card.                                                                                                   | "Research, not advice. Hypothetical results."                        | (silence — disclaimer reads in 3 seconds)           |

### Production notes

- The tweet screenshot at 0:00 should be a fabricated mock for legal safety unless you have rights to a real one. Keep the handle/avatar generic.
- Don't crop the sandbox reviewer warning — the *language* of it ("results may be noise", "regime-dependent", "low N") is the brand asset. If reviewer output is too verbose, hard-cut to the most punchy sentence.
- Trending sound: pick a low-tension instrumental from CapCut's library, under -18 dB so the voiceover sits on top.

### Caption (TikTok / Reels / Shorts)

> A viral finance claim, actually tested. 200-day MA on NVDA — what the real backtest looks like, and what the sandbox flagged. Free to try yourself, link in bio. Hypothetical backtest results. Past performance does not guarantee future results. Research, not advice.

### TO VERIFY before recording

Open `/workspace`, run "200-day MA on NVDA, last 12 months" with the **Trend Following** template, then fill in:

- 12-month strategy return (%)
- 12-month NVDA buy-and-hold return (%)
- Max drawdown (%)
- Exact sandbox reviewer warning text (paraphrase if needed for line length)

If the real return is actually *higher* than 80% (regime-dependent — bullish years bend this), pivot the angle: *"They said 80%. The data says even better — and here's why you wouldn't have held it."* The drawdown panel is still the punchline.

---

## Creative 2 — "60-second backtest" (Style 2)

**One-line pitch:** Build, run, and read a real Sector Rotation backtest end-to-end in 60 seconds. The viewer effectively sees the entire product loop.

**Production surface:**
- `livermorealpha.com/templates` — pick **Sector Rotation (SPDR)** (Tier A, ranks 11 SPDR ETFs monthly — verified live)
- `livermorealpha.com/workspace` — configure + run + read metrics
- Save → Strategy list (proves the strategy persists)
- Live ticker bar across the top (the FMP-quote ticker bar is now global per work log 2026-05-21)

**Length:** 60 seconds.

### Shot-by-shot

| Time  | Shot                                                                                          | On-screen text                                          | Voiceover (≤8 words)                              |
| ----- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------- |
| 0:00  | `/` home page. Cursor moves toward "Strategy Builder" tile.                                   | "60 seconds. One real backtest."                        | "Sixty seconds. Real backtest. Let's go."         |
| 0:04  | Click into `/templates`. Filter chip "Rotation" highlighted.                                  | "Filter: Rotation"                                      | "Pick a template — Sector Rotation."              |
| 0:09  | Click **Sector Rotation (SPDR)**. Card detail reveals: "Tier A. 11 SPDR ETFs. Monthly ranks." | "Tier A — strong evidence"                              | "Eleven SPDR sectors. Monthly ranks."             |
| 0:16  | Cut to `/workspace`. Template auto-fills strategy. Date range set to last 5 years.            | "Period: 2021–2026"                                     | "Five years. Sectors only."                       |
| 0:21  | Hit **Run**. Equity curve animates in.                                                        | "Return: [TO VERIFY]%"                                  | "Equity curve in real time."                      |
| 0:27  | Scroll to metrics row.                                                                        | "Sharpe [TO VERIFY] · Max DD [TO VERIFY]% · Win [TO VERIFY]%" | "Sharpe. Drawdown. Win rate."             |
| 0:35  | Cursor highlights SPY benchmark line on the chart.                                            | "vs SPY: [TO VERIFY] points"                            | "Beat — or behind — SPY."                         |
| 0:42  | Sandbox reviewer panel opens. Frame the warning line.                                         | "Reviewer: '[TO VERIFY paraphrase]'"                    | "Sandbox flags overfit. Read it."                 |
| 0:50  | Click **Save**. Strategy appears in saved list.                                               | "Saved. Alerts available."                              | "Save it. Get signal alerts."                     |
| 0:55  | End card.                                                                                     | "livermorealpha.com — free anonymous backtest"          | "Try it free. Link below."                        |

### Production notes

- Screen Studio with smooth-cursor enabled. One zoom-in on Run, one zoom on the drawdown number, one zoom on the reviewer panel. Don't over-zoom — three peaks max.
- The 9:16 crop is tight; keep all important UI in the middle 80% horizontally. Livermore is built for desktop, so the producer should narrow the browser window to ~700px wide before recording for cleaner crops.
- Caption bottom-safe-zone: TikTok eats the bottom 20%. Park on-screen text 60–75% from the top.

### Caption

> Sixty seconds. One full strategy build on Livermore — Sector Rotation, 5 years, SPDR sectors. Sharpe, drawdown, win rate. And what the sandbox reviewer warned about. livermorealpha.com — free, no signup. Hypothetical backtest results. Research, not advice.

### TO VERIFY before recording

Run **Sector Rotation (SPDR)** template, 5-year period (2021-05–2026-05). Fill in:

- 5-year strategy return (%)
- Sharpe ratio
- Max drawdown (%)
- Win rate (%)
- SPY benchmark return
- Sandbox reviewer warning text (whatever it actually says — don't invent)

---

## Creative 3 — "POV / scenario" (Style 3)

**One-line pitch:** The viewer's friend YOLO'd into a meme stock. Before they do the same, they learn that Livermore can answer "what would the actual strategy have done" in under a minute, including the part with the pain.

**Production surface:**
- Stock chart B-roll (Pexels: phone-screen-of-stock-chart shot)
- Cuts to `/workspace`: natural-language input field + results + drawdown panel + sandbox warning
- No talking head needed — pure text overlay + screen recording

**Length:** 30 seconds.

### Shot-by-shot

| Time  | Shot                                                                                                | On-screen text                                                          | Voiceover (≤8 words)                                  |
| ----- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------- |
| 0:00  | B-roll: phone showing a green stock chart pumping. Zoom in slightly.                                | "POV: your friend made $4K on a meme stock and wants you to YOLO too"   | (no VO — text reads in 3.5s)                          |
| 0:05  | Same B-roll, text swap.                                                                             | "Before you do — backtest the strategy they swear by"                   | "Before you YOLO — test it."                          |
| 0:09  | Cut to `/workspace`. Cursor types the strategy in plain English.                                    | "'Buy at every dip — last 3 years'"                                     | "Type the strategy plainly."                          |
| 0:15  | Hit Run. Equity curve animates.                                                                     | "Return looks great…"                                                   | "Looks good — until you scroll."                      |
| 0:19  | Scroll to drawdown panel. Highlight a deep red trough.                                              | "Max drawdown: [TO VERIFY]%"                                            | "Worst losing streak. Months."                        |
| 0:24  | Sandbox reviewer warning visible.                                                                   | "Reviewer flagged: [TO VERIFY paraphrase]"                              | "The system flags the risk."                          |
| 0:27  | End card.                                                                                           | "livermorealpha.com — free. No signup."                                 | "Test it. Free. Link below."                          |

### Production notes

- This is the cheapest video in the set. No filming. No voice if you don't want one — text-overlay-only versions perform well on TikTok and Reels per the research doc.
- Background music: trending TikTok meme-stock-related sound, low volume. CapCut's "trending" tab will surface options weekly.
- Variant prompts (for spinning more of these): per research doc §3 Style 3, swap the POV scenario each week — "your dad keeps telling you to buy XYZ", "a TikTok ad is selling a trading course for $997", "you're about to buy at all-time highs because everyone else is."

### Caption

> POV: your friend wants you to YOLO. Before you do, type the strategy in plain English and let Livermore show you the drawdown — the part nobody screenshots. Free, no signup. Hypothetical backtest results. Past performance does not guarantee future results.

### TO VERIFY before recording

Run **"buy at every dip on [popular meme ticker], last 3 years"** in `/workspace`. The producer chooses the ticker close to record-time so it's topical (GME, AMC, PLTR, NVDA after a pop — whatever's in the discourse that week). Fill in:

- Max drawdown (%)
- Sandbox reviewer warning text

If the strategy doesn't trigger a "Reviewer flagged" line, swap to a strategy that does — overfitting warnings reliably appear on short-window or single-ticker strategies. The reviewer is the punchline; if it's silent, the video doesn't land.

---

## Creative 4 — "What if you had…" (Style 4)

**One-line pitch:** A counterfactual on a real, defensible historical strategy. The big-number reveal pulls viewers in; the drawdown reveal is the actual lesson. Brand-true: the past is louder than the future, but the past also hurt more than the screenshots show.

**Production surface:**
- `livermorealpha.com/workspace` — **Dual Momentum** template (Tier A, "combines absolute and relative momentum signals" — verified live)
- Equity curve animation, drawdown panel
- End on a `livermorealpha.com/s/[slug]` share-URL teaser — viewer can open the actual backtest

**Length:** 40 seconds.

### Shot-by-shot

| Time  | Shot                                                                                | On-screen text                                                              | Voiceover (≤8 words)                                  |
| ----- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------- |
| 0:00  | Faded chart background. Text dominates.                                             | "What if you'd run Dual Momentum since 2020?"                               | "What if you ran Dual Momentum?"                      |
| 0:04  | Equity curve animates in from zero. Y-axis value scales up.                         | "$10,000 → $[TO VERIFY]"                                                    | "Ten thousand became [TO VERIFY]."                    |
| 0:10  | Hold on the peak value. Then beat (1 second silence).                               | "But here's what nobody shows you—"                                         | "But here's what you missed."                         |
| 0:14  | Drawdown panel zoom. Specific date label highlighted (e.g. Oct 2022).               | "[TO VERIFY date] — drop to $[TO VERIFY]. [TO VERIFY] months."              | "[TO VERIFY] months. Watching it drop."               |
| 0:24  | Cut back to equity curve, full timeline.                                            | "Most people sell at the bottom."                                           | "Most sell at the bottom."                            |
| 0:29  | Strategy header card visible: "Dual Momentum · Tier A."                             | "Tier A — strong multi-market evidence"                                     | "Tier A. Strong evidence. Still hurts."               |
| 0:34  | End card with share-URL teaser.                                                     | "Run your own 'what if.' livermorealpha.com"                                | "Run your own. Free. Link below."                     |
| 0:38  | Disclaimer overlay.                                                                 | "Research, not advice. Hypothetical results."                               | (no VO)                                               |

### Production notes

- The drawdown beat at 0:10 is the most important moment in this video. Don't rush it. A 1-second hold where the music drops out lets the viewer brace.
- Music: dramatic-curious, not hype. CapCut's "documentary" or "tension" categories. Drop the music briefly at the 0:10 beat then bring it back.
- Cinematic Runway shot (1 per video budget): use it as the opening 1.5s fade-in over the equity curve — clean financial-news aesthetic.

### Caption

> What if you'd run Dual Momentum since 2020? Real numbers, real drawdown — the part nobody screenshots. Open the full backtest from the link in bio. Hypothetical backtest results. Past performance does not guarantee future results. Research, not advice.

### TO VERIFY before recording

Run **Dual Momentum** template starting 2020-01-01. Fill in:

- End value on $10K seed
- Date of worst drawdown (month-year)
- Trough value at the worst drawdown
- Duration of the drawdown (months from peak to recovery)

Save the backtest. The share URL (e.g. `livermorealpha.com/s/abc-123`) goes in the bio + caption so viewers can open the exact view from the video. The published-strategy + share-URL flow shipped in Stage 4a so this is fully working today.

---

## Creative 5 — "Concept in 30 seconds" (Style 5)

**One-line pitch:** Max drawdown explained in plain English with two side-by-side strategies, ending on the counterintuitive truth: the bigger number isn't always the better strategy.

**Production surface:**
- Pure animated text + Livermore screenshots in 2-up grid
- Pull two backtests from the **Trend Following** and **Low Volatility** templates and screenshot their metrics panels
- No talking head, no fancy editing — CapCut animated text + Screen Studio screenshots

**Length:** 30 seconds.

### Shot-by-shot

| Time  | Shot                                                  | On-screen text                                              | Voiceover (≤8 words)                                  |
| ----- | ----------------------------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------- |
| 0:00  | Black background. Two words flash in.                 | "Max Drawdown"                                              | "Max drawdown. Sounds intense."                       |
| 0:03  | Same background. Subtitle appears.                    | "Here's all it is."                                         | "Here's all it is."                                   |
| 0:06  | Simple line chart animation: a peak, then a trough.   | "Peak → trough.  The worst loss."                           | "Peak to trough. The worst loss."                     |
| 0:13  | Two Livermore screenshot panels side by side.         | "Strategy A: Trend Following · DD [TO VERIFY]%"             | "A made [TO VERIFY] percent."                         |
| 0:18  | Continue showing the comparison.                      | "Strategy B: Low Volatility · DD [TO VERIFY]%"              | "B made [TO VERIFY] percent."                         |
| 0:22  | Highlight the drawdown row only on both panels.       | "B's drawdown was half."                                    | "B's drawdown was half."                              |
| 0:25  | Punchline text card.                                  | "Most people couldn't hold A."                              | "Most couldn't hold A. Through it."                   |
| 0:28  | End card.                                             | "Find your tolerance. livermorealpha.com"                   | "Backtest yours. Link below."                         |

### Production notes

- This one is evergreen — once recorded, it works for months and re-uploads. Prioritize for the "concept-in-30" content well that the research doc lists 10 candidate concepts for (Sharpe, mean reversion, survivorship bias, etc. — see research doc §3 Style 5).
- The 0:22 beat is the surprise. Don't undersell it with music. Let the on-screen text breathe for a full second before the punchline arrives.
- Strategy A and B don't need to be Trend Following / Low Volatility specifically — pick any two real Livermore templates where one has a higher return *and* much higher drawdown. Tier A templates only (Cross-Sectional Momentum 12-1, Time-Series Momentum, Sector Rotation SPDR, Dual Momentum, Low Volatility) so the source is defensible.

### Caption

> Max drawdown in 30 seconds. The number nobody quotes when they screenshot their wins. Find the strategy you can actually hold — livermorealpha.com. Hypothetical backtest results. Research, not advice.

### TO VERIFY before recording

Run two Tier A backtests (5y, same period). Fill in:

- Strategy A return + max drawdown
- Strategy B return + max drawdown
- Confirm B's DD is meaningfully lower than A's (≥30% lower — otherwise the punchline is weak; pick different templates)

---

## Production sequencing & batch math

Per the research doc §5 workflow:

| Step                         | Per-video time  | Notes                                                                                                  |
| ---------------------------- | --------------- | ------------------------------------------------------------------------------------------------------ |
| Run real backtests for TO VERIFY values | 10–15 min  | Do all 5 videos' backtests in one Livermore session — share-URL each so they persist                   |
| Voice-over (ElevenLabs or phone) | 5 min       | Skip for Creative 3 (text-only)                                                                        |
| Screen recording (Screen Studio) | 5–15 min  | All 5 share the same `/workspace` setup, so record sequentially in one window                          |
| B-roll (Pexels + 1 Runway)   | 5 min          | Mostly Creative 3 (phone-screen-chart) and Creative 4 (opening fade-in)                                |
| Edit + caption in CapCut     | 20–30 min each | First time per style is slower; second video in the same style is ~50% faster                          |

**Realistic first-batch timeline:** 90 minutes per video × 5 = 7.5 hours, batched over 2–3 days. After this batch you'll have templates in CapCut for each style, dropping subsequent videos to ~30 min.

---

## What this batch validates

Per research doc §8 (what to measure), with five videos in five styles you don't yet have a winner — but you'll know after watching:

- **30-day signal:** which 1–2 styles cross 4% engagement first
- **60-day signal:** which 1–2 styles drive `/templates/<slug>` traffic (Stage 5a SEO landing pages have UTM-ready URLs already)
- **90-day signal:** which style converts to anonymous backtests (Stage 1a flow is live; conversion measurable via `attribution_visits` table)

Once you have 8 videos in the winning style(s), the research doc says drop everything else and make it 50% of output. Don't shortcut that — five videos is not enough data to declare a winner. Resist the urge.

---

## Brand guardrails reminder (every video must clear)

From research doc §2, repeated here so the producer doesn't have to flip back:

- [ ] Skeptical, not bearish
- [ ] Numbers on-screen are real (TO VERIFY filled in from an actual Livermore backtest)
- [ ] One specific insight per video — no feature dumps
- [ ] No predictions ("here's what happened," not "here's what will")
- [ ] No specific buy/sell calls to the viewer
- [ ] Captions baked in (auto-caption in CapCut, manual review)
- [ ] Hook lands in 1.5 seconds
- [ ] 9:16 vertical, length within spec
- [ ] Disclaimer in description AND on-screen at least once: "Hypothetical backtest results. Past performance does not guarantee future results. Research, not advice."
- [ ] Caption stays out of the bottom 25% (Reels safe zone — the tightest of the three)

---

## Open questions for the producer

These aren't blocking — answer when you record:

- **Whose voice?** For Batch 1, founder voice (Jimmy) is highest-trust and the research doc §10 recommends it for the first 30 videos. ElevenLabs is the fallback if scheduling is hard. Don't use HeyGen avatar for Batch 1; revisit after we have organic traction.
- **Music posture?** Calm-tension instrumental from CapCut, under -18 dB. Don't chase trending sounds for Batch 1 — voice clarity matters more than algorithmic reach when proving the format.
- **One-shot or multi-take?** Multi-take. The Livermore UI animations need to be clean; one bad equity-curve render means a re-record. Plan for 2–3 takes per video.

---

*Generated 2026-05-21 from [`research_video_creatives.md`](research_video_creatives.md) + live `livermorealpha.com` UI inventory. All references to Livermore surfaces, templates, and UI elements verified against the production site on date.*
