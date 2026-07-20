"""Pipeline control: POST /pipeline/run, GET /pipeline/runs[/id]."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, require_auth
from app.api.serializers import run_to_out
from app.core import redis as redis_helpers
from app.core.errors import NotFoundError
from app.repositories import PipelineRunRepository
from app.schemas.api import EnqueuedOut, RunOut
from app.workers.queue import enqueue_pipeline_run

router = APIRouter(tags=["pipeline"])


@router.post(
    "/pipeline/run",
    response_model=EnqueuedOut,
    dependencies=[Depends(require_auth)],
)
async def run_pipeline() -> EnqueuedOut:
    run_id = await enqueue_pipeline_run()
    return EnqueuedOut(run_id=run_id)


@router.get("/pipeline/runs", response_model=list[RunOut])
async def list_runs(
    session: SessionDep, limit: int = Query(20, ge=1, le=100)
) -> list[RunOut]:
    runs = await PipelineRunRepository(session).list_recent(limit)
    return [run_to_out(run) for run in runs]


@router.get("/pipeline/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: int, session: SessionDep) -> RunOut:
    run = await PipelineRunRepository(session).get(run_id)
    if run is None:
        raise NotFoundError("Run not found")
    progress = await redis_helpers.get_progress(run_id)
    return run_to_out(run, progress)
