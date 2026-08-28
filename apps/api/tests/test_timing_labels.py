"""PRD-43b §3.6 — the leakage boundary, and the guards that hold it.

The structural rule this file exists for: `setup_type` is decision-time
information and MAY compile into a live Rule; `timing_outcome` is retrospective
and NEVER may. A label that mixes them compiles into look-ahead bias, and the
failure is invisible at review time because the merged label reads perfectly
sensibly.
"""

from __future__ import annotations

import ast
import re
import inspect
from datetime import date, timedelta
from pathlib import Path

from app.services.backtester.signal_provider import get_signal_provider
from app.services.timing import classify
from app.services.timing.bars import BarSeries
from app.services.timing.classify import setup_type, timing_outcome
from app.services.timing.snapshot import TechnicalSnapshot, snapshot_at

TIMING_DIR = Path(classify.__file__).parent


def _snap(**values):
    return TechnicalSnapshot(on_date=date(2026, 1, 5), values=dict(values))


# ── the static guards (§6, mandatory) ───────────────────────────────────────


def test_the_classifier_module_imports_NO_markout_or_excursion_symbol():
    """MANDATORY. The setup classifier must be unable to see an outcome, and
    the cheapest durable enforcement is that the symbols are not in scope at
    all. A future edit that reaches for `mae` here fails this test before it
    can reach a user."""
    tree = ast.parse(Path(classify.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any(
        m.endswith(("timing.markout", "timing.excursion")) for m in imported
    ), sorted(imported)


def test_setup_type_takes_a_SNAPSHOT_and_nothing_else():
    """The boundary as a signature. `setup_type` cannot read an outcome even
    by accident, because there is no parameter through which one could arrive."""
    params = list(inspect.signature(setup_type).parameters)
    assert params == ["state"]


def test_an_outcome_may_read_a_setup_but_never_the_reverse():
    """`chased` is defined on `extended_momentum` fills. The dependency runs
    one way, and this pins the direction."""
    assert "entry_setup" in inspect.signature(timing_outcome).parameters
    src = inspect.getsource(setup_type)
    for label in classify.TIMING_OUTCOMES:
        assert label not in src, label


def test_thresholds_are_module_CONSTANTS_not_values_fitted_to_the_user():
    """A label fitted to the record it then describes is circular — it would
    always find what it was tuned on."""
    for name in (
        "RSI_ELEVATED", "RSI_DEPRESSED", "EXTENDED_ABOVE_SMA20",
        "STRONG_5D_RUN", "MATERIAL_MOVE", "PREMATURE_CAPTURE",
    ):
        assert isinstance(getattr(classify, name), float)


def test_no_timing_module_can_produce_a_MARKET_VALIDATION_claim():
    """MANDATORY (§4.4). This package measures one person's record. The
    strongest claim available to it is `tested_on_personal_record`; DSR, PBO
    and market-validation vocabulary describe a different population, and a
    market-shaped number computed from 42 personal episodes is the exact
    confusion 43d §0.5 exists to prevent.

    Scans CODE, not prose: identifiers, imports, and string literals that are
    not docstrings. A module is allowed to explain the rule in its docstring —
    an earlier draft of this test scanned raw text and failed on the package
    docstring that names the ban, which would have pushed the documentation
    out of the package to satisfy the guard.
    """
    banned = {"deflated_sharpe", "pbo", "validated"}

    def _docstring_nodes(tree):
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    out.add(id(body[0].value))
        return out

    for path in TIMING_DIR.glob("*.py"):
        tree = ast.parse(path.read_text())
        skip = _docstring_nodes(tree)
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                found.add(node.id.lower())
            elif isinstance(node, ast.Attribute):
                found.add(node.attr.lower())
            elif isinstance(node, ast.alias):
                found.update(node.name.lower().split("."))
                if node.asname:
                    found.add(node.asname.lower())
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.update(node.module.lower().split("."))
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
                  and id(node) not in skip):
                found.update(re.findall(r"[a-z_]+", node.value.lower()))
        leaked = banned & found
        assert not leaked, f"{path.name} emits {sorted(leaked)}"


# ── setup_type fires on its own fixture and nothing else ────────────────────


def test_each_setup_fires_on_its_threshold_fixture():
    assert setup_type(_snap(
        rsi14=75.0, distance_from_sma20=0.15, return_5d=0.08,
        close_over_sma50=1.2)) == "extended_momentum"

    assert setup_type(_snap(
        distance_from_20d_high=-0.001, relative_volume=2.0,
        close_over_sma50=1.05, distance_from_sma20=0.02)) == "breakout"

    assert setup_type(_snap(
        close_over_sma50=1.05, distance_from_sma20=0.01,
        distance_from_20d_high=-0.08, rsi14=52.0)) == "pullback"

    assert setup_type(_snap(
        rsi14=22.0, distance_from_sma20=-0.09, distance_from_sma50=-0.14,
        close_over_sma50=0.86)) == "oversold"

    assert setup_type(_snap(
        close_over_sma50=1.06, distance_from_sma20=0.05,
        distance_from_20d_high=-0.04, rsi14=58.0)) == "trend_continuation"


def test_a_fill_matching_nothing_is_None_and_never_other():
    """`None` is not a category. A wide `other` bucket is how a taxonomy stops
    being falsifiable — and on the first real account 41 of 68 episodes matched
    nothing, with a BETTER win rate than any named setup. That is a signal the
    taxonomy deserves review, not a licence to widen it."""
    assert setup_type(_snap(rsi14=50.0, close_over_sma50=0.99,
                            distance_from_sma20=-0.01)) is None
    assert "other" not in (classify.SETUP_TYPES or ())


def test_a_snapshot_with_no_data_classifies_as_None_rather_than_guessing():
    assert setup_type(TechnicalSnapshot()) is None


# ── timing_outcome, and the sign convention that inverts every exit label ───


def test_chased_requires_the_setup_AND_the_bad_near_term_move():
    assert timing_outcome(
        entry_markouts={1: -0.04, 3: -0.05, 5: -0.06},
        entry_setup="extended_momentum") == "chased"
    # Same move, different setup — not a chase.
    assert timing_outcome(
        entry_markouts={1: -0.04, 3: -0.05, 5: -0.06},
        entry_setup="pullback") != "chased"


def test_early_entry_is_a_bad_week_inside_a_good_month():
    assert timing_outcome(
        entry_markouts={1: -0.04, 3: -0.05, 5: -0.04, 20: 0.09},
        entry_setup="pullback") == "early_entry"


def test_exit_markouts_are_read_as_NEGATED_so_labels_do_not_invert():
    """The engine negates exit markouts everywhere — a stock rising after you
    sell is a bad exit and reads NEGATIVE. A classifier that treats them as
    raw returns inverts every exit label while still producing plausible
    output, which is why this is pinned rather than trusted."""
    # Stock rose 8% after the sale -> exit markouts are −0.08.
    rose = {1: -0.06, 3: -0.08, 5: -0.08, 20: -0.09}
    assert timing_outcome(
        exit_markouts=rose, mae=-0.09, realised_return=-0.02) == "panic_exit"
    # Stock FELL after the sale -> exit markouts positive -> not a panic.
    fell = {1: 0.06, 3: 0.08, 5: 0.08, 20: 0.09}
    assert timing_outcome(
        exit_markouts=fell, mae=-0.09, realised_return=-0.02) != "panic_exit"


def test_premature_exit_needs_a_winner_that_left_most_of_the_move_behind():
    assert timing_outcome(
        exit_markouts={1: -0.05, 3: -0.06, 5: -0.07},
        mfe=0.20, realised_return=0.05) == "premature_exit"


def test_efficient_stop_is_a_loss_that_kept_falling():
    assert timing_outcome(
        exit_markouts={20: 0.12}, realised_return=-0.06) == "efficient_stop"


def test_an_episode_matching_nothing_has_no_outcome_label():
    assert timing_outcome(
        entry_markouts={1: 0.001, 3: 0.002, 5: 0.001, 20: 0.004},
        exit_markouts={1: 0.0, 3: 0.0, 5: 0.0, 20: 0.0},
        mae=-0.01, mfe=0.02, realised_return=0.015) is None


# ── the snapshot reads the CATALOG, never a second implementation ───────────


def test_snapshot_indicators_come_from_the_catalog_provider_itself():
    """§6: asserted against the provider, not against a re-derivation. A second
    RSI in this repo would drift from the one the backtester runs, so a rule
    discovered here would be tested against a different indicator than the one
    it compiles into."""
    rows, d, price = [], date(2025, 1, 1), 100.0
    for i in range(320):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        price *= 1.004 if i % 3 else 0.994
        rows.append({"trading_date": d, "open": price, "high": price * 1.01,
                     "low": price * 0.99, "close": price, "volume": 1_000_000,
                     "split_coefficient": 1.0})
        d += timedelta(days=1)
    series = BarSeries.from_rows("NVDA", rows)
    snap = snapshot_at(series, series.dates[-1])

    frame = series.frame()
    for key, provider, params in (
        ("rsi14", "rsi", {"period": 14}),
        ("atr14", "atr", {"period": 14}),
    ):
        base = get_signal_provider(provider)
        want = type(base).with_params(**params)._compute(frame).iloc[-1]
        assert snap.get(key) is not None
        assert abs(snap.get(key) - float(want)) < 1e-9, key


def test_an_unavailable_feature_returns_None_WITH_A_REASON_never_a_proxy():
    """VIX coverage in `price_bars` is unverified. Absent is a stated reason;
    substituting a proxy would put a number in the field that looks like a
    measurement and is not."""
    rows, d = [], date(2026, 1, 5)
    for _ in range(30):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        rows.append({"trading_date": d, "open": 100.0, "high": 100.0,
                     "low": 100.0, "close": 100.0, "volume": 1_000_000,
                     "split_coefficient": 1.0})
        d += timedelta(days=1)
    snap = snapshot_at(BarSeries.from_rows("NVDA", rows), rows[-1]["trading_date"])
    assert snap.get("vix") is None
    assert snap.unavailable["vix"] == "no_vix_bars"
    assert snap.unavailable["benchmark_trend20"] == "no_benchmark_bars"
    # sma200 cannot exist on 30 bars, and says so rather than using what it has.
    assert snap.get("close_over_sma200") is None
    assert snap.unavailable["close_over_sma200"] == "insufficient_history"


def test_the_retired_price_band_remedy_is_gone_from_the_router():
    """PRD-43b §3.7 retires `price_band` in this PR.

    It shipped in #353 and routed to a tool the packet no longer plans — the
    band is demoted to a ticket reference (§3.8). Offering someone a remedy
    that does not exist is worse than offering none, because the whole point
    of the remedy field is that a diagnosis without one is just a verdict.

    Scans emitted CODE, not prose: a comment recording why the key was retired
    is exactly the kind of thing that should survive, and a raw text scan would
    force it to be deleted to stay green.
    """
    api = Path(classify.__file__).resolve().parents[3]
    hits = []
    for path in (api / "app").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            emitted = (
                (isinstance(node, ast.Constant) and node.value == "price_band")
                or (isinstance(node, ast.Name) and node.id == "price_band")
                or (isinstance(node, ast.Attribute) and node.attr == "price_band")
            )
            if emitted:
                hits.append(f"{path.relative_to(api)}:{getattr(node, 'lineno', '?')}")
    assert not hits, hits
