"""Engine worlds with revenue from obligations satisfied in prior periods (ENGINE_SPEC_B §15.2.4
S15-R-13, S15-R-14; ENGINE_SPEC S08-R-15 late carries; PRD WLD-X-16 family).

``late_world`` is the two-obligation point-in-time contract ``K-LATE`` of
``tests/engine/s15_disclosures/test_s15_prior_period_disaggregation.py`` (lane ENG-C4, D-97 (19)),
lifted here so the report reader can be tested on ACTUAL native traces: deliveries effective in a
closed period and recorded afterwards carry into the posting period (S08-R-15), and with
``second_entity`` POB-02 performs on that entity's own calendar while the contract header stays on
``ENTITY``. ``cross_entity_late_world`` is the admitted cross-entity, distinct-calendar case
(C4-PP-R1): US01 monthly with January closed, US02 calendar-quarter with Q1 closed, both
obligations delivered on 20 January 2026 and recorded after the closes, so POB-01 carries 1,000.00
into US01's ``FY2026-P02`` (February) and POB-02 carries 1,000.00 into US02's ``FY2026-P02`` (the
second quarter) — the same period-key string on two calendars — and the stage 15 sum node
``revenue_prior_period_sum:K-LATE@US01:FY2026-P02`` (the CONTRACTING entity) collects both
(2,000.00).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BookInput,
    EntityInput,
    EventInput,
    InputBundle,
    MappingRuleInput,
    PeriodInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.dates import month_end
from support import bundles

CONTRACT: Final = "K-LATE"
ENTITY: Final = "US01"
SECOND_ENTITY: Final = "US02"
KEYS: Final = ("POB-01", "POB-02")
INCEPTION: Final = date(2026, 1, 5)
BOOK: Final = "ASC606"


def pit_template(code: str = "TPL-PIT") -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256="0" * 64,
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
        revenue_category=None,
        disaggregation={},
        account_role_overrides={},
        stratification_label=None,
        is_excluded_from_netting_attribution=False,
        policy_values={},
        effective_from=date(2020, 1, 1),
        effective_to=None,
    )


def ssp_version(
    products: Sequence[str], values: Mapping[str, str] | None = None
) -> SspVersionInput:
    """Observable point SSPs, 1,000.00 unless ``values`` names the product's."""
    entries = tuple(
        SspEntryInput(
            entry_key=f"SSP-US@v1/{product}//-/USD",
            product_code=product,
            stratification="",
            region=None,
            channel=None,
            segment=None,
            deal_size_band=None,
            term_band=None,
            currency="USD",
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
                    "NONE",
                    None,
                    None,
                    Decimal((values or {}).get(product, "1000.00")),
                    None,
                    None,
                    None,
                ),
            ),
        )
        for product in products
    )
    return SspVersionInput(
        ssp_book_code="SSP-US",
        version_key="SSP-US@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2020, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        content_sha256="0" * 64,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=entries,
    )


def delivery(stream: int, key: str, on: date, contract: str = CONTRACT) -> EventInput:
    payload = {"obligation_key": key, "quantity": Decimal("1"), "trigger": "CONTROL_TRANSFER"}
    return bundles.event(contract, stream, "DELIVERY_RECORDED", on, payload, obligation_keys=[key])


def quarterly_entity(
    code: str = SECOND_ENTITY, year: int = 2026, *, closed: Iterable[str] = ()
) -> EntityInput:
    """A calendar-quarter entity (ALG-11 rule 3), period keys ``FY<year>-P01`` to ``P04``; the
    periods named in ``closed`` are closed for the book."""
    shut = set(closed)
    periods = tuple(
        PeriodInput(
            period_key=f"FY{year}-P{quarter:02d}",
            fiscal_year=year,
            period_no=quarter,
            start_date=date(year, 3 * quarter - 2, 1),
            end_date=month_end(date(year, 3 * quarter, 1)),
            states=((BOOK, "closed" if f"FY{year}-P{quarter:02d}" in shut else "open"),),
        )
        for quarter in range(1, 5)
    )
    return EntityInput(code, "USD", "America/New_York", "P445", periods)


def late_world(
    deliveries: Sequence[EventInput],
    *,
    states: Mapping[str, str],
    previous_heads: int = 0,
    second_entity: EntityInput | None = None,
) -> InputBundle:
    """Two 1,000.00 point-in-time obligations booked and activated on 5 January 2026; with
    ``second_entity`` POB-02 performs on that entity (its own calendar)."""
    calendar = bundles.entity(months=12, states=states)
    entities = [calendar] + ([second_entity] if second_entity is not None else [])
    header = bundles.contract(CONTRACT, inception=INCEPTION)
    booking = []
    for key in KEYS:
        line = bundles.booking_line(
            key,
            product_code=f"KIT-{key}",
            quantity="1",
            total_price="1000.00",
            start=INCEPTION,
            end=INCEPTION,
        )
        if second_entity is not None and key == "POB-02":
            line["performing_entity_code"] = second_entity.code
        booking.append(line)
    events = [
        bundles.event(
            CONTRACT,
            1,
            "CONTRACT_BOOKED",
            INCEPTION,
            {"lines": booking},
            obligation_keys=list(KEYS),
        ),
        bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
        *deliveries,
    ]
    products = tuple(
        bundles.product(f"KIT-{key}", template_code="TPL-PIT", family=None) for key in KEYS
    )
    group = dataclasses.replace(
        bundles.group((header,), group_key=f"CG-{CONTRACT}", products=products),
        previous_stream_heads=((CONTRACT, previous_heads),) if previous_heads else (),
    )
    policies = list(bundles.policy_set(book_code=BOOK, entity=calendar))
    if second_entity is not None:
        seen = {(p.code, p.scope, p.subject_key) for p in policies}
        for policy in bundles.policy_set(book_code=BOOK, entity=second_entity):
            if (policy.code, policy.scope, policy.subject_key) not in seen:
                policies.append(policy)
    mapping = bundles.account_mapping()
    if second_entity is not None:  # JET-13 intercompany lines of the performing-entity obligation
        extra = tuple(
            MappingRuleInput(role, None, None, None, None, None, code, {}, 0, 0)
            for role, code in (("INTERCOMPANY_DUE_FROM", "1800"), ("INTERCOMPANY_DUE_TO", "2800"))
        )
        rules = sorted(
            (*mapping.rules, *extra),
            key=lambda rule: (rule.account_role, rule.clearing_purpose or "", rule.account_code),
        )
        mapping = dataclasses.replace(mapping, rules=tuple(rules))
    book = BookInput(
        BOOK,
        True,
        tuple(sorted(entity.code for entity in entities)),
        tuple(sorted(policies, key=lambda p: (p.code, p.scope, p.subject_key))),
        mapping,
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=tuple(sorted(entities, key=lambda entity: entity.code)),
        group=group,
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(ssp_version([f"KIT-{key}" for key in KEYS]),),
        pob_template_versions=(pit_template(),),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def cross_entity_late_world() -> InputBundle:
    """The C4-PP-R1 case: POB-01 on US01 (monthly, January closed) and POB-02 on US02 (quarterly,
    Q1 closed), both delivered on 20 January 2026 and recorded after the closes."""
    return late_world(
        [delivery(3, "POB-01", date(2026, 1, 20)), delivery(4, "POB-02", date(2026, 1, 20))],
        states={"FY2026-P01": "closed"},
        previous_heads=2,
        second_entity=quarterly_entity(closed=("FY2026-P01",)),
    )
