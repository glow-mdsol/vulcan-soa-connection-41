from fastapi.testclient import TestClient

from vulcan_soa.api.app import create_app
from vulcan_soa.config import Settings


def _test_settings() -> Settings:
    return Settings(
        fhir_base_url="https://aidbox.test/fhir",
        oauth_authorize_url="https://aidbox.test/authorize",
        oauth_token_url="https://aidbox.test/token",
        smart_client_id="client-1",
        smart_client_secret="secret-1",
        redirect_uri="https://app.test/callback",
        frontend_url="https://app.test",
    )


def test_create_app_returns_401_on_context_without_session_cookie():
    client = TestClient(create_app(settings=_test_settings()))

    response = client.get("/api/context")

    assert response.status_code == 401


def test_create_app_mounts_launch_routes():
    client = TestClient(create_app(settings=_test_settings()), follow_redirects=False)

    response = client.get("/launch/standalone")

    assert response.status_code in (302, 307)


def test_create_app_sets_cors_allow_origin_for_frontend_url():
    client = TestClient(create_app(settings=_test_settings()))

    response = client.options(
        "/api/context",
        headers={"Origin": "https://app.test", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.test"
    assert response.headers["access-control-allow-credentials"] == "true"
