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
    entra_api_scope: str = "access_as_user"
    admin_object_ids: list[str] = Field(default_factory=list)
    admin_role_names: list[str] = Field(default_factory=lambda: ["Admin", "MyMediaVault.Admin"])

    @property
    def is_test(self) -> bool:
        return self.environment == "test" or self.test_mode

    @property
    def production_auth_configured(self) -> bool:
        return bool(self.entra_tenant_id and self.entra_client_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
