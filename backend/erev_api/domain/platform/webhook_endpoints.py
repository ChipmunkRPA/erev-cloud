"""Webhook endpoints and the delivery log (04 API-R-15, T-PLT-35, T-PLT-36; 05 NTR-10 to NTR-13,
KEY-08; REQ-PLT-034; BUILD_SPEC PLF-24).

An endpoint subscribes an https URL, or ``http://127.0.0.1`` or ``http://localhost`` with a path as
the T-PLT-35 check allows for the in-process mocks, to one or more of the six event kinds. Creating
an endpoint generates its signing secret, seals it under the key ring (``secret_ciphertext``,
KEY-08) and returns it once; no read shows it again. Endpoints are never deleted: ``is_active``
false stops their deliveries. Endpoint commands are AUD-CMD; deliveries are AUD-OPS. The SAR-15
destination guard runs when a delivery resolves the host (``adapters.http.guard``).

A sandbox holds no active endpoint (05 SBX-08 rev 1.64; REQ-PLT-022; CTL-043; security finding
SF-1): an endpoint is created active, so ``create_endpoint`` is refused there, and so is an
``update_endpoint`` that would leave the endpoint active — 403 ``sandbox-restricted``, the attempt
audited ``DENIED`` in a transaction of its own (``guards.ensure_production``). Deactivating an
endpoint and editing an inactive one stay possible. ``events.webhooks`` and the DB-15 trigger
``tg_webhook_endpoint__sandbox`` refuse independently of this module.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import Select, insert, select, update
from sqlalchemy.orm import Session

from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import webhook_delivery, webhook_endpoint
from erev_api.domain.platform import guards, provisioning
from erev_api.events import webhooks
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext
    from erev_api.uow import UnitOfWork

ENDPOINT_OBJECT: Final = "webhook_endpoint"
CREATE_ACTION: Final = "webhook_endpoint.create"
UPDATE_ACTION: Final = "webhook_endpoint.update"
RULE_ENDPOINT: Final = "T-PLT-35"
URL_LENGTH: Final = 2048
SECRET_BYTES: Final = 32
URL_INVALID: Final = "Enter an https URL, or http://127.0.0.1 or http://localhost with a path."
SANDBOX_ENDPOINT: Final = (
    "Webhook endpoints are not available in a sandbox workspace; a sandbox sends no webhooks "
    "(05 SBX-08)."
)
EVENT_KINDS_INVALID: Final = "Choose one or more of " + ", ".join(webhooks.EVENT_KINDS) + "."
DESCRIPTION_LENGTH: Final = "A description has at most 400 characters."
VALUE_REQUIRED: Final = "Send a value or leave the member out."
REQUIRED_WHEN_SENT: Final = ("url", "event_kinds", "is_active")
_LOCAL_URL: Final = re.compile(r"^http://(127\.0\.0\.1|localhost)(:[0-9]+)?/")
ENDPOINT_COLUMNS: Final = (
    webhook_endpoint.c.id,
    webhook_endpoint.c.url,
    webhook_endpoint.c.description,
    webhook_endpoint.c.event_kinds,
    webhook_endpoint.c.is_active,
    webhook_endpoint.c.created_at,
    webhook_endpoint.c.updated_at,
    webhook_endpoint.c.row_version,
)
DELIVERY_COLUMNS: Final = (
    webhook_delivery.c.id,
    webhook_delivery.c.webhook_endpoint_id,
    webhook_delivery.c.event_kind,
    webhook_delivery.c.payload,
    webhook_delivery.c.payload_sha256,
    webhook_delivery.c.status,
    webhook_delivery.c.attempt_count,
    webhook_delivery.c.next_attempt_at,
    webhook_delivery.c.abandon_at,
    webhook_delivery.c.last_response_status,
    webhook_delivery.c.last_error,
    webhook_delivery.c.succeeded_at,
    webhook_delivery.c.created_at,
)


@dataclass(frozen=True, slots=True)
class CreatedEndpoint:
    endpoint: Mapping[str, Any]
    signing_secret: str  # shown once


def _url_valid(url: str) -> bool:
    if len(url) > URL_LENGTH or any(character.isspace() for character in url):
        return False
    try:
        parts = urlsplit(url)
        _ = parts.port
    except ValueError:
        return False
    if parts.username is not None or parts.password is not None or not parts.hostname:
        return False
    return url.startswith("https://") or _LOCAL_URL.match(url) is not None


def _validate(
    url: str, description: str | None, event_kinds: Sequence[str]
) -> tuple[str, str | None, list[str]]:
    """The URL, trimmed description and de-duplicated kinds, or 422 with every finding."""
    errors: list[ProblemError] = []
    if not _url_valid(url):
        errors.append(ProblemError(field="url", rule_id=RULE_ENDPOINT, message=URL_INVALID))
    text = None if description is None or not description.strip() else description.strip()
    if text is not None and len(text) not in provisioning.LABEL_LENGTH:
        errors.append(
            ProblemError(field="description", rule_id=RULE_ENDPOINT, message=DESCRIPTION_LENGTH)
        )
    kinds = list(dict.fromkeys(event_kinds))
    if not kinds or any(kind not in webhooks.EVENT_KINDS for kind in kinds):
        errors.append(
            ProblemError(field="event_kinds", rule_id=RULE_ENDPOINT, message=EVENT_KINDS_INVALID)
        )
    if errors:
        raise Problem("validation-failed", errors=errors)
    return url, text, kinds


def _read(session: Session, endpoint_id: UUID, *, lock: bool = False) -> Mapping[str, Any]:
    statement = select(*ENDPOINT_COLUMNS).where(webhook_endpoint.c.id == endpoint_id)
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return MappingProxyType(dict(row))


def _audited(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "url": row["url"],
        "description": row["description"],
        "event_kinds": list(row["event_kinds"]),
        "is_active": row["is_active"],
    }


def create_endpoint(
    uow: UnitOfWork, *, url: str, description: str | None, event_kinds: Sequence[str]
) -> CreatedEndpoint:
    """Subscribe ``url`` to ``event_kinds`` with a new signing secret, returned once (KEY-08).

    Refused in a sandbox before anything is validated, generated or written (05 SBX-08): the
    endpoint would be created active."""
    guards.ensure_production(
        uow,
        action=CREATE_ACTION,
        object_type=ENDPOINT_OBJECT,
        object_id=None,
        detail={"is_active": True},
        message=SANDBOX_ENDPOINT,
    )
    clean_url, text, kinds = _validate(url, description, event_kinds)
    principal = uow.principal
    endpoint_id = new_id()
    signing_secret = secrets.token_urlsafe(SECRET_BYTES)
    ciphertext = uow.keyring.encrypt(
        signing_secret.encode("ascii"),
        context=webhooks.secret_context(principal.tenant_id, endpoint_id),
    )
    key_id = uow.keyring.envelope_key_id(ciphertext)
    uow.session.execute(
        insert(webhook_endpoint).values(
            tenant_id=principal.tenant_id,
            id=endpoint_id,
            url=clean_url,
            description=text,
            event_kinds=kinds,
            secret_ciphertext=ciphertext,
            secret_key_id=key_id,
            is_active=True,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    row = _read(uow.session, endpoint_id)
    uow.audit(
        action=CREATE_ACTION,
        object_type=ENDPOINT_OBJECT,
        object_id=endpoint_id,
        after={**_audited(row), "secret_key_id": key_id},
    )
    return CreatedEndpoint(endpoint=row, signing_secret=signing_secret)


def update_endpoint(
    uow: UnitOfWork,
    endpoint_id: UUID,
    changes: Mapping[str, Any],
    *,
    check_version: Callable[[int], None],
) -> Mapping[str, Any]:
    """Change the URL, description, event kinds or activity of an endpoint (If-Match).

    In a sandbox a change that would leave the endpoint active is refused (05 SBX-08): an
    activation, and any edit of an endpoint that is active and stays so."""
    current = _read(uow.session, endpoint_id, lock=True)
    check_version(int(current["row_version"]))
    asked = changes.get("is_active")
    if bool(current["is_active"]) if asked is None else bool(asked):
        guards.ensure_production(
            uow,
            action=UPDATE_ACTION,
            object_type=ENDPOINT_OBJECT,
            object_id=endpoint_id,
            detail={"is_active": True, "was_active": bool(current["is_active"])},
            message=SANDBOX_ENDPOINT,
        )
    missing = [key for key in REQUIRED_WHEN_SENT if key in changes and changes[key] is None]
    if missing:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(field=key, rule_id=RULE_ENDPOINT, message=VALUE_REQUIRED)
                for key in missing
            ],
        )
    before = _audited(current)
    merged = {key: changes[key] if key in changes else before[key] for key in before}
    clean_url, text, kinds = _validate(
        str(merged["url"]), merged["description"], list(merged["event_kinds"])
    )
    after = {
        "url": clean_url,
        "description": text,
        "event_kinds": kinds,
        "is_active": bool(merged["is_active"]),
    }
    changed = {key: value for key, value in after.items() if value != before[key]}
    if changed:
        principal = uow.principal
        uow.session.execute(
            update(webhook_endpoint)
            .where(webhook_endpoint.c.id == endpoint_id)
            .values(
                **changed,
                updated_at=uow.now,
                updated_by=principal.id,
                updated_by_kind=principal.kind.value,
            )
        )
        uow.audit(
            action=UPDATE_ACTION,
            object_type=ENDPOINT_OBJECT,
            object_id=endpoint_id,
            before=before,
            after=after,
        )
    return _read(uow.session, endpoint_id)


def get_endpoint(ctx: RequestContext, endpoint_id: UUID) -> Mapping[str, Any]:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return _read(session, endpoint_id)


def list_endpoints[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the workspace's endpoints; ``page`` applies the list parameters."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*ENDPOINT_COLUMNS))


def list_deliveries[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the delivery log; ``page`` applies the list parameters."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, select(*DELIVERY_COLUMNS))
