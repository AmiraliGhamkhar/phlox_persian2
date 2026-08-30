"""Regression tests for SPA route handling when the API does not serve the frontend.

In desktop / bare-metal dev modes ``BUILD_DIR`` is ``None`` (the Tauri bundle
or the Vite dev server serves the SPA). The SPA routes must respond with a
clean 404 JSON instead of crashing with a TypeError/500.
"""

import pytest
from fastapi.testclient import TestClient

from server.constants import BUILD_DIR
from server.server import initialize_and_get_app
from server.utils.local_request_token import set_request_token

TEST_TOKEN = "e2e-static-routes-test-token"


@pytest.fixture(scope="module")
def app_client():
    set_request_token(TEST_TOKEN)
    app = initialize_and_get_app()
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


SPA_PATHS = [
    "/",
    "/new-note",
    "/settings",
    "/rag",
    "/clinic-summary",
    "/outstanding-jobs",
    "/note/42",
    "/some-unknown-client-route",
]


@pytest.mark.skipif(
    BUILD_DIR is not None,
    reason="only meaningful when the API does not serve the SPA (BUILD_DIR is None)",
)
def test_spa_routes_404_when_build_dir_none(app_client, auth_headers):
    """Every SPA path must return a clean 404 JSON — never a 500."""
    for path in SPA_PATHS:
        response = app_client.get(path, headers=auth_headers)
        assert response.status_code == 404, (
            f"GET {path} returned {response.status_code}, expected 404"
        )
        assert response.headers["content-type"].startswith("application/json")


@pytest.mark.skipif(
    BUILD_DIR is not None,
    reason="only meaningful when the API does not serve the SPA (BUILD_DIR is None)",
)
def test_api_routes_still_work_when_build_dir_none(app_client, auth_headers):
    """The API surface must be unaffected by the SPA-serving guard."""
    response = app_client.get("/api/dashboard/health", headers=auth_headers)
    assert response.status_code == 200
    response = app_client.get("/api/definitely-not-a-route", headers=auth_headers)
    assert response.status_code == 404
