from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin_tags, videos
from app.auth.dependencies import configure_azure_scheme, load_azure_openid_config
from app.core.config import Settings, get_settings
from app.core.db import create_db_and_tables
from app.core.errors import register_exception_handlers


@asynccontextmanager
async def lifespan(_: FastAPI, settings: Settings) -> AsyncIterator[None]:
    create_db_and_tables()
    await load_azure_openid_config(settings)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    if resolved_settings.production_auth_configured:
        configure_azure_scheme(resolved_settings)
    app = FastAPI(
        title="MyMediaVault API",
        version="0.1.0",
        lifespan=lambda app: lifespan(app, resolved_settings),
        swagger_ui_oauth2_redirect_url="/oauth2-redirect",
        swagger_ui_init_oauth={
            "usePkceWithAuthorizationCodeGrant": True,
            "clientId": resolved_settings.entra_openapi_client_id or "",
            "scopes": resolved_settings.entra_scope_name,
        },
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(videos.router)
    app.include_router(admin_tags.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "commit": get_settings().commit_sha}

    return app


app = create_app()
