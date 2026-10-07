"""G4 answer keys (docs/dev-guide.md §9.5.8; DG-MK-answer-keys; BUILD_SPEC EKC-12).

One test per selected active key (`FAMILY`, `ID`, `REQ`; DG-AK-42). A withdrawn id in the selection
is validated and reported, never collected (DG-AK-13; D-79). Engine keys run through `run_engine`
and `assert_checkpoints`. Platform keys run through `platform_runner.run_platform` (BUILD_SPEC
PRP-1 to PRP-3): on the in-memory platform the best outcome is `not_run` with the in-memory
evidence (XR-12: never green without the database platform), any mismatch is `failed`, and the
pytest item fails in both cases; `passed` needs every block compared clean on the database
platform (`EREV_AK_PLATFORM=db`). Each outcome reaches the `make answer-keys` report through
`report.record`, with the run note of the inputs the runner derived from the key (D-85).

A platform key is judged by `platform_runner.key_verdict`: supported overrides follow the
approval lifecycle, while unsupported declarations produce a finding beside numeric mismatches.
"""

from __future__ import annotations

import dataclasses

import pytest
from support.answer_keys.loader import LoadedKey, active_selection
from support.answer_keys.platform_runner import key_verdict, run_platform
from support.answer_keys.report import KeyOutcome, outcome_of, record
from support.answer_keys.runners import assert_checkpoints, run_engine

pytestmark = pytest.mark.answer_key


@pytest.mark.parametrize("loaded", active_selection(), ids=lambda k: k.key.id)
def test_answer_key(loaded: LoadedKey, request: pytest.FixtureRequest) -> None:
    notes: tuple[str, ...] = ()
    if loaded.key.runner == "platform":
        _platform_key(loaded, request)
        return
    try:
        result = run_engine(loaded)
        notes = result.notes
        assert_checkpoints(loaded, result)
    except Exception as error:
        record(request.config, loaded, dataclasses.replace(outcome_of(error), notes=notes))
        raise
    record(request.config, loaded, KeyOutcome("passed", notes=notes))


def _platform_key(loaded: LoadedKey, request: pytest.FixtureRequest) -> None:
    """Run and compare a platform key; record its verdict; fail unless it passed on the database
    platform (XR-12 kept honest: an in-memory run is evidence, not closure). The verdict is the
    key's (``key_verdict``): the run's outcome with a finding for unsupported policy overrides
    among the mismatches and at the end of the message."""
    try:
        result = run_platform(loaded)
    except Exception as error:
        record(request.config, loaded, outcome_of(error))
        raise
    status, mismatches, message = key_verdict(loaded, result)
    record(request.config, loaded, KeyOutcome(status, mismatches, message, result.notes))
    if status != "passed":
        pytest.fail(f"{loaded.key.id}: {status}: {message}", pytrace=False)
