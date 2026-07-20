from __future__ import annotations

from sqlalchemy import select

from app.models.ai_summary import AISummary
from app.repositories.base import BaseRepository


class AISummaryRepository(BaseRepository[AISummary]):
    model = AISummary

    def create(self, title_id: int, **fields) -> AISummary:
        summary = AISummary(title_id=title_id, **fields)
        self.session.add(summary)
        return summary

    async def latest_for_title(self, title_id: int) -> AISummary | None:
        result = await self.session.execute(
            select(AISummary)
            .where(AISummary.title_id == title_id)
            .order_by(AISummary.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
