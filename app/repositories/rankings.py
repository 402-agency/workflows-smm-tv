from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.models.ranking import Ranking
from app.repositories.base import BaseRepository


class RankingRepository(BaseRepository[Ranking]):
    model = Ranking

    def create(
        self,
        title_id: int,
        pipeline_run_id: int,
        score: float,
        position: int,
        components: dict,
        weights_snapshot: dict,
    ) -> Ranking:
        ranking = Ranking(
            title_id=title_id,
            pipeline_run_id=pipeline_run_id,
            score=score,
            position=position,
            components=components,
            weights_snapshot=weights_snapshot,
        )
        self.session.add(ranking)
        return ranking

    async def delete_for_run(self, run_id: int) -> None:
        await self.session.execute(
            delete(Ranking).where(Ranking.pipeline_run_id == run_id)
        )

    async def list_for_run(self, run_id: int, limit: int | None = None) -> list[Ranking]:
        stmt = (
            select(Ranking)
            .where(Ranking.pipeline_run_id == run_id)
            .order_by(Ranking.position.asc())
            .options(selectinload(Ranking.title))
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_title(self, title_id: int) -> Ranking | None:
        result = await self.session.execute(
            select(Ranking)
            .where(Ranking.title_id == title_id)
            .order_by(Ranking.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_map(self, title_ids: list[int]) -> dict[int, Ranking]:
        """Most-recent ranking per title id."""
        if not title_ids:
            return {}
        result = await self.session.execute(
            select(Ranking)
            .where(Ranking.title_id.in_(title_ids))
            .order_by(Ranking.created_at.desc())
        )
        out: dict[int, Ranking] = {}
        for ranking in result.scalars().all():
            out.setdefault(ranking.title_id, ranking)
        return out
