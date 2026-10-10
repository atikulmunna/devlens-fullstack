from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    env: str
    redis_url: str
    database_url: str
    qdrant_url: AnyHttpUrl
    qdrant_collection: str = 'devlens_code_chunks'
    qdrant_api_key: str | None = None

    parse_clone_timeout_seconds: int = 60
    parse_max_files: int = 8000
    parse_max_chunks: int = 20000
    parse_chunk_lines: int = 120
    parse_chunk_overlap_lines: int = 20

    # Embeddings via OpenRouter; model and size must match the backend's.
    embed_model: str = "openai/text-embedding-3-small"
    embed_vector_size: int = 1536
    embed_timeout_seconds: int = 15
    embed_batch_size: int = 32
    embed_retry_attempts: int = 3
    embed_cache_ttl_seconds: int = 604800  # 7 days; content-addressed embedding cache
    worker_retry_max_attempts: int = 3
    worker_retry_base_delay_seconds: int = 30
    worker_metrics_port: int = 9101

    # OpenRouter is the only external AI provider: chunk embeddings (required) and the analysis
    # summary LLM (if only that call fails, the summary falls back to a structural one).
    openrouter_api_key: str | None = None
    openrouter_base_url: AnyHttpUrl = "https://openrouter.ai/api/v1"
    llm_summary_model: str = "openai/gpt-4o-mini"
    llm_summary_timeout_seconds: int = 15

    # Ignore unknown keys so env files that still carry removed settings keep working.
    model_config = SettingsConfigDict(env_file='.env', case_sensitive=False, extra='ignore')


settings = WorkerSettings()
