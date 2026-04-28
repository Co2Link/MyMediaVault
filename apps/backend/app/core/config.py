from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MMV_", env_file=".env", extra="ignore")

    environment: Environment = "development"
    database_url: str = "sqlite:///./mymediavault.db"
    test_mode: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    blob_storage_root: Path = Path(".local/blob-storage")
    azure_storage_connection_string: str | None = None
    azure_blob_container: str = "torrent-raw"
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None

    @property
    def is_test(self) -> bool:
        return self.environment == "test" or self.test_mode


@lru_cache
def get_settings() -> Settings:
    return Settings()
