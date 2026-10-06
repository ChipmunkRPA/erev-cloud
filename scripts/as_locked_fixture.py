#!/usr/bin/env python3
"""What the web application knows about an as-locked report run, written from the API's own rule
(item RV-AS-LOCKED-DEFAULT-1; ENGINE_SPEC_B S15-R-19 and §15.2.7; SCREENS_B RV-04 rev 1.98;
docs/dev-guide.md DG-FE-18).

A report screen decides two things from tables that are the API's: whether a report has a lock
dataset at all (``locked.SNAPSHOT_KIND_BY_REPORT``), and what an as-locked run may be asked
(``locked.reconcile_selectors``: the lock, ``known_at`` and the lock's own entity, book and period —
nothing else). The screens' tests answered 202 to any parameter set, so three views sent a set the
API refuses and no test said so. This script writes both tables for the frontend, and a unit test
(``backend/tests/unit/test_as_locked_fixture.py``) compares the committed files with a fresh run,
so a change of ``locked.py`` or of a report's parameter schema turns the tree red until they are
written again.

It writes two files:

``frontend/src/routes/reports/viewer/lock-datasets.json``
    The reports that have a lock dataset, by code, with the E-64 kind: what the screens read to
    default a closed period to "As locked". API-S-ReportDefinition does not state it.

``frontend/src/test/as-locked.json``
    For the tests: every report definition as ``GET /report-definitions/{code}`` answers it to a
    reader without ``report.export``; the admitted keys and the refusals' sentences; and a table of
    parameter sets with the findings the API's function gives each for one lock (``lock``) — the
    lock alone, the lock with its own selectors, every other key of each schema, another entity,
    another book, another period — and, for a report that takes ``period_lock_id`` and has no
    dataset, the finding ``framework._resolve`` answers. The fake of the screens' tests is the
    rule in TypeScript, held to every row of that table. Since S15-R-19 rev 1.167 (register
    index 280) a run names a ``LOCK`` record or is refused: ``records`` holds each E-63 kind of
    record, where a lock's datasets stand for its period and where none does, with the sentence
    ``locked.not_a_lock`` gives — none for a ``LOCK`` — and the fake is held to those rows too.

No database is read and nothing but the two files is written.

Usage: backend/.venv/bin/python scripts/as_locked_fixture.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from erev_api.domain.reports import framework, locked
from erev_api.domain.reports.catalogue import DEFINITIONS, ReportDefinition
from erev_api.enums import LockKind

ROOT: Final = Path(__file__).resolve().parents[1]
DATASETS_FILE: Final = ROOT / "frontend/src/routes/reports/viewer/lock-datasets.json"
FIXTURE_FILE: Final = ROOT / "frontend/src/test/as-locked.json"
COMMAND: Final = "backend/.venv/bin/python scripts/as_locked_fixture.py"

# The lock the table's findings are given for: Avenmoor Inc., ASC 606, August 2026.
LOCK: Final = locked.LockScope(
    lock_id=UUID("8b10c4d2-6e1f-4a3b-9c8d-7e6f5a4baa42"),
    entity_id=UUID("0a1b2c3d-4e5f-4a6b-8c7d-000000000001"),
    entity_code="AVM-US",
    book_code="ASC606",
    period_id=UUID("2c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e08"),
    period_key="FY2026-P08",
)
# A record of the lock's period that is no LOCK: its reopen, or its permanent lock.
OTHER_RECORD: Final = UUID("8b10c4d2-6e1f-4a3b-9c8d-7e6f5a4bff08")
OTHER_ENTITY: Final = "AVM-JP"
OTHER_BOOK: Final = "IFRS15"
OTHER_PERIOD: Final = "FY2026-P09"
KNOWN_AT: Final = "2026-09-03T09:14:00Z"
LOCK_KEY: Final = "period_lock_id"


def definition_out(definition: ReportDefinition) -> dict[str, Any]:
    """API-S-ReportDefinition as ``framework.definition_out`` answers a row of the catalogue to
    a principal without ``report.export`` (no ``ipe_logic``)."""
    return {
        "code": definition.code,
        "version": definition.version,
        "name": definition.name,
        "kind": str(definition.kind),
        "description": definition.description,
        "parameters_schema": dict(definition.parameters_schema),
        "output_formats": [str(item) for item in definition.output_formats],
        "tie_outs": list(definition.tie_outs),
    }


def properties_of(definition: ReportDefinition) -> dict[str, Any]:
    return dict(definition.parameters_schema.get("properties", {}))


def sample(schema: Mapping[str, Any]) -> Any:
    """A value of the key's type. The rule reads the key of a parameter it does not admit, not
    its value."""
    kind = schema.get("type")
    if kind == "array":
        return [sample(schema.get("items", {"type": "string"}))]
    if kind == "boolean":
        return True
    if kind in ("integer", "number"):
        return 1
    values = schema.get("enum")
    if isinstance(values, list) and values:
        return values[0]
    if schema.get("format") == "date":
        return "2026-08-31"
    if schema.get("format") == "date-time":
        return KNOWN_AT
    return "x"


def own_selectors(properties: Mapping[str, Any]) -> dict[str, Any]:
    """The lock with what an as-locked run of the schema may say beside it: its own entity, book
    and period, and a cutoff."""
    given: dict[str, Any] = {LOCK_KEY: str(LOCK.lock_id)}
    if "entity_codes" in properties:
        given["entity_codes"] = [LOCK.entity_code]
    if "book" in properties:
        given["book"] = LOCK.book_code
    for key in locked.PERIOD_KEYS:
        if key in properties:
            given[key] = LOCK.period_key
    if "known_at" in properties:
        given["known_at"] = KNOWN_AT
    if "known_at_basis" in properties:
        given["known_at_basis"] = "historical"
    return given


def parameter_sets(properties: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    lock = {LOCK_KEY: str(LOCK.lock_id)}
    sets: list[tuple[str, dict[str, Any]]] = [
        ("the lock alone", dict(lock)),
        ("the lock with its own selectors", own_selectors(properties)),
    ]
    others = {
        key: sample(properties[key])
        for key in sorted(properties)
        if key not in locked.ADMITTED_KEYS
    }
    for key, value in others.items():
        sets.append((f"the lock with {key}", {**lock, key: value}))
    if len(others) > 1:
        # What a view that sends its own defaults beside the lock sends: several findings, in the
        # function's order.
        sets.append(("the lock with every key it does not admit", {**lock, **others}))
    if "entity_codes" in properties:
        sets.append(("another entity", {**lock, "entity_codes": [OTHER_ENTITY]}))
        sets.append(("two entities", {**lock, "entity_codes": [LOCK.entity_code, OTHER_ENTITY]}))
    if "book" in properties:
        sets.append(("another book", {**lock, "book": OTHER_BOOK}))
    for key in locked.PERIOD_KEYS:
        if key in properties:
            sets.append((f"another period as {key}", {**lock, key: OTHER_PERIOD}))
    return sets


def finding(field: str, rule_id: str | None, message: str) -> dict[str, Any]:
    return {"field": field, "rule_id": rule_id, "message": message}


def cases() -> list[dict[str, Any]]:
    """Each parameter set with the findings of the API's own function, report by report."""
    table: list[dict[str, Any]] = []
    for definition in DEFINITIONS:
        properties = properties_of(definition)
        if LOCK_KEY not in properties:
            continue
        kind = locked.snapshot_kind_of(definition.code)
        if kind is None:
            # framework._resolve: a report without a lock dataset refuses the lock by name.
            message = locked.NO_DATASET.format(code=definition.code)
            table.append(
                {
                    "report": definition.code,
                    "case": "the lock alone",
                    "given": {LOCK_KEY: str(LOCK.lock_id)},
                    "findings": [finding(locked.FIELD, locked.RULE, message)],
                }
            )
            continue
        for name, given in parameter_sets(properties):
            _, errors = locked.reconcile_selectors(given, LOCK, properties, kind=kind)
            table.append(
                {
                    "report": definition.code,
                    "case": name,
                    "given": given,
                    "findings": [
                        finding(error.field or "", error.rule_id, error.message) for error in errors
                    ],
                }
            )
    return table


def records() -> list[dict[str, Any]]:
    """Each E-63 kind of record a run can name, where a ``LOCK``'s datasets stand for the record's
    period and where none does, with what ``locked.not_a_lock`` answers: nothing for a ``LOCK``,
    and for another record the sentence that names it and the lock to pass, or that none stands."""
    table: list[dict[str, Any]] = []
    for kind in LockKind:
        named = (
            LOCK if kind is LockKind.LOCK else replace(LOCK, lock_id=OTHER_RECORD, kind=kind.value)
        )
        for standing in (LOCK.lock_id, None):
            table.append(
                {
                    "kind": kind.value,
                    "id": str(named.lock_id),
                    "period_key": named.period_key,
                    "dataset_lock_id": None if standing is None else str(standing),
                    "refusal": locked.not_a_lock(named, standing),
                }
            )
    return table


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def listed(name: str, items: Sequence[Any]) -> list[str]:
    """A member whose items stand one to a line, so that a changed report is a changed line."""
    lines = [f"  {json.dumps(name)}: ["]
    lines += [
        f"    {compact(item)}{',' if index < len(items) - 1 else ''}"
        for index, item in enumerate(items)
    ]
    lines.append("  ]")
    return lines


def datasets_text() -> str:
    kinds = dict(sorted(locked.SNAPSHOT_KIND_BY_REPORT.items()))
    return json.dumps(kinds, indent=2) + "\n"


def fixture_text() -> str:
    note = f"By scripts/as_locked_fixture.py from the API. Do not edit: run {COMMAND}"
    members: list[list[str]] = [
        [f'  "generated": {json.dumps(note)}'],
        [f'  "rule_id": {json.dumps(locked.RULE)}'],
        [f'  "scope_rule_id": {json.dumps(framework.RULE_SCOPE)}'],
        [f'  "field": {json.dumps(locked.FIELD)}'],
        [f'  "admitted_keys": {compact(sorted(locked.ADMITTED_KEYS))}'],
        [f'  "period_keys": {compact(list(locked.PERIOD_KEYS))}'],
        [
            '  "messages": '
            + compact(
                {
                    "not_a_lock_selector": locked.NOT_A_LOCK_SELECTOR,
                    "entity_mismatch": locked.ENTITY_MISMATCH,
                    "book_mismatch": locked.BOOK_MISMATCH,
                    "period_mismatch": locked.PERIOD_MISMATCH,
                    "no_dataset": locked.NO_DATASET,
                    # framework._resolve: a lock outside the caller's workspace or scope.
                    "lock_unknown": framework.LOCK_UNKNOWN,
                    # locked.not_a_lock: a record that froze nothing, then the lock to pass.
                    "not_a_lock": locked.NOT_A_LOCK,
                    "pass_dataset_lock": locked.PASS_DATASET_LOCK,
                    "no_dataset_lock": locked.NO_DATASET_LOCK,
                }
            )
        ],
        [f'  "record_words": {compact(dict(locked.RECORD_WORDS))}'],
        [f'  "kinds": {compact(dict(locked.SNAPSHOT_KIND_BY_REPORT))}'],
        [
            '  "lock": '
            + compact(
                {
                    "id": str(LOCK.lock_id),
                    "entity_code": LOCK.entity_code,
                    "book_code": LOCK.book_code,
                    "period_key": LOCK.period_key,
                }
            )
        ],
        listed("records", records()),
        listed("definitions", [definition_out(definition) for definition in DEFINITIONS]),
        listed("cases", cases()),
    ]
    text = "{\n" + ",\n".join("\n".join(member) for member in members) + "\n}\n"
    json.loads(text)  # the file is JSON, whatever its layout
    return text


def rendered() -> dict[Path, str]:
    return {DATASETS_FILE: datasets_text(), FIXTURE_FILE: fixture_text()}


def stale() -> list[Path]:
    """The files whose committed text is not what the API's tables give now."""
    return [
        path
        for path, text in rendered().items()
        if not path.is_file() or path.read_text(encoding="utf-8") != text
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare and write nothing")
    arguments = parser.parse_args(argv)
    if arguments.check:
        changed = stale()
        for path in changed:
            print(f"{path.relative_to(ROOT)} is stale; run {COMMAND}")
        return 1 if changed else 0
    for path, text in rendered().items():
        path.write_text(text, encoding="utf-8")
        print(f"written {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
