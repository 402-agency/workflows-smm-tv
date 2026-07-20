from __future__ import annotations

from sqlalchemy import delete, select

from app.models.rating import Rating
from app.repositories.base import BaseRepository


class RatingRepository(BaseRepository[Rating]):
    model = Rating

    async def list_for_title(self, title_id: int) -> list[Rating]:
        result = await self.session.execute(
            select(Rating).where(Rating.title_id == title_id)
        )
        return list(result.scalars().all())

    async def delete_for_title(self, title_id: int) -> None:
        await self.session.execute(delete(Rating).where(Rating.title_id == title_id))

    def create(self, title_id: int, source: str, **fields) -> Rating:
        rating = Rating(title_id=title_id, source=source, **fields)
        self.session.add(rating)
        return rating
