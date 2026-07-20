import base64


def _basic(user="admin", pw="changeme"):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


async def test_trends_empty(client):
    r = await client.get("/trends")
    assert r.status_code == 200
    assert r.json() == []


async def test_titles_empty(client):
    r = await client.get("/titles")
    assert r.status_code == 200
    assert r.json() == []


async def test_title_not_found(client):
    r = await client.get("/titles/999")
    assert r.status_code == 404
    assert r.json()["error"] == "NotFoundError"


async def test_pipeline_run_requires_auth(client):
    r = await client.post("/pipeline/run")
    assert r.status_code == 401


async def test_wrong_credentials_rejected(client):
    r = await client.post("/pipeline/run", headers=_basic(pw="nope"))
    assert r.status_code == 401


async def test_titles_populated(client, db_session):
    from app.repositories import TitleRepository

    await TitleRepository(db_session).upsert(
        "tmdb", "movie:1", title="Dune", type="movie", popularity=99.0, genres=["Sci-Fi"]
    )
    await db_session.commit()

    r = await client.get("/titles")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["title"] == "Dune"
    assert data[0]["sentiment"]["total"] == 0
