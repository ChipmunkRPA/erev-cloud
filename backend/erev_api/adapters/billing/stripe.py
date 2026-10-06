"""``STRIPE``: the billing inbound adapter over the in-process mock (05 §5.2 ``InboundAdapter``,
ADP-01 to ADP-05, ADP-12, ADP-14, ADP-17; PRD WLD-F-31, J-23.6; BUILD_SPEC DIN-13; lane F-DIN
preparation).

Pure over its inputs and the HTTP client the composition root supplies. ``verify_webhook`` checks
the Stripe scheme ``Stripe-Signature: t=<ts>,v1=<hex HMAC-SHA256(secret, "<ts>.<body>")>`` with
the secret at call time (ADP-01, ADP-14) and reads the events. ``fetch_changes`` pages
``/v1/events`` after the checkpoint's event ordinal (Stripe's ``starting_after`` cursor, kept as
``replay_id``; the cursor advances over the complete consumed page, events about objects this
adapter ignores included — DIN-R1) and, when the checkpoint is stale (ADP-16, shared
``ports.sweep_due``), sweeps to exhaustion: the events feed by ``created`` since the watermark (the
authoritative recovery of creations and changes of subscriptions, invoices and credit notes) plus
the ``created``-filtered lists of the three object types (the fallback for creations older than the
feed's retention), every list paged (``limit``, ``starting_after``, ``has_more``) before the
watermark advances; a page budget exhausted mid-sweep returns ``has_more`` with the watermark
unchanged (05 ADP-17 rev 1.12; DIN-R2, DIN-G1). ``fetch_object`` reads the subscription, invoice or
credit note before anything is applied (ADP-17) on the ADP-12 schedule (408, 429 and every 5xx
``Transient``; DIN-R3). ``normalise`` is pure: a subscription is the
contract source (``NormalisedOrderDraft`` with its items as lines, ``sub_…`` as the order number),
an invoice a ``NormalisedInvoiceDraft`` of kind ``INVOICE`` whose lines carry the service period as
the ``BILLING_RECORDED`` hint, a credit note a ``CREDIT_MEMO`` naming the invoice it credits
(``CREDIT_MEMO_RECORDED``). A repeated event id is a duplicate notification the sync records once.
Amounts are Stripe API minor units converted with **Stripe's** documented scale for the currency
(``api_scale``), never the ISO 4217 exponent alone (DIN-R4 and Codex's scale supplement): the
zero-decimal list; ISK and UGX as two-decimal values by backward compatibility (``500`` is 5 units);
the three-decimal currencies BHD, JOD, KWD, OMR and TND (minor units whose last digit is 0) —
**refused** ``Permanent`` with the reason ``CURRENCY_NOT_ENABLED_FOR_ACCOUNT`` until the
connection's account-level allowlist (``config["enabled_currencies"]``) admits them, because the
presentment list retrieved 2026-09-20 does not carry them and their availability is
account-dependent (supervisor ruling on Codex's DIN-R4; the scale table and the last-digit-zero rule
are kept for that day); every other presentment currency two-decimal; an unlisted currency is
refused ``Permanent``. Source:
https://docs.stripe.com/currencies (retrieved 2026-09-20, rendering saved under the lane's
``.run/l3-fdin/sources/``; the lists are copied below) and Codex's
PRODUCTION-STRIPE-CURRENCY-SOURCE-NOTE-20260920 (KWD availability depends on account and payment
context). No further external retrieval: the saved rendering is the cited source.

Sweep modes (``sweep``): ``RECOVERY`` is the ADP-16 default behind ``fetch_changes`` (events feed
plus the three created-filtered lists); ``INVOICES_CREATED`` is the original creation-only invoice
sweep, kept as a distinct still-callable mode whose original ADP-15 expectation stays true
(supervisor ruling on DIN-G1: recovery is defined beside the original oracle, not by rewriting it).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final, Literal
from urllib.parse import quote

from pydantic import SecretStr

from erev_api.clock import SystemClock
from erev_api.domain.integrations import ports
from erev_api.enums import SourceObjectType, SourceSystem

__all__ = [
    "CURRENCY_NOT_ENABLED",
    "ENABLED_CURRENCIES_KEY",
    "MAPPING_VERSION",
    "MAX_SWEEP_PAGES",
    "PRESENTMENT",
    "REPLAY_WINDOW_SECONDS",
    "THREE_DECIMAL",
    "TWO_DECIMAL_BY_COMPATIBILITY",
    "ZERO_DECIMAL",
    "SIGNATURE_HEADER",
    "StripeAdapter",
    "SweepMode",
    "api_scale",
    "money",
    "normalise_credit_note",
    "normalise_invoice",
    "normalise_subscription",
    "register",
]

MAPPING_VERSION: Final = "STRIPE-BILLING-v1"
SIGNATURE_HEADER: Final = "Stripe-Signature"
# ADP-01: a signed notification is accepted within this many seconds of its timestamp, either way.
REPLAY_WINDOW_SECONDS: Final = 300
RETRY_BACKOFF_SECONDS: Final = (30, 60, 120, 240, 480, 900, 900, 900)
MAX_ATTEMPTS: Final = 8
# Page budget of one sweep call (rev 1.12): beyond it the sweep returns ``has_more`` and resumes.
MAX_SWEEP_PAGES: Final = 100
MAX_PAGE_SIZE: Final = 100  # Stripe's list ``limit`` ceiling
DEFAULT_ENTITY_KEY: Final = "default_legal_entity"
PRODUCT_CODE_KEY: Final = "erev_product_code"  # Stripe price / product metadata member
# 05 ADP-17 rev 1.204 (item ACT-FLAGS-1): the subscription metadata members that state the two
# terms a booking carries, read as ``legal_entity`` is.
ACCEPTANCE_KEY: Final = "acceptance_clause"
SIDE_LETTER_KEY: Final = "side_letter"

# --- Stripe's API scale table (https://docs.stripe.com/currencies, retrieved 2026-09-20) ----------
# "Supported presentment currencies": 130 codes; "Currencies are two-decimal currencies unless
# otherwise specified."
PRESENTMENT: Final = frozenset(
    "AED AFN AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BIF BMD BND BOB BRL BSD BWP BYN BZD CAD CDF "
    "CHF CLP CNY COP CRC CVE CZK DJF DKK DOP DZD EGP ETB EUR FJD FKP GBP GEL GIP GMD GNF GTQ GYD "
    "HKD HNL HTG HUF IDR ILS INR ISK JMD JPY KES KGS KHR KMF KRW KYD KZT LAK LBP LKR LRD LSL MAD "
    "MDL MGA MKD MMK MNT MOP MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD PAB PEN PGK PHP PKR "
    "PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SEK SGD SHP SLE SRD SZL THB TJS TRY TTD TWD TZS UAH "
    "UGX USD UYU UZS VND VUV WST XAF XCD XCG XOF XPF YER ZAR ZMW".split()
)
# "Zero-decimal currencies": "the charge and the amount are the same, without requiring
# multiplication. For example, to charge 500 JPY, provide an amount value of 500."
ZERO_DECIMAL: Final = frozenset(
    "BIF CLP DJF GNF JPY KMF KRW MGA PYG RWF UGX VND VUV XAF XOF XPF".split()
)
# "Special cases": ISK and UGX "transitioned to a zero-decimal currency, but backward compatibility
# requires you to represent it as a two-decimal value, where the decimal amount is always 00. For
# example, to charge 5 ISK, provide an amount value of 500." (UGX is also on the zero-decimal list;
# the special case governs the API representation.) HUF and TWD charge two-decimal amounts (their
# payout divisibility rule does not change the scale).
TWO_DECIMAL_BY_COMPATIBILITY: Final = frozenset({"ISK", "UGX"})
# Three-decimal currencies: API amounts in minor units whose last digit is 0 (5.120 KWD is 5120).
# Not in the general presentment list retrieved 2026-09-20 (Codex's UAE-support note names KWD
# among three-decimal charge currencies, account-dependent): refused until the connection's
# account-level allowlist ``enabled_currencies`` admits them.
THREE_DECIMAL: Final = frozenset({"BHD", "JOD", "KWD", "OMR", "TND"})
CURRENCY_NOT_ENABLED: Final = "CURRENCY_NOT_ENABLED_FOR_ACCOUNT"
ENABLED_CURRENCIES_KEY: Final = "enabled_currencies"  # connection config: the account allowlist
SweepMode = Literal["RECOVERY", "INVOICES_CREATED"]
OBJECT_PATHS: Final[Mapping[SourceObjectType, str]] = {
    SourceObjectType.ORDER: "/v1/subscriptions",
    SourceObjectType.INVOICE: "/v1/invoices",
    SourceObjectType.CREDIT_MEMO: "/v1/credit_notes",
}
EVENT_OBJECTS: Final[Mapping[str, SourceObjectType]] = {
    "subscription": SourceObjectType.ORDER,
    "invoice": SourceObjectType.INVOICE,
    "credit_note": SourceObjectType.CREDIT_MEMO,
}
# The ``created``-filtered lists a sweep pages (rev 1.12), in the order they are consumed.
SWEEP_LISTS: Final = (
    ("subscription", "/v1/subscriptions"),
    ("invoice", "/v1/invoices"),
    ("credit_note", "/v1/credit_notes"),
)


def api_scale(currency: str, *, enabled: Collection[str] = ()) -> int:
    """The number of decimals Stripe's API amount carries for ``currency`` (the provider table
    above); ``Permanent`` for a currency Stripe does not list, and ``Permanent``
    ``CURRENCY_NOT_ENABLED_FOR_ACCOUNT`` for a three-decimal currency the connection's account
    allowlist ``enabled`` does not carry."""
    code = currency.upper()
    if code in TWO_DECIMAL_BY_COMPATIBILITY:
        return 2
    if code in ZERO_DECIMAL:
        return 0
    if code in THREE_DECIMAL:
        if code in {item.upper() for item in enabled}:
            return 3
        raise ports.Permanent(
            f"{CURRENCY_NOT_ENABLED}: {code} is a three-decimal currency Stripe enables per "
            "account and this connection's allowlist does not carry it"
        )
    if code in PRESENTMENT:
        return 2
    raise ports.Permanent(f"currency {code!r} is not a Stripe presentment currency")


def money(minor: Any, currency: str, *, enabled: Collection[str] = ()) -> Decimal:
    """Stripe API minor units → currency units at Stripe's scale for the currency."""
    scale = api_scale(currency, enabled=enabled)
    units = Decimal(str(minor))
    if scale == 3 and units % 10 != 0:
        raise ports.Permanent(
            f"a {currency.upper()} amount ends in 0 in Stripe's three-decimal representation "
            f"({minor!r})"
        )
    return units.scaleb(-scale)


def _day(epoch: Any) -> date | None:
    if epoch in (None, ""):
        return None
    return datetime.fromtimestamp(int(epoch), tz=UTC).date()


def _product_code(price: Mapping[str, Any]) -> str:
    metadata = price.get("metadata") or {}
    product = price.get("product") if isinstance(price.get("product"), Mapping) else {}
    code = metadata.get(PRODUCT_CODE_KEY) or (product or {}).get("metadata", {}).get(
        PRODUCT_CODE_KEY
    )
    if not code:
        raise ports.Permanent("a Stripe price names no erev_product_code")
    return str(code)


def normalise_subscription(
    payload: Mapping[str, Any],
    *,
    default_entity: str | None = None,
    enabled_currencies: Collection[str] = (),
) -> ports.NormalisedOrderDraft:
    """A subscription is the contract source: one order line per item, the annual (or plan) price
    times quantity as the line total, the current period as the line's dates. Its metadata names
    the legal entity and, since rev 1.204, states the two terms of the booking — the keys
    ``acceptance_clause`` and ``side_letter``, each ``true`` or ``false``; a key that is absent
    states nothing of its term."""
    currency = str(payload.get("currency", "usd")).upper()
    metadata = payload.get("metadata") or {}
    entity = str(metadata.get("legal_entity") or default_entity or "")
    if not entity:
        raise ports.Permanent(
            "the subscription names no legal entity and the profile has no default"
        )
    items = (payload.get("items") or {}).get("data", ())
    lines = tuple(
        ports.NormalisedLine(
            line_external_id=str(item["id"]),
            product_code=_product_code(item.get("price") or {}),
            quantity=Decimal(str(item.get("quantity", 1))),
            total_price=money(item["price"]["unit_amount"], currency, enabled=enabled_currencies)
            * Decimal(str(item.get("quantity", 1))),
            start_date=_day(payload.get("current_period_start")),
            end_date=_day(payload.get("current_period_end")),
            performing_entity_code=entity,
        )
        for item in items
    )
    if not lines:
        raise ports.Permanent("a subscription without items cannot be ingested")
    started = _day(payload.get("start_date") or payload.get("created"))
    if started is None:
        raise ports.Permanent("the subscription has no start date")
    return ports.NormalisedOrderDraft(
        source_system=SourceSystem.STRIPE,
        external_order_id=str(payload["id"]),
        external_version=str(payload.get("version", "1")),
        order_number=str(payload["id"]),
        order_date=started,
        customer_external_id=str(payload["customer"]),
        legal_entity_code=entity,
        transaction_currency=currency,
        lines=lines,
        document_ref=str(payload["id"]),
        custom_attributes={"mapping_version": MAPPING_VERSION},
        acceptance_clause=ports.stated_term(metadata.get(ACCEPTANCE_KEY), ACCEPTANCE_KEY),
        side_letter=ports.stated_term(metadata.get(SIDE_LETTER_KEY), SIDE_LETTER_KEY),
    )


def _invoice_lines(
    payload: Mapping[str, Any], currency: str, enabled: Collection[str] = ()
) -> tuple[ports.NormalisedInvoiceLine, ...]:
    data = (payload.get("lines") or {}).get("data", ())
    found = []
    for line in data:
        period = line.get("period") or {}
        found.append(
            ports.NormalisedInvoiceLine(
                line_external_id=str(line["id"]),
                product_code=_product_code(line.get("price") or {}),
                amount=money(line["amount"], currency, enabled=enabled),
                quantity=Decimal(str(line.get("quantity", 1))),
                service_period_start=_day(period.get("start")),
                service_period_end=_day(period.get("end")),
                contract_ref=(str(line["subscription"]) if line.get("subscription") else None),
            )
        )
    if not found:
        raise ports.Permanent("a document without lines cannot be ingested")
    return tuple(found)


def normalise_invoice(
    payload: Mapping[str, Any],
    *,
    default_entity: str | None = None,
    enabled_currencies: Collection[str] = (),
) -> ports.NormalisedInvoiceDraft:
    """An invoice → ``INVOICE`` with service-period hints (ADP-17; REQ-INT-005)."""
    if str(payload.get("status", "")) not in {"open", "paid", "uncollectible", "finalized"}:
        raise ports.Permanent("only finalized invoices are ingested (drafts are not billing)")
    currency = str(payload.get("currency", "usd")).upper()
    issued = _day(payload.get("created"))
    if issued is None:
        raise ports.Permanent("the invoice has no created timestamp")
    return ports.NormalisedInvoiceDraft(
        source_system=SourceSystem.STRIPE,
        external_invoice_id=str(payload["id"]),
        external_version=str(payload.get("version", "1")),
        document_kind="INVOICE",
        invoice_number=str(payload.get("number") or payload["id"]),
        issue_date=issued,
        customer_external_id=str(payload["customer"]),
        currency=currency,
        lines=_invoice_lines(payload, currency, enabled_currencies),
        due_date=_day(payload.get("due_date")),
        legal_entity_code=(payload.get("metadata") or {}).get("legal_entity") or default_entity,
        document_ref=str(payload["id"]),
        custom_attributes={"mapping_version": MAPPING_VERSION, "status": payload.get("status")},
    )


def normalise_credit_note(
    payload: Mapping[str, Any],
    *,
    default_entity: str | None = None,
    enabled_currencies: Collection[str] = (),
) -> ports.NormalisedInvoiceDraft:
    """A credit note → ``CREDIT_MEMO`` naming the invoice it credits (``CREDIT_MEMO_RECORDED``)."""
    currency = str(payload.get("currency", "usd")).upper()
    issued = _day(payload.get("created"))
    if issued is None:
        raise ports.Permanent("the credit note has no created timestamp")
    credited = payload.get("invoice")
    if not credited:
        raise ports.Permanent("a credit note names the invoice it credits")
    return ports.NormalisedInvoiceDraft(
        source_system=SourceSystem.STRIPE,
        external_invoice_id=str(payload["id"]),
        external_version=str(payload.get("version", "1")),
        document_kind="CREDIT_MEMO",
        invoice_number=str(payload.get("number") or payload["id"]),
        issue_date=issued,
        customer_external_id=str(payload["customer"]),
        currency=currency,
        lines=_invoice_lines(payload, currency, enabled_currencies),
        legal_entity_code=(payload.get("metadata") or {}).get("legal_entity") or default_entity,
        credited_invoice_external_id=str(credited),
        document_ref=str(payload["id"]),
        custom_attributes={"mapping_version": MAPPING_VERSION},
    )


class StripeAdapter:
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
        # a test-connection probe passes 1), else the ADP-12 default — as the Salesforce adapter.
        configured = self._config.get("max_attempts", MAX_ATTEMPTS)
        self._max_attempts = max(1, int(max_attempts if max_attempts is not None else configured))
        self._max_sweep_pages = max(1, max_sweep_pages)
        self._enabled: frozenset[str] = frozenset(
            str(code).upper() for code in (self._config.get(ENABLED_CURRENCIES_KEY) or ())
        )
        self.attempts: list[tuple[str, int]] = []

    @property
    def code(self) -> ports.AdapterCode:
        return "STRIPE"

    # --- ADP-01 / ADP-14 --------------------------------------------------------------------------

    def verify_webhook(
        self, headers: Mapping[str, str], body: bytes, secret: SecretStr
    ) -> ports.WebhookNotice:
        presented = next(
            (value for name, value in headers.items() if name.lower() == SIGNATURE_HEADER.lower()),
            None,
        )
        if presented is None:
            return ports.WebhookNotice(verified=False, reason="signature header missing")
        parts = dict(part.split("=", 1) for part in presented.split(",") if "=" in part)
        timestamp, signature = parts.get("t"), parts.get("v1")
        if not timestamp or not signature:
            return ports.WebhookNotice(verified=False, reason="signature scheme incomplete")
        expected = hmac.new(
            secret.get_secret_value().encode(), f"{timestamp}.".encode() + body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature.strip().lower()):
            return ports.WebhookNotice(verified=False, reason="signature mismatch")
        # 05 ADP-01 rev 1.47 (ruling R-48 (f)): the scheme signs its timestamp, so a notification
        # is accepted only near the moment it was signed; a captured one cannot be replayed later.
        if not timestamp.isascii() or not timestamp.isdigit():
            return ports.WebhookNotice(verified=False, reason="signature timestamp malformed")
        if abs(self._now().timestamp() - int(timestamp)) > REPLAY_WINDOW_SECONDS:
            return ports.WebhookNotice(verified=False, reason="timestamp outside the replay window")
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ports.WebhookNotice(verified=False, reason="body is not JSON")
        events = parsed.get("data", parsed) if isinstance(parsed, Mapping) else parsed
        return ports.WebhookNotice(verified=True, notifications=self._notifications(events))

    @staticmethod
    def _notifications(events: Any) -> tuple[ports.Notification, ...]:
        found: list[ports.Notification] = []
        for event in events or ():
            obj = (event.get("data") or {}).get("object") or {}
            kind = EVENT_OBJECTS.get(str(obj.get("object", "")))
            if kind is None:
                continue  # an event about an object this adapter does not ingest
            found.append(
                ports.Notification(
                    notification_id=str(event["id"]),
                    object_type=kind,
                    external_id=str(obj["id"]),
                    external_version=str(obj.get("version", "1")),
                    replay_id=int(event.get("ordinal", 0)),
                )
            )
        return tuple(found)

    # --- poll and sweep ---------------------------------------------------------------------------

    def fetch_changes(self, checkpoint: ports.Checkpoint, limit: int) -> ports.ChangePage:
        now = self._now()
        cursor = checkpoint.sweep_cursor
        if cursor is not None or ports.sweep_due(checkpoint, now):
            # a sweep in progress resumes first, in its own mode (DIN-R2 residual)
            mode = str((cursor or {}).get("mode") or "RECOVERY")
            resumed: SweepMode = "INVOICES_CREATED" if mode == "INVOICES_CREATED" else "RECOVERY"
            return self.sweep(checkpoint, limit, mode=resumed)
        after = checkpoint.replay_id or 0
        body = self._get(f"/v1/events?starting_after={after}&limit={limit}")
        events = list(body.get("data", ()))
        notifications = self._notifications(events)
        # DIN-R1: the cursor advances over the complete consumed page, ignored events included.
        latest = max((int(event.get("ordinal", after)) for event in events), default=after)
        return ports.ChangePage(
            notifications=notifications,
            checkpoint=ports.Checkpoint(
                replay_id=latest,
                replay_at=now,
                last_modified_watermark=checkpoint.last_modified_watermark,
            ),
            has_more=bool(body.get("has_more", False)),
            kind="POLL",
        )

    def sweep(
        self, checkpoint: ports.Checkpoint, limit: int, *, mode: SweepMode = "RECOVERY"
    ) -> ports.ChangePage:
        """ADP-17 rev 1.12 (DIN-R2, DIN-G1). ``RECOVERY`` (the ADP-16 default behind
        ``fetch_changes``): the events feed since the watermark plus the ``created``-filtered lists
        of subscriptions, invoices and credit notes; ``INVOICES_CREATED``: the original
        creation-only invoice sweep, a distinct mode kept callable so its original expectation
        stays true. Every list is paged to exhaustion; the watermark moves to the latest consumed
        ``created`` only when every list was exhausted, else the sweep returns ``has_more`` with
        the checkpoint's watermark and replay cadence unchanged (Stripe lists are newest-first, so
        no partial timestamp is complete) and its ``sweep_cursor`` carrying the source index, the
        list's ``starting_after`` and the highest ``created`` seen, so the next call resumes exactly
        there (DIN-R2 residual)."""
        now = self._now()
        watermark = checkpoint.last_modified_watermark
        since = 0 if watermark is None else int(watermark.timestamp())
        size = max(1, min(limit, MAX_PAGE_SIZE))
        if mode == "INVOICES_CREATED":
            sources: list[tuple[str, str]] = [("invoice", f"/v1/invoices?created[gt]={since}")]
        else:
            sources = [
                ("event", f"/v1/events?created[gt]={since}"),
                *((kind, f"{path}?created[gt]={since}") for kind, path in SWEEP_LISTS),
            ]
        carried = dict(checkpoint.sweep_cursor or {})
        resuming = carried.get("source") == self.code and carried.get("mode") == mode
        start_index = min(int(carried.get("index") or 0), len(sources) - 1) if resuming else 0
        start_after = carried.get("after") if resuming else None
        stamps: list[int] = (
            [] if not resuming or carried.get("seen_max") is None else [int(carried["seen_max"])]
        )
        notifications: dict[tuple[SourceObjectType, str, str], ports.Notification] = {}
        pages = 0
        exhausted = True
        stop: tuple[int, str | None] | None = None
        for index, (kind, base_path) in enumerate(sources):
            if index < start_index:
                continue
            cursor: str | None = str(start_after) if index == start_index and start_after else None
            while True:
                path = f"{base_path}&limit={size}"
                if cursor is not None:
                    path += f"&starting_after={quote(cursor)}"
                body = self._get(path)
                pages += 1
                data = list(body.get("data", ()))
                if kind == "event":
                    for item in self._notifications(data):
                        key = (item.object_type, item.external_id, item.external_version)
                        notifications.setdefault(key, item)
                    stamps.extend(int(e["created"]) for e in data if e.get("created") is not None)
                    # the events cursor is the ordinal under the mock's committed convention
                    cursor = str(data[-1].get("ordinal", data[-1].get("id"))) if data else None
                else:
                    for record in data:
                        item = ports.Notification(
                            notification_id=f"SWEEP:{record['id']}:{record.get('version', '1')}",
                            object_type=EVENT_OBJECTS[kind],
                            external_id=str(record["id"]),
                            external_version=str(record.get("version", "1")),
                            replay_id=checkpoint.replay_id or 0,
                        )
                        key = (item.object_type, item.external_id, item.external_version)
                        notifications.setdefault(key, item)
                        if record.get("created") is not None:
                            stamps.append(int(record["created"]))
                    cursor = str(data[-1]["id"]) if data else None
                more = bool(data) and bool(body.get("has_more", False))
                if more and pages >= self._max_sweep_pages:
                    stop = (index, cursor)  # resume this list after its last consumed item
                    break
                if not more:
                    break
            if stop is not None:
                exhausted = False
                break
            if pages >= self._max_sweep_pages and index + 1 < len(sources):
                stop = (index + 1, None)  # resume at the next list
                exhausted = False
                break
        if exhausted:
            new_watermark = datetime.fromtimestamp(max(stamps), tz=UTC) if stamps else watermark
            replay_at: datetime | None = now  # the completed sweep re-baselines the cadence
            new_cursor: dict[str, Any] | None = None
        else:
            new_watermark = watermark
            replay_at = checkpoint.replay_at
            assert stop is not None
            new_cursor = {
                "source": self.code,
                "mode": mode,
                "index": stop[0],
                "after": stop[1],
                "seen_max": max(stamps) if stamps else None,
            }
        return ports.ChangePage(
            notifications=tuple(notifications.values()),
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

    # --- the truth before acting ------------------------------------------------------------------

    def fetch_object(self, object_type: SourceObjectType, external_id: str) -> ports.SourceObject:
        path = OBJECT_PATHS.get(object_type)
        if path is None:
            raise ports.Permanent(f"the Stripe adapter ingests no {object_type.value}")
        body = self._get(f"{path}/{quote(external_id)}")
        version = str(body.get("version", "1"))
        created = body.get("created")
        return ports.SourceObject(
            source_system=SourceSystem.STRIPE,
            object_type=object_type,
            external_id=str(body.get("id", external_id)),
            external_version=version,
            version_order=int(version),
            payload=body,
            last_modified=(
                None if created is None else datetime.fromtimestamp(int(created), tz=UTC)
            ),
        )

    def normalise(self, obj: ports.SourceObject, mapping_version: str) -> ports.NormalisedRecords:
        if mapping_version != MAPPING_VERSION:
            raise ports.Permanent(f"mapping version {mapping_version!r} is not supported")
        entity = self._config.get(DEFAULT_ENTITY_KEY)
        options: dict[str, Any] = {"default_entity": entity, "enabled_currencies": self._enabled}
        if obj.object_type is SourceObjectType.ORDER:
            return ports.NormalisedRecords(
                mapping_version, orders=(normalise_subscription(obj.payload, **options),)
            )
        if obj.object_type is SourceObjectType.INVOICE:
            return ports.NormalisedRecords(
                mapping_version, invoices=(normalise_invoice(obj.payload, **options),)
            )
        return ports.NormalisedRecords(
            mapping_version, invoices=(normalise_credit_note(obj.payload, **options),)
        )

    def control_totals(self, objects: Sequence[ports.SourceObject]) -> ports.ControlTotals:
        items: list[tuple[str, str, str, Decimal]] = []
        for obj in objects:
            records = self.normalise(obj, MAPPING_VERSION)
            for order in records.orders:
                items.append(
                    (obj.external_id, obj.external_version, order.transaction_currency, order.total)
                )
            for document in records.invoices:
                items.append(
                    (obj.external_id, obj.external_version, document.currency, document.total)
                )
        return ports.ControlTotals.of(items)

    # --- transport with the ADP-12 schedule ------------------------------------------------------

    def _now(self) -> datetime:
        clock = self._config.get(ports.NOW_HOOK)
        return clock() if callable(clock) else SystemClock().now()  # DG-KRN-TIME-05

    def _get(self, path: str) -> dict[str, Any]:
        last: ports.Transient | None = None
        for attempt in range(self._max_attempts):
            try:
                response = self._client.get(f"{self._base}{path}")
            except Exception as error:  # noqa: BLE001 - driver errors are transient (ADP-12)
                last = ports.Transient(f"connection error: {type(error).__name__}")
                self.attempts.append((path, 0))
            else:
                status = int(response.status_code)
                self.attempts.append((path, status))
                if status < 300:
                    body = response.json()
                    return dict(body) if isinstance(body, Mapping) else {"data": body}
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
    """Composition-root wiring (DG-LAY-03): the ``STRIPE`` factory over the context's client."""
    ports.register_inbound_adapter("STRIPE", StripeAdapter)
