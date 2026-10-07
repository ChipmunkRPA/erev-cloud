"""Immutability and grants DG-TST-21 (04 §1.5, §1.6, §14.2; DB-13, DB-14 (f); BUILD_SPEC PLF-1,
PLF-3, PLF-4)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    contract,
    contract_event,
    contract_version,
    journal_batch,
    lock_snapshot,
    metadata,
    password_reset_token,
    period_lock,
    posting_ack,
    role,
    role_permission,
    security_event,
    signoff,
    source_record,
    subledger_line,
)
from erev_api.db.transitions import TRANSITIONS
from sqlalchemy import (
    Connection,
    CursorResult,
    Executable,
    and_,
    delete,
    exc,
    insert,
    select,
    text,
    update,
)
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    contract_event_values,
    insert_app_user,
    insert_close_parts,
    insert_contract_rows,
    insert_journal_rows,
    insert_ledger_rows,
    insert_version_rows,
    lock_snapshot_values,
    period_lock_values,
    posting_ack_values,
    signoff_values,
    source_record_values,
)

pytestmark = pytest.mark.pg

# 04 §14.2 rev 1.2: the app_user columns erev_app may update; rev 1.86 (revision 0073) adds
# email and external_id for user.anonymise (05 PRV-07 a) — "admitted only in the erasure form by
# DB-19" (tests/pg/test_app_user_erasure_guard.py).
APP_USER_UPDATE_COLUMNS = frozenset(
    {
        "display_name",
        "password_hash",
        "password_changed_at",
        "status",
        "failed_login_count",
        "locked_until",
        "identity_provider_id",
        "last_login_at",
        "preferences",
        "updated_at",
        "updated_by",
        "updated_by_kind",
        "row_version",
        "email",
        "external_id",
        # rev 1.108 (revision 0092): written at the first sign-in through the provider.
        "identity_provider_subject",
    }
)
_TABLE_GRANTS = text(
    "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
    "WHERE grantee = 'erev_app' AND table_schema = 'erev' AND table_name = ANY(:tables)"
)
_APP_USER_UPDATE_GRANTS = text(
    "SELECT column_name FROM information_schema.column_privileges "
    "WHERE grantee = 'erev_app' AND table_schema = 'erev' AND table_name = 'app_user' "
    "AND privilege_type = 'UPDATE'"
)
_RECOVERY_CODE_UPDATE_GRANTS = text(
    "SELECT column_name FROM information_schema.column_privileges "
    "WHERE grantee = 'erev_app' AND table_schema = 'erev' AND table_name = 'user_recovery_code' "
    "AND privilege_type = 'UPDATE'"
)
_AUDIT_PARTITIONS = text(
    "SELECT c.relname, "
    "has_table_privilege('erev_app', c.oid, "
    "'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN') "
    "OR has_any_column_privilege('erev_app', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES') "
    "FROM pg_partition_tree(CAST('erev.audit_event' AS regclass)) t "
    "JOIN pg_class c ON c.oid = t.relid "
    "WHERE t.relid <> CAST('erev.audit_event' AS regclass) ORDER BY c.relname"
)


def _grants(session_tables: list[str]) -> dict[str, set[str]]:
    grants: dict[str, set[str]] = {}
    with identity_session(request_id="tests-dg-tst-21-grants") as session:
        for table_name, privilege in session.execute(_TABLE_GRANTS, {"tables": session_tables}):
            grants.setdefault(str(table_name), set()).add(str(privilege))
    return grants


def test_dg_tst_21_identity_grants(test_database: TestDatabase) -> None:
    with identity_session(request_id="tests-dg-tst-21") as session:
        update_columns = {str(name) for name in session.scalars(_APP_USER_UPDATE_GRANTS)}
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(update(security_event).values(request_id="tampered"))
        savepoint.rollback()

    assert _grants(["app_user", "identity_provider", "security_event"]) == {
        "app_user": {"SELECT", "INSERT"},
        "identity_provider": {"SELECT"},
        "security_event": {"SELECT", "INSERT"},
    }
    assert len(APP_USER_UPDATE_COLUMNS) == 16
    assert update_columns == APP_USER_UPDATE_COLUMNS
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"


def test_dg_tst_21_mfa_grants(test_database: TestDatabase) -> None:
    with identity_session(request_id="tests-dg-tst-21-mfa") as session:
        recovery_update = {str(name) for name in session.scalars(_RECOVERY_CODE_UPDATE_GRANTS)}
    # 04 §14.2: SELECT, INSERT, UPDATE and no DELETE; recovery codes grant UPDATE of used_at only.
    assert _grants(["user_mfa_factor", "user_recovery_code"]) == {
        "user_mfa_factor": {"SELECT", "INSERT", "UPDATE"},
        "user_recovery_code": {"SELECT", "INSERT"},
    }
    assert recovery_update == {"used_at"}


def test_dg_tst_21_audit_partitions_without_child_privileges(test_database: TestDatabase) -> None:
    with identity_session(request_id="tests-dg-tst-21-partitions") as session:
        partitions = [(str(name), bool(held)) for name, held in session.execute(_AUDIT_PARTITIONS)]

    names = [name for name, _ in partitions]
    assert len(partitions) == 181
    assert names[0] == "audit_event_p201801"
    assert names[-2:] == ["audit_event_p203212", "audit_event_pdefault"]
    assert [name for name, held in partitions if held] == []
    assert _grants(["audit_event", "audit_chain_head"]) == {
        "audit_event": {"SELECT", "INSERT"},
        "audit_chain_head": {"SELECT", "INSERT", "UPDATE"},
    }


# 04 T-PLT-10 and §14.2: the role_assignment columns erev_app may update.
ROLE_ASSIGNMENT_UPDATE_COLUMNS = frozenset(
    {"revoked_at", "revoked_by", "revoked_by_kind", "valid_to"}
)
_UPDATE_COLUMNS = text(
    "SELECT column_name FROM information_schema.column_privileges "
    "WHERE grantee = 'erev_app' AND table_schema = 'erev' AND table_name = :table "
    "AND privilege_type = 'UPDATE'"
)


def test_dg_tst_21_role_grants(committed_db: TestDatabase, keyring: KeyRing) -> None:
    assert _grants(["role", "role_assignment", "role_permission"]) == {
        "role": {"SELECT", "INSERT", "UPDATE"},
        "role_assignment": {"SELECT", "INSERT"},
        "role_permission": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    }
    with identity_session(request_id="tests-dg-tst-21-role-columns") as session:
        columns = {
            str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": "role_assignment"})
        }
    assert columns == ROLE_ASSIGNMENT_UPDATE_COLUMNS

    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    viewer = select(role.c.id).where(role.c.code == "viewer").scalar_subquery()
    report_run = (
        role_permission.c.role_id == viewer,
        role_permission.c.permission_code == "report.run",
    )
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # DB-01 blocks UPDATE of role_permission (04 T-PLT-12).
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(
                update(role_permission).where(*report_run).values(permission_code="report.export")
            )
        savepoint.rollback()
        # DELETE is granted on role_permission; the removal is rolled back.
        savepoint = session.begin_nested()
        removed = cast(
            CursorResult[Any], session.execute(delete(role_permission).where(*report_run))
        )
        assert removed.rowcount == 1
        savepoint.rollback()
    orig = excinfo.value.orig
    assert getattr(orig, "sqlstate", None) == "P0001"
    message = str(getattr(getattr(orig, "diag", None), "message_primary", ""))
    assert message.startswith("EREV-IMM-001")


def test_dg_tst_21_sod_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-P SELECT, INSERT, UPDATE, DELETE; IM-S UPDATE of the T-PLT-14 columns only.
    assert _grants(["sod_rule", "sod_exception"]) == {
        "sod_rule": {"SELECT", "INSERT", "UPDATE", "DELETE"},
        "sod_exception": {"SELECT", "INSERT"},
    }
    with identity_session(request_id="tests-dg-tst-21-sod-columns") as session:
        columns = {
            str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": "sod_exception"})
        }
    assert columns == {"status", "approved_at", "revoked_at", "revoked_by", "revoked_by_kind"}


def test_dg_tst_21_file_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 and T-PLT-29, T-PLT-30: SELECT and INSERT, UPDATE of the allow-listed columns only.
    assert _grants(["file_object", "file_attachment"]) == {
        "file_object": {"SELECT", "INSERT"},
        "file_attachment": {"SELECT", "INSERT"},
    }
    with identity_session(request_id="tests-dg-tst-21-file-columns") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in ("file_object", "file_attachment")
        }
    assert columns == {
        "file_object": {
            "legal_hold",
            "retention_until",
            "shredded_at",
            "shredded_by",
            "shredded_by_kind",
            "shred_reason",
            "shred_completed_at",  # 04 rev 1.237 (revision 0120): set once, by the completion
        },
        "file_attachment": {"voided_at", "voided_by", "voided_by_kind", "void_reason"},
    }


_PROCRASTINATE_GRANTS = text(
    "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
    "WHERE grantee = 'erev_app' AND table_schema = 'public' "
    "AND starts_with(table_name, 'procrastinate_')"
)


def test_dg_tst_21_approval_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-S SELECT, INSERT and UPDATE of the T-PLT-17, T-PLT-18 and T-PLT-21 columns only;
    # IM-A SELECT and INSERT.
    tables = ["approval_request", "approval_step", "approval_decision", "approval_delegation"]
    assert _grants(tables) == {table: {"SELECT", "INSERT"} for table in tables}
    with identity_session(request_id="tests-dg-tst-21-approval-columns") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in tables
        }
    assert columns == {
        "approval_request": {"status", "decided_at", "voided_at", "void_reason", "current_step_no"},
        "approval_step": {"status", "activated_at", "completed_at"},
        "approval_decision": set(),
        "approval_delegation": {"revoked_at", "revoked_by", "revoked_by_kind"},
    }


def test_dg_tst_21_rule_set_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M SELECT, INSERT, UPDATE; IM-P and IM-P children SELECT, INSERT, UPDATE, DELETE
    # (DB-04 limits DELETE and child writes to editable versions).
    tables = ["rule_set", "rule_set_version", "rule", "rule_test_case"]
    im_p = {"SELECT", "INSERT", "UPDATE", "DELETE"}
    assert _grants(tables) == {
        "rule_set": {"SELECT", "INSERT", "UPDATE"},
        "rule_set_version": im_p,
        "rule": im_p,
        "rule_test_case": im_p,
    }


def test_dg_tst_21_saved_view_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M SELECT, INSERT, UPDATE, plus DELETE on saved_view (T-PLT-37).
    assert _grants(["saved_view"]) == {"saved_view": {"SELECT", "INSERT", "UPDATE", "DELETE"}}


def test_dg_tst_21_calendar_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M SELECT, INSERT, UPDATE and no DELETE (T-REF-04, T-REF-05).
    im_m = {"SELECT", "INSERT", "UPDATE"}
    assert _grants(["fiscal_calendar", "period"]) == {"fiscal_calendar": im_m, "period": im_m}


def test_dg_tst_21_account_and_dimension_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M SELECT, INSERT, UPDATE and no DELETE (T-REF-13, T-REF-16, T-REF-17).
    tables = ["gl_account", "dimension_definition", "dimension_value"]
    assert _grants(tables) == dict.fromkeys(tables, {"SELECT", "INSERT", "UPDATE"})


def test_dg_tst_21_entity_book_and_period_state_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M legal_entity and entity_book; IM-X period_state; IM-A period_state_transition;
    # IM-M book, whose immutable code is left out of its UPDATE grant (T-REF-02).
    tables = ["legal_entity", "book", "entity_book", "period_state", "period_state_transition"]
    assert _grants(tables) == {
        "legal_entity": {"SELECT", "INSERT", "UPDATE"},
        "book": {"SELECT", "INSERT"},
        "entity_book": {"SELECT", "INSERT", "UPDATE"},
        "period_state": {"SELECT", "INSERT", "UPDATE"},
        "period_state_transition": {"SELECT", "INSERT"},
    }
    with identity_session(request_id="tests-dg-tst-21-book-columns") as session:
        columns = {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": "book"})}
    assert columns == {
        "name",
        "is_primary",
        "is_enabled",
        "posting_target",
        "updated_at",
        "updated_by",
        "updated_by_kind",
        "row_version",
    }


def test_dg_tst_21_currency_and_fx_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M tenant_currency and fx_rate_set (DELETE forbidden; disable instead); IM-P
    # fx_rate_set_version and its child fx_rate, whose DELETE DB-04 limits to DRAFT versions.
    tables = ["tenant_currency", "fx_rate_set", "fx_rate_set_version", "fx_rate"]
    assert _grants(tables) == {
        "tenant_currency": {"SELECT", "INSERT", "UPDATE"},
        "fx_rate_set": {"SELECT", "INSERT", "UPDATE"},
        "fx_rate_set_version": {"SELECT", "INSERT", "UPDATE", "DELETE"},
        "fx_rate": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    }


def test_dg_tst_21_customer_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M SELECT, INSERT, UPDATE and no DELETE (T-REF-18, T-REF-19; deactivate instead).
    tables = ["related_party_group", "customer"]
    assert _grants(tables) == dict.fromkeys(tables, {"SELECT", "INSERT", "UPDATE"})


def test_dg_tst_21_product_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M SELECT, INSERT, UPDATE; DELETE only on product_bundle_component among the
    # product tables (T-REF-20 deactivate instead; T-REF-21 rows are replaced).
    assert _grants(["product", "product_bundle_component"]) == {
        "product": {"SELECT", "INSERT", "UPDATE"},
        "product_bundle_component": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    }


def test_dg_tst_21_account_mapping_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-P account_mapping_version and its child account_mapping_rule (T-REF-14,
    # T-REF-15), whose DELETE DB-04 limits to DRAFT and TESTED versions.
    tables = ["account_mapping_version", "account_mapping_rule"]
    assert _grants(tables) == dict.fromkeys(tables, {"SELECT", "INSERT", "UPDATE", "DELETE"})


def test_dg_tst_21_ssp_book_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M ssp_book (T-REF-28); IM-P ssp_book_version and its children ssp_entry and
    # ssp_range (T-REF-29 to T-REF-31), whose DELETE DB-04 limits to editable versions.
    versioned = ["ssp_book_version", "ssp_entry", "ssp_range"]
    assert _grants(["ssp_book", *versioned]) == {
        "ssp_book": {"SELECT", "INSERT", "UPDATE"},
        **dict.fromkeys(versioned, {"SELECT", "INSERT", "UPDATE", "DELETE"}),
    }


def test_dg_tst_21_pob_template_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M pob_template (T-REF-22); IM-P pob_template_version (T-REF-23), whose DELETE
    # DB-04 limits to DRAFT and TESTED versions.
    assert _grants(["pob_template", "pob_template_version"]) == {
        "pob_template": {"SELECT", "INSERT", "UPDATE"},
        "pob_template_version": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    }


def test_dg_tst_21_ssp_calculator_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-S ssp_calculator_run (T-REF-32) with UPDATE of its listed columns only; IM-A
    # ssp_calculator_result (T-REF-33) and ssp_calculator_exclusion (T-REF-34).
    tables = ["ssp_calculator_run", "ssp_calculator_result", "ssp_calculator_exclusion"]
    assert _grants(tables) == {
        "ssp_calculator_run": {"SELECT", "INSERT"},
        "ssp_calculator_result": {"SELECT", "INSERT"},
        "ssp_calculator_exclusion": {"SELECT", "INSERT"},
    }
    with identity_session(request_id="tests-dg-tst-21-ssp-calculator-columns") as session:
        columns = {
            str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": "ssp_calculator_run"})
        }
    assert columns == {
        "status",
        "observation_count",
        "result_file_id",
        "draft_ssp_book_version_id",
        "started_at",
        "finished_at",
    }


def test_dg_tst_21_audit_chain_verification_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-A SELECT and INSERT (T-PLT-23).
    assert _grants(["audit_chain_verification"]) == {
        "audit_chain_verification": {"SELECT", "INSERT"}
    }


def test_dg_tst_21_audit_event_contract_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-A SELECT and INSERT (T-PLT-48, revision 0101): the index of the audit log by
    # contract is as immutable for the application as the log it indexes.
    assert _grants(["audit_event_contract"]) == {"audit_event_contract": {"SELECT", "INSERT"}}


def test_dg_tst_21_file_upload_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-A SELECT and INSERT (T-PLT-49, revision 0103): an upload, once recorded, is as
    # immutable for the application as the file row it names.
    assert _grants(["file_upload"]) == {"file_upload": {"SELECT", "INSERT"}}


def test_dg_tst_21_webhook_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M SELECT, INSERT, UPDATE (T-PLT-35); IM-S SELECT, INSERT and UPDATE of the
    # T-PLT-36 columns only.
    assert _grants(["webhook_endpoint", "webhook_delivery"]) == {
        "webhook_endpoint": {"SELECT", "INSERT", "UPDATE"},
        "webhook_delivery": {"SELECT", "INSERT"},
    }
    with identity_session(request_id="tests-dg-tst-21-webhook-columns") as session:
        columns = {
            str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": "webhook_delivery"})
        }
    assert columns == {
        "status",
        "attempt_count",
        "next_attempt_at",
        "last_response_status",
        "last_error",
        "succeeded_at",
    }


def test_dg_tst_21_api_client_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-M SELECT, INSERT, UPDATE (T-PLT-15); IM-E SELECT, INSERT, UPDATE, DELETE
    # (T-PLT-16).
    assert _grants(["api_client", "api_token"]) == {
        "api_client": {"SELECT", "INSERT", "UPDATE"},
        "api_token": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    }


def test_dg_tst_21_support_grant_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-S SELECT, INSERT and UPDATE of the T-PLT-33 columns only.
    assert _grants(["support_grant"]) == {"support_grant": {"SELECT", "INSERT"}}
    with identity_session(request_id="tests-dg-tst-21-support-grant-columns") as session:
        columns = {
            str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": "support_grant"})
        }
    assert columns == {"status", "approved_at", "revoked_at", "revoked_by", "revoked_by_kind"}


def test_dg_tst_21_access_review_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-S SELECT, INSERT and UPDATE of the T-PLT-40 and T-PLT-41 columns only.
    tables = ["access_review_campaign", "access_review_item"]
    assert _grants(tables) == {table: {"SELECT", "INSERT"} for table in tables}
    sc_m = {"updated_at", "updated_by", "updated_by_kind", "row_version"}
    with identity_session(request_id="tests-dg-tst-21-access-review-columns") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in tables
        }
    assert columns == {
        "access_review_campaign": {"status", "started_at", "completed_at", "snapshot_file_id"}
        | sc_m,
        "access_review_item": {
            "decision",
            "reviewer_id",
            "decided_at",
            "comment",
            "revocation_completed_at",
        }
        | sc_m,
    }


def test_dg_tst_21_numbering_and_job_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-X SELECT, INSERT, UPDATE; IM-S UPDATE of the T-PLT-27 columns only; the
    # Procrastinate tables in public SELECT, INSERT, UPDATE, DELETE (DG-MIG-09).
    assert _grants(["numbering_series", "job"]) == {
        "numbering_series": {"SELECT", "INSERT", "UPDATE"},
        "job": {"SELECT", "INSERT"},
    }
    with identity_session(request_id="tests-dg-tst-21-job-columns") as session:
        columns = {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": "job"})}
        public: dict[str, set[str]] = {}
        for table_name, privilege in session.execute(_PROCRASTINATE_GRANTS):
            public.setdefault(str(table_name), set()).add(str(privilege))
    assert columns == {
        "state",
        "progress_done",
        "progress_total",
        "result",
        "problem",
        "procrastinate_job_id",
        "started_at",
        "finished_at",
        "cancel_requested_at",
        "updated_at",
        "updated_by",
        "updated_by_kind",
        "row_version",
    }
    tables = ("procrastinate_events", "procrastinate_jobs", "procrastinate_periodic_defers")
    assert public == {
        table: {"SELECT", "INSERT", "UPDATE", "DELETE"}
        for table in (*tables, "procrastinate_workers")
    }


def test_dg_tst_21_outbox_and_notification_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-S SELECT, INSERT and UPDATE of the T-INT-03 and T-PLT-24 columns only; IM-M
    # SELECT, INSERT and UPDATE (T-PLT-25).
    tables = ["outbox_message", "notification", "notification_preference"]
    assert _grants(tables) == {
        "outbox_message": {"SELECT", "INSERT"},
        "notification": {"SELECT", "INSERT"},
        "notification_preference": {"SELECT", "INSERT", "UPDATE"},
    }
    with identity_session(request_id="tests-dg-tst-21-outbox-columns") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in ("outbox_message", "notification")
        }
    assert columns == {
        "outbox_message": {
            "status",
            "attempt_count",
            "next_attempt_at",
            "last_error",
            "dispatched_at",
            "updated_at",
            "updated_by",
            "updated_by_kind",
            "row_version",
        },
        "notification": {"read_at", "email_sent_at"},
    }


def test_dg_tst_21_integration_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 (DIN-12, revision 0072): IM-M SELECT, INSERT, UPDATE (T-INT-01); IM-S SELECT, INSERT
    # and UPDATE of the T-INT-02 ledger members with SC-M (the class header — every move of a run
    # stamps SC-M, and one column missing from the grant refuses the whole UPDATE with 42501) and
    # of T-INT-04 ``valid_to`` only.
    tables = ["integration_connection", "sync_run", "external_id_map"]
    assert _grants(tables) == {
        "integration_connection": {"SELECT", "INSERT", "UPDATE"},
        "sync_run": {"SELECT", "INSERT"},
        "external_id_map": {"SELECT", "INSERT"},
    }
    with identity_session(request_id="tests-dg-tst-21-integration-columns") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in ("sync_run", "external_id_map")
        }
    assert columns == {
        "sync_run": {
            "status",
            "checkpoint_after",
            "source_totals",
            "loaded_totals",
            "record_count",
            "exception_count",
            "problem",
            "started_at",
            "finished_at",
            "updated_at",
            "updated_by",
            "updated_by_kind",
            "row_version",
        },
        "external_id_map": {"valid_to"},
    }


def test_db_03_registry_columns_are_granted(test_database: TestDatabase) -> None:
    """Every column the DB-03 registry lets the application move — the status column and the
    updatable columns, SC-M included — is in ``erev_app``'s UPDATE grant of its table. One column
    missing from the grant refuses the whole UPDATE with 42501, whatever the transition trigger
    allows: revision 0072 listed ``sync_run`` without SC-M and no run could start."""
    with identity_session(request_id="tests-db-03-grants") as session:
        granted = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in TRANSITIONS
        }
    missing: dict[str, list[str]] = {}
    for table, spec in TRANSITIONS.items():
        wanted = set(spec.updatable_columns)
        if spec.status_column is not None:
            wanted.add(spec.status_column)
        if wanted - granted[table]:
            missing[table] = sorted(wanted - granted[table])
    assert missing == {}


def test_dg_tst_21_password_reset_token_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 rev 1.2: SELECT, INSERT, UPDATE (used_at, superseded_at) and DELETE (retention).
    assert _grants(["password_reset_token"]) == {
        "password_reset_token": {"SELECT", "INSERT", "DELETE"}
    }
    with identity_session(request_id="tests-dg-tst-21-reset") as session:
        columns = {
            str(name)
            for name in session.scalars(
                text(
                    "SELECT column_name FROM information_schema.column_privileges "
                    "WHERE grantee = 'erev_app' AND table_schema = 'erev' "
                    "AND table_name = 'password_reset_token' AND privilege_type = 'UPDATE'"
                )
            )
        }
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(update(password_reset_token).values(request_id="tampered"))
        savepoint.rollback()
    assert columns == {"used_at", "superseded_at"}
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"


def test_dg_tst_21_idempotency_grants(test_database: TestDatabase) -> None:
    # 04 §14.2: IM-E tables grant SELECT, INSERT, UPDATE and DELETE (T-PLT-28).
    assert _grants(["idempotency_record"]) == {
        "idempotency_record": {"SELECT", "INSERT", "UPDATE", "DELETE"}
    }


CONTRACT_TABLES = (
    "contract",
    "combination_group",
    "combination_group_member",
    "contract_event",
    "obligation",
    "event_submission",
)
_SC_M_COLUMNS = frozenset({"updated_at", "updated_by", "updated_by_kind", "row_version"})


def test_dg_tst_21_contract_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 (CTR-1): IM-X contract SELECT, INSERT, UPDATE; IM-A contract_event and obligation
    # SELECT, INSERT; IM-S combination_group, combination_group_member and event_submission SELECT,
    # INSERT and UPDATE of their T-CON-03, T-CON-04 and T-CON-24 columns (L3-1-Q-13).
    assert _grants(list(CONTRACT_TABLES)) == {
        "contract": {"SELECT", "INSERT", "UPDATE"},
        **{table: {"SELECT", "INSERT"} for table in CONTRACT_TABLES[1:]},
    }
    with identity_session(request_id="tests-dg-tst-21-contract-columns") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in CONTRACT_TABLES[1:]
        }
    assert columns == {
        "combination_group": {
            "status",
            "criterion",
            "rationale",
            "judgement_record_id",
            "approval_request_id",
            "inception_date",
            "head_computation_id",
            "dirty_since",
            "period_ends_open",  # 04 T-CON-03 rev 1.172 (revision 0111; item CLO-GATE-RUN-1)
            "dirty_trigger",  # 04 T-CON-03 rev 1.297 (revision 0128; item FX-REPUBLISH-DIRTY-1)
        }
        | _SC_M_COLUMNS,
        "combination_group_member": {"valid_to_known_at", "leave_event_id"},
        "contract_event": set(),
        "obligation": set(),
        "event_submission": {
            "events",
            "status",
            "comment",
            "content_sha256",
            "approval_request_id",
            "applied_event_ids",
        }
        | _SC_M_COLUMNS,
    }


def test_dg_tst_21_policy_override_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 (CTR-15): IM-S policy_override SELECT, INSERT and UPDATE of the T-CON-23 columns
    # that change while DRAFT or afterwards; the DB-03 trigger narrows them after submission.
    assert _grants(["policy_override"]) == {"policy_override": {"SELECT", "INSERT"}}
    with identity_session(request_id="tests-dg-tst-21-policy-override-columns") as session:
        columns = {
            str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": "policy_override"})
        }
    assert (
        columns
        == {
            "value",
            "rationale",
            "judgement_record_id",
            "status",
            "content_sha256",
            "approval_request_id",
            "approved_at",
        }
        | _SC_M_COLUMNS
    )


def _committed_event(keyring: KeyRing) -> tuple[DbContext, dict[str, Any]]:
    """A contract at head 1 with its first event, committed as erev_app."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        chain = insert_contract_rows(session, tenant_id, head_stream_version=1)
        row = contract_event_values(
            tenant_id,
            contract_id=chain.contract_id,
            contracting_entity_id=chain.entity_id,
            stream_version=1,
        )
        session.execute(insert(contract_event).values(**row))
    return context, row


_TABLE_TRIGGERS = text(
    "SELECT t.tgname, t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'erev' AND c.relname = :table AND NOT t.tgisinternal"
)


def test_contract_event_append_only(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-01 (CTR-1; DG-TST-21): erev_app holds no UPDATE, DELETE or TRUNCATE on contract_event
    # (42501), and the DB-01 row and statement triggers guard it for any other role (EREV-IMM-001).
    context, row = _committed_event(keyring)
    target = contract_event.c.id == row["id"]
    outcomes: list[str | None] = []
    with tenant_session(context) as session:
        for statement in (
            update(contract_event).where(target).values(request_id="tampered"),
            delete(contract_event).where(target),
            text("TRUNCATE erev.contract_event"),
        ):
            savepoint = session.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                session.execute(statement)
            savepoint.rollback()
            outcomes.append(getattr(excinfo.value.orig, "sqlstate", None))
    assert outcomes == ["42501", "42501", "42501"]
    with identity_session(request_id="tests-contract-event-triggers") as session:
        triggers = {
            str(name): str(enabled)
            for name, enabled in session.execute(_TABLE_TRIGGERS, {"table": "contract_event"})
        }
    assert triggers == {
        "tg_contract_event__immutable": "O",
        "tg_contract_event__insert": "O",
        "tg_contract_event__truncate": "O",
    }


@pytest.mark.control("CTL-047")
def test_ctl_047_contract_event_update_denied(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # CTL-047 (REQ-CON-014): an UPDATE of a committed event fails and the row is unchanged.
    context, row = _committed_event(keyring)
    target = contract_event.c.id == row["id"]
    columns = (
        contract_event.c.payload,
        contract_event.c.payload_sha256,
        contract_event.c.stream_version,
        contract_event.c.request_id,
    )
    with tenant_session(context, read_only=True) as session:
        before = tuple(session.execute(select(*columns).where(target)).one())
    with tenant_session(context) as session:
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(
                update(contract_event)
                .where(target)
                .values(payload={"description": "Tampered"}, payload_sha256="0" * 64)
            )
        savepoint.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"
    with tenant_session(context, read_only=True) as session:
        after = tuple(session.execute(select(*columns).where(target)).one())
    assert after == before
    assert after[0] == {"description": "Probe change"}


ENGINE_OUTPUT_TABLES = (
    "contract_computation",
    "contract_version",
    "contract_version_balance",
    "obligation_version",
    "schedule",
    "schedule_line",
    "calc_trace",
    "loss_provision_version",
    "loss_provision_eac",
)
_ENABLED_TRIGGERS = text(
    "SELECT c.relname, t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'erev' "
    "AND c.relname = ANY(:tables) AND NOT t.tgisinternal AND t.tgenabled <> 'D'"
)


def test_dg_tst_21_engine_output_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 (CTR-2): the seven IM-A tables of computed state grant erev_app SELECT and INSERT
    # only, with the DB-01 row and statement triggers and the DB-17 constraint trigger enabled.
    tables = list(ENGINE_OUTPUT_TABLES)
    assert _grants(tables) == {table: {"SELECT", "INSERT"} for table in tables}
    with identity_session(request_id="tests-dg-tst-21-engine-output") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in tables
        }
        triggers = {
            (str(table), str(name))
            for table, name in session.execute(_ENABLED_TRIGGERS, {"tables": tables})
        }
    assert columns == {table: set() for table in tables}
    expected = {
        (table, f"tg_{table}__{purpose}")
        for table in tables
        for purpose in ("immutable", "truncate")
    }
    assert expected | {("contract_version", "tg_contract_version__allocation")} == triggers


@pytest.mark.control("CTL-047")
def test_ctl_047_contract_version_update_denied(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # CTL-047 (REQ-CON-014): an UPDATE of a committed contract version fails and the row is
    # unchanged; DELETE fails too.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        rows = insert_version_rows(session, tenant_id)
    target = contract_version.c.id == rows.version_id
    columns = (
        contract_version.c.transaction_price,
        contract_version.c.output_sha256,
        contract_version.c.version_no,
        contract_version.c.calc_trace_id,
    )
    with tenant_session(context, read_only=True) as session:
        before = tuple(session.execute(select(*columns).where(target)).one())
    outcomes: list[str | None] = []
    with tenant_session(context) as session:
        for statement in (
            update(contract_version)
            .where(target)
            .values(transaction_price=Decimal("1"), output_sha256="0" * 64),
            delete(contract_version).where(target),
        ):
            savepoint = session.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                session.execute(statement)
            savepoint.rollback()
            outcomes.append(getattr(excinfo.value.orig, "sqlstate", None))
    assert outcomes == ["42501", "42501"]
    with tenant_session(context, read_only=True) as session:
        after = tuple(session.execute(select(*columns).where(target)).one())
    assert after == before
    assert (after[0], after[2], after[3]) == (Decimal(0), 1, rows.trace_id)


SUBLEDGER_TABLES = ("subledger_posting", "subledger_posting_seal", "subledger_line")


def test_dg_tst_21_subledger_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 (CTR-3): postings, seals and lines are IM-A (SELECT, INSERT) with the DB-01 row and
    # statement triggers and the DB-06 and DB-07 triggers; the ledger chain head is IM-X.
    tables = [*SUBLEDGER_TABLES, "ledger_chain_head"]
    assert _grants(tables) == {
        "subledger_posting": {"SELECT", "INSERT"},
        "subledger_posting_seal": {"SELECT", "INSERT"},
        "subledger_line": {"SELECT", "INSERT"},
        "ledger_chain_head": {"SELECT", "INSERT", "UPDATE"},
    }
    with identity_session(request_id="tests-dg-tst-21-subledger") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in SUBLEDGER_TABLES
        }
        triggers = {
            (str(table), str(name))
            for table, name in session.execute(_ENABLED_TRIGGERS, {"tables": tables})
        }
    assert columns == {table: set() for table in SUBLEDGER_TABLES}
    expected = {
        (table, f"tg_{table}__{purpose}")
        for table in SUBLEDGER_TABLES
        for purpose in ("immutable", "truncate")
    }
    assert triggers == expected | {
        ("subledger_posting", "tg_subledger_posting__sealed"),
        ("subledger_posting_seal", "tg_subledger_posting_seal__insert"),
        ("subledger_line", "tg_subledger_line__insert"),
        ("subledger_line", "tg_subledger_line__period_guard"),
    }


@pytest.mark.control("CTL-047")
def test_ctl_047_subledger_line_update_denied(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # CTL-047 (REQ-JE-006): an UPDATE or DELETE of a committed subledger line fails as erev_app,
    # and the line is unchanged.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        rows = insert_ledger_rows(session, tenant_id)
    debit = rows.lines[0]
    target = and_(
        subledger_line.c.period_end_date == debit["period_end_date"],
        subledger_line.c.id == debit["id"],
    )
    columns = (
        subledger_line.c.amount_txn,
        subledger_line.c.amount_functional,
        subledger_line.c.account_role,
        subledger_line.c.dr_cr,
    )
    with tenant_session(context, read_only=True) as session:
        before = tuple(session.execute(select(*columns).where(target)).one())
    outcomes: list[str | None] = []
    with tenant_session(context) as session:
        for statement in (
            update(subledger_line).where(target).values(amount_txn=Decimal("11.00")),
            delete(subledger_line).where(target),
        ):
            savepoint = session.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                session.execute(statement)
            savepoint.rollback()
            outcomes.append(getattr(excinfo.value.orig, "sqlstate", None))
    assert outcomes == ["42501", "42501"]
    with tenant_session(context, read_only=True) as session:
        after = tuple(session.execute(select(*columns).where(target)).one())
    assert after == before == (Decimal("10.0000"), Decimal("10.0000"), "CONTRACT_LIABILITY", "D")


JOURNAL_TABLES = (
    "manual_adjustment",
    "journal_run",
    "journal_batch",
    "journal_entry",
    "journal_line",
    "posting_ack",
)
JOURNAL_IM_A_TABLES = ("journal_entry", "journal_line", "posting_ack")
CLOSE_TABLES = (
    "close_run",
    "close_checklist_template",
    "close_checklist_item",
    "period_lock",
    "lock_snapshot",
    "reconciliation",
    "reconciliation_item",
    "signoff",
)
CLOSE_IM_A_TABLES = ("period_lock", "lock_snapshot", "signoff")
IM_A_TABLES = (*JOURNAL_IM_A_TABLES, *CLOSE_IM_A_TABLES)


def test_dg_tst_21_journal_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 (CLO-1): journal entries, lines and posting acknowledgements are IM-A (SELECT,
    # INSERT) with the DB-01 row and statement triggers; manual adjustments, runs and batches are
    # IM-S with UPDATE of their listed columns, the DB-01 delete and truncate triggers and DB-03.
    # DB-07 guards lines, DB-15 and DB-16 batches, and DB-16 runs.
    tables = list(JOURNAL_TABLES)
    assert _grants(tables) == {table: {"SELECT", "INSERT"} for table in tables}
    with identity_session(request_id="tests-dg-tst-21-journal") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in tables
        }
        triggers = {
            (str(table), str(name))
            for table, name in session.execute(_ENABLED_TRIGGERS, {"tables": tables})
        }
    assert columns == {
        "manual_adjustment": {
            "kind",
            "obligation_id",
            "period_id",
            "effective_date",
            "payload",
            "amount_functional_abs",
            "currency",
            "reason_code",
            "memo",
            "impact_preview_file_id",
            "content_sha256",
            "status",
            "approval_request_id",
            "applied_event_id",
            "subledger_posting_id",
            "is_deferred_past_lock",
        }
        | _SC_M_COLUMNS,
        "journal_run": {
            "state",
            "approval_request_id",
            "approved_at",
            "exported_at",
            "acknowledged_at",
            "cancelled_at",
        }
        | _SC_M_COLUMNS,
        "journal_batch": {
            "state",
            "export_file_id",
            "export_sha256",
            "outbox_message_id",
            "attempt_count",
            "last_error",
            "exported_at",
            "acknowledged_at",
        }
        | _SC_M_COLUMNS,
        "journal_entry": set(),
        "journal_line": set(),
        "posting_ack": set(),
    }
    expected = {
        (table, f"tg_{table}__{purpose}")
        for table in tables
        for purpose in ("immutable", "truncate")
    }
    assert triggers == expected | {
        ("manual_adjustment", "tg_manual_adjustment__transition"),
        ("journal_run", "tg_journal_run__transition"),
        ("journal_run", "tg_journal_run__coverage"),
        ("journal_run", "tg_journal_run__je_sequence"),
        # 04 DB-07 rev 1.205 (revision 0104; item JR-CLOSED-PERIOD-GUARD-1)
        ("journal_run", "tg_journal_run__period_guard"),
        ("journal_batch", "tg_journal_batch__transition"),
        ("journal_batch", "tg_journal_batch__approve"),
        ("journal_batch", "tg_journal_batch__approve_at_commit"),
        ("journal_batch", "tg_journal_batch__sandbox"),
        ("journal_line", "tg_journal_line__period_guard"),
        # 04 DB-16 rev 1.205 (revision 0104; supervisor ruling R-112 (b) (6))
        ("journal_line", "tg_journal_line__batch_draft"),
    }


def test_dg_tst_21_close_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 (CLO-2): close runs, reconciliations and their items are IM-S (SELECT, INSERT and
    # UPDATE of their listed columns) with the DB-01 delete and truncate triggers and DB-03;
    # checklist templates and items are IM-M (SELECT, INSERT, UPDATE; no DELETE) with the DB-02
    # touch trigger, the system-row rule of templates and the DB-03 pairs of items; locks, snapshots
    # and sign-offs are IM-A with DB-01, and sign-offs carry DB-10.
    tables = list(CLOSE_TABLES)
    append_only = {"SELECT", "INSERT"}
    assert _grants(tables) == {
        "close_run": append_only,
        "close_checklist_template": append_only | {"UPDATE"},
        "close_checklist_item": append_only | {"UPDATE"},
        "period_lock": append_only,
        "lock_snapshot": append_only,
        "reconciliation": append_only,
        "reconciliation_item": append_only,
        "signoff": append_only,
    }
    status_tables = ("close_run", "reconciliation", "reconciliation_item")
    with identity_session(request_id="tests-dg-tst-21-close") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in status_tables
        }
        triggers = {
            (str(table), str(name))
            for table, name in session.execute(_ENABLED_TRIGGERS, {"tables": tables})
        }
    assert columns == {
        "close_run": {
            "status",
            "current_step_code",
            "steps",
            "counts",
            "started_at",
            "finished_at",
            # 0127: what the first period-end step read, each written once while the run is
            # RUNNING (04 T-CLS-01 rev 1.291; item CLO-RATE-AFTER-RUN-1)
            "rates_read",
            "registry_read",
        }
        | _SC_M_COLUMNS,
        "reconciliation": {
            "status",
            "totals",
            "variance_count",
            "unexplained_other_amount",
            "report_run_id",
            "certified_at",
            "period_lock_id",  # 0059: GRANT UPDATE (period_lock_id), set-once (04 T-CLS-06 IM-S)
            # 0095: the trial-balance attachment, set-once (04 T-CLS-06 rev 1.121; ruling R-54 (a))
            "source_file_id",
            "sync_run_id",
        }
        | _SC_M_COLUMNS,
        "reconciliation_item": {"explanation", "resolved_at", "resolved_by", "resolved_by_kind"}
        | _SC_M_COLUMNS,
    }
    guarded = (*status_tables, *CLOSE_IM_A_TABLES)
    expected = {
        (table, f"tg_{table}__{purpose}")
        for table in guarded
        for purpose in ("immutable", "truncate")
    }
    assert triggers == expected | {
        ("close_run", "tg_close_run__transition"),
        ("close_checklist_template", "tg_close_checklist_template__touch"),
        ("close_checklist_template", "tg_close_checklist_template__system"),
        ("close_checklist_item", "tg_close_checklist_item__touch"),
        ("close_checklist_item", "tg_close_checklist_item__transition"),
        ("reconciliation", "tg_reconciliation__transition"),
        ("reconciliation_item", "tg_reconciliation_item__transition"),
        ("signoff", "tg_signoff__separation"),
    }


REPORT_TABLES = ("report_definition", "report_run", "disclosure_snapshot", "evidence_pack")


def test_dg_tst_21_report_grants(test_database: TestDatabase) -> None:
    # 04 §14.2 (RPS-1): erev_app only reads the global report catalogue (IM-A, RLS-NONE-G); report
    # runs and evidence packs are IM-S (SELECT, INSERT and UPDATE of their listed columns) with the
    # DB-01 delete and truncate triggers and DB-03; disclosure snapshots are IM-A with DB-01.
    tables = list(REPORT_TABLES)
    append_only = {"SELECT", "INSERT"}
    assert _grants(tables) == {
        "report_definition": {"SELECT"},
        "report_run": append_only,
        "disclosure_snapshot": append_only,
        "evidence_pack": append_only,
    }
    status_tables = ("report_run", "evidence_pack")
    with identity_session(request_id="tests-dg-tst-21-report") as session:
        columns = {
            table: {str(name) for name in session.scalars(_UPDATE_COLUMNS, {"table": table})}
            for table in status_tables
        }
        triggers = {
            (str(table), str(name))
            for table, name in session.execute(_ENABLED_TRIGGERS, {"tables": tables})
        }
    assert columns == {
        "report_run": {
            "status",
            "output_file_id",
            "output_sha256",
            "manifest_file_id",
            "row_count",
            "control_totals",
            "tie_out_results",
            "ledger_heads",
            "child_report_run_ids",
            "disclosure_snapshot_ids",
            "source_binding",  # 0065 (F-RPS frps3b; 04 T-RPT-02 rev 1.55): bound once at SUCCEEDED
            "started_at",
            "finished_at",
            "problem",
        }
        | _SC_M_COLUMNS,
        "evidence_pack": {"status", "manifest", "manifest_sha256", "file_id", "report_run_ids"}
        | _SC_M_COLUMNS,
    }
    expected = {
        (table, f"tg_{table}__{purpose}")
        for table in REPORT_TABLES
        for purpose in ("immutable", "truncate")
    }
    assert triggers == expected | {
        ("report_run", "tg_report_run__transition"),
        ("evidence_pack", "tg_evidence_pack__transition"),
    }


def _owner_failure(connection: Connection, statement: Executable) -> str:
    """Message of an owner statement that must fail; only its savepoint rolls back."""
    savepoint = connection.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        connection.execute(statement)
    savepoint.rollback()
    return str(getattr(getattr(excinfo.value.orig, "diag", None), "message_primary", "") or "")


def test_im_a_tables_reject_mutation(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DG-TST-21 (CLO-1, CLO-2): erev_app holds no UPDATE, DELETE or TRUNCATE on journal_entry,
    # journal_line, posting_ack, period_lock, lock_snapshot and signoff (42501), and erev_owner
    # without a data-fix ticket meets DB-01 (EREV-IMM-001). The unlisted journal_batch.external_id
    # is not granted to erev_app (42501), and for erev_owner the DB-03 trigger refuses it
    # (EREV-TRN-001).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with identity_session(request_id="tests-im-a-signer") as session:
        signer_id = insert_app_user(session)
    with tenant_session(context) as session:
        rows = insert_journal_rows(session, tenant_id)
        ack = posting_ack_values(tenant_id, batch_id=rows.batch["id"])
        session.execute(insert(posting_ack).values(**ack))
        parts = insert_close_parts(session, tenant_id)
        lock = period_lock_values(tenant_id, parts=parts)
        session.execute(insert(period_lock).values(**lock))
        snapshot = lock_snapshot_values(tenant_id, period_lock_id=lock["id"], file_id=parts.file_id)
        session.execute(insert(lock_snapshot).values(**snapshot))
        signed = signoff_values(
            tenant_id,
            subject_id=lock["id"],
            signer_id=signer_id,
            subject_type="period_lock",
            role="CONTROLLER",
        )
        session.execute(insert(signoff).values(**signed))
    ids = {
        "journal_entry": rows.entries[0]["id"],
        "journal_line": rows.lines[0]["id"],
        "posting_ack": ack["id"],
        "period_lock": lock["id"],
        "lock_snapshot": snapshot["id"],
        "signoff": signed["id"],
    }

    truncates = {
        "journal_entry": text("TRUNCATE erev.journal_entry"),
        "journal_line": text("TRUNCATE erev.journal_line"),
        "posting_ack": text("TRUNCATE erev.posting_ack"),
        "period_lock": text("TRUNCATE erev.period_lock"),
        "lock_snapshot": text("TRUNCATE erev.lock_snapshot"),
        "signoff": text("TRUNCATE erev.signoff"),
    }

    def statements(name: str) -> tuple[Executable, Executable, Executable]:
        table = metadata.tables[f"erev.{name}"]
        row = table.c.id == ids[name]
        # A sign-off has no SC-C columns; its statement stands in.
        tamper = {"statement": "Tampered"} if name == "signoff" else {"created_by_kind": "SYSTEM"}
        return (
            update(table).where(row).values(**tamper),
            delete(table).where(row),
            truncates[name],
        )

    external = (
        update(journal_batch)
        .where(journal_batch.c.id == rows.batch["id"])
        .values(external_id="erev:tampered")
    )
    outcomes: dict[str, list[str | None]] = {}
    with tenant_session(context) as session:
        for name in (*IM_A_TABLES, "journal_batch"):
            for statement in statements(name) if name != "journal_batch" else (external,):
                savepoint = session.begin_nested()
                with pytest.raises(exc.DBAPIError) as excinfo:
                    session.execute(statement)
                savepoint.rollback()
                sqlstate = getattr(excinfo.value.orig, "sqlstate", None)
                outcomes.setdefault(name, []).append(sqlstate)
    assert outcomes == {
        **{name: ["42501", "42501", "42501"] for name in IM_A_TABLES},
        "journal_batch": ["42501"],
    }

    # erev_owner holds every privilege; FORCE RLS names no owner policy, hence NO FORCE inside the
    # rolled-back transaction (SPEC-Q-129).
    messages: list[str] = []
    with committed_db.owner_engine.connect() as connection:
        connection.begin()
        try:
            for name in (*IM_A_TABLES, "journal_batch"):
                connection.exec_driver_sql(f"ALTER TABLE erev.{name} NO FORCE ROW LEVEL SECURITY")
            for name in IM_A_TABLES:
                update_row, delete_row, _ = statements(name)
                messages.append(_owner_failure(connection, update_row))
                messages.append(_owner_failure(connection, delete_row))
            messages.append(_owner_failure(connection, external))
        finally:
            connection.rollback()
    assert messages == [
        *(
            f"EREV-IMM-001: {verb} on erev.{table} is not permitted; the table is append-only"
            for table in IM_A_TABLES
            for verb in ("UPDATE", "DELETE")
        ),
        "EREV-TRN-001: columns external_id of erev.journal_batch cannot change",
    ]


SOURCE_TABLES = (
    "source_record",
    "source_order",
    "source_order_line",
    "source_invoice",
    "source_invoice_line",
    "source_usage",
    "source_payment",
    "source_match",
    "contract_source_link",  # T-CON-02, IM-A (BUILD_SPEC DIN-4)
)


def test_source_record_append_only(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-01 (DIN-2; DG-TST-21): the eight T-SRC tables are IM-A. erev_app holds SELECT and INSERT
    # only, so UPDATE, DELETE and TRUNCATE of a stored source_record fail (42501); erev_owner meets
    # the DB-01 row trigger (EREV-IMM-001), and every table carries the row and statement triggers.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    row = source_record_values(tenant_id)
    with tenant_session(context) as session:
        session.execute(insert(source_record).values(**row))
    target = source_record.c.id == row["id"]
    outcomes: list[str | None] = []
    with tenant_session(context) as session:
        for statement in (
            update(source_record).where(target).values(external_version="2"),
            delete(source_record).where(target),
            text("TRUNCATE erev.source_record"),
        ):
            savepoint = session.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                session.execute(statement)
            savepoint.rollback()
            outcomes.append(getattr(excinfo.value.orig, "sqlstate", None))
    assert outcomes == ["42501", "42501", "42501"]
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(
            select(source_record.c.external_version).where(target)
        ).scalar_one()
    assert stored == "1"

    assert _grants(list(SOURCE_TABLES)) == {table: {"SELECT", "INSERT"} for table in SOURCE_TABLES}
    with identity_session(request_id="tests-source-record-triggers") as session:
        triggers = {
            (str(table), str(name))
            for table, name in session.execute(_ENABLED_TRIGGERS, {"tables": list(SOURCE_TABLES)})
        }
    assert triggers == {
        (table, f"tg_{table}__{purpose}")
        for table in SOURCE_TABLES
        for purpose in ("immutable", "truncate")
    }
    messages: list[str] = []
    with committed_db.owner_engine.connect() as connection:
        connection.begin()
        try:
            connection.exec_driver_sql("ALTER TABLE erev.source_record NO FORCE ROW LEVEL SECURITY")
            messages.append(
                _owner_failure(
                    connection, update(source_record).where(target).values(external_version="2")
                )
            )
        finally:
            connection.rollback()
    assert messages == [
        "EREV-IMM-001: UPDATE on erev.source_record is not permitted; the table is append-only"
    ]


def test_contract_rows_never_deleted(committed_db: TestDatabase, keyring: KeyRing) -> None:
    """REQ-CON-015, D-01 (BUILD_SPEC CTR-11; CTL-046): ``erev_app`` holds no DELETE on ``contract``
    or ``contract_event``, so a DELETE as the application role fails with 42501 — a void reverses,
    it never removes."""
    grants = _grants(["contract", "contract_event"])
    assert all("DELETE" not in privileges for privileges in grants.values()), grants
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        for table in (contract, contract_event):
            savepoint = session.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                session.execute(delete(table))
            savepoint.rollback()
            assert getattr(excinfo.value.orig, "sqlstate", None) == "42501", table.name
