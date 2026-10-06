"""API-R-45 commands: connections, test connection, sync requests and the webhook receiver (04
§15.3 API-R-45; T-INT-01, T-INT-02; 05 ADP-01, ADP-14; 03 REQ-INT-006; PRD BR-INT-01, J-23.1,
J-23.4; SCREENS SF-16; BUILD_SPEC DIN-12).

``create_connection`` / ``update_connection`` write the T-INT-01 row (IM-M; AUD-CMD with field-level
``before`` / ``after``; the DB-15 trigger refuses an ACTIVE outbound adapter other than ``CSV_GL``
in a sandbox tenant). ``secret_ref`` is the NAME of a key-provider secret and is stored as given;
it names a secret of the workspace's own namespace of the secret store, ``tenant-<tenant id>-…``,
and any other reference is refused with 422 (04 T-INT-01 rev 1.108; security review P3-23). The
value is read only at call time by ``sync.probe_connection`` and the webhook receiver (ADP-14,
REQ-INT-006) and is never written, returned or logged.

``test_connection`` runs ``sync.probe_connection`` synchronously (API-R-45 "sync"), records
``last_test_at`` (the unit of work's UTC instant), ``last_test_result`` and ``last_test_detail``,
and writes a ``TEST_CONNECTION`` sync run so the ledger keeps every test (J-23.1). In a sandbox
the test of an adapter that calls out is refused before the probe (05 SBX-08 rev 1.116).

``request_sync`` inserts a QUEUED T-INT-02 row whose ``job_id`` names the ``SYNC_RUN`` job deferred
in the same transaction (DG-KRN-JOB-02); the job's params carry the run id, the connection id, the
kind and — for a ``WEBHOOK_BATCH`` — the verified notifications, since T-INT-02 has no payload
column. ``receive_webhook`` is the ADP-01 receiver: the route resolves the tenant from the receiver
id (``receiver_id`` ‖ ``parse_receiver_id``, the ``erevc_<tenant hex>_…`` client-id pattern of
API-R-02), verifies the signature with the adapter, and this command stores nothing but the
``WEBHOOK_BATCH`` run and the deferred job.

A command on a connection takes the row through ``queries.get_connection_in_reach``: the caller's
scope of the command's permission covers every entity the connection serves, or the answer is 404
(04 API-C-03 rev 1.243). ``create_connection`` and a change of ``entity_ids`` hold the entities
named to the caller's own scope (``_entity_findings``). The worker's paths act as SYSTEM, which
covers every entity.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import DBAPIError

from erev_api.audit import writer as audit_writer
from erev_api.auth import entity_scope
from erev_api.auth.keyring import adapter_secret_namespace, in_adapter_namespace
from erev_api.db import new_id
from erev_api.db.tables import (
    contract,
    customer,
    dimension_value,
    external_id_map,
    gl_account,
    integration_connection,
    journal_batch,
    legal_entity,
    obligation,
    product,
    sync_run,
)
from erev_api.domain.integrations import ports, queries
from erev_api.domain.integrations import sync as sync_module
from erev_api.domain.platform import guards
from erev_api.enums import JobKind, SyncRunStatus
from erev_api.problems import Problem, ProblemError, from_db_error
from erev_api.schemas.integrations import ExternalIdMapIn, IntegrationConnectionIn
from erev_api.uow import UnitOfWork

__all__ = [
    "CONNECTION_OBJECT",
    "CREATE_ACTION",
    "INBOUND_KINDS",
    "MAINTAIN_PERMISSION",
    "MANAGE_PERMISSION",
    "RECEIVER_PATTERN",
    "RECEIVER_PREFIX",
    "SYNC_REQUEST_ACTION",
    "SYNC_RUN_OBJECT",
    "TEST_ACTION",
    "UPDATE_ACTION",
    "WEBHOOK_ACTION",
    "RequestedSync",
    "base_url_refusal",
    "create_connection",
    "create_external_id",
    "is_inbound",
    "parse_receiver_id",
    "receive_webhook",
    "receiver_id",
    "refuse_inbound_in_sandbox",
    "refuse_probe_in_sandbox",
    "request_sync",
    "test_connection",
    "update_connection",
]

CONNECTION_OBJECT: Final = queries.CONNECTION_OBJECT
SYNC_RUN_OBJECT: Final = queries.SYNC_RUN_OBJECT
CREATE_ACTION: Final = "integration_connection.create"
UPDATE_ACTION: Final = "integration_connection.update"
TEST_ACTION: Final = "integration_connection.test"
SYNC_REQUEST_ACTION: Final = "sync_run.request"
WEBHOOK_ACTION: Final = "sync_run.webhook"
# 04 API-R-45: the connections and their runs; an alias of a record under a connection (rev 1.81).
MANAGE_PERMISSION: Final = "integration.manage"
MAINTAIN_PERMISSION: Final = "masterdata.maintain"

RULE_CONNECTION: Final = "T-INT-01"
RULE_SYNC_RUN: Final = "T-INT-02"
CODE_TAKEN: Final = "A connection with this code already exists."
NAME_REQUIRED: Final = "Enter a name."
SECRET_REF_NAMESPACE: Final = (
    "Enter the name of a secret of this workspace. It begins with {prefix} and continues after it."
)
ENTITY_UNKNOWN: Final = "entity_ids name no legal entity of this workspace: {ids}."
CONNECTION_DISABLED: Final = "The connection is DISABLED; enable it before running a sync."
BASE_URL_REFUSED: Final = "Enter a public https address as the base URL: {reason}."
# 05 SAR-15 static form: names that never leave the host or the site (``controls.doctor`` applies
# the same suffixes to the deployment's own URLs, SAR-40).
LOCAL_NAME_SUFFIXES: Final = (".localhost", ".local", ".internal")
# A DNS name as a base URL may write it: ASCII labels of letters, digits, hyphens and underscores
# (an internationalised name is entered in its ``xn--`` form). Anything else — a backslash, a
# percent escape, a full-width digit that a resolver's mapping would fold into an address — is
# refused, not interpreted.
_DNS_NAME: Final = re.compile(r"[a-z0-9_-]+(\.[a-z0-9_-]+)*")
# A last label that is a number makes the host an IPv4 address to a resolver (``127.1``,
# ``0x7f.0.0.1``, ``10.0.513``); only the dotted-decimal form is read as an address here.
_NUMBER_LABEL: Final = re.compile(r"[0-9]+|0x[0-9a-f]*")
KIND_NOT_INBOUND: Final = (
    "{kind} is not a run kind of an inbound {adapter} connection in this release."
)
KIND_NOT_CHART: Final = (
    "{kind} is a run kind of a connection whose adapter serves a chart of accounts; {adapter}"
    " does not in this release."
)
TEST_KIND_REFUSED: Final = "Use POST /integrations/{{id}}/test for a TEST_CONNECTION run."
WEBHOOK_KIND_REFUSED: Final = (
    "A WEBHOOK_BATCH run is created by the webhook receiver, not requested (05 ADP-01)."
)

# Run kinds an inbound CRM / billing connection accepts through ``/sync`` (T-INT-02 CHECK list);
# COA_SYNC is a GL connection's (DIN-14), TRIAL_BALANCE_PULL is CLO-15's, JOURNAL_EXPORT the
# relay's (ADP-30).
INBOUND_KINDS: Final = frozenset({"INBOUND_POLL", "RECONCILIATION_SWEEP", "WEBHOOK_BATCH"})
INBOUND_ADAPTERS: Final = frozenset({"SALESFORCE", "STRIPE"})
# The run kind of a chart-of-accounts sync and the GL adapters that serve a chart (03 REQ-INT-008;
# BUILD_SPEC DIN-14): NetSuite; QuickBooks Online has no adapter in 1.0 and CSV_GL has no chart.
CHART_KIND: Final = "COA_SYNC"
CHART_ADAPTERS: Final = ports.CHART_ADAPTERS
INBOUND_DIRECTIONS: Final = frozenset({"INBOUND", "BOTH"})
SANDBOX_INBOUND: Final = (
    "Inbound integration connections are not available in a sandbox workspace (05 SBX-08)."
)
SANDBOX_OUTBOUND: Final = (
    "Outbound adapters cannot be activated in a sandbox workspace; only CSV exports leave a "
    "sandbox (05 SBX-08)."
)
SANDBOX_PROBE: Final = (
    "A connection cannot be tested in a sandbox workspace: a sandbox reaches no external system "
    "(05 SBX-08)."
)
# The one outbound adapter a sandbox may hold ACTIVE: a download, never a call (04 DB-15).
SANDBOX_OUTBOUND_ADAPTER: Final = "CSV_GL"
WEBHOOK_BATCH: Final = "WEBHOOK_BATCH"

# ADP-01 receiver id: the API-R-02 client-id pattern (``erevc_<tenant hex32>_…``) applied to a
# connection — derived from the row, never stored (pending team-lead's Q-A ruling on the name).
RECEIVER_PREFIX: Final = "erevw_"
RECEIVER_PATTERN: Final = re.compile(r"erevw_([0-9a-f]{32})_([0-9a-f]{32})")

AUDITED_MEMBERS: Final = (
    "code",
    "name",
    "adapter",
    "direction",
    "entity_ids",
    "base_url",
    "config",
    "secret_ref",
    "status",
)
UPDATABLE_MEMBERS: Final = frozenset(
    {"name", "entity_ids", "base_url", "config", "secret_ref", "status"}
)


def base_url_refusal(url: str) -> str | None:
    """Why ``url`` fails the STATIC form of 05 SAR-15, or None when it passes (04 T-INT-01 rev
    1.115; ruling R-45 (c)): scheme ``https``; no credentials; a host; and that host neither a
    literal address that is not global unicast (loopback, private, link-local, shared, reserved,
    unspecified, multicast — an IPv4-mapped IPv6 address is judged by its IPv4 address) nor
    ``localhost``, a ``.localhost``, ``.local`` or ``.internal`` name, or a single-label name.
    A host that is no dotted-decimal or IPv6 literal must be a DNS name in ASCII whose last label
    is not a number: the other ways of writing an address (``127.1``, ``0x7f.0.0.1``, full-width
    digits) are refused, not interpreted. Nothing is resolved here: the resolving guard runs at
    every connection (``adapters.http.guard``); this is the first refusal, at save."""
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port_valid = parts.port is None or 0 < parts.port < 65536
    except ValueError:
        return "it is not a URL"
    if parts.scheme.lower() != "https":
        return "it does not use https"
    if parts.username is not None or parts.password is not None:
        return "it carries credentials"
    if not host:
        return "it names no host"
    if not port_valid:
        return "its port is not valid"
    try:
        address: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(host)
    except ValueError:
        name = host.lower().rstrip(".")
        if name == "localhost" or name.endswith(LOCAL_NAME_SUFFIXES):
            return "it names a local host"
        if _DNS_NAME.fullmatch(name) is None:
            return "its host is not a DNS name in ASCII letters, digits, hyphens and dots"
        if "." not in name:
            return "it names a single-label host"
        if _NUMBER_LABEL.fullmatch(name.rsplit(".", 1)[1]) is not None:
            return "it writes an address in a form other than dotted decimal"
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if not address.is_global or address.is_multicast or address.is_reserved:
        return "it names a loopback, private, link-local or otherwise non-public address"
    return None


def _base_url_errors(base_url: Any, *, local_destinations: bool) -> list[ProblemError]:
    """``base_url`` at create and update: no rule in ``dev``, ``test`` and ``e2e`` (the in-process
    mock URLs); under production the static SAR-15 form, 422 naming why."""
    if local_destinations or base_url is None:
        return []
    reason = base_url_refusal(str(base_url))
    if reason is None:
        return []
    return [
        ProblemError(
            field="base_url",
            rule_id=RULE_CONNECTION,
            message=BASE_URL_REFUSED.format(reason=reason),
        )
    ]


def is_inbound(adapter: str, direction: str) -> bool:
    """An inbound connection (SBX-08): an inbound or two-way direction, or a CRM / billing
    adapter."""
    return direction in INBOUND_DIRECTIONS or adapter in INBOUND_ADAPTERS


def refuse_inbound_in_sandbox(
    uow: UnitOfWork,
    *,
    action: str,
    object_type: str,
    object_id: UUID | None,
    detail: Mapping[str, Any],
) -> None:
    """05 SBX-08 (REQ-PLT-022, CTL-043; Codex 0339 §3 DIN12-SANDBOX-ADMISSION-1): in a sandbox an
    inbound connection cannot be created, activated, synced or fed by a webhook — 403
    ``sandbox-restricted``, the attempt audited DENIED in a transaction of its own (the
    ``journals.export`` pattern); DB-15 guards the outbound side."""
    guards.ensure_production(
        uow,
        action=action,
        object_type=object_type,
        object_id=object_id,
        detail=detail,
        message=SANDBOX_INBOUND,
    )


def refuse_activation_in_sandbox(
    uow: UnitOfWork, *, connection_id: UUID, adapter: str, direction: str
) -> None:
    """05 SBX-08 rev 1.64 (REQ-PLT-022, CTL-043): the one connection a sandbox may hold ACTIVE is
    the ``CSV_GL`` export. An inbound connection is refused as on creation. An outbound adapter
    other than ``CSV_GL`` was refused only by the DB-15 trigger
    ``tg_integration_connection__sandbox`` — inside the command's transaction, which rolled the
    evidence back with it; the guard refuses first, 403 ``sandbox-restricted`` with the attempt
    audited ``DENIED`` in a transaction of its own, and the trigger stays the last line."""
    inbound = is_inbound(adapter, direction)
    if not inbound and adapter == SANDBOX_OUTBOUND_ADAPTER:
        return
    guards.ensure_production(
        uow,
        action=UPDATE_ACTION,
        object_type=CONNECTION_OBJECT,
        object_id=connection_id,
        detail={"status": "ACTIVE", "adapter": adapter, "direction": direction},
        message=SANDBOX_INBOUND if inbound else SANDBOX_OUTBOUND,
    )


def refuse_probe_in_sandbox(
    uow: UnitOfWork, *, connection_id: UUID, adapter: str, direction: str
) -> None:
    """05 SBX-08 rev 1.116 (item SBX-PROBE-1; REQ-PLT-022, CTL-043): a sandbox reaches no external
    system, a probe included. The test of every adapter that calls out — every adapter but
    ``CSV_GL``, whose export is a download — is refused before the secret store is asked and
    before a request leaves: 403 ``sandbox-restricted``, the attempt audited ``DENIED`` in a
    transaction of its own. A new adapter is refused until it is named here as one that calls
    nothing."""
    if adapter == SANDBOX_OUTBOUND_ADAPTER:
        return
    guards.ensure_production(
        uow,
        action=TEST_ACTION,
        object_type=CONNECTION_OBJECT,
        object_id=connection_id,
        detail={"adapter": adapter, "direction": direction},
        message=SANDBOX_PROBE,
    )


def receiver_id(tenant_id: UUID, connection_id: UUID) -> str:
    """The webhook receiver id of a connection: the ``{connection_id}`` path segment of ``POST
    /webhooks/{adapter}/{connection_id}``."""
    return f"{RECEIVER_PREFIX}{tenant_id.hex}_{connection_id.hex}"


def parse_receiver_id(value: str) -> tuple[UUID, UUID] | None:
    """``(tenant_id, connection_id)`` of a receiver id, or None for any other string."""
    match = RECEIVER_PATTERN.fullmatch(value)
    if match is None:
        return None
    return UUID(hex=match.group(1)), UUID(hex=match.group(2))


# --- helpers --------------------------------------------------------------------------------------


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _touch(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _audited(row: Mapping[str, Any]) -> dict[str, Any]:
    """The AUD-CMD ``before`` / ``after`` members of a connection (never a secret value: the row
    holds only ``secret_ref``, the reference name)."""
    out: dict[str, Any] = {}
    for member in AUDITED_MEMBERS:
        value = row.get(member)
        if member == "entity_ids":
            out[member] = [str(item) for item in (value or ())]
        elif member == "config":
            out[member] = dict(value or {})
        else:
            out[member] = value
    return out


def _entity_findings(
    uow: UnitOfWork, entity_ids: Sequence[UUID]
) -> tuple[list[ProblemError], bool | None]:
    """The findings of the entities a connection is to serve, and whether the request reached
    beyond the caller's own ``integration.manage`` (None when it did not; True when it asked for
    every entity; False when it named an entity that is not among the caller's).

    Every id names a legal entity of the tenant (the DB-12 rule of ``role_assignment.entity_ids``
    applied in Python; T-INT-01 has no trigger for it), and nobody makes a connection serve more
    than their own access covers (03 REQ-PLT-012; the supervisor's ruling of 2026-10-01 on item
    SCOPE-WORKSPACE-LISTS-1 (c2)): a holder of named entities names only those, and the empty
    list — every entity — is for a holder of all entities. An entity outside the caller's scope
    answers exactly as an id that names none, as a grant's entity does (``auth.entity_scope``) —
    and is recorded alike: for a holder of named entities the two are one case, because the
    session reads no entity outside its own.
    Measured before: an Integration Admin of one entity created a connection serving every
    entity and re-pointed another entity's connection to his own."""
    held = entity_scope.held_scope(uow.principal, MANAGE_PERMISSION)
    wanted = {UUID(str(value)) for value in entity_ids}
    if not wanted:
        if held == "*":
            return [], None
        finding = ProblemError(
            field="entity_ids", rule_id=RULE_CONNECTION, message=entity_scope.BEYOND_OWN_SCOPE
        )
        return [finding], True
    known = {
        UUID(str(value))
        for value in uow.session.scalars(
            select(legal_entity.c.id).where(legal_entity.c.id.in_(sorted(wanted)))
        )
    }
    beyond = held != "*" and bool(wanted - held)
    if held != "*":
        known &= held
    unknown = sorted(str(value) for value in wanted - known)
    if not unknown:
        return [], None
    finding = ProblemError(
        field="entity_ids",
        rule_id=RULE_CONNECTION,
        message=ENTITY_UNKNOWN.format(ids=", ".join(unknown)),
    )
    return [finding], (False if beyond else None)


def _refuse(
    uow: UnitOfWork,
    errors: Sequence[ProblemError],
    *,
    beyond: bool | None,
    action: str,
    connection_id: UUID | None,
) -> Problem:
    """The 422 of a connection's findings. A request that reached beyond the caller's own scope is
    recorded first as a denial of the command, in a transaction of its own (DG-KRN-AUTH-05), with
    the rule and, when it asked for every entity, the scope; like the answer the event names no
    entity."""
    if beyond is not None:
        audit_writer.record_denied(
            uow.ctx,
            action=action,
            object_type=CONNECTION_OBJECT,
            object_id=connection_id,
            permission=MANAGE_PERMISSION,
            detail={"rule_id": RULE_CONNECTION, **({"scope": "*"} if beyond else {})},
            keyring=uow.keyring,
        )
    return _failed(errors)


def _secret_ref_errors(uow: UnitOfWork, secret_ref: str | None) -> list[ProblemError]:
    """422 when the reference names a secret outside the workspace's own namespace of the secret
    store (04 T-INT-01 rev 1.108; 05 KEY-09; ruling R-48 (f)); the key ring refuses the same
    reference again when it is read. A connection without a reference sends no credential."""
    if secret_ref is None or in_adapter_namespace(secret_ref, uow.principal.tenant_id):
        return []
    return [
        ProblemError(
            field="secret_ref",
            rule_id=RULE_CONNECTION,
            message=SECRET_REF_NAMESPACE.format(
                prefix=adapter_secret_namespace(uow.principal.tenant_id)
            ),
        )
    ]


def _code_errors(uow: UnitOfWork, code: str) -> list[ProblemError]:
    taken = uow.session.execute(
        select(integration_connection.c.id).where(integration_connection.c.code == code)
    ).scalar_one_or_none()
    if taken is None:
        return []
    return [ProblemError(field="code", rule_id=RULE_CONNECTION, message=CODE_TAKEN)]


def _failed(errors: Sequence[ProblemError]) -> Problem:
    count = len(errors)
    return Problem(
        "validation-failed",
        f"{count} field{'s' if count != 1 else ''} need{'s' if count == 1 else ''} attention.",
        errors=errors,
    )


def _execute(uow: UnitOfWork, statement: Any) -> Any:
    """Execute, mapping a database refusal (the DB-15 sandbox trigger, a CHECK) to its problem."""
    try:
        return uow.session.execute(statement)
    except DBAPIError as error:
        problem = from_db_error(error, method="PATCH")
        if problem is None:
            raise
        raise problem from error


# --- connections ----------------------------------------------------------------------------------


def create_connection(
    uow: UnitOfWork, body: IntegrationConnectionIn, *, local_destinations: bool = False
) -> dict[str, Any]:
    """``POST /integrations`` (201): a DISABLED T-INT-01 row with an empty checkpoint; an inbound
    connection is refused in a sandbox (SBX-08). ``local_destinations`` is true only where the
    deployment runs as ``dev``, ``test`` or ``e2e`` — the caller says so; a caller that does not
    gets the production rule — and lifts the static SAR-15 form of ``base_url`` for the
    in-process mocks (04 T-INT-01 rev 1.115)."""
    if is_inbound(body.adapter, body.direction):
        refuse_inbound_in_sandbox(
            uow,
            action=CREATE_ACTION,
            object_type=CONNECTION_OBJECT,
            object_id=None,
            detail={"code": body.code, "adapter": body.adapter, "direction": body.direction},
        )
    entity_errors, beyond = _entity_findings(uow, body.entity_ids)
    errors = (
        _code_errors(uow, body.code)
        + entity_errors
        + _base_url_errors(body.base_url, local_destinations=local_destinations)
        + _secret_ref_errors(uow, body.secret_ref)
    )
    if errors:
        raise _refuse(uow, errors, beyond=beyond, action=CREATE_ACTION, connection_id=None)
    values: dict[str, Any] = {
        "tenant_id": uow.principal.tenant_id,
        "id": new_id(),
        "code": body.code,
        "name": body.name,
        "adapter": body.adapter,
        "direction": body.direction,
        "entity_ids": [UUID(str(value)) for value in body.entity_ids],
        "base_url": body.base_url,
        "config": dict(body.config),
        "secret_ref": body.secret_ref,
        "status": "DISABLED",
        "checkpoint": {},
        "last_test_at": None,
        "last_test_result": None,
        "last_test_detail": None,
        **_created(uow),
        "row_version": 1,
    }
    _execute(uow, insert(integration_connection).values(**values))
    uow.audit(
        action=CREATE_ACTION,
        object_type=CONNECTION_OBJECT,
        object_id=values["id"],
        object_version="1",
        after=_audited(values),
    )
    return queries.connection_out(values, None)


def update_connection(
    uow: UnitOfWork,
    connection_id: UUID,
    changes: Mapping[str, Any],
    *,
    check_version: Callable[[int], None],
    local_destinations: bool = False,
) -> dict[str, Any]:
    """``PATCH /integrations/{id}`` (If-Match), 404 for a connection out of the caller's reach:
    the members sent replace the stored values, and ``entity_ids`` stays within the caller's own
    scope — nobody re-points a connection to entities they do not hold, or to every entity. In a
    sandbox only the ``CSV_GL`` export is activated — every other activation is refused and
    audited by ``refuse_activation_in_sandbox``, with the DB-15 trigger behind it; a ``base_url``
    sent is held to the rule of ``create_connection``."""
    unknown = sorted(set(changes) - UPDATABLE_MEMBERS)
    if unknown:
        raise _failed(
            [
                ProblemError(field=key, rule_id=RULE_CONNECTION, message="This member is fixed.")
                for key in unknown
            ]
        )
    current = queries.get_connection_in_reach(
        uow.session, uow.principal, MANAGE_PERMISSION, connection_id, lock=True
    )
    check_version(int(current["row_version"]))
    if changes.get("status") == "ACTIVE":
        refuse_activation_in_sandbox(
            uow,
            connection_id=connection_id,
            adapter=str(current["adapter"]),
            direction=str(current["direction"]),
        )
    errors: list[ProblemError] = []
    beyond: bool | None = None
    if "name" in changes and changes["name"] is None:
        errors.append(ProblemError(field="name", rule_id=RULE_CONNECTION, message=NAME_REQUIRED))
    if "entity_ids" in changes:
        # a null list is the empty list: the connection would serve every entity
        entity_errors, beyond = _entity_findings(uow, changes["entity_ids"] or ())
        errors += entity_errors
    if "base_url" in changes:
        errors += _base_url_errors(changes["base_url"], local_destinations=local_destinations)
    if "secret_ref" in changes:
        errors += _secret_ref_errors(uow, changes["secret_ref"])
    if errors:
        raise _refuse(uow, errors, beyond=beyond, action=UPDATE_ACTION, connection_id=connection_id)
    before = _audited(current)
    after_values: dict[str, Any] = {}
    for key in sorted(changes):
        value = changes[key]
        if key == "entity_ids":
            after_values[key] = [UUID(str(item)) for item in (value or ())]
        elif key == "config":
            after_values[key] = dict(value or {})
        else:
            after_values[key] = value
    merged = {**dict(current), **after_values}
    after = _audited(merged)
    changed = {key: after_values[key] for key in after_values if after[key] != before[key]}
    if not changed:
        latest = queries.latest_sync_runs(uow.session, [connection_id])
        return queries.connection_out(current, latest.get(connection_id))
    row = (
        _execute(
            uow,
            update(integration_connection)
            .where(integration_connection.c.id == connection_id)
            .values(**changed, **_touch(uow))
            .returning(*integration_connection.c),
        )
        .mappings()
        .one()
    )
    uow.audit(
        action=UPDATE_ACTION,
        object_type=CONNECTION_OBJECT,
        object_id=connection_id,
        object_version=str(int(row["row_version"])),
        before={key: before[key] for key in changed},
        after={key: after[key] for key in changed},
    )
    latest = queries.latest_sync_runs(uow.session, [connection_id])
    return queries.connection_out(row, latest.get(connection_id))


# --- test connection ------------------------------------------------------------------------------


def _insert_run(
    uow: UnitOfWork,
    *,
    run_id: UUID,
    connection: Mapping[str, Any],
    kind: str,
    status: SyncRunStatus,
    job_id: UUID | None,
    **values: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "tenant_id": uow.principal.tenant_id,
        "id": run_id,
        "integration_connection_id": connection["id"],
        "kind": kind,
        "status": status.value,
        "checkpoint_before": dict(connection["checkpoint"] or {}),
        "checkpoint_after": None,
        "source_totals": None,
        "loaded_totals": None,
        "record_count": 0,
        "exception_count": 0,
        "problem": None,
        "job_id": job_id,
        "started_at": None,
        "finished_at": None,
        **values,
        **_created(uow),
        "row_version": 1,
    }
    _execute(uow, insert(sync_run).values(**row))
    return row


def test_connection(
    uow: UnitOfWork,
    connection_id: UUID,
    *,
    probe: Callable[[UnitOfWork, Mapping[str, Any]], sync_module.ProbeResult] | None = None,
) -> dict[str, Any]:
    """``POST /integrations/{id}/test``, 404 for a connection out of the caller's reach: probe the
    source through the adapter and the secret store, record ``last_test_*`` (UTC) and a
    ``TEST_CONNECTION`` sync run (REQ-INT-006; BR-INT-01). In a sandbox an adapter that calls out
    is not probed (``refuse_probe_in_sandbox``)."""
    current = queries.get_connection_in_reach(
        uow.session, uow.principal, MANAGE_PERMISSION, connection_id, lock=True
    )
    refuse_probe_in_sandbox(
        uow,
        connection_id=connection_id,
        adapter=str(current["adapter"]),
        direction=str(current["direction"]),
    )
    outcome = (probe or sync_module.probe_connection)(uow, current)
    row = (
        _execute(
            uow,
            update(integration_connection)
            .where(integration_connection.c.id == connection_id)
            .values(
                last_test_at=uow.now,
                last_test_result=outcome.result,
                last_test_detail=outcome.detail,
                **_touch(uow),
            )
            .returning(*integration_connection.c),
        )
        .mappings()
        .one()
    )
    succeeded = outcome.result == "SUCCESS"
    run_id = new_id()
    run = _insert_run(
        uow,
        run_id=run_id,
        connection=current,
        kind="TEST_CONNECTION",
        status=SyncRunStatus.SUCCEEDED if succeeded else SyncRunStatus.FAILED,
        job_id=None,
        started_at=uow.now,
        finished_at=uow.now,
        # SYNC-PROBLEM-SHAPE-1 (04 T-INT-02 rev 1.90; PRD ERR-57): the T-PLT-27 envelope.
        problem=None
        if succeeded
        else sync_module.run_problem(
            sync_module.CONNECTION_TEST_FAILED,
            sync_module.PROBE_FAILED_DETAIL.format(reason=outcome.detail),
            run_id=run_id,
            failures=[],
        ),
    )
    uow.audit(
        action=TEST_ACTION,
        object_type=CONNECTION_OBJECT,
        object_id=connection_id,
        object_version=str(int(row["row_version"])),
        after={
            "last_test_result": outcome.result,
            "last_test_at": uow.now.isoformat(),
            "sync_run_id": str(run["id"]),
        },
    )
    return queries.connection_out(row, run)


# --- external ids (04 §16.14 rev 1.81) ------------------------------------------------------------

LINK_OBJECT: Final = queries.EXTERNAL_ID_OBJECT
INTERNAL_UNKNOWN: Final = "No {object_type} has this id."
_TARGET_TABLES: Final[Mapping[str, Any]] = {
    "legal_entity": legal_entity,
    "gl_account": gl_account,
    "dimension_value": dimension_value,
    "customer": customer,
    "product": product,
    "contract": contract,
    "obligation": obligation,
    "journal_batch": journal_batch,
}


def create_external_id(uow: UnitOfWork, body: ExternalIdMapIn) -> dict[str, Any]:
    """``POST /external-ids`` (201): the live T-INT-04 link of ``external_id`` to ``internal_id``
    under a connection the caller reaches with ``masterdata.maintain``, 404 otherwise (AUD-FACT
    through ``sync.link_external_id``, which closes the superseded live link of the same external
    or internal id); the internal id must name a row of its object type (422)."""
    connection = queries.get_connection_in_reach(
        uow.session, uow.principal, MAINTAIN_PERMISSION, body.integration_connection_id
    )
    target = _TARGET_TABLES[body.object_type]
    found = uow.session.execute(
        select(target.c.id).where(target.c.id == body.internal_id)
    ).scalar_one_or_none()
    if found is None:
        raise _failed(
            [
                ProblemError(
                    field="internal_id",
                    rule_id="T-INT-04",
                    message=INTERNAL_UNKNOWN.format(object_type=body.object_type),
                )
            ]
        )
    connection_id = UUID(str(connection["id"]))
    sync_module.link_external_id(
        uow,
        connection_id,
        object_type=body.object_type,
        internal_id=body.internal_id,
        external_id=body.external_id,
        external_version=body.external_version,
        sync_run_id=None,
    )
    row = (
        uow.session.execute(
            select(external_id_map).where(
                external_id_map.c.integration_connection_id == connection_id,
                external_id_map.c.object_type == body.object_type,
                external_id_map.c.external_id == body.external_id,
                external_id_map.c.valid_to.is_(None),
            )
        )
        .mappings()
        .one()
    )
    return queries.external_id_out(dict(row))


# --- sync requests --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequestedSync:
    """What ``request_sync`` / ``receive_webhook`` created: the run row and its job id."""

    run: Mapping[str, Any]
    job_id: UUID

    @property
    def run_id(self) -> UUID:
        return UUID(str(self.run["id"]))


def _kind_errors(connection: Mapping[str, Any], kind: str) -> list[ProblemError]:
    adapter = str(connection["adapter"])
    if kind == "TEST_CONNECTION":
        return [ProblemError(field="kind", rule_id=RULE_SYNC_RUN, message=TEST_KIND_REFUSED)]
    if kind == WEBHOOK_BATCH:
        return [ProblemError(field="kind", rule_id=RULE_SYNC_RUN, message=WEBHOOK_KIND_REFUSED)]
    if kind == CHART_KIND:
        if adapter in CHART_ADAPTERS:
            return []
        return [
            ProblemError(
                field="kind",
                rule_id=RULE_SYNC_RUN,
                message=KIND_NOT_CHART.format(kind=kind, adapter=adapter),
            )
        ]
    if kind not in INBOUND_KINDS or adapter not in INBOUND_ADAPTERS:
        return [
            ProblemError(
                field="kind",
                rule_id=RULE_SYNC_RUN,
                message=KIND_NOT_INBOUND.format(kind=kind, adapter=adapter),
            )
        ]
    return []


def _queue_run(
    uow: UnitOfWork,
    connection: Mapping[str, Any],
    *,
    kind: str,
    action: str,
    notifications: Sequence[Mapping[str, Any]] | None,
    extra_params: Mapping[str, Any] | None = None,
) -> RequestedSync:
    run_id = new_id()
    params: dict[str, Any] = {
        "sync_run_id": str(run_id),
        "connection_id": str(connection["id"]),
        "kind": kind,
    }
    if notifications is not None:
        params["notifications"] = [dict(item) for item in notifications]
    if extra_params:
        # 04 §16.14 rev 1.81: a reprocess run is INBOUND_POLL with ``source_record_ids`` and
        # ``exception_item_id``; the params mark it as a reprocess.
        params.update({key: value for key, value in extra_params.items() if key not in params})
    deferred = uow.defer(JobKind.SYNC_RUN, params, subject_type=SYNC_RUN_OBJECT, subject_id=run_id)
    job_id = UUID(str(deferred["id"]))
    run = _insert_run(
        uow,
        run_id=run_id,
        connection=connection,
        kind=kind,
        status=SyncRunStatus.QUEUED,
        job_id=job_id,
    )
    uow.audit(
        action=action,
        object_type=SYNC_RUN_OBJECT,
        object_id=run_id,
        object_version="1",
        after={
            "integration_connection_id": str(connection["id"]),
            "kind": kind,
            "job_id": str(job_id),
            "notifications": 0 if notifications is None else len(notifications),
        },
    )
    return RequestedSync(run=run, job_id=job_id)


def request_sync(uow: UnitOfWork, connection_id: UUID, *, kind: str) -> RequestedSync:
    """``POST /integrations/{id}/sync`` (202) and the ``SYNC_REQUEST`` outbox handler: a QUEUED
    T-INT-02 row of ``kind`` and its ``SYNC_RUN`` job; a connection out of the caller's reach is
    404 (the handler acts as SYSTEM), a DISABLED connection is 409 ``invalid-transition``, a kind
    the connection cannot run 422."""
    connection = queries.get_connection_in_reach(
        uow.session, uow.principal, MANAGE_PERMISSION, connection_id, lock=True
    )
    if is_inbound(str(connection["adapter"]), str(connection["direction"])):
        refuse_inbound_in_sandbox(
            uow,
            action=SYNC_REQUEST_ACTION,
            object_type=SYNC_RUN_OBJECT,
            object_id=None,
            detail={"integration_connection_id": str(connection_id), "kind": kind},
        )
    errors = _kind_errors(connection, kind)
    if errors:
        raise _failed(errors)
    if str(connection["status"]) != "ACTIVE":
        raise Problem(
            "invalid-transition",
            errors=[
                ProblemError(field="status", rule_id=RULE_CONNECTION, message=CONNECTION_DISABLED)
            ],
        )
    return _queue_run(uow, connection, kind=kind, action=SYNC_REQUEST_ACTION, notifications=None)


def notification_params(notifications: Sequence[ports.Notification]) -> list[dict[str, Any]]:
    """The job-params form of verified notifications (ADP-01)."""
    return [
        {
            "notification_id": item.notification_id,
            "object_type": item.object_type.value,
            "external_id": item.external_id,
            "external_version": item.external_version,
            "replay_id": item.replay_id,
        }
        for item in notifications
    ]


def receive_webhook(
    uow: UnitOfWork, connection: Mapping[str, Any], notice: ports.WebhookNotice
) -> RequestedSync:
    """ADP-01: a verified webhook stores nothing but a ``WEBHOOK_BATCH`` sync run with the
    notification ids (in its job's params) and defers ``SYNC_RUN``; the job fetches every object
    from the source before acting."""
    if not notice.verified:
        raise ValueError("receive_webhook takes a verified notice")
    refuse_inbound_in_sandbox(
        uow,
        action=WEBHOOK_ACTION,
        object_type=SYNC_RUN_OBJECT,
        object_id=None,
        detail={"integration_connection_id": str(connection["id"])},
    )
    return _queue_run(
        uow,
        connection,
        kind=WEBHOOK_BATCH,
        action=WEBHOOK_ACTION,
        notifications=notification_params(notice.notifications),
    )
