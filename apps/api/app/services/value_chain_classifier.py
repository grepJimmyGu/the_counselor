from __future__ import annotations

from typing import Optional

from app.data.sectors import normalize_sector

# These maps are keyed on the 11 canonical GICS sector labels (app/data/sectors.py),
# which is what `symbols.sector` now stores. They were originally keyed on FMP's
# vocabulary ("Technology", "Healthcare", "Consumer Cyclical", "Consumer
# Defensive", "Basic Materials") while their callers read GICS-labelled rows out
# of `symbols` — so every lookup missed and `get_value_chain_role` /
# `get_cyclicality_implication` returned None for the great majority of
# companies. Callers still passing an FMP label are covered by the
# `normalize_sector()` call in the lookup helpers below.
SECTOR_INDUSTRY_TO_ROLE: dict[tuple[str, str], str] = {
    ("Information Technology", "Semiconductors"): "Component Supplier",
    ("Information Technology", "Semiconductor Equipment & Materials"): "Infrastructure Provider",
    ("Information Technology", "Software—Application"): "Software Layer",
    ("Information Technology", "Software—Infrastructure"): "Infrastructure Provider",
    ("Information Technology", "Consumer Electronics"): "Manufacturer / Producer",
    ("Information Technology", "Electronic Components"): "Component Supplier",
    ("Information Technology", "Information Technology Services"): "Service Provider",
    ("Information Technology", "Internet Content & Information"): "Platform Provider",
    ("Communication Services", "Internet Content & Information"): "Platform Provider",
    ("Communication Services", "Telecom Services"): "Infrastructure Provider",
    ("Communication Services", "Entertainment"): "End-Market Brand",
    ("Health Care", "Biotechnology"): "Value-Added Technology Provider",
    ("Health Care", "Drug Manufacturers—General"): "Manufacturer / Producer",
    ("Health Care", "Medical Devices"): "Component Supplier",
    ("Health Care", "Health Information Services"): "Software Layer",
    ("Health Care", "Healthcare Plans"): "Financial Intermediary",
    ("Financials", "Banks—Diversified"): "Financial Intermediary",
    ("Financials", "Insurance—Diversified"): "Financial Intermediary",
    ("Financials", "Asset Management"): "Financial Intermediary",
    ("Financials", "Capital Markets"): "Financial Intermediary",
    ("Consumer Discretionary", "Specialty Retail"): "Retailer",
    ("Consumer Discretionary", "Auto Manufacturers"): "Manufacturer / Producer",
    ("Consumer Staples", "Beverages—Non-Alcoholic"): "End-Market Brand",
    ("Consumer Staples", "Grocery Stores"): "Retailer",
    ("Consumer Staples", "Household & Personal Products"): "End-Market Brand",
    ("Energy", "Oil & Gas E&P"): "Raw Material Provider",
    ("Energy", "Oil & Gas Refining & Marketing"): "Manufacturer / Producer",
    ("Energy", "Oil & Gas Integrated"): "Raw Material Provider",
    ("Industrials", "Aerospace & Defense"): "Manufacturer / Producer",
    ("Industrials", "Railroads"): "Distributor",
    ("Industrials", "Trucking"): "Distributor",
    ("Industrials", "Specialty Industrial Machinery"): "Infrastructure Provider",
    ("Materials", "Agricultural Inputs"): "Raw Material Provider",
    ("Materials", "Chemicals"): "Raw Material Provider",
    ("Materials", "Steel"): "Raw Material Provider",
    ("Utilities", "Utilities—Regulated Electric"): "Infrastructure Provider",
    ("Utilities", "Utilities—Renewable"): "Infrastructure Provider",
}

SECTOR_FALLBACK_ROLE: dict[str, str] = {
    "Information Technology": "Software Layer",
    "Health Care": "Value-Added Technology Provider",
    "Financials": "Financial Intermediary",
    "Consumer Discretionary": "Retailer",
    "Consumer Staples": "End-Market Brand",
    "Industrials": "Manufacturer / Producer",
    "Energy": "Raw Material Provider",
    "Materials": "Raw Material Provider",
    "Real Estate": "Service Provider",
    "Utilities": "Infrastructure Provider",
    "Communication Services": "Platform Provider",
}

SECTOR_CYCLICALITY: dict[str, str] = {
    "Information Technology": "Low to moderate — typically non-cyclical but sensitive to enterprise spending cycles",
    "Health Care": "Low — defensive sector, relatively immune to economic cycles",
    "Financials": "High — closely tied to credit cycles, interest rates, and economic activity",
    "Consumer Discretionary": "High — demand rises and falls with consumer confidence and income",
    "Consumer Staples": "Low — essential goods maintain demand across economic cycles",
    "Industrials": "Moderate to high — tied to capital expenditure and manufacturing cycles",
    "Energy": "High — commodity-linked, driven by global supply/demand and macro cycles",
    "Materials": "High — directly commodity-linked, highly cyclical",
    "Real Estate": "Moderate — interest-rate sensitive, location-dependent",
    "Utilities": "Low — regulated monopolies with stable, predictable demand",
    "Communication Services": "Low to moderate — subscription revenue is sticky",
}

ROLE_EXPECTED_MARGINS: dict[str, tuple[float, float]] = {
    "Software Layer": (0.60, 0.85),
    "Platform Provider": (0.55, 0.90),
    "Value-Added Technology Provider": (0.50, 0.80),
    "Component Supplier": (0.30, 0.55),
    "Manufacturer / Producer": (0.20, 0.45),
    "Raw Material Provider": (0.15, 0.40),
    "Retailer": (0.20, 0.40),
    "Financial Intermediary": (0.30, 0.70),
    "Service Provider": (0.25, 0.55),
    "Infrastructure Provider": (0.30, 0.60),
    "Distributor": (0.15, 0.35),
    "End-Market Brand": (0.35, 0.65),
}


def get_value_chain_role(sector: Optional[str], industry: Optional[str]) -> Optional[str]:
    # Normalize first: callers pass sector straight through from an FMP profile
    # or a raw `symbols` row, so the label arrives in either vocabulary.
    sector = normalize_sector(sector)
    if sector and industry:
        role = SECTOR_INDUSTRY_TO_ROLE.get((sector, industry))
        if role:
            return role
    if sector:
        return SECTOR_FALLBACK_ROLE.get(sector)
    return None


def get_cyclicality_implication(sector: Optional[str]) -> Optional[str]:
    sector = normalize_sector(sector)
    if not sector:
        return None
    return SECTOR_CYCLICALITY.get(sector)


def derive_margin_implication(gross_margin: Optional[float], value_chain_role: Optional[str]) -> Optional[str]:
    if gross_margin is None or value_chain_role is None:
        return None
    low, high = ROLE_EXPECTED_MARGINS.get(value_chain_role, (0.20, 0.60))
    if gross_margin >= high:
        return f"Above-average for {value_chain_role} — suggests pricing power or premium positioning"
    elif gross_margin < low:
        return f"Below-average for {value_chain_role} — margin pressure or commoditisation risk"
    else:
        return f"In-line with typical {value_chain_role} margins"
