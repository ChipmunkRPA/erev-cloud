"""Engine bundle builders for tests (dev-guide §7, §9.7; ENGINE_SPEC §0.4; BUILD_SPEC EKC-7).

The builders return deterministic ``erev_engine.bundle`` inputs: currencies, one entity with
monthly periods, books whose resolved policies come from the ``DEFAULT`` or ``LEGACY_PARITY``
preset of ``erev_api.registry.policies.POLICY_PARAMETERS`` (POLICIES §0.4, §6.3), an account
mapping, contracts and events. They read no clock, draw no random values and need no database
(DG-TST-18).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from erev_api.registry.policies import POLICY_PARAMETERS, RegistryParameterSpec
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    AccountMappingInput,
    BookInput,
    ContractInput,
    EntityInput,
    EstimateVersionInput,
    EventInput,
    GroupInput,
    InputBundle,
    MappingRuleInput,
    PayableInput,
    PaymentPointInput,
    PeriodInput,
    PortfolioInput,
    ProductInput,
    ResolvedPolicyInput,
)
from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217, CurrencyTable
from erev_engine.dates import month_end

PRESETS = ("DEFAULT", "LEGACY_PARITY")
ENTITY_CODE = "US01"
INCEPTION = date(2026, 1, 1)
KNOWN_AT = datetime(2026, 1, 31, 23, 0, tzinfo=UTC)
ZERO_SHA256 = "0" * 64
# A minimal chart for kernel tests: (account role, clearing purpose, account code).
ACCOUNTS = (
    ("ACCOUNTS_RECEIVABLE", None, "1200"),
    ("BILLING_CLEARING", "BILLING", "1290"),
    ("CONTRACT_ASSET", None, "1400"),
    # JET-09a to JET-09f roles, posted since stage 14 reads the stage 11 cost assets (lane L5-5).
    ("CONTRACT_COST_AMORTIZATION", None, "5100"),
    ("CONTRACT_COST_CLEARING", None, "2020"),
    ("CONTRACT_COST_IMPAIRMENT", None, "6000"),
    ("CONTRACT_LIABILITY", None, "2400"),
    ("COST_TO_FULFILL_ASSET", None, "1430"),
    ("COST_TO_OBTAIN_ASSET", None, "1420"),
    ("REVENUE", None, "4000"),
    ("UNBILLED_RECEIVABLE", None, "1410"),
)

PolicyValue = str | tuple[str, ...] | Mapping[str, str]


def currencies(*codes: str) -> CurrencyTable:
    """ISO 4217 specs of ``codes``; USD when none is named."""
    return {code: ISO_4217[code] for code in sorted(codes or ("USD",))}


def entity(
    code: str = ENTITY_CODE,
    *,
    functional_currency: str = "USD",
    start: date = INCEPTION,
    months: int = 24,
    books: Iterable[str] = ("ASC606",),
    states: Mapping[str, str] | None = None,
) -> EntityInput:
    """Monthly calendar periods ``FY<year>-P<nn>`` from ``start``; each book is ``open`` unless
    ``states`` maps the period key to another E-04 state."""
    if start.day != 1:
        raise ValueError("start must be the first day of a month")
    periods = []
    for offset in range(months):
        years, month = divmod(start.month - 1 + offset, 12)
        first = date(start.year + years, month + 1, 1)
        key = f"FY{first.year}-P{first.month:02d}"
        state = (states or {}).get(key, "open")
        periods.append(
            PeriodInput(
                period_key=key,
                fiscal_year=first.year,
                period_no=first.month,
                start_date=first,
                end_date=month_end(first),
                states=tuple((book, state) for book in sorted(books)),
            )
        )
    return EntityInput(code, functional_currency, "America/New_York", "MONTHLY", tuple(periods))


def default_entity() -> EntityInput:
    return entity()


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | Decimal):
        return str(value)
    if isinstance(value, list | tuple):
        return ",".join(_literal(item) for item in value)
    raise TypeError(f"unsupported policy value {type(value).__qualname__}")


def policy_value(value: object) -> PolicyValue:
    """A registry value as ``ResolvedPolicyInput.value``: literals and decimals as strings (§0.4).

    A list becomes a tuple; a mapping maps to strings, and a list member of a mapping is joined
    with commas (for example ``je.books`` ``{"primary": "ASC606", "set": "ASC606"}``).
    """
    if isinstance(value, Mapping):
        return {str(key): _literal(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple):
        return tuple(_literal(item) for item in value)
    return _literal(value)


def _preset_value(spec: RegistryParameterSpec, preset: str, book_code: str) -> object | None:
    # policies.py: None in default_ifrs15 or legacy_parity_value means the ASC606 default applies.
    if preset == "LEGACY_PARITY" and spec.legacy_parity_value is not None:
        return spec.legacy_parity_value
    if book_code == "IFRS15" and spec.default_ifrs15 is not None:
        return spec.default_ifrs15
    return spec.default_asc606


def policy_set(
    preset: str = "DEFAULT", *, book_code: str = "ASC606", entity: EntityInput | None = None
) -> tuple[ResolvedPolicyInput, ...]:
    """The resolved policies of ``preset`` for one book, sorted (code, scope, subject_key).

    Pin ``K`` values take the GROUP scope; pin ``P`` values take the PERIOD scope of every period of
    ``entity`` (CV-17). Codes without a framework default are omitted: the engine applies the rule
    of their §1 cell. Preset values carry level ``T`` and source ``LEGACY_PARITY``; framework
    defaults carry level ``DEFAULT`` and the POL id.
    """
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; expected one of {', '.join(PRESETS)}")
    calendar = default_entity() if entity is None else entity
    policies: list[ResolvedPolicyInput] = []
    for code, spec in sorted(POLICY_PARAMETERS.items()):
        raw = _preset_value(spec, preset, book_code)
        if raw is None:
            continue
        from_preset = preset == "LEGACY_PARITY" and spec.legacy_parity_value is not None
        level, source = ("T", "LEGACY_PARITY") if from_preset else ("DEFAULT", spec.source_ref)
        value = policy_value(raw)
        if spec.pin == "P":
            policies.extend(
                ResolvedPolicyInput(
                    code, "PERIOD", f"{calendar.code}@{p.period_key}", value, level, source, "P"
                )
                for p in calendar.periods
            )
        else:
            policies.append(ResolvedPolicyInput(code, "GROUP", "", value, level, source, "K"))
    return tuple(sorted(policies, key=lambda p: (p.code, p.scope, p.subject_key)))


def account_mapping(
    version_key: str = "MAP-KERNEL@v1",
    *,
    extra: Iterable[tuple[str, str | None, str]] = (),
) -> AccountMappingInput:
    """The kernel mapping of ``ACCOUNTS``; ``extra`` adds (role, purpose, account) rows — for
    example ``FX_GAIN_LOSS`` for a world whose functional currency differs (JET-10a)."""
    rows = (*ACCOUNTS, *extra)
    rules = tuple(
        MappingRuleInput(role, purpose, None, None, None, None, code, {}, 0, 0)
        for role, purpose, code in sorted(rows, key=lambda row: (row[0], row[1] or "", row[2]))
    )
    return AccountMappingInput(version_key, ZERO_SHA256, rules)


def book(
    book_code: str = "ASC606", *, preset: str = "DEFAULT", entity: EntityInput | None = None
) -> BookInput:
    calendar = default_entity() if entity is None else entity
    policies = policy_set(preset, book_code=book_code, entity=calendar)
    return BookInput(
        book_code, book_code == "ASC606", (calendar.code,), policies, account_mapping()
    )


def product(
    code: str = "SKU-1", *, template_code: str | None = "TPL-RATABLE", family: str | None = "SaaS"
) -> ProductInput:
    return ProductInput(
        code=code,
        sku_number=None,
        product_family=family,
        revenue_category=None,
        default_template_code=template_code,
        principal_agent="PRINCIPAL",
        distinctness_default="distinct",
        unit_of_measure="EA",
        is_bundle=False,
        policy_values={},
        assurance_cost_per_unit=None,
        components=(),
    )


def contract(
    external_id: str = "K-01",
    *,
    entity_code: str = ENTITY_CODE,
    currency: str = "USD",
    inception: date = INCEPTION,
    payment_schedule: Sequence[PaymentPointInput] = (),
    consideration_payable: Sequence[PayableInput] = (),
) -> ContractInput:
    return ContractInput(
        external_id=external_id,
        customer_code="CUST-1",
        related_party_group=None,
        contracting_entity_code=entity_code,
        transaction_currency=currency,
        inception_date=inception,
        signature_date=inception,
        document_ref=f"DOC-{external_id}",
        termination_party=None,
        termination_has_penalty=None,
        termination_notice_days=None,
        has_commercial_substance=True,
        region=None,
        channel=None,
        contract_type=None,
        renewal_of_contract_key=None,
        judgements=(),
        material_rights=(),
        modifications=(),
        noncash_consideration=(),
        consideration_payable=tuple(consideration_payable),
        payment_schedule=tuple(payment_schedule),
        scope_605_35=False,
    )


def group(
    contracts: Sequence[ContractInput],
    *,
    group_key: str = "CG-1",
    products: Sequence[ProductInput] = (),
    portfolios: Sequence[PortfolioInput] = (),
) -> GroupInput:
    return GroupInput(
        group_key=group_key,
        transaction_currency=contracts[0].transaction_currency,
        inception_date=min(c.inception_date for c in contracts),
        member_contract_keys=tuple(sorted(c.external_id for c in contracts)),
        criterion=None,
        previous_stream_heads=(),
        products=tuple(sorted(products, key=lambda p: p.code)),
        portfolios=tuple(sorted(portfolios, key=lambda p: p.code)),
    )


def booking_line(
    obligation_key: str = "POB-01",
    *,
    product_code: str = "SKU-1",
    quantity: str = "1",
    total_price: str = "1200.00",
    start: date = INCEPTION,
    end: date = date(2026, 12, 31),
) -> dict[str, object]:
    """An API-S-ContractLine member set (04 §16.1)."""
    return {
        "obligation_key": obligation_key,
        "product_code": product_code,
        "quantity": Decimal(quantity),
        "total_price": Decimal(total_price),
        "start_date": start,
        "end_date": end,
    }


VC_ELEMENT = "VC-1"


def estimate_version(
    contract: str,
    version_no: int,
    effective_date: date,
    *,
    scenarios: Sequence[tuple[Decimal, Decimal]],
    most_conservative: Decimal,
    constrained: Decimal,
    currency: str = "USD",
    unconstrained: Decimal | None = None,
) -> EstimateVersionInput:
    """An APPROVED ``EXPECTED_VALUE`` version of the contract's one ``VARIABLE_CONSIDERATION``
    element ``VC-1`` (``PERFORMANCE_INCENTIVE``, untargeted — allocation target ``CONTRACT``):
    ``scenarios`` = (amount, probability) pairs in currency units, the most conservative amount
    and the preparer's constrained amount K (S04-R-05, S04-R-07); versions after the first name
    their predecessor (S08-R-01)."""
    key = f"{contract}/{VC_ELEMENT}"
    return EstimateVersionInput(
        estimate_key=key,
        estimate_kind="VARIABLE_CONSIDERATION",
        element_code=VC_ELEMENT,
        method="EXPECTED_VALUE",
        vc_element_type="PERFORMANCE_INCENTIVE",
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key=None,
        version_key=f"{key}@v{version_no}",
        version_no=version_no,
        status="APPROVED",
        effective_date=effective_date,
        scenarios=tuple(
            {"outcome": f"S{index}", "amount": amount, "probability": probability}
            for index, (amount, probability) in enumerate(scenarios, start=1)
        ),
        parameters={},
        unconstrained_amount=unconstrained,
        most_conservative_amount=most_conservative,
        constrained_amount=constrained,
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency=currency,
        supersedes_version_key=None if version_no == 1 else f"{key}@v{version_no - 1}",
        judgement_key=None,
        content_sha256=ZERO_SHA256,
    )


def event(
    contract_key: str,
    stream_version: int,
    event_type: str,
    effective_date: date,
    payload: Mapping[str, object],
    *,
    record_seq: int | None = None,
    obligation_keys: Iterable[str] = (),
) -> EventInput:
    """An event with the CV-22 key and a record time at noon UTC of its effective date."""
    return EventInput(
        event_key=f"{contract_key}/EV-{stream_version:06d}",
        contract_key=contract_key,
        stream_version=stream_version,
        event_type=event_type,
        schema_version=1,
        effective_date=effective_date,
        recorded_at=datetime(
            effective_date.year, effective_date.month, effective_date.day, 12, tzinfo=UTC
        ),
        record_seq=stream_version if record_seq is None else record_seq,
        origin="API",
        is_manual=False,
        obligation_keys=tuple(obligation_keys),
        payload=payload,
        payload_sha256=sha256_hex(payload),
        idempotency_key=None,
        supersedes_event_key=None,
        modification_key=None,
        estimate_version_key=None,
        manual_adjustment_key=None,
    )


def minimal_contract(preset: str = "DEFAULT") -> InputBundle:
    """One entity, the ASC606 book, one product and one contract booked with one line."""
    calendar = default_entity()
    header = contract()
    line = booking_line()
    booked = event(
        header.external_id,
        1,
        "CONTRACT_BOOKED",
        header.inception_date,
        {"lines": [line]},
        obligation_keys=[str(line["obligation_key"])],
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset=preset,
        currencies=currencies("USD"),
        books=(book(preset=preset, entity=calendar),),
        entities=(calendar,),
        group=group((header,), products=(product(),)),
        contracts=(header,),
        events=(booked,),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )
