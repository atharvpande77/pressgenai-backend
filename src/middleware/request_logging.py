from __future__ import annotations

import logging
import time
from uuid import uuid4
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.config.logging import (
    reset_request_context,
    set_request_context,
    update_request_context,
)


logger = logging.getLogger('pressgenai.request')


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get('X-Request-ID') or str(uuid4())
        token = set_request_context(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        except Exception:
            logger.exception('Unhandled request failure', extra={'event': 'request.exception'})
            raise
        finally:
            duration = (time.perf_counter() - start) * 1000
            status_code = response.status_code if response else 500
            update_request_context(status_code=status_code, duration_ms=duration)
            logger.info('Request completed', extra={'event': 'request.completed'})
            if response is not None:
                response.headers.setdefault('X-Request-ID', request_id)
            reset_request_context(token)
