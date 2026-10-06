"""The four stamping consumers write the process's own release row (05 REL-03 consumers, rev 1.15;
DG-KRN-JOB-13 rev 1.25; ``controls.stamping``; lane P5 integration slice 1). DB-free: a Session
stand-in answers only the latest-per-version fallback query and counts how often it was asked."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.config import Environment
from erev_api.controls import release
from erev_api.controls.release import EngineRelease
from erev_api.domain.contracts import computation, compute_job
from erev_api.domain.journals import summarise
from erev_api.domain.reports import framework
from erev_api.problems import Problem
from erev_engine import ENGINE_VERSION

LATEST = UUID(int=9)  # "the latest engine_release row of the running version" — never the answer


class _Result:
    def __init__(self, value: UUID | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> UUID | None:
        return self.value


class _Session:
    """Answers the latest-per-version query only; counts how often it was asked."""

    def __init__(self, latest: UUID | None = LATEST) -> None:
        self.latest = latest
        self.queries = 0

    def execute(self, statement: Any) -> _Result:
        self.queries += 1
        return _Result(self.latest)


def _release(version: str = ENGINE_VERSION) -> EngineRelease:
    return EngineRelease(uuid4(), version, "b" * 40, "0055", datetime(2026, 9, 19, tzinfo=UTC))


Consumer = Callable[[Any], UUID]
CONSUMERS: tuple[tuple[str, Consumer], ...] = (
    ("computation.persist", lambda s: computation._engine_release_id(s, ENGINE_VERSION)),
    ("compute_job", lambda s: compute_job._release_id(s, ENGINE_VERSION)),
    ("journals.summarise", lambda s: summarise._release_id(s)),
    ("reports.framework", lambda s: framework._release_id(s)),
)
IDS = [name for name, _ in CONSUMERS]


@pytest.fixture
def process_state() -> Iterator[None]:
    """Restore what ``stamp_release`` would have recorded in this process."""
    # getattr: the fixture also runs against a source without the slice (fail-first evidence), where
    # the consumers ignore the process release and answer the latest row.
    before = release.current_release()
    env = getattr(release, "current_environment", lambda: None)()
    try:
        yield
    finally:
        release.remember_release(before)
        getattr(release, "remember_environment", lambda value: None)(env)


@pytest.mark.parametrize(("name", "consumer"), CONSUMERS, ids=IDS)
def test_consumers_stamp_the_process_release_never_the_latest_row(
    process_state: None, name: str, consumer: Consumer
) -> None:
    current = _release()
    release.remember_release(current)
    getattr(release, "remember_environment", lambda value: None)(Environment.PRODUCTION)
    session = _Session()  # a newer row of the same version exists; it must not be consulted
    assert consumer(session) == current.id, name
    assert session.queries == 0, name


@pytest.mark.control("CTL-032")
@pytest.mark.parametrize(("name", "consumer"), CONSUMERS, ids=IDS)
def test_consumers_fail_closed_in_production_without_a_stamped_release(
    process_state: None, name: str, consumer: Consumer
) -> None:
    """CTL-032, the refusal of an unstamped process: in production each of the four
    consumers that write a run record refuses (``release-mismatch``) when the
    process stamped no release, and consults no row. Not witnessed here: the stamp
    on the records through the product
    (``tests/domain/platform/test_release_stamping.py``) and the evidence writer
    (``test_evidence_release_identity.py``).
    """
    release.remember_release(None)
    release.remember_environment(Environment.PRODUCTION)
    session = _Session()
    with pytest.raises(Problem) as refused:
        consumer(session)
    assert refused.value.slug == "release-mismatch" and session.queries == 0, name


@pytest.mark.control("CTL-032")
@pytest.mark.parametrize(("name", "consumer"), CONSUMERS, ids=IDS)
def test_consumers_fall_back_only_in_dev_or_test_and_refuse_another_engine_version(
    process_state: None, name: str, consumer: Consumer
) -> None:
    """CTL-032, the refusal of an unstamped process, its bounds: a process that
    remembered the test environment falls back to the latest row of the version
    (one lookup); one that remembered none, the e2e or the production environment
    refuses (``release-mismatch``) without a lookup; and a process whose release is
    of another engine version refuses. Not witnessed here: the stamp on the
    records through the product
    (``tests/domain/platform/test_release_stamping.py``).
    """
    release.remember_release(None)
    release.remember_environment(Environment.TEST)
    session = _Session()
    assert consumer(session) == LATEST and session.queries == 1, name
    # D-98 60: a process that never stamped (no remembered environment) fails closed, as e2e and
    # production do; only a remembered dev / test environment falls back.
    for env in (None, Environment.E2E, Environment.PRODUCTION):
        release.remember_environment(env)
        session = _Session()
        with pytest.raises(Problem) as closed:
            consumer(session)
        # Codex oracle (PRODUCTION-P5-INTEGRATION-REVIEW-9564d08): refusal, zero fallback SELECT.
        assert closed.value.slug == "release-mismatch" and session.queries == 0, (name, env)
    release.remember_environment(Environment.TEST)
    # A process row of another engine version never stamps this version's output.
    release.remember_release(_release("0.0.1"))
    with pytest.raises(Problem) as refused:
        consumer(_Session())
    assert refused.value.slug == "release-mismatch", name
