"""RPT-31: period loss tests from immutable, report-bound calculation versions.

No loss is reconstructed from today's estimates or policy. Trace coverage distinguishes an
untested contract from an older version whose loss tests were never persisted. Foreign views
read the original independent functional test and retained reporting-currency rates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Final
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    calc_trace,
    contract,
    contract_version_balance,
    estimate,
    estimate_version,
    loss_provision_eac,
    loss_provision_version,
    obligation,
)
from erev_api.domain.reports import reporting_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.out_of_period_register import refuse_locked_source
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.explain import store
from erev_api.uow import UnitOfWork
from erev_engine.stages.s01_canonicalize import encode_key
from erev_engine.trace import Trace

CODE: Final = "loss_provision_register"
MONEY: Final = (
    "expected_consideration",
    "expected_total_costs",
    "costs_to_date",
    "revenue_to_date",
    "expected_margin",
    "provision_balance",
    "provision_movement",
)
COLUMNS: Final = (
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("unit", "Unit", "text"),
    Column("measurement_basis", "Basis", "text"),
    Column("eac_version_no", "EAC version", "integer"),
    Column("eac_versions", "EAC contributors", "codes"),
    Column("currency", "Currency", "code"),
    *(
        Column(key, label, "money")
        for key, label in zip(
            MONEY,
            (
                "Expected consideration",
                "Expected total costs",
                "Costs to date",
                "Revenue to date",
                "Expected margin",
                "Provision balance",
                "Movement in period",
            ),
            strict=True,
        )
    ),
)


def check_coverage(
    trace: Trace | None, *, external_id: str, period_key: str, rows: Sequence[Mapping[str, Any]]
) -> None:
    """Require every period loss test in the selected member's trace to have a stored row."""
    if trace is None:
        raise tie_outs.invalid("period_key", "The selected version has no loss-test trace.")
    prefixes = (
        f"loss_provision_required:{external_id}:{period_key}",
        f"loss_provision_required:{encode_key(external_id)}/",
    )
    expected = {
        node.id
        for node in trace.nodes
        if node.measure == "loss_provision_required"
        and (node.id == prefixes[0] or node.id.startswith(prefixes[1]))
        and node.id.endswith(f":{period_key}")
    }
    actual = {str(row["trace_nodes"].get("loss_provision_required")) for row in rows}
    if expected != actual:
        raise tie_outs.invalid(
            "period_key", "The selected version has incomplete stored loss tests for this period."
        )


def dataset_rows(found: Sequence[Mapping[str, Any]]) -> ReportData:
    rows: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Decimal]] = {key: {} for key in MONEY[-2:]}
    for source in sorted(found, key=lambda r: (r["external_id"], r["obligation_key"] or "")):
        currency = str(source["currency"]).strip()
        key = (
            f"contract:{source['external_id']}"
            if source["unit"] == "CONTRACT"
            else f"obligation:{source['external_id']}:{source['obligation_key']}"
        )
        contributors = source["eac_versions"]
        rows.append(
            {
                "row_key": key,
                "contract_external_id": source["external_id"],
                "obligation_key": source["obligation_key"],
                "unit": "Contract" if source["unit"] == "CONTRACT" else "Obligation",
                "measurement_basis": {"ASC_605_35": "ASC 605-35", "IAS_37": "IAS 37"}[
                    source["measurement_basis"]
                ],
                "eac_version_no": contributors[0][1] if len(contributors) == 1 else None,
                "eac_versions": [f"{code}@v{number}" for code, number in contributors],
                "currency": currency,
                **{field: tie_outs.money(Decimal(source[field]), currency) for field in MONEY},
            }
        )
        for field in totals:
            tie_outs.add(totals[field], currency, Decimal(source[field]))
    return ReportData(
        columns=COLUMNS,
        rows=tuple(rows),
        control_totals={
            "row_count": len(rows),
            **{key: tie_outs.by_currency(value) for key, value in totals.items()},
        },
        tie_out_results=(),
    )


FUNCTIONAL_FIELDS = {
    "expected_consideration": "loss_expected_consideration_functional",
    "expected_total_costs": "loss_expected_total_costs_functional",
    "costs_to_date": "loss_costs_to_date_functional",
    "revenue_to_date": "loss_revenue_to_date_functional",
    "expected_margin": "expected_margin_functional",
    "provision_balance": "loss_provision_required_functional",
    "provision_movement": "provision_movement_functional",
}
REPORTING_KEY = "loss_register_reporting_v1"


def project_functional(
    row: Mapping[str, Any], trace: Trace | None, currency: str
) -> dict[str, Any]:
    if trace is None:
        raise tie_outs.invalid("currency_view", "Functional loss test has no original trace.")
    original_id = row["trace_nodes"]["loss_provision_required"]
    tail = original_id.removeprefix("loss_provision_required:")
    nodes = {n.id: n for n in trace.nodes}
    original = nodes.get(original_id)
    if original is None or Decimal(original.value) != Decimal(row["provision_balance"]):
        raise tie_outs.invalid(
            "currency_view", "Original loss provision differs from its stored test."
        )
    values = {}
    for field, measure in FUNCTIONAL_FIELDS.items():
        node = nodes.get(f"{measure}:{tail}")
        if node is None or node.currency != currency or not Decimal(node.value).is_finite():
            raise tie_outs.invalid(
                "currency_view", "Original functional loss test is unavailable or inconsistent."
            )
        values[field] = Decimal(node.value)
    return {
        **row,
        **values,
        "currency": currency,
        "functional_trace_node_id": f"loss_provision_required_functional:{tail}",
    }


def sources(
    session: Session, params: ReportParams, *, tenant_id: UUID | None = None
) -> list[dict[str, Any]]:
    refuse_locked_source(params)
    book = tie_outs.book_of(session, params)
    entities = tie_outs.entities(session, params.entity_ids, params=params)
    calendars = tie_outs.calendars(session, entities, params=params)
    periods = {e.id: tie_outs.period_of(params, calendars[e.id], e) for e in entities}
    functional = {e.id: e.functional_currency for e in entities}
    translations = {}
    view = str(params.parameters.get("currency_view", "transaction"))
    if view == "reporting" and (params.binding is None or REPORTING_KEY in params.binding.evidence):
        if params.binding is not None:
            tenant_id = UUID(params.binding.evidence[REPORTING_KEY])
        elif tenant_id is None and params.requester is not None:
            tenant_id = params.requester.principal.tenant_id
        if tenant_id is None:
            raise tie_outs.invalid("currency_view", "Reporting loss tests require tenant context.")
        tie_outs.record_evidence(params, REPORTING_KEY, str(tenant_id))
        for entity in entities:
            for kind in ("closing", "average"):
                translations[(entity.id, kind)] = reporting_currency.rates_for_period(
                    session,
                    params,
                    tenant_id=tenant_id,
                    entities=(entity,),
                    periods={entity.id: periods[entity.id]},
                    rate_type=kind,
                    evidence_key=f"loss_reporting_v1:{entity.id}:{periods[entity.id].key}:{kind}",
                )
    cutoff = tie_outs.cutoff_for(session, params)
    balance = contract_version_balance.c
    owners = list(
        session.execute(
            select(
                balance.contract_id,
                balance.contract_version_id,
                balance.entity_id,
                contract.c.external_id,
            )
            .join(
                contract,
                and_(
                    contract.c.tenant_id == balance.tenant_id, contract.c.id == balance.contract_id
                ),
            )
            .where(
                balance.entity_id.in_(params.entity_ids),
                contract.c.contracting_entity_id == balance.entity_id,
                tie_outs.rows_read(
                    session,
                    params,
                    balance.contract_id,
                    balance.contract_version_id,
                    book_code=book,
                    cutoff=cutoff,
                ),
            )
        ).mappings()
    )
    versions = {row["contract_version_id"] for row in owners}
    loss = loss_provision_version.c
    stored = (
        list(
            session.execute(
                select(loss_provision_version, obligation.c.obligation_key)
                .outerjoin(
                    obligation,
                    and_(
                        obligation.c.tenant_id == loss.tenant_id,
                        obligation.c.id == loss.obligation_id,
                    ),
                )
                .where(
                    loss.contract_version_id.in_(versions),
                    loss.entity_id.in_(params.entity_ids),
                    loss.book_code == book,
                    loss.period_key.in_({p.key for p in periods.values()}),
                    loss.as_of.in_({p.end for p in periods.values()}),
                )
            ).mappings()
        )
        if versions
        else []
    )
    lineage: dict[UUID, list[tuple[str, int]]] = {}
    if stored:
        for loss_id, estimate_id, code, number in session.execute(
            select(
                loss_provision_eac.c.loss_provision_version_id,
                estimate.c.id,
                estimate.c.element_code,
                estimate_version.c.version_no,
            )
            .join(
                estimate_version,
                and_(
                    estimate_version.c.tenant_id == loss_provision_eac.c.tenant_id,
                    estimate_version.c.id == loss_provision_eac.c.estimate_version_id,
                ),
            )
            .join(
                estimate,
                and_(
                    estimate.c.tenant_id == estimate_version.c.tenant_id,
                    estimate.c.id == estimate_version.c.estimate_id,
                ),
            )
            .where(loss_provision_eac.c.loss_provision_version_id.in_([r["id"] for r in stored]))
        ):
            label = tie_outs.label_for(params, "loss.estimate", estimate_id, str(code))
            lineage.setdefault(loss_id, []).append((str(label), int(number)))
    by_owner: dict[tuple[UUID, UUID, UUID, str], list[dict[str, Any]]] = {}
    for stored_row in stored:
        identity = (
            stored_row["contract_id"],
            stored_row["contract_version_id"],
            stored_row["entity_id"],
            stored_row["period_key"],
        )
        by_owner.setdefault(identity, []).append(dict(stored_row))
    traces = {version: store.load_trace(session, version) for version in versions}
    found: list[dict[str, Any]] = []
    for owner in owners:
        period = periods[owner["entity_id"]]
        identity = (
            owner["contract_id"],
            owner["contract_version_id"],
            owner["entity_id"],
            period.key,
        )
        selected = [r for r in by_owner.get(identity, []) if r["as_of"] == period.end]
        external = str(
            tie_outs.label_for(
                params, "loss.contract", owner["contract_id"], str(owner["external_id"])
            )
        )
        check_coverage(
            traces[owner["contract_version_id"]],
            external_id=external,
            period_key=period.key,
            rows=selected,
        )
        for row in selected:
            if not row["in_scope"]:
                continue
            if (
                view != "transaction"
                and str(row["currency"]).strip() != functional[owner["entity_id"]]
            ):
                row = project_functional(
                    row, traces[owner["contract_version_id"]], functional[owner["entity_id"]]
                )
            if (
                params.parameters.get("only_with_provision", False)
                and row["provision_balance"] == 0
            ):
                continue
            if translations:
                row = {
                    **row,
                    "reporting_source": {
                        "functional_currency": str(row["currency"]).strip(),
                        "functional_provision": str(row["provision_balance"]),
                        "rates": [
                            translations[(owner["entity_id"], kind)].rates[owner["entity_id"]]
                            for kind in ("closing", "average")
                        ],
                    },
                }
                row = {
                    **row,
                    **{
                        field: translations[
                            (
                                owner["entity_id"],
                                "average" if field == "provision_movement" else "closing",
                            )
                        ].amount(owner["entity_id"], Decimal(row[field]))
                        for field in MONEY
                    },
                    "currency": translations[(owner["entity_id"], "closing")].currency,
                }
            key = tie_outs.label_for(
                params, "loss.obligation", row["obligation_id"], row["obligation_key"]
            )
            found.append(
                {
                    **row,
                    "external_id": external,
                    "obligation_key": key,
                    "eac_versions": sorted(lineage.get(row["id"], [])),
                }
            )
    return found


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    return dataset_rows(sources(uow.session, params, tenant_id=uow.principal.tenant_id))


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[Mapping[str, str], list[dict[str, Any]]]:
    """Explain the original register's provision through its exact immutable period test."""
    if column_key != "provision_balance":
        raise tie_outs.invalid("column_key", "Only the provision balance has an Explain drill.")
    for source in sources(session, params):
        row = dataset_rows([source]).rows[0]
        if row["row_key"] == row_key:
            value = tie_outs.money(Decimal(source[column_key]), str(source["currency"]).strip())
            href = f"/api/v1/explain/loss_provision_version/{source['id']}/{column_key}"
            if source.get("functional_trace_node_id"):
                trace_id = session.execute(
                    select(calc_trace.c.id).where(
                        calc_trace.c.contract_version_id == source["contract_version_id"]
                    )
                ).scalar_one()
                href = (
                    f"/trace/{trace_id}?node={quote(source['functional_trace_node_id'], safe='')}"
                )
            details = []
            if source.get("functional_trace_node_id"):
                details.append(
                    "Independent functional test: historical actual costs/revenue "
                    "and assessment-date remaining forecasts."
                )
            if source.get("reporting_source"):
                projection = source["reporting_source"]
                details.append(
                    f"Functional provision: {projection['functional_provision']} "
                    f"{projection['functional_currency']}."
                )
                details.extend(
                    f"Retained {rate['rate_type']} rate {rate['period_key']}: "
                    f"{rate['base_currency']}/{rate['quote_currency']} at {rate['rate']}; "
                    f"version {rate['version_id']}."
                    for rate in projection["rates"]
                )
            return value, [
                {
                    "object_type": "loss_provision_version",
                    "id": source["id"],
                    "measure": column_key,
                    "value": value,
                    "href": href,
                    **(
                        {
                            "_source_set_details": details,
                            "_source_set_links": [
                                {"label": "Original measured provision", "href": href}
                            ],
                            "_entity_id": str(source["entity_id"]),
                            "_source_set_entity_ids": [str(source["entity_id"])],
                        }
                        if details
                        else {}
                    ),
                }
            ]
    raise tie_outs.invalid("row_key", "The bound loss register has no such row.")
