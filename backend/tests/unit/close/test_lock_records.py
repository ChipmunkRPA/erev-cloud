"""The lock record whose datasets stand, without a database (item PERMLOCK-DATASETS-1; the
supervisor's ruling of 2026-10-02 16:16; 04 API-S-Period ``dataset_lock`` rev 1.301): the rule of
``close.lock_records`` as its statements state it, and the period reads that answer the member.
The database witnesses are ``tests/domain/close/test_dataset_lock.py``.

- The record is the current one while that is a ``LOCK``, the one a ``PERMANENT_LOCK`` names as
  ``previous_lock_id``, and none for a ``REOPEN`` — and it is a ``LOCK`` of the same tenant,
  entity, book and period, or none.
- For an entity, book and period it is read through the state row and its current record.
- API-S-Period reads the current lock and the dataset lock in ONE statement, for one period and
  for a page, and names the member in every row.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from erev_api.db.tables import period_lock
from erev_api.domain.close import lock_records, queries
from erev_api.domain.reference import queries as reference_queries
from erev_api.schemas.periods import PeriodLockOut, PeriodOut
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

ENTITY = UUID(int=0xE1)
PERIOD = UUID(int=0xA8)
STATE = UUID(int=0x51)
LOCK = UUID(int=0x10)
PERMANENT = UUID(int=0x20)
REOPEN = UUID(int=0x30)
MAYA = UUID(int=0x77)
AT = datetime(2026, 9, 4, 13, 0, tzinfo=UTC)
NAMED = (
    "dataset_lock.id = CASE WHEN (erev.period_lock.kind = 'LOCK') THEN erev.period_lock.id "
    "WHEN (erev.period_lock.kind = 'PERMANENT_LOCK') THEN erev.period_lock.previous_lock_id END"
)
SAME_SCOPE = (
    "dataset_lock.tenant_id = erev.period_lock.tenant_id",
    "dataset_lock.kind = 'LOCK'",
    "dataset_lock.entity_id = erev.period_lock.entity_id",
    "dataset_lock.book_code = erev.period_lock.book_code",
    "dataset_lock.period_id = erev.period_lock.period_id",
)


def _sql(statement: Any) -> str:
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compiled).split())


# --- the rule -------------------------------------------------------------------------------------


def test_the_record_is_the_lock_itself_or_the_one_a_permanent_lock_names() -> None:
    """A ``LOCK`` names itself, a ``PERMANENT_LOCK`` the record it follows; the ``CASE`` has no
    other branch, so a ``REOPEN`` record — and any kind added later — finds no row."""
    rule = _sql(lock_records.stands_for())
    assert NAMED in rule
    assert rule.count("WHEN") == 2 and "ELSE" not in rule
    assert "REOPEN" not in rule


def test_the_record_found_is_a_lock_of_the_same_tenant_entity_book_and_period() -> None:
    """Fail closed: a record that names another kind, or a lock of another entity, book or
    period, finds nothing — six conditions, all of them ``AND``."""
    rule = _sql(lock_records.stands_for())
    for condition in SAME_SCOPE:
        assert condition in rule, condition
    assert rule.count(" AND ") == 5 and " OR " not in rule


def test_the_rule_reads_the_current_record_it_is_given() -> None:
    """``stands_for`` joins to whichever table expression holds the current record."""
    current = period_lock.alias("current_lock")
    rule = _sql(lock_records.stands_for(current))
    assert "erev.period_lock." not in rule
    assert NAMED.replace("erev.period_lock.", "current_lock.") in rule


def test_the_dataset_lock_of_a_scope_is_read_through_the_state_row_and_its_current_record() -> None:
    """One statement, inner joins: the state row of the entity, book and period, the record it
    names as current, and the record that stands — no row where none stands."""
    statement = _sql(
        lock_records.dataset_lock_of(entity_id=ENTITY, book_code="ASC606", period_id=PERIOD)
    )
    assert statement.startswith(
        "SELECT dataset_lock.id FROM erev.period_state JOIN erev.period_lock ON "
        "erev.period_lock.tenant_id = erev.period_state.tenant_id AND erev.period_lock.id = "
        "erev.period_state.current_lock_id JOIN erev.period_lock AS dataset_lock ON "
    )
    assert "OUTER" not in statement and NAMED in statement
    assert statement.endswith(
        f"WHERE erev.period_state.entity_id = '{ENTITY}' AND erev.period_state.book_code = "
        f"'ASC606' AND erev.period_state.period_id = '{PERIOD}'"
    )


# --- API-S-Period ---------------------------------------------------------------------------------


class _Session:
    """Answers each statement with the next list of rows and keeps the statements."""

    def __init__(self, *answers: list[dict[str, Any]]) -> None:
        self.answers = list(answers)
        self.statements: list[str] = []

    def execute(self, statement: Any) -> Any:
        self.statements.append(_sql(statement))
        rows = self.answers.pop(0)
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: rows[0], all=rows))


def _record(lock_id: UUID | None, kind: str | None, prefix: str = "") -> dict[str, Any]:
    """The columns of one T-CLS-04 record as ``_PERIOD_LOCKS`` labels them; every one NULL where
    the outer join found no record."""
    found = lock_id is not None
    return {
        f"{prefix}id": lock_id,
        f"{prefix}kind": kind,
        f"{prefix}created_at": AT if found else None,
        f"{prefix}created_by": MAYA if found else None,
        f"{prefix}ledger_head_chain_seq": 7 if found else None,
        f"{prefix}snapshot_manifest_sha256": ("ab" * 32 if kind == "LOCK" else None),
        f"{prefix}created_by_kind": "USER" if found else None,
        f"{prefix}created_by__named": {"kind": "USER", "display_name": "Maya"} if found else None,
    }


def _row(current: tuple[UUID, str], standing: tuple[UUID, str] | None) -> dict[str, Any]:
    dataset = (None, None) if standing is None else standing
    return {**_record(*current), **_record(*dataset, prefix="dataset_lock__")}


def _member(lock_id: UUID, kind: str) -> dict[str, Any]:
    return {
        "id": lock_id,
        "kind": kind,
        "created_at": AT,
        "created_by": {"id": MAYA, "kind": "USER", "display_name": "Maya"},
        "ledger_head_chain_seq": 7,
        "snapshot_manifest_sha256": "ab" * 32 if kind == "LOCK" else None,
    }


def test_the_statement_reads_both_records_with_who_created_each() -> None:
    """The six members and the creator of the current record, and the same of the record whose
    datasets stand under the prefix ``dataset_lock__``, over ONE outer join by the rule."""
    labels = [column.name for column in queries._PERIOD_LOCKS]
    own = [*queries._LOCK_MEMBERS, "created_by_kind", "created_by__named"]
    assert labels == [*own, *(f"dataset_lock__{name}" for name in own)]
    assert tuple(PeriodLockOut.model_fields) == queries._LOCK_MEMBERS
    joined = _sql(select(period_lock.c.id).select_from(queries._WITH_DATASET_LOCK))
    head, rule = joined.split(" LEFT OUTER JOIN erev.period_lock AS dataset_lock ON ")
    assert head == _sql(select(period_lock.c.id))
    assert rule == _sql(lock_records.stands_for())


def test_one_period_reads_its_two_records_in_one_statement() -> None:
    """``period_locks``: a ``LOCK`` is both records; a ``PERMANENT_LOCK`` names the lock it
    follows; under a ``REOPEN`` no lock's datasets stand; a period never locked reads nothing."""
    scope = SimpleNamespace(current_lock_id=PERMANENT)
    session = _Session([_row((PERMANENT, "PERMANENT_LOCK"), (LOCK, "LOCK"))])
    assert queries.period_locks(session, scope) == (  # type: ignore[arg-type]
        _member(PERMANENT, "PERMANENT_LOCK"),
        _member(LOCK, "LOCK"),
    )
    (statement,) = session.statements
    assert "LEFT OUTER JOIN erev.period_lock AS dataset_lock ON" in statement
    assert statement.endswith(f"WHERE erev.period_lock.id = '{PERMANENT}'")

    closed = _Session([_row((LOCK, "LOCK"), (LOCK, "LOCK"))])
    current, standing = queries.period_locks(closed, SimpleNamespace(current_lock_id=LOCK))  # type: ignore[arg-type]
    assert current == standing == _member(LOCK, "LOCK")

    reopened = _Session([_row((REOPEN, "REOPEN"), None)])
    assert queries.period_locks(reopened, SimpleNamespace(current_lock_id=REOPEN)) == (  # type: ignore[arg-type]
        _member(REOPEN, "REOPEN"),
        None,
    )

    never = _Session()
    assert queries.period_locks(never, SimpleNamespace(current_lock_id=None)) == (None, None)  # type: ignore[arg-type]
    assert never.statements == []


def test_a_page_reads_the_two_records_of_every_row_in_one_statement() -> None:
    """``_locks_of``: one statement for the page, by the state rows' current records; a state
    that names no lock has no entry."""
    other = UUID(int=0x52)
    rows = [
        {"of_state__id": STATE, **_row((PERMANENT, "PERMANENT_LOCK"), (LOCK, "LOCK"))},
        {"of_state__id": other, **_row((REOPEN, "REOPEN"), None)},
    ]

    class _Page(_Session):
        def execute(self, statement: Any) -> Any:
            self.statements.append(_sql(statement))
            return SimpleNamespace(mappings=lambda: self.answers.pop(0))

    session = _Page(rows)
    found = queries._locks_of(session, [STATE, other, UUID(int=0x53)])  # type: ignore[arg-type]
    assert found == {
        STATE: (_member(PERMANENT, "PERMANENT_LOCK"), _member(LOCK, "LOCK")),
        other: (_member(REOPEN, "REOPEN"), None),
    }
    (statement,) = session.statements
    assert (
        "FROM erev.period_state JOIN erev.period_lock ON erev.period_lock.tenant_id = "
        "erev.period_state.tenant_id AND erev.period_lock.id = erev.period_state.current_lock_id "
        "LEFT OUTER JOIN erev.period_lock AS dataset_lock ON"
    ) in statement


def test_every_row_of_the_schema_names_the_member() -> None:
    """The base row states ``dataset_lock`` null beside ``current_lock``; the schema carries it
    as the same object, optional for a reader built before it."""
    row = {
        "id": STATE,
        "entity_id": ENTITY,
        "entity_code": "AVM-US",
        "entity_name": "Avenmoor US",
        "book_code": "ASC606",
        "period_id": PERIOD,
        "period_key": "FY2026-P08",
        "period_name": "Aug 2026",
        "fiscal_year": 2026,
        "period_no": 8,
        "quarter_no": 3,
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 31),
        "state": "permanently_locked",
        "state_changed_at": AT,
        "is_first_open": False,
        "row_version": 4,
        "follows_book_code": None,
        "follows_state": None,
    }
    shown = reference_queries.period_out(row)
    assert (shown["current_lock"], shown["dataset_lock"]) == (None, None)
    field = PeriodOut.model_fields["dataset_lock"]
    assert field.annotation == (PeriodLockOut | None) and field.default is None
    assert field.annotation == PeriodOut.model_fields["current_lock"].annotation
    out = PeriodOut.model_validate(
        {
            **shown,
            "current_lock": _member(PERMANENT, "PERMANENT_LOCK"),
            "dataset_lock": _member(LOCK, "LOCK"),
        }
    )
    assert out.dataset_lock is not None and out.dataset_lock.id == LOCK
    assert out.model_dump()["dataset_lock"]["kind"] == "LOCK"
    assert "dataset_lock" not in PeriodOut.model_json_schema()["required"]
