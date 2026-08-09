"""Cross-language contract: the results table's technical metric ids must all
exist in the daily snapshot.

`result-metrics.ts` hardcodes ~10 primitive ids as the "Technicals" group of
the additional-metrics picker. Those ids are sent verbatim to
`POST /api/screen/metric-values`, which can only serve what the snapshot
covers. An id that is renamed or dropped on the Python side produces a column
of em dashes with no error anywhere — the table looks like those stocks have
no RSI.

Same pattern (and same reason) as `test_condition_builder_contract.py`: parse
the `.tsx`/`.ts` file, assert every id round-trips.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.screener.signal_snapshot_service import snapshot_primitive_ids

METRICS_TS = (
    Path(__file__).resolve().parents[2]
    / "web"
    / "src"
    / "components"
    / "screen"
    / "result-metrics.ts"
)


def _technical_metric_ids() -> list[str]:
    """The `key:` values inside the TECHNICAL_METRICS array literal."""
    src = METRICS_TS.read_text()
    start = src.index("export const TECHNICAL_METRICS")
    end = src.index("export const METRIC_GROUPS", start)
    return re.findall(r'key:\s*"([^"]+)"', src[start:end])


@pytest.mark.skipif(not METRICS_TS.exists(), reason="web app not present")
def test_every_technical_metric_is_in_the_snapshot():
    ids = _technical_metric_ids()
    assert ids, "parsed zero ids — the TECHNICAL_METRICS literal shape changed"
    covered = set(snapshot_primitive_ids())
    missing = [i for i in ids if i not in covered]
    assert not missing, (
        f"result-metrics.ts offers {missing} but the daily snapshot doesn't "
        "cover them — those columns would render as em dashes. Either drop "
        "them from TECHNICAL_METRICS or add them to the snapshot."
    )


@pytest.mark.skipif(not METRICS_TS.exists(), reason="web app not present")
def test_technical_metric_count_fits_the_endpoint_cap():
    """Selecting every offered technical metric must be a servable request.
    If the list outgrows the cap, the last ones picked are silently dropped."""
    from app.api.routes.screen import _METRIC_VALUES_PRIMITIVE_CAP

    assert len(_technical_metric_ids()) <= _METRIC_VALUES_PRIMITIVE_CAP


@pytest.mark.skipif(not METRICS_TS.exists(), reason="web app not present")
def test_no_duplicate_metric_ids():
    ids = _technical_metric_ids()
    assert len(ids) == len(set(ids))
