"""Authorized eRev inputs for RPT-42 from journal facts and traced/frozen balances.

The caller supplies the independently established legacy population. A missing
expected contract balance withholds that period instead of fabricating zero actuals.
This reader operates only in its authorized tenant; it never switches to a sandbox.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.domain.journals import views
from erev_api.domain.reports import locked_ends, tie_outs
from erev_api.domain.reports.builders import ReportParams, SourceCollector
from erev_api.domain.reports.parallel_comparison import Balance, Journal, Period, Snapshot
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class Read:
    snapshot: Snapshot
    evidence: dict[str, Any]


def read(
    uow: UnitOfWork, *, expected: Snapshot, entity_ids: tuple[UUID, ...], known_at: datetime
) -> Read:
    actor = uow.principal
    scope = actor.permission_scopes.get("report.run")
    if (
        "report.run" not in actor.permissions
        or not scope
        or (scope != "*" and not set(entity_ids) <= scope)
    ):
        raise Problem("forbidden")
    if known_at.tzinfo is None:
        raise Problem("validation-failed", "The comparison cutoff must include a time zone.")
    sources = SourceCollector()
    sources.record_cutoff(known_at)
    params = ReportParams(
        "parallel_run_comparison",
        1,
        {},
        entity_ids,
        known_at,
        book_code="ASC606",
        historical=True,
        sources=sources,
    )
    entities = tie_outs.entities(uow.session, entity_ids, params=params)
    by_code = {entity.code: entity for entity in entities}
    if len(entities) != len(set(entity_ids)) or any(
        p.entity_code not in by_code or p.book_code != "ASC606" for p in expected.periods
    ):
        raise Problem(
            "validation-failed", "Comparison periods do not match the authorized entity scope."
        )
    calendars = tie_outs.calendars(uow.session, entities, params=params)
    ends = locked_ends.Reader(
        uow,
        params,
        book_code="ASC606",
        cutoff=known_at,
        entity_codes={e.id: e.code for e in entities},
    )
    journals: list[Journal] = []
    balances: list[Balance] = []
    available: set[Period] = set()
    facts: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for period in sorted(expected.periods):
        entity = by_code[period.entity_code]
        ref = calendars[entity.id].named(period.key, "period_key")
        if (ref.start, ref.end) != (period.start, period.end):
            raise Problem("validation-failed", "Legacy and eRev calendar boundaries differ.")
        actual = tie_outs.balances_at(
            uow.session,
            entity_ids=(entity.id,),
            book_code="ASC606",
            period_keys={entity.id: ref},
            cutoff=known_at,
            params=params,
            locked_ends=ends,
        )
        required = {row.contract for row in expected.balances if row.period == period}
        seen = {row.external_id for row in actual if row.currency == period.currency}
        if required - seen:
            missing.append(
                {
                    "entity": period.entity_code,
                    "period": period.key,
                    "currency": period.currency,
                    "missing_contracts": sorted(required - seen),
                }
            )
            continue
        # Unrepresented currencies cannot silently disappear from the comparison.
        if any(row.currency != period.currency for row in actual):
            raise Problem(
                "validation-failed",
                "eRev balances include a currency absent from the legacy source.",
            )
        grouped = views._consolidated(
            uow.session,
            entity_ids=(entity.id,),
            books=("ASC606",),
            from_date=period.start,
            to_date=period.end,
            known_at=known_at,
            historical=True,
            include_sources=True,
        )
        totals: dict[str, tuple[Decimal, Decimal]] = {}
        refs: dict[str, set[str]] = {}
        input_groups = []
        for group in grouped:
            currency = str(group["txn_currency"]).strip()
            if currency != period.currency:
                raise Problem(
                    "validation-failed",
                    "eRev journals include a currency absent from the legacy source.",
                )
            account = str(group["account"])
            amount = tie_outs.quantized(Decimal(group["amount"]), currency)
            debit, credit = totals.get(account, (Decimal(0), Decimal(0)))
            totals[account] = debit + max(amount, Decimal(0)), credit - min(amount, Decimal(0))
            group_refs = sorted(
                f"subledger-line:{row['period_end_date']}:{row['line_id']}:posting:{row['posting_id']}"
                for row in group["source_rows"]
            )
            refs.setdefault(account, set()).update(group_refs)
            input_groups.append(
                {
                    "account": account,
                    "legacy_key": str(group["legacy_key"]),
                    "amount": str(group["amount"]),
                    "source_rows": group_refs,
                }
            )
        for account, (debit, credit) in sorted(totals.items()):
            if debit or credit:
                journals.append(
                    Journal(period, account, debit, credit, tuple(sorted(refs[account])))
                )
        input_balances = []
        frozen = ends.at(entity.id, ref)
        for row in actual:
            liability = row.value("contract_liability")
            asset = row.value("contract_asset") + row.value("unbilled_receivable")
            reference = (
                f"contract-version:{row.version_id}:contract:{row.contract_id}:period:{period.key}"
            )
            if frozen is not None:
                reference = (
                    f"lock:{frozen.lock_id}:balances:{frozen.balances_sha256}:"
                    f"contract:{row.external_id}"
                )
            balances.append(
                Balance(period, row.external_id, liability - asset, (reference,), liability, asset)
            )
            input_balances.append(
                {
                    "contract": row.external_id,
                    "liability": str(liability),
                    "asset_and_unbilled": str(asset),
                    "source": reference,
                }
            )
        available.add(period)
        facts.append(
            {
                "entity": entity.code,
                "book": "ASC606",
                "currency": period.currency,
                "period": period.key,
                "start": period.start.isoformat(),
                "end": period.end.isoformat(),
                "journal_groups": sorted(
                    input_groups, key=lambda row: (row["account"], row["legacy_key"])
                ),
                "balances": input_balances,
            }
        )
    evidence = {
        "version": 1,
        "tenant_id": str(actor.tenant_id),
        "known_at": known_at.isoformat(),
        "entity_ids": sorted(str(v) for v in entity_ids),
        "expected_source": {"id": expected.source_id, "sha256": expected.sha256},
        "periods": facts,
        "unavailable_periods": missing,
        "locked_ends": sources.evidence.get("locked_ends", {}),
    }
    return Read(
        Snapshot(
            f"erev:{actor.tenant_id}:{known_at.isoformat()}",
            sha256_hex(evidence),
            frozenset(available),
            tuple(journals),
            tuple(balances),
        ),
        evidence,
    )
