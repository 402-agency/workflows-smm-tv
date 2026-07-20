from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, obj_id: int) -> ModelType | None:
        return await self.session.get(self.model, obj_id)

    def add(self, obj: ModelType) -> ModelType:
        self.session.add(obj)
        return obj

    def add_all(self, objs: Sequence[ModelType]) -> None:
        self.session.add_all(list(objs))

    async def delete(self, obj: ModelType) -> None:
        await self.session.delete(obj)

    async def count(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return int(result.scalar_one())

    async def flush(self) -> None:
        await self.session.flush()
