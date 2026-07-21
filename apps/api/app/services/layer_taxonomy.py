"""Supply-chain layer taxonomy (PRD-25).

Chain fluency is the method's non-negotiable — these layers must never collapse
into a single "component" bucket. A company occupies exactly ONE layer; if
extraction places it in two, that is an extraction defect: take the more
upstream layer and flag ``layer_ambiguous``.
"""
from __future__ import annotations

from typing import Optional

# Generic layers — apply to any physical supply chain, upstream → downstream.
GENERIC_LAYERS: list[str] = [
    "raw_material",
    "processed_input",
    "component",
    "subassembly",
    "module",
    "system",
    "integrator",
    "end_customer",
]

# Vertical-specific refinements. Generic layers are the fallback for any vertical
# not listed here.
VERTICAL_LAYERS: dict[str, list[str]] = {
    "photonics": [
        "substrate",
        "epiwafer",
        "specialty_foundry",
        "laser_die",
        "external_light_source",
        "light_engine",
        "pluggable_transceiver",
        "cpo_module",
        "package_test",
        "ems",
        "switch_system",
    ],
    "memory": [
        "wafer",
        "fab",
        "die",
        "stack_hbm",
        "module",
        "controller",
        "system",
    ],
    "datacenter_power": [
        "raw_material",
        "power_semi",
        "power_module",
        "psu",
        "busbar_800vdc",
        "rack",
        "facility",
    ],
}


def layers_for_vertical(vertical: Optional[str]) -> list[str]:
    """Ordered (upstream → downstream) layer list for a vertical.

    Falls back to :data:`GENERIC_LAYERS` for an unknown or missing vertical.
    """
    if vertical and vertical in VERTICAL_LAYERS:
        return VERTICAL_LAYERS[vertical]
    return GENERIC_LAYERS


def is_known_layer(layer: str, vertical: Optional[str]) -> bool:
    return layer in layers_for_vertical(vertical)


def upstream_rank(layer: str, vertical: Optional[str]) -> int:
    """Index of ``layer`` within its chain — lower is more upstream, ``-1`` if
    unknown. Used to resolve an ambiguous placement toward the upstream layer.
    """
    layers = layers_for_vertical(vertical)
    return layers.index(layer) if layer in layers else -1


def resolve_ambiguous_layer(
    candidates: list[str], vertical: Optional[str]
) -> tuple[Optional[str], bool]:
    """Pick the single layer a company occupies from >=1 candidates.

    Returns ``(layer, ambiguous)``. With multiple known candidates we take the
    most upstream one and flag ``ambiguous=True`` (an extraction defect worth
    surfacing). Unknown candidates are ignored; an empty/all-unknown input
    yields ``(None, False)``.
    """
    known = [c for c in candidates if is_known_layer(c, vertical)]
    if not known:
        return None, False
    if len(known) == 1:
        return known[0], False
    most_upstream = min(known, key=lambda c: upstream_rank(c, vertical))
    return most_upstream, True
