"""Tests for PHI sanitization, the pending-action store, and the SSRF guard.

These are pure-Python units and do not touch the database.
"""

from server.chat.tools.sanitization import (
    sanitize_pubmed_query,
    sanitize_query_for_external_search,
    set_active_patient_context,
)
from server.utils.ssrf import validate_fetch_url


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
        # If sanitization would empty the query, the original is returned.
        assert sanitize_query_for_external_search("UR:123456")  # truthy


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
