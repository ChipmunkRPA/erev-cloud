"""Worlds for the stage 07 opening-balance flows through stages 10, 13 and 14 (ENGINE_SPEC
S07-R-05, S07-R-08; ENGINE_SPEC_B S10-R-03, S14-R-26 rev 1.11; BUILD_SPEC ENB-9; lane ENG-C5).

CHK-121 (ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION): a 24-month subscription of 240,000.00
billed upfront on 1 January 2025 by an acquiree; the acquirer books the contract with its original
inception on 31 December 2025 (FY2025-P12 closed) and establishes the opening balances at that
cutover with reason ``BUSINESS_COMBINATION``: revenue 120,000.00, billed 240,000.00, remaining
allocation 120,000.00, fair value of the contract liability 90,000.00 for the IFRS15 book. Figures
derived with Fraction arithmetic in ``.run/eng-c5/derive.py``. Bundles come from
``support.bundles`` and ``support.cpc_worlds`` (DG-ENG-11); no database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BookOutput,
    EventInput,
    InputBundle,
    MappingRuleInput,
    PayableInput,
    ResolvedPolicyInput,
)
from support import bundles
from support.cpc_worlds import CPC_ACCOUNTS, PIT, line, product, ssp_book, template

__all__ = [
    "CONTRACT",
    "CUTOVER",
    "ENTITY",
    "INCEPTION",
    "OBLIGATION",
    "SUBJECT",
    "chk_121",
    "deposit_recompute",
    "journal",
]

CONTRACT = "C-ACQ-SUB"
ENTITY = bundles.ENTITY_CODE
OBLIGATION = "L1-SUB"
SUBJECT = f"{CONTRACT}/{OBLIGATION}"
INCEPTION = date(2025, 1, 1)
CUTOVER = date(2025, 12, 31)
END = date(2026, 12, 31)
RATABLE = template(
    "TPL-RATABLE",
    "TIME_ELAPSED",
    satisfaction_pattern="OVER_TIME",
    over_time_criterion="OT_A",
    ratable_convention="MONTHLY_EVEN",
)


def opening_payload(
    *,
    revenue_cum: str = "120000.00",
    billed_cum: str | None = "240000.00",
    remaining_allocation: str = "120000.00",
    fair_value: str | None = "90000.00",
    reason: str = "BUSINESS_COMBINATION",
) -> dict[str, object]:
    """The ``OPENING_BALANCE_ESTABLISHED`` payload of the key (04 §16.3); ``billed_cum`` None omits
    the optional member (S07-R-07 rev 1.18)."""
    row: dict[str, object] = {
        "obligation_key": OBLIGATION,
        "delivered_quantity_cum": Decimal("0"),
        "ssp_delivered_cum": Decimal("0"),
        "remaining_quantity": Decimal("1"),
        "remaining_ssp": Decimal("240000"),
        "revenue_cum": Decimal(revenue_cum),
        "catch_up_cum": Decimal("0.00"),
        "pre_standard_revenue_cum": Decimal("0.00"),
        "remaining_allocation": Decimal(remaining_allocation),
        "remaining_billing": Decimal("0.00"),
        "position_obligation": Decimal(revenue_cum),
        "netting_reclass_amount": Decimal("0.00"),
    }
    if billed_cum is not None:
        row["billed_cum"] = Decimal(billed_cum)
    payload: dict[str, object] = {"reason": reason, "cutover_date": CUTOVER, "obligations": [row]}
    if fair_value is not None:
        payload["fair_value_contract_liability"] = Decimal(fair_value)
    return payload


def chk_121(
    *,
    as_of: date = date(2026, 1, 31),
    states: Mapping[str, str] | None = None,
    books: Sequence[str] = ("ASC606", "IFRS15"),
    payload: Mapping[str, object] | None = None,
    extra: Sequence[EventInput] = (),
    policies: Mapping[str, str] | None = None,
    payables: Sequence[PayableInput] = (),
    accounts: Sequence[tuple[str, str | None, str]] = (),
) -> InputBundle:
    """The CHK-121 world computed at ``as_of`` (a COMMAND compute known at 23:00 UTC that day).
    ``payables`` adds consideration-payable promises to the contract (JET-14) and ``accounts`` adds
    mapping rules (role, purpose, account code) to every book, for example ``CPC_ACCOUNTS``.
    Periods FY2025-P01 to FY2026-P12 for both books; the periods after ``as_of`` are future,
    FY2025-P12 is closed unless ``states`` says otherwise; the contract is booked and activated
    on the cutover day with its original inception and the opening balances are established the
    same day (the key's timeline). ``policies`` replaces the value of every row of the named
    policy codes per book, whatever their scope (for example ``{"billing.posting": "ENGINE"}``,
    POL-004, PERIOD rows)."""
    lines = [line(OBLIGATION, "SUB-24M", "1", "240000.00", start=INCEPTION, end=END)]
    events = [
        bundles.event(
            CONTRACT, 1, "CONTRACT_BOOKED", CUTOVER, {"lines": lines}, obligation_keys=[OBLIGATION]
        ),
        bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", CUTOVER, {"checklist": {}}),
        bundles.event(
            CONTRACT,
            3,
            "OPENING_BALANCE_ESTABLISHED",
            CUTOVER,
            dict(payload) if payload is not None else opening_payload(),
            obligation_keys=[OBLIGATION],
        ),
        *extra,
    ]
    future = {
        f"FY{year}-P{month:02d}": "future"
        for year in (2025, 2026)
        for month in range(1, 13)
        if date(year, month, 1) > as_of
    }
    calendar = bundles.entity(
        start=INCEPTION,
        months=24,
        books=books,
        states={**future, "FY2025-P12": "closed", **(states or {})},
    )
    book_inputs = []
    for code in books:
        base = bundles.book(code, entity=calendar)
        overrides = dict(policies or {})
        rows = tuple(
            dataclasses.replace(policy, value="MONTHLY_EVEN")
            if policy.code == "recognition.time_convention" and policy.scope == "GROUP"
            else dataclasses.replace(policy, value=overrides[policy.code])
            if policy.code in overrides
            else policy
            for policy in base.policies
        )
        base = dataclasses.replace(base, policies=rows)
        if accounts:
            mapping = base.account_mapping
            rules = tuple(
                sorted(
                    (
                        *mapping.rules,
                        *(
                            MappingRuleInput(role, purpose, None, None, None, None, code, {}, 0, 0)
                            for role, purpose, code in accounts
                        ),
                    ),
                    key=lambda rule: (
                        rule.account_role,
                        rule.clearing_purpose or "",
                        rule.account_code,
                    ),
                )
            )
            base = dataclasses.replace(
                base, account_mapping=dataclasses.replace(mapping, rules=rules)
            )
        book_inputs.append(base)
    contract = dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION, consideration_payable=tuple(payables)),
        judgements=(),
        modifications=(),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(as_of.year, as_of.month, as_of.day, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=tuple(book_inputs),
        entities=(calendar,),
        group=bundles.group((contract,), products=(product("SUB-24M", "TPL-RATABLE"),)),
        contracts=(contract,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(ssp_book({"SUB-24M": "240000"}),),
        pob_template_versions=(RATABLE,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def journal(book: BookOutput, *roles: str) -> list[tuple[str, str, str, str, str, int, str | None]]:
    """(posting period, entry kind, class, role, side, txn, origin) of the lines of ``roles``
    (every role when none is named), sorted."""
    return sorted(
        (
            intent.posting_period_key,
            intent.entry_kind,
            intent.posting_class,
            item.account_role,
            item.side,
            item.amount_txn,
            intent.origin_period_key or "",
        )
        for intent in book.posting_intents
        for item in intent.lines
        if not roles or item.account_role in roles
    )


def deposit_recompute(
    *,
    as_of: date = date(2026, 7, 31),
    cutover: date = date(2026, 6, 30),
    deposit_member: str | None = "0.00",
) -> InputBundle:
    """ONB-DIFF-ROLES deposits: goods of 1,200.00 booked 1 January 2026 while ``NOT_A_CONTRACT``
    (collectibility not probable), 1,200.00 received 15 February (a deposit, JET-01b receipt), and
    ``OPENING_BALANCE_ESTABLISHED`` (SYSTEM_ONBOARDING) at the ``cutover`` (30 June 2026, a period
    end) under ``RECOMPUTE_FROM_INCEPTION`` with revenue 0, billing 0 and the optional payload
    member ``deposit_liability`` = ``deposit_member`` (an explicit 0; None omits it, S07-R-07 rev
    1.13): the recomputed ``deposit_received_cum`` at the cutover (1,200.00) less the imported 0 is
    the JET-01b receipt difference posted once at the cutover. FY2026-P01 to P06 closed, later
    periods open through ``as_of``."""
    from erev_engine.bundle import JudgementInput

    contract = "C-DEP-ONB"
    goods = line("L1-GOODS", "GOODS", "1", "1200.00", start=date(2026, 1, 1), end=date(2026, 1, 1))
    row: dict[str, object] = {
        "obligation_key": "L1-GOODS",
        "delivered_quantity_cum": Decimal("0"),
        "ssp_delivered_cum": Decimal("0"),
        "remaining_quantity": Decimal("1"),
        "remaining_ssp": Decimal("1200"),
        "revenue_cum": Decimal("0.00"),
        "billed_cum": Decimal("0.00"),
        "catch_up_cum": Decimal("0.00"),
        "pre_standard_revenue_cum": Decimal("0.00"),
        "remaining_allocation": Decimal("1200.00"),
        "remaining_billing": Decimal("1200.00"),
        "position_obligation": Decimal("0.00"),
        "netting_reclass_amount": Decimal("0.00"),
    }
    if deposit_member is not None:
        row["deposit_liability"] = Decimal(deposit_member)
    events = [
        bundles.event(
            contract,
            1,
            "CONTRACT_BOOKED",
            date(2026, 1, 1),
            {"lines": [goods]},
            obligation_keys=["L1-GOODS"],
        ),
        bundles.event(
            contract,
            2,
            "COLLECTIBILITY_ASSESSED",
            date(2026, 1, 1),
            {"book": "ASC606", "is_probable": False, "judgement_record_id": "J-2"},
        ),
        bundles.event(contract, 3, "CONTRACT_ACTIVATED", date(2026, 1, 1), {"checklist": {}}),
        bundles.event(
            contract,
            4,
            "PAYMENT_RECEIVED",
            date(2026, 2, 15),
            {
                "receipt_reference": "R-4",
                "amount": Decimal("1200.00"),
                "receipt_date": date(2026, 2, 15),
            },
        ),
        bundles.event(
            contract,
            5,
            "OPENING_BALANCE_ESTABLISHED",
            cutover,
            {"reason": "SYSTEM_ONBOARDING", "cutover_date": cutover, "obligations": [row]},
            obligation_keys=["L1-GOODS"],
        ),
    ]
    states = {f"FY2026-P{m:02d}": "closed" for m in range(1, 7)}
    states.update({f"FY2026-P{m:02d}": "future" for m in range(1, 13) if date(2026, m, 1) > as_of})
    calendar = bundles.entity(start=date(2026, 1, 1), months=12, books=("ASC606",), states=states)
    base = bundles.book("ASC606", entity=calendar)
    mapping = base.account_mapping
    rules = tuple(
        sorted(
            (
                *mapping.rules,
                *(
                    MappingRuleInput(role, purpose, None, None, None, None, code, {}, 0, 0)
                    for role, purpose, code in CPC_ACCOUNTS
                ),
            ),
            key=lambda rule: (rule.account_role, rule.clearing_purpose or "", rule.account_code),
        )
    )
    base = dataclasses.replace(base, account_mapping=dataclasses.replace(mapping, rules=rules))
    header = dataclasses.replace(
        bundles.contract(contract, inception=date(2026, 1, 1)),
        judgements=(
            JudgementInput(
                "J-NAC", "NOT_A_CONTRACT", contract, None, {"consideration_nonrefundable": "false"}
            ),
        ),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(as_of.year, as_of.month, as_of.day, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(base,),
        entities=(calendar,),
        group=bundles.group((header,), products=(product("GOODS", "TPL-PIT"),)),
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(ssp_book({"GOODS": "1200"}),),
        pob_template_versions=(PIT,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


COLLIDING = ("K/A", "K%2FA")  # CV-21: "K/A" encodes to "K%2FA", the raw id of the second contract


def two_contracts(*, as_of: date = date(2026, 1, 31)) -> InputBundle:
    """Two CHK-121-shaped contracts whose ids collide under CV-21 encoding (Codex C5-PH3-R1):
    ``K/A`` onboarded under ``RECOMPUTE_FROM_INCEPTION`` and ``K%2FA`` under
    ``OPENING_BALANCES_AT_CUTOVER`` (CONTRACT-scope ``onboarding.method`` rows), each with one
    24-month ratable obligation of 240,000.00 from ``INCEPTION``, booked, activated and opened at
    ``CUTOVER`` with the key's payload (a valid inception / opening chronology). ASC606 only;
    FY2025-P12 closed."""
    events: list[EventInput] = []
    for contract in COLLIDING:
        lines = [line(OBLIGATION, "SUB-24M", "1", "240000.00", start=INCEPTION, end=END)]
        events += [
            bundles.event(
                contract,
                1,
                "CONTRACT_BOOKED",
                CUTOVER,
                {"lines": lines},
                obligation_keys=[OBLIGATION],
            ),
            bundles.event(contract, 2, "CONTRACT_ACTIVATED", CUTOVER, {"checklist": {}}),
            bundles.event(
                contract,
                3,
                "OPENING_BALANCE_ESTABLISHED",
                CUTOVER,
                opening_payload(),
                obligation_keys=[OBLIGATION],
            ),
        ]
    future = {
        f"FY{year}-P{month:02d}": "future"
        for year in (2025, 2026)
        for month in range(1, 13)
        if date(year, month, 1) > as_of
    }
    calendar = bundles.entity(
        start=INCEPTION, months=24, books=("ASC606",), states={**future, "FY2025-P12": "closed"}
    )
    base = bundles.book("ASC606", entity=calendar)
    rows = [
        dataclasses.replace(policy, value="MONTHLY_EVEN")
        if policy.code == "recognition.time_convention" and policy.scope == "GROUP"
        else policy
        for policy in base.policies
    ]
    for contract, method in zip(
        COLLIDING, ("RECOMPUTE_FROM_INCEPTION", "OPENING_BALANCES_AT_CUTOVER"), strict=True
    ):
        rows.append(
            ResolvedPolicyInput(
                "onboarding.method",
                "CONTRACT",
                contract,
                method,
                "C",
                f"{contract}/policy_overrides/onboarding.method",
                "K",
            )
        )
    book = dataclasses.replace(
        base, policies=tuple(sorted(rows, key=lambda p: (p.code, p.scope, p.subject_key)))
    )
    contracts = tuple(
        sorted(
            (
                dataclasses.replace(
                    bundles.contract(contract, inception=INCEPTION),
                    judgements=(),
                    modifications=(),
                )
                for contract in COLLIDING
            ),
            key=lambda item: item.external_id,
        )
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(as_of.year, as_of.month, as_of.day, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=bundles.group(contracts, products=(product("SUB-24M", "TPL-RATABLE"),)),
        contracts=contracts,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(ssp_book({"SUB-24M": "240000"}),),
        pob_template_versions=(RATABLE,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )
