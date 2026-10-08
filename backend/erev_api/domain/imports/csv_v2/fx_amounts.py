"""Independent source-to-storage reconciliation for imported FX versions (CTL-002)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import fx_rate, fx_rate_set, fx_rate_set_version, period
from erev_api.domain.imports.csv_v2.framework import Applied, ApplyContext, Plan


def _rate(value: Any) -> str:
    with localcontext() as ctx:
        ctx.prec = 80
        return format(Decimal(str(value)).quantize(Decimal("1e-12"), rounding=ROUND_HALF_UP), "f")


def _ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows, key=lambda row: (row["base_currency"], row["quote_currency"], row["effective_date"])
    )


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Check entered rates, derived inverses, complete version and per-row lineage targets."""
    first = plan.rows[0].normalized
    source_set = (
        session.execute(select(fx_rate_set).where(fx_rate_set.c.code == first["fx_rate_set_code"]))
        .mappings()
        .one()
    )
    entered: list[dict[str, Any]] = []
    for source in plan.rows:
        cells = source.normalized
        day = cells.get("lines.effective_date")
        period_id = None
        if cells.get("lines.period_key") is not None:
            # Validated period keys may have several equal-end calendars. The earliest ID
            # matches the command's deterministic representative for that key.
            match = session.execute(
                select(period.c.id, period.c.end_date)
                .where(period.c.period_key == cells["lines.period_key"])
                .order_by(period.c.id)
            ).first()
            if match is None:
                return {"source_period": cells["lines.period_key"]}, {"source_period": None}
            period_id, day = str(match.id), str(match.end_date)
        entered.append(
            {
                "base_currency": str(cells["lines.base_currency"]),
                "quote_currency": str(cells["lines.quote_currency"]),
                "rate": _rate(cells["lines.rate"]),
                "effective_date": str(day),
                "period_id": period_id,
                "rate_type": str(source_set["rate_type"]),
                "is_derived": False,
            }
        )
    pairs = {(r["base_currency"], r["quote_currency"], r["effective_date"]) for r in entered}
    all_expected = list(entered)
    for row in entered:
        if (row["quote_currency"], row["base_currency"], row["effective_date"]) not in pairs:
            with localcontext() as ctx:
                ctx.prec = 80
                inverse = _rate(Decimal(1) / Decimal(row["rate"]))
            all_expected.append(
                {
                    **row,
                    "base_currency": row["quote_currency"],
                    "quote_currency": row["base_currency"],
                    "rate": inverse,
                    "is_derived": True,
                }
            )
    expected = {
        "version": {
            "set_id": str(source_set["id"]),
            "coverage_from": str(first["coverage_from"]),
            "coverage_to": str(first["coverage_to"]),
            "import_upload_id": str(context.import_upload_id),
            "status": "SUBMITTED",
            "rate_count": len(all_expected),
        },
        "rates": _ordered(all_expected),
        "source_targets": entered,
        "complete": True,
    }
    target_ids = [key for kind, key in applied.targets if kind == "fx_rate"]
    version_ids = list(
        session.scalars(
            select(fx_rate.c.fx_rate_set_version_id).where(fx_rate.c.id.in_(target_ids)).distinct()
        )
    )
    if len(version_ids) != 1:
        return expected, {"version_count": len(version_ids)}
    version = (
        session.execute(
            select(fx_rate_set_version).where(fx_rate_set_version.c.id == version_ids[0])
        )
        .mappings()
        .one()
    )
    stored = {}
    for stored_row in session.execute(
        select(fx_rate).where(fx_rate.c.fx_rate_set_version_id == version["id"])
    ).mappings():
        stored[stored_row["id"]] = {
            "base_currency": str(stored_row["base_currency"]).strip(),
            "quote_currency": str(stored_row["quote_currency"]).strip(),
            "rate": _rate(stored_row["rate"]),
            "effective_date": str(stored_row["effective_date"]),
            "period_id": None if stored_row["period_id"] is None else str(stored_row["period_id"]),
            "rate_type": str(stored_row["rate_type"]),
            "is_derived": stored_row["is_derived"],
        }
    source_targets: list[Any] = []
    source_ids = []
    for source_row in plan.rows:
        targets = applied.row_targets.get(source_row.id, [])
        if len(targets) != 1 or targets[0][0] != "fx_rate":
            source_targets.append(None)
        else:
            source_ids.append(targets[0][1])
            source_targets.append(stored.get(targets[0][1]))
    entered_ids = {key for key, value in stored.items() if not value["is_derived"]}
    actual = {
        "version": {
            "set_id": str(version["fx_rate_set_id"]),
            "coverage_from": str(version["coverage_from"]),
            "coverage_to": str(version["coverage_to"]),
            "import_upload_id": str(version["import_upload_id"]),
            "status": str(version["status"]),
            "rate_count": version["rate_count"],
        },
        "rates": _ordered(list(stored.values())),
        "source_targets": source_targets,
        "complete": (
            len(source_ids) == len(set(source_ids)) == len(entered_ids)
            and set(source_ids) == entered_ids
            and len(applied.targets) == len(entered_ids)
            and set(applied.targets) == {("fx_rate", key) for key in entered_ids}
        ),
    }
    return expected, actual
