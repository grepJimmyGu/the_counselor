"""Tests for the Market Pulse audit script.

The script is HTTP-only; we mock `_fetch` with a stub returning
synthetic API responses, then assert each check's findings.

Imports the script as a module via `importlib.util.spec_from_file_location`
because `apps/api/scripts/` isn't a package (no `__init__.py` — matches
the existing one-off script pattern of `check_orphan_users.py` etc.).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


def _load_audit_module():
    """Load the audit script as a module without installing it as a package."""
    script_path = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "audit_market_pulse.py"
    )
    spec = importlib.util.spec_from_file_location("audit_market_pulse", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = _load_audit_module()


# ── Synthetic API fixtures ───────────────────────────────────────────────────


_GOOD_LATENCY = {
    "overall_status": "fresh",
    "overall_latest_date": "2026-05-22",
    "overall_hours_stale": 0,
    "sources": [
        {
            "group": "Benchmarks",
            "description": "S&P 500 — ETF + index",
            "latest_date": "2026-05-22", "status": "fresh", "hours_stale": 0,
            "members": [
                {"symbol": "SPY", "latest_date": "2026-05-22", "status": "fresh", "hours_stale": 0},
                {"symbol": "^GSPC", "latest_date": "2026-05-22", "status": "fresh", "hours_stale": 0},
            ],
        },
        {
            "group": "Sector ETFs",
            "description": "11 SPDR sector ETFs",
            "latest_date": "2026-05-22", "status": "fresh", "hours_stale": 0,
            "members": [],
        },
        {
            "group": "Macro basket",
            "description": "Rates / vol / etc.",
            "latest_date": "2026-05-22", "status": "fresh", "hours_stale": 0,
            "members": [],
        },
        {
            "group": "CN proxies",
            "description": "China ETFs",
            "latest_date": "2026-05-22", "status": "fresh", "hours_stale": 0,
            "members": [],
        },
    ],
}


_GOOD_PULSE_US = {
    "top_assets": [
        {"symbol": "NVDA", "perf_1d": 0.025},
        {"symbol": "AAPL", "perf_1d": 0.012},
        {"symbol": "GOOG", "perf_1d": -0.018},
        {"symbol": "TSLA", "perf_1d": -0.032},
    ],
    "macro_signals": [
        {"category": "Growth", "source": "mock_pending_fred", "latestLabel": "ISM PMI: 52.0"},
        {"category": "Inflation", "source": "alpha_vantage", "latestLabel": "CPI YoY: 3.4%"},
        {"category": "Rates", "source": "alpha_vantage", "latestLabel": "10Y Yield: 4.30%"},
        {"category": "Stress", "source": "mock_pending_fred", "latestLabel": "HY Spread: 3.4%"},
    ],
}


_GOOD_PULSE_CN = {
    "top_assets": [
        {"symbol": "FXI", "perf_1d": 0.008},
        {"symbol": "KWEB", "perf_1d": 0.014},
    ],
}


_GOOD_HISTORY_RHYMES_CN = {
    "matches": [],
    "caveat": "History Rhymes is US-only in v1.",
}


_GOOD_SECTOR_COMPARISON = {
    "symbol": "XLK", "range": "1M",
    "series": [
        {"date": "2026-04-22", "sector": 0.0, "spy": 0.0},
        {"date": "2026-05-22", "sector": 0.082, "spy": 0.054},
    ],
}


def _fetcher(fixtures: dict[str, dict]):
    """Make a stub that returns the right fixture per path."""
    def fake_fetch(base_url: str, path: str):
        for key, payload in fixtures.items():
            if key in path:
                return payload
        raise RuntimeError(f"No fixture for {path}")
    return fake_fetch


# ── Tests per check ─────────────────────────────────────────────────────────


def test_freshness_all_fresh():
    with patch.object(audit, "_fetch", _fetcher({"data-latency": _GOOD_LATENCY})):
        findings = audit.check_freshness("http://test")
    assert all(f.status == audit._OK for f in findings)


def test_freshness_one_group_stale():
    stale = {
        **_GOOD_LATENCY,
        "overall_status": "stale",
        "sources": [
            {**_GOOD_LATENCY["sources"][0], "status": "stale"},
            *_GOOD_LATENCY["sources"][1:],
        ],
    }
    with patch.object(audit, "_fetch", _fetcher({"data-latency": stale})):
        findings = audit.check_freshness("http://test")
    statuses = {f.status for f in findings}
    assert audit._WARN in statuses  # at least one WARN for the stale group


def test_region_integrity_no_leaks():
    with patch.object(audit, "_fetch", _fetcher({"pulse?market=US": _GOOD_PULSE_US})):
        findings = audit.check_region_integrity("http://test")
    assert len(findings) == 1
    assert findings[0].status == audit._OK


def test_region_integrity_catches_cn_leak():
    leaky = {
        "top_assets": [
            {"symbol": "NVDA", "perf_1d": 0.02},
            {"symbol": "510300.SH", "perf_1d": 0.001},
        ],
    }
    with patch.object(audit, "_fetch", _fetcher({"pulse?market=US": leaky})):
        findings = audit.check_region_integrity("http://test")
    assert findings[0].status == audit._ERROR
    assert "510300.SH" in findings[0].message


def test_sort_sanity_passes_with_both():
    with patch.object(audit, "_fetch", _fetcher({"pulse?market=US": _GOOD_PULSE_US})):
        findings = audit.check_sort_sanity("http://test")
    assert findings[0].status == audit._OK


def test_sort_sanity_warns_when_no_losers():
    all_gainers = {"top_assets": [
        {"symbol": "A", "perf_1d": 0.01},
        {"symbol": "B", "perf_1d": 0.02},
    ]}
    with patch.object(audit, "_fetch", _fetcher({"pulse?market=US": all_gainers})):
        findings = audit.check_sort_sanity("http://test")
    assert findings[0].status == audit._WARN
    assert "losers" in findings[0].message.lower()


def test_macro_signals_real_for_inflation_and_rates():
    with patch.object(audit, "_fetch", _fetcher({"pulse?market=US": _GOOD_PULSE_US})):
        findings = audit.check_macro_signals_reality("http://test")
    # Both required signals OK, mock signals OK (expected)
    assert all(f.status == audit._OK for f in findings)


def test_macro_signals_errors_when_inflation_fell_back():
    bad = {**_GOOD_PULSE_US, "macro_signals": [
        {"category": "Inflation", "source": "mock_av_failed", "latestLabel": "—"},
        {"category": "Rates", "source": "alpha_vantage", "latestLabel": "10Y: 4.3%"},
    ]}
    with patch.object(audit, "_fetch", _fetcher({"pulse?market=US": bad})):
        findings = audit.check_macro_signals_reality("http://test")
    errors = [f for f in findings if f.status == audit._ERROR]
    assert len(errors) == 1
    assert "Inflation" in errors[0].message


def test_cn_scope_ok_when_clean():
    fixtures = {
        "pulse?market=CN": _GOOD_PULSE_CN,
        "history-rhymes?market=CN": _GOOD_HISTORY_RHYMES_CN,
    }
    with patch.object(audit, "_fetch", _fetcher(fixtures)):
        findings = audit.check_cn_scope("http://test")
    assert all(f.status == audit._OK for f in findings)


def test_math_spot_check_passes_when_normalized():
    with patch.object(audit, "_fetch", _fetcher({"sector-comparison/XLK": _GOOD_SECTOR_COMPARISON})):
        findings = audit.check_math_spot("http://test")
    assert findings[0].status == audit._OK


def test_math_spot_check_errors_when_series_zero_nonzero():
    bad = {**_GOOD_SECTOR_COMPARISON, "series": [
        {"date": "2026-04-22", "sector": 0.015, "spy": 0.0},  # should be 0
        {"date": "2026-05-22", "sector": 0.082, "spy": 0.054},
    ]}
    with patch.object(audit, "_fetch", _fetcher({"sector-comparison/XLK": bad})):
        findings = audit.check_math_spot("http://test")
    assert findings[0].status == audit._ERROR


def test_benchmark_identity_ok_when_gspc_fresh():
    with patch.object(audit, "_fetch", _fetcher({"data-latency": _GOOD_LATENCY})):
        findings = audit.check_benchmark_identity("http://test")
    assert findings[0].status == audit._OK


def test_benchmark_identity_warns_when_gspc_missing():
    missing = {
        **_GOOD_LATENCY,
        "sources": [
            {
                **_GOOD_LATENCY["sources"][0],
                "members": [
                    {"symbol": "SPY", "latest_date": "2026-05-22", "status": "fresh", "hours_stale": 0},
                    {"symbol": "^GSPC", "latest_date": None, "status": "missing", "hours_stale": None},
                ],
            },
            *_GOOD_LATENCY["sources"][1:],
        ],
    }
    with patch.object(audit, "_fetch", _fetcher({"data-latency": missing})):
        findings = audit.check_benchmark_identity("http://test")
    assert findings[0].status == audit._WARN
    assert "backfill_gspc" in findings[0].message


# ── End-to-end run_audit ────────────────────────────────────────────────────


def test_run_audit_returns_finding_count():
    fixtures = {
        "data-latency": _GOOD_LATENCY,
        "pulse?market=US": _GOOD_PULSE_US,
        "pulse?market=CN": _GOOD_PULSE_CN,
        "history-rhymes?market=CN": _GOOD_HISTORY_RHYMES_CN,
        "sector-comparison/XLK": _GOOD_SECTOR_COMPARISON,
    }
    with patch.object(audit, "_fetch", _fetcher(fixtures)):
        findings, errors = audit.run_audit("http://test")
    assert errors == 0
    assert any(f.status == audit._OK for f in findings)
    # Markdown formatting smoke
    report = audit.format_report(findings, "http://test")
    assert "# Market Pulse audit report" in report
    assert "OK:" in report  # summary line


def test_run_audit_surfaces_error():
    leaky_pulse = {
        "top_assets": [{"symbol": "510300.SH", "perf_1d": 0.001}],
        "macro_signals": _GOOD_PULSE_US["macro_signals"],
    }
    fixtures = {
        "data-latency": _GOOD_LATENCY,
        "pulse?market=US": leaky_pulse,
        "pulse?market=CN": _GOOD_PULSE_CN,
        "history-rhymes?market=CN": _GOOD_HISTORY_RHYMES_CN,
        "sector-comparison/XLK": _GOOD_SECTOR_COMPARISON,
    }
    with patch.object(audit, "_fetch", _fetcher(fixtures)):
        findings, errors = audit.run_audit("http://test")
    assert errors >= 1
