"""Exact proposed judgement content for independent opening-migration promotion review.

BS3-D-23/26: each distinct/nondistinct template line needs its distinctness judgement, and
collectibility must be reviewed per enabled book. These are proposals, not reviewed records.
Natural contract/obligation keys survive the reproduction savepoint; database target ids do not.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import pob_template_version, product
from erev_api.domain.contracts import activation, repo
from erev_api.enums import BookCode, JudgementTopic
from erev_api.problems import Problem
from erev_api.schemas.judgements import JudgementCreateIn


@dataclass(frozen=True, slots=True)
class ProposedJudgement:
    contract_key: str
    obligation_key: str | None
    topic: JudgementTopic
    book: BookCode | None
    conclusion: str
    rationale: str
    assessment_date: date | None = None
    distinctness: str | None = None
    template_version_id: UUID | None = None
    template_content_sha256: str | None = None

    def body(self, contract_id: UUID, obligation_ids: Mapping[str, UUID]) -> JudgementCreateIn:
        """Resolve targets only after booking; never substitute the contract for a missing line."""
        subject_id = contract_id
        questionnaire: dict[str, Any] = {}
        if self.obligation_key is not None:
            if self.obligation_key not in obligation_ids:
                raise Problem(
                    "invalid-transition", "A reviewed migration judgement target is missing."
                )
            subject_id = obligation_ids[self.obligation_key]
            questionnaire = {
                "obligation_key": self.obligation_key,
                "distinctness": self.distinctness,
            }
        return JudgementCreateIn(
            topic=self.topic,
            subject_type="contract" if self.obligation_key is None else "obligation",
            subject_id=subject_id,
            contract_id=contract_id,
            book=self.book,
            conclusion=self.conclusion,
            rationale=self.rationale,
            questionnaire=questionnaire,
        )

    def review_content(self) -> dict[str, Any]:
        return {
            "contract_key": self.contract_key,
            "obligation_key": self.obligation_key,
            "topic": self.topic.value,
            "book": None if self.book is None else self.book.value,
            "conclusion": self.conclusion,
            "rationale": self.rationale,
            "questionnaire": {}
            if self.obligation_key is None
            else {
                "obligation_key": self.obligation_key,
                "distinctness": self.distinctness,
            },
            "template_version_id": None
            if self.template_version_id is None
            else str(self.template_version_id),
            "template_content_sha256": self.template_content_sha256,
            "proposed_assessment": None
            if self.obligation_key is not None
            else {
                "event_type": "COLLECTIBILITY_ASSESSED",
                "book": self.book.value if self.book else None,
                "is_probable": True,
                "effective_date": None
                if self.assessment_date is None
                else self.assessment_date.isoformat(),
            },
        }


def plan(session: Session, contract_id: UUID, migration_no: str) -> tuple[ProposedJudgement, ...]:
    current = repo.get_contract(session, contract_id)
    key = str(current["external_id"])
    obligations = repo.obligations(session, contract_id)
    product_ids = {UUID(str(row["product_id"])) for row in obligations}
    # Same PUBLISHED-version selection as the activation checklist. Retain the concrete
    # version identity and content hash so a later publication changes the review basis.
    templates = {
        UUID(str(row["product_id"])): row
        for row in session.execute(
            select(
                product.c.id.label("product_id"),
                product.c.code,
                pob_template_version.c.id,
                pob_template_version.c.distinctness,
                pob_template_version.c.content_sha256,
            )
            .join(
                pob_template_version,
                pob_template_version.c.pob_template_id == product.c.default_pob_template_id,
            )
            .where(product.c.id.in_(product_ids), pob_template_version.c.status == "PUBLISHED")
            .order_by(product.c.id, pob_template_version.c.version_no)
        ).mappings()
    }
    rationale = (
        f"Proposed from legacy migration {migration_no}; subject to independent promotion "
        "review (BUILD_SPEC BS3-D-23/26)."
    )
    result: list[ProposedJudgement] = []
    for row in sorted(obligations, key=lambda item: str(item["obligation_key"])):
        template = templates.get(UUID(str(row["product_id"])))
        if template is None:
            raise Problem(
                "invalid-transition", "Migration judgement planning needs published templates."
            )
        flag = str(template["distinctness"])
        if flag == "series":
            continue
        if flag not in {"distinct", "nondistinct"}:
            raise Problem("invalid-transition", "Migration template distinctness needs a decision.")
        obligation = str(row["obligation_key"])
        result.append(
            ProposedJudgement(
                contract_key=key,
                obligation_key=obligation,
                topic=JudgementTopic.POB_DISTINCT_OVERRIDE,
                book=None,
                conclusion=(
                    f"{obligation} ({template['code']}) is {flag}: legacy migration {migration_no}."
                ),
                rationale=rationale,
                distinctness=flag,
                template_version_id=UUID(str(template["id"])),
                template_content_sha256=str(template["content_sha256"]),
            )
        )
    books = activation.enabled_books(session, UUID(str(current["contracting_entity_id"])))
    if not books:
        raise Problem(
            "invalid-transition", "Migration collectibility review needs an enabled book."
        )
    for book in books:
        result.append(
            ProposedJudgement(
                contract_key=key,
                obligation_key=None,
                topic=JudgementTopic.COLLECTIBILITY,
                book=BookCode(book),
                assessment_date=current["inception_date"],
                conclusion=f"Collectibility probable: legacy migration {migration_no}.",
                rationale=rationale,
            )
        )
    return tuple(result)
