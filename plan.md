# Plan: AI Entertainment Trend Analysis & Short-Form Script Generator

## Context

`brief.md` specifies a self-hosted web application that discovers trending movies/TV, aggregates
reviews and social discussion, runs local sentiment analysis, ranks titles with configurable
weights, and uses an LLM to generate per-title analysis plus a short-form video script (YouTube
Shorts / TikTok / Reels). It must run on a VPS via Docker and expose a REST API + web dashboard,
orchestrated as a modular LangGraph pipeline.

This document is the agreed build plan. **No application code will be written yet** — the sole
deliverable of the current session is `plan.md`. Implementation happens in a later session.

### Decisions locked with the user
| Area | Decision |
|------|----------|
| Trend/metadata + ratings | **TMDB** (trends, metadata, poster, user rating, review excerpts) **+ OMDb** (IMDb rating, Rotten Tomatoes critic, Metascore) |
| Social sources | **Reddit** (asyncpraw, official API) **+ YouTube** (Data API v3 comments) |
| AI provider | **OpenAI only** — but behind a thin `AIProvider` interface so Claude can be added later without a rewrite |
| Orchestration | **ARQ** (async Redis queue) worker runs the pipeline off the web process; separate worker container. **No scheduler** — the pipeline is triggered only manually from the dashboard button / `POST /pipeline/run` |
| Sentiment model | **distilbert-base-uncased-finetuned-sst-2-english** (2-class); *neutral* derived via confidence threshold |
| Auth | **Single-token / HTTP Basic** from env on write endpoints (read/health optionally open) |
| Frontend | **Server-rendered** Jinja2 + Tailwind, full-page reloads (no HTMX/JS build) |
| Build scope | **Plan only for now**; implement in a later session |

---

## Technology & key libraries
- Python 3.12, FastAPI, Uvicorn, asyncio, httpx
- SQLAlchemy 2.0 (async, `asyncmy` driver) + Alembic, MySQL 8
- Redis 7 (cache, locks, rate limiting, live pipeline state, ARQ broker)
- LangGraph (pipeline), pydantic v2 + pydantic-settings (config)
- Transformers + torch (CPU) for sentiment; `openai` SDK for AI
- `asyncpraw` (Reddit); YouTube Data API via httpx
- `tenacity` (retry/backoff), `structlog` (structured JSON logging)
- Tailwind **standalone CLI** to compile static CSS at image-build time (no Node at runtime)
- pytest + pytest-asyncio + `respx` (mock httpx) for tests

---

## Project structure (concrete)
```text
app/
  main.py                      # FastAPI app factory, middleware, router mounting, lifespan
  api/
    deps.py                    # DB session, auth dependency
    routes_health.py
    routes_trends.py           # /trends
    routes_titles.py           # /titles, /titles/{id}
    routes_scripts.py          # /scripts/{id}, /scripts/generate
    routes_pipeline.py         # /pipeline/run, /pipeline/runs, /pipeline/runs/{id}
    routes_web.py              # dashboard HTML routes
  core/
    logging.py                 # structlog config + request-id middleware
    security.py                # HTTP Basic / token auth
    redis.py                   # redis client, cache, distributed lock, rate limiter
    errors.py
  config/
    settings.py                # pydantic-settings; all env-based config incl. ranking weights
  database/
    session.py                 # async engine + sessionmaker
    base.py                    # DeclarativeBase
  models/                      # SQLAlchemy models (one file per table or grouped)
  schemas/                     # pydantic request/response + internal DTOs
  repositories/                # one repo class per aggregate (async)
  services/
    collectors/
      base.py                  # Collector ABC (async), cache+rate-limit helpers
      tmdb.py  omdb.py  reddit.py  youtube.py
    analyzers/
      sentiment.py             # HF pipeline (load once), batch classify, neutral threshold
    ranking/
      engine.py                # weighted, normalized scoring
    ai/
      base.py                  # AIProvider interface
      openai_provider.py
      factory.py               # provider selection from config
  graph/
    state.py                   # PipelineState (TypedDict)
    nodes.py                   # 9 node functions
    build.py                   # assemble StateGraph + RetryPolicy per node
  workers/
    worker.py                  # ARQ WorkerSettings + run_pipeline_task (no cron_jobs)
  templates/                   # base.html, index.html, title_detail.html, runs.html
  static/                      # compiled Tailwind css, minimal assets
  prompts/                     # analysis.txt, script.txt (versioned prompt templates)
  utils/                       # normalization, text cleaning, helpers
docker/
  app.Dockerfile               # multi-stage: build tailwind + deps -> slim runtime
  worker.Dockerfile            # (or reuse app image with different CMD)
  nginx.conf
  entrypoint.sh                # wait-for-mysql, alembic upgrade head, launch
alembic/                       # migrations
tests/
docker-compose.yml
.env.example
README.md
```

---

## Database schema (SQLAlchemy models + Alembic migration)
- **titles** — id, source, external_id, tmdb_id, imdb_id, title, type(movie|tv), release_date,
  popularity, genres(JSON), overview(TEXT), poster_url, created_at, updated_at.
  **Unique(source, external_id)** to avoid duplicates (upsert by this key).
- **ratings** — id, title_id FK, source(tmdb|imdb|rotten_tomatoes|metacritic), average_rating,
  review_count, critic_score, audience_score, fetched_at.
- **reviews** — id, title_id FK, source, author, content(TEXT), rating, url, created_at, fetched_at.
- **social_posts** — id, title_id FK, source(reddit|youtube), platform_id, content(TEXT), author,
  posted_at, engagement(JSON: score/likes/comments), url, fetched_at. Unique(source, platform_id).
- **sentiment_results** — id, title_id FK, content_type(review|social_post), content_id,
  label(positive|neutral|negative), confidence, model_name, created_at.
- **rankings** — id, title_id FK, pipeline_run_id FK, score, position, components(JSON breakdown),
  weights_snapshot(JSON), created_at.
- **ai_summaries** — id, title_id FK, pipeline_run_id FK, summary, strengths, weaknesses,
  audience_reception, notable_topics(JSON), recommendation, provider, model, created_at.
- **scripts** — id, pipeline_run_id FK, title_id FK (nullable — a script covers a ranked list),
  hook, narration(TEXT), ranked_list(JSON), cta, video_title, thumbnail_text, hashtags(JSON),
  description(TEXT), provider, model, created_at.
- **pipeline_runs** — id, status(pending|running|success|failed), trigger(manual),
  current_node, started_at, finished_at, error(TEXT), stats(JSON), created_at.

---

## Configuration (`app/config/settings.py`, all env-based)
DB creds/URL; `REDIS_URL`; `OPENAI_API_KEY`, `OPENAI_MODEL`; `TMDB_API_KEY`, `OMDB_API_KEY`;
`REDDIT_CLIENT_ID/SECRET/USER_AGENT`; `YOUTUBE_API_KEY`; `SENTIMENT_MODEL_NAME`,
`SENTIMENT_NEUTRAL_THRESHOLD` (default 0.65); ranking weights (`RANKING_WEIGHTS` JSON or per-field
env: popularity, rating, review_volume, sentiment, discussion_volume, engagement); `TRENDING_WINDOW`
(day|week), `TOP_N`; auth (`AUTH_USERNAME`/`AUTH_PASSWORD` or `API_TOKEN`); `LOG_LEVEL`.
Ship `.env.example` with all keys. (No scheduler config — runs are manual only.)

---

## Services

**Collectors** (`services/collectors/`) — each subclasses `Collector` (async `fetch(...)`), uses a
shared `httpx.AsyncClient`, wraps calls in `tenacity` retry + Redis response cache (TTL) + Redis
rate limiter, and returns normalized pydantic DTOs.
- `tmdb.py` — `/trending/{movie,tv}/{window}`; details + `external_ids` (imdb_id), genres, poster
  base URL, vote_average/vote_count; `/{type}/{id}/reviews` for excerpts.
- `omdb.py` — lookup by imdb_id (fallback title+year); parse imdbRating, Metascore, and the
  `Ratings` array (Rotten Tomatoes → critic, IMDb → audience).
- `reddit.py` — asyncpraw; search r/movies, r/television (+ global search) by title; top posts +
  top comments with engagement.
- `youtube.py` — search videos by title, then `commentThreads` for top comments + engagement.

**Sentiment** (`analyzers/sentiment.py`) — load HF `text-classification` pipeline once (module
singleton); batch-classify text. distilbert SST-2 emits POSITIVE/NEGATIVE + softmax; map to 3
classes: if `max_prob < SENTIMENT_NEUTRAL_THRESHOLD` → **neutral**, else argmax label. Store
per-item results; expose per-title aggregate (counts + shares).

**Ranking** (`ranking/engine.py`) — per-run min-max normalize popularity / review_volume /
discussion_volume / engagement to 0–1; ratings normalized by scale; sentiment component =
`(pos_share − neg_share)` mapped to 0–1. Final = weighted sum of components (weights from config,
re-normalized to sum 1). Persist score, position, component breakdown, and weights snapshot.

**AI** (`ai/`) — `AIProvider` interface: `generate_analysis(title_ctx)`,
`generate_script(ranked_titles_ctx)`. `openai_provider.py` implements it via the `openai` SDK with
JSON-structured responses; prompts loaded from `prompts/`. `factory.py` selects provider from
config (OpenAI now; interface leaves room for a future Claude provider). Analysis → summary,
strengths, weaknesses, audience reception, notable topics, recommendation. Script → hook, ranked
list, narration, CTA + video title, thumbnail text, hashtags, description.

---

## LangGraph pipeline (`app/graph/`)
`PipelineState` (TypedDict) carries: run_id, config snapshot, discovered titles, per-title
data buckets (ratings/reviews/social/sentiment), rankings, ai outputs, script, errors, current_node.
Nodes (linear per brief): **discovery → metadata → reviews → social_collection → sentiment →
ranking → ai_analysis → script_generation → persistence**. Each node is async and registered with a
LangGraph `RetryPolicy` (retries + backoff). Nodes persist their results incrementally and update
`pipeline_runs.current_node` + live Redis progress state so partial results survive failures. A
Redis distributed lock guarantees only one run executes at a time (so a second button press while a
run is in progress is rejected rather than overlapping).

---

## Orchestration (ARQ)
`workers/worker.py` defines `WorkerSettings` with `run_pipeline_task` (builds + invokes the graph),
running in its own `worker` container against Redis. There is **no cron / scheduler**: the pipeline
runs only when triggered manually — the dashboard button and `POST /pipeline/run` enqueue
`run_pipeline_task` and return a run_id. Keeping the worker (rather than running the graph inside the
web request) is deliberate: the pipeline is long-running and does local torch model inference, which
would otherwise block/bloat the web process.

---

## REST API (FastAPI routers + pydantic schemas)
- `GET /health` — DB + Redis connectivity.
- `GET /trends` — latest run's ranked titles (top N).
- `GET /titles` — list with search (`q`), filters (type, genre, min_score), sort, pagination.
- `GET /titles/{id}` — metadata + ratings + sentiment distribution + latest AI summary + social sample.
- `GET /scripts/{id}` — a generated script.
- `POST /pipeline/run` — enqueue a manual run (**auth**). Returns run_id.
- `POST /scripts/generate` — regenerate AI analysis/script for a run or title (**auth**).
- `GET /pipeline/runs`, `GET /pipeline/runs/{id}` — run history/status (dashboard).
Auth dependency (`core/security.py`) enforces HTTP Basic / token from env on write endpoints.

---

## Web dashboard (server-rendered)
`base.html` (Tailwind nav) + `index.html` (trending list: rank score, sentiment mini-bar, ratings;
GET search/filter form; "Run pipeline" POST button) + `title_detail.html` (full detail incl.
sentiment distribution, ratings, AI summary, generated script; "Regenerate AI"/"Regenerate script"
POST buttons) + `runs.html` (run history/current status; refresh to update). Tailwind compiled to
`static/css/app.css` at build time via the standalone CLI. Full-page reloads only.

---

## Redis usage
Collector response cache (keyed endpoint+params, TTL); distributed lock for single-run execution;
per-external-API rate limiting; live pipeline progress state (run_id → node + counts) read by the
status endpoints/dashboard; ARQ broker + result store.

---

## Docker & deployment
`docker-compose.yml` services: **app** (uvicorn), **worker** (ARQ), **mysql:8** (volume
`mysql-data`), **redis:7**, **nginx** (reverse proxy + serves `static/`). `app.Dockerfile`
multi-stage: stage 1 downloads Tailwind CLI + builds CSS and installs Python deps; runtime is
`python:3.12-slim`. HF sentiment model **pre-downloaded during image build** for reproducible,
offline startup (documented; alternatively a cached volume). `entrypoint.sh` waits for MySQL, runs
`alembic upgrade head`, then starts the process. `.env.example` documents every variable.

---

## Logging
`structlog` JSON logs: request middleware (method, path, status, latency, request-id); pipeline
node start/finish + retries; AI requests (model, latency, token usage); errors with traceback.
Correlation via request-id / run-id.

---

## Tests (`tests/`, pytest + pytest-asyncio)
Unit: ranking math, sentiment neutral-threshold logic, collector normalization (httpx mocked via
`respx`), AI provider (mocked SDK), repository CRUD, graph node logic. API: routes via httpx
AsyncClient against a test DB. All external network calls mocked.

---

## Suggested implementation phases (for the later build session)
1. Scaffold + config + Docker Compose + MySQL/Redis + Alembic baseline + `/health`.
2. Models, repositories, migrations.
3. Collectors (TMDB, OMDb, Reddit, YouTube) with cache/rate-limit + tests.
4. Sentiment analyzer + ranking engine + tests.
5. AI provider (OpenAI) + prompts + analysis/script generation.
6. LangGraph pipeline wiring nodes 1–9 with retries + incremental persistence.
7. ARQ worker (manual `run_pipeline_task`) + distributed single-run lock.
8. REST API + auth + schemas.
9. Dashboard templates + Tailwind build + Nginx.
10. Structured logging, README, `.env.example`, end-to-end pass.

---

## Verification (once built)
- `docker compose up` brings up all 5 services; `alembic upgrade head` runs on start.
- `GET /health` returns 200 with DB + Redis OK.
- `POST /pipeline/run` (authed) enqueues a run; `GET /pipeline/runs/{id}` progresses through nodes;
  `GET /trends` returns ranked titles; `GET /titles/{id}` shows sentiment + AI summary;
  `GET /scripts/{id}` returns a script.
- Dashboard renders trending list, title detail, and run history; the manual "Run pipeline" button
  and regenerate buttons work; a second run started while one is active is rejected by the lock.
- `pytest` passes with external APIs mocked.
```
