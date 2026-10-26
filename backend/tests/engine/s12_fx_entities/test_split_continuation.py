"""Foreign splits retain historical sources and reconciling journal/report paths."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction
from uuid import uuid4

import pytest
from erev_engine import compute
from erev_engine.canonical import canonical_bytes
from erev_engine.trace import reevaluate
from support import bundles, intent_totals
from tests.engine.s15_disclosures.test_mixed_acquisition import foreign_value
from tests.engine.test_combination_split_balances import billed_split


def split_value(policy="FIFO"):
    value = replace(foreign_value(billed_split()), evidence_revision=70)
    extra = bundles.event(
        "K-01",
        99999,
        "BILLING_RECORDED",
        date(2026, 9, 1),
        {
            "invoice_number": "BEFORE",
            "line_external_id": "1",
            "obligation_key": "POB-01",
            "amount": "200000",
            "issue_date": "2026-09-01",
            "is_cancellable": False,
        },
        obligation_keys=["POB-01"],
        record_seq=99999,
    )
    rate = next(r for r in value.fx_rates if r.rate_type == "spot")
    rates = (
        *value.fx_rates,
        replace(
            rate, rate_key="SPLIT-SPOT", effective_date=date(2026, 9, 16), rate=Decimal("1.15")
        ),
    )
    return replace(
        value,
        books=tuple(
            replace(
                b,
                policies=tuple(
                    replace(p, value="ENGINE")
                    if p.code == "billing.posting"
                    else replace(p, value=policy)
                    if p.code == "fx.cl_layer_consumption"
                    else p
                    for p in b.policies
                ),
            )
            for b in value.books
        ),
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
        events=tuple(
            sorted(
                (*value.events, extra), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
            )
        ),
    )


@pytest.mark.parametrize("policy", ["FIFO", "PRO_RATA"])
def test_split_gross_layers_monthly_reports_and_close_journals(policy):
    value = split_value(policy)
    digest = value.sha256()
    output = compute(value)
    book = output.books[0]
    assert reevaluate(book.trace) == {n.id: n.value for n in book.trace.nodes}
    from erev_api.domain.reports.split_sources import original_date
    from erev_api.explain.narratives import render

    nodes = {n.id: n for n in book.trace.nodes}
    split_nodes = [n for n in book.trace.nodes if n.formula_id.startswith("fx.split_")]
    assert split_nodes
    for node in split_nodes:
        assert render(node, nodes)
    created = [
        r
        for r in book.fx_layer_movements
        if r.columns["movement_kind"] == "LIABILITY_LAYER_CREATED"
        and "~split~" in r.columns["layer_key"]
    ]
    assert created
    for row in created:
        node = nodes[row.trace_nodes["amount_functional"]]
        assert original_date(node, date.fromisoformat(str(row.columns["effective_date"]))) <= date(
            2026, 9, 16
        )
        assert node.params["original_source_key"]
    restored = [n for n in book.trace.nodes if n.formula_id == "fx.split_restore.v1"]
    assert len(restored) == 2 and restored[0].value == restored[1].value
    assert Fraction(restored[0].value) == Fraction(7214794, 100)
    monthly = book.disclosure_rollforwards
    assert {r.period_key for r in monthly} >= {"FY2026-P08", "FY2026-P09", "FY2026-P10"}
    for row in monthly:
        if row.period_key < "FY2026-P09":
            continue
        suffix = "_functional" if row.view == "FUNCTIONAL" else "_txn"
        for role, lines in row.lines.items():
            assert lines["OTHER"] == 0
            assert lines["CLOSING"] == sum(v for k, v in lines.items() if k != "CLOSING")
            assert lines["CLOSING"] == sum(
                r.columns[role.lower() + suffix]
                for r in book.balances
                if r.period_key == row.period_key
            )
    prior = [output]
    for phase in ("CLOSE_RELEASE", "FX_REMEASUREMENT", "NETTING_RECLASS"):
        prior.append(intent_totals.close_pass(value, prior, phase))
    for period in ("FY2026-P09", "FY2026-P10", "FY2026-P11"):
        for role in ("CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE"):
            for field, suffix in (("amount_functional", "_functional"), ("amount_txn", "_txn")):
                ledger = sum(
                    getattr(line, field)
                    * (1 if line.side == ("C" if role == "CONTRACT_LIABILITY" else "D") else -1)
                    for result in prior
                    for b in result.books
                    for i in b.posting_intents
                    if i.posting_period_key <= period
                    for line in i.lines
                    if line.account_role == role
                )
                assert ledger == sum(
                    r.columns[role.lower() + suffix]
                    for r in book.balances
                    if r.period_key == period
                )
    for row in book.balances:
        if row.period_key >= "FY2026-P09":
            subject = row.subject_key
            target = nodes[f"contract_liability_current_functional:{subject}:{row.period_key}"]
            assert 0 <= Fraction(target.value) * 100 <= row.columns["contract_liability_functional"]
    assert value.sha256() == digest
    assert compute(value).books[0] == book


def test_split_group_report_projection_retains_complete_population(monkeypatch):
    import json

    from erev_api.domain.reports import (
        acquisition_evidence,
        acquisition_groups,
        split_groups,
        tie_outs,
    )
    from erev_api.problems import Problem

    value = split_value()
    output = json.loads(canonical_bytes(compute(value)))
    book = output["books"][0]
    source = {"input_sha256": value.sha256(), "output_sha256": "retained-output"}
    monkeypatch.setattr(acquisition_evidence, "load", lambda *a: (value, output, source))
    entity = uuid4()
    versions = {c: uuid4() for c in value.group.member_contract_keys}
    identities = {c: uuid4() for c in value.group.member_contract_keys}

    def rows(period):
        return [
            tie_outs.BalanceRow(
                identities[c],
                c,
                None,
                entity,
                "US01",
                "EUR",
                versions[c],
                {
                    role: Decimal(
                        next(
                            n["value"]
                            for n in book["trace"]["nodes"]
                            if n["id"] == f"{role}_functional:{c}@US01:{period}"
                        )
                    )
                    for role in tie_outs.ROLLFORWARD_BALANCES
                },
            )
            for c in identities
        ]

    refs = tuple(
        tie_outs.PeriodRef(
            uuid4(),
            p.period_key,
            p.period_key,
            2026,
            int(p.period_key[-2:]),
            None,
            p.start_date,
            p.end_date,
        )
        for p in value.entities[0].periods
        if p.period_key in {"FY2026-P09", "FY2026-P10"}
    )
    closing = rows("FY2026-P10")
    population = {(r.contract_id, r.entity_id): r for r in closing}
    group = split_groups.collect(
        None,
        population,
        value,
        output,
        source,
        book="ASC606",
        entity_id=entity,
        entity_code="US01",
        periods=refs,
        functional=True,
    )
    projected = acquisition_groups.project(
        group,
        opening=rows("FY2026-P08"),
        closing=closing,
        monthly={
            (entity, p.id): {(r.contract_id, r.entity_id): r for r in rows(p.key)} for p in refs
        },
    )
    assert len(projected.group_members) == 3
    assert all(a == 0 for a in projected.lines["OTHER"].values())
    assert all(
        projected.lines["CLOSING"][r] == sum(m.lines["CLOSING"][r] for m in projected.group_members)
        for r in tie_outs.ROLLFORWARD_BALANCES
    )
    assert group.evidence["trace_nodes"]
    with pytest.raises(Problem) as error:
        split_groups.collect(
            None,
            dict(list(population.items())[:-1]),
            value,
            output,
            source,
            book="ASC606",
            entity_id=entity,
            entity_code="US01",
            periods=refs,
            functional=True,
        )

    assert "complete group" in str(error.value.errors)

    from types import SimpleNamespace as NS

    from erev_api.domain.reports import split_cells
    from erev_api.domain.reports.builders import SourceCollector

    collector = SourceCollector()
    collector.record_evidence(split_groups.KEY, {str(group.id): group.evidence})
    params = NS(binding=None, sources=collector)
    key = f"contract:{projected.external_id}:{projected.entity_code}"
    shown = {
        "row_key": key,
        **{
            k.lower(): tie_outs.money(v["contract_liability"], "EUR")
            for k, v in projected.lines.items()
        },
    }
    split_cells.retain(params, [projected], [shown], "contract_liability", [])
    binding = NS(evidence=collector.evidence)
    retained = NS(binding=binding, sources=None)
    split_cells.retain(retained, [projected], [shown], "contract_liability", [])
    session = NS(execute=lambda *a: [(version, uuid4()) for version in versions.values()])
    amount, sources = split_cells.cell(session, retained, key, "reclassifications")
    assert amount == shown["reclassifications"]
    assert sources[0]["object_type"] == split_cells.KIND
    assert any("/trace/" in link["href"] for link in sources[0]["_source_set_links"])
    assert sources[0]["_source_set_entity_ids"] == [str(entity)]

    # Candidate selection is only a filter: original files and full member
    # versions prove the group; a retained rerun must bind exactly the same set.
    seen_sql = []

    def select_versions(statement):
        from sqlalchemy.dialects import postgresql

        seen_sql.append(str(statement.compile(dialect=postgresql.dialect())))
        return NS(scalars=lambda: versions.values())

    original_uow = NS(session=NS(execute=select_versions))
    collected = {}
    split_groups.read(
        original_uow,
        params,
        population,
        {entity: refs},
        "ASC606",
        functional=True,
        groups=collected,
    )
    assert collected == {group.id: group}
    assert "contract_computation.stream_heads" in seen_sql[0]
    assert collector.evidence[split_groups.KEY] == {str(group.id): group.evidence}
    split_groups.read(
        original_uow, retained, population, {entity: refs}, "ASC606", functional=True, groups={}
    )
