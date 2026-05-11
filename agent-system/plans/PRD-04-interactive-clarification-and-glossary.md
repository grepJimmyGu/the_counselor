# PRD-04: Interactive Parameter Clarification + Strategy Capability Glossary

**Status:** Approved for build  
**Date:** 2026-05-11  
**Scope:** Backend schema change + frontend interactive chat loop + homepage glossary section  
**Out of scope:** `not_supported` handling (tracked separately in PRD-05)

---

## Problem

When the parser can't fully parse a user's strategy, it returns `clarification_questions` as a flat list in the validation panel. The user has to:
1. Read the questions in a separate panel
2. Re-type their entire prompt with all the new information
3. Lose conversation context between turns

Additionally, users don't know what signals, assets, and timeframes the system supports before they type anything — so they waste their first attempt with something unsupported.

Two distinct failure modes are currently conflated in the same `needs_clarification` state:
- **Parameter gap** — strategy type is understood and supported, but a specific value (timeframe, threshold, exit rule) is missing
- **Concept gap** — strategy type or signal isn't supported by the engine at all (cross-asset signals, fundamental data, macro triggers)

This PRD covers only the **parameter gap** case.

---

## Goals

1. Make clarification conversational — questions appear as chat bubbles, answers stay in context
2. Pre-populate smart quick-reply chips so users can answer in one click
3. Ensure the re-parse always has full context (original intent + each clarification answer)
4. Surface what's buildable upfront via a homepage glossary so users self-qualify before typing
5. Give the parser a typed `clarification_state` field so the frontend can branch on "needs parameters" vs. "ready" vs. "not supported"

---

## Non-Goals

- Handling `not_supported` strategies (PRD-05)
- Saving clarification conversations to run history
- Multi-turn conversations longer than 5 exchanges (cap at 5 to prevent infinite loops)

---

## Architecture

### Backend changes

#### 1. New `ClarificationState` enum in `app/schemas/strategy.py`

```python
from enum import Enum

class ClarificationState(str, Enum):
    ready = "ready"                      # strategy_json populated, no issues
    needs_parameters = "needs_parameters" # supported type, missing quantifiable fields
    not_supported = "not_supported"       # concept outside engine scope (PRD-05)
```

#### 2. Extend `StrategyChatResponse`

```python
class StrategyChatResponse(BaseModel):
    assistant_message: str
    strategy_json: Optional[StrategyJson]
    missing_fields: list[str]
    clarification_questions: list[str]
    clarification_state: ClarificationState = ClarificationState.ready
    # PRD-05 fields (stubbed here, built later):
    unsupported_reason: Optional[str] = None
    suggested_reformulation: Optional[str] = None
```

**Backward compatibility:** `clarification_state` defaults to `"ready"` — existing clients unaffected.

#### 3. System prompt update in `strategy_parser.py`

Add classification instructions to `_CHAT_PARSE_SYSTEM_PROMPT`:

```
CLASSIFICATION RULES:
Set clarification_state = "needs_parameters" when:
- The strategy type is one of: moving_average_filter, moving_average_crossover,
  momentum_rotation, rsi_mean_reversion, breakout, static_allocation
- AND one or more quantifiable parameters are missing or ambiguous:
  lookback period, entry/exit threshold, universe of tickers, rebalance frequency,
  stop loss %, position sizing

Set clarification_state = "not_supported" when:
- Strategy requires signals from a DIFFERENT asset than the one being traded
  (e.g. "buy gold when oil is up" — signal is oil, trade is gold)
- Strategy requires fundamental data (P/E ratio, earnings, revenue, dividends)
- Strategy requires macro/sentiment data (VIX, CPI, Fed rate, news sentiment)
- Strategy requires short selling, options, or leverage
- Strategy requires intraday data (signals defined in minutes/hours)

Set clarification_state = "ready" when:
- strategy_json is fully populated with no missing required fields
- All parameters have explicit or clearly implied values

For needs_parameters: populate clarification_questions with SPECIFIC, ANSWERABLE
questions. Each question must correspond to exactly one missing parameter.
Maximum 3 questions per turn. Ask the most blocking question first.

GOOD: "Over what lookback period should I measure whether oil is 'up'?
  (e.g. 1 day, 1 week, 1 month)"
BAD: "Can you clarify your strategy?"
```

#### 4. Context accumulation — pass conversation history

Current: parser only receives `user_message` + `previous_strategy_json`.  
Problem: user's follow-up "past 1 month" has no reference to the original "buy gold when oil is up" without context.

**Fix:** frontend constructs a contextual prompt that embeds the original intent:

```
Original strategy request: buy gold when oil price is up

Follow-up answer: The lookback for 'oil is up' should be 1 month (21 trading days)
```

The backend doesn't need to change — this is a frontend concern.

---

### Frontend changes (`research-workspace.tsx`)

#### 1. New `ChatMessage` type

```typescript
type ChatMessage = {
  role: "user" | "assistant" | "clarification";
  content: string;
};
```

`"clarification"` messages render differently — amber left border, HelpCircle icon, no "AI" label prefix.

#### 2. New state

```typescript
const [pendingContext, setPendingContext] = useState<string | null>(null);
// Stores the original strategy prompt when clarifications are pending.
// Cleared on successful parse (clarification_state === "ready") or
// when user explicitly resets the chat.

const [clarificationTurnCount, setClarificationTurnCount] = useState(0);
// Safety cap: max 5 clarification turns before showing "Try rephrasing" message.
```

#### 3. `handleInterpretStrategy` changes

```typescript
async function handleInterpretStrategy(nextPrompt?: string, { autoRun = false } = {}) {
  const activePrompt = nextPrompt ?? prompt;

  // Build contextual prompt: embed original intent if clarifications are pending
  const contextualPrompt = pendingContext
    ? `Original strategy request: ${pendingContext}\n\nFollow-up answer: ${activePrompt}`
    : activePrompt;

  setIsParsing(true);
  setErrorMessage(null);
  setChat((c) => [...c, { role: "user", content: activePrompt }]); // show user's raw answer, not the full context

  try {
    const parsed = await parseStrategy(contextualPrompt, strategy, ...);

    if (parsed.clarification_state === "needs_parameters") {
      // Store original intent on first clarification turn
      if (!pendingContext) setPendingContext(activePrompt);
      setClarificationTurnCount((n) => n + 1);

      // Show assistant message
      setChat((c) => [...c, { role: "assistant", content: parsed.assistant_message }]);

      // Inject each clarification question as its own chat bubble
      parsed.clarification_questions.forEach((q) => {
        setChat((c) => [...c, { role: "clarification", content: q }]);
      });

      setClarifications(parsed.clarification_questions);
      setValidationIssues(parsed.missing_fields);

      // Safety: after 3 turns without resolution, show give-up message
      if (clarificationTurnCount >= 2) {
        setChat((c) => [...c, {
          role: "assistant",
          content: "I'm having trouble pinning down the exact parameters. Try rephrasing your full strategy from scratch, or load a similar example from the templates page."
        }]);
        setPendingContext(null);
        setClarificationTurnCount(0);
      }

    } else {
      // Successful parse — clear clarification state
      setPendingContext(null);
      setClarificationTurnCount(0);
      setClarifications([]);
      setChat((c) => [...c, { role: "assistant", content: parsed.assistant_message }]);
      setStrategy(parsed.strategy_json);
      // ... rest of existing success handling
    }
  } catch { ... }
}
```

#### 4. Clarification chat bubble rendering

```tsx
// In the chat message map:
<div key={...} className={cn(
  "rounded-lg border px-3 py-2.5 text-sm",
  message.role === "assistant" ? "border-border/60 bg-background"
  : message.role === "clarification" ? "border-amber-200 bg-amber-50/60 ml-2"
  : "border-primary/30 bg-primary/8 ml-4"
)}>
  <div className={cn("mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest",
    message.role === "clarification" ? "text-amber-600" : ...)}>
    {message.role === "clarification"
      ? <><HelpCircle className="h-3 w-3" />Question</>
      : message.role === "assistant" ? <><Bot .../>AI Builder</>
      : <><ArrowRight .../>You</>}
  </div>
  <p className="whitespace-pre-wrap leading-6 text-foreground/90">{message.content}</p>
</div>
```

#### 5. Quick-reply chips (shown below scroll area when `clarifications.length > 0`)

Detect question type from keywords and show relevant chips:

```typescript
function getQuickReplies(questions: string[]): string[] {
  const text = questions.join(" ").toLowerCase();
  if (/period|timeframe|lookback|how long|days|week|month/.test(text))
    return ["Past 1 week", "Past 1 month", "Past 3 months", "Past 6 months", "Past 1 year"];
  if (/threshold|how much|percent|%|up by|down by|magnitude/.test(text))
    return ["Any positive move", "More than 2%", "More than 5%", "More than 10%"];
  if (/exit|sell|close|when to|stop/.test(text))
    return ["When signal reverses", "After 1 month", "5% stop loss", "10% stop loss", "No exit rule"];
  if (/universe|ticker|stock|asset|which/.test(text))
    return []; // no chips — user should use ticker search
  // Default
  return ["Use sensible defaults", "Keep it simple", "1 month lookback", "Exit on reversal"];
}
```

Clicking a chip:
1. Sets the prompt textarea value to the chip text
2. Immediately calls `handleInterpretStrategy(chipText)`

Textarea placeholder when `pendingContext` is set:
```
"Answer the question above, or rephrase your full strategy…"
```

---

### Homepage: Strategy Capability Glossary

New section on the homepage between "How It Works" and "Research Templates Preview".

#### Section layout

Title: **"What You Can Build"**  
Subtitle: "Livermore supports price-based strategies. Here's exactly what's available."

Two-column layout:

**Left column — Supported**

| Category | Examples | Parameters |
|---|---|---|
| Moving Average | Simple MA, Exponential MA | Lookback: 5–250 days |
| Crossover | Golden cross, Death cross | Fast: 5–50d · Slow: 50–200d |
| Momentum Rotation | Top-N by N-month return | Top N: 1–5 · Lookback: 21–252d |
| RSI Mean Reversion | Buy oversold, sell overbought | Period: 7–21 · Threshold: 20–40 / 60–80 |
| Breakout | N-day high entry, N-day low exit | Entry window: 10–60d · Stop: 5–15% |
| Static Allocation | Equal-weight, fixed-weight | Rebalance: monthly / quarterly |

**Right column — Available Assets**

Equities:
- US stocks & ETFs (NYSE, NASDAQ) via ticker
- A-shares: Shanghai (.SHH), Shenzhen (.SHZ)

Commodity ETFs:
- GLD (Gold), SLV (Silver), USO (Crude Oil), UNG (Natural Gas), DBA (Agriculture), DBC (Broad Commodities)

Bond ETFs:
- TLT (20Y Treasury), IEF (7-10Y Treasury), SHY (1-3Y Treasury)

Equity ETFs:
- SPY (S&P 500), QQQ (Nasdaq 100), IWM (Russell 2000)

**"Not yet supported" strip** (amber/muted tone):
Cross-asset signals · Fundamental data (P/E, earnings) · Macro indicators (VIX, CPI) · Short selling · Options · Intraday data

#### Component: `components/home/capability-glossary.tsx`

Static component, no API calls. Renders from a hard-coded data structure with a collapsible "Not yet supported" section.

---

## File Inventory

### Backend
| File | Change |
|---|---|
| `app/schemas/strategy.py` | Add `ClarificationState` enum + extend `StrategyChatResponse` |
| `app/services/strategy_parser.py` | Update `_CHAT_PARSE_SYSTEM_PROMPT` with classification rules |

### Frontend
| File | Change |
|---|---|
| `apps/web/src/lib/contracts.ts` | Add `clarification_state` + `unsupported_reason` to `StrategyChatResponse` |
| `apps/web/src/components/workspace/research-workspace.tsx` | `pendingContext` state, `clarificationTurnCount`, chat bubble type, quick-reply chips, `handleInterpretStrategy` branching |
| `apps/web/src/components/home/capability-glossary.tsx` | New static component |
| `apps/web/src/app/page.tsx` | Import and render `CapabilityGlossary` |
| `apps/web/src/lib/i18n.ts` | Add keys for clarification labels, glossary headings |

---

## UX Flow (full happy path)

```
User:  "buy gold when oil price is up"
           ↓
Parser: clarification_state = needs_parameters
        clarification_questions = [
          "Over what lookback period should I measure whether oil is 'up'? (e.g. 1 day, 1 month)",
          "What's the exit condition — when should you sell the gold position?"
        ]
           ↓
Chat injects:
  [AI bubble]   "I understand you want to trade GLD based on USO's performance.
                 I need a couple of details to build this strategy."
  [Question 1]  "Over what lookback period should I measure whether oil is 'up'?"
  [Question 2]  "What's the exit condition — when should you sell the gold position?"

Quick reply chips appear:
  [Past 1 week] [Past 1 month] [Past 3 months] [Past 6 months]

User clicks: "Past 1 month"
           ↓
Re-parse with context:
  prompt = "Original strategy request: buy gold when oil price is up
            Follow-up answer: Past 1 month"
           ↓
Parser: clarification_state = needs_parameters (exit still missing)
        clarification_questions = ["What's the exit condition?"]
           ↓
Quick reply chips:
  [When signal reverses] [After 1 month] [5% stop loss] [10% stop loss]

User clicks: "When signal reverses"
           ↓
Re-parse:  clarification_state = ready
           strategy_json = {
             strategy_type: "moving_average_filter",  ← closest supported approximation
             universe: ["GLD"],
             rules: [{ma_type: "simple", period: 21}],  ← USO 1-month MA as proxy
             ...
           }
           ↓
Auto-run backtest (if autoRun was set)
```

---

## Acceptance Criteria

- [ ] `StrategyChatResponse` has `clarification_state` field with correct enum values
- [ ] Parser classifies "buy SPY when above 200-day MA" as `ready`
- [ ] Parser classifies "buy SPY when the 50-day MA crosses above 200-day MA" with no lookback → `needs_parameters`
- [ ] Parser classifies "buy gold when oil is up" → `not_supported` (verified via unit test or manual test — not built in this PRD, just stubbed)
- [ ] Clarification questions appear as amber chat bubbles, distinct from AI response bubbles
- [ ] Quick reply chips appear and correctly branch by question type (timeframe / magnitude / exit)
- [ ] Clicking a chip auto-submits and re-parses with full context
- [ ] After 5 failed clarification turns, user sees a "try rephrasing" message and state resets
- [ ] `pendingContext` is cleared on successful parse
- [ ] Homepage glossary section renders with supported indicators, asset universe, and "not yet supported" strip
- [ ] All new strings have EN + ZH translations

---

## Decisions (2026-05-11)

1. **Approximation transparency** → **Yes.** When the parser produces a supported approximation of an under-specified or partially-unsupported intent, the `assistant_message` must explicitly state what proxy was used. Example: *"I'm interpreting 'oil is up' as USO's 1-month return being positive, and using that as a moving-average filter on GLD — the closest supported equivalent."*

2. **Glossary placement** → **Both homepage and workspace sidebar.** Homepage section for discovery before first use; collapsible sidebar panel in the workspace for reference while building.

3. **Clarification turn cap** → **3 turns.** If the strategy parameters are unresolved after 3 clarification exchanges, show the "try rephrasing" message and reset clarification state. Rationale: if it takes more than 3 back-and-forths, the user likely needs a different formulation, not more parameters.
