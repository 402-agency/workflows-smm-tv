"""Pipeline graph state.

Kept in-memory (no checkpointer), so nodes may pass rich Python objects. The
source of truth for collected data is the database — nodes persist
incrementally and later nodes re-read from the DB — so this state stays lean:
the working set of titles plus accumulators for stats/errors.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_dict(existing: dict, update: dict) -> dict:
    return {**(existing or {}), **(update or {})}


class PipelineState(TypedDict, total=False):
    run_id: int

    # Config snapshot for this run.
    window: str
    max_titles: int
    top_n: int
    reviews_per_title: int
    social_posts_per_title: int
    weights: dict

    # Working set: [{"id": title_id, "dto": TitleDTO}]
    titles: list[dict[str, Any]]
    # Ranking results as plain dicts (title_id, score, position, ...)
    ranked: list[dict[str, Any]]
    script_id: int | None

    stats: Annotated[dict, _merge_dict]
    errors: Annotated[list, operator.add]
