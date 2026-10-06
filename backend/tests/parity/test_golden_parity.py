"""G3 golden parity cases (docs/dev-guide.md §9.6 DG-PAR-01 to DG-PAR-11; §4.4 DG-MK-parity;
BUILD_SPEC GPA-1).

One parametrised case per id of ``docs/legacy/golden/golden-tests.json``, with the id
``<kind>::<test id>`` (DG-PAR-01). Each case first checks the DG-PAR-03 preconditions, so a stale
``deviations.json`` fails every case before any database work. The case then reads the DG-PAR-04
scenario through the reader of its kind (DG-PAR-05). The scenario is built once per session and
replayed up to the case's ``steps_through``. The case compares the values with ``deviations.json``
under DG-PAR-07. No case is skipped or marked xfail (DG-PAR-09): a kind whose reader a later item
builds fails and names that item. Outcomes reach the ``make parity`` report through
``report.record`` (DG-PAR-08). Kind ``point_in_time_equivalence`` (GPB-3) replays into its own
tenant through ``support.parity.equivalence`` and is compared exactly (``rows`` and
``columns_with_mismatch``), like the probes outside the shared scenario.
"""

from __future__ import annotations

from typing import NoReturn

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.config import get_settings
from support.parity import compare, equivalence, integrity, probes, report, values
from support.parity.integrity import GoldenCase
from support.parity.scenario import ParityScenario

pytestmark = pytest.mark.parity


def _fail(
    request: pytest.FixtureRequest, case: GoldenCase, outcome: report.CaseOutcome
) -> NoReturn:
    report.record(request.config, case, outcome)
    pytest.fail(outcome.message or case.case_id, pytrace=False)


def _probe(case: GoldenCase, request: pytest.FixtureRequest) -> None:
    """DG-PAR-06: a legacy probe replays in its own fresh tenant, not in the scenario."""
    try:
        request.getfixturevalue("test_database")
        keyring: KeyRing = request.getfixturevalue("keyring")
        factory: pytest.TempPathFactory = request.getfixturevalue("tmp_path_factory")
        root = factory.mktemp("probe-files")
        mismatches = probes.check(
            case, get_settings().model_copy(update={"file_root": root}), keyring
        )
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        report.record(request.config, case, report.CaseOutcome(False, message=message))
        raise
    if mismatches:
        found = compare.ParityMismatchError(case.case_id, mismatches)
        _fail(request, case, report.CaseOutcome(False, tuple(mismatches), str(found)))
    report.record(request.config, case, report.CaseOutcome(True))


def _journal(case: GoldenCase, request: pytest.FixtureRequest) -> None:
    """Kind ``journal_entry_totals`` (GPB-1): report runs compared field by field."""
    try:
        world: ParityScenario = request.getfixturevalue("parity_scenario")
        mismatches = values.journal_check(world, case)
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        report.record(request.config, case, report.CaseOutcome(False, message=message))
        raise
    if mismatches:
        found = compare.ParityMismatchError(case.case_id, mismatches)
        _fail(request, case, report.CaseOutcome(False, tuple(mismatches), str(found)))
    report.record(request.config, case, report.CaseOutcome(True))


def _equivalence(case: GoldenCase, request: pytest.FixtureRequest) -> None:
    """Kind ``point_in_time_equivalence`` (GPB-3): the shipped ``Contract_Live`` rows against the
    export rows of the prescribed replay, through F-LMG's ``compare_point_in_time``, in this kind's
    own tenant; ``rows`` and ``columns_with_mismatch`` compared exactly."""
    try:
        request.getfixturevalue("test_database")
        keyring: KeyRing = request.getfixturevalue("keyring")
        factory: pytest.TempPathFactory = request.getfixturevalue("tmp_path_factory")
        root = factory.mktemp("equivalence-files")
        found = equivalence.check(
            case, get_settings().model_copy(update={"file_root": root}), keyring
        )
        mismatches = equivalence.mismatches(case.expected, found.result)
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        report.record(request.config, case, report.CaseOutcome(False, message=message))
        raise
    if mismatches:
        failed = compare.ParityMismatchError(case.case_id, mismatches)
        _fail(request, case, report.CaseOutcome(False, tuple(mismatches), str(failed)))
    report.record(request.config, case, report.CaseOutcome(True))


@pytest.mark.parametrize("case", integrity.cases(), ids=lambda case: case.case_id)
def test_golden_parity(case: GoldenCase, request: pytest.FixtureRequest) -> None:
    if not integrity.session_integrity().ok:
        _fail(request, case, report.CaseOutcome(False, message=integrity.STALE))
    if case.kind == probes.KIND:
        _probe(case, request)
        return
    if case.kind == values.JOURNAL_KIND:
        _journal(case, request)
        return
    if case.kind == equivalence.KIND:
        _equivalence(case, request)
        return
    reader = values.READERS.get(case.kind)
    if reader is None:
        builder = values.PENDING.get(case.kind, "a later GPA item")
        message = f"kind {case.kind} has no parity reader yet; {builder} builds it"
        _fail(request, case, report.CaseOutcome(False, message=message))
    try:
        world: ParityScenario = request.getfixturevalue("parity_scenario")
        actual = reader(world, case)
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        report.record(request.config, case, report.CaseOutcome(False, message=message))
        raise
    mismatches = compare.unit_fields(case.expected, actual, case.legacy)
    if mismatches:
        found = compare.ParityMismatchError(case.case_id, mismatches)
        _fail(request, case, report.CaseOutcome(False, tuple(mismatches), str(found)))
    report.record(request.config, case, report.CaseOutcome(True))
