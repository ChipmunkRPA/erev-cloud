"""The mark of a rate set version's approval, without a database (item FX-REPUBLISH-DIRTY-1; 04
T-REF-11 "The groups a changed rate reaches" and T-CON-03 ``dirty_trigger``, rev 1.297; 05 RCP-17
rev 1.206; dev-guide DG-KRN-DB-08 rev 1.281): the statements of ``close.rate_reach`` and its hook
as rules. The two pure rules are ``test_rate_reach.py``; the database witnesses are
``tests/domain/contracts/test_fx_republish_mark.py`` and
``tests/domain/close/test_rate_reach_db.py``.

- The changed keys are ``close.rate_changes.changes_statement``: one statement of what a version
  changes, for the finding and for the mark.
- A key reaches the entities whose functional currency is its quote currency, and the groups in
  its base currency for which such an entity posts — the pair, both sides.
- The entity a group is reached through is the entity of THAT reach: the performing clause is
  correlated to the reach row, not joined to the whole reach.
- The group rows are taken ``FOR UPDATE`` in ascending id order, in one statement that waits.
- The mark never moves a stamp back and carries the trigger; a version that reaches no group
  writes nothing.
- The reference commands register the mark in front of the finding.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects
from erev_api.db.tables import contract_version_balance
from erev_api.domain.close import rate_changes, rate_reach
from erev_api.domain.reference import commands as reference_commands
from erev_engine.dates import POSTABLE_STATES
from sqlalchemy.dialects import postgresql

TENANT = UUID(int=1)
VERSION = UUID(int=7)
REQUEST = UUID(int=8)
NOW = datetime(2026, 9, 3, 14, 0, tzinfo=UTC)
GROUPS = (UUID(int=21), UUID(int=22))
PROTOCOL_LIMIT = 65_535  # bound values of one statement (Bind: Int16 count, unsigned)


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


# --- which rows -----------------------------------------------------------------------------------


def test_the_changed_keys_are_the_statement_of_what_a_version_changes() -> None:
    """04 T-REF-11: two items state one fact once. The reach reads ``changes_statement`` whole."""
    changed = _sql(rate_changes.changes_statement(VERSION))
    assert f"FROM ({changed}) AS changed JOIN erev.legal_entity" in _sql(
        rate_reach.reach_statement(VERSION)
    )


def test_a_key_reaches_the_entities_of_its_quote_and_the_groups_of_its_base() -> None:
    reach = _sql(rate_reach.reach_statement(VERSION))
    assert (
        ") AS changed JOIN erev.legal_entity"
        " ON erev.legal_entity.functional_currency = changed.quote_currency"
        " JOIN erev.period AS reach_first" in reach
    )
    candidates = _sql(rate_reach.candidates_statement(VERSION))
    assert (
        " FROM erev.combination_group JOIN reach"
        " ON erev.combination_group.transaction_currency = reach.base_currency"
        " WHERE (erev.combination_group.head_computation_id IS NOT NULL"
        " OR erev.combination_group.dirty_since IS NOT NULL) AND " in candidates
    )


def test_the_reach_of_a_key_is_stated_as_the_rule_has_it() -> None:
    """``reach_of`` in SQL. A period rate reaches the period it is dated the last day of; a spot
    rate, from the period that holds its date to the period that holds the day before the pair's
    next spot date in force — of any set — and onward where there is none (``reach_to`` NULL);
    a key dated after the entity's last postable day reaches nothing."""
    statement = rate_reach.reach_statement(VERSION)
    text = _sql(statement)
    assert (
        " CASE WHEN (CAST(changed.rate_type AS TEXT) = %(param_1)s) THEN reach_last.end_date"
        " ELSE reach_first.end_date END AS reach_to FROM (" in text
    )
    next_spot = (
        ") AS in_force WHERE CAST(in_force.rate_type AS TEXT) = %(param_2)s"
        " AND in_force.base_currency = changed.base_currency"
        " AND in_force.quote_currency = changed.quote_currency"
        " AND in_force.effective_date > changed.effective_date) - %(param_3)s"
    )
    assert text.count(next_spot) == 2  # the day before it lies in ``reach_last``: start, end
    assert "in_force.code" not in text  # the next spot date of the pair, in any set
    assert (
        " WHERE (CAST(changed.rate_type AS TEXT) = %(param_1)s"
        " OR reach_first.end_date = changed.effective_date)"
        " AND ((SELECT max(erev.period_state.period_end_date) AS max_1 FROM erev.period_state"
        " WHERE erev.period_state.tenant_id = erev.legal_entity.tenant_id"
        " AND erev.period_state.entity_id = erev.legal_entity.id"
        " AND erev.period_state.state IN (__[POSTCOMPILE_state_1])) IS NULL"
        " OR changed.effective_date <= (SELECT max(" in text
    )
    params = statement.compile(dialect=postgresql.dialect()).params
    assert (params["param_1"], params["param_2"], params["param_3"]) == ("spot", "spot", 1)
    assert sorted(params["state_1"]) == sorted(POSTABLE_STATES)


def test_a_group_is_reached_through_the_entity_of_that_reach() -> None:
    """The contracting entity of a member, or the performing entity of one of its obligations —
    of the reach row the group is joined to. Measured on the statement before its correction:
    the performing clause read ``FROM erev.obligation_version, reach``, the entity of ANY reach
    row, so a group could be marked for a key of an entity that does not post for it."""
    text = _sql(rate_reach.candidates_statement(VERSION))
    assert (
        "(erev.contract.contracting_entity_id = reach.entity_id OR (EXISTS (SELECT * FROM"
        " erev.obligation_version WHERE erev.obligation_version.tenant_id ="
        " erev.contract.tenant_id AND erev.obligation_version.contract_id = erev.contract.id AND"
        " erev.obligation_version.performing_entity_id = reach.entity_id)))" in text
    )
    # ``reach`` is named once as a relation — the join of the groups — and nowhere joined again
    assert text.count(" JOIN reach ON ") == 1 and ", reach " not in text


def test_the_positions_are_the_balances_a_version_states_in_both_currencies() -> None:
    """A rate enters a balance the version also states in the functional currency (04 T-CON-09:
    nine of them, the layers stage 12 keeps, remeasures or settles). A cumulative flow, the net
    position, a current part, a cost asset and a loss provision have no functional column: no
    rate is read for them, and none of them keeps a group in a reach."""
    names = [column.name for column in contract_version_balance.columns]
    stated = [
        name[: -len("_functional")] + "_txn" for name in names if name.endswith("_functional")
    ]
    assert len(stated) == 9 and set(stated) <= set(names)
    assert sorted(rate_reach.POSITIONS) == sorted(stated)


def test_a_group_is_at_work_by_a_position_an_event_a_schedule_line_or_a_sealed_line() -> None:
    text = _sql(rate_reach.candidates_statement(VERSION))
    for position in rate_reach.POSITIONS:
        assert f"erev.contract_version_balance.{position} != %({position}_1)s" in text, position
    assert (
        "erev.contract_version.contract_computation_id ="
        " erev.combination_group.head_computation_id" in text
    )
    for table in ("contract_event", "schedule_line", "subledger_line"):
        column = "effective_date" if table == "contract_event" else "period_end_date"
        assert f"AND erev.{table}.{column} >= reach.reach_from)" in text, table
    # begun: by the group's inception, or by an event of a member, on or before the reach's end
    assert (
        "(reach.reach_to IS NULL OR erev.combination_group.inception_date <= reach.reach_to"
        " OR (EXISTS (SELECT * FROM erev.contract_event WHERE " in text
    )
    assert "AND erev.contract_event.effective_date <= reach.reach_to))" in text


def test_the_group_rows_are_taken_for_update_in_ascending_id_order_and_waited_for() -> None:
    """dev-guide DG-KRN-DB-08 (1): one globally ascending id order for every path that locks
    group rows. A computation that holds a row is waited for — its group is marked once it has
    ended — so the statement neither skips a held row nor refuses over it."""
    statement = rate_reach.rows_statement(TENANT, VERSION)
    text = _sql(statement)
    assert text.startswith("WITH reach AS (SELECT DISTINCT erev.legal_entity.id AS entity_id, ")
    assert (
        " SELECT erev.combination_group.id FROM erev.combination_group"
        " WHERE erev.combination_group.tenant_id = %(tenant_id_1)s::UUID"
        " AND erev.combination_group.id IN (SELECT candidates.group_id FROM (" in text
    )
    assert text.endswith(") AS candidates) ORDER BY erev.combination_group.id FOR UPDATE")
    assert "NOWAIT" not in text and "SKIP LOCKED" not in text
    assert statement.compile(dialect=postgresql.dialect()).params["tenant_id_1"] == TENANT


# --- the hook -------------------------------------------------------------------------------------


class _Session:
    """A session that answers the lock statement with ``rows`` and records what it is asked."""

    def __init__(self, rows: tuple[UUID, ...]) -> None:
        self.rows = rows
        self.statements: list[Any] = []

    def scalars(self, statement: Any) -> Any:
        self.statements.append(statement)
        rows = self.rows
        return type("R", (), {"all": lambda self: list(rows)})()

    def execute(self, statement: Any, parameters: Any = None) -> Any:
        self.statements.append(statement)
        return None


class _Approval:
    def __init__(self, rows: tuple[UUID, ...]) -> None:
        self.session = _Session(rows)
        self.now = NOW
        self.principal = type(
            "P", (), {"id": UUID(int=3), "tenant_id": TENANT, "kind": type("K", (), {"value": "U"})}
        )


def test_a_version_that_reaches_no_group_takes_no_row_and_writes_nothing() -> None:
    approval = _Approval(())
    assert rate_reach.marked(approval, VERSION, REQUEST) == 0  # type: ignore[arg-type]
    (only,) = approval.session.statements
    assert _sql(only).endswith(" ORDER BY erev.combination_group.id FOR UPDATE")


def test_the_mark_never_moves_a_stamp_back_and_carries_the_trigger() -> None:
    """05 RCP-17 rev 1.207: each writer stamps the later of the stamp that stands and its own
    instant. The rows that were locked are the rows that are written, and no other."""
    approval = _Approval(GROUPS)
    assert rate_reach.marked(approval, VERSION, REQUEST) == 2  # type: ignore[arg-type]
    _, written = approval.session.statements
    compiled = written.compile(dialect=postgresql.dialect())
    text = " ".join(str(compiled).split())
    assert text.startswith(
        "UPDATE erev.combination_group SET"
        " dirty_since=greatest(erev.combination_group.dirty_since, %(greatest_1)s),"
    )
    assert "dirty_trigger=%(dirty_trigger)s" in text
    assert "row_version=(erev.combination_group.row_version + %(row_version_1)s)" in text
    assert text.endswith(
        " WHERE erev.combination_group.tenant_id = %(tenant_id_1)s::UUID"
        " AND erev.combination_group.id = ANY (%(param_1)s::UUID[])"
    )
    params = compiled.params
    assert (params["greatest_1"], params["dirty_trigger"]) == (NOW, "FX_REPUBLISH")
    assert (params["tenant_id_1"], tuple(params["param_1"])) == (TENANT, GROUPS)
    assert (params["updated_at"], params["updated_by"], params["updated_by_kind"]) == (
        NOW,
        UUID(int=3),
        "U",
    )


@pytest.mark.parametrize("count", [2, PROTOCOL_LIMIT + 4_465])
def test_the_marks_update_binds_its_groups_as_one_value_whatever_their_number(count: int) -> None:
    """A version may reach more groups than the bound values one statement can carry. The update
    names the rows it locked as ONE value, an array (``= ANY``), as the journals' drill does
    since index 265 (``journals.summarise.among``); the lock statement names none, it reads them
    by a subquery. An ``IN`` list binds one value a group, and past the protocol's bound the
    driver refuses the statement: the approval of a version that reaches 70,000 groups could
    not be sent (read, 2026-10-03; the supervisor's reading of ``marked``)."""
    groups = tuple(UUID(int=number) for number in range(100, 100 + count))
    approval = _Approval(groups)
    assert rate_reach.marked(approval, VERSION, REQUEST) == count  # type: ignore[arg-type]
    locking, written = approval.session.statements
    compiled = written.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
    )
    values = list(compiled.params.values())
    assert list(groups) in values  # the one value that holds them all
    assert len(values) == 8, len(values)  # six of the SET clause, the tenant and the array
    text = " ".join(str(compiled).split())
    assert "erev.combination_group.id = ANY (" in text
    assert "erev.combination_group.id IN (" not in text
    taken = locking.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
    )
    assert not set(groups) & {value for value in taken.params.values() if isinstance(value, UUID)}
    assert len(taken.params) < 100, len(taken.params)  # the same statement whatever it finds


def test_the_reference_commands_register_the_mark_in_front_of_the_finding() -> None:
    """dev-guide DG-KRN-DB-08 rev 1.281: group rows before period-state rows, as a computation
    takes them. The kernel runs the hooks of an approval in the order of their registration."""
    assert reference_commands.rate_reach is rate_reach
    hooks = subjects.FX_RATE_VERSION_APPROVED
    assert hooks.index(rate_reach.marked) < hooks.index(rate_changes.approved)
    before = list(hooks)
    subjects.register_fx_rate_version_approved(rate_reach.marked)
    assert before == hooks  # registering again changes nothing, and moves nothing
