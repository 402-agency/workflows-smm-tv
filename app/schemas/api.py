"""API request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class RatingOut(BaseModel):
    source: str
    average_rating: float | None = None
    review_count: int | None = None
    critic_score: float | None = None
    audience_score: float | None = None


class SentimentOut(BaseModel):
    counts: dict[str, int]
    total: int
    shares: dict[str, float]


class TitleSummaryOut(BaseModel):
    id: int
    title: str
    type: str
    release_date: date | None = None
    popularity: float = 0.0
    genres: list[str] = []
    poster_url: str | None = None
    overview: str | None = None
    score: float | None = None
    position: int | None = None
    sentiment: SentimentOut | None = None


class ReviewOut(BaseModel):
    source: str
    author: str | None = None
    content: str
    rating: float | None = None
    url: str | None = None


class SocialPostOut(BaseModel):
    source: str
    content: str
    author: str | None = None
    url: str | None = None
    engagement: dict[str, Any] = {}
    posted_at: datetime | None = None


class AISummaryOut(BaseModel):
    summary: str | None = None
    strengths: list[str] = []
    weaknesses: list[str] = []
    audience_reception: str | None = None
    notable_topics: list[str] = []
    recommendation: str | None = None
    provider: str | None = None
    model: str | None = None
    created_at: datetime | None = None


class TitleDetailOut(TitleSummaryOut):
    ratings: list[RatingOut] = []
    ai_summary: AISummaryOut | None = None
    reviews: list[ReviewOut] = []
    social_sample: list[SocialPostOut] = []


class ScriptOut(BaseModel):
    id: int
    pipeline_run_id: int | None = None
    title_id: int | None = None
    hook: str | None = None
    narration: str | None = None
    ranked_list: list[dict] = []
    cta: str | None = None
    video_title: str | None = None
    thumbnail_text: str | None = None
    hashtags: list[str] = []
    description: str | None = None
    provider: str | None = None
    model: str | None = None
    created_at: datetime | None = None


class TrendItemOut(BaseModel):
    position: int
    score: float
    title: TitleSummaryOut


class RunOut(BaseModel):
    id: int
    status: str
    trigger: str
    current_node: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    stats: dict = {}
    created_at: datetime | None = None
    progress: dict | None = None


class EnqueuedOut(BaseModel):
    run_id: int
    status: str = "queued"


class GenerateRequest(BaseModel):
    run_id: int | None = None
