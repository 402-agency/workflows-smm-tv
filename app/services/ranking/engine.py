"""Configurable, weighted trend-ranking engine.

Each title contributes six raw signals. Volume-like signals (popularity,
review volume, discussion volume, engagement) are min-max normalised across the
batch so no single high-magnitude signal dominates; rating and sentiment are
already bounded. The final score is a weighted sum of the normalised
components, with weights taken from configuration and re-normalised to sum 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

COMPONENTS = (
    "popularity",
    "rating",
    "review_volume",
    "sentiment",
    "discussion_volume",
    "engagement",
)

# Volume-like signals that need cross-batch min-max normalisation.
_NORMALISE = ("popularity", "review_volume", "discussion_volume", "engagement")


@dataclass
class TitleFeatures:
    title_id: int
    popularity: float = 0.0
    rating: float = 0.0  # already 0..1 (best available rating / its scale)
    review_volume: float = 0.0
    sentiment: float = 0.0  # (pos_share - neg_share) in [-1, 1]
    discussion_volume: float = 0.0
    engagement: float = 0.0


@dataclass
class RankingResult:
    title_id: int
    score: float
    position: int
    components: dict = field(default_factory=dict)
    weights_snapshot: dict = field(default_factory=dict)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    filtered = {k: max(0.0, float(weights.get(k, 0.0))) for k in COMPONENTS}
    total = sum(filtered.values())
    if total <= 0:
        return {k: 1.0 / len(COMPONENTS) for k in COMPONENTS}
    return {k: v / total for k, v in filtered.items()}


def _minmax(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi - lo <= 1e-12:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


class RankingEngine:
    def __init__(self, weights: dict[str, float]) -> None:
        self.weights = normalize_weights(weights)

    def rank(self, items: list[TitleFeatures]) -> list[RankingResult]:
        if not items:
            return []

        # Normalise volume-like columns across the batch.
        normalised_cols: dict[str, list[float]] = {}
        for name in _NORMALISE:
            normalised_cols[name] = _minmax([getattr(it, name) for it in items])

        results: list[RankingResult] = []
        for i, item in enumerate(items):
            components = {
                "popularity": normalised_cols["popularity"][i],
                "rating": _clamp01(item.rating),
                "review_volume": normalised_cols["review_volume"][i],
                "sentiment": _clamp01((item.sentiment + 1.0) / 2.0),
                "discussion_volume": normalised_cols["discussion_volume"][i],
                "engagement": normalised_cols["engagement"][i],
            }
            score = sum(self.weights[k] * components[k] for k in COMPONENTS)
            results.append(
                RankingResult(
                    title_id=item.title_id,
                    score=round(score, 6),
                    position=0,
                    components={k: round(v, 6) for k, v in components.items()},
                    weights_snapshot=dict(self.weights),
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        for position, result in enumerate(results, start=1):
            result.position = position
        return results


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
