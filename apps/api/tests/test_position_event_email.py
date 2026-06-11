"""PRD-16c-4 — Position-event email template tests.

Verifies the three primary trigger types render with the right copy,
color, action label, and CAN-SPAM/compliance scaffolding.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.emails.position_event import (
    PositionEventPayload,
    _TRIGGER_META,
    _trigger_meta,
    render_position_event,
)


def _user(uid: str = "user-1") -> SimpleNamespace:
    """Minimal duck-typed User — only `id` is touched by the renderer."""
    return SimpleNamespace(id=uid)


def _payload(**overrides) -> PositionEventPayload:
    defaults = dict(
        strategy_name="SpaceX Active",
        strategy_id="strat-123",
        symbol="AAPL",
        trigger_type="stop_hit",
        tier_label="Stop",
        entry_price=100.0,
        current_price=88.5,
        pct_change=-0.115,
        action_taken="sold_all",
        shares_sold=10.0,
        shares_remaining=0.0,
        fired_at=datetime(2026, 6, 9, 14, 30, 0),
    )
    defaults.update(overrides)
    return PositionEventPayload(**defaults)


# ── _trigger_meta lookup ────────────────────────────────────────────────────


def test_trigger_meta_known_types() -> None:
    assert _trigger_meta("stop_hit")["color"] == "#ef4444"
    assert _trigger_meta("tp1_hit")["color"] == "#22c55e"
    assert _trigger_meta("tp2_hit")["color"] == "#10b981"


def test_trigger_meta_unknown_falls_back_to_neutral() -> None:
    meta = _trigger_meta("tp5_hit")
    assert meta["color"] == "#0ea5e9"  # neutral
    assert "tp5 hit" in meta["verb"]


def test_three_canonical_trigger_types_registered() -> None:
    """Pre-commit guard — the canonical SpaceX ladder names are present."""
    assert {"stop_hit", "tp1_hit", "tp2_hit"}.issubset(_TRIGGER_META.keys())


# ── Subject lines ───────────────────────────────────────────────────────────


def test_stop_subject_has_emoji_and_pct() -> None:
    out = render_position_event(_user(), _payload())
    assert "🛑" in out["subject"]
    assert "AAPL" in out["subject"]
    assert "-11.5%" in out["subject"]
    assert "SpaceX Active" in out["subject"]


def test_tp1_subject_uses_green_emoji() -> None:
    out = render_position_event(_user(), _payload(
        trigger_type="tp1_hit", tier_label="TP1",
        entry_price=100.0, current_price=115.0, pct_change=0.15,
        action_taken="sold_fraction", shares_sold=3.33, shares_remaining=6.67,
    ))
    assert "🎯" in out["subject"]
    assert "+15.0%" in out["subject"]
    assert "TP1" in out["subject"]


def test_tp2_subject_uses_check_emoji() -> None:
    out = render_position_event(_user(), _payload(
        trigger_type="tp2_hit", tier_label="TP2",
        entry_price=100.0, current_price=130.0, pct_change=0.30,
        action_taken="sold_all", shares_sold=6.67, shares_remaining=0.0,
    ))
    assert "✅" in out["subject"]
    assert "+30.0%" in out["subject"]


# ── HTML content ────────────────────────────────────────────────────────────


def test_html_contains_entry_and_current_prices() -> None:
    out = render_position_event(_user(), _payload())
    assert "$100.00" in out["html"]
    assert "$88.50" in out["html"]
    assert "Entry" in out["html"]
    assert "Current" in out["html"]


def test_html_action_line_suggestion_sell_all() -> None:
    """Default (is_suggestion=True) frames as advice, not a fait accompli."""
    out = render_position_event(_user(), _payload(
        trigger_type="stop_hit", action_taken="sold_all",
        shares_sold=10.0, shares_remaining=10.0,
    ))
    assert "Suggested action" in out["html"]
    assert "suggests closing the position" in out["html"]
    assert "Execute in your brokerage" in out["html"]
    # Never claims Livermore sold.
    assert "Closed full position" not in out["html"]


def test_html_action_line_suggestion_sell_fraction() -> None:
    out = render_position_event(_user(), _payload(
        trigger_type="tp1_hit", action_taken="sold_fraction",
        shares_sold=3.33, shares_remaining=10.0,
    ))
    assert "suggests selling 3.33 of your 10 shares" in out["html"]
    assert "Suggested action" in out["html"]


def test_html_action_line_past_tense_when_not_suggestion() -> None:
    """is_suggestion=False keeps the replay/backtest 'sold' framing."""
    out = render_position_event(_user(), _payload(
        trigger_type="tp1_hit", action_taken="sold_fraction",
        shares_sold=3.33, shares_remaining=6.67, is_suggestion=False,
    ))
    assert "Sold 3.33 shares" in out["html"]
    assert "6.67 remaining" in out["html"]
    assert "Action taken" in out["html"]


# ── Compliance + CAN-SPAM ──────────────────────────────────────────────────


def test_html_includes_compliance_footer() -> None:
    out = render_position_event(_user(), _payload())
    assert "Not investment advice" in out["html"]
    assert "Past performance does not guarantee future results" in out["html"]
    assert "Livermore does not place trades" in out["html"]


def test_text_includes_compliance_footer() -> None:
    out = render_position_event(_user(), _payload())
    assert "Not investment advice" in out["text"]


def test_html_includes_strategy_scoped_unsub_link() -> None:
    out = render_position_event(_user(), _payload(strategy_id="strat-xyz"))
    # Token-bearing URL — exact format is opaque but the route exists.
    assert "/api/email/unsub?token=" in out["html"]
    assert "Unsubscribe from this strategy" in out["html"]


def test_html_includes_mark_as_executed_cta() -> None:
    out = render_position_event(_user(), _payload(strategy_id="strat-xyz"))
    assert "/strategies/strat-xyz?action=executed" in out["html"]
    assert "I executed this" in out["html"]


# ── Renderer contract: returns {subject, html, text} ───────────────────────


def test_renderer_returns_three_keys() -> None:
    out = render_position_event(_user(), _payload())
    assert set(out.keys()) == {"subject", "html", "text"}
    assert all(isinstance(v, str) for v in out.values())
    assert all(v for v in out.values())  # non-empty
