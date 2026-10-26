"""Authenticate and present split-group movements without invented member movement quotas."""

from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from erev_engine.bundle import InputBundle
from erev_engine.stages.s01_canonicalize import group_entity_subject_key
from sqlalchemy import Text, cast, select

from erev_api.db.tables import contract_computation, contract_event, contract_version
from erev_api.uow import UnitOfWork

from . import acquisition_evidence, acquisition_groups, tie_outs
from .builders import ReportParams

KEY = "foreign_split_groups_v1"


def collect(
    uow: UnitOfWork,
    rows: Mapping[tuple[UUID, UUID], tie_outs.BalanceRow],
    bundle: InputBundle,
    output: dict[str, Any],
    source: Mapping[str, Any],
    *,
    book: str,
    entity_id: UUID,
    entity_code: str,
    periods: Sequence[tie_outs.PeriodRef],
    functional: bool,
) -> acquisition_groups.NativeGroup:
    population = set(bundle.group.member_contract_keys)
    members = tuple(
        sorted(
            (r for r in rows.values() if r.entity_id == entity_id and r.external_id in population),
            key=lambda r: r.external_id,
        )
    )
    if {r.external_id for r in members} != population:
        raise tie_outs.invalid(
            "contract_external_id", "Split reporting requires the complete group."
        )
    versions = {}
    for member in members:
        original, _, held = acquisition_evidence.load(uow, member.version_id, book)
        if original.group != bundle.group or any(
            held[k] != source[k] for k in ("input_sha256", "output_sha256")
        ):
            raise tie_outs.invalid(
                "currency_view", "Split members do not share the original computation."
            )
        versions[str(member.contract_id)] = str(member.version_id)
    entity = next(e for e in bundle.entities if e.code == entity_code)
    view = "FUNCTIONAL" if functional else "TRANSACTION"
    currency = entity.functional_currency if functional else bundle.group.transaction_currency
    # Same-currency views use the original transaction snapshot.
    if entity.functional_currency == bundle.group.transaction_currency:
        view = "TRANSACTION"
    original_book = next(b for b in output["books"] if b["book_code"] == book)
    snapshots = []
    for period in periods:
        matches = [
            s
            for s in original_book["disclosure_rollforwards"]
            if s["entity"] == entity_code and s["period_key"] == period.key and s["view"] == view
        ]
        if len(matches) != 1:
            raise tie_outs.invalid(
                "currency_view", "Split reporting lacks an original monthly snapshot."
            )
        s = matches[0]
        if (
            s["unit"] != group_entity_subject_key(bundle.group.group_key, entity_code)
            or s["currency"] != currency
            or s["minor_unit"] != bundle.currencies[currency].minor_unit
            or s["closing_date"] != period.end.isoformat()
            or s["opening_date"] != (period.start - timedelta(days=1)).isoformat()
        ):
            raise tie_outs.invalid("currency_view", "Split snapshot scope differs.")
        acquisition_groups.convert(s)
        if any(v["OTHER"] for v in s["lines"].values()):
            raise tie_outs.invalid("currency_view", "Split snapshot has unexplained movements.")
        snapshots.append((period, s))
    identity = uuid5(NAMESPACE_URL, f"erev:foreign-split:{bundle.group.group_key}:{entity_id}")
    return acquisition_groups.NativeGroup(
        identity,
        entity_id,
        entity_code,
        bundle.group.group_key,
        currency,
        members,
        tuple(snapshots),
        {},
        {
            "input_sha256": source["input_sha256"],
            "output_sha256": source["output_sha256"],
            "member_versions": versions,
            "trace_nodes": {
                str(members[0].version_id): [
                    n["id"]
                    for n in original_book["trace"]["nodes"]
                    if n["measure"]
                    in {
                        "fx_split_transferred",
                        "fx_split_restored",
                        "fx_split_layer_created",
                        "fx_split_asset_remeasured",
                        "fx_split_destination_current",
                    }
                ]
            },
            "snapshots": [s for _, s in snapshots],
        },
    )


def read(
    uow: UnitOfWork,
    params: ReportParams,
    rows: Mapping[tuple[UUID, UUID], tie_outs.BalanceRow],
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    book: str,
    *,
    functional: bool,
    groups: dict[UUID, Any],
) -> None:
    if params.binding is not None and KEY not in params.binding.evidence:
        return
    candidates = set(
        uow.session.execute(
            select(contract_version.c.id)
            .join(
                contract_computation,
                contract_computation.c.id == contract_version.c.contract_computation_id,
            )
            .where(
                contract_version.c.id.in_([r.version_id for r in rows.values()]),
                select(contract_event.c.id)
                .where(
                    contract_event.c.payload.has_key("prospective_split_destinations"),
                    contract_computation.c.stream_heads.has_key(
                        cast(contract_event.c.contract_id, Text)
                    ),
                )
                .exists(),
            )
        ).scalars()
    )
    captured = {}
    seen = set()
    for row in rows.values():
        if row.version_id not in candidates or not periods.get(row.entity_id):
            continue
        bundle, output, source = acquisition_evidence.load(uow, row.version_id, book)
        if (bundle.evidence_revision or 0) < 70:
            continue
        entity = next(e for e in bundle.entities if e.code == row.entity_code)
        if entity.functional_currency == bundle.group.transaction_currency:
            continue
        voided = {e.supersedes_event_key for e in bundle.events if e.event_type == "EVENT_VOIDED"}
        if not any(
            e.event_key not in voided
            and "prospective_split_destinations" in e.payload
            and e.effective_date <= periods[row.entity_id][-1].end
            for e in bundle.events
        ):
            continue
        key = (bundle.group.group_key, row.entity_id)
        if key in seen:
            continue
        group = collect(
            uow,
            rows,
            bundle,
            output,
            source,
            book=book,
            entity_id=row.entity_id,
            entity_code=row.entity_code,
            periods=periods[row.entity_id],
            functional=functional,
        )
        groups[group.id] = group
        captured[str(group.id)] = group.evidence
        seen.add(key)
    if params.binding is not None and params.binding.evidence[KEY] != captured:
        raise tie_outs.invalid("currency_view", "Retained split group evidence differs.")
    tie_outs.record_evidence(params, KEY, captured)
