from app.services.ranking import RankingEngine, TitleFeatures
from app.services.ranking.engine import normalize_weights


def test_weights_normalise_to_one():
    w = normalize_weights({"popularity": 2, "rating": 2, "sentiment": 0, "engagement": 0})
    assert abs(sum(w.values()) - 1.0) < 1e-9
    # Only the two non-zero inputs share the weight equally.
    assert abs(w["popularity"] - 0.5) < 1e-9
    assert w["sentiment"] == 0.0


def test_zero_weights_fall_back_to_equal():
    w = normalize_weights({})
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert len({round(v, 6) for v in w.values()}) == 1


def test_ranking_orders_by_score_and_assigns_positions():
    items = [
        TitleFeatures(title_id=1, popularity=100, rating=0.9, review_volume=500,
                      sentiment=0.6, discussion_volume=50, engagement=2000),
        TitleFeatures(title_id=2, popularity=10, rating=0.4, review_volume=20,
                      sentiment=-0.3, discussion_volume=5, engagement=100),
        TitleFeatures(title_id=3, popularity=55, rating=0.7, review_volume=200,
                      sentiment=0.1, discussion_volume=25, engagement=800),
    ]
    results = RankingEngine({"popularity": 1, "rating": 1, "review_volume": 1,
                             "sentiment": 1, "discussion_volume": 1, "engagement": 1}).rank(items)
    assert [r.title_id for r in results] == [1, 3, 2]
    assert [r.position for r in results] == [1, 2, 3]
    assert results[0].score >= results[1].score >= results[2].score
    # Components are all normalised to [0, 1].
    for r in results:
        for v in r.components.values():
            assert 0.0 <= v <= 1.0


def test_single_item_is_stable():
    results = RankingEngine(normalize_weights({"popularity": 1})).rank(
        [TitleFeatures(title_id=7, popularity=42)]
    )
    assert len(results) == 1
    assert results[0].position == 1


def test_empty_input():
    assert RankingEngine(normalize_weights({})).rank([]) == []
