"""RPT-38 dataset and contributor evidence from reconciled historical replay.

The standard report writers consume this dataset. The worker must still load and
re-authorize the original sources before publishing; this module performs no I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Any, Final

from erev_engine.stages.s01_canonicalize import encode_key
from erev_engine.stages.s15_disclosures.variance import DRIVERS, totals_by_driver

from erev_api.problems import Problem

from . import tie_outs, variance_groups, variance_measures
from .outputs import Column, ReportData
from .variance_sources import Pair

CODE: Final = "variance_between_closes"
LABELS: Final = {
    "REVENUE": "Revenue",
    "CONTRACT_LIABILITY": "Contract liability",
    "CONTRACT_ASSET_AND_UNBILLED": "Contract asset and unbilled receivable",
    "RPO": "Remaining performance obligations",
}
DRIVER_LABELS: Final = {
    "NEW_CONTRACT": "New contracts",
    "MODIFICATION": "Modifications",
    "ESTIMATE_CHANGE": "VC and estimate changes",
    "PROGRESS": "Progress",
    "BILLING": "Billing",
    "FX": "FX",
    "LATE_EVENT": "Late events",
    "OTHER": "Other",
}
COLUMNS: Final = (
    Column("section_label", "Section", "text"),
    Column("measure_label", "Measure", "text"),
    Column("scope", "Scope", "code"),
    Column("currency", "Currency", "code"),
    Column("earlier_value", "Earlier lock", "money"),
    Column("later_value", "Later lock", "money"),
    Column("change", "Change", "money"),
    Column("driver_label", "Driver", "text"),
)


@dataclass(frozen=True)
class Presentation:
    data: ReportData
    evidence: dict[str, Any]


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Close variance presentation: {detail}")


def _money(value: Fraction, currency: str) -> dict[str, str]:
    """Format exact minor units without Decimal context or silent rounding."""
    places = tie_outs.minor_unit(currency)
    scaled = value * 10**places
    if scaled.denominator != 1:
        raise _refuse("a monetary change is below the currency's minor unit.")
    digits = str(abs(scaled.numerator)).rjust(places + 1, "0")
    text = digits if not places else digits[:-places] + "." + digits[-places:]
    return {"amount": ("-" if value < 0 else "") + text, "currency": currency}


def dataset(pair: Pair, replay: variance_groups.GroupReplay) -> Presentation:
    """Present both sections, preserving drill evidence separately from grid values."""
    if replay.required_entity_ids != pair.required_entity_ids:
        raise _refuse("the replay access scope differs from its source pair.")
    frozen = variance_measures.compare(pair.earlier.frozen, pair.later.frozen)
    before = variance_measures.endpoints(pair.earlier.frozen)
    after = variance_measures.endpoints(pair.later.frozen)
    zero = Fraction(0)
    keys = before.keys() | after.keys() | replay.measures.keys()
    totals: dict[tuple[str, str], Fraction] = {}
    drivers: dict[tuple[str, str, str], Fraction] = {}
    rows: list[dict[str, Any]] = []
    contributors: dict[str, Any] = {}
    driver_contributors: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    scope = pair.earlier.frozen.scope
    for key in sorted(keys):
        was = before[key].amount if key in before else zero
        now = after[key].amount if key in after else zero
        change = replay.measures.get(key)
        if (
            change is None
            or not change.sums_exactly
            or (change.metric_before, change.metric_after) != (was, now)
        ):
            raise _refuse("replay does not reconcile every frozen monetary endpoint.")
        if key.measure not in LABELS:
            raise _refuse("the replay contains an unsupported measure.")
        total_key = key.currency, key.measure
        totals[total_key] = totals.get(total_key, zero) + change.total
        old_id = pair.earlier.contract_computations.get(key.contract_external_id)
        new_id = pair.later.contract_computations.get(key.contract_external_id)
        source = (
            pair.earlier.computations.get(old_id)
            if old_id is not None
            else pair.later.computations.get(new_id)
            if new_id is not None
            else None
        )
        group = replay.groups.get(source.group_id) if source is not None else None
        if (
            group is None
            or group.replay.measures.get(key) != change
            or (None if group.earlier is None else group.earlier.computation_id) != old_id
            or (None if group.later is None else group.later.computation_id) != new_id
        ):
            raise _refuse("a contract has no matching group execution evidence.")
        group_id = str(source.group_id) if source is not None else ""
        by_driver = totals_by_driver(change.effects)
        for driver, amount in by_driver.items():
            driver_key = key.currency, key.measure, driver
            drivers[driver_key] = drivers.get(driver_key, zero) + amount
            if amount:
                driver_contributors.setdefault(driver_key, []).append(
                    {
                        "contract_external_id": key.contract_external_id,
                        "group_id": group_id,
                        "change": _money(amount, key.currency),
                        "event_keys": [
                            event
                            for effect in change.effects
                            if effect.driver == driver
                            for event in effect.event_keys
                        ],
                    }
                )
        if not change.total:
            continue
        row_key = "change:" + ":".join(
            encode_key(part)
            for part in (key.contract_external_id, key.measure, scope.period_key, key.currency)
        )
        rows.append(
            {
                "row_key": row_key,
                "section": 2,
                "section_label": "Changes by contract",
                "measure_label": LABELS[key.measure]
                + (f", {scope.period_key}" if key.measure == "REVENUE" else ""),
                "measure": key.measure,
                "scope": key.contract_external_id,
                "contract_external_id": key.contract_external_id,
                "currency": key.currency,
                "earlier_value": _money(was, key.currency),
                "later_value": _money(now, key.currency),
                "change": _money(change.total, key.currency),
                "driver_label": ", ".join(DRIVER_LABELS[d] for d in DRIVERS if by_driver[d]),
            }
        )
        contributors[row_key] = {
            "contract_external_id": key.contract_external_id,
            "measure": key.measure,
            "value": _money(change.total, key.currency),
            "group_id": group_id,
            "earlier_source_rows": list(before[key].source_rows) if key in before else [],
            "later_source_rows": list(after[key].source_rows) if key in after else [],
            "effects": [
                {
                    "driver": effect.driver,
                    "change": _money(effect.amount, key.currency),
                    "event_keys": list(effect.event_keys),
                    "value_after": _money(effect.value_after, key.currency),
                }
                for effect in change.effects
            ],
        }
    if any(
        drivers.get(key, zero) != replay.driver_totals.get(key, zero)
        for key in drivers.keys() | replay.driver_totals.keys()
    ):
        raise _refuse("group driver totals differ from the contract decompositions.")
    summary: list[dict[str, Any]] = []
    for (currency, measure, driver), amount in sorted(drivers.items()):
        if amount:
            summary.append(
                {
                    "row_key": f"driver:{currency}:{measure}:{driver}",
                    "section": 1,
                    "section_label": "Change by driver",
                    "measure_label": LABELS[measure],
                    "measure": measure,
                    "scope": scope.entity_code,
                    "currency": currency,
                    "earlier_value": None,
                    "later_value": None,
                    "change": _money(amount, currency),
                    "driver_label": DRIVER_LABELS[driver],
                    "driver": driver,
                }
            )
    for row in summary:
        driver = row["driver"]
        contributors[row["row_key"]] = {
            "measure": row["measure"],
            "value": row["change"],
            "driver": driver,
            "contracts": driver_contributors[(row["currency"], row["measure"], driver)],
        }
    evidence: dict[str, Any] = {
        "format": "erev.close_variance_presentation.v1",
        "sources": frozen["sources"],
        "earlier_recorded_at": frozen["earlier_recorded_at"].isoformat(),
        "later_recorded_at": frozen["later_recorded_at"].isoformat(),
        "required_entity_ids": [str(identity) for identity in replay.required_entity_ids],
        "contributors": contributors,
        "groups": {
            str(identity): {
                "earlier": None
                if run.earlier is None
                else {
                    **asdict(run.earlier),
                    "computation_id": str(run.earlier.computation_id),
                },
                "later": None
                if run.later is None
                else {**asdict(run.later), "computation_id": str(run.later.computation_id)},
                "normalized_fields": list(run.normalized_fields),
                "replay_input_sha256": run.replay_input_sha256,
                "engine_version": run.replay.engine_version,
                "executions": [asdict(step) for step in run.replay.executions],
            }
            for identity, run in sorted(replay.groups.items(), key=lambda item: str(item[0]))
        },
    }
    # Totals remain separate by measure and currency. Do not invent visible rows
    # for an identical pair: the viewer's empty state then remains truthful.
    active = {(row["currency"], row["measure"]) for row in (*summary, *rows)}
    total_rows = []
    for section, label in ((1, "Change by driver"), (2, "Changes by contract")):
        for currency, measure in sorted(active):
            total_rows.append(
                {
                    "row_key": f"TOTAL:{currency}:{measure}:{section}",
                    "section": section,
                    "section_label": label,
                    "measure_label": LABELS[measure],
                    "measure": measure,
                    "scope": scope.entity_code,
                    "currency": currency,
                    "earlier_value": None,
                    "later_value": None,
                    "change": _money(totals[(currency, measure)], currency),
                    "driver_label": "",
                }
            )
    controls = {
        f"{currency}:{measure}": _money(amount, currency)["amount"]
        for (currency, measure), amount in sorted(totals.items())
    }
    return Presentation(ReportData(COLUMNS, tuple(summary + rows + total_rows), controls), evidence)
