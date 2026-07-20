"""OpenAI implementation of the AIProvider interface (JSON-mode chat)."""

from __future__ import annotations

import json
import time
from typing import Any

from app.config import Settings, get_settings
from app.core.errors import ConfigurationError, ProviderError
from app.core.logging import get_logger
from app.prompts import load_prompt
from app.services.ai.base import AIProvider, AnalysisResult, ScriptResult

_log = get_logger("ai.openai")


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.settings.openai_api_key)

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        return self._client

    async def _complete_json(self, system: str, context: dict) -> dict[str, Any]:
        client = self._get_client()
        started = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": "DATA (JSON):\n"
                        + json.dumps(context, default=str, ensure_ascii=False),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
        except Exception as exc:  # noqa: BLE001 - normalise SDK errors
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

        usage = getattr(resp, "usage", None)
        _log.info(
            "openai_completion",
            model=self.settings.openai_model,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )

        content = resp.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError("OpenAI returned non-JSON content") from exc

    async def generate_analysis(self, context: dict) -> AnalysisResult:
        if not self.available:
            raise ConfigurationError("OpenAI API key not configured")
        data = await self._complete_json(load_prompt("analysis"), context)
        return AnalysisResult.model_validate(data)

    async def generate_script(self, context: dict) -> ScriptResult:
        if not self.available:
            raise ConfigurationError("OpenAI API key not configured")
        data = await self._complete_json(load_prompt("script"), context)
        return ScriptResult.model_validate(data)
