if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()

import logging
import os
import secrets
import socket
import sys
from contextlib import asynccontextmanager, closing
from typing import Any

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server.constants import (
    ALLOWED_ORIGINS,
    APP_NAME,
    BUILD_DIR,
    IS_DOCKER,
    IS_TESTING,
    PROXY_AUTH_ALLOWED_USERS,
    PROXY_AUTH_ENABLED,
    PROXY_AUTH_USER_HEADER,
    RATE_LIMIT_ENABLED,
)
from server.middleware import (
    HostValidationMiddleware,
    LocalTokenMiddleware,
    ProxyAuthMiddleware,
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    TrustedProxyMiddleware,
)
from server.utils.parent_watchdog import start_parent_watchdog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)

# Silence noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
logger.info("Initialising application...")
scheduler = AsyncIOScheduler()

# Local request token for API authentication (desktop mode only)
from server.utils.local_request_token import get_request_token, set_request_token  # noqa: E402

if IS_TESTING:
    try:
        from server.tests.test_database import test_db as test_database
    except ImportError:
        test_database: Any = None
else:
    test_database: Any = None


# Start the scheduler when the app starts
@asynccontextmanager
async def lifespan(_app: FastAPI):
    from server.middleware import RateLimitMiddleware

    # Startup
    scheduler.start()
    # Clean up zombie IPs from rate limiter every 5 minutes
    scheduler.add_job(
        RateLimitMiddleware.cleanup_all_zombie_ips,
        "interval",
        minutes=5,
    )

    # Docker has no Rust sidecar: start whichever bundled local servers the
    # saved config asks for (best-effort, in a thread — model loads are slow
    # and must not block startup).
    import threading

    def _autostart_local_servers() -> None:
        try:
            from server.utils.local_servers import ensure_configured_local_servers

            ensure_configured_local_servers()
        except Exception:
            logger.debug("Local server autostart skipped", exc_info=True)

    autostart = threading.Thread(
        target=_autostart_local_servers, name="local-autostart", daemon=True
    )
    autostart.start()

    yield

    # Shutdown
    scheduler.shutdown()
    try:
        from server.utils.local_servers import stop_local_servers

        stop_local_servers()
    except Exception:
        logger.debug("Local server shutdown skipped", exc_info=True)


def initialize_and_get_app():
    """Initialize database and return the FastAPI app.

    This is called after passphrase is available (desktop) or immediately (docker).
    """
    # Initialize config_manager and run migrations
    logger.info("Initializing DB and running migrations...")

    logger.info("Database initialized")

    app = FastAPI(
        title=APP_NAME,
        lifespan=lifespan,  # Add the lifespan context manager
    )

    # A malformed request whose validation errors carry non-JSON-safe values
    # (e.g. the raw bytes of a bad file upload, or a bound method in a
    # custom-validator context) makes FastAPI's default 422 encoder die with
    # a UnicodeDecodeError/TypeError — turning a routine 422 into a 500 and
    # hiding the actual problem. Replace binary/non-serializable values with
    # safe placeholders so clients always get the structured 422.
    @app.exception_handler(RequestValidationError)
    async def _safe_validation_error_handler(
        request: Request,  # noqa: ARG001 - required by the handler signature
        exc: RequestValidationError,
    ):
        def _sanitise(value: object) -> object:
            if isinstance(value, (bytes, bytearray, memoryview)):
                return f"<binary payload: {len(value)} bytes>"
            if isinstance(value, dict):
                return {str(key): _sanitise(item) for key, item in value.items()}
            if isinstance(value, (list, tuple, set, frozenset)):
                return [_sanitise(item) for item in value]
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            return str(value)

        detail = [_sanitise(dict(error)) for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": detail})

    # CORS configuration - restrict via environment variable.
    # Default (unset/empty) = same-origin only: no CORS middleware is added and
    # the browser's same-origin policy blocks other origins from reading API
    # responses. Explicitly set ALLOWED_ORIGINS=* to opt back into the wildcard
    # (credentials are impossible with a wildcard), or list specific origins to
    # allow credentialed cross-origin access for exactly those hosts.
    allowed_origins = list(ALLOWED_ORIGINS)
    if not allowed_origins:
        logger.info("No ALLOWED_ORIGINS configured - API is same-origin only")
    elif "*" in allowed_origins:
        # Wildcard mode - no credentials allowed by browsers
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # Specific origins - credentials allowed
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Add security middleware (order matters: last added runs first)
    # So we add in reverse order: Token -> Proxy -> RateLimit -> TrustedProxy -> Security
    # This ensures TrustedProxy sets client_ip before RateLimit needs it

    # Add token verification middleware (only for desktop mode)
    if not IS_DOCKER:
        app.add_middleware(LocalTokenMiddleware)

    # Add proxy auth middleware (for Docker deployments behind auth proxy)
    if PROXY_AUTH_ENABLED:
        app.add_middleware(ProxyAuthMiddleware)
        logger.info(f"Proxy auth enabled, header: {PROXY_AUTH_USER_HEADER}")

    # Add rate limiting middleware (enabled by default in Docker mode)
    if RATE_LIMIT_ENABLED:
        app.add_middleware(RateLimitMiddleware)
        logger.info("Rate limiting enabled")

    app.add_middleware(TrustedProxyMiddleware)
    # Host/Origin validation (anti DNS-rebinding + anti cross-site form POST)
    app.add_middleware(HostValidationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    # Cheap early rejection of oversized bodies (runs before auth/rate limits)
    app.add_middleware(RequestBodyLimitMiddleware)
    # Correlation id for every request (X-Request-Id echo/generation). Added
    # last so it executes first and downstream middleware/handlers can include
    # the id in their logs.
    app.add_middleware(RequestIdMiddleware)

    # Then load API submodules (the simplified app serves transcription,
    # workspace/report, settings, and health only)
    from server.api import dashboard, transcribe, workspace
    from server.api.config import router as config_router

    # Only create test endpoint in testing environment
    if IS_TESTING and test_database is not None:

        @app.get("/test-db")
        async def test_db():  # type: ignore[misc]
            try:
                result = test_database()
                logger.info(f"Database test succeeded: {result}")
                return {"success": "Database test succeeded", "result": result}
            except Exception as e:
                logger.error(f"Database test failed: {str(e)}")
                raise HTTPException(
                    status_code=500, detail=f"Database test failed: {str(e)}"
                ) from e

    # Include routers
    app.include_router(transcribe.router, prefix="/api/transcribe")
    app.include_router(dashboard.router, prefix="/api/dashboard")
    app.include_router(workspace.router, prefix="/api/workspace")
    app.include_router(config_router, prefix="/api/config")

    # PUBLIC_PATHS lists these as unauthenticated probes. Serve JSON here so
    # a container/orchestrator hitting /health does not receive the SPA HTML
    # (or a 404 in desktop/dev where BUILD_DIR is None).
    @app.get("/health")
    @app.get("/api/health")
    async def root_health():
        return {"status": "ok"}

    @app.get("/version")
    async def root_version():
        from server._version import __version__

        return {"name": APP_NAME, "version": __version__}

    # React app routes (specialty picker, workspace, settings)
    @app.get("/settings")
    @app.get("/workspace")
    async def serve_react_app():
        # Desktop / bare-metal dev modes do not serve the SPA from the API
        # (Tauri bundles it, or the Vite dev server serves it). A clean 404
        # beats the TypeError that a None BUILD_DIR would otherwise produce.
        if BUILD_DIR is None:
            raise HTTPException(
                status_code=404,
                detail="Frontend is not served by the API in this mode",
            )
        return FileResponse(BUILD_DIR / "index.html")

    # Serve static files
    if BUILD_DIR is not None:
        app.mount("/", StaticFiles(directory=BUILD_DIR, html=True), name="static")

    # Catch-all route for any other paths
    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        if BUILD_DIR is None:
            raise HTTPException(
                status_code=404,
                detail="Frontend is not served by the API in this mode",
            )
        return FileResponse(BUILD_DIR / "index.html")

    return app


# For Docker mode, initialize app at module load (backward compatibility)
if IS_DOCKER:
    from server.database.core.connection import initialize_database

    initialize_database()  # Uses env/secret
    app = initialize_and_get_app()
else:
    # Desktop mode: app will be initialized after passphrase is received.
    # Bare-metal web development (`npm run dev`) opts in via PHLOX_DEV_BOOT
    # so the app boots immediately from DB_ENCRYPTION_KEY, like docker mode.
    if os.environ.get("PHLOX_DEV_BOOT") == "1":
        from server.database.core.connection import initialize_database

        initialize_database()  # Uses env/secret
        app = initialize_and_get_app()
    else:
        app: Any = None


def find_free_port():
    """Find a free port on the local machine"""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def start_server_for_desktop():
    """Start server with dynamic port for desktop app.

    Waits for passphrase from stdin before initializing database.
    """
    global app
    logger.info("Desktop environment detected")

    # Generate cryptographically secure request token
    token = secrets.token_hex(32)  # 64 character hex string (256 bits)
    set_request_token(token)
    logger.info("Request token generated (256 bits)")

    # Signal that we're waiting for passphrase
    print("WAITING_FOR_PASSPHRASE", flush=True)

    # Block waiting for passphrase from stdin
    passphrase = sys.stdin.readline().strip()

    if not passphrase:
        logger.error("No passphrase received from stdin")
        sys.exit(1)

    # Initialize database with passphrase
    from server.database.core.connection import initialize_database

    try:
        initialize_database(passphrase=passphrase)
    except ValueError as e:
        logger.error(f"Failed to initialize database: {e}")
        print(f"ERROR:{e}", flush=True)
        sys.exit(1)

    # Now initialize the app
    app = initialize_and_get_app()

    # Find ports - one for each service
    server_port = find_free_port()
    llama_port = find_free_port()
    whisper_port = find_free_port()
    embedding_port = find_free_port()

    # Store in global state for other modules to access
    from server.utils.allocated_ports import set_ports

    set_ports(server_port, llama_port, whisper_port, embedding_port)

    # Write ports and token to stdout so process manager can read them
    print(
        f"PORTS:{server_port},{llama_port},{whisper_port},{embedding_port}|TOKEN:{get_request_token()}",
        flush=True,
    )

    # Start parent-PID watchdog
    parent_pid = os.environ.get("PHLOX_PARENT_PID")
    if parent_pid:
        try:
            start_parent_watchdog(int(parent_pid))
        except ValueError:
            logger.warning("Invalid PHLOX_PARENT_PID: %r", parent_pid)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",  # Only localhost
        port=server_port,
        timeout_keep_alive=300,
        timeout_graceful_shutdown=10,
        loop="asyncio",
        workers=0,
        http="httptools",
        # Access logs are the only place the full request URL (including any
        # query string) is written, and the desktop shell pipes server stdout
        # into the on-disk app log. Disable access logs to keep secrets
        # (e.g. handshake auth) out of log files (A09:2025).
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


def _enforce_docker_network_policy(host: str, *, exposed: bool) -> None:
    """Fail fast when a Docker deployment exposes the API without auth.

    The API has no authentication of its own in Docker (LocalTokenMiddleware
    is skipped); the only auth option is the reverse-proxy header. Publishing
    the API beyond loopback while ``PROXY_AUTH_ENABLED`` is off would expose
    every /api route — including provider keys and transcripts — without
    credentials. The compose stack declares that intent explicitly via
    ``PHLOX_EXPOSE_PUBLIC=1`` because a container must bind 0.0.0.0 even for
    a loopback-only publish (docker-proxy connects to the bridge IP).
    """
    if IS_TESTING:
        return
    loopback = {"127.0.0.1", "localhost", "::1", "[::1]"}
    if not exposed:
        # Loopback-only publish (the compose default): allowed with or
        # without proxy auth; warn when a public-facing proxy setup is
        # half-configured so the operator notices.
        if PROXY_AUTH_ENABLED and not PROXY_AUTH_ALLOWED_USERS:
            logger.warning(
                "PROXY_AUTH_ENABLED=true but PROXY_AUTH_ALLOWED_USERS is empty: "
                "every authenticated proxy user is treated as the same single "
                "clinic account."
            )
        return

    # Explicit intent to be reachable from other hosts (host networking or a
    # non-loopback port mapping): authentication is mandatory.
    if host.strip().lower() not in loopback and not PROXY_AUTH_ENABLED:
        raise RuntimeError(
            "Refusing to start: PHLOX_EXPOSE_PUBLIC=1 (non-loopback API) requires "
            "PROXY_AUTH_ENABLED=true. Set PROXY_AUTH_ENABLED=true and "
            "PROXY_AUTH_ALLOWED_USERS, or keep the loopback-only publish."
        )
    if PROXY_AUTH_ENABLED and not PROXY_AUTH_ALLOWED_USERS:
        logger.warning(
            "Exposed deployment with PROXY_AUTH_ENABLED=true but no "
            "PROXY_AUTH_ALLOWED_USERS: every authenticated proxy user is treated as "
            "the same single clinic account."
        )


if __name__ == "__main__":
    if not IS_DOCKER:
        # Desktop mode - dynamic port, single worker
        start_server_for_desktop()
    else:
        # Docker mode
        docker_host = os.getenv("SERVER_HOST", "0.0.0.0")
        _enforce_docker_network_policy(
            docker_host,
            exposed=os.getenv("PHLOX_EXPOSE_PUBLIC") == "1",
        )
        config = uvicorn.Config(
            app,
            host=docker_host,
            port=int(os.getenv("PORT", 5000)),
            timeout_keep_alive=300,
            timeout_graceful_shutdown=10,
            loop="asyncio",
            workers=1,
            http="httptools",
            ws_ping_interval=None,
            ws_ping_timeout=None,
            # Same secret-in-logs rationale as desktop: uvicorn access logs
            # include query strings.
            access_log=False,
        )
        server = uvicorn.Server(config)
        server.run()
