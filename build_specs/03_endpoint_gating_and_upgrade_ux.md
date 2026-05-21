# Stage 3 — Endpoint Gating + Upgrade UX

**Depends on:** Stage 1 (entitlements + identity), Stage 1a (weekly meter + anonymous + 402 envelope foundation), Stage 2 (subscription status).
**Unblocks:** Revenue. After this stage ships, you can charge money.
**Estimated build:** 3–5 working days (down from 10 — Stage 1a already shipped the foundation).
**Branch:** `stage-3-gating-upgrade-ux`

> **REVISION HISTORY**
>
> - **2026-05-19 (original)** — 600-line spec with 10 gating codes, API access namespace,
>   asset-class/commodity/supply-chain gating, ZH localization, and refresh scripts.
> - **2026-05-20 (this version)** — Scoped down to revenue-blocking gates after
>   discussion with the user. Codifies the scope decisions taken before Stage 1a
>   shipped and reflects what Stage 1a actually built (402 envelope, weekly meter,
>   QuotaBadge, AnonymousCTA, saved-strategy quota). See §0 for the full delta.

---

## 0. What changed from the original spec

This stage was rewritten on 2026-05-20 after Stage 1a shipped. The cuts and adjustments:

### Cut entirely

- **API access (`/api/v1/*` namespace + `ApiKey` model)** — no user has asked for it; Quant differentiation rests on robustness suite, A-shares, longer history, larger universe, verified badge.
- **Asset-class gating** (commodities + A-shares) — deferred to a later stage when we actually have non-equity users.
- **Commodity Evaluation Framework gating** — deferred (same reasoning).
- **Supply-chain deep-dive gating** — deferred.
- **A-share symbol search with `is_locked: true`** — deferred.
- **Top-250 ticker quarterly refresh script + admin endpoint** — replaced with a static S&P 500 file (~500 tickers).
- **Tier-aware sandbox review LLM differentiation** — deferred.
- **ZH localization of upgrade copy** — EN only for v1.

### Already shipped in Stage 1a (do not re-build)

- ✅ 402 envelope (`EntitlementErrorDetail`, `EntitlementErrorResponse`, `upgrade_error()` helper) in `apps/api/app/api/entitlement_errors.py`.
- ✅ Weekly runs meter (`weekly_usage` table, `increment_custom_backtest()`, `increment_template_backtest()`).
- ✅ `Entitlements` schema with `custom_backtest_runs_remaining`, `week_start`, `template_runs_unlimited`, `universe_size_max_custom`, `history_window_years_custom`, `saved_strategies_always_public`.
- ✅ Anonymous one-shot flow (`/api/anonymous/entitlements`, `/api/anonymous/backtest/run`, `anonymous_sessions` table, signup-merge).
- ✅ `saved_strategies_quota_reached` gate enforced in `saved_strategy_service.save_strategy()`.
- ✅ `<QuotaBadge />` in nav (Scout shows `N/5 runs · resets Monday`; anonymous shows signup CTA).
- ✅ `<AnonymousCTA />` component (not yet wired into pages — Stage 3 wires it).
- ✅ Frontend `Entitlements` + `AnonymousEntitlements` + `EntitlementErrorDetail` types in `contracts.ts`.

### New in this stage

- `require_entitlement` FastAPI dependency that wraps gated routes.
- Wire `/api/backtest/run` (runs quota + custom-universe + custom-history).
- Wire `/api/robustness/run` (runs quota + test-name whitelist).
- Wire Market Pulse routes (`/api/company/{symbol}/*`, `/api/stocks/*`) for the S&P 500 scope for Scout.
- `GATING_ENABLED` env-var feature flag for shadow-mode rollout.
- Frontend `<UpgradeModal />`, `<SoftPaywall />`, 402 interceptor in API client.
- S&P 500 ticker set as a static Python file.

---

## 1. Context

Stages 1, 1a, and 2 set up identity, plan, billing, and the entitlements data layer. The product still serves every feature to every authenticated user. Stage 3 actually **enforces the tier matrix** — applies gating to every metered endpoint and surfaces the friction as a friendly upgrade UX (not a 403 wall).

The tier matrix to enforce (Stage 1a canonical version — replaces the original `Livermore_Tiered_GTM_Proposal.docx`):

| Lever | Scout (Free) | Strategist ($24) | Quant ($79) | Enforced in Stage 3? |
|---|---|---|---|---|
| Custom backtest runs / week | 5 | Unlimited | Unlimited | **YES** |
| Template runs | Unlimited | Unlimited | Unlimited | n/a (not gated) |
| Custom universe size | 5 | 25 | 100 | **YES** |
| Custom history window | 5 yr | 10 yr | 20 yr | **YES** |
| Robustness suite | — | 2 of 5 tests | All 5 | **YES** |
| Market Pulse ticker scope | S&P 500 | All US | All US + alerts | **YES** |
| Saved strategies | 10 (all public) | 25 | Unlimited | ✅ already enforced (Stage 1a) |
| Asset classes | Equities | + Commodities | + A-shares | Deferred |
| Commodity Eval Framework | — | Yes | Yes | Deferred |
| Supply-chain deep-dive | — | — | Yes | Deferred |

**Design principle:** every gate fails with a structured **402** response (the envelope already exists in Stage 1a). The frontend reads `error === "upgrade_required"`, picks the matching upgrade modal copy by `code`, and shows the user exactly which tier unlocks it.

---

## 2. Scope

### In scope (this stage)

- FastAPI dependency `require_entitlement` (new).
- Backtest run metering on `/api/backtest/run` (template vs custom split — templates exempt).
- Custom-universe size validator on `/api/backtest/run`.
- Custom-history window validator on `/api/backtest/run`.
- Robustness gating on `/api/robustness/run` (test-name whitelist + counts against weekly quota).
- Market Pulse S&P 500 scope check on `/api/company/{symbol}/trend` and adjacent stock-detail routes.
- `GATING_ENABLED` feature flag + structured shadow-mode logs (when off, log "would-be 402s" but allow the request).
- Frontend `<UpgradeModal />` driven by 402 response.
- Frontend `<SoftPaywall />` inline card for embedded gates.
- Frontend 402 interceptor in `lib/api.ts`.
- Telemetry hooks (structured log lines for now; Stage 6 wires PostHog).

### Out of scope (already shipped or deferred)

- 402 envelope and `upgrade_error()` helper — **already in `entitlement_errors.py`** (Stage 1a).
- Weekly meter + `increment_*` helpers — **already in `entitlements.py`** (Stage 1a).
- `<QuotaBadge />` — **already in nav** (Stage 1a).
- Saved-strategy quota — **already enforced** in `saved_strategy_service.save_strategy()` (Stage 1a).
- API access / `/api/v1/*` namespace / `ApiKey` model — **cut entirely**.
- Asset-class gating (commodities, A-shares) — deferred.
- Commodity Eval Framework gating — deferred.
- Supply-chain deep-dive gating — deferred.
- Symbol search asset-class filter — deferred.
- ZH copy for upgrade modal — EN only for v1.
- Top-250 quarterly refresh script + admin endpoint — replaced by static S&P 500 file.

---

## 3. The 402 envelope (reference)

**Already exists** in `apps/api/app/api/entitlement_errors.py`. Stage 3 uses it as-is. For reference:

```python
class EntitlementErrorDetail(BaseModel):
    code: CodeT  # see Literal definition in the file
    current_tier: Optional[Literal["scout", "strategist", "quant"]] = None
    required_tier: Optional[Literal["strategist", "quant"]] = None
    current_value: Optional[str] = None      # e.g. "5/5 runs", "7 tickers"
    limit_value: Optional[str] = None        # e.g. "5", "10 yr"
    upgrade_url: str                         # frontend deep-link target
    cta_text: str                            # button label
    detail: str                              # human-readable explanation
    is_anonymous: bool = False
    cta_action: Literal["signup", "trial", "checkout", "upgrade"] = "upgrade"
```

The `CodeT` literal already declares all Stage 3 codes for type stability — we just need to wire them through.

### Codes used in Stage 3

| Code | When | Required tier | cta_action |
|---|---|---|---|
| `runs_exhausted` | Scout's 6th custom backtest in a week | strategist | upgrade |
| `universe_too_large` | Custom strategy with > tier cap tickers | strategist (Scout→Strategist) or quant (Strategist→Quant) | upgrade |
| `history_too_long` | Custom strategy with start_date older than tier cap | strategist or quant | upgrade |
| `robustness_test_locked` | Test name not in `ent.robustness_tests` | quant | upgrade |
| `market_pulse_ticker_out_of_scope` | Scout requests a non-S&P-500 ticker | strategist | upgrade |
| `saved_strategies_quota_reached` | Already enforced in Stage 1a | strategist | upgrade |

---

## 4. The gating dependency

**File:** `apps/api/app/api/deps_entitlement.py` (new).

```python
from datetime import date, datetime
from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.entitlement_errors import upgrade_error
from app.data.sp500_tickers import SP500_TICKERS
from app.db.session import get_db
from app.models.user import User
from app.schemas.identity import Entitlements
from app.services.entitlements import (
    get_entitlements,
    get_or_create_current_weekly_usage,
)


def require_entitlement(
    *,
    needs_run_quota: bool = False,
    universe_field: Optional[str] = None,
    history_field: Optional[str] = None,
    template_id_field: Optional[str] = "template_id",  # custom caps skipped if set
    robustness_tests_field: Optional[str] = None,
    market_pulse_ticker_field: Optional[str] = None,
):
    """
    Returns a FastAPI dependency that:
    1. Resolves entitlements for the current user.
    2. Validates the incoming request against those entitlements.
    3. Raises 402 with EntitlementErrorResponse if anything fails.
    4. Returns the (user, entitlements) tuple to the route handler.

    Custom-strategy caps (universe, history) are skipped if the request body
    has a non-null template_id — templates are exempt from those caps.

    When GATING_ENABLED=false (shadow mode), violations are logged as
    `gate_event` info lines but the request is allowed through.
    """
    async def _dep(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        weekly = get_or_create_current_weekly_usage(db, user.id)
        ent = get_entitlements(user, weekly)
        body = await _safe_body(request)

        is_template = bool(body.get(template_id_field)) if template_id_field else False

        # Runs quota — counts custom runs only (templates are unlimited)
        if needs_run_quota and not is_template:
            if ent.custom_backtest_runs_remaining is not None and ent.custom_backtest_runs_remaining <= 0:
                _gate("runs_exhausted", ent,
                      current_value=f"{5 - ent.custom_backtest_runs_remaining}/5",
                      limit_value="5",
                      user_id=user.id, path=request.url.path)

        # Universe size — custom only
        if universe_field and not is_template and body.get(universe_field):
            requested = len(body[universe_field])
            if requested > ent.universe_size_max_custom:
                _gate("universe_too_large", ent,
                      current_value=str(requested),
                      limit_value=str(ent.universe_size_max_custom),
                      user_id=user.id, path=request.url.path)

        # History window — custom only. body[history_field] must be ISO date or YYYY-MM-DD string.
        if history_field and not is_template and body.get(history_field):
            requested_years = _compute_history_years(body[history_field], body.get("end_date"))
            if requested_years > ent.history_window_years_custom:
                _gate("history_too_long", ent,
                      current_value=f"{requested_years:.1f} yr",
                      limit_value=f"{ent.history_window_years_custom} yr",
                      user_id=user.id, path=request.url.path)

        # Robustness test names
        if robustness_tests_field and body.get(robustness_tests_field):
            for test in body[robustness_tests_field]:
                if test not in ent.robustness_tests:
                    _gate("robustness_test_locked", ent,
                          current_value=test,
                          limit_value=",".join(ent.robustness_tests) or "—",
                          user_id=user.id, path=request.url.path)

        # Market Pulse — Scout limited to S&P 500
        if market_pulse_ticker_field:
            ticker = request.path_params.get(market_pulse_ticker_field, "").upper()
            if ent.market_pulse_ticker_scope == "top_250" and ticker not in SP500_TICKERS:
                _gate("market_pulse_ticker_out_of_scope", ent,
                      current_value=ticker,
                      limit_value="S&P 500",
                      user_id=user.id, path=request.url.path)

        return user, ent

    return _dep


async def _safe_body(request: Request) -> dict:
    """Read JSON body if present; return {} otherwise. Body is consumed but
    cached on request.state so the route handler can re-read."""
    if request.method not in ("POST", "PUT", "PATCH"):
        return {}
    if not hasattr(request.state, "_cached_body"):
        try:
            request.state._cached_body = await request.json()
        except Exception:
            request.state._cached_body = {}
    return request.state._cached_body or {}


def _compute_history_years(start_date: str, end_date: Optional[str]) -> float:
    """Parse ISO date strings → years between."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date) if end_date else date.today()
    return (end - start).days / 365.25


def _gate(code, ent: Entitlements, *, current_value: str, limit_value: str,
          user_id: str, path: str) -> None:
    """Either raise 402 (gating enabled) or log shadow-mode event (gating disabled)."""
    from app.core.config import get_settings
    import logging
    log = logging.getLogger("livermore.gating")
    if get_settings().gating_enabled:
        raise upgrade_error(code,
                            current_tier=ent.tier,
                            current_value=current_value,
                            limit_value=limit_value)
    log.info(
        "gate_event code=%s tier=%s user_id=%s path=%s current=%s limit=%s shadow=true",
        code, ent.tier, user_id, path, current_value, limit_value,
    )
```

**Body re-read issue:** FastAPI's `Request.json()` can only be called once by default. The `_safe_body` helper caches the parsed body on `request.state` so the route handler can re-read it. Existing route handlers that use `req: BacktestRunRequest` (Pydantic body parameter) work unchanged because FastAPI's body parsing reads from the same cached stream.

**Shadow-mode log line shape:** `gate_event code=runs_exhausted tier=scout user_id=abc123 path=/api/backtest/run current=5/5 limit=5 shadow=true`. Easy to grep + later parse by Stage 6.

---

## 5. Endpoint-by-endpoint gating

### 5.1 `POST /api/backtest/run`

**Gates:**
- Runs quota (custom only — `template_id` null/missing)
- Universe size (custom only)
- History window (custom only)

**Wiring:**

```python
from app.api.deps_entitlement import require_entitlement
from app.services.entitlements import increment_custom_backtest, increment_template_backtest

@router.post("/run", response_model=BacktestResult)
async def run_backtest(
    payload: BacktestRunRequest,
    auth = Depends(require_entitlement(
        needs_run_quota=True,
        universe_field="universe",          # body.strategy_json.universe — see note
        history_field="start_date",         # body.strategy_json.start_date
        template_id_field="template_id",    # body.template_id
    )),
    db = Depends(get_db),
) -> BacktestResult:
    user, ent = auth
    # ... existing validation + engine.run ...
    result = await engine.run(db, payload.strategy_json)
    # Persist user_id on the BacktestRecord
    bt = db.get(BacktestRecord, result.backtest_id)
    if bt:
        bt.user_id = user.id
        db.commit()
    # Increment the right counter
    if payload.template_id:
        increment_template_backtest(db, user.id)
    else:
        increment_custom_backtest(db, user.id)
    return result
```

**Schema change required:** `BacktestRunRequest` currently is `{strategy_json: StrategyJSON}`. To support template tagging, extend:

```python
class BacktestRunRequest(BaseModel):
    strategy_json: StrategyJSON
    template_id: Optional[str] = None  # NEW — required for templates, null for custom
```

**Universe field path note:** The dependency reads `body[universe_field]`, but the universe is nested inside `strategy_json`. Options:
- (A) Have the dep read `body["strategy_json"]["universe"]` via a path traversal.
- (B) Flatten the request: top-level `universe` and `start_date` alongside `strategy_json`.
- (C) Do the gating inside the route handler instead of the dep.

**Recommendation: (C)** — keep the dep generic, but for routes with nested bodies, do the universe/history check directly in the handler before calling `engine.run`. Less magic, more obvious in code. Concretely:

```python
@router.post("/run", response_model=BacktestResult)
async def run_backtest(
    payload: BacktestRunRequest,
    auth = Depends(require_entitlement(
        needs_run_quota=True,
        # universe + history checked inline below (nested body)
        template_id_field="template_id",
    )),
    db = Depends(get_db),
) -> BacktestResult:
    user, ent = auth
    is_template = bool(payload.template_id)
    if not is_template:
        if len(payload.strategy_json.universe) > ent.universe_size_max_custom:
            raise upgrade_error("universe_too_large",
                                current_tier=ent.tier,
                                current_value=str(len(payload.strategy_json.universe)),
                                limit_value=str(ent.universe_size_max_custom))
        history_years = (payload.strategy_json.end_date - payload.strategy_json.start_date).days / 365.25
        if history_years > ent.history_window_years_custom:
            raise upgrade_error("history_too_long",
                                current_tier=ent.tier,
                                current_value=f"{history_years:.1f} yr",
                                limit_value=f"{ent.history_window_years_custom} yr")
    # ... rest of route
```

### 5.2 `POST /api/robustness/run`

**Gates:**
- Runs quota (counts against same weekly bucket; one robustness suite = one custom run for accounting)
- Test names (each requested test must be in `ent.robustness_tests`)

Robustness uses templates? No — robustness runs against an existing backtest. So the runs quota counts every robustness invocation as "custom" for billing. Reconsider if Quant users hit the limit (they're unlimited so won't).

```python
@router.post("/run")
def run_robustness(
    req: RobustnessRunRequest,
    auth = Depends(require_entitlement(
        needs_run_quota=True,
        robustness_tests_field="tests",
    )),
    db = Depends(get_db),
) -> RobustnessJobResponse:
    user, ent = auth
    increment_custom_backtest(db, user.id)
    return robustness_service.start_job(db, req, user_id=user.id)
```

### 5.3 Market Pulse — `GET /api/company/{symbol}/trend` and adjacent

Routes affected (need verification — likely list):
- `GET /api/company/{symbol}/trend`
- `GET /api/company/{symbol}/overview`
- `GET /api/company/{symbol}/financials`
- `GET /api/company/{symbol}/business`
- `GET /api/stocks/{ticker}` (frontend page → maps to one or more API calls)

For each:

```python
@router.get("/company/{symbol}/trend", response_model=...)
def trend(
    symbol: str,
    auth = Depends(require_entitlement(market_pulse_ticker_field="symbol")),
    ...
):
    user, ent = auth
    # existing logic
```

**Audit step:** before wiring, list every route that returns per-ticker Market Pulse data and decide whether it's gated. Probably 4–6 routes. Document each in the route docstring.

### 5.4 `POST /api/chat/strategy` — NOT gated

Chat is free for all tiers. Every chat that leads to a backtest is metered via `/api/backtest/run`. **Optional addition:** include `entitlements_snapshot` in the response so the chat UI can show "you have 3 of 5 runs left" before the user clicks Run (avoids a 402 surprise).

### 5.5 `POST /api/anonymous/backtest/run` — already gated

Stage 1a's anonymous endpoint already enforces the one-shot cap and constraints. Stage 3 does not change it.

---

## 6. S&P 500 ticker list

**File:** `apps/api/app/data/sp500_tickers.py` (new).

```python
"""Hardcoded S&P 500 constituent list (as of 2026-05-20).

Used by Market Pulse gating: Scout tier can request company-level data for
S&P 500 tickers only. Strategist+ has unrestricted ticker scope.

Refresh policy: manual, when the index reconstitutes (~quarterly). We use
the full S&P 500 (not "top 250") because the mental model is cleaner for
users ("Scout: S&P 500 only") and the source list is a well-known public
artifact, not a market-cap snapshot that drifts daily.
"""
SP500_TICKERS: frozenset[str] = frozenset({
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "BRK.B",
    "LLY", "AVGO", "JPM", "V", "WMT", "XOM", "MA", "UNH", "ORCL", "COST", "HD",
    # ... (full ~500 entries; populate from S&P 500 reference list)
})
```

**Source:** Public reference (Wikipedia's S&P 500 article, or any reliable static source). One-time population; not auto-refreshed for v1. Add a comment with the as-of date and document that staleness for ~1 quarter is acceptable.

**No refresh script for v1.** Manual maintenance via PR when needed.

---

## 7. Frontend

### 7.1 `<UpgradeModal />` (new)

`apps/web/src/components/UpgradeModal.tsx`:

- Subscribed to a global event bus (`apps/web/src/lib/upgrade-modal-event-bus.ts`).
- When a 402 with `error="upgrade_required"` arrives at the API client interceptor, the interceptor emits an event with the `EntitlementErrorDetail`.
- The modal reads `entitlement.code` and picks copy + CTA action.

EN-only copy (no i18n for upgrade modal in v1):

```typescript
const COPY: Record<EntitlementErrorCode, ModalCopy> = {
  runs_exhausted: {
    title: "You've used all 5 custom backtests this week",
    body: "Strategist gives you unlimited custom runs and 10 years of history. Templates always remain unlimited. Try Strategist free for 14 days — no card required.",
    primary_cta: "Start free trial",
    secondary_cta: "See all plans",
  },
  universe_too_large: {
    title: "Custom strategies are capped at {limit} tickers",
    body: "Strategist lets you test up to 25 tickers per custom strategy. Templates have no cap regardless of tier.",
    primary_cta: "Upgrade to Strategist",
    secondary_cta: "Reduce universe",
  },
  history_too_long: {
    title: "Custom backtests are limited to {limit}",
    body: "Strategist gives you 10 years of history — enough to test through 2015-16 and the 2020 crash. Templates use their pre-set windows regardless of tier.",
    primary_cta: "Upgrade to Strategist",
    secondary_cta: "Use {limit} instead",
  },
  robustness_test_locked: {
    title: "{test} is a Quant feature",
    body: "Quant gives you all 5 robustness tests — parameter sensitivity, sub-period, transaction cost, benchmark comparison, peer ticker.",
    primary_cta: "Upgrade to Quant",
    secondary_cta: "Cancel",
  },
  market_pulse_ticker_out_of_scope: {
    title: "{ticker} is outside Scout's research scope",
    body: "Scout covers the S&P 500. Strategist unlocks all US stocks and active market data alerts.",
    primary_cta: "Upgrade to Strategist",
    secondary_cta: "Back",
  },
  saved_strategies_quota_reached: {
    title: "You've saved 10 strategies",
    body: "Strategist lets you save 25 private or public strategies. Quant is unlimited.",
    primary_cta: "Upgrade to Strategist",
    secondary_cta: "Delete a saved strategy",
  },
  // Anonymous codes — emit cta_action="signup" instead of "upgrade"
  anonymous_runs_exhausted: { /* see Stage 1a */ },
  anonymous_universe_too_large: { /* ... */ },
  anonymous_chat_locked: { /* ... */ },
  anonymous_asset_class_locked: { /* ... */ },
};
```

Click handlers map `cta_action`:
- `signup` → `router.push("/signup?intent=continue")`
- `trial` → `router.push("/signup?intent=trial&tier=strategist")`
- `checkout` → `await createCheckoutSession({...}); window.location.href = url`
- `upgrade` → same as `checkout` for the default tier (Strategist or Quant per `required_tier`)

### 7.2 `<SoftPaywall />` (new)

`apps/web/src/components/SoftPaywall.tsx`:

For when a feature is gated but the user is still on the page — render an inline card instead of a modal.

```tsx
<SoftPaywall
  code="market_pulse_ticker_out_of_scope"
  ticker="SMCI"
  onUpgrade={() => router.push("/pricing?gate=market_pulse_ticker_out_of_scope&from=scout")}
/>
```

The card layout:
- Lock icon + feature name (large)
- One-sentence "what you'd see if you upgraded"
- Primary CTA button (Upgrade/Sign up depending on auth state)
- Optional secondary action

Used by `/stocks/[ticker]/page.tsx` when the page-level Market Pulse fetch returns 402.

### 7.3 402 interceptor (new)

`apps/web/src/lib/withUpgradeHandling.ts`:

```typescript
import { dispatchUpgradeModal } from "./upgrade-modal-event-bus";
import type { EntitlementErrorResponse } from "./contracts";

export async function withUpgradeHandling<T>(promise: Promise<T>): Promise<T> {
  try {
    return await promise;
  } catch (err: unknown) {
    if (err instanceof Response && err.status === 402) {
      const body = await err.json() as EntitlementErrorResponse;
      if (body.error === "upgrade_required") {
        dispatchUpgradeModal(body.entitlement);
      }
    }
    throw err;
  }
}
```

The existing `fetchApi` helper in `apps/web/src/lib/api.ts` is updated to detect 402 status, parse the envelope, dispatch the event, and rethrow.

### 7.4 `<QuotaBadge />` — already exists

Stage 1a shipped this. It already reads `custom_backtest_runs_remaining` from the entitlements hook. No changes for Stage 3.

### 7.5 `<AnonymousCTA />` — wire into pages

Stage 1a built the component but didn't wire it. Stage 3 wires it into:
- The strategy-builder result panel (after an anonymous run completes — variant=`after-run`)
- The `/templates/[id]` page below the preview (variant=`before-run`)

### 7.6 Pre-flight warnings in the chat UI

Before the user clicks Run on a custom-built strategy:
- If `universe.length > ent.universe_size_max_custom`: show yellow inline warning with "Strategist supports 25 tickers — upgrade or trim your universe" + a quick-trim button.
- If `history_years > ent.history_window_years_custom`: similar inline warning + auto-clip-to-5yr option.
- If `custom_backtest_runs_remaining === 0`: disable the Run button with tooltip "You've used your weekly custom runs. Templates remain unlimited."

The point: avoid 402 surprise by surfacing the cap before it bites.

---

## 8. Acceptance criteria

1. Scout's 6th custom backtest in a week returns 402 `runs_exhausted`.
2. Scout's 6th custom backtest count is unaffected by template runs (Scout runs 100 templates → custom counter stays at 0).
3. Scout custom strategy with 6-ticker universe returns 402 `universe_too_large`.
4. Scout running a 7-ticker template (e.g., Mag-7 momentum rotation) succeeds (no `universe_too_large`).
5. Scout custom backtest with `start_date = today - 6yr` returns 402 `history_too_long`.
6. Scout running a template with the template's own 10-year window succeeds.
7. Strategist running `parameter_sensitivity` robustness test succeeds.
8. Strategist running `sub_period` robustness test returns 402 `robustness_test_locked`.
9. Quant runs all 5 robustness tests successfully.
10. Scout visits `/stocks/SMCI` (assumed non-S&P-500) → backend returns 402 `market_pulse_ticker_out_of_scope` → frontend renders `<SoftPaywall />`.
11. Scout visits `/stocks/AAPL` → page loads normally.
12. All 402 responses include `upgrade_url` field for deep-linking.
13. `<UpgradeModal />` renders for each Stage 3 code with the correct copy + CTA action.
14. `<QuotaBadge />` shows `3/5 runs · resets Monday` for a Scout with 3 custom runs used (already shipped in Stage 1a; regression test only).
15. **Shadow mode:** with `GATING_ENABLED=false`, a Scout's 6th custom backtest succeeds AND produces a structured log line `gate_event code=runs_exhausted tier=scout user_id=... shadow=true`.
16. **Enforcement mode:** with `GATING_ENABLED=true`, the same request returns 402.

---

## 9. Test plan

### Backend unit tests

`apps/api/tests/test_gating_backtest.py`:
- `test_scout_5_custom_runs_succeed`
- `test_scout_6th_custom_run_returns_402`
- `test_scout_template_runs_dont_decrement_custom_quota` (the central Stage 1a invariant, retested at the route level)
- `test_strategist_unlimited_custom_runs`
- `test_universe_6_custom_returns_402`
- `test_universe_25_custom_for_strategist_succeeds`
- `test_universe_100_template_for_scout_succeeds`
- `test_history_6yr_custom_returns_402_for_scout`
- `test_history_20yr_template_for_scout_succeeds`

`apps/api/tests/test_gating_robustness.py`:
- `test_strategist_param_sensitivity_succeeds`
- `test_strategist_benchmark_succeeds`
- `test_strategist_sub_period_returns_402`
- `test_strategist_peer_ticker_returns_402`
- `test_quant_all_tests_succeed`

`apps/api/tests/test_gating_market_pulse.py`:
- `test_scout_sp500_ticker_succeeds`
- `test_scout_non_sp500_returns_402`
- `test_strategist_any_ticker_succeeds`

`apps/api/tests/test_gating_shadow_mode.py`:
- `test_shadow_mode_logs_event_and_allows_request` (monkey-patch `GATING_ENABLED=false`)
- `test_enforcement_mode_returns_402`

### Frontend tests

Manual smoke (Playwright deferred to Stage 6):
- Scout signup → run 5 custom backtests → 6th shows `<UpgradeModal />` → click "Start free trial" → trial active → 6th run succeeds.
- Visit `/stocks/SMCI` as Scout → `<SoftPaywall />` renders → click "Upgrade to Strategist" → land on `/pricing?gate=market_pulse_ticker_out_of_scope&from=scout`.

---

## 10. Edge cases

- **Trialing user.** `ent.tier = "strategist"` while trial is active. Passes Strategist gates. After trial expiry, the dunning job reverts plan to Scout; they hit weekly caps immediately. Existing saved strategies are NOT retroactively blocked.
- **`past_due` users.** Keep entitlements (no degradation) until the Stage 2 dunning expiry (7 days), then revert to Scout.
- **Race during plan upgrade.** Webhook arrives mid-request. The user's `ent` is computed once at request start; one in-flight request may complete at the old tier. Acceptable.
- **Race on the weekly counter.** `get_or_create_current_weekly_usage` handles the first-insert race via `IntegrityError → re-fetch`. Subsequent increments are unconditional (no `SELECT ... FOR UPDATE` — accept off-by-one in extreme concurrency).
- **Week boundary.** Scout running their 5th backtest at 23:59:00 UTC Sunday and 6th at 00:01:00 UTC Monday: 5th counts in week N, 6th in week N+1 (fresh row). Quota does not roll over. Documented in `<QuotaBadge />` copy ("resets Monday").
- **Time-zone confusion.** UTC Monday is non-obvious for non-UTC users. Acceptable for v1; Year 2 can add user-locale rollover.
- **Anonymous → signup mid-page.** Two tabs: tab 1 anonymous run in progress, tab 2 just completed signup. The anonymous endpoint also accepts authenticated requests (just routes to the regular handler). No special handling.
- **Body re-read race.** If `require_entitlement` reads the body and the route handler reads it again, FastAPI's underlying stream is exhausted. Mitigated by `request.state._cached_body` (see §4).
- **402 vs 401 vs 403.** Use 402 for "would work if you paid more." Use 401 only for missing/invalid auth. Use 403 only for revoked accounts.
- **Pre-flight warning consistency.** If the frontend pre-flight (universe size warning) says "you'll need to upgrade" but the user clicks Run anyway, the 402 envelope copy must match the warning copy. Test once before launch.

---

## 11. Files to create / modify

### Backend (create)

- `apps/api/app/api/deps_entitlement.py` — `require_entitlement` dependency.
- `apps/api/app/data/sp500_tickers.py` — `SP500_TICKERS: frozenset[str]`.
- `apps/api/tests/test_gating_backtest.py`
- `apps/api/tests/test_gating_robustness.py`
- `apps/api/tests/test_gating_market_pulse.py`
- `apps/api/tests/test_gating_shadow_mode.py`

### Backend (modify)

- `apps/api/app/core/config.py` — add `gating_enabled: bool = False` setting.
- `apps/api/app/schemas/backtest.py` — extend `BacktestRunRequest` with `template_id: Optional[str] = None`.
- `apps/api/app/api/routes/backtest.py` — wire `require_entitlement` + inline universe/history checks + increment_*_backtest call.
- `apps/api/app/api/routes/robustness.py` — wire `require_entitlement(robustness_tests_field="tests")` + increment.
- Market Pulse route file(s) (`company_overview.py`, `market_data.py`, `screener.py` — audit required) — wire `require_entitlement(market_pulse_ticker_field="symbol")` per route.

### Frontend (create)

- `apps/web/src/components/UpgradeModal.tsx`
- `apps/web/src/components/SoftPaywall.tsx`
- `apps/web/src/lib/withUpgradeHandling.ts`
- `apps/web/src/lib/upgrade-modal-event-bus.ts`

### Frontend (modify)

- `apps/web/src/lib/api.ts` — wrap `fetchApi` with 402 interceptor.
- `apps/web/src/app/layout.tsx` (or root) — mount `<UpgradeModal />` once at the root.
- `apps/web/src/app/stocks/[ticker]/page.tsx` — handle 402 with `<SoftPaywall />`.
- `apps/web/src/components/workspace/research-workspace.tsx` — pre-flight warnings + disable-Run-when-exhausted.
- `apps/web/src/components/strategy-builder/strategy-builder-modal.tsx` — variant of pre-flight in the chat builder.

### Files NOT touched (already in place from Stage 1a)

- `apps/api/app/api/entitlement_errors.py` — 402 envelope + `upgrade_error()` helper.
- `apps/api/app/services/entitlements.py` — TIER_CAPS + `increment_custom_backtest` + `increment_template_backtest`.
- `apps/api/app/services/saved_strategy_service.py` — `saved_strategies_quota_reached` already enforced.
- `apps/web/src/components/QuotaBadge.tsx` — already in nav.
- `apps/web/src/components/AnonymousCTA.tsx` — exists; Stage 3 wires it into pages.
- `apps/web/src/lib/useEntitlements.ts` — shape already correct.
- `apps/web/src/lib/contracts.ts` — `EntitlementErrorDetail` + `EntitlementErrorCode` already defined.

---

## 12. Migration & rollout

Stage 3 changes user-visible behavior. Roll out in phases:

1. **Day 1–3 (build):** All backend gating + frontend modal + shadow mode flag (default OFF). Deploy to production with `GATING_ENABLED=false` — every request still succeeds, every "would-be 402" emits a `gate_event` log line.
2. **Day 4 (observe):** Tail Railway logs / aggregate the structured `gate_event` lines. Validate:
   - The 5/week custom quota is realistic (look for distribution of `runs_exhausted` events).
   - Market Pulse out-of-scope rate (how often Scouts hit non-S&P-500 tickers — informs whether the cap is too tight).
   - Robustness test mix (which tests do Strategists use?).
3. **Day 5 (enforce):** Flip `GATING_ENABLED=true`. Frontend `<UpgradeModal />` was already deployed; now starts firing.
4. **Day 6–7 (monitor):** Watch conversion rate from upgrade modal CTAs. Watch support tickets. Watch error rates.

Rollback: flip `GATING_ENABLED=false`. No data state needs to be reset.

---

## 13. Removed sections

The following sections from the original Stage 3 spec were dropped:

- Section 5.4 (insights/sandbox tier-aware payload) — deferred.
- Section 5.5 (symbol search asset-class filter + `is_locked` flag) — deferred.
- Section 5.7 (supply-chain deep-dive gate) — deferred.
- Section 5.8 (Commodity Eval Framework gate) — deferred.
- Section 5.10 (API access / `/api/v1/*` / `ApiKey` model) — cut entirely.
- Section 6 (quarterly refresh script + admin endpoint) — replaced with static file; manual maintenance.
- Section 7.4 (trial banner countdown urgency) — kept the existing Stage 2 banner; defer copy refinement.
- Section 7.6 (symbol search locked-tickers UI) — deferred with the search filter.
- ZH localization for upgrade modal — EN only for v1.

If/when these are picked up, they get their own follow-up specs.

---

## 14. Open questions

- **Grandfathered pre-launch users.** Pre-launch users who were promised lifetime access — do we add a `legacy_grandfathered` boolean to `users`? Recommend: yes, with a manual SQL update for the known emails, gated by entitlements resolver returning effectively-Quant caps regardless of plan tier.
- **Pre-flight warning copy.** The warning text needs to match the 402 modal text. Draft both at the same time; review side-by-side.

---

## 15. Definition of done

- All acceptance criteria (§8) pass.
- All new tests (§9) + existing 358 tests pass.
- Postgres CI smoke test still green (no new schema, but route-level changes shouldn't break it).
- `GATING_ENABLED=false` deployed to production for at least 24 hours of shadow-mode observation.
- Structured `gate_event` log lines visible in Railway logs.
- `GATING_ENABLED=true` flipped; 402s firing; `<UpgradeModal />` rendering correctly.
- One pre-launch user (test account) has gone through the Scout → Strategist trial → paid flow end-to-end.
- Stage 4 can begin.
