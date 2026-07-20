"""Base HTTP collector: shared client, Redis response cache, rate limiting
and retry with exponential backoff.

Subclasses set ``source``/``base_url``/``rate_bucket`` and (optionally)
``default_params`` for auth query params. ``default_params`` are injected at
request time and deliberately excluded from cache keys so API keys never leak
into Redis.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, get_settings
from app.core import redis as redis_helpers
from app.core.logging import get_logger


class _RetryableHTTP(Exception):
    """Raised for 429/5xx so tenacity retries the request."""


class HTTPCollector:
    source: str = "http"
    base_url: str = ""
    rate_bucket: str = "http"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self.default_params: dict[str, Any] = {}
        self.log = get_logger(f"collector.{self.source}")

    # -- lifecycle ---------------------------------------------------
    async def __aenter__(self) -> "HTTPCollector":
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(20.0),
                headers={"User-Agent": "trend-analyzer/0.1"},
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def enabled(self) -> bool:  # overridden by subclasses that need keys
        return True

    # -- request pipeline -------------------------------------------
    def _cache_key(self, path: str, params: dict[str, Any]) -> str:
        blob = json.dumps(params, sort_keys=True, default=str)
        return f"{self.source}:{path}:{blob}"

    async def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        use_cache: bool = True,
        cache_ttl: int | None = None,
    ) -> Any | None:
        params = params or {}
        key = self._cache_key(path, params)
        if use_cache:
            cached = await redis_helpers.cache_get(key)
            if cached is not None:
                return cached

        await redis_helpers.rate_limit_acquire(
            self.rate_bucket, self.settings.rate_limit_per_second
        )
        try:
            data = await self._request(path, params)
        except (_RetryableHTTP, httpx.HTTPError) as exc:
            self.log.warning("request_failed", path=path, error=str(exc))
            return None

        if use_cache and data is not None:
            await redis_helpers.cache_set(
                key, data, cache_ttl or self.settings.cache_ttl_seconds
            )
        return data

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception_type((httpx.TransportError, _RetryableHTTP)),
    )
    async def _request(self, path: str, params: dict[str, Any]) -> Any | None:
        assert self._client is not None
        merged = {**params, **self.default_params}
        resp = await self._client.get(path, params=merged)
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _RetryableHTTP(f"status={resp.status_code}")
        if resp.status_code >= 400:
            self.log.warning(
                "http_client_error",
                status=resp.status_code,
                path=path,
                body=resp.text[:200],
            )
            return None
        try:
            return resp.json()
        except json.JSONDecodeError:
            return None
