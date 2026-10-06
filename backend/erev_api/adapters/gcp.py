"""Google Cloud client error classification shared by the hosted adapters (05 SAR-21, CMP-05).

The client libraries raise ``google.api_core.exceptions`` subclasses. The adapters never import
that package (they are exercised with fakes, DG-KRN-FILE-05, DG-ENV-17) and classify an error by
the class names in its MRO and its HTTP ``code``. Every message built here names resource names
and error kinds only, never payloads.
"""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from typing import Any, Final, Literal

from erev_api.logging import get_logger, register_logger_fields

ClientKind = Literal["storage", "kms", "secretmanager"]
ErrorKind = Literal[
    "not_found", "precondition_failed", "already_exists", "denied", "transient", "other"
]

_KINDS: Final[dict[str, ErrorKind]] = {
    "NotFound": "not_found",
    "PreconditionFailed": "precondition_failed",
    "AlreadyExists": "already_exists",
    "Conflict": "already_exists",
    "PermissionDenied": "denied",
    "Forbidden": "denied",
    "Unauthenticated": "denied",
    "Unauthorized": "denied",
    "ServiceUnavailable": "transient",
    "InternalServerError": "transient",
    "TooManyRequests": "transient",
    "ResourceExhausted": "transient",
    "DeadlineExceeded": "transient",
    "GatewayTimeout": "transient",
    "BadGateway": "transient",
    "Aborted": "transient",
    "RetryError": "transient",
    "ConnectionError": "transient",
    "TimeoutError": "transient",
}
_CODES: Final[dict[int, ErrorKind]] = {
    404: "not_found",
    412: "precondition_failed",
    409: "already_exists",
    401: "denied",
    403: "denied",
    429: "transient",
    500: "transient",
    502: "transient",
    503: "transient",
    504: "transient",
}
# Bounded backoff for transient failures, seconds; the precondition never changes between tries.
RETRY_DELAYS: Final[tuple[float, ...]] = (0.2, 0.5, 1.0)
_LOGGER: Final = "erev_api.adapters.gcp"
Sleep = Callable[[float], None]

register_logger_fields(_LOGGER, ("operation", "resource", "attempt"))


def error_kind(exc: BaseException) -> ErrorKind:
    """Classify a client exception without importing the client library."""
    for klass in type(exc).__mro__:
        kind = _KINDS.get(klass.__name__)
        if kind is not None:
            return kind
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code in _CODES:
        return _CODES[code]
    return "other"


def make_client(kind: ClientKind) -> Any:
    """Construct a Google client from the ``gcp`` extra with the process identity (ADC).

    The one place the client libraries are imported; tests replace this function, so no test ever
    constructs a real client or reaches the network (DG-ENV-17, DG-KRN-FILE-05).
    """
    if kind == "storage":
        return importlib.import_module("google.cloud.storage").Client()
    if kind == "kms":
        return importlib.import_module("google.cloud.kms").KeyManagementServiceClient()
    return importlib.import_module("google.cloud.secretmanager").SecretManagerServiceClient()


class GcpError(RuntimeError):
    """A hosted provider call failed; ``kind`` classifies it and the message holds no payload."""

    def __init__(self, kind: ErrorKind, operation: str, resource: str, cause: BaseException):
        super().__init__(f"{operation} on {resource} failed: {kind} ({type(cause).__name__})")
        self.kind = kind
        self.operation = operation
        self.resource = resource


def call_with_retry(
    operation: str, resource: str, call: Callable[[], Any], *, sleep: Sleep = time.sleep
) -> Any:
    """Run one client call; transient failures are retried with the same arguments (and so the
    same preconditions) and bounded backoff, every other failure raises ``GcpError`` classified by
    kind. A lost success followed by a 412 on retry reaches the caller as ``precondition_failed``,
    which then verifies the winner instead of declaring loss (contract §"Retry strategy")."""
    for attempt, delay in enumerate((*RETRY_DELAYS, None), start=1):
        try:
            return call()
        except Exception as exc:
            kind = error_kind(exc)
            if kind == "transient" and delay is not None:
                get_logger(_LOGGER).warning(
                    "gcp.retry",
                    operation=operation,
                    resource=resource,
                    attempt=attempt,
                    error_code=type(exc).__name__,
                )
                sleep(delay)
                continue
            raise GcpError(kind, operation, resource, exc) from None
    raise AssertionError("unreachable: the last attempt raises or returns")
