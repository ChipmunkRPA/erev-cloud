"""REQ-PLT-019 audit categories and the command-route audit inventory (BUILD_SPEC SOP-7; 03
REQ-PLT-019; 04 §1.7 AUD-CMD, AUD-FACT, AUD-OPS; dev-guide DG-KRN-AUD-04, DG-KRN-AUTH-05).

Two catalogues, both static so ``tests/unit/test_audit_catalogue.py`` can check them without a
database, and both consumed by the SOP-7 database tests
(``tests/domain/platform/test_audit_coverage.py``):

- ``CATEGORIES``: the fourteen REQ-PLT-019 categories mapped to the ``audit_event.action`` names and
  ``security_event`` kinds the handlers write today. Every name is taken from the handler source
  (the unit test greps for it); a category whose handler does not exist on this build names the
  owning lane instead of a name (``pending``).
- ``ROUTES``: every POST, PUT, PATCH and DELETE operation of the committed ``docs/api/openapi.json``
  with the evidence it is expected to write: ``audit_event`` with the expected actions where the
  handler's literal is known, ``security_event`` with the kind, ``provisioning`` (DG-KRN-TEN-01), or
  ``query`` for a command-shaped operation that computes and writes nothing (evaluations,
  explain-verify, the 04 §1.7 AUD-OPS personal read markers, preferences and saved views; D-98 (20)
  defines the class, ``QUERY_EXEMPT`` enumerates it). A preview that defers a job is not a query:
  D-98 (49) keeps the two job-starting previews (``JOB_STARTING``) in the audited class, evidenced
  by the job-start event. The only infrastructure write the walk allows on every path is the
  ``idempotency_record`` row ``run_command`` writes (BUILD_SPEC SOP-7). An ``audit_event`` route
  with an empty ``actions`` tuple is inventoried but unverified: the database walk establishes its
  action, and a route that writes none is a handler defect for its owning lane. ``refused``
  (BUILD_SPEC SOP-7 class (e), fragment 11 rev 1.44) is a command the release refuses by name,
  which stores nothing: it has no successful call to evidence, stays required, and is walked for
  its refusal — the rule id of ``rule_ids``, no audit event and no changed table
  (``RELEASE_REFUSED`` enumerates the class).

The unit test keeps ``ROUTES`` equal to the OpenAPI command operations, so a new command route
fails the build until it is catalogued.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from erev_api.enums import SecurityEventKind

ROOT: Final = Path(__file__).resolve().parents[3]
OPENAPI: Final = ROOT / "docs/api/openapi.json"
ROUTERS_DIR: Final = ROOT / "backend/erev_api/api/v1"
APPLICATION: Final = ROOT / "backend/erev_api"
COMMAND_METHODS: Final = frozenset({"post", "put", "patch", "delete"})
Evidence = Literal["audit_event", "security_event", "provisioning", "query", "confirm", "refused"]


@dataclass(frozen=True, slots=True)
class Category:
    """One REQ-PLT-019 category: the actions and security-event kinds that evidence it."""

    name: str
    actions: tuple[str, ...] = ()
    security_events: tuple[str, ...] = ()
    pending: str | None = None  # the lane whose feature will write the first action


@dataclass(frozen=True, slots=True)
class Route:
    """One command operation and the evidence a successful call writes."""

    operation_id: str
    evidence: Evidence
    actions: tuple[str, ...] = ()  # audit_event actions the handler writes, when known
    security_events: tuple[str, ...] = ()
    note: str | None = None
    rule_ids: tuple[str, ...] = ()  # a ``refused`` route: the rule ids its 422 answers, exactly

    @property
    def verified_statically(self) -> bool:
        return self.evidence != "audit_event" or bool(self.actions)


# ---- REQ-PLT-019 categories --------------------------------------------------------------------

CATEGORIES: Final[tuple[Category, ...]] = (
    Category("login and logout", security_events=("LOGIN_SUCCEEDED", "LOGIN_FAILED", "LOGOUT")),
    Category("MFA changes", ("user_mfa_factor.reset",), ("MFA_ENROLLED", "MFA_RESET")),
    Category(
        "role, permission and SoD changes",
        (
            "role.create",
            "role_assignment.create",
            "role_assignment.revoke",
            "sod_exception.request",
            "sod_exception.revoke",
            "sod_rule.create",
        ),
    ),
    Category(
        "configuration, policy, mapping and SSP changes",
        (
            "registry_version.update",
            "account_mapping_version.create",
            "account_mapping_version.update",
            "ssp_book_version.approve",
            "ssp_book_version.submit",
        ),
    ),
    Category(
        "imports (upload, validate, approve, commit)",
        (
            "import_upload.upload",
            "import_upload.validate",
            "import_upload.approve",
            "import_upload.commit",
        ),
    ),
    Category(
        "events submitted and voided",
        (
            "contract_event.append",
            "event_submission.submit_manual_events",
            "event_submission.request_void",
            "contract.void",
            "contract.void_requested",
            "contract.void_executed",
            "contract.void_request_closed",
        ),
    ),
    Category("approvals and rejections", ("approval_request.approve", "approval_request.reject")),
    Category("calculation and close runs", ("period.start_close", "journal_run.calculate")),
    Category(
        "period status changes",
        ("period.open", "period.close", "period.lock", "period_state_transition.create"),
    ),
    Category(
        "journal lifecycle",
        (
            "journal_run.submit",
            "journal_run.approve",
            "journal_run.request_export",
            "journal_batch.export",
        ),
    ),
    Category("report runs and exports", ("report_run.create", "report.export")),
    Category(
        "API client lifecycle",
        (
            "api_client.create",
            "api_client.activate",
            "api_client.reject",
            "api_client.revoke",
            "api_client.rotate_secret",
        ),
    ),
    Category(
        "support grants", ("support_grant.request", "support_grant.approve", "support_grant.revoke")
    ),
    Category("AI proposal lifecycle", pending="F-AIX"),
)


# ---- command routes ----------------------------------------------------------------------------

# D-98 (20): a failed invitation lookup or acceptance (malformed, unknown, expired, used or inactive
# token) writes this E-79 kind (lane F-ADM, sprint/l22-fadm b5e8352, 04 rev 1.38). Listed only when
# the build under test defines it, so the catalogue stays truthful before and after that merge.
INVITATION_LOOKUP_FAILED: Final = "INVITATION_LOOKUP_FAILED"
INVITATION_FAILURE_KINDS: Final[tuple[str, ...]] = (
    (INVITATION_LOOKUP_FAILED,) if INVITATION_LOOKUP_FAILED in SecurityEventKind.__members__ else ()
)


def _audit(operation_id: str, *actions: str, note: str | None = None) -> Route:
    return Route(operation_id, "audit_event", tuple(actions), note=note)


def _security(operation_id: str, *kinds: str, note: str | None = None) -> Route:
    return Route(operation_id, "security_event", security_events=tuple(kinds), note=note)


def _query(operation_id: str, note: str) -> Route:
    return Route(operation_id, "query", note=note)


def _confirm(operation_id: str, published_action: str, note: str) -> Route:
    """An idempotent confirm (SOP7-PUBLISH-CONFIRM-1): the approval that precedes the command
    performs and audits the state change (04 §16.5 publish note; lifecycle.approve → publish), and
    the command returns the published version as it is. Covered only when BOTH hold — the approval
    call's audit rows include ``published_action`` AND the confirm route answers 200 with status
    PUBLISHED and ZERO audit rows under its own request id. ``published_action`` is f-string-built
    by ``lifecycle.transition`` (``f"{kind.object_type}.{status}"``), so ``action_literals()``
    cannot see it; the walk verifies it at runtime."""
    return Route(operation_id, "confirm", (published_action,), note=note)


def _refused(operation_id: str, rule_id: str, note: str) -> Route:
    """A command the release refuses by name, which stores nothing (BUILD_SPEC SOP-7 class (e)):
    no successful call exists, so the walk is satisfied only by the refusal itself — 422 with
    exactly ``rule_id``, zero audit rows under the request and no changed tenant table."""
    return Route(operation_id, "refused", note=note, rule_ids=(rule_id,))


JOB_START_ACTION: Final = "job.start"  # jobs/registry.py START_ACTION (04 T-PLT-27 rev 1.106)


def _job_start(operation_id: str, note: str) -> Route:
    """A command that defers a job (D-98 (49)): audited, never ``query``. Its evidence is the
    ``job.start`` event the jobs registry writes in the ``job`` row's transaction, as the caller
    and under the command's request id (04 T-PLT-27 rev 1.106; supervisor ruling R-50 (a))."""
    return Route(
        operation_id,
        "audit_event",
        (JOB_START_ACTION,),
        note=f"job-starting command; {note}; job.start written by the jobs registry (R-50 (a))",
    )


_ROUTE_LIST: Final[tuple[Route, ...]] = (
    # access reviews (API-R-49)
    _audit("access_reviews_create", "access_review_campaign.create"),
    _audit("access_reviews_start", "access_review_campaign.start"),
    _audit("access_reviews_cancel", "access_review_campaign.cancel"),
    _audit("access_reviews_complete", "access_review_campaign.complete"),
    _audit("access_reviews_items_decide", "access_review_item.decide"),
    _audit("access_reviews_items_confirm_revocation", "access_review_item.confirm_revocation"),
    # account mappings and GL accounts
    _audit("account_mappings_create", "account_mapping_version.create"),
    _audit("account_mappings_update", "account_mapping_version.update"),
    _audit("account_mappings_submit"),
    _confirm(
        "account_mappings_publish",
        "account_mapping_version.published",
        note="idempotent confirm: the approval published and audited (SOP7-PUBLISH-CONFIRM-1)",
    ),
    _audit("account_mappings_test"),
    _audit("account_mapping_rules_create", "account_mapping_rule.create"),
    _audit("account_mapping_rules_delete", "account_mapping_rule.delete"),
    _audit("gl_accounts_create", "gl_account.create"),
    _audit("gl_accounts_update", "gl_account.update"),
    # API clients, delegations, approvals
    _audit("api_clients_create", "api_client.create"),
    _audit("api_clients_revoke", "api_client.revoke"),
    _audit("api_clients_rotate_secret", "api_client.rotate_secret"),
    _audit("approval_delegations_create", "approval_delegation.create"),
    _audit("approval_delegations_revoke", "approval_delegation.revoke"),
    _audit("approvals_approve", "approval_request.approve"),
    _audit("approvals_reject", "approval_request.reject"),
    _audit("approvals_withdraw"),
    _audit("approvals_bulk_approve", "approval_request.approve"),
    # files and attachments
    _audit("attachments_create", "file_attachment.create"),
    _audit("attachments_void", "file_attachment.void"),
    _audit("files_upload", "file.upload"),
    # audit
    _audit(
        "audit_events_verify",
        JOB_START_ACTION,
        note="on-demand chain verification: job.start when it defers (DG-KRN-AUD-07)",
    ),
    # books, entities, currencies, calendars
    _audit("books_update", "book.update"),
    _audit("entities_create", "legal_entity.create"),
    _audit("entities_update", "legal_entity.update"),
    _audit("entities_put_book", "entity_book.create", "entity_book.update"),
    _audit("tenant_currencies_put", "tenant_currency.create", "tenant_currency.update"),
    _audit("fx_rate_sets_create", "fx_rate_set.create"),
    _audit("fx_rate_set_versions_create", "fx_rate_set_version.create"),
    _audit("fx_rate_set_versions_update", "fx_rate_set_version.update"),
    _audit("fx_rate_set_versions_submit", "fx_rate_set_version.submit"),
    _audit("fx_rate_set_versions_withdraw", "fx_rate_set_version.withdraw"),
    _audit("calendars_create", "fiscal_calendar.create"),
    _audit("calendars_generate_year", "period.generate"),
    # close checklist templates, combinations, config test cases
    _audit("close_checklist_templates_create", "close_checklist_template.create"),
    _audit("close_checklist_templates_update", "close_checklist_template.update"),
    _audit("combination_groups_create", "combination_group.create"),
    _audit("combination_groups_submit"),
    _audit(
        "combination_groups_discard",
        "judgement_record.voided",
        note=(
            "04 T-CON-19 rev 1.289: the draft proposal is voided with its group; the event "
            "of the group, combination_group.voided, is built from its status"
        ),
    ),
    _audit(
        "combination_suggestions_dismiss",
        "exception_item.dismiss",
        note="a suggestion is an exception_item (COMBINATION_SUGGESTED); SOP-7 slice 4 correction",
    ),
    _audit("config_test_cases_create", "rule_test_case.create"),
    _audit("config_test_cases_update", "rule_test_case.update"),
    _audit("config_test_cases_delete", "rule_test_case.delete"),
    # contracts, events, estimates, obligations
    _audit("contracts_create", "contract.create"),
    _audit("contracts_replace_draft", "contract.replace_draft"),
    _audit("contracts_update_memos", "contract.update_memos"),
    _audit("contracts_apply_hold", "contract_hold.apply"),
    _audit("contracts_release_hold", "contract_hold.release"),
    _audit("contracts_submit_activation"),
    _audit(
        "contracts_request_void", "contract.void_requested"
    ),  # CTR-11; approval → contract.voided
    _audit("contracts_distinct_review"),
    # BUILD_SPEC CTR-6 (04 §16.3 "Manual events"): a request that waits for approval writes the
    # submission's event instead of the append's.
    _audit(
        "contract_events_append",
        "contract_event.append",
        "event_submission.submit_manual_events",
        "event_submission.submit_attribute_change",
    ),
    _job_start("contract_events_preview", "defers a CONTRACT_COMPUTE PREVIEW dry run (202)"),
    _audit("events_request_void", "event_submission.request_void"),
    _audit("event_submissions_withdraw", "event_submission.withdraw"),
    _audit("contract_estimates_create", "estimate.create"),
    _audit("estimate_versions_create", "estimate_version.create"),
    _audit("estimate_versions_update"),
    _audit("estimate_versions_submit"),
    _audit("estimate_versions_withdraw"),
    _audit("estimate_versions_discard"),
    _job_start(
        "estimate_versions_preview", "defers a CONTRACT_COMPUTE ESTIMATE_PREVIEW dry run (202)"
    ),
    # CTR-17 (D-98 140): the modification object, classification and approval.
    _audit("contract_modifications_create", "modification.create"),
    _audit("modifications_update", "modification.update"),
    _audit("modifications_classify", "modification.classify"),
    _job_start(
        "modifications_preview", "defers a CONTRACT_COMPUTE MODIFICATION_PREVIEW dry run (202)"
    ),
    _audit("modifications_submit", "modification.submit"),
    _audit("modifications_withdraw", "modification.withdraw"),
    _audit("modifications_discard", "modification.discard"),
    _audit("contracts_regroup", "contract.regroup"),
    _audit("obligations_request_ssp_override", "obligation.ssp_override"),
    # customers, products, dimensions, related parties
    _audit("customers_create", "customer.create"),
    _audit("customers_update", "customer.update"),
    _audit("products_create", "product.create"),
    _audit("products_update", "product.update"),
    _audit(
        "products_bundle_components_put",
        "product_bundle_component.create",
        "product_bundle_component.update",
        "product_bundle_component.delete",
    ),
    _audit("products_propose_principal_agent_change"),
    _audit("products_propose_policy_values_change"),
    _audit("dimensions_create", "dimension_definition.create"),
    _audit("dimension_values_create", "dimension_value.create"),
    _audit("dimension_values_update", "dimension_value.update"),
    _audit("related_party_groups_create", "related_party_group.create"),
    _audit("related_party_groups_update", "related_party_group.update"),
    # exceptions
    _audit("exceptions_assign", "exception_item.assign"),
    _audit("exceptions_dismiss", "exception_item.dismiss"),
    _audit("exceptions_reprocess", "exception_item.reprocess"),
    _audit(
        "exceptions_request_waiver",
        "approval_request.submit",
        note=(
            "the route submits the waiver's approval request; exception_item.waive is written when"
            " the waiver is approved (SOP-7 slice 4 correction)"
        ),
    ),
    _audit("exceptions_resolve", "exception_item.resolve"),
    # explain
    _query("explain_verify", "recomputes a measure for comparison; no row changes"),
    # imports and mapping profiles
    _audit("imports_create", "import_upload.upload"),
    _audit("imports_submit", "import_upload.submit"),
    _audit("imports_cancel", "import_upload.cancel"),
    # API-R-48 migrations (lane F-LMG, LMG-API-1; record §25): every command writes AUD-CMD
    _audit("migrations_create", "migration_batch.create"),
    _audit("migrations_profile", "migration_batch.profile"),
    _audit("migrations_import", "migration_batch.import"),
    _audit("migrations_reconcile", "migration_batch.reconcile"),
    _audit("migrations_cancel", "migration_batch.cancel"),
    _audit("import_mapping_profiles_create", "import_mapping_profile.create"),
    _audit("import_mapping_profiles_update", "import_mapping_profile.update"),
    _audit("import_mapping_profiles_submit"),
    _confirm(
        "import_mapping_profiles_publish",
        "import_mapping_profile.published",
        note="idempotent confirm: the approval published and audited (SOP7-PUBLISH-CONFIRM-1)",
    ),
    _audit("import_mapping_profiles_test"),
    # API-R-45 integrations (lane F-ADM on F-DIN's branch, DIN-12): every command writes AUD-CMD;
    # the ADP-01 receiver is unauthenticated (allow-list) and audits the WEBHOOK_BATCH run it stores
    _audit("integrations_create", "integration_connection.create"),
    _audit("integrations_update", "integration_connection.update"),
    _audit("integrations_test", "integration_connection.test"),
    _audit("integrations_sync", "sync_run.request"),
    _audit("webhooks_receive", "sync_run.webhook"),
    _audit("external_ids_create", "external_id_map.link"),  # 04 rev 1.81 (DIN-12 remediation)
    # jobs (04 T-PLT-27 rev 1.106; supervisor ruling R-50 (a))
    _audit("jobs_cancel", "job.cancel"),
    # journals
    _audit("journal_runs_create", "journal_run.request_calculation"),
    _audit("journal_runs_submit", "journal_run.submit"),
    # JRN-FAILED-CANCEL-1 (04 rev 1.159): the cancel of a draft or approved run writes
    # journal_run.cancel; of a run with a failed batch, journal_run.request_cancel beside the
    # job.start of the job that asks the ledger and decides (journal_run.cancel, SYSTEM)
    _audit("journal_runs_cancel", "journal_run.cancel", "journal_run.request_cancel"),
    _audit("journal_runs_export", "journal_run.request_export"),
    # CLO-14 (lane F-CLO-A; 04 rev 1.127): the person who imported a CSV batch records the ERP
    # document reference; a failed batch is sent again
    _audit("journal_batches_acknowledge", "journal_batch.acknowledge"),
    _audit("journal_batches_retry", "journal_batch.retry"),
    # JRN-FAILED-CANCEL-1: a failed batch of an ERP adapter is handed over for manual posting;
    # the job's decision is journal_batch.hand_over (SYSTEM)
    _audit("journal_batches_hand_over", "journal_batch.request_hand_over"),
    # API-R-37 manual adjustments (lane F-CLO-A, CLO-12; 04 rev 1.120): every command writes
    # AUD-CMD; the approval that posts, rejects or defers writes manual_adjustment.post, .reject or
    # .defer_past_lock in the decision's own transaction
    _audit("manual_adjustments_create", "manual_adjustment.create"),
    _audit("manual_adjustments_update", "manual_adjustment.update"),
    _job_start(
        "manual_adjustments_preview", "defers a CONTRACT_COMPUTE ADJUSTMENT_PREVIEW dry run (202)"
    ),
    _audit("manual_adjustments_submit", "manual_adjustment.submit"),
    _audit("manual_adjustments_withdraw", "manual_adjustment.withdraw"),
    _audit("manual_adjustments_discard", "manual_adjustment.discard"),
    _audit(
        "manual_adjustments_request_defer_past_lock", "manual_adjustment.request_defer_past_lock"
    ),
    # judgements
    _audit("judgements_create", "judgement_record.create"),
    _audit("judgements_update", "judgement_record.update"),
    _audit("judgements_submit", "judgement_record.submitted"),
    _audit("judgements_discard", "judgement_record.voided"),
    # me
    _security("me_mfa_enroll", "MFA_ENROLMENT_STARTED"),
    _security("me_mfa_confirm", "MFA_ENROLLED"),
    _security("me_change_password", "PASSWORD_CHANGED"),
    _security("me_regenerate_recovery_codes", "RECOVERY_CODES_REGENERATED"),
    _query("me_notification_preferences_put", "personal preference; AUD-OPS (04 §1.7)"),
    _query("me_notifications_read", "read marker; AUD-OPS (04 §1.7)"),
    _query("me_notifications_read_all", "read marker; AUD-OPS (04 §1.7)"),
    _query("me_preferences_update", "personal preference; AUD-OPS (04 §1.7)"),
    # oauth, operator
    _security("oauth_token", note="SOP-7 exemption: client-credentials token issuance"),
    Route("operator_tenants_create", "provisioning", note="DG-KRN-TEN-01 provisioning events"),
    # periods and close
    _audit("periods_open", "period.open"),
    _audit("periods_start_close", "period.start_close"),
    _audit("periods_cancel_close", "period.cancel_close"),
    # F-CLO CLO-6 / CLO-7: the lock, permanent-lock and reopen requests audit the request on the
    # period state; the decisions that execute them are approval-engine routes.
    _audit("periods_request_lock", "period.request_lock"),
    _audit("periods_request_permanent_lock", "period.request_permanent_lock"),
    _audit("periods_request_reopen", "period.request_reopen"),
    _audit("periods_checklist_sign", "close_checklist_item.sign"),
    _audit("periods_checklist_waive", "close_checklist_item.request_waiver"),
    # POB templates
    _audit("pob_templates_create", "pob_template.create"),
    _audit("pob_template_versions_create", "pob_template_version.create"),
    _audit("pob_template_versions_update", "pob_template_version.update"),
    _audit("pob_template_versions_submit"),
    _confirm(
        "pob_template_versions_publish",
        "pob_template_version.published",
        note="idempotent confirm: the approval published and audited (SOP7-PUBLISH-CONFIRM-1)",
    ),
    _audit("pob_template_versions_test", "pob_template_version.test"),
    # policies (registry versions) and overrides
    _audit("policies_create", "registry_version.update"),
    _audit("policies_update", "registry_version.update"),
    _audit("policies_submit"),
    _confirm(
        "policies_publish",
        "registry_version.published",
        note="idempotent confirm: the approval published and audited (SOP7-PUBLISH-CONFIRM-1)",
    ),
    _audit("policies_withdraw"),
    _audit("policies_test", "registry_version.test_requested"),
    _audit("policies_presets_legacy_parity"),
    # Release 1.0 offers no policy override (04 T-CON-23 rev 1.322; PRD ERR-102): the creation is
    # refused by name; the submit keeps its code and is walked on a row the walk's world writes.
    _refused(
        "policy_overrides_create",
        "POLICY_OVERRIDE_NOT_OFFERED",
        note="refused by name in release 1.0 and stores nothing (item POLICY-OVERRIDE-WITHDRAW-1)",
    ),
    _audit("policy_overrides_submit", "policy_override.submit"),
    # reconciliations (API-R-40; BUILD_SPEC CLO-16, lane F-CLO-B): the generation request audits
    # the request on the reconciliation the job inserts; each later command its transition.
    _audit("reconciliations_create", "reconciliation.request_generation"),
    _audit("reconciliations_attach_trial_balance", "reconciliation.request_trial_balance"),
    _audit("reconciliations_items_update", "reconciliation_item.explain"),
    _audit("reconciliations_prepare", "reconciliation.prepare"),
    _audit("reconciliations_sign", "reconciliation.sign"),
    _audit("reconciliations_reopen", "reconciliation.reopen"),
    _audit("close_runs_create", "close_run.create"),
    _audit("close_runs_resume", "close_run.resume"),
    _audit("close_runs_cancel", "close_run.cancel"),
    # reports
    _audit("report_runs_create", "report_run.create"),
    _audit("report_runs_rerun", "report_run.create"),
    # roles and SoD
    _audit("roles_create", "role.create"),
    _audit("roles_propose_change"),
    _audit("role_assignments_create", "role_assignment.create"),
    _audit("role_assignments_revoke", "role_assignment.revoke"),
    _audit("sod_exceptions_create", "sod_exception.request"),
    _audit("sod_exceptions_revoke", "sod_exception.revoke"),
    _audit("sod_rule_versions_create", "sod_rule.create"),
    # rule sets
    _audit("rule_sets_create", "rule_set.create"),
    _query("rule_sets_evaluate", "evaluates a rule set against inputs; no row changes"),
    _audit("rule_set_versions_create", "rule_set_version.create"),
    _audit("rule_set_versions_update", "rule_set_version.update"),
    _audit("rule_set_versions_submit"),
    _confirm(
        "rule_set_versions_publish",
        "rule_set_version.published",
        note="idempotent confirm: the approval published and audited (SOP7-PUBLISH-CONFIRM-1)",
    ),
    _audit("rule_set_versions_lint", "rule_set_version.lint"),
    _audit("rule_set_versions_test", "rule_set_version.test"),
    _audit("rule_set_version_rules_upsert", "rule.upsert"),
    _audit("rule_set_version_rules_delete", "rule.delete"),
    _audit("rule_set_version_test_cases_create", "rule_test_case.create"),
    # saved views: a user's own grid filters and favourites, AUD-OPS (04 T-PLT-37) — class (c)
    _query("saved_views_create", "the caller's own saved_view row; AUD-OPS (04 T-PLT-37)"),
    _query("saved_views_update", "the caller's own saved_view row; AUD-OPS (04 T-PLT-37)"),
    _query("saved_views_delete", "the caller's own saved_view row; AUD-OPS (04 T-PLT-37)"),
    # session
    _security("session_login", "LOGIN_SUCCEEDED", "LOGIN_FAILED"),
    _security("session_logout", "LOGOUT"),
    # 04 E-79 rev 1.189 (ruling R-111 (6)): a passed challenge is an event of its own.
    _security("session_verify_mfa", "MFA_CHALLENGE_PASSED", "MFA_CHALLENGE_FAILED"),
    _security("session_select_tenant", "TENANT_SELECTED"),
    _security("session_request_password_reset", "PASSWORD_RESET_REQUESTED"),
    _security("session_confirm_password_reset", "PASSWORD_RESET_COMPLETED"),
    Route(
        "session_accept_invitation",
        "audit_event",
        ("membership.accept",),
        security_events=INVITATION_FAILURE_KINDS,
        note='a bad token writes INVITATION_LOOKUP_FAILED with route "accept" (F-ADM b5e8352)',
    ),
    # D-98 (20): not exempt — a lookup with an unknown, expired or malformed token is a probing
    # signal and writes INVITATION_LOOKUP_FAILED (F-ADM b5e8352: outcome FAILED, anonymous caller,
    # detail {"reason": malformed|unknown|expired|used|inactive, "route": "lookup"}, own identity
    # transaction after the tenant_directory read); a successful lookup writes nothing else.
    Route(
        "session_lookup_invitation",
        "security_event",
        security_events=INVITATION_FAILURE_KINDS,
        note="failed lookup → INVITATION_LOOKUP_FAILED (F-ADM sprint/l22-fadm b5e8352; listed once "
        "the kind is on this build); success writes nothing",
    ),
    # SSP
    _audit("ssp_books_create", "ssp_book.create"),
    _audit("ssp_books_update", "ssp_book.update"),
    _audit("ssp_book_versions_create", "ssp_book_version.create"),
    _audit("ssp_book_versions_update", "ssp_book_version.update"),
    _audit("ssp_book_versions_submit", "ssp_book_version.submit"),
    _audit("ssp_book_versions_withdraw", "ssp_book_version.withdraw"),
    _audit("ssp_entries_upsert", "ssp_entry.create", "ssp_entry.update"),
    _audit("ssp_entries_delete", "ssp_entry.delete"),
    _audit("ssp_calculator_runs_create", "ssp_calculator_run.create"),
    _audit("ssp_calculator_runs_create_draft_version", "ssp_calculator_run.create_draft_version"),
    _audit("ssp_calculator_exclusions_create", "ssp_calculator_exclusion.create"),
    # support grants, tenant, users, webhooks
    _audit("support_grants_create", "support_grant.request"),
    _audit("support_grants_revoke", "support_grant.revoke"),
    _audit("tenant_update", "tenant.update"),
    _audit(
        "tenant_snapshots_request",
        "tenant.snapshot_requested",
        note="SNP-1 (lane F-SNP): inserts the T-PLT-34 row QUEUED and defers TENANT_SNAPSHOT (202)",
    ),
    _audit(
        "tenant_sandboxes_request",
        "tenant.sandbox_requested",
        note="SNP-2 (lane F-SNP): defers TENANT_SNAPSHOT in load-only mode for a new sandbox (202)",
    ),
    _audit(
        "tenant_reset_request",
        "tenant.sandbox_reset_requested",
        note="SNP-3 (lane F-SNP): defers SANDBOX_RESET in the sandbox it supersedes (202)",
    ),
    _audit("users_invite", "tenant_membership.invite"),
    _audit("users_update", "tenant_membership.update"),
    _audit("users_reactivate", "tenant_membership.reactivate"),
    _audit("users_remove", "tenant_membership.remove"),
    _audit(
        "files_shred",
        "file_object.shred",
        "file_object.shred_complete",
        note=(
            "05 PRV-07 b (SOP-5; rev 1.171): the row marked and the decision written; after "
            "that commit the sidecar is destroyed and the completion written, under the same "
            "request id"
        ),
    ),
    _audit(
        "files_request_shred",
        "file_object.request_shred",
        note="05 PRV-07 b rev 1.81 (rulings R-49 (a), R-86; lane SECFIX-IMP): opens the "
        "EVIDENCE_SHRED approval for a file a record holds as its evidence; the file is "
        "unchanged until the decision",
    ),
    _audit(
        "users_anonymise",
        "app_user.anonymise",
        "tenant_membership.remove",
        note="05 PRV-07 a (SOP-5): the identity event plus the acting tenant's membership removal",
    ),
    _audit("users_resend_invitation", "tenant_membership.resend_invitation"),
    _audit("users_reset_mfa", "user_mfa_factor.reset"),
    _audit("users_suspend", "tenant_membership.suspend"),
    _audit("webhook_endpoints_create", "webhook_endpoint.create"),
    _audit("webhook_endpoints_update", "webhook_endpoint.update"),
)
ROUTES: Final[Mapping[str, Route]] = {route.operation_id: route for route in _ROUTE_LIST}

# D-98 (20): the SOP-7 exemption classes (b) stateless evaluations and (c) AUD-OPS personal rows,
# enumerated; the database walk asserts each persists nothing but the 04 §1.7 personal rows and the
# idempotency_record row run_command writes. This set is a declaration, not proof: only the walk is.
# Class (c) is defined by the 04 §1.7 AUD-OPS class, so the three saved-view operations belong to it
# (04 T-PLT-37 classes saved_view AUD-OPS; BUILD_SPEC rev 1.25, supervisor ruling R-14).
QUERY_EXEMPT: Final = frozenset(
    {
        "rule_sets_evaluate",
        "explain_verify",
        "me_notifications_read",
        "me_notifications_read_all",
        "me_notification_preferences_put",
        "me_preferences_update",
        "saved_views_create",
        "saved_views_update",
        "saved_views_delete",
    }
)
# D-98 (49): commands that start a job (uow.defer inserts the job row in the command's transaction)
# are audited (04 T-PLT-27 AUD-OPS), never query; a queued job row is not routine infrastructure.
# + the CTR-17 modification preview (D-98 140); + the CLO-12 manual adjustment preview. Their
# evidence is the registry's job.start (supervisor ruling R-50 (a)).
JOB_STARTING: Final = frozenset(
    {
        "contract_events_preview",
        "estimate_versions_preview",
        "manual_adjustments_preview",
        "modifications_preview",
    }
)
# BUILD_SPEC SOP-7 class (e) (fragment 11 rev 1.44; item POLICY-OVERRIDE-WITHDRAW-1): the commands
# the release refuses by name, which store nothing. Required, never exempt: the walk asks each for
# its refusal. This set is a declaration, not proof: only the walk shows that nothing is stored.
RELEASE_REFUSED: Final = frozenset({"policy_overrides_create"})
# The routes SOP-7's route test excludes by name; they write security or provisioning events.
SOP_7_EXEMPT: Final = frozenset(
    {
        "session_login",
        "session_verify_mfa",
        "session_request_password_reset",
        "session_confirm_password_reset",
        "oauth_token",
        "operator_tenants_create",
    }
)

_OPERATION_ID: Final = re.compile(r'operation_id="([a-z_]+)"')
_LITERAL: Final = re.compile(r'"([a-z_]+\.[a-z_]+)"')


def required_operations() -> frozenset[str]:
    """The operations the SOP-7 walk must exercise: every command operation but the class (a)
    routes of ``SOP_7_EXEMPT`` (the ``query`` class is walked too, for its no-write assertion)."""
    return frozenset(operation_id for operation_id in ROUTES if operation_id not in SOP_7_EXEMPT)


def uncovered_categories(
    actions: Iterable[str],
    kinds: Iterable[str],
    categories: Iterable[Category] = CATEGORIES,
) -> list[str]:
    """Every REQ-PLT-019 category without an observed action or security-event kind, named — a
    category the catalogue marks pending on a lane is named WITH its owner and still counts as
    missing (Codex P4-SOP7 R1: no category may pass silently; SOP-7 fails each missing category by
    name)."""
    seen_actions, seen_kinds = set(actions), set(kinds)
    missing: list[str] = []
    for category in categories:
        observed = bool(
            set(category.actions) & seen_actions or set(category.security_events) & seen_kinds
        )
        if observed:
            continue
        owner = f" (pending on lane {category.pending})" if category.pending else ""
        missing.append(f"{category.name}{owner}")
    return missing


def command_operations(openapi: Path = OPENAPI) -> dict[str, tuple[str, str]]:
    """``operation_id -> (METHOD, path)`` for every command operation of the committed document."""
    document = json.loads(openapi.read_text(encoding="utf-8"))
    found: dict[str, tuple[str, str]] = {}
    for path, methods in document["paths"].items():
        for method, operation in methods.items():
            if method in COMMAND_METHODS:
                found[operation["operationId"]] = (method.upper(), path)
    return found


def router_modules(routers: Path = ROUTERS_DIR) -> dict[str, str]:
    """``operation_id -> router module`` from the ``operation_id="…"`` declarations."""
    modules: dict[str, str] = {}
    for module in sorted(routers.glob("*.py")):
        for operation_id in _OPERATION_ID.findall(module.read_text(encoding="utf-8")):
            modules[operation_id] = module.stem
    return modules


def _sources(root: Path) -> Iterator[str]:
    for path in sorted(root.rglob("*.py")):
        yield path.read_text(encoding="utf-8")


def action_literals(application: Path = APPLICATION) -> frozenset[str]:
    """Every ``"<object>.<verb>"`` string literal in the application: the vocabulary an expected
    action must come from (a catalogue name that is not written anywhere is a typo or a wish)."""
    return frozenset(name for source in _sources(application) for name in _LITERAL.findall(source))
