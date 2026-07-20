"""Enqueue helpers used by the API/dashboard to trigger background jobs."""

from __future__ import annotations

from app.config import get_settings
from app.core.errors import ConflictError
from app.core.logging import get_logger
from app.database import session_scope
from app.models.enums import RunTrigger
from app.repositories import PipelineRunRepository

_log = get_logger("queue")
_pool = None


async def get_pool():
    """Lazily create the shared ARQ Redis pool."""
    global _pool
    if _pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue_pipeline_run(trigger: str = RunTrigger.MANUAL) -> int:
    """Create a pending run and enqueue it. Rejects if one is already active."""
    async with session_scope() as session:
        repo = PipelineRunRepository(session)
        if await repo.active_exists():
            raise ConflictError("A pipeline run is already in progress")
        run = await repo.create(trigger=trigger)
        run_id = run.id

    pool = await get_pool()
    await pool.enqueue_job("run_pipeline_task", run_id)
    _log.info("pipeline_run_enqueued", run_id=run_id)
    return run_id


async def enqueue_regenerate(run_id: int) -> None:
    pool = await get_pool()
    await pool.enqueue_job("regenerate_ai_task", run_id)
    _log.info("regenerate_enqueued", run_id=run_id)
