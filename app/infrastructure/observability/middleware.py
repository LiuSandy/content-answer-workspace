from __future__ import annotations

import logging
import re
import time
import uuid

from .context import bind_log_context

logger = logging.getLogger(__name__)
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        incoming = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = incoming if _REQUEST_ID.fullmatch(incoming) else f"req_{uuid.uuid4().hex}"
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        with bind_log_context(request_id=request_id):
            logger.info("request.started", extra={"method": scope["method"], "path": scope["path"]})
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception:
                logger.exception("request.failed", extra={"method": scope["method"], "path": scope["path"]})
                raise
            finally:
                logger.info(
                    "request.completed",
                    extra={
                        "method": scope["method"], "path": scope["path"],
                        "status_code": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    },
                )
