"""ACT-2 — the API permission each plan step needs, declared once and checked before any direct
domain call (record §34; dev-guide DG-AK-41 rev 1.38; D-98 candidate 107, second half).

The platform runner calls domain handlers directly, below the API layer whose guards decide who
may do what. ACT-1 proves *which* principal acts; ACT-2 proves that principal *may* act: before the
conversion and the unit of work, ``check`` compares the step's declared API permission with the
principal's permissions the way the API does — a guarded route's ``require(code)`` passes when
``code in principal.permissions`` (``erev_api.auth.dependencies.require``); a per-subject route's
handler passes when ``codes & principal.permissions`` is non-empty
(``erev_api.domain.platform.attachments.authorize``) — and refuses by name.

One table, sourced from the API: a ``route`` entry names the route whose ``require`` guard the
API records as ``openapi_extra["x-erev-permission"]`` (``api.deps.GuardedRoute``); a ``handler``
entry names a per-subject route and carries the domain module's own permission-set constant; an
``approval`` entry resolves the permission from the approval engine's subject spec
(``erev_api.approvals.subjects.spec_for(subject).required_permission``) — for ``decide`` from the
subject the latest committed submission opened (RES-2 / READ-3), for the SSP approval from its
fixed subject; ``system`` steps run as the SYSTEM principal and have no route; the ``operator``
step is the platform operator's route without a tenant permission; the ``invitation`` step is the
invited user's own route, which the API guards with the invitation token and no permission — the
adapter reads that token from the message the invitation sent to the acting persona's membership,
so nobody accepts for another. The tests read the routes from the application and the constants
from the domain, so the table can neither under- nor overstate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

from erev_api.approvals import subjects
from erev_api.domain.platform import attachments, file_access
from erev_api.domain.reference import commands as reference_commands
from erev_api.domain.reference import periods as reference_periods
from erev_api.domain.reports import framework as report_framework
from erev_api.enums import ApprovalSubjectType, FilePurpose, PrincipalKind
from support.answer_keys.platform_plan import ESTIMATE_MARKER, PRESET_HANDLER, H
from support.answer_keys.platform_runner import NotProvisioned

if TYPE_CHECKING:
    from support.answer_keys.workspace_adapter import Call, LedgerEntry

Kind = Literal["route", "handler", "approval", "system", "operator", "invitation"]
KINDS: Final[frozenset[str]] = frozenset(
    {"route", "handler", "approval", "system", "operator", "invitation"}
)
V1: Final = "/api/v1"
APPROVE_ROUTE: Final = ("POST", f"{V1}/approvals/{{approval_request_id}}/approve")


@dataclass(frozen=True, slots=True)
class StepPermission:
    """What the API requires of the step's route: ``required`` is one code for a guarded route,
    the handler's any-of set for a per-subject route, empty when resolved from the approval
    subject at check time (``approval``) or when no tenant permission applies."""

    kind: Kind
    method: str | None = None
    path: str | None = None
    required: frozenset[str] = frozenset()
    subject: ApprovalSubjectType | None = None


def _route(method: str, path: str, code: str) -> StepPermission:
    return StepPermission("route", method, f"{V1}{path}", frozenset({code}))


def _handler(method: str, path: str, codes: frozenset[str]) -> StepPermission:
    return StepPermission("handler", method, f"{V1}{path}", frozenset(codes))


def _approval(subject: ApprovalSubjectType | None = None) -> StepPermission:
    return StepPermission("approval", *APPROVE_ROUTE, frozenset(), subject)


SYSTEM_STEP: Final = StepPermission("system")
# The domain's own sets for the per-subject routes (API-R-17 / API-R-18 / API-R-19). World steps
# open periods right after provisioning, while ``tenant.setup_completed_at IS NULL``.
MAINTAIN: Final = reference_commands.MAINTAIN_PERMISSIONS
FX: Final = reference_commands.FX_PERMISSIONS
OPEN_DURING_SETUP: Final = reference_periods.open_permissions(setup_completed=False)
# API-R-41 is per-subject since supervisor ruling R-63 (a): a report is run under ITS run
# permission (``framework.run_permission``). Every report a key's checkpoint runs is run under
# ``report.run`` — the three access registers, which answer to ``audit.read``, are not answer-key
# reports (``test_platform_step_permissions`` checks each planned report code against the API).
REPORT_RUN: Final = frozenset({report_framework.RUN_PERMISSION})
# API-R-10: an upload answers to its purpose's permission, an attachment to the write permission
# of its subject's type — the study of an SSP book version is the analyst's on both.
STUDY_UPLOAD: Final = attachments.UPLOAD_PERMISSIONS[FilePurpose.SSP_STUDY]
STUDY_ATTACH: Final = file_access.ATTACHMENT_SUBJECTS["ssp_book_version"].write
# The evidence of an estimate version is its preparer's on both (04 §16.14 rev 1.241).
EVIDENCE_UPLOAD: Final = attachments.UPLOAD_PERMISSIONS[FilePurpose.ATTACHMENT]
EVIDENCE_ATTACH: Final = file_access.ATTACHMENT_SUBJECTS["estimate_version"].write

PERMISSIONS: Final[Mapping[str, StepPermission]] = MappingProxyType(
    {
        # PROVISION / PERSONAS
        H["provision"]: StepPermission("operator", "POST", f"{V1}/operator/tenants"),
        H["invite"]: _route("POST", "/users", "user.manage"),
        H["accept"]: StepPermission("invitation", "POST", f"{V1}/session/accept-invitation"),
        H["assign_role"]: _route("POST", "/role-assignments", "role.manage"),
        H["api_client"]: _route("POST", "/api-clients", "api_client.manage"),
        H["decide"]: _approval(),
        # WORLD — tenant settings (the operator's), reference data, configuration lifecycles
        H["currencies"]: _route("PUT", "/tenant-currencies", "settings.manage"),
        H["calendar"]: _handler("POST", "/calendars", MAINTAIN),
        H["fiscal_year"]: _handler("POST", "/calendars/{calendar_id}/generate-year", MAINTAIN),
        H["entity"]: _handler("POST", "/entities", MAINTAIN),
        H["entity_book"]: _handler("PUT", "/entities/{entity_id}/books/{code}", MAINTAIN),
        H["open_period"]: _handler("POST", "/periods/{period_id}/open", OPEN_DURING_SETUP),
        H["gl_account"]: _route("POST", "/gl-accounts", "config.author"),
        H["mapping"]: _route("POST", "/account-mappings", "config.author"),
        H["mapping_rule"]: _route("POST", "/account-mappings/{version_id}/rules", "config.author"),
        H["mapping_submit"]: _route(
            "POST", "/account-mappings/{version_id}/submit", "config.author"
        ),
        H["mapping_publish"]: _route(
            "POST", "/account-mappings/{version_id}/publish", "config.author"
        ),
        H["customer"]: _route("POST", "/customers", "masterdata.maintain"),
        H["template"]: _route("POST", "/pob-templates", "config.author"),
        H["template_version"]: _route(
            "POST", "/pob-templates/{template_id}/versions", "config.author"
        ),
        H["template_submit"]: _route(
            "POST", "/pob-template-versions/{version_id}/submit", "config.author"
        ),
        H["template_publish"]: _route(
            "POST", "/pob-template-versions/{version_id}/publish", "config.author"
        ),
        H["product"]: _route("POST", "/products", "masterdata.maintain"),
        H["ssp_book"]: _route("POST", "/ssp-books", "ssp.create"),
        H["ssp_version"]: _route("POST", "/ssp-books/{book_id}/versions", "ssp.create"),
        H["ssp_entries"]: _route("POST", "/ssp-book-versions/{version_id}/entries", "ssp.create"),
        H["ssp_study"]: _handler("POST", "/files", STUDY_UPLOAD),
        H["ssp_study_attach"]: _handler("POST", "/attachments", STUDY_ATTACH),
        H["ssp_submit"]: _route("POST", "/ssp-book-versions/{version_id}/submit", "ssp.create"),
        H["fx_set"]: _handler("POST", "/fx-rate-sets", FX),
        H["fx_version"]: _handler("POST", "/fx-rate-sets/{set_id}/versions", FX),
        H["fx_submit"]: _handler("POST", "/fx-rate-set-versions/{version_id}/submit", FX),
        H["rule_set"]: _route("POST", "/rule-sets", "config.author"),
        H["rule_set_version"]: _route("POST", "/rule-sets/{rule_set_id}/versions", "config.author"),
        H["rule"]: _route("POST", "/rule-set-versions/{version_id}/rules", "config.author"),
        # One T-REF-27 command serves rule-set AND template cases; `POST /config-test-cases` is
        # the route that accepts every configuration subject (API-R-12).
        H["rule_case"]: _route("POST", "/config-test-cases", "config.author"),
        H["template_test"]: _route(
            "POST", "/pob-template-versions/{version_id}/test", "config.author"
        ),
        H["mapping_test"]: _route("POST", "/account-mappings/{version_id}/test", "config.author"),
        H["policy_test"]: _route("POST", "/policies/{policy_id}/test", "config.author"),
        H["policy_effective"]: _route("PATCH", "/policies/{policy_id}", "config.author"),
        H["product_template"]: _route("PATCH", "/products/{product_id}", "masterdata.maintain"),
        H["rule_tests"]: _route("POST", "/rule-set-versions/{version_id}/test", "config.author"),
        H["rule_set_submit"]: _route(
            "POST", "/rule-set-versions/{version_id}/submit", "config.author"
        ),
        H["rule_set_publish"]: _route(
            "POST", "/rule-set-versions/{version_id}/publish", "config.author"
        ),
        H["policy"]: _route("POST", "/policies", "config.author"),
        H["policy_submit"]: _route("POST", "/policies/{policy_id}/submit", "config.author"),
        H["policy_publish"]: _route("POST", "/policies/{policy_id}/publish", "config.author"),
        PRESET_HANDLER: _route("POST", "/policies/presets/legacy-parity", "config.author"),
        # CONTRACTS / TIMELINE
        H["book"]: _route("POST", "/contracts", "contract.create"),
        H["override"]: _route("POST", "/policy-overrides", "contract.create"),
        H["override_submit"]: _route(
            "POST", "/policy-overrides/{override_id}/submit", "contract.create"
        ),
        H["judgement"]: _route("POST", "/judgements", "judgement.create"),
        H["judgement_submit"]: _route(
            "POST", "/judgements/{judgement_id}/submit", "judgement.create"
        ),
        H["distinct_review"]: _route(
            "POST",
            "/contracts/{contract_id}/obligations/{obligation_key}/distinct-review",
            "judgement.create",
        ),
        H["estimate"]: _route("POST", "/contracts/{contract_id}/estimates", "estimate.create"),
        H["estimate_version"]: _route(
            "POST", "/estimates/{estimate_id}/versions", "estimate.create"
        ),
        H["estimate_version_update"]: _route(
            "PATCH", "/estimate-versions/{version_id}", "estimate.create"
        ),
        H["estimate_submit"]: _route(
            "POST", "/estimate-versions/{version_id}/submit", "estimate.create"
        ),
        H["submit_activation"]: _route(
            "POST", "/contracts/{contract_id}/submit-activation", "contract.create"
        ),
        H["record_events"]: _route("POST", "/contracts/{contract_id}/events", "event.record"),
        H["compute"]: SYSTEM_STEP,  # the compute job; no route
        H["start_close"]: _route("POST", "/periods/{period_id}/start-close", "period.close"),
        # AK-CLOSE-RUN-STEP-1: the close run a checkpoint expects, started by the preparer.
        H["close_run"]: _route("POST", "/close-runs", "period.close"),
        H["import_create"]: _route("POST", "/imports", "import.upload"),
        H["import_submit"]: _route("POST", "/imports/{import_id}/submit", "import.upload"),
        # AK-JOURNAL-RUN-PLAN-1: the journal run that answers a journals block, where the
        # checkpoint stands in the timeline; the run that stands in its way is cancelled first.
        H["journal_create"]: _route("POST", "/journal-runs", "journal.run"),
        H["journal_cancel"]: _route("POST", "/journal-runs/{run_id}/cancel", "journal.run"),
        H["journal_submit"]: _route("POST", "/journal-runs/{run_id}/submit", "journal.run"),
        # CHECKPOINT — runs the adapter starts through the API's run routes, and the reads
        H["read_journal"]: _route("GET", "/journal-runs/{run_id}/lines", "contract.read"),
        H["report_create"]: _handler("POST", "/report-runs", REPORT_RUN),
        H["report_run"]: _handler("POST", "/report-runs", REPORT_RUN),  # the run the create starts
        H["read_version"]: _route(
            "GET", "/contracts/{contract_id}/versions/{version_no}", "contract.read"
        ),
        H["read_balances"]: _route("GET", "/contracts/{contract_id}/balances", "contract.read"),
        H["read_subledger"]: _route("GET", "/subledger-lines", "contract.read"),
        H["read_period"]: _route("GET", "/periods/{period_id}", "config.read"),
    }
)


# ``POST /files`` and ``POST /attachments`` serve two subjects of the plan, and ``PERMISSIONS``
# is keyed by the command: it declares the SSP study. A step that carries the evidence of an
# estimate version — the plan marks it (``platform_plan.ESTIMATE_MARKER``) — answers to these.
EVIDENCE_PERMISSIONS: Final[Mapping[str, StepPermission]] = MappingProxyType(
    {
        H["estimate_evidence"]: _handler("POST", "/files", EVIDENCE_UPLOAD),
        H["estimate_evidence_attach"]: _handler("POST", "/attachments", EVIDENCE_ATTACH),
    }
)


def declared(handler: str) -> StepPermission:
    """The step's declaration; a handler without one is refused by name, never waved through."""
    found = PERMISSIONS.get(handler)
    if found is None:
        raise NotProvisioned(f"ACT-2: no declared API permission for handler {handler}", handler)
    return found


def declaration(handler: str, detail: Mapping[str, str]) -> StepPermission:
    """The declaration of a command as a step uses it: the command's own, or — for the two
    commands that serve two subjects — the evidence declaration when the step is one of an
    estimate version's prerequisites (``detail`` holds the plan's marker)."""
    if handler in EVIDENCE_PERMISSIONS and ESTIMATE_MARKER in detail:
        return EVIDENCE_PERMISSIONS[handler]
    return declared(handler)


def declared_for(call: Call) -> StepPermission:
    """The declaration of a call: of its own command — which is not always its step's, a
    step may send several — as its step uses it."""
    return declaration(call.handler, call.step.detail)


def required_permissions(call: Call, ledger: Sequence[LedgerEntry]) -> frozenset[str]:
    """The codes of which the acting principal must hold one: the declaration, or for an approval
    the engine's permission for the subject the latest committed submission opened."""
    step = declared_for(call)
    if step.kind != "approval":
        return step.required
    subject = step.subject
    if subject is None:
        from support.answer_keys.ledger_resolver import LedgerResolver  # local: import cycle

        subject = LedgerResolver(ledger).pending_subject_type()
    return frozenset({subjects.spec_for(subject).required_permission})


def describe(codes: frozenset[str]) -> str:
    ordered = sorted(codes)
    return ordered[0] if len(ordered) == 1 else "any of " + ", ".join(ordered)


def check(call: Call, principal: Any, ledger: Sequence[LedgerEntry]) -> None:
    """Rule ACT-2: refuse by name unless the principal may perform the step through the API."""
    step = declared_for(call)
    if step.kind == "system":
        if getattr(principal, "kind", None) is not PrincipalKind.SYSTEM:
            raise NotProvisioned(
                f"ACT-2: actor {call.actor!r} is not the SYSTEM principal for step "
                f"{call.step.subject!r}",
                call.handler,
            )
        return
    if step.kind == "invitation":
        if call.actor != call.step.subject:
            raise NotProvisioned(
                f"ACT-2: actor {call.actor!r} cannot accept the invitation of "
                f"{call.step.subject!r}",
                call.handler,
            )
        return
    required = required_permissions(call, ledger)
    if not required:
        return
    held = frozenset(getattr(principal, "permissions", None) or ())
    if not (required & held):
        raise NotProvisioned(
            f"ACT-2: actor {call.actor!r} lacks permission {describe(required)} for step "
            f"{call.step.subject!r}",
            call.handler,
        )
