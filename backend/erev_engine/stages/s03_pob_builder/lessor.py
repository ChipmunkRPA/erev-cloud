"""POL-231: reviewed eligible nonlease components and their associated operating lease."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from erev_engine.enums import ScopeFlag
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder.distinct import merge, obligation_judgement
from erev_engine.stages.s03_pob_builder.templates import PobDraft
from erev_engine.stages.state import BookContext


def combine(ctx: BookContext, st: IdentifiedState, drafts: Sequence[PobDraft]) -> list[PobDraft]:
    """Preserve separate components unless the election and reviewed criteria both apply.

    Each qualifying nonlease component names its associated lease. Predominance is a
    reviewed assessment, never inferred from prices. Ineligible components stay separate.
    """
    if str(ctx.framework) != "ASC606":
        return list(drafts)
    indexed = {(d.contract_key, d.obligation_key): d for d in drafts}
    groups: dict[tuple[str, str], list[tuple[PobDraft, bool, str, str]]] = {}
    for draft in drafts:
        if draft.scope_flag != ScopeFlag.IN_SCOPE_606:
            continue
        header = st.canonical.contracts[draft.contract_key].header
        # OTHER also holds unrelated assessments. They must not hide this assessment.
        lessor_header = dataclasses.replace(
            header,
            judgements=tuple(
                record
                for record in header.judgements
                if "lessor_lease_obligation_key" in record.outcome
            ),
        )
        record = obligation_judgement(
            lessor_header,
            "OTHER",
            ctx.book_code,
            draft.obligation_key,
        )
        if record is None or "lessor_lease_obligation_key" not in record.outcome:
            continue
        outcome = record.outcome
        if (
            ctx.policies.value(
                "scope.lessor_combination_expedient",
                contract=draft.contract_key,
                obligation=obligation_subject_key(
                    draft.contract_key, outcome["lessor_lease_obligation_key"]
                ),
            )
            != "ELECTED"
        ):
            continue
        lease_key = outcome["lessor_lease_obligation_key"]
        lease = indexed.get((draft.contract_key, lease_key))
        if lease is None or lease.scope_flag != ScopeFlag.LEASE_842:
            raise ValueError("POL-231 assessment must name an associated lease component")
        fields = (
            "lessor_same_transfer_pattern",
            "lessor_operating_lease",
            "lessor_nonlease_predominates",
        )
        if any(outcome.get(field) not in {"true", "false"} for field in fields):
            raise ValueError("POL-231 requires explicit eligibility and predominance assessments")
        asset_class = outcome.get("lessor_asset_class", "").strip()
        if not asset_class:
            raise ValueError("POL-231 requires the underlying asset class")
        if any(outcome[field] != "true" for field in fields[:2]):
            continue
        if draft.start_date != lease.start_date or draft.end_date != lease.end_date:
            raise ValueError("POL-231 assessed transfer timing conflicts with component dates")
        groups.setdefault((draft.contract_key, lease_key), []).append(
            (draft, outcome[fields[2]] == "true", asset_class, record.judgement_key)
        )
    consumed: set[tuple[str, str]] = set()
    combined: list[PobDraft] = []
    for key, assessed in sorted(groups.items()):
        if len({(predominates, asset) for _, predominates, asset, _ in assessed}) != 1:
            raise ValueError(
                "POL-231 components disagree on predominance or underlying asset class"
            )
        lease = indexed[key]
        components = sorted((item[0] for item in assessed), key=lambda d: d.subject_key)
        patterns = {
            (d.satisfaction_pattern, d.recognition_method, d.ratable_convention) for d in components
        }
        if len(patterns) != 1:
            raise ValueError("POL-231 nonlease components require the same transfer measure")
        predominates = assessed[0][1]
        host = components[0] if predominates else lease
        others = [d for d in [lease, *components] if d.subject_key != host.subject_key]
        result = merge(host, others, rule="S03-R-11")
        combined.append(
            dataclasses.replace(
                result,
                scope_flag=ScopeFlag.IN_SCOPE_606 if predominates else ScopeFlag.LEASE_842,
                routed_out=not predominates,
                lessor_judgement_keys=tuple(sorted(item[3] for item in assessed)),
            )
        )
        consumed.update((d.contract_key, d.obligation_key) for d in [lease, *components])
    return [d for d in drafts if (d.contract_key, d.obligation_key) not in consumed] + combined
