from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    env: str
    redis_url: str
    database_url: str
    qdrant_url: AnyHttpUrl
    qdrant_collection: str = 'devlens_code_chunks'

    parse_clone_timeout_seconds: int = 60
    parse_max_files: int = 8000
    parse_max_chunks: int = 20000
    parse_chunk_lines: int = 120
    parse_chunk_overlap_lines: int = 20

    embed_vector_size: int = 384
    embed_batch_size: int = 32
    embed_retry_attempts: int = 3
    worker_retry_max_attempts: int = 3
    worker_retry_base_delay_seconds: int = 30
    worker_metrics_port: int = 9101

    # LLM summary generation routing
    llm_summary_provider: str = "openrouter"
    llm_summary_model: str = "openai/gpt-4o-mini"
    llm_summary_timeout_seconds: int = 15
    llm_primary_provider: str | None = None
    llm_fallback_provider: str | None = "groq"
    llm_primary_timeout_seconds: int | None = None
    llm_fallback_timeout_seconds: int | None = None
    llm_fallback_model: str | None = "llama-3.1-8b-instant"

    openrouter_api_key: str | None = None
    openrouter_base_url: AnyHttpUrl = "https://openrouter.ai/api/v1"
    groq_api_key: str | None = None
    groq_base_url: AnyHttpUrl = "https://api.groq.com/openai/v1"

    model_config = SettingsConfigDict(env_file='.env', case_sensitive=False)


settings = WorkerSettings()
