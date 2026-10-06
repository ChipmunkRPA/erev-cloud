"""Consumer stamping with the process's own release row (05 REL-03 consumers, rev 1.15; REL-05;
D-96; SOP-2 remainder ruled to lane P5 on 2026-09-19; wired in integration slice 1).

The four consumers that write ``engine_release_id`` — ``domain/contracts/computation.py`` and
``compute_job.py`` (``contract_computation``), ``domain/journals/summarise.py`` (``journal_batch``)
and ``domain/reports/framework.py`` (``report_run``) — call ``process_release_id`` with the release
``controls.release.stamp_release`` recorded in this process (``current_release()``) and the
environment it recorded (``current_environment()``; domain code never reads ``get_settings()``,
DG-KRN-CFG-01 is satisfied by that entrypoint boundary — api lifespan, worker start, every CLI
command — never by inference). Design call, D-98 60: a process without a stamped release **fails
closed** unless the remembered environment is explicitly ``dev`` or ``test``, where the latest row
of the running engine version is the documented fallback with a WARN line; an unknown or
unremembered environment is production, so a missing stamp never classifies a caller as
non-production. A stamped row never stamps another engine version's output.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final
from uuid import UUID

from erev_api.config import Environment
from erev_api.controls.release import EngineRelease
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import Problem

__all__ = ["FALLBACK_ENVIRONMENTS", "FALLBACK_EVENT", "process_release_id"]

# DG-LOG-02 event name of the WARN-class line the fallback emits (team-lead ruling (4), 2026-09-19).
FALLBACK_EVENT: Final = "release.stamp_fallback"
# D-98 60: the only environments in which an unstamped process may fall back to latest-per-version.
FALLBACK_ENVIRONMENTS: Final = frozenset({Environment.DEV, Environment.TEST})
register_logger_fields(__name__, ("env", "fallback", "detail"))


def _warn(message: str) -> None:
    get_logger(__name__).warning(FALLBACK_EVENT, fallback="latest-per-version", detail=message)


def process_release_id(
    current: EngineRelease | None,
    *,
    env: Environment | None,
    latest_for_version: Callable[[], UUID | None],
    engine_version: str | None = None,
    warn: Callable[[str], None] | None = None,
) -> UUID:
    """The ``engine_release_id`` a consumer stamps on the rows it writes (CTL-032).

    ``env`` is the environment the entrypoint boundary recorded (``stamp_release`` or the CLI
    services); None means unremembered and is treated as production (D-98 60). ``engine_version``
    is the engine version of the output being
    stamped; the process's row must carry the same version, else ``release-mismatch``. ``warn``
    receives the one-line notice when the fallback is taken (the default writes the
    ``release.stamp_fallback`` WARN event); the production path never warns — it fails."""
    if current is not None:
        if engine_version is not None and current.engine_version != engine_version:
            raise Problem("release-mismatch")  # a row of one engine version never stamps another's
        return current.id
    if env not in FALLBACK_ENVIRONMENTS:
        # Fail closed: production, e2e and an unremembered environment (REL-03 stamps before any
        # work; a missing stamp never makes a caller non-production — D-98 60).
        raise Problem("release-mismatch")
    found = latest_for_version()
    if found is None:
        raise Problem("release-mismatch")
    (warn or _warn)(
        f"no release stamped in this process ({env.value}); stamping the latest engine_release row "
        "of "
        "the running engine version instead (latest-per-version fallback, REL-03)"
    )
    return found
