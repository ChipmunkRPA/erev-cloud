"""Salesforce mock server (05 ADP-16, ADP-20 to ADP-22; PRD WLD-F-31, J-23; BUILD_SPEC DIN-12).

State is in memory per api process, seeded from
``fixtures/quayside/quayside-salesforce-scenario.json`` and restored by ``POST /__admin/reset``.
Routes, under ``/api/v1/__mocks__/salesforce``:

- ``GET /services/data/<version>/sobjects/Order/{id}`` — the order with its ``OrderItems`` at its
  latest version (``?version=`` selects an earlier one, as a stale notification would fetch it);
- ``GET /services/data/<version>/query?q=…`` — a minimal SOQL: ``FROM Order`` with an optional
  ``WHERE LastModifiedDate > <ISO timestamp>`` and ``ORDER BY LastModifiedDate`` (the reconciliation
  sweep). The result is paged like Salesforce's: ``batchSize`` from the ``Sforce-Query-Options``
  header (default 2, so every scenario exercises the continuation — 05 ADP-16 rev 1.12), ``done``
  and ``nextRecordsUrl`` → ``GET /services/data/<version>/query/{locator}`` for the next page;
- ``GET /events?replayId=<n>&limit=<m>`` — the change feed after a replay id (poll), delivering the
  scenario's duplicate notification and out-of-order version as WLD-F-31 says;
- ``POST /webhooks/sign`` — a test helper that signs a notification body with the mock's shared
  secret so a test can present a valid ``X-Erev-Mock-Signature`` (HMAC-SHA256 hex) to the API's
  webhook route; the mock never proxies to a real service (ADP-20).

Every route passes ``admin.fault_response`` first, so ADP-21 faults (429 with ``Retry-After``,
5xx, 504 timeout, 400 permanent) apply to the next matching requests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from erev_api.adapters.mocks.admin import fault_response, world_of

__all__ = ["CODE", "PREFIX", "SCENARIO_FIXTURE", "SalesforceMock", "load_scenario", "router"]

CODE: Final = "salesforce"
PREFIX: Final = f"/{CODE}"
FIXTURES: Final = Path(__file__).with_name("fixtures")
SCENARIO_FIXTURE: Final = FIXTURES / "quayside" / "quayside-salesforce-scenario.json"
SHARED_SECRET: Final = "quayside-mock-webhook-secret"  # a fixture value, not a credential
_LAST_MODIFIED: Final = re.compile(
    r"LastModifiedDate\s*>\s*'?([0-9T:\-\.Z+]+)'?", flags=re.IGNORECASE
)
DEFAULT_BATCH_SIZE: Final = 2  # a mock convention: small pages make every sweep page (rev 1.12)
_BATCH_SIZE: Final = re.compile(r"batchSize\s*=\s*(\d+)", flags=re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MockOrder:
    order_id: str
    header: dict[str, Any]
    versions: dict[str, list[dict[str, Any]]]  # version → OrderItems

    @property
    def latest_version(self) -> str:
        return max(self.versions, key=int)

    def at(self, version: str | None) -> dict[str, Any]:
        chosen = self.latest_version if version is None else version
        body = dict(self.header)
        body["Version__c"] = chosen
        body["OrderItems"] = {"records": list(self.versions[chosen])}
        return body


@dataclass(frozen=True, slots=True)
class Scenario:
    api_version: str
    signature_header: str
    orders: dict[str, MockOrder]
    notifications: tuple[dict[str, Any], ...]


def load_scenario(path: Path = SCENARIO_FIXTURE) -> Scenario:
    raw = json.loads(path.read_text(encoding="utf-8"))
    orders = {
        str(order["Id"]): MockOrder(
            order_id=str(order["Id"]),
            header={k: v for k, v in order.items() if k != "versions"},
            versions={str(v): list(items["OrderItems"]) for v, items in order["versions"].items()},
        )
        for order in raw["orders"]
    }
    return Scenario(
        api_version=str(raw["api_version"]),
        signature_header=str(raw["webhook_signature_header"]),
        orders=orders,
        notifications=tuple(dict(item) for item in raw["notifications"]),
    )


def sign(body: bytes, secret: str = SHARED_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class SalesforceMock:
    """ADP-22 state: the scenario orders and notifications, and the requests served."""

    def __init__(self, scenario_path: Path = SCENARIO_FIXTURE) -> None:
        self._path = scenario_path
        self._lock = threading.Lock()
        self.scenario = load_scenario(scenario_path)
        self.served: list[str] = []
        self._cursors: dict[str, tuple[list[dict[str, Any]], int]] = {}
        self._locators = 0

    def reset(self) -> None:
        with self._lock:
            self.scenario = load_scenario(self._path)
            self.served = []
            self._cursors = {}
            self._locators = 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "orders": sorted(self.scenario.orders),
                "notifications": len(self.scenario.notifications),
                "served": len(self.served),
            }

    def _note(self, what: str) -> None:
        with self._lock:
            self.served.append(what)

    def order(self, order_id: str, version: str | None) -> dict[str, Any] | None:
        found = self.scenario.orders.get(order_id)
        if found is None or (version is not None and version not in found.versions):
            return None
        self._note(f"order:{order_id}:{version or found.latest_version}")
        return found.at(version)

    def events(self, after_replay_id: int, limit: int) -> list[dict[str, Any]]:
        self._note(f"events:{after_replay_id}")
        later = [n for n in self.scenario.notifications if int(n["replayId"]) > after_replay_id]
        return later[: max(1, limit)]

    def query(self, soql: str, batch_size: int = DEFAULT_BATCH_SIZE) -> dict[str, Any]:
        """``FROM Order`` with an optional ``LastModifiedDate > <ts>`` and ``ORDER BY
        LastModifiedDate``; latest versions only; the first page of ``batch_size`` records with
        ``done`` and, when more remain, a ``nextRecordsUrl`` locator."""
        self._note("query")
        if "from order" not in soql.lower():
            return self._page([], batch_size, total=0)
        found = _LAST_MODIFIED.search(soql)
        watermark = found.group(1) if found else None
        rows = []
        for order in self.scenario.orders.values():
            stamp = str(order.header.get("SystemModstamp"))
            if watermark is None or stamp > watermark.replace("+00:00", "Z"):
                rows.append(order.at(None))
        if "order by lastmodifieddate" in soql.lower():
            rows.sort(key=lambda row: str(row.get("SystemModstamp")))
        return self._page(rows, batch_size, total=len(rows))

    def query_more(
        self, locator: str, batch_size: int = DEFAULT_BATCH_SIZE
    ) -> dict[str, Any] | None:
        """The next page of a query locator, or None when the locator is unknown or spent."""
        self._note(f"query:{locator}")
        with self._lock:
            entry = self._cursors.pop(locator, None)
        if entry is None:
            return None
        rows, total = entry
        return self._page(rows, batch_size, total=total)

    def _page(self, rows: list[dict[str, Any]], batch_size: int, *, total: int) -> dict[str, Any]:
        size = max(1, batch_size)
        page, rest = rows[:size], rows[size:]
        body: dict[str, Any] = {"totalSize": total, "done": not rest, "records": page}
        if rest:
            with self._lock:
                self._locators += 1
                locator = f"01gQUAY{self._locators:04d}-{size}"
                self._cursors[locator] = (rest, total)
            body["nextRecordsUrl"] = f"/services/data/{self.scenario.api_version}/query/{locator}"
        return body


def mock_of(request: Request) -> SalesforceMock:
    adapter = world_of(request).adapters[CODE]
    assert isinstance(adapter, SalesforceMock)
    return adapter


router = APIRouter(prefix=PREFIX)


@router.get("/services/data/{version}/sobjects/Order/{order_id}")
def get_order(version: str, order_id: str, request: Request) -> Response:
    del version
    fault = fault_response(request, f"{PREFIX}/sobjects/Order")
    if fault is not None:
        return fault
    body = mock_of(request).order(order_id, request.query_params.get("version"))
    if body is None:
        message = f"Provided external ID field does not exist or is not accessible: {order_id}"
        return JSONResponse([{"errorCode": "NOT_FOUND", "message": message}], status_code=404)
    return JSONResponse(body)


def _batch_size(request: Request) -> int:
    """``Sforce-Query-Options: batchSize=<n>`` as Salesforce reads it; the mock's small default
    otherwise."""
    found = _BATCH_SIZE.search(request.headers.get("Sforce-Query-Options", ""))
    return int(found.group(1)) if found else DEFAULT_BATCH_SIZE


@router.get("/services/data/{version}/query")
def query(version: str, request: Request) -> Response:
    del version
    fault = fault_response(request, f"{PREFIX}/query")
    if fault is not None:
        return fault
    body = mock_of(request).query(request.query_params.get("q", ""), _batch_size(request))
    return JSONResponse(body)


@router.get("/services/data/{version}/query/{locator}")
def query_more(version: str, locator: str, request: Request) -> Response:
    del version
    fault = fault_response(request, f"{PREFIX}/query")
    if fault is not None:
        return fault
    body = mock_of(request).query_more(locator, _batch_size(request))
    if body is None:
        message = f"invalid query locator: {locator}"
        return JSONResponse([{"errorCode": "INVALID_QUERY_LOCATOR", "message": message}], 404)
    return JSONResponse(body)


@router.get("/events")
def events(request: Request) -> Response:
    fault = fault_response(request, f"{PREFIX}/events")
    if fault is not None:
        return fault
    after = int(request.query_params.get("replayId", "0"))
    limit = int(request.query_params.get("limit", "100"))
    items = mock_of(request).events(after, limit)
    latest = items[-1]["replayId"] if items else after
    return JSONResponse({"events": items, "latestReplayId": latest})


@router.post("/webhooks/sign")
async def sign_webhook(request: Request) -> Response:
    """Test helper: the signature the mock would send with ``body`` (ADP-01 verification input)."""
    body = await request.body()
    header = mock_of(request).scenario.signature_header
    return JSONResponse({"header": header, "signature": sign(body)})
