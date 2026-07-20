"""AI provider interface + structured result models.

Concrete providers (OpenAI now; Claude could be added later) implement
:class:`AIProvider`. Results are pydantic models with tolerant coercion so a
slightly-off LLM JSON response degrades to sensible defaults rather than
raising.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]


class AnalysisResult(BaseModel):
    model_config = {"extra": "ignore"}

    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    audience_reception: str = ""
    notable_topics: list[str] = Field(default_factory=list)
    recommendation: str = ""

    @field_validator("strengths", "weaknesses", "notable_topics", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[str]:
        return _as_str_list(v)


class RankedItem(BaseModel):
    model_config = {"extra": "ignore"}

    position: int = 0
    title: str = ""
    blurb: str = ""


class ScriptResult(BaseModel):
    model_config = {"extra": "ignore"}

    hook: str = ""
    ranked_list: list[RankedItem] = Field(default_factory=list)
    narration: str = ""
    cta: str = ""
    video_title: str = ""
    thumbnail_text: str = ""
    hashtags: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("hashtags", mode="before")
    @classmethod
    def _coerce_hashtags(cls, v: Any) -> list[str]:
        return _as_str_list(v)


class AIProvider(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether the provider has the credentials/config to run."""

    @abstractmethod
    async def generate_analysis(self, context: dict) -> AnalysisResult:
        ...

    @abstractmethod
    async def generate_script(self, context: dict) -> ScriptResult:
        ...
