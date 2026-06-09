"""Signal primitive catalog routes — PRD-16a Slices 1 + 2.

  GET  /api/signal-primitives                       — full catalog + ETag
  GET  /api/signal-primitives/{id}/preview          — sample series on a symbol

The catalog itself is a static Python module (`app/data/signal_primitives.py`)
loaded into memory once at import. There's no DB read for the catalog
endpoint — the catalog is content, not user data. That makes it
trivially fast (sub-ms).

The preview endpoint DOES hit DB + Alpha Vantage (local computation
needs price history; AV-endpoint primitives fetch directly). Default
symbol is SPY (cache-warm on production), but any tradeable symbol is
allowed. Per Mr Gu's 2026-06-09 call: paid AV tier, no rate-limit
budget concern.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Union

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fastapi import Depends

from app.data.signal_primitives import (
    SIGNAL_PRIMITIVES,
    get_catalog_version_hash,
)
from app.db.session import get_db
from app.schemas.signal_primitive import (
    SignalCategory,
    SignalPrimitive,
    SignalPrimitivesResponse,
)

router = APIRouter(prefix="/api", tags=["signal_primitives"])


# ── Preview response model ──────────────────────────────────────────────────


class PreviewPoint(BaseModel):
    """One (date, value) pair from a preview series. `value` is float
    or None (NaN-equivalent — the indicator hasn't warmed up yet,
    or the underlying data is missing)."""
    date: str
    value: Optional[float] = None


class PreviewResponse(BaseModel):
    primitive_id: str
    symbol: str
    parameters: dict
    series: list[PreviewPoint]


def _find_primitive(primitive_id: str) -> Optional[SignalPrimitive]:
    for p in SIGNAL_PRIMITIVES:
        if p.id == primitive_id:
            return p
    return None


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


# ── PRD-16a-2: GET /api/signal-primitives/{id}/preview ─────────────────────


@router.get("/signal-primitives/{primitive_id}/preview", response_model=PreviewResponse)
async def preview_signal_primitive(
    primitive_id: str,
    request: Request,
    symbol: str = Query("SPY", description="Symbol to compute the indicator on"),
    days: int = Query(
        252, ge=30, le=2000,
        description="How many trading days back to compute. Default ~1 year.",
    ),
    db: Session = Depends(get_db),
) -> PreviewResponse:
    """Compute a primitive on the requested symbol over the last `days`
    trading days and return the resulting series.

    Parameter overrides are accepted as additional query params keyed on
    the primitive's `Parameter.name`. E.g.
    `GET /api/signal-primitives/rsi/preview?symbol=NVDA&period=21`
    computes 21-day RSI on NVDA. Unknown query params are ignored so
    the frontend can pass {primitive_id, symbol, days} without filtering.

    Failures:
      - 404 if the primitive_id doesn't exist in the catalog
      - 200 with empty `series` if the symbol has no price data; the
        frontend renders a "no data" placeholder rather than an error
      - 502 if Alpha Vantage rejects the request for an AV-endpoint
        primitive
    """
    from app.services.alpha_vantage import AlphaVantageError
    from app.services.backtester.signal_provider import get_signal_provider
    from app.services.backtester.technical_signal_providers import (
        TechnicalSignalProvider,
    )

    primitive = _find_primitive(primitive_id)
    if primitive is None:
        raise HTTPException(status_code=404, detail="Primitive not found.")

    # Extract parameter overrides from query string. The Parameter
    # objects in the catalog tell us which names to look for; everything
    # else is ignored.
    raw_query = dict(request.query_params)
    raw_query.pop("symbol", None)
    raw_query.pop("days", None)
    param_overrides: dict = {}
    for catalog_param in primitive.parameters:
        if catalog_param.name in raw_query:
            raw = raw_query[catalog_param.name]
            # Coerce based on the default's type — keeps `period=14` →
            # int and `acceleration=0.05` → float.
            default = catalog_param.default
            try:
                if isinstance(default, bool):
                    param_overrides[catalog_param.name] = (raw.lower() == "true")
                elif isinstance(default, int):
                    param_overrides[catalog_param.name] = int(raw)
                elif isinstance(default, float):
                    param_overrides[catalog_param.name] = float(raw)
                else:
                    param_overrides[catalog_param.name] = raw
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid value for parameter '{catalog_param.name}': "
                        f"got '{raw}', expected {type(default).__name__}."
                    ),
                )

    # Build the provider — runtime overrides via the `with_params`
    # factory, falling back to the registry instance for primitives
    # that don't subclass TechnicalSignalProvider.
    if param_overrides:
        try:
            base = get_signal_provider(primitive.provider_impl)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        if isinstance(base, TechnicalSignalProvider):
            provider = type(base).with_params(**param_overrides)
        else:
            # Non-technical providers (fundamental, sentiment) ignore
            # runtime overrides for v1.
            provider = base
    else:
        try:
            provider = get_signal_provider(primitive.provider_impl)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    end = date.today()
    start = end - timedelta(days=days)
    try:
        series = await provider.get_signal_frame(db, symbol.upper(), start, end)
    except AlphaVantageError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Alpha Vantage error: {exc}",
        )

    # Resolve final params (default + overrides) for the response.
    if hasattr(provider, "params"):
        final_params = dict(getattr(provider, "params", {}))
    else:
        final_params = {p.name: p.default for p in primitive.parameters}

    points: list[PreviewPoint] = []
    for ts, value in series.items():
        # NaN → None so JSON serializes cleanly; pandas NaN is float
        # but invalid in JSON.
        val: Optional[float] = None
        if value is not None and not (isinstance(value, float) and value != value):
            val = float(value)
        # ts is a pandas Timestamp; serialize as ISO date.
        date_str = ts.date().isoformat() if hasattr(ts, "date") else str(ts)
        points.append(PreviewPoint(date=date_str, value=val))

    return PreviewResponse(
        primitive_id=primitive_id,
        symbol=symbol.upper(),
        parameters=final_params,
        series=points,
    )
