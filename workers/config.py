from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    env: str
    redis_url: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = WorkerSettings()
