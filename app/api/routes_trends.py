"""GET /trends — the latest successful run's ranked titles."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import SessionDep, SettingsDep
from app.api.serializers import build_title_summary
from app.repositories import PipelineRunRepository, RankingRepository
from app.schemas.api import TrendItemOut

router = APIRouter(tags=["trends"])


@router.get("/trends", response_model=list[TrendItemOut])
async def get_trends(
    session: SessionDep,
    settings: SettingsDep,
    limit: int | None = Query(None, ge=1, le=100),
) -> list[TrendItemOut]:
    run = await PipelineRunRepository(session).latest_successful()
    if run is None:
        return []
    rankings = await RankingRepository(session).list_for_run(
        run.id, limit=limit or settings.top_n
    )
    items: list[TrendItemOut] = []
    for ranking in rankings:
        summary = await build_title_summary(session, ranking.title, ranking)
        items.append(
            TrendItemOut(position=ranking.position, score=ranking.score, title=summary)
        )
    return items
