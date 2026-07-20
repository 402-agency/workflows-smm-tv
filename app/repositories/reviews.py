from __future__ import annotations

from sqlalchemy import delete, func, select

from app.models.review import Review
from app.repositories.base import BaseRepository


class ReviewRepository(BaseRepository[Review]):
    model = Review

    async def list_for_title(self, title_id: int, limit: int | None = None) -> list[Review]:
        stmt = select(Review).where(Review.title_id == title_id)
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_title(self, title_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(Review).where(Review.title_id == title_id)
        )
        return int(result.scalar_one())

    async def delete_for_title(self, title_id: int) -> None:
        await self.session.execute(delete(Review).where(Review.title_id == title_id))

    def create(self, title_id: int, source: str, content: str, **fields) -> Review:
        review = Review(title_id=title_id, source=source, content=content, **fields)
        self.session.add(review)
        return review
