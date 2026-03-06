from pydantic import AnyHttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    env: str
    database_url: PostgresDsn
    redis_url: str
    qdrant_url: AnyHttpUrl
    qdrant_collection: str = "devlens_code_chunks"
    qdrant_api_key: str | None = None
    github_client_id: str
    github_client_secret: str
    github_oauth_redirect_uri: AnyHttpUrl
    frontend_url: AnyHttpUrl
    openrouter_api_key: str
    groq_api_key: str
    llm_chat_model: str = "openai/gpt-4o-mini"
    llm_fallback_model: str = "llama-3.1-8b-instant"
    llm_primary_provider: str = "openrouter"
    llm_fallback_provider: str = "groq"
    llm_primary_timeout_seconds: int = 15
    llm_fallback_timeout_seconds: int = 15
    openrouter_base_url: AnyHttpUrl = "https://openrouter.ai/api/v1"
    groq_base_url: AnyHttpUrl = "https://api.groq.com/openai/v1"
    jwt_secret: str
    jwt_access_ttl_minutes: int
    jwt_refresh_ttl_days: int
    share_token_ttl_days: int
    r2_bucket: str
    r2_access_key: str
    r2_secret_key: str
    rate_limit_window_seconds: int = 3600
    rate_limit_guest_per_window: int = 10
    rate_limit_auth_per_window: int = 50
    reranker_enabled: bool = False
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_candidate_limit: int = 50

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
