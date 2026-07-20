from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.models.enums import RunStatus, RunTrigger
from app.models.pipeline_run import PipelineRun
from app.repositories.base import BaseRepository


class PipelineRunRepository(BaseRepository[PipelineRun]):
    model = PipelineRun

    async def create(self, trigger: str = RunTrigger.MANUAL) -> PipelineRun:
        run = PipelineRun(status=RunStatus.PENDING, trigger=trigger, stats={})
        self.session.add(run)
        await self.session.flush()
        return run

    async def list_recent(self, limit: int = 20) -> list[PipelineRun]:
        result = await self.session.execute(
            select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def latest_successful(self) -> PipelineRun | None:
        result = await self.session.execute(
            select(PipelineRun)
            .where(PipelineRun.status == RunStatus.SUCCESS)
            .order_by(PipelineRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def active_exists(self) -> bool:
        result = await self.session.execute(
            select(PipelineRun.id).where(
                PipelineRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING])
            )
        )
        return result.first() is not None

    async def mark_running(self, run: PipelineRun, node: str | None = None) -> None:
        run.status = RunStatus.RUNNING
        if run.started_at is None:
            run.started_at = datetime.utcnow()
        if node:
            run.current_node = node
        await self.session.flush()

    async def set_node(self, run: PipelineRun, node: str) -> None:
        run.current_node = node
        await self.session.flush()

    async def mark_success(self, run: PipelineRun, stats: dict | None = None) -> None:
        run.status = RunStatus.SUCCESS
        run.current_node = None
        run.finished_at = datetime.utcnow()
        if stats is not None:
            run.stats = stats
        await self.session.flush()

    async def mark_failed(self, run: PipelineRun, error: str) -> None:
        run.status = RunStatus.FAILED
        run.finished_at = datetime.utcnow()
        run.error = error[:4000]
        await self.session.flush()
