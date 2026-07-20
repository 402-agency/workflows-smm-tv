"""TMDB collector: trending discovery, metadata enrichment, review excerpts."""

from __future__ import annotations

from datetime import date, datetime

from app.schemas.dto import RatingDTO, ReviewDTO, TitleDTO
from app.services.collectors.base import HTTPCollector

_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


class TMDBCollector(HTTPCollector):
    source = "tmdb"
    base_url = "https://api.themoviedb.org/3"
    rate_bucket = "tmdb"

    def __init__(self, settings=None, client=None) -> None:
        super().__init__(settings, client)
        if self.settings.tmdb_api_key:
            self.default_params = {"api_key": self.settings.tmdb_api_key}
        self._genre_cache: dict[str, dict[int, str]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.settings.tmdb_api_key)

    async def _genre_map(self, media_type: str) -> dict[int, str]:
        if media_type in self._genre_cache:
            return self._genre_cache[media_type]
        data = await self.get_json(f"/genre/{media_type}/list", cache_ttl=86400)
        mapping = {g["id"]: g["name"] for g in (data or {}).get("genres", [])}
        self._genre_cache[media_type] = mapping
        return mapping

    async def discover_trending(self, window: str, limit: int) -> list[TitleDTO]:
        if not self.enabled:
            self.log.warning("tmdb_disabled_no_key")
            return []
        window = window if window in ("day", "week") else "day"
        items: list[TitleDTO] = []
        for media_type in ("movie", "tv"):
            data = await self.get_json(
                f"/trending/{media_type}/{window}", cache_ttl=3600
            )
            genre_map = await self._genre_map(media_type)
            for row in (data or {}).get("results", []):
                title_text = row.get("title") or row.get("name") or "Untitled"
                items.append(
                    TitleDTO(
                        source="tmdb",
                        external_id=f"{media_type}:{row['id']}",
                        tmdb_id=row.get("id"),
                        title=title_text,
                        type="movie" if media_type == "movie" else "tv",
                        release_date=_parse_date(
                            row.get("release_date") or row.get("first_air_date")
                        ),
                        popularity=float(row.get("popularity") or 0.0),
                        genres=[
                            genre_map[g]
                            for g in row.get("genre_ids", [])
                            if g in genre_map
                        ],
                        overview=row.get("overview"),
                        poster_url=(
                            f"{_IMAGE_BASE}{row['poster_path']}"
                            if row.get("poster_path")
                            else None
                        ),
                    )
                )
        items.sort(key=lambda t: t.popularity, reverse=True)
        return items[:limit]

    async def enrich(self, dto: TitleDTO) -> RatingDTO | None:
        """Fill imdb_id/genres/overview from details; return the TMDB rating."""
        if not self.enabled or not dto.tmdb_id:
            return None
        media_type = "movie" if dto.type == "movie" else "tv"
        data = await self.get_json(
            f"/{media_type}/{dto.tmdb_id}",
            params={"append_to_response": "external_ids"},
            cache_ttl=86400,
        )
        if not data:
            return None
        dto.imdb_id = dto.imdb_id or (data.get("external_ids") or {}).get("imdb_id")
        if data.get("genres"):
            dto.genres = [g["name"] for g in data["genres"]]
        dto.overview = dto.overview or data.get("overview")
        vote_average = data.get("vote_average")
        vote_count = data.get("vote_count")
        if vote_average is None:
            return None
        return RatingDTO(
            source="tmdb",
            average_rating=float(vote_average),
            review_count=int(vote_count) if vote_count is not None else None,
            audience_score=round(float(vote_average) * 10, 1),
        )

    async def fetch_reviews(self, dto: TitleDTO, limit: int) -> list[ReviewDTO]:
        if not self.enabled or not dto.tmdb_id:
            return []
        media_type = "movie" if dto.type == "movie" else "tv"
        data = await self.get_json(
            f"/{media_type}/{dto.tmdb_id}/reviews", cache_ttl=3600
        )
        reviews: list[ReviewDTO] = []
        for row in (data or {}).get("results", [])[:limit]:
            content = (row.get("content") or "").strip()
            if not content:
                continue
            details = row.get("author_details") or {}
            reviews.append(
                ReviewDTO(
                    source="tmdb",
                    author=row.get("author"),
                    content=content,
                    rating=details.get("rating"),
                    url=row.get("url"),
                )
            )
        return reviews
