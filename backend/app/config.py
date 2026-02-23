from pydantic import AnyHttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    env: str
    database_url: PostgresDsn
    redis_url: str
    qdrant_url: AnyHttpUrl
    github_client_id: str
    github_client_secret: str
    openrouter_api_key: str
    groq_api_key: str
    jwt_secret: str
    jwt_access_ttl_minutes: int
    jwt_refresh_ttl_days: int
    share_token_ttl_days: int
    r2_bucket: str
    r2_access_key: str
    r2_secret_key: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
