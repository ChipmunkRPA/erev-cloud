"""The sixth baseline check ``setting-references`` (05 REL-07) and ``erev doctor --analyze``
(05 PERF-27; DG-MK-perf-seed step 4), without a database (BUILD_SPEC SOP-6; runbook RB-03).

The pg counterpart ``tests/pg/test_doctor.py::test_rel_07_unknown_setting_reference`` creates a
probe function and runs the command; here the predicate, the source parser, the catalogue
collector over a fake connection, the analyze helper over a fake engine, and the CLI composition
are exercised.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from erev_api.config import Environment
from erev_api.controls import doctor
from erev_api.controls.doctor import (
    CHECK_NAMES,
    DOCUMENTED_SETTINGS,
    SETTING_REFERENCES,
    UNPARSABLE_SETTING,
    UNRESOLVED_SETTING,
    AnalyzeFailed,
    CheckResult,
    FunctionSettingReferences,
    UnknownTable,
    analyze_tables,
    observe_setting_references,
    referenced_settings,
    run_doctor,
    setting_references,
)
from erev_api.db import session as db_session
from support.clock import frozen_clock
from support.operators import invoke, operator_services

TENANT_FN = FunctionSettingReferences("erev_current_tenant()", ("app.tenant_id",))
SCOPE_FN = FunctionSettingReferences(
    "tg_tenant__platform_scope()", ("app.entity_scope", "app.platform_scope")
)
PLAIN_FN = FunctionSettingReferences("tg_audit_event__immutable()", ())


def test_check_names_end_with_setting_references() -> None:
    assert len(CHECK_NAMES) == 6 and CHECK_NAMES[-1] == SETTING_REFERENCES
    assert DOCUMENTED_SETTINGS == frozenset(
        {
            "app.tenant_id",
            "app.user_id",
            "app.entity_scope",
            "app.platform_scope",
            "app.data_fix_ticket",
        }
    )


@pytest.mark.parametrize(
    ("source", "settings"),
    [
        ("SELECT nullif(current_setting('app.tenant_id', true), '')::uuid", ("app.tenant_id",)),
        (
            "IF current_setting( 'app.platform_scope' , true) = 'provisioning' THEN\n"
            "  PERFORM current_setting('app.entity_scope', true);",
            ("app.entity_scope", "app.platform_scope"),
        ),
        ("BEGIN RETURN NEW; END", ()),
        ("current_setting('app.x') || current_setting('app.x')", ("app.x",)),
        ("current_setting('bad name!')", (UNPARSABLE_SETTING,)),
        # Codex P4C-S6-R1: SQL lexical structure — spelling, whitespace and comments before the
        # parenthesis, quoted function name, E-strings, dollar-quoted strings.
        ("SELECT CURRENT_SETTING('app.unlisted', true)", ("app.unlisted",)),
        ("SELECT current_setting ('app.unlisted', true)", ("app.unlisted",)),
        ("SELECT current_setting\n('app.unlisted', true)", ("app.unlisted",)),
        ("SELECT current_setting /* planner */ ('app.unlisted', true)", ("app.unlisted",)),
        ("SELECT \"current_setting\"('app.unlisted', true)", ("app.unlisted",)),
        ("SELECT pg_catalog.current_setting('app.unlisted', true)", ("app.unlisted",)),
        ("SELECT current_setting(E'app.unlisted', true)", ("app.unlisted",)),
        ("SELECT current_setting(E'app.\\x75nlisted', true)", ("app.unlisted",)),
        ("SELECT current_setting($$app.unlisted$$, true)", ("app.unlisted",)),
        ("SELECT current_setting($q$app.unlisted$q$)", ("app.unlisted",)),
        ("SELECT current_setting('app.it''s')", (UNPARSABLE_SETTING,)),
        # An argument that is not a single string literal is never resolved to a documented name.
        ("SELECT current_setting('app.tenant_id' || '_shadow', true)", (UNRESOLVED_SETTING,)),
        ("SELECT current_setting(setting_name, true)", (UNRESOLVED_SETTING,)),
        ("SELECT current_setting(lower('APP.TENANT_ID'))", (UNRESOLVED_SETTING,)),
        ("SELECT current_setting(42)", (UNRESOLVED_SETTING,)),
        ("SELECT current_setting()", (UNRESOLVED_SETTING,)),
        # Comments and string contents are not references.
        ("-- current_setting('app.unlisted',true)\nSELECT 1", ()),
        ("/* current_setting('app.unlisted',true) */ SELECT 1", ()),
        ("/* outer /* nested current_setting('app.unlisted') */ still comment */ SELECT 1", ()),
        ("SELECT 'current_setting(''app.unlisted'')'", ()),
        ("SELECT $$ current_setting('app.unlisted') $$", ()),
        ('SELECT "current_setting" FROM t', ()),
        ("SELECT \"CURRENT_SETTING\"('app.unlisted')", ()),
        ("SELECT my_current_setting('app.unlisted')", ()),
    ],
)
def test_rel_07_referenced_settings_parsing(source: str, settings: tuple[str, ...]) -> None:
    assert referenced_settings(source) == settings


def test_rel_07_setting_references_predicate() -> None:
    ok = setting_references((TENANT_FN, SCOPE_FN, PLAIN_FN))
    assert ok.ok and ok.lines() == [
        f"OK {SETTING_REFERENCES}: 3 functions reference only the documented app.* settings"
    ]
    probe = FunctionSettingReferences(
        "tg_probe__data_fix()", ("app.data_fix_other", "app.tenant_id")
    )
    failing = setting_references((TENANT_FN, probe))
    assert failing.failures == (
        "function tg_probe__data_fix() references setting app.data_fix_other, which 04 does not "
        "list (05 REL-07)",
    )
    assert failing.lines() == [f"FAIL {SETTING_REFERENCES}: {failing.failures[0]}"]
    # A reference whose name is not identifier-shaped is named as unparsable, never echoed.
    odd = setting_references((FunctionSettingReferences("tg_odd()", ("<unparsable>",)),))
    assert odd.failures == (
        "function tg_odd() references a setting whose name is not identifier-shaped (05 REL-07)",
    )
    assert setting_references(()).summary == (
        "0 functions reference only the documented app.* settings"
    )
    # Codex P4C-S6-R1: an unresolved argument can never establish "only documented settings".
    unresolved = setting_references(
        (FunctionSettingReferences("tg_shadow()", (UNRESOLVED_SETTING, "app.tenant_id")),)
    )
    assert unresolved.failures == (
        "function tg_shadow() passes current_setting an argument that is not a single string "
        "literal (05 REL-07)",
    )


def test_rel_07_composition_fails_on_an_unlisted_setting_in_any_spelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex P4C-S6-R1 composition control: the real collector and predicate over a synthetic
    catalogue row spelled ``CURRENT_SETTING ('app.unlisted',true)`` turn the sixth result FAIL."""

    class _Connection:
        def execute(self, statement: object) -> Iterable[tuple[str, str | None]]:
            return [
                ("erev_current_tenant()", "SELECT current_setting('app.tenant_id', true)"),
                ("tg_shadow()", "SELECT CURRENT_SETTING ('app.unlisted',true)"),
                ("tg_commented()", "-- current_setting('app.unlisted',true)\nSELECT 1"),
            ]

    @contextmanager
    def connection(*, request_id: str) -> Iterator[_Connection]:
        yield _Connection()

    def sentinel(name: str) -> object:
        return lambda *args, **kwargs: CheckResult(name, "sentinel")

    monkeypatch.setattr(doctor, "catalogue_connection", connection)
    for name in ("row_level_security", "app_role", "immutability_triggers", "audit_chain", "ai"):
        monkeypatch.setattr(doctor, name, sentinel(name.replace("_", "-")))
    monkeypatch.setattr(doctor, "_tenants", lambda *, keyring, request_id: [])
    results = run_doctor(
        clock=frozen_clock(),
        keyring=None,  # type: ignore[arg-type]
        request_id="test",
        ai_kill_switch=False,
    )
    assert [r.check for r in results] == list(CHECK_NAMES) and len(results) == 6
    sixth = results[-1]
    assert sixth.failures == (
        "function tg_shadow() references setting app.unlisted, which 04 does not list (05 REL-07)",
    )


def test_rel_07_collector_reads_function_sources() -> None:
    class _Connection:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: object) -> Iterable[tuple[str, str | None]]:
            self.statements.append(str(statement))
            return [
                ("erev_current_tenant()", "SELECT current_setting('app.tenant_id', true)"),
                ("tg_probe__data_fix()", "IF current_setting('app.data_fix_other', true) = 'x'"),
                ("tg_plain()", None),
            ]

    connection = _Connection()
    observed = observe_setting_references(connection)  # type: ignore[arg-type]
    assert "pg_proc" in connection.statements[0] and "nspname = 'erev'" in connection.statements[0]
    assert observed == (
        FunctionSettingReferences("erev_current_tenant()", ("app.tenant_id",)),
        FunctionSettingReferences("tg_probe__data_fix()", ("app.data_fix_other",)),
        FunctionSettingReferences("tg_plain()", ()),
    )
    assert setting_references(observed).failures == (
        "function tg_probe__data_fix() references setting app.data_fix_other, which 04 does not "
        "list (05 REL-07)",
    )


# Codex P4C-S6-R2: a fabricated credential canary, never a real value.
CANARY = "P4C-SYNTHETIC-CANARY-3b1e"


class _FakeConnection:
    def __init__(self, log: list[str], failure: Exception | None, fail_at: int) -> None:
        self._log = log
        self._failure = failure
        self._fail_at = fail_at

    def exec_driver_sql(self, statement: str) -> None:
        if self._failure is not None and len(self._log) + 1 == self._fail_at:
            raise self._failure
        self._log.append(statement)


class _FakeEngine:
    def __init__(self, *, failure: Exception | None = None, fail_at: int = 1) -> None:
        self.statements: list[str] = []
        self.disposed = False
        self.entered = 0
        self._failure = failure
        self._fail_at = fail_at

    @contextmanager
    def begin(self) -> Iterator[_FakeConnection]:
        self.entered += 1
        if self._failure is not None and self._fail_at == 0:
            raise self._failure
        yield _FakeConnection(self.statements, self._failure, self._fail_at)

    def dispose(self) -> None:
        self.disposed = True


def test_analyze_tables_allow_lists_schema_erev_tables() -> None:
    engine = _FakeEngine()
    count = analyze_tables(  # type: ignore[arg-type]
        engine, ["schedule_line", "subledger_line", "contract_event", "obligation_version"]
    )
    assert count == 4
    assert engine.statements == [
        "ANALYZE erev.schedule_line",
        "ANALYZE erev.subledger_line",
        "ANALYZE erev.contract_event",
        "ANALYZE erev.obligation_version",
    ]
    # Every name is validated before the first statement: nothing is entered or planned.
    for names in (
        ["schedule_line", "nope"],
        ["erev.schedule_line; DROP"],
        ["erev.schedule_line"],
        ["public.schedule_line"],
        ["schedule_line\nDROP TABLE x"],
    ):
        refused = _FakeEngine()
        with pytest.raises(UnknownTable) as unknown:
            analyze_tables(refused, names)  # type: ignore[arg-type]
        assert unknown.value.table in names and refused.entered == 0 and refused.statements == []
    assert analyze_tables(_FakeEngine(), []) == 0  # type: ignore[arg-type]


def test_analyze_tables_execution_failure_is_type_and_position_only() -> None:
    """Codex P4C-S6-R2: an execution-layer failure renders as the exception type and the table
    position, never its message; the message may carry anything the driver saw."""
    engine = _FakeEngine(failure=ValueError(f"password={CANARY}"), fail_at=2)
    with pytest.raises(AnalyzeFailed) as failed:
        analyze_tables(engine, ["schedule_line", "subledger_line", "contract_event"])  # type: ignore[arg-type]
    assert str(failed.value) == "ANALYZE failed at table 2 of 3: ValueError"
    assert (failed.value.index, failed.value.count, failed.value.exception_type) == (
        2,
        3,
        "ValueError",
    )
    assert CANARY not in repr(failed.value) and failed.value.__cause__ is None
    assert engine.statements == ["ANALYZE erev.schedule_line"]
    before_first = _FakeEngine(failure=RuntimeError(f"Authorization: Bearer {CANARY}"), fail_at=0)
    with pytest.raises(AnalyzeFailed) as connect:
        analyze_tables(before_first, ["schedule_line"])  # type: ignore[arg-type]
    assert str(connect.value) == "ANALYZE failed at table 0 of 1: RuntimeError"


def test_cli_doctor_analyze_runs_analyze_as_owner_and_no_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engines: list[_FakeEngine] = []
    roles: list[str] = []

    def build_engine(url: str, *, role: str, component: str) -> _FakeEngine:
        roles.append(role)
        engines.append(_FakeEngine())
        return engines[-1]

    def never(*args: object, **kwargs: object) -> list[CheckResult]:
        raise AssertionError("run_doctor must not run under --analyze")

    monkeypatch.setattr(db_session, "build_engine", build_engine)
    monkeypatch.setattr(doctor, "run_doctor", never)
    services = operator_services(None, frozen_clock(), tmp_path, env=Environment.TEST)  # type: ignore[arg-type]
    result = invoke(services, ["doctor", "--analyze", "schedule_line, subledger_line"])
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == ["OK analyze: 2 tables analyzed as erev_owner"]
    assert roles == ["erev_owner"] and engines[0].disposed
    assert engines[0].statements == ["ANALYZE erev.schedule_line", "ANALYZE erev.subledger_line"]
    unknown = invoke(services, ["doctor", "--analyze", "nope"])
    assert unknown.exit_code == 2 and unknown.stdout.strip() == "unknown table nope"
    assert engines[1].disposed and engines[1].entered == 0
    mixed = invoke(services, ["doctor", "--analyze", "schedule_line, erev.schedule_line; DROP"])
    assert mixed.exit_code == 2 and mixed.stdout.startswith("unknown table ")
    assert engines[2].entered == 0 and engines[2].statements == [] and engines[2].disposed


def test_cli_doctor_analyze_never_echoes_an_execution_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Codex P4C-S6-R2 through the actual Typer command: an execution-layer ValueError carrying a
    canary renders as type and position, exit 1, engine disposed; no message text anywhere."""
    engines: list[_FakeEngine] = []

    def build_engine(url: str, *, role: str, component: str) -> _FakeEngine:
        engines.append(_FakeEngine(failure=ValueError(f"password={CANARY}"), fail_at=1))
        return engines[-1]

    monkeypatch.setattr(db_session, "build_engine", build_engine)
    monkeypatch.setattr(doctor, "run_doctor", lambda *a, **k: pytest.fail("no doctor checks"))
    services = operator_services(None, frozen_clock(), tmp_path, env=Environment.TEST)  # type: ignore[arg-type]
    result = invoke(services, ["doctor", "--analyze", "schedule_line"])
    assert result.exit_code == 1, result.output
    assert CANARY not in result.output and "password" not in result.output
    assert result.stdout.strip() == "ANALYZE failed at table 1 of 1: ValueError"
    assert engines[0].disposed


def test_run_doctor_appends_setting_references_after_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def no_connection(*, request_id: str) -> Iterator[None]:
        yield None

    def sentinel(name: str) -> object:
        return lambda *args, **kwargs: CheckResult(name, "sentinel")

    monkeypatch.setattr(doctor, "catalogue_connection", no_connection)
    for name in ("row_level_security", "app_role", "immutability_triggers", "audit_chain", "ai"):
        monkeypatch.setattr(doctor, name, sentinel(name.replace("_", "-")))
    monkeypatch.setattr(doctor, "_tenants", lambda *, keyring, request_id: [])
    monkeypatch.setattr(
        doctor,
        "observe_setting_references",
        lambda connection: (
            TENANT_FN,
            FunctionSettingReferences("tg_probe__data_fix()", ("app.data_fix_other",)),
        ),
    )
    results = run_doctor(
        clock=frozen_clock(),
        keyring=None,  # type: ignore[arg-type]
        request_id="test",
        ai_kill_switch=False,
    )
    assert [r.check for r in results] == list(CHECK_NAMES)
    assert not results[-1].ok and "tg_probe__data_fix()" in results[-1].failures[0]
