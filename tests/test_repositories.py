from app.models.enums import ContentType, SentimentLabel
from app.repositories import (
    SentimentRepository,
    TitleRepository,
)


async def test_title_upsert_inserts_then_updates(db_session):
    repo = TitleRepository(db_session)
    t1 = await repo.upsert("tmdb", "movie:1", title="Dune", type="movie", popularity=10.0)
    await db_session.commit()
    assert t1.id is not None

    t2 = await repo.upsert("tmdb", "movie:1", title="Dune: Part Two", type="movie", popularity=55.0)
    await db_session.commit()
    assert t2.id == t1.id  # same row (deduped by source+external_id)
    assert t2.title == "Dune: Part Two"
    assert t2.popularity == 55.0
    assert await repo.count() == 1


async def test_title_search_filters(db_session):
    repo = TitleRepository(db_session)
    await repo.upsert("tmdb", "movie:1", title="Space Movie", type="movie", genres=["Sci-Fi"])
    await repo.upsert("tmdb", "tv:2", title="Space Show", type="tv", genres=["Drama"])
    await db_session.commit()

    movies = await repo.search(type_="movie")
    assert [t.title for t in movies] == ["Space Movie"]

    q = await repo.search(q="show")
    assert [t.title for t in q] == ["Space Show"]

    drama = await repo.search(genre="Drama")
    assert [t.title for t in drama] == ["Space Show"]


async def test_sentiment_aggregate(db_session):
    trepo = TitleRepository(db_session)
    title = await trepo.upsert("tmdb", "movie:1", title="X", type="movie")
    await db_session.commit()

    srepo = SentimentRepository(db_session)
    for label in [SentimentLabel.POSITIVE, SentimentLabel.POSITIVE, SentimentLabel.NEGATIVE]:
        srepo.create(title.id, ContentType.REVIEW, 1, label, 0.9, "m")
    await db_session.commit()

    agg = await srepo.aggregate_for_title(title.id)
    assert agg["total"] == 3
    assert agg["counts"]["positive"] == 2
    assert abs(agg["shares"]["positive"] - 2 / 3) < 1e-6
