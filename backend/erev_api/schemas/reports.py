"""API-R-41 Reports schemas (04 §16.9 API-S-ReportDefinition, API-S-ReportRunCreate,
API-S-ReportRun; SCREENS_B RV-01 to RV-07, RPT-R-01; BUILD_SPEC RPS-2).

[J] L5-2-Q-12: ``output.manifest_href`` names ``GET /report-runs/{id}/output?part=manifest``,
because the job principal owns the manifest file, which ``GET /files/{id}/content`` would refuse.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import BookCode, RunStatus
from erev_api.schemas.common import ActorOut, MoneyOut, ProblemOut, RefOut

__all__ = [
    "EngineReleaseRefOut",
    "IpeLogicOut",
    "ReportColumnOut",
    "ReportDefinitionOut",
    "ReportOutputOut",
    "ReportRefOut",
    "ReportRowOut",
    "ReportRunCreateIn",
    "ReportRunDataOut",
    "ReportRunOut",
    "TieOutResultOut",
]

type OutputFormat = Literal["XLSX", "CSV", "PDF", "JSON", "ZIP"]


class IpeLogicOut(BaseModel):
    """T-RPT-01 ``ipe_logic`` (REQ-RPT-027): source tables, joins, filters, parameters, version."""

    version: int
    source_tables: list[str]
    joins: list[str]
    filters: list[str]
    parameters: list[str]


class ReportDefinitionOut(BaseModel):
    """API-S-ReportDefinition; ``ipe_logic`` is present only for holders of ``report.export``."""

    code: str
    version: int
    name: str
    kind: str
    description: str
    parameters_schema: dict[str, Any]
    output_formats: list[str]
    tie_outs: list[str]
    ipe_logic: IpeLogicOut | None = None


class ReportRunCreateIn(BaseModel):
    """API-S-ReportRunCreate."""

    model_config = ConfigDict(extra="forbid")

    report_code: str = Field(min_length=1)
    report_version: int | None = Field(default=None, ge=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_format: OutputFormat


class ReportRefOut(BaseModel):
    code: str
    version: int
    name: str


class EngineReleaseRefOut(BaseModel):
    engine_version: str
    build_sha: str


class TieOutResultOut(BaseModel):
    """04 API-S-ReportRun ``tie_out_results`` item: the T-RPT-02 item (a table 10-T code and an E-98
    result) and ``difference``, ``actual − expected`` per currency, computed when the run is
    serialised (D-88 L7-3-Q-3); None when the result carries no amounts."""

    code: str
    result: Literal["PASS", "FAIL", "NOT_APPLICABLE"]
    expected: Any = None
    actual: Any = None
    difference: list[MoneyOut] | None


class ReportOutputOut(BaseModel):
    file_id: uuid.UUID
    format: str
    sha256: str
    href: str
    manifest_href: str | None


class ReportRunSourcesOut(BaseModel):
    """API-S-ReportRun ``sources`` (04 §16.9 rev 1.55; frps3b): a summary of the T-RPT-02
    ``source_binding`` — ``bound`` with the bound cutoff and the counts of bound contract versions,
    bound grouping labels and original row keys; ``bound: false`` with null / zero members for a
    live run created before the binding and for an as-locked run (its frozen dataset is its
    source, S15-R-19)."""

    bound: bool
    # Codex 2154 (4): the lifecycle class of the run's sources — ``bound`` (adapter strategy),
    # ``retained`` (no source adapter; the retained output is the same-source evidence),
    # ``as_locked`` (the frozen dataset is the source), ``pending`` (QUEUED / RUNNING: not yet
    # captured), ``failed_without_capture`` (FAILED before capture: a rerun is a NEW evaluation,
    # never a reproduction), ``legacy_unbound`` (SUCCEEDED before source binding: rerun and cell
    # explanation refuse by name).
    kind: str
    strategy: str | None
    cutoff: datetime | None
    versions: int
    labels: int
    members: int
    rows: int
    # The source dimensions the builder's contract leaves OPEN for this report (declared, never
    # silently narrowed; Codex 2202).
    open: list[str]


class ReportRunOut(BaseModel):
    """API-S-ReportRun."""

    id: uuid.UUID
    report_run_no: str
    report: ReportRefOut
    status: RunStatus
    parameters: dict[str, Any]
    entity_scope: list[RefOut]
    book: BookCode | None
    as_of: date | None
    known_at: datetime
    period_lock_id: uuid.UUID | None
    engine_release: EngineReleaseRefOut
    row_count: int | None
    control_totals: dict[str, Any] | None
    tie_out_results: list[TieOutResultOut]
    ledger_heads: dict[str, Any]
    # frps3b (04 §16.9 rev 1.55; S15-R-24): the run's bound sources, summarised.
    sources: ReportRunSourcesOut
    output: ReportOutputOut | None
    problem: ProblemOut | None
    # The run's REPORT_RUN job (T-RPT-02 `job_id`), so a stored run names its own job on every
    # report surface (04 rev 1.17; D-90e L9-PLT-Q-5; SCREENS_B RV-14 rev 1.7).
    job_id: uuid.UUID | None
    run_by: ActorOut
    started_at: datetime | None
    finished_at: datetime | None


class ReportRowOut(BaseModel):
    """One row of ``GET /report-runs/{id}/data``: ``row_key`` and the definition's column fields."""

    model_config = ConfigDict(extra="allow")

    row_key: str


class ReportColumnOut(BaseModel):
    """One column of the run's stored dataset document: the row field ``key``, its header copy and
    its kind (RPT-R-02)."""

    key: str
    header: str
    kind: str


class ReportRunDataOut(BaseModel):
    """``GET /report-runs/{id}/data``: API-S-List of rows plus the additive member ``columns`` on
    every page, the definition's columns copied in order from the stored dataset document (builder
    order, the output order; 04 §16.9; D-88 L7-1-Q-5)."""

    items: list[ReportRowOut]
    next_cursor: str | None
    columns: list[ReportColumnOut]
