from __future__ import annotations

from app.core.config import get_settings
from app.schemas.sentiment import CommunityMention, ProviderStatus


class RedditCommunityProvider:
    """
    Reddit community provider. Active only when REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET
    are set in environment variables. Returns not_configured otherwise.
    When active: searches r/wallstreetbets, r/investing, r/stocks for ticker mentions.
    """
    name = "reddit"

    def __init__(self) -> None:
        self._settings = get_settings()

    def _is_configured(self) -> bool:
        return bool(
            getattr(self._settings, "reddit_client_id", None)
            and getattr(self._settings, "reddit_client_secret", None)
        )

    def status(self) -> ProviderStatus:
        if not self._is_configured():
            return ProviderStatus.not_configured
        try:
            import praw  # noqa: F401
            return ProviderStatus.active
        except ImportError:
            return ProviderStatus.unavailable

    async def fetch(self, symbol: str, limit: int = 30) -> list[CommunityMention]:
        if not self._is_configured():
            return []
        try:
            import praw
        except ImportError:
            return []

        mentions = []
        try:
            reddit = praw.Reddit(
                client_id=self._settings.reddit_client_id,
                client_secret=self._settings.reddit_client_secret,
                user_agent=getattr(self._settings, "reddit_user_agent", "livermore-research/1.0"),
                read_only=True,
            )
            subreddits = ["wallstreetbets", "investing", "stocks"]
            for sub in subreddits:
                results = reddit.subreddit(sub).search(
                    f"${symbol}", sort="new", time_filter="week", limit=limit // len(subreddits)
                )
                for post in results:
                    from datetime import datetime
                    mentions.append(CommunityMention(
                        provider="reddit",
                        platform="Reddit",
                        symbol=symbol.upper(),
                        title=post.title,
                        text=post.selftext[:500] if post.selftext else post.title,
                        author=str(post.author) if post.author else None,
                        community_name=sub,
                        url=f"https://reddit.com{post.permalink}",
                        published_at=datetime.utcfromtimestamp(post.created_utc),
                        upvotes=post.score,
                        comments=post.num_comments,
                    ))
        except Exception:
            pass
        return mentions
