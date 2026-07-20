from __future__ import annotations

from sqlalchemy import select

from app.models.script import Script
from app.repositories.base import BaseRepository


class ScriptRepository(BaseRepository[Script]):
    model = Script

    def create(self, **fields) -> Script:
        script = Script(**fields)
        self.session.add(script)
        return script

    async def latest(self) -> Script | None:
        result = await self.session.execute(
            select(Script).order_by(Script.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 20) -> list[Script]:
        result = await self.session.execute(
            select(Script).order_by(Script.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def for_run(self, run_id: int) -> Script | None:
        result = await self.session.execute(
            select(Script)
            .where(Script.pipeline_run_id == run_id)
            .order_by(Script.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
