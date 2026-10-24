"""Net agent opening income only where the complete original source set proves its bucket."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import contract_version, obligation_version
from erev_api.domain.reports import computation_sources, revenue_attribution, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry
from erev_api.enums import PrincipalKind
from erev_api.uow import UnitOfWork
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.state import PolicyResolver

LEGACY_KEY = "agent_opening_source_sets_v1"
PREVIOUS_KEY = "agent_opening_source_sets_v2"
KEY = "agent_opening_source_sets_v3"
SUPPORTED_KEYS = (KEY, PREVIOUS_KEY, LEGACY_KEY)
ZERO = Decimal(0)
HISTORY_KEY = "agent_historical_source_owners_v1"


def historical_enabled(params: ReportParams) -> bool:
    """Preserve saved-report admission while retaining the historical-owner interpretation."""
    if params.binding is not None and HISTORY_KEY not in params.binding.evidence:
        return False
    value = {"basis": "ORIGINAL_COMPUTATION_AND_PAID_HISTORY"}
    if params.binding is not None and params.binding.evidence[HISTORY_KEY] != value:
        raise tie_outs.invalid("currency_view", "Historical agent source interpretation differs.")
    tie_outs.record_evidence(params, HISTORY_KEY, value)
    return True


CONTRACTING_KEY = "agent_contracting_revenue_sources_v1"


def contracting_enabled(params: ReportParams) -> bool:
    """Admit another performer only with verified contracting-entity agent postings."""
    if params.binding is not None and CONTRACTING_KEY not in params.binding.evidence:
        return False
    value = {"basis": "ORIGINAL_CONTRACTING_ENTITY_NET_POSTINGS"}
    if params.binding is not None and params.binding.evidence[CONTRACTING_KEY] != value:
        raise tie_outs.invalid("currency_view", "Agent revenue-entity interpretation differs.")
    tie_outs.record_evidence(params, CONTRACTING_KEY, value)
    return True


def _contracting_policy(uow: UnitOfWork, row: tie_outs.BalanceRow) -> bool:
    source = uow.session.execute(
        select(contract_version.c.contract_computation_id, contract_version.c.book_code)
        .join(obligation_version, obligation_version.c.contract_version_id == contract_version.c.id)
        .where(
            contract_version.c.id == row.version_id,
            obligation_version.c.contract_id == row.contract_id,
            obligation_version.c.contracting_entity_id == row.entity_id,
            obligation_version.c.performing_entity_id != row.entity_id,
            obligation_version.c.principal_agent == "AGENT",
        )
        .limit(1)
    ).first()
    if source is None:
        return False
    if source.contract_computation_id is None:
        raise tie_outs.invalid("currency_view", "Agent revenue policy lacks original computation.")
    original = computation_sources.read_for_report(
        uow,
        source.contract_computation_id,
        system_snapshot=uow.principal.kind == PrincipalKind.SYSTEM,
    )
    book = next(b for b in original.bundle.books if b.book_code == source.book_code)
    return (
        PolicyResolver(book.policies).value("ic.revenue_entity", entity=row.entity_code)
        == "CONTRACTING_ENTITY"
    )


def _owners(
    proof: revenue_attribution.AmountProof, allowed: set[UUID], historical: bool
) -> list[str]:
    outside = {source.contract_id for source in proof.sources} - allowed
    if outside and (not historical or not outside <= set(proof.verified_source_owners)):
        raise ValueError(
            "Agent sources outside the selected group lack verified original membership."
        )
    return sorted(map(str, outside))


def key_for(evidence: Mapping[str, Any] | None) -> str:
    if evidence is None:
        return KEY
    return next((key for key in SUPPORTED_KEYS if key in evidence), LEGACY_KEY)


class MixedSources(ValueError):
    pass


def bucket(proof: revenue_attribution.AmountProof, start: date) -> str:
    """Classify a whole verified net amount, never assign a fraction to an individual source."""
    if proof.amount == 0:
        return "ZERO_NET"
    dates = {(owner, layer): created for owner, layer, created in proof.layer_dates}
    if not proof.sources or any((s.contract_id, s.layer_key) not in dates for s in proof.sources):
        raise ValueError("Agent net income lacks original source-layer creation dates.")
    kinds = {
        "OPENING"
        if s.movement_kind == "LIABILITY_LAYER_CONSUMED"
        and dates[s.contract_id, s.layer_key] < start
        else "NON_OPENING"
        for s in proof.sources
    }
    if len(kinds) != 1:
        raise MixedSources(
            "Agent net income mixes opening and non-opening sources; "
            "no per-source net allocation is retained."
        )
    return next(iter(kinds))


@dataclass(frozen=True)
class Result:
    entries: tuple[Entry, ...]
    eligible: dict[str, Decimal]
    evidence: dict[str, Any]
    paid_lines: set[UUID]
    opening_entries: tuple[Entry, ...]
    unresolved: set[str] = field(default_factory=set)


def read(
    uow: UnitOfWork,
    row: tie_outs.BalanceRow,
    entries: list[Entry],
    start: date,
    opening: Decimal,
    *,
    view: str = "transaction",
    net_entries: list[Entry] | None = None,
    allowed_source_contracts: set[UUID] | None = None,
    classify_opening: bool = True,
    allow_unresolved: bool = False,
    allow_historical_owners: bool = False,
    allow_contracting_revenue: bool = False,
) -> Result | None:
    if view not in {"transaction", "functional"}:
        raise ValueError("Agent source view must be transaction or functional.")
    allowed_owners = allowed_source_contracts or {row.contract_id}
    allow_contracting_revenue = allow_contracting_revenue and _contracting_policy(uow, row)
    agents = set(
        uow.session.scalars(
            select(obligation_version.c.obligation_key).where(
                obligation_version.c.contract_version_id == row.version_id,
                obligation_version.c.contract_id == row.contract_id,
                obligation_version.c.contracting_entity_id == row.entity_id,
                *(
                    ()
                    if allow_contracting_revenue
                    else (obligation_version.c.performing_entity_id == row.entity_id,)
                ),
                obligation_version.c.principal_agent == "AGENT",
            )
        )
    )
    if not agents:
        return None
    subjects = {obligation_subject_key(row.external_id, key) for key in agents}
    eligible = dict.fromkeys(subjects, ZERO)
    facts: dict[str, Any] = {
        subject: {"basis": "UNIFORM_NET_SOURCE_SET", "lines": []} for subject in subjects
    }
    converted = []
    opening_entries = []
    paid: set[UUID] = set()
    seen_net: set[UUID] = set()
    unresolved: set[str] = set()

    def category_for(proof: revenue_attribution.AmountProof, subject: str) -> str:
        if opening <= 0:
            return "NO_OPENING"
        if not classify_opening:
            return "NO_CONSUMPTION"
        try:
            return bucket(proof, start)
        except MixedSources:
            if not allow_unresolved:
                raise
            unresolved.add(subject)
            facts[subject]["basis"] = "MIXED_NET_SOURCE_SET"
            return "UNRESOLVED"

    for entry in entries:
        if not entry.flow.is_revenue or entry.subject_key not in subjects:
            converted.append(entry)
            continue
        if entry.line_id is None:
            raise tie_outs.invalid("currency_view", "Agent income lacks an original control line.")
        try:
            _, gross = revenue_attribution.for_control(uow, entry.line_id, view=view)
            if not gross.components or gross.delta.amount != -Fraction(entry.flow.amount):
                raise ValueError(
                    "Original agent gross relief does not reconcile to the posted flow."
                )
            net = ZERO
            opening_net = ZERO
            lines = []
            paid.update((entry.line_id, *gross.paid_line_ids))
            for identity, role, txn, functional in gross.components:
                paid.add(identity)
                if role != "REVENUE":
                    continue
                seen_net.add(identity)
                proof = revenue_attribution.verify_component(uow, identity, view=view)
                posted_amount = txn if view == "transaction" else functional
                if proof.amount != Fraction(posted_amount):
                    raise ValueError("Agent net amount differs from its original posting.")
                historical_owners = _owners(proof, allowed_owners, allow_historical_owners)
                category = category_for(proof, entry.subject_key)
                amount = -Decimal(posted_amount)
                net += amount
                if category == "OPENING":
                    eligible[entry.subject_key] += amount
                    opening_net += amount
                paid.update(proof.paid_line_ids)
                lines.append(
                    {
                        **(
                            {"historical_source_owners": historical_owners}
                            if historical_owners
                            else {}
                        ),
                        "net_line": str(identity),
                        "bucket": category,
                        "net_income": str(amount),
                        "sources": [
                            {
                                k: (
                                    v.isoformat()
                                    if isinstance(v, date)
                                    else str(v)
                                    if isinstance(v, UUID)
                                    else v
                                )
                                for k, v in asdict(s).items()
                            }
                            for s in proof.sources
                        ],
                        "layer_dates": [
                            [str(c), k, d.isoformat()] for c, k, d in proof.layer_dates
                        ],
                        "evidence": [[str(c), digest] for c, digest in proof.evidence],
                    }
                )
            facts[entry.subject_key]["lines"].append(
                {
                    "control_line": str(entry.line_id),
                    "gross_relief": str(entry.flow.amount),
                    "net_income": str(net),
                    "components": [[str(i), r, t, f] for i, r, t, f in gross.components],
                    "source_sets": lines,
                }
            )
            converted.append(replace(entry, flow=replace(entry.flow, amount=net)))
            opening_entries.append(replace(entry, flow=replace(entry.flow, amount=opening_net)))
        except ValueError as error:
            raise tie_outs.invalid("currency_view", str(error)) from error
    if net_entries is not None and not seen_net <= {entry.line_id for entry in net_entries}:
        raise tie_outs.invalid(
            "currency_view", "Agent control counterpart is absent from the retained net population."
        )
    for entry in net_entries or []:
        if entry.subject_key not in subjects or entry.line_id in seen_net:
            continue
        if entry.line_id is None:
            raise tie_outs.invalid(
                "currency_view", "Agent net posting lacks its original identity."
            )
        try:
            from .opening_agent_postings import supplier_pair

            pair_rows, supplier = supplier_pair(uow, entry.line_id, view=view)
            proof = revenue_attribution.verify_component(uow, entry.line_id, view=view)
            if proof.amount != -Fraction(entry.flow.amount):
                raise ValueError("Agent net-only amount differs from the original posting.")
            historical_owners = _owners(proof, allowed_owners, allow_historical_owners)
            category = category_for(proof, entry.subject_key)
            amount = entry.flow.amount if category == "OPENING" else ZERO
            eligible[entry.subject_key] += amount
            converted.append(entry)
            opening_entries.append(replace(entry, flow=replace(entry.flow, amount=amount)))
            paid.update(
                [*(line["id"] for line in pair_rows), *proof.paid_line_ids, *supplier.paid_line_ids]
            )
            facts[entry.subject_key]["lines"].append(
                {
                    "control_line": None,
                    "gross_relief": "0",
                    "net_income": str(entry.flow.amount),
                    "basis": "NET_SUPPLIER_REALLOCATION",
                    "components": [
                        [
                            str(line["id"]),
                            line["account_role"],
                            str(line["amount_txn"]),
                            str(line["amount_functional"]),
                        ]
                        for line in pair_rows
                    ],
                    "source_sets": [
                        {
                            **(
                                {"historical_source_owners": historical_owners}
                                if historical_owners
                                else {}
                            ),
                            "net_line": str(entry.line_id),
                            "bucket": category,
                            "net_income": str(entry.flow.amount),
                            "sources": [
                                {
                                    k: v.isoformat()
                                    if isinstance(v, date)
                                    else str(v)
                                    if isinstance(v, UUID)
                                    else v
                                    for k, v in asdict(source).items()
                                }
                                for source in proof.sources
                            ],
                            "layer_dates": [
                                [str(c), k, d.isoformat()] for c, k, d in proof.layer_dates
                            ],
                            "evidence": [[str(c), digest] for c, digest in proof.evidence],
                        }
                    ],
                }
            )
        except ValueError as error:
            raise tie_outs.invalid("currency_view", str(error)) from error
    if allow_contracting_revenue:
        for detail in facts.values():
            if detail["lines"]:
                detail["contracting_revenue_entity_id"] = str(row.entity_id)
    return Result(tuple(converted), eligible, facts, paid, tuple(opening_entries), unresolved)
