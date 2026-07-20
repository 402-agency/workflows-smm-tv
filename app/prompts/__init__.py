"""Prompt template loading."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


@lru_cache
def load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8").strip()
