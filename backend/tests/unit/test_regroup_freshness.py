"""Transfer freshness excludes its own draft headers, not actual source changes."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from erev_api.domain.contracts import regroup_freshness as freshness
from erev_api.problems import Problem
from tests.engine.s03_pob_builder.test_combined_reassessment import continuation


def read(value, pending=frozenset()):
    return freshness.source_basis(
        value,
        contract_key=value.contracts[0].external_id,
        effective_date=value.events[-1].effective_date,
        obligation_keys=("SERVICE",),
        pending_pair=pending,
    )


def test_preparation_headers_and_read_time_do_not_make_the_basis_stale():
    original = continuation()
    expected = read(original)
    contract = original.contracts[0]
    pending = replace(contract.modifications[0], modification_key="NEW-PAIR", status="DRAFT")
    current = replace(
        original,
        known_at=original.known_at + timedelta(days=1),
        contracts=(replace(contract, modifications=(*contract.modifications, pending)),),
    )
    assert read(current, frozenset({"NEW-PAIR"})) == expected
    assert expected["ASC606"]["input_sha256"] == original.sha256()


def test_other_source_inputs_and_current_term_remain_in_the_basis():
    original = continuation()
    expected = read(original)
    booking = original.events[0]
    changed = replace(
        booking,
        payload={
            **booking.payload,
            "lines": [{**line, "end_date": "2027-12-31"} for line in booking.payload["lines"]],
        },
    )
    current = replace(original, events=(changed, *original.events[1:]))
    assert read(current) != expected
    assert read(current)["ASC606"]["obligations"]["SERVICE"]["service_end_date"] == "2027-12-31"
    with pytest.raises(Problem, match="invalid-transition"):
        read(original, frozenset({original.contracts[0].modifications[0].modification_key}))


@pytest.mark.parametrize("change", [None, "source", "target_books"])
def test_freshness_entry_reads_current_source_and_target(monkeypatch, change):
    original = continuation()
    source_id, target_id, source_group, target_group = (uuid4() for _ in range(4))
    source = {
        "contract_id": source_id,
        "id": uuid4(),
        "kind": "REMOVE_OBLIGATION",
        "effective_date": original.events[-1].effective_date,
        "lines": [{"obligation_key": "SERVICE"}],
        "questionnaire": {"regroup_source_basis": read(original)},
    }
    target = {"contract_id": target_id, "id": uuid4(), "kind": "ADD_OBLIGATION"}
    sources = {source_group: original, target_group: original}
    if change == "source":
        # No financial mutation is needed: changing an input identity still needs a review.
        sources[source_group] = replace(original, trigger="DRY_RUN")
    elif change == "target_books":
        sources[target_group] = replace(original, books=())
    monkeypatch.setattr(
        freshness.repo,
        "get_contract",
        lambda session, identity: {
            "combination_group_id": source_group if identity == source_id else target_group,
            "external_id": original.contracts[0].external_id,
            "transaction_currency": "USD",
        },
    )
    monkeypatch.setattr(freshness.bundles, "build", lambda session, group, now: sources[group])
    uow = SimpleNamespace(session=object(), now=original.known_at)
    if change:
        with pytest.raises(Problem, match="invalid-transition"):
            freshness.require_fresh(uow, [source, target])
    else:
        freshness.require_fresh(uow, [source, target])
