from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import _build_azure_scheme
from app.core.config import Settings


def test_openapi_exposes_entra_oauth_scheme(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    security_schemes = schema["components"]["securitySchemes"]
    azure_scheme = security_schemes["AzureAD_PKCE_single_tenant"]

    assert azure_scheme["type"] == "oauth2"
    authorization_code = azure_scheme["flows"]["authorizationCode"]
    assert authorization_code["authorizationUrl"].endswith("/oauth2/v2.0/authorize")
    assert authorization_code["tokenUrl"].endswith("/oauth2/v2.0/token")
    assert authorization_code["scopes"]["access_as_user"] == "Access MyMediaVault"


def test_openapi_marks_video_routes_as_secured(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()

    assert {"AzureAD_PKCE_single_tenant": []} in schema["paths"]["/videos"]["get"]["security"]
    assert {"AzureAD_PKCE_single_tenant": []} in schema["paths"]["/videos"]["post"]["security"]


def test_swagger_ui_uses_pkce_oauth_settings(client: TestClient) -> None:
    app = cast(FastAPI, client.app)

    assert app.swagger_ui_oauth2_redirect_url == "/oauth2-redirect"
    oauth_settings = app.swagger_ui_init_oauth
    assert oauth_settings is not None
    assert oauth_settings["usePkceWithAuthorizationCodeGrant"] is True
    assert oauth_settings["scopes"] == "access_as_user"


def test_azure_scheme_accepts_client_id_and_app_id_uri_audiences() -> None:
    scheme = _build_azure_scheme(
        Settings(
            entra_tenant_id="tenant",
            entra_client_id="backend-client-id",
            entra_api_scope="api://backend-client-id/access_as_user",
        )
    )

    assert scheme.accepted_audiences == ["backend-client-id", "api://backend-client-id"]
