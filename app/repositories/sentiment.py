from __future__ import annotations

from sqlalchemy import delete, func, select

from app.models.enums import SentimentLabel
from app.models.sentiment_result import SentimentResult
from app.repositories.base import BaseRepository


class SentimentRepository(BaseRepository[SentimentResult]):
    model = SentimentResult

    def create(
        self,
        title_id: int,
        content_type: str,
        content_id: int,
        label: str,
        confidence: float,
        model_name: str,
    ) -> SentimentResult:
        row = SentimentResult(
            title_id=title_id,
            content_type=content_type,
            content_id=content_id,
            label=label,
            confidence=confidence,
            model_name=model_name,
        )
        self.session.add(row)
        return row

    async def delete_for_title(self, title_id: int) -> None:
        await self.session.execute(
            delete(SentimentResult).where(SentimentResult.title_id == title_id)
        )

    async def aggregate_for_title(self, title_id: int) -> dict:
        result = await self.session.execute(
            select(SentimentResult.label, func.count())
            .where(SentimentResult.title_id == title_id)
            .group_by(SentimentResult.label)
        )
        counts = {label: 0 for label in SentimentLabel.ALL}
        for label, count in result.all():
            counts[label] = int(count)
        total = sum(counts.values())
        shares = {
            label: (counts[label] / total if total else 0.0) for label in counts
        }
        return {"counts": counts, "total": total, "shares": shares}
