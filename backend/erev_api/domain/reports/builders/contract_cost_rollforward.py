"""RPT-32 ``contract_cost_rollforward`` Contract cost rollforward — the governed
``COST_ROLLFORWARD`` dataset (SCREENS_B §5.6.1 RPT-32 rev 1.14; ENGINE_SPEC_B §15.2.6 S15-R-17,
§15.2.7 S15-R-20a / S15-R-20b; 04 T-CLS-05; POLICIES POL-140 to POL-146; 03 REQ-CST-006; ASC
340-40-50-3; BUILD_SPEC RPS-12; supervisor rulings D-98 85 / 97; lane ENG-C8).

The dataset and the API rows are the long form: one row per (``cost_kind``, ``line_code``) and
entity with one signed money field ``amount`` — the S15-R-17 lines ``OPENING``, ``ADDITIONS``,
``CLAWBACKS``, ``AMORTIZATION``, ``ACCELERATION``, ``IMPAIRMENT``, ``IMPAIRMENT_REVERSAL``,
``CLOSING`` — the codes ``cost_kind`` / ``line_code`` (the F-CLO ``KeySpec`` key) and
``entity_code`` as code columns, the labels as attributes. Every line of a cost kind with a cost
asset in scope is a row (zero rows kept); a kind without an asset has no rows. Movements are signed
as they enter the carrying amount; ``OPENING`` + Σ movements = ``CLOSING`` per kind. The on-screen
wide grid is a view-level pivot of these rows (D-98 97). Section 2 "By cost asset" is DEFERRED
until its own key is ruled.

Source (S15-R-20b; interim per F-RPS ruling Q-2 until CTR-14 persists T-CON-15/16): the T-SL-04
subledger lines of the two asset roles, read as of the run's ``known_at`` (D-98 96). Per kind,
``OPENING`` is the asset role's balance before the range (Σ lines through the end of the period
before the range — the carrying amount, S11-INV-06) and the range lines are classified by entry
kind, side and ``reason_code`` (D-98 19): a ``CONTRACT_COST_CAPITALIZATION`` debit is
``ADDITIONS``, a credit or ``reason_code = CLAWBACK`` ``CLAWBACKS``; a
``CONTRACT_COST_AMORTIZATION`` line is ``AMORTIZATION``, or ``ACCELERATION`` under ``reason_code =
TERMINATION_ACCELERATION``; a ``CONTRACT_COST_IMPAIRMENT`` credit is ``IMPAIRMENT`` and a debit
``IMPAIRMENT_REVERSAL``. The previous lock's snapshot ``CLOSING`` as ``OPENING`` follows F-CLO's
locked-dataset reader (CLO-8); until then the subledger balance is the only opening. Tie-out
``TO_COST_ROLLFORWARD_BALANCES``: every kind's ``OPENING`` + Σ movements equals its ``CLOSING`` and
Σ ``CLOSING`` per currency equals Σ T-CON-09 ``cost_asset_carrying`` at the range end.

Currency: the entity's functional currency by default (``currency_view`` ``functional``); the
``transaction`` view only when the entity's cost assets carry one currency, else the run refuses
(RPT-07 pattern). Money cells are typed API-S-Money values (``tie_outs.money``), never bare
decimals (Codex C6-RPT-R1); the pure core works in minor units. A row whose ``cost_kind`` or
``line_code`` cannot be supplied refuses by name (``CostRollforwardRefusal``) — never a proxy or a
default (S15-R-20a).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, legal_entity, subledger_line
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_balance_rollforward import FUNCTIONAL_ONLY, ranges
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import BalanceRow, EntityRef, PeriodRef
from erev_api.uow import UnitOfWork

CODE: Final = "contract_cost_rollforward"
TO_COST_ROLLFORWARD_BALANCES: Final = tie_outs.TO_COST_ROLLFORWARD_BALANCES
CARRYING_MEASURE: Final = "cost_asset_carrying"
DEFAULT_CURRENCY_VIEW: Final = "functional"  # SCREENS_B RPT-32 "Currency view: default functional"
KEY_COLUMNS: Final = ("cost_kind", "line_code")  # S15-R-20a / F-CLO KeySpec COST_ROLLFORWARD
COST_KINDS: Final = ("OBTAIN", "FULFILL")  # E-83
ROLE_KIND: Final[Mapping[str, str]] = {
    "COST_TO_OBTAIN_ASSET": "OBTAIN",
    "COST_TO_FULFILL_ASSET": "FULFILL",
}
CATEGORY_LABELS: Final[Mapping[str, str]] = {
    "OBTAIN": "Costs to obtain a contract",
    "FULFILL": "Costs to fulfil a contract",
}
# S15-R-17 order (ENGINE_SPEC_B S15-R-20b); the engine kernel's LINES without its OTHER line.
LINE_CODES: Final = (
    "OPENING",
    "ADDITIONS",
    "CLAWBACKS",
    "AMORTIZATION",
    "ACCELERATION",
    "IMPAIRMENT",
    "IMPAIRMENT_REVERSAL",
    "CLOSING",
)
MOVEMENT_LINES: Final = LINE_CODES[1:-1]
LINE_LABELS: Final[Mapping[str, str]] = {
    "OPENING": "Opening carrying amount",
    "ADDITIONS": "Additions",
    "CLAWBACKS": "Clawbacks",
    "AMORTIZATION": "Amortization",
    "ACCELERATION": "Acceleration on termination",
    "IMPAIRMENT": "Impairment",
    "IMPAIRMENT_REVERSAL": "Impairment reversal",
    "CLOSING": "Closing carrying amount",
}
REASON_CLAWBACK: Final = "CLAWBACK"
REASON_ACCELERATION: Final = "TERMINATION_ACCELERATION"
CAPITALIZATION: Final = "CONTRACT_COST_CAPITALIZATION"
AMORTIZATION: Final = "CONTRACT_COST_AMORTIZATION"
IMPAIRMENT: Final = "CONTRACT_COST_IMPAIRMENT"
# The dataset header in KeySpec order: codes, labels, currency, the one measure (04 T-CLS-05).
COLUMNS: Final = (
    Column("section", "Section", "integer"),
    Column("entity_code", "Entity", "code"),
    Column("cost_kind", "Cost kind", "code"),
    Column("line_code", "Line code", "code"),
    Column("category_label", "Category", "text"),
    Column("line_label", "Line", "text"),
    Column("currency", "Currency", "code"),
    Column("amount", "Amount", "money"),
)


class CostRollforwardRefusal(RuntimeError):
    """A governed key column cannot be supplied, or a row set is not one row per key: refused by
    name (S15-R-20a / S15-R-20b), never a proxy, a default or a dropped row."""

    def __init__(self, column: str, detail: str) -> None:
        self.column = column
        self.detail = detail
        super().__init__(f"{CODE}: {column}: {detail}")


@dataclass(frozen=True, slots=True)
class CostMovement:
    """One classified subledger line of a cost asset, in minor units signed as it enters the
    carrying amount; ``in_range`` False places it in the opening."""

    entity_code: str
    cost_kind: str  # COST_KINDS
    line_code: str  # MOVEMENT_LINES
    amount_minor: int
    currency: str
    in_range: bool
    contract_external_id: str


def classify(
    account_role: str, entry_kind: str, dr_cr: str, reason_code: str | None, amount_minor: int
) -> tuple[str, str, int]:
    """(cost kind, line code, signed minor amount) of one cost-asset line (S15-R-17; D-98 19).
    ``CostRollforwardRefusal`` names the column that cannot be supplied: ``cost_kind`` for a role
    outside E-83, ``line_code`` for an entry kind that is not a JET-09 movement."""
    cost_kind = ROLE_KIND.get(account_role)
    if cost_kind is None:
        raise CostRollforwardRefusal(
            "cost_kind", f"account role {account_role!r} is not a contract-cost asset role (E-83)"
        )
    debit = dr_cr == "D"
    magnitude = abs(amount_minor)
    if entry_kind == CAPITALIZATION:
        if reason_code == REASON_CLAWBACK or not debit:
            return cost_kind, "CLAWBACKS", -magnitude if not debit else magnitude
        return cost_kind, "ADDITIONS", magnitude
    if entry_kind == AMORTIZATION:
        line = "ACCELERATION" if reason_code == REASON_ACCELERATION else "AMORTIZATION"
        return cost_kind, line, magnitude if debit else -magnitude
    if entry_kind == IMPAIRMENT:
        if debit:
            return cost_kind, "IMPAIRMENT_REVERSAL", magnitude
        return cost_kind, "IMPAIRMENT", -magnitude
    raise CostRollforwardRefusal(
        "line_code",
        f"entry kind {entry_kind!r} ({dr_cr}) on {account_role} is not a JET-09 movement",
    )


type Lines = dict[str, int]  # LINE_CODES -> minor units, signed


def rollforward(
    movements: Sequence[CostMovement],
) -> tuple[dict[tuple[str, str], Lines], dict[str, str]]:
    """The lines per (entity code, cost kind) and the currency per entity: ``OPENING`` from the
    movements before the range, the range movements by line, ``CLOSING`` = ``OPENING`` + Σ
    movements. A second currency inside one entity refuses by name (one row per key)."""
    lines: dict[tuple[str, str], Lines] = {}
    currencies: dict[str, str] = {}
    for item in movements:
        known = currencies.setdefault(item.entity_code, item.currency)
        if known != item.currency:
            raise CostRollforwardRefusal(
                "currency",
                f"entity {item.entity_code} carries cost assets in {known} and {item.currency}: "
                "the dataset row (cost_kind, line_code) admits one currency per entity",
            )
        into = lines.setdefault((item.entity_code, item.cost_kind), dict.fromkeys(LINE_CODES, 0))
        into["OPENING" if not item.in_range else item.line_code] += item.amount_minor
    for into in lines.values():
        into["CLOSING"] = into["OPENING"] + sum(into[code] for code in MOVEMENT_LINES)
    ordered = sorted(lines, key=lambda key: (key[0], COST_KINDS.index(key[1])))
    return {key: lines[key] for key in ordered}, dict(sorted(currencies.items()))


def _money(minor: int, currency: str) -> dict[str, str]:
    return tie_outs.money(Decimal(minor).scaleb(-tie_outs.minor_unit(currency)), currency)


def dataset_rows(
    lines: Mapping[tuple[str, str], Lines], currencies: Mapping[str, str]
) -> list[dict[str, Any]]:
    """The section 1 rows: one per (entity, cost kind, line code) in entity, E-83 and S15-R-17
    order; ``row_key`` ``<cost_kind>:<line_code>``, prefixed ``<entity>:`` when several entities."""
    entities = sorted({entity for entity, _ in lines})
    prefixed = len(entities) > 1
    rows: list[dict[str, Any]] = []
    for (entity, cost_kind), found in lines.items():
        currency = currencies[entity]
        for line_code in LINE_CODES:
            key = f"{cost_kind}:{line_code}"
            rows.append(
                {
                    "row_key": f"{entity}:{key}" if prefixed else key,
                    "section": 1,
                    "entity_code": entity,
                    "cost_kind": cost_kind,
                    "line_code": line_code,
                    "category_label": CATEGORY_LABELS[cost_kind],
                    "line_label": LINE_LABELS[line_code],
                    "currency": currency,
                    "amount": _money(found[line_code], currency),
                }
            )
    return rows


def check_key_columns(rows: Sequence[Mapping[str, Any]]) -> None:
    """S15-R-20a shape statement: every row supplies the key columns from their governed sets and
    the key (entity, cost kind, line code) occurs once; otherwise refuse by name."""
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        cost_kind, line_code = str(row.get("cost_kind") or ""), str(row.get("line_code") or "")
        if cost_kind not in COST_KINDS:
            raise CostRollforwardRefusal(
                "cost_kind", f"row {row.get('row_key')!r} carries {cost_kind!r}"
            )
        if line_code not in LINE_CODES:
            raise CostRollforwardRefusal(
                "line_code", f"row {row.get('row_key')!r} carries {line_code!r}"
            )
        key = (str(row.get("entity_code") or ""), cost_kind, line_code)
        if key in seen:
            raise CostRollforwardRefusal(
                "line_code", f"the key {cost_kind}:{line_code} of entity {key[0]} occurs twice"
            )
        seen.add(key)


def control_totals(
    lines: Mapping[tuple[str, str], Lines], currencies: Mapping[str, str]
) -> dict[str, dict[str, str]]:
    """``opening`` and ``closing`` per currency (§15.2.7 control totals)."""
    out: dict[str, dict[str, str]] = {}
    for line_code in ("OPENING", "CLOSING"):
        totals: dict[str, Decimal] = {}
        for (entity, _), found in lines.items():
            currency = currencies[entity]
            tie_outs.add(
                totals, currency, Decimal(found[line_code]).scaleb(-tie_outs.minor_unit(currency))
            )
        out[line_code.lower()] = tie_outs.by_currency(totals)
    return out


def cost_tie(
    lines: Mapping[tuple[str, str], Lines],
    currencies: Mapping[str, str],
    balances: Sequence[BalanceRow],
) -> dict[str, Any]:
    """``TO_COST_ROLLFORWARD_BALANCES``: every kind's ``OPENING`` + Σ movements equals its
    ``CLOSING`` and Σ ``CLOSING`` per currency equals Σ ``cost_asset_carrying`` at the range end
    (S15-R-17, S11-INV-06)."""
    expected: dict[str, Decimal] = {}
    for balance in balances:
        tie_outs.add(expected, balance.currency, balance.value(CARRYING_MEASURE))
    actual: dict[str, Decimal] = {}
    identity = True
    for (entity, _), found in lines.items():
        currency = currencies[entity]
        tie_outs.add(
            actual, currency, Decimal(found["CLOSING"]).scaleb(-tie_outs.minor_unit(currency))
        )
        identity = identity and (
            found["OPENING"] + sum(found[code] for code in MOVEMENT_LINES) == found["CLOSING"]
        )
    result = tie_outs.compared(TO_COST_ROLLFORWARD_BALANCES, expected, actual)
    if not identity:
        result["result"] = tie_outs.FAIL
    return result


def _movements(
    session: Session,
    *,
    entity_ids: Sequence[UUID],
    book_code: str,
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    known_at: datetime,
    params: ReportParams,
) -> list[CostMovement]:
    """Every JET-09 subledger line of the cost-asset roles through each entity's range end, as of
    ``known_at`` (D-98 96); lines before the range make the opening."""
    if not entity_ids or not any(periods.values()):
        # R1: an empty range is a CAPTURED empty membership (recorded), never an absent kind
        tie_outs.require_members(params, "subledger_line", ())
        tie_outs.record_members(params, "subledger_line", ())
        return []
    range_end = {entity_id: items[-1].end for entity_id, items in periods.items() if items}
    range_start = {entity_id: items[0].start for entity_id, items in periods.items() if items}
    statement = (
        select(
            subledger_line.c.id,
            subledger_line.c.entity_id,
            subledger_line.c.account_role,
            subledger_line.c.entry_kind,
            subledger_line.c.dr_cr,
            subledger_line.c.reason_code,
            subledger_line.c.amount_txn,
            subledger_line.c.txn_currency,
            subledger_line.c.period_end_date,
            contract.c.external_id,
            legal_entity.c.code.label("entity_code"),
        )
        .select_from(
            subledger_line.join(
                contract,
                and_(
                    contract.c.tenant_id == subledger_line.c.tenant_id,
                    contract.c.id == subledger_line.c.contract_id,
                ),
            ).join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == subledger_line.c.tenant_id,
                    legal_entity.c.id == subledger_line.c.entity_id,
                ),
            )
        )
        .where(
            subledger_line.c.book_code == book_code,
            subledger_line.c.entity_id.in_(list(entity_ids)),
            subledger_line.c.account_role.in_(list(ROLE_KIND)),
            subledger_line.c.recorded_at <= known_at,
            subledger_line.c.period_end_date <= max(range_end.values()),
            *tie_outs.bound_member_where(params, "subledger_line", subledger_line.c.id),
        )
        .order_by(
            subledger_line.c.effective_date,
            subledger_line.c.period_end_date,
            subledger_line.c.recorded_at,
            subledger_line.c.entry_no,
            subledger_line.c.id,
        )
    )
    found: list[CostMovement] = []
    consumed: list[UUID] = []  # frps3c-2: the lines the movements actually consumed
    for row in session.execute(statement).mappings():
        entity_id = UUID(str(row["entity_id"]))
        if entity_id not in range_end or row["period_end_date"] > range_end[entity_id]:
            continue
        consumed.append(UUID(str(row["id"])))
        currency = str(row["txn_currency"]).strip()
        minor = int(Decimal(row["amount_txn"]).scaleb(tie_outs.minor_unit(currency)))
        cost_kind, line_code, signed = classify(
            str(row["account_role"]),
            str(row["entry_kind"]),
            str(row["dr_cr"]),
            None if row["reason_code"] is None else str(row["reason_code"]),
            minor,
        )
        found.append(
            CostMovement(
                # the consumed code by entity id (retained under a binding; Codex 8ede60b7 R1)
                entity_code=tie_outs.entity_code_for(params, entity_id, str(row["entity_code"])),
                cost_kind=cost_kind,
                line_code=line_code,
                amount_minor=signed,
                currency=currency,
                in_range=row["period_end_date"] >= range_start[entity_id],
                contract_external_id=str(row["external_id"]),
            )
        )
    tie_outs.require_members(params, "subledger_line", consumed)
    tie_outs.record_members(params, "subledger_line", consumed)
    return found


def _check_view(
    params: ReportParams, found: Sequence[EntityRef], items: Sequence[CostMovement]
) -> None:
    """``functional`` (the default): every movement is in its entity's functional currency, else
    the run is refused (``FUNCTIONAL_ONLY``); ``transaction``: the rollforward refuses a second
    currency per entity itself."""
    view = str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW)
    functional = {entity.code: entity.functional_currency for entity in found}
    if view != "transaction" and any(
        item.currency != functional[item.entity_code] for item in items
    ):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found, periods, _ = ranges(session, params)
    movements = _movements(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        periods=periods,
        known_at=params.known_at,
        params=params,
    )
    _check_view(params, found, movements)
    lines, currencies = rollforward(movements)
    rows = dataset_rows(lines, currencies)
    check_key_columns(rows)
    cutoff = tie_outs.cutoff_for(session, params)
    closing_balances = tie_outs.balances_at(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        period_keys={key: (value[-1] if value else None) for key, value in periods.items()},
        cutoff=cutoff,
        params=params,
    )
    return ReportData(
        columns=COLUMNS,
        rows=tuple(rows),
        control_totals=control_totals(lines, currencies),
        tie_out_results=(cost_tie(lines, currencies, closing_balances),),
    )
