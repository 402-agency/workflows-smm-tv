"""Regenerate AI content (analyses + script) for an existing run without
re-collecting data. Reuses the rankings and collected signals already in the DB.
"""

from __future__ import annotations

from app.config import get_settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger
from app.database import session_scope
from app.graph.context import build_analysis_context, build_script_context
from app.repositories import (
    AISummaryRepository,
    RankingRepository,
    ScriptRepository,
)
from app.services.ai import get_ai_provider

_log = get_logger("regeneration")


async def regenerate_run_ai(run_id: int) -> dict:
    provider = get_ai_provider()
    if not provider.available:
        raise ConfigurationError("AI provider is not configured")

    settings = get_settings()
    async with session_scope() as session:
        rankings = await RankingRepository(session).list_for_run(
            run_id, limit=settings.top_n
        )
        ranked_items = [
            {"title_id": r.title_id, "position": r.position, "score": r.score}
            for r in rankings
        ]

    if not ranked_items:
        _log.warning("regenerate_no_rankings", run_id=run_id)
        return {"summaries": 0, "script_id": None}

    summaries = 0
    for item in ranked_items:
        title_id = item["title_id"]
        async with session_scope() as session:
            context = await build_analysis_context(session, title_id)
        if context is None:
            continue
        try:
            result = await provider.generate_analysis(context)
        except Exception as exc:  # noqa: BLE001
            _log.warning("regenerate_analysis_failed", title_id=title_id, error=str(exc))
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
                model=settings.openai_model,
            )
        summaries += 1

    async with session_scope() as session:
        script_context = await build_script_context(session, ranked_items)

    script_id = None
    if script_context["titles"]:
        try:
            script_result = await provider.generate_script(script_context)
        except Exception as exc:  # noqa: BLE001
            _log.warning("regenerate_script_failed", run_id=run_id, error=str(exc))
            script_result = None
        if script_result is not None:
            async with session_scope() as session:
                script = ScriptRepository(session).create(
                    pipeline_run_id=run_id,
                    title_id=None,
                    hook=script_result.hook,
                    narration=script_result.narration,
                    ranked_list=[i.model_dump() for i in script_result.ranked_list],
                    cta=script_result.cta,
                    video_title=script_result.video_title,
                    thumbnail_text=script_result.thumbnail_text,
                    hashtags=script_result.hashtags,
                    description=script_result.description,
                    provider=provider.name,
                    model=settings.openai_model,
                )
                await session.flush()
                script_id = script.id

    _log.info("regenerate_complete", run_id=run_id, summaries=summaries, script_id=script_id)
    return {"summaries": summaries, "script_id": script_id}
