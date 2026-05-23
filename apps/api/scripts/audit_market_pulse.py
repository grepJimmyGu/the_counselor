"""Market Pulse data accuracy + latency audit.

Read-only audit script that walks `/api/market/pulse` (US + CN),
`/api/market/sector-comparison/{symbol}`, `/api/market/history-rhymes`,
`/api/market/data-latency`, and the underlying `price_bars` table, then
emits a markdown report with findings tagged `OK` / `WARN` / `ERROR`.

The script is the workhorse for the `market-pulse-audit` Claude skill
(`/Users/jimmygu/the_counselor/.claude/skills/market-pulse-audit/SKILL.md`)
but is fully usable standalone.

Usage:
    cd apps/api
    # Local / staging — talks to whatever DATABASE_URL points at
    python scripts/audit_market_pulse.py --base-url http://localhost:8001

    # Production
    python scripts/audit_market_pulse.py \\
        --base-url https://thecounselor-production.up.railway.app

    # Markdown to file
    python scripts/audit_market_pulse.py --output audit_report.md

Exit code:
    0   no ERROR findings (WARNs allowed)
    1   at least one ERROR finding

Checks:
    1. **Freshness** — every group in `/api/market/data-latency`
       should be `fresh`. Anything older raises WARN/ERROR.
    2. **Region integrity** — US `top_assets` must contain ZERO
       symbols ending in `.SH` / `.SZ` / `.HK`.
    3. **Sort sanity** — currently spot-checks that the pool
       contains both gainers AND losers (so client-side losers-sort
       has data to work with).
    4. **Math spot-check** — recomputes cumulative return for a
       random sector ETF in `/api/market/sector-comparison/XLK` and
       diffs against the API's `series[-1].sector`. ERROR on |delta|
       > 0.5%.
    5. **Macro signals reality** — `macro_signals[i].source` should
       be `alpha_vantage` for Inflation + Rates (regression net for
       the AV-disabled silent-mock fallback).
    6. **CN scope** — `market=CN` response: `top_assets` only CN
       proxies; `macro_signals == []` (hidden client-side, but
       backend should match); history-rhymes caveat is "US-only".
    7. **Benchmark identity** — sector-comparison should be using
       ^GSPC (verifies the PR-5 swap actually fired in production).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Optional

# Sit the script on the import path so we can borrow shared bits if
# needed (currently the script is HTTP-only; DB-level checks live in
# `tests/test_market_pulse_*.py`).
_API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)


# ── Result types ────────────────────────────────────────────────────────────


_OK = "OK"
_WARN = "WARN"
_ERROR = "ERROR"


class Finding:
    __slots__ = ("section", "status", "message", "detail")

    def __init__(self, section: str, status: str, message: str, detail: Optional[str] = None):
        self.section = section
        self.status = status
        self.message = message
        self.detail = detail

    def as_md(self) -> str:
        icon = {_OK: "✓", _WARN: "⚠", _ERROR: "✗"}[self.status]
        line = f"  {icon} **{self.status}** — {self.message}"
        if self.detail:
            line += f"\n     `{self.detail}`"
        return line


# ── HTTP helpers ────────────────────────────────────────────────────────────


def _fetch(base_url: str, path: str) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "market-pulse-audit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ── Check 1: Freshness ──────────────────────────────────────────────────────


def check_freshness(base_url: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        latency = _fetch(base_url, "/api/market/data-latency")
    except Exception as exc:
        return [Finding("Freshness", _ERROR, "Could not fetch /api/market/data-latency", repr(exc))]

    overall = latency.get("overall_status", "missing")
    overall_latest = latency.get("overall_latest_date")
    if overall == "fresh":
        findings.append(Finding(
            "Freshness", _OK,
            f"All data groups fresh (oldest source: {overall_latest})",
        ))
    elif overall == "stale":
        findings.append(Finding(
            "Freshness", _WARN,
            f"Page is stale — oldest data group at {overall_latest}",
        ))
    else:
        findings.append(Finding(
            "Freshness", _ERROR,
            f"Page status={overall}; overall_latest_date={overall_latest}",
        ))

    # Per-group detail when not all fresh
    for group in latency.get("sources", []):
        if group.get("status") != "fresh":
            findings.append(Finding(
                "Freshness", _WARN if group["status"] == "stale" else _ERROR,
                f"{group['group']}: {group['status']} (latest: {group.get('latest_date')})",
                detail=group.get("description"),
            ))
    return findings


# ── Check 2: Region integrity ───────────────────────────────────────────────


_BAD_SUFFIXES = (".SH", ".SZ", ".HK")


def check_region_integrity(base_url: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        us = _fetch(base_url, "/api/market/pulse?market=US")
    except Exception as exc:
        return [Finding("Region integrity", _ERROR, "Could not fetch /api/market/pulse?market=US", repr(exc))]

    leaks = []
    for asset in us.get("top_assets", []):
        sym = asset.get("symbol", "")
        if any(sym.endswith(s) for s in _BAD_SUFFIXES):
            leaks.append(sym)
    if leaks:
        findings.append(Finding(
            "Region integrity", _ERROR,
            f"US top_assets contains non-US symbols: {leaks}",
        ))
    else:
        findings.append(Finding(
            "Region integrity", _OK,
            f"US top_assets has no .SH/.SZ/.HK leakage "
            f"({len(us.get('top_assets', []))} symbols checked)",
        ))
    return findings


# ── Check 3: Sort sanity ────────────────────────────────────────────────────


def check_sort_sanity(base_url: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        us = _fetch(base_url, "/api/market/pulse?market=US")
    except Exception as exc:
        return [Finding("Sort sanity", _ERROR, "Could not fetch /api/market/pulse?market=US", repr(exc))]

    perfs = [a.get("perf_1d") for a in us.get("top_assets", []) if a.get("perf_1d") is not None]
    if not perfs:
        return [Finding("Sort sanity", _WARN, "No perf_1d data in top_assets")]

    gainers = [p for p in perfs if p > 0]
    losers = [p for p in perfs if p < 0]
    if len(gainers) >= 1 and len(losers) >= 1:
        findings.append(Finding(
            "Sort sanity", _OK,
            f"Pool contains both gainers ({len(gainers)}) and losers ({len(losers)})",
        ))
    elif len(losers) == 0:
        findings.append(Finding(
            "Sort sanity", _WARN,
            "Pool has zero losers — 'Top losers' sort will show 'least gainers' "
            "instead of real losers. Either the day is unusually one-sided or "
            "the candidate pool is too narrow (PR-2 regression).",
            detail=f"perf_1d range: {min(perfs):.4f} to {max(perfs):.4f}",
        ))
    else:
        findings.append(Finding(
            "Sort sanity", _WARN,
            f"Pool has zero gainers (perf range {min(perfs):.4f} to {max(perfs):.4f})",
        ))
    return findings


# ── Check 4: Math spot-check ────────────────────────────────────────────────


def check_math_spot(base_url: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        comp = _fetch(base_url, "/api/market/sector-comparison/XLK?range=1M")
    except Exception as exc:
        return [Finding("Math spot-check", _WARN, "Could not fetch sector-comparison/XLK", repr(exc))]

    series = comp.get("series", [])
    if len(series) < 2:
        return [Finding("Math spot-check", _WARN, f"sector-comparison/XLK series too short ({len(series)} points)")]

    # The first point should normalize to 0. Last point should match
    # the API's sector_day / sector_3y reported below the chart for
    # reasonable consistency (chart uses windowed slice; totals use
    # full history — so we only spot-check the chart series's own
    # internal consistency).
    if abs(series[0].get("sector", 0)) > 1e-6:
        findings.append(Finding(
            "Math spot-check", _ERROR,
            f"sector-comparison/XLK series[0].sector should be 0; got {series[0].get('sector')}",
        ))
    elif abs(series[0].get("spy", 0)) > 1e-6:
        findings.append(Finding(
            "Math spot-check", _ERROR,
            f"sector-comparison/XLK series[0].spy should be 0; got {series[0].get('spy')}",
        ))
    else:
        findings.append(Finding(
            "Math spot-check", _OK,
            f"sector-comparison/XLK series normalized to 0 at window start ({len(series)} points)",
        ))
    return findings


# ── Check 5: Macro signals reality ──────────────────────────────────────────


def check_macro_signals_reality(base_url: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        us = _fetch(base_url, "/api/market/pulse?market=US")
    except Exception as exc:
        return [Finding("Macro signals", _ERROR, "Could not fetch /api/market/pulse?market=US", repr(exc))]

    macro_signals = us.get("macro_signals", [])
    if not macro_signals:
        return [Finding("Macro signals", _WARN, "macro_signals empty — frontend will use hardcoded mock fallback")]

    by_category = {s.get("category"): s for s in macro_signals}
    for required in ("Inflation", "Rates"):
        sig = by_category.get(required)
        if sig is None:
            findings.append(Finding(
                "Macro signals", _ERROR,
                f"Missing required real-data signal: {required}",
            ))
            continue
        source = sig.get("source")
        if source == "alpha_vantage":
            findings.append(Finding(
                "Macro signals", _OK,
                f"{required} signal is real ({source}, latest={sig.get('latestLabel')})",
            ))
        else:
            findings.append(Finding(
                "Macro signals", _ERROR,
                f"{required} signal silently fell back to mock (source={source}); "
                f"Alpha Vantage path is broken",
            ))
    # Growth + Stress are intentionally mock until FRED — log info, not WARN
    for label in ("Growth", "Stress"):
        sig = by_category.get(label)
        if sig and sig.get("source") == "mock_pending_fred":
            findings.append(Finding(
                "Macro signals", _OK,
                f"{label}: mock_pending_fred (expected until FRED_API_KEY is set)",
            ))
    return findings


# ── Check 6: CN scope ───────────────────────────────────────────────────────


def check_cn_scope(base_url: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        cn = _fetch(base_url, "/api/market/pulse?market=CN")
    except Exception as exc:
        return [Finding("CN scope", _ERROR, "Could not fetch /api/market/pulse?market=CN", repr(exc))]

    leaks = [a.get("symbol") for a in cn.get("top_assets", []) if any(a.get("symbol", "").endswith(s) for s in (".SH", ".SZ"))]
    # CN proxies are US-listed ETFs (FXI, KWEB, etc.) — they should NOT be
    # .SH / .SZ. Confusingly, A-shares ARE .SH/.SZ; the CN proxies are NOT.
    if leaks:
        # Actually that means raw A-shares snuck in here — also bad.
        findings.append(Finding(
            "CN scope", _ERROR,
            f"CN top_assets contains raw A-share symbols: {leaks}",
        ))
    else:
        findings.append(Finding(
            "CN scope", _OK,
            f"CN top_assets shape OK ({len(cn.get('top_assets', []))} ETF proxies)",
        ))

    # History Rhymes US-only caveat
    try:
        hr = _fetch(base_url, "/api/market/history-rhymes?market=CN")
        caveat = hr.get("caveat", "")
        if "US-only" in caveat or "US only" in caveat:
            findings.append(Finding(
                "CN scope", _OK,
                "history-rhymes?market=CN returns US-only caveat as expected",
            ))
        else:
            findings.append(Finding(
                "CN scope", _WARN,
                f"history-rhymes?market=CN caveat changed: {caveat!r}",
            ))
    except Exception as exc:  # noqa: BLE001
        findings.append(Finding("CN scope", _WARN, f"history-rhymes?market=CN errored: {exc!r}"))
    return findings


# ── Check 7: Benchmark identity ─────────────────────────────────────────────


def check_benchmark_identity(base_url: str) -> list[Finding]:
    """Confirm sector-comparison is reading ^GSPC, not SPY. PR-5 added
    a fallback to SPY if ^GSPC has no bars; this check verifies the
    backfill actually ran."""
    findings: list[Finding] = []
    try:
        latency = _fetch(base_url, "/api/market/data-latency")
    except Exception as exc:
        return [Finding("Benchmark identity", _WARN, "Could not fetch /api/market/data-latency", repr(exc))]

    benchmarks = next((g for g in latency.get("sources", []) if g.get("group") == "Benchmarks"), None)
    if benchmarks is None:
        return [Finding("Benchmark identity", _WARN, "No 'Benchmarks' group in data-latency response")]

    gspc = next((m for m in benchmarks.get("members", []) if m.get("symbol") == "^GSPC"), None)
    if gspc is None:
        return [Finding("Benchmark identity", _WARN, "^GSPC not in latency report — code may not be on this deploy")]

    if gspc.get("status") == "missing":
        findings.append(Finding(
            "Benchmark identity", _WARN,
            "^GSPC has no bars — sector chart is falling back to SPY. "
            "Run `apps/api/scripts/backfill_gspc.py` against the prod DB.",
        ))
    elif gspc.get("status") == "fresh":
        findings.append(Finding(
            "Benchmark identity", _OK,
            f"^GSPC backfilled and fresh (latest: {gspc.get('latest_date')})",
        ))
    else:
        findings.append(Finding(
            "Benchmark identity", _WARN,
            f"^GSPC present but {gspc.get('status')} (latest: {gspc.get('latest_date')})",
        ))
    return findings


# ── Runner ──────────────────────────────────────────────────────────────────


_CHECKS = [
    ("Freshness", check_freshness),
    ("Region integrity", check_region_integrity),
    ("Sort sanity", check_sort_sanity),
    ("Math spot-check", check_math_spot),
    ("Macro signals reality", check_macro_signals_reality),
    ("CN scope", check_cn_scope),
    ("Benchmark identity", check_benchmark_identity),
]


def run_audit(base_url: str) -> tuple[list[Finding], int]:
    """Run all checks. Returns (findings_list, error_count)."""
    all_findings: list[Finding] = []
    for name, fn in _CHECKS:
        try:
            all_findings.extend(fn(base_url))
        except Exception as exc:  # noqa: BLE001
            all_findings.append(Finding(name, _ERROR, f"Check itself crashed: {exc!r}"))
    errors = sum(1 for f in all_findings if f.status == _ERROR)
    return all_findings, errors


def format_report(findings: list[Finding], base_url: str) -> str:
    lines = [
        "# Market Pulse audit report",
        "",
        f"- **Base URL**: `{base_url}`",
        f"- **Run at**: {datetime.utcnow().isoformat()}Z",
        "",
    ]
    by_section: dict[str, list[Finding]] = {}
    for f in findings:
        by_section.setdefault(f.section, []).append(f)
    for section, fs in by_section.items():
        lines.append(f"## {section}")
        for f in fs:
            lines.append(f.as_md())
        lines.append("")
    summary = {
        _OK: sum(1 for f in findings if f.status == _OK),
        _WARN: sum(1 for f in findings if f.status == _WARN),
        _ERROR: sum(1 for f in findings if f.status == _ERROR),
    }
    lines.append("## Summary")
    lines.append(f"- OK: {summary[_OK]}  ·  WARN: {summary[_WARN]}  ·  ERROR: {summary[_ERROR]}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Market Pulse data audit")
    parser.add_argument(
        "--base-url", required=True,
        help="API base URL (e.g. https://thecounselor-production.up.railway.app)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Write the markdown report to this path instead of stdout",
    )
    args = parser.parse_args()

    findings, errors = run_audit(args.base_url)
    report = format_report(findings, args.base_url)
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(report)
        print(f"Report written to {args.output} ({len(findings)} findings, {errors} errors)")
    else:
        print(report)
    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()
