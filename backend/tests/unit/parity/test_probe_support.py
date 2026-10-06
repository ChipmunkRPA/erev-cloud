"""Probe support (docs/dev-guide.md §9.6 DG-PAR-06, DG-PAR-10, DG-PAR-11 and the table "Probe
import-status mapping"; BUILD_SPEC GPA-6, GPB-1; D-87b).

The classification, ordering and comparison of ``support.parity.probes`` are pure, so these tests
build observations by hand and need no database. ``make parity`` runs the replay itself. GPB-1 adds
the journal expectations through report ``legacy_je_summary`` (XR-12), the rev 1.1 upload objects
and suffixed counts of P4, and the D-87b ``detail`` rule of P3.
"""

from __future__ import annotations

from typing import Any

from erev_api.domain.reports.framework import BUILDERS
from erev_api.problems import TYPE_BASE
from support.parity import probes, values
from support.parity.probes import Classification, ProbeFinding, ProbeObservation, ProbeUpload

SHA = "0" * 64
DUPLICATE_MESSAGE = (
    "This file was already imported in IMP-000004 on 2026-01-01. Nothing was imported again."
)
OVER_DELIVERY = (
    "Progress Tracking row 2, column Current Delivery: Contract 1, obligation POB #1 (Hardware 1): "
    "requested 7, remaining 5. Rows 2, 6. Key Contract 1 / POB #1 / Hardware 1. "
    "(PROGRESS_OVER_DELIVERY)"
)


def _upload(
    status: str | None,
    *findings: ProbeFinding,
    problem: dict[str, object] | None = None,
) -> ProbeUpload:
    return ProbeUpload(
        file_name="probe.xlsx", sha256=SHA, e40_status=status, findings=findings, problem=problem
    )


def _row(code: str, severity: str, row: int, *, sheet: str = "Progress Tracking") -> ProbeFinding:
    return ProbeFinding(
        code=code,
        severity=severity,
        message=f"{sheet} row {row}: finding. ({code})",
        sheet_name=sheet,
        row_number=row,
        business_key="Contract 1 / POB #1 / Hardware 1",
    )


def test_probe_status_mapping() -> None:
    # COMMITTED: E-40 COMMITTED with zero findings.
    assert probes.classify(_upload("COMMITTED")) == Classification("COMMITTED")
    # COMMITTED_WITH_FINDINGS: at least one WARNING and no ERROR.
    warned = _upload("COMMITTED", _row("PROGRESS_MEMO_BLANK", "WARNING", 3))
    assert probes.classify(warned) == Classification("COMMITTED_WITH_FINDINGS")
    # REJECTED (validation): E-40 INVALID; error_code and detail of the first ERROR in DG-PAR-11
    # order, whatever order the findings were read in.
    first = ProbeFinding(
        code="PROGRESS_OVER_DELIVERY",
        severity="ERROR",
        message=OVER_DELIVERY,
        sheet_name="Progress Tracking",
        row_number=2,
        business_key="Contract 1 / POB #1 / Hardware 1",
    )
    later = _row("PROGRESS_OVER_BILLING", "ERROR", 5)
    warning = _row("PROGRESS_MEMO_BLANK", "WARNING", 1)
    rejected = probes.classify(_upload("INVALID", later, warning, first))
    assert rejected == Classification("REJECTED", "PROGRESS_OVER_DELIVERY", OVER_DELIVERY)
    # REJECTED (upload refused): 409 duplicate-import and no import_upload row.
    problem: dict[str, object] = {
        "type": f"{TYPE_BASE}duplicate-import",
        "title": "Already imported",
        "status": 409,
        "errors": [
            {
                "field": None,
                "sheet": None,
                "row": None,
                "rule_id": "IMPORT_FILE_DUPLICATE",
                "message": DUPLICATE_MESSAGE,
            }
        ],
    }
    refused = probes.classify(_upload(None, problem=problem))
    assert refused == Classification("REJECTED", "IMPORT_FILE_DUPLICATE", DUPLICATE_MESSAGE)
    # A terminal state that no row matches is unclassified, and the case reports what it saw.
    for status in ("REJECTED", "FAILED", "CANCELLED"):
        unmatched = probes.classify(_upload(status))
        assert unmatched.import_status is None and status in (unmatched.condition or "")
    assert probes.classify(_upload("COMMITTED", first)).import_status is None
    assert probes.classify(_upload("INVALID", warning)).import_status is None
    assert probes.classify(_upload("UNKNOWN", problem=problem)).import_status is None
    # The comparison asserts import_status, error_code, detail and the basis members, never the
    # provenance keys.
    expected = {
        "import_status": "REJECTED",
        "import_status_basis": {
            "mapping": "DG-PAR-06",
            "e40_import_status": None,
            "condition": "upload refused before validation",
            "problem": {
                "slug": "duplicate-import",
                "status": 409,
                "errors": [{"rule_id": "IMPORT_FILE_DUPLICATE"}],
            },
        },
        "error_code": "IMPORT_FILE_DUPLICATE",
        "error_code_source": "errors[0].rule_id of the problem response",
        "legacy_oracle": "not asserted",
        "legacy_replica_rows": ["not asserted"],
        "findings": [],
    }
    observed = ProbeObservation(uploads=(_upload(None, problem=problem),), watched={})
    assert probes.compare(expected, observed) == []
    # A validation rejection is also REJECTED, so only its code, basis and findings differ.
    wrong = ProbeObservation(uploads=(_upload("INVALID", first),), watched={})
    fields = {item.field for item in probes.compare(expected, wrong)}
    assert fields == {
        "error_code",
        "import_status_basis.e40_import_status",
        "import_status_basis.problem",
        "findings.count",
    }


def test_findings_order_and_business_key() -> None:
    file_stage = ProbeFinding(
        code="IMPORT_NO_DATA_ROWS",
        severity="ERROR",
        message="The file has headers but no data rows.",
    )
    unordered = (
        _row("PROGRESS_OVER_BILLING", "ERROR", 4),
        _row("PROGRESS_MEMO_BLANK", "WARNING", 2),
        _row("CONTRACT_NOT_FOUND", "ERROR", 2),
        file_stage,
        _row("POB_NOT_FOUND", "ERROR", 9, sheet="Another sheet"),
    )
    ordered = probes.order_findings(unordered)
    assert [(item.sheet_name, item.row_number, item.code) for item in ordered] == [
        (None, None, "IMPORT_NO_DATA_ROWS"),
        ("Another sheet", 9, "POB_NOT_FOUND"),
        ("Progress Tracking", 2, "CONTRACT_NOT_FOUND"),
        ("Progress Tracking", 2, "PROGRESS_MEMO_BLANK"),
        ("Progress Tracking", 4, "PROGRESS_OVER_BILLING"),
    ]
    assert (
        probes.normalised_key("Contract 1 / POB #2 / Software 1") == "Contract 1 POB #2 Software 1"
    )
    # worksheet_rows: every contributing row that the message names; its lowest is worksheet_row.
    over = ProbeFinding(
        code="PROGRESS_OVER_DELIVERY",
        severity="ERROR",
        message=OVER_DELIVERY,
        sheet_name="Progress Tracking",
        row_number=2,
        business_key="Contract 1 / POB #1 / Hardware 1",
    )
    assert (over.worksheet_rows, over.pob) == ((2, 6), "Contract 1 POB #1 Hardware 1")
    assert file_stage.worksheet_rows == () and file_stage.pob is None
    expected = [
        {
            "code": "PROGRESS_OVER_DELIVERY",
            "severity": "ERROR",
            "worksheet_row": 2,
            "worksheet_rows": [2, 6],
            "pob": "Contract 1 POB #1 Hardware 1",
        }
    ]
    assert probes.finding_mismatches(expected, (over,)) == []
    # Other string members (blank_memos) must appear verbatim in the message.
    memo = ProbeFinding(
        code="PROGRESS_MEMO_BLANK",
        severity="WARNING",
        message="Progress Tracking row 3, column Memo 3: Memo 3 is blank. (PROGRESS_MEMO_BLANK)",
        sheet_name="Progress Tracking",
        row_number=3,
        business_key="Contract 1 / POB #2 / Software 1",
    )
    blank = {
        "code": "PROGRESS_MEMO_BLANK",
        "severity": "WARNING",
        "worksheet_row": 3,
        "pob": "Contract 1 POB #2 Software 1",
        "blank_memos": ["Memo 3"],
    }
    assert probes.finding_mismatches([blank], (memo,)) == []
    missing = probes.finding_mismatches([{**blank, "blank_memos": ["Memo 2"]}], (memo,))
    assert [item.field for item in missing] == ["findings[0].blank_memos"]
    # Order is part of the comparison, and an empty expected list requires zero findings.
    swapped = probes.finding_mismatches([blank, expected[0]], (over, memo))
    assert {item.field for item in swapped} >= {"findings[0].code", "findings[1].code"}
    assert probes.finding_mismatches([], ()) == []
    assert [item.field for item in probes.finding_mismatches([], (memo,))] == ["findings.count"]


def _money(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


# P1 je_gross_2023_01 (GT-22; DEV-010) as deviations.json states it.
P1_GROSS: dict[str, Any] = {
    "lines": 6,
    "by_account": [
        {"account": "5001", "debit": "0.00", "credit": "187.69", "net": "-187.69"},
        {"account": "5002", "debit": "0.00", "credit": "118.53", "net": "-118.53"},
        {"account": "5003", "debit": "0.00", "credit": "48.32", "net": "-48.32"},
        {"account": "15002", "debit": "58.85", "credit": "0.00", "net": "58.85"},
        {"account": "21001", "debit": "295.69", "credit": "0.00", "net": "295.69"},
    ],
    "total_debit": "354.54",
    "total_credit": "354.54",
    "net": "0.00",
    "line_items": [
        {"key": "Contract 1", "account": "21001", "amount": "295.69"},
        {"key": "Contract 1 POB #1 Hardware 1", "account": "5001", "amount": "-128.84"},
        {"key": "Contract 1 POB #2 Software 1", "account": "5002", "amount": "-118.53"},
        {"key": "Contract 1 POB #3 Consulting 1", "account": "5003", "amount": "-48.32"},
        {"key": "Contract 2", "account": "15002", "amount": "58.85"},
        {"key": "Contract 2 POB #1 Hardware 1", "account": "5001", "amount": "-58.85"},
    ],
}
ZERO_VIEW: dict[str, Any] = {
    "lines": 0,
    "by_account": [],
    "total_debit": "0.00",
    "total_credit": "0.00",
    "net": "0.00",
    "line_items": [],
}


def _gross_run() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A ``legacy_je_summary`` run of January 2023 as API-R-41 returns it: API-S-ReportRun control
    totals and the data rows in section order."""
    totals = {
        "mode": "GROSS",
        "book": "ASC606",
        "from_date": "2023-01-01",
        "to_date": "2023-01-31",
        "lines": 6,
        "total_debit": {"USD": "354.54"},
        "total_credit": {"USD": "354.54"},
        "net": {"USD": "0.00"},
    }
    rows: list[dict[str, Any]] = [
        {
            "row_key": f"account:{item['account']}",
            "section": "by_account",
            "account": item["account"],
            "currency": "USD",
            "debit": _money(item["debit"]),
            "credit": _money(item["credit"]),
            "net": _money(item["net"]),
        }
        for item in P1_GROSS["by_account"]
    ]
    rows += [
        {
            "row_key": f"entity:{code}",
            "section": "by_entity",
            "entity_code": code,
            "currency": "USD",
            "debit": _money(amount),
            "credit": _money(amount),
            "balanced": True,
            "difference": _money("0.00"),
        }
        for code, amount in (("Mock Entity 1", "295.69"), ("Mock Entity 2", "58.85"))
    ]
    rows += [
        {
            "row_key": f"item:{item['key']}:{item['account']}",
            "section": "line_items",
            "key": item["key"],
            "account": item["account"],
            "entity_code": "Mock Entity 2"
            if item["key"].startswith("Contract 2")
            else "Mock Entity 1",
            "currency": "USD",
            "amount": _money(item["amount"]),
        }
        for item in P1_GROSS["line_items"]
    ]
    return totals, rows


def test_journal_expectation_uses_legacy_je_summary() -> None:
    # RPT-13 has a builder (RPS-5), so a journal key is compared with the report run's view.
    assert probes.journal_built() and probes.JOURNAL_REPORT in BUILDERS
    view = values.journal_view(*_gross_run())
    observed = ProbeObservation(uploads=(), watched={}, journals={"je_gross_2023_01": view})
    found = probes.compare({"je_gross_2023_01": P1_GROSS}, observed)
    assert found == []
    # Field by field: lines, a by_account member to the cent, the line item list.
    first, *others = P1_GROSS["by_account"]
    changed = {
        **P1_GROSS,
        "lines": 5,
        "by_account": [{**first, "credit": "187.68"}, *others],
        "line_items": P1_GROSS["line_items"][:-1],
    }
    fields = [item.field for item in probes.compare({"je_gross_2023_01": changed}, observed)]
    assert fields == [
        "je_gross_2023_01.lines",
        "je_gross_2023_01.by_account[0].credit",
        "je_gross_2023_01.line_items.count",
    ]
    # A window without lines has no currency row; its totals read 0.00 (P2 je_delta_feb).
    empty = values.journal_view(
        {"mode": "DELTA", "lines": 0, "total_debit": {}, "total_credit": {}, "net": {}}, []
    )
    feb = ProbeObservation(uploads=(), watched={}, journals={"je_delta_feb": empty})
    assert probes.compare({"je_delta_feb": ZERO_VIEW}, feb) == []
    # Windows and modes: probe.json reports; P1's month label takes the je_gross report.
    p1 = probes.probe_reports("probe-P1-blank-memo-drops-progress-rows")
    p2 = probes.probe_reports("probe-P2-mod-reposts-pre-asc606-in-delta-je")
    assert probes.journal_window(p1, "je_gross_2023_01") == ("2023-01-01", "2023-01-31")
    assert probes.journal_window(p2, "je_delta_jan") == ("2023-01-01", "2023-01-31")
    assert probes.journal_window(p2, "je_gross_feb") == ("2023-02-01", "2023-02-28")
    february = {"je_gross": {"window": ["2023-02-01", "2023-02-28"]}}
    assert probes.journal_window(february, "je_gross_2023_01") is None
    assert (probes.journal_mode("je_gross_feb"), probes.journal_mode("je_delta_feb")) == (
        "GROSS",
        "DELTA",
    )
    # No "not built" mismatch remains with the report; a key without a view still fails.
    unobserved = ProbeObservation(uploads=(), watched={})
    missing = probes.compare({"je_gross_2023_01": P1_GROSS}, unobserved)
    assert [(item.field, item.actual) for item in missing] == [
        ("je_gross_2023_01", probes.JOURNAL_NO_WINDOW)
    ]
    assert all(probes.JOURNAL_NOT_BUILT != item.actual for item in missing)
    # Fail-closed rule of GPA-6 (XR-12): without the report each journal key names BUILD_SPEC RPS.
    expected = {"je_gross_2023_01": P1_GROSS, "je_delta_feb": ZERO_VIEW}
    mismatches = probes.compare(expected, unobserved, report_built=False)
    assert [item.field for item in mismatches] == ["je_gross_2023_01", "je_delta_feb"]
    assert all(item.actual == probes.JOURNAL_NOT_BUILT for item in mismatches)
    # A member without a DG-PAR-06 rule fails the case too; nothing passes by omission.
    unruled = probes.compare({"unknown_member": {}}, unobserved, report_built=False)
    assert [item.field for item in unruled] == ["unknown_member"]


def test_journal_window_of_a_month_label_is_the_whole_month() -> None:
    # [J] L7-1-Q-7 (DG-PAR-06 as amended): a month key without its own report takes the view's
    # window only when it equals [YYYY-MM-01, the last day of that month].
    quarter = {"je_gross": {"window": ["2023-01-01", "2023-03-31"]}}
    assert probes.journal_window(quarter, "je_gross_2023_01") is None
    january = {"je_gross": {"window": ["2023-01-01", "2023-01-31"]}}
    assert probes.journal_window(january, "je_gross_2023_01") == ("2023-01-01", "2023-01-31")
    # The last day comes from the calendar: 29 February 2024, 28 February 2023.
    leap = {"je_delta": {"window": ["2024-02-01", "2024-02-29"]}}
    assert probes.journal_window(leap, "je_delta_2024_02") == ("2024-02-01", "2024-02-29")
    short = {"je_delta": {"window": ["2023-02-01", "2023-02-29"]}}
    assert probes.journal_window(short, "je_delta_2023_02") is None
    assert (
        probes.journal_window({"je_gross": {"window": ["2023-01-01"]}}, "je_gross_2023_01") is None
    )
    assert (
        probes.journal_window(
            {"je_gross": {"window": ["2023-13-01", "2023-13-31"]}}, "je_gross_2023_13"
        )
        is None
    )
    # A key without a month label, or with its own report, is unchanged.
    assert probes.journal_window(january, "je_gross_jan") is None
    own = {"je_gross_feb": {"window": ["2023-02-01", "2023-02-28"]}}
    assert probes.journal_window(own, "je_gross_feb") == ("2023-02-01", "2023-02-28")
    # The unmatched key fails the case with JOURNAL_NO_WINDOW.
    missing = probes.compare(
        {"je_gross_2023_01": P1_GROSS}, ProbeObservation(uploads=(), watched={})
    )
    assert [(item.field, item.actual) for item in missing] == [
        ("je_gross_2023_01", probes.JOURNAL_NO_WINDOW)
    ]


def _duplicate_problem() -> dict[str, object]:
    return {
        "type": f"{TYPE_BASE}duplicate-import",
        "title": "Already imported",
        "status": 409,
        "errors": [{"rule_id": "IMPORT_FILE_DUPLICATE", "message": DUPLICATE_MESSAGE}],
    }


def test_upload_objects_and_suffixed_counts() -> None:
    feb = "Contract Progress Tracking Template 2.28.2023.xlsx"
    january = ProbeUpload(
        file_name="Contract Progress Tracking Template 1.31.2023.xlsx",
        sha256="1" * 64,
        e40_status="COMMITTED",
        versions_before=16,
        versions_after=24,
    )
    first = ProbeUpload(
        file_name=feb, sha256=SHA, e40_status="COMMITTED", versions_before=24, versions_after=36
    )
    second = ProbeUpload(
        file_name=feb,
        sha256=SHA,
        e40_status=None,
        problem=_duplicate_problem(),
        versions_before=36,
        versions_after=36,
    )
    observed = ProbeObservation(uploads=(january, first, second), watched={})
    assert probes.repeated_uploads(observed.uploads) == ((first, second),)
    assert probes.named_upload(observed, "second", "2_28") is second
    assert probes.named_upload(observed, "second", None) is second
    assert probes.named_upload(observed, "first", "1_31") is None
    # P4: each object describes, in order, the uploads of the same file (DG-PAR-06 rev 1.1).
    expected: dict[str, Any] = {
        "first_2_28_upload": {
            "import_status": "COMMITTED",
            "import_status_basis": {"mapping": "DG-PAR-06", "e40_import_status": "COMMITTED"},
            "findings": [],
            "sha256": SHA,
        },
        "second_2_28_upload": {
            "import_status": "REJECTED",
            "import_status_basis": {
                "mapping": "DG-PAR-06",
                "e40_import_status": None,
                "problem": {
                    "slug": "duplicate-import",
                    "status": 409,
                    "errors": [{"rule_id": "IMPORT_FILE_DUPLICATE"}],
                },
            },
            "error_code": "IMPORT_FILE_DUPLICATE",
            "error_code_source": "not asserted",
            "findings": [],
            "sha256": SHA,
        },
        "versions_before_second": 36,
        "versions_after_second": 36,
    }
    assert probes.compare(expected, observed) == []
    wrong = {
        **expected,
        "first_2_28_upload": {**expected["first_2_28_upload"], "sha256": "f" * 64},
        "versions_before_second": 24,
    }
    assert [item.field for item in probes.compare(wrong, observed)] == [
        "first_2_28_upload.sha256",
        "versions_before_second",
    ]
    # Without a repeated file the objects and the counts fail closed.
    single = ProbeObservation(uploads=(january,), watched={})
    refused = probes.compare({"second_2_28_upload": {}, "versions_after_second": 36}, single)
    assert [item.actual for item in refused] == [probes.NO_REPEATED_UPLOAD] * 2


def test_probe_detail_by_key_and_quantities() -> None:
    # D-87b (L7-1-Q-1): key tokens and quantities, not equal text, for legacy_probe detail.
    legacy = "Contract 1 POB #1 Hardware 1: delivery 7 exceeds remaining quantity 5"
    assert probes.detail_equal(legacy, OVER_DELIVERY)
    assert not probes.detail_equal(legacy, OVER_DELIVERY.replace("requested 7", "requested 8"))
    assert not probes.detail_equal(legacy, OVER_DELIVERY.replace("remaining 5", "remaining 50"))
    assert not probes.detail_equal(legacy, OVER_DELIVERY.replace("POB #1", "POB #10"))
    assert not probes.detail_equal(legacy.replace("delivery", "billing"), OVER_DELIVERY)
    assert not probes.detail_equal(legacy, None)
    assert probes.detail_equal(None, None) and not probes.detail_equal(None, OVER_DELIVERY)
    finding = ProbeFinding(
        code="PROGRESS_OVER_DELIVERY",
        severity="ERROR",
        message=OVER_DELIVERY,
        sheet_name="Progress Tracking",
        row_number=2,
        business_key="Contract 1 / POB #1 / Hardware 1",
    )
    rejected = ProbeObservation(uploads=(_upload("INVALID", finding),), watched={})
    assert probes.compare({"import_status": "REJECTED", "detail": legacy}, rejected) == []
