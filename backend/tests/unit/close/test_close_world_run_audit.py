"""The close-world fixtures carry the journal producer's facts (F-CLO record §25.22; integrated
batch #7 on main 104a954c). CPU-only pins: (1) ``close_world.run_audit_after`` builds the
``journal_run.calculate`` audit ``after`` a real run writes (``summarise.calculate``) — the same key
set, the explicit zero-held state ``held_subledger_line_ids == []`` and ``counts.held_lines == 0`` —
so a fixture run is verifiable to ``completeness.run_exclusions`` instead of an unverifiable named
finding; (2) ``sealed_activity`` builds its obligation with the ``created_by_event_id`` the row
helper has required since 808caf73."""

from __future__ import annotations

import inspect
import re
from decimal import Decimal
from uuid import UUID

from erev_api.domain.journals import completeness, summarise
from support import close_world, rows

PRODUCER_AFTER_KEYS = {
    "run_no",
    "validation_execution_id",
    "entity_id",
    "book_code",
    "period_id",
    "mode",
    "grain",
    "coverage",
    "total_debit_functional",
    "total_credit_functional",
    "counts",
    "held_detail_file_id",
    "held_detail_sha256",
    "held_subledger_line_ids",
    # item JRN-HELD-AFTER-EXPORT-1 (ENGINE_SPEC_B S14-R-17 rev 1.164): what the run took over
    "taken_over_subledger_line_ids",
    "taken_over_detail_file_id",
    "taken_over_detail_sha256",
}


def _rows() -> rows.JournalRows:
    run = {
        "id": UUID(int=1),
        "run_no": "JR-TEST",
        "entity_id": UUID(int=2),
        "book_code": "ASC606",
        "period_id": UUID(int=3),
        "mode": "GROSS",
        "grain": "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
        "from_chain_seq": 0,
        "to_chain_seq": 0,
        "delta_from_chain_seq": None,
        "delta_to_chain_seq": None,
        "total_debit_functional": Decimal("295.69"),
        "total_credit_functional": Decimal("295.69"),
    }
    return rows.JournalRows(
        parts=None,  # type: ignore[arg-type]
        run=run,
        batch={"id": UUID(int=4)},
        entries=({"id": UUID(int=5)},),
        lines=({"id": UUID(int=6)}, {"id": UUID(int=7)}),
    )


def test_the_fixture_audit_payload_is_the_producers_shape() -> None:
    after = close_world.run_audit_after(_rows(), validation_execution_id=UUID(int=8))
    assert set(after) == PRODUCER_AFTER_KEYS
    assert after["validation_execution_id"] == str(UUID(int=8))
    assert after["held_subledger_line_ids"] == [] and after["held_detail_file_id"] is None
    assert after["held_detail_sha256"] is None
    assert after["taken_over_subledger_line_ids"] == []
    assert (after["taken_over_detail_file_id"], after["taken_over_detail_sha256"]) == (None, None)
    assert after["counts"] == {
        "batches": 1,
        "entries": 1,
        "lines": 2,
        "detail_lines": 2,
        "held_lines": 0,
    }
    assert after["coverage"] == [0, 0, None, None]
    assert (after["total_debit_functional"], after["total_credit_functional"]) == (
        "295.69",
        "295.69",
    )
    assert (after["run_no"], after["mode"], after["book_code"]) == ("JR-TEST", "GROSS", "ASC606")


def _producer_after_keys() -> set[str]:
    """The keys of the ``after={...}`` payload ``summarise.calculate`` writes for its CALCULATE
    audit event, read from the producer's source so the fixture cannot drift from production (the
    team lead's condition on §25.22: no separate payload builder exists in ``summarise``)."""
    source = inspect.getsource(summarise.calculate)
    start = source.index("after={", source.index("action=CALCULATE_ACTION"))
    depth = 0
    for offset, char in enumerate(source[start + len("after=") :]):
        depth += char == "{"
        depth -= char == "}"
        if depth == 0:
            block = source[start + len("after=") : start + len("after=") + offset + 1]
            break
    else:  # pragma: no cover
        raise AssertionError("unterminated after={...} block")
    return set(re.findall(r'^\s*"([a-z0-9_]+)":', block, flags=re.MULTILINE))


def test_the_producer_keys_pin_summarise_and_completeness_read_the_same_facts() -> None:
    """The fixture payload's key set EQUALS the producer's (exact, both directions), and the
    members ``completeness.run_exclusions`` reads are among them."""
    assert _producer_after_keys() == PRODUCER_AFTER_KEYS
    assert (
        set(close_world.run_audit_after(_rows(), validation_execution_id=UUID(int=8)))
        == _producer_after_keys()
    )
    assert (close_world.RUN_AUDIT_ACTION, close_world.RUN_AUDIT_OBJECT_TYPE) == (
        summarise.CALCULATE_ACTION,
        summarise.OBJECT_TYPE,
    )
    assert (completeness.CALCULATE_ACTION, completeness.RUN_OBJECT_TYPE) == (
        summarise.CALCULATE_ACTION,
        summarise.OBJECT_TYPE,
    )


def test_sealed_activity_builds_its_obligation_with_the_creating_event() -> None:
    required = inspect.signature(rows.obligation_values).parameters["created_by_event_id"]
    assert required.default is inspect.Parameter.empty
    source = inspect.getsource(close_world.sealed_activity)
    assert "created_by_event_id=event_id" in source
    assert "contract_id, event_id, group_id = contract_of(" in source
