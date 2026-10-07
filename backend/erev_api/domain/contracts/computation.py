"""Persisting engine output (dev-guide §6.1 DG-CMD-04, DG-CMD-05, DG-CMD-10; 04 T-CON-07 to
T-CON-09, T-CON-11, T-ENG-01 to T-ENG-03, §14.1 DB-17; 05 §3.8 RCP-17, RCP-21; 03 REQ-CON-014,
REQ-REC-020, REQ-SSP-011, REQ-SSP-014, REQ-REF-015; CTL-011; BUILD_SPEC CTR-2).

``persist(uow, bundle, output)`` writes one computation in the caller's unit of work:

1. When a SUCCEEDED computation of the group has the same ``input_sha256`` and ``engine_version``,
   it returns that computation and writes nothing (``ux_contract_computation__idempotent``; RCP-21).
2. It refuses output whose obligation versions lack the SSP lineage columns (CTL-011) before any
   insert, raising ``EngineError("ENGINE_INVARIANT_VIOLATED")``. Then, still before any insert,
   it holds the group row and — inside a window of a close run — the state rows of the window's
   periods ``FOR SHARE``, so that a lock decision waits for it as for a posting
   (``period_ends.window_held``; 04 DB-07; dev-guide DG-KRN-DB-08 (1c); item CLO-GATE-RUN-1).
   A lock decision that did not wait has committed by then: a computation whose bundle holds an
   event recorded in its own transaction reads the LOCK records of the bundle's entities and
   books, and one whose cutoff is later than the transaction's record instant ends it 409
   ``lock-conflict`` with nothing written (rule ``PERIOD_STATE_MOVED``, PRD ERR-72; 04 §14.1 "A
   command recorded before a lock"; ``_refuse_a_lock_met``).
3. It inserts ``contract_computation`` (the stream heads of the included events, the record-time
   cutoff, the pinned references of ``bundles.pinned_refs``, the stamped engine release), then per
   book with a contract version: ``calc_trace`` (``explain.store``), ``contract_version`` (the next
   ``version_no`` of the group and book, ``cause_event_ids`` of the events first included,
   ``output_sha256``, and ``pinned_policies`` from the bundle's GROUP pin K values),
   ``obligation_version`` (``ssp_override_approval_request_id`` names the request of the last
   included ``LINE_ATTRIBUTES_CHANGED`` that corrected the obligation's SSP pin; CTR-15),
   ``contract_version_balance``, ``schedule`` and ``schedule_line``.
   Natural keys map to row ids through ``bundles.index`` (DG-ENG-02); posted amounts arrive as
   integer minor units and exact values as ``Fraction``.
4. Per book with posting intents it writes one sealed ``subledger_posting`` through
   ``journals.subledger.post``: key ``compute:<contract_computation_id>`` (``release:<close run
   id>:<group id>`` for a close release), ``entry_no`` the 1-based position of the entry in
   ascending entry-key order (S14-R-12), accounts resolved from the intent's account codes, amounts
   signed debit positive (T-SL-04; CTR-3).
5. It sets ``combination_group.head_computation_id`` and each member's
   ``latest_computation_id``; ``dirty_since`` is cleared when the included heads cover every
   member's head (RCP-17); the group's ``period_ends_open`` is written in the same statement when
   the computation moved it (``period_ends.after_computation``; 04 T-CON-03 rev 1.172, item
   CLO-GATE-RUN-1). It audits AUD-FACT summaries.

DB-17 checks at commit that the obligation versions of each contract version allocate
``transaction_price − consideration_payable_amount`` (``EREV-ALC-001``).

[J] L3-1-Q-22 records the choices the documents leave open: the LEGACY book (no contract version)
stores no trace; ``rpo_amount`` falls back to scheduled plus awaiting trigger until stage 15 emits
it; a balance's ``revenue_cum_txn``, ``billed_cum_txn`` and ``net_position_txn`` fall back to the
obligation sums; the balance kept per contract and entity is the one of the latest period;
``ssp_range_id`` and ``last_modification_id`` stay null; cost-asset schedule subjects take a uuid5
of their subject key until T-CON-16 exists. L3-1-Q-30 records the posting choices: a line's
effective date is the latest effective date of the bundle's events inside the entry's origin period
(else its posting period), or that period's end; a foreign-currency line is refused until the
output bundle carries the pinned rates of its lines; the ``legacy_key`` of a revenue line is the
obligation's ``legacy_record_key`` and of any other line the contract's external id (REQ-JE-007).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from itertools import groupby
from typing import TYPE_CHECKING, Any, Final, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import erev_engine
from erev_engine.bundle import (
    BalanceOut,
    BookOutput,
    InputBundle,
    IntentLine,
    OutputBundle,
    PostingIntent,
)
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, minor_to_decimal
from erev_engine.stages.s01_canonicalize import (
    contract_subject_key,
    group_entity_subject_key,
)
from erev_engine.stages.s14_posting.assign import VOID as VOID_REASON
from sqlalchemy import Column, Table, and_, func, insert, select, update
from sqlalchemy.orm import Session

from erev_api.audit.writer import record_facts
from erev_api.controls.release import current_environment, current_release
from erev_api.controls.stamping import process_release_id
from erev_api.db import new_id
from erev_api.db.session import require_tenant_scope
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    contract_version_balance,
    engine_release,
    gl_account,
    obligation_version,
    period_lock,
    schedule,
    schedule_line,
    subledger_posting,
)
from erev_api.db.types import ExactType, MoneyType
from erev_api.domain.contracts import bundles, fx_layers, period_ends
from erev_api.domain.journals import subledger
from erev_api.enums import (
    ComputationStatus,
    ComputationTrigger,
    ContractEventType,
    SubledgerPostingKind,
)
from erev_api.explain import store
from erev_api.logging import get_logger
from erev_api.problems import LOCK_CONFLICT_DETAIL, Problem, period_state_moved

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "LINEAGE_COLUMNS",
    "Engine",
    "book_lines",
    "default_engine",
    "lineage_findings",
    "persist",
    "recompute",
    "require_lineage",
]

type Engine = Callable[[InputBundle], OutputBundle]

PARITY_PRESET: Final = "LEGACY_PARITY"
VC_LINE: Final = "VC_LINE"
# REQ-SSP-011: the lineage every allocated obligation stores (low, mid, high and the in-range flag
# are null for a point entry, S05-R-07).
LINEAGE_COLUMNS: Final = (
    "ssp_book_version_key",
    "ssp_entry_key",
    "original_ssp_selected",
    "allocation_weight",
    "allocated_amount",
    "allocated_exact",
)
COST_ASSET_NAMESPACE: Final = "https://erev.dev/ns/contract-cost-asset/{group}/{subject}"
COMPUTATION_OBJECT: Final = "contract_computation"
VERSION_OBJECT: Final = "contract_version"
OBLIGATION_VERSION_OBJECT: Final = "obligation_version"
BALANCE_OBJECT: Final = "contract_version_balance"
SCHEDULE_OBJECT: Final = "schedule"
SCHEDULE_LINE_OBJECT: Final = "schedule_line"
TRACE_OBJECT: Final = "calc_trace"
CREATE: Final = "create"


def default_engine() -> Engine:
    """``erev_engine.compute`` (END-9); ``RuntimeError`` while the engine package lacks it."""
    found = getattr(erev_engine, "compute", None)
    if found is None:
        raise RuntimeError("erev_engine.compute is not available (BUILD_SPEC END-9)")
    return cast(Engine, found)


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _plain(value: object) -> object:
    """A JSON value: enum literals, exact decimals, dates and ids as strings."""
    if isinstance(value, Enum):
        return _plain(value.value)
    if isinstance(value, Fraction):
        return format_exact(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple | set | frozenset):
        return [_plain(item) for item in value]
    return value


def _value(column: Column[Any], value: object, minor_unit: int) -> object:
    """An engine column value bound to its 04 type: posted amounts in minor units (CV-30)."""
    if value is None:
        return None
    if isinstance(value, Enum):
        value = value.value
    if isinstance(column.type, MoneyType):
        if isinstance(value, bool):
            raise TypeError(f"{column.name} is money, not a boolean")
        if isinstance(value, int):
            return minor_to_decimal(value, minor_unit)
        if isinstance(value, Fraction):
            return Decimal(format_exact(value))
        return Decimal(str(value))
    if isinstance(column.type, ExactType):
        if isinstance(value, bool):
            raise TypeError(f"{column.name} is exact, not a boolean")
        if isinstance(value, Fraction | int):
            return Decimal(format_exact(value))
        return Decimal(str(value))
    if isinstance(value, Mapping):
        return _plain(value)
    if isinstance(value, list | tuple):
        return [_plain(item) if isinstance(item, Mapping) else item for item in value]
    return value


def _row(
    table: Table,
    columns: Mapping[str, object],
    fixed: Mapping[str, object],
    *,
    minor_unit: Callable[[str], int],
    skip: Iterable[str] = (),
) -> dict[str, Any]:
    """The table's row from ``fixed`` and the engine ``columns``; a NOT NULL column without a
    default that neither names is a programming error of the engine contract (CV-45)."""
    row: dict[str, Any] = dict(fixed)
    skipped = set(skip)
    for column in table.columns:
        name = column.name
        if name in row or name in skipped:
            continue
        if name not in columns:
            if not column.nullable and column.server_default is None:
                raise ValueError(f"the engine output lacks {table.name}.{name}")
            continue
        row[name] = _value(column, columns[name], minor_unit(name))
    return row


def _insert_rows(session: Session, table: Table, rows: Sequence[Mapping[str, Any]]) -> None:
    """Insert ``rows``, each with the columns it names (item CTR-BALANCE-ROWS-1; supervisor
    ruling R-114 (g)).

    One INSERT of several rows takes its columns from the first: a later row that names fewer is
    refused, and one that names more loses them without a word. ``_row`` names the columns the
    engine output carries, and the engine names a ``_functional`` balance only where it measures
    one — every measure at rate 1, the stage 12 remeasurements otherwise — so the T-CON-09 rows
    of two contracting entities with different functional currencies differ in columns. Each run
    of rows with one column set is one statement; a column a row does not name takes the table's
    default, as it does when the row is stored alone.
    """
    for _, run in groupby(rows, key=lambda row: tuple(sorted(row))):
        session.execute(insert(table), list(run))


def lineage_findings(bundle: InputBundle, output: OutputBundle) -> list[tuple[str, str, str]]:
    """(book, obligation subject key, missing columns) of every allocated obligation version
    without its SSP lineage (REQ-SSP-011; CTL-011). A parity VC line has none (T-CON-11)."""
    found: list[tuple[str, str, str]] = []
    for book_output in output.books:
        if book_output.contract_version is None:
            continue
        for item in book_output.obligation_versions:
            kind = _plain(item.columns.get("obligation_kind"))
            if kind == VC_LINE and bundle.tenant_preset == PARITY_PRESET:
                continue
            missing = [name for name in LINEAGE_COLUMNS if item.columns.get(name) is None]
            if missing:
                found.append((book_output.book_code, item.subject_key, ",".join(missing)))
    return found


def require_lineage(bundle: InputBundle, output: OutputBundle) -> None:
    """CTL-011: refuse, before any insert, a computation whose obligation versions lack lineage."""
    findings = lineage_findings(bundle, output)
    if findings:
        book_code, subject_key, missing = findings[0]
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "an obligation version lacks its SSP lineage (CTL-011)",
            subject_key=subject_key,
            detail={
                "control": "CTL-011",
                "rule": "REQ-SSP-011",
                "book_code": book_code,
                "columns": missing,
                "count": str(len(findings)),
            },
        )


def _existing(
    session: Session, group_id: UUID, input_sha256: str, engine_version: str
) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(contract_computation).where(
                contract_computation.c.combination_group_id == group_id,
                contract_computation.c.input_sha256 == input_sha256,
                contract_computation.c.engine_version == engine_version,
                contract_computation.c.status == ComputationStatus.SUCCEEDED.value,
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def _version_ids(session: Session, computation_id: UUID) -> dict[str, str]:
    statement = select(contract_version.c.book_code, contract_version.c.id).where(
        contract_version.c.contract_computation_id == computation_id
    )
    return {str(book_code): str(version_id) for book_code, version_id in session.execute(statement)}


def _posting_ids(session: Session, computation_id: UUID) -> dict[str, str]:
    statement = select(subledger_posting.c.book_code, subledger_posting.c.id).where(
        subledger_posting.c.contract_computation_id == computation_id
    )
    return {str(book_code): str(posting_id) for book_code, posting_id in session.execute(statement)}


def _engine_release_id(session: Session, engine_version: str) -> UUID:
    """The process's own release row for an output of ``engine_version`` (05 REL-03 consumers,
    rev 1.15; ``controls.stamping``); the latest row of that version is only the dev / test
    fallback, and a process row of another version is ``release-mismatch``."""

    def latest_for_version() -> UUID | None:
        found = session.execute(
            select(engine_release.c.id)
            .where(engine_release.c.engine_version == engine_version)
            .order_by(engine_release.c.deployed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return None if found is None else UUID(str(found))

    return process_release_id(
        current_release(),
        env=current_environment(),
        engine_version=engine_version,
        latest_for_version=latest_for_version,
    )


def _pinned_policies(bundle: InputBundle, book_code: str) -> dict[str, Any]:
    """T-CON-08 ``pinned_policies``: each GROUP pin K value, POL key → {value, level, source_id}."""
    book_input = next(item for item in bundle.books if item.book_code == book_code)
    return {
        policy.code: {
            "value": _plain(policy.value),
            "level": policy.level,
            "source_id": policy.source_ref,
        }
        for policy in book_input.policies
        if policy.scope == "GROUP" and policy.pin == "K"
    }


def _stream_heads(bundle: InputBundle, found: bundles.BundleIndex) -> dict[str, int]:
    heads: dict[str, int] = {}
    for event in bundle.events:
        contract_id = str(found.contracts[event.contract_key]["id"])
        heads[contract_id] = max(heads.get(contract_id, 0), event.stream_version)
    return dict(sorted(heads.items()))


def _cause_event_ids(bundle: InputBundle, found: bundles.BundleIndex) -> list[UUID]:
    previous = dict(bundle.group.previous_stream_heads)
    ids: list[UUID] = []
    for event in bundle.events:
        if event.stream_version > previous.get(event.contract_key, 0):
            event_id = found.events.get((event.contract_key, event.stream_version))
            if event_id is None:
                raise ValueError(f"event {event.event_key} is not stored; append it before persist")
            ids.append(event_id)
    return ids


def _lineage_ids(line: IntentLine, event_ids: Mapping[str, UUID]) -> list[UUID]:
    """The T-SL-12 ids of the line's ``source_event_keys`` (S14-R-13a), in set order. A key without
    a stored event is a bundle-assembly defect, refused as ``_cause_event_ids`` refuses it — never
    dropped, since a dropped member would silently narrow the register's attribution (S15-R-18b)."""
    ids: list[UUID] = []
    for key in line.source_event_keys:
        event_id = event_ids.get(key)
        if event_id is None:
            raise ValueError(f"event {key} is not stored; append it before persist (S14-R-13a)")
        ids.append(event_id)
    return ids


def _minor_units(bundle: InputBundle) -> Callable[[str], int]:
    return lambda code: bundle.currencies[code].minor_unit


def _ssp_override_requests(
    session: Session, bundle: InputBundle, found: bundles.BundleIndex
) -> dict[UUID, UUID]:
    """The ``SSP_OVERRIDE`` request behind each obligation's corrected SSP pin: the approval request
    of the last included ``LINE_ATTRIBUTES_CHANGED`` naming ``changes.ssp_book_version_id``
    (REQ-SSP-006; 04 §16.2 ``request-ssp-override``; BUILD_SPEC CTR-15)."""
    event_ids = [
        found.events[(event.contract_key, event.stream_version)]
        for event in bundle.events
        if event.event_type == bundles.ATTRIBUTES_EVENT
        and (event.contract_key, event.stream_version) in found.events
    ]
    if not event_ids:
        return {}
    statement = (
        select(
            contract_event.c.obligation_ids,
            contract_event.c.approval_request_id,
            contract_event.c.payload,
        )
        .where(
            contract_event.c.id.in_(event_ids),
            contract_event.c.approval_request_id.is_not(None),
        )
        .order_by(contract_event.c.effective_date, contract_event.c.record_seq)
    )
    requests: dict[UUID, UUID] = {}
    for obligation_ids, approval_request_id, payload in session.execute(statement):
        changes = payload.get("changes") if isinstance(payload, Mapping) else None
        if not isinstance(changes, Mapping) or changes.get("ssp_book_version_id") is None:
            continue
        for obligation_id in obligation_ids or ():
            requests[UUID(str(obligation_id))] = UUID(str(approval_request_id))
    return requests


def _obligation_rows(
    uow: UnitOfWork,
    bundle: InputBundle,
    found: bundles.BundleIndex,
    book_output: BookOutput,
    *,
    version_id: UUID,
    version_no: int,
    previous_version_id: UUID | None,
) -> list[dict[str, Any]]:
    session = uow.session
    previous: dict[UUID, Mapping[str, Any]] = {}
    if previous_version_id is not None:
        for row in session.execute(
            select(
                obligation_version.c.id,
                obligation_version.c.obligation_id,
                obligation_version.c.effective_date,
            ).where(obligation_version.c.contract_version_id == previous_version_id)
        ).mappings():
            previous[UUID(str(row["obligation_id"]))] = dict(row)
    currency = bundle.group.transaction_currency
    minor = bundle.currencies[currency].minor_unit
    override_requests = _ssp_override_requests(session, bundle, found)
    rows: list[dict[str, Any]] = []
    for item in book_output.obligation_versions:
        obligation_row = found.obligations.get(item.subject_key)
        if obligation_row is None:
            raise ValueError(f"obligation version {item.subject_key} names no obligation row")
        columns = item.columns
        obligation_id = UUID(str(obligation_row["id"]))
        before = previous.get(obligation_id)
        fixed: dict[str, Any] = {
            "tenant_id": uow.principal.tenant_id,
            "id": new_id(),
            "contract_version_id": version_id,
            "obligation_id": obligation_id,
            "contract_id": obligation_row["contract_id"],
            "combination_group_id": found.group["id"],
            "book_code": book_output.book_code,
            "version_no": version_no,
            "previous_obligation_version_id": None if before is None else before["id"],
            "legacy_record_key": obligation_row["legacy_record_key"],
            "product_id": found.products[str(columns["product_code"])],
            "pob_template_version_id": found.templates[str(columns["pob_template_version_key"])],
            "contracting_entity_id": found.entities[str(columns["contracting_entity_code"])]["id"],
            "performing_entity_id": found.entities[str(columns["performing_entity_code"])]["id"],
            "ssp_book_version_id": _key(found.ssp_versions, columns.get("ssp_book_version_key")),
            "ssp_entry_id": _key(found.ssp_entries, columns.get("ssp_entry_key")),
            "ssp_range_id": None,
            "ssp_override_approval_request_id": override_requests.get(obligation_id),
            "last_modification_id": None,
            "previous_effective_date": None if before is None else before["effective_date"],
            "trace_nodes": _plain(item.trace_nodes),
            **_stamps(uow),
        }
        rows.append(_row(obligation_version, columns, fixed, minor_unit=lambda _: minor))
    return rows


def _key(ids: Mapping[str, UUID], key: object) -> UUID | None:
    if key is None:
        return None
    found = ids.get(str(key))
    if found is None:
        raise ValueError(f"natural key {key!r} names no stored row")
    return found


def _latest_balances(bundle: InputBundle, balances: Sequence[BalanceOut]) -> dict[str, BalanceOut]:
    """Per ``<contract>@<entity>`` subject, the balance of its latest period."""
    starts = {
        (entity.code, period.period_key): period.start_date
        for entity in bundle.entities
        for period in entity.periods
    }
    latest: dict[str, BalanceOut] = {}
    for item in balances:
        entity_code = str(item.columns.get("entity") or item.subject_key.rsplit("@", 1)[-1])
        start = starts.get((entity_code, item.period_key), date.min)
        current = latest.get(item.subject_key)
        if current is None:
            latest[item.subject_key] = item
            continue
        current_entity = str(current.columns.get("entity") or entity_code)
        if start >= starts.get((current_entity, current.period_key), date.min):
            latest[item.subject_key] = item
    return latest


def _contract_key_of(found: bundles.BundleIndex, subject_key: str) -> str:
    """The external id of a ``<contract>@<entity>`` or ``<contract>/...`` subject (CV-21)."""
    for external_id in found.contracts:
        prefix = contract_subject_key(external_id)
        if subject_key == prefix or subject_key.startswith((f"{prefix}@", f"{prefix}/")):
            return external_id
    raise ValueError(f"subject {subject_key} names no member contract")


def _balance_rows(
    uow: UnitOfWork,
    bundle: InputBundle,
    found: bundles.BundleIndex,
    book_output: BookOutput,
    *,
    version_id: UUID,
    obligation_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    currency = bundle.group.transaction_currency
    for subject_key, item in sorted(_latest_balances(bundle, book_output.balances).items()):
        external_id = _contract_key_of(found, subject_key)
        contract_row = found.contracts[external_id]
        entity_code = str(item.columns.get("entity") or subject_key.rsplit("@", 1)[-1])
        entity_row = found.entities[entity_code]
        functional = str(
            item.columns.get("functional_currency") or entity_row["functional_currency"]
        )
        members = [
            row
            for row in obligation_rows
            if row["contract_id"] == contract_row["id"]
            and row["contracting_entity_id"] == entity_row["id"]
        ]
        revenue = sum((Decimal(row["revenue_cum"]) for row in members), Decimal(0))
        billed = sum((Decimal(row["billed_cum"]) for row in members), Decimal(0))
        fixed: dict[str, Any] = {
            "tenant_id": uow.principal.tenant_id,
            "id": new_id(),
            "contract_version_id": version_id,
            "contract_id": contract_row["id"],
            "entity_id": entity_row["id"],
            "book_code": book_output.book_code,
            "txn_currency": currency,
            "functional_currency": functional.strip(),
            **_stamps(uow),
        }
        defaults = {
            "revenue_cum_txn": revenue,
            "billed_cum_txn": billed,
            "net_position_txn": billed - revenue,
        }
        for name, value in defaults.items():
            if name not in item.columns:
                fixed[name] = value
        units = _BalanceUnits(
            txn=bundle.currencies[currency].minor_unit,
            functional=bundle.currencies[fixed["functional_currency"]].minor_unit,
        )
        rows.append(_row(contract_version_balance, item.columns, fixed, minor_unit=units.of))
    return rows


class _BalanceUnits:
    """The minor unit of a T-CON-09 column: functional columns use the functional currency's."""

    __slots__ = ("functional", "txn")

    def __init__(self, *, txn: int, functional: int) -> None:
        self.txn = txn
        self.functional = functional

    def of(self, name: str) -> int:
        return self.functional if name.endswith("_functional") else self.txn


def _schedule_rows(
    uow: UnitOfWork,
    bundle: InputBundle,
    found: bundles.BundleIndex,
    book_output: BookOutput,
    *,
    version_id: UUID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tenant_id = uow.principal.tenant_id
    currency = bundle.group.transaction_currency
    minor = bundle.currencies[currency].minor_unit
    headers: dict[str, dict[str, Any]] = {}
    lines: list[dict[str, Any]] = []
    for line in book_output.schedules:
        kind = str(_plain(line.schedule_kind))
        header = headers.get(kind)
        if header is None:
            header = {
                "tenant_id": tenant_id,
                "id": new_id(),
                "contract_version_id": version_id,
                "combination_group_id": found.group["id"],
                "book_code": book_output.book_code,
                "schedule_kind": kind,
                "currency": currency,
                "line_count": 0,
                "total_amount": Decimal(0),
                **_stamps(uow),
            }
            headers[kind] = header
        if line.subject_type == "obligation":
            obligation_row = found.obligations[line.subject_key]
            subject_id, contract_id = obligation_row["id"], obligation_row["contract_id"]
        else:
            external_id = _contract_key_of(found, line.subject_key)
            contract_id = found.contracts[external_id]["id"]
            subject_id = (
                contract_id
                if line.subject_type == "contract"
                else uuid5(
                    NAMESPACE_URL,
                    COST_ASSET_NAMESPACE.format(group=found.group["id"], subject=line.subject_key),
                )
            )
        period_id, end_date = found.periods[(line.entity, line.period_key)]
        amount = minor_to_decimal(line.amount, minor)
        header["line_count"] += 1
        header["total_amount"] += amount
        lines.append(
            {
                "tenant_id": tenant_id,
                "period_end_date": end_date,
                "id": new_id(),
                "schedule_id": header["id"],
                "contract_version_id": version_id,
                "contract_id": contract_id,
                "book_code": book_output.book_code,
                "subject_type": line.subject_type,
                "subject_id": subject_id,
                "entity_id": found.entities[line.entity]["id"],
                "period_id": period_id,
                "line_type": str(_plain(line.line_type)),
                "amount": amount,
                "cumulative_amount": minor_to_decimal(line.cumulative_amount, minor),
                "cumulative_exact": Decimal(format_exact(line.cumulative_exact)),
                "quantity": None if line.quantity is None else Decimal(format_exact(line.quantity)),
                "currency": currency,
                "is_released_at_close": line.is_released_at_close,
                "trace_node_id": line.trace_node_id,
                "created_at": uow.now,
            }
        )
    return list(headers.values()), lines


def _previous(session: Session, group_id: UUID, book_code: str) -> Mapping[str, Any] | None:
    return bundles.previous_version(session, group_id, book_code)


def _persist_book(
    uow: UnitOfWork,
    bundle: InputBundle,
    output: OutputBundle,
    found: bundles.BundleIndex,
    book_output: BookOutput,
    *,
    computation_id: UUID,
    known_at: datetime,
    cause_event_ids: Sequence[UUID],
    facts: dict[str, list[UUID]],
) -> tuple[UUID, UUID] | None:
    """The book's version and trace ids, or None for a book without a contract version."""
    version_out = book_output.contract_version
    if version_out is None:
        return None
    session = uow.session
    tenant_id = uow.principal.tenant_id
    group_id = UUID(str(found.group["id"]))
    previous = _previous(session, group_id, book_output.book_code)
    version_no = 1 if previous is None else int(previous["version_no"]) + 1
    previous_id = None if previous is None else UUID(str(previous["id"]))
    version_id, trace_id = new_id(), new_id()
    store.insert_trace(
        session,
        values={"tenant_id": tenant_id, "id": trace_id, **_stamps(uow)},
        contract_version_id=version_id,
        combination_group_id=group_id,
        book_code=book_output.book_code,
        trace=book_output.trace,
    )
    obligation_rows = _obligation_rows(
        uow,
        bundle,
        found,
        book_output,
        version_id=version_id,
        version_no=version_no,
        previous_version_id=previous_id,
    )
    columns = dict(version_out.columns)
    if "rpo_amount" not in columns:
        columns["rpo_amount"] = sum(
            (Decimal(row["scheduled_amount"]) + Decimal(row["awaiting_trigger_amount"]))
            for row in obligation_rows
        )
    if columns.get("status_in_book") is None:
        statuses = [status for _, status in book_output.status_in_book]
        columns["status_in_book"] = statuses[0] if statuses else "DRAFT"
    currency = bundle.group.transaction_currency
    minor = bundle.currencies[currency].minor_unit
    fixed = {
        "tenant_id": tenant_id,
        "id": version_id,
        "combination_group_id": group_id,
        "contract_computation_id": computation_id,
        "book_code": book_output.book_code,
        "version_no": version_no,
        "previous_version_id": previous_id,
        "known_at": known_at,
        "cause_event_ids": list(cause_event_ids),
        "output_sha256": output.sha256(),
        "calc_trace_id": trace_id,
        "transaction_currency": currency,
        "pinned_policies": _pinned_policies(bundle, book_output.book_code),
        **_stamps(uow),
    }
    row = _row(contract_version, columns, fixed, minor_unit=lambda _: minor)
    session.execute(insert(contract_version).values(**row))
    _insert_rows(session, obligation_version, obligation_rows)
    balance_rows = _balance_rows(
        uow, bundle, found, book_output, version_id=version_id, obligation_rows=obligation_rows
    )
    _insert_rows(session, contract_version_balance, balance_rows)
    headers, lines = _schedule_rows(uow, bundle, found, book_output, version_id=version_id)
    _insert_rows(session, schedule, headers)
    _insert_rows(session, schedule_line, lines)
    facts["fx_layer_movement"] += fx_layers.persist(uow, bundle, found, book_output, version_id)
    facts[VERSION_OBJECT].append(version_id)
    facts[TRACE_OBJECT].append(trace_id)
    facts[OBLIGATION_VERSION_OBJECT] += [row["id"] for row in obligation_rows]
    facts[BALANCE_OBJECT] += [row["id"] for row in balance_rows]
    facts[SCHEDULE_OBJECT] += [row["id"] for row in headers]
    facts[SCHEDULE_LINE_OBJECT] += [row["id"] for row in lines]
    return version_id, trace_id


def _effective_date(bundle: InputBundle) -> Callable[[str, str], date]:
    """[J] L3-1-Q-30: the latest effective date of the bundle's events inside a period of an
    entity, else that period's end date."""
    periods = {
        (entity.code, item.period_key): item
        for entity in bundle.entities
        for item in entity.periods
    }

    def of(entity_code: str, period_key: str) -> date:
        found = periods[(entity_code, period_key)]
        inside = [
            event.effective_date
            for event in bundle.events
            if found.start_date <= event.effective_date <= found.end_date
        ]
        return max(inside, default=found.end_date)

    return of


def group_line_contract(
    contracts: Mapping[str, Mapping[str, Any]], entity_id: object, performed: Collection[object]
) -> Mapping[str, Any]:
    """The member contract a line of the GROUP's own subject is listed under (04 T-SL-04
    ``contract_id`` rev 1.303; dev-guide DG-CMD-10 rev 1.284; item BILLING-GROUP-SUBJECT-1, the
    supervisor's ruling of 2026-10-02): the first by external id among the members the entry's
    entity posts for — as their contracting entity, or as the performing entity of one of their
    obligations (``performed``: the ids of those members).

    Every JET-10 part — the remeasurement of a foreign-currency balance and the difference at its
    settlement — is one entry per group and entity (ENGINE_SPEC_B Table 14-A), and the engine
    names no contract for it where the group has several. The line belongs to the group; the
    contract is where it is listed, so that a line's entity and its contract's never part. The
    choice moves no amount: posted amounts are read back by their subject."""
    posts_for = sorted(
        external_id
        for external_id, row in contracts.items()
        if row["contracting_entity_id"] == entity_id or row["id"] in performed
    )
    if not posts_for:
        raise ValueError("the entry's entity posts for no member contract of the group")
    return contracts[posts_for[0]]


def _performed_by(found: bundles.BundleIndex, book_output: BookOutput) -> dict[str, set[object]]:
    """Per entity code, the ids of the member contracts with an obligation that entity performs
    (T-CON-11 ``performing_entity_code`` of the book's obligation versions)."""
    performed: dict[str, set[object]] = {}
    for item in book_output.obligation_versions:
        row = found.obligations.get(item.subject_key)
        code = item.columns.get("performing_entity_code")
        if row is not None and code is not None:
            performed.setdefault(str(code), set()).add(row["contract_id"])
    return performed


def _line_contract(
    found: bundles.BundleIndex,
    intent: PostingIntent,
    obligation_row: Mapping[str, Any] | None,
    listed: Mapping[str, Collection[object]] | None = None,
) -> Mapping[str, Any]:
    """The member contract of an entry: its obligation's, the ``contract_key`` dimension, the only
    member, or the contract a ``<contract>@<entity>`` subject names (S14-R-13). An entry of the
    group's own subject in a group of several belongs to no member: ``ValueError``, as for a
    subject that names nothing. With ``listed`` — per entity code, the members with an obligation
    that entity performs (``_performed_by``) — such an entry answers the member its LINES are
    listed under (``group_line_contract``): what a ledger line needs, not whose the entry is."""
    if obligation_row is not None:
        return next(
            row for row in found.contracts.values() if row["id"] == obligation_row["contract_id"]
        )
    keys = {
        str(line.dimensions["contract_key"])
        for line in intent.lines
        if line.dimensions.get("contract_key")
    }
    if len(keys) == 1:
        return found.contracts[keys.pop()]
    if len(found.contracts) == 1:
        return next(iter(found.contracts.values()))
    if listed is not None:
        unit = group_entity_subject_key(str(found.group["code"]), intent.entity)
        if intent.subject_key == unit or intent.subject_key.startswith(f"{unit}/"):
            return group_line_contract(
                found.contracts, found.entities[intent.entity]["id"], listed.get(intent.entity, ())
            )
    return found.contracts[_contract_key_of(found, intent.subject_key)]


def _posting_source(
    bundle: InputBundle,
    found: bundles.BundleIndex,
    intents: Sequence[PostingIntent],
    *,
    group_id: UUID,
    computation_id: UUID,
    close_run_id: UUID | None,
) -> tuple[SubledgerPostingKind, str, str | None]:
    """E-31 kind, T-SL-01 idempotency key and, for a void, the description of a computation's
    posting: ``CLOSE_RELEASE`` under its close run; ``VOID_REVERSAL`` under the ``CONTRACT_VOIDED``
    event whose reversal the intents carry — an entry of a voided member's contract, or any delta
    with reason ``VOID`` (the stage 14 rule once the compute loop binds the void, D-98 80) — with a
    description naming the event and the approved cutoff its payload carries (D-98 99a); otherwise
    ``ENGINE_COMPUTE`` under the computation (ENGINE_SPEC_B S14-R-08; REQ-CON-015; CTR-11)."""
    if bundle.trigger == ComputationTrigger.CLOSE_RELEASE.value:
        if close_run_id is None:
            raise ValueError("a CLOSE_RELEASE computation posts under its close run (T-SL-01)")
        return (
            SubledgerPostingKind.CLOSE_RELEASE,
            subledger.release_key(close_run_id, group_id),
            None,
        )
    voids = {
        event.contract_key: event  # the latest void of each member in ENG-06 order
        for event in bundle.events
        if event.event_type == ContractEventType.CONTRACT_VOIDED.value
    }
    if voids:
        reversed_members = {
            key for intent in intents if (key := _intent_contract(found, intent)) in voids
        }
        if any(intent.reason_code == VOID_REASON for intent in intents) and not reversed_members:
            reversed_members = set(voids)
        for event in reversed(list(voids.values())):
            if event.contract_key not in reversed_members:
                continue
            event_id = found.events.get((event.contract_key, event.stream_version))
            if event_id is not None:
                payload = event.payload
                description = (
                    f"Void reversal of {event.contract_key} under {event.event_key} "
                    f"(approval request {payload.get('approval_request_id')}; posted through "
                    f"{payload.get('posted_through')}, {payload.get('posted_line_count')} lines; "
                    f"chain positions {payload.get('posted_through_seq')})"
                )
                return SubledgerPostingKind.VOID_REVERSAL, subledger.void_key(event_id), description
    return SubledgerPostingKind.ENGINE_COMPUTE, subledger.compute_key(computation_id), None


def _intent_contract(found: bundles.BundleIndex, intent: PostingIntent) -> str | None:
    """The external id of the member contract an entry belongs to (S14-R-13), or None when the
    entry names none (a group-level entry of a several-member group)."""
    try:
        return str(
            _line_contract(found, intent, found.obligations.get(intent.subject_key))["external_id"]
        )
    except (KeyError, StopIteration, ValueError):
        return None


def _post_book(
    uow: UnitOfWork,
    bundle: InputBundle,
    found: bundles.BundleIndex,
    book_output: BookOutput,
    *,
    computation_id: UUID,
    stored: tuple[UUID, UUID] | None,
    close_run_id: UUID | None,
    deviations: list[str] | None = None,
) -> subledger.Posted | None:
    """DG-CMD-10: the book's posting intents as one sealed posting (T-SL-01 to T-SL-04).

    A foreign-currency line takes ``fx_rate_id`` and ``fx_rate_set_version_id`` of the RateRef in
    ``BookOutput.line_rates`` with the latest effective date, ties to the greatest rate key; a line
    with several RateRefs appends ``<book>:<line key>`` to ``deviations``, and its full list stays
    in the calculation trace (D-88 L7-6-Q-1; T-SL-04 carries one rate id). A RateRef is a rate the
    bundle pins or, for a line that reverses posted amounts, a rate the bundle's ``posted`` amounts
    name (``rate_refs``; ENGINE_SPEC_B S14-R-28), resolved from the rate row stamped on the posted
    lines.
    """
    intents = sorted(book_output.posting_intents, key=lambda intent: intent.entry_key)
    if not intents:
        return None
    lines = book_lines(
        uow.session, bundle, found, book_output, intents, stored=stored, deviations=deviations
    )
    group_id = UUID(str(found.group["id"]))
    kind, key, described = _posting_source(
        bundle,
        found,
        intents,
        group_id=group_id,
        computation_id=computation_id,
        close_run_id=close_run_id,
    )
    return subledger.post(
        uow,
        book_code=book_output.book_code,
        posting_kind=kind,
        idempotency_key=key,
        description=described or f"Computation {computation_id} of {bundle.group.group_key}",
        lines=lines,
        combination_group_id=group_id,
        contract_computation_id=computation_id,
        close_run_id=close_run_id,
        require_subject_key=True,
    )


def book_lines(
    session: Session,
    bundle: InputBundle,
    found: bundles.BundleIndex,
    book_output: BookOutput,
    intents: Sequence[PostingIntent],
    *,
    stored: tuple[UUID, UUID] | None,
    deviations: list[str] | None = None,
    first_entry_no: int = 1,
) -> list[dict[str, Any]]:
    """The T-SL-04 line values of ``intents`` — posting intents of ``book_output`` — one entry per
    intent, numbered from ``first_entry_no`` in the order given; ``stored`` is the contract version
    and trace the lines belong to, or None for lines no stored version carries (the period-end
    passes of a close run; supervisor ruling R-79 (d)). Rate stamping as ``_post_book`` states it.
    Every line carries ``subject_key``, the subject its intent was posted under (04 T-SL-04 rev
    1.282; supervisor ruling R-11 as amended): the read-back of posted amounts answers it, so a
    computation over its own postings finds each amount under the role key it was posted for
    (05 RCP-05; ENGINE_SPEC_B S14-INV-02).
    """
    line_rates = dict(book_output.line_rates)
    pinned = {rate.rate_key: rate for rate in bundle.fx_rates}
    rate_ids = bundles.fx_rate_ids(session, bundle) if line_rates else {}
    posted_rates = _posted_rates(session, bundle, found) if line_rates else {}
    codes = sorted({line.account_code for intent in intents for line in intent.lines})
    accounts = {
        str(code): UUID(str(account_id))
        for account_id, code in session.execute(
            select(gl_account.c.id, gl_account.c.code).where(gl_account.c.code.in_(codes))
        )
    }
    event_ids = {
        event.event_key: found.events[(event.contract_key, event.stream_version)]
        for event in bundle.events
        if (event.contract_key, event.stream_version) in found.events
    }
    effective = _effective_date(bundle)
    minor = _minor_units(bundle)
    version_id, trace_id = (None, None) if stored is None else stored
    performed = _performed_by(found, book_output)
    lines: list[dict[str, Any]] = []
    for entry_no, intent in enumerate(intents, start=first_entry_no):
        entity_row = found.entities[intent.entity]
        period_id, period_end = found.periods[(intent.entity, intent.posting_period_key)]
        origin_id = (
            None
            if intent.origin_period_key is None
            else found.periods[(intent.entity, intent.origin_period_key)][0]
        )
        obligation_row = found.obligations.get(intent.subject_key)
        contract_row = _line_contract(found, intent, obligation_row, performed)
        effective_date = effective(
            intent.entity, intent.origin_period_key or intent.posting_period_key
        )
        for line in intent.lines:
            stamp: tuple[UUID | None, UUID | None, Decimal | None] = (None, None, None)
            if line.txn_currency != line.functional_currency:
                refs = line_rates.get(line.line_key, ())
                if not refs:
                    raise ValueError(
                        f"line {line.line_key} converts {line.txn_currency} to "
                        f"{line.functional_currency}, but the output carries no pinned rate "
                        "(REQ-FX-006; L3-1-Q-30)"
                    )
                stamp = _rate_stamp(line.line_key, refs, pinned, rate_ids, posted_rates)
                if len(refs) > 1 and deviations is not None:
                    deviations.append(f"{book_output.book_code}:{line.line_key}")
            account_id = accounts.get(line.account_code)
            if account_id is None:
                raise ValueError(
                    f"account {line.account_code} of {intent.subject_key} names no GL account "
                    "(REQ-JE-022)"
                )
            sign = 1 if line.side == "D" else -1
            revenue = obligation_row is not None and line.account_role == "REVENUE"
            lines.append(
                {
                    "period_end_date": period_end,
                    "entity_id": entity_row["id"],
                    "period_id": period_id,
                    "origin_period_id": origin_id,
                    "effective_date": effective_date,
                    "entry_no": entry_no,
                    "entry_kind": intent.entry_kind,
                    "subject_key": intent.subject_key,
                    "account_role": line.account_role,
                    "clearing_purpose": line.clearing_purpose,
                    "gl_account_id": account_id,
                    "dimensions": dict(sorted(line.dimensions.items())),
                    "dimension_set_sha256": subledger.dimension_set_sha256(line.dimensions),
                    "txn_currency": line.txn_currency,
                    "amount_txn": sign
                    * minor_to_decimal(line.amount_txn, minor(line.txn_currency)),
                    "functional_currency": line.functional_currency,
                    "amount_functional": sign
                    * minor_to_decimal(line.amount_functional, minor(line.functional_currency)),
                    "fx_rate_id": stamp[0],
                    "fx_rate_set_version_id": stamp[1],
                    "fx_rate": stamp[2],
                    "contract_id": contract_row["id"],
                    "obligation_id": None if obligation_row is None else obligation_row["id"],
                    "contract_version_id": version_id,
                    "contract_event_id": None
                    if line.source_event_key is None
                    else event_ids.get(line.source_event_key),
                    subledger.LINE_EVENTS_KEY: _lineage_ids(line, event_ids),
                    "counterparty_entity_id": None
                    if line.counterparty_entity is None
                    else found.entities[line.counterparty_entity]["id"],
                    "reason_code": intent.reason_code,
                    "legacy_key": obligation_row["legacy_record_key"]
                    if revenue and obligation_row is not None
                    else contract_row["external_id"],
                    "calc_trace_id": trace_id,
                    "trace_node_id": line.trace_node_id,
                }
            )
    return lines


# The rates the bundle's posted amounts name: rate key -> (version key, effective date, (rate id,
# rate-set version id, rate)).
PostedRates = Mapping[str, tuple[str, date, tuple[UUID, UUID, Decimal]]]


def _posted_rates(session: Session, bundle: InputBundle, found: bundles.BundleIndex) -> PostedRates:
    """ENGINE_SPEC_B S14-R-28: the rates ``bundle.posted`` names as ``rate_refs``, resolved from
    the rate rows stamped on the sealed lines of the member contracts. A line that reverses posted
    amounts names the rates of the lines it reverses, and such a rate may belong to a rate-set
    version superseded since, which the bundle no longer pins (D-87 L6-5-Q-23)."""
    named = {ref for item in bundle.posted for ref in item.rate_refs}
    if not named:
        return {}
    member_ids = [UUID(str(row["id"])) for row in found.contracts.values()]
    return {
        rate_key: row
        for rate_key, row in bundles.posted_rate_rows(session, member_ids).items()
        if (rate_key, row[0]) in named
    }


def _rate_stamp(
    line_key: str,
    refs: Sequence[tuple[str, str]],
    pinned: Mapping[str, Any],
    rate_ids: Mapping[str, tuple[UUID, UUID, Decimal]],
    posted_rates: PostedRates | None = None,
) -> tuple[UUID | None, UUID | None, Decimal | None]:
    """D-88 L7-6-Q-1: (``fx_rate_id``, ``fx_rate_set_version_id``, ``fx_rate``) of the line's
    RateRef with the latest effective date, ties to the greatest rate key. The rate is that
    ``fx_rate`` row's, so T-SL-04 ``fx_rate`` is set beside ``fx_rate_id`` (L8-merge: the drill and
    API-S-SubledgerLine format it). A RateRef is a rate the bundle pins or, failing that, one its
    posted amounts name (``posted_rates``; S14-R-28); any other, or one whose version differs or
    whose row id the platform cannot resolve, raises (REQ-FX-006)."""
    found: list[tuple[date, str, tuple[UUID, UUID, Decimal]]] = []
    for rate_key, version_key in refs:
        rate = pinned.get(rate_key)
        ids = rate_ids.get(rate_key)
        if rate is not None and ids is not None and rate.version_key == version_key:
            found.append((rate.effective_date, rate_key, ids))
            continue
        named = None if posted_rates is None else posted_rates.get(rate_key)
        if named is None or named[0] != version_key:
            raise ValueError(
                f"line {line_key} names the rate {rate_key} of {version_key}, which the bundle "
                "does not pin and its posted amounts do not name (REQ-FX-006; L7-6-Q-1; S14-R-28)"
            )
        found.append((named[1], rate_key, named[2]))
    _, _, (rate_id, version_id, rate_value) = max(found, key=lambda item: (item[0], item[1]))
    return rate_id, version_id, rate_value


def _update_heads(
    uow: UnitOfWork,
    found: bundles.BundleIndex,
    *,
    computation_id: UUID,
    heads: Mapping[str, int],
    period_ends_open: Mapping[str, str] | None = None,
) -> bool:
    """Point the group and members at the computation; clear ``dirty_since`` when the included
    heads cover every member's head (RCP-17). Returns whether it was cleared. ``period_ends_open``
    is the group's mark when the computation moved it (``period_ends.after_computation``)."""
    session = uow.session
    principal = uow.principal
    member_ids = [UUID(str(row["id"])) for row in found.contracts.values()]
    current = {
        str(contract_id): int(head)
        for contract_id, head in session.execute(
            select(contract.c.id, contract.c.head_stream_version).where(
                contract.c.id.in_(member_ids)
            )
        )
    }
    clear = all(heads.get(contract_id, 0) >= head for contract_id, head in current.items())
    modified = {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    group_values: dict[str, Any] = {
        "head_computation_id": computation_id,
        "row_version": combination_group.c.row_version + 1,
        **modified,
    }
    if clear:
        # the mark and the trigger it carries end together (04 T-CON-03 rev 1.297)
        group_values["dirty_since"] = None
        group_values["dirty_trigger"] = None
    if period_ends_open is not None:
        group_values["period_ends_open"] = dict(period_ends_open)
    session.execute(
        update(combination_group)
        .where(combination_group.c.id == found.group["id"])
        .values(**group_values)
    )
    session.execute(
        update(contract)
        .where(contract.c.id.in_(member_ids))
        .values(
            latest_computation_id=computation_id,
            row_version=contract.c.row_version + 1,
            **modified,
        )
    )
    return clear


def _refuse_a_lock_met(uow: UnitOfWork, bundle: InputBundle, found: bundles.BundleIndex) -> None:
    """PRD ERR-72, rule ``PERIOD_STATE_MOVED`` (04 §14.1 "A command recorded before a lock" rev
    1.157; 05 RCP-18 rev 1.96; dev-guide DG-CMD-10 rev 1.140; supervisor rulings R-105 (3) and of
    2026-10-01 13:57).

    An event carries the start of the transaction that records it (04 DB-08). A period lock
    decided after that start and committed before this point froze its datasets without the
    event, at a cutoff the stamp precedes: written now, the version would count as known at the
    cutoff for every later reader while the lock's datasets do not hold it, and the late entry
    report would not list the event. So a computation whose bundle holds an event recorded in
    THIS transaction reads the LOCK records of the bundle's entities and books — a ``LOCK``
    record alone names a cutoff (T-CLS-04) — and one whose cutoff is later than the bundle's
    record-time cutoff (``bundles.record_cutoff``: the later of the application instant and the
    transaction timestamp, the rule a lock's cutoff follows too) ends the command 409
    ``lock-conflict`` before anything is written. The comparison is strict: under an application
    clock that stands still, an event recorded after a lock at the same instant is not refused.
    Sent again, the command is recorded after the lock (the refusal is not kept for its
    idempotency key, DG-KRN-IDEM-03). The problem is the kernel's (``problems.period_state_moved``):
    inside an approval's decision ``approvals.engine.decide`` answers with its decision form.

    Called after ``period_ends.window_held``: a lock decision has then either committed, and its
    record is read here, or it waits for this transaction and sees it. A computation that records
    nothing — a job, a recomputation — is not judged: its events carry their own transactions'
    stamps."""
    session = uow.session
    started = session.execute(select(func.transaction_timestamp())).scalar_one()
    if not any(event.recorded_at == started for event in bundle.events):
        return
    met = session.execute(
        select(period_lock.c.id)
        .where(
            period_lock.c.entity_id.in_([UUID(str(row["id"])) for row in found.entities.values()]),
            period_lock.c.book_code.in_([book.book_code for book in bundle.books]),
            period_lock.c.cutoff_known_at > bundle.known_at,
        )
        .limit(1)
    ).first()
    if met is not None:
        raise period_state_moved()


BEHIND_EVENT: Final = "event"  # a member's event beyond the bundle's stream head for it
BEHIND_MARK: Final = "mark"  # ``dirty_since`` later than the bundle's cutoff
BEHIND_HEAD: Final = "head"  # the group's head admitted by a later cutoff than the bundle's


def head_is_later(
    head_cutoff_at: datetime | None, head_created_at: datetime, cutoff: datetime
) -> bool:
    """Whether a group's head computation admitted by a later bound than ``cutoff`` — the way
    ``head`` of ``behind_its_group`` (04 §14.1 rev 1.302; item COMPUTE-BEHIND-CUTOFF-1).

    The head's bound is the cutoff its bundle admitted by, which the computation stored
    (T-CON-07 ``cutoff_at``). A head stored before the column has none and answers as the
    clause was built, by its ``created_at``. Strictly later: two computations of one
    transaction share a cutoff, and the second is not behind the first."""
    made = head_created_at if head_cutoff_at is None else head_cutoff_at
    return made > cutoff


def behind_its_group(
    uow: UnitOfWork, bundle: InputBundle, found: bundles.BundleIndex
) -> tuple[str, ...]:
    """In which ways ``bundle`` is behind its group, as the group stands now — nothing when it is
    not (04 §14.1 "A computation behind its group", rev 1.298 and 1.302; 05 RCP-22 rev 1.207 and
    1.208; dev-guide DG-CMD-10 rev 1.282 and 1.288; items COMPUTE-BEHIND-GROUP-1 and
    COMPUTE-BEHIND-CUTOFF-1, the supervisor's rulings and order of 2026-10-02).

    A bundle admits what was recorded by its cutoff — the later of the application instant and
    the transaction timestamp, both fixed when the unit of work and its transaction BEGAN
    (``bundles.record_cutoff``) — while ``posted``, the previous version and the period states
    are read as committed when the bundle is BUILT. What another transaction committed for the
    group in between is in the second and not in the first, and a computation posts target minus
    posted: stored, it would post that fact's reversal and become the head, with the group left
    clean. Measured before the item: a computation begun before a second delivery was recorded,
    persisting after it, reversed the delivery's revenue; one begun before a rate version's
    approval ended the mark of a version it had not read, and — where another computation had
    posted the version's difference meanwhile — posted the difference back out.

    The group holds something the bundle's cutoff precedes when:

    - ``event``: a member's ``head_stream_version`` lies beyond the bundle's stream head for it.
      Exact, and on the database's clock: an event carries the start of the transaction that
      recorded it (04 DB-08).
    - ``mark``: ``dirty_since`` is later than the cutoff. Whatever set the mark — the approval of
      a policy override, a period's opening, an event whose computation was deferred — began
      after this bundle's cutoff, and the bundle admits by that same instant.
    - ``head``: the group's head computation admitted by a later cutoff than this bundle's
      (``head_is_later``). A later computation has read at least what this one read; a writer
      that computes in its own transaction (a judgement review, a combination, an event within
      the budget) leaves no mark behind, and where it appended no event the stream heads cover
      as well.

    Bound is compared with bound: a computation stores the cutoff its bundle admitted by (04
    T-CON-07 ``cutoff_at``), so no clock is assumed. Before the column the clause read the
    head's ``created_at`` — the instant of its unit of work — and a head whose transaction
    began later than that instant, as an application clock behind the database's makes every
    head, was not told apart from a computation whose cutoff lay between the two: measured with
    the clock twenty seconds behind, such a computation was stored and posted the head's
    difference back out. A head stored before the column has no cutoff and is read as it was,
    by its ``created_at``, until its group is computed again. The cutoff itself is not moved to
    the read: PRD ERR-72 stands on its being the start of the transaction.

    The caller holds the group row (``period_ends.window_held`` in ``_persist``;
    ``repo.lock_group`` in ``compute_job``): an appender that has inserted its event waits for
    that row before it commits, so what is read here is everything committed for the group."""
    session = uow.session
    heads = _stream_heads(bundle, found)
    member_ids = [UUID(str(row["id"])) for row in found.contracts.values()]
    current = session.execute(
        select(contract.c.id, contract.c.head_stream_version).where(contract.c.id.in_(member_ids))
    ).all()
    ways: list[str] = []
    if any(int(head) > heads.get(str(contract_id), 0) for contract_id, head in current):
        ways.append(BEHIND_EVENT)
    dirty_since, head_created_at, head_cutoff_at = session.execute(
        select(
            combination_group.c.dirty_since,
            contract_computation.c.created_at,
            contract_computation.c.cutoff_at,
        )
        .select_from(
            combination_group.outerjoin(
                contract_computation,
                and_(
                    contract_computation.c.tenant_id == combination_group.c.tenant_id,
                    contract_computation.c.id == combination_group.c.head_computation_id,
                ),
            )
        )
        .where(combination_group.c.id == found.group["id"])
    ).one()
    if dirty_since is not None and dirty_since > bundle.known_at:
        ways.append(BEHIND_MARK)
    # ``head_created_at`` is NULL where the group has no head computation yet.
    if head_created_at is not None and head_is_later(
        head_cutoff_at, head_created_at, bundle.known_at
    ):
        ways.append(BEHIND_HEAD)
    return tuple(ways)


def refuse_a_bundle_behind_its_group(
    uow: UnitOfWork, bundle: InputBundle, found: bundles.BundleIndex
) -> None:
    """A computation whose bundle is behind its group is not stored (``behind_its_group``): 409
    ``lock-conflict`` with the sentence of PRD ERR-52 as it stands — another change to the same
    records was being saved at the same moment, so nothing was saved — before anything is
    written. The command is sent again and computes on a later cutoff (the refusal is not kept
    for its idempotency key, DG-KRN-IDEM-03); inside an approval's decision the request stays
    pending and is decided again; a job's attempt ends with it, the group as it was — marked, or
    computed by the later computation that made this one late."""
    ways = behind_its_group(uow, bundle, found)
    if not ways:
        return
    # One line per refusal, the line an operator counts: ``behind_codes`` are the ways, in the
    # order of ``behind_its_group`` (field names within the allow-list of 05 OPR-21).
    get_logger(__name__).info(
        "contract.computation_behind_group",
        combination_group_id=str(found.group["id"]),
        behind_codes=list(ways),
        trigger_code=bundle.trigger,
    )
    raise Problem("lock-conflict", LOCK_CONFLICT_DETAIL)


def persist(
    uow: UnitOfWork,
    bundle: InputBundle,
    output: OutputBundle,
    *,
    duration_ms: int = 0,
    job_id: UUID | None = None,
    close_run_id: UUID | None = None,
) -> Mapping[str, Any]:
    """DG-CMD-10: store the computation of ``bundle`` whose result is ``output``.

    The outputs are written as SYSTEM on behalf of the unit of work's principal, under the tenant's
    scope (05 RCP-18 rev 1.82, TXN-10; dev-guide DG-KRN-UOW-05; supervisor ruling R-95): the
    ledger and schedule lines of a performing entity, and the heads of every member contract,
    belong to the computation whoever asked for it."""
    with uow.as_system():
        return _persist(
            uow, bundle, output, duration_ms=duration_ms, job_id=job_id, close_run_id=close_run_id
        )


def _persist(
    uow: UnitOfWork,
    bundle: InputBundle,
    output: OutputBundle,
    *,
    duration_ms: int,
    job_id: UUID | None,
    close_run_id: UUID | None,
) -> Mapping[str, Any]:
    """``persist`` as SYSTEM under the tenant's scope."""
    session = uow.session
    require_tenant_scope(session)
    input_sha256 = bundle.sha256()
    if output.input_sha256 != input_sha256:
        raise ValueError("the output was computed from another bundle (CV-26)")
    found = bundles.index(session, bundle)
    group_id = UUID(str(found.group["id"]))
    existing = _existing(session, group_id, input_sha256, output.engine_version)
    if existing is not None:
        return {
            **existing,
            "replayed": True,
            "contract_version_ids": _version_ids(session, UUID(str(existing["id"]))),
            "subledger_posting_ids": _posting_ids(session, UUID(str(existing["id"]))),
        }
    require_lineage(bundle, output)
    # Before anything is written: the group row and, inside a window, the state rows of the
    # window's periods (04 DB-07; dev-guide DG-KRN-DB-08 (1c); item CLO-GATE-RUN-1).
    held = period_ends.window_held(uow, bundle, group_id)
    _refuse_a_lock_met(uow, bundle, found)  # PRD ERR-72: a lock decided since the event's stamp
    refuse_a_bundle_behind_its_group(uow, bundle, found)  # PRD ERR-52: the group moved on
    heads = _stream_heads(bundle, found)
    known_at = max((event.recorded_at for event in bundle.events), default=bundle.known_at)
    computation_id = new_id()
    computation_row: dict[str, Any] = {
        "tenant_id": uow.principal.tenant_id,
        "id": computation_id,
        "combination_group_id": group_id,
        "stream_heads": heads,
        "known_at": known_at,
        # The bound this bundle admitted by (04 T-CON-07 rev 1.302): what the way ``head`` of
        # ``behind_its_group`` reads of this computation once it is its group's head.
        "cutoff_at": bundle.known_at,
        "trigger": bundle.trigger,
        "engine_release_id": _engine_release_id(session, output.engine_version),
        "engine_version": output.engine_version,
        "input_sha256": input_sha256,
        "pinned_refs": bundles.pinned_refs(session, bundle, found, output),
        "status": ComputationStatus.SUCCEEDED.value,
        "problem": None,
        "duration_ms": duration_ms,
        "job_id": job_id,
        "close_run_id": close_run_id,
        **_stamps(uow),
    }
    session.execute(insert(contract_computation).values(**computation_row))
    cause_event_ids = _cause_event_ids(bundle, found)
    facts: dict[str, list[UUID]] = {
        name: []
        for name in (
            VERSION_OBJECT,
            TRACE_OBJECT,
            OBLIGATION_VERSION_OBJECT,
            BALANCE_OBJECT,
            SCHEDULE_OBJECT,
            SCHEDULE_LINE_OBJECT,
            "fx_layer_movement",
        )
    }
    version_ids: dict[str, str] = {}
    posting_ids: dict[str, str] = {}
    rate_deviations: list[str] = []  # multi-rate lines stamped with one rate (D-88 L7-6-Q-1)
    for book_output in output.books:
        stored = _persist_book(
            uow,
            bundle,
            output,
            found,
            book_output,
            computation_id=computation_id,
            known_at=known_at,
            cause_event_ids=cause_event_ids,
            facts=facts,
        )
        if stored is not None:
            version_ids[book_output.book_code] = str(stored[0])
        posted = _post_book(
            uow,
            bundle,
            found,
            book_output,
            computation_id=computation_id,
            stored=stored,
            close_run_id=close_run_id,
            deviations=rate_deviations,
        )
        if posted is not None:
            posting_ids[book_output.book_code] = str(posted.posting_id)
    cleared = _update_heads(
        uow,
        found,
        computation_id=computation_id,
        heads=heads,
        period_ends_open=period_ends.after_computation(bundle, held),
    )
    detail: dict[str, Any] = {
        "combination_group_id": str(group_id),
        "trigger": bundle.trigger,
        "engine_version": output.engine_version,
        "input_sha256": input_sha256,
        "dirty_cleared": cleared,
    }
    if rate_deviations:
        # D-88 L7-6-Q-1: T-SL-04 holds one fx_rate_id; these lines keep every rate in their trace.
        detail["rate_stamp_deviations"] = sorted(rate_deviations)
    # A computation is keyed by group: its events name the group's members (04 T-PLT-19).
    members = [UUID(str(row["id"])) for row in found.contracts.values()]
    record_facts(
        uow,
        action=f"{COMPUTATION_OBJECT}.{CREATE}",
        object_type=COMPUTATION_OBJECT,
        ids=[computation_id],
        detail=detail,
        contract_ids=members,
    )
    for object_type, ids in facts.items():
        if ids:
            record_facts(
                uow,
                action=f"{object_type}.{CREATE}",
                object_type=object_type,
                ids=ids,
                contract_ids=members,
            )
    return {
        **computation_row,
        "replayed": False,
        "contract_version_ids": version_ids,
        "subledger_posting_ids": posting_ids,
    }


def recompute(
    uow: UnitOfWork,
    group_id: UUID,
    *,
    trigger: ComputationTrigger = ComputationTrigger.COMMAND,
    engine: Engine | None = None,
    job_id: UUID | None = None,
) -> Mapping[str, Any]:
    """Build the group's bundle at ``uow.now``, call the engine once (DG-CMD-04) and persist, as
    SYSTEM under the tenant's scope (DG-KRN-UOW-05)."""
    run = engine if engine is not None else default_engine()
    with uow.as_system():
        bundle = bundles.build(uow.session, group_id, uow.now, (), trigger)
        started = time.perf_counter()
        output = run(bundle)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return persist(uow, bundle, output, duration_ms=duration_ms, job_id=job_id)
