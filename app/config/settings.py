"""Environment-based application configuration.

Everything the app needs is expressed as an environment variable (see
``.env.example``). Access the singleton via :func:`get_settings`.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Application -------------------------------------------------
    app_name: str = "Trend Analyzer"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # -- MySQL -------------------------------------------------------
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "trend"
    mysql_password: str = "trend"
    mysql_database: str = "trend"

    # -- Redis -------------------------------------------------------
    redis_url: str = "redis://redis:6379/0"

    # -- Auth --------------------------------------------------------
    auth_username: str = "admin"
    auth_password: str = "changeme"
    api_token: str | None = None
    auth_protect_reads: bool = False

    # -- AI ----------------------------------------------------------
    ai_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # -- External providers -----------------------------------------
    tmdb_api_key: str | None = None
    omdb_api_key: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "trend-analyzer/0.1"
    youtube_api_key: str | None = None

    # -- Sentiment ---------------------------------------------------
    sentiment_model_name: str = "distilbert-base-uncased-finetuned-sst-2-english"
    sentiment_neutral_threshold: float = 0.65
    sentiment_max_length: int = 512

    # -- Discovery / sizing -----------------------------------------
    trending_window: str = "day"  # "day" | "week"
    max_titles: int = 20
    top_n: int = 10
    reviews_per_title: int = 10
    social_posts_per_title: int = 25

    # -- Ranking weights (relative; normalised at runtime) ----------
    weight_popularity: float = 0.25
    weight_rating: float = 0.20
    weight_review_volume: float = 0.10
    weight_sentiment: float = 0.25
    weight_discussion_volume: float = 0.10
    weight_engagement: float = 0.10

    # -- Caching / rate limiting ------------------------------------
    cache_ttl_seconds: int = 3600
    rate_limit_per_second: int = 5

    # -- Derived -----------------------------------------------------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_async(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        """Synchronous URL used by Alembic migrations."""
        return (
            f"mysql+pymysql://{self.mysql_user}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def ranking_weights(self) -> dict[str, float]:
        return {
            "popularity": self.weight_popularity,
            "rating": self.weight_rating,
            "review_volume": self.weight_review_volume,
            "sentiment": self.weight_sentiment,
            "discussion_volume": self.weight_discussion_volume,
            "engagement": self.weight_engagement,
        }


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
