"""Period-bound exceptions preserve historical approvals and member/book isolation."""

from datetime import UTC, datetime
from uuid import UUID

from erev_api.domain.contracts.policy_inputs import period_scoped_inputs
from erev_engine.bundle import contract_period_key

CODE = "fx.cl_historical_layering"
C1, C2 = UUID(int=1), UUID(int=2)


def instant(month: int, day: int = 1, hour: int = 0) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


def row(n: int, approved_at: datetime, status: str, value: str, contract: UUID = C1):
    return dict(
        id=UUID(int=n),
        contract_id=contract,
        obligation_id=None,
        level="CONTRACT",
        policy_key=CODE,
        status=status,
        approved_at=approved_at,
        value=value,
    )


def inputs(rows, known_at=None, book="ASC606"):
    return period_scoped_inputs(
        rows,
        book_code=book,
        contracts={C1: ("A", "US"), C2: ("B", "UK")},
        known_at=known_at or instant(10, 15),
        period_cutoffs=[
            ("US", "AUG", instant(9)),
            ("US", "SEP", instant(10)),
            ("US", "OCT", instant(11)),
            ("UK", "SEP", instant(10)),
        ],
    )


def test_approval_is_effective_only_in_its_period_and_successors_preserve_history():
    rows = [
        row(10, instant(9, 4), "SUPERSEDED", "DISABLED_REMEASURE_AS_MONETARY"),
        row(11, instant(10, 4), "APPROVED", "ENABLED"),
    ]
    found = {p.subject_key: p for p in inputs(rows)}
    september = found[contract_period_key("A", "US", "SEP")]
    assert september.value == "DISABLED_REMEASURE_AS_MONETARY"
    assert september.source_ref == str(UUID(int=10))
    assert found[contract_period_key("A", "US", "OCT")].value == "ENABLED"
    assert len(found) == 2  # no August rewrite, other member or entity leakage
    historical = inputs(rows, known_at=instant(9, 15))
    assert {p.value for p in historical} == {"DISABLED_REMEASURE_AS_MONETARY"}
    assert inputs(rows, known_at=instant(9, 3)) == ()
    assert inputs(rows, book="IFRS15") == ()


def test_unapproved_foreign_and_obligation_rows_are_not_admitted():
    rows = [
        row(10, instant(9, 4), "DRAFT", "ENABLED"),
        row(11, instant(9, 4), "SUBMITTED", "ENABLED"),
        row(12, instant(9, 4), "APPROVED", "ENABLED", UUID(int=99)),
        {**row(13, instant(9, 4), "APPROVED", "ENABLED"), "obligation_id": UUID(int=3)},
        {**row(14, instant(9, 4), "APPROVED", "ENABLED"), "level": "OBLIGATION"},
    ]
    assert inputs(rows) == ()


def test_equal_approval_instants_choose_current_then_id_independently_of_input_order():
    rows = [
        row(100, instant(9, 4), "SUPERSEDED", "ENABLED"),
        row(11, instant(9, 4), "APPROVED", "DISABLED_REMEASURE_AS_MONETARY"),
    ]
    assert inputs(rows) == inputs(list(reversed(rows)))
    assert {p.source_ref for p in inputs(rows)} == {str(UUID(int=11))}


def test_entity_local_period_cutoff_is_inclusive_without_leaking_later_approval():
    # End of September in a west-of-UTC entity is already October in UTC.
    cutoff = instant(10, 1, 7)
    rows = [
        row(10, instant(10, 1, 6), "SUPERSEDED", "ENABLED"),
        row(11, cutoff, "SUPERSEDED", "DISABLED_REMEASURE_AS_MONETARY"),
        row(12, instant(10, 1, 8), "APPROVED", "ENABLED"),
    ]
    found = period_scoped_inputs(
        rows,
        book_code="ASC606",
        contracts={C1: ("A", "US")},
        period_cutoffs=[("US", "SEP", cutoff)],
        known_at=instant(10, 2),
    )
    assert len(found) == 1
    assert found[0].source_ref == str(UUID(int=11))
