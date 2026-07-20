"""Run the compiled pipeline for a given run id and manage its lifecycle."""

from __future__ import annotations

import traceback

from app.config import get_settings
from app.core.logging import get_logger
from app.database import session_scope
from app.graph.build import get_compiled_graph
from app.repositories import PipelineRunRepository

_log = get_logger("graph.runner")


def _initial_state(run_id: int) -> dict:
    settings = get_settings()
    return {
        "run_id": run_id,
        "window": settings.trending_window,
        "max_titles": settings.max_titles,
        "top_n": settings.top_n,
        "reviews_per_title": settings.reviews_per_title,
        "social_posts_per_title": settings.social_posts_per_title,
        "weights": settings.ranking_weights,
        "stats": {},
        "titles": [],
        "ranked": [],
        "errors": [],
    }


async def execute_run(run_id: int) -> dict:
    """Mark the run running, invoke the graph, and finalise its status."""
    async with session_scope() as session:
        repo = PipelineRunRepository(session)
        run = await repo.get(run_id)
        if run is None:
            raise ValueError(f"pipeline run {run_id} not found")
        await repo.mark_running(run, node="discovery")

    graph = get_compiled_graph()
    try:
        final = await graph.ainvoke(_initial_state(run_id))
    except Exception as exc:  # noqa: BLE001
        _log.exception("pipeline_failed", run_id=run_id)
        async with session_scope() as session:
            repo = PipelineRunRepository(session)
            run = await repo.get(run_id)
            if run is not None:
                await repo.mark_failed(run, f"{exc}\n{traceback.format_exc()}")
        raise

    stats = final.get("stats", {})
    async with session_scope() as session:
        repo = PipelineRunRepository(session)
        run = await repo.get(run_id)
        if run is not None:
            await repo.mark_success(run, stats=stats)

    _log.info("pipeline_succeeded", run_id=run_id, stats=stats)
    return final
