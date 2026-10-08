"""CSV v2 template ``estimates``: DRAFT estimate versions of estimated elements (04 T-IMP-01, NC-19,
T-CON-12, T-CON-13, §15.3 API-R-32, §16.14 estimates; PRD SM-04; 03 REQ-DAT-004, REQ-DAT-012;
BUILD_SPEC DIN-9, CTR-12; D-86).

[J] L7-4-Q-2: the commands are ``POST /contracts/{id}/estimates`` (API-S EstimateCreateIn) and
``POST /estimates/{id}/versions`` (EstimateVersionCreateIn), so the rows of one (``contract``,
``element_code``, ``effective_date``) are one version:

- column ``contract`` names the contract by its external id (the path member ``{id}``), and
  ``element_code`` names the element (the path member ``{id}`` of the versions command);
- the element members of EstimateCreateIn and the version members of EstimateVersionCreateIn are
  repeated on each row of the version;
- each row carries at most one outcome of the version's ``scenarios`` (``lines.outcome``,
  ``lines.amount``, ``lines.probability``), as ``fx_rates`` and ``ssp_values`` carry their arrays in
  ``lines``; a version without scenarios leaves them blank;
- ``parameters.*`` holds every member of the T-CON-13 parameter schemas of the E-09 kinds, and the
  kind's schema validates the members sent (``schemas.db_json.EstimateParameters``);
- ``target_obligation_keys`` (an array of strings) and ``constraint_checklist`` (a free-form object)
  have no single-row form and are not columns (L5-1-Q-4); an element allocated to obligations is
  created through the API, and its versions then import by element code.

A file states ONE version of an element. One version of an element is prepared at a time (04
T-CON-13, §16.14 rev 1.241; PRD SM-04, ERR-93; item EST-ONE-OPEN-VERSION-1) and a version an
import creates stays DRAFT, so rows of one element under two effective dates are two versions and
the second is refused as the API refuses it — as is a file that names an element whose version is
DRAFT or SUBMITTED. The dry run reports the refusal by row (``IMPORT_PROCESSING_FAILED``), and a
file with such a row is not applied.

The apply runs the CTR-12 commands as the import principal, so the findings and refusals equal the
API's. An element absent from the contract is created with the row's element members. An existing
element keeps its members (IM-A); a row naming another ``estimate_kind`` is refused, and a
different ``method`` meets ``ESTIMATE_METHOD_LOCKED``. The version stays DRAFT and follows the
``ESTIMATE_VERSION`` lifecycle (submission, approval, ``ESTIMATE_CHANGED``), so an import changes no
revenue and appends no event. [J] L7-4-Q-3: E-39 has no estimate literal and only lane L7-6 may add
a revision (D-87), so the source records take ``CONTRACT_SETUP_ROW``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, estimate, estimate_version, obligation
from erev_api.domain.imports.csv_v2 import recorded
from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    CsvRow,
    CsvTemplate,
    Plan,
    Repeated,
    flatten,
    grouped,
    header_cells,
    row_model,
    unflatten,
)
from erev_api.enums import EstimateKind, EstimateMethod, SourceObjectType
from erev_api.problems import Problem
from erev_api.schemas.db_json import EstimateParameters
from erev_api.schemas.estimates import (
    AllocationTarget,
    Direction,
    EstimateCreateIn,
    EstimateVersionCreateIn,
    ScenarioIn,
    VcElementType,
)

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "COLUMNS",
    "CROSS_RULE",
    "ROW_MODEL",
    "TEMPLATE",
    "EstimateParametersRowIn",
    "EstimatesIn",
]

CODE: Final = "estimates"
KIND_DIFFERS: Final = (
    "Element {code} of contract {contract} is a {stored} estimate; the file names {named}."
)
ELEMENT_MEMBERS: Final = (
    "estimate_kind",
    "element_code",
    "obligation_key",
    "vc_element_type",
    "direction",
    "method",
    "allocation_target",
    "allocation_criteria_evidence",
)
VERSION_MEMBERS: Final = (
    "method",
    "effective_date",
    "unconstrained_amount",
    "most_conservative_amount",
    "constrained_amount",
    "rate",
    "expected_total_amount",
    "expected_quantity",
    "amortization_months",
    "currency",
    "rationale",
    "judgement_record_id",
)
_LINES: Final = frozenset({"lines"})


class ScenarioRowIn(BaseModel):
    """At most one outcome of the version's scenario table per row (L7-4-Q-2)."""

    model_config = ConfigDict(extra="forbid")

    outcome: str | None = None
    amount: str | None = None
    probability: str | None = None


class EstimateParametersRowIn(BaseModel):
    """Every member of the T-CON-13 parameter schemas (``db_json.ESTIMATE_PARAMETERS``); the members
    sent go to the kind's schema, which refuses the members of other kinds."""

    model_config = ConfigDict(extra="forbid")

    no_change_attestation: bool | None = None
    refund_liability_target: str | None = None
    carrying_cost_per_unit: str | None = None
    recovery_cost_per_unit: str | None = None
    window_end_date: date | None = None
    usage_period_start_date: date | None = None
    usage_period_end_date: date | None = None
    uninstalled_materials_cost: str | None = None
    grant_date: date | None = None
    grant_date_fair_value: str | None = None
    vesting_probable: bool | None = None
    expected_forfeiture_ratio: str | None = None


class EstimatesIn(BaseModel):
    """One DRAFT version of one element of one contract, with the element's members (L7-4-Q-2)."""

    model_config = ConfigDict(extra="forbid")

    contract: str
    estimate_kind: EstimateKind
    element_code: str
    obligation_key: str | None = None
    vc_element_type: VcElementType | None = None
    direction: Direction | None = None
    method: EstimateMethod
    allocation_target: AllocationTarget = "CONTRACT"
    allocation_criteria_evidence: str | None = None
    effective_date: date
    parameters: EstimateParametersRowIn | None = None
    unconstrained_amount: str | None = None
    most_conservative_amount: str | None = None
    constrained_amount: str | None = None
    rate: str | None = None
    expected_total_amount: str | None = None
    expected_quantity: str | None = None
    amortization_months: int | None = None
    currency: str | None = None
    rationale: str
    judgement_record_id: uuid.UUID | None = None
    lines: list[ScenarioRowIn]


COLUMNS: Final = tuple(flatten(EstimatesIn))
ROW_MODEL: Final = row_model("CsvEstimatesRow", COLUMNS)
CROSS_RULE: Final = recorded.contract_findings
# The rows of one contract, element code and effective date make one version; the element's and
# the version's members — its amounts among them — are read from the first of those rows, so a
# later row states them alike or not at all (05 IPL-05 rev 1.210).
KEY: Final = ("contract", "element_code", "effective_date")
REPEATS: Final = (
    Repeated("estimate", KEY, header_cells(COLUMNS, KEY), ("contract", "element_code")),
)


def _scenario(values: Mapping[str, Any]) -> dict[str, Any]:
    return dict(unflatten(values).get("lines", {}))


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per (contract, element code, effective date) in worksheet order; the key is
    ``<contract> / <element code>``, which names no contract, so the diff lists no contract."""
    return [
        Plan(
            key=f"{contract} / {code}",
            rows=tuple(members),
            body={
                **unflatten(members[0].normalized, skip=_LINES),
                "lines": [line for row in members if (line := _scenario(row.normalized))],
            },
        )
        for (contract, code, _), members in grouped(rows, KEY).items()
    ]


def _members(body: EstimatesIn, names: Sequence[str]) -> dict[str, Any]:
    return {name: getattr(body, name) for name in names if getattr(body, name) is not None}


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """``create_estimate`` when the element is absent, then ``create_version`` (module
    docstring)."""
    from erev_api.domain.contracts import estimates, repo

    del context
    body = EstimatesIn.model_validate(dict(plan.body))
    session = uow.session
    found = repo.contract_by_external_id(session, body.contract)
    if found is None:
        raise Problem("validation-failed", recorded.NOT_FOUND.format(contract=body.contract))
    contract_id = UUID(str(found["id"]))
    applied = Applied()
    element = (
        session.execute(
            select(estimate.c.id, estimate.c.estimate_kind).where(
                estimate.c.contract_id == contract_id,
                estimate.c.element_code == body.element_code,
            )
        )
        .mappings()
        .one_or_none()
    )
    if element is None:
        created = estimates.create_estimate(
            uow,
            contract_id=contract_id,
            body=EstimateCreateIn.model_validate(_members(body, ELEMENT_MEMBERS)),
        )
        estimate_id = created.id
        applied.targets.append(("estimate", estimate_id))
    else:
        estimate_id = UUID(str(element["id"]))
        stored = _text(element["estimate_kind"])
        if stored != body.estimate_kind.value:
            raise Problem(
                "validation-failed",
                KIND_DIFFERS.format(
                    code=body.element_code,
                    contract=body.contract,
                    stored=stored,
                    named=body.estimate_kind.value,
                ),
            )
    parameters = {} if body.parameters is None else body.parameters.model_dump(exclude_none=True)
    version = estimates.create_version(
        uow,
        estimate_id=estimate_id,
        body=EstimateVersionCreateIn.model_validate(
            {
                **_members(body, VERSION_MEMBERS),
                "parameters": parameters,
                "scenarios": [
                    ScenarioIn.model_validate(line.model_dump(exclude_none=True))
                    for line in body.lines
                ],
            }
        ),
    )
    applied.targets.append(("estimate_version", version.id))
    for row in plan.rows:
        applied.row_targets[row.id] = [("estimate_version", version.id)]
    return applied


MONEY_COLUMNS: Final = (
    "unconstrained_amount",
    "most_conservative_amount",
    "constrained_amount",
    "expected_total_amount",
)
EXACT_COLUMNS: Final = ("rate", "expected_quantity")


def _number(value: Any, scale: int | None = None) -> str | None:
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        number = Decimal(str(value))
        if scale is not None:
            number = number.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
        return format(number.normalize(), "f") if number else "0"


def _financial_values(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **{name: _number(values.get(name), 4) for name in MONEY_COLUMNS},
        **{name: _number(values.get(name), 18) for name in EXACT_COLUMNS},
        "amortization_months": values.get("amortization_months"),
        "parameters": dict(values.get("parameters") or {}),
        "scenarios": [
            {
                "outcome": line["outcome"],
                "amount": _number(line["amount"]),
                "probability": _number(line.get("probability")),
            }
            for line in values.get("scenarios") or []
        ],
    }


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """CTL-002: independently read saved estimate inputs and complete scenario evidence."""
    from erev_api.domain.contracts import estimates as estimate_commands

    del context
    source = EstimatesIn.model_validate(
        {
            **unflatten(plan.rows[0].normalized, skip=_LINES),
            "lines": [line for row in plan.rows if (line := _scenario(row.normalized))],
        }
    )
    currency = (
        source.currency
        or str(
            session.execute(
                select(contract.c.transaction_currency).where(
                    contract.c.external_id == source.contract
                )
            ).scalar_one()
        ).strip()
    )
    obligation_id = None
    if source.obligation_key is not None:
        obligation_id = session.execute(
            select(obligation.c.id)
            .join(
                contract,
                and_(
                    contract.c.tenant_id == obligation.c.tenant_id,
                    contract.c.id == obligation.c.contract_id,
                ),
            )
            .where(
                contract.c.external_id == source.contract,
                obligation.c.obligation_key == source.obligation_key,
            )
        ).scalar_one()
    # An existing element keeps omitted metadata; explicit file values still must agree.
    inherited: Mapping[str, Any] = {}
    if not any(kind == "estimate" for kind, _ in applied.targets):
        inherited = dict(
            session.execute(
                select(estimate)
                .join(
                    contract,
                    and_(
                        contract.c.tenant_id == estimate.c.tenant_id,
                        contract.c.id == estimate.c.contract_id,
                    ),
                )
                .where(
                    contract.c.external_id == source.contract,
                    estimate.c.element_code == source.element_code,
                )
            )
            .mappings()
            .one()
        )
        if source.obligation_key is None:
            obligation_id = inherited.get("obligation_id")
    values = source.model_dump(mode="json")
    values["parameters"] = EstimateParameters.validate(
        source.estimate_kind,
        {} if source.parameters is None else source.parameters.model_dump(exclude_none=True),
    )
    values["scenarios"] = values.pop("lines")
    expected = {
        "versions": [
            {
                "contract": source.contract,
                "element_code": source.element_code,
                "estimate_kind": source.estimate_kind.value,
                "method": source.method.value,
                "vc_element_type": source.vc_element_type or inherited.get("vc_element_type"),
                "direction": source.direction
                or inherited.get("direction")
                or estimate_commands._default_direction(
                    source.estimate_kind, source.vc_element_type
                ),
                "allocation_target": source.allocation_target
                if plan.rows[0].normalized.get("allocation_target") is not None
                else inherited.get("allocation_target", source.allocation_target),
                "obligation_id": None if obligation_id is None else str(obligation_id),
                "effective_date": source.effective_date.isoformat(),
                "currency": currency,
                **_financial_values(values),
            }
        ]
    }
    rows = session.execute(
        select(
            estimate_version,
            contract.c.external_id.label("contract"),
            estimate.c.element_code,
            estimate.c.estimate_kind,
            estimate.c.method,
            estimate.c.vc_element_type,
            estimate.c.direction,
            estimate.c.allocation_target,
            estimate.c.obligation_id,
        )
        .select_from(
            estimate_version.join(
                estimate,
                and_(
                    estimate.c.tenant_id == estimate_version.c.tenant_id,
                    estimate.c.id == estimate_version.c.estimate_id,
                ),
            ).join(
                contract,
                and_(
                    contract.c.tenant_id == estimate.c.tenant_id,
                    contract.c.id == estimate.c.contract_id,
                ),
            )
        )
        .where(
            estimate_version.c.id.in_(
                [key for kind, key in applied.targets if kind == "estimate_version"]
            ),
        )
    ).mappings()
    actual = {
        "versions": [
            {
                "contract": row["contract"],
                "element_code": row["element_code"],
                "estimate_kind": str(row["estimate_kind"]),
                "method": str(row["method"]),
                "vc_element_type": row["vc_element_type"],
                "direction": row["direction"],
                "allocation_target": row["allocation_target"],
                "obligation_id": None
                if row["obligation_id"] is None
                else str(row["obligation_id"]),
                "effective_date": row["effective_date"].isoformat(),
                "currency": str(row["currency"]).strip(),
                **_financial_values(dict(row)),
            }
            for row in rows
        ]
    }
    return expected, actual


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.CONTRACT_SETUP_ROW,
    target_type="estimate_version",
    key_column="contract",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    group_key=KEY,
    repeats=REPEATS,
    reconcile_amounts=reconcile_amounts,
)
