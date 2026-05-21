# Research Note — Chat v2: From Wizard to Research Partner

**Author:** Claude (PM/UX collaboration with Jimmy Gu)
**Date:** 2026-05-20
**Status:** Proposal / research note. Not a build spec yet — needs a product decision on scope before promoting to a numbered stage.
**Horizon:** Year 1 (3–6 months). Ships alongside Stages 4–6.
**Tier policy:** Chat is equal for all authenticated tiers. (Anonymous remains locked per the May 19 decision.)

---

## 1. The strategic shift

### 1.1 Where chat is today

Today's chat is a **strategy wizard**. The user types a natural-language description ("buy SPY when above its 200-day MA"); the LLM converts it to a strategy JSON; the deterministic engine runs a backtest; the result page renders. One-shot, one-purpose.

This treats the LLM as a complicated form. It works, but it underuses three things:

1. **The LLM's actual strength** — multi-turn reasoning over heterogeneous data sources.
2. **Livermore's data surface** — backtests, robustness suites, evaluation dashboards, community strategies, 10-K extractions. The current chat ignores all of this except the parser path.
3. **The user's research workflow** — questions about strategies, stocks, results, concepts, and comparisons are the actual jobs-to-be-done. Strategy entry is one of many.

### 1.2 The vision: chat as research partner

Reframe chat as a **research partner that knows your data, our data, and investing concepts** — anchored to whatever the user is looking at. The same chat interface answers very different intents based on context:

| Where the user is | What chat knows | Example question |
|---|---|---|
| Workspace, building a strategy | The in-progress strategy JSON | "What if I used the 50-day instead of 200-day?" |
| Stock page (e.g., `/stocks/AAPL`) | The Health/Valuation/Trend dashboard + 10-K data | "What's the bear case for AAPL?" |
| Backtest result page | The completed backtest + robustness results | "Why was my drawdown so bad in March 2020?" |
| Community feed | Public strategies + author info | "Find me momentum strategies that worked in 2022." |
| `/account/saved` | The user's own strategies | "Which of my strategies have the worst Sharpe?" |
| Blank canvas `/chat` | Nothing specific — general research | "What's a Calmar ratio?" |

This is **not** a chatbot grafted onto the side. It is the **universal interface** to every existing capability, plus a few new ones that only work conversationally (multi-turn refinement, cross-data synthesis, comparative analysis).

### 1.3 What chat will NOT do (locked refusals)

To stay credible and within compliance, chat refuses three categories of request:

1. **Trade execution** — "Buy 100 shares of NVDA" gets refused. Livermore is research-only; we say so.
2. **Personalized financial advice** — "Should I invest my $50K in this strategy?" gets a structured refusal pointing the user to the existing sandbox-reviewer skepticism + suitability disclaimers.
3. **Forward predictions** — "Will NVDA go up tomorrow?" — refused with a redirect to backtests of strategies that target the implied thesis.

These refusals are first-class product features, not afterthoughts. They're what makes Livermore chat differ from a general-purpose LLM with stock data.

---

## 2. Three user-facing modes

Internally there's **one chat**, but three framings help users discover what chat can do.

### 2.1 Builder Mode

The current chat, but interactive instead of one-shot. The user iterates a strategy via conversation; chat asks clarifying questions, suggests variations, and incrementally builds up the strategy JSON before running the backtest.

Example multi-turn:

> **User:** I want to test a moving-average strategy on tech stocks.
>
> **Chat:** Great. A few clarifications:
> - **Which tech stocks** — pick a basket (e.g., the Mag-7), an ETF (QQQ), or specific tickers?
> - **What MA length** — 50-day is sensitive, 200-day is slow. I'd suggest 200-day for filter-style, or 50/200 for crossovers.
> - **Long-only or long/short?** Long-only is simpler and usually a better starting point.
>
> **User:** QQQ, 200-day, long-only.
>
> **Chat:** Built. *(strategy preview card renders)*. This is a moving-average filter on QQQ — hold when above 200-day MA, cash otherwise. Last 5 years window by default. Ready to run?
>
> **User:** Yes, but use the last 10 years if you can.
>
> **Chat:** That requires Strategist (Scout custom-history is 5 years). Want me to run 5 years now, or upgrade?

This is the existing wizard turned conversational. Same engine, same parser, dramatically better UX.

### 2.2 Researcher Mode

Q&A about markets, stocks, and investing concepts — anchored to Livermore's data wherever possible.

Examples:

- "Explain Sharpe ratio in one paragraph." → uses `concept_explainer` tool.
- "What's the bear case for AAPL?" → on a stock page, uses `stock_lookup` for current Health/Valuation/Trend + 10-K key risks.
- "How did momentum strategies do in 2022?" → uses `template_search` + `backtest_execute` to pull a recent comparison.
- "Compare AAPL and MSFT on valuation." → `stock_compare`.
- "What does 'sub-period robustness' mean?" → `concept_explainer` anchored to robustness suite docs.

### 2.3 Coach Mode

Analyze user-specific results, walk users through the product, and suggest improvements. Always anchored to the user's own data or to a guided demo.

Examples:

- **"Show me how Livermore works"** → `onboarding_tutor` runs a guided demo with a pre-baked NVDA 200-day MA backtest, walks the user through reading the equity curve, the explainer, the sandbox reviewer, and one robustness sample. Ships **Phase 1** as the primary anchor for new-user activation.
- "Why did this strategy underperform?" → `backtest_drilldown` on attached result.
- "What's the worst-case scenario from these robustness results?" → reads the robustness job output.
- "Suggest two ways to make this strategy more robust." → `backtest_drilldown` + LLM reasoning, suggests parameter changes the user can apply with one click.
- "Apply momentum rotation to my portfolio" → `portfolio_apply_template` (Phase 2 — see §3 catalog).
- "Which of my saved strategies are most correlated?" → `portfolio_diagnostic` (Phase 3).

Coach mode is the most differentiated long-term — it's the experience no general-purpose LLM can replicate. **However, Researcher mode is prioritized higher for Year 1 phasing** (see §6); Coach gets onboarding in Phase 1 and the rest in Phases 2–3.

---

## 3. Modular abilities (the tool catalog)

Chat is built as a tool-calling agent. The LLM picks tools based on intent; each tool is a discrete capability with a clean input/output contract. The catalog below is the **superset** to build over Year 1; phasing in §6 says what ships first.

| # | Tool | Mode | Phase | Description | Tier behaviour |
|---|---|---|---|---|---|
| 1 | `strategy_builder_iterate` | Builder | 1 | Refines an in-progress strategy JSON across turns. Asks clarifying questions when a field is missing. | Equal access. Runs that result in a backtest still count against weekly quota. |
| 2 | `backtest_execute` | Builder + Coach | 1 | Runs a backtest from chat. Streams progress; result renders inline. | Universe/history caps from Stage 3 apply; templates exempt. |
| 3 | `concept_explainer` | Researcher | 1 | Investment concept Q&A (Sharpe, RSI, drawdown, etc.) Answers from a curated content library + LLM, **not** open web search. | Equal access. |
| 4 | `stock_lookup` | Researcher | 1 | Get Health/Valuation/Trend for a ticker. Reuses existing Market Pulse data. | S&P 500 scope for Scout (Stage 3 already gates this). |
| 5 | `template_search` | Builder + Researcher | 1 | Search the template library by intent ("momentum on tech"). | Equal access. |
| 6 | `onboarding_tutor` | Coach | 1 | **NEW.** Guided demo + product walkthrough. Runs a pre-baked NVDA backtest, explains every panel (equity curve, metrics, explainer, sandbox reviewer, sample robustness output), highlights features the user hasn't tried. Doubles as a website explanation surface (linked from `/`, `/templates`, `/account`). | Equal access. Free for first 3 turns even on Scout's daily cap (anti-friction). |
| 7 | `backtest_explain` | Coach | 1 | Plain-English explanation of a finished backtest. Wraps the existing `/api/insights/explain`. | Equal access. |
| 8 | `stock_compare` (with **percentile mode**) | Researcher | 2 | Two modes: (a) **side-by-side** — compare 2–5 stocks on Health/Valuation/Trend metrics; (b) **percentile** — for a single ticker and a metric (FCF yield, P/E, ROE, gross margin, etc.), return the ticker's percentile rank within a reference universe. Default universe: **S&P 500**. Example: "What's AAPL's FCF percentile?" → returns "AAPL FCF yield is 2.1%, which is the 38th percentile in the S&P 500." | Side-by-side: top-500 only for Scout. Percentile: same scope rule, universe always S&P 500 for Scout. |
| 9 | `strategy_search` | Researcher | 2 | Search community published strategies. | Equal access. |
| 10 | `backtest_drilldown` | Coach | 2 | Specific drill-down on a backtest result. Examples: worst drawdown month, top 3 winning trades, regime breakdown. | Equal access. |
| 11 | `robustness_run_from_chat` | Coach | 2 | Trigger a robustness suite from chat. Returns job_id + streams status. | Robustness gate from Stage 3 applies (Strategist+ only for full suite). |
| 12 | `portfolio_apply_template` | Builder | 2 | **NEW.** User uploads a portfolio (CSV or pasted tickers + weights) and applies a strategy template to it. Returns: (a) current signals — for each holding, whether the strategy says HOLD / SELL / BUY now; (b) hypothetical backtest of the template on the user's universe over the user's allowed window; (c) allocation comparison (template's recommended weights vs user's current). | Equal access. Backtest portion inherits Stage 3 universe + history caps. Portfolio file is private to the user. |
| 13 | `portfolio_diagnostic` | Coach | 3 | Analyze the user's saved strategies as a portfolio. Correlation, concentration, regime exposure. | Equal access. Phase 3. |
| 14 | `news_anchored_qa` | Researcher | 3 | Q&A on recent news for a stock. Requires news/sentiment infra (Stage 4-extension or Year 2). | Equal access if shipped. |

### 3.1 Tool design conventions

Every tool follows the same shape so the LLM can compose them naturally:

```python
class ToolSchema:
    name: str
    description: str  # exactly what this does, anchored to Livermore
    parameters: JSONSchema  # OpenAI function-calling format
    cost_class: Literal["light", "medium", "heavy"]  # for routing
    requires_tier: Optional[Literal["strategist", "quant"]]  # most are None
```

Tools return structured JSON that the LLM can quote, summarize, or expand on. Examples:

```python
# stock_lookup returns
{
  "ticker": "AAPL",
  "as_of": "2026-05-20",
  "health": {"score": "Moderately Positive", "drivers": ["FCF strong", "ROE 35%", "balance sheet healthy"]},
  "valuation": {"score": "Caution", "drivers": ["P/E 32 above 5y avg", "FCF yield 2.1%"]},
  "trend": {"score": "Neutral", "drivers": ["3M flat", "above 200-day MA"]},
  "summary": "Strong operating fundamentals offset by stretched valuation. Trend uninspiring."
}
```

The chat then weaves this into a natural-language answer, with citation chips (see §5.4) linking the data points back to their source.

### 3.2 Tool-routing examples

How the LLM decides which tool to call:

| User says | Intent | Tools called |
|---|---|---|
| "How does this product work?" / "Show me what I can do here." | onboarding | `onboarding_tutor` |
| "What's a Sharpe ratio?" | concept | `concept_explainer` |
| "AAPL bear case?" | stock-anchored | `stock_lookup(AAPL)` |
| "Compare AAPL and MSFT." | comparison | `stock_compare(tickers=[AAPL, MSFT], mode="side_by_side")` |
| "What's AAPL's FCF percentile?" | percentile | `stock_compare(ticker="AAPL", metric="fcf_yield", mode="percentile", universe="sp500")` |
| "Is NVDA's ROE high or low?" | percentile | `stock_compare(ticker="NVDA", metric="roe", mode="percentile", universe="sp500")` |
| "Build a moving-average strategy on QQQ." | builder | `strategy_builder_iterate` (multi-turn) |
| "Run it." (after a strategy is built) | execute | `backtest_execute(...)` |
| "Here's my portfolio — apply momentum rotation to it." (CSV attached or pasted) | portfolio | `portfolio_apply_template(portfolio=..., template_id="momentum_rotation")` |
| "Why was the 2020 drawdown so bad?" | coach | `backtest_drilldown(result_id, "drawdown_march_2020")` |
| "Which of my strategies are too correlated?" | coach | `portfolio_diagnostic(user_id)` |
| "Find me momentum strategies on commodities." | researcher | `strategy_search(query)` + `template_search(query)` |

---

## 4. Technical complexity

### 4.1 Architecture overview

```
┌──────────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                           │
│  ┌─────────────────┐   ┌──────────────────────────────────┐  │
│  │ Chat widget /   │──▶│ EventSource → server-sent events │  │
│  │ /chat page      │   │ (streaming tokens + tool calls)  │  │
│  └─────────────────┘   └──────────────────────────────────┘  │
└──────────────────┬───────────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  POST /api/chat/conversations/{id}/messages (FastAPI)         │
│                                                                │
│   1. Load conversation history from `chat_messages`           │
│   2. Compose prompt: system + history + user message          │
│   3. Call LLM with tool definitions                           │
│   4. If LLM returns tool_call → execute tool → loop          │
│   5. Stream final tokens to client via SSE                    │
│   6. Persist user message + assistant response                │
└──────────────────┬───────────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Tool executor                                                 │
│  ┌──────────────────┬──────────────────┬──────────────────┐  │
│  │ strategy_builder │ backtest_execute │ stock_lookup     │  │
│  │ concept_explainer│ backtest_drilldown │ stock_compare  │  │
│  │ template_search  │ strategy_search    │ robustness_run │  │
│  └──────────────────┴──────────────────┴──────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Implementation primitives

**Tool-calling LLM** — Use OpenAI function-calling format via the existing `llm_adapter.py`. The adapter already speaks OpenAI-compatible JSON. Extend it with `chat_completion_with_tools(messages, tools, stream=True)`.

**Streaming** — FastAPI server-sent events (SSE) endpoint. Stream both LLM token output AND tool-call status (`{"type": "tool_call", "tool": "stock_lookup", "status": "running"}`). Frontend renders progressively.

**Conversation persistence** — Two new tables:

```python
class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), default="New chat")
    context_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # ^ "workspace" | "stock:AAPL" | "backtest:abc123" | "saved:xyz"
    context_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant" | "tool"
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # what tools the assistant called
    tool_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # cached tool outputs
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
```

Context window management: pass the last 10 messages + a summary of older turns. Re-summarize every 20 messages.

**Cost-aware model routing** — Default to `gpt-4o-mini` for routine queries; escalate to `gpt-4o` only when:

- A tool returns a complex JSON payload (>5 KB) that needs synthesis
- The user explicitly asks for "deep analysis" / "compare" / "explain why"
- The conversation has >10 turns (context size grows; mini struggles with long context)

Routing decision is a simple heuristic in the adapter, not LLM-decided.

**Caching common responses** — `concept_explainer` outputs are cached for 30 days per `(concept, locale)` key. Frequently asked stock questions ("AAPL bear case") cached for 24h. Cache invalidates on price/fundamental refresh.

### 4.3 Cost analysis (Year 1, 100K MAU target)

Assumptions:
- 100K MAU split: 93K Scout, 6.8K Strategist, 0.7K Quant (per GTM proposal)
- 40% of authed MAU use chat at all in a given week
- Scouts: hard cap at 20 turns/day, 100/week. Median Scout user 6–8 turns/week, p95 hits the 100/wk cap.
- Strategists: median 15 turns/week, p95 60 turns/week.
- Quants: median 25 turns/week, p95 100+ turns/week.
- Average turn: ~4K input tokens + 1K output tokens (after context summarization)
- Model split: 80% `gpt-4o-mini` ($0.15 / $0.60 per 1M tokens), 20% `gpt-4o` ($2.50 / $10 per 1M)
- Weighted average per turn: ~$0.0007

| Cohort | Weekly active in chat | Median turns/wk | Weekly turns | Weekly cost | Monthly cost |
|---|---|---|---|---|---|
| Scout (capped) | 37,000 | 8 | 296K | $210 | $840 |
| Strategist | 2,700 | 15 | 40K | $30 | $120 |
| Quant | 280 | 25 | 7K | $5 | $20 |
| **Total** | **40K** | | **343K** | **$245** | **~$980/mo** |

The Scout daily cap **roughly halves** the worst-case cost vs the original "equal at all tiers without cap" model (the original projected $1.5K/mo; the cap brings it to ~$1K/mo). For comparison, Stripe transaction fees on $200K MRR are ~$6K/mo. Chat LLM cost is ~16% of that — material but very manageable.

Cost containment levers if usage runs hot:
1. Move more queries to `gpt-4o-mini` (saves ~60% of LLM spend)
2. Tighten caching window (concept_explainer to 90d, stock_lookup to 6h)
3. Tighten Scout cap from 20→15 turns/day (saves ~25% if Scouts are the cost driver)
4. Per-tool cost class — heavy tools (`portfolio_apply_template`, `robustness_run_from_chat`) restricted on Scout

### 4.4 Latency targets

| Operation | Target p50 | Target p95 |
|---|---|---|
| First token after user message | 800ms | 2.5s |
| Per-token streaming | 30ms | 80ms |
| Tool call latency (light tools like `concept_explainer`) | 200ms | 600ms |
| Tool call latency (medium: `stock_lookup`, `template_search`) | 500ms | 1.5s |
| Tool call latency (heavy: `backtest_execute`, `robustness_run`) | 3s | 10s — show progress |

Heavy tools stream progress events (`"Running backtest..." → "Fetching AAPL prices..." → "Computing metrics..."`) so the UX doesn't feel stuck.

### 4.5 Anti-abuse and refusals

**Rate limits (per §7):**
- Anonymous: chat locked entirely (returns 401 `authentication_required` from `/api/chat/conversations/*`)
- Scout: 20 turns/day, 100/week (rolling). First 3 `onboarding_tutor` turns exempt. Hitting the cap returns 402 with `code='chat_quota_exhausted'` and `cta_action='trial'`.
- Strategist: 100 turns/day, 500/week
- Quant: unlimited (soft monitoring)
- 1 active conversation at a time per user (no parallel sessions; prevents bot abuse)
- 20K-token-per-turn cap (truncate user prompt if exceeded)
- 50K-token-per-conversation cap (auto-archive and start new conv at limit)

**Prompt injection / jailbreaks:**
- Sanitize any user-supplied content (community strategy descriptions, comments) before LLM sees them — strip `<system>` blocks, role-flip attempts
- Wrap tool outputs in clearly delimited markers so LLM doesn't confuse data with instructions
- System prompt is unchangeable; user cannot override

**Refusal patterns** (built into system prompt):

```
You are Livermore's research partner. You DO NOT:
- Execute trades or recommend specific securities to buy or sell
- Provide personalized financial advice — always remind users that backtest
  results are hypothetical and not predictive
- Make forward-looking predictions about prices
- Discuss topics unrelated to investment research, markets, and strategies
  (politely redirect)

When a user asks you to do any of these, respond with a brief refusal and
offer a research-oriented alternative.
```

These refusals are tested with adversarial prompts in CI.

### 4.6 Hallucination management

Chat is anchored to **Livermore-controlled data**. The LLM is NOT given open web search.

Three guardrails:

1. **Tool-output-or-refuse** — if a question would require data the chat can't get (e.g., "What's NVDA's earnings call going to say next week?"), the LLM is instructed to say so and offer an alternative ("I can show you historical earnings reaction patterns").

2. **Citation chips on numeric claims** — when chat mentions a metric (Sharpe 1.4, drawdown -23%), it generates a citation chip linking to the actual data row. Numeric claims without citations are flagged in QA.

3. **Confidence levels** — chat is encouraged to express uncertainty when data is sparse. "Based on 3 backtests over a short window — limited confidence" is preferred to a flat statement.

### 4.7 Existing code to extend vs build

| Module | Status | Action |
|---|---|---|
| `apps/api/app/services/llm_adapter.py` | Exists | Extend with `chat_completion_with_tools` + streaming |
| `apps/api/app/services/strategy_parser.py` | Exists | Refactor into a tool callable by chat |
| `apps/api/app/services/insights.py` | Exists | Wrap `explain` + `sandbox_review` as chat tools |
| `apps/api/app/services/robustness_service.py` | Exists | Wrap as chat tool |
| `apps/api/app/api/routes/chat.py` | Exists (one-shot) | Replace with conversation-based routes |
| `apps/web/src/components/research-workspace.tsx` | Exists | Extract chat UI into a reusable widget |

Net new code: tool router, conversation persistence, SSE streaming, frontend chat widget, citation rendering. Roughly 2,500–3,500 lines of new code.

---

## 5. User adoption and product experience

### 5.1 Placement

Chat lives in **two places**:

1. **Floating widget** — bottom-right of every authenticated page. Collapsed by default; expands to a 380×600 panel. Carries page context automatically (`context_type: "stock:AAPL"` on a stock page).

2. **Dedicated `/chat` page** — full-screen, conversation list on the left, message thread + composer in the center. For blank-canvas exploration and revisiting past conversations.

Both surfaces share the same conversation store, so the user can start a chat in the widget and continue at full-screen later.

Anonymous users see the floating widget collapsed with a "Sign up to use chat" CTA on click (chat remains locked for anonymous per the May 19 decision).

### 5.2 Context awareness

The widget detects context from the URL on mount and passes it to the conversation:

| Page | Detected context | What chat knows |
|---|---|---|
| `/workspace` | `workspace` | Current draft strategy from local state |
| `/stocks/[ticker]` | `stock:[ticker]` | Health/Val/Trend, business model, market position |
| `/backtest/[result_id]` | `backtest:[result_id]` | Full result + robustness if available |
| `/s/[slug]` | `community_strategy:[slug]` | Published strategy details + comments |
| `/account/saved` | `user_saved` | List of user's saved strategies |
| `/chat` | `general` | Nothing pre-loaded — blank canvas |

Context shows as a chip at the top of the chat: `📊 Looking at AAPL` or `📈 Looking at backtest from 2026-05-12`. User can click to dismiss the context (switch to blank-canvas mode).

### 5.3 Conversation persistence

Every chat is saved. `/chat` page shows a left sidebar with:

- "Today" (current conversation)
- "Yesterday"
- "Last 7 days"
- "Older" (paginated)

Auto-generated title (first user message, summarized to ~6 words by `gpt-4o-mini`). User can rename or pin conversations.

Search across conversation history is a Phase 3 feature.

### 5.4 Multi-modal output

Chat messages are not plain text. They render:

- **Markdown** — headings, bullets, code blocks (for strategy JSON), tables
- **Embedded charts** — when chat returns time series, render a small Recharts chart inline
- **Citation chips** — clickable pills next to numeric claims, e.g., "Sharpe 1.4 [AAPL 5y backtest →]" links to the actual backtest
- **Action cards** — at the bottom of certain responses, render a card with the result of a tool call (strategy preview, backtest summary, stock scorecard) and a primary CTA ("Run this", "Save", "Open full result")
- **Quick-action chips** — at the bottom of each assistant message, 2–4 suggested follow-ups ("Compare to SPY", "Run robustness", "Try with 50-day MA")

The quick-action chips are LLM-generated based on the prior message; they're not hardcoded.

### 5.5 Onboarding

First time a user opens chat, a one-time onboarding shows:

```
Hi — I'm Livermore's research partner.

You can ask me to:
  📊 Build and refine a strategy: "build me a momentum strategy on tech"
  🔍 Research a stock: "what's the bear case for AAPL?"
  💡 Explain a concept: "what's a Sharpe ratio?"
  📈 Analyze a backtest: "why was my drawdown so bad in 2020?"

What would you like to start with?

  [ Build a strategy ] [ Research a stock ] [ Explain a concept ]
```

Each button preloads a quick-start prompt. Onboarding never re-shows.

### 5.6 Discoverability of advanced features

Most users won't discover the deeper tools (`robustness_run_from_chat`, `portfolio_diagnostic`) on their own. Two surfaces help:

1. **Quick-action chips in context** — after a backtest result is shown, chat suggests "Run robustness on this" as a chip. The user clicks, and the tool runs without them needing to know it exists.

2. **`/chat/help` doc** — a curated catalog of "things you can ask" with examples per mode. Linked from the chat widget header.

### 5.7 Discoverable refusals

When chat refuses (e.g., "I can't give specific buy/sell advice"), the refusal text **explains why** and **offers an alternative**:

> "I can't tell you whether to buy AAPL — that depends on your goals and risk tolerance, which are yours to set. What I CAN do:
>   • Show you the current Health/Valuation/Trend scorecard
>   • Backtest a strategy that would have signaled when to buy or sell AAPL historically
>   • Compare AAPL to other large-cap tech on key metrics
>
> Which of these would help?"

Refusal-as-redirect, not refusal-as-wall. This is a UX detail that materially changes trust.

---

## 6. Phasing and roadmap

Three phases over Year 1 (~12 weeks). Phasing puts **Researcher Mode + onboarding ahead of deep Coach features**, on the basis that:

- Researcher unlocks chat value the moment a user signs up (no need to first build a strategy)
- Onboarding (Coach Mode entry point) is the activation lever for new signups
- Deep Coach features (drilldown, robustness, portfolio diagnostic) are higher leverage but reach fewer users until the funnel is filled

Each phase ships independently and can move to prod separately.

### Phase 1 — Foundation + Builder + Researcher (light) + Onboarding (Weeks 1–4)

**Goal:** Functional chat that helps a new user understand the product (Coach onboarding), build a strategy (Builder), and answer basic research questions (Researcher light). Foundation for everything else.

**Ships:**
- `chat_conversations` + `chat_messages` tables
- SSE streaming endpoint
- LLM adapter extension (tool-calling, streaming)
- Tool executor framework
- **Tools shipped (6):** `strategy_builder_iterate`, `backtest_execute`, `concept_explainer`, `stock_lookup`, `template_search`, `onboarding_tutor`, `backtest_explain`
- Floating widget on workspace + stock pages
- Onboarding entry points: homepage, `/templates`, `/account` — each links into the chat widget with `onboarding_tutor` pre-triggered
- Quick-explanation card on the website (above-the-fold on homepage) — 30-second product summary that opens chat as the next step
- Conversation list (basic)
- Refusal patterns
- Rate limits: Scout 20 turns/day, Strategist 100/day, Quant unlimited (see §7)
- `onboarding_tutor` first 3 turns exempt from Scout's cap (anti-friction)

**Success metrics:**
- 40% of new Scouts run `onboarding_tutor` in week 1
- 30% of Strategists use chat in their first week
- p95 first-token latency <2.5s
- Cost <$500/mo at first 5K paid users

### Phase 2 — Researcher (full) + Coach (drilldown + portfolio apply) (Weeks 5–8)

**Goal:** Chat becomes the primary research surface. The percentile-mode `stock_compare` is the highest-leverage Phase 2 tool because it answers questions that have no UI equivalent today ("Where does AAPL rank on FCF yield in the S&P 500?").

**Ships:**
- **Tools shipped (5):** `stock_compare` (with side-by-side AND percentile modes), `strategy_search`, `backtest_drilldown`, `robustness_run_from_chat`, `portfolio_apply_template`
- Pre-computed S&P 500 metric distributions (refreshed daily) for percentile mode
- File-upload UI for `portfolio_apply_template` (CSV parser + ticker validator)
- Multi-modal output (embedded charts, citation chips, action cards)
- Widget extended to all authenticated pages
- `/chat` full-screen page with conversation list
- Quick-action chips (LLM-generated follow-ups)
- Auto-titles for conversations

**Success metrics:**
- 50% of Strategists use chat weekly
- ≥3 tools called per conversation on average (vs ~1 in Phase 1)
- 15% of Strategists upload at least one portfolio in their first month with Phase 2 shipped
- Cost ratio: 70% of tool calls hit cache or `gpt-4o-mini`

### Phase 3 — Cross-strategy + advanced (Weeks 9–12)

**Goal:** The capabilities only a multi-turn, data-anchored research partner can deliver.

**Ships:**
- `portfolio_diagnostic` (correlation + concentration across user's saved strategies)
- `news_anchored_qa` IF news/sentiment infra is ready; otherwise defer to Year 2
- Conversation search across history
- Pinned conversations
- Export conversation to markdown (for sharing or note-taking)
- LLM-generated weekly summary email ("Your chat highlights this week")

**Success metrics:**
- 65% of Strategists use chat weekly
- p50 user reports using chat for "research not just strategy" in NPS survey
- Cross-conversation reference rate (user references "the AAPL conversation from yesterday") — measurable via search/click

---

## 7. Tier policy details

**Revised May 20.** Chat is broadly available across tiers, but with hard turn caps for anonymous (locked) and Scout (rate-limited) to contain LLM cost.

### 7.1 Turn caps by tier

| Tier | Daily turn cap | Weekly cap | Notes |
|---|---|---|---|
| **Anonymous** | 0 (locked) | 0 | Anonymous gets the AnonymousCTA telling them to sign up. The only exception: the website's `onboarding_tutor` quick-explanation card can render a static demo without invoking the LLM. |
| **Scout** | 20 turns/day | 100 turns/week | First 3 `onboarding_tutor` turns exempt from the cap (anti-friction on day 0). Hitting the cap triggers a `chat_quota_exhausted` 402 with `cta_action='trial'` (start Strategist trial = unlimited). |
| **Strategist** | 100 turns/day | 500 turns/week | Effectively unlimited for normal use; cap exists for abuse only. |
| **Quant** | Unlimited | Unlimited | Soft monitoring only. |

The Scout cap of 20/day is generous enough for real research (a focused 30-min session is ~15 turns) but caps LLM cost at predictable levels. A user who burns through 20 turns/day has demonstrated enough engagement that the trial CTA is well-timed.

### 7.2 Tool-level tier behaviour

| Tool | Tier behaviour |
|---|---|
| `strategy_builder_iterate` | Equal. The eventual backtest call goes through `/api/backtest/run` and respects Stage 3 gates (5/wk runs, 5-ticker custom universe for Scout). |
| `backtest_execute` | Equal triggering, but tier caps apply at execution time. Scout that hits the runs cap gets the upgrade modal as usual. |
| `stock_lookup` + `stock_compare` (both modes) | S&P 500 scope for Scout (Stage 3 gate). Percentile mode reference universe is S&P 500 for all tiers; this is a deliberate scope choice for data freshness. |
| `onboarding_tutor` | Equal access. First 3 turns exempt from Scout's daily cap. Anonymous gets the static rendition only. |
| `portfolio_apply_template` | Equal access. The backtest portion inherits Stage 3 universe + history caps. Scout uploading a 30-position portfolio gets a soft pre-warning: "I can backtest the strategy on 5 of your 30 holdings — pick which, or upgrade to test all 30." |
| `robustness_run_from_chat` | Robustness gate from Stage 3 — Strategist+ for full suite, 2-of-5 for Strategist, all 5 for Quant. |
| `portfolio_diagnostic` | Equal but only useful at 5+ saved strategies — naturally favors Strategist+. |

### 7.3 Pre-execution warnings

A Scout can chat-build a 100-ticker strategy, but when they try to run it, the universe gate fires. **Crucial UX point:** chat warns BEFORE running, not just after the 402.

Inline pre-warning in chat:

> **Chat:** I've built a momentum-rotation strategy with 8 tickers and a 7-year backtest window. Heads up: **on Scout, custom strategies are capped at 5 tickers and 5 years of history**. This one would run on Strategist or above ($24/mo, 14-day free trial). Want me to:
>
> - Shrink to 5 tickers + 5-year window and run as Scout
> - Keep as-is and start a free Strategist trial

Same pattern for `chat_quota_exhausted` — chat tells the Scout when they're at 18 of 20 daily turns so they can pace, and when the cap fires, the upgrade CTA is the response, not a hard wall.

### 7.4 New 402 code

Add to the existing entitlement error envelope:

| Code | When | Required tier | cta_action |
|---|---|---|---|
| `chat_quota_exhausted` | Scout 21st turn in a day, or 101st turn in a week | strategist | trial |

The chat is the perfect place for these conversions — natural language, contextual, soft.

---

## 8. Risks and open decisions

### 8.1 Hallucination on financial topics

Even with anchoring, LLMs hallucinate. Mitigations:
- Tool-output-or-refuse pattern
- Citation chips on every numeric claim
- Confidence-level encouraging in system prompt
- Adversarial QA suite (run 100 known-hard questions before each prompt change)

**Open decision:** establish a hallucination-rate target (e.g., <2% of responses contain a factual error per QA sample). Need a manual evaluation cadence — recommend weekly review of 50 random conversations in Phase 1.

### 8.2 Cost overrun

Year 1 forecast is $1.5K–3K/month at 100K MAU. Worst case if users abuse chat: ~3× that. Mitigations:
- 50-turn daily cap (in place from day 1)
- Model routing (default mini, escalate selectively)
- Caching aggressive on stable content
- Monthly cost review with circuit-breaker: if monthly cost >$5K, tighten caps

**Open decision:** confirm $5K/month soft ceiling. If higher acceptable, can relax limits.

### 8.3 Latency vs quality

Faster responses use weaker models. Quality matters more for Coach mode (analyzing results) than Researcher mode (concept Q&A). Recommend:
- Builder + Researcher: default to gpt-4o-mini for speed
- Coach mode: gpt-4o (slower but better reasoning on complex data)

**Open decision:** acceptable to have a 1–2s additional latency on Coach responses?

### 8.4 Refusal too aggressive

Users will be annoyed if chat refuses things that feel reasonable ("show me top dividend stocks" — refused as advice? or returned as a screening result?). Mitigations:
- Distinguish "advice" (specific recommendation for THIS user) from "research" (general screening, analysis)
- Test refusal patterns with 30 real prompts during Phase 1; iterate

**Open decision:** who reviews refusal output during Phase 1? Recommend a weekly 15-min review session.

### 8.5 Privacy and prompt injection from community

Community strategy descriptions are user-supplied. A malicious user could embed prompt-injection text in a description that the chat later processes. Mitigations:
- Sanitize community content before LLM sees it
- Wrap user-supplied content in clear `<community_content>...</community_content>` markers in the system prompt
- Adversarial test: a "prompt injection" community strategy should NOT cause the chat to leak its system prompt

**Open decision:** at what point do we add a content-moderation layer for community-published content? Recommend Year 2 unless an incident triggers earlier.

### 8.6 Chat as a SPOF

If the LLM provider goes down, chat is unavailable. Mitigations:
- Status page for chat
- Graceful degradation: builder mode falls back to the existing one-shot parser
- Multi-provider adapter (later) so we can fail over

**Open decision:** SLA target for chat uptime? Recommend 99% in Phase 1 (allows 7h/month outage), raising to 99.5% in Phase 3.

---

## 9. What this proposal does NOT solve

These were intentionally deferred:

- **Voice input/output** — Year 2.
- **Multi-user shared chats** — Year 2 (collaboration feature).
- **Cross-conversation memory** — chat remembers within a conversation, not across. Implementing cross-conversation memory cleanly requires vector store + retrieval. Year 2.
- **Auto-generated daily/weekly briefings** — Stage 6's email lifecycle covers some of this; chat-driven briefings are deeper but Year 2.
- **Multi-language beyond EN** — Year 2 (chat in Chinese requires a different prompt set, separate model evaluation).
- **Mobile-optimized chat** — works on mobile via responsive widget, but not optimized. Year 2.

---

## 10. Recommended next steps

If this proposal lands:

1. **Promote to a numbered build spec.** Suggest filename `07_chat_v2_research_partner.md` to slot after the current Stage 6 in the build plan.
2. **Pre-decisions to lock** before writing the spec:
   - Confirm tier policy (equal — confirmed today)
   - Confirm cost ceiling ($5K/month soft cap?)
   - Confirm phasing — Phase 1 alone is 4 weeks of focused work; can it run in parallel with Stage 4 (Community) or only after?
   - Confirm refusal-review cadence and owner
3. **Scaffold Phase 1 tickets** — break the Phase 1 deliverable into 5–8 sub-tickets for Claude Code execution, similar to how Stage 3 was scoped down post-Stage-1a.

This proposal lives at `build_specs/research_chat_v2.md`. It is not yet a build spec — it's the strategic case + design that a build spec would be written from.
