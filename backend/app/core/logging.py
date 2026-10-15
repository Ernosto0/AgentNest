"""structlog setup: JSON in production, console in development (ADR-017, ADR-018).

Never logged: tokens, secrets, cookies, authorization headers, passwords, message text.
The redaction processor below is a safety net, not the primary control.
"""

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, unbind_contextvars
from structlog.typing import EventDict, Processor

from app.core.config import Settings

REDACTED = "[REDACTED]"

# ``code`` is redacted only as an exact key (OAuth ``code``); ``error_code`` stays visible.
# ``token`` does not match the plural ``tokens`` (usage counters).
_SENSITIVE_KEY = re.compile(
    r"token(?!s)|secret|password|passwd|authorization|cookie|api[_-]?key", re.I
)
_BEARER = re.compile(r"^\s*(bearer|basic)\s+\S+", re.I)


def _is_sensitive_key(key: str) -> bool:
    return key.lower() == "code" or bool(_SENSITIVE_KEY.search(key))


def _mask(key: object, value: Any) -> Any:
    """Mask the value of a sensitive key. Booleans and None cannot carry a secret, so
    flags such as ``cookie_secure=True`` stay readable in startup diagnostics."""
    if (
        isinstance(key, str)
        and _is_sensitive_key(key)
        and not (value is None or isinstance(value, bool))
    ):
        return REDACTED
    return _redact(value)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _mask(k, v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    if isinstance(value, str) and _BEARER.match(value):
        return REDACTED
    return value


def redact_processor(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key != "event":
            event_dict[key] = _mask(key, event_dict[key])
    return event_dict


def _env_processor(env: str) -> Processor:
    def add_env(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
        event_dict["env"] = env
        return event_dict

    return add_env


def configure_logging(settings: Settings) -> None:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        _env_processor(settings.app_env),
        redact_processor,
    ]
    renderer: Processor
    final: list[Processor]
    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
        final = [structlog.processors.format_exc_info, renderer]
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        final = [renderer]

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *final],
    )
    handler = logging.StreamHandler(sys.stderr)  # stdout stays free for machine-readable output
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # The request middleware logs one line per request, so uvicorn's access log is redundant.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def bind_context(**values: Any) -> None:
    bind_contextvars(**values)


def unbind_context(*keys: str) -> None:
    unbind_contextvars(*keys)


def clear_context() -> None:
    clear_contextvars()
