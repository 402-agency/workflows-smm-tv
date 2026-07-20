"""Normalised data-transfer objects produced by collectors.

Collectors translate provider-specific payloads into these so the rest of
the pipeline never sees a provider's raw shape.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TitleDTO(BaseModel):
    source: str = "tmdb"
    external_id: str
    tmdb_id: int | None = None
    imdb_id: str | None = None
    title: str
    type: str  # "movie" | "tv"
    release_date: date | None = None
    popularity: float = 0.0
    genres: list[str] = Field(default_factory=list)
    overview: str | None = None
    poster_url: str | None = None

    @property
    def year(self) -> int | None:
        return self.release_date.year if self.release_date else None


class RatingDTO(BaseModel):
    source: str  # tmdb | imdb | rotten_tomatoes | metacritic
    average_rating: float | None = None
    review_count: int | None = None
    critic_score: float | None = None
    audience_score: float | None = None


class ReviewDTO(BaseModel):
    source: str
    author: str | None = None
    content: str
    rating: float | None = None
    url: str | None = None


class SocialPostDTO(BaseModel):
    source: str  # reddit | youtube
    platform_id: str
    content: str
    author: str | None = None
    posted_at: datetime | None = None
    engagement: dict = Field(default_factory=dict)
    url: str | None = None
