"""Request/upload size limits.

Shared caps so unauthenticated-with-CORS deployments (and any client) cannot
exhaust memory by streaming an arbitrarily large body into RAM. Two layers:

1. ``RequestBodyLimitMiddleware`` rejects early on the Content-Length header.
2. ``read_upload_limited`` caps the actual bytes read (covers chunked bodies
   that have no Content-Length).
"""

from fastapi import HTTPException, UploadFile, status

MB = 1024 * 1024

# Per-category caps (aligned with what the features legitimately need).
MAX_AUDIO_UPLOAD_BYTES = 100 * MB  # visit recordings
MAX_DOCUMENT_UPLOAD_BYTES = 25 * MB  # referrals / PDFs for processing
MAX_IMAGE_UPLOAD_BYTES = 25 * MB  # chat image attachments
MAX_PDF_UPLOAD_BYTES = 50 * MB  # RAG ingestion (matches /api/pdf-forms cap)

# Global per-request body cap applied by middleware (JSON vision payloads with
# up to 8 base64 pages fit comfortably).
DEFAULT_API_BODY_LIMIT = 64 * MB
TRANSCRIBE_API_BODY_LIMIT = 110 * MB  # multipart audio + form overhead


async def read_upload_limited(file: UploadFile, max_bytes: int, label: str = "Upload") -> bytes:
    """Read at most ``max_bytes`` bytes from an upload, else raise 413."""
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{label} is too large (max {max_bytes // MB} MB)",
        )
    return data
