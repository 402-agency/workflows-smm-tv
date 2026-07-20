"""Build API response models from ORM rows (composed reads)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ranking import Ranking
from app.models.script import Script
from app.models.title import Title
from app.repositories import (
    AISummaryRepository,
    RatingRepository,
    ReviewRepository,
    SentimentRepository,
    SocialPostRepository,
)
from app.schemas.api import (
    AISummaryOut,
    RatingOut,
    ReviewOut,
    RunOut,
    ScriptOut,
    SentimentOut,
    SocialPostOut,
    TitleDetailOut,
    TitleSummaryOut,
)


async def build_sentiment(session: AsyncSession, title_id: int) -> SentimentOut:
    agg = await SentimentRepository(session).aggregate_for_title(title_id)
    return SentimentOut(**agg)


def _summary_kwargs(title: Title, ranking: Ranking | None) -> dict:
    return {
        "id": title.id,
        "title": title.title,
        "type": title.type,
        "release_date": title.release_date,
        "popularity": title.popularity,
        "genres": title.genres or [],
        "poster_url": title.poster_url,
        "overview": title.overview,
        "score": ranking.score if ranking else None,
        "position": ranking.position if ranking else None,
    }


async def build_title_summary(
    session: AsyncSession,
    title: Title,
    ranking: Ranking | None = None,
    include_sentiment: bool = True,
) -> TitleSummaryOut:
    kwargs = _summary_kwargs(title, ranking)
    if include_sentiment:
        kwargs["sentiment"] = await build_sentiment(session, title.id)
    return TitleSummaryOut(**kwargs)


async def build_title_detail(
    session: AsyncSession, title: Title, ranking: Ranking | None = None
) -> TitleDetailOut:
    ratings = await RatingRepository(session).list_for_title(title.id)
    reviews = await ReviewRepository(session).list_for_title(title.id, limit=8)
    posts = await SocialPostRepository(session).list_for_title(title.id, limit=12)
    summary = await AISummaryRepository(session).latest_for_title(title.id)

    return TitleDetailOut(
        **_summary_kwargs(title, ranking),
        sentiment=await build_sentiment(session, title.id),
        ratings=[RatingOut.model_validate(r, from_attributes=True) for r in ratings],
        reviews=[ReviewOut.model_validate(r, from_attributes=True) for r in reviews],
        social_sample=[
            SocialPostOut.model_validate(p, from_attributes=True) for p in posts
        ],
        ai_summary=(
            AISummaryOut.model_validate(summary, from_attributes=True)
            if summary
            else None
        ),
    )


def script_to_out(script: Script) -> ScriptOut:
    return ScriptOut.model_validate(script, from_attributes=True)


def run_to_out(run, progress: dict | None = None) -> RunOut:
    out = RunOut.model_validate(run, from_attributes=True)
    if progress:
        out.progress = progress
    return out
