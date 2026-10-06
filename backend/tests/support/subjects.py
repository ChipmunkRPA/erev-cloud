"""A probe approval subject for approval engine tests (dev-guide §5.6; BUILD_SPEC PLF-10).

``ProbeSubjects`` keeps subject contents in memory and records the callbacks the engine runs.
``install`` registers its ``SubjectSpec`` for one E-08 subject type through ``monkeypatch``, so the
registry is restored after the test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects
from erev_api.approvals.subjects import SubjectSpec
from erev_api.db import new_id
from erev_api.enums import ApprovalSubjectType
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork


class ProbeCallbackError(RuntimeError):
    """Raised by ``on_approved`` when a test asks for a failing callback."""


@dataclass
class ProbeSubjects:
    contents: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[str, UUID, UUID]] = field(default_factory=list)
    fail_on_approved: bool = False

    def new_subject(self, **content: Any) -> UUID:
        subject_id = new_id()
        self.contents[subject_id] = {"name": "Probe subject", **content}
        return subject_id

    def _content(self, _: Session, subject_id: UUID) -> dict[str, Any]:
        return dict(self.contents[subject_id])

    def _approved(self, _: UnitOfWork, subject_id: UUID, request_id: UUID) -> None:
        if self.fail_on_approved:
            raise ProbeCallbackError("probe on_approved failed")
        self.calls.append(("approved", subject_id, request_id))

    def _rejected(self, _: UnitOfWork, subject_id: UUID, request_id: UUID) -> None:
        self.calls.append(("rejected", subject_id, request_id))

    def _voided(self, _: UnitOfWork, subject_id: UUID, request_id: UUID) -> None:
        self.calls.append(("voided", subject_id, request_id))

    def spec(
        self,
        subject_type: ApprovalSubjectType = ApprovalSubjectType.ROLE_CHANGE,
        *,
        required_permission: str = "access.approve",
        revenue_affecting: bool = False,
        min_approvers: int = 1,
    ) -> SubjectSpec:
        return SubjectSpec(
            subject_type=subject_type,
            table="role",
            required_permission=required_permission,
            revenue_affecting=revenue_affecting,
            min_approvers=min_approvers,
            content=self._content,
            entity_id=lambda _session, _subject_id: None,
            amount_functional=lambda _session, _subject_id: None,
            flags=lambda _session, _subject_id: frozenset(),
            on_approved=self._approved,
            on_rejected=self._rejected,
            on_voided=self._voided,
        )


def install(monkeypatch: pytest.MonkeyPatch, spec: SubjectSpec) -> SubjectSpec:
    """Register ``spec`` for its subject type for the duration of the test."""
    monkeypatch.setitem(subjects.SUBJECTS, spec.subject_type, spec)
    return spec
