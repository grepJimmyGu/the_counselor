from __future__ import annotations

from app.schemas.sentiment import CommunityMention, ProviderStatus


class XCommunityProvider:
    """
    X (Twitter) community provider — placeholder only.
    Status: not_configured by default.
    Reason: requires $100/mo X API Basic subscription.
    Actual integration deferred until budget approved.
    Interface is complete — activation requires only env var + implementation.
    """
    name = "x"

    def status(self) -> ProviderStatus:
        return ProviderStatus.not_configured

    async def fetch(self, symbol: str, limit: int = 30) -> list[CommunityMention]:
        return []
