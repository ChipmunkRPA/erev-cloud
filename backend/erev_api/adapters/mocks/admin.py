"""Mock adapter administration (05 ADP-20 to ADP-22; dev-guide DG-API-09; D-72; BUILD_SPEC PLF-27).

``POST /api/v1/__mocks__/__admin/faults`` queues a fault for the next ``count`` requests to one mock
route, named by its path below ``/api/v1/__mocks__`` (for example ``/oidc/token``).
``POST /__admin/reset`` restores every mock to its seeded state and clears the queued faults, and
``GET /__admin/state`` reports both. The state lives on the application: one copy per api process.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

ADMIN_PREFIX: Final = "/__admin"
RATE_LIMIT_RETRY_SECONDS: Final = 1
MAX_FAULT_COUNT: Final = 1000


class FaultKind(StrEnum):
    """05 ADP-21 fault kinds."""

    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    RATE_LIMIT = "RATE_LIMIT"
    SERVER_ERROR = "SERVER_ERROR"
    TIMEOUT = "TIMEOUT"
    PERMANENT_ERROR = "PERMANENT_ERROR"
    # Rev 1.175 (item JRN-EXIT-SETTLE-1): the ledger accepts now and shows later. A journal
    # route whose adapter reads back what it posted stores the journal, answers as accepted and
    # leaves it out of its reads until released (the NetSuite mock); any other route handles the
    # request normally.
    READ_LAG = "READ_LAG"


# [J] SPEC-Q-192: the status each error fault answers with. DUPLICATE and OUT_OF_ORDER repeat or
# reorder the deliveries of event-emitting mocks; a request-response route handles them normally.
ERROR_STATUS: Final[Mapping[FaultKind, int]] = {
    FaultKind.RATE_LIMIT: 429,
    FaultKind.SERVER_ERROR: 500,
    FaultKind.TIMEOUT: 504,
    FaultKind.PERMANENT_ERROR: 400,
}


class MockAdapter(Protocol):
    """The state of one mock server."""

    def reset(self) -> None: ...

    def snapshot(self) -> dict[str, Any]: ...


@dataclass(slots=True)
class Fault:
    route: str
    kind: FaultKind
    remaining: int


class Faults:
    """Queued faults, oldest first; each applies to the next ``remaining`` requests to its route."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: list[Fault] = []

    def add(self, route: str, kind: FaultKind, count: int) -> None:
        with self._lock:
            self._queue.append(Fault(route=route, kind=kind, remaining=count))

    def take(self, route: str) -> FaultKind | None:
        """The kind of the oldest fault queued for ``route``, counting one use of it."""
        with self._lock:
            for fault in self._queue:
                if fault.route == route:
                    fault.remaining -= 1
                    if fault.remaining == 0:
                        self._queue.remove(fault)
                    return fault.kind
        return None

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"route": fault.route, "kind": fault.kind.value, "remaining": fault.remaining}
                for fault in self._queue
            ]


@dataclass(frozen=True, slots=True)
class MockWorld:
    """Every mounted mock by adapter code, and the fault queue they share (ADP-22)."""

    adapters: Mapping[str, MockAdapter]
    faults: Faults

    def reset(self) -> None:
        self.faults.clear()
        for adapter in self.adapters.values():
            adapter.reset()

    def snapshot(self) -> dict[str, Any]:
        return {
            "faults": self.faults.snapshot(),
            "adapters": {code: self.adapters[code].snapshot() for code in sorted(self.adapters)},
        }


def world_of(request: Request) -> MockWorld:
    world = request.app.state.mocks
    assert isinstance(world, MockWorld)
    return world


def error_response(kind: FaultKind | None) -> Response | None:
    """The response of an error fault of ``kind``; None for no fault and for a kind a
    request-response route handles normally (``DUPLICATE``, ``OUT_OF_ORDER``, ``READ_LAG``)."""
    status = None if kind is None else ERROR_STATUS.get(kind)
    if kind is None or status is None:
        return None
    headers = (
        {"Retry-After": str(RATE_LIMIT_RETRY_SECONDS)} if kind is FaultKind.RATE_LIMIT else None
    )
    return JSONResponse(
        {"error": "mock_fault", "kind": kind.value}, status_code=status, headers=headers
    )


def fault_response(request: Request, route: str) -> Response | None:
    """The response of a queued error fault for ``route``, or None to handle the request."""
    return error_response(world_of(request).faults.take(route))


class FaultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str = Field(min_length=2, max_length=200, pattern=r"^/[A-Za-z0-9_./-]+$")
    kind: FaultKind
    count: int = Field(default=1, ge=1, le=MAX_FAULT_COUNT)


router = APIRouter(prefix=ADMIN_PREFIX)


@router.post("/reset", status_code=204, response_class=Response)
def reset(request: Request) -> Response:
    """Restore the seeded state of every mock and clear the faults."""
    world_of(request).reset()
    return Response(status_code=204)


@router.post("/faults", status_code=201)
def add_fault(body: FaultIn, request: Request) -> dict[str, Any]:
    """Queue a fault; the response is the state after it."""
    world = world_of(request)
    world.faults.add(body.route, body.kind, body.count)
    return world.snapshot()


@router.get("/state")
def state(request: Request) -> dict[str, Any]:
    """The queued faults and the state of each mock."""
    return world_of(request).snapshot()
