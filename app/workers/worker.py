"""ARQ worker: runs the pipeline (and AI regeneration) off the web process.

No cron/scheduler — jobs are enqueued only on demand (dashboard button /
POST /pipeline/run). A Redis distributed lock guarantees a single pipeline run
executes at a time; ``max_jobs=1`` enforces the same at the worker level.
"""

from __future__ import annotations

from arq.connections import RedisSettings

from app.config import get_settings
from app.core import redis as redis_helpers
from app.core.logging import configure_logging, get_logger
from app.database import dispose_engine
from app.graph.runner import execute_run
from app.repositories import PipelineRunRepository
from app.services.regeneration import regenerate_run_ai
from app.database import session_scope

_PIPELINE_LOCK = "pipeline"


async def run_pipeline_task(ctx: dict, run_id: int) -> dict:
    log = get_logger("worker")
    async with redis_helpers.try_lock(_PIPELINE_LOCK, ttl=3600) as acquired:
        if not acquired:
            log.warning("pipeline_run_rejected_locked", run_id=run_id)
            async with session_scope() as session:
                repo = PipelineRunRepository(session)
                run = await repo.get(run_id)
                if run is not None:
                    await repo.mark_failed(
                        run, "Another pipeline run is already in progress"
                    )
            return {"skipped": True, "run_id": run_id}
        # execute_run marks the run failed on error; swallow here so ARQ does
        # not retry (the run row is the source of truth for status).
        try:
            await execute_run(run_id)
            return {"ok": True, "run_id": run_id}
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline_task_error", run_id=run_id, error=str(exc))
            return {"ok": False, "run_id": run_id, "error": str(exc)}


async def regenerate_ai_task(ctx: dict, run_id: int) -> dict:
    try:
        return await regenerate_run_ai(run_id)
    except Exception as exc:  # noqa: BLE001
        get_logger("worker").warning(
            "regenerate_task_error", run_id=run_id, error=str(exc)
        )
        return {"ok": False, "run_id": run_id, "error": str(exc)}


async def on_startup(ctx: dict) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    get_logger("worker").info("worker_startup")


async def on_shutdown(ctx: dict) -> None:
    await dispose_engine()
    await redis_helpers.close_redis()
    get_logger("worker").info("worker_shutdown")


class WorkerSettings:
    functions = [run_pipeline_task, regenerate_ai_task]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = 1
    job_timeout = 3600
    keep_result = 3600
