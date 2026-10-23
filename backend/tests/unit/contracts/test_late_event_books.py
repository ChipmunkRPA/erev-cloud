"""Book-specific late findings use only books kept by the contracting entity."""

from datetime import date
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from erev_api.domain.contracts import compute_job


def test_late_findings_keep_each_books_posting_period(monkeypatch: pytest.MonkeyPatch) -> None:
    event_id, entity_id, contract_id = uuid4(), uuid4(), uuid4()
    event = NS(
        stream_version=2,
        contract_key="C",
        event_key="C:2",
        effective_date=date(2026, 8, 31),
        obligation_keys=(),
    )
    bundle = NS(
        group=NS(previous_stream_heads=(("C", 1),)),
        events=(event,),
        books=(
            NS(book_code="ASC606", entity_codes=("DE",)),
            NS(book_code="IFRS15", entity_codes=("DE",)),
            NS(book_code="LEGACY", entity_codes=("US",)),
        ),
    )
    found = NS(
        events={("C", 2): event_id},
        contracts={"C": {"id": contract_id, "contracting_entity_id": entity_id}},
        entities={"DE": {"id": entity_id}},
        obligations={},
    )
    captured = []
    called = []

    def posting(session, **kwargs):
        code = kwargs["book_code"].value
        called.append(code)
        return NS(period_key="SEP" if code == "ASC606" else "OCT"), NS(period_key="AUG", id=uuid4())

    def raised(uow, **kwargs):
        captured.append(kwargs)
        return NS(id=uuid4())

    monkeypatch.setattr(compute_job.queries, "primary_book", lambda session: "ASC606")
    monkeypatch.setattr(compute_job, "posting_period", posting)
    monkeypatch.setattr(compute_job, "raise_exception_item", raised)
    held = {}
    compute_job._raise_late_events(NS(session=None), bundle, found, uuid4(), held)
    assert called == ["ASC606", "IFRS15"]
    assert [x["dedupe"] for x in captured] == [
        f"ENGINE:LATE_EVENT:{event_id}",
        f"ENGINE:LATE_EVENT:{event_id}:IFRS15",
    ]
    assert [
        (x["source_payload"]["book_code"], x["source_payload"]["posting_period_key"])
        for x in captured
    ] == [("ASC606", "SEP"), ("IFRS15", "OCT")]
    # An existing diagnostic for one book must not suppress the other book's finding.
    captured.clear()
    compute_job._raise_late_events(
        NS(session=None), bundle, found, uuid4(), {("LATE_EVENT", str(event_id)): uuid4()}
    )
    assert [x["source_payload"]["book_code"] for x in captured] == ["IFRS15"]
    # Events already included in the prior computation are not raised again.
    captured.clear()
    bundle.group.previous_stream_heads = (("C", 2),)
    compute_job._raise_late_events(NS(session=None), bundle, found, uuid4(), {})
    assert captured == []


def test_engine_diagnostics_do_not_merge_two_books(monkeypatch: pytest.MonkeyPatch) -> None:
    event_id, entity_id, contract_id = uuid4(), uuid4(), uuid4()
    event = NS(
        event_key="C:2", contract_key="C", stream_version=2, effective_date=date(2026, 8, 31)
    )
    found = NS(
        events={("C", 2): event_id},
        contracts={"C": {"id": contract_id, "contracting_entity_id": entity_id}},
        obligations={},
        entities={"DE": {"id": entity_id}},
        periods={},
    )
    captured = []

    def raised(uow, **kwargs):
        captured.append(kwargs)
        return NS(id=uuid4())

    monkeypatch.setattr(compute_job.bundles, "index", lambda session, bundle: found)
    monkeypatch.setattr(compute_job.queries, "primary_book", lambda session: "ASC606")
    monkeypatch.setattr(compute_job, "raise_exception_item", raised)
    monkeypatch.setattr(compute_job, "_raise_late_events", lambda *args: None)
    diagnostics = tuple(
        NS(
            code="LATE_EVENT",
            event_key="C:2",
            subject_key=None,
            severity="WARNING",
            book_code=book,
            detail={},
        )
        for book in ("ASC606", "IFRS15", "IFRS15")
    )
    result = compute_job._raise_diagnostics(
        NS(session=None), NS(events=(event,)), NS(diagnostics=diagnostics), uuid4()
    )
    assert len(result) == 2
    assert [x["dedupe"] for x in captured] == [
        f"ENGINE:LATE_EVENT:{event_id}",
        f"ENGINE:LATE_EVENT:{event_id}:IFRS15",
    ]
