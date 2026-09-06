from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration, loaded from environment / .env.

    Swapping DATABASE_URL from a sqlite+aiosqlite DSN to a
    postgresql+asyncpg DSN is the entire migration described in
    ADR-002 — no application code changes.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MLOps Platform API"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./mlops.db"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: list[str] = ["http://localhost:4200"]

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
