"""API-R-49 explain schemas (04 §15.3 API-R-49, §16.11 API-S-Explain, §16.14 API-S-CalcTrace,
T-ENG-03; dev-guide DG-KRN-EXP-06; SCREENS R-19 to R-21; BUILD_SPEC CTR-19)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from erev_api.enums import BookCode
from erev_api.schemas.common import ContextOut, MoneyOut, RefOut

__all__ = [
    "CalcTraceOut",
    "EstimateVersionPairOut",
    "ExplainCellContributorOut",
    "ExplainCellEntityPartOut",
    "ExplainCellOut",
    "ExplainDrillOut",
    "ExplainHistoryItemOut",
    "ExplainNodeInputOut",
    "ExplainNodeOut",
    "ExplainObjectOut",
    "ExplainObjectType",
    "ExplainOut",
    "ExplainSourceInputOut",
    "ExplainSourceRowOut",
    "ExplainVerifyOut",
]

# 04 §16.11: the object types of ``GET /explain/{object_type}/{id}/{measure}``.
ExplainObjectType = Literal[
    "contract_version",
    "obligation",
    "obligation_version",
    "schedule_line",
    "subledger_line",
    "journal_line",
    "contract_version_balance",
    "loss_provision_version",
]


class ExplainCellContributorOut(BaseModel):
    """One record behind a report cell (04 §16.11 ``GET /explain/report-runs/{id}/cell``)."""

    object_type: str
    id: uuid.UUID
    measure: str
    value: MoneyOut
    href: str


class ExplainCellContributorsOut(BaseModel):
    """API-S-List of contributors; every contributor is returned, so ``next_cursor`` is null."""

    items: list[ExplainCellContributorOut]
    next_cursor: str | None = None


class ExplainCellEntityPartOut(BaseModel):
    """The part of a report cell held by records of ONE entity the caller's entity scope does not
    reach (04 §16.11 rev 1.239; the supervisor's ruling of 2026-10-01): the entity's reference
    and the sum of those records' values — no record, no id of a record, no address, no count."""

    entity: RefOut
    value: MoneyOut


class ExplainCellOut(BaseModel):
    """``{value: Money, contributors: API-S-List, other_entities}`` of one report cell
    (REQ-RPT-017; SB-R-07). ``contributors`` names the records the caller's entity scope reaches,
    ``other_entities`` states the rest as one sum per entity in entity-code order: together they
    are every contributor of the cell (04 §16.11 rev 1.239)."""

    value: MoneyOut
    contributors: ExplainCellContributorsOut
    other_entities: list[ExplainCellEntityPartOut]


class ExplainObjectOut(BaseModel):
    """``{type, id, measure, period_key}``: the figure explained."""

    type: ExplainObjectType
    id: uuid.UUID
    measure: str
    period_key: str | None


class ExplainNodeInputOut(BaseModel):
    """A node-id input."""

    node_id: str


class ExplainSourceInputOut(BaseModel):
    """A source reference input; ``href`` is null when no API route reads the reference."""

    ref_type: str
    ref_id: str
    label: str
    href: str | None


class ExplainNodeOut(BaseModel):
    """One stored trace node (T-ENG-03), values as stored (DG-KRN-EXP-03)."""

    id: str
    measure: str
    value: str
    currency: str | None
    formula_id: str
    params: dict[str, str]
    rounding_residue: str | None
    inputs: list[ExplainNodeInputOut | ExplainSourceInputOut]


class EstimateVersionPairOut(BaseModel):
    """The estimate versions pinned before and after the change."""

    before: str | None
    after: str | None


class ExplainHistoryItemOut(BaseModel):
    """A contract version in which the figure changed (SCREENS R-19)."""

    contract_version_id: uuid.UUID
    version_no: int
    known_at: datetime
    value: str
    delta: str | None
    cause: str
    estimate_version_pair: EstimateVersionPairOut | None
    origin_period_key: str | None


class ExplainSourceRowOut(BaseModel):
    import_upload_id: uuid.UUID
    sheet: str | None
    row_number: int
    href: str


class ExplainDrillOut(BaseModel):
    """Drill links of the figure (REQ-RPT-017)."""

    contract_href: str | None
    obligation_href: str | None
    schedule_lines_href: str | None
    subledger_lines_href: str | None
    source_rows: list[ExplainSourceRowOut]


class ExplainOut(BaseModel):
    """API-S-Explain: ``value`` is Money for a figure with a currency, else a decimal string."""

    object: ExplainObjectOut
    value: MoneyOut | str
    context: ContextOut
    calc_trace_id: uuid.UUID
    engine_version: str
    root_node_id: str
    nodes: list[ExplainNodeOut]
    narrative: list[str]
    history: list[ExplainHistoryItemOut]
    drill: ExplainDrillOut


class ExplainVerifyOut(BaseModel):
    """``POST /explain/{object_type}/{id}/{measure}/verify`` (SCREENS R-20)."""

    recomputed_value: str
    stored_value: str
    matches: bool


class CalcTraceOut(BaseModel):
    """API-S-CalcTrace: the T-ENG-03 row as stored (SCREENS R-21)."""

    id: uuid.UUID
    contract_version_id: uuid.UUID
    combination_group_id: uuid.UUID
    book: BookCode
    format_version: int
    engine_version: str
    trace_sha256: str
    node_count: int
    root_measures: dict[str, str]
    trace: dict[str, Any]
