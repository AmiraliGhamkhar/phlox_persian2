"""Tests for the API request audit trail (audit_log table)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.database.core.connection import get_db
from server.middleware import AuditLogMiddleware


def _audited_app():
    app = FastAPI()
    app.add_middleware(AuditLogMiddleware)

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    @app.get("/page")
    def page():
        return {"ok": True}

    return app


def _audit_count():
    with get_db().read() as cursor:
        return cursor.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]


def _last_audit_row():
    with get_db().read() as cursor:
        return cursor.execute(
            "SELECT actor, method, path, status, client_ip, duration_ms "
            "FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()


def test_audit_records_api_requests():
    client = TestClient(_audited_app())
    response = client.get("/api/ping")
    assert response.status_code == 200

    row = _last_audit_row()
    assert row["method"] == "GET"
    assert row["path"] == "/api/ping"
    assert row["status"] == 200
    assert row["actor"] == "local"
    assert row["duration_ms"] >= 0


def test_audit_records_error_statuses():
    client = TestClient(_audited_app())
    assert client.get("/api/does-not-exist").status_code == 404

    row = _last_audit_row()
    assert row["path"] == "/api/does-not-exist"
    assert row["status"] == 404


def test_audit_skips_non_api_paths():
    client = TestClient(_audited_app())
    before = _audit_count()
    assert client.get("/page").status_code == 200
    assert _audit_count() == before


def test_audit_query_strings_are_not_stored():
    client = TestClient(_audited_app())
    client.get("/api/ping?secret=hunter2")

    row = _last_audit_row()
    assert row["path"] == "/api/ping"  # no query component
    assert row["client_ip"] is None or "hunter2" not in str(row["client_ip"])


def test_audit_purge_respects_retention():
    with get_db().transaction() as cursor:
        cursor.execute(
            "INSERT INTO audit_log (timestamp, actor, method, path, status) "
            "VALUES (datetime('now', '-365 days'), 'local', 'GET', '/api/old-row', 200)"
        )

    AuditLogMiddleware.purge_expired_rows_sync()

    with get_db().read() as cursor:
        remaining = cursor.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE path = '/api/old-row'"
        ).fetchone()["n"]
    assert remaining == 0


def test_audit_write_failure_never_breaks_request(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(AuditLogMiddleware, "_write_audit_row", staticmethod(boom))
    client = TestClient(_audited_app())
    response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
