"""Production startup refusals (05 SAR-40 rev 1.53 "startup subset"; R-34 SD-5, SD-6).

``erev doctor`` is a rollout gate: nothing forces an operator to run it. Two of its production
checks describe a deployment that is unsafe the moment it serves — mail that is written to files
nobody reads (``email-backend``) and master keys that are placeholders or repeated
(``master-keys``) — so the api and the worker evaluate exactly those two on their own settings when
they start and refuse to start when either fails. The predicates are the doctor's: one rule, two
places that apply it.

Only configuration is judged. A check over tenant data (``integration-urls``) never decides whether
a process starts, because one workspace could then stop the platform; the SAR-15 guard refuses
such a destination when it is called.
"""

from __future__ import annotations

from erev_api.config import Environment, Settings, SettingsError
from erev_api.logging import get_logger, register_logger_fields

# OPR-21: the refusal's FAIL lines are code-owned text that names variables and rules.
register_logger_fields(__name__, ("findings",))


class StartupRefused(SettingsError):
    """A production process must not start with its configuration; the message carries the
    failing checks' ``FAIL`` lines, which name variables and rules and never a value."""

    def __init__(self, findings: tuple[str, ...]) -> None:
        super().__init__("production refuses to start: " + "; ".join(findings))
        # One ``FAIL <check>: <finding>`` line each, for a caller that prints them (the CLI).
        self.findings = findings


def production_refusals(settings: Settings) -> tuple[str, ...]:
    """The ``FAIL <check>: <finding>`` lines of the startup subset for ``settings``; empty outside
    ``production`` and for a sound configuration."""
    if settings.env is not Environment.PRODUCTION:
        return ()
    # Imported here: the doctor module reads the catalogue and the key ring, which this module
    # never touches, and the composition roots import this one at start.
    from erev_api.controls.doctor import email_backend, master_keys, snapshot_settings

    snapshot = snapshot_settings(settings)
    return tuple(
        line
        for result in (email_backend(snapshot), master_keys(snapshot))
        if not result.ok
        for line in result.lines()
    )


def refuse_unsafe_production(settings: Settings) -> None:
    """Raise ``StartupRefused`` when the startup subset fails. Called by the api lifespan and by
    the worker before the release is stamped, so before any database connection opens, and by the
    operator commands before the key ring is built (``cli.cli_services``; rev 1.53, R-53 (6))."""
    refusals = production_refusals(settings)
    if not refusals:
        return
    get_logger(__name__).error("startup.refused", findings=list(refusals))
    raise StartupRefused(refusals)
