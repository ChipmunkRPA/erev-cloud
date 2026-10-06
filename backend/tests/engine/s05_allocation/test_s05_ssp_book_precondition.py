"""An approved SSP book in the contract currency is a precondition of every world that computes
(ENGINE_SPEC S05-R-02; CV-15): the batch ci on main 065e7f65 failed TWO F-RPS database tests
(`test_platform_following_db.py::test_estimate_route_emits_estimate_changed_from_the_keys_values`
and `test_platform_reads_db.py::test_reads_rebuild_the_book_and_read_state_digest_and_approvals`,
recorded "not run — databases not provisioned" by their lane) with ``EngineError:
SSP_KEY_NOT_FOUND`` from the estimate-submission dry run and the activation compute, because their
K06-shaped world (entity AVM-DE, EUR, product AVM-PART on the units template TPL_PROD_UNITS,
contract NS-SO-DE-5002 for 57,500.00 EUR) omitted the ``DE-LIST`` EUR SSP book that
``test_estimates.py``'s K06 world approves. The third failure of that module
(``test_override_is_created_and_submitted…``) is a separate approval-id assertion owned by F-RPS
(PLAT-OVR-1), not an SSP case.

Scope, stated plainly (Codex packet 1222): this is a NARROWER absent / present SSP-precondition
check on the engine — the bundle below uses a POINT_IN_TIME template, not the factory fixture's
TPL_PROD_UNITS (``UNITS_DELIVERED``), and it does not replay the factory world or prove the
database approval, estimate or activation paths; it pins two engine facts: without a book stage 05
refuses the line by name (S05-R-02, empty book code), and with an approved EUR range entry the
one-line contract allocates its stated price. Neither fact changed between T1's base 4ed5f423 and
065e7f65 (checked against the archived base engine; no lane regression).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import (
    InputBundle,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.errors import EngineError
from support import bundles

ENTITY = "AVM-DE"
CONTRACT = "NS-SO-DE-5002"
PART = "AVM-PART"
TEMPLATE = "TPL-PROD-UNITS"
INCEPTION = date(2026, 7, 1)
ZERO_SHA = "0" * 64
KNOWN_AT = datetime(2026, 7, 31, tzinfo=UTC)


def _template() -> TemplateInput:
    return TemplateInput(
        template_code=TEMPLATE,
        version_key=f"{TEMPLATE}@v1",
        version_no=1,
        content_sha256=ZERO_SHA,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern="POINT_IN_TIME",
        over_time_criterion="NOT_APPLICABLE",
        recognition_method="POINT_IN_TIME",
        ratable_convention=None,
        start_date_rule="LINE_START",
        end_date_rule="LINE_END",
        term_months=None,
        principal_agent="PRINCIPAL",
        warranty_type="NONE",
        licence_nature="NOT_APPLICABLE",
        sfc_assessment_required=False,
        revenue_category="PRODUCT",
        disaggregation={},
        account_role_overrides={},
        stratification_label=None,
        is_excluded_from_netting_attribution=False,
        policy_values={},
        effective_from=date(2026, 1, 1),
        effective_to=None,
    )


def _de_list_book() -> SspVersionInput:
    """The ``DE-LIST`` EUR book of ``test_estimates.py``'s K06 world: AVM-PART 90.00 / 100.00 /
    110.00 per unit (``range_entry``), version 2026 effective 1 January 2026, approved."""
    entry = SspEntryInput(
        entry_key=f"DE-LIST@v1/{PART}//-/EUR",
        product_code=PART,
        stratification="",
        region=None,
        channel=None,
        segment=None,
        deal_size_band=None,
        term_band=None,
        currency="EUR",
        method="observable",
        value_basis="AMOUNT",
        unit_list_price=None,
        midpoint_discount_ratio=None,
        range_ratio=None,
        cost_basis=None,
        margin_ratio=None,
        distinctness="distinct",
        revenue_account_code=None,
        observable_point=None,
        ranges=(
            SspRangeInput(
                "NONE", None, None, None, Decimal("90.00"), Decimal("100.00"), Decimal("110.00")
            ),
        ),
    )
    return SspVersionInput(
        ssp_book_code="DE-LIST",
        version_key="DE-LIST@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label="2026",
        effective_from_date=date(2026, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2026, 1, 15, tzinfo=UTC),
        content_sha256=ZERO_SHA,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=(entry,),
    )


def k06_world(*, ssp_versions: tuple[SspVersionInput, ...]) -> InputBundle:
    """The factory world of the F-RPS platform tests as an engine bundle: one EUR entity, one
    product on a units template, one contract line O1 for 575 × AVM-PART at 57,500.00 EUR."""
    calendar = bundles.entity(ENTITY, functional_currency="EUR", start=INCEPTION, months=6)
    header = bundles.contract(CONTRACT, entity_code=ENTITY, currency="EUR", inception=INCEPTION)
    line = bundles.booking_line(
        "O1",
        product_code=PART,
        quantity="575",
        total_price="57500.00",
        start=INCEPTION,
        end=INCEPTION,
    )
    booked = bundles.event(
        CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": [line]}, obligation_keys=["O1"]
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("EUR"),
        books=(bundles.book("ASC606", entity=calendar),),
        entities=(calendar,),
        group=bundles.group(
            (header,),
            group_key=f"CG-{CONTRACT}",
            products=(bundles.product(PART, template_code=TEMPLATE, family=None),),
        ),
        contracts=(header,),
        events=(booked,),
        ssp_versions=ssp_versions,
        pob_template_versions=(_template(),),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def test_a_world_without_an_ssp_book_refuses_its_line_by_name() -> None:
    """The failing factory path: no approved SSP book → stage 05 S05-R-02 finds no book for the
    line and the compute fails closed with SSP_KEY_NOT_FOUND naming the product and an empty book
    code (CV-15) — the estimate-submission dry run and the activation compute raise this."""
    with pytest.raises(EngineError) as refused:
        compute(k06_world(ssp_versions=()))
    assert refused.value.code == "SSP_KEY_NOT_FOUND"
    findings = json.loads(str(refused.value.detail["findings"]))
    (finding,) = [item for item in findings if item["code"] == "SSP_KEY_NOT_FOUND"]
    assert finding["stage"] == 5 and finding["subject_key"] == f"{CONTRACT}/O1"
    assert finding["detail"] == {
        "product_code": PART,
        "rule": "S05-R-02",
        "ssp_book_code": "",
        "ssp_version_label": "",
        "stratification": "",
    }


def test_the_de_list_eur_book_lets_the_one_line_contract_allocate_its_price() -> None:
    """With the K06 world's approved DE-LIST EUR book (range 90.00 / 100.00 / 110.00 per unit) the
    contract computes: O1 carries the whole stated price 57,500.00 EUR (575 units within the
    range), in the transaction currency of the entity's book, no FX conversion."""
    output = compute(k06_world(ssp_versions=(_de_list_book(),)))
    (book,) = output.books
    assert book.book_code == "ASC606"
    (obligation,) = book.obligation_versions
    assert obligation.subject_key == f"{CONTRACT}/O1"
    assert obligation.columns["allocated_amount"] == 5750000  # minor units, EUR
    assert not [item for item in output.diagnostics if "SSP_KEY_NOT_FOUND" in str(item)]
