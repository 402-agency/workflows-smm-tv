"""GET /titles and /titles/{id}."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.api.serializers import build_title_detail, build_title_summary
from app.core.errors import NotFoundError
from app.repositories import RankingRepository, TitleRepository
from app.schemas.api import TitleDetailOut, TitleSummaryOut

router = APIRouter(tags=["titles"])


@router.get("/titles", response_model=list[TitleSummaryOut])
async def list_titles(
    session: SessionDep,
    q: str | None = Query(None, description="search in title"),
    type_: str | None = Query(None, alias="type"),
    genre: str | None = Query(None),
    order_by: str = Query("popularity", pattern="^(popularity|title|created)$"),
    min_score: float | None = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[TitleSummaryOut]:
    titles = await TitleRepository(session).search(
        q=q, type_=type_, genre=genre, order_by=order_by, limit=limit, offset=offset
    )
    ranking_map = await RankingRepository(session).latest_map([t.id for t in titles])

    out: list[TitleSummaryOut] = []
    for title in titles:
        ranking = ranking_map.get(title.id)
        if min_score is not None and (ranking is None or ranking.score < min_score):
            continue
        out.append(await build_title_summary(session, title, ranking))
    return out


@router.get("/titles/{title_id}", response_model=TitleDetailOut)
async def get_title(title_id: int, session: SessionDep) -> TitleDetailOut:
    title = await TitleRepository(session).get(title_id)
    if title is None:
        raise NotFoundError("Title not found")
    ranking = await RankingRepository(session).latest_for_title(title_id)
    return await build_title_detail(session, title, ranking)
