from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime
from typing import Any

from src.config.settings import settings

REQUEST_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar('request_context', default=None)

STANDARD_RECORD_ATTRS = {
    'name',
    'msg',
    'args',
    'levelname',
    'levelno',
    'pathname',
    'filename',
    'module',
    'exc_info',
    'exc_text',
    'stack_info',
    'lineno',
    'funcName',
    'created',
    'msecs',
    'relativeCreated',
    'thread',
    'threadName',
    'process',
    'processName',
    'message',
    'event',
    'request_id',
    'path',
    'method',
    'status_code',
    'duration_ms',
}


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = REQUEST_CONTEXT.get() or {}
        for key in ('request_id', 'path', 'method', 'status_code', 'duration_ms'):
            setattr(record, key, context.get(key))
        return True


class StructuredJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            'timestamp': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'event': getattr(record, 'event', record.getMessage()),
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        for field in ('request_id', 'path', 'method', 'status_code', 'duration_ms'):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in STANDARD_RECORD_ATTRS
            and not key.startswith('__')
            and value is not None
        }

        if extras:
            payload['extra'] = extras

        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    formatter = StructuredJSONFormatter()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    access_logger = logging.getLogger('uvicorn.access')
    access_logger.handlers = []
    access_logger.propagate = settings.LOG_INCLUDE_UVICORN_ACCESS
    access_logger.setLevel(log_level)

    error_logger = logging.getLogger('uvicorn.error')
    error_logger.handlers = []
    error_logger.propagate = True
    error_logger.setLevel(log_level)


def set_request_context(**values: Any) -> Token:
    ctx: dict[str, Any] = dict(values)
    return REQUEST_CONTEXT.set(ctx)


def update_request_context(**values: Any) -> None:
    context = REQUEST_CONTEXT.get()
    if context is None:
        context = {}
        REQUEST_CONTEXT.set(context)
    context.update(values)


def reset_request_context(token: logging.Token) -> None:
    REQUEST_CONTEXT.reset(token)


def get_request_id() -> str | None:
    context = REQUEST_CONTEXT.get()
    return context.get('request_id') if context else None
