"""The frontend's as-locked tables are the API's (item RV-AS-LOCKED-DEFAULT-1; SCREENS_B RV-04
rev 1.98; ENGINE_SPEC_B S15-R-19; docs/dev-guide.md DG-FE-18).

``scripts/as_locked_fixture.py`` writes ``frontend/src/routes/reports/viewer/lock-datasets.json``
— the reports a screen defaults to "As locked" on a closed period — and
``frontend/src/test/as-locked.json`` — the definitions, the admitted keys, the refusals' sentences,
the findings the fake of the screens' tests is held to and, since register index 280, the refusal
of a record that is no ``LOCK``. Both are derived from ``locked.py`` and the report catalogue. The
screens' tests once answered 202 to any parameter set, and three views sent a set the API refuses;
this module is what turns the tree red, by the command's name, when the API's rule or a report's
schema moves and the files have not been written again.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from erev_api.domain.reports import framework, locked
from erev_api.domain.reports.catalogue import DEFINITIONS, DEFINITIONS_BY_CODE
from erev_api.enums import LockKind

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "as_locked_fixture.py"
COMMAND = "backend/.venv/bin/python scripts/as_locked_fixture.py"
LOCK_KEY = "period_lock_id"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("as_locked_fixture", SCRIPT)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load()


@pytest.fixture
def scratch() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _fixture(script: ModuleType) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(script.FIXTURE_FILE.read_text(encoding="utf-8"))
    return loaded


def test_the_committed_files_are_what_the_api_gives_now(script: ModuleType) -> None:
    stale = [str(path.relative_to(ROOT)) for path in script.stale()]
    assert stale == [], (
        f"{', '.join(stale)}: written from locked.py and the report catalogue, which have moved. "
        f"Run {COMMAND} and commit the files with the change."
    )
    assert script.COMMAND == COMMAND


def test_the_screens_table_is_the_kinds_table(script: ModuleType) -> None:
    datasets = json.loads(script.DATASETS_FILE.read_text(encoding="utf-8"))
    assert datasets == dict(locked.SNAPSHOT_KIND_BY_REPORT)
    assert list(datasets) == sorted(datasets)
    # A report with a dataset takes the lock: a screen sends it to no report without the key.
    for code in datasets:
        assert LOCK_KEY in DEFINITIONS_BY_CODE[code].parameters_schema["properties"], code


def test_the_fixture_holds_every_definition_and_the_rule(script: ModuleType) -> None:
    fixture = _fixture(script)
    assert [item["code"] for item in fixture["definitions"]] == [item.code for item in DEFINITIONS]
    for item in fixture["definitions"]:
        definition = DEFINITIONS_BY_CODE[item["code"]]
        assert item["parameters_schema"] == json.loads(json.dumps(definition.parameters_schema))
        # As ``GET /report-definitions/{code}`` answers a reader without ``report.export``.
        assert set(item) == {
            "code",
            "version",
            "name",
            "kind",
            "description",
            "parameters_schema",
            "output_formats",
            "tie_outs",
        }
    assert fixture["admitted_keys"] == sorted(locked.ADMITTED_KEYS)
    assert fixture["period_keys"] == list(locked.PERIOD_KEYS)
    assert fixture["rule_id"] == locked.RULE and fixture["field"] == locked.FIELD
    assert fixture["scope_rule_id"] == framework.RULE_SCOPE
    assert fixture["messages"] == {
        "not_a_lock_selector": locked.NOT_A_LOCK_SELECTOR,
        "entity_mismatch": locked.ENTITY_MISMATCH,
        "book_mismatch": locked.BOOK_MISMATCH,
        "period_mismatch": locked.PERIOD_MISMATCH,
        "no_dataset": locked.NO_DATASET,
        "lock_unknown": framework.LOCK_UNKNOWN,
        "not_a_lock": locked.NOT_A_LOCK,
        "pass_dataset_lock": locked.PASS_DATASET_LOCK,
        "no_dataset_lock": locked.NO_DATASET_LOCK,
    }
    assert fixture["record_words"] == dict(locked.RECORD_WORDS)


def test_the_records_table_is_the_refusal_of_a_record_that_is_no_lock(script: ModuleType) -> None:
    """S15-R-19 rev 1.167 (register index 280): a run names a ``LOCK`` record or is refused. The
    table holds every E-63 kind, where a lock's datasets stand for the period and where none
    does; a kind added to the enumeration without its words fails here, by ``RECORD_WORDS``."""
    fixture = _fixture(script)
    rows = fixture["records"]
    assert [(row["kind"], row["dataset_lock_id"] is not None) for row in rows] == [
        (kind.value, standing) for kind in LockKind for standing in (True, False)
    ]
    lock = str(script.LOCK.lock_id)
    for row in rows:
        assert row["period_key"] == script.LOCK.period_key
        assert row["dataset_lock_id"] in (lock, None)
        if row["kind"] == LockKind.LOCK.value:
            # The record of a close is never refused, whether its datasets still stand or not.
            assert row["id"] == lock and row["refusal"] is None
            continue
        assert row["id"] != lock
        refusal = row["refusal"]
        assert refusal.startswith(
            f"Lock {row['id']} is {locked.RECORD_WORDS[row['kind']]} of {row['period_key']}: "
        )
        # Then the lock to pass, or that none stands for the period.
        if row["dataset_lock_id"] is None:
            assert refusal.endswith(locked.NO_DATASET_LOCK.format(period=row["period_key"]))
        else:
            assert refusal.endswith(
                locked.PASS_DATASET_LOCK.format(period=row["period_key"], dataset_lock=lock)
            )


def test_the_table_asks_every_key_of_every_report_that_takes_a_lock(script: ModuleType) -> None:
    fixture = _fixture(script)
    by_report: dict[str, list[dict[str, Any]]] = {}
    for case in fixture["cases"]:
        by_report.setdefault(case["report"], []).append(case)
    taking = [item.code for item in DEFINITIONS if LOCK_KEY in item.parameters_schema["properties"]]
    assert sorted(by_report) == sorted(taking)
    for code in taking:
        cases = {case["case"]: case for case in by_report[code]}
        alone = cases["the lock alone"]
        if code not in locked.SNAPSHOT_KIND_BY_REPORT:
            # Refused by name, as framework._resolve refuses a report without a lock dataset.
            assert list(cases) == ["the lock alone"], code
            assert alone["findings"] == [
                {
                    "field": locked.FIELD,
                    "rule_id": locked.RULE,
                    "message": locked.NO_DATASET.format(code=code),
                }
            ]
            continue
        assert alone["findings"] == [], code
        assert cases["the lock with its own selectors"]["findings"] == [], code
        properties = DEFINITIONS_BY_CODE[code].parameters_schema["properties"]
        for key in properties:
            if key in locked.ADMITTED_KEYS:
                continue
            (found,) = cases[f"the lock with {key}"]["findings"]
            assert found["field"] == f"parameters.{key}", (code, key)
        assert [item["field"] for item in cases["another entity"]["findings"]] == [
            "parameters.entity_codes"
        ]
        for key in locked.PERIOD_KEYS:
            if key in properties:
                (found,) = cases[f"another period as {key}"]["findings"]
                assert found["field"] == f"parameters.{key}", (code, key)


def test_check_names_a_stale_file_and_the_command(
    script: ModuleType,
    scratch: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert script.main(["--check"]) == 0
    assert capsys.readouterr().out == ""

    # A file that no longer says what the API gives: reported by its path, with the command.
    moved = scratch / "lock-datasets.json"
    moved.write_text('{\n  "rpo": "RPO"\n}\n', encoding="utf-8")
    monkeypatch.setattr(script, "DATASETS_FILE", moved)
    monkeypatch.setattr(script, "ROOT", scratch)
    monkeypatch.setattr(script, "FIXTURE_FILE", scratch / "as-locked.json")
    assert script.main(["--check"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        f"lock-datasets.json is stale; run {COMMAND}",
        f"as-locked.json is stale; run {COMMAND}",
    ]
    # Without --check the files are written, and the check passes on them.
    assert script.main([]) == 0
    capsys.readouterr()
    assert script.main(["--check"]) == 0
    assert json.loads(moved.read_text(encoding="utf-8")) == dict(locked.SNAPSHOT_KIND_BY_REPORT)
