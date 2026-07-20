"""Assemble and compile the LangGraph pipeline."""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    ai_analysis_node,
    discovery_node,
    metadata_node,
    persistence_node,
    ranking_node,
    reviews_node,
    script_generation_node,
    sentiment_node,
    social_collection_node,
)
from app.graph.state import PipelineState

try:  # RetryPolicy moved across langgraph versions
    from langgraph.types import RetryPolicy
except ImportError:  # pragma: no cover
    from langgraph.pregel import RetryPolicy  # type: ignore

# Ordered (name, callable) — linear pipeline per the brief.
_NODES = [
    ("discovery", discovery_node),
    ("metadata", metadata_node),
    ("reviews", reviews_node),
    ("social_collection", social_collection_node),
    ("sentiment", sentiment_node),
    ("ranking", ranking_node),
    ("ai_analysis", ai_analysis_node),
    ("script_generation", script_generation_node),
    ("persistence", persistence_node),
]


def build_graph():
    graph = StateGraph(PipelineState)
    retry = RetryPolicy(max_attempts=3)

    for name, fn in _NODES:
        graph.add_node(name, fn, retry=retry)

    graph.add_edge(START, _NODES[0][0])
    for (prev, _), (nxt, _) in zip(_NODES, _NODES[1:]):
        graph.add_edge(prev, nxt)
    graph.add_edge(_NODES[-1][0], END)

    return graph.compile()


@lru_cache
def get_compiled_graph():
    return build_graph()
