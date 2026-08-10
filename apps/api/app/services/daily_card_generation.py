"""Generate-once-per-trading-day, then serve the same card forever.

The lifecycle Jimmy specified: the first share of a day generates from the
PRIOR CLOSE, writes one row per `(trading_date, lang)`, and every later viewer
gets that exact row. No cron — nothing generates on a day nobody shares.

Three things this has to get right, in order of how badly they'd bite:

1. **The card must never carry an invented figure.** `card_copy.validate_copy`
   drops any field whose numbers we didn't supply. That runs before anything
   is persisted, so a bad generation can't be cached and re-served forever.
2. **Concurrent first-shares must not double-generate.** Two users in the same
   second both find no row and both call the model. The unique constraint
   makes one insert lose; the loser re-reads and serves the winner's card
   rather than writing a divergent one.
3. **A failed model call must still produce a card.** Every figure is
   deterministic; only the prose needs the LLM. A card with real numbers and
   no headline beats a share button that errors.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.daily_card import DailyCard
from app.services.card_copy import CardCopy, build_prompt, validate_copy
from app.services.card_labels import EN, LANGUAGES
from app.services.daily_card_service import CardPayload, build_card_payload
from app.services.daily_brief_service import DailyBrief
from app.services.evaluation_scoring import ThreeDimensionalScore

logger = logging.getLogger("livermore.daily_card")


def get_existing(db: Session, trading_date: str, lang: str) -> Optional[DailyCard]:
    return db.execute(
        select(DailyCard).where(
            DailyCard.trading_date == trading_date, DailyCard.lang == lang
        )
    ).scalars().first()


def _persist(
    db: Session,
    *,
    trading_date: str,
    lang: str,
    payload: CardPayload,
    copy: CardCopy,
    model: Optional[str],
) -> DailyCard:
    """Insert, or return whoever won the race.

    `IntegrityError` here is the EXPECTED path under concurrent first-shares,
    not an error condition — so it's caught narrowly and resolved by re-reading
    rather than retried or surfaced.
    """
    row = DailyCard(
        id=str(uuid.uuid4()),
        trading_date=trading_date,
        lang=lang,
        payload=json.dumps(payload.to_dict(), ensure_ascii=False),
        copy=json.dumps(copy.to_dict(), ensure_ascii=False),
        model=model,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = get_existing(db, trading_date, lang)
        if existing is not None:
            logger.info(
                "daily card %s/%s: lost the insert race, serving the winner",
                trading_date,
                lang,
            )
            return existing
        raise
    return row


async def generate_copy(
    payload: CardPayload,
    *,
    news: Optional[List[Dict[str, str]]] = None,
) -> tuple:
    """(copy, model). Empty copy and no model when the LLM is off or fails.

    Never raises: the figures are already computed, and a share button that
    errors is worse than a card with no headline.
    """
    from app.services.llm_adapter import LLMAdapterError, get_llm_gateway

    gateway = get_llm_gateway()
    if not gateway.is_enabled:
        logger.info("daily card: LLM disabled, rendering data-only")
        return CardCopy(), None

    system, user = build_prompt(payload, news=news)
    try:
        raw = await gateway.generate_json(system_prompt=system, user_prompt=user)
    except (LLMAdapterError, Exception) as exc:  # noqa: BLE001
        logger.warning("daily card: generation failed, rendering data-only: %r", exc)
        return CardCopy(), None

    copy = validate_copy(raw, payload, news=news)
    if copy.rejected:
        # Loud on purpose. A card silently missing its headline every day is a
        # prompt problem someone needs to see, not a quirk to live with.
        logger.warning(
            "daily card: dropped %s for invented figures", ", ".join(copy.rejected)
        )
    return copy, gateway.settings.llm_model or None


async def get_or_create_card(
    db: Session,
    *,
    brief: DailyBrief,
    lang: str = EN,
    score: Optional[ThreeDimensionalScore] = None,
    news: Optional[List[Dict[str, str]]] = None,
) -> Optional[DailyCard]:
    """The share button's entry point.

    Returns the existing row untouched when there is one — the card is
    immutable, so a second look at the same day must not regenerate it even if
    today's prose would be better.
    """
    if lang not in LANGUAGES:
        lang = EN
    trading_date = (brief.as_of or "")[:10]
    if not trading_date:
        # No close date means no key. Better to decline than to write a row
        # under a blank date that can never be found again.
        logger.warning("daily card: brief has no as_of; refusing to generate")
        return None

    existing = get_existing(db, trading_date, lang)
    if existing is not None:
        return existing

    payload = build_card_payload(brief, lang=lang, score=score)
    copy, model = await generate_copy(payload, news=news)
    return _persist(
        db,
        trading_date=trading_date,
        lang=lang,
        payload=payload,
        copy=copy,
        model=model,
    )


def card_to_dict(row: DailyCard) -> Dict[str, Any]:
    """Row -> the shape the renderer and the API return.

    Tolerates a payload that fails to parse rather than 500ing: a corrupt row
    should degrade to an empty card, and the log line says which row.
    """

    def _load(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw  # Postgres JSONB comes back parsed
        try:
            return json.loads(raw or "{}")
        except (TypeError, ValueError):
            logger.warning("daily card %s: unparseable JSON column", row.id)
            return {}

    return {
        "trading_date": row.trading_date,
        "lang": row.lang,
        "model": row.model,
        "payload": _load(row.payload),
        "copy": _load(row.copy),
    }
