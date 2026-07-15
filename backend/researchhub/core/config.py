"""Typed application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for API, database, queue, connectors, and AI services."""

    app_name: str = "ResearchHub Ethiopia"
    app_env: str = "local"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    allowed_origins: list[str] = Field(default_factory=list)

    database_url: str = "postgresql+asyncpg://researchhub:researchhub@localhost:5432/researchhub"
    sync_database_url: str = "postgresql+psycopg://researchhub:researchhub@localhost:5432/researchhub"
    redis_url: str = "redis://localhost:6379/0"
    instance_id: str | None = None
    api_workers: int = Field(default=1, ge=1, le=64)
    api_graceful_timeout_seconds: int = Field(default=30, ge=1, le=300)
    api_keepalive_seconds: int = Field(default=5, ge=1, le=120)
    api_max_concurrent_requests: int = Field(default=500, ge=1, le=100_000)
    slow_request_threshold_ms: int = Field(default=1000, ge=1)
    max_request_body_mb: int = Field(default=10, ge=1, le=1000)

    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=5, ge=0, le=100)
    db_pool_timeout_seconds: int = Field(default=10, ge=1, le=120)
    db_pool_recycle_seconds: int = Field(default=1800, ge=30)
    db_pool_pre_ping: bool = True
    db_statement_timeout_ms: int = Field(default=30_000, ge=100)
    db_lock_timeout_ms: int = Field(default=5_000, ge=100)
    db_idle_transaction_timeout_ms: int = Field(default=60_000, ge=1000)
    db_use_pgbouncer: bool = False

    redis_max_connections: int = Field(default=100, ge=1, le=10_000)
    redis_socket_connect_timeout: float = Field(default=2.0, gt=0, le=60)
    redis_socket_timeout: float = Field(default=2.0, gt=0, le=60)
    redis_health_check_interval: int = Field(default=30, ge=1, le=300)
    redis_retry_on_timeout: bool = True
    redis_cache_default_ttl: int = Field(default=300, ge=1)

    connector_user_agent: str = "ResearchHubEthiopia/0.1"
    connector_timeout_seconds: int = 30
    connector_max_retries: int = 4
    connector_rate_limit_per_second: float = 2.0
    harvest_config_path: str | None = "harvester/config/harvest_connectors.example.json"
    metadata_quality_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "completeness": 0.30,
            "validity": 0.20,
            "consistency": 0.15,
            "uniqueness": 0.15,
            "timeliness": 0.10,
            "accessibility": 0.10,
        }
    )
    metadata_quality_check_url_reachability: bool = False
    metadata_quality_url_timeout_seconds: float = 3.0
    openalex_mailto: str | None = None
    crossref_mailto: str | None = None

    openai_base_url: AnyHttpUrl | None = None
    openai_api_key: str | None = None
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: str = "cpu"
    embedding_dimension: int = 384
    ai_provider: str = "local"
    ai_chat_model: str = "grounded-local-v1"
    ai_request_timeout: float = 60.0
    ai_max_retries: int = 3
    ai_max_context_publications: int = 8
    ai_max_message_chars: int = 4000
    ai_default_temperature: float = 0.1
    ai_enable_openai: bool = False
    ai_enable_ollama: bool = False
    ollama_base_url: AnyHttpUrl = AnyHttpUrl("http://ollama:11434")
    ai_chat_provider: str = "local"
    ai_summary_provider: str = "local"
    ai_embedding_provider: str = "local"
    ai_summary_model: str = "grounded-extractive-v1"
    ai_embedding_batch_size: int = Field(default=32, ge=1, le=512)
    ai_embedding_normalize: bool = True
    ai_chat_max_context_tokens: int = Field(default=8000, ge=512, le=128000)
    ai_chat_retrieval_limit: int = Field(default=20, ge=1, le=100)
    keyword_extraction_method: str = "hybrid"
    keyword_max_keywords: int = Field(default=12, ge=1, le=100)
    keyword_min_confidence: float = Field(default=0.25, ge=0, le=1)
    duplicate_minimum_score: float = Field(default=0.70, ge=0, le=1)
    duplicate_high_confidence_score: float = Field(default=0.85, ge=0, le=1)
    duplicate_very_high_confidence_score: float = Field(default=0.95, ge=0, le=1)
    semantic_search_minimum_score: float = Field(default=0.45, ge=0, le=1)
    semantic_search_weight: float = Field(default=0.50, ge=0, le=1)
    lexical_search_weight: float = Field(default=0.25, ge=0, le=1)
    trend_minimum_publications: int = Field(default=3, ge=1)
    trend_cache_ttl_seconds: int = Field(default=3600, ge=60)
    harvest_batch_size: int = Field(default=500, ge=1, le=10_000)
    harvest_request_timeout_seconds: int = Field(default=60, ge=5, le=600)
    harvest_max_retries: int = Field(default=3, ge=0, le=10)
    harvest_retry_backoff_seconds: int = Field(default=5, ge=1, le=300)
    harvest_max_concurrent_per_source: int = Field(default=1, ge=1, le=5)
    max_active_harvests_global: int = Field(default=8, ge=1, le=1000)
    max_active_imports_global: int = Field(default=4, ge=1, le=1000)
    max_active_ai_generations_per_user: int = Field(default=2, ge=1, le=100)
    max_active_chat_streams_per_user: int = Field(default=2, ge=1, le=100)
    max_active_chat_streams_global: int = Field(default=50, ge=1, le=10_000)
    max_active_document_jobs: int = Field(default=4, ge=1, le=1000)
    max_search_page_size: int = Field(default=100, ge=1, le=1000)
    max_batch_operation_size: int = Field(default=1000, ge=1, le=100_000)
    import_max_file_size_mb: int = Field(default=100, ge=1, le=1000)
    import_storage_path: str = "/app/data/imports"
    import_preview_limit: int = Field(default=20, ge=1, le=100)
    auth_jwt_secret: str = "development-only-change-me-at-least-32-characters"
    auth_jwt_algorithm: str = "HS256"
    auth_jwt_issuer: str = "researchhub-ethiopia"
    auth_jwt_audience: str = "researchhub-api"
    auth_access_token_minutes: int = Field(default=15, ge=1, le=1440)
    auth_refresh_token_days: int = Field(default=30, ge=1, le=365)
    auth_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    auth_max_failed_attempts: int = Field(default=5, ge=2, le=20)
    auth_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    auth_reset_token_minutes: int = Field(default=30, ge=5, le=1440)

    http_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=120)
    http_read_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    http_write_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    http_max_connections: int = Field(default=100, ge=1, le=10_000)
    http_max_keepalive_connections: int = Field(default=20, ge=1, le=1000)
    celery_task_soft_time_limit: int = Field(default=900, ge=10)
    celery_task_time_limit: int = Field(default=960, ge=10)
    celery_worker_prefetch_multiplier: int = Field(default=1, ge=1, le=128)
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    load_test_mode: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RESEARCHHUB_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings so dependency injection is cheap and consistent."""

    return Settings()
