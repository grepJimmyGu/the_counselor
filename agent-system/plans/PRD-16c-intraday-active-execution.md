# PRD-16c: Intraday Data + Active Live Monitoring + Multi-Tier Exits

**Status**: Ready to build (once PRD-19, PRD-16a, and PRD-16b are on `main`)
**Phase**: Custom Mode active execution
**Depends on**:
- **PRD-19** (notifications) — HARD. Consumes `NotificationThrottle`, `ChannelDispatcher`, `EmailDispatcher`, `InAppDispatcher`, `<NotificationBanner>`, `<NotInvestmentAdviceFooter>`, settings form scaffold.
- **PRD-16a** (signal catalog) — HARD. Active strategies use signal primitives; intraday extends the catalog with sub-daily-resolution entries.
- **PRD-16b** (composer) — HARD. Active strategies are composed via the same composer; this PRD adds the "Active execution" toggle in the WHEN OUT block.
- **Soft** PRD-20 — coordinates settings-form extensions to avoid merge conflicts.

**Blocks**: nothing immediate. Future PRD could add curated themes catalog as the user wanted; that's outside this PRD's scope.

**Effort**: ~3 weeks, single owner (or 2 owners working backend/frontend in parallel)
**Owner**: TBD
**Source spec**:
- [`/Quant Strategy/framework/livermore_product_flow_v2.html`](../../Quant%20Strategy/framework/livermore_product_flow_v2.html) — §2 Mode 4
- SpaceX strategy reference (chat 2026-06-08): multi-tier exits, intraday monitoring loop, dashboard pattern
- [`/Quant Strategy/framework/livermore_notification_framework.html`](../../Quant%20Strategy/framework/livermore_notification_framework.html) — extends Trigger 1 (signal change) with intraday position-event triggers

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md
first (auto-loaded). Then read agent-system/plans/HANDOFF-livermore-product-flow-v2.md
AND agent-system/plans/HANDOFF-livermore-notifications.md (both apply).

Goal: ship intraday active execution for Custom Mode. Five deliverables:

  1. Intraday data source (IntradayBarService — Alpha Vantage 1/5/15/30/60-min
     endpoints + caching). Extends existing live_quote_service.

  2. Engine support for sub-daily bars — same BacktestEngine accepts a
     `bar_resolution` parameter; existing 22 strategy_types work unchanged on
     either resolution.

  3. Multi-tier exit ladder schema: stop + TP1 partial + TP2 full. Schema +
     engine + composer UI.

  4. Intraday monitor cron job (IntradayPositionMonitorJob — separate from
     PRD-19's EOD cron). Fires position-event notifications (stop_hit,
     tp1_hit, tp2_hit) via PRD-19's dispatcher.

  5. Live dashboard on strategy detail page (Universe Watch, Position
     Cards, Trade Log). Renders only for strategies with active execution.

PREREQUISITES (must be on main):
  - PRD-19: notification dispatcher + throttle + banner + settings form + email scaffold
  - PRD-16a: signal catalog (extended in this PRD with intraday-resolution entries)
  - PRD-16b: composer UI + multi-rule engine fold
  - existing live_quote_service (30s in-process cache)

OUT OF SCOPE for this PRD:
  - Curated thematic universe / themes catalog — separate future PRD
  - Catalyst date awareness / deadline exits — per user 2026-06-08 decision
  - Auto-execution / broker integration — never; signal-only platform
  - SMS or webhook channels for intraday alerts — PRD-21
  - Real-time (sub-1-minute) cadence — start at 5-min minimum
  - User-supplied Python custom signals — far-future Pro feature

Context to read in order:
  - SpaceX strategy reference: chat 2026-06-08 (the design inspiration)
  - /Quant Strategy/framework/livermore_product_flow_v2.html §2 Mode 4
  - /Quant Strategy/framework/livermore_notification_framework.html §2 Trigger 1
  - agent-system/plans/PRD-19-phase-b-reshape.md (the foundation you extend)
  - apps/api/app/services/live_quote_service.py (existing 30s cache pattern)
  - apps/api/app/services/backtester/engine.py (where bar_resolution lands)

Architecture rules (the four principles, see HANDOFF §2):
  1. Reuse — PRD-19 throttle + dispatcher + banner are foundation. Don't fork.
  2. LEGO bricks — IntradayBarService and PositionState are bricks future
     workstreams will plug into (e.g. curated themes will compose them).
  3. FlowDefinition — Active toggle lives in composer (PRD-16b's flow);
     dashboard is a content surface on strategy detail page, not a flow.
  4. UX rules — useFlowCopy('active_exec', key); skeleton on live data;
     optimistic UI for position-event acknowledgment.

Acceptance: see "Acceptance Checklist" at the bottom. Branch as
`<your-agent-name>/feat/intraday-active-execution`. Open one PR; base=main.
```

---

## Design Constraints (the four principles)

Restated for the agent.

### 1. Reuse, don't replicate

PRD-19 built the foundation. PRD-16c consumes:

- `NotificationThrottle` — extends with new trigger types (`stop_hit`, `tp1_hit`, `tp2_hit`) under existing per-strategy + per-user caps.
- `ChannelDispatcher` + `EmailDispatcher` + `InAppDispatcher` — used unchanged. Just new `Notification` payloads.
- `<NotificationBanner>` — renders new position-event entries.
- `<NotInvestmentAdviceFooter>` — used in new email templates.
- `<NotificationSettingsForm>` — extended (NOT forked) with intraday section.
- Existing Jinja2 email-template scaffold — followed for new templates.
- Existing `live_quote_service` (30s in-process cache) — extends, not forks.
- Existing `BacktestEngine` — gets a `bar_resolution` parameter; same engine, same strategy_types, different data shape.
- Existing PRD-16a `SignalCatalogBrowser` and `SignalPrimitive` model — extended (not forked) with intraday-resolution entries.
- Existing PRD-16b composer flow — gets a new "Active execution" toggle in the WHEN OUT block; same flow, new option.

The genuinely novel work is: intraday data fetching service, multi-tier exit schema + engine + UI, intraday monitor cron loop, per-position state machine, live dashboard components, 3 new trigger types + email templates.

### 2. LEGO bricks

This PRD ships infrastructure that future workstreams will compose:

- `IntradayBarService` — any future feature needing sub-daily data uses this (curated themes, regime detection v2, future paper-trading).
- `PositionState` table — any future feature tracking per-position holdings uses this.
- Multi-tier exit ladder schema — generalizable to any strategy_type, not just Active Custom.
- Live dashboard bricks (`<UniverseWatchPanel>`, `<PositionCardsGrid>`, `<TradeLogTable>`) — reusable on any strategy detail surface.

### 3. FlowDefinition (where applicable)

Active execution is **not** a new mode flow. It's a toggle inside the existing `custom_build_mode` flow (PRD-16b's `WhenOutBlock` is the right home for the toggle). Backtest with intraday data is a parameter on the existing run, not a separate flow.

The live dashboard is a content surface on the strategy detail page, not a flow.

### 4. UX consistency + sub-300ms perceived load

- **Centralized labels** via `useFlowCopy('active_exec', key)`.
- **Live dashboard skeleton** while initial state loads.
- **Optimistic UI** for "Mark as executed" on position events.
- **No infinite polling** — dashboard subscribes to a SSE or polls every 30s; throttled enough not to crush the API.
- **Quiet hours respected** — intraday email notifications honor user's quiet hours from PRD-20 prefs.

---

## Problem

The user's SpaceX example demonstrates what Custom Mode users want once they've graduated past EOD strategies: intraday monitoring with multi-tier exits and a live dashboard. Today's Livermore can backtest a SpaceX-style strategy on daily bars; it cannot:

1. **Run with intraday data** — the engine only accepts EOD bars.
2. **Express multi-tier exits** — `RiskManagement` has a single `stop_loss_pct` + single `take_profit_pct`. A user wanting "−10% stop, +15% partial out 1/3, +30% full exit" cannot express it.
3. **Monitor live positions** — the EOD cron from PRD-19 detects signal changes, not per-position stop/TP triggers.
4. **Show a live dashboard** — strategy detail page shows backtest results, not current open positions.

This PRD ships all four capabilities for users who explicitly opt their strategy into Active execution.

**Explicit non-vision** (per user 2026-06-08): catalyst dates / deadline exits, NLP universe curation, intraday-specific tier-gating. Those are out of scope. This PRD enables the four capabilities above; product positioning of "active vs passive execution" is a label, not a separate mode.

## Goals

1. **`IntradayBarService`** fetches and caches 1/5/15/30/60-minute bars from Alpha Vantage.
2. **`BacktestEngine`** accepts a `bar_resolution` parameter; works on intraday bars without changes to the existing 22 strategy_types.
3. **`RiskManagement` extended with `exit_ladder`** — list of `ExitTier(trigger_pct, action, fraction)` entries.
4. **`PositionState` table** tracks per-position entry, shares, shares_remaining, trade_log.
5. **`IntradayPositionMonitorJob`** cron runs every 5 minutes during market hours; fires `stop_hit` / `tp1_hit` / `tp2_hit` via PRD-19 dispatcher.
6. **3 new email templates**: `position_stop.html`, `position_tp1.html`, `position_tp2.html`.
7. **3 new throttle trigger types**: `stop_hit`, `tp1_hit`, `tp2_hit` (per-position, not per-strategy throttling — different cap profile).
8. **Live dashboard** on strategy detail page: `<UniverseWatchPanel>`, `<PositionCardsGrid>`, `<TradeLogTable>`. Renders for active-execution strategies only.
9. **Composer integration**: a single "Active execution" toggle in the WHEN OUT block of the composer flow.
10. **Settings extension**: `<NotificationSettingsForm>` gets intraday-prefs section.

## Non-Goals

- **No curated thematic universe** — separate future PRD.
- **No catalyst date / deadline exits** — explicitly out per user 2026-06-08.
- **No NLP universe curation** — explicitly out.
- **No broker integration / auto-execution** — never; signal-only.
- **No SMS / webhook channels** — PRD-21.
- **No real-time (< 5 min) cadence** — 5-min minimum to manage API + cost.
- **No paper trading integration** — out of scope.
- **No user-supplied Python signals** — far-future Pro feature.
- **No backtest with bar resolutions finer than 5-min** — Alpha Vantage's 1-min endpoint is rate-limited too aggressively; not worth the complexity for v1.
- **No "what would have happened if" replay** of historical intraday events — future polish.

## User stories

1. **As a prosumer building a custom mean-reversion strategy on intraday bars**, I want to backtest with 15-min bars to see how the strategy behaves intraday — not just at EOD.
2. **As any active-execution user**, I want to define a multi-tier exit: −10% stop, +15% partial 1/3 out, +30% full out — without writing code.
3. **As any active-execution user**, when my position hits TP1, I want an email and an in-app banner within 5 minutes — same channel mix as EOD signal changes.
4. **As any active-execution user**, when I open the strategy detail page, I want a live dashboard showing current positions with distance to stop/TP1/TP2, the universe watch, and my trade log — not just backtest results.
5. **As any user with active strategies during quiet hours**, I want intraday alerts to respect my quiet-hours setting from PRD-20 — push waits until 7am, email still arrives.
6. **As a returning user**, I want the dashboard to load quickly (< 1s perceived) and refresh data without a full page reload.

---

## Architecture overview

```
┌────────────────────────────────────────────────────────────────────────┐
│  INTRADAY DATA LAYER                                                   │
│   apps/api/app/services/intraday_bar_service.py (new)                  │
│     - Fetches Alpha Vantage 5/15/30/60-min bars                        │
│     - Postgres-backed cache (same pattern as PriceDataService)         │
│     - Returns pd.DataFrame indexed by datetime (vs date for EOD)        │
│   apps/api/app/services/live_quote_service.py (existing, unchanged)    │
│     - 30s in-process cache for monitor job's per-position polls       │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  ENGINE EXTENSION                                                      │
│   apps/api/app/services/backtester/engine.py                           │
│     BacktestEngine.run(strategy, bar_resolution="daily" | "15min")    │
│       - Same engine path, different bar series shape                   │
│       - Existing 22 strategy_types work unchanged                      │
│       - SignalProvider impls in PRD-16a are resolution-aware            │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  MULTI-TIER EXIT SCHEMA                                                │
│   apps/api/app/schemas/strategy.py                                     │
│     RiskManagement.exit_ladder: list[ExitTier]                         │
│       ExitTier(trigger_pct, action="sell_fraction"|"sell_all",         │
│                fraction: Optional[float])                              │
│   Backwards-compatible: single stop_loss_pct + take_profit_pct work    │
│   unchanged on existing templates.                                     │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  PER-POSITION STATE                                                    │
│   apps/api/app/models/position_state.py (new)                          │
│     PositionState(saved_strategy_id, symbol, entry_price,              │
│                   shares_initial, shares_remaining, entered_at,        │
│                   trade_log: JSON)                                     │
│   IntradayPositionMonitorJob writes here when triggers fire.           │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  INTRADAY MONITOR CRON                                                 │
│   apps/api/app/jobs/intraday_jobs.py (new)                             │
│     intraday_position_monitor_job()                                    │
│       - Runs every 5 minutes during market hours                       │
│       - For each SavedStrategy with bar_resolution != "daily":         │
│         - Fetch quotes for held positions                              │
│         - Evaluate exit_ladder tiers against current price             │
│         - If trigger met:                                              │
│            - Write PositionState update                                │
│            - throttle.check_and_record(... 'stop_hit' or 'tp_hit')    │
│            - dispatch via PRD-19's EmailDispatcher + InAppDispatcher  │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│  USER SURFACES                                                         │
│   Inbox: position_stop.html, position_tp1.html, position_tp2.html     │
│   In-app banner: PRD-19's <NotificationBanner> renders new types      │
│   Strategy detail (active-mode view):                                  │
│     <UniverseWatchPanel /> - live price cards for each tracked ticker  │
│     <PositionCardsGrid />  - per-position cards with distance bars    │
│     <TradeLogTable />      - chronological event log                  │
│   Settings: extended <NotificationSettingsForm /> with intraday section│
└────────────────────────────────────────────────────────────────────────┘
```

---

## Backend changes

### 1. Intraday data service

`apps/api/app/services/intraday_bar_service.py` (new file)

```python
class IntradayBarService:
    """Fetches and caches intraday OHLCV bars from Alpha Vantage.

    Resolutions: 5min, 15min, 30min, 60min. (1min not supported in v1
    due to AV rate-limit complexity.)

    Caching: Postgres-backed (intraday_bars table). Cache key:
    (symbol, resolution, date). Returns pandas DataFrame indexed by
    datetime (vs date for EOD).

    Different from live_quote_service: live_quote is 30s in-process
    cache for "what's the current price right now" — IntradayBarService
    is historical bar series for backtest + recent-state evaluation.
    """

    async def get_bars(
        self,
        db: Session,
        symbol: str,
        resolution: str,                   # '5min' | '15min' | '30min' | '60min'
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame: ...

    async def ensure_recent_bars(
        self,
        db: Session,
        symbol: str,
        resolution: str,
        lookback_minutes: int = 120,
    ) -> pd.DataFrame:
        """For monitor job: ensure last N minutes of bars are cached."""
```

New table:

```python
class IntradayBar(Base):
    __tablename__ = "intraday_bars"

    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    resolution: Mapped[str] = mapped_column(String(8), primary_key=True)
    bar_time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    open: Mapped[float]
    high: Mapped[float]
    low: Mapped[float]
    close: Mapped[float]
    volume: Mapped[float]
```

### 2. Engine extension for bar resolution

`apps/api/app/services/backtester/engine.py`

Add `bar_resolution` parameter to `BacktestEngine.run`:

```python
async def run(
    self,
    db: Session,
    strategy: StrategyJSON,
    bar_resolution: str = "daily",        # 'daily' | '5min' | '15min' | '30min' | '60min'
) -> BacktestResult:
    if bar_resolution == "daily":
        bars = await self._load_eod_bars(strategy.universe, ...)
    else:
        bars = await self._load_intraday_bars(strategy.universe, bar_resolution, ...)

    # Engine logic from here forward is identical — operates on bar series
    # regardless of resolution. SignalProvider.compute() is resolution-aware
    # via the existing `resolution` parameter (added in PRD-16a).
```

The existing 22 strategy_types work unchanged on either resolution because they operate on the bar series, not on calendar dates.

Default `bar_resolution="daily"` preserves all existing callers' behavior.

### 3. Multi-tier exit schema

`apps/api/app/schemas/strategy.py`

```python
class ExitTier(BaseModel):
    """One tier in a multi-tier exit ladder.

    Trigger: % change from entry. Positive for TP, negative for stop.
    Action: 'sell_all' or 'sell_fraction' (with fraction).
    """
    trigger_pct: float                     # e.g. -0.10 = -10% stop, +0.30 = +30% TP
    action: Literal["sell_all", "sell_fraction"]
    fraction: Optional[float] = None       # required when action='sell_fraction'; 0 < f < 1
    label: Optional[str] = None            # plain-English for UI: "Stop", "TP1", "TP2"


class RiskManagement(BaseModel):
    # ... existing fields unchanged ...

    exit_ladder: Optional[list[ExitTier]] = None
    """Multi-tier exit ladder. When set, replaces single stop_loss_pct +
    take_profit_pct. Evaluated in order; first trigger met fires.

    Example for SpaceX-style strategy:
      exit_ladder=[
        ExitTier(trigger_pct=-0.10, action='sell_all', label='Stop'),
        ExitTier(trigger_pct=+0.15, action='sell_fraction', fraction=0.33, label='TP1'),
        ExitTier(trigger_pct=+0.30, action='sell_all', label='TP2'),
      ]

    Backwards-compatible: existing single stop_loss_pct + take_profit_pct
    continue to work when exit_ladder is None.
    """
```

Validator: if `exit_ladder` is set, must contain ≥ 1 stop tier (`trigger_pct < 0` with `action='sell_all'`). If `sell_fraction`, fraction must be `0 < f < 1`. Tiers ordered ascending by `trigger_pct`.

### 4. PositionState table

`apps/api/app/models/position_state.py` (new file)

```python
class PositionState(Base):
    __tablename__ = "position_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    saved_strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("saved_strategies.id", ondelete="CASCADE"),
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(10), index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime)
    entry_price: Mapped[float]
    shares_initial: Mapped[float]
    shares_remaining: Mapped[float]
    trade_log: Mapped[dict] = mapped_column(JSON, default=list)
    # trade_log: [
    #   {"event": "entry", "timestamp": "...", "price": ..., "shares": ...},
    #   {"event": "tp1_hit", "timestamp": "...", "price": ..., "shares_sold": ...},
    #   ...
    # ]
    is_open: Mapped[bool] = mapped_column(default=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    final_pnl: Mapped[Optional[float]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 5. Intraday monitor cron

`apps/api/app/jobs/intraday_jobs.py` (new file)

```python
async def intraday_position_monitor_job():
    """Runs every 5 minutes during market hours.

    For each SavedStrategy with bar_resolution != 'daily':
      1. Query open PositionState rows for this strategy
      2. Fetch live quotes for held symbols (via live_quote_service — 30s cache)
      3. For each position:
         - Compute pct change from entry: (current_price / entry_price) - 1
         - Walk exit_ladder tiers in order
         - First trigger met → execute the tier's action:
            - sell_all: shares_remaining -> 0; close position; log event
            - sell_fraction: shares_remaining -= fraction * shares_initial; log event
         - Update PositionState row (atomically — use db locking)
      4. For each trigger fired:
         - throttle.check_and_record(user, strategy, channel, trigger_type)
         - If allowed: dispatcher.dispatch(...)
    """
```

Cron registration: extend existing scheduler config. Market-hours awareness reuses existing utility (Mon-Fri, 9:30-16:00 ET). Outside hours → no-op skip.

### 6. New email templates

`apps/api/app/emails/position_stop.html`
`apps/api/app/emails/position_tp1.html`
`apps/api/app/emails/position_tp2.html`

Follow PRD-19's `signal_change.html` style. Include:
- Position symbol + entry price + current price + pct change
- Action ("Stop hit — sell all" / "TP1 hit — sell 1/3" / "TP2 hit — sell all")
- Reference prices snapshot
- Mini chart of intraday move (reuse PRD-20's `ChartRenderer` if shipped; else text-only)
- Standard `<NotInvestmentAdviceFooter>` + CAN-SPAM unsubscribe

### 7. Throttle extension

The 3 new trigger types (`stop_hit`, `tp1_hit`, `tp2_hit`) have a different cap profile from `signal_change`:

- Per-position (not per-strategy) — a stop on AAPL doesn't prevent a TP1 on NVDA in the same strategy
- 1 per (user, strategy, symbol, trigger_type) per day — same TP hit on same symbol in same day = noise

Implement via extending `NotificationThrottle.check_and_record` with an optional `symbol` parameter:

```python
def check_and_record(
    user_id, strategy_id, channel, trigger_type,
    symbol: Optional[str] = None,  # for per-position throttling
) -> ThrottleResult: ...
```

### 8. Test plan

`apps/api/tests/`

- `test_intraday_bar_service.py` — fetch 15-min bars on synthetic input; cache hit/miss.
- `test_engine_intraday.py` — synthetic intraday bars; existing strategy_type (MA filter) produces same logical output as on daily bars.
- `test_exit_ladder_schema.py` — validator enforces stop-tier requirement; fraction bounds.
- `test_exit_ladder_engine.py` — multi-tier ladder fires in order on synthetic price path.
- `test_position_state.py` — entry, partial exit (TP1), full exit (TP2 or stop).
- `test_intraday_monitor_job.py` — integration: simulate price move through TP1; assert PositionState updated + dispatch called.
- `test_intraday_throttle.py` — per-position throttle: same TP on same symbol same day → throttled.

---

## Frontend changes

### 1. Composer extension (small)

`apps/web/src/components/custom-build/when-out-block.tsx` (extend existing)

Add toggle:

```tsx
<div>
  <label>
    <Toggle
      checked={config.active_execution}
      onChange={(v) => update({ active_execution: v })}
    />
    Enable active execution (intraday monitoring + multi-tier exits)
  </label>

  {config.active_execution && (
    <>
      <BarResolutionPicker value={config.bar_resolution} onChange={...} />
      <ExitLadderEditor value={config.exit_ladder} onChange={...} />
    </>
  )}
</div>
```

### 2. Exit ladder editor brick

`apps/web/src/components/custom-build/exit-ladder-editor.tsx`

```tsx
export function ExitLadderEditor({ value, onChange }: Props) {
  // 3 default rows on enable: Stop (-10%), TP1 (+15%, sell 1/3), TP2 (+30%, sell all)
  // Each row: trigger_pct slider + action dropdown + fraction slider (when sell_fraction)
  // Add/remove rows; max 5 tiers
  // Validation messages inline
}
```

### 3. Live dashboard bricks

`apps/web/src/components/active-execution/universe-watch-panel.tsx`

```tsx
export function UniverseWatchPanel({ strategy }: Props) {
  // Polls /api/strategies/{slug}/universe-state every 30s
  // Renders: grid of cards for each ticker in the strategy's universe
  // Each card: symbol, last price, change %, mini 30-day sparkline
  // Skeleton state during initial load
}
```

`apps/web/src/components/active-execution/position-cards-grid.tsx`

```tsx
export function PositionCardsGrid({ strategy }: Props) {
  // Polls /api/strategies/{slug}/positions every 30s
  // Renders: one card per open position
  // Each card: symbol, entry price, current price, P&L $ and %,
  //   visual distance bar showing position relative to stop/TP1/TP2,
  //   action badges (HOLD / TP1 HIT / STOP HIT)
}
```

`apps/web/src/components/active-execution/trade-log-table.tsx`

```tsx
export function TradeLogTable({ strategy }: Props) {
  // Fetches /api/strategies/{slug}/trade-log (paginated)
  // Renders chronological table of position events: entry, TP1, TP2, stop
  // Sortable by timestamp; filterable by symbol
}
```

### 4. Strategy detail page surgery

`apps/web/src/app/strategies/[slug]/page.tsx`

Conditional render — active-execution strategies get the live dashboard instead of (or in addition to) the static backtest viewer:

```tsx
if (strategy.is_active_execution) {
  return (
    <>
      <UniverseWatchPanel strategy={strategy} />
      <PositionCardsGrid strategy={strategy} />
      <TradeLogTable strategy={strategy} />
      {/* existing backtest viewer below, collapsed by default */}
    </>
  );
}
```

### 5. Two new endpoints for the dashboard

`GET /api/strategies/{slug}/universe-state` — returns live quotes for the universe
`GET /api/strategies/{slug}/positions` — returns open PositionState rows
`GET /api/strategies/{slug}/trade-log` — paginated trade events

All three are read-only; tier-gated via existing entitlements.

### 6. Settings form extension

`<NotificationSettingsForm>` gets a new section (coordinate with PRD-20 if both in flight):

```tsx
<section>
  <h3>Active strategy alerts (intraday)</h3>
  <Checkbox label="Stop-loss hit" ... />
  <Checkbox label="Take-profit hit" ... />
  <p className="dim">Channels: email + in-app banner. Respects your quiet hours.</p>
</section>
```

### 7. Catalog extension (PRD-16a content addition)

Within PRD-16a's `SIGNAL_PRIMITIVES`, mark primitives that support intraday resolution by adding `"intraday"` to the `resolution` list:

```python
SignalPrimitive(
    id="rsi_14",
    ...
    resolution=["daily", "intraday"],
),
```

Mostly all price-based primitives support intraday; fundamental and event-driven primitives are EOD-only and keep `resolution=["daily"]`.

### 8. Test plan

- `__tests__/exit-ladder-editor.test.tsx` — validation: stop required; fraction bounds.
- `__tests__/universe-watch-panel.test.tsx` — renders cards; polls 30s; skeleton state.
- `__tests__/position-cards-grid.test.tsx` — distance bars correct; action badges.
- `__tests__/trade-log-table.test.tsx` — pagination, sort.
- E2E: `e2e/active-execution.spec.ts` — compose strategy with active toggle → save → live dashboard renders → simulate position event → banner appears → "Mark as executed" wires.

### 9. Manual smoke

- Send each of 3 new email templates to test account; verify rendering in Gmail web, Outlook web, Apple Mail.
- Trigger synthetic stop_hit; verify email + banner + PositionState update.
- Test quiet hours: stop hit during quiet window → push (if shipped in Sprint C) queued, email arrives, in-app banner persists.

---

## Reusable LEGO bricks created by this PRD

### Backend

| Brick | Path | Used by |
|---|---|---|
| `IntradayBarService` | `services/intraday_bar_service.py` | This PRD; future curated-themes PRD; future paper-trading PRD |
| `intraday_bars` table | `models/intraday_bar.py` | Cache layer for intraday consumers |
| `BacktestEngine.run(bar_resolution=...)` | `services/backtester/engine.py` (extended) | Intraday backtests; future replay features |
| `ExitTier`, `RiskManagement.exit_ladder` | `schemas/strategy.py` (extended) | Multi-tier exit consumers; reusable on any strategy_type |
| `PositionState` table | `models/position_state.py` | All active-execution strategies; future paper-trading audit |
| `IntradayPositionMonitorJob` | `jobs/intraday_jobs.py` | Active-execution monitoring; pattern reusable for other intraday triggers |
| 3 new email templates + 3 new trigger types | `emails/`, `services/notification_throttle.py` (extended) | This PRD; future curated-themes PRD may add similar templates |
| 3 new dashboard endpoints | `routes/strategies.py` (extended) | Dashboard; future "my strategies hub" features |

### Frontend

| Brick | Path | Used by |
|---|---|---|
| `<ExitLadderEditor>` | `components/custom-build/` | Composer WHEN OUT block; future Pro-tier strategy edit |
| `<UniverseWatchPanel>` | `components/active-execution/` | Strategy detail (active view); future watchlist surfaces |
| `<PositionCardsGrid>` | Same | Strategy detail (active view); future portfolio dashboard |
| `<TradeLogTable>` | Same | Strategy detail; future "all my trades" surface |
| `<BarResolutionPicker>` | `components/custom-build/` | Composer; future "intraday backtest" surface |

---

## Acceptance checklist

A PR is accepted when **all of the following are true**.

### Prerequisites

- [ ] PRD-19 (notifications Phase B re-shape) on `main`. Verify `NotificationThrottle` + `ChannelDispatcher` + `<NotificationBanner>` exist.
- [ ] PRD-16a (signal catalog) on `main`. Verify `GET /api/signal-primitives` returns ≥ 50 entries.
- [ ] PRD-16b (composer) on `main`. Verify `lib/flows/custom_build_mode.ts` exists.

### Backend

- [ ] `IntradayBarService` implemented; fetches 5/15/30/60-min bars; postgres-cached.
- [ ] `intraday_bars` table + migration added.
- [ ] `BacktestEngine.run` accepts `bar_resolution` parameter; existing daily callers unchanged.
- [ ] `RiskManagement.exit_ladder` added; `ExitTier` model; validator enforces stop requirement + fraction bounds.
- [ ] `PositionState` table + migration added.
- [ ] `IntradayPositionMonitorJob` registered in scheduler; runs every 5 min during market hours.
- [ ] 3 new email templates exist; include `<NotInvestmentAdviceFooter>`; no buy/sell verbs in subject lines.
- [ ] 3 new trigger types (`stop_hit`, `tp1_hit`, `tp2_hit`) work through `NotificationThrottle` with per-position semantics.
- [ ] 3 new dashboard endpoints live; tier-gated; respect ownership.
- [ ] PRD-16a's `SIGNAL_PRIMITIVES` catalog extended: each price-based primitive's `resolution` list includes `"intraday"`.
- [ ] No `X | None` syntax (Python 3.9 compat).
- [ ] All 7 new backend tests pass.
- [ ] Full backend suite passes: `cd apps/api && python3 -m pytest -q`.

### Frontend

- [ ] `<ExitLadderEditor>` brick in composer's WHEN OUT block (when "Active execution" enabled).
- [ ] `<BarResolutionPicker>` brick added to composer.
- [ ] `<UniverseWatchPanel>`, `<PositionCardsGrid>`, `<TradeLogTable>` bricks implemented.
- [ ] Strategy detail page renders live dashboard when `is_active_execution = true`.
- [ ] `<NotificationSettingsForm>` extended with "Active strategy alerts" section.
- [ ] All 4 unit tests + 1 E2E pass.
- [ ] `cd apps/web && npm run build` clean.

### Quality

- [ ] Live dashboard polls 30s — no faster (avoid hammering); SSE upgrade path documented for future.
- [ ] Skeleton states on initial load of each dashboard component.
- [ ] Distance bars on position cards accurately reflect price-to-stop/TP distance.
- [ ] Active-execution toggle hidden from Scout-tier users if entitlement gating is on; visible to Strategist+.

### Manual smoke

- [ ] Compose a strategy → toggle Active execution → set exit ladder → save.
- [ ] Run backtest with `bar_resolution="15min"` → backtest result returns successfully.
- [ ] Simulate position event: stub a quote that crosses TP1 → monitor cron runs → PositionState updates → email + banner dispatched.
- [ ] Verify email renders in Gmail web, Outlook web, Apple Mail.
- [ ] Test quiet hours: simulated event during quiet window → in-app banner persists; email arrives; if push channel exists (PRD-21), queued.

### Compliance

- [ ] All 3 new email templates include "Not investment advice" footer.
- [ ] One-click CAN-SPAM unsubscribe in all 3 templates.
- [ ] No buy/sell verbs in subject lines — use "stop hit", "TP1 reached", "TP2 reached".

### Telemetry

- [ ] PostHog events: `active_execution_enabled`, `exit_ladder_configured`, `intraday_backtest_run` (with `bar_resolution`), `position_event_fired` (with `event_type`, `latency_seconds`), `live_dashboard_opened`.

### Documentation

- [ ] Update HANDOFF-livermore-product-flow-v2.md §6 Brick inventory: mark PRD-16c bricks as ✅.
- [ ] Update HANDOFF-livermore-notifications.md §5 Brick inventory: mark new trigger types + email templates as ✅.
- [ ] PR title: `feat(active-execution): intraday + multi-tier exits + live dashboard (PRD-16c)`.

---

## Out of scope (do not build in this PRD)

- **Curated thematic universe / themes catalog** — separate future PRD.
- **Catalyst date / deadline-exit features** — user 2026-06-08 explicitly de-scoped.
- **NLP universe curation** — same.
- **Broker integration / auto-execution** — never; signal-only platform.
- **SMS / webhook channels for intraday alerts** — PRD-21.
- **1-min cadence** — start at 5-min; reconsider after observing API cost in production.
- **Paper trading integration** — separate future workstream.
- **User-supplied Python signals** — far-future Pro feature.
- **Backtest replay / "what would have happened" historical event simulation** — future polish.
- **Tier-gating decisions** — per user 2026-06-08, tabled; ship without gating, address later.

---

## Why this is one PRD, not a split

Three deliverables (intraday data, multi-tier exits, live dashboard) — all part of the same user story ("I want to actively run a custom strategy with intraday monitoring"). Splitting would force half-shipped UX (data + schema without dashboard = useless to users; dashboard without backend = a dead UI).

If the engine `bar_resolution` parameter + intraday data + multi-tier schema turns out to be unexpectedly complex (likely — there's real risk in the intraday data caching layer), the natural split is:

- **PRD-16c1**: Intraday data + engine bar_resolution + multi-tier schema (backend foundation, ~2 weeks)
- **PRD-16c2**: Monitor cron + email templates + live dashboard (~1 week)

But ship them in adjacent sprints — half-shipped is worse than waiting.

---

## Cross-references

- Source spec: `/Quant Strategy/framework/livermore_product_flow_v2.html` §2 Mode 4
- SpaceX reference: chat 2026-06-08 (the design inspiration; uploaded `SPACEX_RIPPLE_TECHNICAL_REFERENCE.md`)
- Notification framework: `/Quant Strategy/framework/livermore_notification_framework.html` §2 Trigger 1 (extends for intraday position events)
- Master handoff (v2): `agent-system/plans/HANDOFF-livermore-product-flow-v2.md`
- Master handoff (notifications): `agent-system/plans/HANDOFF-livermore-notifications.md`
- Hard deps: `PRD-19-phase-b-reshape.md`, `PRD-16a-signal-library-catalog.md`, `PRD-16b-custom-build-composer.md`
- Soft dep: `PRD-20-sprint-b-milestone-maintenance.md` (coordinate settings-form extension)
- Existing live_quote_service: `apps/api/app/services/live_quote_service.py`
- Repo conventions: `CLAUDE.md` (auto-loaded), `agent-system/PARALLEL_WORK.md`

---

*Drafted 2026-06-08. The biggest of the three PRD-16 sub-PRDs. Sets the foundation for active execution on Custom Mode. Curated themes, paper trading, broker integration are all downstream of this.*
