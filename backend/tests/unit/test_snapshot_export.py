"""Export-time filters and the SBX-05 determinism comparison of a tenant snapshot (F-SNP
preparation; SBX-03 "referenced by copied rows", SBX-05; T-PLT-34). No database."""

from __future__ import annotations

import dataclasses
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals.subjects import SUBJECTS
from erev_api.db.tables import metadata
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform import snapshot_export as sx
from erev_api.domain.platform.snapshot_dataset import LOAD_ORDER
from erev_engine import compute
from erev_engine.bundle import InputBundle, OutputBundle
from support.billing_lines import checkpoint_bundle

# A stand-in PENDING entry for the fail-closed branches (every real file-attachment subject table
# is copied since CTR-17 landed `modification`; D-98 140).
_PENDING_STAND_IN = sd.PendingTable(
    "manual_adjustment", sd.SnapshotClass.COPIED, sd.Category.FACT, "TEST", "stand-in for the test"
)

DATA_MODEL = Path(__file__).resolve().parents[3] / "docs/04-DATA_MODEL.md"

KNOWN_AT = datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC)


def _u(n: int) -> UUID:
    return UUID(int=n)


def test_reference_columns_are_pinned_to_the_model() -> None:
    """Every copied table that names an approval request or a file, by column name (drift guard:
    a new reference column changes this map and forces a decision)."""
    columns = sx.reference_columns()
    assert dict(columns[sx.APPROVAL_REFERENCE]) == {
        name: "approval_request_id"
        for name in (
            "account_mapping_version",
            "combination_group",
            "contract_event",
            "estimate_version",
            "event_submission",
            "fx_rate_set_version",
            "import_mapping_profile",
            "import_upload",
            "judgement_record",
            "manual_adjustment",
            "modification",
            "period_lock",
            "period_state_transition",
            "pob_template_version",
            "policy_override",
            "registry_version",
            "role_assignment",
            "rule_set_version",
            "sod_exception",
            "sod_rule",
            "ssp_book_version",
            "migration_batch",  # T-MIG-01 (main 065e7f65)
        )
    }
    # The approval's own rows (request, step, decision) are not references to it.
    assert not {"approval_request", "approval_step", "approval_decision"} & set(
        columns[sx.APPROVAL_REFERENCE]
    )
    assert dict(columns[sx.FILE_REFERENCE]) == {
        "account_mapping_version": "impact_simulation_file_id",
        "approval_request": "impact_preview_file_id",
        "file_attachment": "file_object_id",
        "import_upload": "diff_file_id|file_object_id",
        "manual_adjustment": "impact_preview_file_id",
        "modification": "impact_preview_file_id",  # T-CON-06 (CTR-17; D-98 140)
        "period_lock": "diff_report_file_id",
        "registry_version": "impact_simulation_file_id",
        "rule_set_version": "impact_simulation_file_id",
        "ssp_calculator_run": "result_file_id",  # ruling Q-1: the calculator tables are copied,
        "migration_batch": "source_file_id",  # T-MIG-01: the legacy database file (main 065e7f65)
    }


def test_referenced_ids_collects_uuids_and_refuses_other_types() -> None:
    columns = sx.reference_columns()[sx.APPROVAL_REFERENCE]
    rows = {
        "contract_event": [{"approval_request_id": _u(1)}, {"approval_request_id": None}],
        "judgement_record": [{"approval_request_id": _u(2)}],
        "customer": [{"approval_request_id": _u(9)}],  # not a reference table: ignored
    }
    assert sx.referenced_ids(rows, columns) == frozenset({_u(1), _u(2)})
    with pytest.raises(TypeError, match="UUID"):
        sx.referenced_ids({"contract_event": [{"approval_request_id": "x"}]}, columns)
    files = sx.reference_columns()[sx.FILE_REFERENCE]
    rows = {"import_upload": [{"file_object_id": _u(3), "diff_file_id": _u(4)}]}
    assert sx.referenced_ids(rows, files) == frozenset({_u(3), _u(4)})


def test_filter_approvals_keeps_referenced_requests_with_their_steps_and_decisions() -> None:
    requests = [{"id": _u(1)}, {"id": _u(2)}]
    steps = [
        {"id": _u(11), "approval_request_id": _u(1)},
        {"id": _u(12), "approval_request_id": _u(2)},
    ]
    decisions = [
        {"id": _u(21), "approval_request_id": _u(1)},
        {"id": _u(22), "approval_request_id": _u(2)},
    ]
    kept = sx.filter_approvals(requests, steps, decisions, frozenset({_u(1)}))
    assert [r["id"] for r in kept.requests] == [_u(1)]
    assert [s["id"] for s in kept.steps] == [_u(11)]
    assert [d["id"] for d in kept.decisions] == [_u(21)]
    assert sx.filter_approvals(requests, steps, decisions, frozenset()) == sx.Approvals((), (), ())
    with pytest.raises(ValueError, match="unknown request"):
        sx.filter_approvals(
            requests, [{"id": _u(13), "approval_request_id": _u(3)}], [], frozenset()
        )


def test_filter_files_keeps_referenced_rows_and_refuses_a_missing_reference() -> None:
    files = [{"id": _u(3)}, {"id": _u(4)}, {"id": _u(5)}]
    assert [f["id"] for f in sx.filter_files(files, frozenset({_u(4)}))] == [_u(4)]
    assert sx.filter_files(files, frozenset()) == ()
    with pytest.raises(ValueError, match="missing for referenced ids"):
        sx.filter_files(files, frozenset({_u(4), _u(7)}))


def _version(
    group: int, book: str, no: int, at: datetime, sha: str, input_sha: str = "in"
) -> sx.SourceVersion:
    return sx.SourceVersion(_u(group), book, no, at, sha, input_sha)


def test_latest_as_of_picks_the_highest_version_not_after_known_at() -> None:
    versions = [
        _version(1, "ASC606", 1, KNOWN_AT - timedelta(days=2), "a1"),
        _version(1, "ASC606", 2, KNOWN_AT - timedelta(days=1), "a2"),
        _version(1, "ASC606", 3, KNOWN_AT + timedelta(seconds=1), "a3"),  # after the snapshot
        _version(1, "IFRS15", 1, KNOWN_AT, "i1"),
    ]
    latest = sx.latest_as_of(versions, KNOWN_AT)
    assert {k: v.output_sha256 for k, v in latest.items()} == {
        (_u(1), "ASC606"): "a2",
        (_u(1), "IFRS15"): "i1",
    }


def test_compare_determinism_counts_mismatches_and_one_sided_pairs() -> None:
    source = [
        _version(1, "ASC606", 2, KNOWN_AT, "same"),
        _version(2, "ASC606", 1, KNOWN_AT, "src"),
        _version(3, "ASC606", 1, KNOWN_AT, "only-source"),
    ]
    sandbox = {
        (_u(1), "ASC606"): "same",
        (_u(2), "ASC606"): "recomputed",
        (_u(4), "ASC606"): "only-sandbox",
    }
    report = sx.compare_determinism(source, sandbox, KNOWN_AT)
    assert report.compared == 4
    assert report.derived_mismatches == 3
    assert report.mismatches == (
        sx.Mismatch(_u(2), "ASC606", "src", "recomputed"),
        sx.Mismatch(_u(3), "ASC606", "only-source", None),
        sx.Mismatch(_u(4), "ASC606", None, "only-sandbox"),
    )
    clean = sx.compare_determinism(source[:1], {(_u(1), "ASC606"): "same"}, KNOWN_AT)
    assert (clean.compared, clean.derived_mismatches, clean.mismatches) == (1, 0, ())


# --- SBX-05 rev 1.34 (supervisor ruling R-9): the comparable hash ---------------------------------

# A computable stored-style bundle: the answer-key checkpoint the engine's upgrade tests load
# (``tests/engine/test_upgrade.py``); ``bundles.minimal_contract`` stops at PRODUCT_UNMAPPED.
_COMPUTABLE = ("mod", "MOD-LEGACY-PROS-GT12", "end-june-after-prospective")
_GROUP = _u(7)


def _as_loaded(bundle: InputBundle) -> InputBundle:
    """``bundle`` as a sandbox load presents the same facts to the engine (05 SBX-04): every event
    re-stamped by DB-08 — a later ``recorded_at``, a new ``record_seq``, the ORDER kept — the
    trigger ``MIGRATION`` and a later ``known_at``."""
    shift = timedelta(days=90)
    return dataclasses.replace(
        bundle,
        trigger="MIGRATION",
        known_at=bundle.known_at + shift,
        events=tuple(
            dataclasses.replace(
                event, record_seq=event.record_seq + 5000, recorded_at=event.recorded_at + shift
            )
            for event in bundle.events
        ),
    )


def _expected(output: OutputBundle) -> dict[tuple[UUID, str], sx.SourceVersion]:
    """The source's latest versions of ``_GROUP`` as its computation ``output`` stored them."""
    return {
        (_GROUP, book.book_code): sx.SourceVersion(
            _GROUP, book.book_code, 1, KNOWN_AT, output.sha256(), output.input_sha256
        )
        for book in output.books
        if book.contract_version is not None
    }


def _with_one_more_minor_unit(output: OutputBundle) -> OutputBundle:
    """``output`` with ONE schedule line's amount one minor unit higher — nothing else touched."""
    book = output.books[0]
    line = book.schedules[0]
    schedules = (dataclasses.replace(line, amount=line.amount + 1), *book.schedules[1:])
    return dataclasses.replace(
        output, books=(dataclasses.replace(book, schedules=schedules), *output.books[1:])
    )


def test_comparable_hashes_equal_the_source_hash_when_only_the_input_hash_differs() -> None:
    """The same facts computed in the source and again as a load re-stamps them: the input hashes
    differ (CV-25 covers the arrival metadata and the trigger), so the RAW output hashes differ
    too (CV-26 (a): ``input_sha256`` is a member of the output) — and the sandbox's output under
    the source's input hash is the source's stored hash, for every book with a version."""
    source = compute(checkpoint_bundle(*_COMPUTABLE))
    sandbox = compute(_as_loaded(checkpoint_bundle(*_COMPUTABLE)))
    assert sandbox.input_sha256 != source.input_sha256
    assert sandbox.sha256() != source.sha256()  # why SBX-05 cannot compare the raw hashes
    expected = _expected(source)
    assert expected  # the bundle computes a version (a vacuous equality would prove nothing)
    hashes = sx.comparable_hashes(_GROUP, sandbox, expected)
    assert dict(hashes) == {key: source.sha256() for key in expected}
    report = sx.compare_determinism(expected.values(), hashes, KNOWN_AT)
    assert (report.compared, report.derived_mismatches) == (len(expected), 0)


def test_comparable_hashes_do_not_hide_a_differing_member() -> None:
    """The check can fail: ONE schedule amount off by one minor unit, or another engine stamp —
    anything but the input hash — leaves the comparable hash unequal, and the pair is a mismatch
    carrying both hashes."""
    source = compute(checkpoint_bundle(*_COMPUTABLE))
    sandbox = compute(_as_loaded(checkpoint_bundle(*_COMPUTABLE)))
    expected = _expected(source)
    (key,) = expected  # one book
    faulty = sx.comparable_hashes(_GROUP, _with_one_more_minor_unit(sandbox), expected)
    assert faulty[key] != source.sha256()
    report = sx.compare_determinism(expected.values(), faulty, KNOWN_AT)
    assert report.mismatches == (sx.Mismatch(key[0], key[1], source.sha256(), faulty[key]),)
    restamped = dataclasses.replace(sandbox, engine_version=sandbox.engine_version + "+next")
    assert sx.comparable_hashes(_GROUP, restamped, expected)[key] != source.sha256()


def test_comparable_hashes_keep_the_own_hash_without_a_source_version() -> None:
    """A book the source has no version for as of ``known_at``: nothing to substitute, the
    output's own hash stands and the one-sided pair is a mismatch; a book without a contract
    version yields no pair at all (no T-CON-08 row is written for it)."""
    sandbox = compute(_as_loaded(checkpoint_bundle(*_COMPUTABLE)))
    book_code = sandbox.books[0].book_code
    hashes = sx.comparable_hashes(_GROUP, sandbox, {})
    assert dict(hashes) == {(_GROUP, book_code): sandbox.sha256()}
    report = sx.compare_determinism((), hashes, KNOWN_AT)
    assert report.mismatches == (sx.Mismatch(_GROUP, book_code, None, sandbox.sha256()),)
    unversioned = dataclasses.replace(
        sandbox,
        books=tuple(dataclasses.replace(book, contract_version=None) for book in sandbox.books),
    )
    assert dict(sx.comparable_hashes(_GROUP, unversioned, {})) == {}


# --- ruling Q-2: the reference rules as data; the subject rule ------------------------------------


def test_approval_rules_are_data_per_approval_bearing_table() -> None:
    rules = sx.approval_rules()
    column_rules = [r for r in rules if r.kind == "column"]
    subject_rules = [r for r in rules if r.kind == "subject"]
    # 21 + modification (CTR-17; D-98 140)
    assert len(column_rules) == 22 and all(r.column == "approval_request_id" for r in column_rules)
    assert {r.table for r in column_rules} == set(sx.reference_columns()[sx.APPROVAL_REFERENCE])
    # Every registered subject spec whose table is copied is a subject rule; none points elsewhere.
    expected = {
        (spec.table, subject_type.value)
        for subject_type, spec in SUBJECTS.items()
        if spec.table in LOAD_ORDER
    }
    assert {(r.table, r.subject_type) for r in subject_rules} == expected
    # 20 before main fa87c357; + F-CLO's period lock / permanent-lock / reopen subjects and F-CTR's
    # CONTRACT_VOID, minus none (the expected set above is computed from SUBJECTS).
    # + MODIFICATION (CTR-17; D-98 140)
    # + MIGRATION_SSP_REPLAY on migration_batch (F-LMG PG-7b; 04 rev 1.72)
    # + MANUAL_ADJUSTMENT on manual_adjustment (F-CLO-A CLO-12; the subject left PENDING_SUBJECTS)
    # + EVIDENCE_SHRED on file_object (lane SECFIX-IMP; rulings R-49 (a), R-86; 04 rev 1.142)
    # + STEP1_EVENT on event_submission (B1-13 dated assessment approval).
    assert len(subject_rules) == 28
    not_copied = {spec.table for spec in SUBJECTS.values()} - set(LOAD_ORDER)
    assert not_copied == {"support_grant", "exception_item", "journal_run"}  # never copied subjects
    assert all(r.table in LOAD_ORDER for r in rules)


def test_subject_references_keep_requests_whose_subject_row_is_copied() -> None:
    requests = [
        {"id": _u(1), "subject_type": "CONTRACT_ACTIVATION", "subject_id": _u(101)},
        {"id": _u(2), "subject_type": "CONTRACT_ACTIVATION", "subject_id": _u(102)},  # not copied
        {"id": _u(3), "subject_type": "JOURNAL_RUN", "subject_id": _u(301)},  # never copied
        {"id": _u(4), "subject_type": "JUDGEMENT_RECORD", "subject_id": _u(401)},
        {"id": _u(5), "subject_type": "STEP1_EVENT", "subject_id": _u(501)},
        {"id": _u(6), "subject_type": "STEP1_EVENT", "subject_id": _u(502)},  # not copied
    ]
    copied = {
        "contract": [_u(101)],
        "judgement_record": [_u(401)],
        "journal_run": [_u(301)],
        "event_submission": [_u(501)],
    }
    assert sx.subject_references(requests, copied) == frozenset({_u(1), _u(4), _u(5)})
    assert sx.subject_references(requests, {}) == frozenset()
    # Union with the column rule is the export-time set (SBX-03 read both ways).
    column = sx.referenced_ids(
        {"judgement_record": [{"approval_request_id": _u(9)}]},
        sx.reference_columns()[sx.APPROVAL_REFERENCE],
    )
    assert column | sx.subject_references(requests, copied) == frozenset(
        {_u(1), _u(4), _u(5), _u(9)}
    )


def test_subject_references_fail_closed_on_pending_or_unknown_subject_types() -> None:
    # AI_PROPOSAL_ACCEPTANCE is still PENDING (AIX); MODIFICATION registered with CTR-17 (D-98 140).
    with pytest.raises(ValueError, match="AI_PROPOSAL_ACCEPTANCE has no SubjectSpec yet"):
        sx.subject_references(
            [{"id": _u(1), "subject_type": "AI_PROPOSAL_ACCEPTANCE", "subject_id": _u(5)}], {}
        )
    with pytest.raises(ValueError, match="unknown subject type"):
        sx.subject_references(
            [{"id": _u(1), "subject_type": "NOT_A_SUBJECT", "subject_id": _u(5)}], {}
        )
    with pytest.raises(TypeError, match="subject_id is a UUID"):
        sx.subject_references(
            [{"id": _u(1), "subject_type": "CONTRACT_ACTIVATION", "subject_id": "x"}], {}
        )


def test_referenced_approvals_is_the_union_of_both_readings_without_a_status_filter() -> None:
    """Ruling D-98 candidate 26 on Q-2: column reading OR subject reading; rejected and superseded
    requests are kept and travel with every step and decision."""
    requests = [
        {
            "id": _u(1),
            "subject_type": "CONTRACT_ACTIVATION",
            "subject_id": _u(101),
            "status": "REJECTED",
        },
        {
            "id": _u(2),
            "subject_type": "JUDGEMENT_RECORD",
            "subject_id": _u(201),
            "status": "APPROVED",
        },
        {
            "id": _u(3),
            "subject_type": "JUDGEMENT_RECORD",
            "subject_id": _u(202),
            "status": "APPROVED",
        },
    ]
    rows = {"judgement_record": [{"id": _u(201), "approval_request_id": _u(3)}]}  # names 3, not 2
    copied = {"contract": [_u(101)], "judgement_record": [_u(201)]}
    referenced = sx.referenced_approvals(rows, requests, copied)
    assert referenced == frozenset(
        {_u(1), _u(2), _u(3)}
    )  # 1 rejected by subject, 2 subject, 3 column
    steps = [
        {"id": _u(11), "approval_request_id": _u(1)},
        {"id": _u(13), "approval_request_id": _u(3)},
    ]
    decisions = [{"id": _u(21), "approval_request_id": _u(1), "decision": "REJECT"}]
    kept = sx.filter_approvals(requests, steps, decisions, referenced)
    assert [r["id"] for r in kept.requests] == [_u(1), _u(2), _u(3)]
    assert [s["id"] for s in kept.steps] == [_u(11), _u(13)]
    assert [d["id"] for d in kept.decisions] == [_u(21)]


# --- Codex review of 1a41066: F-SNP-R2 (population and Iterable contract) -------------------------


def test_filter_approvals_refuses_a_missing_referenced_request_and_accepts_iterators() -> None:
    requests = [{"id": _u(1)}, {"id": _u(2)}]
    steps = [{"id": _u(11), "approval_request_id": _u(1)}]
    decisions = [{"id": _u(21), "approval_request_id": _u(1)}]
    with pytest.raises(ValueError, match="approval_request rows missing for referenced ids"):
        sx.filter_approvals(requests, steps, decisions, frozenset({_u(1), _u(7)}))
    kept = sx.filter_approvals(iter(requests), iter(steps), iter(decisions), frozenset({_u(1)}))
    assert [r["id"] for r in kept.requests] == [_u(1)]
    assert [s["id"] for s in kept.steps] == [_u(11)] and [d["id"] for d in kept.decisions] == [
        _u(21)
    ]
    # unrelated requests stay out; a step of an unknown request is still refused
    assert sx.filter_approvals(requests, [], [], frozenset({_u(2)})).requests == ({"id": _u(2)},)
    with pytest.raises(ValueError, match="unknown request"):
        sx.filter_approvals(
            requests, [{"id": _u(13), "approval_request_id": _u(3)}], [], frozenset()
        )


# --- Codex review of 1a41066: F-SNP-R3 (attachments follow copied subjects) -----------------------


def test_attachment_subjects_equal_the_t_plt_30_check_and_classify_once() -> None:
    text = DATA_MODEL.read_text(encoding="utf-8")
    section = text.split("### T-PLT-30 `file_attachment`", 1)[1].split("\n### ", 1)[0]
    literals = set(
        re.findall(
            r"'([a-z_]+)'", re.search(r"CHECK \(subject_type IN \(([^)]*)\)", section).group(1)
        )
    )
    assert set(sx.ATTACHMENT_SUBJECTS) == literals
    assert sx.ATTACHMENT_SUBJECTS["contract"] == "contract"
    assert sx.ATTACHMENT_SUBJECTS["reconciliation"] == "reconciliation"


def test_filter_attachments_keeps_copied_subjects_excludes_regenerated_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = {
        "id": _u(1),
        "file_object_id": _u(31),
        "subject_type": "contract",
        "subject_id": _u(101),
    }
    other = {
        "id": _u(2),
        "file_object_id": _u(32),
        "subject_type": "contract",
        "subject_id": _u(102),
    }
    recon = {
        "id": _u(3),
        "file_object_id": _u(33),
        "subject_type": "reconciliation",
        "subject_id": _u(301),
    }
    copied = {"contract": [_u(101)]}
    kept = sx.filter_attachments([contract, other, recon], copied)
    assert [a["id"] for a in kept] == [_u(1)]  # the copied contract keeps its attachment
    # the REGENERATED reconciliation subject and the uncopied contract lose theirs, so their files
    # are never referenced
    files = sx.reference_columns()[sx.FILE_REFERENCE]
    assert sx.referenced_ids({"file_attachment": kept}, files) == frozenset({_u(31)})
    # No file-attachment subject table is PENDING on this tree (modification landed with CTR-17), so
    # the fail-closed branch is exercised with a PENDING entry stood in for manual_adjustment.
    monkeypatch.setattr(sx, "PENDING", {**sx.PENDING, "manual_adjustment": _PENDING_STAND_IN})
    pending = {
        "id": _u(4),
        "file_object_id": _u(34),
        "subject_type": "manual_adjustment",
        "subject_id": _u(5),
    }
    with pytest.raises(ValueError, match="manual_adjustment is PENDING"):
        sx.filter_attachments([pending], copied)
    unknown = {
        "id": _u(5),
        "file_object_id": _u(35),
        "subject_type": "invoice",
        "subject_id": _u(6),
    }
    with pytest.raises(ValueError, match="unsupported file_attachment subject type"):
        sx.filter_attachments([unknown], copied)


# --- Codex retest of b00a7df: the export chain itself selects attachments and files -------------


def test_export_chain_selects_attachments_and_files_only_through_the_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The direct chain (rows → referenced ids → files) kept a REGENERATED subject's attachment and
    its file; select_export() runs filter_attachments before any file reference is read, refuses a
    PENDING subject, and returns the kept rows, approvals and files together."""
    contract_att = {
        "id": _u(1),
        "file_object_id": _u(31),
        "subject_type": "contract",
        "subject_id": _u(101),
    }
    recon_att = {
        "id": _u(3),
        "file_object_id": _u(33),
        "subject_type": "reconciliation",
        "subject_id": _u(301),
    }
    rows = {
        "contract": [{"id": _u(101)}],
        "file_attachment": [contract_att, recon_att],
        "judgement_record": [
            {
                "id": _u(201),
                "approval_request_id": _u(9),
                "subject_type": "contract",
                "subject_id": _u(101),
            }
        ],
    }
    requests = [
        {
            "id": _u(9),
            "subject_type": "JUDGEMENT_RECORD",
            "subject_id": _u(201),
            "impact_preview_file_id": _u(39),
        },
        {
            "id": _u(8),
            "subject_type": "CONTRACT_ACTIVATION",
            "subject_id": _u(999),
            "impact_preview_file_id": _u(38),
        },
    ]
    files = [{"id": _u(31)}, {"id": _u(33)}, {"id": _u(38)}, {"id": _u(39)}]
    copied = {"contract": [_u(101)], "judgement_record": [_u(201)]}
    # the direct chain without the selector keeps the reconciliation attachment's file (the defect)
    direct = sx.referenced_ids(rows, sx.reference_columns()[sx.FILE_REFERENCE])
    assert _u(33) in direct
    selection = sx.select_export(rows, requests, [], [], files, copied)
    assert [a["id"] for a in selection.rows["file_attachment"]] == [_u(1)]
    assert [r["id"] for r in selection.approvals.requests] == [_u(9)]  # 8 is unrelated
    assert {f["id"] for f in selection.files} == {
        _u(31),
        _u(39),
    }  # via the kept attachment + approval
    assert selection.rows["file_object"] == selection.files  # the dataset is the kept files
    assert selection.rows["contract"] == [{"id": _u(101)}]  # other datasets pass through
    monkeypatch.setattr(sx, "PENDING", {**sx.PENDING, "manual_adjustment": _PENDING_STAND_IN})
    pending = {**recon_att, "subject_type": "manual_adjustment"}
    with pytest.raises(ValueError, match="manual_adjustment is PENDING"):
        sx.select_export({**rows, "file_attachment": [pending]}, requests, [], [], files, copied)
    # every dataset the selection returns is a copied dataset of LOAD_ORDER
    assert set(selection.rows) <= set(LOAD_ORDER)


# --- Codex export review of 353d794: F-SNP-R5 (copied ids materialised once at the boundary) -----


def _r5_fixture() -> tuple[
    dict[str, list[dict[str, object]]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Codex's exact fixture: attachment 300 on contract 302 with file 301; approval request
    (100) whose subject is judgement record 201, with step 101 and decision 102."""
    rows = {
        "contract": [{"id": _u(302)}],
        "judgement_record": [{"id": _u(201), "subject_type": "contract", "subject_id": _u(302)}],
        "file_attachment": [
            {
                "id": _u(300),
                "file_object_id": _u(301),
                "subject_type": "contract",
                "subject_id": _u(302),
            }
        ],
    }
    requests = [{"id": _u(100), "subject_type": "JUDGEMENT_RECORD", "subject_id": _u(201)}]
    steps = [{"id": _u(101), "approval_request_id": _u(100)}]
    decisions = [{"id": _u(102), "approval_request_id": _u(100)}]
    files = [{"id": _u(301)}]
    return rows, requests, steps, decisions, files


def _counts(selection: sx.ExportSelection) -> list[int]:
    return [
        len(selection.rows["file_attachment"]),
        len(selection.approvals.requests),
        len(selection.approvals.steps),
        len(selection.approvals.decisions),
        len(selection.files),
    ]


def test_r5_copied_ids_as_iterators_give_the_same_export_as_lists() -> None:
    rows, requests, steps, decisions, files = _r5_fixture()
    as_lists = {"contract": [_u(302)], "judgement_record": [_u(201)]}
    as_iterators = {"contract": iter([_u(302)]), "judgement_record": iter([_u(201)])}
    with_lists = sx.select_export(rows, requests, steps, decisions, files, as_lists)
    assert _counts(with_lists) == [1, 1, 1, 1, 1]
    with_iterators = sx.select_export(rows, requests, steps, decisions, files, as_iterators)
    assert _counts(with_iterators) == [1, 1, 1, 1, 1]  # R5: [1, 0, 0, 0, 1] before the fix
    assert [r["id"] for r in with_iterators.approvals.requests] == [_u(100)]
    assert [s["id"] for s in with_iterators.approvals.steps] == [_u(101)]
    assert [d["id"] for d in with_iterators.approvals.decisions] == [_u(102)]
    assert [f["id"] for f in with_iterators.files] == [_u(301)]
    # the row inputs may be iterators too
    streamed = sx.select_export(
        {table: iter(items) for table, items in rows.items()},
        iter(requests),
        iter(steps),
        iter(decisions),
        iter(files),
        {"contract": iter([_u(302)]), "judgement_record": iter([_u(201)])},
    )
    assert _counts(streamed) == [1, 1, 1, 1, 1]


# --- SBX-05 rev 1.50 (supervisor ruling R-43 (a)): the monetary state ----------------------------

_OBLIGATION, _OTHER = str(_u(31)), str(_u(32))
_LINE_KEY = {
    "schedule_kind": "REVENUE",
    "subject_type": "obligation",
    "subject_id": _u(31),
    "entity_id": _u(41),
    "period_id": _u(51),
    "line_type": "RECOGNITION",
}


def _stored(table: str, **values: Any) -> dict[str, Any]:
    """A stored row of ``table``: every column None but ``values`` (the comparison reads the
    member columns of the real table)."""
    row: dict[str, Any] = {str(c.name): None for c in metadata.tables[f"erev.{table}"].columns}
    unknown = set(values) - set(row) - {"schedule_kind"}
    assert not unknown, unknown
    return {**row, **values}


def _version_rows(**changes: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The stored rows of one contract version: the version, one balance, two obligation
    versions, one schedule with two lines; ``changes`` overrides columns per table (the first
    row of the table)."""
    rows = {
        "contract_version": [
            _stored(
                "contract_version",
                id=_u(1),
                version_no=1,
                transaction_price=Decimal("135000.00"),
                revenue_cum=Decimal("96200.00"),
            )
        ],
        "contract_version_balance": [
            _stored(
                "contract_version_balance",
                contract_id=_u(21),
                entity_id=_u(41),
                contract_liability_txn=Decimal("38800.00"),
            )
        ],
        "obligation_version": [
            _stored(
                "obligation_version",
                obligation_id=_u(31),
                version_no=1,
                revenue_cum=Decimal("16200.00"),
                revenue_amount=Decimal("16200.00"),
                billed_amount=Decimal("15000.00"),
                effective_date=date(2026, 2, 27),
            ),
            _stored("obligation_version", obligation_id=_u(32), revenue_cum=Decimal("80000.00")),
        ],
        "schedule": [_stored("schedule", schedule_kind="REVENUE", line_count=2)],
        "schedule_line": [
            _stored("schedule_line", **_LINE_KEY, amount=Decimal("6480.00")),
            _stored(
                "schedule_line", **{**_LINE_KEY, "period_id": _u(52)}, amount=Decimal("9720.00")
            ),
        ],
    }
    for table, values in changes.items():
        rows[table] = [{**rows[table][0], **values}, *rows[table][1:]]
    return rows


def _differs(**changes: dict[str, Any]) -> sx.Difference | None:
    return sx.first_difference(
        sx.monetary_state(_version_rows()), sx.monetary_state(_version_rows(**changes))
    )


def test_monetary_state_is_the_stored_category_m_without_history() -> None:
    """The tables, keys and exclusions of the monetary state against the model: every excluded
    and every key column exists (no stale name), the six activity columns are T-CON-11 columns
    and are the only MONEY members left out, and the three category-M tables the platform does
    not store yet are still pending — the day one lands, this pin makes it join."""
    assert sx.MONETARY_TABLES == (
        "contract_version",
        "contract_version_balance",
        "obligation_version",
        "schedule_line",  # before its header: the line is what a difference names
        "schedule",
    )
    assert set(sx.MONETARY_EXCLUDED) == set(sx.MONETARY_KEYS) == set(sx.MONETARY_TABLES)
    for table in sx.MONETARY_TABLES:
        columns = {str(c.name) for c in metadata.tables[f"erev.{table}"].columns}
        assert sx.MONETARY_EXCLUDED[table] <= columns, table
        assert set(sx.MONETARY_KEYS[table]) - {"schedule_kind"} <= columns, table
        assert set(sx.monetary_members(table)) == columns - sx.MONETARY_EXCLUDED[table]
        assert not set(sx.MONETARY_KEYS[table]) & sx.MONETARY_EXCLUDED[table], table
    assert sx.ACTIVITY_COLUMNS == {
        "revenue_amount",
        "billed_amount",
        "pre_standard_revenue_amount",
        "delivered_quantity",
        "ssp_delivered",
        "catch_up_amount",
    }
    members = set(sx.monetary_members("obligation_version"))
    assert not sx.ACTIVITY_COLUMNS & members
    assert {"revenue_cum", "billed_cum", "catch_up_cum", "delivered_quantity_cum"} <= members
    assert {"allocated_amount", "remaining_allocation", "scheduled_amount"} <= members
    assert {"version_no", "previous_effective_date", "trace_nodes"}.isdisjoint(members)
    assert "amount" in sx.monetary_members("schedule_line")
    assert "trace_node_id" not in sx.monetary_members("schedule_line")
    assert {"transaction_price", "revenue_cum", "rpo_amount"} <= set(
        sx.monetary_members("contract_version")
    )
    # RCP-28a category M also covers T-CON-16 / 17 / 18; none is a table of the model yet
    pending = {"cost_asset_version", "loss_provision_version", "fx_layer_movement"}
    assert pending <= set(sd.PENDING)
    assert not pending & {table.name for table in metadata.tables.values()}


def test_first_difference_names_the_member_and_ignores_history() -> None:
    """Equal states have no difference. History never counts: the activity of one version, its
    number, its predecessor, its surrogate ids, its trace. A state member does, and is named
    with both values — first in the fixed order of tables, row keys and columns."""
    assert _differs() is None
    assert _differs(contract_version={"revenue_cum": Decimal("96200.0")}) is None  # the value
    history = {
        "revenue_amount": Decimal("9720.00"),  # the activity of the LAST computation only
        "billed_amount": Decimal("0.00"),
        "catch_up_amount": Decimal("1.00"),
        "delivered_quantity": Decimal("3"),
        "ssp_delivered": Decimal("3"),
        "pre_standard_revenue_amount": Decimal("5.00"),
        "version_no": 7,
        "previous_effective_date": date(2026, 1, 31),
        "previous_obligation_version_id": _u(99),
        "trace_nodes": {"revenue_cum": "node"},
        "id": _u(98),
    }
    assert _differs(obligation_version=history) is None
    assert _differs(contract_version={"version_no": 7, "cause_event_ids": [_u(5)]}) is None
    assert _differs(schedule_line={"trace_node_id": "other", "id": _u(97)}) is None

    found = _differs(obligation_version={"revenue_cum": Decimal("16200.01")})
    assert found == sx.Difference(
        "obligation_version",
        (_OBLIGATION,),
        "revenue_cum",
        Decimal("16200.00"),
        Decimal("16200.01"),
    )
    assert found is not None and found.member == f"obligation_version[{_OBLIGATION}].revenue_cum"
    line = _differs(schedule_line={"amount": Decimal("6480.01")})
    assert line is not None and (line.table, line.column) == ("schedule_line", "amount")
    assert line.member == (
        f"schedule_line[REVENUE, obligation, {_u(31)}, {_u(41)}, {_u(51)}, RECOGNITION].amount"
    )
    assert (line.source, line.sandbox) == (Decimal("6480.00"), Decimal("6480.01"))
    top = _differs(contract_version={"transaction_price": Decimal("1.00")})
    assert top is not None and top.member == "contract_version.transaction_price"
    # the first in the fixed order: the version before a balance, a balance before a line
    both = _differs(
        schedule_line={"amount": Decimal("1.00")},
        contract_version_balance={"contract_liability_txn": Decimal("1.00")},
    )
    assert both is not None and both.table == "contract_version_balance"
    assert both.member == f"contract_version_balance[{_u(21)}, {_u(41)}].contract_liability_txn"
    # a line before the header that sums it
    summed = _differs(
        schedule={"total_amount": Decimal("16200.01")},
        schedule_line={"amount": Decimal("6480.01")},
    )
    assert summed is not None and summed.table == "schedule_line"
    header = _differs(schedule={"total_amount": Decimal("16200.01")})
    assert header is not None and header.member == "schedule[REVENUE].total_amount"


def test_first_difference_names_a_row_on_one_side_only() -> None:
    fewer = _version_rows()
    fewer["schedule_line"] = fewer["schedule_line"][:1]
    found = sx.first_difference(sx.monetary_state(_version_rows()), sx.monetary_state(fewer))
    assert found is not None and found.column is None
    assert (found.table, found.source, found.sandbox) == ("schedule_line", "present", "absent")
    assert found.member == (
        f"schedule_line[REVENUE, obligation, {_u(31)}, {_u(41)}, {_u(52)}, RECOGNITION]"
    )
    other = _version_rows()
    other["obligation_version"] = [other["obligation_version"][0]]
    back = sx.first_difference(sx.monetary_state(other), sx.monetary_state(_version_rows()))
    assert back is not None
    assert (back.member, back.source, back.sandbox) == (
        f"obligation_version[{_OTHER}]",
        "absent",
        "present",
    )
    doubled = _version_rows()
    doubled["obligation_version"].append(doubled["obligation_version"][0])
    with pytest.raises(ValueError, match="obligation_version: two rows of one version carry"):
        sx.monetary_state(doubled)


def test_judge_puts_the_hash_and_the_state_together() -> None:
    """SBX-05 rev 1.50 per pair. One-sided: a finding. States differ: a finding naming the
    member, whatever the hashes say. States equal: verified — except a FIRST computation whose
    comparable hash differs all the same (a one-shot recompute must reproduce all of it). A hash
    mismatch without facts is never dropped."""
    gone = sx.Difference("schedule_line", ("k",), "amount", Decimal("1.00"), Decimal("1.01"))
    report = sx.DeterminismReport(
        compared=7,
        mismatches=(
            sx.Mismatch(_u(1), "ASC606", "src", "sbx"),  # later version, states equal: verified
            sx.Mismatch(_u(2), "ASC606", "src", "sbx"),  # first computation, states equal
            sx.Mismatch(_u(3), "ASC606", "src", "sbx"),  # later version, states differ
            sx.Mismatch(_u(4), "ASC606", "src", None),  # nothing recomputed
            sx.Mismatch(_u(5), "ASC606", None, "sbx"),  # no source version as of known_at
            sx.Mismatch(_u(6), "ASC606", "src", "sbx"),  # no facts were read
        ),
    )
    facts = {
        (_u(1), "ASC606"): sx.PairFacts(first_computation=False, difference=None),
        (_u(2), "ASC606"): sx.PairFacts(first_computation=True, difference=None),
        (_u(3), "ASC606"): sx.PairFacts(first_computation=False, difference=gone),
        # equal hashes, first computation — and yet the stored states differ: a finding
        (_u(7), "ASC606"): sx.PairFacts(first_computation=True, difference=gone),
    }
    assert sx.judge(report, facts) == (
        sx.Finding(_u(2), "ASC606", sx.COMPARISON_HASH, "output_sha256", "src", "sbx"),
        sx.Finding(_u(3), "ASC606", sx.COMPARISON_STATE, gone.member, gone.source, gone.sandbox),
        sx.Finding(_u(4), "ASC606", sx.COMPARISON_ONE_SIDED, None, "src", None),
        sx.Finding(_u(5), "ASC606", sx.COMPARISON_ONE_SIDED, None, None, "sbx"),
        sx.Finding(_u(6), "ASC606", sx.COMPARISON_HASH, "output_sha256", "src", "sbx"),
        sx.Finding(_u(7), "ASC606", sx.COMPARISON_STATE, gone.member, gone.source, gone.sandbox),
    )
    clean = sx.DeterminismReport(compared=1, mismatches=())
    assert sx.judge(clean, {(_u(1), "ASC606"): sx.PairFacts(True, None)}) == ()
    assert (sx.COMPARISON_STATE, sx.COMPARISON_HASH, sx.COMPARISON_ONE_SIDED) == (
        "MONETARY_STATE",
        "OUTPUT_HASH",
        "ONE_SIDED",
    )
