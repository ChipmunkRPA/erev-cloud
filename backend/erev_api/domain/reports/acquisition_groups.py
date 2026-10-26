"""Present original mixed-acquisition group movements without invented member quotas."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from erev_api.uow import UnitOfWork
from erev_engine.bundle import InputBundle

from . import acquisition_evidence, acquisition_native, tie_outs
from .builders.contract_balance_rollforward import LINES, ContractRollforward

KEY = "mixed_acquisition_groups_v1"
EXTRA_LINES = ("GROUP_PERIOD_OPENING_REVENUE", "GROUP_ASSET_SETTLEMENTS")
LABELS = {
    "GROUP_PERIOD_OPENING_REVENUE": "Group revenue from each month's opening balance",
    "GROUP_ASSET_SETTLEMENTS": "Group assets transferred to receivables or settled",
}
MAPPING = {
    "OPENING": "OPENING",
    "CLOSING": "CLOSING",
    "OTHER": "OTHER",
    "BUSINESS_COMBINATIONS": "BUSINESS_COMBINATIONS",
    "FX": "FX_REMEASUREMENT",
    "INCREASES_BILLING": "BILLINGS",
    "DECREASES_CREDIT_MEMO": "BILLINGS",
    "INCREASES_CREDIT_MEMO": "BILLINGS",
    "REVENUE_FROM_OPENING_BALANCE": EXTRA_LINES[0],
    "REVENUE_FROM_OTHER_INCREASES": "REVENUE_FROM_PERIOD_BILLINGS",
    "REVENUE_IN_EXCESS_OF_BILLING": "REVENUE_FROM_PERIOD_BILLINGS",
    "INCREASES_NEGATIVE_REVENUE": "REVENUE_FROM_PERIOD_BILLINGS",
    "TRANSFERRED_TO_RECEIVABLES_OR_SETTLED": EXTRA_LINES[1],
    **dict.fromkeys(
        (
            "INCREASES_DEPOSIT_TRANSFER",
            "INCREASES_NONCASH",
            "INCREASES_FINANCING",
            "INCREASES_REFUND_RELEASE",
            "DECREASES_REFUND_LIABILITY",
            "DECREASES_CONTRA",
            "DECREASES_FINANCING",
            "INCREASES_REFUND_LIABILITY",
            "INCREASES_CONTRA",
            "RECLASSIFIED_BETWEEN_ASSET_CAPTIONS",
        ),
        "RECLASSIFICATIONS",
    ),
}


@dataclass(frozen=True)
class NativeGroup:
    id: UUID
    entity_id: UUID
    entity_code: str
    group_key: str
    currency: str
    members: tuple[tie_outs.BalanceRow, ...]
    snapshots: tuple[tuple[tie_outs.PeriodRef, dict[str, Any]], ...]
    facts: Mapping[str, Any]
    evidence: Mapping[str, Any]

    @property
    def keys(self) -> frozenset[tuple[UUID, UUID]]:
        return frozenset((m.contract_id, m.entity_id) for m in self.members)


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
) -> NativeGroup:
    population = set(bundle.group.member_contract_keys)
    members = tuple(
        sorted(
            (
                row
                for row in rows.values()
                if row.entity_id == entity_id and row.external_id in population
            ),
            key=lambda m: m.external_id,
        )
    )
    if {m.external_id for m in members} != population:
        raise tie_outs.invalid(
            "contract_external_id", "Mixed acquisition reporting requires the complete group."
        )
    member_versions = {}
    for member in members:
        original, _, held = acquisition_evidence.load(uow, member.version_id, book)
        if (
            original.group != bundle.group
            or held["input_sha256"] != source["input_sha256"]
            or held["output_sha256"] != source["output_sha256"]
        ):
            raise tie_outs.invalid(
                "currency_view", "Mixed group members do not share the original computation."
            )
        member_versions[str(member.contract_id)] = str(member.version_id)
    identity = uuid5(NAMESPACE_URL, f"erev:mixed-acquisition:{bundle.group.group_key}:{entity_id}")
    original_book = next(b for b in output["books"] if b["book_code"] == book)
    anchor = members[0]
    snapshots = []
    facts = {}
    for period in periods:
        native = acquisition_native.read(
            bundle,
            output,
            book=book,
            entity=entity_code,
            period=period,
            functional=functional,
        )
        if native is None:
            raise tie_outs.invalid(
                "currency_view",
                "Mixed acquisition lacks an original group snapshot for the selected range.",
            )
        snapshot = next(
            row
            for row in original_book["disclosure_rollforwards"]
            if row["entity"] == entity_code
            and row["period_key"] == period.key
            and row["view"] == native["view"]
        )
        # Validate every movement, including zero-valued known rows. Unknown nonzero
        # rows refuse rather than being folded into a residual.
        convert(snapshot)
        snapshots.append((period, snapshot))
        sources = native["sources"]
        if not sources:
            continue
        events = sorted({str(s.get("event_key", s.get("source_key", ""))) for s in sources})
        nodes = {str(s["trace_node_id"]) for s in sources if s.get("trace_node_id")}
        if native["view"] == "TRANSACTION":
            subjects = {subject for s in sources for subject in s.get("subjects", ())}
            nodes.update(
                n["id"]
                for n in original_book["trace"]["nodes"]
                if any(n["id"].startswith(f"opening_revenue_cum@{event}:") for event in events)
                and any(f":{subject}:" in n["id"] for subject in subjects)
            )
        if not nodes:
            raise tie_outs.invalid(
                "currency_view", "Mixed acquisition lacks original source nodes."
            )
        scale = Decimal(10) ** -native["minor_unit"]
        facts[f"{anchor.version_id}:{identity}:{entity_id}:{period.key}"] = {
            "event_key": ", ".join(events),
            "input_sha256": source["input_sha256"],
            "output_sha256": source["output_sha256"],
            "currency": native["currency"],
            "nodes": sorted(nodes),
            "amounts": {r.lower(): str(a * scale) for r, a in native["amounts"].items()},
            "native_cutover": native,
            "group_members": [
                {
                    "contract_id": str(m.contract_id),
                    "external_id": m.external_id,
                    "version_id": str(m.version_id),
                }
                for m in members
            ],
        }
    return NativeGroup(
        identity,
        entity_id,
        entity_code,
        bundle.group.group_key,
        snapshots[0][1]["currency"],
        members,
        tuple(snapshots),
        facts,
        {
            "input_sha256": source["input_sha256"],
            "output_sha256": source["output_sha256"],
            "member_versions": member_versions,
            "snapshots": [s for _, s in snapshots],
        },
    )


def convert(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Decimal]]:
    scale = Decimal(10) ** -snapshot["minor_unit"]
    result = {
        code: dict.fromkeys(tie_outs.ROLLFORWARD_BALANCES, Decimal(0))
        for code in (*LINES, *EXTRA_LINES)
    }
    if set(snapshot["lines"]) != acquisition_native.ROLES:
        raise tie_outs.invalid("currency_view", "Mixed group snapshot has different balance roles.")
    for role, lines in snapshot["lines"].items():
        if any(type(v) is not int for v in lines.values()):
            raise tie_outs.invalid("currency_view", "Mixed group movement amount is invalid.")
        if lines["CLOSING"] != sum(v for k, v in lines.items() if k != "CLOSING"):
            raise tie_outs.invalid("currency_view", "Original group movements do not reconcile.")
        for code, amount in lines.items():
            target = MAPPING.get(code)
            if target is None:
                if amount:
                    raise tie_outs.invalid("currency_view", "Unknown original group movement.")
                continue
            result[target][role.lower()] += Decimal(amount) * scale
    return result


def project(
    group: NativeGroup,
    *,
    opening: Sequence[tie_outs.BalanceRow],
    closing: Sequence[tie_outs.BalanceRow],
    monthly: Mapping[tuple[UUID, UUID], Mapping[tuple[UUID, UUID], tie_outs.BalanceRow]],
) -> ContractRollforward:
    def values(rows: Sequence[tie_outs.BalanceRow]) -> dict[str, Decimal]:
        selected = [r for r in rows if (r.contract_id, r.entity_id) in group.keys]
        if any(r.currency != group.currency for r in selected):
            raise tie_outs.invalid("currency_view", "Group endpoint currency differs.")
        return {
            role: sum((r.value(role) for r in selected), Decimal(0))
            for role in tie_outs.ROLLFORWARD_BALANCES
        }

    totals = None
    period_lines = {}
    previous = values(opening)
    for period, snapshot in group.snapshots:
        lines = convert(snapshot)
        if lines["OPENING"] != previous:
            raise tie_outs.invalid(
                "currency_view", "Original group opening differs from reported member balances."
            )
        endpoint = monthly.get((group.entity_id, period.id))
        if endpoint is not None and values(tuple(endpoint.values())) != lines["CLOSING"]:
            raise tie_outs.invalid(
                "currency_view", "Original group closing differs from reported member balances."
            )
        period_lines[period.id] = lines
        if totals is None:
            totals = {code: dict(amounts) for code, amounts in lines.items()}
        else:
            for code, amounts in lines.items():
                if code == "OPENING":
                    continue
                for role, amount in amounts.items():
                    if code == "CLOSING":
                        totals[code][role] = amount
                    else:
                        totals[code][role] += amount
        previous = lines["CLOSING"]
    if previous != values(closing) or totals is None:
        raise tie_outs.invalid(
            "currency_view", "Original group closing differs from reported member balances."
        )
    # Endpoint-only member rows are informational and never enter aggregate totals.
    members = []
    for member in group.members:
        lines = {code: dict.fromkeys(tie_outs.ROLLFORWARD_BALANCES, Decimal(0)) for code in LINES}
        for code, rows in (("OPENING", opening), ("CLOSING", closing)):
            lines[code] = values([r for r in rows if r.contract_id == member.contract_id])
        members.append(
            ContractRollforward(
                member.contract_id,
                member.external_id,
                member.customer_name,
                group.entity_id,
                group.entity_code,
                group.currency,
                lines,
            )
        )
    return ContractRollforward(
        group.id,
        f"Group {group.group_key}",
        None,
        group.entity_id,
        group.entity_code,
        group.currency,
        totals,
        period_lines,
        tuple(members),
    )
