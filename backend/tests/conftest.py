"""Shared pytest configuration for the eRev Cloud backend suite (docs/dev-guide.md §9)."""

from __future__ import annotations

import os

# DG-ENV-10: pytest forces EREV_ENV before any erev_api import; only make perf sets EREV_PERF_RUN.
PERF_RUN = os.environ.get("EREV_PERF_RUN") == "1"
os.environ["EREV_ENV"] = "dev" if PERF_RUN else "test"
# DG-LAY-01, DG-LAY-08: Hypothesis keeps its storage under backend/.hypothesis, never in the
# working directory; it reads the variable when it first needs the directory.
os.environ["HYPOTHESIS_STORAGE_DIRECTORY"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".hypothesis"
)

import io  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import structlog  # noqa: E402
from erev_api.auth.keyring import KeyRing, build_keyring  # noqa: E402
from erev_api.clock import FrozenClock  # noqa: E402
from erev_api.config import Environment, Settings, get_settings  # noqa: E402
from erev_api.db.lint import lint_as_app  # noqa: E402
from erev_api.db.session import (  # noqa: E402
    CONTEXT_INFO_KEY,
    DbContext,
    dispose_engines,
    owner_engine,
    set_component,
    set_tenant_context,
)
from erev_api.logging import configure_logging  # noqa: E402
from hypothesis import HealthCheck, settings  # noqa: E402
from hypothesis.database import DirectoryBasedExampleDatabase  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from support import log_guard, markers, network  # noqa: E402
from support.clock import frozen_clock  # noqa: E402
from support.db import TEST_DB_LOCK_KEY, TestDatabase, fresh_head  # noqa: E402
from support.markers import area_of, collection_rank  # noqa: E402

set_component("tests")

TESTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TESTS_ROOT.parents[1]

# DG-PROP-01: dev by default, ci for make test and make ci, thorough for make properties (§9.7).
_EXAMPLE_DATABASE = DirectoryBasedExampleDatabase(str(REPO_ROOT / "backend/.hypothesis"))
settings.register_profile(
    "dev", max_examples=20, deadline=2000, database=_EXAMPLE_DATABASE, print_blob=True
)
settings.register_profile(
    "ci",
    max_examples=100,
    deadline=None,
    derandomize=True,
    database=None,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "thorough",
    max_examples=1000,
    deadline=None,
    derandomize=False,
    database=_EXAMPLE_DATABASE,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
# DG-TST-10: the session fixture runs only against these databases.
TEST_DATABASES = re.compile(r"^(erev_test|erev_rv_[a-z0-9_]+)$")

SessionFactory = Callable[[DbContext], Session]

# docs/dev-guide.md §9.2.
MARKERS = (
    "control(control_id): designated system control CTL-NNN proven by this test (G7)",
    "parity: legacy golden parity case (G3)",
    "answer_key: accounting answer key (G4)",
    "property: Hypothesis invariant (G5)",
    "pg: isolation, immutability, chain, invariant, lint and migration suite (G6)",
    "perf: performance benchmark (G9)",
    "slow: a single test that takes more than 10 seconds",
)
# DG-LOG-07 applies the personal-data guard to these directories.
LOG_GUARDED_AREAS = frozenset({"api", "domain", "unit"})


def pytest_configure(config: pytest.Config) -> None:
    for marker in MARKERS:
        config.addinivalue_line("markers", marker)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    # Under make perf only backend/tests/perf/ is collected (DG-ENV-10, DG-PERF-06).
    if not PERF_RUN:
        return None
    try:
        parts = collection_path.resolve().relative_to(TESTS_ROOT).parts
    except ValueError:
        return None
    return True if parts and parts[0] != "perf" else None


# Pytester drives the DG-TST-06 collection tests in backend/tests/unit/test_controls_report.py.
pytest_plugins = ("pytester",)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # DG-TST-06, DG-TST-09: every control marker is validated before -m deselection hides a test.
    from erev_api.controls.registry import check_control_markers

    check_control_markers(items)
    # DG-TST-07, DG-TST-09 (ruling D-78): gate markers stay in their directories, never skipped.
    markers.check(items, TESTS_ROOT)
    items.sort(key=lambda item: collection_rank(item.path))


@pytest.fixture(autouse=True, scope="session")
def no_network() -> Iterator[None]:
    """DG-TST-15: only loopback and Unix sockets; anything else raises NetworkBlocked."""
    with pytest.MonkeyPatch.context() as patch:
        network.install(patch)
        yield


@pytest.fixture
def clock() -> FrozenClock:
    """DG-TST-14: FrozenClock at 2026-09-12T12:00:00Z; tests advance it explicitly."""
    return frozen_clock()


@pytest.fixture(scope="session")
def keyring() -> KeyRing:
    """The key ring over the .env master keys; EREV_ENV=test requires the local provider."""
    return build_keyring(get_settings())


@pytest.fixture(scope="session")
def test_database() -> Iterator[TestDatabase]:
    """DG-TST-10, DG-TST-11: a serialised, freshly reset and migrated test database.

    The schema is dropped and ``alembic upgrade head`` runs as ``erev_owner``; the DB-14 lint then
    runs as ``erev_app`` and any finding fails the session.
    """
    os.environ["EREV_ENV"] = "test"
    settings = get_settings()
    database = settings.database_name()
    if settings.env is not Environment.TEST or not TEST_DATABASES.fullmatch(database):
        raise RuntimeError(
            f"test_database requires EREV_ENV=test on erev_test or erev_rv_*, not {database}"
        )
    # The lock's own connection outlives a ``dispose_engines()`` of a test: a disposed engine
    # closes the connections it holds idle, never one that is checked out.
    lock_connection = owner_engine().connect()
    try:
        # Session-level lock; committed so the connection is not idle in a transaction (TXN-03).
        lock_connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": TEST_DB_LOCK_KEY})
        lock_connection.commit()
        # reset + upgrade head, waiting out a full shared lock table (support.db.fresh_head)
        fresh_head()
        findings = lint_as_app(request_id="tests-lint")
        if findings:
            raise RuntimeError("DB-14 lint after upgrade:\n" + "\n".join(map(str, findings)))
        yield TestDatabase(clock=frozen_clock())
    finally:
        lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": TEST_DB_LOCK_KEY})
        lock_connection.commit()
        lock_connection.close()
        dispose_engines()


@pytest.fixture
def db(test_database: TestDatabase) -> Iterator[SessionFactory]:
    """DG-TST-12: sessions over one ``erev_app`` transaction that rolls back at teardown.

    Sessions use savepoints, so code under test that commits releases a savepoint only; the
    context settings live on the outer transaction and survive a savepoint rollback.
    """
    connection = test_database.app_engine.connect()
    outer = connection.begin()
    sessions: list[Session] = []

    def open_session(ctx: DbContext) -> Session:
        connection.info[CONTEXT_INFO_KEY] = ctx
        set_tenant_context(connection, ctx)
        session = Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            autoflush=False,
            expire_on_commit=False,
        )
        sessions.append(session)
        return session

    try:
        yield open_session
    finally:
        for session in sessions:
            session.close()
        outer.rollback()
        connection.info.pop(CONTEXT_INFO_KEY, None)
        connection.close()


@pytest.fixture
def committed_db(test_database: TestDatabase) -> TestDatabase:
    """DG-TST-13: real commits through the production factories; tests isolate by fresh tenant."""
    return test_database


@pytest.fixture
def app_settings(tmp_path: Path) -> Settings:
    """The process settings with the file store under the test's temporary directory."""
    return get_settings().model_copy(update={"file_root": tmp_path / "files"})


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    """A fresh JSON logging pipeline writing to a buffer; the previous one is restored after."""
    saved = structlog.get_config()
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    root.handlers[:] = []
    stream = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=stream)
    try:
        yield stream
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        structlog.configure(
            processors=list(saved["processors"]),
            context_class=saved["context_class"],
            wrapper_class=saved["wrapper_class"],
            logger_factory=saved["logger_factory"],
            cache_logger_on_first_use=saved["cache_logger_on_first_use"],
        )


@pytest.fixture(autouse=True)
def no_personal_data_in_logs(request: pytest.FixtureRequest) -> Iterator[None]:
    """DG-LOG-07: fail api, domain and unit tests whose log events carry personal data."""
    if area_of(request.path) not in LOG_GUARDED_AREAS:
        yield
        return
    with log_guard.capture() as events:
        yield
    log_guard.check(events)


@pytest.fixture(autouse=True)
def _forget_stamped_release() -> Iterator[None]:
    """05 REL-05: a release one test's startup stamped (the enqueuer identity `defer` records in
    job.params) never leaks into another test's jobs."""
    yield
    from erev_api.controls.release import remember_release

    remember_release(None)
