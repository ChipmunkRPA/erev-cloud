"""Register index 182 as pure rules (04 §16.7 rev 1.245; the supervisor's rulings of 2026-10-01 and
2026-10-02). CPU-only: how the obligation is joined, what the two schemas admit, where a
counterparty the statement could not name comes from, and under which scope a batch's chunk reads
its references. The database witnesses are ``tests/domain/journals/test_line_reader_scope.py`` and
``tests/api/test_drill_chain.py``.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from erev_api.domain.journals import export, queries, subledger
from erev_api.schemas.journals import JournalLineContractOut
from erev_api.schemas.subledger import SubledgerLineOut
from sqlalchemy.dialects import postgresql

DOCS: Final = Path(__file__).resolve().parents[4] / "docs"
LINE, BATCH, ACCOUNT, CONTRACT, HERE, ELSEWHERE = (UUID(int=number) for number in range(1, 7))
THROUGH_THE_CONTRACT: Final = "obligation.contract_id = erev.contract.id"


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


def _row(**changes: Any) -> dict[str, Any]:
    """A ``lines_statement`` row of an intercompany line at the contract grain."""
    row: dict[str, Any] = {
        "id": LINE,
        "journal_batch_id": BATCH,
        "je_no": "JE-AVM-US-000001",
        "je_type": "automated",
        "line_no": 1,
        "gl_account_id": ACCOUNT,
        "gl_account_code": "1800",
        "account_name": "Intercompany due from",
        "account_role": "INTERCOMPANY_DUE_FROM",
        "dimensions": {},
        "txn_currency": "GBP",
        "functional_currency": "USD",
        "debit_txn": Decimal("4790.62"),
        "credit_txn": Decimal("0.00"),
        "debit_functional": Decimal("6036.18"),
        "credit_functional": Decimal("0.00"),
        "contract_id": CONTRACT,
        "contract_external_id": None,
        "obligation_key": None,
        "legacy_key": None,
        "counterparty_entity_id": ELSEWHERE,
        "counterparty_code": None,
        "counterparty_name": None,
        "origin_period_key": None,
        "is_post_close": False,
        "fx_rate_ids": [],
        "memo": None,
        "source_line_count": 1,
        "source_grouping_sha256": "0" * 64,
    }
    return {**row, **changes}


class _NoStatement:
    """A session that must not be asked."""

    def execute(self, *_: Any, **__: Any) -> Any:
        raise AssertionError("a statement was sent")


def test_the_obligation_is_joined_through_the_contracts_row() -> None:
    """T-CON-10 is RLS-T, the contract RLS-TE: a join by the obligation's id alone would name the
    obligation of a contract whose name the reader is not told. The three statements that answer
    an obligation key — the subledger line's two and the journal line's — join it by its id AND
    by the joined contract's id, so the key is null wherever the contract's name is."""
    joined = _sql(subledger.OBLIGATION_JOIN)
    assert "obligation.id = erev.subledger_line.obligation_id" in joined
    assert THROUGH_THE_CONTRACT in joined
    drill = _sql(queries.drill_statement([LINE]))
    assert "LEFT OUTER JOIN erev.obligation ON" in drill and THROUGH_THE_CONTRACT in drill
    assert "obligation.obligation_key" in drill
    lines = _sql(queries.lines_statement(LINE))
    assert "obligation.id = erev.journal_line.obligation_id" in lines
    assert THROUGH_THE_CONTRACT in lines
    # the register's statement is built from the same join (it needs a session for its book)
    assert ".outerjoin(obligation, OBLIGATION_JOIN)" in inspect.getsource(subledger.line_statement)


def test_the_schemas_admit_the_reader_who_is_not_told() -> None:
    """API-S-JournalLine ``contract.external_id`` and API-S-SubledgerLine ``obligation_key`` are
    answered on every row — required members — and may be null."""
    assert JournalLineContractOut(id=CONTRACT, external_id=None).external_id is None
    for model, member in (
        (JournalLineContractOut, "external_id"),
        (SubledgerLineOut, "obligation_key"),
    ):
        schema = model.model_json_schema()
        assert member in schema["required"], model.__name__
        assert {"type": "null"} in schema["properties"][member]["anyOf"], model.__name__


def test_a_counterparty_the_statement_could_not_name_is_named_beside_it() -> None:
    """The reference of a counterparty entity outside the caller's scope is handed to
    ``line_outs`` beside the rows (``counterparties``); a counterparty the statement joined is
    answered from the row, and a line without one answers null. The contract keeps its id where
    its name is null."""
    named = {ELSEWHERE: {"id": ELSEWHERE, "code": "AVM-UK", "name": "Avenmoor UK Ltd"}}
    [unseen] = queries.line_outs([_row()], named)
    assert unseen.counterparty_entity is not None
    assert unseen.counterparty_entity.model_dump() == named[ELSEWHERE]
    assert unseen.contract is not None
    assert (unseen.contract.id, unseen.contract.external_id) == (CONTRACT, None)
    joined = _row(counterparty_entity_id=HERE, counterparty_code="AVM-US", counterparty_name="US")
    [seen] = queries.line_outs([joined], named)
    assert seen.counterparty_entity is not None
    assert (seen.counterparty_entity.id, seen.counterparty_entity.code) == (HERE, "AVM-US")
    [none] = queries.line_outs([_row(counterparty_entity_id=None, contract_id=None)])
    assert (none.counterparty_entity, none.contract) == (None, None)


def test_no_statement_is_sent_where_the_rows_name_every_counterparty() -> None:
    """``counterparties`` reads under the tenant's scope only what the statement could not
    join: for a caller of every entity, and for a run without an intercompany line, it sends
    nothing."""
    rows = [
        _row(counterparty_entity_id=None),
        _row(counterparty_entity_id=HERE, counterparty_code="AVM-US", counterparty_name="US"),
    ]
    assert queries.counterparties(_NoStatement(), rows) == {}  # type: ignore[arg-type]
    source = inspect.getsource(queries.counterparties)
    assert "with system_entity_scope(session):" in source
    # the id, the code and the name, and nothing else of the entity
    assert "select(legal_entity.c.id, legal_entity.c.code, legal_entity.c.name)" in source


def test_a_batch_reads_its_references_under_the_tenants_scope() -> None:
    """A line's reference is part of the entry — its legacy key or, without one, the external id
    of its contract, then the journal line's identity — and the statement that reads it for a
    chunk runs under the tenant's scope, for the job and for a download alike."""
    row = {"legacy_key": None, "contract_external_id": "SF-ORD-UK-2001", "id": LINE}
    assert export._references({**row, "source_line_count": 1}) == (
        f"SF-ORD-UK-2001; journal_line={LINE}; source_lines=1"
    )
    source = inspect.getsource(export.chunk_of)
    scope = source.index("with system_entity_scope(session):")
    assert scope < source.index('contract.c.external_id.label("contract_external_id")')
    # the batch itself is read before, under the caller's own scope
    assert source.index("select(journal_batch).where(journal_batch.c.id == batch_id)") < scope


def test_the_rows_state_the_reads() -> None:
    """04 §16.7 rev 1.245 states the four reads word for word, and fragment 14 rev 1.53 names the
    three database witnesses."""
    model = (DOCS / "04-DATA_MODEL.md").read_text(encoding="utf-8")
    for sentence in (
        "| `obligation_key` | string or null | — | Rev 1.245 (register index 182; the "
        "supervisor's ruling of 2026-10-01): the key of the line's obligation",
        "so the key is joined THROUGH the contract's row",
        "`external_id` is a string or null — null in one case only: the contract is outside the "
        "caller's entity scope",
        "the counterparty of an intercompany line is named — id, code and name — to every reader "
        "of the line",
        "what is downloaded is the batch as it leaves, whoever downloads it — one artifact, one "
        "digest",
        "the take-over is then evidenced by the run's `CALCULATE` event and its detail file "
        "alone, since no entry leaves",
    ):
        assert model.count(sentence) == 1, sentence
    fragment = (DOCS / "build-spec/14-close-reports-ai-demo-release.md").read_text(encoding="utf-8")
    scope, drill = "backend/tests/domain/journals/test_line_reader_scope.py", "backend/tests/api"
    for witness in (
        f"`{scope}::test_a_reader_of_one_entity_reads_the_lines_of_a_contract_of_another`",
        f"`{scope}::test_a_batch_is_downloaded_as_it_leaves_whoever_downloads_it`",
        f"`{drill}/test_drill_chain.py::"
        "test_the_drill_names_the_obligation_of_every_line_through_its_contract`",
    ):
        assert fragment.count(witness) == 1, witness
