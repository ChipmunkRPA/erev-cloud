"""Stripe mock server (05 ADP-17, ADP-20 to ADP-22; PRD WLD-F-31, J-23.6; BUILD_SPEC DIN-13).

State is in memory per api process, seeded from ``fixtures/quayside/quayside-stripe-scenario.json``
and restored by ``POST /__admin/reset``. Routes, under ``/api/v1/__mocks__/stripe``:

- ``GET /v1/subscriptions/{id}``, ``GET /v1/invoices/{id}`` (``?version=`` selects an earlier
  version, as a stale event would fetch it), ``GET /v1/credit_notes/{id}``;
- ``GET /v1/subscriptions``, ``GET /v1/invoices``, ``GET /v1/credit_notes`` with
  ``created[gt]=<epoch>``, ``limit`` and ``starting_after=<id>`` — Stripe's list shape, newest
  first, ``has_more`` exact (the reconciliation sweep; 05 ADP-17 rev 1.12);
- ``GET /v1/events?starting_after=<ordinal>&limit=<m>`` (optionally ``created[gt]=<epoch>``) — the
  event feed after a cursor with an exact ``has_more`` (F-DIN DIN-R1), carrying the scenario's
  repeated event id and out-of-order invoice version; every event carries ``created`` — the
  scenario's value, else the referenced object's ``created``;
- ``POST /webhooks/sign`` — a test helper answering the ``Stripe-Signature`` value
  (``t=<ts>,v1=<hex HMAC-SHA256(secret, "<ts>.<body>")>``) for a body.

Every route passes ``admin.fault_response`` first (ADP-21). Amounts are Stripe minor units.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from erev_api.adapters.mocks.admin import fault_response, world_of

__all__ = [
    "CODE",
    "PREFIX",
    "SCENARIO_FIXTURE",
    "SHARED_SECRET",
    "StripeMock",
    "load_scenario",
    "router",
]

CODE: Final = "stripe"
PREFIX: Final = f"/{CODE}"
FIXTURES: Final = Path(__file__).with_name("fixtures")
SCENARIO_FIXTURE: Final = FIXTURES / "quayside" / "quayside-stripe-scenario.json"
SHARED_SECRET: Final = "whsec_quayside_mock"  # a fixture value, not a credential
DEFAULT_LIMIT: Final = 10  # Stripe's default page size
LIST_KINDS: Final = ("subscription", "invoice", "credit_note")


@dataclass(frozen=True, slots=True)
class MockInvoice:
    header: dict[str, Any]
    versions: dict[str, dict[str, Any]]

    @property
    def latest_version(self) -> str:
        return max(self.versions, key=int)

    def at(self, version: str | None) -> dict[str, Any]:
        chosen = self.latest_version if version is None else version
        return {**self.header, **self.versions[chosen], "version": chosen}


@dataclass(frozen=True, slots=True)
class Scenario:
    signature_header: str
    subscriptions: dict[str, dict[str, Any]]
    invoices: dict[str, MockInvoice]
    credit_notes: dict[str, dict[str, Any]]
    events: tuple[dict[str, Any], ...]


def load_scenario(path: Path = SCENARIO_FIXTURE) -> Scenario:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Scenario(
        signature_header=str(raw["webhook_signature_header"]),
        subscriptions={str(s["id"]): dict(s) for s in raw["subscriptions"]},
        invoices={
            str(i["id"]): MockInvoice(
                header={k: v for k, v in i.items() if k != "versions"},
                versions={str(v): dict(body) for v, body in i["versions"].items()},
            )
            for i in raw["invoices"]
        },
        credit_notes={str(c["id"]): dict(c) for c in raw["credit_notes"]},
        events=tuple(dict(e) for e in raw["events"]),
    )


def sign(body: bytes, timestamp: int, secret: str = SHARED_SECRET) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


class StripeMock:
    """ADP-22 state: the scenario objects and events, and the requests served."""

    def __init__(self, scenario_path: Path = SCENARIO_FIXTURE) -> None:
        self._path = scenario_path
        self._lock = threading.Lock()
        self.scenario = load_scenario(scenario_path)
        self.served: list[str] = []

    def reset(self) -> None:
        with self._lock:
            self.scenario = load_scenario(self._path)
            self.served = []

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "subscriptions": sorted(self.scenario.subscriptions),
                "invoices": sorted(self.scenario.invoices),
                "credit_notes": sorted(self.scenario.credit_notes),
                "events": len(self.scenario.events),
                "served": len(self.served),
            }

    def _note(self, what: str) -> None:
        with self._lock:
            self.served.append(what)

    def subscription(self, sub_id: str) -> dict[str, Any] | None:
        found = self.scenario.subscriptions.get(sub_id)
        if found is not None:
            self._note(f"subscription:{sub_id}")
        return found

    def invoice(self, invoice_id: str, version: str | None) -> dict[str, Any] | None:
        found = self.scenario.invoices.get(invoice_id)
        if found is None or (version is not None and version not in found.versions):
            return None
        self._note(f"invoice:{invoice_id}:{version or found.latest_version}")
        return found.at(version)

    def credit_note(self, note_id: str) -> dict[str, Any] | None:
        found = self.scenario.credit_notes.get(note_id)
        if found is not None:
            self._note(f"credit_note:{note_id}")
        return found

    def _latest(self, kind: str) -> list[dict[str, Any]]:
        if kind == "subscription":
            return [dict(body) for body in self.scenario.subscriptions.values()]
        if kind == "invoice":
            return [invoice.at(None) for invoice in self.scenario.invoices.values()]
        return [dict(body) for body in self.scenario.credit_notes.values()]

    def list_objects(
        self, kind: str, created_after: int, limit: int, starting_after: str | None = None
    ) -> tuple[list[dict[str, Any]], bool]:
        """Stripe's list shape: ``created[gt]`` filter, newest first, ``limit`` and
        ``starting_after=<id>`` paging, ``has_more`` exact (rev 1.12)."""
        self._note(f"{kind}s:list")
        rows = [r for r in self._latest(kind) if int(r.get("created", 0)) > created_after]
        rows.sort(key=lambda row: (int(row.get("created", 0)), str(row["id"])), reverse=True)
        if starting_after is not None:
            index = next((i for i, row in enumerate(rows) if row["id"] == starting_after), None)
            rows = [] if index is None else rows[index + 1 :]
        page = rows[: max(1, limit)]
        return page, len(rows) > len(page)

    def _created_of(self, kind: str, object_id: str) -> int:
        """The referenced object's ``created`` — an event's ``created`` when the scenario gives
        the event none (the WLD-F-31 scenario predates dated events)."""
        for row in self._latest(kind) if kind in LIST_KINDS else ():
            if row["id"] == object_id:
                return int(row.get("created", 0))
        return 0

    def _event_created(self, event: Mapping[str, Any]) -> int:
        if event.get("created") is not None:
            return int(event["created"])
        return self._created_of(str(event["object"]), str(event["object_id"]))

    def events(
        self, after_ordinal: int, limit: int, created_after: int | None = None
    ) -> tuple[list[dict[str, Any]], bool]:
        """The events after a cursor (and, for a sweep, created after an epoch): one page and an
        exact ``has_more`` (DIN-R1: the page used to say ``has_more=false`` whatever remained)."""
        self._note(f"events:{after_ordinal}")
        later = [
            e
            for e in self.scenario.events
            if int(e["ordinal"]) > after_ordinal
            and (created_after is None or self._event_created(e) > created_after)
        ]
        page = later[: max(1, limit)]
        return [self._event_body(e) for e in page], len(later) > len(page)

    def _event_body(self, event: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": event["id"],
            "object": "event",
            "ordinal": int(event["ordinal"]),
            "created": self._event_created(event),
            "type": event["type"],
            "data": {
                "object": {
                    "object": event["object"],
                    "id": event["object_id"],
                    "version": str(event.get("version", "1")),
                }
            },
        }


def mock_of(request: Request) -> StripeMock:
    adapter = world_of(request).adapters[CODE]
    assert isinstance(adapter, StripeMock)
    return adapter


def _not_found(kind: str, object_id: str) -> Response:
    return JSONResponse(
        {
            "error": {
                "type": "invalid_request_error",
                "code": "resource_missing",
                "message": f"No such {kind}: '{object_id}'",
            }
        },
        status_code=404,
    )


router = APIRouter(prefix=PREFIX)


@router.get("/v1/subscriptions/{sub_id}")
def get_subscription(sub_id: str, request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/v1/subscriptions")
    if fault is not None:
        return fault
    body = mock_of(request).subscription(sub_id)
    return _not_found("subscription", sub_id) if body is None else JSONResponse(body)


@router.get("/v1/invoices/{invoice_id}")
def get_invoice(invoice_id: str, request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/v1/invoices")
    if fault is not None:
        return fault
    body = mock_of(request).invoice(invoice_id, request.query_params.get("version"))
    return _not_found("invoice", invoice_id) if body is None else JSONResponse(body)


def _list(request: Request, kind: str) -> Response:
    params = request.query_params
    rows, has_more = mock_of(request).list_objects(
        kind,
        created_after=int(params.get("created[gt]", "0")),
        limit=int(params.get("limit", str(DEFAULT_LIMIT))),
        starting_after=params.get("starting_after"),
    )
    return JSONResponse({"object": "list", "data": rows, "has_more": has_more})


@router.get("/v1/subscriptions")
def list_subscriptions(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/v1/subscriptions")
    return fault if fault is not None else _list(request, "subscription")


@router.get("/v1/invoices")
def list_invoices(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/v1/invoices")
    return fault if fault is not None else _list(request, "invoice")


@router.get("/v1/credit_notes")
def list_credit_notes(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/v1/credit_notes")
    return fault if fault is not None else _list(request, "credit_note")


@router.get("/v1/credit_notes/{note_id}")
def get_credit_note(note_id: str, request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/v1/credit_notes")
    if fault is not None:
        return fault
    body = mock_of(request).credit_note(note_id)
    return _not_found("credit_note", note_id) if body is None else JSONResponse(body)


@router.get("/v1/events")
def list_events(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/v1/events")
    if fault is not None:
        return fault
    params = request.query_params
    after = int(params.get("starting_after", "0"))
    limit = int(params.get("limit", "100"))
    created_after = params.get("created[gt]")
    items, has_more = mock_of(request).events(
        after, limit, None if created_after is None else int(created_after)
    )
    return JSONResponse({"object": "list", "data": items, "has_more": has_more})


@router.post("/webhooks/sign")
async def sign_webhook(request: Request) -> Response:
    """Test helper: the ``Stripe-Signature`` value the mock would send with ``body``."""
    body = await request.body()
    timestamp = int(request.query_params.get("t", "1758300000"))
    header = mock_of(request).scenario.signature_header
    return JSONResponse({"header": header, "signature": sign(body, timestamp)})
