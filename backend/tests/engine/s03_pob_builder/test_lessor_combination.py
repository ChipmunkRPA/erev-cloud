"""Reviewed POL-231 eligibility, routing and retained combined-component evidence."""

import dataclasses
from fractions import Fraction

import pytest
from pydantic import ValidationError

from erev_api.enums import JudgementTopic
from erev_api.schemas.db_json import JudgementQuestionnaire
from erev_engine.bundle import JudgementInput
from erev_engine.enums import ScopeFlag
from tests.engine.s03_pob_builder.test_s03_elections import (
    CONTRACT,
    OVER_TIME,
    booked,
    bundle,
    fold,
    header,
    line,
    product,
    template,
)


def assessment(**changes):
    return {
        "obligation_key": "SERVICE",
        "lessor_lease_obligation_key": "LEASE",
        "lessor_asset_class": "Equipment",
        "lessor_same_transfer_pattern": True,
        "lessor_operating_lease": True,
        "lessor_nonlease_predominates": True,
        **changes,
    }


def example(*, elected=True, book="ASC606", outcome=None):
    values = assessment() if outcome is None else outcome
    record = JudgementInput(
        "J-LESSOR",
        "OTHER",
        CONTRACT,
        None,
        {
            key: str(value).lower() if isinstance(value, bool) else value
            for key, value in values.items()
        },
    )
    return bundle(
        booked(
            line("SERVICE", "MAINT", price="2500.00"),
            line("LEASE", "EQUIP", price="7500.00", scope_flag="LEASE_842"),
        ),
        products=[product("EQUIP"), product("MAINT")],
        templates=[template(**OVER_TIME)],
        contracts=[header(judgements=(record,))],
        books=(book,),
        policies={
            book: {"scope.lessor_combination_expedient": "ELECTED" if elected else "NOT_ELECTED"}
        },
    )


@pytest.mark.parametrize("predominates", [True, False])
def test_eligible_combination_retains_full_price_and_source_members(predominates):
    state, nodes = fold(example(outcome=assessment(lessor_nonlease_predominates=predominates)))
    assert len(state.obligations) == 1
    obligation = state.obligations[0]
    assert obligation.stated_price == Fraction(10000)
    assert {member.obligation_key for member in obligation.members} == {"LEASE", "SERVICE"}
    assert obligation.scope_flag == (
        ScopeFlag.IN_SCOPE_606 if predominates else ScopeFlag.LEASE_842
    )
    assert obligation.routed_out is not predominates
    assert obligation.lessor_judgement_keys == ("J-LESSOR",)
    node = nodes[f"stated_price:{obligation.subject_key}:-"]
    assert "J-LESSOR" in str(node)


@pytest.mark.parametrize("case", ["not_elected", "ineligible", "ifrs", "missing"])
def test_no_unapproved_or_ineligible_combination(case):
    value = example(
        elected=case != "not_elected",
        book="IFRS15" if case == "ifrs" else "ASC606",
        outcome=assessment(lessor_operating_lease=False) if case == "ineligible" else None,
    )
    if case == "missing":
        value = dataclasses.replace(value, contracts=(header(),))
    state, _ = fold(value, "IFRS15" if case == "ifrs" else "ASC606")
    assert len(state.obligations) == 2


def test_unknown_lease_cannot_silently_route_revenue():
    with pytest.raises(ValueError, match="associated lease"):
        fold(example(outcome=assessment(lessor_lease_obligation_key="UNKNOWN")))


def test_questionnaire_requires_complete_strict_assessment():
    assert JudgementQuestionnaire.validate(JudgementTopic.OTHER, assessment()) == assessment()
    for change in (
        {"lessor_asset_class": ""},
        {"lessor_operating_lease": "true"},
        {"lessor_lease_obligation_key": "SERVICE"},
        {"lessor_nonlease_predominates": None},
    ):
        with pytest.raises(ValidationError):
            JudgementQuestionnaire.validate(JudgementTopic.OTHER, assessment(**change))


@pytest.mark.parametrize("predominates", [True, False])
def test_complete_engine_allocates_combined_amount_and_routes_revenue(predominates):
    from support import bundles

    from erev_engine import compute
    from tests.engine.s03_pob_builder.test_s03_elections import INCEPTION, points

    value = example(outcome=assessment(lessor_nonlease_predominates=predominates))
    value = dataclasses.replace(
        value,
        events=value.events
        + (bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),),
        ssp_versions=(points(EQUIP="7500", MAINT="2500"),),
    )
    output = compute(value).books[0]
    columns = output.contract_version.columns
    assert columns["fixed_consideration"] == 1_000_000
    assert columns["transaction_price"] == (1_000_000 if predominates else 0)
    assert columns["out_of_scope_amount"] == (0 if predominates else 1_000_000)
    assert columns["revenue_cum"] > 0 if predominates else columns["revenue_cum"] == 0
    assert columns["rpo_amount"] > 0 if predominates else columns["rpo_amount"] == 0
    if not predominates:
        assert output.schedules == ()


def test_later_unrelated_other_assessment_does_not_hide_lessor_assessment():
    value = example()
    original = value.contracts[0]
    unrelated = JudgementInput(
        "J-Z",
        "OTHER",
        CONTRACT,
        None,
        {"obligation_key": "SERVICE", "returns_immaterial": "true"},
    )
    value = dataclasses.replace(
        value,
        contracts=(dataclasses.replace(original, judgements=original.judgements + (unrelated,)),),
    )
    state, _ = fold(value)
    assert len(state.obligations) == 1


def test_election_resolves_at_associated_lease_product():
    from tests.engine.s03_pob_builder.test_s03_elections import policy

    value = example(elected=False)
    book = value.books[0]
    election = policy(
        "scope.lessor_combination_expedient",
        "OBLIGATION",
        f"{CONTRACT}/LEASE",
        "ELECTED",
        level="PRODUCT",
    )
    value = dataclasses.replace(
        value,
        books=(
            dataclasses.replace(
                book,
                policies=tuple(
                    sorted(
                        (*book.policies, election), key=lambda p: (p.code, p.scope, p.subject_key)
                    )
                ),
            ),
        ),
    )
    state, _ = fold(value)
    assert len(state.obligations) == 1
