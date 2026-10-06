"""CTR-17 Modifications — CPU witnesses (design note §h; D-98 140): the routing facts derived from
a stored impact preview (Q-5), the candidate ``CONTRACT_AMENDED`` built from a T-CON-06 row, the
engine's proposal read back from the output bundle, the bundle builder's native-versus-legacy key
rule (Q-3) and the registry state. No database."""

from __future__ import annotations

import dataclasses
import inspect
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.api.v1 import modifications as modifications_api
from erev_api.approvals import subjects
from erev_api.approvals.subjects import (
    MODIFICATION_CATCH_UP_FLAG,
    MODIFICATION_TP_CHANGE_FLAG,
    PENDING_SUBJECTS,
    SUBJECTS,
)
from erev_api.domain.contracts import bundles, modifications
from erev_api.enums import ApprovalSubjectType, ContractEventType, ModificationTreatment
from erev_api.events.payloads import ContractAmendedV1
from erev_api.problems import Problem
from erev_api.schemas.modifications import ModificationCreateIn
from erev_engine.bundle import FxRateInput, ProposalOut
from erev_engine.stages.s06_modifications import subscriptions


def _money(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def _summary(*, before: str, after: str, catch_up: str, currency: str = "USD") -> dict[str, Any]:
    return {
        "transaction_price_before": _money(before, currency),
        "transaction_price_after": _money(after, currency),
        "catch_up_total": _money(catch_up, currency),
    }


def _fx(
    *, currency: str, functional: str, to_functional: str | None, to_threshold: str | None
) -> dict[str, Any]:
    """A retained ``fx_basis`` as ``run_preview`` stores it (04 §16.14); None = explicit absence."""

    def entry(quote: str, rate: str | None) -> dict[str, Any]:
        found: dict[str, Any] = {
            "base": currency,
            "quote": quote,
            "rate": rate,
            "rate_type": "spot",
        }
        if rate is None:
            found["missing"] = {"rule": "S12-R-01"}
        return found

    return {
        "transaction_currency": currency,
        "functional_currency": functional,
        "threshold_currency": "USD",
        "effective_date": "2026-09-16",
        "to_functional": entry(functional, to_functional),
        "to_threshold": entry("USD", to_threshold),
    }


def test_q5_routing_facts_thresholds_and_basis() -> None:
    """PRD §2.5 second step: |catch-up| ≥ USD 50,000.00 and |ΔTP| ≥ USD 250,000.00 as flags;
    ``amount_functional`` = |ΔTP| in the functional currency (rate 1 when equal; D-98 140 Q-5)."""
    usd = _fx(currency="USD", functional="USD", to_functional="1", to_threshold="1")
    amount, flags, basis = modifications.routing_facts(
        _summary(before="240000.00", after="300000.00", catch_up="0.00"),
        currency="USD",
        functional_currency="USD",
        fx_basis=usd,
    )
    assert amount == (Decimal("60000.00"), "USD")
    assert flags == frozenset()
    assert basis == modifications.AMOUNT_BASIS_FUNCTIONAL
    amount, flags, basis = modifications.routing_facts(
        _summary(before="1000000.00", after="1300000.00", catch_up="-50000.00"),
        currency="USD",
        functional_currency="USD",
        fx_basis=usd,
    )
    assert amount == (Decimal("300000.00"), "USD")
    assert flags == frozenset({MODIFICATION_CATCH_UP_FLAG, MODIFICATION_TP_CHANGE_FLAG})


def test_routing_fx_1_converts_at_the_retained_spot_rate_and_keeps_usd_distinct() -> None:
    """D-98 140-A5 ROUTING-FX-1 (Codex 1713): EUR 240,000.00 of ΔTP at a retained EUR→USD 1.11 is
    USD 266,400.00 — the TP-change flag fires although the raw amount is below 250,000; the
    functional amount converts at the retained EUR→functional rate; for a GBP-functional entity
    the USD threshold stays USD (the functional amount is GBP)."""
    amount, flags, basis = modifications.routing_facts(
        _summary(before="100.00", after="240100.00", catch_up="45000.00", currency="EUR"),
        currency="EUR",
        functional_currency="USD",
        fx_basis=_fx(currency="EUR", functional="USD", to_functional="1.11", to_threshold="1.11"),
    )
    assert amount == (Decimal("266400.00"), "USD")
    assert flags == frozenset({MODIFICATION_TP_CHANGE_FLAG})  # 45,000 × 1.11 = 49,950 < 50,000
    assert basis == modifications.AMOUNT_BASIS_RETAINED
    amount, flags, basis = modifications.routing_facts(
        _summary(before="0.00", after="200000.00", catch_up="46000.00", currency="EUR"),
        currency="EUR",
        functional_currency="GBP",
        fx_basis=_fx(currency="EUR", functional="GBP", to_functional="0.85", to_threshold="1.11"),
    )
    assert amount == (Decimal("170000.00"), "GBP")  # 200,000 × 0.85, in the functional currency
    assert flags == frozenset({MODIFICATION_CATCH_UP_FLAG})  # 46,000 × 1.11 = 51,060 ≥ 50,000
    # rounding at the functional minor unit, half up (S12-R-02)
    amount, _, _ = modifications.routing_facts(
        _summary(before="0.00", after="1000.005", catch_up="0.00", currency="EUR"),
        currency="EUR",
        functional_currency="JPY",
        fx_basis=_fx(currency="EUR", functional="JPY", to_functional="160.5", to_threshold="1.11"),
    )
    assert amount == (Decimal("160501"), "JPY")


def test_routing_fx_1_refuses_a_retained_absence_and_a_currency_mismatch() -> None:
    """Both sides authored: no retained EUR→USD rate → 422 REQ-PLT-015 naming the pair and the
    date (never a foreign numeric amount, never None); a summary in another currency than the
    row → 422 REQ-PLT-015 currency mismatch."""
    with pytest.raises(Problem) as missing:
        modifications.routing_facts(
            _summary(before="0.00", after="1000.00", catch_up="0.00", currency="EUR"),
            currency="EUR",
            functional_currency="USD",
            fx_basis=_fx(currency="EUR", functional="USD", to_functional=None, to_threshold=None),
        )
    (error,) = missing.value.errors
    assert (error.rule_id, error.field) == ("REQ-PLT-015", "impact_preview")
    assert "no spot rate from EUR to USD on 2026-09-16" in error.message
    with pytest.raises(Problem) as mismatch:
        modifications.routing_facts(
            _summary(before="0.00", after="1000.00", catch_up="0.00", currency="EUR"),
            currency="USD",
            functional_currency="USD",
            fx_basis=_fx(currency="USD", functional="USD", to_functional="1", to_threshold="1"),
        )
    (error,) = mismatch.value.errors
    assert error.rule_id == "REQ-PLT-015" and "EUR" in error.message and "USD" in error.message
    # a basis retained for another pair does not serve
    with pytest.raises(Problem):
        modifications.routing_facts(
            _summary(before="0.00", after="1000.00", catch_up="0.00", currency="EUR"),
            currency="EUR",
            functional_currency="USD",
            fx_basis=_fx(currency="GBP", functional="USD", to_functional="1.3", to_threshold="1.3"),
        )


def _rate(base: str, quote: str, on: str, rate: str, *, version: str = "FX-2026/1") -> FxRateInput:
    return FxRateInput(
        rate_key=f"{version}/spot/{base}/{quote}/{on}",
        version_key=version,
        rate_type="spot",
        base_currency=base,
        quote_currency=quote,
        effective_date=date.fromisoformat(on),
        period_key=None,
        rate=Decimal(rate),
    )


def test_spot_basis_selects_the_latest_spot_on_or_before_and_marks_absence() -> None:
    """The retained basis uses the engine's S12-R-01 selection (``Rates.spot``): the latest spot
    on or before the modification date; rate 1 for equal currencies; an explicit absence
    otherwise (no inverse-pair or later-dated rate is silently used)."""
    rows = (
        _rate("EUR", "USD", "2026-09-01", "1.10"),
        _rate("EUR", "USD", "2026-09-15", "1.11"),
        _rate("EUR", "USD", "2026-09-17", "1.12"),
        _rate("USD", "GBP", "2026-09-10", "0.78"),
    )
    chosen = modifications.spot_basis(rows, base="EUR", quote="USD", on=date(2026, 9, 16))
    assert (chosen["rate"], chosen["rate_key"]) == ("1.11", "FX-2026/1/spot/EUR/USD/2026-09-15")
    assert (
        modifications.spot_basis(rows, base="USD", quote="USD", on=date(2026, 9, 16))["rate"] == "1"
    )
    absent = modifications.spot_basis(rows, base="GBP", quote="USD", on=date(2026, 9, 16))
    assert absent["rate"] is None and absent["missing"]["rule"] == "S12-R-01"
    early = modifications.spot_basis(rows, base="EUR", quote="USD", on=date(2026, 8, 31))
    assert early["rate"] is None


def test_judgement_1_override_applies_only_to_this_rows_reviewed_record() -> None:
    """D-98 140-A5 JUDGEMENT-1: two modifications A and B of one contract — B's reviewed
    MODIFICATION_TREATMENT_OVERRIDE does not satisfy A's departure; A's own does; a record on
    another contract, another subject type, another topic or not REVIEWED does not."""
    contract = uuid4()
    a = {"id": uuid4(), "contract_id": contract}
    b = {"id": uuid4(), "contract_id": contract}

    def record(**overrides: Any) -> dict[str, Any]:
        found: dict[str, Any] = {
            "topic": "MODIFICATION_TREATMENT_OVERRIDE",
            "status": "REVIEWED",
            "subject_type": "modification",
            "subject_id": a["id"],
            "contract_id": contract,
        }
        found.update(overrides)
        return found

    assert modifications.override_applies(record(), a)
    assert not modifications.override_applies(record(), b)  # wrong row, same contract
    assert not modifications.override_applies(record(subject_id=b["id"]), a)
    assert not modifications.override_applies(record(contract_id=uuid4()), a)
    assert not modifications.override_applies(record(contract_id=None), a)
    assert not modifications.override_applies(
        record(subject_type="contract", subject_id=contract), a
    )
    assert not modifications.override_applies(record(status="DRAFT"), a)
    assert not modifications.override_applies(record(topic="POB_DISTINCTNESS"), a)


def test_domain_r1_preview_basis_strips_only_the_preview_hashes() -> None:
    """The retained ``basis_sha256`` is over the §16.10 content without ``impact_preview_sha256``:
    a later preview of the pair's other row leaves it equal; any member head, authored member or
    judgement hash change moves it (D-98 140-A5 DOMAIN-R1)."""
    content = {
        "object_type": "modification",
        "regroup_id": None,
        "modifications": [
            {
                "modification_id": "m-1",
                "lines": [{"obligation_key": "O2", "action": "ADD"}],
                "judgement_content_sha256": None,
                "impact_preview_sha256": "a" * 64,
                "contract": {"combination_group_id": "g", "head_stream_version": 4},
                "members": [
                    {"contract_id": "A", "combination_group_id": "g", "head_stream_version": 4},
                    {"contract_id": "B", "combination_group_id": "g", "head_stream_version": 2},
                ],
            }
        ],
    }
    basis = modifications.strip_preview_hashes(content)
    assert "impact_preview_sha256" not in basis["modifications"][0]
    assert basis["modifications"][0]["members"][1]["head_stream_version"] == 2
    other_preview = {
        **content,
        "modifications": [{**content["modifications"][0], "impact_preview_sha256": "b" * 64}],
    }
    assert modifications.strip_preview_hashes(other_preview) == basis
    moved_b = {
        **content,
        "modifications": [
            {
                **content["modifications"][0],
                "members": [
                    content["modifications"][0]["members"][0],
                    {"contract_id": "B", "combination_group_id": "g", "head_stream_version": 3},
                ],
            }
        ],
    }
    assert modifications.strip_preview_hashes(moved_b) != basis
    assert content["modifications"][0]["impact_preview_sha256"] == "a" * 64  # input untouched


def test_domain_r2_pending_rows_lines_join_the_builder_without_an_event() -> None:
    """A classification's bundle collects the pending row's ADD lines (products, entities,
    policies) without an applying event; a row whose candidate event is pending contributes
    through the event instead (no double count); rows of other contracts are ignored."""
    contract_a, contract_b = uuid4(), uuid4()
    rows = [
        {
            "id": uuid4(),
            "contract_id": contract_a,
            "lines": [{"obligation_key": "O4", "action": "ADD", "product_code": "AVM-ONB"}],
        },
        {
            "id": uuid4(),
            "contract_id": contract_b,
            "lines": [{"obligation_key": "X", "action": "ADD"}],
        },
        {
            "id": uuid4(),
            "contract_id": contract_a,
            "lines": [{"obligation_key": "O5", "action": "ADD"}],
        },
    ]
    lines = bundles.pending_lines(rows, {contract_a: "SF-A"}, applied={str(rows[2]["id"])})
    assert lines == [("SF-A", {"obligation_key": "O4", "action": "ADD", "product_code": "AVM-ONB"})]


def test_q3_named_modification_ids_split_native_and_legacy() -> None:
    """Every named id is resolved before the native / legacy decision: a legacy template
    treatment's id is returned separately so the builder looks it up too and refuses a legacy
    event over an EXISTING native row (D-98 140-A5 Q3); a plain native id stays native."""
    native_id, legacy_id = uuid4(), uuid4()
    stored = [
        {
            "event_type": "CONTRACT_AMENDED",
            "payload": {"modification_id": str(native_id), "treatments": {"O1": "PROSPECTIVE"}},
        },
        {
            "event_type": "CONTRACT_AMENDED",
            "payload": {
                "modification_id": str(legacy_id),
                "treatments": {"O1": next(iter(bundles.TEMPLATE_MODES))},  # a legacy template
            },
        },
        {"event_type": "CONTRACT_BOOKED", "payload": {"modification_id": str(uuid4())}},
    ]
    native, legacy = bundles.named_modification_ids(stored, ())
    assert (native, legacy) == (frozenset({native_id}), frozenset({legacy_id}))


def test_rowversion_1_updates_advance_the_row_version_in_the_same_statement() -> None:
    """Every UPDATE of the row carries ``row_version = row_version + 1`` (IM-S has no tg_touch);
    the INSERT stamps do not (server default 1)."""
    uow = dataclasses.make_dataclass("Uow", ["principal", "now"])(
        principal=dataclasses.make_dataclass("P", ["id", "kind"])(
            id=uuid4(), kind=dataclasses.make_dataclass("K", ["value"])(value="USER")
        ),
        now="2026-09-21T10:00:00+00:00",
    )
    bumped = modifications._bump(uow)  # type: ignore[arg-type]
    assert str(bumped["row_version"]) == "erev.modification.row_version + :row_version_1"
    assert set(bumped) == {"updated_at", "updated_by", "updated_by_kind", "row_version"}
    assert "row_version" not in modifications._stamps(uow)  # type: ignore[arg-type]


def test_a4_list_item_reads_catch_up_total_from_the_retained_preview() -> None:
    """``impact_summary.catch_up_total`` of a list item is the retained preview's, null without."""
    stored = {"summary": {"catch_up_total": {"amount": "1250.00", "currency": "USD"}}}
    assert modifications._catch_up_total(stored) == {"amount": "1250.00", "currency": "USD"}
    assert modifications._catch_up_total(None) is None
    assert modifications._catch_up_total({"provenance": {}}) is None


def test_a4_etag_is_the_row_version() -> None:
    """API-C-08: ``GET /modifications/{id}`` and the row-answering commands carry ``"r<n>"``."""
    out = dataclasses.make_dataclass("Out", ["row_version"])(row_version=7)
    assert modifications_api._etag(out) == '"r7"'  # type: ignore[arg-type]


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": UUID("00000000-0000-0000-0000-000000000123"),
        "modification_no": "MOD-000001",
        "effective_date": date(2026, 9, 16),
        "lines": [
            {
                "obligation_key": "O2",
                "action": "CHANGE",
                "quantity_delta": "50",
                "consideration_delta": {"amount": "60000.00", "currency": "USD"},
                "start_date": "2026-09-16",
                "end_date": "2027-12-31",
            },
            {"obligation_key": "O4", "action": "ADD", "product_code": "AVM-SEAT-MO"},
        ],
        "questionnaire": {"price_change_settlement": "FUTURE_PRICING"},
        "chosen_treatments": {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"},
        "ssp_basis": {"O2": {"ssp_book_version_id": None, "is_override": False}},
        "noncash_consideration": None,
        "consideration_payable": None,
        "scope_605_35": None,
        "row_version": 3,
    }
    row.update(overrides)
    return row


def test_candidate_amended_event_copies_the_row() -> None:
    """The ``CONTRACT_AMENDED`` of a row (04 §16.3): treatments = chosen, lines and ssp_basis
    copied,
    ``modification_id`` = the row id, the ADD lines as obligation keys; the event names its row."""
    event = modifications._amended_event(_row(), approval_request_id=None)
    assert event.event_type is ContractEventType.CONTRACT_AMENDED
    assert event.effective_date == date(2026, 9, 16)
    assert event.obligation_keys == ("O4",)
    assert event.modification_id == UUID("00000000-0000-0000-0000-000000000123")
    payload = event.payload
    assert isinstance(payload, ContractAmendedV1)
    assert payload.modification_id == event.modification_id
    assert payload.treatments == {
        "O1": ModificationTreatment.PROSPECTIVE,
        "O2": ModificationTreatment.PROSPECTIVE,
    }
    assert [line.obligation_key for line in payload.lines] == ["O2", "O4"]
    assert payload.price_change_settlement == "FUTURE_PRICING"


def _output(*proposals: ProposalOut) -> Any:
    book = dataclasses.make_dataclass("Book", [("proposals", tuple)])(tuple(proposals))
    return dataclasses.make_dataclass("Output", [("books", tuple)])((book,))


def test_proposal_is_read_from_the_output_bundle_by_row_id() -> None:
    """Stage 13 proposes for a bundle modification no event applies (S06-R-01); the proposal for the
    row is found by its key — the row id, what every payload names — and other kinds are ignored."""
    row = _row()
    wanted = ProposalOut(
        kind="MODIFICATION_TREATMENT",
        subject_key=f"SF-ORD-10002/{row['id']}",
        summary="PROSPECTIVE",
        treatments={"O2": "PROSPECTIVE", "O1": "PROSPECTIVE"},
        detail={"modification_key": str(row["id"]), "route": "S06-R-05"},
    )
    other = ProposalOut(
        kind="DISCOUNT_EXCEPTION", subject_key="x", summary=None, treatments={}, detail={}
    )
    treatments, summary, detail = modifications._proposal(_output(other, wanted), row)
    assert treatments == {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"}
    assert summary == "PROSPECTIVE" and detail["route"] == "S06-R-05"
    with pytest.raises(Problem) as refused:
        modifications._proposal(_output(other), row)
    assert refused.value.slug == "validation-failed"
    assert refused.value.errors[0].rule_id == modifications.RULE_CLASSIFIED


def test_q3_native_and_legacy_keys_never_collide() -> None:
    """The bundle builder keys a native ``CONTRACT_AMENDED`` by the row id it names and keeps the
    legacy projection's key; a legacy template naming a native row is refused by name."""
    native = frozenset({"11111111-1111-1111-1111-111111111111"})
    payload_native = {
        "modification_id": "11111111-1111-1111-1111-111111111111",
        "treatments": {"O1": "PROSPECTIVE"},
    }
    payload_legacy = {
        "modification_id": "22222222-2222-2222-2222-222222222222",
        "treatments": {"O1": "LEGACY_PROSPECTIVE"},
    }
    key = bundles._event_modification_key("CONTRACT_AMENDED", payload_native, native, event="E1")
    assert key == "11111111-1111-1111-1111-111111111111"
    assert (
        bundles._event_modification_key("CONTRACT_AMENDED", payload_legacy, native, event="E2")
        == "22222222-2222-2222-2222-222222222222"
    )
    assert (
        bundles._event_modification_key("DELIVERY_RECORDED", payload_native, native, event="E3")
        is None
    )
    unknown = {**payload_native, "modification_id": str(uuid4())}
    assert bundles._event_modification_key("CONTRACT_AMENDED", unknown, native, event="E4") is None
    legacy_on_native = {**payload_legacy, "modification_id": next(iter(native))}
    with pytest.raises(ValueError, match="D-98 140 Q-3"):
        bundles._event_modification_key("CONTRACT_AMENDED", legacy_on_native, native, event="E5")


def test_native_input_carries_the_row_as_the_engine_object() -> None:
    row = _row(
        kind="UPGRADE",
        status="DRAFT",
        template_mode=None,
        reference="CR-MARROWBY-2026-09",
        price_change_amount=None,
        currency="USD",
        proposed_treatments={},
        treatment_summary=None,
        judgement_record_id=None,
        content_sha256=None,
    )
    item = bundles._native_input(row, {}, {})
    assert item.modification_key == str(row["id"])
    assert item.kind == "UPGRADE" and item.status == "DRAFT" and item.currency == "USD"
    assert item.chosen_treatments == {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"}
    assert item.ssp_basis == {
        "O2": {"is_override": "false", "justification": "", "ssp_version_key": ""}
    }
    assert item.lines[1]["action"] == "ADD"
    assert item.noncash_consideration is None and item.consideration_payable is None


def test_merged_modifications_refuse_a_duplicate_key() -> None:
    a = bundles._native_input(
        _row(
            kind="UPGRADE",
            status="APPLIED",
            template_mode=None,
            reference=None,
            price_change_amount=None,
            currency="USD",
            proposed_treatments={},
            treatment_summary=None,
            judgement_record_id=None,
            content_sha256=None,
        ),
        {},
        {},
    )
    assert bundles._merged_modifications((), (a,)) == (a,)
    with pytest.raises(ValueError, match="D-98 140 Q-3"):
        bundles._merged_modifications((a,), (a,))


def test_authored_values_are_json_safe() -> None:
    body = ModificationCreateIn.model_validate(
        {
            "effective_date": "2026-09-16",
            "kind": "UPGRADE",
            "reference": "CR-MARROWBY-2026-09",
            "lines": [
                {
                    "obligation_key": "O2",
                    "action": "CHANGE",
                    "quantity_delta": "50",
                    "consideration_delta": {"amount": "60000.00", "currency": "USD"},
                }
            ],
            "questionnaire": {"O2": {"added_goods_distinct": True}},
            "price_change_amount": "0.00",
            "chosen_treatments": {"O2": "PROSPECTIVE"},
        }
    )
    values = modifications._authored_values(body)
    assert values["kind"] == "UPGRADE"
    assert values["lines"][0]["consideration_delta"] == {"amount": "60000.00", "currency": "USD"}
    assert values["chosen_treatments"] == {"O2": "PROSPECTIVE"}
    assert values["price_change_amount"] == Decimal("0.00")
    assert "noncash_consideration" not in values  # None members are left to the stored value


def test_modification_subject_is_registered_and_no_longer_pending() -> None:
    spec = SUBJECTS[ApprovalSubjectType.MODIFICATION]
    assert spec.table == "modification" and spec.revenue_affecting
    assert spec.required_permission == "modification.approve"
    assert spec.second_step_flags == frozenset(
        {MODIFICATION_CATCH_UP_FLAG, MODIFICATION_TP_CHANGE_FLAG}
    )
    assert spec.second_step_role == subjects.CONTROLLER_ROLE
    assert "MODIFICATION" not in {name for name, _ in PENDING_SUBJECTS}
    assert spec.link_path is not None
    assert spec.link_path(UUID(int=7)).startswith("/modifications/")


def test_content_members_exclude_decision_derived_fields() -> None:
    members = set(subjects.MODIFICATION_CONTENT_MEMBERS)
    assert {
        "lines",
        "questionnaire",
        "chosen_treatments",
        "impact_preview_sha256",
        "regroup_id",
    } <= members
    assert members.isdisjoint({"status", "approval_request_id", "applied_event_id", "updated_at"})


# --- D-98 140-A6 (Codex production-20260921-1727 / 1733) CPU witnesses ---------------------------


def _native_row(**overrides: Any) -> dict[str, Any]:
    row = _row(
        modification_no="MOD-000009",
        lines=[
            {
                "obligation_key": "O2",
                "action": "ADD",
                "product_code": "AVM-SEAT-MO",
                "quantity_delta": "775",
                "consideration_delta": {"amount": "60000.00", "currency": "USD"},
                "start_date": "2026-09-16",
                "end_date": "2027-12-31",
            }
        ],
        chosen_treatments={"O2": "PROSPECTIVE"},
        proposed_treatments={"O2": "PROSPECTIVE"},
        contract_id=uuid4(),
        kind="UPGRADE",
        questionnaire={},  # no price_change_settlement (the _row default names one)
        template_mode=None,
        status="DRAFT",
        reference=None,
        price_change_amount=None,
        currency="USD",
        treatment_summary="PROSPECTIVE",
        judgement_record_id=None,
        content_sha256=None,
        effective_date=date(2026, 9, 16),
    )
    row.update(overrides)
    return row


def test_native_money_1_native_line_money_is_normalised_and_currency_checked() -> None:
    """CTR17-NATIVE-MONEY-1: the row's ``consideration_delta`` is an API-S-Money object; the
    bundle adapter hands the engine its amount (``payload_fraction`` reads a scalar), exact value
    kept; a line in another currency is refused by name, never retagged. Fail-first: the previous
    adapter copied the Money object."""
    native = bundles._native_input(_native_row(), {}, {})
    (line,) = native.lines
    assert line["consideration_delta"] == "60000.00"
    assert line["quantity_delta"] == "775" and line["obligation_key"] == "O2"
    foreign = _native_row()
    foreign["lines"][0]["consideration_delta"] = {"amount": "60000.00", "currency": "EUR"}
    with pytest.raises(ValueError, match="EUR, the modification is in USD"):
        bundles._native_input(foreign, {}, {})


def test_separate_choice_1_mode_is_read_from_the_chosen_treatments_both_directions() -> None:
    """CTR17-SEPARATE-CHOICE-1: proposal SEPARATE + chosen PROSPECTIVE → the amendment path;
    proposal PROSPECTIVE + chosen SEPARATE → the booking path; the proposal summary never
    decides."""
    departed_to_amendment = _native_row(
        proposed_treatments={"O2": "SEPARATE_CONTRACT"},
        chosen_treatments={"O2": "PROSPECTIVE"},
        treatment_summary="SEPARATE_CONTRACT",
    )
    assert modifications.separate_choice(departed_to_amendment) is False
    departed_to_booking = _native_row(
        proposed_treatments={"O2": "PROSPECTIVE"},
        chosen_treatments={"O2": "SEPARATE_CONTRACT"},
        treatment_summary="PROSPECTIVE",
    )
    assert modifications.separate_choice(departed_to_booking) is True
    assert modifications.separate_errors(departed_to_booking) == []
    assert modifications.separate_choice(_native_row(chosen_treatments={})) is False


def test_separate_input_1_unsupported_members_and_mixes_are_refused_by_name() -> None:
    """CTR17-SEPARATE-INPUT-1 / CHOICE-1: a mix, a non-ADD line, ``price_change_amount``,
    ``price_change_settlement``, an ``ssp_book_version_id`` without the line's label and an
    override without justification are refused at submit, each naming its field; noncash and
    payable members pass (they map onto the booking)."""
    mixed = _native_row(
        lines=[
            {"obligation_key": "O1", "action": "CHANGE", "quantity_delta": "1"},
            {"obligation_key": "O2", "action": "ADD", "product_code": "AVM-SEAT-MO"},
        ],
        chosen_treatments={"O1": "PROSPECTIVE", "O2": "SEPARATE_CONTRACT"},
        price_change_amount=Decimal("10.00"),
        questionnaire={"price_change_settlement": "FUTURE_PRICING"},
        ssp_basis={
            "O2": {"ssp_book_version_id": str(uuid4()), "is_override": True, "justification": ""}
        },
        noncash_consideration=[
            {
                "units": "1",
                "fair_value_per_unit": "10.00",
                "measurement_date": "2026-09-16",
                "variability": "FORM",
            }
        ],
    )
    fields = [error.field for error in modifications.separate_errors(mixed)]
    assert fields == [
        "chosen_treatments.O1",
        "lines[0].action",
        "price_change_amount",
        "questionnaire.price_change_settlement",
        "ssp_basis.O2.ssp_book_version_id",
        "ssp_basis.O2.justification",
    ]
    assert all(error.rule_id == "S06-R-03" for error in modifications.separate_errors(mixed))


def test_separate_input_1_booking_body_maps_inputs_and_refuses_a_currency_mismatch() -> None:
    """The 25-12 booking carries noncash / payable members and the ssp override justification;
    the external id defaults to <contract>-<modification no>; a line in another currency refuses
    (``T-CON-06``), never retagged."""
    row = _native_row(
        chosen_treatments={"O2": "SEPARATE_CONTRACT"},
        ssp_basis={"O2": {"is_override": True, "justification": "Bundle discount"}},
        noncash_consideration=[
            {
                "units": "2",
                "fair_value_per_unit": "100.00",
                "measurement_date": "2026-09-16",
                "variability": "FORM",
            }
        ],
        consideration_payable=[
            {"amount": {"amount": "50.00", "currency": "USD"}, "promise_date": "2026-10-01"}
        ],
        scope_605_35=None,
    )
    current = {
        "id": uuid4(),
        "external_id": "SF-ORD-10002",
        "customer_id": uuid4(),
        "contracting_entity_id": uuid4(),
    }
    booking = modifications.booking_body(row, current, entity_code="AVM-US")
    assert booking.external_id == "SF-ORD-10002-MOD-000009"
    assert booking.transaction_currency == "USD" and booking.inception_date == date(2026, 9, 16)
    (line,) = booking.lines
    assert (line.obligation_key, str(line.quantity)) == ("O2", "775")
    assert line.total_price.amount == "60000.00" and line.total_price.currency == "USD"
    assert line.ssp_override_justification == "Bundle discount"
    assert len(booking.noncash_consideration) == 1 and len(booking.consideration_payable) == 1
    assert booking.noncash_consideration[0].variability == "FORM"
    foreign = _native_row(chosen_treatments={"O2": "SEPARATE_CONTRACT"})
    foreign["lines"][0]["consideration_delta"] = {"amount": "60000.00", "currency": "EUR"}
    with pytest.raises(Problem) as refused:
        modifications.booking_body(foreign, current, entity_code="AVM-US")
    (error,) = refused.value.errors
    assert (error.field, error.rule_id) == ("lines[0].consideration_delta.currency", "T-CON-06")


def _event_input(
    contract_key: str, event_type: str, payload: dict[str, Any], *, keys: tuple[str, ...] = ()
) -> Any:
    from datetime import UTC, datetime

    from erev_engine.bundle import EventInput

    return EventInput(
        event_key=f"{contract_key}/EV-000001",
        contract_key=contract_key,
        stream_version=1,
        event_type=event_type,
        schema_version=1,
        effective_date=date(2026, 1, 1),
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
        record_seq=1,
        origin="UI",
        is_manual=False,
        obligation_keys=keys,
        payload=payload,
        payload_sha256="0" * 64,
        idempotency_key=None,
        supersedes_event_key=None,
        modification_key=payload.get("modification_id") if event_type == "REGROUPED" else None,
        estimate_version_key=None,
        manual_adjustment_key=None,
    )


def test_regroup_r1_target_group_reconstructs_the_move_from_the_in_events_lines() -> None:
    """REGROUP-R1: source and target in different groups. The target group's bundle holds only its
    own stream — the IN event's ``lines`` (04 §16.3) are the evidence, so the target's booking gains
    O2 without the source; the source group's bundle removes O2 from its booking through the OUT
    event alone. Groups are never merged. Fail-first: the previous assembly needed both bookings."""
    regroup_id, out_row_id, in_row_id = uuid4(), uuid4(), uuid4()
    moved_line = {
        "obligation_key": "O2",
        "product_code": "AVM-SEAT-MO",
        "quantity": "960",
        "total_price": "96000.00",
    }
    rows = {
        out_row_id: {"id": out_row_id, "approval_request_id": None},
        in_row_id: {"id": in_row_id, "approval_request_id": None},
    }
    target_bundle = (
        _event_input(
            "SF-B",
            "CONTRACT_BOOKED",
            {"lines": [{"obligation_key": "O1", "product_code": "AVM-SEAT-MO", "quantity": "1"}]},
            keys=("O1",),
        ),
        _event_input(
            "SF-B",
            "REGROUPED",
            {
                "regroup_id": str(regroup_id),
                "direction": "IN",
                "obligation_keys": ["O2"],
                "counterpart_contract_id": str(uuid4()),
                "modification_id": str(in_row_id),
                "lines": [moved_line],
            },
            keys=("O2",),
        ),
    )
    changed = bundles._apply_regroups(target_bundle, rows)
    booking = next(e for e in changed if e.event_type == "CONTRACT_BOOKED")
    assert [line["obligation_key"] for line in booking.payload["lines"]] == ["O1", "O2"]
    assert booking.obligation_keys == ("O1", "O2")
    source_bundle = (
        _event_input(
            "SF-A",
            "CONTRACT_BOOKED",
            {"lines": [{"obligation_key": "O1"}, moved_line]},
            keys=("O1", "O2"),
        ),
        _event_input(
            "SF-A",
            "REGROUPED",
            {
                "regroup_id": str(regroup_id),
                "direction": "OUT",
                "obligation_keys": ["O2"],
                "counterpart_contract_id": str(uuid4()),
                "modification_id": str(out_row_id),
            },
        ),
    )
    changed = bundles._apply_regroups(source_bundle, rows)
    booking = next(e for e in changed if e.event_type == "CONTRACT_BOOKED")
    assert [line["obligation_key"] for line in booking.payload["lines"]] == ["O1"]
    assert booking.obligation_keys == ("O1",)
    # a pair that went through approval (after posting) changes nothing here
    approved = {**rows, in_row_id: {"id": in_row_id, "approval_request_id": uuid4()}}
    assert bundles._apply_regroups(target_bundle, approved) == target_bundle


def test_regroup_r4_move_lines_take_the_bound_terms_and_refuse_a_missing_line() -> None:
    """REGROUP-R4 / R3: the pair's lines copy the source's booked terms; before posting the
    consideration is the booked price (the booking is the basis), after posting the bound remaining
    allocation ``amounts`` (complete by R3); a key without a booked line refuses by name."""
    from erev_api.domain.contracts import regroup

    booking = {
        "O2": {
            "obligation_key": "O2",
            "product_code": "AVM-SEAT-MO",
            "quantity": "960",
            "total_price": {"amount": "96000.00", "currency": "USD"},
            "start_date": "2026-01-01",
            "end_date": "2027-12-31",
        }
    }
    before = regroup._move_lines(
        booking,
        ["O2"],
        {},
        sign=-1,
        action="REMOVE",
        currency="USD",
        external_id="SF-A",
        posted=False,
    )
    assert before[0]["consideration_delta"] == {"amount": "-96000.00", "currency": "USD"}
    assert before[0]["quantity_delta"] == "-960"
    after = regroup._move_lines(
        booking,
        ["O2"],
        {"O2": Decimal("71726.03")},
        sign=1,
        action="ADD",
        currency="USD",
        external_id="SF-A",
        posted=True,
    )
    assert after[0]["consideration_delta"] == {"amount": "71726.03", "currency": "USD"}
    with pytest.raises(Problem) as refused:
        regroup._move_lines(
            booking,
            ["O9"],
            {},
            sign=1,
            action="ADD",
            currency="USD",
            external_id="SF-A",
            posted=False,
        )
    (error,) = refused.value.errors
    assert (error.field, error.rule_id) == ("obligation_keys", "REQ-CON-012")
    assert "books no line O9" in error.message


def test_a8_preview_job_locks_the_group_before_the_bundle_and_commits_before_success() -> None:
    """D-98 140-A8 PREVIEW-COMMIT-1 / DOMAIN-R1 capture, witnessed on the source order of
    ``run_preview`` (the database witnesses are NOT RUN): the governed lock order
    (``lock_group_then_contract``) precedes the row lock and the dry run, and ``uow.commit()``
    precedes the SUCCEEDED outcome so the stored preview survives the unit's exit."""
    import inspect

    source = inspect.getsource(modifications.run_preview)
    lock = source.index("lock_group_then_contract(")
    row_lock = source.index("_row(session, modification_id, lock=True)")
    dry_run = source.index("dry_run_summary(")
    commit = source.index("uow.commit()")
    success = source.index('JobOutcome(state="SUCCEEDED"')
    assert lock < row_lock < dry_run < commit < success
    assert (
        source.index("_separate_dry_run(") > lock
    )  # the booking preview also runs under the locks


# --- D-98 140-A9 (Codex production-20260921-1925) CPU witnesses -----------------------------------


def test_a9_input_1_every_native_monetary_member_is_normalised_with_its_currency() -> None:
    """INPUT-1 payable: the stored API-S items carry Money objects (payable amount, distinct-good
    fair value, committed purchases) — each is validated against the modification's currency and
    stripped to its scalar at the adapter; a bare decimal is kept; a mismatch refuses by name."""
    money = lambda amount: {"amount": amount, "currency": "USD"}  # noqa: E731
    row = _native_row(
        consideration_payable=[
            {
                "amount": money("50.00"),
                "promise_date": "2026-10-01",
                "distinct_good_fair_value": money("40.00"),
                "committed_purchases": None,
            }
        ],
        noncash_consideration=[
            {
                "units": "2",
                "fair_value_per_unit": "100.00",
                "measurement_date": "2026-09-16",
                "variability": "FORM",
            }
        ],
        price_change_amount=Decimal("12.50"),
    )
    native = bundles._native_input(row, {}, {})
    (payable,) = native.consideration_payable or ()
    assert (payable.amount, payable.distinct_good_fair_value, payable.committed_purchases) == (
        Decimal("50.00"),
        Decimal("40.00"),
        None,
    )
    (noncash,) = native.noncash_consideration or ()
    assert noncash.fair_value_per_unit == Decimal("100.00")
    assert native.price_change_amount == Decimal("12.50")
    assert bundles.native_money("7.5", currency="USD", key="x", member="m") == Decimal("7.5")
    assert bundles.native_money(None, currency="USD", key="x", member="m") is None
    foreign = _native_row(
        consideration_payable=[
            {"amount": {"amount": "50.00", "currency": "EUR"}, "promise_date": "2026-10-01"}
        ]
    )
    with pytest.raises(ValueError, match=r"payable\[0\].amount is stated in EUR"):
        bundles._native_input(foreign, {}, {})


def test_a9_input_1_ssp_basis_override_is_verified_against_the_named_version_and_policy() -> None:
    """INPUT-1 SSP basis: two eligible approved versions — an override naming v2 while the line is
    labelled with v1's label refuses (mismatch); label = v2's legacy label or its `<book>@v2` key
    passes under NAMED_VERSION; under a non-NAMED policy the override has no consumer and refuses;
    an id naming no approved version refuses."""
    v1, v2 = str(uuid4()), str(uuid4())
    versions = {v1: ("2026-H1", "US-LIST@v1"), v2: ("2026-H2", "US-LIST@v2")}

    def row(label: str | None, version: str) -> dict[str, Any]:
        found = _native_row(chosen_treatments={"O2": "SEPARATE_CONTRACT"})
        found["lines"][0]["ssp_version_label"] = label
        found["ssp_basis"] = {
            "O2": {"ssp_book_version_id": version, "is_override": True, "justification": "j"}
        }
        return found

    mismatch = modifications.ssp_basis_mismatches(
        row("2026-H1", v2), versions=versions, option="NAMED_VERSION"
    )
    assert [e.field for e in mismatch] == ["ssp_basis.O2.ssp_book_version_id"]
    assert "US-LIST@v2" in mismatch[0].message and "'2026-H1'" in mismatch[0].message
    assert (
        modifications.ssp_basis_mismatches(
            row("2026-H2", v2), versions=versions, option="NAMED_VERSION"
        )
        == []
    )
    assert (
        modifications.ssp_basis_mismatches(
            row("US-LIST@v2", v2), versions=versions, option="NAMED_VERSION"
        )
        == []
    )
    policy = modifications.ssp_basis_mismatches(
        row("2026-H2", v2), versions=versions, option="LATEST_APPROVED_EFFECTIVE_AT_INCEPTION"
    )
    assert len(policy) == 1 and "only under NAMED_VERSION" in policy[0].message
    unknown = modifications.ssp_basis_mismatches(
        row("2026-H2", str(uuid4())), versions=versions, option="NAMED_VERSION"
    )
    assert len(unknown) == 1 and "names no approved SSP book version" in unknown[0].message
    # not a separate choice → nothing to verify here (the amendment path carries the basis itself)
    plain = row("2026-H1", v2)
    plain["chosen_treatments"] = {"O2": "PROSPECTIVE"}
    assert modifications.ssp_basis_mismatches(plain, versions=versions, option="X") == []


def test_a9_choice_1_structural_refusal_precedes_the_preview_prerequisite() -> None:
    """CHOICE-1 order (source witness; the DB witness is NOT RUN): ``submit`` evaluates
    ``separate_errors`` before ``_stored_preview`` and dispatches the override / SSP checks after
    the preview; a wrong shape answers S06-R-03, never a masking REQ-PLT-015."""
    import inspect

    source = inspect.getsource(modifications.submit)
    assert source.index("separate_errors(") < source.index("_stored_preview(")
    assert source.index("_stored_preview(") < source.index("_ssp_basis_errors(")


def test_a9_regroup_r4_missing_terms_are_found_before_any_target_branch() -> None:
    """REGROUP-R4: ``missing_terms`` names the moved keys the source's latest booking does not
    carry (an obligation acquired by an earlier regroup has none) — checked before either target
    branch and before any write (source witness on ``regroup``)."""
    import inspect

    from erev_api.domain.contracts import regroup

    booking = {"O1": {"obligation_key": "O1"}, "O2": {"obligation_key": "O2"}}
    assert regroup.missing_terms(booking, ["O2", "O5", "O1"]) == ["O5"]
    assert regroup.missing_terms(booking, ["O1"]) == []
    source = inspect.getsource(regroup.regroup)
    assert source.index("missing_terms(") < source.index("_new_target(")
    assert source.index("missing_terms(") < source.index("_insert_row(")


def test_a9_regroup_r3_remaining_basis_is_bound_to_the_current_group() -> None:
    """REGROUP-R3: the remaining-consideration query binds the source's CURRENT combination group
    beside the book and the cutoff (source witness; versions are per group / book, so an old
    singleton v5 never outranks the joined group's v1) — the DB witness is NOT RUN."""
    import inspect

    from erev_api.domain.contracts import regroup

    source = inspect.getsource(regroup._remaining)
    assert "obligation_version.c.combination_group_id == group_id" in source
    assert "contract_version.c.known_at <= cutoff" in source
    assert "REMAINING_BASIS_MISSING" in source and "total_price" not in source


# --- D-98 140-A12 (Codex production-20260921-2006) CPU witnesses ----------------------------------


def test_a12_ssp_selection_binds_the_version_the_booking_actually_selects() -> None:
    """A12 (1): two approved books share the legacy label L; an override naming book B's version
    while the booking actually selects book A's L-version is refused by name (mismatch); a
    selection equal to the override passes; no selection for the line is refused as unresolved;
    the amendment path (not a separate choice) is untouched."""
    a_v1, b_v1 = str(uuid4()), str(uuid4())
    versions = {a_v1: ("L", "BOOK-A@v1"), b_v1: ("L", "BOOK-B@v1")}
    row = _native_row(chosen_treatments={"O2": "SEPARATE_CONTRACT"})
    row["lines"][0]["ssp_version_label"] = "L"
    row["ssp_basis"] = {
        "O2": {"ssp_book_version_id": b_v1, "is_override": True, "justification": "j"}
    }
    # ssp_basis_mismatches alone cannot tell A from B (both carry L under NAMED_VERSION)
    assert modifications.ssp_basis_mismatches(row, versions=versions, option="NAMED_VERSION") == []
    mismatch = modifications.ssp_selection_mismatches(
        row, selection={"O2": "BOOK-A@v1"}, versions=versions
    )
    assert [e.field for e in mismatch] == ["ssp_basis.O2.ssp_book_version_id"]
    assert "BOOK-A@v1" in mismatch[0].message and "BOOK-B@v1" in mismatch[0].message
    assert (
        modifications.ssp_selection_mismatches(
            row, selection={"O2": "BOOK-B@v1"}, versions=versions
        )
        == []
    )
    unresolved = modifications.ssp_selection_mismatches(row, selection={}, versions=versions)
    assert len(unresolved) == 1 and "made no SSP selection" in unresolved[0].message
    applied = modifications.ssp_applied_mismatches(row, persisted={"O2": UUID(a_v1)})
    assert len(applied) == 1 and a_v1 in applied[0].message
    assert modifications.ssp_applied_mismatches(row, persisted={"O2": UUID(b_v1)}) == []
    plain = dict(row, chosen_treatments={"O2": "PROSPECTIVE"})
    assert modifications.ssp_selection_mismatches(plain, selection={}, versions=versions) == []


def test_a12_selected_ssp_versions_reads_the_output_bundles_selection_per_obligation() -> None:
    """``selected_ssp_versions`` reads ``ssp_book_version_key`` of the new contract's obligation
    versions in the named book — the same column the persisted ``ssp_book_version_id`` derives
    from; another contract's rows and another book are ignored."""
    from erev_engine.bundle import ObligationVersionOut
    from erev_engine.stages.s01_canonicalize import obligation_subject_key

    book = dataclasses.make_dataclass("Book", ["book_code", "obligation_versions"])(
        book_code="ASC606",
        obligation_versions=[
            ObligationVersionOut(
                obligation_subject_key("SF-NEW", "O2"), {"ssp_book_version_key": "BOOK-A@v1"}, {}
            ),
            ObligationVersionOut(obligation_subject_key("SF-NEW", "O3"), {}, {}),
            ObligationVersionOut(
                obligation_subject_key("SF-OTHER", "O2"), {"ssp_book_version_key": "X@v9"}, {}
            ),
        ],
    )
    output = dataclasses.make_dataclass("Out", ["books"])(books=[book])
    assert modifications.selected_ssp_versions(
        output, external_id="SF-NEW", book_code="ASC606"
    ) == {  # type: ignore[arg-type]
        "O2": "BOOK-A@v1",
        "O3": None,
    }
    assert (
        modifications.selected_ssp_versions(output, external_id="SF-NEW", book_code="IFRS15") == {}
    )  # type: ignore[arg-type]


def test_a12_native_currency_mismatch_is_typed_and_translated_at_the_boundary() -> None:
    """A12 (4): the adapter raises the typed ``NativeCurrencyMismatch`` (never a bare ValueError
    the API would blanket-map); create / update refuse a foreign payable member at the input
    boundary with the exact field (``_member_currency_errors``); classify / preview translate
    exactly that typed error to a T-CON-06 field refusal (source witness)."""
    import inspect

    foreign = _native_row(
        consideration_payable=[
            {"amount": {"amount": "50.00", "currency": "EUR"}, "promise_date": "2026-10-01"}
        ]
    )
    with pytest.raises(bundles.NativeCurrencyMismatch) as raised:
        bundles._native_input(foreign, {}, {})
    assert raised.value.member == "payable[0].amount"
    body = ModificationCreateIn.model_validate(
        {
            "effective_date": "2026-09-16",
            "kind": "UPGRADE",
            "lines": [{"obligation_key": "O2", "action": "ADD", "product_code": "P"}],
            "consideration_payable": [
                {
                    "amount": {"amount": "500.00", "currency": "EUR"},
                    "promise_date": "2026-06-15",
                    "committed_purchases": {"amount": "1.00", "currency": "USD"},
                }
            ],
        }
    )
    errors = modifications._member_currency_errors(body, "USD")
    assert [(e.field, e.rule_id) for e in errors] == [
        ("consideration_payable[0].amount.currency", "T-CON-06")
    ]
    assert modifications._member_currency_errors(body, "EUR") != []  # committed_purchases is USD
    classify_source = inspect.getsource(modifications.classify)
    assert "except bundles.NativeCurrencyMismatch as error" in classify_source
    # MAIN DEFECT 3 (supervisor, method (c)): the ONE ``except ValueError`` clause is the
    # origin-gated S06-R-19 translation that re-raises every other ValueError (no blanket mapping).
    assert classify_source.count("except ValueError") == 1
    assert "s06_r19_refusal(error, row)" in classify_source
    assert "summarise=False" in classify_source  # CLASSIFY-EMPTY-EVENTS-1: no summary window


def test_a12_run_preview_checks_the_structural_choice_before_dispatch() -> None:
    """A12 (2) source witness: ``run_preview`` refuses ``separate_errors`` BEFORE
    ``separate_choice`` dispatches to the booking or the amendment path (the DB witness is NOT
    RUN)."""
    import inspect

    source = inspect.getsource(modifications.run_preview)
    assert source.index("separate_errors(row)") < source.index("if separate_choice(row):")
    assert source.index("if separate_choice(row):") < source.index("_amended_event(row")
    dry_run = inspect.getsource(modifications._separate_dry_run)
    assert dry_run.index("selected_ssp_versions(") < dry_run.index("ssp_selection_mismatches(")


def test_a14_input_1_preview_verifies_ssp_basis_before_booking_then_selection() -> None:
    """A14 (1) (Codex 2029 §2): ``ssp_selection_mismatches`` is silent for an id that names no
    APPROVED version (the basis check names it), so ``_separate_dry_run`` must run the basis check
    itself — ``_ssp_basis_errors`` at the record cutoff BEFORE the savepoint booking — and the
    selection check AFTER the dry run, both before the retained ``ssp_selection`` is built; an
    unknown or unapproved id therefore never yields a SUCCEEDED preview. Fail-first: the previous
    source called only ``ssp_selection_mismatches`` and left the basis check to ``/submit``."""
    import inspect

    unknown = str(uuid4())
    versions = {str(uuid4()): ("2026-H1", "US-LIST@v1")}
    row = _native_row(chosen_treatments={"O2": "SEPARATE_CONTRACT"})
    row["lines"][0]["ssp_version_label"] = "2026-H1"
    row["ssp_basis"] = {
        "O2": {"ssp_book_version_id": unknown, "is_override": True, "justification": "j"}
    }
    # the selection helper alone admits the unknown id — the basis helper is the guard
    assert (
        modifications.ssp_selection_mismatches(
            row, selection={"O2": "US-LIST@v1"}, versions=versions
        )
        == []
    )
    basis = modifications.ssp_basis_mismatches(row, versions=versions, option="NAMED_VERSION")
    assert [(e.field, e.rule_id) for e in basis] == [
        ("ssp_basis.O2.ssp_book_version_id", "S06-R-03")
    ]
    assert "names no approved SSP book version" in basis[0].message
    source = inspect.getsource(modifications._separate_dry_run)
    cutoff = source.index("record_cutoff(")
    basis_check = source.index("_ssp_basis_errors(")
    booking = source.index("begin_nested()")
    selected = source.index("selected_ssp_versions(")
    selection_check = source.index("ssp_selection_mismatches(")
    retained = source.index('"ssp_selection"')
    assert cutoff < basis_check < booking < selected < selection_check < retained


def test_a15_classification_defaults_keep_overrides_and_name_the_selected_version() -> None:
    """D-98 140 AMENDMENT 15 (CTR-17b): ``classification_defaults`` (pure) keeps every authored
    override (``is_override`` true) untouched, writes the dry run's selected version as a default
    (``is_override`` false, no justification) for every other selected key, and drops a stale
    default whose key the engine resolved no version for."""
    v_a, v_b, v_c = uuid4(), uuid4(), uuid4()
    current = {
        "O1": {"ssp_book_version_id": str(v_a), "is_override": True, "justification": "j"},
        "O2": {"ssp_book_version_id": str(v_b), "is_override": False, "justification": None},
        "O3": {"ssp_book_version_id": str(v_b), "is_override": False, "justification": None},
    }
    out = modifications.classification_defaults(current, {"O1": v_c, "O2": v_c})
    assert out["O1"] == current["O1"]  # the authored override stands, not the selection
    assert out["O2"] == {
        "ssp_book_version_id": str(v_c),
        "is_override": False,
        "justification": None,
    }
    assert "O3" not in out  # no selection → no default
    assert list(out) == ["O1", "O2"]
    assert modifications.classification_defaults({}, {}) == {}


def test_ctr17b_null_override_1_a_null_id_true_entry_survives_a_selected_version() -> None:
    """CTR17B-NULL-OVERRIDE-1 (Codex production-20260922-0610): an authored override still
    without a version id — ``{ssp_book_version_id: null, is_override: true, justification}`` —
    is left UNTOUCHED by ``classification_defaults`` when the dry run selects a version for its
    key: neither replaced by a default nor stripped of its justification (04 T-CON-06
    ``ssp_basis``: a true entry is left untouched)."""
    v = uuid4()
    current = {"O1": {"ssp_book_version_id": None, "is_override": True, "justification": "author"}}
    out = modifications.classification_defaults(current, {"O1": v, "O2": v})
    assert out["O1"] == current["O1"]
    assert out["O1"]["is_override"] is True and out["O1"]["justification"] == "author"
    assert out["O2"] == {"ssp_book_version_id": str(v), "is_override": False, "justification": None}


def test_ctr17b_null_override_1_a_null_id_true_entry_survives_no_selection() -> None:
    """CTR17B-NULL-OVERRIDE-1: the same null-id authored override is KEPT when the dry run
    selects no version for its key (before: dropped with the stale defaults)."""
    current = {"O1": {"ssp_book_version_id": None, "is_override": True, "justification": "author"}}
    out = modifications.classification_defaults(current, {})
    assert out == {"O1": current["O1"]}
    # the non-null filter still governs the S06-R-03 checks and the booking pin
    assert modifications.override_entries({"ssp_basis": current}) == {}


def test_a15_override_checks_and_the_booking_pin_apply_to_authored_overrides_only() -> None:
    """A15: a classification default (``is_override`` false) naming an id the checks cannot
    resolve and lacking the line's label is NOT refused by the S06-R-03 override checks and is
    NOT pinned into the booking; the same entry as an authored override (``is_override`` true) is
    checked and pinned. Fail-first: the checks read every entry naming an id."""
    unknown = str(uuid4())
    row = _native_row(chosen_treatments={"O2": "SEPARATE_CONTRACT"})
    row["ssp_basis"] = {
        "O2": {"ssp_book_version_id": unknown, "is_override": False, "justification": None}
    }
    assert modifications.separate_errors(row) == []
    assert modifications.ssp_basis_mismatches(row, versions={}, option="NAMED_VERSION") == []
    assert modifications.ssp_selection_mismatches(row, selection={}, versions={}) == []
    assert modifications.ssp_applied_mismatches(row, persisted={}) == []
    current = {"external_id": "SF-ORD-10001", "customer_id": uuid4()}
    booked = modifications.booking_body(row, current, entity_code="AVM-US")
    assert booked.lines[0].custom_attributes is None  # a default is informational, never pinned
    override = dict(row)
    override["ssp_basis"] = {
        "O2": {"ssp_book_version_id": unknown, "is_override": True, "justification": "pinned"}
    }
    assert [e.field for e in modifications.separate_errors(override)] == [
        "ssp_basis.O2.ssp_book_version_id"  # the label rule applies to the override
    ]
    override["lines"] = [dict(row["lines"][0], ssp_version_label="2026-H1")]
    assert modifications.separate_errors(override) == []
    mismatch = modifications.ssp_basis_mismatches(override, versions={}, option="NAMED_VERSION")
    assert [e.field for e in mismatch] == ["ssp_basis.O2.ssp_book_version_id"]
    pinned = modifications.booking_body(override, current, entity_code="AVM-US")
    assert pinned.lines[0].custom_attributes == {
        "ssp_book_version_id": unknown,
        "ssp_basis_source": "modification_ssp_basis",
    }


def test_a15_classify_writes_the_classification_defaults_after_the_proposal() -> None:
    """A15 source witness: ``classify`` derives the defaults from the dry run's output (existing
    obligations' ``ssp_book_version_key``; added lines' proposal detail ``ssp_version[<key>]``)
    AFTER the proposal is read and BEFORE the row is written, and writes ``ssp_basis``."""
    import inspect

    source = inspect.getsource(modifications.classify)
    proposal = source.index("_proposal(output, row)")
    selected = source.index("selected_ssp_versions(")
    defaults = source.index("classification_defaults(")
    written = source.index("transitions.apply(")
    assert proposal < selected < defaults < written
    assert '"ssp_basis": basis' in source and "ssp_version[" in source


def test_a16_proposal_out_emits_the_added_lines_selected_ssp_version_beside_the_class() -> None:
    """D-98 140 AMENDMENT 16 (engine, additive CV-16 detail): ``Proposal.out()`` emits
    ``ssp_version[<key>]`` for every added line the price test resolved, beside ``class[<key>]``
    and ``modification_key``; an empty ``ssp_versions`` (the default) emits nothing new, so every
    other producer of a proposal is unchanged. Fail-first: ``Proposal`` had no such member."""
    from types import MappingProxyType

    from erev_engine.enums import ModificationTreatment
    from erev_engine.stages import s06_modifications

    proposal = s06_modifications.Proposal(
        contract_key="SF-ORD-10001",
        modification_key="MOD-000001",
        summary=ModificationTreatment.PROSPECTIVE,
        treatments=MappingProxyType({"O2": ModificationTreatment.PROSPECTIVE}),
        classification=MappingProxyType({"O1": "D", "O2": "D"}),
        findings=(),
        ssp_versions=MappingProxyType({"O2": "US-LIST@v1"}),
    )
    detail = dict(proposal.out().detail)
    assert detail == {
        "class[O1]": "D",
        "class[O2]": "D",
        "modification_key": "MOD-000001",
        "ssp_version[O2]": "US-LIST@v1",
    }
    plain = dataclasses.replace(proposal, ssp_versions=MappingProxyType({}))
    assert "ssp_version[O2]" not in plain.out().detail
    assert list(plain.out().detail) == ["class[O1]", "class[O2]", "modification_key"]


# --- MAIN DEFECT 3: the S06-R-19 shape refusal as the named 422 (PRD 1.18 ERR-55; 04 1.84) ---


_K02_LIKE_ROW = {"lines": [{"obligation_key": "O1"}, {"obligation_key": "O2"}]}


def test_main_defect_3_a_line_shape_refusal_is_translated_by_origin_to_err_55() -> None:
    """The engine's ``subscriptions.check`` text "<modification>: line <key> does not have
    the <kind> shape (S06-R-19)" becomes ``validation-failed`` with ``rule_id`` "S06-R-19",
    the field ``lines[<n>]`` of the named key and the engine's text as the message (ERR-55)."""
    error = ValueError("MOD-1: line O2 does not have the UPGRADE shape (S06-R-19)")
    refused = modifications.s06_r19_refusal(error, _K02_LIKE_ROW)
    assert refused is not None and refused.slug == "validation-failed"
    (detail,) = refused.errors
    assert (detail.field, detail.rule_id, detail.message) == (
        "lines[1]",
        modifications.RULE_LINE_SHAPE,
        "MOD-1: line O2 does not have the UPGRADE shape (S06-R-19)",
    )


def test_main_defect_3_refusals_naming_no_line_use_the_lines_field() -> None:
    """The two other S06-R-19 texts ("a <kind> modification has lines", "an early renewal adds
    a renewal line") carry the field ``lines``; an unknown key falls back to ``lines`` too."""
    for text in (
        "MOD-1: a CO_TERM modification has lines (S06-R-19)",
        "MOD-1: an early renewal adds a renewal line (S06-R-19)",
        "MOD-1: line O9 does not have the DOWNGRADE shape (S06-R-19)",
    ):
        refused = modifications.s06_r19_refusal(ValueError(text), _K02_LIKE_ROW)
        assert refused is not None and refused.errors[0].field == "lines", text
        assert refused.errors[0].rule_id == "S06-R-19" and refused.errors[0].message == text


def test_main_defect_3_any_other_value_error_is_not_translated() -> None:
    """Never a blanket catch: a ``ValueError`` without the S06-R-19 origin returns None, so the
    boundary re-raises it unchanged (CV-45: still a programming error)."""
    for text in (
        "MOD-1: MOD-RG-K-01 is absent (CV-10)",
        "boom",
        "MOD-1: line O2 does not have the UPGRADE shape (S06-R-19) and more",  # not at the end
        "MOD-1: something else entirely (S06-R-19)",  # the literal alone is not the origin
        "(S06-R-19)",
    ):
        assert modifications.s06_r19_refusal(ValueError(text), _K02_LIKE_ROW) is None, text


def test_main_defect_3_the_engine_literal_and_both_boundaries_are_pinned() -> None:
    """Origin discrimination rests on the engine's literal ``(S06-R-19)`` and its three message
    shapes — every S06-R-19 refusal in ``subscriptions._require`` / ``check`` ends with it
    (tests/engine/s06_modifications/test_s06_lifecycle.py:472-498 pin the texts through the
    engine) — and on classify AND preview translating through ``s06_r19_refusal`` after the
    ``NativeCurrencyMismatch`` clause (a ``ValueError`` subclass, so it must come first).
    S06R19-TYPED-ERR-1 retires this coupling with a typed engine exception at the next engine
    version step."""
    engine_source = inspect.getsource(subscriptions._require) + inspect.getsource(
        subscriptions.check
    )
    assert engine_source.count("(S06-R-19)") >= 3
    for fragment in ("does not have the", "modification has lines", "adds a renewal line"):
        assert fragment in engine_source, fragment
    for function in (modifications.classify, modifications.run_preview):
        source = inspect.getsource(function)
        assert source.index("NativeCurrencyMismatch") < source.index("s06_r19_refusal(error, row)")
