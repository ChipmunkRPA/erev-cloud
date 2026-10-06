"""Disclosure elections of an entity (POLICIES POL-190 to POL-196, POL-203; SCREENS_B §0.5 RV-12;
03 REQ-RPT-025, REQ-RPT-026, REQ-REF-016; BUILD_SPEC RPS-4).

``entity_elections`` resolves, for one entity and book at ``known_at``, the reporting-entity type
(POL-190) and the nonpublic reliefs (POL-191 to POL-196) through ``registry.resolve``, so only a
published version is in force (a DRAFT changes nothing). A relief counts as elected only for a
``NONPUBLIC`` entity (POL-190 gates POL-191 to POL-196). A suppressed section renders "Omitted under
the <election label> election." with the registry key (RV-12); the report dataset is still computed
(POL-193 "RPO dataset still computed").

``quarterly_pack_parameters`` gives the interim pack of POL-203. ``TOPIC_270_LIST`` (the ASC606
derived default) lists 606-10-50-5 to 50-6 (``disaggregation``), 50-8 (``contract_balances``),
50-12A (``revenue_from_prior_period_obligations``) and 50-13 to 50-15 (``rpo``), less the
nonpublic elections: POL-192 omits 50-12A while opening and closing balances remain, and POL-193
omits the RPO section; POL-191 keeps disaggregation by timing of transfer. ``IAS34_16A_L`` (forced
in IFRS15) lists disaggregation only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from sqlalchemy.orm import Session

from erev_api.enums import BookCode
from erev_api.registry.resolve import resolve

REPORTING_TYPE: Final = "entity.reporting_type"
NONPUBLIC: Final = "NONPUBLIC"
ELECT: Final = "ELECT"
DISAGGREGATION_RELIEF: Final = "disclosure.nonpublic_disaggregation_relief"
CONTRACT_BALANCES_RELIEF: Final = "disclosure.nonpublic_contract_balances_relief"
RPO_RELIEF: Final = "disclosure.nonpublic_rpo_relief"
INTERIM_PACK: Final = "disclosure.interim_revenue_pack"
TOPIC_270_LIST: Final = "TOPIC_270_LIST"
IAS34_16A_L: Final = "IAS34_16A_L"
OMITTED: Final = "Omitted under the {label} election."
# POL-191 to POL-196: registry code → (POL id, election label).
RELIEFS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        DISAGGREGATION_RELIEF: ("POL-191", "nonpublic disaggregation relief"),
        CONTRACT_BALANCES_RELIEF: ("POL-192", "nonpublic contract balances relief"),
        RPO_RELIEF: ("POL-193", "nonpublic RPO relief"),
        "disclosure.nonpublic_judgements_relief": ("POL-194", "nonpublic judgements relief"),
        "disclosure.nonpublic_expedient_relief": (
            "POL-195",
            "nonpublic practical expedient relief",
        ),
        "disclosure.nonpublic_cost_relief": ("POL-196", "nonpublic contract costs relief"),
    }
)
# POL-203 TOPIC_270_LIST in paragraph order: (report code, the relief that omits it, or None).
TOPIC_270_REPORTS: Final = (
    ("disaggregation", None),
    ("contract_balances", None),
    ("revenue_from_prior_period_obligations", CONTRACT_BALANCES_RELIEF),
    ("rpo", RPO_RELIEF),
)


@dataclass(frozen=True, slots=True)
class Elections:
    entity_id: UUID
    reporting_type: str
    elected: frozenset[str]  # relief codes elected by a nonpublic entity
    interim_pack: str

    def is_elected(self, code: str) -> bool:
        return code in self.elected

    def note(self, code: str, section: int) -> dict[str, Any]:
        """The RV-12 section note of an elected relief."""
        return {
            "section": section,
            "registry_key": code,
            "note": OMITTED.format(label=RELIEFS[code][1]),
        }


def entity_elections(
    session: Session, *, entity_id: UUID, book_code: str, known_at: datetime
) -> Elections:
    book = BookCode(book_code)

    def value(code: str) -> Any:
        return resolve(session, code, book_code=book, entity_id=entity_id, known_at=known_at).value

    reporting_type = str(value(REPORTING_TYPE) or "PBE")
    elected = frozenset(
        code for code in RELIEFS if reporting_type == NONPUBLIC and value(code) == ELECT
    )
    pack = value(INTERIM_PACK)
    if pack is None:
        pack = IAS34_16A_L if book is BookCode.IFRS15 else TOPIC_270_LIST
    return Elections(
        entity_id=entity_id, reporting_type=reporting_type, elected=elected, interim_pack=str(pack)
    )


def quarterly_pack_parameters(
    session: Session, *, entity_id: UUID, book_code: str, known_at: datetime
) -> dict[str, Any]:
    """The interim pack of one entity: the POL-203 option, the reports it requires and the notes of
    the omitted sections (REQ-RPT-026)."""
    found = entity_elections(session, entity_id=entity_id, book_code=book_code, known_at=known_at)
    if found.interim_pack == IAS34_16A_L:
        required = ["disaggregation"]
        omitted: list[dict[str, Any]] = []
    else:
        required = [code for code, relief in TOPIC_270_REPORTS if relief not in found.elected]
        omitted = [
            {"report_code": code, **found.note(relief, 1)}
            for code, relief in TOPIC_270_REPORTS
            if relief is not None and relief in found.elected
        ]
    return {
        "entity_id": str(entity_id),
        "reporting_type": found.reporting_type,
        "interim_revenue_pack": found.interim_pack,
        "required_reports": required,
        "omitted_sections": omitted,
    }
