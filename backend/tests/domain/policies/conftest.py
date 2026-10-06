"""Shared fixtures of the configuration lifecycle tests (BUILD_SPEC RFD-5).

Maya holds Revenue Accountant (``config.author``); Marcus holds Controller (``config.approve``) and
is enrolled in MFA. ``policies`` drives the API-R-25, API-R-57 and API-R-09 routes as them, and
``Policies.submit_probe`` submits a probe approval subject (``support.subjects``) as Maya through
the approval engine.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine as approvals
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import api_client
from erev_api.enums import ApprovalSubjectType, PrincipalKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import unit_of_work
from fastapi import FastAPI
from sqlalchemy import Select, insert
from support.db import TestDatabase
from support.http import HttpResponse, call
from support.principals import (
    Actor,
    Member,
    colleague,
    cookie_headers,
    enrolled,
    member,
    sign_in,
    workspace,
)
from support.rows import api_client_values, insert_role_assignment
from support.subjects import ProbeSubjects

RULE_SETS = "/api/v1/rule-sets"
VERSIONS = "/api/v1/rule-set-versions"
APPROVALS = "/api/v1/approvals"

# An example case: name, input facts, expected evaluation.
type Case = tuple[str, Mapping[str, Any], Mapping[str, Any]]


def context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def assign(someone: Member, *codes: str) -> None:
    """Grant default roles directly (``support.rows``), without the SoD check of assignment."""
    with tenant_session(context(someone.tenant_id)) as session:
        for code in codes:
            insert_role_assignment(
                session,
                tenant_id=someone.tenant_id,
                membership_id=someone.membership_id,
                role_code=code,
            )


@dataclass(frozen=True, slots=True)
class Policies:
    app: FastAPI
    clock: FrozenClock
    keyring: KeyRing
    settings: Settings
    maya: Actor
    marcus: Actor

    @property
    def tenant_id(self) -> UUID:
        return self.maya.member.tenant_id

    def get(self, path: str, actor: Actor | None = None, **params: str) -> HttpResponse:
        who = actor or self.maya
        return call(
            self.app, "GET", path, params=params, headers=cookie_headers(who.token, key=False)
        )

    def post(
        self, path: str, json: Mapping[str, Any] | None = None, actor: Actor | None = None
    ) -> HttpResponse:
        who = actor or self.maya
        return call(
            self.app,
            "POST",
            path,
            json=dict(json or {}),
            headers=cookie_headers(who.token, who.csrf_token),
        )

    def patch(self, path: str, json: Mapping[str, Any], *, etag: str) -> HttpResponse:
        return call(
            self.app,
            "PATCH",
            path,
            json=dict(json),
            headers=cookie_headers(self.maya.token, self.maya.csrf_token, **{"If-Match": etag}),
        )

    def rows(self, statement: Select[Any]) -> list[dict[str, Any]]:
        with tenant_session(context(self.tenant_id), read_only=True) as session:
            return [dict(row) for row in session.execute(statement).mappings()]

    def rule_set(self, code: str, kind: str) -> str:
        created = self.post(RULE_SETS, {"code": code, "kind": kind})
        assert created.status_code == 201, created.text
        return str(created.json()["id"])

    def version(self, rule_set_id: str, **body: Any) -> str:
        created = self.post(f"{RULE_SETS}/{rule_set_id}/versions", body)
        assert created.status_code == 201, created.text
        return str(created.json()["id"])

    def add_rule(self, version_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        added = self.post(f"{VERSIONS}/{version_id}/rules", body)
        assert added.status_code in (200, 201), added.text
        return dict(added.json())

    def add_case(self, version_id: str, case: Case) -> dict[str, Any]:
        name, facts, expected = case
        added = self.post(
            f"{VERSIONS}/{version_id}/test-cases",
            {"name": name, "input": facts, "expected_output": expected},
        )
        assert added.status_code == 201, added.text
        return dict(added.json())

    def draft(
        self,
        code: str,
        kind: str,
        rules: Sequence[Mapping[str, Any]],
        cases: Sequence[Case],
        **version: Any,
    ) -> tuple[str, str]:
        """A rule set with a DRAFT version holding ``rules`` and ``cases``."""
        rule_set_id = self.rule_set(code, kind)
        version_id = self.version(rule_set_id, **version)
        for body in rules:
            self.add_rule(version_id, body)
        for case in cases:
            self.add_case(version_id, case)
        return rule_set_id, version_id

    def tested(
        self,
        code: str,
        kind: str,
        rules: Sequence[Mapping[str, Any]],
        cases: Sequence[Case],
        **version: Any,
    ) -> tuple[str, str]:
        rule_set_id, version_id = self.draft(code, kind, rules, cases, **version)
        tested = self.post(f"{VERSIONS}/{version_id}/test")
        assert (tested.status_code, tested.json()["status"]) == (200, "TESTED"), tested.text
        return rule_set_id, version_id

    def submit(self, version_id: str) -> dict[str, Any]:
        submitted = self.post(f"{VERSIONS}/{version_id}/submit", {"comment": "Ready for review"})
        assert submitted.status_code == 200, submitted.text
        return dict(submitted.json())

    def approve(self, request_id: str, approver: Actor | None = None) -> HttpResponse:
        """Approve through API-R-09 with the hashes the approval detail shows."""
        who = approver or self.marcus
        detail = self.get(f"{APPROVALS}/{request_id}", who)
        assert detail.status_code == 200, detail.text
        preview = detail.json()["impact_preview"]
        return self.post(
            f"{APPROVALS}/{request_id}/approve",
            {
                "subject_content_sha256": detail.json()["subject"]["content_sha256"],
                "impact_preview_sha256": None if preview is None else preview["sha256"],
                "comment": "Reviewed the rules and the simulation",
            },
            actor=who,
        )

    def published(
        self,
        code: str,
        kind: str,
        rules: Sequence[Mapping[str, Any]],
        cases: Sequence[Case],
        **version: Any,
    ) -> tuple[str, str]:
        """A version tested and submitted by Maya and approved, so published, by Marcus."""
        rule_set_id, version_id = self.tested(code, kind, rules, cases, **version)
        submitted = self.submit(version_id)
        approved = self.approve(str(submitted["approval_request_id"]))
        assert approved.status_code == 200, approved.text
        current = self.get(f"{VERSIONS}/{version_id}")
        assert current.json()["status"] == "PUBLISHED", current.text
        return rule_set_id, version_id

    def submit_probe(
        self,
        subject_type: ApprovalSubjectType,
        probe: ProbeSubjects,
        *,
        kind: PrincipalKind = PrincipalKind.USER,
        withheld: bool = False,
    ) -> dict[str, Any]:
        """Submit a probe subject through ``approvals.submit`` (DG-KRN-APR-01): as Maya, or with
        ``kind`` ``API_CLIENT`` as an integration's client — the originator of the
        system-originated items a rule may approve (04 §16.10 rev 1.104). ``withheld``: as a
        subject command that takes its own routing reading and withholds auto-approval."""
        if kind is PrincipalKind.API_CLIENT:
            client = api_client_values(self.tenant_id, name=f"svc-probe-{secrets.token_hex(3)}")
            with tenant_session(context(self.tenant_id)) as session:
                session.execute(insert(api_client).values(**client))
            return self.submit_probe_as(
                subject_type,
                probe,
                Principal(
                    kind=PrincipalKind.API_CLIENT,
                    id=UUID(str(client["id"])),
                    tenant_id=self.tenant_id,
                    membership_id=None,
                    display_name="svc-salesforce",
                    roles=(),
                    permissions=frozenset({"import.upload"}),
                    permission_scopes=MappingProxyType({"import.upload": "*"}),
                    entity_scope="*",
                    auth_method="client_credentials",
                    mfa_verified_at=None,
                    session_id=None,
                    support_grant_id=None,
                    on_behalf_of_id=None,
                ),
                withheld=withheld,
            )
        principal = Principal(
            kind=PrincipalKind.USER,
            id=self.maya.member.user_id,
            tenant_id=self.tenant_id,
            membership_id=self.maya.member.membership_id,
            display_name="Maya",
            roles=("revenue_accountant",),
            permissions=frozenset(),
            permission_scopes=MappingProxyType({}),
            entity_scope="*",
            auth_method="password",
            mfa_verified_at=None,
            session_id=None,
            support_grant_id=None,
            on_behalf_of_id=None,
        )
        return self.submit_probe_as(subject_type, probe, principal)

    def submit_probe_as(
        self,
        subject_type: ApprovalSubjectType,
        probe: ProbeSubjects,
        principal: Principal,
        *,
        withheld: bool = False,
    ) -> dict[str, Any]:
        ctx = RequestContext(
            principal=principal,
            tenant_kind=TenantKind.PRODUCTION,
            request_id="tests-policies-probe",
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=self.clock.now(),
            format_locale="en-US",
        )
        files = LocalFileStore(self.settings.file_root)
        with unit_of_work(ctx, clock=self.clock, keyring=self.keyring, files=files) as uow:
            subject_id = probe.new_subject()
            if withheld:
                # A subject command that withholds auto-approval says so when it takes its reading
                # (``route_submission(auto_approval=False)``): the reading carries no rule. A
                # reading that auto-approves beside ``auto_approval = False`` is refused (R-66
                # (9)), so the argument can never be ignored.
                matching = approvals.route_submission(uow, subject_type, subject_id)
                assert matching.auto_rule is not None
                with pytest.raises(ValueError, match="auto_approval=False"):
                    approvals.submit(
                        uow,
                        subject_type=subject_type,
                        subject_id=subject_id,
                        summary="Probe submission",
                        auto_approval=False,
                        routing_decision=matching,
                    )
                reading = approvals.route_submission(
                    uow, subject_type, subject_id, auto_approval=False
                )
                assert reading.auto_rule is None
                # Rev 1.273 (item ACT-FLAGS-1; DG-KRN-APR-01): routing facts beside a reading are
                # a second statement of what the reading states already — refused, whichever of
                # the two is given, and nothing is written.
                for facts in ({"flags": ()}, {"amount": None}):
                    with pytest.raises(ValueError, match="beside a routing decision"):
                        approvals.submit(
                            uow,
                            subject_type=subject_type,
                            subject_id=subject_id,
                            summary="Probe submission",
                            auto_approval=False,
                            routing_decision=reading,
                            **facts,
                        )
                request = approvals.submit(
                    uow,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    summary="Probe submission",
                    auto_approval=False,
                    routing_decision=reading,
                )
            else:
                request = approvals.submit(
                    uow,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    summary="Probe submission",
                )
            uow.commit()
        return dict(request)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def policies(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> Policies:
    maya = member(keyring, clock)
    marcus = colleague(maya.tenant_id, "marcus")
    assign(maya, "revenue_accountant")
    assign(marcus, "controller")
    return Policies(
        app=app,
        clock=clock,
        keyring=keyring,
        settings=app_settings,
        maya=workspace(app, maya, sign_in(app, maya.email)),
        marcus=enrolled(app, clock, marcus),
    )
