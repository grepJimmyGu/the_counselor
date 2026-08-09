"""Daily share card — the injected payload.

Everything here is the half the model never writes: labels, figures, rankings,
the date stamp. Pure over a `DailyBrief`, so the whole shape is testable
without a DB, an LLM, or a render.
"""
from __future__ import annotations

from app.services.card_labels import EN, ZH
from app.services.daily_brief_service import (
    BriefMover,
    BriefQuote,
    BriefSector,
    DailyBrief,
)
from app.services.daily_card_service import (
    SECTOR_COLUMN_CAP,
    build_card_payload,
    injected_numbers,
    numeric_tokens,
)
from app.services.evaluation_scoring import ThreeDimensionalScore


def _brief(**over) -> DailyBrief:
    b = DailyBrief(as_of="2026-07-31T21:00:00")
    b.indices = [
        BriefQuote("^DJI", "Dow Jones", 44_500.12, 1.19),
        BriefQuote("^GSPC", "S&P 500", 7_757.64, 1.66),
        BriefQuote("^IXIC", "NASDAQ Composite", 26_690.62, 2.78),
    ]
    b.vix = BriefQuote("^VIX", "VIX", 14.90, -6.83)
    b.sectors = [
        BriefSector("Technology", 5.50, 0.19),
        BriefSector("Industrials", 1.00, 0.08),
        BriefSector("Financials", 0.60, 0.05),
        BriefSector("Real Estate", -1.40, -0.03),
        BriefSector("Healthcare", -1.64, -0.06),
        BriefSector("Consumer Staples", -2.16, -0.09),
        BriefSector("Communication", -2.70, -0.14),
    ]
    b.flow_into = BriefSector("Technology", 5.50, 0.19)
    b.flow_out_of = BriefSector("Communication", -2.70, -0.14)
    b.unusual = BriefMover("MSFT", "Microsoft", 15.51)
    for k, v in over.items():
        setattr(b, k, v)
    return b


SCORE = ThreeDimensionalScore(health=92, valuation=78, trend=90, final=87, label="Attractive")


# ── header ──────────────────────────────────────────────────────────────────


def test_date_stamp_matches_both_prompts():
    assert build_card_payload(_brief(), lang=EN).date_label == "26.7.31 · Friday"
    assert build_card_payload(_brief(), lang=ZH).date_label == "26.7.31 · 周五"


def test_masthead_and_disclaimer_switch_language():
    zh = build_card_payload(_brief(), lang=ZH)
    assert zh.masthead == "每日美股复盘 · Livermore"
    assert zh.disclaimer == "仅个人复盘记录，不构成任何投资建议。"


# ── indices ─────────────────────────────────────────────────────────────────


def test_index_labels_come_from_the_map_not_the_quote():
    """FMP returns "NASDAQ Composite"; the card says "Nasdaq" / 纳斯达克. The
    card's typography can't depend on an upstream string we don't control."""
    en = build_card_payload(_brief(), lang=EN)
    assert [s.label for s in en.indices] == ["Dow Jones", "S&P 500", "Nasdaq", "VIX"]
    zh = build_card_payload(_brief(), lang=ZH)
    assert [s.label for s in zh.indices] == ["道琼斯", "标普500", "纳斯达克", "VIX 恐慌指数"]


def test_figures_render_with_explicit_sign_and_two_decimals():
    en = build_card_payload(_brief(), lang=EN)
    dow = en.indices[0]
    assert dow.value == "44,500.12"
    assert dow.change == "+1.19%"


def test_vix_carries_no_direction_so_it_cannot_be_coloured():
    """"VIX -6.83%" is not good news the way "S&P +1.66%" is. Leaving
    `direction` None is what stops the renderer painting it green."""
    en = build_card_payload(_brief(), lang=EN)
    vix = en.indices[-1]
    assert vix.label.startswith("VIX")
    assert vix.change == "-6.83%"
    assert vix.direction is None
    assert en.indices[0].direction == "up"


# ── sectors ─────────────────────────────────────────────────────────────────


def test_winners_and_losers_split_by_sign():
    en = build_card_payload(_brief(), lang=EN)
    assert [s.label for s in en.winners] == ["Technology", "Industrials", "Financials"]
    assert "Technology" not in [s.label for s in en.losers]


def test_losers_read_worst_first():
    """A losers column ordered best-to-worst buries its own headline."""
    en = build_card_payload(_brief(), lang=EN)
    assert [s.label for s in en.losers][0] == "Communication"
    assert en.losers[0].value == "-2.70%"


def test_sector_columns_are_capped():
    b = _brief()
    b.sectors = [BriefSector(f"S{i}", -float(i), None) for i in range(1, 9)]
    p = build_card_payload(b, lang=EN)
    assert len(p.losers) == SECTOR_COLUMN_CAP


def test_sectors_are_translated_from_the_map():
    zh = build_card_payload(_brief(), lang=ZH)
    assert [s.label for s in zh.winners] == ["科技", "工业", "金融"]
    assert zh.losers[0].label == "通信服务"


# ── money flow ──────────────────────────────────────────────────────────────


def test_money_flow_names_are_translated_and_carry_their_figures():
    zh = build_card_payload(_brief(), lang=ZH)
    assert zh.flow_from == "通信服务"
    assert zh.flow_to == "科技"
    assert zh.flow_from_value == "-0.14"
    assert zh.flow_to_value == "0.19"


def test_flow_absent_when_the_brief_has_no_direction():
    p = build_card_payload(_brief(flow_into=None, flow_out_of=None), lang=EN)
    assert p.flow_from is None and p.flow_to is None


# ── stock of the day ────────────────────────────────────────────────────────


def test_stock_of_the_day_is_the_unusual_mover_with_its_score():
    p = build_card_payload(_brief(), lang=EN, score=SCORE)
    assert p.stock.symbol == "MSFT"
    assert p.stock.change == "+15.51%"
    assert (p.stock.score_health, p.stock.score_valuation, p.stock.score_trend) == (92, 78, 90)


def test_no_stock_module_on_a_quiet_day():
    """The brief withholds `unusual` below the threshold. The card must drop
    the module rather than promote a +2% name to "stock of the day"."""
    p = build_card_payload(_brief(unusual=None), lang=EN, score=SCORE)
    assert p.stock is None


def test_stock_renders_without_a_score_rather_than_faking_one():
    p = build_card_payload(_brief(), lang=EN, score=None)
    assert p.stock is not None
    assert p.stock.score_health is None


# ── the hallucination guard ─────────────────────────────────────────────────


def test_numeric_tokens_normalises_sign_and_separators():
    """Prose carries the sign in words — "VIX fell 6.83%" is correct English
    for a -6.83% move — and "26690.62" is the same figure as "26,690.62".
    Comparing raw strings would reject well-written copy as a hallucination,
    which is worse than useless: it trains whoever hits it to disable the
    guard."""
    got = numeric_tokens("Nasdaq rose 2.78% to 26,690.62; VIX fell 6.83%")
    assert "2.78" in got
    assert "26690.62" in got  # separators stripped
    assert "6.83" in got      # matches the injected "-6.83%"


def test_the_guard_does_not_claim_to_check_direction():
    """Documented limit: deciding which figure a sentence refers to is
    parsing, not validation. A wrong direction word passes — the prompt
    supplies direction, and the card is reviewable."""
    nums = injected_numbers(build_card_payload(_brief(), lang=EN, score=SCORE))
    wrong_direction = "VIX rose 6.83%"
    assert all(t in nums for t in numeric_tokens(wrong_direction))


def test_injected_numbers_covers_everything_the_card_shows():
    """The generation step checks the model's prose against this set. Anything
    missing here would flag a legitimate figure as a hallucination; anything
    extra would let a real one through."""
    nums = injected_numbers(build_card_payload(_brief(), lang=EN, score=SCORE))
    for expected in ("1.19", "1.66", "2.78", "6.83", "5.50", "2.70", "15.51", "92", "78", "90"):
        assert expected in nums, f"{expected} is on the card but not in the guard set"


def test_guard_set_would_catch_an_invented_figure():
    nums = injected_numbers(build_card_payload(_brief(), lang=EN, score=SCORE))
    invented = [t for t in numeric_tokens("Microsoft jumped 18.4% on the day") if t not in nums]
    assert invented == ["18.4"]
