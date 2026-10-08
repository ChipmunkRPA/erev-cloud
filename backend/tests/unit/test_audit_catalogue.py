"""The SOP-7 audit catalogue is complete and truthful without a database (BUILD_SPEC SOP-7; 03
REQ-PLT-019; 04 §1.7).

``tests/domain/platform/test_audit_coverage.py`` (database) walks the routes and observes the
events; here the catalogue is held to the committed OpenAPI, to the router declarations and to the
action vocabulary the handlers actually write, so a new command route or a renamed action fails
the build until the catalogue follows.
"""

from __future__ import annotations

from collections import Counter

from erev_api.domain.policies import overrides
from erev_api.enums import SecurityEventKind
from support.audit_catalogue import (
    CATEGORIES,
    JOB_STARTING,
    QUERY_EXEMPT,
    REFUSED_CASES,
    RELEASE_REFUSED,
    ROUTES,
    SOP_7_EXEMPT,
    Category,
    action_literals,
    command_operations,
    required_operations,
    router_modules,
    uncovered_categories,
)


def test_catalogue_equals_the_committed_command_operations() -> None:
    operations = command_operations()
    missing = sorted(set(operations) - set(ROUTES))
    extra = sorted(set(ROUTES) - set(operations))
    assert not missing, f"command operations without a catalogue entry: {missing}"
    assert not extra, f"catalogue entries without a command operation: {extra}"
    # 187 on main (183 + F-CLO's request-lock / -permanent-lock / -reopen + F-CTR's request-void)
    # 187 on main (183 + F-CLO's request-lock / -permanent-lock / -reopen + F-CTR's request-void)
    # + tenant_snapshots_request (SNP-1, lane F-SNP)
    # + the five API-R-48 migration commands (F-LMG) + tenant_sandboxes_request (F-SNP SNP-2) = 194;
    # + the six API-R-31 modification commands (F-CTR CTR-17; D-98 140) + contracts_regroup
    # (API-R-28) = 201 on main 0959b560; + users_anonymise and files_shred (lane P8 SOP-5,
    # 05 PRV-07) = 203 (merge of main 0959b560 into sprint/l16, 2026-09-21).
    # + the four API-R-45 integration commands, the ADP-01 webhook receiver and POST /external-ids
    # (DIN-12, lane F-ADM; 04 rev 1.77 / 1.81) = 209 (merge of main 109bf240 into sprint/l3-fdin,
    # 2026-09-22).
    # + the five API-R-40 reconciliation commands (CLO-16, lane F-CLO-B; 04 rev 1.121) = 214.
    # + attach-trial-balance of API-R-40 (CLO-17, lane F-CLO-B; 04 rev 1.121) = 215.
    # + the three API-R-39 close run commands (CLO-19, lane F-CLO-B; 04 rev 1.134) = 218.
    # + the seven API-R-37 manual adjustment commands (CLO-12, lane F-CLO-A; 04 rev 1.120) = 225.
    # + journal_batches_acknowledge and journal_batches_retry (CLO-14, lane F-CLO-A; 04 rev
    # 1.127) = 227.
    # + products_propose_policy_values_change (lane SECFIX-CFG, security ruling R-21; 04 API-R-23
    # rev 1.110) = 228.
    # + tenant_reset_request (POST /tenant/reset; BUILD_SPEC SNP-3, lane F-SNP; 04 rev 1.125) = 229
    # (merge of main d0c5eceb into sprint/l9, 2026-09-30).
    # + journal_batches_hand_over (item JRN-FAILED-CANCEL-1, lane F-CLO-A; 04 rev 1.159) = 230.
    # + modifications_discard (item MOD-DISCARD-1, lane SECFIX-ACT, supervisor ruling R-118 (e);
    # 04 API-R-31 rev 1.188) = 231.
    # + files_request_shred (lane SECFIX-IMP; rulings R-49 (a), R-86; 04 rev 1.142 API-R-12)
    # = 232.
    # + estimate_versions_discard (item EST-DISCARD-1, lane SECFIX-ACT, supervisor ruling
    # R-119 (e); 04 API-R-32 rev 1.210) = 233.
    # + judgements_discard (the discard of a judgement record, lane SECFIX-ACT, the supervisor's
    # ruling of 2026-10-01 on question J1 (a); 04 API-R-33 rev 1.242) = 234.
    # + combination_groups_discard (item COMBINATION-PROPOSAL-DISCARD-1, lane F-RPS-REG, the
    # supervisor's rulings of 2026-10-02; 04 API-R-28 rev 1.289) = 235.
    assert len(operations) == 235


def test_every_catalogued_route_is_declared_by_one_router_module() -> None:
    modules = router_modules()
    unknown = sorted(operation_id for operation_id in ROUTES if operation_id not in modules)
    assert not unknown, unknown
    assert modules["roles_create"] == "roles" and modules["session_login"] == "session"


def test_expected_actions_and_kinds_exist_in_the_application() -> None:
    literals = action_literals()
    kinds = {kind.value for kind in SecurityEventKind}
    for route in ROUTES.values():
        if route.evidence == "confirm":
            # <table>.published is f-string-built by lifecycle.transition; the walk verifies it.
            assert all(action.endswith(".published") for action in route.actions), route
            continue
        for action in route.actions:
            assert action in literals, f"{route.operation_id}: no handler writes {action!r}"
        for kind in route.security_events:
            assert kind in kinds, f"{route.operation_id}: unknown security event {kind}"
    for category in CATEGORIES:
        for action in category.actions:
            assert action in literals, f"{category.name}: no handler writes {action!r}"
        for kind in category.security_events:
            assert kind in kinds, f"{category.name}: unknown security event {kind}"


def test_req_plt_019_categories_are_all_mapped() -> None:
    names = [category.name for category in CATEGORIES]
    assert len(names) == 14 and len(set(names)) == 14
    for category in CATEGORIES:
        evidenced = bool(category.actions or category.security_events)
        assert evidenced or category.pending, f"{category.name}: no evidence and no owning lane"
        assert not (evidenced and category.pending), category.name
    pending = {category.name: category.pending for category in CATEGORIES if category.pending}
    assert pending == {"AI proposal lifecycle": "F-AIX"}


def test_sop_7_exemptions_are_security_or_provisioning_routes() -> None:
    for operation_id in SOP_7_EXEMPT:
        assert ROUTES[operation_id].evidence in {"security_event", "provisioning"}, operation_id
    assert ROUTES["operator_tenants_create"].evidence == "provisioning"
    assert "LOGIN_FAILED" in ROUTES["session_login"].security_events


def test_d_98_20_query_class_is_exactly_the_ruled_exemptions() -> None:
    """D-98 (20): the catalogue's ``query`` class enumerates the spec's exemption classes (b) and
    (c) and nothing else; the invitation lookup and the job-starting previews (D-98 (49)) are not
    among them. This pins the declaration; only the database walk proves a query writes nothing."""
    queried = {route.operation_id for route in ROUTES.values() if route.evidence == "query"}
    assert queried == QUERY_EXEMPT, sorted(queried ^ QUERY_EXEMPT)
    # Six until BUILD_SPEC rev 1.25 (supervisor ruling R-14): class (c) is the 04 §1.7 AUD-OPS
    # class, and 04 T-PLT-37 classes ``saved_view`` AUD-OPS, so its three commands join it.
    saved_views = {"saved_views_create", "saved_views_update", "saved_views_delete"}
    assert saved_views <= QUERY_EXEMPT
    assert all("T-PLT-37" in (ROUTES[operation_id].note or "") for operation_id in saved_views)
    assert len(QUERY_EXEMPT) == 9 and not QUERY_EXEMPT & JOB_STARTING
    assert "session_lookup_invitation" not in QUERY_EXEMPT
    lookup = ROUTES["session_lookup_invitation"]
    assert lookup.evidence == "security_event" and lookup.note and "F-ADM" in lookup.note
    # The failure kind is listed exactly when the build defines it (lane F-ADM's merge).
    defined = "INVITATION_LOOKUP_FAILED" in SecurityEventKind.__members__
    expected = ("INVITATION_LOOKUP_FAILED",) if defined else ()
    assert lookup.security_events == expected
    assert ROUTES["session_accept_invitation"].security_events == expected
    for operation_id in QUERY_EXEMPT:
        assert ROUTES[operation_id].note, operation_id  # every exemption states its reason


def test_d_98_49_job_starting_previews_are_audited_not_exempt() -> None:
    """D-98 (49) (Codex P4-SOP7-R1): a preview that defers a job is a job-starting command in the
    audited class, never ``query``. Its evidence is the ``job.start`` event the jobs registry
    writes in the ``job`` row's transaction (04 T-PLT-27 rev 1.106; supervisor ruling R-50 (a)):
    until that ruling the emission was unconfirmed and the three routes were inventoried without
    an action."""
    assert JOB_STARTING == {
        "contract_events_preview",
        "estimate_versions_preview",
        "manual_adjustments_preview",  # CLO-12 (lane F-CLO-A; 04 rev 1.120 API-R-37)
        "modifications_preview",  # CTR-17 (D-98 140)
    }
    for operation_id in JOB_STARTING:
        route = ROUTES[operation_id]
        assert route.evidence == "audit_event" and route.actions == ("job.start",), operation_id
        assert route.verified_statically, operation_id
        assert route.note and "job-starting command" in route.note and "R-50 (a)" in route.note
        assert operation_id not in QUERY_EXEMPT and operation_id not in SOP_7_EXEMPT
    # The cancel command and the on-demand verification are evidenced the same way.
    assert ROUTES["jobs_cancel"].actions == ("job.cancel",)
    assert ROUTES["audit_events_verify"].actions == ("job.start",)


def test_inventory_shape_for_the_database_walk() -> None:
    """The numbers the record carries: how much of the route walk is pre-mapped."""
    by_evidence = Counter(route.evidence for route in ROUTES.values())
    unverified = sorted(
        route.operation_id
        for route in ROUTES.values()
        if route.evidence == "audit_event" and not route.actions
    )
    assert by_evidence["audit_event"] + by_evidence["security_event"] + by_evidence[
        "provisioning"
    ] + by_evidence["query"] + by_evidence["confirm"] + by_evidence["refused"] == len(ROUTES)
    assert by_evidence["confirm"] == 5  # the five *_publish idempotent confirms
    assert by_evidence["refused"] == 0  # Unsupported inputs are separate refusal cases.
    assert by_evidence["provisioning"] == 1
    # Every unverified audit_event route is a named item for the database walk, never silent.
    assert all(not ROUTES[operation_id].verified_statically for operation_id in unverified)
    # R-50 (a): the job-starting previews, the cancel command and the on-demand verification name
    # their action, so they left the unverified inventory (32 before the ruling).
    assert not (JOB_STARTING | {"jobs_cancel", "audit_events_verify"}) & set(unverified)
    assert len(unverified) <= 27, unverified


def test_policy_override_creation_has_success_and_refusal_evidence() -> None:
    assert RELEASE_REFUSED == frozenset()
    assert ROUTES["policy_overrides_create"].evidence == "audit_event"
    assert ROUTES["policy_overrides_create"].actions == ("policy_override.create",)
    refused = REFUSED_CASES["policy_overrides_create"]
    assert refused.evidence == "refused"
    assert refused.rule_ids == (overrides.RULE_NOT_OFFERED,)
    assert set(REFUSED_CASES) <= required_operations()
    assert not set(REFUSED_CASES) & (SOP_7_EXEMPT | QUERY_EXEMPT | JOB_STARTING)
    assert "policy_override.create" in action_literals()
    assert "policy_override.create" in {
        action for category in CATEGORIES for action in category.actions
    }
    assert ROUTES["policy_overrides_submit"].actions == ("policy_override.submit",)


def test_req_plt_019_pending_category_still_fails_by_name() -> None:
    """Codex P4-SOP7 R1: an otherwise-complete observation — one action or kind of EVERY evidenced
    category — still fails, naming the AI proposal lifecycle with its owner; nothing pending passes
    silently."""
    actions = {category.actions[0] for category in CATEGORIES if category.actions}
    kinds = {category.security_events[0] for category in CATEGORIES if category.security_events}
    assert uncovered_categories(actions, kinds) == ["AI proposal lifecycle (pending on lane F-AIX)"]
    # Nothing observed: every category is named, the pending one with its owner.
    everything = uncovered_categories((), ())
    assert len(everything) == len(CATEGORIES) == 14
    assert "AI proposal lifecycle (pending on lane F-AIX)" in everything
    # Once the lane's action exists and is observed, the category is covered like any other.
    landed = [
        Category("AI proposal lifecycle", ("ai_proposal.accept",))
        if category.name == "AI proposal lifecycle"
        else category
        for category in CATEGORIES
    ]
    assert uncovered_categories(actions | {"ai_proposal.accept"}, kinds, landed) == []


def test_sop_7_required_operations_exclude_class_a() -> None:
    """Codex P4-SOP7 C1: the command operations minus the 6 class (a) routes are the required set —
    215 − 6 = 209 on this OpenAPI (194 at the P4 slice, + 7 CTR-17 operations landed by F-CTR at
    0959b560, + 2 P8 SOP-5 privacy commands landed at 143062c8: ``users_anonymise`` and
    ``files_shred``, 05 PRV-07 — both REQUIRED, not exempt; fix-forward P8-MERGE-SOP7-PIN-1, Codex
    0200); an exempt route walked for its security evidence (``session_login``) does not count as
    authored."""
    required = required_operations()
    # + the six DIN-12 operations (lane F-ADM, 04 rev 1.77 / 1.81: integrations_create / _update
    # / _test / _sync, webhooks_receive, external_ids_create — all REQUIRED, none exempt) landed at
    # the merge of main 109bf240 into sprint/l3-fdin, 2026-09-22: 209 − 6 = 203 (measured on the
    # merged tree: command operations 209 = catalogue routes 209; SOP_7_EXEMPT 6; required 203).
    # + the five API-R-40 reconciliation commands (CLO-16, lane F-CLO-B; all REQUIRED, none
    # exempt): 214 − 6 = 208; + attach-trial-balance (CLO-17; REQUIRED): 215 − 6 = 209;
    # + the three API-R-39 close run commands (CLO-19; all REQUIRED): 218 − 6 = 212.
    # + the seven API-R-37 manual adjustment commands (CLO-12, lane F-CLO-A: create, update,
    # preview, submit, withdraw, discard, request-defer-past-lock — all REQUIRED, none exempt):
    # 225 − 6 = 219.
    # + the two API-R-38 batch commands (CLO-14, lane F-CLO-A: acknowledge and retry — both
    # REQUIRED, none exempt): 227 − 6 = 221.
    # + products_propose_policy_values_change (lane SECFIX-CFG, security ruling R-21; 04 API-R-23
    # rev 1.110 — REQUIRED, not exempt): 228 − 6 = 222.
    # + tenant_reset_request (BUILD_SPEC SNP-3, lane F-SNP; REQUIRED — it writes
    # ``tenant.sandbox_reset_requested``): 229 − 6 = 223.
    # + journal_batches_hand_over (item JRN-FAILED-CANCEL-1, lane F-CLO-A; 04 rev 1.159 —
    # REQUIRED, not exempt): 230 − 6 = 224.
    # + modifications_discard (item MOD-DISCARD-1, supervisor ruling R-118 (e); 04 API-R-31 rev
    # 1.188 — REQUIRED, not exempt): 231 − 6 = 225.
    # + files_request_shred (lane SECFIX-IMP; rulings R-49 (a), R-86): required, not exempt:
    # 232 − 6 = 226.
    # + estimate_versions_discard (item EST-DISCARD-1, supervisor ruling R-119 (e); 04 API-R-32
    # rev 1.210 — REQUIRED, not exempt): 233 − 6 = 227.
    # + judgements_discard (the supervisor's ruling of 2026-10-01 on question J1 (a); 04
    # API-R-33 rev 1.242 — REQUIRED, not exempt): 234 − 6 = 228.
    # + combination_groups_discard (item COMBINATION-PROPOSAL-DISCARD-1; 04 API-R-28 rev
    # 1.289 — REQUIRED, not exempt): 235 − 6 = 229.
    assert len(ROUTES) - len(SOP_7_EXEMPT) == len(required) == 235 - 6 == 229
    assert {"users_anonymise", "files_shred"} <= required, "the P8 privacy commands are required"
    assert "session_login" not in required and "session_login" in SOP_7_EXEMPT
    assert QUERY_EXEMPT <= required
