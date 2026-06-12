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

*PRD drafted 2026-06-12. Cross-references: v2 spec at `/Quant Strategy/framework/signal_catalog_v2_spec.html` §3+§4, parent HANDOFF at `agent-system/plans/HANDOFF-livermore-signal-catalog-v2.md`, depends on PRD-22a.*
