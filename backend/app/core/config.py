from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AICTE CaseSync"
    environment: str = "development"
    database_url: str = "sqlite:///./casesync.db"
    secret_key: str = "development-only-change-me"
    access_token_minutes: int = 480
    demo_mode: bool = True
    demo_password: str = "CaseSync@2026"
    cors_origins: str = "http://localhost:3000"
    upload_dir: Path = Path("storage")
    max_upload_mb: int = 10
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


