"""Status transitions DB-03 in Python (dev-guide §6.2 DG-SM-01, DG-SM-02; BUILD_SPEC PLF-4,
PLF-6)."""

from __future__ import annotations

from typing import Any, cast

import pytest
from erev_api.db import new_id
from erev_api.db.transitions import (
    TRANSITIONS,
    FrozenElement,
    ParentStatus,
    TableTransitions,
    apply,
    render_trigger_body,
    transition_trigger_sql,
    violations,
)
from erev_api.problems import Problem
from sqlalchemy.orm import Session

PROBE = TableTransitions(
    table="probe",
    status_column="status",
    updatable_columns=frozenset({"note"}),
    pairs=frozenset({("DRAFT", "SUBMITTED"), ("SUBMITTED", "APPROVED")}),
    editable_while=frozenset({"DRAFT"}),
)


class _NoSql:
    """A session stand-in that fails the test on any statement."""

    def execute(self, *_: Any, **__: Any) -> None:
        raise AssertionError("apply issued SQL before validating the change")


def test_dg_sm_02_apply_checks_python_first() -> None:
    session = cast(Session, _NoSql())
    with pytest.raises(Problem) as excinfo:
        apply(
            session, "role_assignment", new_id(), to_status=None, set_values={"role_id": new_id()}
        )
    problem = excinfo.value
    assert (problem.slug, problem.status) == ("invalid-transition", 409)
    assert (problem.errors[0].rule_id, problem.errors[0].field) == ("DB-03", "role_id")

    with pytest.raises(Problem) as no_status:
        apply(session, "role_assignment", new_id(), to_status="REVOKED", set_values={})
    assert [(error.field, error.rule_id) for error in no_status.value.errors] == [(None, "DB-03")]
    with pytest.raises(ValueError):
        apply(session, "role_assignment", new_id(), to_status=None, set_values={})


def test_role_assignment_trigger_body() -> None:
    body = transition_trigger_sql("role_assignment")
    assert set(TRANSITIONS) == {
        "access_review_campaign",
        "access_review_item",
        "approval_delegation",
        "approval_request",
        "approval_step",
        "close_checklist_item",
        "close_run",
        "combination_group",
        "combination_group_member",
        "contract",
        "estimate_version",
        "event_submission",
        "modification",
        "evidence_pack",
        "external_id_map",  # DIN-12 (0072)
        "file_attachment",
        "file_object",
        "import_upload",
        "job",
        "journal_batch",
        "journal_run",
        "judgement_record",
        "manual_adjustment",
        "migration_batch",
        "notification",
        "outbox_message",
        "policy_override",
        "reconciliation",
        "reconciliation_item",
        "report_run",
        "role_assignment",
        "sod_exception",
        "ssp_calculator_run",
        "support_grant",
        "sync_run",  # DIN-12 (0072)
        "tenant_snapshot",
        "user_recovery_code",
        "webhook_delivery",
    }
    assert "ARRAY['revoked_at', 'revoked_by', 'revoked_by_kind', 'valid_to']::text[]" in body
    assert "EREV-TRN-001: columns %s of %I.%I cannot change" in body
    assert "OLD.status" not in body
    assert "is already set" not in body
    assert body == transition_trigger_sql("role_assignment")


def test_recovery_code_trigger_sets_used_at_once() -> None:
    body = transition_trigger_sql("user_recovery_code")
    assert "ARRAY['used_at']::text[]" in body
    assert "IF OLD.used_at IS NOT NULL AND NEW.used_at IS DISTINCT FROM OLD.used_at THEN" in body
    assert "EREV-TRN-001: used_at of %I.%I is already set" in body
    with pytest.raises(Problem) as excinfo:
        apply(
            cast(Session, _NoSql()),
            "user_recovery_code",
            new_id(),
            to_status=None,
            set_values={"code_hash": "x"},
        )
    assert [error.field for error in excinfo.value.errors] == ["code_hash"]


def test_sod_exception_pairs_follow_sm_13() -> None:
    # PRD SM-13: REQUESTED → APPROVED → EXPIRED or REVOKED; REQUESTED → REJECTED (E-96).
    spec = TRANSITIONS["sod_exception"]
    body = transition_trigger_sql("sod_exception")
    assert "ARRAY['approved_at', 'revoked_at', 'revoked_by', 'revoked_by_kind', 'status']" in body
    assert (
        "ARRAY['APPROVED>EXPIRED', 'APPROVED>REVOKED', 'REQUESTED>APPROVED', 'REQUESTED>REJECTED']"
        in body
    )
    assert violations(spec, to_status="APPROVED", set_values={}, expected_status="REQUESTED") == []
    refused = violations(
        spec, to_status="APPROVED", set_values={"valid_to": None}, expected_status="REVOKED"
    )
    assert [error.field for error in refused] == ["status", "valid_to"]


def test_support_grant_pairs_follow_t_plt_33() -> None:
    # 04 T-PLT-33 and E-96: REQUESTED → APPROVED or REJECTED; APPROVED → EXPIRED or REVOKED; the
    # decision and revocation columns are set once.
    spec = TRANSITIONS["support_grant"]
    body = transition_trigger_sql("support_grant")
    assert "ARRAY['approved_at', 'revoked_at', 'revoked_by', 'revoked_by_kind', 'status']" in body
    assert "EREV-TRN-001: revoked_at of %I.%I is already set" in body
    assert (
        "ARRAY['APPROVED>EXPIRED', 'APPROVED>REVOKED', 'REQUESTED>APPROVED', 'REQUESTED>REJECTED']"
        in body
    )
    assert violations(spec, to_status="REVOKED", set_values={}, expected_status="APPROVED") == []
    refused = violations(
        spec, to_status="APPROVED", set_values={"valid_to": None}, expected_status="EXPIRED"
    )
    assert [error.field for error in refused] == ["status", "valid_to"]


def test_access_review_pairs_follow_t_plt_40_and_41() -> None:
    # 04 T-PLT-40, T-PLT-41, E-107, E-108 (SPEC-Q-193): campaigns DRAFT → IN_REVIEW → COMPLETED,
    # DRAFT or IN_REVIEW → CANCELLED; items decided once, a requested revocation confirmed once.
    campaign = TRANSITIONS["access_review_campaign"]
    campaign_body = transition_trigger_sql("access_review_campaign")
    assert (
        "ARRAY['DRAFT>CANCELLED', 'DRAFT>IN_REVIEW', 'IN_REVIEW>CANCELLED', 'IN_REVIEW>COMPLETED']"
        in campaign_body
    )
    assert "EREV-TRN-001: snapshot_file_id of %I.%I is already set" in campaign_body
    assert (
        violations(
            campaign,
            to_status="IN_REVIEW",
            set_values={"started_at": None},
            expected_status="DRAFT",
        )
        == []
    )
    refused = violations(
        campaign, to_status="DRAFT", set_values={"as_of": None}, expected_status="COMPLETED"
    )
    assert [error.field for error in refused] == ["status", "as_of"]

    item = TRANSITIONS["access_review_item"]
    item_body = transition_trigger_sql("access_review_item")
    assert (
        "ARRAY['PENDING>CERTIFIED', 'PENDING>REVOKE_REQUESTED', 'REVOKE_REQUESTED>REVOKED']"
        in item_body
    )
    assert "EREV-TRN-001: revocation_completed_at of %I.%I is already set" in item_body
    assert (
        violations(item, to_status="REVOKED", set_values={}, expected_status="REVOKE_REQUESTED")
        == []
    )
    refused = violations(
        item,
        to_status="REVOKE_REQUESTED",
        set_values={"roles_snapshot": []},
        expected_status="CERTIFIED",
    )
    assert [error.field for error in refused] == ["decision", "roles_snapshot"]


def test_job_pairs_follow_t_plt_27() -> None:
    # 04 T-PLT-27 plus RUNNING → QUEUED for retries (DG-KRN-JOB-05; SPEC-Q-162).
    spec = TRANSITIONS["job"]
    assert spec.pairs == {
        ("QUEUED", "RUNNING"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "SUCCEEDED_WITH_EXCEPTIONS"),
        ("RUNNING", "FAILED"),
        ("QUEUED", "CANCELLED"),
        ("RUNNING", "CANCELLED"),
        ("RUNNING", "QUEUED"),
    }
    assert (
        violations(
            spec, to_status="RUNNING", set_values={"started_at": None}, expected_status="QUEUED"
        )
        == []
    )
    refused = violations(
        spec, to_status="QUEUED", set_values={"params": {}}, expected_status="SUCCEEDED"
    )
    assert [error.field for error in refused] == ["state", "params"]


def test_status_pairs_and_editable_statuses() -> None:
    body = render_trigger_body(PROBE)
    assert "IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN" in body
    assert "ARRAY['note', 'status']::text[]" in body
    assert "ARRAY['DRAFT>SUBMITTED', 'SUBMITTED>APPROVED']::text[]" in body
    # D-98 candidate 143 GUARD-TRN-1 (DG-KRN-DB-09): the pair guard precedes the editable
    # early-return, so a DRAFT row moves only along a listed pair at the database layer too.
    assert body.index("IF NEW.status IS DISTINCT FROM OLD.status") < body.index(
        "IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN"
    )


def test_guard_trn_1_pair_guard_precedes_the_editable_return_for_every_editable_spec() -> None:
    """D-98 candidate 143 GUARD-TRN-1 (Codex production-20260921-1642 §1 R1; dev-guide
    DG-KRN-DB-09): for every spec with an editable status the rendered body checks the status
    pairs BEFORE ``RETURN NEW`` on an editable row; ``editable_while`` relaxes only the column
    freeze. Fail-first: the previous renderer emitted the editable return first."""
    editable = sorted(name for name, spec in TRANSITIONS.items() if spec.editable_while)
    assert editable == [
        "contract",
        "estimate_version",
        "event_submission",
        "judgement_record",
        "manual_adjustment",
        "modification",
        "policy_override",
    ]
    for name in editable:
        body = transition_trigger_sql(name)
        status = TRANSITIONS[name].status_column
        guard = body.index(f"IF NEW.{status} IS DISTINCT FROM OLD.{status}")
        early_return = body.index(f"IF OLD.{status}::text = ANY (")
        assert guard < early_return, name
        # the column-freeze check still follows the editable return (an editable row may change
        # any column), and the pairs are the table's
        assert early_return < body.index("SELECT string_agg(n.key"), name

    refused = violations(
        PROBE, to_status="APPROVED", set_values={"amount": 1, "note": "x"}, expected_status="DRAFT"
    )
    assert [error.field for error in refused] == ["status"]
    frozen = violations(
        PROBE, to_status=None, set_values={"amount": 1}, expected_status="SUBMITTED"
    )
    assert [error.field for error in frozen] == ["amount"]
    assert violations(PROBE, to_status="SUBMITTED", set_values={}, expected_status="DRAFT") == []


def test_close_frozen_statuses_and_parent_status() -> None:
    # CLO-2: a SUCCEEDED close run changes only its status, SC-M and steps (the database limits
    # steps to the LOCK element, BS4-D-03); a CERTIFIED reconciliation changes only its status; a
    # reconciliation item is frozen by its parent's status, which only the database can read.
    close_run = TRANSITIONS["close_run"]
    assert (
        violations(
            close_run,
            to_status=None,
            set_values={"steps": [], "updated_at": None},
            expected_status="SUCCEEDED",
        )
        == []
    )
    frozen = violations(
        close_run,
        to_status=None,
        set_values={"counts": {}, "finished_at": None},
        expected_status="SUCCEEDED",
    )
    assert [(error.field, error.rule_id) for error in frozen] == [
        ("counts", "DB-03"),
        ("finished_at", "DB-03"),
    ]
    resumed = violations(close_run, to_status="RUNNING", set_values={}, expected_status="SUCCEEDED")
    assert [error.field for error in resumed] == ["status"]
    assert violations(close_run, to_status="RUNNING", set_values={}, expected_status="FAILED") == []

    reconciliation = TRANSITIONS["reconciliation"]
    certified = violations(
        reconciliation, to_status="REOPENED", set_values={"totals": []}, expected_status="CERTIFIED"
    )
    assert [error.field for error in certified] == ["totals"]
    assert (
        violations(reconciliation, to_status="REOPENED", set_values={}, expected_status="CERTIFIED")
        == []
    )

    run_body = transition_trigger_sql("close_run")
    assert "change only in element LOCK while status is %s" in run_body
    assert "o.item ->> 'step_code' = 'LOCK' AND n.item ->> 'step_code' = 'LOCK'" in run_body
    item_body = transition_trigger_sql("reconciliation_item")
    assert "  parent_status text;\nBEGIN\n  SELECT p.status::text INTO parent_status" in item_body
    assert "FROM erev.reconciliation p" in item_body
    assert "parent_status" not in transition_trigger_sql("journal_run")

    with pytest.raises(ValueError, match="editable and frozen"):
        TableTransitions(
            table="probe",
            status_column="status",
            updatable_columns=frozenset({"note"}),
            pairs=frozenset(),
            editable_while=frozenset({"DRAFT"}),
            frozen_while=frozenset({"DRAFT"}),
        )
    with pytest.raises(ValueError, match="frozen element"):
        TableTransitions(
            table="probe",
            status_column="status",
            updatable_columns=frozenset({"note"}),
            pairs=frozenset(),
            frozen_element=FrozenElement(column="note", key="code", value="LOCK"),
        )
    with pytest.raises(ValueError, match="NC-02"):
        TableTransitions(
            table="probe",
            status_column=None,
            updatable_columns=frozenset({"note"}),
            pairs=frozenset(),
            parent=ParentStatus(
                table="Parent", column="parent_id", status_column="status", statuses=frozenset()
            ),
        )


def test_table_transitions_validation() -> None:
    with pytest.raises(ValueError, match="no status column"):
        TableTransitions("probe", None, frozenset({"note"}), frozenset({("A", "B")}))
    with pytest.raises(ValueError, match="status column"):
        TableTransitions("probe", "status", frozenset({"status"}), frozenset())
    with pytest.raises(ValueError, match="NC-02"):
        TableTransitions("probe", None, frozenset({"Note; DROP"}), frozenset())
    with pytest.raises(ValueError, match="set-once"):
        TableTransitions(
            "probe", None, frozenset({"note"}), frozenset(), set_once=frozenset({"used_at"})
        )
