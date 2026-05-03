"""Tests for DataQualityService check logic (no DB required — mocked)."""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.data_quality import DataQualityReport
from app.services.data_quality_service import DataQualityService

TODAY = date.today()
YEAR_AGO = TODAY - timedelta(days=365)


def _make_service():
    svc = DataQualityService.__new__(DataQualityService)
    svc.price_data = MagicMock()
    svc.price_data.cache_svc = MagicMock()
    return svc


def _mock_cache(svc, *, bar_count, earliest, latest):
    svc.price_data.cache_svc.get_bar_count.return_value = bar_count
    svc.price_data.cache_svc.get_earliest_date.return_value = earliest
    svc.price_data.cache_svc.get_latest_date.return_value = latest


# ── No data ───────────────────────────────────────────────────────────────────

def test_no_data_returns_blocked():
    svc = _make_service()
    _mock_cache(svc, bar_count=0, earliest=None, latest=None)

    with patch.object(svc, "_compute_coverage", return_value={"adjusted_close": 0.0, "volume": 0.0, "missing_date_count": 0}):
        report = svc.check_symbol(MagicMock(), "FAKE")

    assert report.status == "blocked"
    assert report.row_count == 0
    assert len(report.blocking_errors) > 0


# ── Stale data ────────────────────────────────────────────────────────────────

def test_stale_data_returns_warning():
    svc = _make_service()
    stale_date = TODAY - timedelta(days=30)
    _mock_cache(svc, bar_count=500, earliest=YEAR_AGO, latest=stale_date)

    with patch.object(svc, "_compute_coverage", return_value={"adjusted_close": 1.0, "volume": 1.0, "missing_date_count": 0}), \
         patch.object(svc, "_check_price_jumps", return_value=None):
        report = svc.check_symbol(MagicMock(), "AAPL")

    assert report.status == "warning"
    assert any("stale" in w.lower() for w in report.warnings)


# ── Insufficient history ──────────────────────────────────────────────────────

def test_too_few_bars_returns_blocked():
    svc = _make_service()
    _mock_cache(svc, bar_count=10, earliest=TODAY - timedelta(days=15), latest=TODAY)

    with patch.object(svc, "_compute_coverage", return_value={"adjusted_close": 1.0, "volume": 1.0, "missing_date_count": 0}), \
         patch.object(svc, "_check_price_jumps", return_value=None):
        report = svc.check_symbol(MagicMock(), "TINY")

    assert report.status == "blocked"
    assert any("30" in e for e in report.blocking_errors)


# ── Low adjusted_close coverage ───────────────────────────────────────────────

def test_low_adj_close_coverage_blocked():
    svc = _make_service()
    _mock_cache(svc, bar_count=300, earliest=YEAR_AGO, latest=TODAY)

    with patch.object(svc, "_compute_coverage", return_value={"adjusted_close": 0.80, "volume": 1.0, "missing_date_count": 0}), \
         patch.object(svc, "_check_price_jumps", return_value=None):
        report = svc.check_symbol(MagicMock(), "BAD")

    assert report.status == "blocked"
    assert any("coverage" in e.lower() for e in report.blocking_errors)


# ── Low volume coverage ───────────────────────────────────────────────────────

def test_low_volume_coverage_warning():
    svc = _make_service()
    _mock_cache(svc, bar_count=300, earliest=YEAR_AGO, latest=TODAY)

    with patch.object(svc, "_compute_coverage", return_value={"adjusted_close": 1.0, "volume": 0.80, "missing_date_count": 0}), \
         patch.object(svc, "_check_price_jumps", return_value=None):
        report = svc.check_symbol(MagicMock(), "VOL")

    assert report.status == "warning"
    assert any("volume" in w.lower() for w in report.warnings)


# ── Suspicious price jump ─────────────────────────────────────────────────────

def test_suspicious_price_jump_warning():
    svc = _make_service()
    _mock_cache(svc, bar_count=300, earliest=YEAR_AGO, latest=TODAY)

    with patch.object(svc, "_compute_coverage", return_value={"adjusted_close": 1.0, "volume": 1.0, "missing_date_count": 0}), \
         patch.object(svc, "_check_price_jumps", return_value="Suspicious price move detected on 2024-01-15: 60.0% change."):
        report = svc.check_symbol(MagicMock(), "JUMP")

    assert report.status == "warning"
    assert any("suspicious" in w.lower() or "price move" in w.lower() for w in report.warnings)


# ── Clean data ────────────────────────────────────────────────────────────────

def test_clean_data_returns_ready():
    svc = _make_service()
    _mock_cache(svc, bar_count=500, earliest=YEAR_AGO, latest=TODAY)

    with patch.object(svc, "_compute_coverage", return_value={"adjusted_close": 1.0, "volume": 1.0, "missing_date_count": 0}), \
         patch.object(svc, "_check_price_jumps", return_value=None):
        report = svc.check_symbol(MagicMock(), "GOOD")

    assert report.status == "ready"
    assert len(report.blocking_errors) == 0
