"""Local sentiment classification via a HuggingFace text-classification model.

The default model (distilbert SST-2) is binary POSITIVE/NEGATIVE. We derive a
third **neutral** class from the model's confidence: when the winning softmax
probability does not clear ``SENTIMENT_NEUTRAL_THRESHOLD`` the item is treated
as neutral. This keeps a real 3-class output (positive/neutral/negative) as the
brief requires without a separately trained neutral label.

The model is loaded lazily and cached process-wide, so the first classification
pays the download/load cost and subsequent calls are cheap.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.enums import SentimentLabel

_log = get_logger("sentiment")

_pipeline = None
_pipeline_model: str | None = None


def _get_pipeline(model_name: str):
    global _pipeline, _pipeline_model
    if _pipeline is None or _pipeline_model != model_name:
        from transformers import pipeline  # imported lazily (heavy)

        _log.info("loading_sentiment_model", model=model_name)
        _pipeline = pipeline(
            "text-classification",
            model=model_name,
            truncation=True,
        )
        _pipeline_model = model_name
    return _pipeline


def map_label(raw_label: str, score: float, threshold: float) -> str:
    """Map a binary model output + confidence to a 3-class label.

    Pure function so it can be unit-tested without loading a model.
    """
    if score < threshold:
        return SentimentLabel.NEUTRAL
    normalized = raw_label.strip().upper()
    if normalized.startswith("POS") or normalized in {"LABEL_1", "1"}:
        return SentimentLabel.POSITIVE
    return SentimentLabel.NEGATIVE


@dataclass
class SentimentOutcome:
    label: str
    confidence: float


class SentimentAnalyzer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model_name = self.settings.sentiment_model_name
        self.threshold = self.settings.sentiment_neutral_threshold
        self.max_length = self.settings.sentiment_max_length

    def classify(self, texts: list[str], batch_size: int = 16) -> list[SentimentOutcome]:
        cleaned = [(t or "").strip() for t in texts]
        results: list[SentimentOutcome] = []
        non_empty_idx = [i for i, t in enumerate(cleaned) if t]
        outcomes: dict[int, SentimentOutcome] = {}

        if non_empty_idx:
            pipe = _get_pipeline(self.model_name)
            payload = [cleaned[i][: self.max_length * 6] for i in non_empty_idx]
            raw = pipe(payload, batch_size=batch_size, truncation=True)
            if isinstance(raw, dict):
                raw = [raw]
            for idx, res in zip(non_empty_idx, raw):
                label = map_label(res["label"], float(res["score"]), self.threshold)
                outcomes[idx] = SentimentOutcome(label=label, confidence=float(res["score"]))

        for i in range(len(cleaned)):
            results.append(
                outcomes.get(i, SentimentOutcome(SentimentLabel.NEUTRAL, 0.0))
            )
        return results

    def classify_one(self, text: str) -> SentimentOutcome:
        return self.classify([text])[0]
