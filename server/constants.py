import ipaddress
import logging
import os
import tempfile
from pathlib import Path

from platformdirs import user_data_dir

# Constants
IS_TESTING = os.getenv("TESTING", "false").lower() == "true"
IS_DOCKER = Path("/.dockerenv").exists() or os.getenv("DOCKER_CONTAINER") == "true"


def is_docker_runtime() -> bool:
    """Re-evaluate Docker detection at call time.

    ``IS_DOCKER`` is frozen at import time, which is fine for cheap
    module-level decisions. The auth middleware, however, must not trust a
    stale import-time flag: re-check the container markers on every request
    so a process started outside Docker never silently skips token
    validation (fail-closed), even if the environment changes late.
    """
    return Path("/.dockerenv").exists() or os.getenv("DOCKER_CONTAINER") == "true"


RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"

IS_DEMO_MODE = os.getenv("PHLOX_DEMO_MODE", "false").lower() == "true"

RATE_LIMIT_DESKTOP_MULTIPLIER = int(os.getenv("RATE_LIMIT_DESKTOP_MULTIPLIER", "3"))

# Proxy auth configuration (for reverse proxy deployments)
PROXY_AUTH_ENABLED = os.getenv("PROXY_AUTH_ENABLED", "false").lower() == "true"
PROXY_AUTH_USER_HEADER = os.getenv("PROXY_AUTH_USER_HEADER", "X-Forwarded-User")
PROXY_AUTH_ALLOWED_USERS = [
    u.strip() for u in os.getenv("PROXY_AUTH_ALLOWED_USERS", "").split(",") if u.strip()
]


def _split_env(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _parse_networks(raw_entries: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse CIDR entries; invalid entries are logged and skipped."""
    networks = []
    for entry in raw_entries:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid CIDR in TRUSTED_PROXY_CIDRS: %r", entry)
    return networks


# Browser origins allowed to call the API cross-origin. Empty (the default)
# means same-origin only: no CORS middleware is installed and the browser's
# same-origin policy blocks other origins from reading API responses.
ALLOWED_ORIGINS = _split_env("ALLOWED_ORIGINS")

# Extra Host header values the API will serve (defence against DNS rebinding).
# localhost/loopback are always allowed; add your public hostname here when
# deploying behind a reverse proxy.
ALLOWED_HOSTS = _split_env("ALLOWED_HOSTS")

# Reverse proxies whose X-Forwarded-For header may be trusted. When set, only
# connections from these CIDRs have their forwarded headers honoured; when
# empty, any private-IP peer is trusted (previous behaviour).
TRUSTED_PROXY_NETWORKS = _parse_networks(_split_env("TRUSTED_PROXY_CIDRS"))

APP_NAME = "Phlox"
APP_AUTHOR = "bloodworks.io"


logger = logging.getLogger(__name__)


def get_app_directories():
    """Get appropriate directories based on environment"""
    if IS_DOCKER:
        logger.info("Running in Docker environment; setting up directories")
        data_dir = Path("/usr/src/app/data")
        build_dir = Path("/usr/src/app/build")
    else:
        # For Tauri desktop app
        logger.info("Running in desktop environment; setting up directories")
        logger.info(f"IS_DOCKER={IS_DOCKER}")
        data_dir = Path(user_data_dir(APP_NAME, APP_AUTHOR))
        logger.info("Data directory: %s", data_dir)
        build_dir = None  # No need to serve static files

    return data_dir, build_dir


# Get directories
DATA_DIR, BUILD_DIR = get_app_directories()

# Create directories if they don't exist
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_temp_directory():
    """Get appropriate temporary directory based on environment"""
    if IS_DOCKER:
        temp_dir = Path("/usr/src/app/temp")
    else:
        # Use system temp directory with app-specific subdirectory
        temp_dir = Path(tempfile.gettempdir()) / "phlox"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


TEMP_DIR = get_temp_directory()
