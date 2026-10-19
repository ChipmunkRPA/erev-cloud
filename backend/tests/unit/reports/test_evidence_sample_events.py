from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.domain.reports.evidence_sample_events import EVENT_KEYS, event_records
from erev_api.problems import Problem
from erev_engine.canonical import sha256_hex

NOW = datetime(2026, 10, 19, tzinfo=UTC)
CONTRACT = UUID(int=1)
ENTITY = UUID(int=2)


def event():
    payload = {"document_ref": "CONTRACT-001", "contact_email": "private@example.test"}
    return dict.fromkeys(EVENT_KEYS) | {
        "id": UUID(int=3),
        "contract_id": CONTRACT,
        "contracting_entity_id": ENTITY,
        "effective_date": date(2026, 9, 1),
        "recorded_at": NOW,
        "record_seq": 1,
        "payload": payload,
        "payload_sha256": sha256_hex(payload),
    }


def records(rows):
    return event_records(
        rows, contract_ids=[CONTRACT], entity_ids=[ENTITY], as_of=date(2026, 9, 30), known_at=NOW
    )


def test_redacted_payload_has_its_own_digest_and_keeps_original_provenance():
    source = event()
    (row,) = records([source])
    assert row["payload"]["document_ref"] == "CONTRACT-001"
    assert row["payload"]["contact_email"] == "[redacted]"
    assert row["source_payload_sha256"] == source["payload_sha256"]
    assert row["exported_payload_sha256"] == sha256_hex(row["payload"])
    assert row["exported_payload_sha256"] != row["source_payload_sha256"]
    assert source["payload"]["contact_email"] == "private@example.test"


def test_corrupt_out_of_scope_duplicate_and_late_facts_are_refused():
    source = event()
    for change in (
        {"contract_id": UUID(int=9)},
        {"contracting_entity_id": UUID(int=9)},
        {"payload_sha256": "0" * 64},
        {"effective_date": date(2026, 10, 1)},
        {"recorded_at": NOW + timedelta(microseconds=1)},
    ):
        with pytest.raises(Problem):
            records([source | change])
    with pytest.raises(Problem):
        records([source, source])
