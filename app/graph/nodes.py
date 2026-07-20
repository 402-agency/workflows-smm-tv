"""LangGraph pipeline nodes.

Nine linear nodes: discovery -> metadata -> reviews -> social_collection ->
sentiment -> ranking -> ai_analysis -> script_generation -> persistence.

Each node persists its own results in a short transaction and updates the
run's current node + live Redis progress, so a failure leaves partial results
behind and the dashboard can show where a run is.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.core import redis as redis_helpers
from app.core.logging import get_logger
from app.database import session_scope
from app.models.enums import ContentType
from app.models.pipeline_run import PipelineRun
from app.models.review import Review
from app.models.social_post import SocialPost
from app.repositories import (
    AISummaryRepository,
    RankingRepository,
    RatingRepository,
    ReviewRepository,
    SentimentRepository,
    SocialPostRepository,
    TitleRepository,
)
from app.services.ai import get_ai_provider
from app.services.analyzers import SentimentAnalyzer
from app.services.collectors import (
    OMDbCollector,
    RedditCollector,
    TMDBCollector,
    YouTubeCollector,
)
from app.services.ranking import RankingEngine, TitleFeatures

_log = get_logger("graph")


async def _stage(run_id: int, node: str, **progress: Any) -> None:
    """Mark the current node in the DB run row and publish live progress."""
    async with session_scope() as session:
        run = await session.get(PipelineRun, run_id)
        if run is not None:
            run.current_node = node
    await redis_helpers.set_progress(run_id, current_node=node, **progress)


def _title_updates(dto) -> dict:
    return {
        "tmdb_id": dto.tmdb_id,
        "imdb_id": dto.imdb_id,
        "title": dto.title,
        "type": dto.type,
        "release_date": dto.release_date,
        "popularity": dto.popularity,
        "genres": dto.genres,
        "overview": dto.overview,
        "poster_url": dto.poster_url,
    }


# ---------------------------------------------------------------------------
# 1. Discovery
# ---------------------------------------------------------------------------
async def discovery_node(state: dict) -> dict:
    run_id = state["run_id"]
    await _stage(run_id, "discovery")
    settings = get_settings()

    async with TMDBCollector(settings) as tmdb:
        dtos = await tmdb.discover_trending(state["window"], state["max_titles"])

    titles: list[dict] = []
    async with session_scope() as session:
        repo = TitleRepository(session)
        for dto in dtos:
            row = await repo.upsert(dto.source, dto.external_id, **_title_updates(dto))
            titles.append({"id": row.id, "dto": dto})

    await redis_helpers.set_progress(run_id, discovered=len(titles))
    _log.info("discovery_complete", run_id=run_id, count=len(titles))
    return {"titles": titles, "stats": {"discovered": len(titles)}}


# ---------------------------------------------------------------------------
# 2. Metadata + ratings
# ---------------------------------------------------------------------------
async def metadata_node(state: dict) -> dict:
    run_id = state["run_id"]
    await _stage(run_id, "metadata")
    settings = get_settings()
    titles = state.get("titles", [])

    ratings_by_title: dict[int, list] = {}
    async with TMDBCollector(settings) as tmdb, OMDbCollector(settings) as omdb:
        for entry in titles:
            dto = entry["dto"]
            collected = []
            tmdb_rating = await tmdb.enrich(dto)
            if tmdb_rating:
                collected.append(tmdb_rating)
            collected.extend(await omdb.fetch(dto))
            ratings_by_title[entry["id"]] = collected

    total_ratings = 0
    async with session_scope() as session:
        title_repo = TitleRepository(session)
        rating_repo = RatingRepository(session)
        for entry in titles:
            dto = entry["dto"]
            await title_repo.upsert(dto.source, dto.external_id, **_title_updates(dto))
            await rating_repo.delete_for_title(entry["id"])
            for rating in ratings_by_title.get(entry["id"], []):
                rating_repo.create(
                    entry["id"],
                    rating.source,
                    average_rating=rating.average_rating,
                    review_count=rating.review_count,
                    critic_score=rating.critic_score,
                    audience_score=rating.audience_score,
                )
                total_ratings += 1

    await redis_helpers.set_progress(run_id, ratings=total_ratings)
    _log.info("metadata_complete", run_id=run_id, ratings=total_ratings)
    return {"stats": {"ratings": total_ratings}}


# ---------------------------------------------------------------------------
# 3. Reviews
# ---------------------------------------------------------------------------
async def reviews_node(state: dict) -> dict:
    run_id = state["run_id"]
    await _stage(run_id, "reviews")
    settings = get_settings()
    titles = state.get("titles", [])

    reviews_by_title: dict[int, list] = {}
    async with TMDBCollector(settings) as tmdb:
        for entry in titles:
            reviews_by_title[entry["id"]] = await tmdb.fetch_reviews(
                entry["dto"], state["reviews_per_title"]
            )

    total = 0
    async with session_scope() as session:
        repo = ReviewRepository(session)
        for entry in titles:
            await repo.delete_for_title(entry["id"])
            for review in reviews_by_title.get(entry["id"], []):
                repo.create(
                    entry["id"],
                    review.source,
                    review.content,
                    author=review.author,
                    rating=review.rating,
                    url=review.url,
                )
                total += 1

    await redis_helpers.set_progress(run_id, reviews=total)
    _log.info("reviews_complete", run_id=run_id, reviews=total)
    return {"stats": {"reviews": total}}


# ---------------------------------------------------------------------------
# 4. Social collection
# ---------------------------------------------------------------------------
async def social_collection_node(state: dict) -> dict:
    run_id = state["run_id"]
    await _stage(run_id, "social_collection")
    settings = get_settings()
    titles = state.get("titles", [])
    per_title = state["social_posts_per_title"]

    posts_by_title: dict[int, list] = {}
    async with RedditCollector(settings) as reddit, YouTubeCollector(settings) as yt:
        for entry in titles:
            dto = entry["dto"]
            reddit_share = max(1, per_title // 2)
            posts = await reddit.collect(dto, reddit_share)
            posts += await yt.collect(dto, per_title - len(posts))
            posts_by_title[entry["id"]] = posts

    total = 0
    async with session_scope() as session:
        repo = SocialPostRepository(session)
        for entry in titles:
            await repo.delete_for_title(entry["id"])
            for post in posts_by_title.get(entry["id"], []):
                await repo.upsert(
                    entry["id"],
                    post.source,
                    post.platform_id,
                    content=post.content,
                    author=post.author,
                    posted_at=post.posted_at,
                    engagement=post.engagement,
                    url=post.url,
                )
                total += 1

    await redis_helpers.set_progress(run_id, social_posts=total)
    _log.info("social_complete", run_id=run_id, social_posts=total)
    return {"stats": {"social_posts": total}}


# ---------------------------------------------------------------------------
# 5. Sentiment
# ---------------------------------------------------------------------------
async def sentiment_node(state: dict) -> dict:
    run_id = state["run_id"]
    await _stage(run_id, "sentiment")
    titles = state.get("titles", [])
    analyzer = SentimentAnalyzer()

    total = 0
    for entry in titles:
        title_id = entry["id"]
        async with session_scope() as session:
            reviews = (
                await session.execute(
                    select(Review.id, Review.content).where(Review.title_id == title_id)
                )
            ).all()
            posts = (
                await session.execute(
                    select(SocialPost.id, SocialPost.content).where(
                        SocialPost.title_id == title_id
                    )
                )
            ).all()

            items = [(ContentType.REVIEW, r[0], r[1]) for r in reviews]
            items += [(ContentType.SOCIAL_POST, p[0], p[1]) for p in posts]
            if not items:
                continue

            outcomes = analyzer.classify([text for (_, _, text) in items])
            sentiment_repo = SentimentRepository(session)
            await sentiment_repo.delete_for_title(title_id)
            for (content_type, content_id, _), outcome in zip(items, outcomes):
                sentiment_repo.create(
                    title_id=title_id,
                    content_type=content_type,
                    content_id=content_id,
                    label=outcome.label,
                    confidence=outcome.confidence,
                    model_name=analyzer.model_name,
                )
                total += 1

    await redis_helpers.set_progress(run_id, sentiment_items=total)
    _log.info("sentiment_complete", run_id=run_id, items=total)
    return {"stats": {"sentiment_items": total}}


# ---------------------------------------------------------------------------
# 6. Ranking
# ---------------------------------------------------------------------------
def _rating_component(ratings: list) -> float:
    """Best available rating as a 0..1 value."""
    for r in ratings:
        if r.audience_score is not None:
            return max(0.0, min(1.0, r.audience_score / 100.0))
    for r in ratings:
        if r.critic_score is not None:
            return max(0.0, min(1.0, r.critic_score / 100.0))
    for r in ratings:
        if r.average_rating is not None:
            return max(0.0, min(1.0, r.average_rating / 10.0))
    return 0.0


def _engagement_sum(posts: list) -> float:
    total = 0.0
    for post in posts:
        for value in (post.engagement or {}).values():
            if isinstance(value, (int, float)):
                total += float(value)
    return total


async def ranking_node(state: dict) -> dict:
    run_id = state["run_id"]
    await _stage(run_id, "ranking")
    titles = state.get("titles", [])
    weights = state.get("weights") or get_settings().ranking_weights

    features: list[TitleFeatures] = []
    async with session_scope() as session:
        rating_repo = RatingRepository(session)
        review_repo = ReviewRepository(session)
        social_repo = SocialPostRepository(session)
        sentiment_repo = SentimentRepository(session)

        for entry in titles:
            title_id = entry["id"]
            dto = entry["dto"]
            ratings = await rating_repo.list_for_title(title_id)
            posts = await social_repo.list_for_title(title_id)
            agg = await sentiment_repo.aggregate_for_title(title_id)
            review_rows = await review_repo.count_for_title(title_id)
            imdb_votes = next(
                (r.review_count for r in ratings if r.source == "imdb" and r.review_count),
                0,
            )
            shares = agg["shares"]
            features.append(
                TitleFeatures(
                    title_id=title_id,
                    popularity=dto.popularity,
                    rating=_rating_component(ratings),
                    review_volume=float(review_rows + (imdb_votes or 0)),
                    sentiment=shares["positive"] - shares["negative"],
                    discussion_volume=float(len(posts)),
                    engagement=_engagement_sum(posts),
                )
            )

    results = RankingEngine(weights).rank(features)

    async with session_scope() as session:
        ranking_repo = RankingRepository(session)
        await ranking_repo.delete_for_run(run_id)
        for res in results:
            ranking_repo.create(
                title_id=res.title_id,
                pipeline_run_id=run_id,
                score=res.score,
                position=res.position,
                components=res.components,
                weights_snapshot=res.weights_snapshot,
            )

    ranking_state = [
        {"title_id": r.title_id, "score": r.score, "position": r.position}
        for r in results
    ]
    await redis_helpers.set_progress(run_id, ranked=len(results))
    _log.info("ranking_complete", run_id=run_id, count=len(results))
    return {"ranked": ranking_state, "stats": {"ranked": len(results)}}


# ---------------------------------------------------------------------------
# 7. AI analysis
# ---------------------------------------------------------------------------
async def _analysis_context(session, title_id: int, dto) -> dict:
    rating_repo = RatingRepository(session)
    review_repo = ReviewRepository(session)
    social_repo = SocialPostRepository(session)
    sentiment_repo = SentimentRepository(session)

    ratings = await rating_repo.list_for_title(title_id)
    reviews = await review_repo.list_for_title(title_id, limit=5)
    posts = await social_repo.list_for_title(title_id, limit=8)
    agg = await sentiment_repo.aggregate_for_title(title_id)
    return {
        "title": dto.title,
        "type": dto.type,
        "release_year": dto.year,
        "genres": dto.genres,
        "overview": dto.overview,
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


async def ai_analysis_node(state: dict) -> dict:
    run_id = state["run_id"]
    await _stage(run_id, "ai_analysis")
    provider = get_ai_provider()
    if not provider.available:
        _log.warning("ai_analysis_skipped_provider_unavailable", run_id=run_id)
        await redis_helpers.set_progress(run_id, ai_summaries=0, ai_skipped=True)
        return {"stats": {"ai_summaries": 0}}

    ranking = state.get("ranked", [])
    top_ids = [r["title_id"] for r in ranking[: state["top_n"]]]
    dto_by_id = {e["id"]: e["dto"] for e in state.get("titles", [])}

    generated = 0
    for title_id in top_ids:
        dto = dto_by_id.get(title_id)
        if dto is None:
            continue
        async with session_scope() as session:
            context = await _analysis_context(session, title_id, dto)
        try:
            result = await provider.generate_analysis(context)
        except Exception as exc:  # noqa: BLE001
            _log.warning("ai_analysis_failed", title_id=title_id, error=str(exc))
            continue
        async with session_scope() as session:
            AISummaryRepository(session).create(
                title_id=title_id,
                pipeline_run_id=run_id,
                summary=result.summary,
                strengths=result.strengths,
                weaknesses=result.weaknesses,
                audience_reception=result.audience_reception,
                notable_topics=result.notable_topics,
                recommendation=result.recommendation,
                provider=provider.name,
                model=get_settings().openai_model,
            )
        generated += 1
        await redis_helpers.set_progress(run_id, ai_summaries=generated)

    _log.info("ai_analysis_complete", run_id=run_id, generated=generated)
    return {"stats": {"ai_summaries": generated}}


# ---------------------------------------------------------------------------
# 8. Script generation
# ---------------------------------------------------------------------------
async def script_generation_node(state: dict) -> dict:
    run_id = state["run_id"]
    await _stage(run_id, "script_generation")
    provider = get_ai_provider()
    if not provider.available:
        _log.warning("script_skipped_provider_unavailable", run_id=run_id)
        return {"script_id": None, "stats": {"script": 0}}

    ranking = state.get("ranked", [])[: state["top_n"]]
    dto_by_id = {e["id"]: e["dto"] for e in state.get("titles", [])}

    titles_ctx = []
    async with session_scope() as session:
        rating_repo = RatingRepository(session)
        sentiment_repo = SentimentRepository(session)
        summary_repo = AISummaryRepository(session)
        for item in ranking:
            title_id = item["title_id"]
            dto = dto_by_id.get(title_id)
            if dto is None:
                continue
            ratings = await rating_repo.list_for_title(title_id)
            agg = await sentiment_repo.aggregate_for_title(title_id)
            summary = await summary_repo.latest_for_title(title_id)
            titles_ctx.append(
                {
                    "position": item["position"],
                    "title": dto.title,
                    "type": dto.type,
                    "score": item["score"],
                    "ratings": [
                        {"source": r.source, "critic": r.critic_score, "audience": r.audience_score}
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

    if not titles_ctx:
        return {"script_id": None, "stats": {"script": 0}}

    try:
        result = await provider.generate_script({"titles": titles_ctx})
    except Exception as exc:  # noqa: BLE001
        _log.warning("script_generation_failed", run_id=run_id, error=str(exc))
        return {"script_id": None, "stats": {"script": 0}, "errors": [f"script: {exc}"]}

    async with session_scope() as session:
        from app.repositories import ScriptRepository

        script = ScriptRepository(session).create(
            pipeline_run_id=run_id,
            title_id=None,
            hook=result.hook,
            narration=result.narration,
            ranked_list=[item.model_dump() for item in result.ranked_list],
            cta=result.cta,
            video_title=result.video_title,
            thumbnail_text=result.thumbnail_text,
            hashtags=result.hashtags,
            description=result.description,
            provider=provider.name,
            model=get_settings().openai_model,
        )
        await session.flush()
        script_id = script.id

    await redis_helpers.set_progress(run_id, script_id=script_id)
    _log.info("script_complete", run_id=run_id, script_id=script_id)
    return {"script_id": script_id, "stats": {"script": 1}}


# ---------------------------------------------------------------------------
# 9. Persistence (finalise stats)
# ---------------------------------------------------------------------------
async def persistence_node(state: dict) -> dict:
    run_id = state["run_id"]
    await _stage(run_id, "persistence")
    stats = state.get("stats", {})
    async with session_scope() as session:
        run = await session.get(PipelineRun, run_id)
        if run is not None:
            run.stats = stats
    await redis_helpers.set_progress(run_id, finalized=True)
    _log.info("persistence_complete", run_id=run_id, stats=stats)
    return {}
