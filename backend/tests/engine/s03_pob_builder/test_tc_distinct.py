"""Legacy distinct flags are exact and never drop a row (legacy 03 §7.3 TC-13; BUILD_SPEC ENA-3).

Bundles come from ``support.bundles`` (DG-ENG-11); no database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, dates
from erev_engine.bundle import InputBundle, TemplateInput
from erev_engine.enums import BookCode, Distinctness, legacy_distinctness
from erev_engine.errors import EngineError
from erev_engine.stages import s01_canonicalize, s02_contract_identification, s03_pob_builder
from erev_engine.stages.state import BookContext, PolicyResolver
from erev_engine.trace import TraceBuilder
from support import bundles

INCEPTION = date(2026, 1, 1)
PRESET = "LEGACY_PARITY"
# Probe P-04 (legacy 03 §6.3): four SKUs uploaded with the exact legacy flags; TP 420.00.
ROWS = (
    ("POB-1", "Hardware", "Distinct", "100.00"),
    ("POB-2", "Software", "Distinct", "120.00"),
    ("POB-3", "Widget", "Nondistinct", "80.00"),
    ("POB-4", "Consulting", "Nondistinct", "120.00"),
)


def template(code: str, distinctness: Distinctness) -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256="0" * 64,
        obligation_kind="STANDARD",
        distinctness=distinctness.value,
        series_increment_unit=None,
        satisfaction_pattern="POINT_IN_TIME",
        over_time_criterion="NOT_APPLICABLE",
        recognition_method="UNITS_DELIVERED",
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
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


def test_tc_prospective_13_distinct_flag_exact_strings() -> None:
    assert legacy_distinctness("Distinct") == Distinctness.DISTINCT
    assert legacy_distinctness("Nondistinct") == Distinctness.NONDISTINCT
    for flag in ("distinct", "Non-distinct"):
        with pytest.raises(EngineError) as raised:
            legacy_distinctness(flag)
        assert (raised.value.code, raised.value.detail) == (
            "SSP_DISTINCT_FLAG_INVALID",
            {"flag": flag},
        )

    products, lines = [], []
    for key, sku, flag, price in ROWS:
        distinctness = legacy_distinctness(flag)
        code = f"LEGACY-{distinctness.value.upper()}"
        base = bundles.product(sku, template_code=code, family=None)
        products.append(dataclasses.replace(base, distinctness_default=distinctness.value))
        lines.append(bundles.booking_line(key, product_code=sku, total_price=price))
    contract = bundles.contract()
    booked = bundles.event(
        contract.external_id,
        1,
        "CONTRACT_BOOKED",
        INCEPTION,
        {"lines": lines},
        obligation_keys=[key for key, *_ in ROWS],
    )
    calendar = bundles.entity(start=INCEPTION, months=24)
    value = InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 1, 31, 23, tzinfo=UTC),
        tenant_preset=PRESET,
        currencies=bundles.currencies("USD"),
        books=(bundles.book("ASC606", preset=PRESET, entity=calendar),),
        entities=(calendar,),
        group=bundles.group((contract,), products=products),
        contracts=(contract,),
        events=(booked,),
        ssp_versions=(),
        pob_template_versions=(
            template("LEGACY-DISTINCT", Distinctness.DISTINCT),
            template("LEGACY-NONDISTINCT", Distinctness.NONDISTINCT),
        ),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )
    book = value.books[0]
    horizon = {
        calendar.code: [
            p.period_key
            for p in calendar.periods
            if dates.period_state(p, "ASC606") in dates.POSTABLE_STATES
        ][-1]
    }
    ctx = BookContext(
        book_code=BookCode.ASC606,
        framework=BookCode.ASC606,
        currencies=value.currencies,
        txn_currency="USD",
        entities={calendar.code: calendar},
        horizon=horizon,
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=PRESET,
    )
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )

    drafts = s03_pob_builder.build_lines(
        ctx, identified, lines, INCEPTION, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    assert [(d.obligation_key, d.distinctness) for d in drafts] == [
        ("POB-1", Distinctness.DISTINCT),
        ("POB-2", Distinctness.DISTINCT),
        ("POB-3", Distinctness.NONDISTINCT),
        ("POB-4", Distinctness.NONDISTINCT),
    ]
    assert sum((d.stated_price for d in drafts), Fraction(0)) == 420  # no row dropped

    st = s03_pob_builder.run(ctx, identified, TraceBuilder(engine_version=ENGINE_VERSION))
    assert st.findings == ()
    assert [o.obligation_key for o in st.obligations] == ["POB-1", "POB-2", "POB-3", "POB-4"]
    assert sum((o.stated_price for o in st.obligations), Fraction(0)) == 420
