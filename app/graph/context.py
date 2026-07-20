"""Build AI prompt context from persisted data (DB is the source of truth).

Shared by the pipeline's AI nodes and the standalone AI-regeneration path so
both send the model exactly the same shape of grounded context.
"""

from __future__ import annotations

from app.models.title import Title
from app.repositories import (
    AISummaryRepository,
    RatingRepository,
    ReviewRepository,
    SentimentRepository,
    SocialPostRepository,
)


def _year(title: Title) -> int | None:
    return title.release_date.year if title.release_date else None


async def build_analysis_context(session, title_id: int) -> dict | None:
    title = await session.get(Title, title_id)
    if title is None:
        return None

    ratings = await RatingRepository(session).list_for_title(title_id)
    reviews = await ReviewRepository(session).list_for_title(title_id, limit=5)
    posts = await SocialPostRepository(session).list_for_title(title_id, limit=8)
    agg = await SentimentRepository(session).aggregate_for_title(title_id)

    return {
        "title": title.title,
        "type": title.type,
        "release_year": _year(title),
        "genres": title.genres,
        "overview": title.overview,
        "ratings": [
            {
                "source": r.source,
                "average_rating": r.average_rating,
                "critic_score": r.critic_score,
                "audience_score": r.audience_score,
                "review_count": r.review_count,
            }
            for r in ratings
        ],
        "sentiment": agg,
        "sample_reviews": [r.content[:600] for r in reviews],
        "sample_social": [p.content[:300] for p in posts],
    }


async def build_script_context(session, ranked_items: list[dict]) -> dict:
    """`ranked_items` are dicts with title_id/position/score (top-N, ordered)."""
    rating_repo = RatingRepository(session)
    sentiment_repo = SentimentRepository(session)
    summary_repo = AISummaryRepository(session)

    titles_ctx: list[dict] = []
    for item in ranked_items:
        title_id = item["title_id"]
        title = await session.get(Title, title_id)
        if title is None:
            continue
        ratings = await rating_repo.list_for_title(title_id)
        agg = await sentiment_repo.aggregate_for_title(title_id)
        summary = await summary_repo.latest_for_title(title_id)
        titles_ctx.append(
            {
                "position": item.get("position"),
                "title": title.title,
                "type": title.type,
                "score": item.get("score"),
                "ratings": [
                    {
                        "source": r.source,
                        "critic": r.critic_score,
                        "audience": r.audience_score,
                    }
                    for r in ratings
                ],
                "sentiment_shares": agg["shares"],
                "analysis": (
                    {
                        "summary": summary.summary,
                        "strengths": summary.strengths,
                        "weaknesses": summary.weaknesses,
                        "recommendation": summary.recommendation,
                    }
                    if summary
                    else None
                ),
            }
        )
    return {"titles": titles_ctx}
