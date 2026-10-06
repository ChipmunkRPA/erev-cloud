"""Pure rules of the performance harness (dev-guide DG-PERF-06, DG-PERF-02; 05 AIA-02).

Everything here is testable without a database or a process: ``backend/tests/unit/perf/
test_harness_rules.py`` drives these functions with fakes, and ``backend/tests/perf/conftest.py``
applies them to the real session.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final, Protocol

PERF_RUN_FLAG: Final = "EREV_PERF_RUN"
PERF_DATABASE: Final = "erev"
STALE_MESSAGE: Final = "perf tenant missing or stale; run make perf-seed"
NON_DETERMINISTIC_MESSAGE: Final = "perf sandbox copy not deterministic"
# DG-PERF-02 (1), rev 1.243: a load that compared nothing proves nothing, so the restore also
# refuses, with the counts, a contract group the load did not recompute and a sandbox that does
# not hold the contract events perf-volume recorded at or before the snapshot's known_at.
NOT_RECOMPUTED_MESSAGE: Final = (
    "perf sandbox copy proves nothing: the load recomputed {recomputed} contract group(s) and "
    "left {not_recomputed} without a result to compare"
)
EVENTS_NOT_COPIED_MESSAGE: Final = (
    "perf sandbox copy is not perf-volume as of the snapshot: the sandbox holds {sandbox} "
    "contract event(s); perf-volume recorded {source} at or before {known_at}"
)
EVENTS_COPIED_NOTE: Final = "contract events of perf-volume as of the snapshot, all copied: {count}"
REQUESTER_MISSING_MESSAGE: Final = (
    "perf-controller has no ACTIVE membership of perf-volume; run make perf-seed "
    "(the sandbox restore needs a real requesting user, SANDBOX_ACTOR_REQUIRED)"
)
PRIOR_ACTIVE_RESET_ABSENT_MESSAGE: Final = (
    "an ACTIVE perf-run-* sandbox exists and SANDBOX_RESET has no handler on main (F-SNP): "
    "refusing to restore another; wait for the handler (D-98 148 AMENDMENT 4)"
)
PRIOR_ACTIVE_RESET_UNBOUND_MESSAGE: Final = (
    "an ACTIVE perf-run-* sandbox exists; the SANDBOX_RESET handler is registered but the "
    "harness does not call it yet (PRF-4 follow-up binds the call to its landed params)"
)
# DG-PERF-06: perf code writes only to the perf-run-* sandbox; the pytest database fixtures rebuild
# or share databases and are refused.
FORBIDDEN_FIXTURES: Final = frozenset({"test_database", "db", "committed_db"})


def is_perf_run(environ: Mapping[str, str]) -> bool:
    return environ.get(PERF_RUN_FLAG) == "1"


class _Item(Protocol):
    nodeid: str


def deselect_unless_perf_run(
    items: Iterable[_Item], *, perf_run: bool, is_perf: Callable[[Any], bool] = lambda item: True
) -> tuple[list[Any], list[Any]]:
    """(kept, deselected): without ``EREV_PERF_RUN=1`` every PERF item is deselected and every
    other item is kept untouched (Codex 2316 R1: the collection hook sees the whole session)."""
    listed = list(items)
    if perf_run:
        return listed, []
    kept = [item for item in listed if not is_perf(item)]
    deselected = [item for item in listed if is_perf(item)]
    return kept, deselected


def forbidden_fixture(fixturenames: Iterable[str]) -> str | None:
    """The first database fixture a perf test requests, or None."""
    for name in fixturenames:
        if name in FORBIDDEN_FIXTURES:
            return name
    return None


def forbidden_fixture_message(name: str) -> str:
    return (
        f"perf tests never request the {name} fixture (DG-PERF-06); they use the perf-run-* sandbox"
    )


def database_message(actual: str) -> str:
    return f"perf tests run against database {PERF_DATABASE} only; the settings name {actual}"


def require_perf_database(actual: str) -> None:
    if actual != PERF_DATABASE:
        raise RuntimeError(database_message(actual))


def preflight(settings_factory: Callable[[], Any], start_processes: Callable[[], Any]) -> Any:
    """Build the settings before any process starts: under ``EREV_PERF_RUN=1`` ``Settings`` refuses
    ``EREV_AI_PROVIDER=anthropic`` (05 AIA-02; DG-KRN-CFG-02), so a misconfigured run fails here and
    ``start_processes`` is never called. Returns the settings."""
    settings = settings_factory()
    start_processes()
    return settings
