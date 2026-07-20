from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select

from app.models.social_post import SocialPost
from app.repositories.base import BaseRepository


class SocialPostRepository(BaseRepository[SocialPost]):
    model = SocialPost

    async def get_by_platform(self, source: str, platform_id: str) -> SocialPost | None:
        result = await self.session.execute(
            select(SocialPost).where(
                SocialPost.source == source,
                SocialPost.platform_id == str(platform_id),
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self, title_id: int, source: str, platform_id: str, **fields: Any
    ) -> SocialPost:
        existing = await self.get_by_platform(source, platform_id)
        if existing is None:
            post = SocialPost(
                title_id=title_id,
                source=source,
                platform_id=str(platform_id),
                **fields,
            )
            self.session.add(post)
            await self.session.flush()
            return post
        for key, value in fields.items():
            setattr(existing, key, value)
        await self.session.flush()
        return existing

    async def list_for_title(self, title_id: int, limit: int | None = None) -> list[SocialPost]:
        stmt = select(SocialPost).where(SocialPost.title_id == title_id)
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_title(self, title_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(SocialPost)
            .where(SocialPost.title_id == title_id)
        )
        return int(result.scalar_one())

    async def delete_for_title(self, title_id: int) -> None:
        await self.session.execute(
            delete(SocialPost).where(SocialPost.title_id == title_id)
        )
