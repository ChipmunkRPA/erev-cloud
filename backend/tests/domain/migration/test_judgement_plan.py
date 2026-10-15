"""Reviewed migration intent resolves fresh targets without changing its judgement content."""

from datetime import date
from uuid import UUID

import pytest
from erev_api.domain.migration.judgement_plan import ProposedJudgement
from erev_api.enums import BookCode, JudgementTopic
from erev_api.problems import Problem


@pytest.mark.parametrize("distinctness", ["distinct", "nondistinct"])
def test_obligation_body_preserves_reviewed_content(distinctness: str) -> None:
    proposed = ProposedJudgement(
        contract_key="C",
        obligation_key="O",
        topic=JudgementTopic.POB_DISTINCT_OVERRIDE,
        book=None,
        conclusion="Proposed distinctness conclusion",
        rationale="Awaiting review",
        distinctness=distinctness,
        template_version_id=UUID(int=10),
        template_content_sha256="a" * 64,
    )
    content = proposed.review_content()
    body = proposed.body(UUID(int=1), {"O": UUID(int=2)})
    assert body.subject_type == "obligation"
    assert body.subject_id == UUID(int=2)
    assert body.contract_id == UUID(int=1)
    assert body.questionnaire == content["questionnaire"]
    assert body.conclusion == content["conclusion"]
    assert body.rationale == content["rationale"]
    assert content["template_version_id"] == str(UUID(int=10))
    assert content["template_content_sha256"] == "a" * 64
    assert content["proposed_assessment"] is None
    with pytest.raises(Problem, match="target is missing"):
        proposed.body(UUID(int=1), {"OTHER": UUID(int=2)})


@pytest.mark.parametrize("book", [BookCode.ASC606, BookCode.IFRS15])
def test_collectibility_body_and_dated_assessment_are_explicit(book: BookCode) -> None:
    proposed = ProposedJudgement(
        contract_key="C",
        obligation_key=None,
        topic=JudgementTopic.COLLECTIBILITY,
        book=book,
        conclusion="Proposed collectibility conclusion",
        rationale="Awaiting review",
        assessment_date=date(2026, 1, 1),
    )
    body = proposed.body(UUID(int=1), {})
    assert body.subject_type == "contract"
    assert body.subject_id == body.contract_id == UUID(int=1)
    assert body.book == book
    assert body.questionnaire == {}
    assert proposed.review_content()["proposed_assessment"] == {
        "event_type": "COLLECTIBILITY_ASSESSED",
        "book": book.value,
        "is_probable": True,
        "effective_date": "2026-01-01",
    }
    assert "status" not in proposed.review_content()
    assert "reviewer_id" not in proposed.review_content()
