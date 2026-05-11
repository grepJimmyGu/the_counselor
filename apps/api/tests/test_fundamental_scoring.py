"""Tests for PRD-08a fundamental scoring and value chain classifier."""
from __future__ import annotations

import pytest

from app.services.value_chain_classifier import (
    get_value_chain_role,
    get_cyclicality_implication,
    derive_margin_implication,
)
from app.services.financial_validation_service import FinancialCheckMetrics
from app.services.fundamental_scoring_service import (
    compute_financial_validation_score,
    compute_valuation_risk_score,
    get_financial_validation_label,
    get_warnings,
)


# ── Value chain classifier ─────────────────────────────────────────────────────

def test_get_role_exact_match():
    assert get_value_chain_role("Technology", "Semiconductors") == "Component Supplier"

def test_get_role_sector_fallback():
    assert get_value_chain_role("Technology", "Unknown Industry") == "Software Layer"

def test_get_role_none_sector():
    assert get_value_chain_role(None, None) is None

def test_cyclicality_low_for_healthcare():
    result = get_cyclicality_implication("Healthcare")
    assert result is not None
    assert "Low" in result

def test_cyclicality_high_for_energy():
    result = get_cyclicality_implication("Energy")
    assert result is not None
    assert "High" in result or "high" in result.lower()

def test_margin_implication_above_norm():
    result = derive_margin_implication(0.90, "Software Layer")
    assert result is not None
    assert "Above-average" in result

def test_margin_implication_below_norm():
    result = derive_margin_implication(0.10, "Software Layer")
    assert result is not None
    assert "Below-average" in result


# ── Financial validation score ────────────────────────────────────────────────

def test_strong_financial_score():
    m = FinancialCheckMetrics()
    m.revenue_yoy = 0.25   # >20% → 100
    m.gross_margin = 0.75  # high
    m.operating_margin = 0.30  # >20% → 100
    m.fcf_conversion = 1.10  # >100% → 100
    m.net_debt = -1e9  # net cash → 100
    m.operating_cf = 5e9
    m.eps_growth_years = 4

    score = compute_financial_validation_score(m)
    assert score >= 80


def test_weak_financial_score():
    m = FinancialCheckMetrics()
    m.revenue_yoy = -0.10   # negative
    m.gross_margin = 0.08
    m.operating_margin = -0.05
    m.fcf_conversion = 0.20
    m.net_debt = 5e9
    m.operating_cf = 1e9
    m.eps_growth_years = 0

    score = compute_financial_validation_score(m)
    assert score <= 40


def test_valuation_risk_high_pe():
    m = FinancialCheckMetrics()
    m.pe_ratio = 80.0   # >3x sector median of 20 → 100 risk
    m.ps_ratio = 25.0   # >20x → 100 risk
    m.fcf_yield = 0.005  # <1% → 100 risk

    risk = compute_valuation_risk_score(m)
    assert risk >= 70


def test_valuation_risk_low():
    m = FinancialCheckMetrics()
    m.pe_ratio = 12.0   # below median → 0 risk
    m.ps_ratio = 2.0    # <5x → 10 risk
    m.fcf_yield = 0.06  # >4% → 0 risk

    risk = compute_valuation_risk_score(m)
    assert risk <= 30


def test_financial_validation_label_strong():
    assert "Strongly" in get_financial_validation_label(85)

def test_financial_validation_label_weak():
    assert "Weak" in get_financial_validation_label(10)


def test_warnings_valuation_risk_high():
    m = FinancialCheckMetrics()
    warnings = get_warnings(m, valuation_risk=80)
    assert "Valuation Risk High" in warnings
