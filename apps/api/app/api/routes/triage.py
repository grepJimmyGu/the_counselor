"""Internal triage context endpoint (PR-D).

Returns the markdown triage bundle composed by
`triage_context_service.compose_triage_context`. Token-gated via the
`OPS_TRIAGE_TOKEN` env var because the response can leak operational
detail (recent error strings, commit subjects, suspected traps).

Returns `text/markdown` so Jimmy can curl it directly and paste the
output into a fresh Claude session without further formatting.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/triage-context", response_class=PlainTextResponse)
def triage_context(token: str = Query(default="")) -> PlainTextResponse:
    """Return the triage markdown bundle if the token matches.

    The bundle is meant to be one-click copy-pasteable into a Claude
    session, so we serve `text/markdown; charset=utf-8` and let the
    client render however it wants.
    """
    settings = get_settings()
    expected = (settings.ops_triage_token or "").strip()
    if not expected:
        # If no token is configured, the endpoint is effectively closed
        # — refuse rather than accidentally exposing the bundle.
        raise HTTPException(status_code=403, detail="triage_token_not_configured")
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid_triage_token")

    # Late import — keeps the route module light at app load time and
    # avoids importing `app.main` before it's ready in test contexts.
    from app.main import compute_health_state
    from app.services.triage_context_service import compose_triage_context

    payload = compute_health_state()
    markdown = compose_triage_context(payload)
    return PlainTextResponse(content=markdown, media_type="text/markdown; charset=utf-8")
