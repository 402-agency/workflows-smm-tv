import httpx
import pytest
import respx

from app.config import Settings
from app.schemas.dto import TitleDTO
from app.services.collectors import OMDbCollector, TMDBCollector


@pytest.fixture(autouse=True)
def _stub_redis(monkeypatch):
    """Bypass Redis cache + rate limiting for collector unit tests."""
    from app.core import redis as redis_helpers

    async def _get(_key):
        return None

    async def _set(*_a, **_k):
        return None

    async def _rl(*_a, **_k):
        return None

    monkeypatch.setattr(redis_helpers, "cache_get", _get)
    monkeypatch.setattr(redis_helpers, "cache_set", _set)
    monkeypatch.setattr(redis_helpers, "rate_limit_acquire", _rl)


@respx.mock
async def test_omdb_parses_all_rating_sources():
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "imdbID": "tt1",
                "imdbRating": "8.2",
                "imdbVotes": "12,345",
                "Metascore": "74",
                "Ratings": [
                    {"Source": "Internet Movie Database", "Value": "8.2/10"},
                    {"Source": "Rotten Tomatoes", "Value": "91%"},
                    {"Source": "Metacritic", "Value": "74/100"},
                ],
            },
        )
    )
    dto = TitleDTO(external_id="movie:1", title="Dune", type="movie", imdb_id="tt1")
    async with OMDbCollector(Settings(omdb_api_key="k")) as c:
        ratings = await c.fetch(dto)

    by_source = {r.source: r for r in ratings}
    assert by_source["imdb"].average_rating == 8.2
    assert by_source["imdb"].review_count == 12345
    assert by_source["rotten_tomatoes"].critic_score == 91.0
    assert by_source["metacritic"].critic_score == 74.0


@respx.mock
async def test_omdb_disabled_without_key():
    async with OMDbCollector(Settings(omdb_api_key=None)) as c:
        assert c.enabled is False
        assert await c.fetch(TitleDTO(external_id="x", title="X", type="movie")) == []


@respx.mock
async def test_tmdb_discovers_and_maps_genres():
    respx.get("https://api.themoviedb.org/3/genre/movie/list").mock(
        return_value=httpx.Response(200, json={"genres": [{"id": 18, "name": "Drama"}]})
    )
    respx.get("https://api.themoviedb.org/3/genre/tv/list").mock(
        return_value=httpx.Response(200, json={"genres": []})
    )
    respx.get("https://api.themoviedb.org/3/trending/movie/day").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 42,
                        "title": "Big Movie",
                        "popularity": 99.0,
                        "release_date": "2026-01-10",
                        "genre_ids": [18],
                        "overview": "x",
                        "poster_path": "/p.jpg",
                    }
                ]
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/trending/tv/day").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    async with TMDBCollector(Settings(tmdb_api_key="k")) as c:
        titles = await c.discover_trending("day", 10)

    assert len(titles) == 1
    t = titles[0]
    assert t.title == "Big Movie"
    assert t.type == "movie"
    assert t.genres == ["Drama"]
    assert t.poster_url.endswith("/p.jpg")
    assert t.release_date.year == 2026
