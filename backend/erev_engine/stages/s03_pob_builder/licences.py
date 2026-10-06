"""Stage 03 licences of intellectual property: nature, pattern and recognition start.

ENGINE_SPEC S03-R-10 (rev 1.6); 606-10-55-54 to 55-65B; POLICIES POL-024, POL-025, POL-232, §6.2
rows 7 to 9; 03 REQ-POB-010 (V5); 04 T-CON-19 ``LICENCE_NATURE`` (rev 1.11); D-91 gaps (viii).
Private to stage 03. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import date
from typing import Final

from erev_engine.enums import LicenceNature, ObligationKind, RecognitionMethod, SatisfactionPattern
from erev_engine.stages.s01_canonicalize import payload_text
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder.distinct import obligation_judgement
from erev_engine.stages.s03_pob_builder.templates import PobDraft
from erev_engine.stages.state import BookContext

__all__ = [
    "ACTIVITIES_SIGNIFICANTLY_AFFECT_IP",
    "CUSTOMER_REQUIRED_TO_USE_UPDATED_IP",
    "FUNCTIONALITY_EXPECTED_TO_CHANGE",
    "FUNCTIONAL_SYMBOLIC",
    "LATER_OF_AGREEMENT_AND_AVAILABILITY",
    "NATURE_POLICY",
    "RENEWAL_PERIOD_START",
    "RENEWAL_POLICY",
    "apply",
    "availability",
]

NATURE_POLICY: Final = "licence.nature_model"  # POL-024, level B
RENEWAL_POLICY: Final = "licence.renewal_start"  # POL-025, level B
FUNCTIONAL_SYMBOLIC: Final = "FUNCTIONAL_SYMBOLIC"
ACTIVITIES_SIGNIFICANTLY_AFFECT_IP: Final = "ACTIVITIES_SIGNIFICANTLY_AFFECT_IP"
RENEWAL_PERIOD_START: Final = "RENEWAL_PERIOD_START"
LATER_OF_AGREEMENT_AND_AVAILABILITY: Final = "LATER_OF_AGREEMENT_AND_AVAILABILITY"
# The two 606-10-55-62 members of a reviewed ASC606 ``LICENCE_NATURE`` record (04 T-CON-19 rev
# 1.11; D-91 gaps (viii)): (a) the functionality is expected to change substantively through the
# entity's activities that transfer no promised good or service, (b) the customer is contractually
# or practically required to use the updated IP. Answered together, FUNCTIONAL only.
FUNCTIONALITY_EXPECTED_TO_CHANGE: Final = "functionality_expected_to_change_substantively"
CUSTOMER_REQUIRED_TO_USE_UPDATED_IP: Final = "customer_required_to_use_updated_ip"
_AVAILABILITY_TRIGGERS: Final = frozenset({"CONTROL_TRANSFER", "DELIVERY"})
_OVER_TIME_DEFAULT: Final = "OT_A"


def apply(
    ctx: BookContext, st: IdentifiedState, draft: PobDraft, *, agreement: date | None = None
) -> PobDraft:
    """S03-R-10 for a ``LICENCE`` line.

    ASC606 model ``FUNCTIONAL_SYMBOLIC``: nature = the reviewed ``LICENCE_NATURE`` outcome
    ``nature``, else the template value; ``SYMBOLIC`` is a right to access (``OVER_TIME``,
    ``TIME_ELAPSED`` over the licence period), and so is ``FUNCTIONAL`` intellectual property
    whose reviewed record, scoped to ASC606 or to every book, answers both 606-10-55-62 criteria
    true (``functionality_expected_to_change_substantively`` and
    ``customer_required_to_use_updated_ip``; S03-R-10 rev 1.6; D-91 gaps (viii)); one criterion
    alone, no record, or the IFRS-only ``activities_significantly_affect_ip`` keeps the right to
    use (``POINT_IN_TIME``). A stored member is read, never ignored: a member outside
    ``true``/``false`` raises ``ValueError`` (CV-45). IFRS15 model
    ``ACTIVITIES_SIGNIFICANTLY_AFFECT_IP``: a right to access when the outcome
    ``activities_significantly_affect_ip = true``, else a right to use; the 55-62 members are not
    the IFRS test. ``recognition_start_date``
    = max(licence period start, availability). A renewal line (``agreement`` = the modification
    effective date) takes, under POL-025 ``RENEWAL_PERIOD_START``, max(that date, the renewal period
    start = line start), and under ``LATER_OF_AGREEMENT_AND_AVAILABILITY`` max(agreement,
    availability). A literal outside the POL-024 or POL-025 options raises ``ValueError``.
    """
    if draft.obligation_kind != ObligationKind.LICENCE:
        return draft
    header = st.canonical.contracts[draft.contract_key].header
    record = obligation_judgement(header, "LICENCE_NATURE", ctx.book_code, draft.obligation_key)
    outcome = {} if record is None else record.outcome
    nature = LicenceNature(outcome.get("nature") or draft.licence_nature)
    model = ctx.policies.value(NATURE_POLICY, contract=draft.contract_key)
    if model == FUNCTIONAL_SYMBOLIC:
        access = nature == LicenceNature.SYMBOLIC or (
            nature == LicenceNature.FUNCTIONAL and _meets_55_62(outcome, draft.subject_key)
        )
    elif model == ACTIVITIES_SIGNIFICANTLY_AFFECT_IP:
        access = outcome.get("activities_significantly_affect_ip") == "true"
    else:
        raise ValueError(f"{NATURE_POLICY} holds an unknown literal {model!r} (CV-17)")
    # A ROYALTY-method licence keeps its method (E-11): its fixed consideration, the minimum
    # guarantee, follows the licence pattern set here and its royalties their own component
    # (ENGINE_SPEC_B S09-R-33; POL-057; ENC-8).
    royalty = draft.recognition_method == RecognitionMethod.ROYALTY
    if access:
        criterion = draft.over_time_criterion
        terms = dataclasses.replace(
            draft,
            licence_nature=nature,
            satisfaction_pattern=SatisfactionPattern.OVER_TIME,
            recognition_method=draft.recognition_method
            if royalty
            else RecognitionMethod.TIME_ELAPSED,
            over_time_criterion=_OVER_TIME_DEFAULT if criterion == "NOT_APPLICABLE" else criterion,
        )
    else:
        terms = dataclasses.replace(
            draft,
            licence_nature=nature,
            satisfaction_pattern=SatisfactionPattern.POINT_IN_TIME,
            recognition_method=draft.recognition_method
            if royalty
            else RecognitionMethod.POINT_IN_TIME,
            over_time_criterion="NOT_APPLICABLE",
            ratable_convention=None,
        )
    available = availability(st, draft)
    start = _latest(draft.start_date, available)
    if agreement is not None:
        policy = ctx.policies.value(RENEWAL_POLICY, contract=draft.contract_key)
        if policy == RENEWAL_PERIOD_START:
            start = _latest(start, draft.line.line_start_date)
        elif policy == LATER_OF_AGREEMENT_AND_AVAILABILITY:
            start = _latest(agreement, available)
        else:
            raise ValueError(f"{RENEWAL_POLICY} holds an unknown literal {policy!r} (CV-17)")
    return dataclasses.replace(terms, recognition_start_date=start)


def _meets_55_62(outcome: Mapping[str, str], subject_key: str) -> bool:
    """Both 606-10-55-62 criteria answered ``true`` on the reviewed record (D-91 gaps (viii)).

    Absent members are ``false`` (the right to use); a member that is neither ``true`` nor
    ``false`` is refused rather than ignored (CV-45), and one member without the other is refused
    as well, because T-CON-19 answers them together (the API rejects such a record with 422).
    """
    answers: dict[str, bool] = {}
    for member in (FUNCTIONALITY_EXPECTED_TO_CHANGE, CUSTOMER_REQUIRED_TO_USE_UPDATED_IP):
        value = outcome.get(member)
        if value is None:
            continue
        if value not in ("true", "false"):
            raise ValueError(
                f"{subject_key}: LICENCE_NATURE member {member} is neither true nor false "
                "(T-CON-19)"
            )
        answers[member] = value == "true"
    if len(answers) == 1:
        raise ValueError(
            f"{subject_key}: the 606-10-55-62 criteria are answered together (T-CON-19)"
        )
    return len(answers) == 2 and all(answers.values())


def availability(st: IdentifiedState, draft: PobDraft) -> date | None:
    """The first ``DELIVERY_RECORDED`` of the obligation with trigger ``CONTROL_TRANSFER`` or
    ``DELIVERY`` (55-58C), by ENG-06 order; ``None`` when the stream holds none."""
    for event in st.canonical.measure_events:
        if event.event_type != "DELIVERY_RECORDED" or event.contract_key != draft.contract_key:
            continue
        named = draft.subject_key in event.obligation_subject_keys or (
            payload_text(event.payload, "obligation_key") == draft.obligation_key
        )
        if named and payload_text(event.payload, "trigger") in _AVAILABILITY_TRIGGERS:
            return event.effective_date
    return None


def _latest(*values: date | None) -> date | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None
