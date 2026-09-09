"""Host/Origin middleware must honour ALLOWED_ORIGINS=* on POSTs."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.middleware import HostValidationMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(HostValidationMiddleware)

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    @app.post("/api/ping")
    def ping_post():
        return {"ok": True}

    return app


def test_wildcard_origin_allows_preview_post(monkeypatch):
    monkeypatch.setattr("server.constants.IS_TESTING", False)
    monkeypatch.setattr("server.constants.ALLOWED_ORIGINS", ["*"])
    client = TestClient(_app())
    response = client.post(
        "/api/ping",
        json={},
        headers={"Origin": "https://3000-abc.e2b.app"},
    )
    assert response.status_code == 200, response.text


def test_unknown_origin_rejected_without_wildcard(monkeypatch):
    monkeypatch.setattr("server.constants.IS_TESTING", False)
    monkeypatch.setattr("server.constants.ALLOWED_ORIGINS", [])
    client = TestClient(_app())
    response = client.post(
        "/api/ping",
        json={},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_origin_allowed_helper_wildcard(monkeypatch):
    monkeypatch.setattr("server.constants.ALLOWED_ORIGINS", ["*"])
    assert HostValidationMiddleware._origin_allowed(
        "https://3000-abc.e2b.app",
        {"localhost"},
        "localhost:5000",
    )
