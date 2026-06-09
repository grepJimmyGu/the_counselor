"""Signal primitive catalog routes — PRD-16a Slice 1.

  GET  /api/signal-primitives  — full catalog payload + ETag

The endpoint is intentionally minimal in this slice. Future slices will
add:
  - GET /api/signal-primitives/{id}/preview  (PRD-16a-2)
  - POST /api/signal-combos/match-templates  (PRD-16a-3)

The catalog itself is a static Python module (`app/data/signal_primitives.py`)
loaded into memory once at import. There's no DB read — the catalog is
content, not user data. That makes the endpoint trivially fast (sub-ms),
which matters because the frontend hits this on every cold app load
(though it caches in localStorage after the first hit).

ETag pattern:
  - Server returns `ETag: "<version_hash>"` on every response.
  - Frontend sends `If-None-Match: "<version_hash>"` on subsequent fetches.
  - When the hashes match, we return 304 Not Modified (no body); the
    frontend reuses its cached payload.
  - The version hash is content-addressable (hash of every primitive's
    metadata) so a real catalog change always produces a new hash, and
    no catalog change always produces the same hash — even across deploys
    with no code change.
"""
from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, Header, Response

from app.data.signal_primitives import (
    SIGNAL_PRIMITIVES,
    get_catalog_version_hash,
)
from app.schemas.signal_primitive import (
    SignalCategory,
    SignalPrimitivesResponse,
)

router = APIRouter(prefix="/api", tags=["signal_primitives"])


@router.get("/signal-primitives", response_model=SignalPrimitivesResponse)
def get_signal_primitives_catalog(
    response: Response,
    if_none_match: Optional[str] = Header(default=None, alias="If-None-Match"),
) -> Union[SignalPrimitivesResponse, Response]:
    """Return the full primitive catalog.

    Supports conditional GET via `If-None-Match`. The client sends the
    last-seen `version_hash` as the header; if it matches the current
    hash, the server returns 304 with no body and the client reuses its
    cached payload. Saves a few KB of catalog JSON per page load — small
    individually but adds up across the user's session.

    No auth — the catalog is the same for every user. Future PRDs may
    add per-tier filtering (e.g. hide tier-A primitives from Scout); when
    they do, the cache key should incorporate the tier.
    """
    version_hash = get_catalog_version_hash()
    etag = f'"{version_hash}"'

    # Strip surrounding quotes from If-None-Match before comparing —
    # standard ETag wire format wraps in quotes.
    incoming = (if_none_match or "").strip().strip('"')
    if incoming == version_hash:
        response.status_code = 304
        response.headers["ETag"] = etag
        return Response(status_code=304, headers={"ETag": etag})

    response.headers["ETag"] = etag
    # Cache for an hour at the edge. The endpoint is content-static; the
    # ETag handles invalidation on real changes. Vercel/Railway proxies
    # can cache freely.
    response.headers["Cache-Control"] = "public, max-age=3600"
    return SignalPrimitivesResponse(
        primitives=SIGNAL_PRIMITIVES,
        categories=list(SignalCategory),
        version_hash=version_hash,
    )
