"""``COA_SYNC``: the chart-of-accounts and dimension-value sync (03 REQ-INT-008, REQ-REF-007,
REQ-REF-009; 04 T-REF-13 ``gl_account``, T-REF-17 ``dimension_value``, T-INT-02 ``kind``, T-INT-04
``external_id_map``; 05 §5.2 ``GLAdapter.pull_chart_of_accounts``, ADP-12; PRD J-23.7; BUILD_SPEC
DIN-14).

``plan_chart_sync`` is the pure decision of a run: given the ERP's accounts and the workspace's, it
answers what to insert (with ``source_system = NETSUITE``), what to rename, what to deactivate (an
account of ERP origin, or mapped to the ERP, that is absent from the chart or inactive there is set
``is_active = false`` and never deleted), what is unchanged, and the ``external_id_map`` rows
(``object_type = gl_account``) that bind each workspace account to its ERP record id.
``plan_dimension_sync`` does the same for one dimension's values (``object_type =
dimension_value``). Replanning an applied plan yields no changes.

``run_chart_sync`` is the ``SYNC_RUN`` job of kind ``COA_SYNC`` (``sync.run_sync`` hands it the
started run): it pulls the chart and the configured dimensions from the connection's chart source
(``ports.chart_source_for``; no transaction open while the adapter retries), then, in one unit of
work as the sync principal, applies the plans through the reference commands a person would use —
``create_gl_account`` / ``update_gl_account``, ``create_dimension_value`` /
``update_dimension_value`` — so every change is validated and audited as theirs is, and links each
account and value to its ERP record (T-INT-04). ``record_count`` is the number of ERP accounts
read; the source totals count them and the loaded totals the ones the run reflected — held in the
ERP's state, or inactive there and never brought in. A conflict — a workspace account of the same
code with another type or normal balance — or a record a reference command refuses is left alone
and named in the run's ``problem`` (failure step ``reference``), and the run ends FAILED with
everything else applied. A chart the ERP refuses, or states empty, is a ``fetch`` failure that
changes nothing: an empty answer never deactivates the accounts the ERP gave.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import dimension_definition, dimension_value, external_id_map, gl_account
from erev_api.domain.integrations import ports
from erev_api.domain.journals import ports as gl_ports
from erev_api.enums import AccountType, SourceSystem, SyncRunStatus
from erev_api.events.outbox import Undeliverable
from erev_api.jobs.registry import JobOutcome
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import Problem

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

__all__ = [
    "ACCOUNT_OBJECT",
    "COA_SYNC",
    "DEFAULT_DIMENSIONS",
    "DIMENSIONS_KEY",
    "REFERENCE_STEP",
    "VALUE_OBJECT",
    "ChartCounts",
    "ChartSyncPlan",
    "DimensionSyncPlan",
    "ErpAccountInput",
    "ErpValueInput",
    "MappingRow",
    "WorkspaceAccount",
    "WorkspaceValue",
    "chart_totals",
    "dimensions_of",
    "plan_chart_sync",
    "plan_dimension_sync",
    "run_chart_sync",
]

SOURCE_SYSTEM: Final = "NETSUITE"
COA_SYNC: Final = "COA_SYNC"  # T-INT-02 ``kind``
ACCOUNT_OBJECT: Final = "gl_account"  # T-INT-04 object types
VALUE_OBJECT: Final = "dimension_value"
# ``integration_connection.config`` member naming the dimensions a run syncs (non-secret, T-INT-01).
DIMENSIONS_KEY: Final = "dimensions"
DEFAULT_DIMENSIONS: Final = ("department",)
REFERENCE_STEP: Final = "reference"  # T-INT-02 ``problem.failures[].step`` of a reference record
FETCH_STEP: Final = "fetch"
CHART: Final = "chart of accounts"  # the ``external_id`` of a fetch failure of the whole chart
EMPTY_CHART: Final = "the ERP stated an empty chart of accounts; nothing was changed"
_LOGGER: Final = "erev_api.domain.integrations.coa_sync"
register_logger_fields(_LOGGER, ("sync_run_id", "connection_id", "status", "count"))


@dataclass(frozen=True, slots=True)
class ErpAccountInput:
    external_id: str
    code: str
    name: str
    account_type: str
    normal_balance: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class WorkspaceAccount:
    code: str
    name: str
    account_type: str
    normal_balance: str
    is_active: bool
    source_system: str
    external_id: str | None = None  # the mapped ERP record id, when a mapping exists


@dataclass(frozen=True, slots=True)
class MappingRow:
    object_type: Literal["gl_account", "dimension_value"]
    internal_code: str
    external_id: str


@dataclass(frozen=True, slots=True)
class ChartSyncPlan:
    inserts: tuple[ErpAccountInput, ...] = ()
    renames: tuple[tuple[str, str, str], ...] = ()  # (code, old name, new name)
    reactivations: tuple[str, ...] = ()
    deactivations: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    mappings: tuple[MappingRow, ...] = ()
    conflicts: tuple[str, ...] = field(default_factory=tuple)  # never applied; reported

    @property
    def is_noop(self) -> bool:
        return not (
            self.inserts
            or self.renames
            or self.reactivations
            or self.deactivations
            or self.mappings
        )


def plan_chart_sync(
    erp: Sequence[ErpAccountInput], workspace: Sequence[WorkspaceAccount]
) -> ChartSyncPlan:
    """DIN-14: a new ERP account is inserted with ``source_system = NETSUITE``; an existing account
    whose ERP name differs is renamed; an ERP account marked inactive, or a workspace account of
    ERP origin — or mapped to an ERP record — that is absent from the chart, is deactivated, never
    deleted; an account with the same code but another type or balance is a conflict, reported and
    left alone; a workspace account the ERP never knew is untouched."""
    by_code = {account.code: account for account in workspace}
    seen: set[str] = set()
    inserts: list[ErpAccountInput] = []
    renames: list[tuple[str, str, str]] = []
    reactivations: list[str] = []
    deactivations: list[str] = []
    unchanged: list[str] = []
    mappings: list[MappingRow] = []
    conflicts: list[str] = []
    for account in sorted(erp, key=lambda a: a.code):
        seen.add(account.code)
        current = by_code.get(account.code)
        if current is None:
            if account.is_active:
                inserts.append(account)
                mappings.append(MappingRow("gl_account", account.code, account.external_id))
            continue
        if (current.account_type, current.normal_balance) != (
            account.account_type,
            account.normal_balance,
        ):
            conflicts.append(
                f"{account.code}: workspace {current.account_type}/{current.normal_balance} "
                f"vs ERP {account.account_type}/{account.normal_balance}"
            )
            continue
        changed = False
        if current.name != account.name:
            renames.append((account.code, current.name, account.name))
            changed = True
        if current.is_active and not account.is_active:
            deactivations.append(account.code)
            changed = True
        elif not current.is_active and account.is_active:
            reactivations.append(account.code)
            changed = True
        if current.external_id != account.external_id:
            mappings.append(MappingRow("gl_account", account.code, account.external_id))
            changed = True
        if not changed:
            unchanged.append(account.code)
    for existing in sorted(workspace, key=lambda a: a.code):
        of_the_erp = existing.source_system == SOURCE_SYSTEM or existing.external_id is not None
        if existing.code in seen or not existing.is_active or not of_the_erp:
            continue
        deactivations.append(existing.code)  # absent from the ERP chart: deactivated, never deleted
    return ChartSyncPlan(
        inserts=tuple(inserts),
        renames=tuple(renames),
        reactivations=tuple(reactivations),
        deactivations=tuple(sorted(deactivations)),
        unchanged=tuple(unchanged),
        mappings=tuple(mappings),
        conflicts=tuple(conflicts),
    )


@dataclass(frozen=True, slots=True)
class ErpValueInput:
    external_id: str
    code: str
    name: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class WorkspaceValue:
    code: str
    name: str
    is_active: bool
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class DimensionSyncPlan:
    dimension_code: str
    inserts: tuple[ErpValueInput, ...] = ()
    renames: tuple[tuple[str, str, str], ...] = ()
    deactivations: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    mappings: tuple[MappingRow, ...] = ()

    @property
    def is_noop(self) -> bool:
        return not (self.inserts or self.renames or self.deactivations or self.mappings)


def plan_dimension_sync(
    dimension_code: str, erp: Sequence[ErpValueInput], workspace: Sequence[WorkspaceValue]
) -> DimensionSyncPlan:
    """The same decisions for one dimension's values (``department`` from the ERP)."""
    by_code = {value.code: value for value in workspace}
    inserts: list[ErpValueInput] = []
    renames: list[tuple[str, str, str]] = []
    deactivations: list[str] = []
    unchanged: list[str] = []
    mappings: list[MappingRow] = []
    for value in sorted(erp, key=lambda v: v.code):
        current = by_code.get(value.code)
        if current is None:
            if value.is_active:
                inserts.append(value)
                mappings.append(MappingRow("dimension_value", value.code, value.external_id))
            continue
        changed = False
        if current.name != value.name:
            renames.append((value.code, current.name, value.name))
            changed = True
        if current.is_active and not value.is_active:
            deactivations.append(value.code)
            changed = True
        if current.external_id != value.external_id:
            mappings.append(MappingRow("dimension_value", value.code, value.external_id))
            changed = True
        if not changed:
            unchanged.append(value.code)
    return DimensionSyncPlan(
        dimension_code=dimension_code,
        inserts=tuple(inserts),
        renames=tuple(renames),
        deactivations=tuple(deactivations),
        unchanged=tuple(unchanged),
        mappings=tuple(mappings),
    )


# --- the run (unit of work; BUILD_SPEC DIN-14) ----------------------------------------------------


@dataclass(slots=True)
class ChartCounts:
    """What a ``COA_SYNC`` run did, as its job's ``result.counts``."""

    fetched: int = 0  # ERP accounts read
    accounts_created: int = 0
    accounts_renamed: int = 0
    accounts_deactivated: int = 0
    accounts_reactivated: int = 0
    accounts_unchanged: int = 0
    accounts_mapped: int = 0  # T-INT-04 links written or moved
    dimension_values_fetched: int = 0
    dimension_values_created: int = 0
    dimension_values_renamed: int = 0
    dimension_values_deactivated: int = 0
    dimension_values_mapped: int = 0
    conflicts: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "accounts_created": self.accounts_created,
            "accounts_renamed": self.accounts_renamed,
            "accounts_deactivated": self.accounts_deactivated,
            "accounts_reactivated": self.accounts_reactivated,
            "accounts_unchanged": self.accounts_unchanged,
            "accounts_mapped": self.accounts_mapped,
            "dimension_values_fetched": self.dimension_values_fetched,
            "dimension_values_created": self.dimension_values_created,
            "dimension_values_renamed": self.dimension_values_renamed,
            "dimension_values_deactivated": self.dimension_values_deactivated,
            "dimension_values_mapped": self.dimension_values_mapped,
            "conflicts": self.conflicts,
            "failures": len(self.failures),
        }


def dimensions_of(connection: Mapping[str, Any]) -> tuple[str, ...]:
    """The dimensions a run syncs: ``config.dimensions`` of the connection, else ``department``."""
    configured = (connection.get("config") or {}).get(DIMENSIONS_KEY)
    if not configured:
        return DEFAULT_DIMENSIONS
    return tuple(dict.fromkeys(str(code) for code in configured))


def chart_totals(rows: Sequence[tuple[str, str, str, bool]]) -> ports.ControlTotals:
    """T-INT-02 ``source_totals`` / ``loaded_totals`` of a chart: the count of accounts and the
    digest of their sorted (ERP record id, code, name, active) rows; a chart carries no amount."""
    ordered = [
        [external_id, code, name, active] for external_id, code, name, active in sorted(rows)
    ]
    digest = hashlib.sha256(
        json.dumps(ordered, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return ports.ControlTotals(count=len(ordered), amount_by_currency={}, sha256=digest)


def _literal(value: Any) -> str:
    return str(getattr(value, "value", value))


def _links(session: Session, connection_id: UUID, object_type: str) -> dict[UUID, str]:
    """internal id → ERP record id of the connection's live T-INT-04 links of ``object_type``."""
    rows = session.execute(
        select(external_id_map.c.internal_id, external_id_map.c.external_id).where(
            external_id_map.c.integration_connection_id == connection_id,
            external_id_map.c.object_type == object_type,
            external_id_map.c.valid_to.is_(None),
        )
    )
    return {UUID(str(internal_id)): str(external_id) for internal_id, external_id in rows}


def _workspace_accounts(
    session: Session, connection_id: UUID
) -> tuple[list[WorkspaceAccount], dict[str, UUID]]:
    links = _links(session, connection_id, ACCOUNT_OBJECT)
    rows = session.execute(
        select(
            gl_account.c.id,
            gl_account.c.code,
            gl_account.c.name,
            gl_account.c.account_type,
            gl_account.c.normal_balance,
            gl_account.c.is_active,
            gl_account.c.source_system,
        ).order_by(gl_account.c.code)
    ).mappings()
    found: list[WorkspaceAccount] = []
    ids: dict[str, UUID] = {}
    for row in rows:
        account_id = UUID(str(row["id"]))
        ids[str(row["code"])] = account_id
        found.append(
            WorkspaceAccount(
                code=str(row["code"]),
                name=str(row["name"]),
                account_type=_literal(row["account_type"]),
                normal_balance=str(row["normal_balance"]).strip(),
                is_active=bool(row["is_active"]),
                source_system=_literal(row["source_system"]),
                external_id=links.get(account_id),
            )
        )
    return found, ids


def _workspace_values(
    session: Session, connection_id: UUID, dimension_code: str
) -> tuple[list[WorkspaceValue], dict[str, UUID]] | None:
    """The stored values of a dimension, or None when the workspace has no such dimension."""
    definition_id = session.execute(
        select(dimension_definition.c.id).where(dimension_definition.c.code == dimension_code)
    ).scalar_one_or_none()
    if definition_id is None:
        return None
    links = _links(session, connection_id, VALUE_OBJECT)
    rows = session.execute(
        select(
            dimension_value.c.id,
            dimension_value.c.code,
            dimension_value.c.name,
            dimension_value.c.is_active,
        )
        .where(dimension_value.c.dimension_definition_id == definition_id)
        .order_by(dimension_value.c.code)
    ).mappings()
    found: list[WorkspaceValue] = []
    ids: dict[str, UUID] = {}
    for row in rows:
        value_id = UUID(str(row["id"]))
        ids[str(row["code"])] = value_id
        found.append(
            WorkspaceValue(
                code=str(row["code"]),
                name=str(row["name"]),
                is_active=bool(row["is_active"]),
                external_id=links.get(value_id),
            )
        )
    return found, ids


def _any_version(_: int) -> None:
    """The sync writes over whatever version is stored: it holds the row lock the command takes."""


def _refused(
    counts: ChartCounts, object_type: str, external_id: str, code: str, error: object
) -> None:
    record: dict[str, Any] = {
        "step": REFERENCE_STEP,
        "object_type": object_type,
        "external_id": external_id,
        "external_version": None,
        "code": code,
        "error": f"{type(error).__name__}: {error}" if isinstance(error, Exception) else str(error),
    }
    if isinstance(error, Problem):
        record["errors"] = [
            {"field": item.field, "rule_id": item.rule_id, "message": item.message}
            for item in error.errors
        ]
    counts.failures.append(record)


def _attempt(
    uow: UnitOfWork,
    counts: ChartCounts,
    change: Callable[[], None],
    *,
    object_type: str,
    external_id: str,
    code: str,
) -> bool:
    """One reference change in a savepoint: a refusal undoes that change only and is named."""
    try:
        with uow.savepoint():
            change()
    except Problem as problem:
        _refused(counts, object_type, external_id, code, problem)
        return False
    return True


def _apply_chart(
    uow: UnitOfWork,
    plan: ChartSyncPlan,
    *,
    connection_id: UUID,
    ids: dict[str, UUID],
    erp: Mapping[str, ErpAccountInput],
    sync_run_id: UUID,
    counts: ChartCounts,
) -> set[str]:
    """Apply a chart plan; the codes of the ERP accounts the run could NOT reflect — a conflict,
    or a change the reference command refused. Every other ERP account is reflected: held in the
    ERP's state, or inactive there and never brought in."""
    # Imported here: the reference commands reach this package through the policy registry.
    from erev_api.domain.integrations.sync import link_external_id
    from erev_api.domain.reference import commands as reference
    from erev_api.schemas.accounts import GlAccountIn

    refused: set[str] = set()
    for account in plan.inserts:

        def insert(account: ErpAccountInput = account) -> None:
            created = reference.create_gl_account(
                uow,
                body=GlAccountIn(
                    code=account.code,
                    name=account.name,
                    account_type=AccountType(account.account_type),
                    normal_balance=account.normal_balance,
                ),
                source_system=SourceSystem.NETSUITE,
            )
            ids[account.code] = created.id

        if _attempt(
            uow,
            counts,
            insert,
            object_type=ACCOUNT_OBJECT,
            external_id=account.external_id,
            code=account.code,
        ):
            counts.accounts_created += 1
        else:
            refused.add(account.code)
    changes: list[tuple[str, dict[str, Any], str]] = [
        *((code, {"name": new_name}, "accounts_renamed") for code, _, new_name in plan.renames),
        *((code, {"is_active": False}, "accounts_deactivated") for code in plan.deactivations),
        *((code, {"is_active": True}, "accounts_reactivated") for code in plan.reactivations),
    ]
    for code, change, counter in changes:

        def update(code: str = code, change: dict[str, Any] = change) -> None:
            reference.update_gl_account(
                uow, account_id=ids[code], changes=change, check_version=_any_version
            )

        named = erp[code].external_id if code in erp else code
        if _attempt(uow, counts, update, object_type=ACCOUNT_OBJECT, external_id=named, code=code):
            setattr(counts, counter, getattr(counts, counter) + 1)
        else:
            refused.add(code)
    for mapping in plan.mappings:
        if mapping.internal_code in refused or mapping.internal_code not in ids:
            continue
        link_external_id(
            uow,
            connection_id,
            object_type=ACCOUNT_OBJECT,
            internal_id=ids[mapping.internal_code],
            external_id=mapping.external_id,
            external_version=None,
            sync_run_id=sync_run_id,
        )
        counts.accounts_mapped += 1
    for conflict in plan.conflicts:
        code = conflict.split(":", 1)[0]
        refused.add(code)
        counts.conflicts += 1
        _refused(
            counts,
            ACCOUNT_OBJECT,
            erp[code].external_id if code in erp else code,
            code,
            f"account {conflict}; the workspace account was left alone",
        )
    counts.accounts_unchanged += len(plan.unchanged)
    return refused


def _apply_dimension(
    uow: UnitOfWork,
    plan: DimensionSyncPlan,
    *,
    connection_id: UUID,
    ids: dict[str, UUID],
    erp: Mapping[str, ErpValueInput],
    sync_run_id: UUID,
    counts: ChartCounts,
) -> None:
    from erev_api.domain.integrations.sync import link_external_id
    from erev_api.domain.reference import commands as reference
    from erev_api.schemas.dimensions import DimensionValueIn

    refused: set[str] = set()
    for value in plan.inserts:

        def insert(value: ErpValueInput = value) -> None:
            created = reference.create_dimension_value(
                uow,
                dimension_code=plan.dimension_code,
                body=DimensionValueIn(code=value.code, name=value.name),
            )
            ids[value.code] = created.id

        if _attempt(
            uow,
            counts,
            insert,
            object_type=VALUE_OBJECT,
            external_id=value.external_id,
            code=value.code,
        ):
            counts.dimension_values_created += 1
        else:
            refused.add(value.code)
    changes: list[tuple[str, dict[str, Any], str]] = [
        *((code, {"name": new}, "dimension_values_renamed") for code, _, new in plan.renames),
        *(
            (code, {"is_active": False}, "dimension_values_deactivated")
            for code in plan.deactivations
        ),
    ]
    for code, change, counter in changes:

        def update(code: str = code, change: dict[str, Any] = change) -> None:
            reference.update_dimension_value(
                uow,
                dimension_code=plan.dimension_code,
                value_id=ids[code],
                changes=change,
                check_version=_any_version,
            )

        named = erp[code].external_id if code in erp else code
        if _attempt(uow, counts, update, object_type=VALUE_OBJECT, external_id=named, code=code):
            setattr(counts, counter, getattr(counts, counter) + 1)
        else:
            refused.add(code)
    for mapping in plan.mappings:
        if mapping.internal_code in refused or mapping.internal_code not in ids:
            continue
        link_external_id(
            uow,
            connection_id,
            object_type=VALUE_OBJECT,
            internal_id=ids[mapping.internal_code],
            external_id=mapping.external_id,
            external_version=None,
            sync_run_id=sync_run_id,
        )
        counts.dimension_values_mapped += 1


def _fetch_failure(object_type: str, resource: str, error: Exception) -> dict[str, Any]:
    return {
        "step": FETCH_STEP,
        "object_type": object_type,
        "external_id": resource,
        "external_versions": [],
        "error": f"{type(error).__name__}: {error}",
    }


def run_chart_sync(
    jc: JobContext,
    *,
    run_id: UUID,
    connection: Mapping[str, Any],
    tenant_code: str,
) -> JobOutcome:
    """The ``COA_SYNC`` run of a started (RUNNING) T-INT-02 row (module docstring)."""
    # Imported here: ``sync`` dispatches this kind and imports this module to do so.
    from erev_api.domain.integrations import sync

    connection_id = UUID(str(connection["id"]))
    counts = ChartCounts()
    accounts: tuple[ErpAccountInput, ...] = ()
    values: dict[str, tuple[ErpValueInput, ...]] = {}
    fetch_failures: list[dict[str, Any]] = []
    # --- fetch: no transaction open while the adapter retries on the ADP-12 schedule -------------
    try:
        base_url = connection.get("base_url")
        if not base_url:
            raise gl_ports.Permanent("the connection has no base_url")
        source = ports.chart_source_for(
            str(connection["adapter"]),
            ports.InboundContext(
                tenant_code=tenant_code,
                base_url=str(base_url),
                config=dict(connection.get("config") or {}),
                client=sync.http_client(str(base_url)),
            ),
        )
        accounts = tuple(
            ErpAccountInput(
                external_id=item.external_id,
                code=item.code,
                name=item.name,
                account_type=item.account_type,
                normal_balance=item.normal_balance,
                is_active=item.is_active,
            )
            for item in source.pull_erp_accounts()
        )
    except (gl_ports.Transient, Undeliverable, LookupError) as error:
        fetch_failures.append(_fetch_failure(ACCOUNT_OBJECT, CHART, error))
    else:
        if not accounts:
            # An ERP states a chart. An empty answer — a role without the permission to list
            # accounts reads as one — must not deactivate every account the ERP gave: fail closed.
            fetch_failures.append(
                _fetch_failure(ACCOUNT_OBJECT, CHART, gl_ports.Permanent(EMPTY_CHART))
            )
        for dimension in dimensions_of(connection):
            try:
                values[dimension] = tuple(
                    ErpValueInput(
                        external_id=item.external_id,
                        code=item.code,
                        name=item.name,
                        is_active=item.is_active,
                    )
                    for item in source.pull_dimension_values(dimension)
                )
            except (gl_ports.Transient, Undeliverable) as error:
                fetch_failures.append(_fetch_failure(VALUE_OBJECT, dimension, error))
    jc.heartbeat()
    counts.fetched = len(accounts)
    counts.dimension_values_fetched = sum(len(found) for found in values.values())
    erp_accounts = {account.code: account for account in accounts}
    # --- apply: one unit of work as the sync principal --------------------------------------------
    with sync.sync_unit_of_work(jc) as uow:
        session = uow.session
        refused: set[str] = set()
        if accounts:
            workspace, ids = _workspace_accounts(session, connection_id)
            refused = _apply_chart(
                uow,
                plan_chart_sync(accounts, workspace),
                connection_id=connection_id,
                ids=ids,
                erp=erp_accounts,
                sync_run_id=run_id,
                counts=counts,
            )
        for dimension, found in values.items():
            stored = _workspace_values(session, connection_id, dimension)
            if stored is None:
                counts.failures.append(
                    {
                        "step": REFERENCE_STEP,
                        "object_type": VALUE_OBJECT,
                        "external_id": dimension,
                        "external_version": None,
                        "error": f"the workspace has no dimension {dimension!r}",
                    }
                )
                continue
            workspace_values, value_ids = stored
            _apply_dimension(
                uow,
                plan_dimension_sync(dimension, found, workspace_values),
                connection_id=connection_id,
                ids=value_ids,
                erp={value.code: value for value in found},
                sync_run_id=run_id,
                counts=counts,
            )
        source_totals = chart_totals(
            [(a.external_id, a.code, a.name, a.is_active) for a in accounts]
        )
        loaded_totals = chart_totals(
            [
                (a.external_id, a.code, a.name, a.is_active)
                for a in accounts
                if a.code not in refused
            ]
        )
        ledger = sync.Counts(fetched=counts.fetched, records=len(accounts))
        ledger.failures.extend(counts.failures)
        problem = sync.run_problem_of(ledger, run_id=run_id, fetch_failures=fetch_failures)
        status = (
            SyncRunStatus.FAILED.value
            if problem is not None
            else ports.compare_totals(source_totals, loaded_totals)
        )
        sync.finish_run(
            uow,
            run_id=run_id,
            connection=connection,
            status=status,
            source=source_totals,
            loaded=loaded_totals,
            counts=ledger,
            problem=problem,
        )
        uow.commit()
    get_logger(_LOGGER).info(
        "coa_sync.finished",
        sync_run_id=str(run_id),
        connection_id=str(connection_id),
        status=status,
        count=len(accounts),
    )
    clean = status == SyncRunStatus.SUCCEEDED.value
    return JobOutcome(
        state="SUCCEEDED" if clean else "SUCCEEDED_WITH_EXCEPTIONS",
        result={
            "href": f"/api/v1/sync-runs/{run_id}",
            "status": status,
            "kind": COA_SYNC,
            "counts": counts.as_json(),
        },
    )
