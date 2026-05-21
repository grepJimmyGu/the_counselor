# Stage 7 — Chat v2: Research Partner (Phase 1 build spec)

**Depends on:** Stage 1 (entitlements + identity), Stage 1a (`AnonymousSession`, weekly meter, 402 envelope), Stage 3 (gating + `require_entitlement`), Stage 6a (PostHog wrapper for analytics events).
**Unblocks:** Phases 2 (full Researcher + Coach drilldown + portfolio apply) and 3 (cross-strategy diagnostic + memory). Each shippable independently.
**Estimated build:** 4 weeks for Phase 1.
**Branch:** `feat/chat-v2-spec` (this spec); implementation tickets get their own `feat/chat-v2-p1-<n>-*` branches.

> **Research note:** [`build_specs/research_chat_v2.md`](research_chat_v2.md) is the design doc this spec implements. Read it first — this spec does NOT duplicate the strategic rationale, mode descriptions, or tool catalog. It locks the decisions that were open in the research note and breaks Phase 1 into concrete tickets.

---

## 0. Decisions locked since the research note

The research note had four open decisions in §10.2. These are the resolutions as of 2026-05-21:

| Decision | Research-note state | Locked answer | Why |
|---|---|---|---|
| **Tier policy** | Equal across authed tiers (proposed) | ✅ Equal across authed tiers | No change from proposal |
| **Anonymous access** | Locked entirely | ❌ **Reversed → Anonymous = ALLOWED with quota** | Echoes the codex/improve-chat-builder PRD direction — gives chat a guest activation surface, parallels existing Stage 1a anonymous 1-backtest cap |
| **Anonymous quota** | n/a (was locked) | **5 chat turns per `AnonymousSession`** | Matches the stingy-taste philosophy of Stage 1a; converts at exhaustion via existing `AnonymousCTA` |
| **Cost ceiling** | $5K/mo soft cap proposed | ✅ **$5K/mo locked.** Alert at $4K monthly. Auto-tighten if exceeded (Scout daily cap 20→15, force all calls to `gpt-4o-mini`) | §0 + ticket #5 monthly cost summary |
| **Phasing concurrency** | Parallel with Stage 4 vs sequential | **Sequential after current main** | Stage 4 has shipped; chat is the next major surface |
| **Refusal-review process** | Weekly 50-conversation review proposed | ✅ **Log-based, not meetings.** Every refusal emits a structured event to `livermore.chat.refusals`. Weekly digest job emails Jimmy with edge cases | §3.6 + ticket #9 |
| **Hallucination eval methodology** | Open (target <2% only confirmed) | ✅ **Hybrid: runtime citation enforcement + nightly LLM-judge audit** on 50-conv sample | §3.7 + ticket #9 |
| **Adversarial corpus authorship** | Open | ✅ **Claude writes the initial 100 prompts** in ticket #8; Jimmy iterates over time | ticket #8 |
| **`onboarding_tutor` content** | Open | ✅ **Jimmy writes the demo script** (+ possibly video creative). Plumbing ships in ticket #3; content slots in before ticket #8 GA | tickets #3 + #8 |
| **`concept_explainer` library** | Open | ✅ **`apps/api/docs/chat_concepts.md`** — ~30 entries seeded from existing tooltip copy; chat tool reads at runtime (no rebuild needed for content edits) | ticket #3 |

All Phase 1 design decisions are locked as of 2026-05-21. See §7 for the decision log.

---

## 1. Phase 1 scope

Four-week build delivering: a chat drawer on every page, six tools, anonymous access with quota, persistence layer, streaming, and onboarding.

### 1.1 What ships

**Backend**
- `chat_conversations` + `chat_messages` tables (schema in research note §4.2)
- SSE streaming endpoint: `POST /api/chat/conversations/{id}/messages` returns `text/event-stream`
- Anonymous chat endpoint: `POST /api/anonymous/chat/{anon_session_id}/messages` — 5-turn cap per `AnonymousSession`, 402 with `chat_quota_exhausted` + `cta_action='signup'` at exhaustion
- LLM adapter extension: `chat_completion_with_tools(messages, tools, stream=True)` on top of existing `llm_adapter.py`
- Tool executor framework: dispatcher that routes LLM tool-calls to Python implementations
- 6 tools wired (per research note §3 table):
  1. `strategy_builder_iterate` — multi-turn refinement; wraps existing `parseStrategy()`
  2. `backtest_execute` — runs backtest from chat; respects Stage 3 caps
  3. `concept_explainer` — investment-concept Q&A from curated content
  4. `stock_lookup` — Health/Val/Trend for a ticker; reuses Market Pulse data
  5. `template_search` — search template library by intent
  6. `onboarding_tutor` — guided product demo with a pre-baked NVDA backtest
- `backtest_explain` (7th tool) — plain-English explanation of a finished backtest; wraps existing `/api/insights/explain`
- Refusal patterns in system prompt + adversarial QA suite (research note §4.5)
- New 402 code: `chat_quota_exhausted`

**Frontend**
- Floating chat widget (380×600 panel, bottom-right) on workspace + stock pages
- Anonymous variant: same widget, shows turn count "(N/5 free turns remaining — sign up for unlimited)"
- Onboarding entry points: homepage card, `/templates`, `/account` — each opens chat with `onboarding_tutor` pre-triggered
- Conversation list (basic — full `/chat` page deferred to Phase 2)
- Citation chips on numeric claims (basic — full multi-modal output deferred to Phase 2)

### 1.2 What doesn't ship (deferred to Phase 2 or later)

Per research note §6 Phase 2/3:

- `stock_compare` (both modes), `strategy_search`, `backtest_drilldown`, `robustness_run_from_chat`, `portfolio_apply_template`
- Multi-modal output: embedded Recharts, action cards, quick-action chips
- Full-screen `/chat` page with conversation list sidebar
- Auto-titled conversations
- Cross-conversation memory, search, pinning, export
- Voice, multi-user shared chats, ZH chat

### 1.3 Success metrics (per research note §6 Phase 1)

- 40% of new Scouts run `onboarding_tutor` in week 1
- 30% of Strategists use chat in their first week
- p95 first-token latency < 2.5s
- Cost < $500/mo at first 5K paid users
- **NEW** (anonymous): 20% of anonymous chat users hit the 5-turn cap → measures conversion intent (event: `anonymous_chat_quota_hit`)

---

## 2. Anonymous chat quota — implementation detail

The new surface. Pattern mirrors Stage 1a's `/api/anonymous/backtest/run`.

### 2.1 Quota mechanics

- Each `AnonymousSession` (created on first visit, cookied as `anon_session_id`) gets **5 chat turns**.
- "Turn" = one user message + one assistant response. Tool calls inside a single turn count as 1.
- Quota tracked on the `AnonymousSession` table: add column `chat_turns_used INTEGER NOT NULL DEFAULT 0`.
- 6th attempt → 402 `chat_quota_exhausted` with `is_anonymous=true`, `cta_action='signup'`, `cta_text='Sign up for unlimited chat'`.
- Quota merge: when the anonymous user signs up, the conversation history merges into their account via existing `merge_anonymous_into_user` flow. Their first paid/scout turn resets the counter.

### 2.2 Token + rate caps (defense in depth)

- 8K-token-per-turn cap for anonymous users (vs 20K for authed) — truncate input if exceeded
- 1 request per 5 seconds per `anon_session_id` — soft rate limit (prevents bot spam)
- Anonymous tool whitelist: only `strategy_builder_iterate`, `concept_explainer`, `template_search`, `onboarding_tutor`, `backtest_execute`. **Excluded:** `stock_lookup` (gates on S&P 500 via existing Stage 3 anyway), `backtest_explain` (requires authed `backtests.id` ownership).

### 2.3 Anonymous chat UX

- Widget opens normally; no auth gate on entry (unlike research note's original "locked entirely" design)
- Turn-count chip in widget header: `3 of 5 free turns left`
- At exhaustion: assistant message renders `AnonymousCTA` inline ("Loved this? Sign up for unlimited chat — your conversation history will carry over"), composer disables
- Sign-up flow returns user to the chat with their conversation merged

---

## 3. Refusals + safety (Phase 1 scope)

From research note §4.5 and §5.7 — no change in policy, but enforce these in Phase 1:

1. **System-prompt refusals** (locked, untouchable by user):
   - No trade execution
   - No personalized financial advice
   - No forward price predictions
   - No topics unrelated to investment research
2. **Refusal-as-redirect copy** (every refusal points to a research alternative — research note §5.7 example)
3. **Adversarial QA suite** — 100 hard prompts run in CI on every prompt change. New file: `apps/api/tests/test_chat_refusal_adversarial.py`. Initial corpus to seed from research note §8.4.
4. **Compliance disclosure copy** in the widget footer: "Research tooling only. Outputs are paper strategies and historical backtests, not financial advice." (Borrowed from codex/improve-chat-builder PRD §safety-copy.)
5. **Prompt-injection sanitization** — wrap any user-supplied content (community strategy descriptions, comments) in `<community_content>...</community_content>` tags before LLM sees them. Strip `<system>` and role-flip attempts.

### 3.6 Refusal event logging (D1)

Every refusal emits one structured log line. Schema:

```json
{
  "event": "chat_refusal",
  "refusal_category": "trade_execution" | "personalized_advice" | "forward_prediction" | "off_topic",
  "user_message_redacted": "<first 120 chars, PII-scrubbed>",
  "assistant_redirect": "<which alternative was offered, if any>",
  "tool_calls_attempted": [],
  "user_id": "<uuid or 'anonymous'>",
  "anon_session_id": "<if anonymous>",
  "tier": "scout" | "strategist" | "quant" | "anonymous",
  "conversation_id": "<uuid>",
  "timestamp": "ISO8601"
}
```

Logger: `livermore.chat.refusals`. Surface via `railway logs --service the_counselor | grep chat_refusal`.

Weekly digest job (Sunday 09:00 UTC, registered in `_start_scheduler`) aggregates the week's refusals by category, samples 5 edge cases per category, emails Jimmy. Edge-case sampler picks refusals where the redirect text is short (likely terse refusal that should have engaged) or where the same `user_id` triggered ≥3 refusals in a session (frustrated user).

### 3.7 Hallucination guardrails (D3 — hybrid)

**Runtime: citation enforcement.** Every numeric claim in chat output (price, percentage, ratio, date, count) must emit a `<cite source="tool:name" id="...">` chip linking to the tool output that produced it. Executor pseudo-flow:

```
1. LLM generates response
2. Scanner detects numeric tokens
3. For each numeric token without a nearby <cite>, reprompt:
   "Wrap the number `N` in a citation chip pointing to one of the tool outputs above."
4. After 2 reprompt failures: redact the number, append warning
   "(some figures redacted — could not be sourced to chat tools)"
5. Emit `numeric_uncited` event for monitoring
```

**Async: LLM-judge auditor.** Nightly cron (02:00 UTC) samples 50 conversations from the past 24h. For each:

```python
auditor_prompt = f"""
The user asked: "{user_message}"
The chat responded: "{assistant_response}"
The chat used these tool outputs: {tool_outputs}

List any factual claims in the response that are NOT supported by the tool outputs.
Output JSON: {{"unsupported_claims": [{{"claim": "...", "reason": "..."}}]}}
"""
```

Uses `gpt-4o-mini` (~$0.001/audit, ~$3/mo at this volume). Flagged conversations land in the weekly digest alongside refusal edge cases.

Target: hallucination rate < 2% (= unsupported_claims / total numeric+factual claims). Reported in the weekly digest.

---

## 4. Tier matrix — Phase 1 row

Adds **chat** column to the existing tier matrix.

| Tier | Daily turn cap | Weekly cap | Tool access |
|---|---|---|---|
| Anonymous | n/a | n/a | 5 turns / `AnonymousSession` (lifetime, not daily). Subset of tools (§2.2) |
| Scout | 20 turns | 100 turns | All Phase 1 tools. First 3 `onboarding_tutor` turns exempt |
| Strategist | 100 turns | 500 turns | All Phase 1 tools |
| Quant | Unlimited (soft monitor) | Unlimited | All Phase 1 tools |

**New 402 code:** `chat_quota_exhausted`. Add to `apps/api/app/api/entitlement_errors.py`. Surfaces in two flavors:
- `is_anonymous=true` → `cta_action='signup'`, `cta_text='Sign up for unlimited chat'`
- `is_anonymous=false` → `cta_action='trial'` (Scout) or `cta_action='upgrade'` (other tiers; unused in Phase 1 since only Scout hits the cap)

---

## 5. Architecture (Phase 1 minimum)

Full architecture is in research note §4.1. Phase 1 ships the minimum slice:

```
┌─────────────────────────────────────────┐
│  Floating widget (apps/web)              │
│  ├─ context detection (page URL)         │
│  └─ EventSource → SSE stream             │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  POST /api/chat/conversations/{id}/messages
│  POST /api/anonymous/chat/{id}/messages  │
│  (FastAPI SSE)                            │
│                                            │
│  1. Load history from chat_messages       │
│  2. Compose: system + history + user      │
│  3. LLM call w/ tool defs (streaming)     │
│  4. Tool calls → executor → re-invoke LLM │
│  5. Stream tokens + tool_call events      │
│  6. Persist user + assistant + tool rows  │
└──────────────┬──────────────────────────┘
               ▼
┌─────────────────────────────────────────┐
│  Tool executor (apps/api/app/services/   │
│   chat_tools/)                            │
│   - strategy_builder_iterate              │
│   - backtest_execute                      │
│   - concept_explainer                     │
│   - stock_lookup                          │
│   - template_search                       │
│   - onboarding_tutor                      │
│   - backtest_explain                      │
└─────────────────────────────────────────┘
```

**Conversation context strategy:** pass last 10 messages verbatim + LLM-summarized older turns. Re-summarize every 20 messages. (Research note §4.2.)

**Cost-aware model routing:** default `gpt-4o-mini`; escalate to `gpt-4o` only when (a) tool output >5KB, (b) user phrase matches "deep analysis / explain why / compare", (c) conversation has >10 turns. Simple heuristic in adapter — not LLM-decided.

---

## 6. Phase 1 ticket breakdown

Nine tickets, each ~1–5 days, sized for independent landing. Suggested branch prefix: `feat/chat-v2-p1-<n>-<slug>`.

| # | Ticket | Effort | Depends on | Branch |
|---|---|---|---|---|
| 1 | DB schema: `chat_conversations` + `chat_messages` + `AnonymousSession.chat_turns_used`. Migration in `migrations.py`. Tests in `test_postgres_migrations.py`. | 1d | — | `feat/chat-v2-p1-1-schema` |
| 2 | LLM adapter extension: `chat_completion_with_tools(messages, tools, stream=True)`. Returns an async iterator of `(token \| tool_call \| done)` events. Unit tests with mocked OpenAI responses. | 3d | 1 | `feat/chat-v2-p1-2-adapter` |
| 3 | Tool executor framework + 3 light tools: `concept_explainer` (with `apps/api/docs/chat_concepts.md` seeded ~30 entries from existing tooltip copy; tool reads doc at runtime), `template_search`, `onboarding_tutor` (plumbing only — script content from Jimmy slots in later). Per-tool unit tests. | 3d | 2 | `feat/chat-v2-p1-3-tools-light` |
| 4 | 4 heavier tools: `strategy_builder_iterate`, `backtest_execute`, `stock_lookup`, `backtest_explain`. Wraps existing services. | 4d | 3 | `feat/chat-v2-p1-4-tools-heavy` |
| 5 | Authenticated chat endpoint: `POST /api/chat/conversations/{id}/messages` with SSE streaming + tool dispatch loop + persistence + tier-aware rate limits. Integration tests. | 4d | 4 | `feat/chat-v2-p1-5-authed-endpoint` |
| 6 | Anonymous chat endpoint: `POST /api/anonymous/chat/{anon_session_id}/messages` with 5-turn cap, tool whitelist, signup-merge integration. New 402 code. | 2d | 5 | `feat/chat-v2-p1-6-anonymous-endpoint` |
| 7 | Frontend chat widget: floating panel, context detection, SSE client, citation chip rendering, turn-count chip for anonymous, refusal rendering, compliance disclosure. | 5d | 5 | `feat/chat-v2-p1-7-widget` |
| 8 | Onboarding entry points: homepage card, `/templates` link, `/account` link — each opens widget pre-triggered with `onboarding_tutor` (Jimmy's script + optional video creative wired in). + adversarial refusal QA suite (100 prompts authored by Claude as seed corpus). | 3d | 7 | `feat/chat-v2-p1-8-onboarding` |
| 9 | **Guardrails:** runtime citation-enforcement reprompt loop + structured refusal logging (§3.6 schema) + nightly LLM-judge auditor cron + weekly refusal/audit digest email. Reuses `app/jobs/qa_jobs.py` pattern. | 3d | 4 + 5 | `feat/chat-v2-p1-9-guardrails` |

**Critical path:** 1 → 2 → 3 → 4 → 5 → 7 → 8. Tickets 6 (anonymous) and 9 (guardrails) can run in parallel with 7 after 5 lands. Total elapsed ≈ 4 weeks single-developer; ~2.5 weeks with two developers running 6+9 in parallel with 7.

---

## 7. Decision log

All Phase 1 design decisions resolved as of 2026-05-21. Sprint can kick off without further input.

| # | Decision | Resolution | Implementation home |
|---|---|---|---|
| D1 | Refusal-review process | Log-based, not weekly meetings. Structured event per refusal; weekly digest email surfaces edge cases for Jimmy | §3.6, ticket #9 |
| D2 | Cost circuit-breaker | $5K/mo soft cap. Alert at $4K. Auto-tighten if exceeded (Scout daily 20→15, force all to `gpt-4o-mini`) | §0, ticket #5 monthly summary log |
| D3 | Hallucination eval methodology | Hybrid: runtime citation-chip enforcement + nightly LLM-judge auditor on 50-conv sample. Target <2% unsupported claims | §3.7, ticket #9 |
| D4 | Adversarial corpus authorship | Claude authors the initial 100 prompts as seed. Jimmy iterates over time as real edge cases surface | ticket #8 |
| D5 | `onboarding_tutor` content | Jimmy writes the demo script and optionally produces video creative. Ticket #3 ships plumbing; ticket #8 wires Jimmy's content before GA | tickets #3 + #8 |
| D6 | `concept_explainer` content library | `apps/api/docs/chat_concepts.md` doc with ~30 entries seeded from existing tooltip copy. Tool reads at runtime so content edits don't require redeploy. Jimmy owns the doc going forward | ticket #3 |

**Launch-readiness items** (not build-blockers, revisit before GA):
- Hallucination rate measured against the <2% target — first month's digest data
- Cost trajectory tracking — confirm pacing under $5K/mo before lifting any rate-limit
- Anonymous-to-signup conversion rate (success metric §1.3) — calibrate the 5-turn cap if conversion is too low or abuse is too high

---

## 8. References

- Research note: [build_specs/research_chat_v2.md](research_chat_v2.md) (660 lines, the canonical design)
- Borrowed design artifacts from codex/improve-chat-builder (no code carried forward, but the typed action union + L0–L5 risk model + 8 QA scenarios are reusable as design lenses for tickets 3, 4, 7)
- Stage 1a anonymous pattern: [apps/api/app/api/routes/anonymous.py](../apps/api/app/api/routes/anonymous.py), [apps/api/app/models/anonymous_session.py](../apps/api/app/models/anonymous_session.py)
- Stage 3 gating dep: [apps/api/app/api/deps_entitlement.py](../apps/api/app/api/deps_entitlement.py)
- 402 envelope: [apps/api/app/api/entitlement_errors.py](../apps/api/app/api/entitlement_errors.py)
