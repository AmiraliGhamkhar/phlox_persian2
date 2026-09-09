"""Error-contract regressions found during the full-app E2E audit.

A malformed request that carries BINARY parts must still yield a
structured 422. FastAPI's default validation-error encoder calls
``bytes.decode()`` on the raw upload bytes found in ``input``, which
crashed the handler with a UnicodeDecodeError and turned every such
request into an opaque 500 (e.g. sending multipart to a JSON endpoint).
``server.server`` now installs a sanitising RequestValidationError
handler; these tests pin the behaviour.
"""

import base64

import pytest
from fastapi.testclient import TestClient

from server.server import initialize_and_get_app
from server.utils.local_request_token import set_request_token

TEST_TOKEN = "e2e-error-contract-test-token"

# Smallest valid 1x1 RGB PNG (as produced by any encoder).
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
)


@pytest.fixture(scope="module")
def client():
    set_request_token(TEST_TOKEN)
    return TestClient(initialize_and_get_app(), headers={"Authorization": f"Bearer {TEST_TOKEN}"})


class TestBinaryValidation422:
    def test_multipart_to_json_endpoint_is_422_not_500(self, client):
        files = {"file": ("evil.png", TINY_PNG, "image/png")}
        response = client.post("/api/workspace/report", files=files)
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert isinstance(detail, list) and detail
        # the binary input was replaced with a placeholder, never decoded
        flattened = repr(detail)
        assert "binary payload" in flattened
        assert str(TINY_PNG[:8]) not in flattened

    def test_plain_missing_field_422_shape_unchanged(self, client):
        response = client.post("/api/workspace/report", json={})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any(
            err.get("type") == "missing" and err.get("loc") == ["body", "transcript"]
            for err in detail
        )
