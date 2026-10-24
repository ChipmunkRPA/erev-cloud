"""Verified contracting-entity control relief for cross-entity principal obligations."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import obligation_version, subledger_line
from erev_api.uow import UnitOfWork
from erev_engine.stages.s01_canonicalize import obligation_subject_key

from . import opening_source_membership, revenue_attribution, tie_outs
from .builders import ReportParams
from .builders.contract_balance_rollforward import Entry

KEY = "opening_intercompany_sources_v1"


class Reader:
    def __init__(self, uow: UnitOfWork, params: ReportParams, view: str):
        self.uow, self.params, self.view = uow, params, view
        self.enabled = params.binding is None or KEY in params.binding.evidence
        self.evidence: dict[str, Any] = {}
        self.paid: set[UUID] = set()

    def read(
        self,
        row: tie_outs.BalanceRow,
        obligations: Sequence[Mapping[Any, Any]],
        entries: Sequence[Entry],
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}
        subjects = {
            obligation_subject_key(row.external_id, item["obligation_key"]): item
            for item in obligations
            if item["performing_entity_id"] != row.entity_id
            and str(item["principal_agent"]) == "PRINCIPAL"
        }
        facts: dict[str, Any] = {
            subject: {
                "basis": "CONTRACTING_ENTITY_INTERCOMPANY_CONTROL",
                "contracting_entity_id": str(row.entity_id),
                "performing_entity_id": str(item["performing_entity_id"]),
                "lines": [],
            }
            for subject, item in subjects.items()
        }
        owners = (
            set(
                self.uow.session.scalars(
                    select(obligation_version.c.contract_id).where(
                        obligation_version.c.contract_version_id == row.version_id,
                        obligation_version.c.contracting_entity_id == row.entity_id,
                    )
                )
            )
            if subjects and entries
            else set()
        )
        for entry in entries:
            if not entry.flow.is_revenue or entry.subject_key not in subjects:
                continue
            try:
                if entry.line_id is None:
                    raise ValueError("Intercompany relief lacks an original control line.")
                control = (
                    self.uow.session.execute(
                        select(subledger_line).where(subledger_line.c.id == entry.line_id)
                    )
                    .mappings()
                    .one()
                )
                if (
                    control["entry_kind"] != "INTERCOMPANY"
                    or control["account_role"] != "CONTRACT_LIABILITY"
                    or control["contract_id"] != row.contract_id
                    or control["entity_id"] != row.entity_id
                    or control["subject_key"] != entry.subject_key
                ):
                    raise ValueError("Intercompany relief has a different original identity.")
                counterpart, proof = revenue_attribution.for_control(
                    self.uow, entry.line_id, view=self.view
                )
                if proof.components or proof.delta.amount != -entry.flow.amount:
                    raise ValueError("Intercompany due-to sources differ from control relief.")
                historical_owners = opening_source_membership.verify(
                    proof, owners, historical=opening_source_membership.enabled(self.params)
                )
                self.paid.update((entry.line_id, counterpart, *proof.paid_line_ids))
                facts[entry.subject_key]["lines"].append(
                    {
                        **(
                            {"historical_source_owners": historical_owners}
                            if historical_owners
                            else {}
                        ),
                        "control_line": str(entry.line_id),
                        "due_to_line": str(counterpart),
                        "control_relief": str(entry.flow.amount),
                        "sources": list(map(str, proof.delta.source_ids)),
                        "evidence": [
                            [str(identity), digest] for identity, digest in proof.evidence
                        ],
                    }
                )
            except ValueError as error:
                raise tie_outs.invalid("currency_view", str(error)) from error
        for subject, detail in facts.items():
            detail["lines"].sort(key=lambda item: item["control_line"])
            self.evidence[f"{row.version_id}:{row.entity_id}:{subject}"] = detail
        return facts

    def retain(self) -> None:
        if not self.enabled:
            return
        if self.params.binding is not None and self.params.binding.evidence[KEY] != self.evidence:
            raise tie_outs.invalid(
                "currency_view", "Intercompany opening sources differ from retained evidence."
            )
        tie_outs.record_evidence(self.params, KEY, self.evidence)
        tie_outs.require_members(self.params, "opening_intercompany_paid_line", self.paid)
        tie_outs.record_members(self.params, "opening_intercompany_paid_line", self.paid)
