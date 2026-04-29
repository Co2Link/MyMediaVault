from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin_tags, videos
from app.auth.dependencies import load_azure_openid_config
from app.core.config import get_settings
from app.core.db import create_db_and_tables
from app.core.errors import register_exception_handlers


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    await load_azure_openid_config(get_settings())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MyMediaVault API",
        version="0.1.0",
        lifespan=lifespan,
        swagger_ui_oauth2_redirect_url="/oauth2-redirect",
        swagger_ui_init_oauth={
            "usePkceWithAuthorizationCodeGrant": True,
            "clientId": settings.entra_openapi_client_id or settings.entra_client_id or "",
            "scopes": settings.entra_api_scope,
        },
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
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
