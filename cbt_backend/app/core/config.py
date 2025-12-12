from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENV: str = "local"
    APP_NAME: str = "cbt-protocol-backend"

    CHECKPOINT_BACKEND: str = "postgres"  # "postgres" | "sqlite"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/cbt?sslmode=disable"
    SQLITE_PATH: str = "./data/checkpoints.db"

    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()
