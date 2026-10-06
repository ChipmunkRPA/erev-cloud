"""RPT-02 ``contract_balances`` Contract balances (SCREENS_B §5.6.1 RPT-02; ENGINE_SPEC_B §15.2.2;
04 T-CON-09; POLICIES POL-122, POL-124, POL-127; 03 REQ-RPT-005; BUILD_SPEC RPS-3).

One row ``contract:<external id>:<entity code>`` per member contract and contracting entity of each
group's latest version known at the run, with the labelled balances at the end of ``period_key``
(``tie_outs.balances_at``): contract liability (current and noncurrent), contract asset (current),
unbilled receivable, accounts receivable, refund liability (its own column, never netted, POL-127),
return asset, deposit liability, customer incentive asset, consideration payable, contract cost
assets and loss provision. Without ``include_zero`` a contract with every balance 0 is omitted.
One ``TOTAL:<ISO>`` row per currency; control totals per column and currency.

Tie-outs: ``TO_BALANCES_EQ_ROLLFORWARD`` compares Σ contract liability, contract asset and unbilled
receivable with the ``CLOSING`` line of the rollforward of ``period_key`` (CTL-030);
``TO_ROLLFORWARD_EQ_GL`` is ``NOT_APPLICABLE`` without a reviewed subledger-to-GL reconciliation.

R-RC-1 (L6-3-Q-22): "As locked" runs (``period_lock_id``, CLO-6) and the K-03 figures of
``test_contract_balances_k01_k03`` (CLO-7) move post-rc.

A period end that is locked at the run's cutoff (ENGINE_SPEC_B S15-R-20 rev 1.168; item
RPT-ROLLFWD-LOCKED-CLOSING-1): the rows and their figures are those of the lock's dataset in a
current run too (``reports.locked_ends``) — a contract activated after the lock is not a row of
that period end —, and the roll-forward read for the tie takes its two ends the same way.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

from erev_api.domain.reports import locked_ends, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_balance_rollforward as rollforward
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, PeriodRef, add
from erev_api.uow import UnitOfWork

CODE: Final = "contract_balances"
TOTAL_PREFIX: Final = "TOTAL:"
MEASURE_COLUMNS: Final = (
    ("contract_liability", "Contract liability"),
    ("contract_liability_current", "Contract liability, current"),
    ("contract_liability_noncurrent", "Contract liability, noncurrent"),
    ("contract_asset", "Contract asset"),
    ("contract_asset_current", "Contract asset, current"),
    ("unbilled_receivable", "Unbilled receivable"),
    ("accounts_receivable", "Accounts receivable"),
    ("refund_liability", "Refund liability"),
    ("return_asset", "Return asset"),
    ("deposit_liability", "Deposit liability"),
    ("customer_incentive_asset", "Customer incentive asset"),
    ("consideration_payable", "Consideration payable"),
    ("cost_asset_carrying", "Contract cost assets"),
    ("loss_provision", "Loss provision"),
)


def _values(get: Any) -> dict[str, Decimal]:
    values = {
        name: get(name) for name, _ in MEASURE_COLUMNS if name != "contract_liability_noncurrent"
    }
    values["contract_liability_noncurrent"] = (
        values["contract_liability"] - values["contract_liability_current"]
    )
    return values


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found = tie_outs.entities(session, params.entity_ids, params=params)
    found_calendars = tie_outs.calendars(session, found, params=params)
    at: dict[Any, PeriodRef | None] = {
        item.id: tie_outs.period_of(params, found_calendars[item.id], item) for item in found
    }
    contract_id = tie_outs.contract_named(session, params)
    cutoff = tie_outs.cutoff_for(session, params)
    ends = locked_ends.Reader(
        uow,
        params,
        book_code=book_code,
        cutoff=cutoff,
        entity_codes={item.id: item.code for item in found},
    )
    balances = tie_outs.balances_at(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        period_keys=at,
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        locked_ends=ends,
    )
    functional = {item.id: item.functional_currency for item in found}
    view = str(params.parameters.get("currency_view") or "transaction")
    if view != "transaction" and any(row.currency != functional[row.entity_id] for row in balances):
        raise tie_outs.invalid("currency_view", rollforward.FUNCTIONAL_ONLY)
    include_zero = bool(params.parameters.get("include_zero", False))
    rows: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Decimal]] = {}
    for row in balances:
        values = _values(row.value)
        if not include_zero and all(amount == 0 for amount in values.values()):
            continue
        rows.append(
            {
                "row_key": f"contract:{row.external_id}:{row.entity_code}",
                "contract_external_id": row.external_id,
                "customer_name": row.customer_name,
                "entity_code": row.entity_code,
                "currency": row.currency,
                **{name: tie_outs.money(amount, row.currency) for name, amount in values.items()},
            }
        )
        into = totals.setdefault(row.currency, {})
        for name, amount in values.items():
            add(into, name, amount)
    for currency, values in sorted(totals.items()):
        rows.append(
            {
                "row_key": f"{TOTAL_PREFIX}{currency}",
                "contract_external_id": None,
                "customer_name": None,
                "entity_code": None,
                "currency": currency,
                **{name: tie_outs.money(amount, currency) for name, amount in values.items()},
            }
        )
    columns = (
        Column("contract_external_id", "Contract", "code"),
        Column("customer_name", "Customer", "text"),
        Column("entity_code", "Entity", "code"),
        Column("currency", "Currency", "code"),
        *(Column(name, header, "money") for name, header in MEASURE_COLUMNS),
    )
    control = {
        name: tie_outs.by_currency(
            {code: values.get(name, ZERO) for code, values in totals.items()}
        )
        for name, _ in MEASURE_COLUMNS
    }
    periods = {key: (() if value is None else (value,)) for key, value in at.items()}
    before = {
        item.id: (
            None if at[item.id] is None else found_calendars[item.id].before(at[item.id])  # type: ignore[arg-type]
        )
        for item in found
    }
    items = rollforward.rollforwards(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        periods=periods,
        before=before,
        known_at=params.known_at,
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        documents=False,  # CTL-030 compares the CLOSING line: no flow of the path is read
        locked=ends,
    )
    return ReportData(
        columns=columns,
        rows=tuple(rows),
        control_totals=control,
        tie_out_results=(
            rollforward.balances_equal_tie(balances, items),
            tie_outs.not_applicable(tie_outs.TO_ROLLFORWARD_EQ_GL),
        ),
    )
