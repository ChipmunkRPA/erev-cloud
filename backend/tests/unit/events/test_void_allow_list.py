"""The void route's allow-list is complete over E-03 (04 §16.3 "Voids on this route", rev 1.231;
dev-guide DG-KRN-EVT-02 rev 1.222; item EVT-VOID-OWN-COMMANDS-1).

Pure. Every literal of ``ContractEventType`` is one of the twelve fact-capture types
``POST /events/{id}/request-void`` takes, or has the sentence its refusal answers — never both and
never neither, so a type added to E-03 is refused until it is put on the list. The database
witnesses are in ``tests/domain/contracts/test_event_void_types.py``.
"""

from __future__ import annotations

from erev_api.domain.contracts import events as contract_events
from erev_api.enums import ContractEventType
from erev_api.events import step1

FACT_CAPTURE = {
    ContractEventType.DELIVERY_RECORDED,
    ContractEventType.RETURN_RECORDED,
    ContractEventType.PROGRESS_RECORDED,
    ContractEventType.MILESTONE_ACHIEVED,
    ContractEventType.USAGE_REPORTED,
    ContractEventType.COST_INCURRED,
    ContractEventType.BILLING_RECORDED,
    ContractEventType.CREDIT_MEMO_RECORDED,
    ContractEventType.PAYMENT_RECEIVED,
    ContractEventType.PRE_STANDARD_REVENUE_RECORDED,
    ContractEventType.SIGNIFICANT_CHANGE_FLAGGED,
    ContractEventType.MEMO_UPDATED,
}


def test_every_event_type_is_voidable_or_names_what_undoes_it() -> None:
    assert set(contract_events.VOIDABLE_TYPES) == FACT_CAPTURE
    # the twelve are what the events route records, less the Step 1 assessment
    assert contract_events.VOIDABLE_TYPES == (
        contract_events.RECORDED_TYPES - contract_events.STEP1_TYPES
    )
    for event_type in ContractEventType:
        sentence = contract_events.void_refusal(event_type)
        assert (sentence is None) is (event_type in FACT_CAPTURE), event_type
        assert sentence is None or sentence.endswith("."), event_type

    # the refusals that existed keep their sentences
    assert contract_events.void_refusal(ContractEventType.EVENT_VOIDED) == (
        "This event is a void or is already voided."
    )
    assert (
        contract_events.void_refusal(ContractEventType.COLLECTIBILITY_ASSESSED)
        == step1.ASSESSMENT_NOT_VOIDABLE
    )
    for activation in (
        ContractEventType.CONTRACT_CRITERIA_MET,
        ContractEventType.CONTRACT_ACTIVATED,
    ):
        assert contract_events.void_refusal(activation) == step1.ACTIVATION_NOT_VOIDABLE
    assert contract_events.void_refusal(ContractEventType.MANUAL_ADJUSTMENT_APPLIED) == (
        "A posted manual adjustment cannot be voided. Correct it with a further adjustment."
    )

    # fail closed: a literal that E-03 gains before this module is refused
    assert contract_events.void_refusal("A_TYPE_OF_LATER") == (
        "An event of this type is not voided as an event."
    )
