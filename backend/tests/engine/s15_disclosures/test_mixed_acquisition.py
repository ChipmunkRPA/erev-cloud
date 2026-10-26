"""Ordinary activity must not become a residual at another member's acquisition date."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles
from support import onboarding_worlds as w

from erev_engine import compute


def mixed_value(invoice_day, billed, consumption):
    value = w.two_contracts(as_of=date(2026, 1, 31))
    ordinary = w.COLLIDING[0]
    events = [
        replace(e, payload=w.opening_payload(billed_cum=billed))
        if e.event_type == "OPENING_BALANCE_ESTABLISHED"
        else e
        for e in value.events
        if not (e.contract_key == ordinary and e.event_type == "OPENING_BALANCE_ESTABLISHED")
    ]
    events.append(
        bundles.event(
            ordinary,
            4,
            "BILLING_RECORDED",
            invoice_day,
            {
                "invoice_number": "ORDINARY",
                "line_external_id": "ORDINARY-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("240000"),
                "issue_date": invoice_day,
            },
            obligation_keys=[w.OBLIGATION],
        )
    )
    value = replace(
        value,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(p, value=consumption)
                    if p.code == "rollforward.opening_liability_consumption"
                    else p
                    for p in book.policies
                ),
            )
            for book in value.books
        ),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
    )
    return value


@pytest.mark.parametrize("invoice_day", [date(2025, 12, 30), w.CUTOVER])
@pytest.mark.parametrize("billed", ["240000", "0"])
@pytest.mark.parametrize("consumption", ["FIFO_WITHIN_CONTRACT", "FIFO_WITHIN_POB"])
def test_mixed_acquisition_keeps_activity_and_dates_netting(invoice_day, billed, consumption):
    value = mixed_value(invoice_day, billed, consumption)
    ordinary = w.COLLIDING[0]
    prior = compute(replace(value, evidence_revision=24)).books[0]
    current = compute(replace(value, evidence_revision=25)).books[0]
    assert current.posting_intents == prior.posting_intents
    assert current.fx_layer_movements == prior.fx_layer_movements
    row = next(r for r in current.disclosure_rollforwards if r.view == "TRANSACTION")
    assert row.lines["CONTRACT_LIABILITY"]["CLOSING"] == (24000000 if billed == "240000" else 0)
    for role, amounts in row.lines.items():
        assert amounts["OTHER"] == 0, (role, dict(amounts))
        assert amounts["CLOSING"] == sum(v for k, v in amounts.items() if k != "CLOSING")
    if invoice_day < w.CUTOVER:
        assert row.lines["CONTRACT_LIABILITY"]["INCREASES_BILLING"] == 24000000
        assert row.lines["CONTRACT_LIABILITY"]["BUSINESS_COMBINATIONS"] == (
            12000000 if billed == "240000" else -12000000
        )
    elif billed == "240000":
        # Ordinary revenue comes first; acquisition settles its asset before billing.
        assert row.lines["CONTRACT_ASSET"]["BUSINESS_COMBINATIONS"] == -12000000
        assert row.lines["CONTRACT_LIABILITY"]["BUSINESS_COMBINATIONS"] == 0
    if consumption == "FIFO_WITHIN_POB" and invoice_day < w.CUTOVER and billed == "240000":
        later = bundles.event(
            ordinary,
            5,
            "BILLING_RECORDED",
            date(2026, 1, 1),
            {
                "invoice_number": "LATER",
                "line_external_id": "LATER-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("100"),
                "issue_date": date(2026, 1, 1),
            },
            obligation_keys=[w.OBLIGATION],
        )
        subsequent = compute(replace(value, evidence_revision=25, events=(*value.events, later)))
        period = next(
            r
            for r in subsequent.books[0].disclosure_rollforwards
            if r.period_key == "FY2026-P01" and r.view == "TRANSACTION"
        )
        liability = period.lines["CONTRACT_LIABILITY"]
        assert liability["OPENING"] == 24000000
        assert liability["CLOSING"] == 22010000
        assert liability["REVENUE_FROM_OPENING_BALANCE"] == -2000000
        assert liability["OTHER"] == 0


def foreign_value(value):
    from erev_engine.bundle import FxRateInput, MappingRuleInput

    rates = tuple(
        FxRateInput(
            f"{kind}-{p.period_key}",
            "v1",
            kind,
            "USD",
            "EUR",
            p.end_date,
            None if kind == "spot" else p.period_key,
            Decimal("0.88" if kind == "average" else "0.9"),
        )
        for p in value.entities[0].periods
        for kind in ("spot", "average", "closing")
    )
    value = replace(
        value,
        currencies=bundles.currencies("EUR", "USD"),
        entities=tuple(replace(e, functional_currency="EUR") for e in value.entities),
        fx_rates=tuple(
            sorted(
                rates,
                key=lambda r: (
                    r.rate_type,
                    r.base_currency,
                    r.quote_currency,
                    r.effective_date,
                    r.period_key or "",
                    r.version_key,
                ),
            )
        ),
        books=tuple(
            replace(
                b,
                account_mapping=replace(
                    b.account_mapping,
                    rules=tuple(
                        sorted(
                            (
                                *b.account_mapping.rules,
                                MappingRuleInput(
                                    "FX_GAIN_LOSS", None, None, None, None, None, "FX-GL", {}, 0, 0
                                ),
                            ),
                            key=lambda r: (
                                r.account_role,
                                r.clearing_purpose or "",
                                r.account_code,
                            ),
                        )
                    ),
                ),
            )
            for b in value.books
        ),
    )
    return value


@pytest.mark.parametrize("invoice_day", [date(2025, 12, 30), w.CUTOVER])
@pytest.mark.parametrize("billed", ["240000", "0"])
@pytest.mark.parametrize("consumption", ["FIFO_WITHIN_CONTRACT", "FIFO_WITHIN_POB"])
def test_mixed_functional_uses_original_fx_movements(invoice_day, billed, consumption):
    value = foreign_value(mixed_value(invoice_day, billed, consumption))
    prior = compute(replace(value, evidence_revision=25)).books[0]
    current = compute(replace(value, evidence_revision=26)).books[0]
    retained_bundle = replace(value, evidence_revision=27)
    retained_result = compute(retained_bundle)
    retained = retained_result.books[0]
    assert (
        replace(
            retained,
            disclosure_rollforwards=tuple(
                replace(r, acquisition_sources=None) for r in retained.disclosure_rollforwards
            ),
        )
        == current
    )
    import json
    from datetime import timedelta
    from uuid import UUID

    from erev_api.domain.reports.acquisition_native import read
    from erev_api.domain.reports.tie_outs import PeriodRef
    from erev_engine.canonical import canonical_bytes

    encoded = json.loads(canonical_bytes(retained_result))
    for native_row in retained.disclosure_rollforwards:
        period = PeriodRef(
            UUID(int=1),
            native_row.period_key,
            native_row.period_key,
            2025,
            12,
            4,
            native_row.opening_date + timedelta(days=1),
            native_row.closing_date,
        )
        selected = read(
            retained_bundle,
            encoded,
            book=retained.book_code,
            entity=native_row.entity,
            period=period,
            functional=native_row.view == "FUNCTIONAL",
        )
        assert selected is not None
        assert selected["members"] == sorted(value.group.member_contract_keys)
        assert selected["sources"] == json.loads(canonical_bytes(native_row.acquisition_sources))
        assert selected["amounts"] == {
            role: lines["BUSINESS_COMBINATIONS"] for role, lines in native_row.lines.items()
        }
    if consumption == "FIFO_WITHIN_CONTRACT" and invoice_day == w.CUTOVER and billed == "240000":
        from copy import deepcopy

        from erev_api.problems import Problem

        functional_row = next(r for r in retained.disclosure_rollforwards if r.view == "FUNCTIONAL")
        for corruption in ("missing_source", "trace", "currency"):
            changed = deepcopy(encoded)
            raw_row = next(
                r
                for r in changed["books"][0]["disclosure_rollforwards"]
                if r["view"] == "FUNCTIONAL"
            )
            if corruption == "missing_source":
                raw_row["acquisition_sources"].pop()
            elif corruption == "trace":
                raw_row["acquisition_sources"][0]["trace_node_id"] = "missing-original-node"
            else:
                raw_row["currency"] = "USD"
            with pytest.raises(Problem):
                read(
                    retained_bundle,
                    changed,
                    book=retained.book_code,
                    entity=functional_row.entity,
                    period=period,
                    functional=True,
                )
    nodes = {node.id for node in retained.trace.nodes}
    for evidence_row in retained.disclosure_rollforwards:
        sources = evidence_row.acquisition_sources
        assert sources is not None
        for role, amounts in evidence_row.lines.items():
            assert (
                sum(source["amounts"][role] for source in sources)
                == amounts["BUSINESS_COMBINATIONS"]
            )
        for source in sources:
            assert source["effective_date"] == w.CUTOVER.isoformat()
            if evidence_row.view == "FUNCTIONAL":
                assert source["kind"] == "ORIGINAL_FX_MOVEMENT"
                assert source["trace_node_id"] in nodes
                assert any(
                    move.columns["layer_key"] == source["layer_key"]
                    and move.columns["source_key"] == source["source_key"]
                    and move.columns["movement_kind"] == source["movement_kind"]
                    and move.trace_nodes["amount_functional"] == source["trace_node_id"]
                    for move in retained.fx_layer_movements
                )
            else:
                assert source["kind"] == "ORIGINAL_CUTOVER_EVENT"
                event = next(e for e in value.events if e.event_key == source["event_key"])
                assert event.event_type == "OPENING_BALANCE_ESTABLISHED"
                assert source["subjects"]
    assert current.posting_intents == prior.posting_intents
    assert current.fx_layer_movements == prior.fx_layer_movements
    row = next(r for r in current.disclosure_rollforwards if r.view == "FUNCTIONAL")
    for role, amounts in row.lines.items():
        assert amounts["OTHER"] == 0, (role, dict(amounts))
        assert amounts["CLOSING"] == sum(v for k, v in amounts.items() if k != "CLOSING")
    assert row.lines["CONTRACT_LIABILITY"]["CLOSING"] == (21600000 if billed == "240000" else 0)
    if invoice_day == w.CUTOVER:
        assets = row.lines["CONTRACT_ASSET"]
        assert assets["REVENUE_IN_EXCESS_OF_BILLING"] == 10560000
        assert assets["FX"] == 480000
        assert assets["BUSINESS_COMBINATIONS"] == (-11040000 if billed == "240000" else 10560000)
    if consumption == "FIFO_WITHIN_POB" and invoice_day < w.CUTOVER and billed == "240000":
        later = bundles.event(
            w.COLLIDING[0],
            5,
            "BILLING_RECORDED",
            date(2026, 1, 1),
            {
                "invoice_number": "NEXT",
                "line_external_id": "NEXT-1",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("100"),
                "issue_date": date(2026, 1, 1),
            },
            obligation_keys=[w.OBLIGATION],
        )
        following = compute(replace(value, evidence_revision=26, events=(*value.events, later)))
        next_row = next(
            r
            for r in following.books[0].disclosure_rollforwards
            if r.view == "FUNCTIONAL" and r.period_key == "FY2026-P01"
        )
        liability = next_row.lines["CONTRACT_LIABILITY"]
        assert liability["OPENING"] == 21600000
        assert liability["REVENUE_FROM_OPENING_BALANCE"] == -1800000
        assert liability["CLOSING"] == 19809000
        assert liability["OTHER"] == 0


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("foreign", [False, True])
@pytest.mark.parametrize("layer_policy", ["FIFO", "PRO_RATA"])
def test_acquired_member_current_liability_uses_carrying_weights(mixed, foreign, layer_policy):
    from uuid import UUID

    from erev_api.domain.reports.functional_balances import project
    from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
    from erev_engine.trace import reevaluate

    value = (
        mixed_value(w.CUTOVER, "240000", "FIFO_WITHIN_CONTRACT")
        if mixed
        else w.two_contracts(as_of=date(2026, 1, 31))
    )
    value = replace(
        value,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(policy, value="OPENING_BALANCES_AT_CUTOVER")
                    if policy.code == "onboarding.method"
                    else replace(policy, value=layer_policy)
                    if policy.code == "fx.cl_layer_consumption"
                    else policy
                    for policy in book.policies
                ),
            )
            for book in value.books
        ),
    )
    value = replace(
        value,
        events=tuple(
            replace(
                event,
                payload={
                    **event.payload,
                    "lines": [
                        {**line, "end_date": "2028-12-31"} for line in event.payload["lines"]
                    ],
                },
            )
            if event.event_type == "CONTRACT_BOOKED"
            else replace(event, payload=w.opening_payload(billed_cum="180000"))
            if event.event_type == "OPENING_BALANCE_ESTABLISHED"
            and event.contract_key == w.COLLIDING[1]
            else event
            for event in value.events
        ),
    )
    calendar = bundles.entity(start=w.INCEPTION, months=48, books=("ASC606",))
    value = replace(
        value,
        entities=tuple(
            replace(
                entity,
                periods=(
                    *entity.periods,
                    *(
                        replace(period, states=(("ASC606", "future"),))
                        for period in calendar.periods
                        if period.start_date > entity.periods[-1].end_date
                    ),
                ),
            )
            for entity in value.entities
        ),
    )
    if foreign:
        value = foreign_value(value)
    prior = compute(replace(value, evidence_revision=58)).books[0]
    current = compute(replace(value, evidence_revision=59)).books[0]
    assert current.posting_intents == prior.posting_intents
    assert current.schedules == prior.schedules
    assert current.fx_layer_movements == prior.fx_layer_movements
    assert reevaluate(current.trace) == {n.id: n.value for n in current.trace.nodes}
    nodes = {n.id: n for n in current.trace.nodes}
    rows = [r for r in current.balances if r.period_key == "FY2026-P01"]
    assert len(rows) == 2
    for suffix in ("txn", "functional") if foreign else ("txn",):
        totals = [r.columns[f"contract_liability_{suffix}"] for r in rows]
        amounts = []
        for row, total in zip(rows, totals, strict=True):
            measure = "contract_liability_current" + (
                "_functional" if suffix == "functional" else ""
            )
            node = nodes[f"{measure}:{row.subject_key}:{row.period_key}"]
            amount = int(Decimal(node.value) * 100)
            assert 0 <= amount <= total
            assert node.params["basis"] == "MEMBER_LIABILITY_CARRYING"
            amounts.append(amount)
            if suffix == "txn":
                assert row.columns["contract_liability_current_txn"] == amount
            if suffix == "functional":
                member = next(
                    c.external_id
                    for c in value.contracts
                    if contract_entity_subject_key(c.external_id, w.ENTITY) == row.subject_key
                )
                projected = project(
                    current.trace,
                    external_id=member,
                    entity_code=w.ENTITY,
                    period_key=row.period_key,
                    version_id=UUID(int=1),
                    stored={
                        key: Decimal(v) / 100 if isinstance(v, int) else v
                        for key, v in row.columns.items()
                    },
                    measures=("contract_liability", "contract_liability_current"),
                )
                assert projected["contract_liability_current"] == Decimal(amount) / 100
                assert projected["contract_liability"] == Decimal(total) / 100

        assert 0 < sum(amounts) < sum(totals)
        group = nodes[nodes[f"{measure}:{rows[0].subject_key}:{rows[0].period_key}"].inputs[0]]
        assert sum(amounts) == int(Decimal(group.value) * 100)
        for amount, total in zip(amounts, totals, strict=True):
            assert abs(amount * sum(totals) - sum(amounts) * total) <= sum(totals)


@pytest.mark.parametrize("all_recomputed", [False, True])
def test_recomputed_combination_current_members_follow_actual_balances(all_recomputed):
    from erev_engine.trace import reevaluate

    value = w.two_contracts(as_of=date(2026, 1, 31))
    if all_recomputed:
        value = replace(
            value,
            books=tuple(
                replace(
                    book,
                    policies=tuple(
                        replace(p, value="RECOMPUTE_FROM_INCEPTION")
                        if p.code == "onboarding.method"
                        else p
                        for p in book.policies
                    ),
                )
                for book in value.books
            ),
        )
    events = tuple(
        bundles.event(
            member,
            4,
            "BILLING_RECORDED",
            w.CUTOVER,
            {
                "invoice_number": f"SOURCE-{index}",
                "line_external_id": f"SOURCE-{index}",
                "obligation_key": w.OBLIGATION,
                "amount": Decimal("300000") + index,
                "issue_date": w.CUTOVER,
            },
            obligation_keys=[w.OBLIGATION],
        )
        for index, member in enumerate(w.COLLIDING)
    )
    value = replace(
        value,
        events=tuple(
            sorted(
                (*value.events, *events),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
        evidence_revision=60,
    )
    prior = compute(replace(value, evidence_revision=59)).books[0]
    current = compute(value).books[0]
    assert current.posting_intents == prior.posting_intents
    assert current.schedules == prior.schedules
    assert reevaluate(current.trace) == {n.id: n.value for n in current.trace.nodes}
    rows = [r for r in current.balances if r.period_key == "FY2026-P01"]
    assert len(rows) == 2
    amounts = [r.columns["contract_liability_current_txn"] for r in rows]
    totals = [r.columns["contract_liability_txn"] for r in rows]
    assert 0 < sum(amounts) <= sum(totals)
    for amount, total in zip(amounts, totals, strict=True):
        assert 0 <= amount <= total
        assert abs(amount * sum(totals) - total * sum(amounts)) <= sum(totals)


@pytest.mark.parametrize("mode", ["cutover", "recompute", "ordinary_member"])
@pytest.mark.parametrize("foreign", [False, True])
def test_acquired_current_assets_follow_original_member_maturity(mode, foreign):
    from uuid import UUID

    from erev_api.domain.reports.functional_balances import project
    from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
    from erev_engine.trace import reevaluate

    value = w.two_contracts(as_of=date(2026, 1, 31))
    method = "RECOMPUTE_FROM_INCEPTION" if mode == "recompute" else "OPENING_BALANCES_AT_CUTOVER"
    value = replace(
        value,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(p, value=method) if p.code == "onboarding.method" else p
                    for p in book.policies
                ),
            )
            for book in value.books
        ),
    )
    events = []
    for event in value.events:
        if event.event_type == "OPENING_BALANCE_ESTABLISHED":
            if mode == "ordinary_member" and event.contract_key == w.COLLIDING[0]:
                continue
            event = replace(event, payload=w.opening_payload(billed_cum="0"))
        if event.event_type == "CONTRACT_BOOKED" and event.contract_key == w.COLLIDING[1]:
            event = replace(
                event,
                payload={
                    **event.payload,
                    "lines": [
                        {**line, "end_date": "2028-12-31"} for line in event.payload["lines"]
                    ],
                },
            )
        events.append(event)
    calendar = bundles.entity(start=w.INCEPTION, months=48, books=("ASC606",))
    value = replace(
        value,
        evidence_revision=61,
        events=tuple(events),
        entities=tuple(
            replace(
                entity,
                periods=(
                    *entity.periods,
                    *(
                        replace(period, states=(("ASC606", "future"),))
                        for period in calendar.periods
                        if period.start_date > entity.periods[-1].end_date
                    ),
                ),
            )
            for entity in value.entities
        ),
    )
    if foreign:
        value = foreign_value(value)
    if foreign and mode == "recompute":
        from erev_engine.errors import EngineError

        for revision in (60, 61):
            with pytest.raises(EngineError, match="ONBOARDING_DIFFERENCE_UNPOSTED"):
                compute(replace(value, evidence_revision=revision))
        return
    prior = compute(replace(value, evidence_revision=60)).books[0]
    output = compute(value).books[0]
    assert output.posting_intents == prior.posting_intents
    assert output.schedules == prior.schedules
    assert output.fx_layer_movements == prior.fx_layer_movements
    assert reevaluate(output.trace) == {n.id: n.value for n in output.trace.nodes}
    rows = [r for r in output.balances if r.period_key == "FY2026-P01"]
    assert len(rows) == 2
    for row in rows:
        member = next(
            c.external_id
            for c in value.contracts
            if contract_entity_subject_key(c.external_id, w.ENTITY) == row.subject_key
        )
        long_lived = member == w.COLLIDING[1]
        assert row.columns["contract_asset_txn"] > 0
        assert row.columns["contract_asset_current_txn"] == (
            0 if long_lived else row.columns["contract_asset_txn"]
        )
        if foreign:
            values = project(
                output.trace,
                external_id=member,
                entity_code=w.ENTITY,
                period_key=row.period_key,
                version_id=UUID(int=1),
                stored={
                    k: Decimal(v) / 100 if isinstance(v, int) else v for k, v in row.columns.items()
                },
                measures=("contract_asset", "contract_asset_current"),
            )
            assert values["contract_asset"] > 0
            assert values["contract_asset_current"] == (
                0 if long_lived else values["contract_asset"]
            )


@pytest.mark.parametrize("functional", [False, True])
@pytest.mark.parametrize("invoice_day", [date(2025, 12, 30), w.CUTOVER])
@pytest.mark.parametrize("billed", ["240000", "0"])
def test_public_group_projection_preserves_native_movements(
    monkeypatch, functional, invoice_day, billed
):
    import json
    from datetime import timedelta
    from uuid import UUID

    from erev_api.domain.reports import acquisition_groups as groups
    from erev_api.domain.reports import tie_outs
    from erev_api.domain.reports.builders.contract_balance_rollforward import (
        balances_equal_tie,
        balances_tie,
    )
    from erev_api.problems import Problem
    from erev_engine.canonical import canonical_bytes
    from erev_engine.stages.s01_canonicalize import contract_entity_subject_key

    value = replace(
        foreign_value(mixed_value(invoice_day, billed, "FIFO_WITHIN_CONTRACT")),
        evidence_revision=67,
    )
    output = compute(value)
    encoded = json.loads(canonical_bytes(output))
    original = output.books[0]
    entity_id = UUID(int=1)
    currency = "EUR" if functional else "USD"
    view = "FUNCTIONAL" if functional else "TRANSACTION"
    native = sorted(
        (r for r in original.disclosure_rollforwards if r.view == view),
        key=lambda r: r.closing_date,
    )
    periods = tuple(
        tie_outs.PeriodRef(
            UUID(int=100 + i),
            r.period_key,
            r.period_key,
            r.closing_date.year,
            r.closing_date.month,
            4,
            r.opening_date + timedelta(days=1),
            r.closing_date,
        )
        for i, r in enumerate(native)
    )
    nodes = {n.id: n for n in original.trace.nodes}

    def endpoints(period):
        result = []
        for i, member in enumerate(sorted(value.group.member_contract_keys)):
            subject = contract_entity_subject_key(member, w.ENTITY)
            suffix = "_functional" if functional else ""
            result.append(
                tie_outs.BalanceRow(
                    UUID(int=10 + i),
                    member,
                    None,
                    entity_id,
                    w.ENTITY,
                    currency,
                    UUID(int=20 + i),
                    {
                        role: Decimal(nodes[f"{role}{suffix}:{subject}:{period.key}"].value)
                        for role in tie_outs.ROLLFORWARD_BALANCES
                    },
                )
            )
        return tuple(result)

    closing = endpoints(periods[-1])
    rows = {(r.contract_id, r.entity_id): r for r in closing}
    source = {"input_sha256": value.sha256(), "output_sha256": "authenticated-original-output"}
    monkeypatch.setattr(groups.acquisition_evidence, "load", lambda *_: (value, encoded, source))
    group = groups.collect(
        None,
        rows,
        value,
        encoded,
        source,
        book="ASC606",
        entity_id=entity_id,
        entity_code=w.ENTITY,
        periods=periods,
        functional=functional,
    )
    monthly = {
        (entity_id, period.id): {(r.contract_id, r.entity_id): r for r in endpoints(period)}
        for period in periods
    }
    before = json.loads(canonical_bytes(encoded))
    item = groups.project(group, opening=(), closing=closing, monthly=monthly)
    assert len(item.group_members) == 2
    assert {m.contract_id for m in item.group_members} == {r.contract_id for r in closing}
    assert item.lines["OTHER"] == dict.fromkeys(tie_outs.ROLLFORWARD_BALANCES, Decimal(0))
    assert balances_tie({currency: item.lines}, (item,))["result"] == "PASS"
    assert balances_equal_tie(closing, (item,))["result"] == "PASS"
    for period, row in zip(periods, native, strict=True):
        assert item.period_lines[period.id]["BUSINESS_COMBINATIONS"] == {
            role.lower(): Decimal(lines["BUSINESS_COMBINATIONS"]) / 100
            for role, lines in row.lines.items()
        }
    if invoice_day == w.CUTOVER and billed == "240000":
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from erev_api.domain.reports import acquisition_cells, acquisition_flows
        from erev_api.domain.reports.builders import ReportParams, SourceBinding, SourceCollector

        collector = SourceCollector()
        collector.record_evidence(acquisition_flows.KEY, group.facts)
        params = ReportParams(
            "contract_balance_rollforward",
            1,
            {},
            (entity_id,),
            datetime.now(UTC),
            sources=collector,
        )
        row_key = f"contract:{item.external_id}:{item.entity_code}"
        amount = tie_outs.money(item.lines["BUSINESS_COMBINATIONS"]["contract_asset"], currency)
        assert Decimal(amount["amount"]) < 0
        acquisition_cells.retain(
            params,
            (item,),
            ({"row_key": row_key, "business_combinations": amount},),
            "contract_asset",
            [],
        )
        held = replace(
            params,
            binding=SourceBinding(
                params.known_at, {}, {}, frozenset(), evidence=collector.evidence
            ),
        )
        session = SimpleNamespace(
            execute=lambda _: [(UUID(key.split(":")[0]), UUID(int=200)) for key in group.facts]
        )
        cell_value, contributors = acquisition_cells.cell(
            session, held, row_key, "business_combinations"
        )
        assert cell_value == amount and sum(Decimal(c["value"]["amount"]) for c in contributors) < 0
        assert all(len(c["_source_set_links"]) >= 2 for c in contributors)
        assert "Complete members" in str(contributors)
    assert encoded == before
    # Source identities retain each independently bound member version; no per-member flow quota.
    assert len(group.evidence["member_versions"]) == 2
    assert all(len(fact["group_members"]) == 2 for fact in group.facts.values())
    with pytest.raises(Problem):
        groups.collect(
            None,
            {next(iter(rows)): next(iter(rows.values()))},
            value,
            encoded,
            source,
            book="ASC606",
            entity_id=entity_id,
            entity_code=w.ENTITY,
            periods=periods,
            functional=functional,
        )
    bad_closing = (
        replace(closing[0], values={**closing[0].values, "contract_liability": Decimal(1)}),
        closing[1],
    )
    if bad_closing != closing:
        with pytest.raises(Problem):
            groups.project(group, opening=(), closing=bad_closing, monthly={})


def test_mixed_monthly_retention_does_not_change_calculations():
    value = foreign_value(mixed_value(w.CUTOVER, "240000", "FIFO_WITHIN_CONTRACT"))
    prior = compute(replace(value, evidence_revision=67)).books[0]
    current = compute(replace(value, evidence_revision=68)).books[0]
    assert current.posting_intents == prior.posting_intents
    assert current.fx_layer_movements == prior.fx_layer_movements
    assert current.schedules == prior.schedules
    assert current.balances == prior.balances
    assert current.trace == prior.trace
    previous = {(r.entity, r.period_key, r.view): r for r in prior.disclosure_rollforwards}
    assert previous
    assert all(
        r == previous[(r.entity, r.period_key, r.view)]
        for r in current.disclosure_rollforwards
        if (r.entity, r.period_key, r.view) in previous
    )
    cutover = [r for r in current.disclosure_rollforwards if r.period_key == "FY2025-P12"]
    assert len(cutover) == 2 and all(r.acquisition_sources for r in cutover)
    for row in current.disclosure_rollforwards:
        for lines in row.lines.values():
            assert lines["OTHER"] == 0
            assert lines["CLOSING"] == sum(v for k, v in lines.items() if k != "CLOSING")
