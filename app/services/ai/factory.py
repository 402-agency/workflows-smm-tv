"""Select the configured AI provider.

Only OpenAI is implemented today, but the interface + factory make adding a
Claude provider a drop-in change (implement AIProvider, register it here).
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.services.ai.base import AIProvider
from app.services.ai.openai_provider import OpenAIProvider

_log = get_logger("ai.factory")


def get_ai_provider(settings: Settings | None = None) -> AIProvider:
    settings = settings or get_settings()
    provider = (settings.ai_provider or "openai").lower()
    if provider not in ("openai",):
        _log.warning("unknown_ai_provider_defaulting_openai", requested=provider)
    return OpenAIProvider(settings)
