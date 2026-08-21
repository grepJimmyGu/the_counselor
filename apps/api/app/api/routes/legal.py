"""The compliance disclaimer, served from its single source.

Public and unauthenticated: it is the text we show people BEFORE they have
an account, and gating it behind a login would defeat the point.

Served from the backend rather than duplicated as a frontend constant so
there is exactly one copy of this wording in the product. Compliance text
that exists in two places drifts, and the half nobody is looking at is the
half that goes stale.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.services.disclaimer import FULL, SHORT, SHORT_DIGEST

router = APIRouter(prefix="/api/legal", tags=["legal"])


class DisclaimerResponse(BaseModel):
    short: str
    short_digest: str
    full: str


@router.get("/disclaimer", response_model=DisclaimerResponse)
def get_disclaimer(response: Response) -> DisclaimerResponse:
    # Static text; let clients and the CDN hold it rather than round-trip
    # on every render. Short enough a stale copy is corrected within the
    # hour, which is well inside any reasonable review cycle.
    response.headers["Cache-Control"] = "public, max-age=3600"
    return DisclaimerResponse(short=SHORT, short_digest=SHORT_DIGEST, full=FULL)
