"""Structured logging, Sentry, request IDs, and the last-resort error handler.

Wired by `init_observability(app)` in `api/index.py`, immediately after the
FastAPI app is constructed. Three concerns, one entry point:

1. **Logging** — one `basicConfig` for the whole backend (there was none before;
   only `api/instrumentation/services/usage.py` held a logger).
2. **Sentry** — enabled only when `SENTRY_DSN` is set, so local/dev is a no-op.
   `sentry_sdk` is imported lazily inside that branch: the package being absent
   must never stop the app from booting.
3. **Request correlation** — every response carries `X-Request-ID` (echoed from
   the caller when supplied), and any unhandled exception is logged against that
   id and answered with an opaque 500. Tracebacks never reach the client.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.config import settings

logger = logging.getLogger("guildos")

REQUEST_ID_HEADER = "X-Request-ID"

# Set by the middleware so log records emitted anywhere in the request (services,
# db helpers) can be correlated without threading the id through every call.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

# `init_observability` runs at import time, and uvicorn --reload / pytest can
# import the module more than once per process.
_logging_configured = False
_sentry_configured = False


def current_request_id() -> str:
    """The in-flight request's id, or "-" outside a request."""
    return request_id_ctx.get()


def _configure_logging() -> None:
    global _logging_configured
    if _logging_configured:
        return
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)
    _logging_configured = True


def _configure_sentry() -> None:
    global _sentry_configured
    if _sentry_configured or not settings.SENTRY_DSN:
        return
    try:
        import sentry_sdk  # imported lazily: a missing package must not break boot
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed — skipping Sentry")
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.VERCEL_ENV or "local",
        # Errors only for now; tracing is a separate cost decision.
        traces_sample_rate=0,
    )
    _sentry_configured = True


def init_observability(app: FastAPI) -> None:
    """Attach logging, Sentry, request IDs and the catch-all error handler."""
    _configure_logging()
    _configure_sentry()

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        request_id_ctx.set(rid)
        # Also on the ASGI scope, which the exception handler below can read even
        # though it runs *outside* this middleware (see the handler's note).
        request.state.request_id = rid
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Log the failure with its request id; return an opaque 500.

        Starlette installs this on `ServerErrorMiddleware`, which is the
        *outermost* layer — so the request-id middleware's header assignment
        never runs for this path and the header is set here instead. `request_id`
        comes off the shared ASGI scope state, with the contextvar as fallback.

        `HTTPException` is resolved further in by `ExceptionMiddleware` and never
        reaches this handler, so 4xx responses are unchanged.
        """
        rid = getattr(request.state, "request_id", None) or request_id_ctx.get()
        logger.exception(
            "Unhandled exception [request_id=%s] %s %s",
            rid,
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": rid},
            headers={REQUEST_ID_HEADER: rid},
        )
