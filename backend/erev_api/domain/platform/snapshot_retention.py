"""From when a snapshot is possible: the copy of the unset-retention refusal (BUILD_SPEC SNP-5;
PRD ERR-77; 04 T-PLT-31 ``platform.snapshot_retention_families`` rev 1.177; 05 §10 SBX-03, PRV-06;
supervisor ruling of 2026-09-30 on item CFG-PLATFORM-PIN-1).

``TENANT_SNAPSHOT`` refuses 412 ``precondition-failed`` until a PUBLISHED TENANT version carries
the five retention families with a named human approval and is in force at the snapshot's
``known_at`` (``snapshot_job.retention_policy_for``). The person who asked for a copy reads the
refusal as the detail of a FAILED job, so it says from when copies are possible and not only that
the policy is missing:

* a confirmed version exists and is not in force at the ``known_at`` asked for — the instant it
  takes effect, the later of its approval and its ``effective_from``;
* none is confirmed — who sets the policy and who approves it. The copy names no screen: none
  sets the retention families yet (item SBX-RETENTION-UI-1).

The confirmed version is the one that last changed, or first stated, the families
(``confirming_version``; 04 T-PLT-31 rev 1.183): under the whole value set every later PLATFORM
version carries them, and the approval and the date of such a version say nothing of the
retention. The manifest (``snapshot_job.retention_policy_for``) and this refusal read the same
version.

``ahead`` reads, ``copy`` words what it found and ``refusal`` is the problem the job raises with
it: named ``RETENTION_UNSET`` in ``errors[].rule_id``. Nothing here writes or decides.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import approval_decision, registry_version
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.enums import ConfigStatus, RegistryScope
from erev_api.explain.narratives import format_date
from erev_api.problems import Problem, ProblemError
from erev_api.registry import resolve as registry_resolve

__all__ = ["NONE", "NOT_YET", "RULE_ID", "ahead", "confirming_version", "copy", "refusal"]

# The governed rule id of the refusal in ``errors[].rule_id`` (PRD ERR-77, a convention row).
RULE_ID: Final = "RETENTION_UNSET"
# PRD ERR-77, both forms verbatim.
NOT_YET: Final = (
    "Sandbox copies are possible from {effective}: the snapshot retention policy approved on "
    "{approved} takes effect then."
)
NONE: Final = (
    "No snapshot retention policy is confirmed yet. A Tenant Admin sets the retention families "
    "and a second person approves them; sandbox copies are possible from the time the approved "
    "policy takes effect."
)


def _day(at: datetime) -> str:
    """``DD MMM YYYY`` in UTC (DESIGN_SYSTEM DS-FMT-16)."""
    return format_date(at.astimezone(UTC).date().isoformat())


def copy(found: tuple[datetime, datetime] | None) -> str:
    """The refusal's detail: ``found`` is ``ahead``'s answer — (approved at, in force from) of a
    confirmed version that is not in force yet, or None."""
    if found is None:
        return NONE
    approved_at, effective_at = found
    utc = effective_at.astimezone(UTC)
    return NOT_YET.format(
        approved=_day(approved_at),
        effective=f"{_day(utc)} {utc.hour:02d}:{utc.minute:02d} UTC",
    )


def refusal(found: tuple[datetime, datetime] | None) -> Problem:
    """412 ``precondition-failed`` named ``RETENTION_UNSET`` with the copy of ``found`` as its
    detail and as the message of its one error."""
    text = copy(found)
    return Problem(
        "precondition-failed",
        text,
        errors=[ProblemError(field=None, rule_id=RULE_ID, message=text)],
    )


def confirming_version(session: Session, holder: Mapping[str, Any]) -> dict[str, Any]:
    """The version that last changed, or first stated, the retention families ``holder`` holds
    (04 T-PLT-31 rev 1.183; the supervisor's ruling of 2026-10-01 on finding 8 of the pre-build
    line of item REG-VERSION-WHOLE-SET-1): back along SC-V ``supersedes_version_id`` while the
    superseded version holds the same families. A later version of the key carries them forward
    with whatever it changed (T-PLT-32 "Whole value set"), and the person who approved that
    change did not confirm a retention period."""
    families = json.dumps(holder["values"][sd.RETENTION_PARAMETER], sort_keys=True)
    current = dict(holder)
    seen = {current["id"]}
    while current["supersedes_version_id"] is not None:
        earlier = _version(session, current["supersedes_version_id"])
        if earlier is None or earlier["id"] in seen:
            break
        held = earlier["values"].get(sd.RETENTION_PARAMETER)
        if held is None or json.dumps(held, sort_keys=True) != families:
            break
        seen.add(earlier["id"])
        current = earlier
    return current


def _version(session: Session, version_id: UUID) -> dict[str, Any] | None:
    row = (
        session.execute(select(registry_version).where(registry_version.c.id == version_id))
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def ahead(session: Session, known_at: datetime) -> tuple[datetime, datetime] | None:
    """(approved at, in force from) of the retention confirmation that is not in force at
    ``known_at``: the day a named human approved the version that states the families, and the
    instant that version takes effect — the later of its publication and its ``effective_from``.
    None when no confirmed families are ahead. Read in the job's own tenant session.

    The PUBLISHED TENANT version may only carry the families (04 T-PLT-32 "Whole value set"):
    its own approval is of another change and its own date is later than the instant the
    families take effect, so the confirmation is read from the confirming version
    (``confirming_version``), as the manifest reads it. The versions that are ahead of
    ``known_at`` are followed back in turn — an earlier state of the families, and a version
    that holds none (it returned them to the default) is stepped over — up to the version in
    force at ``known_at``: the answer is the first instant from which a confirmed policy is in
    force."""
    spec = registry_resolve.parameter(sd.RETENTION_PARAMETER)
    table = registry_version
    row = (
        session.execute(
            select(table).where(
                table.c.category == spec.category.value,
                table.c.scope == RegistryScope.TENANT.value,
                table.c.status == ConfigStatus.PUBLISHED.value,
            )
        )
        .mappings()
        .one_or_none()
    )
    current = None if row is None else dict(row)
    found: tuple[datetime, datetime] | None = None
    seen: set[Any] = set()
    while current is not None and current["id"] not in seen:
        seen.add(current["id"])
        holds = bool((current["values"] or {}).get(sd.RETENTION_PARAMETER))
        version = confirming_version(session, current) if holds else current
        seen.add(version["id"])
        published_at: datetime = version["published_at"]
        start = max(published_at, version["effective_from"] or published_at)
        if start <= known_at:
            break  # in force at ``known_at``, or before it: the resolution answers from here
        if holds:
            try:
                confirmed = sd.retention_confirmation(version, _decisions(session, version))
            except sd.UnconfirmedRetention:
                pass
            else:
                found = (confirmed.decided_at, start)
        earlier = version["supersedes_version_id"]
        current = None if earlier is None else _version(session, earlier)
    return found


def _decisions(session: Session, version: Mapping[str, Any]) -> list[dict[str, Any]]:
    if version["approval_request_id"] is None:
        return []
    return [
        dict(decision)
        for decision in session.execute(
            select(approval_decision).where(
                approval_decision.c.approval_request_id == version["approval_request_id"]
            )
        ).mappings()
    ]
