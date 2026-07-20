from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.title import Title
from app.repositories.base import BaseRepository

_UPSERTABLE = {
    "tmdb_id",
    "imdb_id",
    "title",
    "type",
    "release_date",
    "popularity",
    "genres",
    "overview",
    "poster_url",
}


class TitleRepository(BaseRepository[Title]):
    model = Title

    async def get_by_external(self, source: str, external_id: str) -> Title | None:
        result = await self.session.execute(
            select(Title).where(
                Title.source == source, Title.external_id == str(external_id)
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, source: str, external_id: str, **fields: Any) -> Title:
        """Insert or update a title, keyed by (source, external_id)."""
        existing = await self.get_by_external(source, external_id)
        payload = {k: v for k, v in fields.items() if k in _UPSERTABLE}
        if existing is None:
            title = Title(source=source, external_id=str(external_id), **payload)
            self.session.add(title)
            await self.session.flush()
            return title
        for key, value in payload.items():
            setattr(existing, key, value)
        await self.session.flush()
        return existing

    async def search(
        self,
        *,
        q: str | None = None,
        type_: str | None = None,
        genre: str | None = None,
        order_by: str = "popularity",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Title]:
        stmt = select(Title)
        if q:
            stmt = stmt.where(Title.title.ilike(f"%{q}%"))
        if type_:
            stmt = stmt.where(Title.type == type_)

        order_col = {
            "popularity": Title.popularity.desc(),
            "title": Title.title.asc(),
            "created": Title.created_at.desc(),
        }.get(order_by, Title.popularity.desc())

        # Genre is stored as a JSON array; JSON containment varies across
        # backends, so filter it in Python. Widen the DB fetch when filtering
        # by genre so pagination still yields a full page.
        fetch_limit = limit if not genre else limit + offset + 200
        stmt = stmt.order_by(order_col).limit(fetch_limit)
        if not genre:
            stmt = stmt.offset(offset)

        result = await self.session.execute(stmt)
        titles = list(result.scalars().all())
        if genre:
            titles = [t for t in titles if genre in (t.genres or [])]
            titles = titles[offset : offset + limit]
        return titles
