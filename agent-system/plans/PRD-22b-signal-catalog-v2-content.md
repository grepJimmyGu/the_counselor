# PRD-22b: Signal Catalog v2 — Content (11 Family Upgrades + 65 New Primitives)

**Status**: Ready to build
**Phase**: Custom Mode v2 (Signal Library upgrade)
**Depends on**: PRD-22a (hard) — needs `output_kind` / `output_channels` / `composes` fields on schema.
**Blocks**: PRD-22c — soft. PRD-22c can render kind widgets for v1 primitives with non-VALUE kinds even before this PRD lands; new primitives light up the widgets once both are on main.
**Effort**: ~3 weeks, single owner (or ~2 weeks engineering + 8 days editorial work)
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/signal_catalog_v2_spec.html`](../../Quant%20Strategy/framework/signal_catalog_v2_spec.html) — §3 (per-family audit), §4 (computation reference), §6 (summary table)

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md
first (auto-loaded). Then read agent-system/plans/HANDOFF-livermore-signal-catalog-v2.md.

Goal: ship the v2 catalog content — 11 family upgrades plus 65 net-new primitives,
each with its computation impl, plain-English description, parameter defaults,
asset compat, evidence tier, and unit test. Plus enrich the KB-lookup endpoint
with output_kind-aware Jaccard similarity.

Five deliverables:

  1. Per-family upgrades (Section 3 of v2 spec): for each of the 11 anchor
     families (MACD, RSI, Bollinger, ADX, MA, Stoch, 52w extrema, Volume,
     Volatility, Momentum, Fundamental+Events, Candle structure), add the
     v2 primitives. ~35 entries total.

  2. Net-new primitive families (Section 4 of v2 spec): TTM Squeeze (2),
     Supertrend (3), Chandelier Exit (3), Anchored VWAP (3), RVOL (2),
     12-1 Momentum (4), PEAD (6), Heikin-Ashi (3), z-score wrapper (1),
     52-week extrema (7). ~30 entries.

  3. Concrete SignalProvider impls for every new primitive. ~40 net-new
     impl files in apps/api/app/services/signal_providers/. The formulas
     are in v2 spec §4.

  4. Hand-authored catalog entries in apps/api/app/data/signal_primitives.py.
     One-line plain-English description + optional long_description.
     ~65 entries × ~1 hour editorial = ~8 days writing.

  5. Update POST /api/signal-combos/match-templates to use (category,
     output_kind) tuples in the Jaccard similarity, not just category.
     Cache results by frozenset(primitive_ids) for 1 hour.

PREREQUISITES (must be on main):
  - PRD-22a — schema fields (output_kind, output_channels, composes).

OUT OF SCOPE for this PRD:
  - Composer rule-builder widgets — PRD-22c.
  - Intraday extension of any new primitive — separate follow-up PR.
  - Cross-asset / macro signals (VIX term structure, put/call, HY-IG) —
    future PRD with new data sources.
  - User-supplied custom Python signals — far-future Pro feature.

Context to read in order:
  - /Quant Strategy/framework/signal_catalog_v2_spec.html §3 + §4 (the
    design source — every primitive maps to a row there)
  - apps/api/app/data/signal_primitives.py (the v1 catalog to extend)
  - apps/api/app/services/signal_providers/ (existing impls to mirror)

DEFINITION OF DONE:
  - ~65 new catalog entries with hand-authored descriptions
  - ~40 new SignalProvider impls with unit tests
  - KB-lookup Jaccard enriched with output_kind tuples
  - Cache layer on /api/signal-combos/match-templates with 1h TTL
  - Catalog endpoint payload size verified <200KB (still cacheable)
  - All existing tests + every new primitive test green
```

---

## 1. The problem

The shipped v1 catalog (~55 primitives) has two gaps that PRD-22a's schema layer alone can't close:

1. **Single-channel decomposition.** MACD has 3 channels, BBANDS has 3, ADX has 3, Stoch has 2 — but each is a single primitive. To compose `MACD signal-line cross + RVOL surge`, the user needs `macd_signal_cross` as a primitive in its own right, not as a synthetic compound expression.

2. **Missing computations.** 65 net-new primitives covering proximity, squeeze detection, anchored references, ATR trailing stops, smoothed candles, the academic 12-1 momentum z-score, and PEAD drift. These are table-stakes in modern quant workflows — the catalog without them blocks Custom Mode from expressing the strategies users actually want to build.

This PRD ships every primitive in the v2 spec §3-§4. It's the heaviest PRD in the packet by far — ~40 provider impls + ~65 editorial entries + KB-lookup enrichment.

---

## 2. Design constraints

1. **The catalog metadata IS the editorial product.** Per the PRD-16 HANDOFF pitfall (repeated in PRD-22's HANDOFF): no LLM-generated descriptions. Each one-line description is ~50 words of plain English explaining what the indicator measures and how a trader uses it. PR review is the editorial gate.

2. **All formulas come from v2 spec §4.** No invention. The spec has the canonical industry formula (with sources) for each new primitive. If the spec's formula is ambiguous, escalate to Jimmy — don't improvise.

3. **All new primitives ship with `resolution=["daily"]`.** Intraday extension is a follow-up PR. The intraday machinery from PRD-16c can flip eligible primitives to `["daily", "intraday"]` once this lands.

4. **`composes` declares the parent for derived primitives.** `macd_signal_cross` declares `composes=["macd"]`. The composer (via PRD-22c) uses this to inherit the parent's parameter knobs.

5. **`output_channels` for multi-channel primitives is a public contract.** Once `macd` ships with `output_channels=["macd_line", "signal_line", "histogram"]`, those names are referenced by saved strategies. **Never rename**, only deprecate.

6. **KB-lookup enrichment must stay sub-200ms.** The Jaccard now operates on `(category, output_kind)` tuples — set size grows from 8 to 56. Still cheap, but cache the response keyed by `frozenset(primitive_ids)` with 1h TTL.

7. **Python 3.9 compat.** `Optional[X]`, `List[X]`.

---

## 3. Implementation

### 3.1 Per-family upgrades

Per v2 spec §3, the 11 anchor families upgrade as follows. **Each row is a new catalog entry + a new provider impl + a unit test.**

| Family | New primitives (id) | Output kind | Composes |
|---|---|---|---|
| MACD | `macd_signal_cross`, `macd_histogram_flip`, `macd_zero_line_cross`, `macd_bullish_divergence`, `macd_bearish_divergence` | CROSS / EVENT / CROSS / DIV / DIV | `["macd"]` |
| RSI | `rsi_oversold`, `rsi_overbought`, `rsi_bullish_failure_swing`, `rsi_bearish_failure_swing`, `rsi_bullish_divergence`, `rsi_bearish_divergence`, `rsi_hidden_bullish_div` | LEVEL × 2 / EVENT × 2 / DIV × 3 | `["rsi"]` |
| Bollinger | `bb_percent_b`, `bb_bandwidth`, `bb_squeeze`, `bb_squeeze_fire`, `bb_walk_upper`, `bb_tag_upper`, `bb_tag_lower` | VALUE × 2 / REGIME / EVENT × 4 | `["bbands"]` |
| ADX/DMI | `adx_regime`, `adx_rising`, `di_cross_bullish`, `di_cross_bearish` | REGIME / LEVEL / CROSS × 2 | `["adx"]` |
| MA | `price_above_ma`, `price_ma_cross_up`, `price_ma_cross_down`, `golden_cross`, `death_cross`, `ma_slope_positive` | LEVEL / CROSS × 2 / CROSS × 2 / LEVEL | various MAs |
| Stochastic | `stoch_k_d_cross`, `stoch_oversold_cross_up`, `stoch_overbought_cross_down` | CROSS / EVENT × 2 | `["stoch"]` |
| 52w extrema | `distance_to_52w_high`, `distance_to_52w_low`, `price_52w_high_ratio`, `price_52w_high_breakout`, `price_52w_low_breakdown`, `price_in_52w_high_zone`, `days_since_52w_high` | DISTANCE × 2 / VALUE / EVENT × 2 / LEVEL / VALUE | — |
| Volume | `rvol`, `rvol_surge`, `obv_divergence_bullish`, `obv_divergence_bearish`, `anchored_vwap`, `distance_to_anchored_vwap`, `price_above_anchored_vwap` | VALUE / EVENT / DIV × 2 / VALUE / DISTANCE / LEVEL | various |
| Volatility | `chandelier_exit_long`, `chandelier_exit_short`, `chandelier_exit_breach`, `supertrend`, `supertrend_flip`, `supertrend_above_price`, `ttm_squeeze`, `ttm_squeeze_fire` | VALUE × 2 / EVENT / VALUE / EVENT / LEVEL / REGIME / EVENT | — |
| Momentum | `momentum_12_1`, `momentum_12_1_zscore`, `momentum_composite_zscore`, `momentum_acceleration` | VALUE × 4 | — |
| Fundamental + Events | `pead_signal`, `pead_drift_window`, `days_to_earnings`, `days_since_earnings`, `estimate_revision_positive_cross`, `insider_net_buy_surge` | VALUE / LEVEL / VALUE × 2 / EVENT × 2 | various |
| Candle structure | `heikin_ashi_trend`, `heikin_ashi_consecutive`, `heikin_ashi_color_flip` | REGIME / VALUE / EVENT | — |

**Total**: ~65 new primitives. Each row = one catalog entry + one provider impl + one unit test.

### 3.2 SignalProvider impl pattern

Each derived primitive's provider impl follows the v1 protocol but reads the parent primitive's computed series as input. Example for `macd_signal_cross`:

```python
# apps/api/app/services/signal_providers/macd_signal_cross.py — NEW

from app.services.signal_providers.base import SignalProvider
from app.services.signal_providers.macd import MacdSignalProvider


class MacdSignalCrossProvider(SignalProvider):
    """Bullish/bearish event when MACD line crosses its signal line.

    Composes on top of MacdSignalProvider — reuses the MACD line and
    signal line series, computes the crossover event.
    """

    primitive_id = "macd_signal_cross"

    def compute(self, df: pd.DataFrame, params: dict) -> pd.Series:
        macd_params = {
            k: params.get(k, default)
            for k, default in [
                ("fast_period", 12),
                ("slow_period", 26),
                ("signal_period", 9),
            ]
        }
        macd_result = MacdSignalProvider().compute(df, macd_params)
        macd_line = macd_result["macd_line"]
        signal_line = macd_result["signal_line"]

        # Bullish cross: MACD crosses above signal
        prev_above = macd_line.shift(1) <= signal_line.shift(1)
        now_above = macd_line > signal_line
        bull_cross = prev_above & now_above

        # Bearish cross (negative sign in series for direction)
        prev_below = macd_line.shift(1) >= signal_line.shift(1)
        now_below = macd_line < signal_line
        bear_cross = prev_below & now_below

        # Direction-aware: positive=bull, negative=bear, zero=no event
        result = pd.Series(0, index=df.index, dtype="int8")
        result[bull_cross] = 1
        result[bear_cross] = -1
        return result
```

The composer's `<CrossRule>` widget (PRD-22c) consumes this series and lets the user pick "above" / "below" direction. The series is non-zero only at the bar of the cross — EVENT semantics.

### 3.3 The DISTANCE family (the SpaceX example)

Per v2 spec §3 — implementing the user-flagged "2-25% below 52-week high" use case:

```python
# apps/api/app/services/signal_providers/distance_to_52w_high.py

class DistanceTo52wHighProvider(SignalProvider):
    primitive_id = "distance_to_52w_high"

    def compute(self, df: pd.DataFrame, params: dict) -> pd.Series:
        lookback = params.get("lookback", 252)
        high_52w = df["close"].rolling(lookback, min_periods=20).max()
        # Signed: negative = below high; positive (rare) = at new high
        return (df["close"] / high_52w - 1.0) * 100
```

```python
# apps/api/app/services/signal_providers/price_in_52w_high_zone.py

class PriceIn52wHighZoneProvider(SignalProvider):
    primitive_id = "price_in_52w_high_zone"

    def compute(self, df: pd.DataFrame, params: dict) -> pd.Series:
        d = DistanceTo52wHighProvider().compute(df, params)
        min_pct = params.get("min_pct", 2)   # 2% below high
        max_pct = params.get("max_pct", 25)  # 25% below high
        return (d <= -min_pct) & (d >= -max_pct)
```

Catalog entry:

```python
SignalPrimitive(
    id="price_in_52w_high_zone",
    category=SignalCategory.MOMENTUM,
    family="52W_EXTREMA",
    name="Price in 52-week high zone",
    description=(
        "True while price sits in a parameterized band below the 52-week "
        "high — the 'breakout setup zone' from 2-25% below by default."
    ),
    long_description=(
        "Captures the early-breakout setup pattern: stocks that have pulled "
        "back from a recent high but not retraced more than 25%. Used in "
        "event-driven momentum strategies (e.g. the SpaceX/Ripple reference) "
        "to filter for names that are 'close to but not at' new highs."
    ),
    parameters=[
        Parameter(name="min_pct", default=2.0, min_value=0.0, max_value=50.0,
                  description="Inner boundary (percent below high)"),
        Parameter(name="max_pct", default=25.0, min_value=1.0, max_value=80.0,
                  description="Outer boundary (percent below high)"),
        Parameter(name="lookback", default=252, min_value=20, max_value=504,
                  description="High lookback window (trading days)"),
    ],
    default_thresholds={},   # LEVEL — no threshold input
    asset_compat=["equity", "etf"],
    evidence_tier="B",
    provider_impl="price_in_52w_high_zone",
    data_source="price",
    output_kind=OutputKind.LEVEL,
    output_channels=["value"],
    composes=[],   # standalone (uses distance internally but doesn't expose it)
    resolution=["daily"],
),
```

### 3.4 KB-lookup enrichment

The shipped endpoint at `POST /api/signal-combos/match-templates` does Jaccard similarity on the **set of categories** the user's primitives belong to. v2 enriches this to the **set of (category, output_kind) tuples**, which is meaningfully more discriminating.

```python
# apps/api/app/services/signal_combos.py

def _signature(primitive_ids: list[str]) -> frozenset[tuple[str, str]]:
    """Return the set of (category, output_kind) tuples for the given primitives."""
    by_id = {p.id: p for p in SIGNAL_PRIMITIVES}
    return frozenset(
        (by_id[pid].category.value, by_id[pid].output_kind.value)
        for pid in primitive_ids
        if pid in by_id
    )


def match_templates(primitive_ids: list[str]) -> list[TemplateMatch]:
    user_sig = _signature(primitive_ids)
    candidates = []
    for template in TEMPLATE_REGISTRY:
        template_sig = _signature(template.primitive_ids)
        jaccard = len(user_sig & template_sig) / len(user_sig | template_sig)
        if jaccard > 0:
            candidates.append((template, jaccard))
    return sorted(candidates, key=lambda x: -x[1])[:3]
```

Cache layer (Redis or in-process LRU):

```python
@lru_cache(maxsize=500)
def cached_match(primitive_ids_frozen: frozenset[str]) -> list[TemplateMatch]:
    return match_templates(sorted(primitive_ids_frozen))
```

TTL is implicit via process restart; for Redis, set 3600s.

---

## 4. Testing

### 4.1 Provider impl tests

Each of the ~40 new providers gets a focused unit test:

```python
def test_macd_signal_cross_fires_on_bullish_cross():
    df = make_macd_test_df_with_cross_at_bar(50, direction="bull")
    result = MacdSignalCrossProvider().compute(df, {})
    # Only the cross bar is non-zero
    assert result.iloc[50] == 1
    assert (result.drop(index=df.index[50]) == 0).all()


def test_price_in_52w_high_zone_default_2_to_25_pct():
    df = make_price_series_at_pct_below_high([1, 5, 15, 30, 50])
    result = PriceIn52wHighZoneProvider().compute(df, {"min_pct": 2, "max_pct": 25})
    # 1% below → outside; 5%, 15% → inside; 30%, 50% → outside
    assert result.tolist() == [False, True, True, False, False]
```

### 4.2 Catalog content tests

```python
def test_v2_primitive_count():
    assert len(SIGNAL_PRIMITIVES) >= 120   # 55 v1 + 65 v2


def test_every_v2_primitive_has_description():
    for p in SIGNAL_PRIMITIVES:
        assert len(p.description) >= 30, f"{p.id}: description too short"
        assert not p.description.startswith("TODO"), f"{p.id}: placeholder"


def test_derived_primitives_declare_composes():
    derived_families = {"macd", "rsi", "bbands", "adx", "stoch"}
    for p in SIGNAL_PRIMITIVES:
        if any(p.id.startswith(f) and p.id != f for f in derived_families):
            assert len(p.composes) >= 1, f"{p.id}: derived but no composes"
```

### 4.3 KB-lookup tests

```python
def test_match_templates_uses_output_kind():
    # Two templates differ only in output_kind composition
    user = ["macd_signal_cross", "rvol_surge"]   # CROSS + EVENT
    matches = match_templates(user)
    # The breakout-with-volume template (CROSS+EVENT) should beat
    # the pure-trend template (VALUE+VALUE) for this combo
    assert matches[0].template.name == "Breakout with volume confirmation"


def test_match_templates_cached():
    # First call computes, second hits cache
    with patch("app.services.signal_combos._compute") as spy:
        match_templates(["rsi"])
        match_templates(["rsi"])
        assert spy.call_count == 1
```

### 4.4 No-regression test (still applies)

```python
def test_no_regression_against_main():
    """Existing saved strategies produce byte-identical backtests."""
    for fixture in load_backtest_fixtures():
        result = run_backtest(fixture)
        assert result == fixture.expected_result
```

This must remain green — new primitives are additive; no existing strategy references them.

---

## 5. Pre-merge checklist

1. ✅ `cd apps/api && python3 -m pytest -q` — all green; ~70+ new tests added.
2. ✅ `cd apps/web && npm run build` — frontend types compile.
3. ✅ Static-import smoke test: `python3 -c "from app.main import app; print(len(app.routes))"`.
4. ✅ Catalog endpoint payload size still under 200KB gzipped (~120 primitives × ~1.5KB JSON each).
5. ✅ `grep "| None" apps/api/app/services/signal_providers/ apps/api/app/data/signal_primitives.py -r` — empty.
6. ✅ PR description includes the full primitive-count delta table from §3.1.
7. ✅ Editorial review: Jimmy signs off on the per-family descriptions.
8. ✅ Branch follows `<agent>/feat/prd-22b-catalog-v2-content` convention.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Editorial budget under-estimated (descriptions take longer than 1hr each) | Sequence editorial by family; ship as separate PRs per family if needed |
| Some Alpha Vantage indicators rate-limit on Scout tier | Confirm coverage from PRD-16a's existing API client; document any gating |
| Divergence detection is heuristic — false positives | Use the well-established peak/trough algorithm from `scipy.signal.find_peaks`; document the params chosen |
| KB-lookup cache invalidation when new templates land | Cache TTL of 1h is short enough; explicit cache bust on template additions |
| 40 new files = 40 missed-`git-add` chances | Static-import smoke test (in pre-merge checklist) catches every miss |
| Multi-channel `output_channels` rename breaks production strategies | Channel names are public contract; never rename, only deprecate |

---

## 7. Definition of done

- [ ] ~65 new catalog entries with hand-authored descriptions (per family table §3.1)
- [ ] ~40 new `SignalProvider` impls under `apps/api/app/services/signal_providers/`
- [ ] Each provider has a unit test
- [ ] KB-lookup endpoint Jaccard enriched with `(category, output_kind)` tuples
- [ ] Cache layer on KB-lookup with 1h TTL
- [ ] Catalog payload remains gzipped <200KB
- [ ] No-regression backtest test green
- [ ] PR merged to `main` with green CI
- [ ] Brick inventory updated in `HANDOFF-livermore-signal-catalog-v2.md` §5

---

## 8. Hand-off to next PRD

When PRD-22b is on `main`:

- **PRD-22c** can light up its kind-specific rule-builder widgets with real primitives. The end-to-end test cases:
  - `<CrossRule>` over `macd_signal_cross` + `golden_cross`
  - `<EventRule>` over `bb_squeeze_fire` + `rvol_surge`
  - `<LevelRule>` over `rsi_oversold` + `pead_drift_window`
  - `<DistanceRule>` over `distance_to_52w_high` (the sweet-spot use case)
  - `<RegimeRule>` over `adx_regime` + `ttm_squeeze`
  - `<DivergenceRule>` over `rsi_bullish_divergence` + `macd_bearish_divergence`
- The KB-lookup endpoint now meaningfully discriminates between templates based on the user's composition shape — composer's recommended-defaults panel becomes more accurate.

---

## 9. Data-source coverage audit (READ BEFORE PR-DRAFTING)

A late-stage question from Jimmy (2026-06-12) flagged that the v2 spec assumed Alpha Vantage coverage without auditing it. Here's the honest map of what each new primitive needs and whether we have the data.

### 9.1 What we already fetch

Per `apps/api/app/services/alpha_vantage.py` and the FMP wiring in `financial_validation_service.py`, we have:

| Source | Currently used for | Endpoint signature |
|---|---|---|
| **AV TIME_SERIES_DAILY_ADJUSTED** | All daily OHLCV | `fetch_daily_adjusted(symbol)` |
| **AV TIME_SERIES_INTRADAY** | Intraday bars (PRD-16c) | `fetch_intraday_bars(symbol, interval)` |
| **AV technical-indicator family** | ~30 indicators (SMA/EMA/MACD/RSI/BBANDS/STOCH/ADX/ATR/OBV/etc) | `fetch_technical_indicator(symbol, function, ...)` |
| **AV NEWS_SENTIMENT** | Sentiment scores | wired via `alpha_vantage_news_provider.py` |
| **AV TREASURY_YIELD / CPI** | Macro | shipped |
| **AV WTI / COPPER / WHEAT** | Commodity | shipped |
| **FMP fundamentals** | `fcf_yield`, `book_to_market`, `ebitda_ev`, `f_score`, P/E, P/B, buyback yield | `financial_validation_service.py` |

### 9.2 Coverage map — every v2 primitive

Categorical column key:
- **✅ Local** — computable from data we already fetch; no new endpoint
- **🟢 New endpoint, AV/FMP has it** — needs wiring; data exists
- **🟡 Approximation** — proxy required because true metric isn't on AV/FMP
- **🔴 Not available** — would need a new data provider

| Family | New primitive(s) | Coverage | Notes |
|---|---|---|---|
| MACD | All 5 derivatives | ✅ Local | Computed from `macd` line + signal line we already fetch |
| RSI | All 7 derivatives | ✅ Local | Computed from `rsi` value series |
| Bollinger | All 7 derivatives (%B, BBW, squeeze, fire, walk, tag×2) | ✅ Local | %B/BBW are simple algebra over BB outputs |
| ADX / DMI | `adx_regime`, `adx_rising`, `di_cross_bullish/bearish` | ✅ Local | AV `function=PLUS_DI` and `MINUS_DI` already callable; needs new pass-through methods |
| MA | `price_above_ma`, `price_ma_cross_up/down`, `golden_cross`, `death_cross`, `ma_slope_positive` | ✅ Local | Computed from existing SMA/EMA series + close |
| Stochastic | `stoch_k_d_cross`, `stoch_oversold_cross_up`, `stoch_overbought_cross_down` | ✅ Local | AV STOCH returns both `SlowK` and `SlowD` already |
| **52-week extrema** | All 7 (distance, ratio, breakout, zone, days_since) | ✅ Local | Pure rolling max/min over daily bars |
| Volume — RVOL family | `rvol`, `rvol_surge` | ✅ Local | Volume / rolling mean of volume |
| Volume — OBV divergence | `obv_divergence_bullish/bearish` | ✅ Local | OBV already fetched; peak-trough detection local |
| Volume — Anchored VWAP | `anchored_vwap`, `distance_to_anchored_vwap`, `price_above_anchored_vwap` | ✅ Local + 🟢 anchor source | VWAP computation is local. The *anchor date* needs to come from somewhere — for earnings-anchored, see PEAD row below |
| Volatility — Chandelier | All 3 (long/short/breach) | ✅ Local | ATR already fetched; rolling HH/LL local |
| Volatility — Supertrend | All 3 (line/flip/above_price) | ✅ Local | hl2 + ATR + state machine, local |
| Volatility — TTM Squeeze | `ttm_squeeze`, `ttm_squeeze_fire` | ✅ Local | Bollinger (have) ∩ Keltner (compute: SMA ± 1.5×ATR — both local) |
| Momentum — 12-1 single-symbol | `momentum_12_1`, `momentum_acceleration` | ✅ Local | Pure price-history math |
| Momentum — cross-sectional z-score | `momentum_12_1_zscore`, `momentum_composite_zscore` | ✅ Local | Cross-sectional means we need the *universe's* return data; we already maintain `SP500_TICKERS` so this is fine for equities. Other asset classes need universe definitions |
| **Events — PEAD signal** | `pead_signal` | 🟡 **Approximation** | AV's `EARNINGS` endpoint returns `surprise` + `surprisePercentage` per quarter, but **NOT the standard-error of historical analyst estimates**. True SUE requires that std-err. We approximate by computing trailing 8-quarter std-dev of `surprisePercentage` and dividing — that's not academically rigorous SUE, but it's the standard fallback when raw SUE isn't sourceable. Document this clearly |
| Events — PEAD drift window | `pead_drift_window` | 🟢 New endpoint | AV `function=EARNINGS` returns `reportedDate` per quarter. Wire a new `fetch_earnings_history(symbol)` method on the AV client. Cacheable monthly |
| Events — earnings dates | `days_to_earnings`, `days_since_earnings` | 🟢 New endpoint | AV `function=EARNINGS_CALENDAR&horizon=3month` (returns CSV). Wire a new `fetch_earnings_calendar()` method. Cacheable daily (universe-level fetch, not per-symbol) |
| Events — estimate revision cross | `estimate_revision_positive_cross` | ✅ Local | Extends shipped `estimate_revision_3m` (already in v1 catalog from FMP); just a sign-cross detector |
| Events — insider surge | `insider_net_buy_surge` | 🟢 New endpoint | AV `function=INSIDER_TRANSACTIONS` (Alpha Intelligence). **Confirmed included on our $49.99/75-RPM plan** (per AV premium docs — all Alpha Intelligence endpoints are part of base premium; only real-time market data is gated above $49.99). Wire `fetch_insider_transactions(symbol)` on the AV client; cache TTL 7 days |
| Candle structure — Heikin-Ashi | All 3 (trend / consecutive / color flip) | ✅ Local | Pure OHLC arithmetic |

**Summary**:
- **~58 of 65 new primitives are ✅ Local** — computed from data we already fetch. Zero new AV calls.
- **3 need new AV endpoint wiring** (EARNINGS, EARNINGS_CALENDAR, INSIDER_TRANSACTIONS) — all exist on AV and **all confirmed available on our $49.99/75-RPM plan**.
- **1 requires 🟡 approximation**: PEAD `pead_signal` true SUE → trailing-std proxy because AV doesn't expose analyst-estimate std-err. Document the proxy in catalog `long_description`.

### 9.3 New AV client methods to add in this PRD

Three new methods on `AlphaVantageClient` (apps/api/app/services/alpha_vantage.py):

```python
async def fetch_earnings_history(self, symbol: str) -> dict:
    """AV function=EARNINGS. Returns quarterlyEarnings array with
    reportedDate, reportedEPS, estimatedEPS, surprise, surprisePercentage.
    Cache TTL: 30 days (re-fetch only after a new quarter prints)."""

async def fetch_earnings_calendar(self, horizon: str = "3month") -> list[dict]:
    """AV function=EARNINGS_CALENDAR. CSV response — parse with csv.DictReader.
    Universe-level (not per-symbol). Cache TTL: 24 hours."""

async def fetch_insider_transactions(self, symbol: str) -> list[dict]:
    """AV function=INSIDER_TRANSACTIONS. Form 4 list.
    Confirmed available on our $49.99 premium tier (all Alpha Intelligence
    endpoints are bundled at the $49.99 level). Cache TTL: 7 days."""
```

No feature flag needed — the endpoint is on our plan. (Earlier draft included an `AV_INSIDER_TXN_ENABLED` flag; removed 2026-06-12 once AV plan was confirmed.)

### 9.4 Rate-limit budget impact

Our shipped Premium plan (presumably 75 req/min or 150 req/min — confirm with Jimmy before PR) handles v1's ~12 calls/symbol/day comfortably. The three new endpoints add minimal load:

| Endpoint | Frequency | Per-symbol? | Daily calls @ 1k-symbol universe |
|---|---|---|---|
| EARNINGS_CALENDAR | 1×/day | No | 1 |
| EARNINGS history | 1×/30 days | Yes | ~33/day amortized |
| INSIDER_TRANSACTIONS | 1×/7 days | Yes | ~143/day amortized |

At 75 req/min that's still <0.5% of the budget. No tier upgrade needed for v2.

### 9.5 What's genuinely blocked (not in v2 scope — flagged for transparency)

These are NOT in PRD-22b, but agents reading the v2 spec might ask: why no VIX term structure / put-call / short interest?

| Idiom | Status | Why |
|---|---|---|
| VIX term structure (front vs back month) | 🔴 Not on AV | Needs CBOE or Cboe Datashop. Separate PRD |
| Put-call ratio | 🔴 Not on AV | Needs options-data provider. Separate PRD |
| Short interest | 🔴 Not on AV (✅ on FMP for premium) | FMP has `/v4/stock_short_interest` — could ship if we upgrade FMP tier. Separate PRD |
| Days to cover | 🔴 Same as above | Derived from short interest + volume |
| Beta / factor exposures | 🟡 Compute locally from returns | Doable but cross-sectional infra needed. Separate PRD |
| Earnings call transcripts NLP | 🔴 Not on AV directly | Out of scope per user's 2026-06-08 decision (no NLP for now) |

The v2 spec §7 already flagged these as out of scope; this section says it more concretely.

---

*PRD drafted 2026-06-12. Cross-references: v2 spec at `/Quant Strategy/framework/signal_catalog_v2_spec.html` §3+§4, parent HANDOFF at `agent-system/plans/HANDOFF-livermore-signal-catalog-v2.md`, depends on PRD-22a. §9 data-source audit added 2026-06-12 in response to feasibility check.*
