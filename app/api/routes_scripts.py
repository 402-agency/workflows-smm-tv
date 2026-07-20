"""GET /scripts/{id} and POST /scripts/generate (regenerate AI content)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep, require_auth
from app.api.serializers import script_to_out
from app.core.errors import ConflictError, NotFoundError
from app.repositories import PipelineRunRepository, ScriptRepository
from app.schemas.api import EnqueuedOut, GenerateRequest, ScriptOut
from app.workers.queue import enqueue_regenerate

router = APIRouter(tags=["scripts"])


@router.get("/scripts/{script_id}", response_model=ScriptOut)
async def get_script(script_id: int, session: SessionDep) -> ScriptOut:
    script = await ScriptRepository(session).get(script_id)
    if script is None:
        raise NotFoundError("Script not found")
    return script_to_out(script)


@router.post(
    "/scripts/generate",
    response_model=EnqueuedOut,
    dependencies=[Depends(require_auth)],
)
async def generate_content(body: GenerateRequest, session: SessionDep) -> EnqueuedOut:
    run_id = body.run_id
    if run_id is None:
        run = await PipelineRunRepository(session).latest_successful()
        if run is None:
            raise ConflictError("No completed run to regenerate from")
        run_id = run.id
    else:
        if await PipelineRunRepository(session).get(run_id) is None:
            raise NotFoundError("Run not found")
    await enqueue_regenerate(run_id)
    return EnqueuedOut(run_id=run_id)
