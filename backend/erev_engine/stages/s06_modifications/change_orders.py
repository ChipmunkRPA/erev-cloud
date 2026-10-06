"""Stage 06 unpriced change orders and claims (ENGINE_SPEC §6.4 S06-R-20; POLICIES §5.5 PT-05,
POL-105, POL-244; REQ-MOD-016).

An approved scope change without an agreed price is a modification whose lines carry ΔC = 0. Its
price enters as a ``VARIABLE_CONSIDERATION`` element of type ``UNPRICED_CHANGE_ORDER``
(``MOST_LIKELY_AMOUNT``, constrained; POL-105 ``ESTIMATE_WITH_CONSTRAINT``) effective at d, which
contributes ΔVC to the pool through the price after the event (S06-R-12). A claim (element type
``CLAIM``) enters the price only with a reviewed ``OTHER`` outcome ``claim_enforceable = true``,
which stage 04 applies (S04-R-04; POL-244). Pricing the change later is an estimate change applied
by stage 08 (ALG-10).

``elements`` names the unpriced change orders of the modified contract effective at d. ``check``
refuses a priced line, or a method other than ``MOST_LIKELY_AMOUNT``, beside such an element
(CV-45). ``params`` records the element versions on the pool node. Private to stage 06. Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import EstimateVersionInput
from erev_engine.stages.s01_canonicalize import contract_subject_key
from erev_engine.stages.s06_modifications.classify import ModificationView
from erev_engine.stages.state import AllocatedState

__all__ = [
    "ELEMENT_TYPE",
    "ESTIMATE_WITH_CONSTRAINT",
    "POLICY_CODE",
    "check",
    "elements",
    "params",
]

ELEMENT_TYPE: Final = "UNPRICED_CHANGE_ORDER"
KIND: Final = "VARIABLE_CONSIDERATION"
METHOD: Final = "MOST_LIKELY_AMOUNT"
POLICY_CODE: Final = "mod.unpriced_change_orders"
ESTIMATE_WITH_CONSTRAINT: Final = "ESTIMATE_WITH_CONSTRAINT"
SEPARATOR: Final = "|"


def elements(st: AllocatedState, mod: ModificationView) -> tuple[EstimateVersionInput, ...]:
    """The ``UNPRICED_CHANGE_ORDER`` versions of the contract whose version in force at d is
    effective at d, in estimate key order (S06-R-20)."""
    prefix = f"{contract_subject_key(mod.contract_key)}/"
    found: list[EstimateVersionInput] = []
    for key in sorted(st.estimates.pins):
        if not key.startswith(prefix):
            continue
        version = st.estimates.pin(key, mod.effective_date)
        if (
            version is None
            or version.estimate_kind != KIND
            or version.vc_element_type != ELEMENT_TYPE
            or version.effective_date != mod.effective_date
        ):
            continue
        found.append(version)
    return tuple(found)


def check(mod: ModificationView, found: Sequence[EstimateVersionInput]) -> None:
    """Beside an unpriced change order every line carries ΔC = 0, and the element is estimated at
    its most likely amount, constrained (S06-R-20; POL-105). ``ValueError`` otherwise."""
    if not found:
        return
    priced = sorted({line.obligation_key for line in mod.lines if line.consideration_delta != 0})
    if priced:
        raise ValueError(
            f"{mod.modification_key}: an unpriced change order carries ΔC = 0, but the line on "
            f"{priced[0]} is priced (S06-R-20)"
        )
    methods = sorted({version.method for version in found} - {METHOD})
    if methods:
        raise ValueError(
            f"{mod.modification_key}: an unpriced change order is estimated by {METHOD}, not "
            f"{methods[0]} (POL-105)"
        )


def params(found: Sequence[EstimateVersionInput]) -> Mapping[str, str]:
    """Pool node evidence: the unpriced change order versions behind ΔVC."""
    if not found:
        return MappingProxyType({})
    keys = SEPARATOR.join(version.version_key for version in found)
    return MappingProxyType({"unpriced_change_orders": keys})
