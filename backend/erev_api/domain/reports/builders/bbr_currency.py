"""Source-time spot valuation for BBR contract values and billing contributions."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes

from erev_api.domain.contracts.bundles import fx_rates_in_force
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.domain.reports.tie_outs import EntityRef
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

EVIDENCE: Final = "bbr_fx_rates_v1"


def functional(
    uow: UnitOfWork,
    params: ReportParams,
    sources: Mapping[str, Sequence[Contribution]],
    entities: Sequence[EntityRef],
) -> dict[str, tuple[Contribution, ...]]:
    targets = {e.id: e.functional_currency for e in entities}
    needed = {
        (r.currency, targets[r.entity_id], r.effective_date)
        for rows in sources.values()
        for r in rows
        if r.functional_amount is None and r.currency != targets[r.entity_id]
    }
    cutoff = params.binding.cutoff if params.binding is not None else params.known_at
    if params.binding is None:
        rates: list[dict[str, Any]] = []
        if needed:
            rate_rows = uow.session.execute(fx_rates_in_force(cutoff)).mappings()
            rates = [
                dict(r)
                for r in rate_rows
                if str(r["rate_type"]) == "SPOT"
                and (r["base_currency"], r["quote_currency"], r["effective_date"]) in needed
            ]
        rates = json.loads(canonical_bytes(rates))
        tie_outs.record_evidence(params, EVIDENCE, rates)
    else:
        rates = tie_outs.bound_evidence(params, EVIDENCE)
    result = {}
    for measure, rows in sources.items():
        valued = []
        for row in rows:
            target = targets[row.entity_id]
            if row.functional_amount is not None or row.currency == target:
                valued.append(row)
                continue
            matches = [
                r
                for r in rates
                if r["base_currency"] == row.currency
                and r["quote_currency"] == target
                and date.fromisoformat(r["effective_date"]) == row.effective_date
                and r["rate_type"] == "SPOT"
            ]
            if len(matches) != 1:
                raise Problem(
                    "invalid-transition",
                    f"BBR needs one approved spot rate for {row.currency}/{target} "
                    f"on {row.effective_date}.",
                )
            rate = matches[0]
            factor = Decimal(rate["rate"])
            if not factor.is_finite() or factor <= 0:
                raise Problem("invalid-transition", "BBR spot rate must be finite and positive.")
            with localcontext() as context:
                context.prec = 80
                amount = tie_outs.quantized(row.amount * factor, target)
            valued.append(
                replace(
                    row,
                    functional_currency=target,
                    functional_amount=amount,
                    basis_ids=(
                        *row.basis_ids,
                        UUID(rate["id"]),
                        UUID(rate["fx_rate_set_version_id"]),
                    ),
                )
            )
        result[measure] = tuple(valued)
    return result
