from app.models.enums import SentimentLabel
from app.services.analyzers.sentiment import map_label


def test_high_confidence_positive():
    assert map_label("POSITIVE", 0.99, 0.65) == SentimentLabel.POSITIVE


def test_high_confidence_negative():
    assert map_label("NEGATIVE", 0.97, 0.65) == SentimentLabel.NEGATIVE


def test_low_confidence_becomes_neutral():
    assert map_label("POSITIVE", 0.55, 0.65) == SentimentLabel.NEUTRAL
    assert map_label("NEGATIVE", 0.60, 0.65) == SentimentLabel.NEUTRAL


def test_label_variants():
    assert map_label("LABEL_1", 0.9, 0.65) == SentimentLabel.POSITIVE
    assert map_label("LABEL_0", 0.9, 0.65) == SentimentLabel.NEGATIVE


def test_threshold_boundary_is_neutral_below():
    # Exactly at threshold counts as confident; just under is neutral.
    assert map_label("POSITIVE", 0.65, 0.65) == SentimentLabel.POSITIVE
    assert map_label("POSITIVE", 0.6499, 0.65) == SentimentLabel.NEUTRAL
