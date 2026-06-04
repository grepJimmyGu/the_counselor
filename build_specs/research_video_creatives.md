# Research Note — Short-Form Video Creatives for Livermore

**Date:** 2026-05-21
**Status:** Research / reference doc. Not a build spec.
**Author:** Claude (creative + production research)
**Platforms in scope:** YouTube Shorts, Instagram Reels, TikTok (9:16 vertical, 30–60s)
**Use case:** Top-of-funnel growth flywheel (per the GTM proposal). Five creative styles to test, with reusable LLM prompts and a recommended production stack.

---

## 1. Why short-form video is the right channel for Livermore

Three platform-specific reasons it fits, beyond "it's where the audience is":

1. **The brand has a real edge against finfluencer hype.** Most short-form finance content is "buy this and get rich." Livermore's anti-hype, data-first tone is *differentiated* on these platforms — there's an underserved audience for skeptical, evidence-based finance content (see The Plain Bagel, Patrick Boyle, Damodaran on YouTube longer-form as proof).
2. **Backtests are visually compelling.** Equity-curve animations, drawdown reveals, side-by-side comparisons — Livermore's UI produces shots that work natively as 9:16 content.
3. **The acquisition funnel is shallow.** From "watched a TikTok" → "land on `/templates/[slug]`" → "run an anonymous backtest" → "sign up" is 3 steps. Most fintech funnels are 6+. The product's own anonymous-one-shot flow (patch 1a) is what makes this video channel work — viewers can taste the product without committing.

---

## 2. Brand voice guardrails (apply to every video)

Any video that violates these damages the brand more than the views are worth:

- **Skeptical, not bearish.** Anti-hype but not preachy or doom-y.
- **Show, don't claim.** Numbers on screen > "trust me bro."
- **One specific insight per video.** Not a feature dump.
- **No predictions.** "Here's what would have happened" not "this will happen."
- **No specific buy/sell calls.** Same publisher-exclusion logic as the Stage 8 alerts spec — Livermore reports what algorithms say, doesn't recommend trades. "The strategy signaled BUY" is fine. "I'm telling you to buy" isn't.
- **Captions on every video.** Most viewers watch muted.
- **Hook in 1.5 seconds.** All three platforms auto-scroll; the first frame matters more than the rest.
- **9:16 vertical, 30–60 seconds.** Sweet spot across all three.
- **Disclaimer text in description / on-screen at least once:** "Research, not advice. Hypothetical results."

---

## 3. Five styles to test

### Style 1 — "I tested that" (investigative debunk)

**Format:** Stitch/duet a finfluencer claim (or screenshot a viral tweet), then run the actual backtest live on Livermore and reveal what the data says. Brand-aligned, naturally viral.

**Why it works:** Stitching/duetting is the highest-reach TikTok format. The reveal-the-truth pattern is one of the most-shared video templates in any niche.

**Sample script (45s):**

```
[0:00, screenshot of finfluencer tweet: "200-day MA on NVDA made 80% last year. Easy money."]
"Eighty percent? Let's check."

[0:03, screen recording: typing in Livermore]
"Backtest. 200-day MA on NVDA. Last 12 months."

[0:10, result renders]
"Returned 34%. Not 80. And here's what they don't show you—"

[0:15, scroll to drawdown panel]
"—a 28% drawdown in March. You'd have sold."

[0:25, sandbox reviewer panel appears]
"Even our system flagged it: 'short window, results may be noise.'"

[0:35]
"Real backtests. Real caveats. Free to try. Link below."
```

**Reusable Claude / ChatGPT prompt:**

```
Write a 45-second short-form video script (TikTok / Reels / YouTube Shorts)
in the "I tested that" investigative-debunk style for Livermore, an anti-hype
investment research tool.

Topic: [INSERT A POPULAR FINANCE CLAIM HERE — e.g., "Buy SPY at every dip
makes guaranteed money", "RSI under 30 = always a buy signal", "DCA into QQQ
beats every active strategy"]

Structure:
- Hook (1-2 seconds): a direct quote of the claim, said skeptically
- Setup (3-10s): "Let's check" — frame the test
- Reveal (10-25s): show the actual backtest result on Livermore (which will
  almost always be less impressive than the hype suggests)
- Twist (25-35s): surface a caveat the original claim ignored — drawdown,
  short window, survivorship bias, regime-dependence
- CTA (35-45s): "Backtest your own claims — free at livermore.app"

Voice: skeptical but not snarky. Data-forward. Calm. Think "The Plain Bagel."
Output format: shot-by-shot with timecodes, on-screen text overlays, and a
voiceover line per shot. Max 8 words per voiceover line.
```

---

### Style 2 — "60-second backtest" (screen-recorded tutorial)

**Format:** Screen recording of building + running a backtest in Livermore, ~60 seconds. Voice-over walking through what you're doing. Hyper-fast pacing.

**Why it works:** Pure product demo. The "build something useful in under a minute" format is evergreen on YouTube Shorts and converts well — viewer who watches the whole thing has effectively seen the entire product loop.

**Sample script (60s):**

```
[0:00, Livermore homepage on screen]
"Sixty seconds. Real backtest. Let's go."

[0:03, click template gallery]
"Pick a template — 200-day moving average."

[0:08, type in ticker]
"Test it on NVDA, last five years."

[0:13, hit Run, equity curve animates in]
"Returned 187% vs SPY's 92%."

[0:22, scroll to metrics]
"Sharpe 0.9. Max drawdown 24%. Win rate 58%."

[0:32, sandbox reviewer panel]
"Here's where it gets real — the system warns this strategy
underperforms in flat markets."

[0:42, hit save → strategy list]
"Save it. Get alerts when the signal flips."

[0:55, link]
"Five years of data. No signup needed. Try it."
```

**Reusable prompt:**

```
Write a 60-second screen-recorded tutorial script for Livermore showing
[INSERT WORKFLOW — e.g., "how to backtest a momentum rotation strategy on
sector ETFs", "how to compare two strategies side-by-side", "how to use
the sandbox reviewer to spot overfitting"].

Pacing is fast — one shot every 3-5 seconds. Voice-over is calm and
confident. Each shot should describe:
1. What's on screen (specific UI element being clicked or shown)
2. The voice-over line (max 8 words per shot)
3. Any on-screen text overlay

End with: "Try it free. Link below."
```

---

### Style 3 — "POV / scenario" (relatable cold open)

**Format:** Text-overlay scenario over a stock image or B-roll. No talking head needed. Highly TikTok-native and the cheapest to produce.

**Why it works:** POV-style hooks are the most-saved format across both Reels and TikTok. The scenario is the hook; the product is the punchline.

**Sample script (30s):**

```
[0:00, text overlay over zoom-in of a phone screen showing a stock chart]
"POV: your friend just made $4K on a meme stock and wants you to YOLO too"

[0:05]
"Before you do — backtest the strategy they swear by"

[0:10, cut to Livermore screen recording]
"Type the strategy in plain English"

[0:15]
"See what it would have done over the last 5 years"

[0:22, zoom on drawdown]
"See the worst losing streak (not just the wins)"

[0:27]
"Free. No signup. livermore.app"
```

**Reusable prompt:**

```
Write a 30-second POV-style short-form video script for Livermore. The POV
scenario should be a relatable retail-investor moment. Pick one:
- "your friend made $4K on a meme stock and wants you to YOLO"
- "you read a Reddit post promising 50%/year returns"
- "a TikTok ad is selling a trading course for $997"
- "you're about to buy at all-time highs because everyone else is"
- "your dad keeps telling you to buy XYZ because his guy on TV said so"

Structure:
- POV setup (0-5s): text overlay describing the scenario, on relevant B-roll
- Pivot (5-10s): "Before you do — backtest it"
- Demo (10-25s): three short screen-recording moments showing Livermore:
  1. input the strategy
  2. see results (with focus on a less-rosy metric like drawdown)
  3. see a sandbox reviewer warning
- CTA (25-30s)

No talking head. Text-overlay style. Background can be: phone-screen B-roll,
stock chart zooms, stylized neutral background, or stock photography.
```

---

### Style 4 — "What if you had..." (historical hypothetical)

**Format:** A counterfactual that taps "what could have been" curiosity. High emotional pull, naturally educational, longer watch time.

**Why it works:** Hypothetical regret + redemption is one of the most engaging narrative arcs in finance content. Bonus: every "what if" is a real backtest, so the work is reusable as a saved strategy + share URL.

**Sample script (40s):**

```
[0:00, text overlay over chart]
"What if you'd backtested 'buy NVDA at every 200-day low' starting in 2020?"

[0:04, equity curve animates]
"$10,000 would have become $94,000."

[0:10]
"But here's what nobody shows you—"

[0:13, drawdown panel]
"You'd have watched it drop to $43,000 in October 2022. For five months."

[0:23]
"Most people sell at the bottom. The strategy only works if you don't."

[0:30, Livermore logo]
"Backtest your own 'what ifs.' Free at livermore.app"
```

**Reusable prompt:**

```
Write a 40-second "what if you had..." historical-hypothetical short-form
video script for Livermore. Pick a real, testable historical strategy:
[INSERT STRATEGY + TICKER + START DATE — e.g., "DCA into QQQ starting Jan 2020",
"200-day MA filter on TSLA since IPO", "Buy gold every time stocks dropped 10%
since 2010", "Sell SPY when VIX > 30 since 2018"]

Structure:
- Hook (0-4s): "What if you had..." with on-screen text and a teasing chart
- Result reveal (4-10s): big number (dollar amount or % return)
- Emotional truth (10-25s): the drawdown / pain that 99% of viewers wouldn't
  have stomached, with specific dates and numbers
- Insight (25-35s): "The strategy works only if you don't sell" or similar
  psychological truth that ties to Livermore's brand of skepticism
- CTA (35-40s)

Voice: dramatic curiosity, not hype. The drawdown is the actual story.
```

---

### Style 5 — "Concept in 30 seconds" (educational explainer)

**Format:** Whiteboard / animated text explaining ONE investing concept. Builds authority and SEO. Evergreen content.

**Why it works:** Educational explainers are the most-linked-to format. They drive long-tail search traffic (YouTube Shorts gets indexed in Google). The viewer doesn't need any product context — they came for the concept and left having learned the tool exists.

**Sample script (30s):**

```
[0:00, "Sharpe Ratio" appears as text, no voice yet]
"Sharpe ratio. Sounds fancy. Here's all it is."

[0:05, simple visualization: bar chart of returns]
"How much extra return you got…"

[0:10, second bar: volatility]
"…per unit of risk you took on."

[0:15, formula appears]
"Returns minus risk-free rate, divided by volatility."

[0:20, example: two strategies side by side]
"Strategy A made 20% with wild swings. Sharpe 0.5."

[0:24]
"Strategy B made 15% smooth. Sharpe 1.2."

[0:27]
"B is better. Even though A made more."

[0:30, CTA]
"Backtest your own strategies. livermore.app"
```

**Reusable prompt:**

```
Write a 30-second "concept in 30 seconds" educational short-form video
script explaining [INSERT INVESTING CONCEPT — e.g., "Sharpe ratio",
"max drawdown", "mean reversion", "survivorship bias", "Sortino ratio",
"win rate vs profit factor", "look-ahead bias", "regime", "carry trade",
"momentum vs value"].

Structure:
- Concept name flashes on screen (0-2s)
- "Sounds fancy. Here's all it is." (deflate the jargon, 2-5s)
- Plain-English definition (5-15s) — one sentence, with a simple visual
- Example showing two cases side-by-side (15-27s)
- Punchline (27-30s) — usually a counterintuitive insight that ties to
  Livermore's brand: e.g., "more return isn't always better", "wins matter
  less than streaks", "the past is louder than the future"

Use animated text + simple visualizations only. No talking head. Tone:
calm, slightly nerdy, friendly.
```

---

## 4. Production stack

### Scripts
- **Claude or ChatGPT** for the prompts above. Either works; Claude is slightly better for tone control if you give it 2–3 examples of your existing brand voice.

### Voice-over (if you don't want to be on camera)
- **ElevenLabs** — most natural-sounding cloned or stock voices. $5–22/mo. Standard for finance creators in 2026.
- **Murf.ai** — solid alternative, slightly more robotic but flexible.
- **Recording your own voice** is still the highest-trust option. iPhone Voice Memos + a $30 lavalier mic gets you 90% of studio quality.

### Screen recording (critical for Styles 2 and 3)
- **Screen Studio** (Mac, $89 one-time) — auto-zooms, smooth cursor, beautiful demos. This is what most fintech and SaaS demo creators use. Best ROI in the stack.
- **CleanShot X** (Mac, $29/yr) — simpler, also great.
- **OBS** (free, all platforms) — full control, steeper learning curve.

### Editing
- **CapCut** (free, desktop + mobile) — dominant editor for TikTok / Reels / Shorts creators. Built-in templates, auto-captions, trending sounds library. Almost no reason to pay for anything else for short-form.
- **Descript** ($15/mo) — if your videos are voice-heavy, this lets you edit by editing the transcript. Game-changer for podcast-style content.
- **DaVinci Resolve** (free, professional) — if you want to grow into longer-form later.

### AI video / avatar (if you want to scale without filming)
- **HeyGen** ($24/mo+) — best AI avatar quality in 2026. Type a script, get a video with a realistic-looking person speaking. Viewers can sometimes tell it's AI; getting harder over time.
- **Runway Gen-4** ($15/mo+) — best for B-roll generation (cinematic stock footage). Don't use for talking heads — uncanny valley still real.
- **Pika** ($10/mo+) — cheaper, faster, lower quality than Runway. Good for quick scene generation.
- **Captions.ai** ($10/mo+) — purpose-built for short-form. Auto-captions, AI editing, eye-contact correction (the "Eye Contact" feature is wildly popular).

### Hooks & trending sounds
- **TrendTok** (TikTok analytics) — find sounds trending in your niche before they peak. Critical for organic reach.
- **CapCut's built-in trending sounds library** — same purpose, simpler.

### Stock footage / B-roll
- **Pexels** (free) and **Pixabay** (free) — solid for finance B-roll (charts, trading screens, city skylines).
- **Storyblocks** ($14/mo) — broader library if you want depth.
- **Custom Runway shots** — 1 per video gives a cinematic signature without breaking budget.

---

## 5. Recommended workflow per video

1. **Script** (5 min) — paste one of the prompts above into Claude or ChatGPT, fill in the bracketed variable, get a draft.
2. **Edit script** (5 min) — cut anything that's not a hook or the punchline. Most AI scripts are 20% too wordy.
3. **Voice-over** (5 min) — record on your phone OR run through ElevenLabs.
4. **Screen recording** (5–15 min) — use Screen Studio for any Livermore UI footage.
5. **B-roll** (5 min) — pull stock chart zooms, phone-screen footage from Pexels. Or use Runway for one custom cinematic shot.
6. **Edit + caption in CapCut** (20–30 min) — drop everything into a 9:16 timeline, auto-caption, pick a trending sound at low volume under the voice-over, color-grade with a CapCut preset.
7. **Export** at 1080×1920 H.264, post natively to each platform.

**Total per video:** 60–90 minutes if you have the assets. 30 minutes once you have a repeatable template.

**Volume target for organic growth:** 3–5 videos/week per platform for the first 60 days to give the algorithm enough data to identify your audience. After that, 2–3/week is sustainable.

---

## 6. Distribution notes (don't waste reach)

- **Don't cross-post the same file to all three platforms.** Each algorithm down-ranks reposted content (it detects the watermark). Recommended: edit one version in CapCut, **export three times** with captions positioned for each platform's safe zone:
  - TikTok UI overlays the bottom 20%
  - Reels overlays the bottom 25%
  - Shorts overlays the bottom 18%
  This 30-second extra step roughly doubles average reach.
- **Post native to each platform.** Don't share a TikTok link to Reels — penalty.
- **Schedule posts in each platform's app or with Buffer / Later.** Algorithms favor posts made through their native APIs.
- **Reply to every comment in the first 60 minutes.** Single highest engagement-rate lever on TikTok and Reels.
- **Cross-link to the SEO landing pages** (Stage 5). The video CTA goes to `livermore.app/templates/<slug>` matching the strategy in the video. The anonymous one-shot flow handles conversion.

---

## 7. Legal / compliance — same posture as the rest of the product

Every video should:

- **Avoid specific buy/sell recommendations to the viewer.** "The strategy signaled BUY" is fine. "I'm telling you to buy" isn't. (Same publisher-exclusion logic as the Stage 8 alerts spec.)
- **Use hypothetical-results disclaimers** — at minimum, on-screen text once and in the video description: "Hypothetical backtest results. Past performance does not guarantee future results. Research, not advice."
- **Don't dramatize specific dollar gains** as predictions. Historical "$10K → $94K" is fine because it's a counterfactual on real data; "you could make $94K" is forward-looking and crosses a line.

If you grow to ≥10K followers on any platform, consult the lawyer who blessed your publisher-exclusion stance and ask whether you want the FTC/SEC disclosure language updated on the channel bio. Common pattern: "Research / education only. Not financial advice."

---

## 8. What to measure

Per platform, weekly:

| Metric | Healthy at 30 days | Healthy at 90 days |
|---|---|---|
| Average view duration | ≥40% | ≥50% |
| Engagement rate (likes + comments + shares ÷ views) | ≥4% | ≥6% |
| Follower growth | +500/week | +2,000/week |
| Click-through rate to livermore.app (where bio link tracking allows) | ≥1.5% | ≥3% |
| Anonymous-backtest conversion rate from video traffic | ≥15% | ≥25% (matches Stage 5's anonymous flow target) |

If a style consistently underperforms after 8 videos, drop it. If a style consistently overperforms after 8 videos, double down — make it 50% of your output and find sub-formats within it.

---

## 9. Suggested first batch (10 videos)

To validate the channel, ship these 10 videos in the first three weeks, mixing styles:

| # | Style | Topic |
|---|---|---|
| 1 | "I tested that" | Most-viral "easy money" finance claim of the week |
| 2 | "60-second backtest" | 200-day MA on NVDA (matches your SEO landing page) |
| 3 | "POV / scenario" | "Your friend wants you to YOLO into a meme stock" |
| 4 | "Concept in 30s" | Sharpe ratio |
| 5 | "What if you had..." | DCA into QQQ starting Jan 2020 |
| 6 | "I tested that" | A popular Reddit r/stocks claim |
| 7 | "60-second backtest" | Momentum rotation on Mag-7 |
| 8 | "Concept in 30s" | Max drawdown |
| 9 | "What if you had..." | 200-day MA filter on TSLA since IPO |
| 10 | "POV / scenario" | "You're about to buy at all-time highs because everyone else is" |

After 10 videos and 3 weeks, you'll have enough engagement data to know which 2–3 styles to scale and which to drop. That decision is the real ROI of running this channel — not any single video going viral.

---

## 10. Open questions to resolve later

- **Whose face / voice fronts the channel?** Founder face = highest trust. AI avatar = scales. Anonymous text-overlay style = no face needed but ceiling on virality. Recommend: founder face for at least the first 30 videos, then test AI avatar variants.
- **English only or bilingual?** Livermore is EN/ZH. Chinese-speaking diaspora is an underserved audience on TikTok/YouTube Shorts for finance content. Recommend: EN only for Year 1; layer in ZH variants of the highest-performing videos in Year 2 (mid-cost: 30 min per video).
- **In-house or agency?** A short-form video agency typically charges $1,500–4,000/month for 12 videos. In-house at 30 min/video × 12 = 6 hours/month — very doable for the founder. Recommend in-house at launch; revisit if the channel takes off.
- **Paid amplification?** Once you have 3–5 videos with ≥7% engagement organically, consider boosting them with $50–200 each on TikTok Spark Ads (uses your organic video as the ad creative). 10× cheaper than starting with paid.
