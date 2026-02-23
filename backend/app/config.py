from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DevLens Backend"
    env: str = "development"
    database_url: str = "postgresql://postgres:postgres@postgres:5432/devlens"
    redis_url: str = "redis://redis:6379/0"
    qdrant_url: str = "http://qdrant:6333"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
