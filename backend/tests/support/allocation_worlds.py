"""Stage 05 allocation worlds shared by the engine tests (D-91 C606-02).

The FASB Example 34 bundles (SSPs A 40, B 55, C 45; bundle B+C regularly sold at 60; D residual,
range 15 to 45) and the targeted-VC ``element`` builder follow the answer keys
``docs/accounting/answer-keys/alc/ALC-CHK-03[234]-*.yaml``. ``native`` builds one activated (or
booked) ASC606 contract over ``TPL-PIT`` point-in-time lines with the SSP entries, estimates and
judgements given; ``fold`` runs stages 01 to 05 with one trace builder for stages 03 to 05 (§0.3).
Extracted from ``tests/engine/s05_allocation/test_s05_exceptions.py`` so that the stage 08 tests
run the same worlds through the public ``compute`` and through ``s08.apply`` after the fold. No
database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BundleComponentInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    JudgementInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
)
from erev_engine.stages.s01_canonicalize import encode_key
from erev_engine.stages.s04_transaction_price import PricedState
from erev_engine.stages.state import AllocatedState, BookContext, ObligationState, PolicyResolver
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles

CONTRACT = "K-01"
GROUP = "CG-1"
INCEPTION = date(2026, 1, 1)
END = date(2026, 12, 31)
ZERO = "0" * 64
BOOK = "SSP-MAIN"
BUNDLE = "BUNDLE-BC"
ELEMENT = f"{CONTRACT}/VC-1"
TOLERANCE = "vc.targeted_allocation_tolerance"

PolicyValue = str | Mapping[str, str]


def template(code: str) -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO,
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
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


def entry(
    product: str,
    *,
    point: str | None = None,
    band: tuple[str, str, str] | None = None,
    method: str = "observable",
) -> SspEntryInput:
    """An entry with one ``NONE`` row: a point, or a (low, mid, high) band."""
    low, mid, high = band or (None, None, None)

    def value(text: str | None) -> Decimal | None:
        return None if text is None else Decimal(text)

    return SspEntryInput(
        entry_key=f"{BOOK}@v1/{product}//-/USD",
        product_code=product,
        stratification="",
        region=None,
        channel=None,
        segment=None,
        deal_size_band=None,
        term_band=None,
        currency="USD",
        method=method,
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
            SspRangeInput("NONE", None, None, value(point), value(low), value(mid), value(high)),
        ),
    )


# FASB Example 34: SSPs A 40, B 55, C 45; bundle B+C regularly sold at 60; D residual, range 15-45.
EX_34 = (
    entry("PROD-A", point="40"),
    entry("PROD-B", point="55"),
    entry("PROD-C", point="45"),
    entry(BUNDLE, point="60"),
)
RESIDUAL_D = entry("PROD-D", band=("15", "30", "45"), method="residual")
ESTIMATED_D = entry("PROD-D", point="30", method="adjusted_market")
# FASB Example 35: licences X (SSP 800) and Y (SSP 1,000).
EX_35 = (entry("LIC-X", point="800"), entry("LIC-Y", point="1000"))


def line(key: str, product: str, price: str) -> dict[str, object]:
    return bundles.booking_line(
        key, product_code=product, quantity="1", total_price=price, start=INCEPTION, end=END
    )


def element(
    amount: str,
    *,
    target: str = "OBLIGATIONS",
    keys: Sequence[str] = ("L2-Y",),
    evidence: bool = True,
    kind: str | None = None,
) -> EstimateVersionInput:
    """A ``VARIABLE_CONSIDERATION`` element entered at ``amount`` and pinned at inception."""
    parameters: dict[str, object] = {}
    if evidence:
        parameters["allocation_criteria_evidence"] = "Reviewer attested 606-10-32-40(a) and (b)"
    return EstimateVersionInput(
        estimate_key=ELEMENT,
        estimate_kind="VARIABLE_CONSIDERATION",
        element_code="VC-1",
        method="ENTERED_AMOUNT",
        vc_element_type=kind,
        allocation_target=target,
        target_obligation_keys=tuple(keys),
        obligation_key=None,
        version_key=f"{ELEMENT}@v1",
        version_no=1,
        status="APPROVED",
        effective_date=INCEPTION,
        scenarios=(),
        parameters=parameters,
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=Decimal(amount),
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256=ZERO,
    )


def approval() -> JudgementInput:
    """The reviewed ``OTHER`` judgement approving the proposed 32-37 exception (OQ-A-17)."""
    return JudgementInput(
        "J-DISC-EXC", "OTHER", CONTRACT, None, {"discount_exception_bundle": BUNDLE}
    )


def override() -> JudgementInput:
    """The reviewed ``OTHER`` judgement clearing the POL-044 test for the element (OQ-A-12)."""
    outcome = {"estimate_key": ELEMENT, "pol_044_override": "true"}
    return JudgementInput("J-POL-044", "OTHER", CONTRACT, None, outcome)


def native(
    *lines: dict[str, object],
    entries: Sequence[SspEntryInput],
    overrides: Mapping[str, PolicyValue] | None = None,
    estimates: Sequence[EstimateVersionInput] = (),
    judgements: Sequence[JudgementInput] = (),
    bundle: bool = False,
    activated: bool = False,
) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24)
    base = bundles.book("ASC606", entity=calendar)
    values = overrides or {}
    policies = tuple(
        dataclasses.replace(policy, value=values[policy.code])
        if policy.code in values and policy.scope == "GROUP"
        else policy
        for policy in base.policies
    )
    header = dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION), judgements=tuple(judgements)
    )
    codes = sorted({str(item["product_code"]) for item in lines})
    products = [bundles.product(code, template_code="TPL-PIT", family=None) for code in codes]
    if bundle:
        components = tuple(
            BundleComponentInput(
                code, Decimal(1), "relative_ssp", None, index, date(2025, 1, 1), None
            )
            for index, code in enumerate(("PROD-B", "PROD-C"), start=1)
        )
        products.append(
            dataclasses.replace(
                bundles.product(BUNDLE, template_code="TPL-PIT", family=None),
                is_bundle=True,
                components=components,
            )
        )
    keys = [str(item["obligation_key"]) for item in lines]
    events: list[EventInput] = [
        bundles.event(
            CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": list(lines)}, obligation_keys=keys
        )
    ]
    for number, version in enumerate(estimates, start=2):
        payload = {"estimate_version_id": version.version_key}
        events.append(bundles.event(CONTRACT, number, "ESTIMATE_CHANGED", INCEPTION, payload))
    if activated:  # the ALC-CHK-032 step bundle (D-88 L7-5-Q-7)
        number = len(events) + 1
        events.append(bundles.event(CONTRACT, number, "CONTRACT_ACTIVATED", INCEPTION, {}))
    book = SspVersionInput(
        ssp_book_code=BOOK,
        version_key=f"{BOOK}@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2025, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2025, 12, 1, tzinfo=UTC),
        content_sha256=ZERO,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(sorted(entries, key=lambda e: e.product_code)),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(dataclasses.replace(base, policies=policies),),
        entities=(calendar,),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=tuple(events),
        ssp_versions=(book,),
        pob_template_versions=(template("TPL-PIT"),),
        rule_set_versions=(),
        estimate_versions=tuple(
            sorted(estimates, key=lambda item: (item.estimate_key, item.version_no))
        ),
        fx_rates=(),
        posted=(),
    )


def ex_34(
    *prices: str,
    residual: SspEntryInput | None = None,
    judgements: Sequence[JudgementInput] = (),
    overrides: Mapping[str, PolicyValue] | None = None,
    activated: bool = False,
    estimates: Sequence[EstimateVersionInput] = (),
) -> InputBundle:
    keys = ("L1-A", "L2-B", "L3-C", "L4-D")[: len(prices)]
    products = ("PROD-A", "PROD-B", "PROD-C", "PROD-D")[: len(prices)]
    lines = [line(k, p, price) for k, p, price in zip(keys, products, prices, strict=True)]
    entries = [*EX_34, *(() if residual is None else (residual,))]
    return native(
        *lines,
        entries=entries,
        judgements=judgements,
        overrides=overrides,
        estimates=estimates,
        bundle=True,
        activated=activated,
    )


def untargeted_element(amount: str = "0", *, code: str = "BASE") -> EstimateVersionInput:
    """A contract-wide ``VARIABLE_CONSIDERATION`` element ``K-01/<code>`` entered at ``amount`` and
    pinned at inception: the S08-R-07 pure-inception route of its later versions."""
    key = f"{CONTRACT}/{code}"
    return dataclasses.replace(
        element(amount, target="CONTRACT", keys=(), evidence=False),
        estimate_key=key,
        element_code=code,
        version_key=f"{key}@v1",
    )


def later_version(
    version: EstimateVersionInput,
    version_no: int,
    effective: date,
    amount: str,
    *,
    keys: Sequence[str] | None = None,
    parameters: Mapping[str, object] | None = None,
) -> EstimateVersionInput:
    """Version ``version_no`` of ``version``'s element, effective on ``effective`` at ``amount``.

    ``keys`` replaces the target set and ``parameters`` the T-CON-13 parameters (the S08-R-04
    target-set and evidence guards); otherwise both carry over.
    """
    return dataclasses.replace(
        version,
        version_no=version_no,
        version_key=f"{version.estimate_key}@v{version_no}",
        effective_date=effective,
        constrained_amount=Decimal(amount),
        supersedes_version_key=f"{version.estimate_key}@v{version_no - 1}",
        target_obligation_keys=version.target_obligation_keys if keys is None else tuple(keys),
        parameters=dict(version.parameters) if parameters is None else dict(parameters),
    )


def with_changes(
    value: InputBundle,
    changes: Sequence[EstimateVersionInput],
    *,
    deliveries: Sequence[tuple[date, str]] = (),
    memo_on: date | None = None,
    policies: Mapping[str, str] | None = None,
) -> InputBundle:
    """``value`` with later estimate versions, deliveries and a dating memo appended as events in
    date order after the inception events, and ``policies`` (code -> value) replacing every scope's
    value on each book (for example POL-200 ``APPLY``)."""
    extra: list[tuple[date, str, dict[str, object], list[str]]] = []
    for on, key in deliveries:
        payload: dict[str, object] = {
            "obligation_key": key,
            "quantity": Decimal(1),
            "trigger": "CONTROL_TRANSFER",
        }
        extra.append((on, "DELIVERY_RECORDED", payload, [key]))
    for version in changes:
        payload = {"estimate_version_id": version.version_key}
        extra.append((version.effective_date, "ESTIMATE_CHANGED", payload, []))
    if memo_on is not None:
        key = str(value.events[0].payload["lines"][0]["obligation_key"])  # type: ignore[index]
        memo: dict[str, object] = {"obligation_key": key, "memo_1": f"close {memo_on.isoformat()}"}
        extra.append((memo_on, "MEMO_UPDATED", memo, [key]))
    events = list(value.events)
    for on, event_type, payload, keys in sorted(extra, key=lambda item: item[0]):
        events.append(
            bundles.event(CONTRACT, len(events) + 1, event_type, on, payload, obligation_keys=keys)
        )
    versions = sorted(
        (*value.estimate_versions, *changes), key=lambda item: (item.estimate_key, item.version_no)
    )
    value = dataclasses.replace(value, events=tuple(events), estimate_versions=tuple(versions))
    if policies:
        value = dataclasses.replace(
            value,
            books=tuple(
                dataclasses.replace(
                    book,
                    policies=tuple(
                        dataclasses.replace(policy, value=policies[policy.code])
                        if policy.code in policies
                        else policy
                        for policy in book.policies
                    ),
                )
                for book in value.books
            ),
        )
    return value


def targeted_world(
    *,
    lines: Sequence[tuple[str, str, str]] = (("A", "PROD-A", "50"), ("B", "PROD-B", "50")),
    ssp: Mapping[str, str] | None = None,
    estimates: Sequence[EstimateVersionInput] = (),
    overrides: Mapping[str, PolicyValue] | None = None,
) -> InputBundle:
    """The D-91 C606-02 review world: point-in-time lines (key, product, price) with SSP points
    (default 100 each) and the estimate versions pinned at inception, activated, with the POL-044
    tolerance not enforced. Later versions, deliveries and policies come from ``with_changes``."""
    products = sorted({product for _, product, _ in lines})
    points = {product: "100" for product in products} if ssp is None else ssp
    return native(
        *(line(key, product, price) for key, product, price in lines),
        entries=[entry(product, point=points[product]) for product in products],
        estimates=list(estimates),
        overrides={TOLERANCE: "NOT_ENFORCED", **(overrides or {})},
        activated=True,
    )


def context(value: InputBundle) -> BookContext:
    book = value.books[0]
    return BookContext(
        book_code=BookCode(book.book_code),
        framework=BookCode(book.book_code),
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in value.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


def fold(
    value: InputBundle,
) -> tuple[BookContext, PricedState, AllocatedState, dict[str, TraceNode]]:
    """Stages 01 to 05 with one trace builder for stages 03 to 05 (§0.3)."""
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    allocated = s05_allocation.run(ctx, priced, tb)
    return ctx, priced, allocated, {node.id: node for node in tb.build(root_measures={}).nodes}


def posted(allocated: AllocatedState) -> dict[str, int]:
    return {ob.obligation_key: ob.original_allocation.a_posted for ob in allocated.obligations}


def exact(allocated: AllocatedState) -> dict[str, Fraction]:
    return {ob.obligation_key: ob.original_allocation.x_exact for ob in allocated.obligations}


def by_key(allocated: AllocatedState, key: str) -> ObligationState:
    return next(ob for ob in allocated.obligations if ob.obligation_key == key)


def share_id(key: str) -> str:
    return f"targeted_vc_allocated@{encode_key(ELEMENT)}:{CONTRACT}/{key}:-"
