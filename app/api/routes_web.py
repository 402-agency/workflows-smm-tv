"""Server-rendered dashboard (Jinja2 + Tailwind, full-page reloads)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import SessionDep, require_auth
from app.core.errors import AppError, NotFoundError
from app.models.enums import RunStatus
from app.repositories import (
    AISummaryRepository,
    PipelineRunRepository,
    RankingRepository,
    RatingRepository,
    ReviewRepository,
    ScriptRepository,
    SentimentRepository,
    SocialPostRepository,
    TitleRepository,
)
from app.workers.queue import enqueue_pipeline_run, enqueue_regenerate

router = APIRouter(tags=["web"], include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


async def _sentiment_pct(session, title_id: int) -> dict:
    agg = await SentimentRepository(session).aggregate_for_title(title_id)
    shares = agg["shares"]
    return {
        "positive": round(shares["positive"] * 100),
        "neutral": round(shares["neutral"] * 100),
        "negative": round(shares["negative"] * 100),
        "total": agg["total"],
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: SessionDep,
    q: str | None = Query(None),
    type_: str | None = Query(None, alias="type"),
    genre: str | None = Query(None),
    order_by: str = Query("popularity"),
    message: str | None = Query(None),
):
    run = await PipelineRunRepository(session).latest_successful()
    title_repo = TitleRepository(session)
    ranking_repo = RankingRepository(session)

    items: list[dict] = []
    searching = bool(q or type_ or genre)
    if searching or run is None:
        titles = await title_repo.search(
            q=q, type_=type_, genre=genre, order_by=order_by, limit=60
        )
        ranking_map = await ranking_repo.latest_map([t.id for t in titles])
        for t in titles:
            items.append(
                {
                    "title": t,
                    "ranking": ranking_map.get(t.id),
                    "sentiment": await _sentiment_pct(session, t.id),
                }
            )
    else:
        rankings = await ranking_repo.list_for_run(run.id)
        for r in rankings:
            items.append(
                {
                    "title": r.title,
                    "ranking": r,
                    "sentiment": await _sentiment_pct(session, r.title_id),
                }
            )

    script = await ScriptRepository(session).for_run(run.id) if run else None

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "items": items,
            "run": run,
            "script": script,
            "searching": searching,
            "filters": {"q": q or "", "type": type_ or "", "genre": genre or "", "order_by": order_by},
            "message": message,
        },
    )


@router.get("/title/{title_id}", response_class=HTMLResponse)
async def title_page(title_id: int, request: Request, session: SessionDep):
    title = await TitleRepository(session).get(title_id)
    if title is None:
        raise NotFoundError("Title not found")
    ranking = await RankingRepository(session).latest_for_title(title_id)
    ratings = await RatingRepository(session).list_for_title(title_id)
    reviews = await ReviewRepository(session).list_for_title(title_id, limit=6)
    posts = await SocialPostRepository(session).list_for_title(title_id, limit=10)
    summary = await AISummaryRepository(session).latest_for_title(title_id)
    return templates.TemplateResponse(
        request,
        "title_detail.html",
        {
            "title": title,
            "ranking": ranking,
            "ratings": ratings,
            "reviews": reviews,
            "posts": posts,
            "summary": summary,
            "sentiment": await _sentiment_pct(session, title_id),
        },
    )


@router.get("/runs", response_class=HTMLResponse)
async def runs_page(request: Request, session: SessionDep, message: str | None = Query(None)):
    runs = await PipelineRunRepository(session).list_recent(30)
    active = any(r.status in (RunStatus.PENDING, RunStatus.RUNNING) for r in runs)
    return templates.TemplateResponse(
        request,
        "runs.html",
        {"runs": runs, "active": active, "message": message},
    )


@router.get("/script/{script_id}", response_class=HTMLResponse)
async def script_page(script_id: int, request: Request, session: SessionDep):
    script = await ScriptRepository(session).get(script_id)
    if script is None:
        raise NotFoundError("Script not found")
    return templates.TemplateResponse(request, "script.html", {"script": script})


@router.post("/actions/run", dependencies=[Depends(require_auth)])
async def action_run() -> RedirectResponse:
    try:
        await enqueue_pipeline_run()
        msg = "Pipeline run started."
    except AppError as exc:
        msg = exc.message
    return RedirectResponse(url=f"/runs?message={msg}", status_code=303)


@router.post("/actions/regenerate", dependencies=[Depends(require_auth)])
async def action_regenerate(
    session: SessionDep, run_id: int | None = Form(None)
) -> RedirectResponse:
    if run_id is None:
        run = await PipelineRunRepository(session).latest_successful()
        run_id = run.id if run else None
    if run_id is None:
        return RedirectResponse(url="/runs?message=No+run+to+regenerate", status_code=303)
    await enqueue_regenerate(run_id)
    return RedirectResponse(
        url="/runs?message=AI+regeneration+started", status_code=303
    )
