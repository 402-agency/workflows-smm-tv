# AI Entertainment Trend Analysis & Short-Form Script Generator

A self-hosted web application that discovers trending movies & TV shows, aggregates ratings and
social discussion, runs **local sentiment analysis**, ranks titles with a **configurable scoring
engine**, and uses an LLM to generate a per-title analysis plus a **short-form video script**
(YouTube Shorts / TikTok / Reels).

Everything runs in Docker, exposes a **REST API** and a **server-rendered dashboard**, and is
orchestrated as a modular **LangGraph** pipeline. The pipeline is triggered **manually** (dashboard
button / API) — there is no scheduler.

📄 **[Architecture case study, workflow diagram & sample output →](https://claude.ai/code/artifact/3f2c8a83-eeec-4b63-901b-c447a68b900e)**

## Stack

| Concern | Choice |
|---|---|
| API / web | FastAPI + Jinja2 + Tailwind (server-rendered, full-page reloads) |
| Pipeline | LangGraph (9 retrying nodes) |
| Tasks | ARQ worker on Redis (no cron) |
| DB | MySQL 8 + SQLAlchemy 2.0 (async) + Alembic |
| Cache / locks / progress | Redis |
| Trends + ratings | TMDB (+ review excerpts) + OMDb (IMDb / Rotten Tomatoes / Metacritic) |
| Social | Reddit (asyncpraw) + YouTube Data API |
| Sentiment | HuggingFace `distilbert-base-uncased-finetuned-sst-2-english` (neutral via threshold) |
| AI text | OpenAI (behind a provider interface; Claude can be added later) |
| Proxy | Nginx |

## Architecture

```
Nginx ──► FastAPI (app)  ──enqueue──►  Redis  ──►  ARQ worker
              │  REST + dashboard                     │
              └──────────────► MySQL ◄────────────────┘  (LangGraph pipeline)

Pipeline: discovery → metadata → reviews → social_collection → sentiment
          → ranking → ai_analysis → script_generation → persistence
```

The web process stays light: pressing **Run pipeline** enqueues an ARQ job; the worker runs the
long-running graph (collection + local model inference) and streams live progress into Redis, which
the dashboard's runs page reflects. A Redis lock guarantees a single run at a time.

## Quick start

1. **Configure.** Copy the example env and fill in the keys you have:
   ```bash
   cp .env.example .env
   ```
   Provision (all free tiers): **TMDB**, **OMDb**, **Reddit** (client id/secret), **YouTube Data
   API**, and **OpenAI**. Any missing provider degrades gracefully (that collector/AI step is
   skipped with a warning) — the pipeline still completes. Change `AUTH_USERNAME` / `AUTH_PASSWORD`.

2. **Run the stack:**
   ```bash
   docker compose up --build -d
   ```
   This starts `mysql`, `redis`, `app`, `worker`, and `nginx`. The app container waits for MySQL and
   runs `alembic upgrade head` automatically on startup. The dashboard is at
   **http://localhost:8080**.

3. **Trigger a run** from the dashboard ("Run pipeline") or the API, then watch progress on
   **/runs**. The first run downloads the sentiment model (~270 MB) into the `hf-cache` volume.

### Development

Bind-mount the source and get autoreload + the app on port 18000:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

## REST API

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | DB + Redis check |
| GET | `/trends` | latest run's ranked titles |
| GET | `/titles` | `q`, `type`, `genre`, `order_by`, `min_score`, `limit`, `offset` |
| GET | `/titles/{id}` | metadata + ratings + sentiment + AI summary + samples |
| GET | `/scripts/{id}` | a generated script |
| POST | `/pipeline/run` | 🔒 enqueue a run (409 if one is active) |
| POST | `/scripts/generate` | 🔒 regenerate AI content (body: `{"run_id": <optional>}`) |
| GET | `/pipeline/runs`, `/pipeline/runs/{id}` | run history + live progress |

🔒 = requires auth (HTTP Basic with `AUTH_USERNAME`/`AUTH_PASSWORD`, or `Authorization: Bearer
<API_TOKEN>` / `?token=`). Example:
```bash
curl -u admin:changeme -X POST http://localhost:8080/pipeline/run
```

## Configuration

All configuration is environment-based — see `.env.example` for the full list. Highlights:

- **Ranking weights** — `WEIGHT_POPULARITY`, `WEIGHT_RATING`, `WEIGHT_REVIEW_VOLUME`,
  `WEIGHT_SENTIMENT`, `WEIGHT_DISCUSSION_VOLUME`, `WEIGHT_ENGAGEMENT` (re-normalised to sum 1).
- **Sentiment** — `SENTIMENT_MODEL_NAME`, `SENTIMENT_NEUTRAL_THRESHOLD` (winning class must clear
  this softmax probability, else the item is labelled *neutral*).
- **Discovery sizing** — `TRENDING_WINDOW` (day|week), `MAX_TITLES`, `TOP_N`, `REVIEWS_PER_TITLE`,
  `SOCIAL_POSTS_PER_TITLE`.
- **AI** — `OPENAI_API_KEY`, `OPENAI_MODEL`.

## Database migrations

Migrations live in `alembic/`. They run automatically on app startup; to run manually:
```bash
docker compose exec app alembic upgrade head
# create a new migration after model changes:
docker compose exec app alembic revision --autogenerate -m "message"
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
The suite is hermetic — SQLite in-memory for DB/repository/API tests and mocked HTTP/Redis for
collectors — so no MySQL/Redis/network is required.

## Project layout

```
app/
  api/          FastAPI routers (REST + dashboard) + auth
  config/       pydantic-settings
  core/         logging, redis helpers, errors
  database/     async engine/session + Base
  models/       SQLAlchemy models (9 tables)
  repositories/ async data access
  schemas/      pydantic DTOs + API models
  services/
    collectors/ TMDB, OMDb, Reddit, YouTube
    analyzers/  sentiment
    ranking/    scoring engine
    ai/         provider interface + OpenAI
  graph/        LangGraph state, nodes, build, runner, context
  workers/      ARQ worker + enqueue helpers
  prompts/      LLM prompt templates
  templates/    Jinja2 dashboard
docker/         Dockerfile, entrypoint, nginx
alembic/        migrations
tests/
```
