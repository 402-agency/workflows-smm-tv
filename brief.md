# Project Brief: AI Entertainment Trend Analysis & Short-Form Script Generator

## Objective

Develop a self-hosted web application that automatically discovers trending movies and TV shows, aggregates review and social discussion data, analyzes audience sentiment, ranks titles using configurable scoring, and generates short-form video scripts suitable for platforms such as YouTube Shorts, TikTok, and Instagram Reels.

The application must run entirely on a VPS using Docker and expose both a web interface and REST API.

---

# Technology Stack

## Backend

* Python 3.12+
* FastAPI
* asyncio
* httpx
* LangGraph
* SQLAlchemy
* Alembic
* MySQL
* Redis

## AI

* Anthropic Claude API (preferred if API access is available)
* OpenAI API (fallback)
* HuggingFace Transformers
* Local sentiment model for review/comment classification

## Frontend

* FastAPI Templates (Jinja2)
* Tailwind CSS
* HTMX (optional for dynamic updates)

## Infrastructure

* Docker
* Docker Compose
* Nginx (reverse proxy)
* VPS deployment

---

# Functional Requirements

## Trend Collection

Retrieve trending movies and television shows from supported providers.

Store:

* title
* type
* release date
* popularity metrics
* genres
* overview
* poster
* source

Avoid duplicate records.

---

## Review Aggregation

Collect available ratings and review information.

Extract:

* average rating
* review count
* critic score (when available)
* audience score (when available)
* review excerpts

---

## Social Data Collection

Collect discussion from supported public sources.

Examples:

* Reddit
* YouTube
* X (if API available)
* other supported public sources

Store:

* post/comment
* timestamp
* source
* engagement metrics

---

## Sentiment Analysis

Use a local Transformers model to classify collected content.

Output:

* positive
* neutral
* negative

Generate aggregate sentiment statistics for each title.

---

## Trend Ranking

Calculate a configurable ranking score using collected metrics.

Possible inputs include:

* popularity
* average rating
* review volume
* sentiment
* discussion volume
* engagement

Ranking weights must be configurable.

---

## AI Analysis

For each title generate:

* summary
* strengths
* weaknesses
* audience reception
* notable discussion topics
* recommendation summary

Use Claude when API access is available.

Otherwise use OpenAI.

---

## Script Generation

Generate a short-form video script.

Output:

* hook
* ranked list
* narration
* closing CTA

Additionally generate:

* video title
* thumbnail text
* hashtags
* description

---

## Scheduling

Support scheduled jobs.

Pipeline:

1. Discover trends
2. Fetch reviews
3. Fetch social content
4. Analyze sentiment
5. Rank titles
6. Generate AI content
7. Store results

Jobs should execute automatically at configurable intervals.

---

# LangGraph Workflow

The workflow should consist of modular nodes.

Suggested graph:

Discovery

↓

Metadata

↓

Reviews

↓

Social Collection

↓

Sentiment

↓

Ranking

↓

AI Analysis

↓

Script Generation

↓

Persistence

Each node should support retries and structured state passing.

---

# REST API

Provide endpoints such as:

GET

* /trends
* /titles
* /titles/{id}
* /scripts/{id}

POST

* /pipeline/run
* /scripts/generate

Health

* /health

---

# Web Dashboard

Dashboard should display:

* latest trending titles
* ranking score
* sentiment distribution
* ratings
* generated script
* AI summary

Support:

* search
* filtering
* manual pipeline execution
* regeneration of AI content

---

# Database

Suggested tables:

* titles
* ratings
* reviews
* social_posts
* sentiment_results
* rankings
* ai_summaries
* scripts
* pipeline_runs

---

# Redis Usage

Redis should be used for:

* caching API responses
* distributed locking
* task coordination
* rate limiting
* temporary pipeline state

---

# Project Structure

```text
app/
    api/
    core/
    config/
    database/
    models/
    schemas/
    repositories/
    services/
        collectors/
        analyzers/
        ranking/
        ai/
    graph/
    scheduler/
    workers/
    templates/
    static/
    prompts/
    utils/

docker/
tests/
```

---

# Docker Services

Compose should include:

* app
* mysql
* redis
* nginx

Persistent volumes should be configured for database storage.

---

# Configuration

All configuration should be environment-based.

Examples:

* API keys
* database credentials
* Redis connection
* AI provider
* scheduler interval
* ranking weights

---

# Logging

Provide structured logging for:

* API requests
* pipeline execution
* AI requests
* errors
* retries

---

# Deliverables

The completed project should provide:

* Self-hosted Docker deployment
* REST API
* Responsive web dashboard
* Automated trend discovery
* Review aggregation
* Social discussion analysis
* Local sentiment analysis
* Configurable ranking engine
* AI-generated summaries
* AI-generated short-form video scripts
* Modular LangGraph workflow
* MySQL persistence
* Redis caching and coordination
* Production-ready project structure

