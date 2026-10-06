"""The drill's id lists as pure rules (item SUBLEDGER-LINE-JOURNAL-RUN-1; the independent review's
point 10, measured through the product on 2026-10-02). CPU-only: the two statements that are
handed the ids of subledger lines — the page of a journal line's drill and the read of the lines
a run took over — bind them as ONE value, an array, whatever their number. Bound one value an
id, a statement ends at the 65,535 bound values the PostgreSQL protocol carries: the drill of a
journal line of 66,000 source lines answered 503. The database witness is
``tests/domain/journals/test_drill_record.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.db.tables import subledger_line
from erev_api.domain.journals import queries, summarise, validation
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

DOCS: Final = Path(__file__).resolve().parents[4] / "docs"
PROTOCOL_LIMIT: Final = 65_535  # bound values of one statement (Bind: Int16 count, unsigned)
ENTITY, PERIOD = UUID(int=1), UUID(int=2)


def _bound(statement: Select[Any]) -> tuple[str, list[Any]]:
    """The statement as the driver would receive it — every expanding list rendered — and its
    bound values."""
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
    )
    return str(compiled), list(compiled.params.values())


@pytest.mark.parametrize("count", [0, 3, PROTOCOL_LIMIT + 4_465])
def test_the_ids_of_the_lines_are_one_bound_value_whatever_their_number(count: int) -> None:
    """``summarise.among``: the ids travel as one array, so a drill over 70,000 lines binds as
    many values as a drill over three — and no statement of the drill can meet the protocol's
    bound. An expanding ``IN`` list binds one value a line."""
    ids = [UUID(int=number) for number in range(100, 100 + count)]
    statements = {
        "the drill's page": queries.drill_statement(ids),
        "the lines a run took over": summarise.left_out_statement(
            entity_id=ENTITY, book_codes=["ASC606", "LEGACY"], period_id=PERIOD, line_ids=ids
        ),
    }
    for name, statement in statements.items():
        text, values = _bound(statement)
        assert ids in values, name  # the one value that holds them all
        assert len(values) < 10, (name, len(values))
        assert "subledger_line.id = ANY (" in text.replace("erev.", ""), name
        assert "subledger_line.id IN (" not in text.replace("erev.", ""), name


def test_an_expanding_list_binds_one_value_a_line() -> None:
    """What the two statements did before: ``column.in_(ids)`` renders one bound value an id, so
    its number grows with the journal line and passes the protocol's bound."""
    ids = [UUID(int=number) for number in range(100, 100 + PROTOCOL_LIMIT + 1)]
    compiled = (
        subledger_line.select()
        .where(subledger_line.c.id.in_(ids))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True})
    )
    assert len(compiled.params) == PROTOCOL_LIMIT + 1
    among = (
        subledger_line.select()
        .where(summarise.among(subledger_line.c.id, ids))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True})
    )
    assert len(among.params) == 1


class _Kept:
    """A session that keeps the statements it is handed and answers no row."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    def execute(self, statement: Any) -> _Kept:
        self.statements.append(statement)
        return self

    def tuples(self) -> list[Any]:
        return []

    def all(self) -> list[Any]:
        return []

    def mappings(self) -> list[Any]:
        return []


def test_three_more_lists_of_the_package_are_one_bound_value_each() -> None:
    """The same bound stood in three more statements of the package (read on 2026-10-02; the
    supervisor's word of that day): ``summarise.open_holds`` — the contracts of a run's range,
    on the path of every calculation —, ``queries.batch_outs`` — the chunks of a page of runs —
    and ``validation.names_of`` — the contracts and the obligations of a failed generation's
    findings. Each binds its ids as one array value."""
    ids = [UUID(int=number) for number in range(100, 100 + PROTOCOL_LIMIT + 4_465)]

    holds = _Kept()
    assert summarise.open_holds(holds, ids) == {}  # type: ignore[arg-type]

    chunks = _Kept()
    with pytest.raises(KeyError):  # the rows are stubs: the read of the acknowledgements is first
        queries.batch_outs(chunks, [{"id": batch_id} for batch_id in ids])  # type: ignore[arg-type]

    names = _Kept()
    findings = [
        validation.LineFinding(
            code="ACCOUNT_MAPPING_MISSING",
            problem="unmapped-account-role",
            line_id=UUID(int=number),
            account_role="REVENUE",
            account_code="4000",
            message="",
            contract_id=found,
            obligation_id=found,
        )
        for number, found in enumerate(ids)
    ]
    assert set(validation.names_of(names, findings).values()) == {(None, None)}  # type: ignore[arg-type]

    kept = {
        "the open holds of a run's contracts": holds.statements,
        "the acknowledgements of a page's chunks": chunks.statements,
        "the names of the findings' contracts and obligations": names.statements,
    }
    assert [len(statements) for statements in kept.values()] == [1, 1, 2]
    for name, statements in kept.items():
        for statement in statements:
            text, values = _bound(statement)
            assert ids in values, name
            assert len(values) < 10, (name, len(values))
            assert " = ANY (" in text and " IN (" not in text, name


def test_the_rows_state_the_bound_and_the_limit_that_stands() -> None:
    """04 T-SL-06 drill-back (rev 1.288) states the bound that is gone and the limit that stands
    — a page of the drill still reads its run's whole range (register index 278, held) — and
    fragment 14 rev 1.77 names the witnesses, every rule of this module among them."""
    model = (DOCS / "04-DATA_MODEL.md").read_text(encoding="utf-8")
    for sentence in (
        "a statement carries at most 65,535 bound values",
        "The ids are bound as one array value, whatever their number — in the drill's page and "
        "in the read of the lines a run took over.",
        "A limit that stands (register index 278, held): a page of the drill still reads every "
        "line of its run's range",
        "Three more statements of the journals package were handed ids with no bound on their "
        "number, bound them one value an id and now bind them the same way",
        "(`summarise.open_holds`); the acknowledgements of the chunks of a page of runs "
        "(`queries.batch_outs`); and the names of the contracts and the obligations of a failed "
        "generation's findings (`validation.names_of`)",
    ):
        assert model.count(sentence) == 1, sentence
    fragment = (DOCS / "build-spec/14-close-reports-ai-demo-release.md").read_text(encoding="utf-8")
    assert (
        fragment.count(
            "`backend/tests/domain/journals/test_drill_record.py::test_the_drills_statements_run_"
            "over_more_lines_than_can_be_bound_one_by_one`"
        )
        == 1
    )
    assert (
        fragment.count(
            "`::test_the_calculation_the_runs_list_and_the_findings_bind_their_ids_as_one_value`"
        )
        == 1
    )
    assert fragment.count("`backend/tests/unit/journals/test_drill_bound_rules.py::") == 1
    rules = sorted(name for name in globals() if name.startswith("test_"))
    assert len(rules) == 4
    assert all(fragment.count(f"::{name}`") == 1 for name in rules), rules
