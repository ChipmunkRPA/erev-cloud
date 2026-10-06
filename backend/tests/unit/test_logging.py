"""Structured logging contract (dev-guide §6.6; 05 OPR-20, OPR-21, SAR-19; BUILD_SPEC FND-2)."""

from __future__ import annotations

import inspect
import io
import json
import logging
import logging.config
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfoNotFoundError

import pytest
import structlog
import uvicorn.config
from erev_api import clock as clock_module
from erev_api.logging import (
    OWN_PACKAGES,
    configure_logging,
    get_logger,
    raised_at,
    register_logger_fields,
)
from support import log_guard

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    """Install a fresh JSON pipeline writing to a buffer, then restore the previous one.

    The fresh pipeline replaces the DG-LOG-07 guard's tap for the duration of the test, so these
    tests may emit forbidden values deliberately to prove the hygiene processor removes them.
    """
    saved = structlog.get_config()
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    root.handlers[:] = []
    stream = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=stream)
    try:
        yield stream
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        structlog.configure(
            processors=list(saved["processors"]),
            context_class=saved["context_class"],
            wrapper_class=saved["wrapper_class"],
            logger_factory=saved["logger_factory"],
            cache_logger_on_first_use=saved["cache_logger_on_first_use"],
        )


@pytest.fixture
def uvicorn_loggers() -> Iterator[None]:
    """Restore the handlers, propagation and level of the uvicorn loggers after the test."""
    saved = {}
    for name in UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        saved[name] = (list(logger.handlers), logger.propagate, logger.level)
    try:
        yield
    finally:
        for name, (handlers, propagate, level) in saved.items():
            logger = logging.getLogger(name)
            logger.handlers[:] = handlers
            logger.propagate = propagate
            logger.setLevel(level)


def _lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def test_dg_log_01_json_fields(log_stream: io.StringIO) -> None:
    get_logger("erev_api.test").info("http.request", route="/api/v1/healthz", duration_ms=3)
    (line,) = _lines(log_stream)
    assert {"ts", "level", "event", "logger", "request_id"} <= line.keys()
    assert line["event"] == "http.request"
    assert line["level"] == "info"
    assert line["logger"] == "erev_api.test"
    assert line["request_id"] is None
    ts = str(line["ts"])
    assert ts.endswith("Z")
    assert datetime.fromisoformat(ts).utcoffset() == timedelta(0)


def test_dg_log_03_forbidden_keys_removed(log_stream: io.StringIO) -> None:
    get_logger("erev_api.test").info(
        "contract.computed", email="maya@demo.erev", amount="146000.00", contract_id="c-1"
    )
    output = log_stream.getvalue()
    assert "maya@demo.erev" not in output
    assert "146000.00" not in output
    (line,) = _lines(log_stream)
    assert line["contract_id"] == "c-1"


def test_sar_19_secret_keys_dropped_and_messages_redacted(log_stream: io.StringIO) -> None:
    logger = get_logger("erev_api.test")
    logger.warning("auth.failed password=hunter2hunter2 for maya@demo.erev", api_key_id="k-1")
    logger.info("import.row_rejected", error_code="E-1", detail_text="x" * 3000)
    first, second = _lines(log_stream)
    assert "api_key_id" not in first
    event = str(first["event"])
    assert "hunter2hunter2" not in event and "maya@demo.erev" not in event
    assert "detail_text" not in second and second["error_code"] == "E-1"


def test_sar_19_nested_secret_keys_dropped(log_stream: io.StringIO) -> None:
    logger = get_logger("erev_api.test")
    logger.info("import.rejected", error_codes={"password": "p-123456", "cookie": "c-123456"})
    logger.info("import.rejected", error_codes=[{"api_key": "k-123456", "row_count": 2}])
    logger.warning('auth.failed password="alpha bravo charlie" retry')
    logger.warning("auth.failed token: alpha bravo\nnext line")
    output = log_stream.getvalue()
    for value in ("p-123456", "c-123456", "k-123456", "alpha", "bravo", "charlie"):
        assert value not in output
    first, second, third, fourth = _lines(log_stream)
    assert first["error_codes"] == {}
    assert second["error_codes"] == [{"row_count": 2}]
    assert third["event"] == "auth.failed password=[REDACTED] retry"
    assert fourth["event"] == "auth.failed token: [REDACTED]\nnext line"

    with pytest.raises(AssertionError) as excinfo:
        log_guard.check([{"event": "x", "error_codes": {"password": "v"}}])
    assert "error_codes.password" in str(excinfo.value)
    with pytest.raises(AssertionError):
        log_guard.check([{"event": "x", "rows": [{"detail": {"email": "v"}}]}])


def test_dg_log_06_uvicorn_records_bridged(log_stream: io.StringIO, uvicorn_loggers: None) -> None:
    logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)
    buf = io.StringIO()
    configure_logging(stream=buf)
    for name in UVICORN_LOGGERS:
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate is True

    logging.getLogger("uvicorn.error").info("Started server process [1]")
    (line,) = _lines(buf)
    assert line["logger"] == "uvicorn.error"
    assert line["event"] == "Started server process [1]"

    logging.getLogger("uvicorn.error").error(
        "Exception in ASGI application password=vhunter2-probe"
    )
    assert "vhunter2-probe" not in buf.getvalue()
    assert len(_lines(buf)) == 2
    # Access records hold the client address and raw query string (DG-LOG-03).
    logging.getLogger("uvicorn.access").info('127.0.0.1:1 - "GET /x?q=marker HTTP/1.1" 200')
    assert "marker" not in buf.getvalue()


def test_opr_21_logger_extension_and_truncation(log_stream: io.StringIO) -> None:
    register_logger_fields("erev_api.test_extension", ["detail_text"])
    get_logger("erev_api.test_extension.child").info("import.row_rejected", detail_text="y" * 3000)
    (line,) = _lines(log_stream)
    assert str(line["detail_text"]).startswith("y" * 2000)
    assert len(str(line["detail_text"])) < 2100


def test_dg_log_05_a_startup_trace_logged_as_the_message_keeps_its_last_lines(
    log_stream: io.StringIO,
) -> None:
    # Lane OPS, runtime fact 2 (2026-09-29): uvicorn logs a failed lifespan startup as the formatted
    # stack trace itself (the message, no exc_info), and the head-first cut at 2,000 characters
    # removed its last line: a production api refused a mismatching release manifest with exit 3
    # and a log that never said why. A trace message keeps its trailing characters instead.
    frames = "".join(
        f'  File "/app/.venv/lib/python3.12/site-packages/pkg/module_{n}.py", line {n}, in call\n'
        f"    return await step_{n}(application)\n"
        for n in range(40)
    )
    reason = (
        "erev_api.controls.release.ReleaseManifestError: "
        "the release manifest names another engine version"
    )
    trace = f"Traceback (most recent call last):\n{frames}{reason}\n"
    assert len(trace) > 4000
    logging.getLogger("uvicorn.error").error(trace)
    (line,) = _lines(log_stream)
    event = str(line["event"])
    assert event.startswith("[truncated]") and event.rstrip().endswith(reason)
    assert len(event) == len("[truncated]") + 2000  # OPR-21: still cut at 2,000 characters
    assert "module_0.py" not in event and "module_39.py" in event  # the first frames go
    # SAR-19 redaction still applies to the part that is kept
    log_stream.seek(0)
    log_stream.truncate()
    secret_line = "RuntimeError: connect failed password=vhunter2-probe for maya@demo.erev"
    logging.getLogger("uvicorn.error").error(
        f"Traceback (most recent call last):\n{frames}{secret_line}\n"
    )
    (line,) = _lines(log_stream)
    assert "vhunter2-probe" not in log_stream.getvalue()
    assert "maya@demo.erev" not in log_stream.getvalue()
    assert "RuntimeError: connect failed" in str(line["event"])
    # a short trace is logged whole, and any other long message still keeps its beginning
    log_stream.seek(0)
    log_stream.truncate()
    short = f'Traceback (most recent call last):\n  File "x.py", line 1, in f\n{reason}\n'
    logging.getLogger("uvicorn.error").error(short)
    logging.getLogger("uvicorn.error").error("y" * 3000)
    whole, other = _lines(log_stream)
    assert whole["event"] == short
    assert str(other["event"]) == "y" * 2000 + "[truncated]"


def test_dg_log_06_standard_library_bridge(log_stream: io.StringIO) -> None:
    logging.getLogger("uvicorn.error").warning("worker contact maya@demo.erev failed")
    (line,) = _lines(log_stream)
    assert line["logger"] == "uvicorn.error"
    assert line["level"] == "warning"
    assert "maya@demo.erev" not in log_stream.getvalue()


def test_dg_log_07_guard_detects_email_value() -> None:
    with pytest.raises(AssertionError) as excinfo:
        log_guard.check([{"event": "x", "note": "maya@demo.erev"}])
    assert "maya@demo.erev" not in str(excinfo.value)
    with pytest.raises(AssertionError):
        log_guard.check([{"event": "x", "amount": "1.00"}])
    log_guard.check([{"event": "contract.computed", "contract_id": "c-1"}])


def test_dg_log_07_guard_captures_emitted_events() -> None:
    with log_guard.capture() as events:
        structlog.get_logger("erev_api.test").info("contract.computed", contract_id="c-1")
        logging.getLogger("erev_api.test").error("plain record")
    assert {"event": "contract.computed", "contract_id": "c-1"}.items() <= events[0].items()
    assert events[1] == {"event": "plain record", "logger": "erev_api.test"}


def _zone_line() -> int:
    """The line of ``clock.to_entity_date`` that asks the zone database."""
    lines, first = inspect.getsourcelines(clock_module.to_entity_date)
    (offset,) = [index for index, line in enumerate(lines) if "ZoneInfo(tz_name)" in line]
    return first + offset


def _unknown_zone() -> None:
    clock_module.to_entity_date(datetime(2026, 10, 1, tzinfo=UTC), "Mars/Olympus_Mons")


def test_dg_log_03_raised_at_names_the_last_frame_of_this_code_base() -> None:
    """DG-LOG-03 rev 1.183 (supervisor ruling of 2026-10-01 on R-118 (k)): an event that carries
    neither the message nor the trace of an exception names where it was raised - the module and
    line of the last frame of this code base - and nothing of the exception's values."""
    assert OWN_PACKAGES == ("erev_api", "erev_engine")
    here = f"erev_api.clock:{_zone_line()}"
    with pytest.raises(ZoneInfoNotFoundError) as caught:
        _unknown_zone()
    assert raised_at(caught.value) == here
    assert "Olympus" in str(caught.value) and "Olympus" not in here
    # No frame of this code base: an exception that was never raised, and one raised here.
    assert raised_at(RuntimeError("never raised")) is None
    with pytest.raises(RuntimeError) as only_here:
        raise RuntimeError("raised in a test module")
    assert raised_at(only_here.value) is None


def test_dg_log_03_raised_at_reads_the_chain_from_its_origin() -> None:
    """A problem a mapper raises from a database error names the place of the statement, not of
    the mapper: the chain is read from its origin, and the first exception that has a frame of
    this code base gives the place."""
    here = f"erev_api.clock:{_zone_line()}"
    # Raised from an error of this code base, in a module that is not: the origin's place.
    with pytest.raises(RuntimeError) as mapped:
        try:
            _unknown_zone()
        except Exception as error:
            raise RuntimeError("a mapper's answer") from error
    assert raised_at(mapped.value) == here
    # The origin has no frame of this code base: the place of the error raised while handling it.
    with pytest.raises(ZoneInfoNotFoundError) as handled:
        try:
            raise ValueError("a value 4111 1111 1111 1111")
        except ValueError:
            _unknown_zone()
    origin: BaseException = handled.value
    while origin.__context__ is not None:  # the zone database raises from an error of its own
        origin = origin.__context__
    assert isinstance(origin, ValueError)
    assert raised_at(handled.value) == here
    # A context that was suppressed is no part of the chain.
    with pytest.raises(RuntimeError) as suppressed:
        try:
            _unknown_zone()
        except Exception:
            raise RuntimeError("raised here") from None
    assert raised_at(suppressed.value) is None
