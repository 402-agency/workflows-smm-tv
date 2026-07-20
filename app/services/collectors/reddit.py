"""Reddit collector via asyncpraw (read-only).

Searches movie/TV subreddits for a title and returns submissions plus a few
top comments as normalised social posts. Degrades to an empty list when
credentials are missing or the API errors.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.dto import SocialPostDTO, TitleDTO
from app.services.collectors.base import HTTPCollector

_SUBREDDITS = "movies+television+entertainment"


class RedditCollector(HTTPCollector):
    source = "reddit"
    rate_bucket = "reddit"

    def __init__(self, settings=None, client=None) -> None:
        super().__init__(settings, client)
        self._reddit = None

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.reddit_client_id and self.settings.reddit_client_secret
        )

    async def __aenter__(self) -> "RedditCollector":
        if self.enabled:
            import asyncpraw

            self._reddit = asyncpraw.Reddit(
                client_id=self.settings.reddit_client_id,
                client_secret=self.settings.reddit_client_secret,
                user_agent=self.settings.reddit_user_agent,
                check_for_async=False,
            )
            self._reddit.read_only = True
        return self

    async def __aexit__(self, *exc) -> None:
        if self._reddit is not None:
            await self._reddit.close()
            self._reddit = None

    async def collect(self, dto: TitleDTO, limit: int) -> list[SocialPostDTO]:
        if not self.enabled or self._reddit is None:
            if not self.enabled:
                self.log.warning("reddit_disabled_no_credentials")
            return []

        posts: list[SocialPostDTO] = []
        sub_limit = max(1, limit // 3)
        try:
            subreddit = await self._reddit.subreddit(_SUBREDDITS)
            async for submission in subreddit.search(
                f'"{dto.title}"', sort="relevance", time_filter="year", limit=sub_limit
            ):
                text = f"{submission.title}\n{submission.selftext or ''}".strip()
                posts.append(
                    SocialPostDTO(
                        source="reddit",
                        platform_id=f"t3_{submission.id}",
                        content=text,
                        author=str(submission.author) if submission.author else None,
                        posted_at=datetime.fromtimestamp(
                            submission.created_utc, tz=timezone.utc
                        ),
                        engagement={
                            "score": int(submission.score),
                            "num_comments": int(submission.num_comments),
                            "upvote_ratio": float(
                                getattr(submission, "upvote_ratio", 0.0)
                            ),
                        },
                        url=f"https://www.reddit.com{submission.permalink}",
                    )
                )
                posts.extend(await self._top_comments(submission, limit - len(posts)))
                if len(posts) >= limit:
                    break
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            self.log.warning("reddit_collect_failed", title=dto.title, error=str(exc))

        return posts[:limit]

    async def _top_comments(self, submission, budget: int) -> list[SocialPostDTO]:
        if budget <= 0:
            return []
        out: list[SocialPostDTO] = []
        try:
            submission.comment_sort = "top"
            await submission.load()
            await submission.comments.replace_more(limit=0)
            for comment in submission.comments.list()[: min(budget, 5)]:
                body = getattr(comment, "body", "") or ""
                if not body.strip():
                    continue
                out.append(
                    SocialPostDTO(
                        source="reddit",
                        platform_id=f"t1_{comment.id}",
                        content=body,
                        author=str(comment.author) if comment.author else None,
                        posted_at=datetime.fromtimestamp(
                            comment.created_utc, tz=timezone.utc
                        ),
                        engagement={"score": int(getattr(comment, "score", 0))},
                        url=f"https://www.reddit.com{submission.permalink}",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            self.log.debug("reddit_comments_failed", error=str(exc))
        return out
