"""Curated bottleneck-lens warm set (Phase 3 scale).

The supply-chain / bottleneck thesis is only meaningful for supply-chain-critical
names — running it on the whole universe is wasteful (banks / retailers return
``no_chain_structure``). This is a hand-picked cluster centred on the
AI-infrastructure / electrical->optical / semicap chokepoints (AXTI's
neighbourhood), so the warmed theses are comparable side-by-side.

Grouped by supply-chain layer for readability; ``BOTTLENECK_CANDIDATES`` is the
flat, de-duplicated, order-preserving list the warm script iterates.

NOTE: TSM and ASML are foreign 20-F filers — central chokepoints (foundry + EUV),
but the hard-evidence extraction may come back thin; the thesis reasoning still
works from their disclosed business.
"""
from __future__ import annotations

BOTTLENECK_CANDIDATES_BY_LAYER: dict[str, list[str]] = {
    # AXTI's layer — the raw scarcity.
    "substrates_compound_semi": ["AXTI", "WOLF", "COHR", "NVTS", "AEHR", "VECO"],
    # The electrical -> optical transition itself.
    "optical_photonics_interconnect": ["LITE", "AAOI", "POET", "MTSI", "CRDO", "ALAB", "CIEN"],
    # Demand pull + the design chokepoint.
    "networking_ai_silicon": ["NVDA", "AMD", "AVGO", "MRVL", "ANET", "LSCC"],
    # The tools — a classic chokepoint layer.
    "semicap_equipment": ["AMAT", "LRCX", "KLAC", "ACLS", "ACMR", "UCTT", "ICHR", "MKSI", "NVMI", "TER", "COHU"],
    # CoWoS-era packaging / metrology / test bottlenecks.
    "advanced_packaging_metrology_test": ["AMKR", "ONTO", "CAMT", "FORM"],
    # Capacity chokepoints (TSM/ASML are 20-F filers — see module note).
    "memory_foundry": ["MU", "INTC", "TSM", "ASML"],
    # Adjacent scarcity.
    "materials_power": ["ENTG", "MP", "MPWR", "VRT"],
}

BOTTLENECK_CANDIDATES: list[str] = list(
    dict.fromkeys(s for names in BOTTLENECK_CANDIDATES_BY_LAYER.values() for s in names)
)
