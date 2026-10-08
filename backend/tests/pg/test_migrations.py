"""Migration round trip DG-MIG-05 (dev-guide §6.5, §9.4 DG-TST-25; BUILD_SPEC FND-6)."""

from __future__ import annotations

import io
from typing import Any

import pytest
from alembic import command
from erev_api.cli import app
from erev_api.db import migration_ops as ops
from erev_api.db.lint import lint_as_app
from erev_api.enums import ApprovalSubjectType
from sqlalchemy import Connection, exc, text
from support.db import TestDatabase, alembic_config, fresh_head
from typer.testing import CliRunner

pytestmark = pytest.mark.pg

# Catalogue of schema erev: names, definitions and grants, never OIDs (DG-MIG-05).
SNAPSHOT_QUERIES: dict[str, str] = {
    "schema": "SELECT nspname, coalesce(nspacl::text, '') FROM pg_namespace WHERE nspname = 'erev'",
    "relations": """
        SELECT c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity,
               coalesce(c.reloptions::text, ''), coalesce(c.relacl::text, ''),
               coalesce(obj_description(c.oid, 'pg_class'), '')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'erev' ORDER BY 1""",
    "columns": """
        SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
               coalesce(pg_get_expr(d.adbin, d.adrelid), ''), coalesce(a.attacl::text, '')
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE n.nspname = 'erev' AND a.attnum > 0 AND NOT a.attisdropped ORDER BY 1, 2""",
    "types": """
        SELECT t.typname, t.typtype, format_type(t.typbasetype, t.typtypmod),
               coalesce((SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
                         FROM pg_enum e WHERE e.enumtypid = t.oid), '')
        FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'erev' ORDER BY 1""",
    "constraints": """
        SELECT con.conname, coalesce(c.relname, ty.typname, ''), pg_get_constraintdef(con.oid)
        FROM pg_constraint con JOIN pg_namespace n ON n.oid = con.connamespace
        LEFT JOIN pg_class c ON c.oid = con.conrelid LEFT JOIN pg_type ty ON ty.oid = con.contypid
        WHERE n.nspname = 'erev' ORDER BY 1, 2""",
    "indexes": "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'erev' ORDER BY 1",
    "policies": """
        SELECT policyname, tablename, permissive, roles::text, cmd, coalesce(qual, ''),
               coalesce(with_check, '')
        FROM pg_policies WHERE schemaname = 'erev' ORDER BY 1, 2""",
    "triggers": """
        SELECT t.tgname, c.relname, pg_get_triggerdef(t.oid), t.tgenabled
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'erev' AND NOT t.tgisinternal ORDER BY 1, 2""",
    "functions": """
        SELECT p.oid::regprocedure::text, pg_get_functiondef(p.oid), coalesce(p.proacl::text, '')
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'erev' ORDER BY 1""",
    "sequences": """
        SELECT sequencename, data_type::text, start_value, increment_by
        FROM pg_sequences WHERE schemaname = 'erev' ORDER BY 1""",
}


def catalogue_snapshot(connection: Connection) -> dict[str, list[tuple[Any, ...]]]:
    return {
        name: [tuple(row) for row in connection.execute(text(query))]
        for name, query in SNAPSHOT_QUERIES.items()
    }


# DG-MIG-09: the Procrastinate objects of public, with their grants, by name.
_PROCRASTINATE_PUBLIC = text(
    "SELECT o.kind, o.name FROM ("
    "SELECT 'relation' AS kind, c.relname::text || ':' || c.relkind::text || ':' || "
    "coalesce(c.relacl::text, '') AS name FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND starts_with(c.relname, 'procrastinate_') "
    "UNION ALL SELECT 'function', p.proname::text || '(' || "
    "pg_get_function_identity_arguments(p.oid) "
    "|| '):' || coalesce(p.proacl::text, '') FROM pg_proc p "
    "JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'public' AND starts_with(p.proname, 'procrastinate_') "
    "UNION ALL SELECT 'type', t.typname::text FROM pg_type t "
    "JOIN pg_namespace n ON n.oid = t.typnamespace "
    "WHERE n.nspname = 'public' AND starts_with(t.typname, 'procrastinate_')"
    ") o ORDER BY 1, 2"
)


def _procrastinate_objects(connection: Connection) -> list[tuple[str, str]]:
    return [(str(kind), str(name)) for kind, name in connection.execute(_PROCRASTINATE_PUBLIC)]


def test_single_head() -> None:
    output = io.StringIO()
    command.heads(alembic_config(stdout=output))
    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    # 0055 on 0054 (lane P5, 04 §18 rule 9; assigned at slice 1c); 0056 on 0055 (lane F-LMG, LMG-1);
    # 0057 on 0056 (lane P4 SOP-1 T-PLT-39 control_execution; assigned at merge prep 2026-09-20);
    # 0058 on 0057 (lane F-ADM, E-79 INVITATION_LOOKUP_FAILED; assigned at merge prep 2026-09-20).
    # 0059 on 0058 (lane F-CLO CLO-6 T-CLS-06 period_lock_id write-once; assigned at merge prep
    # 2026-09-20).
    # 0061 on 0060 (lane P2, T-PLT-06 key attribution; landed after ENG-C1b's 0060).
    # 0062 / 0063 on P2's 0061 (lane F-SNP SNP-1: T-PLT-34 tenant_snapshot; the
    # platform.snapshot_retention_families seed; assigned at merge prep 2026-09-20).
    # 0064 on 0063 (lane ENG-C6 T-SL-12 subledger_line_event; assigned at merge prep 2026-09-20;
    # landed after F-SNP's 0062 / 0063).
    # 0065 (F-RPS report_run.source_binding) on ENG-C6 0064.
    # 0066 (lane F-SNP, T-PLT-47 registry_parameter_correction; 04 1.59) on F-RPS 0065; it adds no
    # erev function (IM-A class triggers reuse tg_forbid_mutation), so the count below stays 78.
    # 0067 on 0066 (lane F-LMG, T-MIG-04 / T-MIG-05 durable capture; number assigned 2026-09-20;
    # re-pointed from 0065 at the single main merge after F-SNP landed, main fe8e85df, 2026-09-21).
    # 0068 on 0067 (lane F-CTR, CTR-17 T-CON-06 modification + E-23 / E-24 / E-25; 04 1.70;
    # D-98 140, number assigned 2026-09-21); it adds one erev function,
    # tg_modification__transition. 0069 on 0068 (lane F-CTR, D-98 candidate 143 GUARD-TRN-1)
    # REPLACES six transition functions: no new function. 0070 on 0069 (lane F-CTR, D-98 candidate
    # 143 AMENDMENT 1): the contract spec admits (DRAFT, ACTIVE) — the stored move of the approved /
    # SYSTEM activation — and tg_contract__transition is re-rendered: no new function.
    # 0071 on 0070 (lane F-LMG, 0071_migration_ssp_replay_subject: one enum value added, no
    # function). 0072 on 0071 (lane F-ADM DIN-12, 04 1.77 / 1.81: E-72 sync_run_status, T-INT-01
    # integration_connection, T-INT-02 sync_run, T-INT-04 external_id_map; re-pointed from 0069 to
    # 0071 at the pre-READY merge of main 109bf240, 2026-09-22). F-LMG-MIG-PIN-1: the stale "0070"
    # head pin left by 0071 is corrected here; P8's 0073 re-pins after.
    # 0073 on 0072 (lane FIX-D2, the code step of P8's PRV-07 a line, 04 1.86 / 1.96; number
    # assigned by the supervisor): the DB-13 UPDATE grant of app_user.email / external_id and the
    # DB-19 tg_app_user__erasure_guard.
    # 0095 on 0073 (lane F-CLO-B, CLO-16; supervisor ruling R-54 (a); 04 1.121; number assigned
    # by the supervisor — 0082 and 0084 to 0094 are other lanes' and are re-pointed at their
    # merges): E-14 RECONCILIATION_GENERATE, the write-once T-CLS-06 source_file_id /
    # sync_run_id and the retired DB-03 pair REOPENED → DRAFT; tg_reconciliation__transition is
    # re-rendered: no new function.
    # 0084 on 0095 (lane FIX-D2 slice 3 rework, supervisor rulings R-31 / R-40 (b), (c); 04 1.113;
    # number assigned by the supervisor; re-pointed from 0073 to main's head 0095 at the merge of
    # main 80284cfe, supervisor ruling R-68 (e)): the two DB-07 period guards read the period's
    # state row FOR SHARE, and T-CLS-04 period_lock.cutoff_known_at with
    # ck_period_lock__cutoff_known_at. The two guard bodies are replaced: no new function.
    # 0087 on 0084 (lane SECFIX-IMP, SC-2: T-IMP-02 named_entity_ids, 04 1.107; number assigned
    # in the package; built on 0072, the head of the lane branch, and re-pointed to main's head
    # 0084 by the supervisor at the merge, ruling R-68 (e)). It REPLACES
    # tg_import_upload__transition: no new function (the count below stays).
    # 0092 on 0087 (lane SECFIX-PLT, the platform security package; rulings R-48 and R-50 (b);
    # 04 1.108; number assigned in the package; re-pointed to main's head at each merge of main,
    # supervisor ruling R-68 (e): from 0095 to 0084 at 808e45fd, to 0087 at 87796c55): E-79
    # MFA_ENROLMENT_STARTED and RECOVERY_CODES_REGENERATED; T-PLT-03 email_domains and T-PLT-02
    # identity_provider_subject with its check, its unique index and its column grant (P3-13) —
    # no new function.
    # 0093 on 0092 (lane F-CLO-A, BUILD_SPEC CLO-12; supervisor ruling R-51 (b); 04 1.120; number
    # assigned by the supervisor; down_revision is main's head at each of this lane's merges of
    # main, ruling R-68 (e): 0087 at 9dbd20e3, 0092 at cfb292bd, and re-pointed again when
    # another lane lands first): the DB-03 pairs of T-SL-05 — tg_manual_adjustment__transition
    # re-rendered with the T-CON-06 pairs — no new function.
    # 0085 on 0093 (lane SECFIX-CLO, security finding SC-7; 04 rev 1.106 DB-16:
    # tg_journal_run__coverage without the mode; number assigned by the supervisor 2026-09-30;
    # built on 0072, the head of the lane branch, and re-pointed to head 0093 by the supervisor
    # at the merge, ruling R-68 (e)). It REPLACES the body of tg_journal_run__coverage: no new
    # function.
    # 0091 on 0085 (lane F-SNP, BUILD_SPEC SNP-4; 04 1.125; security finding SF-1, ruling R-33):
    # the DB-15 tg_webhook_endpoint__sandbox. The number is the register's; the chain follows
    # merge order (ruling R-68 (e)): built on 0095, re-pointed to main's head at each merge of
    # main — to 0087 at afd86782, to 0092 at a7d63e81, to 0085 at d0c5eceb.
    # 0098 on 0091 (lane FIX-D2, item CLO-LOCK-OPEN-REDIRTY-1; supervisor rulings R-101 (a) and
    # R-106 (a); 04 1.164; number assigned by the supervisor; down_revision is main's head at
    # each of this lane's merges of main, ruling R-68 (e): 0093 at 094f7174, 0085 at d0c5eceb,
    # and re-pointed to head 0091 by the supervisor at the merge): E-14 PERIOD_OPEN_REDIRTY —
    # one enum value added — and T-PLT-27 subject_type `period_state`: ck_job__subject_type
    # replaced; no function.
    # 0102 on 0098 (lane SECFIX-IMP, rulings R-98 and R-109 (a): T-IMP-02 uploader_scopes, 04
    # 1.147; number assigned by the supervisor; built on 0087, the head of the lane's tree, and
    # re-pointed to main's head 0098 by the supervisor at the merge, ruling R-68 (e)). One
    # column: no function, no grant.
    # 0101 on 0102 (lane API-GAPS, item AUD-API-GAPS-1; supervisor rulings R-108 and R-114 (c);
    # 04 rev 1.154 T-PLT-48: the link table audit_event_contract with its class IM-A, its policy
    # RLS-T and its grants; number assigned by the supervisor; down_revision is main's head at
    # each of this lane's merges of main, ruling R-68 (e): 0085 at ada3f6f0, 0098 at b4e293c5,
    # and re-pointed to head 0102 by the supervisor at the merge). One table: no function, no
    # enum, and no column or index on audit_event.
    # 0107 on 0101 (lane SECFIX-CLO part 2, item CLO-CANCEL-CLOSE-REOPENED-1; 04 rev 1.170
    # T-REF-07; number assigned by the supervisor; built on 0085, re-pointed to 0102 at the
    # lane's merge of main 92e65393 and to main's head 0101 by the supervisor at the merge,
    # ruling R-68 (e)): the pair closing → reopened. It REPLACES the bodies of
    # tg_period_state__update and tg_period_state_transition__pair and the three T-REF-07
    # checks of period_state_transition: no new function.
    # 0105 on 0107 (lane FIX-D2, item CLO-LOCK-LEGACY-1; supervisor rulings R-97 (2), R-112 (e)
    # and R-114 (d); 04 1.155; number assigned by the supervisor; down_revision is main's head at
    # each of this lane's merges of main, ruling R-68 (e): 0098 at b4e293c5, 0101 at 6101ac17,
    # and re-pointed to head 0107 by the supervisor at the merge): DB-07 —
    # tg_subledger_line__period_guard reads the primary book's state row first for a LEGACY
    # line. It REPLACES the body: no new function.
    # 0099 on 0105 (lane SECFIX-PLT, the lead's finding 5; supervisor ruling R-48 (e); 04 1.151;
    # number assigned by the supervisor, register index 60; down_revision is main's head at each
    # of this lane's merges of main, ruling R-68 (e): 0092 when written, 0093 at 094f7174, 0098
    # at b4e293c5, and re-pointed to head 0105 by the supervisor at the merge): T-PLT-06
    # ix_security_event__email_chain — an index only, no new function.
    # 0113 on 0099 (lane SECFIX-CLO part 2, item REOPEN-CLOSING-FLAG-1; supervisor ruling
    # R-117 (c); 04 rev 1.184 DB-07, T-SL-04, T-REF-07; number assigned by the supervisor;
    # down_revision is main's head at each of this lane's merges of main, ruling R-68 (e):
    # 0107 at 9b5e1e4c, 0099 at 2f97b1ac): is_post_reopen read from the period's lock record,
    # on the body of 0105 (the LEGACY read), and a missing reason refused. It REPLACES the
    # body of tg_subledger_line__period_guard and the check
    # ck_period_state_transition__reason_code: no new function.
    # 0115 on 0113 (lane ENG-FX, item PRODUCT-CODE-FREEZE-1; supervisor ruling R-112 (i); 04 rev
    # 1.160 DB-05; number assigned by the supervisor; down_revision is main's head at this lane's
    # merge of main 76fe6140, ruling R-68 (e)): the DB-05 tg_product__code_frozen — the code of
    # a product that a contract line, an SSP entry or a mapping rule references. One function.
    # 0086 on 0115 (lane SECFIX-APR, supervisor ruling R-25; 04 1.104: T-PLT-17 approval_request
    # entity_ids / is_all_entities and ck_approval_request__entity_scope; number assigned by the
    # supervisor in the lane package, re-pointed to main's head at each merge of main — 0095 at
    # 80284cfe, 0087 at 9dbd20e3, 0092 at 0ac0e8da, 0085 at 2cbd093d, 0099 at
    # 20531d3b — and to head 0115 by the supervisor at the merge; the chain follows merge order,
    # not number order: ruling R-68 (e)): two columns and one CHECK, no function.
    # 0112 on 0086 (lane API-GAPS, item PERF-RLS-INDEX-1; supervisor ruling R-116; 04 rev 1.181
    # NC-20: fifteen index keys in the order the row-level-security policy can use and six
    # status indexes replaced by five partial and three plain ones; number assigned by the
    # supervisor; down_revision was main's head at the lane's merge of main 42d8f48f, 0115, and
    # is main's head 0086 since the supervisor's merge, ruling R-68 (e)). Index definitions
    # only: no table, column, type, function or grant.
    # 0108 on 0112 (lane F-CLO-A, item JRN-FAILED-CANCEL-1; supervisor ruling R-112 (c); 04 rev
    # 1.159 E-34 `failed` → `cancelled`; number assigned by the supervisor; down_revision was
    # main's head at each of this lane's merges of main, ruling R-68 (e) — 0101 at 855af940,
    # 0099 at 20531d3b — and is main's head 0112 since the supervisor's merge). It REPLACES the
    # bodies of tg_journal_run__transition and tg_journal_batch__transition: no new function.
    # 0111 on 0108 (lane F-CLO-B, item CLO-GATE-RUN-1; supervisor rulings R-114 (b) and R-116
    # (e); 04 1.172; number assigned by the supervisor; down_revision was main's head at each of
    # this lane's merges of main, ruling R-68 (e) — 0102 at 92e65393, 0113 at da2ce39e, 0086 at
    # 965ed2bd — and is main's head 0108 since the supervisor's merge): T-CLS-02
    # gate_check_code CLOSE_RUN_COMPLETED — ck_close_checklist_template__gate_check_code
    # replaced — and T-CON-03 period_ends_open with its check and column grant; it REPLACES the
    # body of tg_combination_group__transition: no new function (the count below stays).
    # 0094 on 0111 (lane SECFIX-IMP part B, SC-6: E-08 EVIDENCE_SHRED, 04 1.142; rulings R-49
    # (a) and R-86; number assigned by the supervisor, register index 51; down_revision was
    # main's head 0086 when the lane ported it and is main's head 0111 since the supervisor's
    # merge, ruling R-68 (e)): an enum value only — no function.
    # 0103 on 0094 (lane SECFIX-PLT, the slice of ruling R-111; 04 1.189; the number and the
    # table id T-PLT-49 assigned by the supervisor, register index 98; down_revision is main's
    # head at each of this lane's merges of main, ruling R-68 (e): 0099 at 20531d3b, 0113 at
    # afab0c2a, 0086 at 965ed2bd, 0112 at 9b881b70, 0094 at 4a3a6a4c): T-PLT-49
    # file_upload (IM-A, RLS-T), E-79 MFA_CHALLENGE_PASSED and MFA_PENDING_DENIED, T-PLT-21
    # ck_approval_delegation__ends and the DB-20 tg_app_user__identity_provider — one function.
    # 0114 on 0103 (lane SECFIX-ACT, register index 97; supervisor rulings R-118 (e) and
    # R-119 (e); 04 rev 1.210; number assigned by the supervisor; built on 0085, the head of the
    # lane branch, and re-pointed to main's head 0103 by the supervisor at the merge, ruling
    # R-68 (e)): T-CON-06 classification with its check and column grant, the new predicate of
    # ux_modification__reference, T-CON-13 modification_id with its foreign key and index,
    # T-CON-12 ix_estimate__contract, E-12 VOIDED with ck_estimate_version__status and the DB-03
    # pair DRAFT → VOIDED — tg_estimate_version__transition is re-rendered: no new function.
    # 0104 on 0114 (lane F-CLO-A, item JR-CLOSED-PERIOD-GUARD-1; supervisor rulings R-97 (7) and
    # R-112 (b) (6); 04 rev 1.205 DB-07 and DB-16; number assigned by the supervisor;
    # down_revision is main's head at each of this lane's merges of main, ruling R-68 (e) —
    # 0111 at 4050c50d, 0094 at ac5e337b, 0114 at a978ba29): the DB-07
    # tg_journal_run__period_guard and the DB-16 tg_journal_line__batch_draft. Two functions.
    # 0117 on 0104 (lane SECFIX-ACT, register index 173; the supervisor's rulings of 2026-10-01,
    # item EST-ONE-OPEN-VERSION-1; 04 rev 1.241 T-CON-13; number assigned by the supervisor;
    # down_revision is main's head at the commit the lane's patch was made against, ruling
    # R-68 (e) — 0114 at 3cecdb44, 0104 at afb04675): the partial unique index
    # ux_estimate_version__open, one DRAFT or SUBMITTED version of an element. An index only:
    # no table, column, type, function or grant.
    # 0120 on 0117 (lane SECFIX-PLT, item FILE-SHRED-DURABLE-ORDER-1; the supervisor's ruling on
    # finding B4 of the review of the EVIDENCE_SHRED merge; 04 rev 1.237; number assigned by the
    # supervisor, register index 166; written on 0104, the head of the lane branch, and
    # re-pointed to 0117, the integration branch's head, by the supervisor at the merge, ruling
    # R-68 (e)): T-PLT-29 shred_completed_at with its check and column grant,
    # ix_file_object__shred_incomplete, and the DB-03 tg_file_object__transition re-rendered —
    # no new function.
    # 0118 on 0120 (lane SECFIX-ACT, register index 174; the supervisor's ruling of 2026-10-01
    # on question J1 (a), the discard of a judgement record; 04 rev 1.242 E-57, T-CON-19; number
    # assigned by the supervisor; written on the lane's 0117 and re-pointed to 0120, the
    # integration branch's head, by the supervisor at the merge, ruling R-68 (e)): E-57 VOIDED
    # and the DB-03 pair DRAFT → VOIDED — tg_judgement_record__transition is re-rendered: no new
    # function.
    # 0119 on 0118 (lane F-CLO-B, CLO-17 role basis and the late billing document's column;
    # supervisor rulings R-68 (a), R-69, R-74; 04 rev 1.253; number assigned by the supervisor,
    # register index 196; written on 0104, main's head at the lane's last merge of main, and
    # re-pointed to 0118, the integration branch's head, by the supervisor at the merge, ruling
    # R-68 (e)): T-CLS-07
    # origin_period_id and account_role with their key and check, and item_kind NOT_STATED with
    # its check — no new function.
    # 0121 on 0119 (lane F-CLO-B, item REC-GEN-LOCK-1; the supervisor's rulings of 2026-10-01
    # 21:41 and 22:52, replacing the lock of R-68 (b); 04 rev 1.259; number assigned by the
    # supervisor, register index 211; built on the lane's own 0119): T-CLS-06 ledger_chain_seq,
    # source_documents_read and subledger_documents_read — three nullable columns, no check and
    # no function.
    # 0127 on 0121 (lane F-CLO-B, item CLO-RATE-AFTER-RUN-1; the supervisor's ruling of 2026-10-02
    # 08:56; 04 rev 1.291; number assigned by the supervisor, register index 272; built on the
    # lane's own 0121): T-CLS-01 rates_read and registry_read — two nullable columns with their
    # column grants, and tg_close_run__transition() re-rendered so that each is written once.
    # 0122 on 0127 (lane API-GAPS, ACCT backlog row 4, register index 203; supervisor rulings
    # R-108 (2) and R-105 (2) and the supervisor's ruling of 2026-10-02; 04 rev 1.270 T-IMP-02;
    # number assigned by the supervisor; written on 0104, the head of the lane's branch at its
    # merge of main 51f9bbbe, and re-pointed to 0127, the integration branch's head, by the
    # supervisor at the merge, ruling R-68 (e)): the DB-03 pair DIFFING → INVALID of
    # import_upload, by which a dry run whose job ended FAILED ends its upload — it REPLACES the
    # body of tg_import_upload__transition: no new function (the count below stays).
    # 0110 on 0122 (lane SECFIX-APR, supervisor ruling R-38 (iii); 04 1.168: E-103
    # api_client_status gains PENDING_APPROVAL and REJECTED; number assigned by the supervisor,
    # register index 77; written on 0104, moved to main's head 0117 at the lane's merge of main
    # a101c4c0, and re-pointed to 0122, the integration branch's head, by the supervisor at the
    # merge, ruling R-68 (e); ALTER TYPE … ADD VALUE in a revision of its own): no function.
    # 0123 on 0110 (lane SECFIX-APR, item SSP-ENTITY-SCOPE-1; supervisor ruling R-28, row N-29
    # of the ruled repairs; 04 rev 1.277 T-REF-32; number assigned by the supervisor, register
    # index 234; built on the lane's own 0110): the column ssp_calculator_run.entity_ids with
    # ck_ssp_calculator_run__entity_ids. No function: the DB-03 function of the table refuses
    # a change to any column it does not name.
    # 0125 on 0123 (lane FIX-D2, item ACT-FLAGS-1, register index 260; the supervisor's rulings
    # of 2026-10-02; 04 rev 1.287 T-CON-01; number assigned by the supervisor; written on 0117,
    # main's head at the lane's merge of main a101c4c0, and re-pointed to 0123, the integration
    # branch's head, by the supervisor at the merge, ruling R-68 (e)): T-CON-01
    # acceptance_clause and side_letter, two nullable boolean columns. No table, type, function,
    # trigger, index or grant.
    # 0126 on 0125 (lane F-RPS-REG, register index 266, item COMBINATION-PROPOSAL-DISCARD-1;
    # the supervisor's rulings of 2026-10-02; 04 rev 1.289 E-95, T-CON-03; number assigned
    # by the supervisor; written on 0121, the head of main d6e7d0f8, and re-pointed to 0125,
    # the integration branch's head, by the supervisor at the merge, ruling R-68 (e)): E-95
    # VOIDED and the DB-03 pair PROPOSED → VOIDED — tg_combination_group__transition is
    # re-rendered: no new function.
    # 0130 on 0126 (lane F-CLO-B, item CLO-WAIVER-COVERS-LATER-1; the supervisor's ruling of
    # 2026-10-02 17:32; 04 rev 1.305; number assigned by the supervisor, register index 283;
    # written on the lane's own 0127, re-pointed to 0125 by the lane at its merge of the
    # integration branch's tip 0a626426, and to 0126, that branch's head, by the supervisor at
    # the merge, ruling R-68 (e)): tg_close_checklist_item__transition() re-rendered with two
    # pairs more, WAIVED to FAILED and WAIVED to NOT_STARTED; no column, grant or object.
    # 0129 on 0130 (lane SECFIX-PLT, item COMPUTE-BEHIND-CUTOFF-1; the supervisor's order of
    # 2026-10-02 19:47 on lane ENG-FX's line; 04 rev 1.302 T-CON-07; number assigned by the
    # supervisor, register index 285; written on 0123, the integration branch's head at the
    # lane's build, and re-pointed to 0130, that branch's head, by the supervisor at the merge,
    # ruling R-68 (e)): the column contract_computation.cutoff_at — one nullable column; no
    # check, no index, no grant and no function.
    # 0124 on 0129 (lane ENG-FX, item ENG-COST-READBACK-1, register index 248; supervisor ruling
    # R-11 as amended on 2026-10-02; 04 rev 1.282 T-SL-04 and §18 rule 17; number assigned by the
    # supervisor; written on 0104, main's head at the lane's merge of main, and re-pointed to
    # 0129, the integration branch's head, by the supervisor at the merge, ruling R-68 (e)): the
    # column subject_key of subledger_line on the partitioned parent of 0040, and the refusal of
    # a table that holds a line (EREV-MIG-0124). No table, type, function, trigger, index or
    # grant.
    # 0128 on 0124 (lane ENG-FX, item FX-REPUBLISH-DIRTY-1; the supervisor's rulings of
    # 2026-10-02 on the lane's pre-build line; 04 rev 1.297; number assigned by the supervisor,
    # register index 277; written on 0122, the integration branch's head at the lane's build,
    # and put on 0124, that branch's head, when lane SECFIX-PLT ported the item onto its tip
    # 68863f956, ruling R-68 (e)): T-CON-03 dirty_trigger — one nullable column with its check
    # and column grant, and tg_combination_group__transition() re-rendered on 0126's body so
    # that the application may move it.
    # 0135: fresh manual close-task signatures after an approved reopen.
    # 0136: move the non-leakproof book enum behind the FX layer lookup keys.
    # 0137: persist tenant-bound reviewed judgement citations for error-correction reopens.
    # 0141: period-state references for durable refusal evidence.
    assert lines[0].split()[0] == "0141"


def test_upgrade_downgrade_upgrade(test_database: TestDatabase) -> None:
    # FLMG-WALK-RESET-1: DG-MIG-05's first two steps (reset schema, upgrade head) performed by the
    # walk itself — the descent must not meet rows earlier tests committed (DG-MIG-06)
    fresh_head()
    owner = test_database.owner_engine
    with owner.connect() as connection:
        first = catalogue_snapshot(connection)
    assert first["schema"][0][0] == "erev"
    assert {row[0] for row in first["types"]} >= {"money", "exact", "fx_rate", "tz_name"}
    # Five 0001 functions, the DB-05 tg_tenant__frozen of 0004, the DB-09 tg_audit_event__chain
    # of 0006, the DB-03 and DB-12 functions of role_assignment of 0007, the DB-03 function of
    # user_recovery_code of 0008, and of 0009 the DB-04 tg_config_version, the DB-12 function of
    # sod_rule and the DB-03 function of sod_exception, and of 0011 the DB-03 functions of
    # file_object and file_attachment and the DB-11 tg_file_attachment__void, of 0012 the DB-03
    # function of job, and of 0013 the DB-03 functions of approval_request, approval_step and
    # approval_delegation and the DB-10 tg_approval_decision__sod, of 0014 the DB-04
    # tg_config_child, of 0016 the DB-03 functions of notification and outbox_message, of 0021 the
    # DB-03 function of webhook_delivery, of 0022 the DB-12 functions of api_client scopes and
    # entity_ids, of 0023 the DB-03 function of support_grant, and of 0024 the DB-03 functions of
    # access_review_campaign and access_review_item and the DB-10 tg_access_review_item__separation,
    # and of 0025 the DB-09 tg_audit_chain_head__guard; 0026 replaces the body of tg_config_version;
    # 0027 adds the DB-05 tg_period__contiguous; 0028 adds the DB-12
    # tg_dimension_definition__custom_limit; 0029 adds the DB-07 tg_period_state__update and
    # tg_period_state_transition__pair and the DB-05 tg_period__frozen and
    # tg_fiscal_calendar__frozen, and replaces the bodies of the two DB-12 entity_ids functions;
    # 0030 attaches the existing DB-04 functions to fx_rate_set_version and fx_rate and adds none;
    # 0031 (customers and related-party groups) adds none; 0032 attaches the existing DB-04
    # functions to account_mapping_version and account_mapping_rule and adds none; 0033 (products
    # and bundle components) adds none; 0034 attaches the existing DB-04 functions to
    # ssp_book_version and ssp_entry and adds the DB-04 tg_ssp_range__config_child; 0035 replaces
    # the DB-04 trigger of ssp_book_version with the new tg_ssp_book_version__config_version and
    # adds the DB-05 tg_ssp_book__scope_frozen; 0036 (obligation templates) attaches the existing
    # DB-04 tg_config_version to pob_template_version and adds none; 0037 (SSP calculator) adds the
    # DB-03 tg_ssp_calculator_run__transition; 0038 (contracts and streams) adds the DB-03 functions
    # of combination_group, combination_group_member and event_submission, the DB-18
    # tg_contract__projection and the DB-08 tg_contract_event__insert; 0039 (versions, schedules and
    # traces) adds the DB-17 tg_contract_version__allocation; 0040 (subledger) adds the DB-06
    # tg_subledger_posting__sealed, tg_subledger_line__insert and tg_subledger_posting_seal__insert,
    # the DB-07 tg_subledger_line__period_guard and the DB-05 tg_legal_entity__frozen, and replaces
    # the body of tg_period__frozen; 0041 (exception items) adds none; 0042 (judgement records) adds
    # the DB-03 tg_judgement_record__transition and tg_contract__transition and the DB-10
    # tg_judgement_record__review; 0043 (contract holds) adds none; 0044 (import uploads) adds the
    # DB-03 tg_import_upload__transition; 0045 (policy overrides, CTR-15) adds the DB-03
    # tg_policy_override__transition; 0046 (journal tables, CLO-1) adds the DB-03 functions of
    # manual_adjustment, journal_run and journal_batch, the DB-16 tg_journal_run__coverage,
    # tg_journal_run__je_sequence and tg_journal_batch__approve, the DB-15
    # tg_journal_batch__sandbox and the DB-07 tg_journal_line__period_guard; 0047 (close tables,
    # CLO-2) adds the DB-03 functions of close_run, close_checklist_item, reconciliation and
    # reconciliation_item, the DB-10 tg_signoff__separation and tg_close_checklist_template__system;
    # 0048 (report tables, RPS-1) adds the DB-03 functions of report_run and evidence_pack;
    # 0049 (source store, DIN-2) and 0050 (contract source links, DIN-4) add none; 0051
    # (estimates, CTR-12) adds the DB-03 tg_estimate_version__transition; 0052 (mapping profiles,
    # DIN-10) and 0053 (T-CON-09 functional payable and incentive asset, D-87 L6-5-Q-18) add none;
    # 0054 (DB-17 V1 in scope, D-88 L7-5-Q-6) replaces the body of tg_contract_version__allocation;
    # 0055 (lane P5, engine_release.validation_level + E-125..E-130 types) adds none; 0056 (lane
    # F-LMG, T-MIG-01..03) adds tg_migration_batch__transition; 0057 (SOP-1 control_execution,
    # T-PLT-39) adds none.
    # 0061 (security_event key attribution, T-PLT-06 rev 1.42, lane P2) adds two columns and two
    # checks and no function — 76 at main fa87c357. 0062 (lane F-SNP SNP-1, T-PLT-34
    # tenant_snapshot) adds two: the DB-03 tg_tenant_snapshot__transition and the DB-15
    # tg_tenant_snapshot__target; 0063 (the platform.snapshot_retention_families seed) adds none.
    # 0064 (lane ENG-C6, T-SL-12 subledger_line_event) adds none: IM-A and RLS-T attach the existing
    # 0001 tg_forbid_mutation and the RLS policies; no DB-03 transition, no new function.
    assert (
        len(first["functions"]) == 88  # 0065 REPLACES tg_report_run__transition (frps3b): +0
    )  # 76 + tg_tenant_snapshot__transition + __target (0062); 0064 +0; 0067 +0 (IM-A / RLS-T
    # attach the existing tg_forbid_mutation and policies; no DB-03 transition, no new function);
    # 0068 +1 (lane F-CTR CTR-17: the DB-03 tg_modification__transition; IM-S and RLS-TE attach
    # existing functions and policies) = 79; 0069 REPLACES six transition bodies (GUARD-TRN-1): +0;
    # 0070 re-renders tg_contract__transition: +0; 0071 adds an enum value only: +0; 0072 (lane
    # F-ADM DIN-12) +3 — the DB-15 tg_integration_connection__sandbox and the DB-03
    # tg_sync_run__transition / tg_external_id_map__transition (each create_trigger defines its
    # function) = 82 (re-derived at the pre-READY merge of main 109bf240, 2026-09-22); 0073 (lane
    # FIX-D2, 04 1.86) +1 — the DB-19 tg_app_user__erasure_guard = 83; 0084 (lane FIX-D2, 04
    # 1.113) REPLACES the two DB-07 period guard bodies and adds a column and a check: +0; 0093
    # (lane F-CLO-A CLO-12) re-renders tg_manual_adjustment__transition: +0.
    # 0085 (lane SECFIX-CLO, SC-7) REPLACES the body of tg_journal_run__coverage: +0.
    # 0095 (lane F-CLO-B) and 0087 (lane SECFIX-IMP) re-render a transition function each and
    # 0092 (lane SECFIX-PLT) adds none: +0; 0091 (lane F-SNP SNP-4, 04 1.125) +1 — the DB-15
    # tg_webhook_endpoint__sandbox = 84.
    # 0101 (lane API-GAPS, T-PLT-48 audit_event_contract) creates a table whose class IM-A
    # attaches the existing tg_forbid_mutation: +0.
    # 0107 (lane SECFIX-CLO part 2) REPLACES the two DB-07 period state bodies and three checks: +0.
    # 0115 (lane ENG-FX, PRODUCT-CODE-FREEZE-1, 04 1.160) +1 — the DB-05 tg_product__code_frozen
    # = 85.
    # 0112 (lane API-GAPS, PERF-RLS-INDEX-1) drops and creates indexes only: +0.
    # 0108 (lane F-CLO-A, item JRN-FAILED-CANCEL-1) re-renders tg_journal_run__transition and
    # tg_journal_batch__transition with E-34 `failed` → `cancelled`: +0.
    # 0103 (lane SECFIX-PLT, ruling R-111 (7)) +1 — the DB-20 tg_app_user__identity_provider = 86
    # (its table T-PLT-49 attaches the existing tg_forbid_mutation and policy).
    # 0114 (lane SECFIX-ACT, index 97) re-renders tg_estimate_version__transition: +0.
    # 0104 (lane F-CLO-A, item JR-CLOSED-PERIOD-GUARD-1, 04 1.205) +2 — the DB-07
    # tg_journal_run__period_guard and the DB-16 tg_journal_line__batch_draft = 88.
    # 0117 (lane SECFIX-ACT, index 173) creates the index ux_estimate_version__open only: +0.
    # 0120 (lane SECFIX-PLT, item FILE-SHRED-DURABLE-ORDER-1, 04 1.237) re-renders
    # tg_file_object__transition with the write-once shred_completed_at: +0.
    # 0118 (lane SECFIX-ACT, index 174) re-renders tg_judgement_record__transition: +0.
    # 0119 (lane F-CLO-B, CLO-17 role basis, index 196) adds two columns, a key and three checks:
    # +0.
    # 0121 (lane F-CLO-B, REC-GEN-LOCK-1, index 211) adds three columns: +0.
    # 0127 (lane F-CLO-B, CLO-RATE-AFTER-RUN-1, index 272) adds two columns and replaces the body
    # of tg_close_run__transition(): +0.
    # 0125 (lane FIX-D2, item ACT-FLAGS-1) adds two columns of T-CON-01 only: +0.
    # 0126 (lane F-RPS-REG, index 266) re-renders tg_combination_group__transition: +0.
    # 0130 (lane F-CLO-B, CLO-WAIVER-COVERS-LATER-1, index 283) replaces the body of
    # tg_close_checklist_item__transition(): +0.
    # 0129 (lane SECFIX-PLT, COMPUTE-BEHIND-CUTOFF-1, index 285) adds one column: +0.
    # 0124 (lane ENG-FX, item ENG-COST-READBACK-1) adds the column subject_key of
    # subledger_line and no function: +0.
    # 0128 (lane ENG-FX, FX-REPUBLISH-DIRTY-1, index 277) adds one column with its check and
    # replaces the body of tg_combination_group__transition(): +0.
    with owner.connect() as connection:
        first_public = _procrastinate_objects(connection)
    kinds = {kind for kind, _ in first_public}
    assert kinds == {"function", "relation", "type"}
    assert any(name.startswith("procrastinate_jobs:r:") for _, name in first_public)

    command.downgrade(alembic_config(), "base")
    with owner.connect() as connection:
        remaining = connection.execute(
            text("SELECT count(*) FROM pg_namespace WHERE nspname = 'erev'")
        ).scalar_one()
        public_remaining = _procrastinate_objects(connection)
    assert remaining == 0
    assert public_remaining == []

    command.upgrade(alembic_config(), "head")
    # Recreated types get new OIDs, so plans psycopg prepared on pooled connections before the
    # round trip fail with "cached plan must not change result type"; later tests need new pools.
    test_database.app_engine.dispose()
    owner.dispose()
    with owner.connect() as connection:
        second = catalogue_snapshot(connection)
        second_public = _procrastinate_objects(connection)
    assert second == first
    assert second_public == first_public
    assert lint_as_app(request_id="tests-round-trip") == []


def test_step1_report_filter_migration_round_trip(test_database: TestDatabase) -> None:
    """A report's stored filter must admit the same subjects as the application."""
    fresh_head()
    query = text(
        "SELECT parameters_schema #> '{properties,subject_types,items,enum}' "
        "FROM erev.report_definition WHERE code = 'approvals_register' AND version = 1"
    )
    owner = test_database.owner_engine
    with owner.connect() as connection:
        subjects = connection.execute(query).scalar_one()
    assert subjects == [subject.value for subject in ApprovalSubjectType]

    command.downgrade(alembic_config(), "0138")
    test_database.app_engine.dispose()
    owner.dispose()
    with owner.connect() as connection:
        previous = connection.execute(query).scalar_one()
    assert previous == [subject for subject in subjects if subject != "STEP1_EVENT"]

    command.upgrade(alembic_config(), "head")
    test_database.app_engine.dispose()
    owner.dispose()
    with owner.connect() as connection:
        assert connection.execute(query).scalar_one() == subjects
        assert (
            connection.execute(
                text(
                    "SELECT tgenabled FROM pg_trigger WHERE "
                    "tgrelid = 'erev.report_definition'::regclass "
                    "AND tgname = 'tg_report_definition__immutable'"
                )
            ).scalar_one()
            == "O"
        )


def test_lint_after_upgrade(test_database: TestDatabase, log_stream: io.StringIO) -> None:
    # ``log_stream``: `erev db lint` installs the logging pipeline on the runner's stderr (05
    # OPR-20 rev 1.53); the fixture puts the process's own back afterwards.
    result = CliRunner().invoke(app, ["db", "lint"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[-1] == "DB-14 lint: 0 findings"


def test_dg_mig_06_remove_enum_value_fails_when_used(test_database: TestDatabase) -> None:
    with test_database.owner_engine.connect() as connection, ops.bound_to(connection):
        connection.begin()
        try:
            ops.create_enum("probe_kind", ["ALPHA", "BETA", "GAMMA"])
            connection.exec_driver_sql(
                "CREATE TABLE erev.probe_enum (k erev.probe_kind NOT NULL DEFAULT 'GAMMA')"
            )
            connection.exec_driver_sql("INSERT INTO erev.probe_enum (k) VALUES ('ALPHA')")
            ops.remove_enum_value("probe_kind", "BETA")
            labels = connection.execute(
                text("SELECT enum_range(NULL::erev.probe_kind)::text")
            ).scalar_one()
            assert labels == "{ALPHA,GAMMA}"
            default = connection.execute(
                text(
                    "SELECT column_default FROM information_schema.columns "
                    "WHERE table_schema = 'erev' AND table_name = 'probe_enum'"
                )
            ).scalar_one()
            # Printed unqualified because connections use search_path erev, public (NC-01).
            assert default == "'GAMMA'::probe_kind"
            savepoint = connection.begin_nested()
            with pytest.raises(exc.DBAPIError):
                ops.remove_enum_value("probe_kind", "ALPHA")
            savepoint.rollback()
        finally:
            connection.rollback()


_PROBE_DEFINITIONS = text(
    "SELECT k.conname, pg_get_constraintdef(k.oid) FROM pg_constraint k "
    "WHERE k.conrelid = 'erev.probe_enum'::regclass AND k.contype = 'c' "
    "UNION ALL SELECT i.relname, pg_get_indexdef(x.indexrelid) FROM pg_index x "
    "JOIN pg_class i ON i.oid = x.indexrelid WHERE x.indrelid = 'erev.probe_enum'::regclass "
    "ORDER BY 1"
)


def test_dg_mig_06_remove_enum_value_carries_typed_checks_and_indexes(
    test_database: TestDatabase,
) -> None:
    """DG-MIG-06 (dev-guide rev 1.171; revision 0114's downgrade is the first to need it): E-12
    lost a label while a status check and two partial indexes compared a column with its
    constants. A check constraint and a partial index over constants of the enum survive the
    removal of an unused label — dropped before the type is replaced, re-created from the
    definition the catalogue printed: both read as before, and the index still keeps its rows
    unique over a constant of the type that stays. Before, the conversion of the column
    failed: the stored expressions kept constants of the renamed type ("operator does not
    exist: probe_kind = probe_kind__old")."""
    with test_database.owner_engine.connect() as connection, ops.bound_to(connection):
        connection.begin()
        try:
            ops.create_enum("probe_kind", ["ALPHA", "BETA", "GAMMA"])
            connection.exec_driver_sql(
                "CREATE TABLE erev.probe_enum (id integer NOT NULL, "
                "k erev.probe_kind NOT NULL DEFAULT 'GAMMA', "
                "CONSTRAINT ck_probe_enum__k CHECK (k IN ('ALPHA', 'GAMMA')))"
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX ux_probe_enum__alpha ON erev.probe_enum (id) WHERE k = 'ALPHA'"
            )
            connection.exec_driver_sql("INSERT INTO erev.probe_enum (id, k) VALUES (1, 'ALPHA')")
            before = [tuple(row) for row in connection.execute(_PROBE_DEFINITIONS)]
            assert [name for name, _ in before] == ["ck_probe_enum__k", "ux_probe_enum__alpha"]
            assert all("probe_kind" in definition for _, definition in before)

            ops.remove_enum_value("probe_kind", "BETA")

            labels = connection.execute(
                text("SELECT enum_range(NULL::erev.probe_kind)::text")
            ).scalar_one()
            assert labels == "{ALPHA,GAMMA}"
            assert [tuple(row) for row in connection.execute(_PROBE_DEFINITIONS)] == before
            # the re-created index and check act on the type that stays
            savepoint = connection.begin_nested()
            with pytest.raises(exc.IntegrityError):
                connection.exec_driver_sql(
                    "INSERT INTO erev.probe_enum (id, k) VALUES (1, 'ALPHA')"
                )
            savepoint.rollback()
            connection.exec_driver_sql("INSERT INTO erev.probe_enum (id, k) VALUES (1, 'GAMMA')")
        finally:
            connection.rollback()
