"""ACT-2 (record §34; DG-AK-41 rev 1.38, D-98 candidate 107): the runner's step registry declares
each plan step's API permission once, and the declaration equals the API's own — the route's
recorded ``x-erev-permission`` for a guarded route, the domain module's permission set for a
per-subject route, the approval engine's subject spec for a decision. No parallel table of truths:
the registry references the API's constants and the tests read the routes from the application.
"""

from __future__ import annotations

import pytest
from erev_api.approvals import subjects
from erev_api.auth.dependencies import PERMISSION_EXTENSION
from erev_api.auth.permissions import DEFAULT_ROLES, spec
from erev_api.config import Settings
from erev_api.domain.platform import attachments, file_access
from erev_api.domain.reference import commands as reference_commands
from erev_api.domain.reference import periods as reference_periods
from erev_api.domain.reports import framework as report_framework
from erev_api.enums import ApprovalSubjectType, FilePurpose, PrincipalKind
from erev_api.main import create_app
from fastapi.routing import APIRoute
from support.answer_keys.ledger_resolver import SUBJECTS
from support.answer_keys.platform_plan import (
    ESTIMATE_MARKER,
    PLATFORM_KEY_IDS,
    PRESET_HANDLER,
    H,
    Step,
    load_platform_key,
    plan,
)
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.step_permissions import (
    EVIDENCE_PERMISSIONS,
    KINDS,
    PERMISSIONS,
    StepPermission,
    check,
    required_permissions,
)
from support.answer_keys.workspace_adapter import Call, LedgerEntry

API_HANDLERS = frozenset(handler for handler in H.values() if handler.startswith("erev_api."))


def _routes(app) -> dict[tuple[str, str], APIRoute]:  # noqa: ANN001
    """Every mounted route by (method, path), through the application's included routers."""
    found: dict[tuple[str, str], APIRoute] = {}

    def walk(items) -> None:  # noqa: ANN001
        for item in items:
            if isinstance(item, APIRoute):
                for method in item.methods:
                    found[(method, item.path)] = item
                continue
            original = getattr(item, "original_router", None)
            if original is not None:
                walk(original.routes)
            elif hasattr(item, "routes"):
                walk(item.routes)

    walk(app.routes)
    return found


def _call(handler: str, actor: str, subject: str, **detail: str) -> Call:
    step = Step("CONTRACTS", actor, handler, subject, detail)
    return Call(handler=handler, actor=actor, kwargs={}, step=step)


def _entry(call: Call) -> LedgerEntry:
    return LedgerEntry(
        call=call, actor=call.actor, app_at=None, server_at=None, known_at=None, result=None
    )


def test_every_plan_step_with_an_api_handler_declares_its_permission() -> None:
    """Every handler the five keys' plans name (PROVISION, PERSONAS, WORLD, CONTRACTS, TIMELINE
    and the CHECKPOINT reads) has exactly one registry entry of a known kind, and the registry
    covers the whole handler table — a new handler without a declaration fails here."""
    used = {
        step.handler
        for key_id in PLATFORM_KEY_IDS
        for step in plan(load_platform_key(key_id)).steps
        if step.handler.startswith("erev_api.")
    }
    assert used <= set(PERMISSIONS)
    assert set(PERMISSIONS) == API_HANDLERS | {PRESET_HANDLER}
    for handler, declared in PERMISSIONS.items():
        assert isinstance(declared, StepPermission), handler
        assert declared.kind in KINDS, handler
        if declared.kind == "route":
            assert declared.method and declared.path and len(declared.required) == 1, handler
        elif declared.kind == "handler":
            assert declared.method and declared.path and declared.required, handler
        else:  # approval (resolved from the subject at check time), system, operator
            assert not declared.required, handler
        if declared.kind == "approval":
            assert declared.method and declared.path, handler


def test_declared_permissions_equal_the_apis(app_settings: Settings) -> None:
    """For every declared route the application has that route; a guarded route's recorded
    permission equals the declaration (neither under- nor overstated); a per-subject route
    records none and its declared set is the domain module's own constant."""
    routes = _routes(create_app(app_settings))
    for handler, declared in PERMISSIONS.items():
        if declared.method is None:
            continue
        route = routes[(declared.method, declared.path)]
        recorded = (route.openapi_extra or {}).get(PERMISSION_EXTENSION)
        if declared.kind == "route":
            assert recorded is not None and declared.required == {recorded}, handler
        else:
            assert recorded is None, handler
    maintain = reference_commands.MAINTAIN_PERMISSIONS
    for name in ("calendar", "fiscal_year", "entity", "entity_book"):
        assert PERMISSIONS[H[name]].required == maintain, name
    assert PERMISSIONS[H["open_period"]].required == reference_periods.open_permissions(
        setup_completed=False
    )
    for name in ("fx_set", "fx_version", "fx_submit"):
        assert PERMISSIONS[H[name]].required == reference_commands.FX_PERMISSIONS, name
    # API-R-41 is per-subject (supervisor ruling R-63 (a)): the permission is the report's own run
    # permission, and every report the keys' plans run is run under the declared ``report.run``.
    run_permission = frozenset({report_framework.RUN_PERMISSION})
    for name in ("report_create", "report_run"):
        assert PERMISSIONS[H[name]].required == run_permission, name
    planned = {
        str(step.detail["report_code"])
        for key_id in PLATFORM_KEY_IDS
        for step in plan(load_platform_key(key_id)).steps
        if step.handler in (H["report_create"], H["report_run"])
    }
    assert planned, "the platform keys run reports"
    for code in sorted(planned):
        assert report_framework.run_permission(code) == report_framework.RUN_PERMISSION, code
    for declared in PERMISSIONS.values():
        for code in declared.required:
            spec(code)  # an unknown code is not a permission the API knows (KeyError)


def test_a_decision_requires_the_pending_subjects_approval_permission() -> None:
    """``decide`` is per-subject: the required permission is the approval engine's spec for the
    subject the latest committed submission opened (RES-2 binding), never a fixed code; with no
    submission the requirement is refused by name."""
    for submit, subject_type in SUBJECTS.items():
        ledger = [_entry(_call(submit, "ak-preparer", "contract C-1"))]
        decision = _call(H["decide"], "ak-approver", "contract C-1", decision="APPROVE")
        expected = subjects.spec_for(subject_type).required_permission
        assert required_permissions(decision, ledger) == frozenset({expected}), submit
    with pytest.raises(NotProvisioned, match="no committed submission"):
        required_permissions(_call(H["decide"], "ak-approver", "contract C-1"), [])
    # The approval of an SSP version is such a decision, of the submission before it.
    version = "ssp_book DE-LIST version 1"
    submitted = [_entry(_call(H["ssp_submit"], "ak-ssp-analyst", version))]
    ssp = _call(H["decide"], "ak-ssp-approver", version, decision="APPROVE")
    assert required_permissions(ssp, submitted) == frozenset(
        {subjects.spec_for(ApprovalSubjectType.SSP_BOOK_VERSION).required_permission}
    )


def test_system_and_operator_steps_declare_no_tenant_permission() -> None:
    """The compute job runs as the SYSTEM principal (no route); provisioning is the operator's
    platform route without a tenant permission — both declared, not omitted. An activation is no
    system step of the plan: its approval is the activation (04 §16.1), a decision under the
    activation subject's approval permission."""
    compute = PERMISSIONS[H["compute"]]
    assert compute.kind == "system" and compute.method is None
    system = [handler for handler, declared in PERMISSIONS.items() if declared.kind == "system"]
    assert system == [H["compute"]]
    submitted = [_entry(_call(H["submit_activation"], "ak-preparer", "contract C-1"))]
    approval = _call(H["decide"], "ak-approver", "contract C-1", emits="CONTRACT_ACTIVATED")
    assert required_permissions(approval, submitted) == frozenset(
        {subjects.spec_for(ApprovalSubjectType.CONTRACT_ACTIVATION).required_permission}
    )
    provision = PERMISSIONS[H["provision"]]
    assert provision.kind == "operator" and provision.path == "/api/v1/operator/tenants"
    assert required_permissions(_call(H["compute"], "system", "group G"), []) == frozenset()
    assert PrincipalKind.SYSTEM.value == "SYSTEM"


def test_an_invitation_is_accepted_by_the_invited_person_and_by_nobody_else() -> None:
    """``POST /session/accept-invitation`` is guarded by the invitation's token and by no tenant
    permission, so ACT-2 declares it as a kind of its own: the acting persona is the invited one.
    A persona that accepts for another is refused by name, whatever it holds."""
    declared = PERMISSIONS[H["accept"]]
    assert (declared.kind, declared.method, declared.path) == (
        "invitation",
        "POST",
        "/api/v1/session/accept-invitation",
    )
    assert declared.required == frozenset()
    own = Step("PERSONAS", "ak-preparer", H["accept"], "ak-preparer")
    # no principal exists before the acceptance: the token is the proof
    check(Call(H["accept"], "ak-preparer", {}, own), None, [])
    step = Step("PERSONAS", "ak-approver", H["accept"], "ak-preparer")
    with pytest.raises(NotProvisioned, match="cannot accept the invitation of 'ak-preparer'"):
        check(Call(H["accept"], "ak-approver", {}, step), None, [])


def test_the_study_of_an_ssp_version_answers_to_the_products_own_permission_sets() -> None:
    """API-R-10: an upload answers to its purpose's permission and an attachment to the write
    permission of its subject's type. The declarations are the domain's own constants, and the
    SSP analyst holds one of each — the approver and the preparer do not."""
    upload, attach = PERMISSIONS[H["ssp_study"]], PERMISSIONS[H["ssp_study_attach"]]
    assert upload.required == attachments.UPLOAD_PERMISSIONS[FilePurpose.SSP_STUDY]
    assert attach.required == file_access.ATTACHMENT_SUBJECTS["ssp_book_version"].write
    for declared in (upload, attach):
        assert declared.kind == "handler" and declared.required
        assert declared.required & DEFAULT_ROLES["ssp_analyst"]
        assert not declared.required & DEFAULT_ROLES["ssp_approver"]


def test_the_evidence_of_an_estimate_version_answers_to_the_products_own_permission_sets(
    app_settings: Settings,
) -> None:
    """API-R-10 for the second subject of the two commands (04 §16.14 rev 1.241): a step the
    plan marks as an estimate's prerequisite answers to the domain's own constants — the upload
    of an attachment, the write permission of an estimate version — on the routes the study
    uses, which record no permission of their own. The preparer holds one of each, the
    approver none; and the plans mark every step of these commands that is not a study's."""
    assert set(EVIDENCE_PERMISSIONS) == {H["estimate_evidence"], H["estimate_evidence_attach"]}
    upload = EVIDENCE_PERMISSIONS[H["estimate_evidence"]]
    attach = EVIDENCE_PERMISSIONS[H["estimate_evidence_attach"]]
    assert upload.required == attachments.UPLOAD_PERMISSIONS[FilePurpose.ATTACHMENT]
    assert attach.required == file_access.ATTACHMENT_SUBJECTS["estimate_version"].write
    routes = _routes(create_app(app_settings))
    for handler, declared in EVIDENCE_PERMISSIONS.items():
        study = PERMISSIONS[handler]
        assert (declared.kind, declared.method, declared.path) == (
            "handler",
            study.method,
            study.path,
        )
        assert declared.method is not None and declared.path is not None
        route = routes[(declared.method, declared.path)]
        assert (route.openapi_extra or {}).get(PERMISSION_EXTENSION) is None, handler
        assert declared.required & DEFAULT_ROLES["revenue_accountant"]
        assert not declared.required & DEFAULT_ROLES["controller"]
        for code in declared.required:
            spec(code)
    marked = 0
    for key_id in PLATFORM_KEY_IDS:
        for step in plan(load_platform_key(key_id)).steps:
            if step.handler not in EVIDENCE_PERMISSIONS:
                continue
            assert (ESTIMATE_MARKER in step.detail) != step.subject.startswith("ssp_book "), (
                key_id,
                step.subject,
            )
            marked += ESTIMATE_MARKER in step.detail
    assert marked == 2  # EX42's one version: its upload and its link
