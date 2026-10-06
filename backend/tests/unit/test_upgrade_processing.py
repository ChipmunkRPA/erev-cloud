"""``erev_api.domain.contracts.upgrade_report``: per-portion upgrade processing (E, v5), posting
attribution (F), the frozen validation dataset and the as-of register (R7) — 05 RCP-28a, RCP-29;
04 T-PLT-44, T-PLT-46, T-SL-11; D-96 (4); lane P5 preparation slice. DB-free.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from erev_api.domain.contracts.upgrade_report import (
    AttemptFacts,
    GroupDatasetRow,
    PortionEvent,
    approval_content_sha256,
    attribution_applies,
    attribution_row,
    build_validation_dataset,
    conservative_origins,
    group_terminal,
    portion_transition,
    register_rows,
    seed_portions,
    unresolved_origins,
    upgrade_validation_report,
)
from erev_api.enums import PostingAttributionCause, UpgradeProcessingState
from erev_engine import compute, dates
from erev_engine.bundle import EntityInput, InputBundle, PostedAmountInput
from support.billing_lines import checkpoint_bundle
from support.bundles import contract, entity, event, minimal_contract

COMPUTABLE = ("mod", "MOD-LEGACY-PROS-GT12", "end-june-after-prospective")

U = UpgradeProcessingState
C = PostingAttributionCause
T0 = datetime(2026, 9, 19, 12, tzinfo=UTC)
GROUP = UUID(int=77)
ATTEMPT = UUID(int=88)
BOOK = "ASC606"


def _calendar(code: str, states: dict[str, str]) -> EntityInput:
    """Twelve monthly periods FY2026-P01..P12; unlisted periods are ``open``."""
    return entity(code, start=date(2026, 1, 1), months=12, states=states)


def _jan_mar_jun(july: str) -> EntityInput:
    """January closed, March reopened, June closed and nothing postable after June (until July
    ``open`` for the second half of the scenario)."""
    states = {f"FY2026-P{n:02d}": "closed" for n in range(1, 13)}
    states["FY2026-P03"] = "reopened"
    states["FY2026-P07"] = july
    return _calendar("US01", states)


def _seed(portions: tuple[tuple[str, str], ...] = (("US01", BOOK),)) -> tuple[PortionEvent, ...]:
    return seed_portions(
        effective_level="MAJOR",
        accepted_attempt_id=ATTEMPT,
        group_id=GROUP,
        portions=portions,
        now=T0,
    )


def _bundle_for(calendar: EntityInput, *effective: date) -> InputBundle:
    """A frozen computation of one contract of ``calendar``'s entity with member events on the
    given dates (the origin set is derived from these, never from a caller list)."""
    header = contract("K-ORIGINS", entity_code=calendar.code)
    events = tuple(
        event(header.external_id, index + 1, "CONTRACT_BOOKED", day, {})
        for index, day in enumerate(effective)
    )
    return dataclasses.replace(
        minimal_contract(), entities=(calendar,), contracts=(header,), events=events, posted=()
    )


# --- seeding (C/E) -------------------------------------------------------------------------------


def test_seeding_only_for_minor_or_major_with_an_accepted_attempt() -> None:
    rows = _seed((("US01", BOOK), ("UK01", BOOK), ("US01", "IFRS15")))
    assert [(r.entity_code, r.book_code, r.seq, r.state) for r in rows] == [
        ("UK01", BOOK, 1, U.PENDING),
        ("US01", BOOK, 1, U.PENDING),
        ("US01", "IFRS15", 1, U.PENDING),
    ]
    for level in ("PATCH", "BASELINE", "BOOTSTRAP"):
        assert (
            seed_portions(
                effective_level=level,
                accepted_attempt_id=ATTEMPT,
                group_id=GROUP,
                portions=(("US01", BOOK),),
                now=T0,
            )
            == ()
        )
    assert (
        seed_portions(
            effective_level="MINOR",
            accepted_attempt_id=None,
            group_id=GROUP,
            portions=(("US01", BOOK),),
            now=T0,
        )
        == ()
    )
    assert not attribution_applies(
        effective_level="PATCH", accepted_attempt_id=ATTEMPT, latest_per_portion=rows
    )
    assert attribution_applies(
        effective_level="MAJOR", accepted_attempt_id=ATTEMPT, latest_per_portion=rows
    )


# --- deferral re-applies S08-R-08 (E) -------------------------------------------------------------


def test_unresolved_origins_follow_the_engine_assignment_rule() -> None:
    calendar = _jan_mar_jun("closed")
    frozen = _bundle_for(calendar, date(2026, 1, 15), date(2026, 3, 15), date(2026, 6, 15))
    origins = conservative_origins(calendar, BOOK, bundle=frozen, output=None)
    assert origins == ("FY2026-P01", "FY2026-P06")  # March is reopened, not a closed origin
    unresolved = unresolved_origins(calendar, BOOK, origins)
    assert unresolved == ("FY2026-P06",)  # January posts into March; June has no later period
    # The same rule the engine applies (S08-R-08 via dates.first_open_period_on_or_after).
    for key in origins:
        period = next(p for p in calendar.periods if p.period_key == key)
        later = dates.first_open_period_on_or_after(
            calendar, BOOK, period.end_date + timedelta(days=1)
        )
        assert (later is None) == (key in unresolved)
    assert unresolved_origins(_jan_mar_jun("open"), BOOK, origins) == ()
    with pytest.raises(ValueError, match="no period"):
        unresolved_origins(calendar, BOOK, ["FY2031-P01"])


def test_origin_set_is_derived_inside_the_boundary_and_cannot_be_narrowed() -> None:
    # No parameter accepts a list of period keys: the set comes from the frozen computation only.
    parameters = inspect.signature(conservative_origins).parameters
    assert set(parameters) == {"entity", "book_code", "bundle", "output"}
    assert parameters["bundle"].kind is inspect.Parameter.KEYWORD_ONLY
    calendar = _calendar("US01", {f"FY2026-P{n:02d}": "closed" for n in range(1, 13)})
    # (a) member events: every closed period holding an effective date of this entity's contract.
    frozen = _bundle_for(calendar, date(2026, 2, 10), date(2026, 5, 20))
    assert conservative_origins(calendar, BOOK, bundle=frozen, output=None) == (
        "FY2026-P02",
        "FY2026-P05",
    )
    # (b) posted rows of this entity and book add their posting AND origin periods; another
    # entity's or book's rows add nothing.
    line = PostedAmountInput(
        BOOK,
        "US01",
        "K-ORIGINS",
        "REVENUE_RECOGNITION",
        "REVENUE",
        None,
        None,
        "FY2026-P04",
        "FY2026-P01",
        "EVENT",
        "USD",
        "USD",
        -100,
        -100,
    )
    foreign = dataclasses.replace(line, entity_code="UK01", period_key="FY2026-P09")
    other_book = dataclasses.replace(line, book_code="IFRS15", period_key="FY2026-P10")
    with_posted = dataclasses.replace(frozen, posted=(line, foreign, other_book))
    assert conservative_origins(calendar, BOOK, bundle=with_posted, output=None) == (
        "FY2026-P01",
        "FY2026-P02",
        "FY2026-P04",
        "FY2026-P05",
    )
    # (c) schedule lines of the book's output for this entity, on a real computation: every
    # closed period holding a schedule line is an origin, and the set equals the full union.
    stored = checkpoint_bundle(*COMPUTABLE)
    output = compute(stored)
    entity = stored.entities[0]
    derived = set(conservative_origins(entity, BOOK, bundle=stored, output=output))
    (book_out,) = output.books
    touched = {
        dates.period_of(entity, item.effective_date).period_key
        for item in stored.events
        if item.contract_key
        in {c.external_id for c in stored.contracts if c.contracting_entity_code == entity.code}
    }
    touched |= {p.period_key for p in stored.posted if p.entity_code == entity.code}
    touched |= {
        p.origin_period_key
        for p in stored.posted
        if p.entity_code == entity.code and p.origin_period_key is not None
    }
    touched |= {s.period_key for s in book_out.schedules if s.entity == entity.code}
    closed = {
        key
        for key in touched
        if dates.period_state(next(p for p in entity.periods if p.period_key == key), BOOK)
        in {"closed", "permanently_locked"}
    }
    assert derived == closed
    assert {s.period_key for s in book_out.schedules if s.entity == entity.code} - derived <= (
        touched - closed
    )  # no schedule-line origin is dropped unless its period is not closed


def test_partial_origin_deferral_jan_mar_jun_then_july_opens() -> None:
    (pending,) = _seed()
    calendar = _jan_mar_jun("closed")
    march_posting, first_computation = uuid4(), uuid4()
    frozen = _bundle_for(calendar, date(2026, 1, 15), date(2026, 6, 15))
    origins = conservative_origins(calendar, BOOK, bundle=frozen, output=None)
    deferred = portion_transition(
        pending,
        computation_id=first_computation,
        posting_ids=[march_posting],
        unresolved=unresolved_origins(calendar, BOOK, origins),
        now=T0,
    )
    assert deferred is not None
    # The January carry posted into March and is retained; June stays unresolved; not POSTED.
    assert deferred.state is U.DEFERRED_NO_OPEN_PERIOD and deferred.seq == 2
    assert deferred.posting_ids == (march_posting,)
    assert deferred.unresolved_origin_period_keys == ("FY2026-P06",)
    assert not deferred.terminal and not group_terminal([deferred])
    # July opens: SCH-06 re-marks the group dirty, June posts into July, the portion is POSTED.
    july_posting = uuid4()
    posted = portion_transition(
        deferred,
        computation_id=uuid4(),
        posting_ids=[july_posting],
        unresolved=unresolved_origins(_jan_mar_jun("open"), BOOK, origins),
        now=T0 + timedelta(days=30),
    )
    assert posted is not None and posted.state is U.POSTED and posted.seq == 3
    assert posted.posting_ids == (march_posting, july_posting)
    assert group_terminal([posted])
    # A duplicate computation appends nothing once the portion is terminal.
    assert (
        portion_transition(posted, computation_id=uuid4(), posting_ids=[], unresolved=(), now=T0)
        is None
    )


def test_a_posted_b_deferred_then_b_opens_group_terminal_only_after_both() -> None:
    a_pending, b_pending = _seed((("A", BOOK), ("B", BOOK)))
    a_cal = _calendar("A", {})
    b_cal = _calendar("B", {f"FY2026-P{n:02d}": "closed" for n in range(1, 13)})
    january = date(2026, 1, 15)
    a_origins = conservative_origins(a_cal, BOOK, bundle=_bundle_for(a_cal, january), output=None)
    b_origins = conservative_origins(b_cal, BOOK, bundle=_bundle_for(b_cal, january), output=None)
    assert a_origins == () and b_origins == ("FY2026-P01",)  # A is open: no closed origin
    a_posting = uuid4()
    a_done = portion_transition(
        a_pending,
        computation_id=uuid4(),
        posting_ids=[a_posting],
        unresolved=unresolved_origins(a_cal, BOOK, a_origins),
        now=T0,
    )
    b_deferred = portion_transition(
        b_pending,
        computation_id=uuid4(),
        posting_ids=[],
        unresolved=unresolved_origins(b_cal, BOOK, b_origins),
        now=T0,
    )
    assert a_done is not None and a_done.state is U.POSTED
    assert b_deferred is not None and b_deferred.state is U.DEFERRED_NO_OPEN_PERIOD
    assert not group_terminal([a_done, b_deferred])  # A never settles B
    b_open = _calendar("B", {"FY2026-P01": "closed"})
    b_posting = uuid4()
    b_done = portion_transition(
        b_deferred,
        computation_id=uuid4(),
        posting_ids=[b_posting],
        unresolved=unresolved_origins(b_open, BOOK, b_origins),
        now=T0 + timedelta(days=1),
    )
    assert b_done is not None and b_done.state is U.POSTED and b_done.posting_ids == (b_posting,)
    assert group_terminal([a_done, b_done])


def test_trace_only_or_zero_delta_settles_without_a_ledger_row() -> None:
    (pending,) = _seed()
    calendar = _calendar("US01", {"FY2026-P01": "closed"})  # January closed, February open
    settled = portion_transition(
        pending,
        computation_id=uuid4(),
        posting_ids=[],
        unresolved=unresolved_origins(calendar, BOOK, ["FY2026-P01"]),
        now=T0,
    )
    assert settled is not None and settled.state is U.SETTLED_NO_POSTING
    assert settled.posting_ids == () and settled.reason == "NO_POSTING_DELTA"
    assert settled.terminal and group_terminal([settled])
    assert not attribution_applies(
        effective_level="MAJOR", accepted_attempt_id=ATTEMPT, latest_per_portion=[settled]
    )


# --- attribution (F) -----------------------------------------------------------------------------


def _attribute(previous: bytes | None, current: object) -> PostingAttributionCause:
    from erev_engine.bundle import InputBundle

    assert isinstance(current, InputBundle)
    return attribution_row(
        posting_id=uuid4(),
        attempt_id=ATTEMPT,
        group_id=GROUP,
        computation_id=uuid4(),
        previous_computation_id=uuid4(),
        previous_evidence=previous,
        current=current,
        sampled=False,
        origin_periods={"origins": ["FY2026-P01"]},
        now=T0,
    ).cause


def test_cause_labels_known_at_and_period_state_changes_are_other_inputs() -> None:
    from erev_engine import upgrade

    current = minimal_contract()
    same = upgrade.encode_input(current)
    assert _attribute(None, current) is C.UPGRADE_CONTEXT  # no previous evidence
    assert _attribute(b"not evidence", current) is C.UPGRADE_CONTEXT  # undecodable
    assert _attribute(same, current) is C.UPGRADE_ONLY  # byte-equal attribution views
    moved = dataclasses.replace(current, known_at=current.known_at + timedelta(hours=1))
    assert _attribute(upgrade.encode_input(moved), current) is C.UPGRADE_AND_OTHER_INPUTS
    other_states = dataclasses.replace(current, entities=(entity(states={"FY2026-P01": "closed"}),))
    assert _attribute(upgrade.encode_input(other_states), current) is C.UPGRADE_AND_OTHER_INPUTS
    older = dataclasses.replace(current, engine_version="0.2.0")
    assert _attribute(upgrade.encode_input(older), current) is C.UPGRADE_ONLY  # stamp only
    row = attribution_row(
        posting_id=uuid4(),
        attempt_id=ATTEMPT,
        group_id=GROUP,
        computation_id=uuid4(),
        previous_computation_id=None,
        previous_evidence=same,
        current=current,
        sampled=True,
        origin_periods={},
        now=T0,
    )
    assert row.input_comparison["transform_id"] is not None and row.sampled


# --- frozen dataset and register (R7) ------------------------------------------------------------


def _attempt(entities: tuple[UUID, ...]) -> AttemptFacts:
    return AttemptFacts(
        attempt_id=ATTEMPT,
        release_validation_id=UUID(int=5),
        attempt_no=1,
        effective_level="MAJOR",
        engine_release_id=UUID(int=6),
        source_engine_release_id=UUID(int=7),
        seed=20260912,
        population={"groups": 2, "sampled": 1},
        required_entity_ids=entities,
    )


def _rows() -> list[GroupDatasetRow]:
    return [
        GroupDatasetRow(
            UUID(int=1),
            "OPEN_ACTIVITY",
            (("ASC606", "TIME_ELAPSED"),),
            UUID(int=11),
            "COMPLETE",
            "DIFFERENCES",
            "L1_DIFFERENCES",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            {"M": 1, "P": 0, "T": 0, "R": 3},
            (
                {
                    "path": "books[0].contract_version.columns.transaction_price",
                    "category": "M",
                    "before": "100.00",
                    "after": "101.00",
                },
            ),
        ),
        GroupDatasetRow(
            UUID(int=2),
            "SAMPLED",
            (),
            None,
            "COMPLETE",
            "NO_SOURCE",
            "NO_SOURCE",
            None,
            None,
            None,
            None,
            None,
            (),
        ),
    ]


def test_dataset_is_frozen_and_the_report_derives_from_it_alone() -> None:
    entities = (UUID(int=21), UUID(int=22))
    data, digest = build_validation_dataset(_attempt(entities), _rows())
    again, digest_again = build_validation_dataset(_attempt(entities), list(reversed(_rows())))
    assert data == again and digest == digest_again  # order-insensitive, deterministic
    report = upgrade_validation_report(data)
    assert report.control_totals["groups"] == 2 and report.control_totals["rows"] == 3
    assert report.control_totals["outcomes"] == {"DIFFERENCES": 1, "NO_SOURCE": 1}
    group_row = next(r for r in report.rows if r["row_key"] == f"group:{UUID(int=1)}")
    assert group_row["M"] == 1 and group_row["R"] == 3 and group_row["outcome"] == "DIFFERENCES"
    difference = next(r for r in report.rows if str(r["row_key"]).startswith("difference:"))
    assert difference["expected_output_sha256"] == "100.00"  # signed before/after kept
    assert difference["actual_output_sha256"] == "101.00" and difference["M"] == 1
    assert upgrade_validation_report(data) == report  # a rerun reads the bytes only
    content = approval_content_sha256(
        dataset_sha256=digest, attempt_id=ATTEMPT, required_entity_ids=entities
    )
    assert content != approval_content_sha256(
        dataset_sha256=digest, attempt_id=ATTEMPT, required_entity_ids=entities[:1]
    )
    with pytest.raises(ValueError):
        upgrade_validation_report(b'{"dataset_format": 2}')


def test_register_is_exact_as_of_known_at() -> None:
    (pending,) = _seed()
    calendar = _jan_mar_jun("closed")
    march_posting = uuid4()
    deferred = portion_transition(
        pending,
        computation_id=uuid4(),
        posting_ids=[march_posting],
        unresolved=unresolved_origins(calendar, BOOK, ("FY2026-P01", "FY2026-P06")),
        now=T0 + timedelta(days=1),
    )
    assert deferred is not None
    attribution = attribution_row(
        posting_id=march_posting,
        attempt_id=ATTEMPT,
        group_id=GROUP,
        computation_id=deferred.computation_id or uuid4(),
        previous_computation_id=None,
        previous_evidence=None,
        current=minimal_contract(),
        sampled=True,
        origin_periods={},
        now=T0 + timedelta(days=1),
    )
    before = register_rows([pending, deferred], [attribution], known_at=T0)
    assert [r["upgrade_state"] for r in before] == ["PENDING"] and before[0]["posting_ids"] == []
    after = register_rows([pending, deferred], [attribution], known_at=T0 + timedelta(days=2))
    (row,) = after
    assert row["upgrade_state"] == "DEFERRED_NO_OPEN_PERIOD" and row["group_terminal"] is False
    assert row["unresolved_origin_period_keys"] == ["FY2026-P06"]
    assert row["posting_ids"] == [str(march_posting)] and row["causes"] == ["UPGRADE_CONTEXT"]
    assert row["sampled"] is True
