"""CSV v2 template ``fx_rates``: an FX rate set version submitted for approval (04 T-IMP-01, NC-19,
T-REF-10 to T-REF-12 ``import_upload_id``; API-R-19; PRD SM-04; 03 REQ-REF-006 CSV channel;
BUILD_SPEC DIN-9, BS3-D-07).

[J] L5-1-Q-22: column ``fx_rate_set_code`` names the rate set (the path member ``{id}`` of ``POST
/fx-rate-sets/{id}/versions``), the coverage members are repeated on each row, and each row is one
entered rate (API-S-FxRate). At commit the version names the upload and is submitted, so its rates
resolve only once the ``FX_RATE_SET_VERSION`` request is approved (CTL-031).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update

from erev_api.db.tables import fx_rate_set, fx_rate_set_version
from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    CsvRow,
    CsvTemplate,
    Plan,
    flatten,
    grouped,
    row_model,
    unflatten,
)
from erev_api.domain.reference.commands import (
    create_fx_rate_set_version,
    submit_fx_rate_set_version,
)
from erev_api.enums import SourceObjectType
from erev_api.problems import Problem
from erev_api.schemas.currencies import FxRateIn, FxRateSetVersionCommandIn, FxRateSetVersionIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "ROW_MODEL", "TEMPLATE", "FxRatesIn"]

CODE: Final = "fx_rates"
SET_UNKNOWN: Final = "No FX rate set has the code {code}."
SUBMIT_COMMENT: Final = "Rates of import {import_no}"
_LINES: Final = frozenset({"lines"})


class FxRatesIn(BaseModel):
    """A version of one rate set with its entered rates (L5-1-Q-22)."""

    model_config = ConfigDict(extra="forbid")

    fx_rate_set_code: str
    coverage_from: date
    coverage_to: date
    lines: list[FxRateIn]


COLUMNS: Final = tuple(flatten(FxRatesIn))
ROW_MODEL: Final = row_model("CsvFxRatesRow", COLUMNS)
# The rows of one rate set and coverage make one version; every header member is of its key, so
# its rows repeat nothing (05 IPL-05 rev 1.210).
KEY: Final = ("fx_rate_set_code", "coverage_from", "coverage_to")


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per (set, coverage) in worksheet order."""
    return [
        Plan(
            key=code,
            rows=tuple(members),
            body={
                **unflatten(members[0].normalized, skip=_LINES),
                "lines": [unflatten(row.normalized).get("lines", {}) for row in members],
            },
        )
        for (code, _, _), members in grouped(rows, KEY).items()
    ]


def _no_version_check(row_version: int) -> None:
    del row_version


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """A DRAFT version with the rates; at commit it names the upload and is submitted."""
    body = FxRatesIn.model_validate(dict(plan.body))
    session = uow.session
    found = session.execute(
        select(fx_rate_set.c.id).where(fx_rate_set.c.code == body.fx_rate_set_code)
    ).scalar_one_or_none()
    if found is None:
        raise Problem("validation-failed", SET_UNKNOWN.format(code=body.fx_rate_set_code))
    created = create_fx_rate_set_version(
        uow,
        set_id=UUID(str(found)),
        body=FxRateSetVersionIn(
            coverage_from=body.coverage_from, coverage_to=body.coverage_to, rates=body.lines
        ),
    )
    version_id = created.id
    if not context.dry_run:
        session.execute(
            update(fx_rate_set_version)
            .where(fx_rate_set_version.c.id == version_id)
            .values(
                import_upload_id=context.import_upload_id,
                row_version=fx_rate_set_version.c.row_version + 1,
            )
        )
        submit_fx_rate_set_version(
            uow,
            version_id=version_id,
            body=FxRateSetVersionCommandIn(
                comment=SUBMIT_COMMENT.format(import_no=context.import_no)
            ),
            check_version=_no_version_check,
        )
    # A spot rate is keyed by its day, a closing or average rate by its period (T-REF-12).
    entered: dict[tuple[str, str, str], UUID] = {
        (
            rate.base_currency,
            rate.quote_currency,
            rate.period_key or rate.effective_date.isoformat(),
        ): rate.id
        for rate in created.rates
        if not rate.is_derived
    }
    applied = Applied()
    for row, line in zip(plan.rows, body.lines, strict=True):
        day = None if line.effective_date is None else line.effective_date.isoformat()
        rate_id = entered[(line.base_currency, line.quote_currency, line.period_key or day or "")]
        applied.targets.append(("fx_rate", rate_id))
        applied.row_targets[row.id] = [("fx_rate", rate_id)]
    return applied


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.FX_RATE,
    target_type="fx_rate",
    key_column="fx_rate_set_code",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    group_key=KEY,
)
