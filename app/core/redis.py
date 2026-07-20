"""Redis helpers: shared client, response cache, distributed lock,
rate limiter and live pipeline progress state.

All keys are namespaced under ``ta:`` to keep the ARQ queue (which uses its
own keys) and our helpers from colliding.
"""

from __future__ import annotations

import contextlib
import json
import time
from typing import Any, AsyncIterator

import redis.asyncio as aioredis

from app.config import get_settings
from app.core.logging import get_logger

_log = get_logger("redis")
_NS = "ta:"

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the process-wide async Redis client (lazily created)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception as exc:  # pragma: no cover - connectivity failure path
        _log.warning("redis_ping_failed", error=str(exc))
        return False


# --------------------------------------------------------------------------
# Response cache
# --------------------------------------------------------------------------
async def cache_get(key: str) -> Any | None:
    raw = await get_redis().get(f"{_NS}cache:{key}")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    await get_redis().set(f"{_NS}cache:{key}", json.dumps(value), ex=ttl)


# --------------------------------------------------------------------------
# Rate limiting (fixed 1-second window token counter per bucket)
# --------------------------------------------------------------------------
async def rate_limit_acquire(bucket: str, per_second: int) -> None:
    """Block (cooperatively) until a slot is free for ``bucket``.

    A simple fixed-window counter: at most ``per_second`` calls per wall-clock
    second. Good enough to stay polite to external APIs.
    """
    if per_second <= 0:
        return
    client = get_redis()
    while True:
        window = int(time.time())
        key = f"{_NS}rl:{bucket}:{window}"
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 2)
        if count <= per_second:
            return
        # Sleep until the next window opens.
        import asyncio

        await asyncio.sleep(max(0.0, (window + 1) - time.time()) + 0.01)


# --------------------------------------------------------------------------
# Distributed lock (single pipeline run at a time)
# --------------------------------------------------------------------------
@contextlib.asynccontextmanager
async def try_lock(name: str, ttl: int = 3600) -> AsyncIterator[bool]:
    """Best-effort lock. Yields True if acquired, False otherwise.

    Never blocks: callers decide what to do when the lock is already held.
    """
    client = get_redis()
    key = f"{_NS}lock:{name}"
    token = str(time.time_ns())
    acquired = await client.set(key, token, nx=True, ex=ttl)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            # Only release if we still own it.
            current = await client.get(key)
            if current == token:
                await client.delete(key)


# --------------------------------------------------------------------------
# Live pipeline progress state
# --------------------------------------------------------------------------
def _progress_key(run_id: int | str) -> str:
    return f"{_NS}progress:{run_id}"


async def set_progress(run_id: int | str, **fields: Any) -> None:
    key = _progress_key(run_id)
    mapping = {k: json.dumps(v) for k, v in fields.items()}
    if mapping:
        await get_redis().hset(key, mapping=mapping)
        await get_redis().expire(key, 86400)


async def get_progress(run_id: int | str) -> dict[str, Any]:
    raw = await get_redis().hgetall(_progress_key(run_id))
    out: dict[str, Any] = {}
    for k, v in raw.items():
        try:
            out[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            out[k] = v
    return out
