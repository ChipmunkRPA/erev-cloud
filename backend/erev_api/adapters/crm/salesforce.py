"""``SALESFORCE``: the CRM inbound adapter over the in-process mock (05 §5.2 ``InboundAdapter``,
ADP-01 to ADP-05, ADP-12, ADP-14, ADP-16; PRD WLD-F-31, J-23; BUILD_SPEC DIN-12; lane F-DIN
preparation).

The adapter is pure over its inputs and the HTTP client the composition root supplies (an
``httpx.Client`` bound to ``integration_connection.base_url`` — the mock router in dev / test /
e2e, ADP-20); it holds no credential: ``verify_webhook`` receives the secret at call time and
compares an HMAC-SHA256 of the body (ADP-14). ``fetch_object`` classifies the source's answers into
the ADP-12 error classes (408, 429 and every 5xx ``Transient``; ``ports.transient_status``) and
retries ``Transient`` ones on the ADP-12 schedule (30 s × 2ⁿ capped, honouring ``Retry-After``; the
sleep is injectable so tests run without waiting). The ADP-16 sweep orders by ``LastModifiedDate``,
asks for its page through ``Sforce-Query-Options: batchSize`` and follows ``nextRecordsUrl`` to
exhaustion before the watermark advances; a page budget exhausted mid-sweep returns ``has_more``
with the watermark at the last fully consumed timestamp (05 rev 1.12 after Codex's DIN-R2).
``normalise`` maps
an activated order under mapping profile ``SF-ORDERS-v1`` (``ProductCode`` → product code,
``Performing_Entity__c`` → performing entity, default from ``config``) into ``NormalisedOrderDraft``
records; an order with a parent or an amendment reason is a candidate modification (ADP-05). The
sync run that stores ``source_record`` rows (``normalise.store_source_record``), resolves customers
and products (``PRODUCT_UNMAPPED``), routes by grouping (``grouping.ingest_order``) and writes
``sync_run`` totals is the dispatched DIN-12 lane's.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from urllib.parse import quote

from pydantic import SecretStr

from erev_api.clock import SystemClock
from erev_api.domain.integrations import ports
from erev_api.enums import SourceObjectType, SourceSystem

__all__ = [
    "API_VERSION",
    "MAPPING_VERSION",
    "MAX_SWEEP_PAGES",
    "RETRY_BACKOFF_SECONDS",
    "SIGNATURE_HEADER",
    "SalesforceAdapter",
    "normalise_order",
    "register",
    "version_order",
]

API_VERSION: Final = "v60.0"
MAPPING_VERSION: Final = "SF-ORDERS-v1"
SIGNATURE_HEADER: Final = "X-Erev-Mock-Signature"
# ADP-12: 30 s × 2^n, capped at 15 minutes, at most 8 attempts (tests inject a no-op sleep).
RETRY_BACKOFF_SECONDS: Final = (30, 60, 120, 240, 480, 900, 900, 900)
MAX_ATTEMPTS: Final = 8
# Page budget of one sweep call (rev 1.12): beyond it the sweep returns ``has_more`` and resumes.
MAX_SWEEP_PAGES: Final = 100
QUERY_OPTIONS_HEADER: Final = "Sforce-Query-Options"
DEFAULT_ENTITY_KEY: Final = "default_performing_entity"
# 05 ADP-16 rev 1.204 (item ACT-FLAGS-1): the two checkbox fields of an order that state the
# terms a booking carries; an order without one of them states nothing of that term.
ACCEPTANCE_FIELD: Final = "Acceptance_Clause__c"
SIDE_LETTER_FIELD: Final = "Side_Letter__c"


def version_order(external_version: str) -> int:
    """T-SRC-01 ``version_order`` of a Salesforce order version (``Version__c``, an integer
    text)."""
    try:
        return int(str(external_version).strip())
    except ValueError as error:
        raise ports.Permanent(f"order version {external_version!r} is not an integer") from error


def _decimal(value: Any, what: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ports.Permanent(f"{what} {value!r} is not a decimal") from error


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    return date.fromisoformat(str(value)[:10])


def _stamp(value: Any) -> datetime | None:
    """A Salesforce ``SystemModstamp`` / ISO instant as an aware datetime (None when blank)."""
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def normalise_order(
    payload: Mapping[str, Any],
    *,
    mapping_version: str = MAPPING_VERSION,
    default_entity: str | None = None,
) -> ports.NormalisedOrderDraft:
    """Pure: an activated Salesforce order (with ``OrderItems.records``) as a canonical order draft
    under ``SF-ORDERS-v1`` (PRD J-23.2): ``ProductCode`` → product code; ``Performing_Entity__c``
    → performing entity, else ``default_entity``; ``AccountId`` → customer external id;
    ``CurrencyIsoCode`` → transaction currency; ``EffectiveDate`` → order date;
    ``Acceptance_Clause__c`` and ``Side_Letter__c`` → the two terms of the booking, each true,
    false or not stated (rev 1.204)."""
    if mapping_version != MAPPING_VERSION:
        raise ports.Permanent(f"mapping version {mapping_version!r} is not supported")
    if str(payload.get("Status", "")).lower() != "activated":
        raise ports.Permanent("only activated orders are ingested (ADP-16)")
    items = payload.get("OrderItems") or {}
    records = items.get("records", items) if isinstance(items, Mapping) else items
    entity = str(payload.get("Performing_Entity__c") or default_entity or "")
    if not entity:
        raise ports.Permanent("the order names no performing entity and the profile has no default")
    lines = tuple(
        ports.NormalisedLine(
            line_external_id=str(item["Id"]),
            product_code=str(item["ProductCode"]),
            quantity=_decimal(item.get("Quantity", "1"), "quantity"),
            total_price=_decimal(item.get("TotalPrice", "0"), "total price"),
            start_date=_date(item.get("ServiceDate")),
            end_date=_date(item.get("EndDate")),
            performing_entity_code=entity,
        )
        for item in records
    )
    if not lines:
        raise ports.Permanent("an order without lines cannot be ingested")
    order_date = _date(payload.get("EffectiveDate"))
    if order_date is None:
        raise ports.Permanent("the order has no EffectiveDate")
    return ports.NormalisedOrderDraft(
        source_system=SourceSystem.SALESFORCE,
        external_order_id=str(payload["Id"]),
        external_version=str(payload.get("Version__c", "1")),
        order_number=str(payload.get("OrderNumber") or payload["Id"]),
        order_date=order_date,
        customer_external_id=str(payload["AccountId"]),
        legal_entity_code=entity,
        transaction_currency=str(payload.get("CurrencyIsoCode") or "USD"),
        lines=lines,
        po_number=(str(payload["PoNumber"]) if payload.get("PoNumber") else None),
        parent_order_external_id=(
            str(payload["Parent_Order__c"]) if payload.get("Parent_Order__c") else None
        ),
        amendment_reason=(
            str(payload["Amendment_Reason__c"]) if payload.get("Amendment_Reason__c") else None
        ),
        document_ref=str(payload.get("Id")),
        custom_attributes={"mapping_version": mapping_version},
        acceptance_clause=ports.stated_term(payload.get(ACCEPTANCE_FIELD), ACCEPTANCE_FIELD),
        side_letter=ports.stated_term(payload.get(SIDE_LETTER_FIELD), SIDE_LETTER_FIELD),
    )


class SalesforceAdapter:
    """One adapter per connection, over the client the root supplies."""

    def __init__(
        self,
        context: ports.InboundContext,
        *,
        sleep: Callable[[float], None] | None = None,
        max_attempts: int | None = None,
        max_sweep_pages: int = MAX_SWEEP_PAGES,
    ) -> None:
        self._client = context.client
        self._base = context.base_url.rstrip("/")
        self._config = dict(context.config)
        self._sleep = sleep if sleep is not None else _default_sleep
        # ``max_attempts`` None reads the connection's non-secret ``config.max_attempts`` (T-INT-01;
        # a test-connection probe passes 1), else the ADP-12 default.
        configured = self._config.get("max_attempts", MAX_ATTEMPTS)
        self._max_attempts = max(1, int(max_attempts if max_attempts is not None else configured))
        self._max_sweep_pages = max(1, max_sweep_pages)
        self.attempts: list[tuple[str, int]] = []  # (path, status) of every attempt, for evidence

    @property
    def code(self) -> ports.AdapterCode:
        return "SALESFORCE"

    # --- ADP-01: webhooks are notifications ------------------------------------------------------

    def verify_webhook(
        self, headers: Mapping[str, str], body: bytes, secret: SecretStr
    ) -> ports.WebhookNotice:
        presented = next(
            (value for name, value in headers.items() if name.lower() == SIGNATURE_HEADER.lower()),
            None,
        )
        if presented is None:
            return ports.WebhookNotice(verified=False, reason="signature header missing")
        expected = hmac.new(secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, presented.strip().lower()):
            return ports.WebhookNotice(verified=False, reason="signature mismatch")
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ports.WebhookNotice(verified=False, reason="body is not JSON")
        events = parsed.get("events", parsed) if isinstance(parsed, Mapping) else parsed
        return ports.WebhookNotice(verified=True, notifications=self._notifications(events))

    @staticmethod
    def _notifications(events: Any) -> tuple[ports.Notification, ...]:
        found: list[ports.Notification] = []
        for item in events or ():
            found.append(
                ports.Notification(
                    notification_id=str(item["notificationId"]),
                    object_type=SourceObjectType.ORDER,
                    external_id=str(item["orderId"]),
                    external_version=str(item["version"]),
                    replay_id=int(item["replayId"]),
                )
            )
        return tuple(found)

    # --- poll and sweep (ADP-16) -----------------------------------------------------------------

    def fetch_changes(self, checkpoint: ports.Checkpoint, limit: int) -> ports.ChangePage:
        now = self._now()
        if checkpoint.sweep_cursor is not None or ports.sweep_due(checkpoint, now):
            return self._sweep(checkpoint, now, limit)  # a sweep in progress resumes first
        after = checkpoint.replay_id or 0
        body = self._get(f"/events?replayId={after}&limit={limit}")
        notifications = self._notifications(body.get("events", ()))
        latest = int(body.get("latestReplayId", after))
        return ports.ChangePage(
            notifications=notifications,
            checkpoint=ports.Checkpoint(
                replay_id=latest,
                replay_at=now,
                last_modified_watermark=checkpoint.last_modified_watermark,
            ),
            has_more=len(notifications) >= limit,
            kind="POLL",
        )

    def _sweep(self, checkpoint: ports.Checkpoint, now: datetime, limit: int) -> ports.ChangePage:
        """ADP-16 rev 1.12: every page of the query is consumed (``nextRecordsUrl`` until ``done``)
        before the watermark moves; when the page budget stops the sweep first, the watermark moves
        only past timestamps whose records were all consumed (the query is ordered by
        ``LastModifiedDate``), ``has_more`` is set, ``replay_at`` is not re-baselined and the
        checkpoint's ``sweep_cursor`` carries the query locator and the still-open timestamp, so
        the next call resumes exactly there (DIN-R2 residual). An expired locator (Salesforce keeps
        them for minutes) restarts from the watermark, which never passed an unconsumed row."""
        watermark = checkpoint.last_modified_watermark
        cursor = dict(checkpoint.sweep_cursor or {})
        resuming = cursor.get("source") == self.code and isinstance(cursor.get("next"), str)
        pending = _stamp(cursor.get("pending")) if resuming else None
        # SOQL over the mock's read-only order feed (ADP-16); the only interpolated value is an ISO
        # timestamp this adapter formatted itself, never caller text.
        clause = "" if watermark is None else f" WHERE LastModifiedDate > {watermark.isoformat()}"
        soql = (
            f"SELECT Id, Version__c, SystemModstamp FROM Order{clause}"  # noqa: S608
            " ORDER BY LastModifiedDate ASC"
        )
        headers = {QUERY_OPTIONS_HEADER: f"batchSize={max(1, limit)}"}
        fresh = f"/services/data/{API_VERSION}/query?q={quote(soql)}"
        path = str(cursor["next"]) if resuming else fresh
        records: list[Mapping[str, Any]] = []
        pages = 0
        exhausted = False
        continuation: str | None = None
        while True:
            try:
                body = self._get(path, headers=headers)
            except ports.Permanent:
                if pages > 0 or path == fresh:
                    raise
                pending = None  # the locator expired: restart from the watermark
                path = fresh
                continue
            pages += 1
            records.extend(body.get("records", ()))
            next_url = body.get("nextRecordsUrl")
            if bool(body.get("done", True)) or not next_url:
                exhausted = True
                break
            path = self._relative(str(next_url))
            if pages >= self._max_sweep_pages:
                continuation = path
                break
        notifications = tuple(
            ports.Notification(
                notification_id=f"SWEEP:{record['Id']}:{record.get('Version__c', '1')}",
                object_type=SourceObjectType.ORDER,
                external_id=str(record["Id"]),
                external_version=str(record.get("Version__c", "1")),
                replay_id=checkpoint.replay_id or 0,
            )
            for record in records
        )
        stamps = sorted(
            {
                *(
                    _stamp(record["SystemModstamp"])
                    for record in records
                    if record.get("SystemModstamp")
                ),
                *(() if pending is None else (pending,)),
            }
            - {None}
        )
        if exhausted:
            new_watermark = stamps[-1] if stamps else watermark
            replay_at: datetime | None = now  # the completed sweep re-baselines the cadence
            new_cursor: dict[str, Any] | None = None
        else:
            # the highest consumed timestamp may continue on the next page: it stays pending
            complete = [stamp for stamp in stamps if stamp < stamps[-1]] if stamps else []
            new_watermark = complete[-1] if complete else watermark
            replay_at = checkpoint.replay_at  # a partial sweep resumes on the next call
            new_cursor = {
                "source": self.code,
                "next": continuation,
                "pending": None if not stamps else stamps[-1].isoformat(),
            }
        return ports.ChangePage(
            notifications=notifications,
            checkpoint=ports.Checkpoint(
                replay_id=checkpoint.replay_id,
                replay_at=replay_at,
                last_modified_watermark=new_watermark,
                sweep_cursor=new_cursor,
            ),
            has_more=not exhausted,
            kind="SWEEP",
            pages=pages,
        )

    def _relative(self, url: str) -> str:
        """A continuation URL as a path under the connection's base (Salesforce returns
        ``/services/data/...`` paths; an absolute URL under the base is reduced to its path)."""
        if url.startswith(self._base):
            return url[len(self._base) :]
        return url

    # --- the truth before acting (ADP-01, ADP-12) -----------------------------------------------

    def fetch_object(self, object_type: SourceObjectType, external_id: str) -> ports.SourceObject:
        if object_type is not SourceObjectType.ORDER:
            raise ports.Permanent(f"the Salesforce adapter ingests orders, not {object_type.value}")
        body = self._get(f"/services/data/{API_VERSION}/sobjects/Order/{quote(external_id)}")
        version = str(body.get("Version__c", "1"))
        stamp = body.get("SystemModstamp")
        return ports.SourceObject(
            source_system=SourceSystem.SALESFORCE,
            object_type=SourceObjectType.ORDER,
            external_id=str(body.get("Id", external_id)),
            external_version=version,
            version_order=version_order(version),
            payload=body,
            last_modified=(
                None if stamp is None else datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            ),
        )

    def normalise(self, obj: ports.SourceObject, mapping_version: str) -> ports.NormalisedRecords:
        draft = normalise_order(
            obj.payload,
            mapping_version=mapping_version,
            default_entity=self._config.get(DEFAULT_ENTITY_KEY),
        )
        return ports.NormalisedRecords(mapping_version=mapping_version, orders=(draft,))

    def control_totals(self, objects: Sequence[ports.SourceObject]) -> ports.ControlTotals:
        items: list[tuple[str, str, str, Decimal]] = []
        for obj in objects:
            draft = normalise_order(
                obj.payload, default_entity=self._config.get(DEFAULT_ENTITY_KEY) or "-"
            )
            items.append(
                (obj.external_id, obj.external_version, draft.transaction_currency, draft.total)
            )
        return ports.ControlTotals.of(items)

    # --- transport with the ADP-12 schedule ------------------------------------------------------

    def _now(self) -> datetime:
        clock = self._config.get(ports.NOW_HOOK)
        return clock() if callable(clock) else SystemClock().now()  # DG-KRN-TIME-05

    def _get(self, path: str, headers: Mapping[str, str] | None = None) -> dict[str, Any]:
        last: ports.Transient | None = None
        for attempt in range(self._max_attempts):
            try:
                response = (
                    self._client.get(f"{self._base}{path}", headers=dict(headers))
                    if headers
                    else self._client.get(f"{self._base}{path}")
                )
            except ports.Permanent:
                raise  # a refused destination (SAR-15 guard) is never retried (ADP-12)
            except Exception as error:  # noqa: BLE001 - driver errors are transient (ADP-12)
                last = ports.Transient(f"connection error: {type(error).__name__}")
                self.attempts.append((path, 0))
            else:
                self.attempts.append((path, int(response.status_code)))
                status = int(response.status_code)
                if status < 300:
                    body = response.json()
                    return dict(body) if isinstance(body, Mapping) else {"records": body}
                if ports.transient_status(status):  # ADP-12: 408, 429, every 5xx (rev 1.12)
                    retry_after = response.headers.get("Retry-After")
                    last = ports.Transient(
                        f"HTTP {status}",
                        status=status,
                        retry_after=None if retry_after is None else float(retry_after),
                    )
                else:
                    raise ports.Permanent(f"HTTP {status}", status=status)
            if attempt + 1 < self._max_attempts:
                delay: float = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                if last is not None and last.retry_after is not None:
                    delay = max(delay, last.retry_after)
                self._sleep(float(delay))
        assert last is not None
        raise last


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def register() -> None:
    """Composition-root wiring (DG-LAY-03): the ``SALESFORCE`` factory over the context's client."""
    ports.register_inbound_adapter("SALESFORCE", SalesforceAdapter)
