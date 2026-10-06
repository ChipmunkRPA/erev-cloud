"""Rule-based auto-approval under configuration change control (04 E-07, T-PLT-20, T-REF-26
AUTO_APPROVAL, §16.10 rev 1.104 "Auto-approval and the routing floor"; dev-guide DG-KRN-APR-01,
DG-KRN-APR-08; REQ-PLT-016; CTL-005; BUILD_SPEC RFD-5).

The subject is a probe ``SubjectSpec`` registered for ``IMPORT_COMMIT`` and submitted by an API
client — a system-originated standard item of the allow-list (PRD §2.5 ``AUTO-IMP-01``). Until
supervisor ruling R-26 (b) the two cases ran on a probe registered for ``FX_RATE_SET_VERSION`` that
a user submitted (rule ``AUTO-FX-01``); a rule approves no configuration version and nothing a
person prepared any more, so the mechanism is witnessed where the contract still has it, and the
user's submission of the same item stands beside it as the refusal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from erev_api.db.tables import approval_decision, audit_event, rule
from erev_api.enums import ApprovalSubjectType, PrincipalKind
from sqlalchemy import select
from support.subjects import ProbeSubjects, install

if TYPE_CHECKING:
    from conftest import Policies

IMPORT = ApprovalSubjectType.IMPORT_COMMIT
AUTO_IMP_01: dict[str, Any] = {
    "rule_key": "AUTO-IMP-01",
    "priority": 10,
    "conditions": [
        {"field": "subject.type", "op": "eq", "value": "IMPORT_COMMIT"},
        {"field": "source.channel", "op": "eq", "value": "API_CLIENT"},
    ],
    "outputs": {"auto_approve": True},
}
IMPORT_CASE = (
    "Import commit uploaded by an API client",
    {"subject.type": "IMPORT_COMMIT", "source.channel": "API_CLIENT"},
    {"rule_key": "AUTO-IMP-01", "outputs": {"auto_approve": True}},
)
# A second, less specific rule without the channel condition: by the rules alone it matches an
# import commit a USER submits too, so only the allow-list of R-26 (b) holds that item back.
AUTO_IMP_ANY: dict[str, Any] = {
    "rule_key": "AUTO-IMP-ANY",
    "priority": 0,
    "conditions": [{"field": "subject.type", "op": "eq", "value": "IMPORT_COMMIT"}],
    "outputs": {"auto_approve": True},
}
# The example case of the same item: the evaluation of a case applies the allow-list as a
# submission does (R-41 (7)), so it reports no match although rule AUTO-IMP-ANY fits the facts.
USER_CASE = (
    "Import commit submitted by a user: no rule approves it",
    {"subject.type": "IMPORT_COMMIT", "source.channel": "USER"},
    {"matched": False},
)


def decisions(policies: Policies, request_id: Any) -> list[tuple[Any, ...]]:
    return [
        tuple(row.values())
        for row in policies.rows(
            select(
                approval_decision.c.decision,
                approval_decision.c.approver_kind,
                approval_decision.c.auto_rule_set_version_id,
                approval_decision.c.auto_rule_id,
            ).where(approval_decision.c.approval_request_id == request_id)
        )
    ]


def test_published_auto_approval_rule_approves_standard_item(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = ProbeSubjects()
    install(monkeypatch, probe.spec(IMPORT, required_permission="import.approve"))
    _, version_id = policies.published(
        "AUTO-IMP", "AUTO_APPROVAL", [AUTO_IMP_01, AUTO_IMP_ANY], [IMPORT_CASE, USER_CASE]
    )
    [auto_rule] = policies.rows(
        select(rule.c.id).where(
            rule.c.rule_set_version_id == UUID(version_id), rule.c.rule_key == "AUTO-IMP-01"
        )
    )

    request = policies.submit_probe(IMPORT, probe, kind=PrincipalKind.API_CLIENT)
    assert request["status"] == "APPROVED"
    assert decisions(policies, request["id"]) == [
        ("AUTO_APPROVE", "SYSTEM", UUID(version_id), auto_rule["id"])
    ]
    assert probe.calls == [("approved", request["subject_id"], request["id"])]
    [event] = policies.rows(
        select(audit_event.c.after).where(
            audit_event.c.action == "approval_request.auto_approve",
            audit_event.c.object_id == request["id"],
        )
    )
    assert event["after"]["auto_rule"]["rule_key"] == "AUTO-IMP-01"
    assert event["after"]["auto_rule"]["rule_set_version_id"] == version_id

    # R-26 (b): the same item prepared by a person waits for a person although the published
    # rule AUTO-IMP-ANY matches it — the allow-list is asked before any rule is read.
    by_user = policies.submit_probe(IMPORT, probe)
    assert by_user["status"] == "PENDING"
    assert decisions(policies, by_user["id"]) == []
    assert probe.calls == [("approved", request["subject_id"], request["id"])]

    # ``auto_approval = False`` (BUILD_SPEC CTR-9: a non-standard item) withholds the rule also
    # beside a routing reading the command took itself: a reading that carries the matching rule
    # is refused there, and the withheld reading leaves the request to a person (R-66 (9)).
    withheld = policies.submit_probe(IMPORT, probe, kind=PrincipalKind.API_CLIENT, withheld=True)
    assert withheld["status"] == "PENDING"
    assert decisions(policies, withheld["id"]) == []
    assert probe.calls == [("approved", request["subject_id"], request["id"])]


@pytest.mark.control("CTL-005")
def test_ctl_005_unpublished_auto_approval_rule_does_not_approve(
    policies: Policies, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = ProbeSubjects()
    install(monkeypatch, probe.spec(IMPORT, required_permission="import.approve"))
    _, version_id = policies.tested("AUTO-IMP", "AUTO_APPROVAL", [AUTO_IMP_01], [IMPORT_CASE])

    request = policies.submit_probe(IMPORT, probe, kind=PrincipalKind.API_CLIENT)
    assert request["status"] == "PENDING"
    assert decisions(policies, request["id"]) == []
    assert probe.calls == []
