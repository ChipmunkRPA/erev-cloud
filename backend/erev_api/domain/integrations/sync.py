"""``SYNC_RUN`` job and the test-connection probe (05 §5.1 ADP-01 to ADP-05, §5.2 ADP-12, ADP-14,
ADP-16, ADP-17; 04 T-INT-01, T-INT-02, T-INT-04, E-72, §15.4 ``PRODUCT_UNMAPPED`` /
``STALE_SOURCE_VERSION`` / ``CONTROL_TOTALS_MISMATCH`` / ``SOURCE_VERSION_GAP`` /
``CONTRACT_NOT_FOUND``; 03 REQ-INT-001, REQ-INT-004 to REQ-INT-007, REQ-DAT-010; PRD BR-INT-02,
BR-INT-03, J-23.4, J-23.6; ENGINE_SPEC S01-R-01 to S01-R-03, S02-R-13; BUILD_SPEC DIN-12, DIN-13).

One run of an inbound connection, in three steps:

1. **Start** (unit of work 1): the QUEUED T-INT-02 row becomes RUNNING (DB-03) and the connection's
   checkpoint is read.
2. **Fetch** (no transaction open — network calls, ADP-12 retries and sleeps never hold a lock):
   ``fetch_changes`` pages from the checkpoint (``INBOUND_POLL``; ADP-16 turns a poll whose replay
   id is older than 72 hours into a sweep; a ``RECONCILIATION_SWEEP`` forces one), or the verified
   notifications of a ``WEBHOOK_BATCH`` come from the job params (ADP-01). Notifications are
   deduplicated on (object, version); each object is fetched ONCE as the truth before acting
   (ADP-01; J-23.4 "objects fetched 3 (one 429 retried)": ``counts.fetched`` counts objects, so a
   retried request and a second notified version of one object add nothing).
3. **Apply** (unit of work 2, the sync principal): every fetched object → ``source_record``
   (tokenised, hashed, ``sync_run_id``; S01-R-01) → ``normalise`` → customer and product resolution
   (``PRODUCT_UNMAPPED``, remediable, per unmapped code) → ``grouping.ingest_order`` (S02-R-13:
   a DRAFT contract with the ADP-03 key, or a candidate modification) → T-INT-04 links; a notified
   version lower than the fetched object's is skipped with ``STALE_SOURCE_VERSION`` (ADP-02;
   BR-INT-02). A billing document — a Stripe invoice or credit note (ADP-17) — is stored as
   ``source_invoice`` rows and appended as ``BILLING_RECORDED`` / ``CREDIT_MEMO_RECORDED`` on the
   contract its subscription is linked to (``documents``; ``ingest_document``); a document whose
   subscription is linked to no contract raises ``CONTRACT_NOT_FOUND`` (remediable: reprocess once
   the subscription is ingested). The first sweep a connection completes is its baseline load
   (``checkpoint.swept_at``); in every later sweep a version the run stores is one the feed never
   delivered: it raises ``SOURCE_VERSION_GAP`` naming the object and the version, and is processed
   like a delivered version (REQ-INT-007). Control totals (source: the applied objects; loaded:
   the normalised orders and documents) decide SUCCEEDED or CONTROL_TOTAL_MISMATCH (REQ-DAT-010;
   BR-INT-03 raises the blocking exception); a permanent fetch or normalisation failure, or a
   document the event rules refuse, makes the run FAILED with the failures in ``problem``
   while what was ingested stays committed and the checkpoint advances, so one bad object never
   stalls the feed (the SF-16 "Interface batches failed" blocker, BLK-07, surfaces it). The job
   fails (and ``sync_failed`` marks the run FAILED) only on an infrastructure error.

The run works as the SYSTEM principal with exactly ``SYNC_PERMISSIONS`` (the
``imports.diff.import_principal`` pattern): booking a contract, creating a customer and opening a
DRAFT modification are authorised on the real paths, nothing else is gained. Network access goes
through the ``HttpClientFactory`` a composition root registers (DG-LAY-03; DG-ARC-12: no network
import here) — ``erev_api.adapters.http.adapter_client``.

Pending team-lead rulings (record F-DIN-prep.md, DIN-12 section): the amendment path (ADP-05) opens
a DRAFT modification on an ACTIVE parent contract found through T-INT-04 and otherwise records the
candidate rows and the reason in ``problem`` (Q-B); customers are resolved external-id map →
``customer.external_id`` → ``customer.code`` → created from the source account id (Q-C).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from erev_api.audit import writer as audit_writer
from erev_api.auth.keyring import SecretUnavailable
from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import Clock
from erev_api.db import new_id, transitions
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_computation,
    contract_version,
    customer,
    exception_item,
    external_id_map,
    integration_connection,
    obligation,
    obligation_version,
    product,
    source_record,
    sync_run,
    tenant,
)
from erev_api.domain.imports import exceptions as exception_queue
from erev_api.domain.imports.exceptions import (
    RaisedItem,
    dedupe_key,
    raise_exception_item,
    severity_of,
)
from erev_api.domain.imports.job_items import failed_item
from erev_api.domain.integrations import documents, grouping, normalise, owners, ports, queries
from erev_api.domain.integrations.normalise import SourceIdentity, StoreOutcome
from erev_api.domain.journals import ports as gl_ports
from erev_api.enums import (
    ContractStatus,
    ExceptionDisposition,
    ExceptionSource,
    JobKind,
    ModificationKind,
    NotificationKind,
    SourceObjectType,
    SourceSystem,
    SyncRunStatus,
)
from erev_api.events.notifications import notify
from erev_api.events.outbox import Undeliverable as GlUndeliverable
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_api.jobs.registry import FailedSubject, JobOutcome, RetryPolicy, task
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import Problem, is_period_state_moved
from erev_api.schemas.common import JobOut
from erev_api.uow import UnitOfWork

__all__ = [
    "DEFAULT_MAPPING_VERSIONS",
    "MAX_PAGES",
    "PAGE_LIMIT",
    "SYNC_PERMISSIONS",
    "Collected",
    "Counts",
    "Fetched",
    "HttpClientFactory",
    "ProbeResult",
    "adapter_for",
    "apply_object",
    "collect_changes",
    "ingest_document",
    "request_record_reprocess",
    "resolve_products",
    "stored_objects",
    "fetch_objects",
    "finish_run",
    "force_sweep",
    "http_client",
    "notifications_from_params",
    "ordered_for_processing",
    "probe_connection",
    "register_http_client_factory",
    "run_problem_of",
    "run_sync",
    "sync_failed",
    "sync_principal",
    "sync_unit_of_work",
    "tenant_code_of",
    "unique_notifications",
    "version_rank",
]

_LOGGER: Final = "erev_api.domain.integrations.sync"
register_logger_fields(
    _LOGGER,
    (
        "sync_run_id",
        "connection_id",
        "kind",
        "object_type",
        "external_id",
        "external_version",
        "outcome",
        "count",
        "status",
    ),
)

SYNC_PERMISSIONS: Final = frozenset(
    {"contract.create", "masterdata.maintain", "modification.create"}
)
PAGE_LIMIT: Final = 200  # notifications per ``fetch_changes`` page
MAX_PAGES: Final = 100  # pages per run; ``has_more`` beyond this waits for the next run
SWEEP_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
PRODUCT_UNMAPPED: Final = "PRODUCT_UNMAPPED"
CONTROL_TOTALS_MISMATCH: Final = "CONTROL_TOTALS_MISMATCH"
MODIFICATION_CANDIDATE_UNAPPLIED: Final = "MODIFICATION_CANDIDATE_UNAPPLIED"
CUSTOMER_OBJECT: Final = "customer"  # T-INT-04 object types
CONTRACT_OBJECT: Final = "contract"
LINK_ACTION: Final = "external_id_map.link"
CLOSE_ACTION: Final = "external_id_map.close"
INBOUND_POLL: Final = "INBOUND_POLL"
WEBHOOK_BATCH: Final = "WEBHOOK_BATCH"
RECONCILIATION_SWEEP: Final = "RECONCILIATION_SWEEP"
COA_SYNC: Final = "COA_SYNC"  # DIN-14: ``coa_sync.run_chart_sync`` runs it
# The mapping version an adapter normalises under when ``config.mapping_version`` is absent; pinned
# to the adapters' ``MAPPING_VERSION`` constants by ``tests/unit/test_integration_sync_unit.py``.
DEFAULT_MAPPING_VERSIONS: Final[Mapping[str, str]] = MappingProxyType(
    {"SALESFORCE": "SF-ORDERS-v1", "STRIPE": "STRIPE-BILLING-v1"}
)
PRODUCT_UNMAPPED_MESSAGE: Final = (  # PRD IMP-41 copy (J-23.4 quotes it)
    "Order {order}, line {n}: product {source_product} has no approved product record."
)
PRODUCT_UNMAPPED_SUGGESTION: Final = (
    "Add the source product code as an external id of a product (POST /external-ids), then"
    " reprocess the exception."
)
PRODUCT_OBJECT: Final = "product"  # T-INT-04 object type of the alias
REPROCESS_PARAM: Final = "source_record_ids"
REPROCESS_ITEM_PARAM: Final = "exception_item_id"
TOTALS_MISMATCH_MESSAGE: Final = (
    "Source totals {source} differ from loaded totals {loaded} for sync run {run}."
)
SOURCE_VERSION_GAP: Final = "SOURCE_VERSION_GAP"  # 04 table 15.4-B (rev 1.103); REQ-INT-007
GAP_MESSAGE: Final = (  # PRD IMP-126 copy
    "{source_system} {object} {external_id} version {version} had not been received when the"
    " reconciliation sweep found it. The sweep recorded it and processed it as a delivered"
    " version."
)
CONTRACT_NOT_FOUND: Final = "CONTRACT_NOT_FOUND"  # 04 table 15.4-A, X SYNC since rev 1.103
CONTRACT_NOT_FOUND_MESSAGE: Final = (  # PRD IMP-20 copy
    "Contract {contract} does not exist in this workspace."
)
DOCUMENT_SUGGESTION: Final = (
    "Sync the subscription the document names so that its contract exists, then reprocess the"
    " exception."
)
BILL_STEP: Final = "bill"  # T-INT-02 ``problem.failures[].step`` of a billing document
# SYNC-PROBLEM-SHAPE-1 (04 rev 1.90 §15.2 / T-INT-02; PRD ERR-56 / ERR-57): every stored
# ``sync_run.problem`` is the T-PLT-27 RFC 9457 envelope; the run's own failure records travel
# verbatim in the RFC 9457 EXTENSION member ``failures`` (``errors[]`` stays API-C-05-shaped).
SYNC_OBJECTS_NOT_APPLIED: Final = "sync-objects-not-applied"
CONNECTION_TEST_FAILED: Final = "connection-test-failed"
SYNC_RUN_INSTANCE: Final = "/api/v1/sync-runs/{run_id}"
NOT_APPLIED_DETAIL: Final = (  # PRD ERR-56 copy
    "{failed} of {total} source objects were not applied. Each failure names the object and why it"
    " was not applied. Fix the named objects in the source system, then run the sync again."
)
CANCELLED_DETAIL: Final = (  # PRD ERR-56 copy (a cancelled run)
    "The run was cancelled after {applied} objects. The next run starts again from the last"
    " checkpoint."
)
PROBE_FAILED_DETAIL: Final = (  # PRD ERR-57 copy
    "The connection could not be verified: {reason}. Check the base URL and the secret reference,"
    " then test again."
)
AMENDMENT_UNKNOWN_MESSAGE: Final = (  # PRD IMP-123 copy
    "Amendment {order} names parent {parent}, which is not linked to a contract. Its lines were"
    " recorded and no modification was drafted."
)
AMENDMENT_NOT_ACTIVE_MESSAGE: Final = (  # PRD IMP-123 copy
    "Amendment {order} names parent {external_id}, which is {status} and not ACTIVE. Its lines"
    " were recorded and no modification was drafted."
)
AMENDMENT_NO_CHANGE_MESSAGE: Final = (  # PRD IMP-123 copy
    "Amendment {order} names parent {external_id}, which has the same lines as the parent. Its"
    " lines were recorded and no modification was drafted."
)
BASIS_STALE: Final = "BASIS_STALE"
BASIS_STALE_MESSAGE: Final = (  # PRD IMP-124 copy (values-free; the values are detail members)
    "The parent contract's latest computation does not cover its current events, or its group"
    " awaits a recompute. The amendment was not drafted; retry after the recompute."
)
BASIS_UNSUPPORTED: Final = "BASIS_UNSUPPORTED_TRANSFORMATION"
BASIS_UNSUPPORTED_MESSAGE: Final = (  # PRD IMP-125 copy
    "The parent contract's obligations are not one unchanged source line each, so the amendment"
    " cannot be compared line by line. The amendment was not drafted; make the modification by"
    " hand."
)
NETTED: Final = "AGENT"  # E-xx principal_agent: the engine nets the gross price (s03 agent)
AMENDMENT_SUGGESTION: Final = (
    "Activate or link the parent contract, then reprocess; or draft the modification by hand."
)

# --- composition-root hooks (DG-LAY-03) -----------------------------------------------------------

type HttpClientFactory = Callable[[str], Any]  # base_url → an ``httpx.Client``-like object
_HOOKS: Final[dict[str, HttpClientFactory]] = {}


def register_http_client_factory(factory: HttpClientFactory | None) -> None:
    """A root or a test fixture registers how adapters reach ``base_url``; None clears it."""
    if factory is None:
        _HOOKS.pop("http", None)
    else:
        _HOOKS["http"] = factory


def http_client(base_url: str) -> Any:
    """A client for ``base_url``; ``LookupError`` while no root registered a factory, so a run
    fails closed instead of ingesting nothing silently (``ports.inbound_adapter_for`` pattern)."""
    factory = _HOOKS.get("http")
    if factory is None:
        raise LookupError("no HTTP client factory is registered for the inbound adapters")
    return factory(base_url)


def tenant_code_of(session: Session, tenant_id: UUID) -> str:
    return str(session.execute(select(tenant.c.code).where(tenant.c.id == tenant_id)).scalar_one())


def adapter_for(
    connection: Mapping[str, Any],
    *,
    tenant_code: str,
    client: Any | None = None,
    config: Mapping[str, Any] | None = None,
    clock: Clock | None = None,
) -> ports.InboundAdapter:
    """The connection's adapter over its ``base_url`` and non-secret ``config`` (``config`` here
    overrides members, such as ``max_attempts`` for a probe). ``clock`` is the caller's application
    clock — the job's, the unit of work's, or the webhook receiver's — and becomes the adapter's
    ``now`` hook, so the ADP-16 72-hour sweep decision, the ``replay_at`` a poll stamps and the
    ADP-01 replay window of a signed notification are never read from the wall clock
    (DG-KRN-TIME-06)."""
    base_url = connection.get("base_url")
    if not base_url:
        raise ports.Permanent("the connection has no base_url")
    settings = {**dict(connection.get("config") or {}), **dict(config or {})}
    if clock is not None:
        settings[ports.NOW_HOOK] = clock.now  # set last: a stored config member never wins
    context = ports.InboundContext(
        tenant_code=tenant_code,
        base_url=str(base_url),
        config=settings,
        client=client if client is not None else http_client(str(base_url)),
    )
    return ports.inbound_adapter_for(str(connection["adapter"]), context)


def mapping_version_of(connection: Mapping[str, Any]) -> str:
    configured = dict(connection.get("config") or {}).get("mapping_version")
    if configured:
        return str(configured)
    return DEFAULT_MAPPING_VERSIONS.get(str(connection["adapter"]), "")


# --- the sync principal ---------------------------------------------------------------------------


def sync_principal(tenant_id: UUID, on_behalf_of: UUID | None = None) -> Principal:
    """SYSTEM with exactly ``SYNC_PERMISSIONS`` on every entity (``import_principal`` pattern)."""
    base = system_principal(tenant_id, on_behalf_of_id=on_behalf_of)
    return dataclasses.replace(
        base,
        permissions=SYNC_PERMISSIONS,
        permission_scopes=MappingProxyType({code: "*" for code in SYNC_PERMISSIONS}),
    )


def sync_unit_of_work(jc: JobContext) -> AbstractContextManager[UnitOfWork]:
    principal = sync_principal(jc.principal.tenant_id, jc.principal.on_behalf_of_id)
    return system_unit_of_work(jc.runtime, principal, request_id=f"job-{jc.job_id}", clock=jc.clock)


# --- test connection ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """What ``POST /integrations/{id}/test`` records (T-INT-01 ``last_test_result`` and
    ``last_test_detail``)."""

    result: Literal["SUCCESS", "FAILURE"]
    detail: str


def _probe_chart(connection: Mapping[str, Any], *, tenant_code: str) -> ProbeResult:
    """04 §16.14 rev 1.115 (ruling R-45 (c)): the probe of a connection whose adapter serves a
    chart of accounts is one single-attempt read of the chart. An empty chart is a FAILURE, as it
    is for the ``COA_SYNC`` run: a role that may not list accounts reads as an empty chart."""
    code = str(connection["adapter"])
    try:
        base_url = connection.get("base_url")
        if not base_url:
            raise gl_ports.Permanent("the connection has no base_url")
        source = ports.chart_source_for(
            code,
            ports.InboundContext(
                tenant_code=tenant_code,
                base_url=str(base_url),
                config={**dict(connection.get("config") or {}), "max_attempts": 1},
                client=http_client(str(base_url)),
            ),
        )
        accounts = source.pull_erp_accounts()
    except (gl_ports.Transient, GlUndeliverable, LookupError) as error:
        return ProbeResult("FAILURE", f"{type(error).__name__}: {error}")
    if not accounts:
        return ProbeResult("FAILURE", f"{code} at {base_url} stated an empty chart of accounts")
    return ProbeResult(
        "SUCCESS", f"{code} reachable at {base_url}; {len(accounts)} account(s) in the chart"
    )


def probe_connection(uow: UnitOfWork, connection: Mapping[str, Any]) -> ProbeResult:
    """Resolve ``secret_ref`` through the key ring (ADP-14: the value is read and dropped, never
    logged), then ask the adapter one question with a single attempt: one page of changes of an
    inbound adapter, or the chart of accounts of an adapter that serves one (``_probe_chart``).
    A reference the provider will not serve is a FAILURE on both providers
    (``KeyRing.adapter_secret``), and so is a secret store that does not answer: the person asked
    a question (04 §16.14 rev 1.115; the webhook receiver lets the same outage be a 5xx)."""
    ref = connection.get("secret_ref")
    if ref:
        try:
            uow.keyring.adapter_secret(str(ref), tenant_id=uow.principal.tenant_id)
        except KeyError:
            return ProbeResult("FAILURE", f"secret reference {ref} is not resolvable")
        except SecretUnavailable:
            return ProbeResult(
                "FAILURE", f"the secret store did not answer for secret reference {ref}"
            )
    tenant_code = tenant_code_of(uow.session, uow.principal.tenant_id)
    if str(connection["adapter"]) in ports.CHART_ADAPTERS:
        return _probe_chart(connection, tenant_code=tenant_code)
    try:
        adapter = adapter_for(
            connection,
            tenant_code=tenant_code,
            config={"max_attempts": 1},
            clock=uow.clock,
        )
        page = adapter.fetch_changes(ports.Checkpoint.from_json(connection.get("checkpoint")), 1)
    except (ports.Undeliverable, LookupError) as error:
        return ProbeResult("FAILURE", f"{type(error).__name__}: {error}")
    return ProbeResult(
        "SUCCESS",
        f"{adapter.code} reachable at {connection['base_url']};"
        f" {len(page.notifications)} change(s) visible",
    )


# --- collect --------------------------------------------------------------------------------------


def version_rank(external_version: str) -> tuple[int, int | str]:
    """Orders external versions: integer texts numerically (the Salesforce ``Version__c``), other
    texts lexically after every integer (``salesforce.version_order`` agrees on integers)."""
    text = str(external_version).strip()
    try:
        return (0, int(text))
    except ValueError:
        return (1, text)


def notifications_from_params(items: Iterable[Mapping[str, Any]]) -> tuple[ports.Notification, ...]:
    """The verified notifications a ``WEBHOOK_BATCH`` job carries in its params (ADP-01)."""
    return tuple(
        ports.Notification(
            notification_id=str(item["notification_id"]),
            object_type=SourceObjectType(str(item["object_type"])),
            external_id=str(item["external_id"]),
            external_version=str(item["external_version"]),
            replay_id=int(item.get("replay_id", 0)),
        )
        for item in items
    )


def force_sweep(checkpoint: ports.Checkpoint) -> ports.Checkpoint:
    """A checkpoint ``sweep_due`` answers True for: a ``RECONCILIATION_SWEEP`` asked explicitly."""
    if checkpoint.sweep_cursor is not None:
        return checkpoint  # a sweep in progress resumes (05 rev 1.24)
    if checkpoint.replay_id is not None:
        return dataclasses.replace(checkpoint, replay_at=None)
    if checkpoint.last_modified_watermark is None:
        return dataclasses.replace(checkpoint, last_modified_watermark=SWEEP_EPOCH)
    return checkpoint


@dataclass(frozen=True, slots=True)
class Collected:
    notifications: tuple[ports.Notification, ...]
    checkpoint_after: ports.Checkpoint
    pages: int
    swept: bool
    cancelled: bool = False


def collect_changes(
    adapter: ports.InboundAdapter,
    *,
    kind: str,
    checkpoint: ports.Checkpoint,
    notifications: Sequence[Mapping[str, Any]] | None,
    cancelled: Callable[[], bool] = lambda: False,
    page_limit: int = PAGE_LIMIT,
    max_pages: int = MAX_PAGES,
) -> Collected:
    """Step 2's notifications: from the params (``WEBHOOK_BATCH``) or paged from the source."""
    if kind == WEBHOOK_BATCH:
        return Collected(notifications_from_params(notifications or ()), checkpoint, 0, False)
    current = force_sweep(checkpoint) if kind == RECONCILIATION_SWEEP else checkpoint
    found: list[ports.Notification] = []
    pages = 0
    swept = False
    while True:
        if cancelled():
            return Collected(tuple(found), current, pages, swept, cancelled=True)
        page = adapter.fetch_changes(current, page_limit)
        pages += 1
        found.extend(page.notifications)
        swept = swept or page.kind == "SWEEP"
        current = page.checkpoint
        if not page.has_more or pages >= max_pages:
            return Collected(tuple(found), current, pages, swept)


def unique_notifications(
    items: Iterable[ports.Notification],
) -> tuple[list[ports.Notification], int]:
    """First occurrence per (object type, external id, version); the count of exact repeats (the
    duplicate webhook of WLD-F-31, recorded once)."""
    seen: set[tuple[SourceObjectType, str, str]] = set()
    unique: list[ports.Notification] = []
    duplicates = 0
    for item in items:
        key = (item.object_type, item.external_id, item.external_version)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(item)
    return unique, duplicates


@dataclass(frozen=True, slots=True)
class Fetched:
    """Step 2's objects: one fetch per (object type, external id) in first-arrival order, the
    notified versions of each, and the permanent failures."""

    objects: tuple[ports.SourceObject, ...]
    notified_versions: Mapping[tuple[SourceObjectType, str], tuple[str, ...]]
    failures: tuple[dict[str, Any], ...]
    attempts: int


def fetch_objects(adapter: ports.InboundAdapter, unique: Sequence[ports.Notification]) -> Fetched:
    objects: list[ports.SourceObject] = []
    failures: list[dict[str, Any]] = []
    versions: dict[tuple[SourceObjectType, str], list[str]] = {}
    for item in unique:
        versions.setdefault((item.object_type, item.external_id), []).append(item.external_version)
    for (object_type, external_id), notified in versions.items():
        try:
            objects.append(adapter.fetch_object(object_type, external_id))
        except ports.Undeliverable as error:
            failures.append(
                {
                    "step": "fetch",
                    "object_type": object_type.value,
                    "external_id": external_id,
                    "external_versions": list(notified),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    return Fetched(
        objects=tuple(objects),
        notified_versions=MappingProxyType({key: tuple(value) for key, value in versions.items()}),
        failures=tuple(failures),
        attempts=len(versions),
    )


def ordered_for_processing(objects: Iterable[ports.SourceObject]) -> list[ports.SourceObject]:
    """Fetched objects in arrival order; when a source answered several versions of one object,
    the highest first so the lower ones are stored STALE (ADP-02)."""
    groups: dict[tuple[SourceObjectType, str], list[ports.SourceObject]] = {}
    for obj in objects:
        groups.setdefault((obj.object_type, obj.external_id), []).append(obj)
    ordered: list[ports.SourceObject] = []
    for members in groups.values():
        ordered.extend(sorted(members, key=lambda item: item.version_order, reverse=True))
    return ordered


# --- apply ----------------------------------------------------------------------------------------


@dataclass(slots=True)
class Counts:
    notifications: int = 0
    duplicates: int = 0
    fetched: int = 0
    records: int = 0
    stale: int = 0
    exceptions: int = 0
    unmapped_products: int = 0
    contracts_booked: int = 0
    candidates: int = 0
    modifications_drafted: int = 0
    customers_created: int = 0
    reprocessed: int = 0
    rebooked: int = 0
    gaps: int = 0  # SOURCE_VERSION_GAP items of a sweep (REQ-INT-007)
    documents: int = 0  # invoices and credit notes recorded (T-SRC-04)
    billing_events: int = 0  # BILLING_RECORDED appended
    credit_memo_events: int = 0  # CREDIT_MEMO_RECORDED appended
    failures: list[dict[str, Any]] = field(default_factory=list)
    raised_keys: set[str] = field(default_factory=set)  # dedupe keys of this run's items
    processed_records: set[UUID] = field(default_factory=set)  # records applied without refusal

    def as_json(self) -> dict[str, Any]:
        return {
            "notifications": self.notifications,
            "duplicates": self.duplicates,
            "fetched": self.fetched,
            "records": self.records,
            "stale": self.stale,
            "exceptions": self.exceptions,
            "unmapped_products": self.unmapped_products,
            "contracts_booked": self.contracts_booked,
            "candidates": self.candidates,
            "modifications_drafted": self.modifications_drafted,
            "customers_created": self.customers_created,
            "reprocessed": self.reprocessed,
            "rebooked": self.rebooked,
            "gaps": self.gaps,
            "documents": self.documents,
            "billing_events": self.billing_events,
            "credit_memo_events": self.credit_memo_events,
            "failures": len(self.failures),
        }


def _touch(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _moved(uow: UnitOfWork) -> dict[str, Any]:
    """SC-M of one move of a ``sync_run``. An IM-S row has the DB-03 transition trigger and no
    DB-02 touch trigger, so the move raises ``row_version`` itself: ``GET /sync-runs/{id}`` answers
    ``ETag "r<row_version>"`` (04 API-C-08) and it must change with every status."""
    return {**_touch(uow), "row_version": sync_run.c.row_version + 1}


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _live_link(
    session: Session,
    connection_id: UUID,
    object_type: str,
    *,
    external_id: str | None = None,
    internal_id: UUID | None = None,
) -> Mapping[str, Any] | None:
    statement = select(external_id_map).where(
        external_id_map.c.integration_connection_id == connection_id,
        external_id_map.c.object_type == object_type,
        external_id_map.c.valid_to.is_(None),
    )
    if external_id is not None:
        statement = statement.where(external_id_map.c.external_id == external_id)
    if internal_id is not None:
        statement = statement.where(external_id_map.c.internal_id == internal_id)
    row = session.execute(statement).mappings().first()
    return None if row is None else MappingProxyType(dict(row))


def _close_link(uow: UnitOfWork, link_id: UUID) -> None:
    transitions.apply(
        uow.session,
        "external_id_map",
        link_id,
        to_status=None,
        set_values={"valid_to": uow.now},
    )
    audit_writer.record_facts(
        uow, action=CLOSE_ACTION, object_type="external_id_map", ids=[link_id]
    )


def link_external_id(
    uow: UnitOfWork,
    connection_id: UUID,
    *,
    object_type: str,
    internal_id: UUID,
    external_id: str,
    external_version: str | None,
    sync_run_id: UUID | None,
) -> UUID | None:
    """T-INT-04: the live (connection, object type, external id) ↔ internal id row; a re-link closes
    the superseded rows (``valid_to``, IM-S set-once) and inserts a new one (AUD-FACT). A link a
    user creates through ``POST /external-ids`` (04 §16.14 rev 1.81) has no ``sync_run_id``."""
    session = uow.session
    by_external = _live_link(session, connection_id, object_type, external_id=external_id)
    if by_external is not None and UUID(str(by_external["internal_id"])) == internal_id:
        return None
    if by_external is not None:
        _close_link(uow, UUID(str(by_external["id"])))
    by_internal = _live_link(session, connection_id, object_type, internal_id=internal_id)
    if by_internal is not None:
        _close_link(uow, UUID(str(by_internal["id"])))
    link_id = new_id()
    session.execute(
        insert(external_id_map).values(
            tenant_id=uow.principal.tenant_id,
            id=link_id,
            integration_connection_id=connection_id,
            object_type=object_type,
            internal_id=internal_id,
            external_id=external_id,
            external_version=external_version,
            valid_from=uow.now,
            valid_to=None,
            sync_run_id=sync_run_id,
            **_created(uow),
        )
    )
    audit_writer.record_facts(
        uow,
        action=LINK_ACTION,
        object_type="external_id_map",
        ids=[link_id],
        detail={"object_type": object_type, "external_id": external_id},
    )
    return link_id


def lookup_customer(
    session: Session, connection_id: UUID, draft: ports.NormalisedOrderDraft
) -> UUID | None:
    """The READ-ONLY customer resolution of ``draft.customer_external_id``: the live T-INT-04 link,
    else ``customer.external_id`` under the source system, else ``customer.code`` — nothing created
    (the class-C comparison of a reuse, 04 §16.14 rev 1.81)."""
    external = draft.customer_external_id
    linked = _live_link(session, connection_id, CUSTOMER_OBJECT, external_id=external)
    if linked is not None:
        return UUID(str(linked["internal_id"]))
    found = session.execute(
        select(customer.c.id).where(
            customer.c.external_id == external,
            customer.c.source_system == draft.source_system.value,
        )
    ).scalar_one_or_none()
    if found is None:
        found = session.execute(
            select(customer.c.id).where(customer.c.code == external)
        ).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def resolve_customer(
    uow: UnitOfWork,
    connection: Mapping[str, Any],
    draft: ports.NormalisedOrderDraft,
    *,
    sync_run_id: UUID,
    counts: Counts,
) -> UUID:
    """The customer of ``draft.customer_external_id`` (pending Q-C): the live T-INT-04 link, else
    ``customer.external_id`` under the source system, else ``customer.code``, else a customer
    created from the source account id (code and name = the id; ``masterdata.maintain``)."""
    # Imported here: the reference commands import the contracts package, which imports grouping.
    from erev_api.domain.reference.commands import create_customer
    from erev_api.schemas.customers import CustomerIn

    session = uow.session
    connection_id = UUID(str(connection["id"]))
    external = draft.customer_external_id
    linked = _live_link(session, connection_id, CUSTOMER_OBJECT, external_id=external)
    if linked is not None:
        return UUID(str(linked["internal_id"]))
    found: UUID | None = lookup_customer(session, connection_id, draft)
    if found is None:
        created = create_customer(
            uow,
            body=CustomerIn(code=external, name=external, external_id=external),
            source_system=draft.source_system,
        )
        found = created.id
        counts.customers_created += 1
    customer_id = UUID(str(found))
    link_external_id(
        uow,
        connection_id,
        object_type=CUSTOMER_OBJECT,
        internal_id=customer_id,
        external_id=external,
        external_version=None,
        sync_run_id=sync_run_id,
    )
    return customer_id


@dataclass(frozen=True, slots=True)
class ResolvedProduct:
    """A source product code resolved to a product record: by the product's own ``code`` or by the
    connection's live T-INT-04 ``product`` link (04 §16.14 rev 1.81; the alias J-23.5 adds)."""

    product_id: UUID
    product_code: str
    via_alias: bool


def resolve_products(
    session: Session, connection_id: UUID, codes: Iterable[str]
) -> dict[str, ResolvedProduct]:
    wanted = sorted(set(codes))
    if not wanted:
        return {}
    found: dict[str, ResolvedProduct] = {
        str(code): ResolvedProduct(UUID(str(value)), str(code), False)
        for code, value in session.execute(
            select(product.c.code, product.c.id).where(product.c.code.in_(wanted))
        )
    }
    missing = [code for code in wanted if code not in found]
    if not missing:
        return found
    aliases = {
        str(external): UUID(str(internal))
        for external, internal in session.execute(
            select(external_id_map.c.external_id, external_id_map.c.internal_id).where(
                external_id_map.c.integration_connection_id == connection_id,
                external_id_map.c.object_type == PRODUCT_OBJECT,
                external_id_map.c.external_id.in_(missing),
                external_id_map.c.valid_to.is_(None),
            )
        )
    }
    if aliases:
        rows = {
            UUID(str(row_id)): str(code)
            for row_id, code in session.execute(
                select(product.c.id, product.c.code).where(
                    product.c.id.in_(sorted(set(aliases.values())))
                )
            )
        }
        for external, internal in aliases.items():
            if internal in rows:
                found[external] = ResolvedProduct(internal, rows[internal], True)
    return found


def _products(session: Session, codes: Iterable[str]) -> dict[str, UUID]:
    wanted = sorted(set(codes))
    return {
        str(code): UUID(str(value))
        for code, value in session.execute(
            select(product.c.code, product.c.id).where(product.c.code.in_(wanted))
        )
    }


def _normalised_order(
    draft: ports.NormalisedOrderDraft,
    *,
    source_record_id: UUID,
    customer_id: UUID,
    resolved: Mapping[str, ResolvedProduct] | None = None,
) -> grouping.NormalisedOrder:
    """The stored order of the ORIGINAL draft: every line keeps its SOURCE ``product_code``
    (T-SRC-03) and carries the resolved record code as ``booking_product_code`` when the source code
    is an alias (Codex 0652 §1) — the booking sees the product, the stored row keeps the fact."""

    def booking_code(code: str) -> str | None:
        found = None if resolved is None else resolved.get(code)
        return found.product_code if found is not None and found.via_alias else None

    return grouping.NormalisedOrder(
        source_record_id=source_record_id,
        source_system=draft.source_system,
        external_order_id=draft.external_order_id,
        external_version=draft.external_version,
        order_number=draft.order_number,
        order_date=draft.order_date,
        customer_external_id=draft.customer_external_id,
        customer_id=customer_id,
        legal_entity_code=draft.legal_entity_code,
        transaction_currency=draft.transaction_currency,
        lines=tuple(
            grouping.OrderLine(
                line_external_id=line.line_external_id,
                product_code=line.product_code,
                quantity=line.quantity,
                total_price=line.total_price,
                start_date=line.start_date,
                end_date=line.end_date,
                performing_entity_code=line.performing_entity_code,
                booking_product_code=booking_code(line.product_code),
            )
            for line in draft.lines
        ),
        po_number=draft.po_number,
        parent_order_external_id=draft.parent_order_external_id,
        payment_terms=draft.payment_terms,
        document_ref=draft.document_ref,
        custom_attributes=dict(draft.custom_attributes),
        amendment_reason=draft.amendment_reason,
        acceptance_clause=draft.acceptance_clause,
        side_letter=draft.side_letter,
    )


def _failure(
    counts: Counts, step: str, obj: ports.SourceObject, error: object, **extra: Any
) -> None:
    # F-ADM-ROUTE-DETAIL-1: the identity members are written LAST — a caller's extra keys (a
    # ``rule_id``, a nested ``detail``) can never rename the record to another object; the record
    # names the object that failed, and only that.
    counts.failures.append(
        {
            **extra,
            "step": step,
            "object_type": obj.object_type.value,
            "external_id": obj.external_id,
            "external_version": obj.external_version,
            "error": f"{type(error).__name__}: {error}"
            if isinstance(error, Exception)
            else str(error),
        }
    )


def _raise(uow: UnitOfWork, counts: Counts, **item: Any) -> RaisedItem:
    """``raise_exception_item`` for this run, remembering the item's dedupe key — the SAME-item
    identity ``_settle_item`` checks (04 §16.14 rev 1.81: a reprocessed item resolves only when its
    code is not raised again for its subject; Codex 0545 §2 R2)."""
    counts.raised_keys.add(str(item["dedupe"]))
    return raise_exception_item(uow, **item)


def _stale_notification(
    uow: UnitOfWork,
    obj: ports.SourceObject,
    notified_version: str,
    *,
    sync_run_id: UUID,
    counts: Counts,
) -> None:
    """ADP-02 at the notification level: a notified version lower than the fetched object's is
    skipped with the ``STALE_SOURCE_VERSION`` warning (BR-INT-02); no payload of it exists."""
    identity = SourceIdentity(obj.source_system, obj.object_type, obj.external_id, notified_version)
    _raise(
        uow,
        counts,
        source=ExceptionSource.INTEGRATION,
        code=normalise.STALE_CODE,
        severity=severity_of("WARNING"),
        message=normalise.stale_message(identity, obj.external_version),
        dedupe=dedupe_key(
            ExceptionSource.INTEGRATION,
            normalise.STALE_CODE,
            f"{obj.source_system.value}:{obj.object_type.value}:{obj.external_id}:{notified_version}",
        ),
        business_key=obj.external_id,
        sync_run_id=sync_run_id,
    )
    counts.stale += 1
    counts.exceptions += 1


def _unmapped_products(
    uow: UnitOfWork,
    draft: ports.NormalisedOrderDraft,
    missing: Sequence[str],
    *,
    source_record_id: UUID,
    sync_run_id: UUID,
    counts: Counts,
    contract_id: UUID | None = None,
) -> None:
    """One ``PRODUCT_UNMAPPED`` item per unmapped code, naming the DRAFT contract booked from the
    mapped lines (activation stays blocked until resolved, 04 table 15.4-I rev 1.81) and carrying
    the code and its line ids as ``source_payload.detail`` (the checklist's message). The message
    is PRD IMP-41's copy; ``<n>`` is the number of the first order line that carries the code —
    the payload lists every such line."""
    for code in missing:
        numbers = [
            number for number, line in enumerate(draft.lines, start=1) if line.product_code == code
        ]
        line_ids = [line.line_external_id for line in draft.lines if line.product_code == code]
        _raise(
            uow,
            counts,
            source=ExceptionSource.SYNC,
            code=PRODUCT_UNMAPPED,
            severity=severity_of("ERROR"),
            message=PRODUCT_UNMAPPED_MESSAGE.format(
                order=draft.external_order_id, n=numbers[0] if numbers else 1, source_product=code
            ),
            dedupe=dedupe_key(
                ExceptionSource.SYNC, PRODUCT_UNMAPPED, f"{draft.external_order_id}:{code}"
            ),
            suggestion=PRODUCT_UNMAPPED_SUGGESTION,
            business_key=draft.external_order_id,
            source_payload={"detail": {"product_code": code, "line_external_ids": line_ids}},
            source_record_id=source_record_id,
            sync_run_id=sync_run_id,
            contract_id=contract_id,
            disposition=ExceptionDisposition.REMEDIABLE,
        )
    counts.exceptions += len(missing)
    counts.unmapped_products += 1


def _groups_of(session: Session, contract_ids: Iterable[UUID]) -> list[UUID]:
    """The combination groups the contracts are in now; the caller holds their rows."""
    groups = session.execute(
        select(contract.c.combination_group_id).where(contract.c.id.in_(sorted(contract_ids)))
    ).scalars()
    return [UUID(str(group_id)) for group_id in groups]


def _parent_contract(
    session: Session, connection_id: UUID, parent_external_id: str
) -> Mapping[str, Any] | None:
    linked = _live_link(session, connection_id, CONTRACT_OBJECT, external_id=parent_external_id)
    if linked is None:
        return None
    row = (
        session.execute(select(contract).where(contract.c.id == linked["internal_id"]))
        .mappings()
        .one_or_none()
    )
    return None if row is None else MappingProxyType(dict(row))


def _basis_line(
    key: str, product_code: Any, quantity: Any, total: Any, start: Any, end: Any
) -> dict[str, Any]:
    return {
        "line_external_id": key,
        "product_code": str(product_code or ""),
        "quantity": Decimal(str(quantity)),
        "total_price": Decimal(str(total)),
        "start_date": start,
        "end_date": end,
    }


def _date_of(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _stream_booking_lines(session: Session, contract_id: UUID) -> dict[str, dict[str, Any]]:
    """The lines of the contract's latest non-voided ``CONTRACT_BOOKED`` payload (the stream state
    of a contract that was never computed — a DRAFT booked and not yet activated)."""
    # Imported here: the contracts repository imports the events package, which imports grouping.
    from erev_api.domain.contracts import repo

    rows = repo.stream(session, contract_id)
    voided = {row["supersedes_event_id"] for row in rows if row["supersedes_event_id"]}
    bookings = [
        row
        for row in rows
        if str(row["event_type"]) == "CONTRACT_BOOKED" and row["id"] not in voided
    ]
    if not bookings:
        return {}
    payload = dict(bookings[-1]["payload"] or {})
    basis: dict[str, dict[str, Any]] = {}
    for line in payload.get("lines") or ():
        key = str(line["obligation_key"])
        total = line.get("total_price")
        amount = total.get("amount", "0") if isinstance(total, Mapping) else (total or "0")
        basis[key] = _basis_line(
            key,
            line.get("product_code"),
            line.get("quantity", "0"),
            amount,
            _date_of(line.get("start_date")),
            _date_of(line.get("end_date")),
        )
    return basis


@dataclass(frozen=True, slots=True)
class ParentBasis:
    """The parent's current line state keyed by line external id; the obligations without a line
    external id; a GOVERNED refusal (04 §15.4-B ``BASIS_STALE`` — team-lead's guard — or
    ``BASIS_UNSUPPORTED_TRANSFORMATION`` — Codex 0403 §3: netted, split, merged or regrouped) with
    its values as detail."""

    lines: Mapping[str, Mapping[str, Any]]
    unkeyed: tuple[str, ...] = ()
    refused: str | None = None  # the §15.4-B code
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def message(self) -> str:
        """The PRD copy of the refusal (IMP-124 / IMP-125)."""
        return BASIS_STALE_MESSAGE if self.refused == BASIS_STALE else BASIS_UNSUPPORTED_MESSAGE


def _stale_reason(
    session: Session, parent: Mapping[str, Any], computation_id: UUID
) -> dict[str, Any] | None:
    """Team-lead's guard on Codex 0339 §1: the computation's recorded stream head of this contract
    must equal the contract's head and its group must not be dirty; otherwise the projected basis
    is stale and the amendment is refused by name (never a silent fallback)."""
    heads = session.execute(
        select(contract_computation.c.stream_heads).where(
            contract_computation.c.id == computation_id
        )
    ).scalar_one_or_none()
    recorded = None if heads is None else dict(heads).get(str(parent["id"]))
    head = int(parent["head_stream_version"])
    dirty_since = session.execute(
        select(combination_group.c.dirty_since).where(
            combination_group.c.id == parent["combination_group_id"]
        )
    ).scalar_one_or_none()
    if recorded is None or int(recorded) != head or dirty_since is not None:
        return {
            "external_id": str(parent["external_id"]),
            "computed_head": None if recorded is None else int(recorded),
            "stream_head": head,
            "dirty_since": None if dirty_since is None else str(dirty_since),
        }
    return None


def _unsupported_reasons(
    rows: Sequence[Mapping[str, Any]], booked: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """Codex 0403 §3: an obligation is a usable basis line only when it is ONE UNCHANGED source
    line — its key is a booked line id, its inception quantity and stated price equal that line's
    gross quantity and price (so a netted price never yields a false delta), it is neither a bundle
    component nor a regrouped obligation, and it is not presented net (agent). A booked line with
    no obligation of its own (merged) is refused too. Everything else is named here."""
    reasons: list[str] = []
    seen: set[str] = set()
    for row in rows:
        key = row["obligation_key"]
        if key is None or not str(key).strip():
            continue
        key = str(key)
        seen.add(key)
        line = booked.get(key)
        if line is None:
            reasons.append(f"{key}: not a booked source line (split or renamed)")
            continue
        if row.get("parent_obligation_id") is not None:
            reasons.append(f"{key}: bundle component")
        if row.get("regrouped_from_obligation_id") is not None:
            reasons.append(f"{key}: regrouped obligation")
        if str(row.get("principal_agent") or "") == NETTED:
            reasons.append(f"{key}: net presentation (agent)")
        original_price = Decimal(str(row["original_stated_price"]))
        original_quantity = Decimal(str(row["original_quantity"]))
        if original_price != line["total_price"] or original_quantity != line["quantity"]:
            reasons.append(
                f"{key}: inception basis {original_quantity} / {original_price} differs from the"
                f" booked gross line {line['quantity']} / {line['total_price']}"
            )
    for key in booked:
        if key not in seen:
            reasons.append(f"{key}: booked source line without an obligation of its own (merged)")
    return reasons


def _parent_basis(session: Session, parent: Mapping[str, Any]) -> ParentBasis:
    """The parent contract's CURRENT GOVERNED line state, keyed by line external id (team-lead's
    ruling on Codex 0339 §1 DIN12-AMENDMENT-BASIS-1): the head computation's ``obligation_version``
    rows of the primary book — ``obligation_key`` (the booked line's external id), ``product_code``,
    ``quantity`` and ``stated_price`` ("stated price after modifications", T-CON-11), which carry
    native AND legacy (row-less, Q-3 / L5-1-Q-27) amendments alike — and, for a contract never
    computed (a DRAFT booked and not yet activated), the lines of its latest ``CONTRACT_BOOKED``
    payload. Candidates, unrelated orders of the same external id and unapplied candidates never
    reach either source. The second member names the obligations whose current state carries no
    line external id (``obligation_key`` null): they are reported, never mapped by guess."""
    # Imported here: the contracts queries import the contracts package, which imports grouping.
    from erev_api.domain.contracts.queries import primary_book

    contract_id = UUID(str(parent["id"]))
    computation_id = parent.get("latest_computation_id")
    booked = _stream_booking_lines(session, contract_id)
    is_draft = str(parent.get("status")) == ContractStatus.DRAFT.value
    if computation_id is None:
        if is_draft:
            return ParentBasis(booked)  # never computed: the stream's booking IS the state
        # Codex 0417 §1: a non-DRAFT parent without a computation never resets to inception.
        return ParentBasis(
            {},
            refused=BASIS_STALE,
            detail={
                "external_id": str(parent["external_id"]),
                "computed_head": None,
                "stream_head": int(parent["head_stream_version"]),
                "reason": "no computation",
            },
        )
    stale = _stale_reason(session, parent, UUID(str(computation_id)))
    if stale is not None:
        return ParentBasis({}, refused=BASIS_STALE, detail=stale)
    version_id = session.execute(
        select(contract_version.c.id).where(
            contract_version.c.contract_computation_id == computation_id,
            contract_version.c.book_code == primary_book(session),
        )
    ).scalar_one_or_none()
    if version_id is None:
        if is_draft:
            return ParentBasis(booked)
        return ParentBasis(
            {},
            refused=BASIS_STALE,
            detail={
                "external_id": str(parent["external_id"]),
                "computed_head": None,
                "stream_head": int(parent["head_stream_version"]),
                "reason": "no primary-book version of the latest computation",
            },
        )
    rows = [
        dict(row)
        for row in session.execute(
            select(
                obligation_version.c.obligation_id,
                obligation_version.c.obligation_key,
                obligation_version.c.product_code,
                obligation_version.c.quantity,
                obligation_version.c.stated_price,
                obligation_version.c.original_quantity,
                obligation_version.c.original_stated_price,
                obligation_version.c.principal_agent,
                obligation_version.c.start_date,
                obligation_version.c.end_date,
                obligation.c.parent_obligation_id,
                obligation.c.regrouped_from_obligation_id,
            )
            .select_from(
                obligation_version.join(
                    obligation, obligation.c.id == obligation_version.c.obligation_id
                )
            )
            .where(
                obligation_version.c.contract_version_id == version_id,
                obligation_version.c.contract_id == contract_id,
            )
            .order_by(obligation_version.c.obligation_key)
        ).mappings()
    ]
    reasons = _unsupported_reasons(rows, booked)
    if reasons:
        return ParentBasis(
            {},
            refused=BASIS_UNSUPPORTED,
            detail={"external_id": str(parent["external_id"]), "reasons": reasons},
        )
    basis: dict[str, dict[str, Any]] = {}
    unkeyed: list[str] = []
    for row in rows:
        key = row["obligation_key"]
        if key is None or not str(key).strip():
            unkeyed.append(str(row["obligation_id"]))
            continue
        basis[str(key)] = _basis_line(
            str(key),
            row["product_code"],
            row["quantity"],
            row["stated_price"],
            row["start_date"],
            row["end_date"],
        )
    return ParentBasis(basis, tuple(unkeyed))


def amendment_lines(
    draft: ports.NormalisedOrderDraft, parent_lines: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], ModificationKind]:
    """The mechanical ModificationLineV1 diff of an amendment against the parent's booked lines
    (ADD / REMOVE / CHANGE with signed deltas) and the provisional E-25 kind the preparer confirms
    at classification (pending Q-B)."""
    currency = draft.transaction_currency
    lines: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in draft.lines:
        seen.add(line.line_external_id)
        before = parent_lines.get(line.line_external_id)
        if before is None:
            lines.append(
                {
                    "obligation_key": line.line_external_id,
                    "action": "ADD",
                    "product_code": line.product_code,
                    "quantity_delta": format(line.quantity, "f"),
                    "consideration_delta": {
                        "amount": format(line.total_price, "f"),
                        "currency": currency,
                    },
                    "start_date": None if line.start_date is None else line.start_date.isoformat(),
                    "end_date": None if line.end_date is None else line.end_date.isoformat(),
                }
            )
            continue
        quantity_delta = line.quantity - Decimal(str(before["quantity"]))
        price_delta = line.total_price - Decimal(str(before["total_price"]))
        # A date the source does not send (None) is no date change; a sent date that differs is.
        dates_changed = (
            line.start_date is not None and line.start_date != before["start_date"]
        ) or (line.end_date is not None and line.end_date != before["end_date"])
        if quantity_delta == 0 and price_delta == 0 and not dates_changed:
            continue
        lines.append(
            {
                "obligation_key": line.line_external_id,
                "action": "CHANGE",
                "product_code": line.product_code,
                "quantity_delta": format(quantity_delta, "f"),
                "consideration_delta": {"amount": format(price_delta, "f"), "currency": currency},
                "start_date": None if line.start_date is None else line.start_date.isoformat(),
                "end_date": None if line.end_date is None else line.end_date.isoformat(),
            }
        )
    for key, before in parent_lines.items():
        if key in seen:
            continue
        lines.append(
            {
                "obligation_key": key,
                "action": "REMOVE",
                "product_code": str(before["product_code"]),
                "quantity_delta": format(-Decimal(str(before["quantity"])), "f"),
                "consideration_delta": {
                    "amount": format(-Decimal(str(before["total_price"])), "f"),
                    "currency": currency,
                },
            }
        )
    actions = {line["action"] for line in lines}
    if "ADD" in actions:
        kind = ModificationKind.ADD_OBLIGATION
    elif "REMOVE" in actions:
        kind = ModificationKind.REMOVE_OBLIGATION
    elif any(Decimal(line["consideration_delta"]["amount"]) != 0 for line in lines):
        kind = ModificationKind.PRICE_CHANGE
    elif any(Decimal(line["quantity_delta"]) != 0 for line in lines):
        kind = ModificationKind.QUANTITY_CHANGE
    else:
        kind = ModificationKind.TERM_CHANGE
    return lines, kind


def _candidate_unapplied(
    uow: UnitOfWork,
    draft: ports.NormalisedOrderDraft,
    message: str,
    *,
    source_record_id: UUID,
    sync_run_id: UUID,
    contract_id: UUID | None,
    counts: Counts,
) -> None:
    """04 §15.4-B ``MODIFICATION_CANDIDATE_UNAPPLIED`` (ERROR, X SYNC, remediable; D-98 146 A1
    Q-B): the amendment's candidate rows are stored, no modification drafted, one item to act on."""
    _raise(
        uow,
        counts,
        source=ExceptionSource.SYNC,
        code=MODIFICATION_CANDIDATE_UNAPPLIED,
        severity=severity_of("ERROR"),
        message=message,
        dedupe=dedupe_key(
            ExceptionSource.SYNC,
            MODIFICATION_CANDIDATE_UNAPPLIED,
            f"{draft.external_order_id}:{draft.external_version}",
        ),
        suggestion=AMENDMENT_SUGGESTION,
        business_key=draft.external_order_id,
        source_record_id=source_record_id,
        sync_run_id=sync_run_id,
        contract_id=contract_id,
        disposition=ExceptionDisposition.REMEDIABLE,
    )
    counts.exceptions += 1


def _route_amendment(
    uow: UnitOfWork,
    connection: Mapping[str, Any],
    draft: ports.NormalisedOrderDraft,
    order: grouping.NormalisedOrder,
    obj: ports.SourceObject,
    *,
    source_record_id: UUID,
    sync_run_id: UUID,
    counts: Counts,
) -> None:
    """ADP-05 (D-98 146 A1 Q-B, option (i)): the amendment's candidate rows are recorded; on an
    ACTIVE parent a DRAFT modification is opened with the mechanical line diff and a PROVISIONAL
    rule-derived kind the preparer confirms at classification (``questionnaire.kind_provisional``);
    no event is appended and no treatment is decided here. An unknown or non-ACTIVE parent raises
    ``MODIFICATION_CANDIDATE_UNAPPLIED`` instead."""
    # Imported here: the modification commands import the contracts package, which imports grouping.
    from erev_api.domain.contracts.modifications import create_modification
    from erev_api.schemas.modifications import ModificationCreateIn

    session = uow.session
    # The parent and its governed CURRENT basis (head projection, else the stream's booking) are
    # read BEFORE the candidate rows are recorded; neither source can contain a candidate
    # (Codex 0339 §1): order alone would not have been the fix.
    parent_external_id = str(draft.parent_order_external_id or draft.external_order_id)
    parent = _parent_contract(session, UUID(str(connection["id"])), parent_external_id)
    found = ParentBasis({}) if parent is None else _parent_basis(session, parent)
    if found.refused is not None:
        # Refused BY NAME before any row of the amendment is recorded (stale computation, or an
        # obligation that is not one unchanged source line): a retry after the recompute or a hand
        # modification re-ingests the stored record cleanly — no candidate rows, no draft.
        # F-ADM-ROUTE-DETAIL-1: the refusal's values (the parent's external id, the heads, the
        # reasons) travel NESTED under ``detail``; the record's own ``external_id`` stays the
        # refused amendment's (traceability of the exception evidence).
        _failure(
            counts,
            "amendment",
            obj,
            found.message,
            rule_id=found.refused,
            detail=dict(found.detail),
        )
        return
    basis, unkeyed = dict(found.lines), list(found.unkeyed)
    grouping.record_candidate(uow, order)
    counts.candidates += 1
    if parent is None:
        _candidate_unapplied(
            uow,
            draft,
            AMENDMENT_UNKNOWN_MESSAGE.format(
                order=draft.external_order_id, parent=parent_external_id
            ),
            source_record_id=source_record_id,
            sync_run_id=sync_run_id,
            contract_id=None,
            counts=counts,
        )
        return
    parent_id = UUID(str(parent["id"]))
    if str(parent["status"]) != ContractStatus.ACTIVE.value:
        _candidate_unapplied(
            uow,
            draft,
            AMENDMENT_NOT_ACTIVE_MESSAGE.format(
                order=draft.external_order_id,
                external_id=parent["external_id"],
                status=parent["status"],
            ),
            source_record_id=source_record_id,
            sync_run_id=sync_run_id,
            contract_id=parent_id,
            counts=counts,
        )
        return
    if unkeyed:
        # The current state carries no line external id for these obligations: reported by id,
        # never mapped by guess (team-lead's ruling on Codex 0339 §1).
        _failure(
            counts,
            "amendment",
            obj,
            "parent obligations without a line external id: " + ", ".join(unkeyed),
        )
        return
    lines, kind = amendment_lines(draft, basis)
    if not lines:
        _candidate_unapplied(
            uow,
            draft,
            AMENDMENT_NO_CHANGE_MESSAGE.format(
                order=draft.external_order_id, external_id=parent["external_id"]
            ),
            source_record_id=source_record_id,
            sync_run_id=sync_run_id,
            contract_id=parent_id,
            counts=counts,
        )
        return
    body = ModificationCreateIn.model_validate(
        {
            "effective_date": draft.order_date.isoformat(),
            "kind": kind.value,
            "reference": f"{draft.external_order_id}:{draft.external_version}",
            "lines": lines,
            # The kind is rule-derived and PROVISIONAL until the preparer classifies (Q-B).
            "questionnaire": {
                "source": "SYNC",
                "kind_provisional": True,
                "amendment_reason": draft.amendment_reason,
                "parent_order_external_id": parent_external_id,
            },
        }
    )
    try:
        create_modification(uow, contract_id=parent_id, body=body)
    except Problem as problem:
        _failure(
            counts,
            "amendment",
            obj,
            problem,
            errors=[dataclasses.asdict(e) for e in problem.errors],
        )
        return
    counts.modifications_drafted += 1


def _with_resolved_codes(
    draft: ports.NormalisedOrderDraft, resolved: Mapping[str, ResolvedProduct]
) -> ports.NormalisedOrderDraft:
    """The draft with every aliased line carrying the product record's own code (the source code
    stays in the stored payload); unresolved lines keep their source code."""
    lines = tuple(
        dataclasses.replace(line, product_code=resolved[line.product_code].product_code)
        if line.product_code in resolved and resolved[line.product_code].via_alias
        else line
        for line in draft.lines
    )
    return dataclasses.replace(draft, lines=lines)


def _rebook_draft(
    uow: UnitOfWork,
    contract_id: UUID,
    order: grouping.NormalisedOrder,
    obj: ports.SourceObject,
    *,
    sync_run_id: UUID,
    counts: Counts,
) -> bool:
    """04 §16.14 rev 1.81: a reprocessed record whose DRAFT contract exists is re-booked through the
    DRAFT-replacement path (the earlier booking voided and superseded — no duplicate event); the
    ADP-03 key's ordinal is the new stream version, so a repeated reprocess never repeats a key."""
    # Imported here: the contract commands reach grouping through ssp.resolution.
    from erev_api.domain.contracts.commands import replace_draft

    session = uow.session
    head = session.execute(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    ).scalar_one_or_none()
    if head is None:
        _failure(counts, "rebook", obj, f"contract {contract_id} not found")
        return False
    identity = SourceIdentity(
        obj.source_system, obj.object_type, obj.external_id, obj.external_version
    )
    try:
        replace_draft(
            uow,
            contract_id=contract_id,
            expected_stream_version=int(head),
            body=grouping.booking_body(order),
            origin="ADAPTER",
            idempotency_key=normalise.adapter_event_key(identity, int(head) + 1),
            source_record_id=order.source_record_id,
            sync_run_id=sync_run_id,
        )
    except Problem as problem:
        _failure(
            counts, "rebook", obj, problem, errors=[dataclasses.asdict(e) for e in problem.errors]
        )
        return False
    counts.rebooked += 1
    return True


def _reuse_admitted(
    uow: UnitOfWork,
    connection_id: UUID,
    stored: grouping.StoredOrder,
    draft: ports.NormalisedOrderDraft,
    obj: ports.SourceObject,
    *,
    source_record_id: UUID,
    counts: Counts,
) -> bool:
    """The three-class reuse check of 04 §16.14 rev 1.81 against the stored rows, before any write:
    class A (retained source-authored facts — the retained tokenised payload digest, the header and
    line members incl. the SOURCE product code) must be equal, else
    ``SOURCE_ORDER_CONTENT_MISMATCH``; class C (the entity when defaulted, the mapping version, the
    customer resolution, the grouping values — derived from the CURRENT connection configuration or
    mapping) must equal the values frozen at first ingestion, else
    ``SOURCE_ORDER_DERIVATION_CHANGED``. Both are this object's failure record, the differing
    members named; the stored rows are never rewritten."""
    session = uow.session
    same_content = grouping.same_digest(session, stored.source_record_id, source_record_id)
    # Codex 0652 §1: rows stored before the source-code rule may carry the alias target as their
    # code — admitted only through the alias lineage in force at their receipt (non-mutating); rev
    # 1.91 (Codex 1442 §1 / 1508 §1): the lineage carries the product's code AT the receipt, located
    # by the row's source_order.create audit anchor and walked back by CHAIN POSITION (never by
    # clock); unanchored history keeps the current code and is named in the failure record.
    lineage = grouping.alias_lineage_at(
        session,
        connection_id,
        {line.product_code for line in draft.lines},
        stored.header.get("created_at"),
        tenant_id=uow.principal.tenant_id,
        order_id=stored.id,
    )
    content = grouping.content_conflicts(
        stored, draft, same_content=same_content, aliased_at_receipt=lineage.targets
    )
    if content:
        history = grouping.history_of(lineage, content, draft)
        unverified = sorted(
            {entry["evidence"] for entry in history.values()}
            - {grouping.HistoryState.RECEIPT_ANCHORED.value}
        )
        error = grouping.CONTENT_MISMATCH.format(
            order=draft.external_order_id,
            version=draft.external_version,
            members=", ".join(content),
        )
        if unverified:
            error += grouping.HISTORY_UNVERIFIED.format(states=", ".join(unverified))
        detail: dict[str, Any] = {
            "members": content,
            "stored_record": str(stored.source_record_id),
            "incoming_record": str(source_record_id),
        }
        if history:
            detail["history"] = history
        _failure(counts, "reuse", obj, error, rule_id=grouping.CONTENT_RULE, detail=detail)
        return False
    customer_now = lookup_customer(session, connection_id, draft)
    fields = grouping.grouping_fields(session, known_at=uow.now)
    provisional = _normalised_order(
        draft,
        source_record_id=source_record_id,
        customer_id=customer_now or UUID(str(stored.header["customer_id"])),
    )
    derivation = grouping.derivation_conflicts(
        stored,
        draft,
        customer_id=customer_now,
        grouping=grouping.grouping_values(provisional, fields),
    )
    if derivation:
        _failure(
            counts,
            "reuse",
            obj,
            grouping.DERIVATION_CHANGED.format(
                order=draft.external_order_id,
                version=draft.external_version,
                members=", ".join(derivation),
            ),
            rule_id=grouping.DERIVATION_RULE,
            detail={"members": derivation, "stored_record": str(stored.source_record_id)},
        )
        return False
    return True


def ingest_draft(
    uow: UnitOfWork,
    connection: Mapping[str, Any],
    draft: ports.NormalisedOrderDraft,
    obj: ports.SourceObject,
    *,
    source_record_id: UUID,
    sync_run_id: UUID,
    counts: Counts,
    reprocess: bool = False,
) -> None:
    """One normalised order through validation, matching and booking (S01-R-03; S02-R-13). Products
    resolve by code or through the connection's alias (04 §16.14 rev 1.81); an order with unmapped
    lines is booked as a DRAFT from its MAPPED lines and its ``PRODUCT_UNMAPPED`` items name that
    contract; a reprocess of a record whose DRAFT exists re-books it with every line mapped."""
    session = uow.session
    connection_id = UUID(str(connection["id"]))
    # 04 §16.14 rev 1.81 (Codex 0545 §2 R1 / 0603 §4 / 0606): a stored order identity is REUSED,
    # never stored again; the three-class check runs here, BEFORE any write (no candidate rows, no
    # customer, no booking on a refusal). Class A compares the ORIGINAL draft (the source product
    # codes, before the alias rewrites them); class C the current derivation; class B (the product
    # resolution) is re-derived below.
    stored = grouping.stored_order(
        session,
        source_system=draft.source_system,
        external_order_id=draft.external_order_id,
        external_version=draft.external_version,
    )
    stored_customer: UUID | None = None
    if stored is not None:
        admitted = _reuse_admitted(
            uow,
            connection_id,
            stored,
            draft,
            obj,
            source_record_id=source_record_id,
            counts=counts,
        )
        if not admitted:
            return
        stored_customer = UUID(str(stored.header["customer_id"]))
    codes = {line.product_code for line in draft.lines}
    resolved = resolve_products(session, connection_id, codes)
    missing = sorted(codes - set(resolved))
    original = draft  # the SOURCE codes: what the stored rows keep (Codex 0652 §1)
    draft = _with_resolved_codes(draft, resolved)
    mapped_keys = frozenset(
        line.line_external_id
        for line, source in zip(draft.lines, obj_lines(draft, resolved), strict=True)
        if source
    )
    customer_id = (
        stored_customer  # class C: taken from the stored rows (equal to the current derivation)
        if stored_customer is not None
        else resolve_customer(uow, connection, draft, sync_run_id=sync_run_id, counts=counts)
    )
    order = _normalised_order(
        original, source_record_id=source_record_id, customer_id=customer_id, resolved=resolved
    )
    if draft.is_amendment:
        if missing:
            grouping.record_candidate(uow, order)
            counts.candidates += 1
            _unmapped_products(
                uow,
                draft,
                missing,
                source_record_id=source_record_id,
                sync_run_id=sync_run_id,
                counts=counts,
            )
            return
        _route_amendment(
            uow,
            connection,
            draft,
            order,
            obj,
            source_record_id=source_record_id,
            sync_run_id=sync_run_id,
            counts=counts,
        )
        return
    linked = _live_link(
        session, connection_id, CONTRACT_OBJECT, external_id=draft.external_order_id
    )
    if reprocess and linked is not None and not missing:
        # 04 §16.14 rev 1.81 (Codex 0545 §2 R1): the record's source_order rows exist from the first
        # ingestion and are IM-A — nothing is stored again; the re-booking's lineage is the new
        # CONTRACT_BOOKED event (source_record_id, sync_run_id) with the existing T-CON-02 link.
        contract_id = UUID(str(linked["internal_id"]))
        _rebook_draft(uow, contract_id, order, obj, sync_run_id=sync_run_id, counts=counts)
        return
    if missing and not mapped_keys:
        grouping.record_candidate(uow, order)
        counts.candidates += 1
        _unmapped_products(
            uow,
            draft,
            missing,
            source_record_id=source_record_id,
            sync_run_id=sync_run_id,
            counts=counts,
        )
        return
    try:
        routed = grouping.ingest_order(
            uow, order, sync_run_id=sync_run_id, booked_lines=mapped_keys if missing else None
        )
    except Problem as problem:
        _failure(
            counts, "book", obj, problem, errors=[dataclasses.asdict(e) for e in problem.errors]
        )
        return
    if routed.outcome is grouping.GroupingOutcome.NEW_CONTRACT:
        counts.contracts_booked += 1
        link_external_id(
            uow,
            connection_id,
            object_type=CONTRACT_OBJECT,
            internal_id=routed.contract_id,
            external_id=draft.external_order_id,
            external_version=draft.external_version,
            sync_run_id=sync_run_id,
        )
    else:
        counts.candidates += 1
    if missing:
        _unmapped_products(
            uow,
            draft,
            missing,
            source_record_id=source_record_id,
            sync_run_id=sync_run_id,
            counts=counts,
            contract_id=routed.contract_id,
        )


def _gap(
    uow: UnitOfWork,
    obj: ports.SourceObject,
    *,
    record_id: UUID,
    sync_run_id: UUID,
    counts: Counts,
) -> None:
    """REQ-INT-007 (04 table 15.4-B ``SOURCE_VERSION_GAP``; PRD IMP-126): a reconciliation sweep
    stored a version ``source_record`` did not hold — the feed never delivered it. The item names
    the object, the version and the run; the stored record is named in its payload, not in
    ``source_record_id``, so the queue offers no reprocess of a record the sweep processes itself
    (what that processing raises or refuses is reported on its own). Severity INFO (ruling R-45
    (a)): nothing is left to clear, so the item never holds a period lock."""
    subject = (
        f"{obj.source_system.value}:{obj.object_type.value}:{obj.external_id}"
        f":{obj.external_version}"
    )
    _raise(
        uow,
        counts,
        source=ExceptionSource.SYNC,
        code=SOURCE_VERSION_GAP,
        severity=severity_of("INFO"),
        message=GAP_MESSAGE.format(
            source_system=obj.source_system.value,
            object=obj.object_type.value,
            external_id=obj.external_id,
            version=obj.external_version,
        ),
        dedupe=dedupe_key(ExceptionSource.SYNC, SOURCE_VERSION_GAP, subject),
        business_key=obj.external_id,
        source_payload={
            "detail": {
                "source_system": obj.source_system.value,
                "object_type": obj.object_type.value,
                "external_id": obj.external_id,
                "external_version": obj.external_version,
                "source_record_id": str(record_id),
            }
        },
        sync_run_id=sync_run_id,
    )
    counts.gaps += 1
    counts.exceptions += 1


def _contract_not_found(
    uow: UnitOfWork,
    draft: ports.NormalisedInvoiceDraft,
    reference: str,
    *,
    source_record_id: UUID,
    sync_run_id: UUID,
    counts: Counts,
) -> None:
    """05 §5.1 (referential validation → exception item): a billing document names a source
    contract — a Stripe subscription — that is linked to no contract of this connection. The item
    is remediable and carries the stored record, so a reprocess applies the document once the
    subscription is ingested (PRD IMP-20 copy)."""
    _raise(
        uow,
        counts,
        source=ExceptionSource.SYNC,
        code=CONTRACT_NOT_FOUND,
        severity=severity_of("ERROR"),
        message=CONTRACT_NOT_FOUND_MESSAGE.format(contract=reference),
        dedupe=dedupe_key(
            ExceptionSource.SYNC,
            CONTRACT_NOT_FOUND,
            f"{draft.source_system.value}:{draft.external_invoice_id}:{reference}",
        ),
        suggestion=DOCUMENT_SUGGESTION,
        business_key=draft.invoice_number,
        source_payload={
            "detail": {
                "contract_ref": reference,
                "document_kind": draft.document_kind,
                "external_invoice_id": draft.external_invoice_id,
                "external_version": draft.external_version,
            }
        },
        source_record_id=source_record_id,
        sync_run_id=sync_run_id,
        disposition=ExceptionDisposition.REMEDIABLE,
    )
    counts.exceptions += 1


def ingest_document(
    uow: UnitOfWork,
    connection: Mapping[str, Any],
    draft: ports.NormalisedInvoiceDraft,
    obj: ports.SourceObject,
    *,
    source_record_id: UUID,
    sync_run_id: UUID,
    counts: Counts,
) -> None:
    """One normalised invoice or credit note (05 ADP-17; REQ-INT-005; ``documents``). Each line
    names its contract by the source's reference — a subscription id — resolved through T-INT-04; a
    credit note's line without one takes the single contract of the invoice it credits. The
    document is applied whole or not at all: a reference linked to no contract raises
    ``CONTRACT_NOT_FOUND`` (remediable) and nothing is stored; a refusal of the events — the 05
    §3.9 bounds, the §16.3 identity rules — is a failure record of step ``bill`` naming the rule."""
    session = uow.session
    connection_id = UUID(str(connection["id"]))
    credited: Mapping[str, Any] | None = None
    inherited: list[str] = []
    if draft.document_kind == documents.CREDIT_MEMO:
        credited = documents.credited_invoice(session, draft)
        if credited is None:
            _failure(
                counts,
                BILL_STEP,
                obj,
                f"credit note {draft.invoice_number} names invoice "
                f"{draft.credited_invoice_external_id}, of which no version is stored",
            )
            return
        inherited = sorted(
            {
                str(row["contract_ref"])
                for row in documents.document_lines(session, UUID(str(credited["id"])))
                if row["contract_ref"]
            }
        )
    by_reference: dict[str, list[tuple[int, ports.NormalisedInvoiceLine]]] = {}
    for ordinal, line in enumerate(draft.lines, start=1):
        reference = line.contract_ref
        if reference is None and len(inherited) == 1:
            reference = inherited[0]
        if reference is None:
            _failure(
                counts,
                BILL_STEP,
                obj,
                f"line {line.line_external_id} of {draft.invoice_number} names no contract",
            )
            return
        by_reference.setdefault(reference, []).append((ordinal, line))
    contracts: dict[str, Mapping[str, Any]] = {}
    missing: list[str] = []
    for reference in by_reference:
        found = _parent_contract(session, connection_id, reference)
        if found is None:
            missing.append(reference)
        else:
            contracts[reference] = found
    if missing:
        for reference in missing:
            _contract_not_found(
                uow,
                draft,
                reference,
                source_record_id=source_record_id,
                sync_run_id=sync_run_id,
                counts=counts,
            )
        return
    first = contracts[next(iter(by_reference))]
    credit = draft.document_kind == documents.CREDIT_MEMO
    try:
        with uow.savepoint():
            already = documents.stored_document(session, draft) is not None
            invoice_id = documents.store_document(
                uow,
                draft,
                source_record_id=source_record_id,
                customer_id=UUID(str(first["customer_id"])),
                contracting_entity_id=UUID(str(first["contracting_entity_id"])),
            )
            appended = 0
            for reference, lines in by_reference.items():
                contract_id = UUID(str(contracts[reference]["id"]))
                rows = documents.append_document(
                    uow,
                    draft,
                    lines,
                    contract_id=contract_id,
                    source_invoice_id=invoice_id,
                    source_record_id=source_record_id,
                    sync_run_id=sync_run_id,
                    credited_invoice_number=(
                        None if credited is None else str(credited["invoice_number"])
                    ),
                )
                # a replayed key answers its stored event, which names the run that appended it
                appended += sum(1 for row in rows if row["sync_run_id"] == sync_run_id)
                documents.link_document(
                    uow,
                    contract_id=contract_id,
                    source_record_id=source_record_id,
                    event_id=UUID(str(rows[0]["id"])),
                )
            # PRD ERR-72 for what the document recorded: the run computes nothing, and the
            # computation that follows records nothing and is not judged (supervisor ruling
            # R-122 (j); item PIN-WINDOW-APPENDER-1).
            # Imported here: the contract commands reach this package through ssp.resolution.
            from erev_api.domain.contracts import period_ends

            period_ends.refuse_appends_a_lock_met(
                uow, _groups_of(session, (UUID(str(row["id"])) for row in contracts.values()))
            )
    except Problem as problem:
        if is_period_state_moved(problem):
            # Not this document's failure. A failure record would leave the stored record with no
            # way back — no item names it, and neither the feed nor a sweep brings a stored
            # version again (measured: the invoice was never recorded). The run's transaction is
            # refused whole and the job applies its objects once more (``run_sync``).
            raise
        _failure(
            counts,
            BILL_STEP,
            obj,
            problem,
            errors=[dataclasses.asdict(e) for e in problem.errors],
        )
        return
    if not already:
        counts.documents += 1
    if credit:
        counts.credit_memo_events += appended
    else:
        counts.billing_events += appended


def obj_lines(
    draft: ports.NormalisedOrderDraft, resolved: Mapping[str, ResolvedProduct]
) -> list[bool]:
    """Per line, whether its product resolved (by its record code after aliasing)."""
    resolved_codes = {item.product_code for item in resolved.values()} | set(resolved)
    return [line.product_code in resolved_codes for line in draft.lines]


def apply_object(
    uow: UnitOfWork,
    adapter: ports.InboundAdapter,
    connection: Mapping[str, Any],
    obj: ports.SourceObject,
    *,
    notified_versions: Sequence[str],
    sync_run_id: UUID,
    counts: Counts,
    loaded: list[tuple[str, str, str, Decimal]],
    stored_id: UUID | None = None,
    sweep_gaps: bool = False,
) -> bool:
    """Steps receive → store → normalise → ingest for one fetched object; True when the object
    counts in the source totals (stored now, whatever the ingestion outcome). ``stored_id`` names an
    already-stored record a reprocess applies again (04 §16.14 rev 1.81): no store, no duplicate
    branch — identity retained. ``sweep_gaps`` says the run is a reconciliation sweep of a
    connection whose baseline sweep is complete: a version stored now is one the feed never
    delivered and raises ``SOURCE_VERSION_GAP`` before it is processed (REQ-INT-007)."""
    for version in notified_versions:
        if version_rank(version) < version_rank(obj.external_version):
            _stale_notification(uow, obj, version, sync_run_id=sync_run_id, counts=counts)
    if stored_id is None:
        identity = SourceIdentity(
            obj.source_system, obj.object_type, obj.external_id, obj.external_version
        )
        stored = normalise.store_source_record(
            uow,
            identity=identity,
            version_order=obj.version_order,
            payload=obj.payload,
            sync_run_id=sync_run_id,
        )
        if stored.outcome is StoreOutcome.DUPLICATE:
            counts.duplicates += 1
            return False
        if stored.outcome is StoreOutcome.STALE:
            counts.stale += 1
            counts.exceptions += 1
            return False
        record_id = stored.id
        counts.records += 1
        if sweep_gaps:
            _gap(uow, obj, record_id=record_id, sync_run_id=sync_run_id, counts=counts)
    else:
        # The stored record is applied again: it counts as a record of THIS run (its totals).
        record_id = stored_id
        counts.records += 1
        counts.reprocessed += 1
    try:
        records = adapter.normalise(obj, mapping_version_of(connection))
    except ports.Permanent as error:
        _failure(counts, "normalise", obj, error)
        return False
    # 04 §16.14 rev 1.81 (Codex 0545 §2 R2 / 0606): the return value below is INCLUSION IN THE
    # CONTROL TOTALS, whatever the ingestion outcome. Successful processing is a DISTINCT outcome:
    # the record is processed only when its application recorded no failure and raised no item.
    failures_before, raised_before = len(counts.failures), len(counts.raised_keys)
    for draft in records.orders:
        loaded.append(
            (obj.external_id, obj.external_version, draft.transaction_currency, draft.total)
        )
        ingest_draft(
            uow,
            connection,
            draft,
            obj,
            source_record_id=record_id,
            sync_run_id=sync_run_id,
            counts=counts,
            reprocess=stored_id is not None,
        )
    for document in records.invoices:
        loaded.append((obj.external_id, obj.external_version, document.currency, document.total))
        ingest_document(
            uow,
            connection,
            document,
            obj,
            source_record_id=record_id,
            sync_run_id=sync_run_id,
            counts=counts,
        )
    if len(counts.failures) == failures_before and len(counts.raised_keys) == raised_before:
        counts.processed_records.add(record_id)
    return True


def stored_objects(
    session: Session, record_ids: Sequence[UUID]
) -> tuple[tuple[UUID, ports.SourceObject], ...]:
    """The stored source records a reprocess applies again, as source objects (the tokenised
    payload is the stored truth; identity retained)."""
    rows = session.execute(
        select(source_record).where(source_record.c.id.in_(list(record_ids)))
    ).mappings()
    found: list[tuple[UUID, ports.SourceObject]] = []
    for row in rows:
        found.append(
            (
                UUID(str(row["id"])),
                ports.SourceObject(
                    source_system=SourceSystem(str(row["source_system"])),
                    object_type=SourceObjectType(str(row["object_type"])),
                    external_id=str(row["external_id"]),
                    external_version=str(row["external_version"]),
                    version_order=int(row["version_order"]),
                    payload=dict(row["payload"] or {}),
                ),
            )
        )
    return tuple(found)


def request_record_reprocess(uow: UnitOfWork, item: Mapping[str, Any]) -> JobOut:
    """The SYNC reprocessor (``exceptions.REPROCESSORS[SYNC]``; 04 §16.14 rev 1.81): a QUEUED
    ``INBOUND_POLL`` run of the item's run's connection whose params name the stored record and
    the item; the ``SYNC_RUN`` job applies the record again and settles the item."""
    # Imported here: the commands module imports this one.
    from erev_api.domain.integrations import commands
    from erev_api.domain.platform.jobs import job_out_of

    session = uow.session
    run = queries.get_sync_run_row(session, UUID(str(item["sync_run_id"])))
    connection = queries.get_connection_row(
        session, UUID(str(run["integration_connection_id"])), lock=True
    )
    if commands.is_inbound(str(connection["adapter"]), str(connection["direction"])):
        commands.refuse_inbound_in_sandbox(
            uow,
            action=commands.SYNC_REQUEST_ACTION,
            object_type=commands.SYNC_RUN_OBJECT,
            object_id=None,
            detail={"integration_connection_id": str(connection["id"]), "reprocess": True},
        )
    requested = commands._queue_run(
        uow,
        connection,
        kind=INBOUND_POLL,
        action=commands.SYNC_REQUEST_ACTION,
        notifications=None,
        extra_params={
            REPROCESS_PARAM: [str(item["source_record_id"])],
            REPROCESS_ITEM_PARAM: str(item["id"]),
        },
    )
    return job_out_of(session, requested.job_id)


def _settle_item(
    uow: UnitOfWork, item_id: UUID, counts: Counts, *, attempted: Collection[UUID]
) -> bool:
    """04 §16.14 rev 1.81 (Codex 0545 §2 R2 / 0606): the SAME item is resolved ("Input processed")
    only when (a) its stored record was PROCESSED by this run (applied with no failure recorded and
    no item raised for it — a distinct outcome from control-total inclusion), (b) its own dedupe key
    was NOT raised again (the same code for the same subject; a partially repaired order keeps its
    other ``PRODUCT_UNMAPPED`` item open) and (c) no failure record of this run carries the record's
    identity (``external_id`` + ``external_version``). Otherwise the item stays open, its occurrence
    counted by the re-run. ``reprocessed_at`` is truthful: the item is touched only when the
    reprocess actually ran over its record (``attempted``). ENGINE settle is
    ``exceptions.settle_reprocess``, untouched."""
    session = uow.session
    row = (
        session.execute(select(exception_item).where(exception_item.c.id == item_id))
        .mappings()
        .one_or_none()
    )
    if row is None or row["source_record_id"] is None:
        return False
    record = UUID(str(row["source_record_id"]))
    if record not in set(attempted):
        return False  # not run over: no settlement, no ``reprocessed_at``
    identity = session.execute(
        select(source_record.c.external_id, source_record.c.external_version).where(
            source_record.c.id == record
        )
    ).one_or_none()
    processed = record in counts.processed_records
    raised_again = str(row["dedupe_key"]) in counts.raised_keys
    failed = identity is not None and any(
        str(failure.get("external_id")) == str(identity[0])
        and str(failure.get("external_version")) == str(identity[1])
        for failure in counts.failures
    )
    resolved = processed and not raised_again and not failed
    exception_queue.settle_record_reprocess(uow, item_id, resolved=resolved)
    return resolved


exception_queue.REPROCESSORS[ExceptionSource.SYNC] = request_record_reprocess


def run_problem(
    slug: str, detail: str, *, run_id: UUID, failures: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The stored ``sync_run.problem`` of a FAILED run (04 T-INT-02 rev 1.90): the T-PLT-27 RFC 9457
    envelope of the catalogue problem ``slug`` — ``type``, ``title`` (the catalogue's), ``status``,
    ``detail``, ``instance`` (the run's API path), ``code``, ``errors`` (API-C-05-shaped, empty) —
    plus the RFC 9457 EXTENSION member ``failures``: the failure records verbatim."""
    problem = Problem(slug, detail, failures=[dict(item) for item in failures])
    return problem.to_json(instance=SYNC_RUN_INSTANCE.format(run_id=run_id))


def _problem(
    counts: Counts,
    *,
    run_id: UUID,
    fetch_failures: Sequence[Mapping[str, Any]],
    cancelled: bool,
) -> dict[str, Any] | None:
    """The run's own problem, or None when every object was applied: ``sync-objects-not-applied``
    with the PRD ERR-56 detail (the failed / total counts, or the cancelled sentence)."""
    failures = [dict(item) for item in fetch_failures] + list(counts.failures)
    if cancelled:
        detail = CANCELLED_DETAIL.format(applied=counts.records)
        return run_problem(SYNC_OBJECTS_NOT_APPLIED, detail, run_id=run_id, failures=failures)
    if not failures:
        return None
    detail = NOT_APPLIED_DETAIL.format(
        failed=len(failures), total=counts.records + len(fetch_failures)
    )
    return run_problem(SYNC_OBJECTS_NOT_APPLIED, detail, run_id=run_id, failures=failures)


def _totals_mismatch(
    uow: UnitOfWork,
    *,
    run_id: UUID,
    source: ports.ControlTotals,
    loaded: ports.ControlTotals,
    counts: Counts,
) -> None:
    item = _raise(
        uow,
        counts,
        source=ExceptionSource.SYNC,
        code=CONTROL_TOTALS_MISMATCH,
        severity=severity_of("ERROR"),
        message=TOTALS_MISMATCH_MESSAGE.format(
            source=source.as_json(), loaded=loaded.as_json(), run=run_id
        ),
        dedupe=dedupe_key(ExceptionSource.SYNC, CONTROL_TOTALS_MISMATCH, run_id),
        business_key=str(run_id),
        sync_run_id=run_id,
        disposition=ExceptionDisposition.REMEDIABLE,
    )
    counts.exceptions += 1
    connection = (
        uow.session.execute(
            select(integration_connection)
            .join(sync_run, sync_run.c.integration_connection_id == integration_connection.c.id)
            .where(sync_run.c.id == run_id)
        )
        .mappings()
        .one()
    )
    owner_id = connection["owner_membership_id"]
    if item.created and owners.eligible(uow, owner_id, connection["entity_ids"]):
        uow.session.execute(
            update(exception_item)
            .where(exception_item.c.id == item.id)
            .values(
                owner_membership_id=owner_id,
                row_version=exception_item.c.row_version + 1,
            )
        )
        uow.audit(
            action=exception_queue.ASSIGN_ACTION,
            object_type="exception_item",
            object_id=item.id,
            before={"owner_membership_id": None},
            after={"owner_membership_id": str(owner_id)},
        )
        notify(
            uow,
            recipient_membership_ids=[owner_id],
            kind=NotificationKind.EXCEPTION_ASSIGNED,
            title=f"Exception: {CONTROL_TOTALS_MISMATCH}",
            body=TOTALS_MISMATCH_MESSAGE.format(
                source=source.as_json(), loaded=loaded.as_json(), run=run_id
            ),
            link_path=f"/data/exceptions/{item.id}",
            subject_type="exception_item",
            subject_id=item.id,
        )


def _finish(
    uow: UnitOfWork,
    *,
    run_id: UUID,
    connection: Mapping[str, Any],
    status: str,
    checkpoint_after: Mapping[str, Any],
    advance_checkpoint: bool,
    source: ports.ControlTotals,
    loaded: ports.ControlTotals,
    counts: Counts,
    problem: Mapping[str, Any] | None,
) -> None:
    transitions.apply(
        uow.session,
        "sync_run",
        run_id,
        to_status=status,
        set_values={
            "checkpoint_after": dict(checkpoint_after),
            "source_totals": source.as_json(),
            "loaded_totals": loaded.as_json(),
            "record_count": counts.records,
            "exception_count": counts.exceptions,
            "problem": None if problem is None else dict(problem),
            "finished_at": uow.now,
            **_moved(uow),
        },
        expected_status=SyncRunStatus.RUNNING.value,
    )
    if advance_checkpoint:
        # T-INT-01 ``checkpoint`` is AUD-OPS: the run row is its record (04 T-INT-01 class note).
        uow.session.execute(
            update(integration_connection)
            .where(integration_connection.c.id == connection["id"])
            .values(checkpoint=dict(checkpoint_after), **_touch(uow))
        )


def run_problem_of(
    counts: Counts, *, run_id: UUID, fetch_failures: Sequence[Mapping[str, Any]]
) -> dict[str, Any] | None:
    """The run's own problem for the runner of another kind (``coa_sync.run_chart_sync``): the
    ``sync-objects-not-applied`` envelope of its failure records, or None when there is none."""
    return _problem(counts, run_id=run_id, fetch_failures=fetch_failures, cancelled=False)


def finish_run(
    uow: UnitOfWork,
    *,
    run_id: UUID,
    connection: Mapping[str, Any],
    status: str,
    source: ports.ControlTotals,
    loaded: ports.ControlTotals,
    counts: Counts,
    problem: Mapping[str, Any] | None,
) -> None:
    """Finish a run that moves no checkpoint (``COA_SYNC``): the terminal status, both totals,
    the counts and the problem on the T-INT-02 row; ``checkpoint_after`` restates the
    connection's."""
    _finish(
        uow,
        run_id=run_id,
        connection=connection,
        status=status,
        checkpoint_after=dict(connection["checkpoint"] or {}),
        advance_checkpoint=False,
        source=source,
        loaded=loaded,
        counts=counts,
        problem=problem,
    )


def _start(uow: UnitOfWork, run_id: UUID) -> tuple[Mapping[str, Any], Mapping[str, Any], str]:
    run = queries.get_sync_run_row(uow.session, run_id, lock=True)
    if str(run["status"]) != SyncRunStatus.QUEUED.value:
        raise Problem("invalid-transition", f"sync run {run_id} is {run['status']}, not QUEUED")
    connection = queries.get_connection_row(
        uow.session, UUID(str(run["integration_connection_id"])), lock=True
    )
    transitions.apply(
        uow.session,
        "sync_run",
        run_id,
        to_status=SyncRunStatus.RUNNING.value,
        set_values={"started_at": uow.now, **_moved(uow)},
        expected_status=SyncRunStatus.QUEUED.value,
    )
    return run, connection, tenant_code_of(uow.session, uow.principal.tenant_id)


def sync_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    """The job's last attempt failed: the run ends FAILED with the job's problem (BUILD_SPEC RPS-2
    hook); a run already finished is left alone."""
    run_id = UUID(str(params["sync_run_id"]))
    row = uow.session.execute(
        select(sync_run.c.status).where(sync_run.c.id == run_id)
    ).scalar_one_or_none()
    if row is None or str(row) not in (SyncRunStatus.QUEUED.value, SyncRunStatus.RUNNING.value):
        return
    transitions.apply(
        uow.session,
        "sync_run",
        run_id,
        to_status=SyncRunStatus.FAILED.value,
        set_values={"problem": dict(problem), "finished_at": uow.now, **_moved(uow)},
        expected_status=str(row),
    )


def failed_sync(
    session: Session, subject_type: str | None, subject_id: UUID, params: Mapping[str, Any]
) -> FailedSubject | None:
    """05 JOB-07 rev 1.165: what the exception item of a failed sync names — the one legal
    entity the run's connection serves (04 T-INT-01 ``entity_ids``), with the run. A connection
    of no entity or of several raises no item. Every sync is a run of its own, so the record is
    the connection and the run's kind: a later run of that kind on the connection settles the
    item."""
    found = session.execute(
        select(
            sync_run.c.integration_connection_id,
            sync_run.c.kind,
            integration_connection.c.entity_ids,
        )
        .join(
            integration_connection,
            integration_connection.c.id == sync_run.c.integration_connection_id,
        )
        .where(sync_run.c.id == subject_id)
    ).one_or_none()
    if found is None or not found.entity_ids or len(found.entity_ids) != 1:
        return None
    kind = getattr(found.kind, "value", found.kind)
    return FailedSubject(
        entity_id=UUID(str(found.entity_ids[0])),
        key=f"{found.integration_connection_id}:{kind}",
        sync_run_id=subject_id,
    )


@task(
    JobKind.SYNC_RUN,
    retry=RetryPolicy(max_attempts=1),
    on_failure=sync_failed,
    failed_item=failed_item(ExceptionSource.SYNC, failed_sync),
)
def run_sync(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``SYNC_RUN``: ``params.sync_run_id`` through start → fetch → apply (module docstring); a
    ``COA_SYNC`` run is started here and handed to ``coa_sync.run_chart_sync`` (DIN-14)."""
    run_id = UUID(str(params["sync_run_id"]))
    kind = str(params.get("kind") or INBOUND_POLL)
    log = get_logger(_LOGGER)
    with sync_unit_of_work(jc) as uow:
        _run, connection, tenant_code = _start(uow, run_id)
        uow.commit()
    if kind == COA_SYNC:
        # Imported here: ``coa_sync`` finishes the run through this module's ledger helpers.
        from erev_api.domain.integrations import coa_sync

        return coa_sync.run_chart_sync(
            jc, run_id=run_id, connection=connection, tenant_code=tenant_code
        )
    connection_id = UUID(str(connection["id"]))
    checkpoint = ports.Checkpoint.from_json(connection.get("checkpoint"))
    adapter = adapter_for(connection, tenant_code=tenant_code, clock=jc.clock)
    record_ids = [UUID(str(value)) for value in (params.get(REPROCESS_PARAM) or ())]
    item_id = params.get(REPROCESS_ITEM_PARAM)
    reprocess = bool(record_ids)
    if reprocess:
        # 04 §16.14 rev 1.81: a reprocess applies the STORED records again — no fetch, no
        # checkpoint movement; the run is marked by its params.
        collected = Collected((), checkpoint, 0, False)
        fetched = Fetched((), MappingProxyType({}), (), 0)
    else:
        collected = collect_changes(
            adapter,
            kind=kind,
            checkpoint=checkpoint,
            notifications=params.get("notifications"),
            cancelled=jc.cancel_requested,
        )
        unique, repeats = unique_notifications(collected.notifications)
        fetched = fetch_objects(adapter, unique)
    jc.heartbeat()
    duplicates = 0 if reprocess else repeats
    # REQ-INT-007 (04 table 15.4-B rev 1.103): the first sweep a connection completes is its
    # baseline load; after it, a version a sweep stores is one the feed never delivered.
    sweep_gaps = collected.swept and checkpoint.swept_at is not None
    sweep_completed = (
        collected.swept
        and not collected.cancelled
        and collected.checkpoint_after.sweep_cursor is None
    )

    def apply_once() -> tuple[str, Counts]:
        """The run's apply transaction — every object, the run's end and the checkpoint — with
        counts of its own: an attempt that is refused whole leaves nothing, its counts included."""
        counts = Counts(
            notifications=len(collected.notifications),
            duplicates=duplicates,
            fetched=fetched.attempts,
        )
        loaded: list[tuple[str, str, str, Decimal]] = []
        applied: list[ports.SourceObject] = []
        with sync_unit_of_work(jc) as uow:
            stored = stored_objects(uow.session, record_ids) if reprocess else ()
            stored_ids = {id(obj): record_id for record_id, obj in stored}
            ordered = (
                [obj for _, obj in stored] if reprocess else ordered_for_processing(fetched.objects)
            )
            for index, obj in enumerate(ordered, start=1):
                notified = fetched.notified_versions.get((obj.object_type, obj.external_id), ())
                if apply_object(
                    uow,
                    adapter,
                    connection,
                    obj,
                    notified_versions=notified,
                    sync_run_id=run_id,
                    counts=counts,
                    loaded=loaded,
                    stored_id=stored_ids.get(id(obj)),
                    sweep_gaps=sweep_gaps,
                ):
                    applied.append(obj)
                jc.progress(index, len(ordered))
            if reprocess and item_id is not None:
                attempted = {record_id for record_id, _ in stored}  # the records this run ran over
                _settle_item(uow, UUID(str(item_id)), counts, attempted=attempted)
            source_totals = (
                adapter.control_totals(applied) if applied else ports.ControlTotals.of([])
            )
            loaded_totals = ports.ControlTotals.of(loaded)
            problem = _problem(
                counts,
                run_id=run_id,
                fetch_failures=fetched.failures,
                cancelled=collected.cancelled,
            )
            if problem is not None:
                status = SyncRunStatus.FAILED.value
            else:
                status = ports.compare_totals(source_totals, loaded_totals)
                if status == SyncRunStatus.CONTROL_TOTAL_MISMATCH.value:
                    _totals_mismatch(
                        uow,
                        run_id=run_id,
                        source=source_totals,
                        loaded=loaded_totals,
                        counts=counts,
                    )
            # A webhook batch moves no checkpoint: its ``checkpoint_after`` restates the
            # connection's.
            advance = kind != WEBHOOK_BATCH and not collected.cancelled and not reprocess
            # ``swept_at`` is the job's: adapters answer checkpoints without it (ports.Checkpoint).
            advanced = dataclasses.replace(
                collected.checkpoint_after,
                swept_at=uow.now if sweep_completed else checkpoint.swept_at,
            )
            checkpoint_after = (
                advanced.as_json() if advance else dict(connection["checkpoint"] or {})
            )
            _finish(
                uow,
                run_id=run_id,
                connection=connection,
                status=status,
                checkpoint_after=checkpoint_after,
                advance_checkpoint=advance,
                source=source_totals,
                loaded=loaded_totals,
                counts=counts,
                problem=problem,
            )
            uow.commit()
        return status, counts

    try:
        status, counts = apply_once()
    except Problem as refused:
        # PRD ERR-72 (04 §14.1 rev 1.229; supervisor ruling R-122 (l)): a document of the run was
        # recorded before a period lock that was decided while the run applied its objects
        # (``ingest_document``). Nothing of the attempt was stored. The refusal says what cures
        # it — sent again, the events are recorded after the lock — and a run has no sender: the
        # feed does not repeat an object and a sweep does not apply a stored version again. So
        # the job applies the objects it already fetched once more, in a new transaction, and
        # only for this rule. A second refusal is the job's failure: the run ends FAILED with the
        # rule's sentence (``sync_failed``), its checkpoint where it was, and the next run
        # fetches the same objects.
        if not is_period_state_moved(refused):
            raise
        status, counts = apply_once()
    log.info(
        "sync_run.finished",
        sync_run_id=str(run_id),
        connection_id=str(connection_id),
        kind=kind,
        status=status,
        count=counts.records,
    )
    clean = status == SyncRunStatus.SUCCEEDED.value and counts.exceptions == 0
    return JobOutcome(
        state="SUCCEEDED" if clean else "SUCCEEDED_WITH_EXCEPTIONS",
        result={
            "href": f"/api/v1/sync-runs/{run_id}",
            "status": status,
            "counts": counts.as_json(),
            "pages": collected.pages,
            "swept": collected.swept,
            "reprocess": reprocess,
        },
    )
