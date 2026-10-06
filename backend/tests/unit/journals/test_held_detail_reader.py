"""The held-detail reader that binds journal coverage to a run's recorded exclusions (Codex
production-20260921-1535 follow-through on CLO-10 R5-ORDER-1; F-CLO record §25.19).

``completeness.held_ids_from_document`` is the pure parser behind ``_held_ids_from_file``: the
content must hash as the CALCULATE audit recorded, parse as a JSON object whose ``held`` member is a
list of objects with a UUID ``subledger_line_id``. Explicit empty (``{"held": []}``) is the recorded
zero-held state and yields an EMPTY exclusion set; a missing ``held`` key (``{}``), a non-list
member, a non-UUID id, malformed JSON or a hash mismatch yield ``None`` — the run is then
"unverifiable", covers nothing and is a named finding (never a silent empty set). CPU-only."""

from __future__ import annotations

import hashlib
import json
from typing import Final
from uuid import UUID

from erev_api.domain.journals import completeness

LINE_A: Final = UUID("00000000-0000-4000-8000-00000000a001")
LINE_B: Final = UUID("00000000-0000-4000-8000-00000000a002")


def _content(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(document: object, *, sha: str | None = None) -> frozenset[UUID] | None:
    content = _content(document)
    return completeness.held_ids_from_document(content, sha if sha is not None else _sha(content))


def test_recorded_held_lines_are_read_by_id() -> None:
    document = {
        "external_id": "erev:t:JR-1:held",
        "run_no": "JR-1",
        "held": [
            {"subledger_line_id": str(LINE_A), "hold_id": "h", "txn_currency": "USD"},
            {"subledger_line_id": str(LINE_B), "hold_id": "h", "txn_currency": "USD"},
        ],
    }
    assert _read(document) == frozenset({LINE_A, LINE_B})


def test_explicit_empty_held_list_is_the_zero_held_state() -> None:
    assert _read({"run_no": "JR-1", "held": []}) == frozenset()


def test_a_missing_held_key_is_unverifiable_not_empty() -> None:
    assert _read({}) is None
    assert _read({"run_no": "JR-1"}) is None


def test_a_non_list_held_member_is_unverifiable() -> None:
    assert _read({"held": None}) is None
    assert _read({"held": {"subledger_line_id": str(LINE_A)}}) is None
    assert _read({"held": "[]"}) is None


def test_a_non_uuid_or_missing_line_id_is_unverifiable() -> None:
    assert _read({"held": [{"subledger_line_id": "not-a-uuid"}]}) is None
    assert _read({"held": [{"hold_id": "h"}]}) is None
    assert _read({"held": ["a-string-not-an-object"]}) is None


def test_malformed_json_is_unverifiable() -> None:
    content = b'{"held": [}'
    assert completeness.held_ids_from_document(content, _sha(content)) is None


def test_a_hash_mismatch_is_unverifiable_before_parsing() -> None:
    assert _read({"held": []}, sha="0" * 64) is None


def test_a_non_object_document_is_unverifiable() -> None:
    assert _read([{"subledger_line_id": str(LINE_A)}]) is None
    assert _read("held") is None
