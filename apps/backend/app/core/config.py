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
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    blob_storage_root: Path = Path(".local/blob-storage")
    azure_storage_connection_string: str | None = None
    azure_blob_container: str = "torrent-raw"
    commit_sha: str = "local"
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_openapi_client_id: str | None = None
    entra_api_scope: str = "access_as_user"
    admin_object_ids: list[str] = Field(default_factory=list)
    admin_role_names: list[str] = Field(default_factory=lambda: ["Admin", "MyMediaVault.Admin"])
    torrent_provider: Literal["fake", "http"] = "fake"
    torrent_resolver_urls: list[str] = Field(default_factory=list)
    torrent_fetch_timeout_seconds: float = 10.0
    torrent_worker_enabled: bool = True
    torrent_worker_poll_interval_seconds: float = 2.0
    torrent_job_lease_seconds: int = 30

    @property
    def entra_scope_description(self) -> str:
        if self.entra_api_scope.startswith("api://"):
            return self.entra_api_scope.rsplit("/", 1)[-1]
        return self.entra_api_scope

    @property
    def entra_scope_name(self) -> str:
        if not self.entra_client_id:
            return self.entra_api_scope
        return f"api://{self.entra_client_id}/{self.entra_scope_description}"

    @property
    def entra_scopes(self) -> dict[str, str]:
        return {self.entra_scope_name: self.entra_scope_description}

    @property
    def entra_authorization_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}/oauth2/v2.0/authorize"

    @property
    def entra_token_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}/oauth2/v2.0/token"

    @property
    def production_auth_configured(self) -> bool:
        return bool(self.entra_tenant_id and self.entra_client_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
