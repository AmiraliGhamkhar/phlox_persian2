"""Tests for PHI sanitization, the pending-action store, and the SSRF guard.

Most of these are pure-Python units; ``TestPubMedSanitization`` uses pytest
asyncio support via ``@pytest.mark.asyncio``.
"""

import pytest

from server.chat.tools.sanitization import (
    sanitize_pubmed_query,
    sanitize_query_for_external_search,
    set_active_patient_context,
)
from server.utils.ssrf import (
    build_guarded_http_client,
    build_guarded_sync_http_client,
    validate_fetch_url,
)


class TestSanitizeQueryForExternalSearch:
    def test_strips_ur_numbers(self):
        assert "123456" not in sanitize_query_for_external_search("diabetes UR:123456 management")

    def test_strips_gregorian_dates(self):
        assert "1980-01-01" not in sanitize_query_for_external_search("guideline for 1980-01-01")

    def test_strips_jalali_dates(self):
        assert "1370" not in sanitize_query_for_external_search(" hypertension 1370/05/12 ")

    def test_folds_persian_digits(self):
        # Persian-digit UR number should be folded and stripped
        assert "۱۲۳۴۵" not in sanitize_query_for_external_search("bimaprotocol UR:۱۲۳۴۵ ")
        result = sanitize_query_for_external_search("تاریخ تولد ۱۳۷۰/۰۵/۱۲")
        assert "۱۳۷۰" not in result

    def test_strips_emails(self):
        assert "@" not in sanitize_query_for_external_search("contact a@b.com for info")

    def test_strips_active_patient_identifiers(self):
        set_active_patient_context({"name": "Alice Smith", "ur_number": "UR777"})
        try:
            result = sanitize_query_for_external_search("Alice Smith latest research")
            assert "Alice" not in result
            result2 = sanitize_query_for_external_search("UR777 outcome study")
            assert "777" not in result2
        finally:
            set_active_patient_context(None)

    def test_explicit_context_beats_lookup(self):
        result = sanitize_query_for_external_search(
            "Bob Jones therapy", patient_context={"name": "Bob Jones"}
        )
        assert "Bob" not in result

    def test_never_returns_empty(self):
        # Fail closed: a query that is entirely PHI must come back empty so
        # callers skip the outbound request (LLM02:2026).
        assert sanitize_query_for_external_search("UR:123456") == ""
        assert sanitize_query_for_external_search("ali@example.com") == ""
        assert (
            sanitize_query_for_external_search("علی رضایی", patient_context={"name": "علی رضایی"})
            == ""
        )


def test_sanitize_pubmed_query_keeps_covid19():
    assert sanitize_pubmed_query("COVID-19 vaccines") == "COVID-19 vaccines"


def test_sanitize_pubmed_query_removes_bare_year():
    assert "2024" not in sanitize_pubmed_query("melanoma 2024")


class TestSsrfGuard:
    def test_rejects_non_http_scheme(self):
        for url in ("ftp://example.com", "file:///etc/passwd", "gopher://x"):
            try:
                validate_fetch_url(url)
            except ValueError:
                pass
            else:
                raise AssertionError(f"scheme should be rejected: {url}")

    def test_rejects_link_local_metadata(self):
        # Link-local is where cloud metadata services live (169.254.169.254).
        import socket

        orig = validate_fetch_url.__globals__["socket_getaddrinfo"]
        validate_fetch_url.__globals__["socket_getaddrinfo"] = lambda _host, _port=None: [
            (socket.AF_INET, 1, 6, "", ("169.254.169.254", 0))
        ]
        try:
            try:
                validate_fetch_url("http://metadata.example.com/latest")
            except ValueError as e:
                assert "link-local" in str(e) or "Blocked" in str(e)
            else:
                raise AssertionError("metadata IP should be blocked")
        finally:
            validate_fetch_url.__globals__["socket_getaddrinfo"] = orig

    def test_allows_loopback_and_lan(self, monkeypatch):
        import socket

        monkeypatch.setattr(
            "server.utils.ssrf.socket_getaddrinfo",
            lambda _host, _port=None: [(socket.AF_INET, 1, 6, "", ("127.0.0.1", 0))],
        )
        validate_fetch_url("http://localhost:11434/v1/models")

        monkeypatch.setattr(
            "server.utils.ssrf.socket_getaddrinfo",
            lambda _host, _port=None: [(socket.AF_INET, 1, 6, "", ("192.168.1.50", 0))],
        )
        validate_fetch_url("http://192.168.1.50:8080")

    def test_rejects_empty_and_credential_urls(self):
        for url in ("", "   ", "http://user:pass@example.com"):
            try:
                validate_fetch_url(url)
            except ValueError:
                pass
            else:
                raise AssertionError(f"should be rejected: {url!r}")

    @pytest.mark.asyncio
    async def test_pinned_transport_sends_a_single_host_header(self):
        """Regression: the pinned request must carry exactly one Host header.

        ``dict(headers)`` lowercases keys, so a case-sensitive
        ``setdefault("Host", ...)`` used to insert a *second* entry; h11 then
        rejected the request on the wire ("Found multiple Host: headers") and
        every guarded fetch (LLM chat, embeddings, external ASR, status
        probes) failed.
        """
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        seen: dict = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server API
                seen["hosts"] = self.headers.get_all("Host")
                body = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            async with build_guarded_http_client() as client:
                response = await client.get(f"http://127.0.0.1:{port}/v1/models", timeout=5.0)
            assert response.status_code == 200
            assert response.json() == {"ok": True}
            # Exactly one Host header, echoing the original hostname:port.
            assert seen["hosts"] == [f"127.0.0.1:{port}"]
        finally:
            server.shutdown()
            server.server_close()

    def test_sync_guarded_client_fetches_with_single_host_header(self):
        """The sync twin (used by the sync OpenAI embedding client) must work.

        Passing the *async* guarded client to the sync ``OpenAI`` constructor
        raised ``TypeError`` at construction, which took down the whole vector
        store — so the sync transport gets its own round-trip test.
        """
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        seen: dict = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server API
                seen["hosts"] = self.headers.get_all("Host")
                body = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with build_guarded_sync_http_client() as client:
                response = client.get(f"http://127.0.0.1:{port}/v1/embeddings", timeout=5.0)
            assert response.status_code == 200
            assert response.json() == {"ok": True}
            assert seen["hosts"] == [f"127.0.0.1:{port}"]
        finally:
            server.shutdown()
            server.server_close()


class TestSanitizeFailsClosed:
    """The scrubber must never send the original query when it was all PHI."""

    def test_phi_only_query_returns_empty(self):
        from server.chat.tools.sanitization import sanitize_query_for_external_search

        # Pattern-based PHI (UR/MRN/email) and patient-context names both
        # produce an empty string so callers skip the outbound request.
        assert sanitize_query_for_external_search("UR 4421") == ""
        assert sanitize_query_for_external_search("ali@example.com") == ""
        assert (
            sanitize_query_for_external_search("علی رضایی", patient_context={"name": "علی رضایی"})
            == ""
        )

    def test_mixed_query_keeps_non_phi(self):
        from server.chat.tools.sanitization import sanitize_query_for_external_search

        result = sanitize_query_for_external_search(
            "علی رضایی UR:4421 آسم bronchodilator",
            patient_context={"name": "علی رضایی"},
        )
        assert "آسم" in result and "bronchodilator" in result
        assert "علی" not in result and "4421" not in result


class TestPubMedSanitization:
    """PubMed queries must pass the generic PHI scrubber before going out."""

    def test_pubmed_query_uses_phi_scrubber(self):
        import inspect
        import re

        from server.chat.tools import pubmed_search

        source = inspect.getsource(pubmed_search)
        # In every code path that builds a PubMed query the generic PHI scrub
        # runs immediately before the year-only scrub.
        assert re.search(
            r"sanitize_query_for_external_search\(query\)\s*\n\s*query = sanitize_pubmed_query",
            source,
        )

    @pytest.mark.asyncio
    async def test_search_pubmed_never_sends_phi(self):
        import types
        from unittest.mock import AsyncMock

        from server.chat.tools import pubmed_search

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

            @property
            def text(self):
                return "<PubmedArticleSet></PubmedArticleSet>"

        fake_client = AsyncMock()
        fake_client.get.side_effect = [FakeResponse({"esearchresult": {"idlist": []}})]

        class FakeHttpx(types.SimpleNamespace):
            class AsyncClient:
                def __init__(self, *a, **k):
                    pass

                async def __aenter__(self):
                    return fake_client

                async def __aexit__(self, *a):
                    return False

        original = pubmed_search.httpx
        pubmed_search.httpx = FakeHttpx()
        # Production flow: ChatEngine registers the active patient so the
        # scrubber strips the patient's name as well as generic PHI.
        set_active_patient_context({"name": "علی رضایی"})
        try:
            result = await pubmed_search.search_pubmed("علی رضایی UR:4421 melanoma", max_results=3)
        finally:
            pubmed_search.httpx = original
            set_active_patient_context(None)
        assert result == []
        # The exact term sent to NCBI must be PHI-free.
        term = fake_client.get.call_args.kwargs["params"]["term"]
        assert "علی" not in term
        assert "4421" not in term
