"""Minimal service endpoints: container liveness probe only."""

import logging

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """Simple health check endpoint that returns OK if the server is running."""
    return {"status": "ok"}
