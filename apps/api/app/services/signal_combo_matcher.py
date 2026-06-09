"""Signal-combo → template KB lookup — PRD-16a Slice 3.

Given a list of primitive IDs the user selected in the composer, returns
the top-N matching templates from `TEMPLATE_SIGNAL_METADATA` ranked by
Jaccard similarity on category sets, plus per-primitive threshold
suggestions lifted from each matching template.

The PRD's algorithm verbatim:
  1. Compute the user's category set from the primitives they picked.
  2. For each template, compute its category set.
  3. Jaccard similarity = |user ∩ template| / |user ∪ template|.
  4. Sort by similarity descending; return top-N.
  5. For each match, include any threshold the template specifies for a
     primitive the user actually picked — that's the "suggested defaults"
     UX in the composer.

Out of scope (deferred):
  - ML-based similarity (the PRD explicitly rejects it).
  - Cross-template threshold merging when multiple templates match well
    (the composer can pick one; v1 doesn't merge).
  - Weighting categories by primitive count (Jaccard treats them equally).
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

from app.data.signal_primitives import SIGNAL_PRIMITIVES
from app.data.template_signal_metadata import (
    TEMPLATE_SIGNAL_METADATA,
    get_template_categories,
    get_template_thresholds,
)
from app.schemas.signal_primitive import SignalCategory, SignalPrimitive


def _primitive_id_to_category() -> Dict[str, SignalCategory]:
    """Build the {primitive_id → category} index once. Pure function of
    the catalog; called fresh on every match request (catalog is small)."""
    return {p.id: p.category for p in SIGNAL_PRIMITIVES}


def _user_category_set(primitive_ids: List[str]) -> Set[SignalCategory]:
    """Map the user's selected primitive IDs to their categories. Unknown
    IDs are dropped silently — the matcher is best-effort; an invalid ID
    in the input shouldn't 500."""
    index = _primitive_id_to_category()
    return {index[pid] for pid in primitive_ids if pid in index}


def _jaccard(a: Set[SignalCategory], b: Set[SignalCategory]) -> float:
    """Jaccard similarity. Returns 0.0 for an empty union (both sets
    empty) — defensible since 'no shared categories' should be 0."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def match_templates(
    primitive_ids: List[str],
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """Return the top_n templates whose category set best matches the
    user's primitive picks.

    Each result row:
      {
        "template_id": "bollinger-mean-reversion",
        "similarity": 0.5,
        "shared_categories": ["mean_reversion"],
        "thresholds_for_user_primitives": {
          "bbands": {"period": 20, "std_dev": 2.0, ...},
        },
      }

    `thresholds_for_user_primitives` is filtered to ONLY include the
    primitives the user actually picked — the composer doesn't need
    thresholds for primitives it isn't going to render.

    When two templates tie on similarity, the order is the iteration
    order of `TEMPLATE_SIGNAL_METADATA` (i.e. insertion order in the
    dict, which we control). This makes results stable for tests.
    """
    user_categories = _user_category_set(primitive_ids)
    user_primitive_set = set(primitive_ids)

    scored: List[Dict[str, Any]] = []
    for template_id in TEMPLATE_SIGNAL_METADATA:
        template_categories = get_template_categories(template_id)
        similarity = _jaccard(user_categories, template_categories)
        if similarity == 0.0:
            # No overlap → don't surface as a "match." Includes the
            # all-empty case (no user primitives picked).
            continue

        # Lift only the thresholds for primitives the user picked.
        all_thresholds = get_template_thresholds(template_id)
        scoped_thresholds = {
            pid: thresh
            for pid, thresh in all_thresholds.items()
            if pid in user_primitive_set
        }

        scored.append({
            "template_id": template_id,
            "similarity": round(similarity, 4),
            "shared_categories": sorted(
                (user_categories & template_categories),
                key=lambda c: c.value,
            ),
            "thresholds_for_user_primitives": scoped_thresholds,
        })

    # Stable sort by similarity desc + template_id asc for tie-break
    # (consumer expects deterministic order across calls).
    scored.sort(key=lambda row: (-row["similarity"], row["template_id"]))
    return scored[:top_n]
