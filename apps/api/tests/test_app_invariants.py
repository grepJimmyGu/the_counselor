"""Static invariants the FastAPI app must satisfy at import time.

These run on every pytest invocation (no PG_TEST_URL required) — fast feedback
for trap classes that have crashed production deploys before.

Each test_* corresponds to a row in `docs/KNOWN_ISSUES.md`.
"""
from __future__ import annotations

from fastapi.routing import APIRoute

# Importing this module loads every route decorator. If any of them violates a
# FastAPI startup-time assertion (e.g. status_code=204 with -> None), this
# import raises and the test collection fails before any test runs — which is
# exactly what we want.
from app.main import app


def test_app_imports_and_registers_routes():
    """The app loaded without raising. Sanity check + makes the test visible
    in pytest output so a failure is grep-able."""
    assert len(app.routes) > 10, "expected at least 10 routes registered"


def test_no_204_route_has_response_body():
    """KNOWN_ISSUES.md: FastAPI 0.115+ asserts status_code=204 cannot have a body.

    Caught at import time by FastAPI itself, but having an explicit test makes
    the failure mode obvious in CI output (vs. an opaque AssertionError deep in
    FastAPI internals). If this fails, set response_class=Response on the route."""
    offenders = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        if r.status_code == 204 and r.response_model is not None:
            offenders.append(f"{r.methods} {r.path} → response_model={r.response_model}")
    assert not offenders, (
        f"Routes with status_code=204 must not declare a response_model. "
        f"Add response_class=Response and return Response(status_code=204). "
        f"Offenders: {offenders}"
    )
