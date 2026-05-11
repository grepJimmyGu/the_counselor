from __future__ import annotations

from app.schemas.sentiment import CommunityMention, ProviderStatus


class InternalCommunityProvider:
    """
    Internal platform community provider — placeholder only.
    Status: not_configured until Phase 3 (PRD-11–14).
    Will read from strategy_comments, user_votes, user_watchlists when Phase 3 ships.
    """
    name = "internal_community"

    def status(self) -> ProviderStatus:
        return ProviderStatus.not_configured

    async def fetch(self, symbol: str, limit: int = 30) -> list[CommunityMention]:
        return []
