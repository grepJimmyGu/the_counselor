# PRD-22a: Signal Catalog v2 — Semantics Layer + Schema Fields

**Status**: Ready to build
**Phase**: Custom Mode v2 (Signal Library upgrade)
**Depends on**: PRD-16a (shipped) — extends the existing `SignalPrimitive` schema and catalog.
**Blocks**: PRD-22b (consumes the new fields when authoring new primitives); PRD-22c (consumes `output_kind` for composer dispatch).
**Effort**: ~1 week, single owner
**Owner**: TBD
**Source spec**: [`/Quant Strategy/framework/signal_catalog_v2_spec.html`](../../Quant%20Strategy/framework/signal_catalog_v2_spec.html) — §2 (semantics layer), §5 (schema implications), §7 (Slice A)

---

## 🤖 Coding-agent kickoff prompt

```
You are working in the Livermore AI repo (apps/api + apps/web). Read CLAUDE.md
first (auto-loaded). Then read agent-system/plans/HANDOFF-livermore-signal-catalog-v2.md.

Goal: lay the semantic foundation for the v2 signal catalog. Three deliverables:

  1. Add three additive fields to `SignalPrimitive` in apps/api/app/schemas/signal_primitive.py:
     - output_kind: OutputKind = OutputKind.VALUE (new 7-value enum)
     - output_channels: list[str] = ["value"]   # single-channel default
     - composes: list[str] = []                  # standalone default

  2. Backfill EVERY existing v1 primitive in apps/api/app/data/signal_primitives.py
     with the correct output_kind. ~50 are VALUE; a handful are LEVEL/EVENT/CROSS.
     Source of truth: signal_catalog_v2_spec.html §3 — every v1 family has its
     correct kind listed.

  3. Update GET /api/signal-primitives to return the new fields in the response
     payload. The catalog browser frontend reads them (PRD-22c lights this up).

PREREQUISITES (must be on main):
  - PRD-16a — the existing SignalPrimitive schema + catalog (shipped).

OUT OF SCOPE for this PRD:
  - The 65 new primitives — PRD-22b.
  - The composer rule-builder kind-dispatch — PRD-22c.
  - KB-lookup Jaccard enrichment — PRD-22b.
  - Any backtest behavior change — this PRD is provably a no-op at runtime.

Context to read in order:
  - /Quant Strategy/framework/signal_catalog_v2_spec.html §2 + §5
  - apps/api/app/schemas/signal_primitive.py (the v1 schema)
  - apps/api/app/data/signal_primitives.py (the v1 catalog, 1232 LOC)

DEFINITION OF DONE:
  - Three new fields on SignalPrimitive with backward-compatible defaults
  - All ~55 v1 catalog entries backfilled with output_kind (some VALUE, some not)
  - GET /api/signal-primitives returns the new fields
  - `pytest -q` produces byte-identical output to main on every backtest test
  - `python3 -c "from app.main import app; print(len(app.routes))"` resolves cleanly
  - PR description includes the per-family kind backfill table
```

---

## 1. The problem

PRD-16a's `SignalPrimitive` schema assumes every primitive emits a scalar value. The composer (PRD-16b) renders one rule shape: `[primitive] [< | >] [threshold]`. This works for `RSI < 30` but fails to model:

- **Events**: `MACD signal-line cross`, `bb_squeeze_fire`, `golden_cross` — true only at the bar of transition, not persistent.
- **Levels**: `rsi_oversold`, `price_above_200dma` — persistent boolean condition.
- **Regimes**: `adx_regime` (trending|ranging), `vol_regime` (high|low) — categorical classifier.
- **Distances**: `distance_to_52w_high` — percentage gap consumed as a *range* (e.g., "between 2% and 25% below high"), not a threshold.
- **Crosses**: `di_cross_bullish`, `stoch_k_d_cross` — line A crosses line B, direction-aware.
- **Divergences**: `rsi_bullish_divergence` — pattern detection over a lookback window.

The fix is to make the semantic kind explicit on every primitive. The composer then dispatches to a kind-specific rule-builder widget (PRD-22c). This PRD ships ONLY the schema layer — no widgets, no new primitives. Zero behavior change.

---

## 2. Design constraints

1. **Additive only.** No existing field is renamed or removed. All new fields have backward-compatible defaults — every v1 primitive omitting the new fields gets the equivalent of `output_kind=VALUE`, `output_channels=["value"]`, `composes=[]`.

2. **Backfill is part of this PRD.** Shipping the schema fields without backfilling existing primitives would mean PRD-22c (composer kind-dispatch) sees the default `VALUE` for everything and renders the v1 widget for primitives that should be kind-specific. The backfill table is in the v2 spec §3.

3. **No runtime behavior change.** The fields are metadata read by the composer and the KB-lookup endpoint. The backtest engine and existing `SignalProvider` impls don't look at them. Proof of this: every backtest produces byte-identical output to `main`.

4. **`output_channels` defaults to `["value"]` for forward compat.** Multi-channel primitives (MACD, BB, ADX, Stoch) declare their channels explicitly; PRD-22b will use this when authoring derived primitives via `composes`.

5. **Python 3.9 compat.** Use `Optional[X]`, `List[X]`. The enum uses `str, Enum` for JSON serialization (matching the existing `SignalCategory` pattern).

---

## 3. Implementation

### 3.1 Schema additions

```python
# apps/api/app/schemas/signal_primitive.py

class OutputKind(str, Enum):
    """Semantic shape of the signal a primitive emits at each timestep.

    Drives composer rule-builder dispatch (PRD-22c) and KB-lookup Jaccard
    enrichment (PRD-22b). Defaults to VALUE for backward compat with v1.
    """

    VALUE = "value"
    """Scalar at each bar. Composer renders [primitive] [< | >] [threshold]."""

    EVENT = "event"
    """Boolean true ONLY at the bar of transition. No threshold input."""

    REGIME = "regime"
    """Categorical classifier (trending/ranging/etc). Single-select chip."""

    LEVEL = "level"
    """Boolean true WHILE a condition holds (persists). No threshold input."""

    DISTANCE = "distance"
    """Signed percentage gap. Range slider input (between min% and max%)."""

    CROSS = "cross"
    """EVENT specialization: line A crosses line B. Direction picker."""

    DIVERGENCE = "divergence"
    """Pattern: indicator swings disagree with price swings. Lookback + direction."""


class SignalPrimitive(BaseModel):
    # ... existing fields ...

    output_kind: OutputKind = OutputKind.VALUE
    """Semantic kind. v1 default = VALUE preserves backward compat."""

    output_channels: List[str] = Field(default_factory=lambda: ["value"])
    """Named channels emitted. Multi-channel primitives (MACD, BB, ADX) declare
    multiple. The default ["value"] matches v1 single-channel semantics."""

    composes: List[str] = Field(default_factory=list)
    """Parent primitive_ids this is derived from. Used by PRD-22b for derived
    primitives like macd_signal_cross (composes=["macd"]). Default = standalone."""
```

### 3.2 Catalog backfill (v1 → kind mapping)

Per v2 spec §3, the v1 primitives map to kinds as follows. **This table is the PR-review checklist** — every v1 primitive must have its `output_kind` set explicitly. Don't lazy-default to VALUE.

| v1 primitive | Correct kind | Channels (if not default) |
|---|---|---|
| `sma`, `ema`, `wma`, `dema`, `tema`, `kama` | VALUE | — |
| `ma_crossover` | CROSS | — |
| `macd` | VALUE | `["macd_line", "signal_line", "histogram"]` |
| `adx` | VALUE | `["adx", "plus_di", "minus_di"]` |
| `aroon`, `aroonosc`, `adxr` | VALUE | — |
| `sar`, `ht_trendline` | VALUE | — |
| `rsi`, `stochrsi`, `willr`, `cci`, `cmo` | VALUE | — |
| `stoch` | VALUE | `["k", "d"]` |
| `bbands` | VALUE | `["upper", "lower", "middle"]` |
| `mfi`, `ultosc` | VALUE | — |
| `roc`, `mom`, `trix`, `apo`, `ppo` | VALUE | — |
| `donchian_breakout` | EVENT | — |
| `time_series_momentum` | VALUE | — |
| `bop` | VALUE | — |
| `obv`, `ad`, `adosc`, `vwap`, `avg_dollar_volume` | VALUE | — |
| `atr`, `natr`, `trange`, `realized_vol` | VALUE | — |
| `vol_regime` | REGIME | — |
| All fundamental primitives (`fcf_yield`, `book_to_market`, `ebitda_ev`, `f_score`, `buyback_yield_ttm`) | VALUE | — |
| All sentiment primitives (`estimate_revision_3m`, `earnings_surprise`, `sentiment_score`, `insider_net_buy`, `analyst_rating_change`) | VALUE | — |
| All cross-sectional primitives (`rank_return_6m`, `rank_composite_score`, `sector_rotation_rank`, `pair_spread_zscore`) | VALUE | — |

**Summary**: ~50 of the 55 v1 primitives are VALUE. The 5 exceptions are `ma_crossover` (CROSS), `donchian_breakout` (EVENT), `vol_regime` (REGIME), plus the multi-channel declarations for `macd`, `adx`, `stoch`, `bbands`.

### 3.3 API surface

`GET /api/signal-primitives` already returns the full `SignalPrimitive` shape via Pydantic serialization. The new fields are automatically included once the schema accepts them. **No new endpoints.**

Frontend types (`apps/web/src/lib/contracts.ts`) need the matching TypeScript declarations:

```typescript
export type SignalOutputKind =
  | "value" | "event" | "regime" | "level" | "distance" | "cross" | "divergence";

export interface SignalPrimitive {
  // ... existing fields ...
  output_kind: SignalOutputKind;
  output_channels: string[];
  composes: string[];
}
```

---

## 4. Testing

### 4.1 Schema tests

```python
# apps/api/tests/test_signal_primitive_schema.py — NEW

def test_output_kind_defaults_to_value():
    p = SignalPrimitive(id="x", category=SignalCategory.TREND, family="X",
                       name="X", description="x", parameters=[],
                       asset_compat=["equity"], evidence_tier="A",
                       provider_impl="x", data_source="price")
    assert p.output_kind == OutputKind.VALUE
    assert p.output_channels == ["value"]
    assert p.composes == []


def test_output_kind_serializes_as_string():
    p = SignalPrimitive(..., output_kind=OutputKind.EVENT)
    assert p.model_dump()["output_kind"] == "event"
```

### 4.2 Catalog backfill tests

```python
def test_every_v1_primitive_has_explicit_output_kind():
    """No primitive should be relying on the default — explicit > implicit."""
    for p in SIGNAL_PRIMITIVES:
        # Inspecting via __init__ would not reveal whether it was set
        # explicitly; this test passes by construction once 3.2 backfill ships.
        assert p.output_kind is not None


def test_multi_channel_primitives_declare_channels():
    multi_channel = {"macd", "adx", "stoch", "bbands"}
    by_id = {p.id: p for p in SIGNAL_PRIMITIVES}
    for pid in multi_channel:
        assert len(by_id[pid].output_channels) > 1, f"{pid} missing channels"


def test_cross_event_regime_kinds_present():
    kinds = {p.output_kind for p in SIGNAL_PRIMITIVES}
    assert OutputKind.CROSS in kinds      # ma_crossover
    assert OutputKind.EVENT in kinds      # donchian_breakout
    assert OutputKind.REGIME in kinds     # vol_regime
```

### 4.3 No-regression backtest test

```python
def test_no_regression_against_main():
    """Every saved backtest fixture produces byte-identical output."""
    for fixture in load_backtest_fixtures():
        result = run_backtest(fixture)
        assert result == fixture.expected_result, f"Regression on {fixture.name}"
```

This is the critical test for PRD-22a — it proves the schema additions are a runtime no-op.

### 4.4 API contract test

```python
def test_catalog_endpoint_includes_new_fields(client):
    response = client.get("/api/signal-primitives")
    assert response.status_code == 200
    for entry in response.json():
        assert "output_kind" in entry
        assert "output_channels" in entry
        assert "composes" in entry
```

---

## 5. Pre-merge checklist

1. ✅ `cd apps/api && python3 -m pytest -q` — every existing test green; ~4 new tests added.
2. ✅ `cd apps/web && npm run build` — frontend types compile.
3. ✅ Static-import smoke test: `python3 -c "from app.main import app; print(len(app.routes))"`.
4. ✅ Backtest-regression test green — proves zero runtime behavior change.
5. ✅ `grep "| None" apps/api/app/schemas/signal_primitive.py apps/api/app/data/signal_primitives.py` — empty.
6. ✅ PR description includes the v1 backfill table from §3.2.
7. ✅ Branch follows `<agent>/feat/prd-22a-signal-semantics` convention.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| A v1 primitive's kind is wrong (e.g., should be EVENT, marked VALUE) | PR review by Jimmy against v2 spec §3 audit table |
| Multi-channel `output_channels` get renamed later, breaking saved strategies | Document the channel names as a public contract in v2 spec §3; never rename, only deprecate |
| `composes` field unused in PRD-22a creates dead code | Acceptable — PRD-22b is the immediate consumer, ~2 weeks behind |
| Frontend types drift from backend schema | Same `contracts.ts` discipline as PRD-13a — types-first |

---

## 7. Definition of done

- [ ] `OutputKind` enum shipped with 7 values
- [ ] Three fields (`output_kind`, `output_channels`, `composes`) on `SignalPrimitive` with backward-compatible defaults
- [ ] All ~55 v1 catalog entries backfilled per §3.2 table
- [ ] `GET /api/signal-primitives` returns the new fields
- [ ] Frontend `contracts.ts` updated with TypeScript types
- [ ] 4+ new tests (schema defaults, backfill coverage, multi-channel declarations, catalog endpoint contract)
- [ ] No-regression backtest test green
- [ ] PR merged to `main` with green CI
- [ ] Brick inventory updated in `HANDOFF-livermore-signal-catalog-v2.md` §5

---

## 8. Hand-off to next PRD

When PRD-22a is on `main`:

- **PRD-22b** can begin authoring the 65 new primitives, each declaring its `output_kind`, `output_channels`, and (for derived primitives) `composes`.
- **PRD-22c** can begin building the kind-dispatch rule-builder. The catalog already exposes `output_kind` for every primitive, so 22c's widgets light up immediately on v1 primitives that have a non-VALUE kind.

The v1 primitives with non-VALUE kinds — `ma_crossover`, `donchian_breakout`, `vol_regime` — become the first end-to-end test cases for PRD-22c's new widgets.

---

*PRD drafted 2026-06-12. Cross-references: v2 spec at `/Quant Strategy/framework/signal_catalog_v2_spec.html` §2+§5+§7, parent HANDOFF at `agent-system/plans/HANDOFF-livermore-signal-catalog-v2.md`.*
