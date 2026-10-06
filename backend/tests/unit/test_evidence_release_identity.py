"""The SOP-1 evidence producer (``controls.evidence._release_id``, P4) resolves the process release
through ``controls.stamping.process_release_id`` like the four D-96 consumers (05 REL-03 rev 1.15;
D-98 60). This is the branch behind the integrated-batch failures of ``tests/pg/test_doctor.py``
(P5-DOCTOR-R1): the doctor tests' job runtime never stamped, so the ``AUDIT_CHAIN_VERIFY`` job's
CTL-039 evidence write raised ``Problem("release-mismatch")`` before consulting the inserted probe
row, no verification record was written and doctor saw "0 of 1" tenants verified. DB-free: a
Session stand-in answers only the fallback query."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.config import Environment
from erev_api.controls import evidence, release
from erev_api.controls.release import EngineRelease
from erev_api.problems import Problem
from erev_engine import ENGINE_VERSION

INSERTED_ROW = UUID(int=39)  # the probe row ``insert_engine_release`` puts in the table


class _Result:
    def scalar_one_or_none(self) -> UUID:
        return INSERTED_ROW


class _Session:
    def __init__(self) -> None:
        self.queries = 0

    def execute(self, statement: Any) -> _Result:
        self.queries += 1
        return _Result()


@pytest.fixture
def process_state() -> Iterator[None]:
    before, env = release.current_release(), release.current_environment()
    try:
        yield
    finally:
        release.remember_release(before)
        release.remember_environment(env)


@pytest.mark.control("CTL-032")
def test_unstamped_process_fails_closed_before_any_lookup(process_state: None) -> None:
    """The doctor fixture's state before P5-DOCTOR-R1: a probe row exists, nothing stamped, no
    environment remembered → refusal without consulting the table (the diagnosed branch).

    Of CTL-032's row this witnesses the refusal of an unstamped process at the
    fifth stamping site, the control-evidence writer (``controls.evidence``); the
    other four are ``test_consumer_release_identity.py``. Not witnessed here: the
    stamp on the records through the product
    (``tests/domain/platform/test_release_stamping.py``).
    """
    release.remember_release(None)
    release.remember_environment(None)
    session = _Session()
    with pytest.raises(Problem) as refused:
        evidence._release_id(session)  # type: ignore[arg-type]
    assert refused.value.slug == "release-mismatch" and session.queries == 0


def test_stamped_process_records_its_own_release(process_state: None) -> None:
    """After ``stamp_test_release()`` (the shared pg support): the stamped row, no lookup."""
    stamped = EngineRelease(
        uuid4(), ENGINE_VERSION, "tests-ctr-2", "0055", datetime(2026, 9, 20, tzinfo=UTC)
    )
    release.remember_release(stamped)
    release.remember_environment(Environment.TEST)
    session = _Session()
    assert evidence._release_id(session) == stamped.id  # type: ignore[arg-type]
    assert session.queries == 0


@pytest.mark.control("CTL-032")
def test_remembered_test_environment_without_a_stamp_falls_back_to_the_row(
    process_state: None,
) -> None:
    """Only a remembered dev / test environment may fall back to the inserted row (one lookup);
    production and unremembered environments never do (D-98 60).

    Of CTL-032's row this witnesses the bounds of the refusal of an unstamped
    process at the evidence writer: one that remembered the test environment falls
    back (one lookup); one that remembered the production or the e2e environment,
    or none, refuses.
    """
    release.remember_release(None)
    release.remember_environment(Environment.TEST)
    session = _Session()
    assert evidence._release_id(session) == INSERTED_ROW  # type: ignore[arg-type]
    assert session.queries == 1
    for env in (Environment.PRODUCTION, Environment.E2E, None):
        release.remember_environment(env)
        with pytest.raises(Problem):
            evidence._release_id(_Session())  # type: ignore[arg-type]
