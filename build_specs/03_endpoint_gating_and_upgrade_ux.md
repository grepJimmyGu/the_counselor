# Stage 3 — Endpoint Gating + Upgrade UX

**Depends on:** Stage 1 (entitlements + identity), Stage 2 (subscription status).
**Unblocks:** Revenue. After this stage ships, you can charge money.
**Estimated build:** 2 weeks (10 working days).
**Branch:** `stage-3-gating-upgrade-ux`

---

## 1. Context

Stages 1 and 2 set up identity, plan, and billing. The product still serves every feature to every user. Stage 3 actually enforces the tier proposal — applies gating to every metered endpoint and surfaces the friction as a friendly upgrade UX (not a 403 wall).

The tier matrix to enforce (from `Livermore_Tiered_GTM_Proposal.docx`):

| Lever | Scout (Free) | Strategist ($24) | Quant ($79) |
|---|---|---|---|
| Backtest runs / month | 5 runs | Unlimited | Unlimited |
| Custom strategy via chat | All 6 types (frequency-limited) | All 6 | All 6 + advanced |
| Universe size | 5 | 25 | 100 |
| Backtest history window | 5 yr | 10 yr | 20 yr |
| Asset classes | Equities | + Commodities | + A-shares |
| Robustness suite | — | 2 of 5 | All 5 + scheduled |
| Market Pulse — Health/Val | Top 250 US | All US | All US + alerts |
| Business Model + Market Position | Full | Full | Full + supply chain deep dive |
| Commodity Eval Framework | — | Yes | Yes |
| Saved strategies | 3 | 25 | Unlimited |
| API access | — | — | Yes |

**Design principle:** every gate fails with a structured 402 `Upgrade Required` response that the frontend renders as an inline upgrade card, not an error. The user always knows why they hit the wall and what tier unlocks it.

---

## 2. Scope

### In scope
- FastAPI dependency `require_entitlement` that gates endpoints
- Backtest run metering (increment counter; 402 when exhausted)
- Universe size validator
- History window enforcement (clamp or 402, depending on signal source)
- Asset class checks (equities-only Scouts cannot run a commodities or A-share strategy)
- Market Pulse top-250 whitelist for Scout
- Saved-strategy quota enforcement
- Robustness test gating
- API access gating (Quant-only endpoint group)
- Standardized `EntitlementError` response envelope
- Frontend `<UpgradeModal />` component
- Frontend `<QuotaBadge />` in nav (shows runs left)
- Frontend `<TrialBanner />` integration (extension of Stage 2's banner)
- Frontend `<SoftPaywall />` rendered on 402 responses
- Telemetry events for every paywall hit (will be consumed by Stage 6 PostHog instrumentation; stub today)

### Out of scope
- The PostHog feature-flag A/B test on which paywall variant performs best (Stage 6)
- Email lifecycle on paywall hits (Stage 6)
- Self-serve plan switching UI (handled via Stripe Portal — Stage 2)
- Custom strategy chat type whitelist (chat is open to all types per latest proposal revision; only frequency is metered)

---

## 3. Standardized error envelope

Define once, use everywhere. Add to `apps/api/app/schemas/entitlement_error.py`:

```python
from typing import Literal, Optional
from pydantic import BaseModel

class EntitlementErrorDetail(BaseModel):
    """Returned with HTTP 402 when a request would exceed the user's entitlements."""
    code: Literal[
        "runs_exhausted",
        "universe_too_large",
        "history_too_long",
        "asset_class_locked",
        "robustness_test_locked",
        "market_pulse_ticker_out_of_scope",
        "saved_strategies_quota_reached",
        "api_access_required",
        "commodity_framework_locked",
        "supply_chain_deep_dive_locked",
    ]
    current_tier: Literal["scout", "strategist", "quant"]
    required_tier: Literal["strategist", "quant"]
    current_value: Optional[str] = None  # e.g. "5/5 runs", "7 tickers", "8 yr"
    limit_value: Optional[str] = None  # e.g. "5", "5", "5 yr"
    upgrade_url: str  # frontend redirect target, e.g. "/pricing?gate=runs_exhausted&from=scout"
    cta_text: str  # e.g. "Upgrade to Strategist for unlimited runs"
    detail: str  # human-readable explanation


class EntitlementErrorResponse(BaseModel):
    error: Literal["upgrade_required"] = "upgrade_required"
    entitlement: EntitlementErrorDetail
```

Frontend reads `error === "upgrade_required"`, looks at `entitlement.code`, and renders the matching upgrade card with localized copy.

Server returns this with `status_code=402`.

---

## 4. The gating dependency

`apps/api/app/api/deps_entitlement.py`:

```python
from typing import Callable
from fastapi import Depends, HTTPException
from app.api.deps import get_current_user
from app.services.entitlements import get_entitlements, get_or_create_current_usage

def require_entitlement(
    *,
    needs_run_quota: bool = False,
    universe_field: str | None = None,
    history_field: str | None = None,
    asset_class_field: str | None = None,
    robustness_test_field: str | None = None,
    market_pulse_ticker_field: str | None = None,
    needs_api_access: bool = False,
):
    """
    Returns a FastAPI dependency that:
    1. Resolves entitlements for the current user.
    2. Validates the incoming request against those entitlements.
    3. Raises 402 with EntitlementErrorResponse if anything fails.
    4. Returns the (user, entitlements, usage) tuple to the route handler.
    """
    async def _dep(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        usage = get_or_create_current_usage(db, user.id)
        ent = get_entitlements(user, usage)
        body = await request.json() if request.method == "POST" else {}

        # check runs quota
        if needs_run_quota and ent.backtest_runs_remaining is not None:
            if ent.backtest_runs_remaining <= 0:
                raise upgrade_error("runs_exhausted", ent, f"{usage.backtest_runs}/{ent.backtest_runs_remaining + usage.backtest_runs}", str(ent.backtest_runs_remaining + usage.backtest_runs))

        # check universe
        if universe_field and body.get(universe_field):
            requested_size = len(body[universe_field])
            if requested_size > ent.universe_size_max:
                raise upgrade_error("universe_too_large", ent, str(requested_size), str(ent.universe_size_max))

        # check history window
        if history_field and body.get(history_field):
            # body[history_field] expected to be ISO date or dict with start/end
            requested_years = compute_requested_history_years(body[history_field], body.get("end_date"))
            if requested_years > ent.history_window_years:
                raise upgrade_error("history_too_long", ent, f"{requested_years:.1f} yr", f"{ent.history_window_years} yr")

        # check asset class
        if asset_class_field and body.get(asset_class_field):
            detected = detect_asset_classes(body[asset_class_field])
            disallowed = [a for a in detected if a not in ent.asset_classes]
            if disallowed:
                raise upgrade_error("asset_class_locked", ent, ",".join(disallowed), ",".join(ent.asset_classes))

        # check robustness test
        if robustness_test_field and body.get(robustness_test_field):
            test = body[robustness_test_field]
            if test not in ent.robustness_tests:
                raise upgrade_error("robustness_test_locked", ent, test, ",".join(ent.robustness_tests) or "—")

        # check market pulse
        if market_pulse_ticker_field:
            ticker = request.path_params.get(market_pulse_ticker_field)
            if ent.market_pulse_ticker_scope == "top_250" and ticker not in TOP_250_US_TICKERS:
                raise upgrade_error("market_pulse_ticker_out_of_scope", ent, ticker, "Top 250 US")

        # API access (gates the entire group of /api/v1/* endpoints)
        if needs_api_access and not ent.api_access:
            raise upgrade_error("api_access_required", ent)

        return user, ent, usage

    return _dep


def upgrade_error(code, ent, current_value=None, limit_value=None):
    """Build a 402 HTTPException with the standardized envelope."""
    required = "quant" if code in ("api_access_required", "robustness_test_locked", "asset_class_locked" and "a_shares" in (current_value or ""), "commodity_framework_locked", "supply_chain_deep_dive_locked", "market_pulse_ticker_out_of_scope") else "strategist"
    cta_map = {
        "runs_exhausted": "Upgrade to Strategist for unlimited runs",
        "universe_too_large": "Upgrade to test up to 25 tickers",
        "history_too_long": "Upgrade to backtest with 10 years of data",
        "asset_class_locked": "Upgrade to unlock commodities and A-shares",
        "robustness_test_locked": "Upgrade to Quant for the full robustness suite",
        "market_pulse_ticker_out_of_scope": "Upgrade to research all US stocks",
        "saved_strategies_quota_reached": "Upgrade to save more strategies",
        "api_access_required": "Upgrade to Quant for API access",
        "commodity_framework_locked": "Upgrade to unlock commodity evaluation",
        "supply_chain_deep_dive_locked": "Upgrade to Quant for supply chain deep dive",
    }
    detail = EntitlementErrorDetail(
        code=code,
        current_tier=ent.tier,
        required_tier=required,
        current_value=current_value,
        limit_value=limit_value,
        upgrade_url=f"/pricing?gate={code}&from={ent.tier}",
        cta_text=cta_map[code],
        detail=cta_map[code],
    )
    raise HTTPException(status_code=402, detail=EntitlementErrorResponse(entitlement=detail).model_dump())
```

---

## 5. Endpoint-by-endpoint gating

### 5.1 `POST /api/backtest/run`

**Gates:**
- Run quota
- Universe size (field `universe`)
- History window (`start_date` vs `end_date`)
- Asset class (commodities tickers in universe ⇒ asset_class includes `commodities`; A-share tickers ⇒ `a_shares`)

**Wiring:**

```python
@router.post("/run", response_model=BacktestResult)
def run_backtest(
    req: BacktestRunRequest,
    auth = Depends(require_entitlement(
        needs_run_quota=True,
        universe_field="universe",
        history_field="start_date",
        asset_class_field="universe",
    )),
    db = Depends(get_db),
):
    user, ent, usage = auth
    result = backtest_service.run(req, user_id=user.id)
    increment_backtest_runs(db, user.id)
    return result
```

Asset-class detection: reuse `COMMODITY_TICKERS` set from `strategy_parser.py`. A-share detection: any ticker with suffix `.SHH` or `.SHZ`.

### 5.2 `POST /api/chat/strategy`

**Gates:** chat is **not** rate-limited per request, but every chat that leads to a backtest will count via the backtest endpoint. So this endpoint stays open for all tiers. No gating here.

Optional soft signal: include `entitlements_snapshot` in the response so the chat UI can show "you have 3 of 5 runs left" before the user clicks Run.

### 5.3 `POST /api/robustness/run`

**Gates:**
- Run quota (counts against same monthly budget — 1 robustness suite = 1 run for accounting; reconsider if quant users hit this)
- Robustness test name (`tests` array — each test name must be in `ent.robustness_tests`)

Wiring:

```python
@router.post("/run")
def run_robustness(
    req: RobustnessRunRequest,
    auth = Depends(require_entitlement(needs_run_quota=True)),
    ...
):
    user, ent, _ = auth
    # validate each requested test is in the user's allowed set
    for test in req.tests:
        if test not in ent.robustness_tests:
            raise upgrade_error("robustness_test_locked", ent, test, ",".join(ent.robustness_tests) or "—")
    return robustness_service.start_job(req, user_id=user.id)
```

### 5.4 `GET /api/insights/explain` and `POST /api/review/sandbox`

**Gates:** none (insight features are open to all tiers per the latest proposal revision).

But **for Quant only**: include extra fields in sandbox review (`required_next_tests`, `suggested_next_experiments`) that the LLM prompt populates. Strategist gets the basic shape. Scout gets the basic shape. This is a soft differentiation, not a hard gate.

### 5.5 `GET /api/symbols/search?query=`

**Gates:** asset class filter.

- Scout: only return symbols whose asset class is in `["equities"]` AND whose ticker is in the Top-250 US universe. (Frontend can show full search but backend filters server-side.)
- Strategist: equities + commodities.
- Quant: equities + commodities + A-shares.

Add query param `include_locked=true` for Scout to see locked tickers (e.g., A-share suggestions in autocomplete) with an `is_locked: true` flag so the UI can render them with an upgrade tooltip rather than hiding them entirely.

### 5.6 `GET /api/company/{symbol}/trend` and Market Pulse routes

**Gates:** market_pulse_ticker_field=`symbol`.

- Scout: 402 if `symbol not in TOP_250_US_TICKERS`.
- Strategist + Quant: open.

### 5.7 Supply chain deep dive (`/api/company/{symbol}/market-position?include_deep_chain=true`)

**Gates:** Quant only.

Param `include_deep_chain` → if true and `ent.business_model_section != "full_plus_supply_chain"`, return 402 with `code="supply_chain_deep_dive_locked"`.

### 5.8 Commodity Evaluation Framework (`/api/commodities/{commodity}/trend` and dashboard endpoints)

**Gates:** Strategist+ only.

- Scout: 402 with `code="commodity_framework_locked"`.

### 5.9 Saved strategies

If you add a `/api/strategies/save` endpoint (recommended this stage), enforce `saved_strategies_max`:

```
POST /api/strategies/save
  Validates count(saved_strategies WHERE user_id=...) < ent.saved_strategies_max
  402 with code="saved_strategies_quota_reached" if exceeded
```

### 5.10 API access — `/api/v1/*` namespace

Mount the public API under `/api/v1/`. Every route in this namespace requires `needs_api_access=True`. Add the namespace to the FastAPI app with a dedicated APIRouter and apply `Depends(require_entitlement(needs_api_access=True))` at the router level.

Add an API key model:

```python
class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256 of the key
    name: Mapped[str] = mapped_column(String(80), default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

API key auth dependency reads `Authorization: Bearer <key>`, hashes, looks up. Rate-limit: 10K calls/month (`monthly_usage.api_calls`, new column added in this stage).

---

## 6. Top-250 US tickers list

Maintain `apps/api/app/data/top_250_us_tickers.py` — a Python set of 250 tickers. Source: S&P 500 top 250 by market cap (as of last update). Refresh quarterly via admin endpoint.

```python
TOP_250_US_TICKERS = {
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", ...
}
```

Provide `apps/api/scripts/refresh_top_250.py` that pulls from FMP `/stable/sp500` and writes to the file (or to a DB table — file is simpler and version-controlled).

---

## 7. Frontend

### 7.1 `<UpgradeModal />` component

`apps/web/src/components/UpgradeModal.tsx`:

- Triggered when `useApiCall` receives a 402 with `error="upgrade_required"`.
- Modal content driven by `entitlement.code`:

```typescript
const COPY: Record<string, ModalCopy> = {
  runs_exhausted: {
    title: "You've used all 5 backtests this month",
    body: "Strategist gives you unlimited runs, 10-year backtest history, and access to commodities. Start 14 days free — no card required.",
    primary_cta: "Start free trial",
    secondary_cta: "See all plans",
  },
  universe_too_large: {
    title: "Scout supports up to 5 tickers per strategy",
    body: "Strategist lets you test up to 25 tickers, perfect for rotation and basket strategies.",
    primary_cta: "Upgrade to Strategist",
    secondary_cta: "Cancel",
  },
  history_too_long: {
    title: "Scout backtests up to 5 years",
    body: "Strategist gives you 10 years of history — enough to test through 2015-16 volatility and the 2020 crash.",
    primary_cta: "Upgrade to Strategist",
    secondary_cta: "Use 5 years instead",
  },
  asset_class_locked: {
    title: "Commodities are a Strategist feature",
    body: "Strategist unlocks the Commodity Evaluation Framework and lets you backtest GLD, USO, COPX, and more.",
    primary_cta: "Upgrade to Strategist",
    secondary_cta: "Cancel",
  },
  robustness_test_locked: {
    title: "Full robustness suite is a Quant feature",
    body: "Quant gives you all 5 robustness tests — parameter sensitivity, sub-period, transaction cost, benchmark comparison, peer ticker — plus scheduled monthly re-runs.",
    primary_cta: "Upgrade to Quant",
    secondary_cta: "Cancel",
  },
  // ... etc
};
```

Localize for ZH via i18n.

### 7.2 `<QuotaBadge />` in nav

Top-right of nav for authenticated Scout users:

```
[ 3 / 5 runs · 12 days left in May ]   (clickable → /pricing)
```

For Strategist/Quant: hidden.

Reads from `useEntitlements()` hook (existing from Stage 1).

### 7.3 `<SoftPaywall />` inline cards

When a feature is gated but the user is still on the page (e.g., trying to load supply chain section as a Strategist), render an inline card instead of crashing the page:

```
┌────────────────────────────────────────┐
│  🔒 Supply chain deep dive             │
│                                        │
│  See AAPL's full upstream + downstream │
│  network with revenue concentration.   │
│                                        │
│  [ Upgrade to Quant — $79/mo ]         │
└────────────────────────────────────────┘
```

Component: `apps/web/src/components/SoftPaywall.tsx`. Used in market-position-section, robustness panel, commodity framework, etc.

### 7.4 Trial banner refinement

Extend Stage 2's banner with countdown urgency:

- Days 1–7: "Your 14-day Strategist trial — explore freely. Add a card anytime."
- Days 8–12: "Trial ends in X days. Add a card to keep unlimited runs."
- Day 13: "Trial ends tomorrow. Add a card or you'll revert to Scout (5 runs/month)."
- Day 14 expired: "Trial ended. You're on Scout. Add a card to restore Strategist."

### 7.5 Soft signals in chat UI

The chat builder (in `research-workspace.tsx`) should:

- Show remaining runs inline above the Run button: `3 of 5 runs left this month`
- If 0 left and user is Scout, the Run button is disabled with a tooltip "You've used your monthly runs. Upgrade to continue."
- If the parsed strategy's universe or history exceeds Scout caps, show inline yellow warning before user clicks Run (avoid 402 surprise).

### 7.6 Soft signals on Search

Symbol search shows locked tickers with a lock icon if outside the user's asset_classes set or outside their Market Pulse scope. Clicking a locked ticker opens UpgradeModal.

### 7.7 New API client methods

Add to `src/lib/api.ts`:

- Wrap all existing methods with a `withUpgradeHandling()` helper that catches 402 and dispatches a UpgradeModal event.
- Add `saveStrategy(strategy)`, `listSavedStrategies()`, `deleteSavedStrategy(id)`.
- Add `createApiKey({name})`, `listApiKeys()`, `revokeApiKey(id)` for Quant users.

---

## 8. Acceptance criteria

1. **Scout cannot run 6th backtest in a month** — 6th `POST /api/backtest/run` returns 402 with `code='runs_exhausted'`.
2. **Scout cannot run a 6-ticker universe** — universe of length 6 returns 402 `universe_too_large`.
3. **Scout cannot run with 7 years of history** — `start_date = today-7yr` returns 402 `history_too_long`.
4. **Scout cannot search A-share tickers without upgrade hint** — search for `600519` shows result with `is_locked: true`.
5. **Scout 402 on commodity backtest** — universe `["GLD"]` returns 402 `asset_class_locked`.
6. **Scout sees 402 on Market Pulse for non-top-250 ticker** — visit `/stocks/SMCI` (assume not in top 250) — backend returns 402, frontend renders SoftPaywall.
7. **Scout sees 402 on Commodity Eval** — `/commodities/gold` returns 402 `commodity_framework_locked`.
8. **Strategist runs ALL 6 strategy types and unlimited runs** — 10 backtests in a row all succeed.
9. **Strategist 402 on 3rd robustness test type** — request `sub_period` test returns 402 `robustness_test_locked`.
10. **Quant runs all 5 robustness tests** — succeeds.
11. **Quant can create API key** — `POST /api/me/api-keys` returns a key; subsequent `Authorization: Bearer <key>` calls to `/api/v1/*` succeed.
12. **Strategist cannot create API key** — `POST /api/me/api-keys` returns 402 `api_access_required`.
13. **Saved-strategies quota** — Scout cannot save a 4th strategy.
14. **All 402 responses include `upgrade_url` field** — frontend can deep-link to `/pricing?gate=...&from=...`.
15. **Frontend UpgradeModal renders correctly** for each of the 10 codes.
16. **Frontend QuotaBadge shows correct count** for Scout user with 3 runs used.
17. **Existing anonymous backtest behavior is gone** — anonymous requests get 401 `authentication_required` on metered endpoints. Welcome flow now requires signup.

---

## 9. Test plan

### Unit tests

`apps/api/tests/test_gating_backtest.py`:
- `test_scout_5th_run_succeeds`
- `test_scout_6th_run_returns_402_runs_exhausted`
- `test_strategist_unlimited_runs`
- `test_universe_6_returns_402`
- `test_history_window_7yr_returns_402`
- `test_commodity_ticker_returns_402_for_scout`
- `test_a_share_ticker_returns_402_for_strategist`
- `test_quant_can_use_a_shares`

`apps/api/tests/test_gating_robustness.py`:
- `test_strategist_param_sensitivity_succeeds`
- `test_strategist_sub_period_returns_402`
- `test_quant_all_tests_succeed`

`apps/api/tests/test_gating_market_pulse.py`:
- `test_scout_top_250_ticker_succeeds`
- `test_scout_non_top_250_returns_402`

`apps/api/tests/test_api_keys.py`:
- `test_strategist_cannot_create_key`
- `test_quant_create_and_use_key`
- `test_revoked_key_returns_401`
- `test_api_call_increments_counter`
- `test_api_call_over_quota_returns_429`

### Integration tests

E2E: Scout signup → run 5 backtests → 6th hits paywall → starts trial → 6th now succeeds.

### Frontend tests

Playwright `apps/web/tests/e2e/gating.spec.ts`:
- Scout user → run 5 backtests → 6th shows UpgradeModal with correct copy → click "Start free trial" → land in trial → run succeeds
- Visit `/stocks/SMCI` as Scout → see SoftPaywall, click → land on `/pricing?gate=market_pulse_ticker_out_of_scope`

---

## 10. Edge cases & error handling

- **Existing legacy-anon users** — Stage 1 created `legacy-anon-0000`. This user is on Scout. Old anonymous flows now require signup; we **do not** preserve guest experience. The flagship template gallery `/templates` remains anonymous-browse but clicking Run forces signup. (Justification: from the proposal, the Scout free experience is generous; signup is a one-screen form. Friction is acceptable.)
- **Race on increment** — `increment_backtest_runs` uses a single transaction with `SELECT ... FOR UPDATE`. Two concurrent backtests cannot both succeed if quota is 1.
- **Trial user on Scout endpoints** — trialing user's `ent.tier='strategist'`, so they pass Strategist gates. After trial expires, they revert; we do not retroactively block their saved strategies, but they cannot run new backtests beyond 5/month.
- **Past_due grace period** — past_due users keep their entitlements (no degradation) for 7 days; after dunning expiry job (Stage 2), they revert to Scout.
- **Race during plan upgrade** — webhook arrives after user starts a request. The user's `ent` is computed at request start; they may complete one request at the old tier. Acceptable.
- **Top-250 list staleness** — quarterly refresh. Add admin route `POST /api/admin/refresh-top-250` (auth: admin only).
- **403 vs 402** — use 402 strictly for "would work if you paid more"; use 401 for auth, 403 only for revoked accounts.
- **API key abuse** — rate limit 10K/month is monthly; also add per-minute cap (e.g., 60/min) via slowapi or in-process token bucket.
- **`needs_clarification` from chat parser** — not a gate. Still returns 200. Don't conflate.
- **Iteration counter on sandbox review** — already implemented; persist per user (use `user.id` instead of session var) so a Scout can't reset by clearing cookies.

---

## 11. Files to create / modify

**Backend (create):**
- `apps/api/app/schemas/entitlement_error.py`
- `apps/api/app/api/deps_entitlement.py`
- `apps/api/app/api/routes/api_keys.py`
- `apps/api/app/api/routes/v1/__init__.py` — public API namespace
- `apps/api/app/models/api_key.py`
- `apps/api/app/data/top_250_us_tickers.py`
- `apps/api/scripts/refresh_top_250.py`
- Tests as listed

**Backend (modify):**
- `apps/api/app/api/routes/backtest.py` — wire `require_entitlement(...)`
- `apps/api/app/api/routes/robustness.py` — wire gating
- `apps/api/app/api/routes/symbols.py` — filter by asset class
- `apps/api/app/api/routes/company.py` (or wherever Market Pulse lives) — top-250 check
- `apps/api/app/api/routes/commodities.py` — Strategist+ gate
- `apps/api/app/api/routes/me.py` — add API key CRUD
- `apps/api/app/services/insights.py` — add tier-aware sandbox review payload shape
- `apps/api/app/main.py` — register v1 namespace

**Frontend (create):**
- `apps/web/src/components/UpgradeModal.tsx`
- `apps/web/src/components/SoftPaywall.tsx`
- `apps/web/src/components/QuotaBadge.tsx`
- `apps/web/src/components/UpgradeBanner.tsx` (extends TrialBanner)
- `apps/web/src/lib/withUpgradeHandling.ts` — 402 interceptor
- `apps/web/src/lib/upgrade-modal-event-bus.ts` — global event for modal dispatch

**Frontend (modify):**
- `apps/web/src/lib/api.ts` — wrap all calls with upgrade handling
- `apps/web/src/lib/contracts.ts` — add `EntitlementError` type
- `apps/web/src/lib/i18n.ts` — 30+ new strings for upgrade copy in EN + ZH
- `apps/web/src/components/research-workspace.tsx` — show quota + soft warnings
- `apps/web/src/app/stocks/[ticker]/page.tsx` — handle 402 with SoftPaywall
- `apps/web/src/app/commodities/[symbol]/page.tsx` — handle 402
- `apps/web/src/components/_market-position-section.tsx` — supply chain locked SoftPaywall for non-Quant

---

## 12. Migration & rollout

This stage **changes user-visible behavior**. Roll out carefully:

1. **Week 1 (build):** Implement backend gating + frontend UpgradeModal. Deploy to staging. Have one tester run the full flow.
2. **Week 2 (shadow mode):** Deploy backend to prod with gating **logged but not enforced**. Frontend deployed without UpgradeModal hookup. Observe in PostHog: how many requests would have been blocked? Use this data to validate the 5-run quota.
3. **Week 2 day 5 (enforce):** Flip a feature flag (`gating_enabled=true`) to enable hard 402 responses. Frontend UpgradeModal goes live.
4. **Monitor for 48h:** watch conversion rates, support tickets, error rates.

Feature flag implementation: read `GATING_ENABLED` env var (`true`/`false`). Stage 6 will replace this with a PostHog flag for finer control.

---

## 13. Open questions (must resolve before flip)

- **Promo / waiver path for existing power users** — Some pre-launch users were promised lifetime access. Add a `legacy_grandfathered` flag in `users` table — Stage 1 PRD did not include this; consider adding here. Recommend: scan the existing anonymous backtest log, identify top 20 active emails (from past chat sessions), email them with a 6-month free Strategist promo.
- **A-share search behavior** — Recommended: search returns A-share results to Scout users with `is_locked: true`. Confirm.
- **Iteration counter persistence** — Recommended: persist per user. Confirm.
- **API rate limit per minute** — Recommended: 60/min. Confirm.

---

## 14. Definition of done

- All acceptance criteria pass.
- All new + existing tests pass.
- Shadow-mode telemetry shows expected paywall distribution (≥60% of paywall hits are `runs_exhausted` per the H1 hypothesis).
- Staging end-to-end smoke pass.
- Production rollout completed with `GATING_ENABLED=true`.
- Documentation: every endpoint that gates lists its gates in its docstring.
- Stage 4 can begin.
