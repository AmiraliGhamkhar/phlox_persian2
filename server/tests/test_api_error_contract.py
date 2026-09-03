"""Error-contract regressions found during the full-app E2E audit.

1. A malformed request that carries BINARY parts must still yield a
   structured 422. FastAPI's default validation-error encoder calls
   ``bytes.decode()`` on the raw upload bytes found in ``input``, which
   crashed the handler with a UnicodeDecodeError and turned every such
   request into an opaque 500 (e.g. sending multipart to a JSON endpoint).
   ``server.server`` now installs a sanitising RequestValidationError
   handler; these tests pin the behaviour.

2. ``extract_text_from_document`` documents a RuntimeError contract for
   "extraction dependencies are missing" and its callers answer 503.
   pytesseract raises TesseractNotFoundError (an OSError subclass) when the
   tesseract BINARY is absent while the Python package imports fine, which
   leaked past the contract and produced 500s on every image upload.
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
        response = client.post("/api/transcribe/process-document-visual", files=files)
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert isinstance(detail, list) and detail
        # the binary input was replaced with a placeholder, never decoded
        flattened = repr(detail)
        assert "binary payload" in flattened
        assert str(TINY_PNG[:8]) not in flattened

    def test_plain_missing_field_422_shape_unchanged(self, client):
        response = client.post("/api/letter/save", json={})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any(
            err.get("type") == "missing" and err.get("loc") == ["body", "noteId"] for err in detail
        )


class TestOcrBinaryMissingContract:
    @pytest.mark.asyncio
    async def test_tesseract_binary_missing_becomes_runtime_error(self, monkeypatch):
        from server.nlp_tools import document_processing as dp

        class FakeImage:
            @staticmethod
            def open(_src):
                return object()

        class FakeTess:
            @staticmethod
            def image_to_string(_img, lang=None):  # noqa: ARG004 - fake signature
                raise OSError("tesseract is not installed or it's not in your PATH")

            @staticmethod
            def get_languages(config=""):  # noqa: ARG004
                raise OSError("no tesseract")

        monkeypatch.setattr(dp, "OCR_AVAILABLE", True)
        monkeypatch.setattr(dp, "Image", FakeImage)
        monkeypatch.setattr(dp, "pytesseract", FakeTess)

        with pytest.raises(RuntimeError, match="tesseract binary"):
            await dp.extract_text_from_document(TINY_PNG, "image/png")
