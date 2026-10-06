"""Journal run calculation (ENGINE_SPEC_B §14.3 S14-R-16 to S14-R-24; 04 T-SL-06 to T-SL-09, §16.7;
POLICIES POL-005, POL-006, CHK-020, CHK-022; 05 RCP-27; dev-guide DG-KRN-JOB-01 to DG-KRN-JOB-05;
BUILD_SPEC CLO-8).

``calculate_run`` is the ``JOURNAL_RUN_CALCULATE`` handler. In one transaction it:

1. covers the seals of the book whose ``chain_seq`` lies after the non-cancelled runs of the same
   (entity, book, period) — whatever their mode, so a seal is journalised by one run only (04 DB-16
   rev 1.106; security finding SC-7) — and was sealed by ``cutoff_known_at`` (S14-R-16), under the
   key's coverage lock (``lock_coverage``), which a cancellation also holds. ``DELTA`` also covers
   the LEGACY book's range, which starts where the LEGACY ranges of those runs end, and adds those
   lines, which reverse the pre-standard revenue the ERP booked (S14-R-23; JET-15; D-89 L7-6-Q-8);
2. leaves out the lines of contracts under an open ``journal_export`` hold and lists them as held in
   each batch's detail file and, whatever their currency, in the run's held detail file whose id and
   SHA-256 the CALCULATE audit event carries (S14-R-17; Codex production-20260921-0920 §3) — and
   takes over the lines that a run of the key which is not cancelled left out that way, that no
   such run has taken over since and whose contract is under no open hold now: they are summarized
   with the lines of the range and named by id in the CALCULATE event and in a detail file of
   their own (S14-R-17 rev 1.164; 04 DB-16 rev 1.267; item JRN-HELD-AFTER-EXPORT-1). Until that
   revision a released line inside the range of an exported run was reached by no run;
3. nets the lines per grouping key of the grain (S14-R-18; table 14.3.2), drops a group whose both
   nets are 0, and orders the lines by S14-R-20;
4. writes one batch per transaction currency, in chunks of whole entries, with ``external_id``
   ``erev:<tenant code>:<run_no>:<batch_no>:<chunk_no>`` and the retained detail file (S14-R-21,
   S14-R-22), and one journal entry per group of entry kinds, with gapless JE numbers per entity
   (S14-R-19, S14-R-20; T-SL-08).

The general ledger of a run (BUILD_SPEC CLO-15; 05 ADP-11; T-SL-07 ``adapter`` is not updatable, so
it is fixed here): ``gl_target`` reads the entity's ACTIVE outbound GL connection (T-INT-01) — its
adapter, its id and its chunk size (``config.max_lines_per_chunk``, else the ADP-11 default) — and
answers ``CSV`` without a connection and in a sandbox (DB-15); two such connections for one entity
refuse the calculation by name. ``chunk_entries`` takes whole entries in S14-R-20 order until the
limit would be exceeded; an entry larger than the limit is summarised again at
``CONTRACT_ACCOUNT_DIMENSIONS`` and split by contract, each part balancing on its own, and an
entry that cannot be brought under the limit that way refuses the calculation by name.

[J] L6-3-Q-2: at the ``*_ACCOUNT_DIMENSIONS`` grains the "dimension set" is the line's dimensions
of the workspace's stored-value dimensions (T-REF-16 active codes except ``product`` and
``customer``). The JET R3 descriptors of S14-R-13 (contract, obligation, product) stay drill
attributes, so the three Contract 1 liability lines net to one 21001 line (test_default_grain).
[J] L6-3-Q-3: S14-R-19 "one entry per (batch, entry kind)" with netting across kinds (21002 of
Contract 2 nets to 0 across ``REVENUE_RECOGNITION`` and ``NETTING_RECLASS``, CHK-022) is read as
one entry per group of kinds that share a grouping key; the entry kind is set when the group holds
one kind (T-SL-08), and every entry balances because its kinds balance.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine import ENGINE_VERSION
from erev_engine.canonical import sha256_hex
from sqlalchemy import ColumnElement, Select, Uuid, and_, any_, func, insert, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from erev_api import periods
from erev_api.audit.writer import record_facts
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.controls.release import current_environment, current_release
from erev_api.controls.stamping import process_release_id
from erev_api.db import new_id
from erev_api.db.tables import (
    contract,
    contract_hold,
    dimension_definition,
    engine_release,
    gl_account,
    integration_connection,
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    legal_entity,
    period,
    period_state,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
    tenant,
)
from erev_api.domain.imports.exceptions import raise_exception_item
from erev_api.domain.imports.job_items import failed_item
from erev_api.domain.journals import completeness, ports, validation
from erev_api.domain.journals.subledger import dimension_set_sha256
from erev_api.domain.reference.dimensions import UNSTORED_VALUE_DIMENSIONS
from erev_api.enums import (
    BookCode,
    ControlResult,
    ExceptionSeverity,
    ExceptionSource,
    FilePurpose,
    GlAdapter,
    JeType,
    JobKind,
    JournalRunGrain,
    JournalRunMode,
    JournalState,
    SubledgerEntryKind,
    SubledgerPostingKind,
    TenantKind,
)
from erev_api.files.store import store_file
from erev_api.jobs.registry import FailedSubject, JobOutcome, task
from erev_api.numbering import ensure_entity_series, next_number, next_numbers
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.files.store import FileStore
    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

OBJECT_TYPE: Final = "journal_run"
CALCULATE_ACTION: Final = "journal_run.calculate"
RUN_HREF: Final = "/api/v1/journal-runs/{run_id}"
RUN_SERIES: Final = "JOURNAL_RUN"
JE_SERIES: Final = "JE"
HOLD_JOURNAL_EXPORT: Final = "journal_export"
# PJR-5 and table 14.3.2: the revenue roles of the LEGACY_CONTRACT_POB grain, keyed by legacy key.
REVENUE_ROLES: Final = frozenset({"REVENUE", "PRE_STANDARD_REVENUE"})
# S14-R-19 (rev 1.63): the lines of a manual adjustment are summarised apart from every other
# kind and per adjustment, so its journal entry is ``manual`` and names the adjustment (T-SL-08).
MANUAL_KIND: Final = SubledgerEntryKind.MANUAL_ADJUSTMENT.value
# S14-R-21: the grain at which an entry larger than its ledger's chunk is summarised again, to be
# split by contract (``split_entry``). A journal line of such an entry carries the grouping hash
# of THIS grain, whatever the run's own grain is (``line_grains``).
SPLIT_GRAIN: Final = JournalRunGrain.CONTRACT_ACCOUNT_DIMENSIONS
ZERO: Final = Decimal(0)


@dataclass(frozen=True, slots=True)
class DetailLine:
    """One sealed subledger line as a run reads it; ``sign`` is −1 for the LEGACY lines of a
    ``DELTA`` run (S14-R-23)."""

    id: UUID
    book_code: str
    sign: int
    chain_seq: int
    posting_kind: str
    entry_kind: str
    account_role: str
    gl_account_id: UUID
    gl_account_code: str
    dimensions: Mapping[str, str]
    txn_currency: str
    amount_txn: Decimal
    functional_currency: str
    amount_functional: Decimal
    contract_id: UUID | None = None
    obligation_id: UUID | None = None
    legacy_key: str | None = None
    counterparty_entity_id: UUID | None = None
    origin_period_id: UUID | None = None
    is_post_reopen: bool = False
    contract_event_id: UUID | None = None
    fx_rate_set_version_id: UUID | None = None
    fx_rate_id: UUID | None = None
    # T-SL-01 ``manual_adjustment_id`` of the line's posting (kind ``MANUAL_ADJUSTMENT``).
    manual_adjustment_id: UUID | None = None


def _text(value: object) -> str:
    return "" if value is None else str(value)


def reporting_dimensions(line: DetailLine, codes: frozenset[str]) -> dict[str, str]:
    """The line's members of the workspace's stored-value dimensions (L6-3-Q-2)."""
    return {key: str(value) for key, value in sorted(line.dimensions.items()) if key in codes}


def grouping_key(
    line: DetailLine, grain: JournalRunGrain, dimension_codes: frozenset[str]
) -> tuple[str, ...]:
    """The canonical grouping key of a line under ``grain`` (table 14.3.2). A line of entry kind
    ``MANUAL_ADJUSTMENT`` ends its key with the kind and its adjustment (S14-R-19 rev 1.63): it
    nets only with the lines of the same adjustment, never with an automated line on the same
    account and dimensions."""
    key: tuple[str, ...]
    if grain is JournalRunGrain.LEGACY_CONTRACT_POB:
        if line.account_role in REVENUE_ROLES:
            key = (
                grain.value,
                "REVENUE",
                line.txn_currency,
                str(line.gl_account_id),
                _text(line.legacy_key),
            )
        else:
            key = (
                grain.value,
                "BALANCE",
                line.txn_currency,
                str(line.gl_account_id),
                _text(line.contract_id),
            )
    else:
        key = (
            grain.value,
            line.txn_currency,
            str(line.gl_account_id),
            dimension_set_sha256(reporting_dimensions(line, dimension_codes)),
            _text(line.counterparty_entity_id),
            _text(line.origin_period_id),
        )
        if grain is JournalRunGrain.CONTRACT_ACCOUNT_DIMENSIONS:
            key = (*key, _text(line.contract_id))
    if line.entry_kind == MANUAL_KIND:
        return (*key, MANUAL_KIND, _text(line.manual_adjustment_id))
    return key


def grouping_sha256(key: Sequence[str]) -> str:
    """``source_grouping_sha256`` of a canonical grouping key (S14-R-18; T-SL-09)."""
    return sha256_hex(list(key))


def line_grains(grain: JournalRunGrain) -> tuple[JournalRunGrain, ...]:
    """The grains a journal line of a run of ``grain`` can have been summarised at: the run's
    own, and ``SPLIT_GRAIN`` for a line of an entry that was split by contract (S14-R-21)."""
    return (grain,) if grain is SPLIT_GRAIN else (grain, SPLIT_GRAIN)


def lines_of_group(
    lines: Sequence[DetailLine],
    sha256: str,
    *,
    grain: JournalRunGrain,
    dimension_codes: frozenset[str],
) -> list[DetailLine]:
    """The detail lines of a journal line: those of ``lines`` whose grouping key hashes to the
    journal line's ``source_grouping_sha256`` at the grain the journal line was summarised at —
    the run's own, or ``SPLIT_GRAIN`` (``line_grains``; 04 T-SL-06 drill-back rev 1.288). A key
    starts with its grain, so the hash is met at one grain alone: the run's grain is asked
    first, the split grain only for a journal line that no detail line meets there. Until rev
    1.288 the drill hashed at the run's grain alone, and the journal line of an entry split by
    contract named no detail line at all."""
    for at in line_grains(grain):
        found = [
            line
            for line in lines
            if grouping_sha256(grouping_key(line, at, dimension_codes)) == sha256
        ]
        if found:
            return found
    return []


@dataclass(slots=True)
class SummaryLine:
    """A summarised journal line of one grouping key (S14-R-18)."""

    key: tuple[str, ...]
    sha256: str
    grain: JournalRunGrain
    account_role: str
    gl_account_id: UUID
    gl_account_code: str
    dimensions: dict[str, str]
    txn_currency: str
    functional_currency: str
    net_txn: Decimal = ZERO
    net_functional: Decimal = ZERO
    contracts: set[UUID] = field(default_factory=set)
    obligations: set[UUID] = field(default_factory=set)
    legacy_keys: set[str] = field(default_factory=set)
    counterparties: set[UUID] = field(default_factory=set)
    origin_periods: set[UUID] = field(default_factory=set)
    fx_rate_set_version_ids: set[UUID] = field(default_factory=set)
    fx_rate_ids: set[UUID] = field(default_factory=set)
    event_ids: set[UUID] = field(default_factory=set)
    entry_kinds: set[str] = field(default_factory=set)
    posting_kinds: set[str] = field(default_factory=set)
    manual_adjustment_ids: set[UUID] = field(default_factory=set)
    line_ids: list[UUID] = field(default_factory=list)
    post_close: bool = False

    @property
    def debit_txn(self) -> Decimal:
        return max(self.net_txn, ZERO)

    @property
    def credit_txn(self) -> Decimal:
        return max(-self.net_txn, ZERO)

    @property
    def debit_functional(self) -> Decimal:
        return max(self.net_functional, ZERO)

    @property
    def credit_functional(self) -> Decimal:
        return max(-self.net_functional, ZERO)

    @property
    def entry_kind(self) -> str | None:
        return next(iter(self.entry_kinds)) if len(self.entry_kinds) == 1 else None

    @staticmethod
    def _single[T](values: set[T]) -> T | None:
        return next(iter(values)) if len(values) == 1 else None

    @property
    def manual_adjustment_id(self) -> UUID | None:
        """The adjustment of a line of kind ``MANUAL_ADJUSTMENT``, when its detail lines name
        one (a line stage 14 posted on a replayed ledger names none)."""
        return self._single(self.manual_adjustment_ids)

    @property
    def contract_id(self) -> UUID | None:
        if self.grain is JournalRunGrain.ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS:
            return None
        return self._single(self.contracts)

    @property
    def obligation_id(self) -> UUID | None:
        if (
            self.grain is not JournalRunGrain.LEGACY_CONTRACT_POB
            or self.account_role not in REVENUE_ROLES
        ):
            return None
        return self._single(self.obligations)

    @property
    def legacy_key(self) -> str | None:
        if self.grain is not JournalRunGrain.LEGACY_CONTRACT_POB:
            return None
        return self._single(self.legacy_keys)

    @property
    def counterparty_entity_id(self) -> UUID | None:
        return self._single(self.counterparties)

    @property
    def origin_period_id(self) -> UUID | None:
        return self._single(self.origin_periods)

    def order_key(self) -> tuple[str, ...]:
        """S14-R-20: entry kind, GL account code, dimension set, counterparty, origin period,
        contract, legacy key."""
        return (
            _text(self.entry_kind),
            self.gl_account_code,
            dimension_set_sha256(self.dimensions),
            _text(self.counterparty_entity_id),
            _text(self.origin_period_id),
            _text(self.contract_id),
            _text(self.legacy_key),
        )


def summarise(
    lines: Iterable[DetailLine], *, grain: JournalRunGrain, dimension_codes: frozenset[str]
) -> tuple[list[SummaryLine], list[frozenset[str]]]:
    """Net the lines per grouping key; the kept lines in S14-R-20 order, and the entry kinds of
    every group (kept or dropped) that link kinds into one entry (L6-3-Q-3)."""
    groups: dict[tuple[str, ...], SummaryLine] = {}
    # Primary-book lines first, then the LEGACY lines of a DELTA run, as before the sign flip.
    for line in sorted(
        lines,
        key=lambda item: (item.book_code == BookCode.LEGACY.value, item.chain_seq, str(item.id)),
    ):
        key = grouping_key(line, grain, dimension_codes)
        found = groups.get(key)
        if found is None:
            dimensions = (
                {}
                if grain is JournalRunGrain.LEGACY_CONTRACT_POB
                else reporting_dimensions(line, dimension_codes)
            )
            found = SummaryLine(
                key=key,
                sha256=grouping_sha256(key),
                grain=grain,
                account_role=line.account_role,
                gl_account_id=line.gl_account_id,
                gl_account_code=line.gl_account_code,
                dimensions=dimensions,
                txn_currency=line.txn_currency,
                functional_currency=line.functional_currency,
            )
            groups[key] = found
        found.net_txn += line.sign * line.amount_txn
        found.net_functional += line.sign * line.amount_functional
        for values, value in (
            (found.contracts, line.contract_id),
            (found.obligations, line.obligation_id),
            (found.counterparties, line.counterparty_entity_id),
            (found.origin_periods, line.origin_period_id),
            (found.fx_rate_set_version_ids, line.fx_rate_set_version_id),
            (found.fx_rate_ids, line.fx_rate_id),
            (found.event_ids, line.contract_event_id),
        ):
            if value is not None:
                values.add(value)
        if line.legacy_key is not None:
            found.legacy_keys.add(line.legacy_key)
        if line.manual_adjustment_id is not None:
            found.manual_adjustment_ids.add(line.manual_adjustment_id)
        found.entry_kinds.add(line.entry_kind)
        found.posting_kinds.add(line.posting_kind)
        found.line_ids.append(line.id)
        found.post_close = (
            found.post_close or line.origin_period_id is not None or line.is_post_reopen
        )
    links = [frozenset(item.entry_kinds) for item in groups.values()]
    kept = [item for item in groups.values() if item.net_txn != 0 or item.net_functional != 0]
    return sorted(kept, key=SummaryLine.order_key), links


@dataclass(slots=True)
class EntryPlan:
    """One journal entry of a batch: the lines of a group of linked entry kinds (S14-R-19)."""

    kinds: frozenset[str]
    lines: list[SummaryLine]

    @property
    def entry_kind(self) -> str | None:
        return next(iter(self.kinds)) if len(self.kinds) == 1 else None

    @property
    def manual_adjustment_id(self) -> UUID | None:
        """T-SL-08 ``manual_adjustment_id``: the one adjustment of a ``manual`` entry's lines."""
        if self.entry_kind != MANUAL_KIND:
            return None
        found = {line.manual_adjustment_id for line in self.lines}
        return next(iter(found)) if len(found) == 1 else None

    @property
    def je_type(self) -> JeType:
        if self.entry_kind == MANUAL_KIND:
            return JeType.MANUAL
        postings = {kind for line in self.lines for kind in line.posting_kinds}
        if postings == {SubledgerPostingKind.VOID_REVERSAL.value}:
            return JeType.REVERSAL
        return JeType.AUTOMATED

    @property
    def is_post_close(self) -> bool:
        return any(line.post_close for line in self.lines)

    @property
    def event_ids(self) -> list[UUID]:
        return sorted({value for line in self.lines for value in line.event_ids}, key=str)


def plan_entries(lines: Sequence[SummaryLine], links: Iterable[frozenset[str]]) -> list[EntryPlan]:
    """Union the entry kinds that share a group; one entry per union holding a kept line, in the
    order of its first line. ``MANUAL_ADJUSTMENT`` shares a group with no other kind
    (``grouping_key``) and has one entry per adjustment (S14-R-19 rev 1.63)."""
    parent: dict[str, str] = {}

    def root(kind: str) -> str:
        parent.setdefault(kind, kind)
        while parent[kind] != kind:
            parent[kind] = parent[parent[kind]]
            kind = parent[kind]
        return kind

    for kinds in links:
        ordered = sorted(kinds)
        for other in ordered[1:]:
            first, second = root(ordered[0]), root(other)
            if first != second:
                parent[max(first, second)] = min(first, second)
    plans: dict[tuple[str, UUID | None], EntryPlan] = {}
    members: dict[str, set[str]] = {}
    for kinds in links:
        for kind in kinds:
            members.setdefault(root(kind), set()).add(kind)
    for line in lines:
        group = root(sorted(line.entry_kinds)[0])
        adjustment = line.manual_adjustment_id if line.entry_kinds == {MANUAL_KIND} else None
        plan = plans.get((group, adjustment))
        if plan is None:
            plan = EntryPlan(kinds=frozenset(members.get(group, line.entry_kinds)), lines=[])
            plans[(group, adjustment)] = plan
        plan.lines.append(line)
    return list(plans.values())


def plan_batches(
    lines: Sequence[DetailLine], *, grain: JournalRunGrain, dimension_codes: frozenset[str]
) -> list[tuple[str, list[SummaryLine], list[EntryPlan]]]:
    """S14-R-21: one batch per transaction currency, in currency order, each with its summarised
    lines and entries; a currency whose lines all net to 0 gives no batch."""
    batches: list[tuple[str, list[SummaryLine], list[EntryPlan]]] = []
    for currency in sorted({line.txn_currency for line in lines}):
        summary, links = summarise(
            (line for line in lines if line.txn_currency == currency),
            grain=grain,
            dimension_codes=dimension_codes,
        )
        if summary:
            batches.append((currency, summary, plan_entries(summary, links)))
    return batches


# --- the run's general ledger and its chunks (S14-R-21; 05 ADP-11; BUILD_SPEC CLO-15) -----------

# T-INT-01 ``adapter`` of a connection that takes journals → the E-37 literal of its batches.
GL_CONNECTION_ADAPTERS: Final[Mapping[str, GlAdapter]] = {
    "NETSUITE": GlAdapter.NETSUITE,
    "QUICKBOOKS_ONLINE": GlAdapter.QUICKBOOKS_ONLINE,
    "CSV_GL": GlAdapter.CSV,
}
OUTBOUND_DIRECTIONS: Final = ("OUTBOUND", "BOTH")
ACTIVE_CONNECTION: Final = "ACTIVE"
MIN_CHUNK_LINES: Final = 2  # a balanced entry has at least two lines
RULE_BATCH: Final = "T-SL-07"
RULE_CHUNK: Final = "S14-R-21"
SEVERAL_CONNECTIONS: Final = (
    "{entity} has more than one active general ledger connection ({codes}). Disable all but one "
    "before calculating journals."
)
CHUNK_SIZE_INVALID: Final = (
    "Connection {code} sets max_lines_per_chunk to {value}; it must be a whole number of at "
    "least 2."
)
ENTRY_TOO_LARGE: Final = (
    "A journal entry of {lines} lines cannot be split into chunks of at most {limit} lines: "
    "{reason}."
)


@dataclass(frozen=True, slots=True)
class GlTarget:
    """Where a run's batches go: the E-37 adapter, its connection and the lines one chunk may
    hold (None = no limit)."""

    adapter: GlAdapter = GlAdapter.CSV
    connection_id: UUID | None = None
    max_lines: int | None = None


class ChunkingRefused(ValueError):
    """An entry that no chunk of the limit can hold (S14-R-21): the part of one contract alone has
    ``part`` lines (``contract_id`` names it), or — ``part`` 0 — the entry's lines do not balance
    contract by contract. ``message`` takes the contract's external id when the caller knows it."""

    def __init__(
        self, *, lines: int, limit: int, contract_id: UUID | None = None, part: int = 0
    ) -> None:
        self.lines, self.limit, self.contract_id, self.part = lines, limit, contract_id, part
        super().__init__(self.message())

    def message(self, label: str | None = None) -> str:
        if self.part:
            name = label or self.contract_id
            reason = f"the part of contract {name} alone has {self.part} lines"
        else:
            reason = "its lines do not balance contract by contract"
        return ENTRY_TOO_LARGE.format(lines=self.lines, limit=self.limit, reason=reason)


def _refused(field_name: str, rule_id: str, message: str) -> Problem:
    error = ProblemError(field=field_name, rule_id=rule_id, message=message)
    return Problem("validation-failed", message, errors=[error])


def gl_target(session: Session, *, entity_id: UUID, entity_code: str, sandbox: bool) -> GlTarget:
    """The general ledger of a run of ``entity_id`` (module docstring)."""
    if sandbox:
        return GlTarget()
    found = session.execute(
        select(
            integration_connection.c.id,
            integration_connection.c.code,
            integration_connection.c.adapter,
            integration_connection.c.config,
        )
        .where(
            integration_connection.c.status == ACTIVE_CONNECTION,
            integration_connection.c.adapter.in_(sorted(GL_CONNECTION_ADAPTERS)),
            integration_connection.c.direction.in_(OUTBOUND_DIRECTIONS),
            or_(
                func.cardinality(integration_connection.c.entity_ids) == 0,
                any_(integration_connection.c.entity_ids) == entity_id,
            ),
        )
        .order_by(integration_connection.c.code)
    ).all()
    if not found:
        return GlTarget()
    if len(found) > 1:
        codes = ", ".join(str(row.code) for row in found)
        raise _refused(
            "entity_code", RULE_BATCH, SEVERAL_CONNECTIONS.format(entity=entity_code, codes=codes)
        )
    (row,) = found
    adapter = GL_CONNECTION_ADAPTERS[str(row.adapter)]
    limit = dict(row.config or {}).get(ports.MAX_LINES_KEY, ports.DEFAULT_MAX_LINES[adapter])
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < MIN_CHUNK_LINES
    ):
        raise _refused(
            "entity_code", RULE_CHUNK, CHUNK_SIZE_INVALID.format(code=row.code, value=limit)
        )
    return GlTarget(adapter=adapter, connection_id=UUID(str(row.id)), max_lines=limit)


def _balances(lines: Sequence[SummaryLine]) -> bool:
    return sum((line.net_txn for line in lines), ZERO) == 0 and (
        sum((line.net_functional for line in lines), ZERO) == 0
    )


def split_entry(
    plan: EntryPlan,
    limit: int,
    *,
    details: Mapping[UUID, DetailLine],
    dimension_codes: frozenset[str],
) -> list[EntryPlan]:
    """S14-R-21: an entry larger than ``limit``, summarised again at the
    ``CONTRACT_ACCOUNT_DIMENSIONS`` grain (``SPLIT_GRAIN``) and split by contract — one entry per
    contract, in the order of its first line, each balancing in transaction and functional
    currency. Its journal lines carry the grouping hash of that grain: a reader of the hash asks
    ``lines_of_group``."""
    lines, _ = summarise(
        (details[line_id] for line in plan.lines for line_id in line.line_ids),
        grain=SPLIT_GRAIN,
        dimension_codes=dimension_codes,
    )
    parts: dict[UUID | None, list[SummaryLine]] = {}
    for line in lines:
        parts.setdefault(line.contract_id, []).append(line)
    total = len(plan.lines)
    for contract_id, part in parts.items():
        if not _balances(part):
            raise ChunkingRefused(lines=total, limit=limit)
        if len(part) > limit:
            raise ChunkingRefused(lines=total, limit=limit, contract_id=contract_id, part=len(part))
    return [EntryPlan(kinds=plan.kinds, lines=part) for part in parts.values()]


def chunk_entries(
    plans: Sequence[EntryPlan],
    limit: int | None,
    *,
    details: Mapping[UUID, DetailLine],
    dimension_codes: frozenset[str],
) -> list[list[EntryPlan]]:
    """S14-R-21 / ADP-11: the entries of one batch in chunks of at most ``limit`` lines. Whole
    entries in their order until the limit would be exceeded — an entry is never split across
    chunks, so every chunk balances; an entry larger than the limit is split by contract first
    (``split_entry``). Without a limit: one chunk."""
    if limit is None:
        return [list(plans)] if plans else []
    entries: list[EntryPlan] = []
    for plan in plans:
        if len(plan.lines) <= limit:
            entries.append(plan)
        else:
            entries.extend(
                split_entry(plan, limit, details=details, dimension_codes=dimension_codes)
            )
    chunks: list[list[EntryPlan]] = []
    current: list[EntryPlan] = []
    count = 0
    for plan in entries:
        size = len(plan.lines)
        if current and count + size > limit:
            chunks.append(current)
            current, count = [], 0
        current.append(plan)
        count += size
    if current:
        chunks.append(current)
    return chunks


# --- S14-R-24 currency conversion residue --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConvertedBatch:
    """The summarised lines converted to a batch currency, with at most one ROUNDING line."""

    currency: str
    lines: tuple[tuple[Decimal, Decimal], ...]  # (debit, credit) per line, in input order
    rounding: tuple[Decimal, Decimal] | None  # (debit, credit) of the ROUNDING line


def convert_batch(
    lines: Sequence[tuple[Decimal, Decimal]], *, rate: Decimal, currency: str, minor_unit: int
) -> ConvertedBatch:
    """S14-R-24 (D-16): each line converted at ``rate`` with ``round_half_up`` to the currency's
    minor unit; Σ converted debits − Σ converted credits posts as one ROUNDING line that balances
    the batch, and no line when the difference is 0."""
    quantum = Decimal(1).scaleb(-minor_unit)
    converted = tuple(
        (
            (debit * rate).quantize(quantum, rounding=ROUND_HALF_UP),
            (credit * rate).quantize(quantum, rounding=ROUND_HALF_UP),
        )
        for debit, credit in lines
    )
    residue = sum((debit for debit, _ in converted), ZERO) - sum(
        (credit for _, credit in converted), ZERO
    )
    if residue == 0:
        return ConvertedBatch(currency=currency, lines=converted, rounding=None)
    rounding = (ZERO, residue) if residue > 0 else (-residue, ZERO)
    return ConvertedBatch(currency=currency, lines=converted, rounding=rounding)


# --- reads ---------------------------------------------------------------------------------------

DETAIL_COLUMNS: Final = (
    subledger_line.c.id,
    subledger_line.c.book_code,
    subledger_posting_seal.c.chain_seq,
    subledger_posting.c.posting_kind,
    subledger_line.c.entry_kind,
    subledger_line.c.account_role,
    subledger_line.c.gl_account_id,
    gl_account.c.code.label("gl_account_code"),
    subledger_line.c.dimensions,
    subledger_line.c.txn_currency,
    subledger_line.c.amount_txn,
    subledger_line.c.functional_currency,
    subledger_line.c.amount_functional,
    subledger_line.c.contract_id,
    subledger_line.c.obligation_id,
    subledger_line.c.legacy_key,
    subledger_line.c.counterparty_entity_id,
    subledger_line.c.origin_period_id,
    subledger_line.c.is_post_reopen,
    subledger_line.c.contract_event_id,
    subledger_line.c.fx_rate_set_version_id,
    subledger_line.c.fx_rate_id,
    subledger_posting.c.manual_adjustment_id,
)


def detail_statement(
    *, entity_id: UUID, book_code: str, period_id: UUID, from_seq: int, to_seq: int
) -> Select[Any]:
    """The sealed lines of (entity, book, period) with ``chain_seq`` in (from_seq, to_seq]."""
    tenant_id = subledger_line.c.tenant_id
    joined = (
        subledger_line.join(
            subledger_posting,
            and_(
                subledger_posting.c.tenant_id == tenant_id,
                subledger_posting.c.id == subledger_line.c.subledger_posting_id,
            ),
        )
        .join(
            subledger_posting_seal,
            and_(
                subledger_posting_seal.c.tenant_id == tenant_id,
                subledger_posting_seal.c.subledger_posting_id
                == subledger_line.c.subledger_posting_id,
            ),
        )
        .join(
            gl_account,
            and_(
                gl_account.c.tenant_id == tenant_id,
                gl_account.c.id == subledger_line.c.gl_account_id,
            ),
        )
    )
    return (
        select(*DETAIL_COLUMNS)
        .select_from(joined)
        .where(
            subledger_line.c.entity_id == entity_id,
            subledger_line.c.book_code == book_code,
            subledger_line.c.period_id == period_id,
            subledger_posting_seal.c.chain_seq > from_seq,
            subledger_posting_seal.c.chain_seq <= to_seq,
        )
    )


def among(column: ColumnElement[Any], ids: Sequence[UUID]) -> ColumnElement[bool]:
    """``column`` is one of ``ids``, bound as ONE value — an array — whatever their number.

    A list bound one value an id (``column.in_(ids)``) ends at the 65,535 bound values a
    PostgreSQL statement can carry. Five lists of this package have no such bound: the lines
    one journal line summarizes (``queries.drill_statement``) and the lines one run takes over
    (``left_out_statement``); the contracts of a run's range (``open_holds``, on the
    calculation's path); the chunks of a page of runs (``queries.batch_outs``); the contracts
    and the obligations of a failed generation's findings (``validation.names_of``). Past the
    bound the driver refused the statement and the kernel read an unavailable server: the drill
    of a journal line of 66,000 source lines answered 503 (measured through the product on
    2026-10-02)."""
    return column == any_(literal(list(ids), ARRAY(Uuid())))


def left_out_statement(
    *, entity_id: UUID, book_codes: Sequence[str], period_id: UUID, line_ids: Sequence[UUID]
) -> Select[Any]:
    """The sealed lines of (entity, period) in ``book_codes`` among ``line_ids``: the lines a run
    takes over are named by id, not by a range (``detail_statement`` reads a range)."""
    tenant_id = subledger_line.c.tenant_id
    joined = (
        subledger_line.join(
            subledger_posting,
            and_(
                subledger_posting.c.tenant_id == tenant_id,
                subledger_posting.c.id == subledger_line.c.subledger_posting_id,
            ),
        )
        .join(
            subledger_posting_seal,
            and_(
                subledger_posting_seal.c.tenant_id == tenant_id,
                subledger_posting_seal.c.subledger_posting_id
                == subledger_line.c.subledger_posting_id,
            ),
        )
        .join(
            gl_account,
            and_(
                gl_account.c.tenant_id == tenant_id,
                gl_account.c.id == subledger_line.c.gl_account_id,
            ),
        )
    )
    return (
        select(*DETAIL_COLUMNS)
        .select_from(joined)
        .where(
            subledger_line.c.entity_id == entity_id,
            subledger_line.c.book_code.in_(list(book_codes)),
            subledger_line.c.period_id == period_id,
            among(subledger_line.c.id, line_ids),
        )
        .order_by(subledger_posting_seal.c.chain_seq, subledger_line.c.id)
    )


def detail_lines(session: Session, statement: Select[Any], *, sign: int = 1) -> list[DetailLine]:
    """``DetailLine`` of each row of ``detail_statement``."""
    return [
        DetailLine(
            id=UUID(str(row["id"])),
            book_code=str(row["book_code"]),
            sign=sign,
            chain_seq=int(row["chain_seq"]),
            posting_kind=str(row["posting_kind"]),
            entry_kind=str(row["entry_kind"]),
            account_role=str(row["account_role"]),
            gl_account_id=UUID(str(row["gl_account_id"])),
            gl_account_code=str(row["gl_account_code"]),
            dimensions={str(key): str(value) for key, value in (row["dimensions"] or {}).items()},
            txn_currency=str(row["txn_currency"]).strip(),
            amount_txn=Decimal(row["amount_txn"]),
            functional_currency=str(row["functional_currency"]).strip(),
            amount_functional=Decimal(row["amount_functional"]),
            contract_id=row["contract_id"],
            obligation_id=row["obligation_id"],
            legacy_key=row["legacy_key"],
            counterparty_entity_id=row["counterparty_entity_id"],
            origin_period_id=row["origin_period_id"],
            is_post_reopen=bool(row["is_post_reopen"]),
            contract_event_id=row["contract_event_id"],
            fx_rate_set_version_id=row["fx_rate_set_version_id"],
            fx_rate_id=row["fx_rate_id"],
            manual_adjustment_id=row["manual_adjustment_id"],
        )
        for row in session.execute(statement).mappings()
    ]


def dimension_codes(session: Session) -> frozenset[str]:
    """The workspace's active stored-value dimension codes (L6-3-Q-2)."""
    codes = session.execute(
        select(dimension_definition.c.code).where(dimension_definition.c.is_active.is_(True))
    ).scalars()
    return frozenset(str(code) for code in codes) - UNSTORED_VALUE_DIMENSIONS


def open_holds(session: Session, contract_ids: Iterable[UUID]) -> dict[UUID, UUID]:
    """Contract id → id of its open ``journal_export`` hold (S14-R-17; T-CON-20)."""
    ids = sorted(set(contract_ids), key=str)
    if not ids:
        return {}
    rows = session.execute(
        select(contract_hold.c.contract_id, contract_hold.c.id)
        .where(
            contract_hold.c.hold_type == HOLD_JOURNAL_EXPORT,
            contract_hold.c.released_at.is_(None),
            among(contract_hold.c.contract_id, ids),
        )
        .order_by(contract_hold.c.applied_at)
    ).tuples()
    held: dict[UUID, UUID] = {}
    for contract_id, hold_id in rows:
        held.setdefault(UUID(str(contract_id)), UUID(str(hold_id)))
    return held


def covered_to(session: Session, *, book_code: str, from_seq: int, cutoff: datetime) -> int:
    """The greatest ``chain_seq`` of the book sealed by ``cutoff``, at least ``from_seq``."""
    found = session.execute(
        select(func.max(subledger_posting_seal.c.chain_seq)).where(
            subledger_posting_seal.c.book_code == book_code,
            subledger_posting_seal.c.sealed_at <= cutoff,
        )
    ).scalar_one_or_none()
    return max(from_seq, 0 if found is None else int(found))


def lock_coverage(
    session: Session, *, tenant_id: UUID, entity_id: UUID, book_code: str, period_id: UUID
) -> None:
    """One writer of a key's coverage at a time (DB-16): the calculation, which reads where the
    non-cancelled runs of the entity, book and period end, and the cancellation, which takes a run
    out of them (``commands.cancel_run``; ruling R-52 (b)), hold this transaction advisory lock
    before they read, so neither decides on runs the other is changing."""
    key = f"erev.journal_coverage:{tenant_id}:{entity_id}:{book_code}:{period_id}"
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


# PRD ERR-86 (04 §14.1 DB-07 and §16.7 rev 1.205; item JR-CLOSED-PERIOD-GUARD-1; supervisor ruling
# R-97 (7)): a journal run is neither calculated nor cancelled in a closed period.
RULE_PERIOD_CLOSED: Final = "RUN_PERIOD_CLOSED"
CLOSED_STATES: Final = frozenset(member.value for member in periods.CLOSED_STATES)
RUN_PERIOD_CLOSED: Final = "{period} is closed for {entity} in book {book}. {consequence}"
NOT_CALCULATED: Final = "A journal run cannot be calculated for a closed period."
NOT_CANCELLED: Final = "A journal run of a closed period cannot be cancelled."


def hold_period(
    session: Session, *, entity_id: UUID, book_code: str, period_id: UUID
) -> str | None:
    """The state of the period for the entity and book, its ``period_state`` row read ``FOR
    SHARE`` and held to the end of the transaction; None when the caller sees no such row.

    Every writer of a journal run takes it before it decides (04 §14.1 "DB-07 row lock and lock
    order" rev 1.205; dev-guide DG-KRN-DB-08 rev 1.188): the calculation directly after the key's
    coverage lock, the cancel after the run row, the batch rows and the coverage lock. A change
    of the period's state takes the same row ``FOR UPDATE`` as its first read and takes no journal
    row, so the lock decision waits for a calculation or a cancel in flight and then counts that
    run, and one that arrives while the lock is decided waits here and reads ``closed``. The
    DB-07 guard ``tg_journal_run__period_guard`` takes the row again at the run's insert and at
    its move to ``cancelled``; this read comes first so that the refusal has a name."""
    found = session.execute(
        select(period_state.c.state)
        .where(
            period_state.c.entity_id == entity_id,
            period_state.c.book_code == book_code,
            period_state.c.period_id == period_id,
        )
        .with_for_update(read=True)
    ).scalar_one_or_none()
    return None if found is None else str(getattr(found, "value", found))


def period_closed(
    session: Session,
    *,
    entity_id: UUID,
    book_code: str,
    period_id: UUID,
    consequence: str,
    field: str | None = None,
) -> Problem:
    """409 ``period-closed`` under rule ``RUN_PERIOD_CLOSED`` (PRD ERR-86): the period by its
    name, the entity by its code, and what is not done — ``NOT_CALCULATED`` or
    ``NOT_CANCELLED``."""
    names = session.execute(
        select(period.c.name, legal_entity.c.code)
        .select_from(period.join(legal_entity, legal_entity.c.tenant_id == period.c.tenant_id))
        .where(period.c.id == period_id, legal_entity.c.id == entity_id)
    ).one()
    detail = RUN_PERIOD_CLOSED.format(
        period=names[0], entity=names[1], book=book_code, consequence=consequence
    )
    error = ProblemError(field=field, rule_id=RULE_PERIOD_CLOSED, message=detail)
    return Problem("period-closed", detail, errors=[error])


def refuse_closed_period(
    session: Session,
    *,
    entity_id: UUID,
    book_code: str,
    period_id: UUID,
    consequence: str,
    field: str | None = None,
) -> Problem | None:
    """``hold_period``, and the refusal of PRD ERR-86 when the period is ``closed`` or
    ``permanently_locked``; None for any other state — a ``future`` period refuses nothing — and
    for a period without a visible state row."""
    state = hold_period(session, entity_id=entity_id, book_code=book_code, period_id=period_id)
    if state not in CLOSED_STATES:
        return None
    return period_closed(
        session,
        entity_id=entity_id,
        book_code=book_code,
        period_id=period_id,
        consequence=consequence,
        field=field,
    )


# PRD ERR-96 (04 §16.7 API-S-JournalRunCreate rev 1.248; item JRN-EMPTY-RUN-1): where a run of the
# entity, book and period that is not cancelled stands, no further run is made without a line.
# The sentence says what holds in every such case and claims no coverage: a posting a run left
# out under a journal-export hold, or one that is under such a hold now, is not journalised and
# is not reached by a new run either (04 §16.7 lists the cases and the operator's way in each).
RULE_NOTHING_PENDING: Final = "RUN_NOTHING_PENDING"
NOTHING_PENDING: Final = (
    "Journal run {run} is the latest run of {period} for {entity} in book {book}, and there is "
    "nothing for a new run to summarize."
)


@dataclass(frozen=True, slots=True)
class Detail:
    """What a run of an entity, book and period calculated now would read (DB-16; S14-R-16,
    S14-R-17, S14-R-23): the range of sealed postings beyond what the key's runs cover — the
    book's, and for a ``DELTA`` run the LEGACY book's — through the cutoff, and their detail lines,
    those of a contract under an open ``journal_export`` hold apart (``held``, each with its
    hold); and the lines it takes over (``taken``, each with the run that left it out; S14-R-17
    rev 1.164). ``kept`` is what it summarizes: the lines of the range that are not held, then
    the lines taken over."""

    from_seq: int
    to_seq: int
    delta_from: int
    delta_to: int | None
    kept: list[DetailLine]
    held: list[tuple[DetailLine, UUID]]
    taken: list[tuple[DetailLine, UUID]] = field(default_factory=list)


def read_detail(
    session: Session,
    *,
    entity_id: UUID,
    book_code: str,
    period_id: UUID,
    mode: JournalRunMode,
    cutoff: datetime,
    files: FileStore | None = None,
    keyring: KeyRing | None = None,
) -> Detail:
    """``Detail`` of the key for a run of ``mode`` at ``cutoff``: what the calculation summarizes
    under the key's coverage lock, and what ``POST /journal-runs`` reads on a plain read to say
    whether a run would hold a line.

    The lines taken over are those ``completeness.left_out_of`` names for the key — left out as
    held by a run that is not cancelled and taken over by none — of the books this mode reads
    (the LEGACY book's for a ``DELTA`` run alone) and of a contract under no open hold now. A
    line that is still held stays with the record of the run that left it out: it is in no later
    range, so this run does not list it as held again. ``files`` and ``keyring`` let a run's held
    detail file stand in for a CALCULATE event written before it named the lines."""
    from_seq, delta_from = _covered_from(
        session, entity_id=entity_id, book_code=book_code, period_id=period_id
    )
    to_seq = covered_to(session, book_code=book_code, from_seq=from_seq, cutoff=cutoff)
    lines = detail_lines(
        session,
        detail_statement(
            entity_id=entity_id,
            book_code=book_code,
            period_id=period_id,
            from_seq=from_seq,
            to_seq=to_seq,
        ),
    )
    delta_to: int | None = None
    if mode is JournalRunMode.DELTA:
        delta_to = covered_to(
            session, book_code=BookCode.LEGACY.value, from_seq=delta_from, cutoff=cutoff
        )
        lines += detail_lines(
            session,
            detail_statement(
                entity_id=entity_id,
                book_code=BookCode.LEGACY.value,
                period_id=period_id,
                from_seq=delta_from,
                to_seq=delta_to,
            ),
            sign=1,  # DELTA = primary + LEGACY lines (S14-R-23; D-89 L7-6-Q-8)
        )
    left = completeness.left_out_of(
        session,
        entity_id=entity_id,
        book_code=book_code,
        period_id=period_id,
        files=files,
        keyring=keyring,
    )
    candidates: list[DetailLine] = []
    if left:
        books = [book_code]
        if mode is JournalRunMode.DELTA and book_code != BookCode.LEGACY.value:
            books.append(BookCode.LEGACY.value)
        candidates = detail_lines(
            session,
            left_out_statement(
                entity_id=entity_id, book_codes=books, period_id=period_id, line_ids=sorted(left)
            ),
        )
    holds = open_holds(
        session,
        (line.contract_id for line in [*lines, *candidates] if line.contract_id is not None),
    )
    taken = [(line, left[line.id]) for line in candidates if line.contract_id not in holds]
    kept = [line for line in lines if line.contract_id not in holds]
    return Detail(
        from_seq=from_seq,
        to_seq=to_seq,
        delta_from=delta_from,
        delta_to=delta_to,
        kept=[*kept, *(line for line, _ in taken)],
        held=[(line, holds[line.contract_id]) for line in lines if line.contract_id in holds],
        taken=taken,
    )


def run_wanted(*, live_run: bool, lines: int) -> bool:
    """Whether a journal run calculated now is made (04 §16.7 API-S-JournalRunCreate rev 1.248): it
    would be the first run of its entity, book and period that is not cancelled — made with or
    without lines, because the lock gates need a run — or it would hold a line. A further run
    without a line is not made: it would stand after the run it follows and keep it from being
    cancelled (PRD ERR-96)."""
    return not live_run or lines > 0


def _latest_run(
    session: Session, *, entity_id: UUID, book_code: str, period_id: UUID
) -> str | None:
    """The number of the latest run of the key that is not cancelled, else None."""
    found = session.execute(
        select(journal_run.c.run_no)
        .where(
            journal_run.c.entity_id == entity_id,
            journal_run.c.book_code == book_code,
            journal_run.c.period_id == period_id,
            journal_run.c.state != JournalState.CANCELLED.value,
        )
        .order_by(
            journal_run.c.created_at.desc(),
            func.length(journal_run.c.run_no).desc(),
            journal_run.c.run_no.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    return None if found is None else str(found)


def nothing_pending(
    session: Session,
    *,
    entity_id: UUID,
    book_code: str,
    period_id: UUID,
    mode: JournalRunMode | None = None,
    cutoff: datetime | None = None,
    found: Detail | None = None,
    files: FileStore | None = None,
    keyring: KeyRing | None = None,
) -> Problem | None:
    """The refusal of PRD ERR-96 — 409 ``invalid-transition`` under rule ``RUN_NOTHING_PENDING``,
    naming the latest run of the entity, book and period that is not cancelled — when a run
    calculated now is not wanted (``run_wanted``); None when it would be the key's first run or
    would hold a line.

    The lines are those the run itself would read (``read_detail``): of its mode — a ``DELTA``
    run beside ``GROSS`` runs holds the LEGACY book's lines, which no predicate over the book's
    own postings sees — through its cutoff, a held contract's left out. ``POST /journal-runs``
    asks on a plain read, with ``mode`` and ``cutoff``, and reads the lines only where a run
    stands; the calculation asks again under the key's coverage lock with the ``found`` it read,
    so two commands accepted at once end in one run. Until rev 1.248 the second made a
    ``draft`` run without lines.

    The refusal is not a statement that the period is journalised — ``JE_COMPLETE`` says that
    (``completeness``). It is met in four cases: every posting is journalised; the postings
    beyond the runs are all under a journal-export hold now (released, they make the next run);
    a run left postings out under such a hold that is still open (released, the next run takes
    them over — rev 1.267; until then no later run reached them); and a cutoff before the
    postings beyond the runs."""
    latest = _latest_run(session, entity_id=entity_id, book_code=book_code, period_id=period_id)
    if latest is None:
        return None
    if found is None:
        assert mode is not None and cutoff is not None
        found = read_detail(
            session,
            entity_id=entity_id,
            book_code=book_code,
            period_id=period_id,
            mode=mode,
            cutoff=cutoff,
            files=files,
            keyring=keyring,
        )
    if run_wanted(live_run=True, lines=len(found.kept)):
        return None
    names = session.execute(
        select(period.c.name, legal_entity.c.code)
        .select_from(period.join(legal_entity, legal_entity.c.tenant_id == period.c.tenant_id))
        .where(period.c.id == period_id, legal_entity.c.id == entity_id)
    ).one()
    detail = NOTHING_PENDING.format(run=latest, period=names[0], entity=names[1], book=book_code)
    error = ProblemError(rule_id=RULE_NOTHING_PENDING, message=detail)
    return Problem("invalid-transition", detail, errors=[error])


def _covered_from(
    session: Session, *, entity_id: UUID, book_code: str, period_id: UUID
) -> tuple[int, int]:
    """(from_chain_seq, delta_from_chain_seq) after the non-cancelled runs of the key (DB-16).

    The key is (entity, book, period): the runs of EVERY mode count (04 DB-16 rev 1.106; supervisor
    ruling R-32 on security finding SC-7). A ``DELTA`` run outputs the primary-book lines a
    ``GROSS`` run outputs, so a run of either mode starts where the key's runs end; the LEGACY
    range starts where the LEGACY ranges of the key's ``DELTA`` runs end (a ``GROSS`` run states
    none). ``tg_journal_run__coverage`` refuses any other start with ``EREV-JR-001``."""
    row = session.execute(
        select(
            func.coalesce(func.max(journal_run.c.to_chain_seq), 0),
            func.coalesce(func.max(journal_run.c.delta_to_chain_seq), 0),
        ).where(
            journal_run.c.entity_id == entity_id,
            journal_run.c.book_code == book_code,
            journal_run.c.period_id == period_id,
            journal_run.c.state != JournalState.CANCELLED.value,
        )
    ).one()
    return int(row[0]), int(row[1])


def _release_id(session: Session) -> UUID:
    """The process's own release row (05 REL-03 consumers, rev 1.15; ``controls.stamping``): the
    latest row of the running engine version is only the dev / test fallback (D-98 60)."""

    def latest_for_version() -> UUID | None:
        found = session.execute(
            select(engine_release.c.id)
            .where(engine_release.c.engine_version == ENGINE_VERSION)
            .order_by(engine_release.c.deployed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return None if found is None else UUID(str(found))

    return process_release_id(
        current_release(),
        env=current_environment(),
        engine_version=ENGINE_VERSION,
        latest_for_version=latest_for_version,
    )


# --- the handler ---------------------------------------------------------------------------------


def _detail_file(
    uow: UnitOfWork,
    *,
    external_id: str,
    run_no: str,
    lines: Sequence[tuple[int, str, SummaryLine]],
    held: Sequence[tuple[DetailLine, UUID]],
) -> tuple[UUID, str]:
    """The retained detail file of a batch (REQ-JE-010): the contributing lines of each journal
    line, and the lines held back by ``journal_export`` holds (S14-R-17)."""
    document = {
        "external_id": external_id,
        "run_no": run_no,
        "lines": [
            {
                "line_no": line_no,
                "je_no": je_no,
                "source_grouping_sha256": item.sha256,
                "subledger_line_ids": [str(value) for value in item.line_ids],
            }
            for line_no, je_no, item in lines
        ],
        "held": _held_entries(held),
    }
    return _stored_json(uow, document, filename=f"{external_id.replace(':', '_')}-detail.json")


def _held_entries(held: Sequence[tuple[DetailLine, UUID]]) -> list[dict[str, str]]:
    return [
        {
            "subledger_line_id": str(line.id),
            "contract_id": str(line.contract_id),
            "hold_id": str(hold_id),
            "book_code": line.book_code,
            "txn_currency": line.txn_currency,
            "amount_txn": format(line.sign * line.amount_txn, "f"),
            "amount_functional": format(line.sign * line.amount_functional, "f"),
        }
        for line, hold_id in held
    ]


def _held_detail_file(
    uow: UnitOfWork, *, external_id: str, run_no: str, held: Sequence[tuple[DetailLine, UUID]]
) -> tuple[UUID, str]:
    """The run-level retained detail of every held line, whatever its currency (S14-R-17; Codex
    production-20260921-0920 §3): a wholly held run, or a currency whose kept groups all net to
    zero, has no batch and so no batch detail file to list its held lines — this file lists them
    by id, and the run's CALCULATE audit event carries its id and SHA-256. No journal entry is
    invented for them."""
    document = {"external_id": external_id, "run_no": run_no, "held": _held_entries(held)}
    return _stored_json(uow, document, filename=f"{external_id.replace(':', '_')}-held.json")


def _taken_over_detail_file(
    uow: UnitOfWork,
    *,
    external_id: str,
    run_no: str,
    taken: Sequence[tuple[DetailLine, UUID]],
) -> tuple[UUID, str]:
    """The run-level retained detail of every line the run took over (S14-R-17 rev 1.164): the
    line, its contract and the run that had left it out, by id and by number. The CALCULATE audit
    event carries the file's id and SHA-256 beside the ids themselves."""
    run_ids = sorted({run_id for _, run_id in taken}, key=str)
    numbers = {
        UUID(str(row[0])): str(row[1])
        for row in uow.session.execute(
            select(journal_run.c.id, journal_run.c.run_no).where(journal_run.c.id.in_(run_ids))
        )
    }
    document = {
        "external_id": external_id,
        "run_no": run_no,
        "taken_over": [
            {
                "subledger_line_id": str(line.id),
                "contract_id": str(line.contract_id),
                "left_out_by_run_id": str(run_id),
                "left_out_by_run_no": numbers[run_id],
                "book_code": line.book_code,
                "txn_currency": line.txn_currency,
                "amount_txn": format(line.sign * line.amount_txn, "f"),
                "amount_functional": format(line.sign * line.amount_functional, "f"),
            }
            for line, run_id in taken
        ],
    }
    return _stored_json(uow, document, filename=f"{external_id.replace(':', '_')}-taken-over.json")


def _stored_json(
    uow: UnitOfWork, document: Mapping[str, Any], *, filename: str
) -> tuple[UUID, str]:
    content = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    stored = store_file(
        uow,
        purpose=FilePurpose.JOURNAL_EXPORT,
        stream=io.BytesIO(content),
        original_filename=filename,
        media_type="application/json",
    )
    return UUID(str(stored["id"])), hashlib.sha256(content).hexdigest()


def _stamps(uow: UnitOfWork, *, modified: bool) -> dict[str, Any]:
    principal = uow.principal
    values: dict[str, Any] = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }
    if modified:
        values |= {
            "updated_at": uow.now,
            "updated_by": principal.id,
            "updated_by_kind": principal.kind.value,
        }
    return values


def _description(entity_code: str, period_name: str, kind: str | None) -> str:
    label = "summarised entries" if kind is None else kind.replace("_", " ").lower()
    return f"{entity_code} {period_name} {label}"


def calculate(
    uow: UnitOfWork,
    params: Mapping[str, Any],
    *,
    job_id: UUID | None,
    within_close_run: bool = False,
) -> dict[str, int]:
    """Insert the draft run of ``params`` with its batches, entries and lines (module docstring).

    Where a run of the key that is not cancelled stands and this one would hold no line, no run
    is made (PRD ERR-96; 04 §16.7 rev 1.248): the job of ``POST /journal-runs`` ends with that
    problem, and the step of a close run (``within_close_run``) — which asked its own question
    before it called (``close_runs._journal_pending``) — writes nothing and answers no counts."""
    session = uow.session
    tenant_id = uow.principal.tenant_id
    run_id = UUID(str(params["journal_run_id"]))
    entity_id = UUID(str(params["entity_id"]))
    book_code = str(params["book_code"])
    period_id = UUID(str(params["period_id"]))
    mode = JournalRunMode(str(params["mode"]))
    grain = JournalRunGrain(str(params["grain"]))
    cutoff = datetime.fromisoformat(str(params["cutoff_known_at"]))
    close_run_id = None if params.get("close_run_id") is None else UUID(str(params["close_run_id"]))

    entity = session.execute(
        select(legal_entity.c.code, legal_entity.c.functional_currency).where(
            legal_entity.c.id == entity_id
        )
    ).one()
    entity_code, functional_currency = str(entity[0]), str(entity[1]).strip()
    period_name = str(
        session.execute(select(period.c.name).where(period.c.id == period_id)).scalar_one()
    )
    tenant_code = str(
        session.execute(select(tenant.c.code).where(tenant.c.id == tenant_id)).scalar_one()
    )

    lock_coverage(
        session, tenant_id=tenant_id, entity_id=entity_id, book_code=book_code, period_id=period_id
    )
    # The period's state row, held from here on: directly after the coverage lock and before the
    # key's runs are read and the numbering series taken (DG-KRN-DB-08 rev 1.188). A period the
    # lock decision closed while this job waited takes no run (PRD ERR-86).
    closed = refuse_closed_period(
        session,
        entity_id=entity_id,
        book_code=book_code,
        period_id=period_id,
        consequence=NOT_CALCULATED,
        field="period_key",
    )
    if closed is not None:
        raise closed
    found = read_detail(
        session,
        entity_id=entity_id,
        book_code=book_code,
        period_id=period_id,
        mode=mode,
        cutoff=cutoff,
        files=uow.files,
        keyring=uow.keyring,
    )
    # PRD ERR-96, asked again under the coverage lock on the lines this run would hold: a run
    # calculated since the command was accepted may have summarized them, and this one would
    # then stand after it without a line.
    covered = nothing_pending(
        session, entity_id=entity_id, book_code=book_code, period_id=period_id, found=found
    )
    if covered is not None:
        if within_close_run:
            return {}
        raise covered
    from_seq, to_seq = found.from_seq, found.to_seq
    delta_from, delta_to = found.delta_from, found.delta_to
    held, kept, taken = found.held, found.kept, found.taken
    # CLO-10 (REQ-JE-022): every line the run would write is validated first — account existence,
    # activity and entity, mandatory dimensions, FX rate — and a failing line fails the generation
    # by name before any run, batch, entry or line is written; nothing is dropped.
    findings = validation.validate_lines(
        session, kept, entity_id=entity_id, functional_currency=functional_currency
    )
    if findings:
        raise validation.JournalValidationFailed(findings)
    codes = dimension_codes(session)

    target = gl_target(
        session,
        entity_id=entity_id,
        entity_code=entity_code,
        sandbox=uow.ctx.tenant_kind is TenantKind.SANDBOX,
    )
    by_id = {line.id: line for line in kept}
    try:
        # One batch per transaction currency (its batch_no), in chunks of whole entries.
        batches = [
            (
                currency,
                chunk_entries(plans, target.max_lines, details=by_id, dimension_codes=codes),
            )
            for currency, _, plans in plan_batches(kept, grain=grain, dimension_codes=codes)
        ]
    except ChunkingRefused as refused:
        named = None
        if refused.contract_id is not None:
            named = session.execute(
                select(contract.c.external_id).where(contract.c.id == refused.contract_id)
            ).scalar_one_or_none()
        raise _refused("grain", RULE_CHUNK, refused.message(named)) from refused
    written = [
        line for _, chunks in batches for plans in chunks for plan in plans for line in plan.lines
    ]
    entry_count = sum(len(plans) for _, chunks in batches for plans in chunks)
    je_numbers: list[str] = []
    if entry_count:
        ensure_entity_series(uow, entity_id, entity_code)
        je_numbers = next_numbers(uow, JE_SERIES, entry_count, scope_key=str(entity_id))
    run_no = next_number(uow, RUN_SERIES)
    release_id = _release_id(session) if batches else None
    total_debit = sum((item.debit_functional for item in written), ZERO)
    total_credit = sum((item.credit_functional for item in written), ZERO)
    line_count = len(written)
    session.execute(
        insert(journal_run).values(
            tenant_id=tenant_id,
            id=run_id,
            run_no=run_no,
            entity_id=entity_id,
            book_code=book_code,
            period_id=period_id,
            mode=mode.value,
            delta_book_code=BookCode.LEGACY.value if mode is JournalRunMode.DELTA else None,
            grain=grain.value,
            state=JournalState.DRAFT.value,
            cutoff_known_at=cutoff,
            from_chain_seq=from_seq,
            to_chain_seq=to_seq,
            delta_from_chain_seq=delta_from if mode is JournalRunMode.DELTA else None,
            delta_to_chain_seq=delta_to,
            functional_currency=functional_currency,
            line_count=line_count,
            total_debit_functional=total_debit,
            total_credit_functional=total_credit,
            close_run_id=close_run_id,
            job_id=job_id,
            **_stamps(uow, modified=True),
        )
    )
    entry_ids: list[UUID] = []
    line_ids: list[UUID] = []
    numbers = iter(je_numbers)
    for batch_no, (currency, chunks) in enumerate(batches, start=1):
        batch_held = [(line, hold_id) for line, hold_id in held if line.txn_currency == currency]
        for chunk_no, plans in enumerate(chunks, start=1):
            # the chunk's lines in S14-R-20 order; line_no runs within the chunk
            summary = sorted(
                (line for plan in plans for line in plan.lines), key=SummaryLine.order_key
            )
            batch_id = new_id()
            external_id = f"erev:{tenant_code}:{run_no}:{batch_no}:{chunk_no}"
            entries = [(new_id(), next(numbers), plan) for plan in plans]
            entry_of = {
                id(item): (entry_id, je_no)
                for entry_id, je_no, plan in entries
                for item in plan.lines
            }
            entry_ids += [entry_id for entry_id, _, _ in entries]
            numbered = [
                (line_no, entry_of[id(item)][1], item)
                for line_no, item in enumerate(summary, start=1)
            ]
            # the held lines of the currency are listed once, in the detail file of its first chunk
            file_id, file_sha = _detail_file(
                uow,
                external_id=external_id,
                run_no=run_no,
                lines=numbered,
                held=batch_held if chunk_no == 1 else [],
            )
            session.execute(
                insert(journal_batch).values(
                    tenant_id=tenant_id,
                    id=batch_id,
                    journal_run_id=run_id,
                    batch_no=batch_no,
                    chunk_no=chunk_no,
                    entity_id=entity_id,
                    book_code=book_code,
                    period_id=period_id,
                    txn_currency=currency,
                    functional_currency=functional_currency,
                    state=JournalState.DRAFT.value,
                    line_count=len(summary),
                    total_debit_txn=sum((item.debit_txn for item in summary), ZERO),
                    total_credit_txn=sum((item.credit_txn for item in summary), ZERO),
                    total_debit_functional=sum((item.debit_functional for item in summary), ZERO),
                    total_credit_functional=sum((item.credit_functional for item in summary), ZERO),
                    engine_release_id=release_id,
                    adapter=target.adapter.value,
                    integration_connection_id=target.connection_id,
                    external_id=external_id,
                    detail_file_id=file_id,
                    detail_sha256=file_sha,
                    **_stamps(uow, modified=True),
                )
            )
            # SOP-1 CTL-022: the batch balances per entity, book, currency and period (the DB-16
            # constraint fails closed; a written batch is a PASS over its lines).
            record_execution(
                uow,
                control_id="CTL-022",
                run_ref_type=RunRefType.JOURNAL_BATCH,
                run_ref_id=batch_id,
                population_count=len(summary),
                exception_count=0,
                result=ControlResult.PASS,
                entity_id=entity_id,
                book_code=str(book_code),
                period_id=period_id,
                detail={
                    "txn_currency": currency,
                    "total_debit_functional": str(
                        sum((item.debit_functional for item in summary), ZERO)
                    ),
                    "total_credit_functional": str(
                        sum((item.credit_functional for item in summary), ZERO)
                    ),
                },
            )
            for entry_id, je_no, plan in entries:
                session.execute(
                    insert(journal_entry).values(
                        tenant_id=tenant_id,
                        id=entry_id,
                        journal_batch_id=batch_id,
                        entity_id=entity_id,
                        je_seq=int(je_no.rsplit("-", 1)[1]),
                        je_no=je_no,
                        je_type=plan.je_type.value,
                        entry_kind=plan.entry_kind,
                        description=_description(entity_code, period_name, plan.entry_kind),
                        source_event_ids=plan.event_ids,
                        manual_adjustment_id=plan.manual_adjustment_id,
                        reverses_journal_entry_id=None,
                        is_post_close=plan.is_post_close,
                        **_stamps(uow, modified=False),
                    )
                )
            rows: list[dict[str, Any]] = []
            for line_no, _je_no, item in numbered:
                entry_id = entry_of[id(item)][0]
                line_id = new_id()
                line_ids.append(line_id)
                rows.append(
                    {
                        "tenant_id": tenant_id,
                        "id": line_id,
                        "journal_entry_id": entry_id,
                        "journal_batch_id": batch_id,
                        "line_no": line_no,
                        "entity_id": entity_id,
                        "book_code": book_code,
                        "period_id": period_id,
                        "account_role": item.account_role,
                        "gl_account_id": item.gl_account_id,
                        "gl_account_code": item.gl_account_code,
                        "dimensions": item.dimensions,
                        "dimension_set_sha256": dimension_set_sha256(item.dimensions),
                        "txn_currency": item.txn_currency,
                        "debit_txn": item.debit_txn,
                        "credit_txn": item.credit_txn,
                        "functional_currency": item.functional_currency,
                        "debit_functional": item.debit_functional,
                        "credit_functional": item.credit_functional,
                        "contract_id": item.contract_id,
                        "obligation_id": item.obligation_id,
                        "legacy_key": item.legacy_key,
                        "counterparty_entity_id": item.counterparty_entity_id,
                        "origin_period_id": item.origin_period_id,
                        "fx_rate_set_version_ids": sorted(item.fx_rate_set_version_ids, key=str),
                        "fx_rate_ids": sorted(item.fx_rate_ids, key=str),
                        "memo": None,
                        "source_line_count": len(item.line_ids),
                        "source_grouping_sha256": item.sha256,
                        **_stamps(uow, modified=False),
                    }
                )
            session.execute(insert(journal_line), rows)
    held_file: tuple[UUID, str] | None = None
    if held:
        held_file = _held_detail_file(
            uow, external_id=f"erev:{tenant_code}:{run_no}:held", run_no=run_no, held=held
        )
    taken_file: tuple[UUID, str] | None = None
    if taken:
        taken_file = _taken_over_detail_file(
            uow, external_id=f"erev:{tenant_code}:{run_no}:taken-over", run_no=run_no, taken=taken
        )
    counts = {
        "batches": sum(len(chunks) for _, chunks in batches),
        "entries": len(entry_ids),
        "lines": len(line_ids),
        "detail_lines": len(kept),
        "held_lines": len(held),
    }
    uow.audit(
        action=CALCULATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        object_version="1",
        after={
            "run_no": run_no,
            "entity_id": str(entity_id),
            "book_code": book_code,
            "period_id": str(period_id),
            "mode": mode.value,
            "grain": grain.value,
            "coverage": [from_seq, to_seq, delta_from if delta_to is not None else None, delta_to],
            "total_debit_functional": format(total_debit, "f"),
            "total_credit_functional": format(total_credit, "f"),
            "counts": counts,
            "held_detail_file_id": None if held_file is None else str(held_file[0]),
            "held_detail_sha256": None if held_file is None else held_file[1],
            # The lines this run left out as held, by id — the identity completeness binds coverage
            # to (Codex production-20260921-1317 R5-ORDER-1); an empty list is the explicit
            # zero-held state (D-98 132).
            "held_subledger_line_ids": sorted(str(line.id) for line, _ in held),
            # The lines this run took over from runs of its key that had left them out, by id —
            # what coverage counts for this run beside its range, and what no later run takes
            # again (S14-R-17 rev 1.164); an empty list is the explicit state of none.
            "taken_over_subledger_line_ids": sorted(str(line.id) for line, _ in taken),
            "taken_over_detail_file_id": None if taken_file is None else str(taken_file[0]),
            "taken_over_detail_sha256": None if taken_file is None else taken_file[1],
        },
    )
    if entry_ids:
        record_facts(uow, action="journal_entry.create", object_type="journal_entry", ids=entry_ids)
        record_facts(uow, action="journal_line.create", object_type="journal_line", ids=line_ids)
    return counts


def _record_findings(
    uow: UnitOfWork, params: Mapping[str, Any], findings: Sequence[validation.LineFinding]
) -> None:
    """One T-IMP-05 item per failing line, source ``JOURNAL``, naming contract, obligation and
    role; a repeated attempt counts the open item again (``dedupe``)."""
    entity_id = UUID(str(params["entity_id"]))
    period_id = UUID(str(params["period_id"]))
    names = validation.names_of(uow.session, findings)
    for finding in findings:
        external_id, obligation_key = names.get(finding.line_id, (None, None))
        subject = " / ".join(
            part
            for part in (
                None if external_id is None else f"contract {external_id}",
                None if obligation_key is None else f"obligation {obligation_key}",
                f"role {finding.account_role}",
            )
            if part
        )
        raise_exception_item(
            uow,
            source=ExceptionSource.JOURNAL,
            code=finding.code,
            severity=ExceptionSeverity.BLOCKING,  # 04 table 15.4-E: ERROR → BLOCKING
            message=f"{finding.message} ({subject}).",
            dedupe=f"JOURNAL:{finding.code}:{finding.line_id}",
            title=f"Journal generation blocked: {subject}",
            contract_id=finding.contract_id,
            obligation_id=finding.obligation_id,
            entity_id=entity_id,
            period_id=period_id,
        )


def failed_calculation(
    session: Session, subject_type: str | None, subject_id: UUID, params: Mapping[str, Any]
) -> FailedSubject | None:
    """05 JOB-07 rev 1.165: what the exception item of a failed calculation names. The job
    creates the run under the id its command chose, so a failed job leaves no row to read: the
    entity, the book and the period are the job's params, and together they are the record — a
    later calculation of the same entity, book and period settles the item, under another run
    id."""
    entity_id, period_id = params.get("entity_id"), params.get("period_id")
    if entity_id is None or period_id is None:
        return None
    return FailedSubject(
        entity_id=UUID(str(entity_id)),
        period_id=UUID(str(period_id)),
        key=f"{entity_id}:{params.get('book_code')}:{period_id}",
    )


@task(
    JobKind.JOURNAL_RUN_CALCULATE,
    failed_item=failed_item(ExceptionSource.JOURNAL, failed_calculation),
)
def calculate_run(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``JOURNAL_RUN_CALCULATE`` (05 §5.6 queue ``close``): one transaction per run. A retried
    attempt whose run exists answers with that run (DG-KRN-JOB-03)."""
    run_id = UUID(str(params["journal_run_id"]))
    counts: dict[str, int] = {}
    try:
        with jc.unit_of_work() as uow:
            exists = uow.session.execute(
                select(journal_run.c.id).where(journal_run.c.id == run_id)
            ).scalar_one_or_none()
            if exists is None:
                counts = calculate(
                    uow,
                    params,
                    job_id=jc.job_id,
                    within_close_run=jc.kind is JobKind.CLOSE_RUN,
                )
                uow.commit()
    except validation.JournalValidationFailed as failed:
        # The run's unit of work rolled back (no journal_run row, batch, entry or line). The
        # findings become exception items in a unit of work of their own, then the job fails
        # with the finding's 422 (CLO-10; 04 §15.4 ACCOUNT_MAPPING_MISSING / FX_RATE_MISSING).
        with jc.unit_of_work() as uow:
            _record_findings(uow, params, failed.findings)
            uow.commit()
        raise failed.problem from None
    return JobOutcome(
        state="SUCCEEDED",
        result={"href": RUN_HREF.format(run_id=run_id), "counts": counts},
    )
