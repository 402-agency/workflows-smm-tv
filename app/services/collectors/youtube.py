"""YouTube collector: find videos for a title and pull top comments."""

from __future__ import annotations

from datetime import datetime

from app.schemas.dto import SocialPostDTO, TitleDTO
from app.services.collectors.base import HTTPCollector


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class YouTubeCollector(HTTPCollector):
    source = "youtube"
    base_url = "https://www.googleapis.com/youtube/v3"
    rate_bucket = "youtube"

    def __init__(self, settings=None, client=None) -> None:
        super().__init__(settings, client)
        if self.settings.youtube_api_key:
            self.default_params = {"key": self.settings.youtube_api_key}

    @property
    def enabled(self) -> bool:
        return bool(self.settings.youtube_api_key)

    async def collect(self, dto: TitleDTO, limit: int) -> list[SocialPostDTO]:
        if not self.enabled:
            self.log.warning("youtube_disabled_no_key")
            return []

        kind = "movie" if dto.type == "movie" else "TV series"
        query = f"{dto.title} {kind} review trailer"
        search = await self.get_json(
            "/search",
            params={
                "q": query,
                "part": "snippet",
                "type": "video",
                "maxResults": 3,
                "order": "relevance",
            },
            cache_ttl=3600,
        )
        video_ids = [
            item["id"]["videoId"]
            for item in (search or {}).get("items", [])
            if item.get("id", {}).get("videoId")
        ]

        posts: list[SocialPostDTO] = []
        per_video = max(1, limit // max(1, len(video_ids)))
        for video_id in video_ids:
            if len(posts) >= limit:
                break
            posts.extend(await self._comments(video_id, per_video))
        return posts[:limit]

    async def _comments(self, video_id: str, limit: int) -> list[SocialPostDTO]:
        data = await self.get_json(
            "/commentThreads",
            params={
                "part": "snippet",
                "videoId": video_id,
                "maxResults": min(limit, 50),
                "order": "relevance",
                "textFormat": "plainText",
            },
            cache_ttl=3600,
        )
        out: list[SocialPostDTO] = []
        for item in (data or {}).get("items", []):
            top = (
                item.get("snippet", {})
                .get("topLevelComment", {})
                .get("snippet", {})
            )
            text = (top.get("textDisplay") or "").strip()
            if not text:
                continue
            out.append(
                SocialPostDTO(
                    source="youtube",
                    platform_id=item["id"],
                    content=text,
                    author=top.get("authorDisplayName"),
                    posted_at=_parse_ts(top.get("publishedAt")),
                    engagement={"likeCount": int(top.get("likeCount") or 0)},
                    url=f"https://www.youtube.com/watch?v={video_id}",
                )
            )
        return out
