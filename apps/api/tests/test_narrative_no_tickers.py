"""Market Pulse narrative — no tickers, real index levels.

SYMPTOM (live on the home page, 2026-08-09, the hour the LLM was switched on):

    "Technology drove gains today with the Nasdaq rising 1.17%, led by XLK's
     1.42% increase."

Two defects in one clause.

ROOT CAUSE, both in `_build_user_prompt`:

1. Every line led with a ticker — `XLK Technology: +1.42%` — so the model
   quoted one. Nobody reading a market recap should meet `XLK`.
2. The INDICES block fed `QQQ (NASDAQ 100)`. QQQ moved 1.17%; the Nasdaq
   Composite moved 1.30%. The model read the name and wrote "the Nasdaq",
   getting both the instrument and the index wrong.

FIX: send names, never symbols — a model can't quote a ticker it never saw,
which is stronger than asking it not to. And send real `^GSPC`/`^IXIC`/`^DJI`
levels; without them the ETFs are labelled AS ETFs so the same mistake can't
be made silently.
"""
from __future__ import annotations

from app.services.market_pulse_narrative_service import (
    _NARRATIVE_INDICES,
    _SYSTEM_PROMPT,
    _build_user_prompt,
)

SNAPSHOT = {
    "indices": [
        {"symbol": "SPY", "name": "S&P 500", "price": 655.1, "perf_1d": 0.006115},
        {"symbol": "QQQ", "name": "NASDAQ 100", "price": 723.03, "perf_1d": 0.011726},
        {"symbol": "DIA", "name": "Dow Jones", "price": 441.2, "perf_1d": 0.002657},
    ],
    "sectors": [
        {"symbol": "XLK", "name": "Technology", "perf_1d": 0.0142, "cmf_20": 0.19},
        {"symbol": "XLE", "name": "Energy", "perf_1d": -0.008, "cmf_20": -0.05},
    ],
    "macro": [
        {"symbol": "VXX", "label": "VIX / Volatility", "price": 14.9, "perf_1d": -0.0165},
    ],
}

INDEX_QUOTES = {
    "^GSPC": {"price": 7757.64, "change_percent": 0.62},
    "^IXIC": {"price": 26690.62, "change_percent": 1.30},
    "^DJI": {"price": 54036.93, "change_percent": 0.28},
}

TICKERS = ("XLK", "XLE", "QQQ", "SPY", "DIA", "VXX")


# ── no tickers ──────────────────────────────────────────────────────────────


def test_no_ticker_reaches_the_model():
    """The strong form of the fix: it can't quote what it never saw."""
    prompt = _build_user_prompt(SNAPSHOT, index_quotes=INDEX_QUOTES)
    for t in TICKERS:
        assert t not in prompt, f"{t} leaked into the prompt"


def test_no_ticker_in_the_etf_fallback_either():
    """The fallback branch is the one that runs when the quote fetch fails —
    exactly when nobody is looking."""
    prompt = _build_user_prompt(SNAPSHOT, index_quotes=None)
    for t in TICKERS:
        assert t not in prompt, f"{t} leaked into the fallback prompt"


def test_sector_names_survive():
    prompt = _build_user_prompt(SNAPSHOT, index_quotes=INDEX_QUOTES)
    assert "Technology" in prompt and "Energy" in prompt


def test_system_prompt_forbids_tickers_explicitly():
    """Belt as well as braces: the data can't carry one, and the instruction
    says not to write one."""
    assert "NEVER write a ticker symbol" in _SYSTEM_PROMPT
    assert "XLK" in _SYSTEM_PROMPT  # named as the counter-example


# ── real index levels ───────────────────────────────────────────────────────


def test_real_index_levels_are_used_when_supplied():
    prompt = _build_user_prompt(SNAPSHOT, index_quotes=INDEX_QUOTES)
    assert "26,690.62" in prompt
    assert "Nasdaq Composite" in prompt
    # The ETF's price and its move must not be anywhere near the index block.
    assert "723.03" not in prompt
    assert "+1.17%" not in prompt


def test_the_index_percentage_is_the_index_not_the_etf():
    """The exact defect: QQQ +1.17% was reported as "the Nasdaq rising
    1.17%" when the Nasdaq did +1.30%."""
    prompt = _build_user_prompt(SNAPSHOT, index_quotes=INDEX_QUOTES)
    assert "+1.30%" in prompt
    assert "1.17" not in prompt


def test_fallback_labels_etfs_as_etfs():
    """When the quote fetch fails we degrade, but we must never let the model
    call an ETF by its index's name again."""
    prompt = _build_user_prompt(SNAPSHOT, index_quotes=None)
    assert "ETF" in prompt
    assert "describe as ETFs, not as the index" in prompt


def test_narrative_index_list_is_the_real_indices():
    syms = [s for s, _ in _NARRATIVE_INDICES]
    assert syms == ["^GSPC", "^IXIC", "^DJI"]
    assert all(s.startswith("^") for s in syms)


def test_missing_one_index_quote_skips_that_row_not_the_block():
    partial = {"^GSPC": INDEX_QUOTES["^GSPC"]}
    prompt = _build_user_prompt(SNAPSHOT, index_quotes=partial)
    assert "S&P 500" in prompt
    assert "7,757.64" in prompt
    # Nasdaq simply doesn't appear rather than appearing empty or as its ETF.
    assert "Nasdaq Composite" not in prompt
