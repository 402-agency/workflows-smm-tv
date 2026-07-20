"""Liveness / readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__
from app.core import redis as redis_helpers
from app.database import session_scope

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    db_ok = False
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    redis_ok = await redis_helpers.ping()
    status = "ok" if (db_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "version": __version__,
        "checks": {"database": db_ok, "redis": redis_ok},
    }
