"""Upgrade processing per portion, posting attribution and the frozen validation dataset
(05 RCP-28a, RCP-29; 04 T-PLT-44, T-PLT-46, T-SL-11, T-RPT-01 rule 3; D-96 (4), (E), (F), R7).

Pure functions over injected facts; the integration slice (after the P2 merge) wires them into
``computation.persist()``, the ``REPLAY_VERIFY`` fan-out and the two report builders.

- **Seeding** (C/E): ``seed_portions`` — only an effective MINOR/MAJOR validation with an
  accepted attempt seeds ``PENDING`` rows, one per portion (group × entity × enabled book);
  ``PATCH``, ``BASELINE`` and ``BOOTSTRAP`` seed nothing.
- **Deferral** (E, v5): ``conservative_origins`` derives the portion's origin set inside the
  persistence boundary from the frozen computation (events, posted rows, schedule lines — never a
  caller-supplied list, which could under-state it); ``unresolved_origins`` re-applies S08-R-08's
  own assignment rule (``dates.first_open_period_on_or_after`` over the entity's calendar for the
  book) to that set; ``portion_transition`` always attributes the actual postings and lets only an
  empty unresolved set reach ``POSTED`` or ``SETTLED_NO_POSTING``. The engine output carries no
  marker for a dropped delta (``s14_posting/assign.py``), so this is the same rule re-applied, not
  a guess.
- **Attribution** (F): ``cause_label`` — ``UPGRADE_ONLY`` only when the attribution input view
  of the current bundle equals the previous head's evidence view; ``UPGRADE_AND_OTHER_INPUTS``
  when they differ; ``UPGRADE_CONTEXT`` when no comparison is possible. Metadata only.
- **Frozen dataset** (R7): ``build_validation_dataset`` writes the ``VALIDATION_DATASET`` bytes
  once; ``upgrade_validation_report`` derives every row and total from those bytes alone, so a
  rerun reproduces the same hash; ``approval_content_sha256`` binds the dataset, the attempt and
  the frozen required entity set. ``register_rows`` is the as-of view over the append-only events.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal
from uuid import UUID

from erev_engine import dates, upgrade
from erev_engine.bundle import EntityInput, InputBundle, OutputBundle
from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.errors import EngineError

from erev_api.enums import PostingAttributionCause, UpgradeProcessingState

__all__ = [
    "CLOSED_STATES",
    "NO_POSTING_DELTA",
    "AttemptFacts",
    "AttributionRow",
    "DatasetReport",
    "GroupDatasetRow",
    "PortionEvent",
    "PortionKey",
    "approval_content_sha256",
    "attribution_applies",
    "attribution_row",
    "build_validation_dataset",
    "cause_label",
    "conservative_origins",
    "group_terminal",
    "portion_transition",
    "register_rows",
    "seed_portions",
    "unresolved_origins",
    "upgrade_validation_report",
]

CLOSED_STATES: Final = frozenset({"closed", "permanently_locked"})  # E-04, as S08 reads them
NO_POSTING_DELTA: Final = "NO_POSTING_DELTA"
_TERMINAL: Final = frozenset(
    {UpgradeProcessingState.POSTED, UpgradeProcessingState.SETTLED_NO_POSTING}
)
_SEEDING_LEVELS: Final = frozenset({"MINOR", "MAJOR"})

PortionKey = tuple[str, str]  # (entity_code, book_code)


# --- Portion processing (E) ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PortionEvent:
    """One T-PLT-46 row (append-only); the portion's current state is its latest ``seq``."""

    group_id: UUID
    entity_code: str
    book_code: str
    seq: int
    state: UpgradeProcessingState
    computation_id: UUID | None
    posting_ids: tuple[UUID, ...]
    unresolved_origin_period_keys: tuple[str, ...]
    reason: str | None
    created_at: datetime

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL


def seed_portions(
    *,
    effective_level: str,
    accepted_attempt_id: UUID | None,
    group_id: UUID,
    portions: Iterable[PortionKey],
    now: datetime,
) -> tuple[PortionEvent, ...]:
    """The ``seq = 1`` ``PENDING`` rows written at enablement — MINOR/MAJOR with an accepted
    attempt only; ``PATCH``, ``BASELINE`` and ``BOOTSTRAP`` seed nothing (C/E)."""
    if effective_level not in _SEEDING_LEVELS or accepted_attempt_id is None:
        return ()
    return tuple(
        PortionEvent(
            group_id, entity, book, 1, UpgradeProcessingState.PENDING, None, (), (), None, now
        )
        for entity, book in sorted(set(portions))
    )


def _period(entity: EntityInput, period_key: str) -> dates.PeriodLike:
    for period in entity.periods:
        if period.period_key == period_key:
            return period
    raise ValueError(f"{entity.code} has no period {period_key}")


def conservative_origins(
    entity: EntityInput, book_code: str, *, bundle: InputBundle, output: OutputBundle | None
) -> tuple[str, ...]:
    """The portion's conservative origin set, derived **inside the persistence boundary** from the
    frozen computation itself (team-lead ruling (2), 2026-09-19): every ``closed`` /
    ``permanently_locked`` period of the entity (for the book) that holds (a) the effective date of
    a member event of a contract this entity contracts, (b) a posted row of this entity and book
    (its posting period and its origin period), or (c) a schedule line of this entity in the book's
    output. There is no caller-supplied list: a caller cannot narrow the set."""
    contracts = {
        item.external_id for item in bundle.contracts if item.contracting_entity_code == entity.code
    }
    keys: set[str] = set()
    for item in bundle.events:
        if item.contract_key in contracts:
            try:
                keys.add(dates.period_of(entity, item.effective_date).period_key)
            except EngineError:
                continue  # a date outside the calendar horizon is not a closed origin
    for posted in bundle.posted:
        if posted.entity_code == entity.code and posted.book_code == book_code:
            keys.add(posted.period_key)
            if posted.origin_period_key is not None:
                keys.add(posted.origin_period_key)
    if output is not None:
        for book in output.books:
            if book.book_code != book_code:
                continue
            for line in book.schedules:
                if line.entity == entity.code:
                    keys.add(line.period_key)
    return tuple(
        sorted(
            key
            for key in keys
            if dates.period_state(_period(entity, key), book_code) in CLOSED_STATES
        )
    )


def unresolved_origins(
    entity: EntityInput, book_code: str, origin_period_keys: Iterable[str]
) -> tuple[str, ...]:
    """S08-R-08 re-applied: a closed origin whose calendar has no later ``open``/``closing``/
    ``reopened`` period for the book has no assignable posting period and stays unresolved."""
    unresolved: list[str] = []
    for key in sorted(set(origin_period_keys)):
        period = _period(entity, key)
        if dates.period_state(period, book_code) not in CLOSED_STATES:
            continue
        later = dates.first_open_period_on_or_after(
            entity, book_code, period.end_date + timedelta(days=1)
        )
        if later is None:
            unresolved.append(key)
    return tuple(unresolved)


def portion_transition(
    latest: PortionEvent,
    *,
    computation_id: UUID,
    posting_ids: Sequence[UUID],
    unresolved: Sequence[str],
    now: datetime,
) -> PortionEvent | None:
    """The v5 rule (D-96 (E); Codex v4 review). Evaluated for every unsettled portion whether or
    not postings were produced: the actual postings are always kept (the caller attributes each
    with a T-SL-11 row); if any origin remains unassignable the portion appends
    ``DEFERRED_NO_OPEN_PERIOD`` retaining the unresolved keys **and** the posting ids; only an
    empty unresolved set permits ``POSTED`` (when the sequence holds posting ids) or
    ``SETTLED_NO_POSTING``. A terminal portion appends nothing (duplicate computation)."""
    if latest.terminal:
        return None
    all_postings = tuple(dict.fromkeys((*latest.posting_ids, *posting_ids)))
    seq = latest.seq + 1
    if unresolved:
        return PortionEvent(
            latest.group_id,
            latest.entity_code,
            latest.book_code,
            seq,
            UpgradeProcessingState.DEFERRED_NO_OPEN_PERIOD,
            computation_id,
            all_postings,
            tuple(sorted(set(unresolved))),
            None,
            now,
        )
    if all_postings:
        return PortionEvent(
            latest.group_id,
            latest.entity_code,
            latest.book_code,
            seq,
            UpgradeProcessingState.POSTED,
            computation_id,
            all_postings,
            (),
            None,
            now,
        )
    return PortionEvent(
        latest.group_id,
        latest.entity_code,
        latest.book_code,
        seq,
        UpgradeProcessingState.SETTLED_NO_POSTING,
        computation_id,
        (),
        (),
        NO_POSTING_DELTA,
        now,
    )


def group_terminal(latest_per_portion: Iterable[PortionEvent]) -> bool:
    """A group is settled only when every portion is ``POSTED`` or ``SETTLED_NO_POSTING``."""
    events = list(latest_per_portion)
    return bool(events) and all(event.terminal for event in events)


# --- Attribution (F) ------------------------------------------------------------------------------


def attribution_applies(
    *,
    effective_level: str,
    accepted_attempt_id: UUID | None,
    latest_per_portion: Iterable[PortionEvent],
) -> bool:
    """T-SL-11 rows are written only for MINOR/MAJOR validations with an accepted attempt, and
    only while any portion of the group is still ``PENDING`` or ``DEFERRED_NO_OPEN_PERIOD``."""
    if effective_level not in _SEEDING_LEVELS or accepted_attempt_id is None:
        return False
    return any(not event.terminal for event in latest_per_portion)


def cause_label(comparison: upgrade.AttributionComparison) -> PostingAttributionCause:
    if comparison.equal is None:
        return PostingAttributionCause.UPGRADE_CONTEXT
    if comparison.equal:
        return PostingAttributionCause.UPGRADE_ONLY
    return PostingAttributionCause.UPGRADE_AND_OTHER_INPUTS


@dataclass(frozen=True, slots=True)
class AttributionRow:
    """One T-SL-11 row; amounts, posting behaviour and line ``reason_code`` are untouched."""

    subledger_posting_id: UUID
    release_validation_attempt_id: UUID
    combination_group_id: UUID
    contract_computation_id: UUID
    previous_computation_id: UUID | None
    cause: PostingAttributionCause
    sampled: bool
    origin_periods: Mapping[str, object]
    input_comparison: Mapping[str, object]
    created_at: datetime


def attribution_row(
    *,
    posting_id: UUID,
    attempt_id: UUID,
    group_id: UUID,
    computation_id: UUID,
    previous_computation_id: UUID | None,
    previous_evidence: bytes | None,
    current: InputBundle,
    sampled: bool,
    origin_periods: Mapping[str, object],
    now: datetime,
) -> AttributionRow:
    """Attribute one posting. The previous head's evidence bytes (T-CON-25) are decoded and
    brought to the current version through the registered transforms; undecodable or absent
    evidence, or no transform chain, keeps the conservative ``UPGRADE_CONTEXT`` label."""
    previous: InputBundle | None = None
    if previous_evidence is not None:
        try:
            previous = upgrade.decode_input(previous_evidence)
        except (ValueError, TypeError):
            previous = None
    comparison = upgrade.attribution_comparison(previous, current)
    return AttributionRow(
        posting_id,
        attempt_id,
        group_id,
        computation_id,
        previous_computation_id,
        cause_label(comparison),
        sampled,
        dict(origin_periods),
        comparison.as_json(),
        now,
    )


# --- Frozen dataset and reports (R7) --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AttemptFacts:
    attempt_id: UUID
    release_validation_id: UUID
    attempt_no: int
    effective_level: str
    engine_release_id: UUID
    source_engine_release_id: UUID | None
    seed: int
    population: Mapping[str, object]
    required_entity_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class GroupDatasetRow:
    """What the dataset keeps per group: selection, source, outcome and the L0/L1/L2 facts."""

    group_id: UUID
    selection: str
    strata: tuple[tuple[str, str], ...]
    source_computation_id: UUID | None
    orchestration_state: str
    outcome: str | None
    reason: str | None
    expected_output_sha256: str | None
    actual_output_sha256: str | None
    normalised_expected_sha256: str | None
    normalised_actual_sha256: str | None
    difference_summary: Mapping[str, object] | None
    differences: tuple[Mapping[str, object], ...]  # {path, category, before, after}


def build_validation_dataset(
    attempt: AttemptFacts, groups: Sequence[GroupDatasetRow]
) -> tuple[bytes, str]:
    """The ``VALIDATION_DATASET`` file written once at →COMPLETE/INCOMPLETE and its SHA-256."""
    payload = {
        "dataset_format": 1,
        "attempt": {
            "release_validation_attempt_id": attempt.attempt_id,
            "release_validation_id": attempt.release_validation_id,
            "attempt_no": attempt.attempt_no,
            "effective_level": attempt.effective_level,
            "engine_release_id": attempt.engine_release_id,
            "source_engine_release_id": attempt.source_engine_release_id,
            "seed": attempt.seed,
            "population": dict(attempt.population),
            "required_entity_ids": sorted(str(item) for item in attempt.required_entity_ids),
        },
        "groups": [
            {
                "group_id": row.group_id,
                "selection": row.selection,
                "strata": [list(pair) for pair in row.strata],
                "source_computation_id": row.source_computation_id,
                "orchestration_state": row.orchestration_state,
                "outcome": row.outcome,
                "reason": row.reason,
                "expected_output_sha256": row.expected_output_sha256,
                "actual_output_sha256": row.actual_output_sha256,
                "normalised_expected_sha256": row.normalised_expected_sha256,
                "normalised_actual_sha256": row.normalised_actual_sha256,
                "difference_summary": None
                if row.difference_summary is None
                else dict(row.difference_summary),
                "differences": [dict(item) for item in row.differences],
            }
            for row in sorted(groups, key=lambda row: str(row.group_id))
        ],
    }
    data = canonical_bytes(payload)
    return data, sha256_hex(payload)


@dataclass(frozen=True, slots=True)
class DatasetReport:
    """Columns, rows and control totals of a report derived from the frozen dataset only; the
    integration slice maps them onto the report framework's ``ReportData``."""

    columns: tuple[str, ...]
    rows: tuple[Mapping[str, object], ...]
    control_totals: Mapping[str, object]


_GROUP_COLUMNS: Final = (
    "row_key",
    "group_id",
    "selection",
    "strata",
    "source_computation_id",
    "orchestration_state",
    "outcome",
    "reason",
    "expected_output_sha256",
    "actual_output_sha256",
    "normalised_expected_sha256",
    "normalised_actual_sha256",
    "M",
    "P",
    "T",
    "R",
)


def upgrade_validation_report(dataset: bytes) -> DatasetReport:
    """``upgrade_validation`` rows and totals from the dataset bytes alone (T-RPT-01 rule 3): no
    table is read, so a rerun after approval, retry or true-up reproduces the same output."""
    parsed = json.loads(dataset.decode("utf-8"))
    if parsed.get("dataset_format") != 1:
        raise ValueError("unknown validation dataset format")
    rows: list[Mapping[str, object]] = []
    outcomes: dict[str, int] = {}
    for group in parsed["groups"]:
        summary = group.get("difference_summary") or {}
        outcome = group.get("outcome") or "NONE"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        rows.append(
            {
                "row_key": f"group:{group['group_id']}",
                "group_id": group["group_id"],
                "selection": group["selection"],
                "strata": ",".join(f"{book}/{method}" for book, method in group["strata"]),
                "source_computation_id": group["source_computation_id"],
                "orchestration_state": group["orchestration_state"],
                "outcome": group["outcome"],
                "reason": group["reason"],
                "expected_output_sha256": group["expected_output_sha256"],
                "actual_output_sha256": group["actual_output_sha256"],
                "normalised_expected_sha256": group["normalised_expected_sha256"],
                "normalised_actual_sha256": group["normalised_actual_sha256"],
                "M": summary.get("M", 0),
                "P": summary.get("P", 0),
                "T": summary.get("T", 0),
                "R": summary.get("R", 0),
            }
        )
        for index, difference in enumerate(group["differences"]):
            rows.append(
                {
                    "row_key": f"difference:{group['group_id']}:{index}",
                    "group_id": group["group_id"],
                    "selection": group["selection"],
                    "strata": "",
                    "source_computation_id": group["source_computation_id"],
                    "orchestration_state": group["orchestration_state"],
                    "outcome": group["outcome"],
                    "reason": difference.get("path"),
                    "expected_output_sha256": difference.get("before"),
                    "actual_output_sha256": difference.get("after"),
                    "normalised_expected_sha256": None,
                    "normalised_actual_sha256": None,
                    "M": 1 if difference.get("category") == "M" else 0,
                    "P": 1 if difference.get("category") == "P" else 0,
                    "T": 1 if difference.get("category") == "T" else 0,
                    "R": 1 if difference.get("category") == "R" else 0,
                }
            )
    totals: dict[str, object] = {
        "groups": len(parsed["groups"]),
        "rows": len(rows),
        "outcomes": dict(sorted(outcomes.items())),
        "required_entity_ids": len(parsed["attempt"]["required_entity_ids"]),
        "effective_level": parsed["attempt"]["effective_level"],
    }
    return DatasetReport(_GROUP_COLUMNS, tuple(rows), totals)


def approval_content_sha256(
    *, dataset_sha256: str, attempt_id: UUID, required_entity_ids: Iterable[UUID]
) -> str:
    """The ``ENGINE_RELEASE_VALIDATION`` subject content hash: any change to the frozen dataset,
    the attempt or the frozen entity set voids the request (REQ-PLT-014)."""
    return sha256_hex(
        {
            "dataset_sha256": dataset_sha256,
            "release_validation_attempt_id": str(attempt_id),
            "required_entity_ids": sorted(str(item) for item in required_entity_ids),
        }
    )


RegisterState = Literal["PENDING", "DEFERRED_NO_OPEN_PERIOD", "SETTLED_NO_POSTING", "POSTED"]


def register_rows(
    events: Sequence[PortionEvent],
    attributions: Sequence[AttributionRow],
    *,
    known_at: datetime,
) -> tuple[Mapping[str, object], ...]:
    """``engine_trueup_register`` as of ``known_at``: the latest event per portion among those
    created at or before ``known_at`` (exact, the rows are append-only), the group's terminal
    flag and the attributed postings with their cause labels."""
    latest: dict[tuple[UUID, str, str], PortionEvent] = {}
    for event in events:
        if event.created_at > known_at:
            continue
        key = (event.group_id, event.entity_code, event.book_code)
        if key not in latest or event.seq > latest[key].seq:
            latest[key] = event
    by_group: dict[UUID, list[PortionEvent]] = {}
    for event in latest.values():
        by_group.setdefault(event.group_id, []).append(event)
    visible = [row for row in attributions if row.created_at <= known_at]
    rows: list[Mapping[str, object]] = []
    for (group_id, entity, book), event in sorted(
        latest.items(), key=lambda item: tuple(map(str, item[0]))
    ):
        postings = [
            row
            for row in visible
            if row.combination_group_id == group_id
            and row.subledger_posting_id in event.posting_ids
        ]
        rows.append(
            {
                "row_key": f"portion:{group_id}:{entity}:{book}",
                "group_id": group_id,
                "entity_code": entity,
                "book_code": book,
                "upgrade_state": event.state.value,
                "group_terminal": group_terminal(by_group[group_id]),
                "unresolved_origin_period_keys": list(event.unresolved_origin_period_keys),
                "posting_ids": [str(item) for item in event.posting_ids],
                "causes": sorted({row.cause.value for row in postings}),
                "sampled": any(row.sampled for row in postings),
                "reason": event.reason,
            }
        )
    return tuple(rows)
