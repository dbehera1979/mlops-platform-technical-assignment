import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.logging_conf import correlation_id_var, get_logger, log_event

logger = get_logger("app.request")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Accepts an inbound X-Correlation-Id (set by the Angular client) or
    generates one, makes it available to every log line for the duration
    of the request via a contextvar, and echoes it back on the response."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        token = correlation_id_var.set(correlation_id)
        try:
            log_event(
                logger,
                "request.start",
                outcome="in_progress",
                method=request.method,
                path=request.url.path,
            )
            response = await call_next(request)
            response.headers["X-Correlation-Id"] = correlation_id
            log_event(
                logger,
                "request.complete",
                outcome=str(response.status_code),
                method=request.method,
                path=request.url.path,
            )
            return response
        finally:
            correlation_id_var.reset(token)
