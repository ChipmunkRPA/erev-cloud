"""Personal-data guard for captured log events (docs/dev-guide.md DG-LOG-07).

The guard taps structlog before any processor runs, so it sees what code tried to log, not what
the hygiene processor let through. Failure messages name keys only, never values.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Final

import structlog
from structlog.typing import EventDict, WrappedLogger

FORBIDDEN_KEYS: Final[frozenset[str]] = frozenset(
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
EMAIL: Final = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


def _holds_email(value: object) -> bool:
    if isinstance(value, str):
        return bool(EMAIL.search(value))
    if isinstance(value, Mapping):
        return any(_holds_email(item) for item in value.values())
    if isinstance(value, list | tuple | set | frozenset):
        return any(_holds_email(item) for item in value)
    return False


def _nested_forbidden_keys(value: object, path: str) -> Iterator[str]:
    """Paths of forbidden keys inside mappings and sequences, at any depth (D-78)."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}"
            if key in FORBIDDEN_KEYS:
                yield child
            yield from _nested_forbidden_keys(item, child)
    elif isinstance(value, list | tuple | set | frozenset):
        for index, item in enumerate(value):
            yield from _nested_forbidden_keys(item, f"{path}[{index}]")


def check(events: Iterable[Mapping[str, object]]) -> None:
    """Raise ``AssertionError`` for a forbidden key at any depth or an email-shaped value."""
    problems: list[str] = []
    for index, event in enumerate(events):
        for key, value in event.items():
            if key in FORBIDDEN_KEYS:
                problems.append(f"event {index}: forbidden key {key!r}")
            elif _holds_email(value):
                problems.append(f"event {index}: key {key!r} holds an email address")
            problems.extend(
                f"event {index}: forbidden key {path!r}"
                for path in _nested_forbidden_keys(value, str(key))
            )
    if problems:
        raise AssertionError("personal data in logs (DG-LOG-07): " + "; ".join(problems))


class _RecordTap(logging.Handler):
    def __init__(self, events: list[dict[str, object]]) -> None:
        super().__init__(level=logging.NOTSET)
        self._events = events

    def emit(self, record: logging.LogRecord) -> None:
        if isinstance(record.msg, dict):  # already seen by the structlog tap
            return
        self._events.append({"event": record.getMessage(), "logger": record.name})


@contextmanager
def capture() -> Iterator[list[dict[str, object]]]:
    """Collect structlog events and standard-library records emitted inside the block."""
    events: list[dict[str, object]] = []
    saved = structlog.get_config()
    processors = list(saved["processors"])

    def tap(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        events.append(dict(event_dict))
        return event_dict

    structlog.configure(processors=[tap, *processors])
    handler = _RecordTap(events)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield events
    finally:
        root.removeHandler(handler)
        structlog.configure(
            processors=processors,
            context_class=saved["context_class"],
            wrapper_class=saved["wrapper_class"],
            logger_factory=saved["logger_factory"],
            cache_logger_on_first_use=saved["cache_logger_on_first_use"],
        )
