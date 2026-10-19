"""Retained entity-level policy facts for disclosure pack section 7.

These are policies resolved for the entity, not assertions that each contract used
an expedient. Contract/product overrides and locked snapshots require their own evidence.
Standard references follow the repository's POLICIES table; no website links are emitted.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import legal_entity
from erev_api.domain.reports import elections
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import BookCode, RegistryCategory
from erev_api.problems import Problem
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_api.registry.resolve import resolve
from erev_api.uow import UnitOfWork

REFERENCES = {
    "POL-015": ("606-10-10-4", "15.4"),
    "POL-021": ("606-10-25-18A to 25-18B", None),
    "POL-045": ("606-10-32-2A", "15.47 (no election)"),
    "POL-046": ("606-10-32-18; 606-10-50-22", "15.63"),
    "POL-140": ("340-40-25-4; 340-40-50-5", "15.94"),
    "POL-197": ("606-10-50-14(a); 50-15", "15.121(a)"),
    "POL-198": ("606-10-50-14(b); 50-15", "15.121(b); B16"),
    "POL-199": ("606-10-50-14A(a); 50-14B", None),
    "POL-200": ("606-10-50-14A(b); 50-14B", None),
    "POL-202": ("952-606-25-2 to 25-4; 952-606-50-1 to 50-2", None),
}
LABELS = {
    "APPLY": "Applied",
    "DO_NOT_APPLY": "Not applied",
    "TRUE": "Elected",
    "FALSE": "Not elected",
    "ENABLED": "Applied",
    "DISABLED": "Not applied",
    "EXCLUDE_ALL_IN_SCOPE": "Elected",
    "ASSESS_EACH_TAX": "Not elected",
    "NOT_ELECTED": "Not elected",
    "ELECT_DISTINCT_SERVICES": "Elected — distinct services",
    "ELECT_SINGLE_SERVICES_POB": "Elected — single services obligation",
}
RELIEF = "disclosure.nonpublic_expedient_relief"
COLUMNS = (
    Column("expedient", "Expedient", "text"),
    Column("registry_key", "Registry key", "code"),
    Column("value", "Value", "text"),
    Column("disclosure", "Disclosure", "text"),
)


def capture(uow: UnitOfWork, *, entity_id: UUID, book: str, known_at: datetime) -> dict[str, Any]:
    scope = uow.principal.permission_scopes.get("report.run")
    if (
        "report.run" not in uow.principal.permissions
        or not scope
        or (scope != "*" and entity_id not in scope)
    ):
        raise Problem("forbidden")
    if known_at.tzinfo is None or book not in {"ASC606", "IFRS15"}:
        raise Problem("validation-failed", "Choose an accounting book and an aware policy cutoff.")
    entity = uow.session.execute(
        select(legal_entity.c.code).where(
            legal_entity.c.id == entity_id, legal_entity.c.created_at <= known_at
        )
    ).scalar_one_or_none()
    if entity is None:
        raise Problem("validation-failed", "The disclosure entity is unavailable at this cutoff.")
    resolved = {}
    specs = sorted(
        (
            s
            for s in POLICY_PARAMETERS.values()
            if s.category == RegistryCategory.PRACTICAL_EXPEDIENT
        ),
        key=lambda s: s.pol_id or "",
    )
    if {s.pol_id for s in specs} != set(REFERENCES):
        raise Problem(
            "validation-failed", "Practical expedient disclosure references need updating."
        )
    for code in [elections.REPORTING_TYPE, RELIEF, *(s.code for s in specs)]:
        value = resolve(
            uow.session, code, book_code=BookCode(book), entity_id=entity_id, known_at=known_at
        )
        resolved[code] = {
            "value": value.value,
            "level": value.level,
            "source_id": None if value.source_id is None else str(value.source_id),
        }
    reporting_type = resolved[elections.REPORTING_TYPE]["value"] or "PBE"
    omitted = reporting_type == elections.NONPUBLIC and resolved[RELIEF]["value"] == elections.ELECT
    rows = []
    for spec in specs:
        value = resolved[spec.code]["value"]
        if value not in LABELS:
            raise Problem("validation-failed", "An expedient has an unsupported resolved value.")
        if (
            spec.pol_id == "POL-202"
            and reporting_type != elections.NONPUBLIC
            and value != "NOT_ELECTED"
        ):
            raise Problem(
                "validation-failed", "The franchisor expedient requires a nonpublic entity."
            )
        asc, ifrs = REFERENCES[str(spec.pol_id)]
        disclosure = (
            f"Disclosed under ASC {asc}"
            if book == "ASC606"
            else "No corresponding IFRS election"
            if ifrs is None
            else f"IFRS {ifrs}"
        )
        rows.append(
            {
                "row_key": spec.code,
                "expedient": spec.description,
                "registry_key": spec.code,
                "value": LABELS[value],
                "disclosure": disclosure,
            }
        )
    return {
        "version": 1,
        "tenant_id": str(uow.principal.tenant_id),
        "entity_id": str(entity_id),
        "entity_code": entity,
        "book": book,
        "known_at": known_at.isoformat(),
        "reporting_type": reporting_type,
        "resolved": resolved,
        "rows": rows,
        "omitted": omitted,
        "omission_note": elections.OMITTED.format(label=elections.RELIEFS[RELIEF][1])
        if omitted
        else None,
    }


def dataset(facts: dict[str, Any]) -> ReportData:
    """Render retained facts; suppression never destroys the underlying policy evidence."""
    if facts.get("version") != 1:
        raise Problem("validation-failed", "Unsupported practical expedient evidence version.")
    notes = (
        [{"section": 7, "registry_key": RELIEF, "note": facts["omission_note"]}]
        if facts["omitted"]
        else []
    )
    return ReportData(
        COLUMNS,
        () if facts["omitted"] else tuple(facts["rows"]),
        {"omitted_sections": notes, "policy_count": len(facts["rows"])},
    )
