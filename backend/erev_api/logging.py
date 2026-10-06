"""Structured logging LOG (docs/dev-guide.md §6.6; docs/05-ARCHITECTURE.md OPR-20, OPR-21, SAR-19).

structlog renders one JSON line per event. The standard ``logging`` module is bridged through the
same processors, so third-party records get the same fields and the same hygiene (DG-LOG-06).
"""

from __future__ import annotations

import logging
import re
import sys
import traceback
from collections.abc import Iterable, Mapping
from typing import Final, Literal, TextIO

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

# OPR-20 fields, plus the DG-LOG-04 request method and the DG-LOG-05 stack trace.
STANDARD_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "ts",
        "level",
        "logger",
        "event",
        "request_id",
        "trace_id",
        "span_id",
        "tenant_id",
        "principal_kind",
        "principal_id",
        "job_id",
        "job_kind",
        "route",
        "status",
        "duration_ms",
        "db_statements",
        "engine_version",
        "component",
        "method",
        "exception",
    }
)
# Fields every line carries, null when unknown (DG-LOG-01).
DEFAULT_FIELDS: Final[tuple[str, ...]] = ("request_id", "tenant_id", "principal_kind", "job_id")
# Event-specific ids, codes, counts and durations are allowed (DG-LOG-01, DG-LOG-03).
_EVENT_FIELD = re.compile(r"^[a-z][a-z0-9_]*_(id|ids|code|codes|count|ms)$|^count$")
# Keys never logged, whatever the allow-list says (DG-LOG-07; SAR-19).
FORBIDDEN_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "email",
        "display_name",
        "name",
        "phone",
        "ip",
        "source_ip",
        "user_agent",
        "amount",
        "price",
        "password",
        "token",
        "secret",
        "prompt",
        "response_text",
    }
)
_SECRET_KEY = re.compile(r"(?i)(password|secret|token|api_key|authorization|cookie)")
# A quoted value is redacted to its closing quote, an unquoted one to the end of its line (D-78).
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|secret|token|api_key|authorization|cookie)\b([\"']?\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|\"[^\n]*|'[^']*'|'[^\n]*|[^\n]*)"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_PROCESSOR_META: Final = frozenset({"_record", "_from_structlog"})
MAX_STRING_LENGTH: Final = 2000
# DG-LOG-05 stack traces keep up to this many trailing characters.
MAX_TRACE_LENGTH: Final = 8000
REDACTED: Final = "[REDACTED]"
MESSAGE_HIDDEN: Final = "[message hidden]"
_HANDLER_NAME: Final = "erev-structlog"
# HTTP clients log full request URLs, and uvicorn access records hold the client address and raw
# query string (DG-LOG-03); the api writes its own http.request line instead (DG-LOG-04).
QUIET_LOGGERS: Final[tuple[str, ...]] = ("httpx", "httpcore", "uvicorn.access")
# uvicorn installs its own handlers and stops propagation (DG-LOG-06; D-78).
UVICORN_LOGGERS: Final[tuple[str, ...]] = ("uvicorn", "uvicorn.error", "uvicorn.access")
# The first line of a formatted stack trace (``traceback.format_exc``), as uvicorn logs one.
# The import packages of this code base: a frame of theirs is a place ``raised_at`` may name.
OWN_PACKAGES: Final[tuple[str, ...]] = ("erev_api", "erev_engine")
_TRACE_PREFIX: Final = "Traceback (most recent call last):"
_CAUSE: Final = "\nThe above exception was the direct cause of the following exception:\n\n"
_CONTEXT: Final = "\nDuring handling of the above exception, another exception occurred:\n\n"

_logger_fields: dict[str, frozenset[str]] = {}


def register_logger_fields(logger_name: str, fields: Iterable[str]) -> None:
    """Extend the allow-list for one logger and its children (OPR-21 per-logger extension)."""
    _logger_fields[logger_name] = _logger_fields.get(logger_name, frozenset()) | frozenset(fields)


def _extension_fields(logger_name: object) -> frozenset[str]:
    if not isinstance(logger_name, str):
        return frozenset()
    extra: frozenset[str] = frozenset()
    for registered, fields in _logger_fields.items():
        if logger_name == registered or logger_name.startswith(registered + "."):
            extra |= fields
    return extra


def _redact(text: str) -> str:
    text = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return _EMAIL.sub(REDACTED, text)


def _scrub_trace(value: object) -> object:
    """DG-LOG-05: a stack trace keeps its last lines, which name the exception and raise site."""
    if not isinstance(value, str):
        return _scrub(value)
    text = _redact(value)
    return text if len(text) <= MAX_TRACE_LENGTH else "[truncated]" + text[-MAX_TRACE_LENGTH:]


def _chain(exc: BaseException) -> list[BaseException]:
    """``exc`` and what it was raised from, the outermost first: the explicit cause, else the
    context unless it is suppressed."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and all(current is not seen for seen in chain):
        chain.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
        else:
            current = None if current.__suppress_context__ else current.__context__
    return chain


def raised_at(exc: BaseException) -> str | None:
    """Where ``exc`` was raised, for an event that carries neither its message nor its trace: the
    module and line of the last frame of this code base, as ``erev_api.domain.x:123``.

    The chain is read from its origin, so a problem raised from a database error names the place
    of the statement, not of the mapper. None when no frame of the chain is this code base's. No
    value and no message can be in it (DG-LOG-03).
    """
    for item in reversed(_chain(exc)):
        place: str | None = None
        for frame, line in traceback.walk_tb(item.__traceback__):
            module = frame.f_globals.get("__name__")
            if isinstance(module, str) and module.split(".")[0] in OWN_PACKAGES:
                place = f"{module}:{line}"
        if place is not None:
            return place
    return None


def trace_without_messages(exc: BaseException) -> str:
    """The stack trace of ``exc`` and its chain: frames and classes, no messages or source lines.

    Database driver messages can quote bound values, for example ``invalid input syntax for type
    numeric``, so database errors are logged through this form (DG-LOG-03, DG-LOG-05; D-78).
    """
    chain = _chain(exc)
    parts: list[str] = []
    for index in range(len(chain) - 1, -1, -1):
        item = chain[index]
        if index < len(chain) - 1:
            parts.append(_CAUSE if item.__cause__ is not None else _CONTEXT)
        parts.append("Traceback (most recent call last):\n")
        frames = traceback.StackSummary.extract(
            traceback.walk_tb(item.__traceback__), lookup_lines=False
        )
        parts.extend(f'  File "{f.filename}", line {f.lineno}, in {f.name}\n' for f in frames)
        kind = type(item)
        name = kind.__qualname__
        if kind.__module__ != "builtins":
            name = f"{kind.__module__}.{name}"
        parts.append(f"{name}: {MESSAGE_HIDDEN}\n")
    return "".join(parts)


def _forbidden_key(key: object) -> bool:
    text = str(key)
    return text in FORBIDDEN_FIELDS or bool(_SECRET_KEY.search(text))


def _scrub(value: object) -> object:
    if isinstance(value, str):
        text = _redact(value)
        return text if len(text) <= MAX_STRING_LENGTH else text[:MAX_STRING_LENGTH] + "[truncated]"
    if isinstance(value, Mapping):
        # Forbidden and SAR-19 keys are dropped at every depth (D-78).
        return {key: _scrub(item) for key, item in value.items() if not _forbidden_key(key)}
    if isinstance(value, list | tuple):
        return [_scrub(item) for item in value]
    return value


def _scrub_event(value: object) -> object:
    """OPR-21 for the message itself. A stack trace logged as the message keeps its trailing
    characters, which name the exception and its reason (DG-LOG-05), instead of its first frames:
    uvicorn logs a failed lifespan startup that way, and the head-first cut of every other string
    removed the one line an operator needs (``ReleaseManifestError: …``, a refused key provider,
    an unreachable database). Every other message keeps its beginning."""
    if isinstance(value, str) and value.startswith(_TRACE_PREFIX):
        text = _redact(value)
        return text if len(text) <= MAX_STRING_LENGTH else "[truncated]" + text[-MAX_STRING_LENGTH:]
    return _scrub(value)


def _allowed(key: str, extension: frozenset[str]) -> bool:
    if key in _PROCESSOR_META:
        return True
    if _forbidden_key(key):
        return False
    return key in STANDARD_FIELDS or key in extension or bool(_EVENT_FIELD.match(key))


def log_hygiene(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """OPR-21: drop keys outside the allow-list, apply SAR-19 redaction, truncate long strings."""
    extension = _extension_fields(event_dict.get("logger"))
    return {
        key: value
        if key in _PROCESSOR_META
        else _scrub_trace(value)
        if key == "exception"
        else _scrub_event(value)
        if key == "event"
        else _scrub(value)
        for key, value in event_dict.items()
        if _allowed(key, extension)
    }


def _default_fields(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    for key in DEFAULT_FIELDS:
        event_dict.setdefault(key, None)
    return event_dict


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        structlog.processors.format_exc_info,
        _default_fields,
        log_hygiene,
    ]


def configure_logging(
    *,
    level: str = "INFO",
    fmt: Literal["json", "console"] = "json",
    stream: TextIO | None = None,
) -> None:
    """Install the process logging pipeline; composition roots pass the CFG-22 settings."""
    shared = _shared_processors()
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    root = logging.getLogger()
    for existing in list(root.handlers):
        if existing.get_name() == _HANDLER_NAME:
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())
    for name in UVICORN_LOGGERS:
        bridged = logging.getLogger(name)
        for existing in list(bridged.handlers):
            bridged.removeHandler(existing)
        bridged.propagate = True
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """A named logger; event names follow ``<area>.<event>`` (DG-LOG-02)."""
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger
