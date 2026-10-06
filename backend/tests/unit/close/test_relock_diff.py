"""CLO-7 re-lock diff (BR-CLS-07; S15-R-18, S15-R-20; 04 T-CLS-04 rev 1.25; supervisor ruling
D-98 81): pure comparison of two locks' datasets by the explicit per-kind row key — hashes, row
counts, rows added / removed / changed with every non-key column compared (measure changes with a
delta, attribute changes without), manifests and certification — over RPT-shaped CSVs. Codex's two
counterexamples (name-only; name plus amount) are the regression. No database."""

from __future__ import annotations

import json
import re
from uuid import UUID

import pytest
from erev_api.domain.close import relock_diff
from erev_api.domain.close.relock_diff import DatasetSide, LockSide
from erev_api.enums import SnapshotKind

LOCK_1 = UUID("00000000-0000-0000-0000-00000000f001")
LOCK_2 = UUID("00000000-0000-0000-0000-00000000f002")
HEADER = (
    "contract_external_id,customer_name,entity_code,currency,contract_liability,contract_asset\n"
)
CASTELLAN = "PRJ-CB-2026-01,Castellan Build Group Inc. (Demo),AVM-US,USD,0.00,{asset}\n"
PELLWORTH = "SF-ORD-10001,Pellworth Logistics Inc. (Demo),AVM-US,USD,39708.49,0.00\n"
BEFORE = (
    HEADER
    + CASTELLAN.format(asset="97294.12")
    + PELLWORTH
    + "SF-ORD-10009,Removed Co,AVM-US,USD,10.00,0.00\n"
).encode()
AFTER = (
    HEADER
    + CASTELLAN.format(asset="129852.94")
    + PELLWORTH
    + "SF-ORD-10011,Added Co,AVM-US,USD,5.00,0.00\n"
).encode()
# Codex counterexamples: only the customer's name changed; name and the amount changed.
NAME_ONLY = (
    HEADER
    + "PRJ-CB-2026-01,Castellan Build Group LLC (Demo),AVM-US,USD,0.00,97294.12\n"
    + PELLWORTH
).encode()
NAME_AND_AMOUNT = (
    HEADER
    + "PRJ-CB-2026-01,Castellan Build Group LLC (Demo),AVM-US,USD,0.00,129852.94\n"
    + PELLWORTH
).encode()
BASE = (HEADER + CASTELLAN.format(asset="97294.12") + PELLWORTH).encode()
RPO = (
    b"section,entity_code,contract_external_id,obligation_key,customer_name,currency,total\n"
    b"RPO,AVM-US,PRJ-CB-2026-01,O1,Castellan,USD,552705.88\n"
)
CERT_BEFORE = [
    {"gate_check_code": "JE_BALANCED", "status": "PASSED", "count": 0, "evaluated_at": "t1"},
    {
        "gate_check_code": "CONTROLLER_CERTIFIED",
        "status": "PASSED",
        "count": 0,
        "evaluated_at": "t1",
    },
]
CERT_AFTER = [
    {"gate_check_code": "JE_BALANCED", "status": "PASSED", "count": 0, "evaluated_at": "t2"},
    {
        "gate_check_code": "CONTROLLER_CERTIFIED",
        "status": "PASSED",
        "count": 0,
        "evaluated_at": "t2",
    },
]
# Fixture headers per E-64 kind: the report builders' columns on this tree, or the SCREENS_B field
# names where the builder is not on the tree yet (the table entry states which).
FIXTURE_HEADERS: dict[str, list[str]] = {
    "WATERFALL": [
        "contract_external_id",
        "customer_name",
        "obligation_key",
        "product_code",
        "revenue_category",
        "entity_code",
        "currency",
        "period_key",
        "period:FY2026-P09",
        "scheduled",
        "recognised",
        "awaiting_trigger",
        "total",
    ],
    "CONTRACT_BALANCES": [
        "contract_external_id",
        "customer_name",
        "entity_code",
        "currency",
        "contract_liability",
        "contract_liability_current",
        "contract_liability_noncurrent",
        "contract_asset",
        "contract_asset_current",
        "unbilled_receivable",
        "accounts_receivable",
        "refund_liability",
        "return_asset",
        "deposit_liability",
        "customer_incentive_asset",
        "consideration_payable",
        "cost_asset_carrying",
        "loss_provision",
    ],
    "CONTRACT_BALANCE_ROLLFORWARD": [
        "section",
        "line_code",
        "line_label",
        "contract_liability",
        "contract_asset",
        "unbilled_receivable",
        "contract_external_id",
        "customer_name",
        "currency",
        "opening",
        "billings",
        "revenue_from_opening",
        "revenue_from_period_billings",
        "reclassifications",
        "fx_remeasurement",
        "business_combinations",
        "other",
        "closing",
    ],
    "RPO": [
        "section",
        "contract_external_id",
        "customer_name",
        "entity_code",
        "currency",
        "total",
        "within_12_months",
        "months_13_to_24",
        "after_24_months",
        "current",
        "noncurrent",
        "obligation_key",
        "expedient",
        "expedient_label",
        "nature",
        "remaining_duration_months",
        "excluded_amount",
        "excluded_descriptor",
    ],
    "RPO_ROLLFORWARD": [
        "section",
        "line_code",
        "line_label",
        "rpo",
        "contract_external_id",
        "currency",
        "opening",
        "new_contracts",
        "modifications",
        "vc_estimate_changes",
        "late_events",
        "revenue",
        "cancellations",
        "fx",
        "unexplained",
        "closing",
    ],
    "DISAGGREGATION": [
        "dimension_code",
        "dimension_value",
        "timing_code",
        "dimension_value_label",
        "timing",
        "currency",
        "period:FY2026-P09",
        "total",
    ],
    "PRIOR_PERIOD_POB_REVENUE": [
        "entity_code",
        "contract_external_id",
        "obligation_key",
        "product_code",
        "satisfied_period_key",
        "cause",
        "currency",
        "from_price_changes",
        "from_estimate_changes",
        "from_modifications",
        "from_late_events",
        "from_other",
        "revenue",
    ],
    "COST_ROLLFORWARD": ["cost_kind", "line_code", "category_label", "line_label", "amount"],
    "JE_POPULATION": [
        "je_no",
        "line_no",
        "entity_code",
        "book",
        "period_key",
        "je_type",
        "description",
        "account_code",
        "account_role",
        "dimensions",
        "txn_currency",
        "debit_txn",
        "credit_txn",
        "functional_currency",
        "debit_functional",
        "credit_functional",
    ],
    "OUT_OF_PERIOD_REGISTER": [
        "event_key",
        "contract_external_id",
        "event_type",
        "effective_date",
        "recorded_at",
        "origin_period_key",
        "posting_period_key",
        "reason_code",
        "origin",
        "currency",
        "revenue_effect",
        "balance_effect",
        "recorded_by",
        "approval_request_no",
    ],
    # CTR-17 slice 1 (ENGINE_SPEC_B S15-R-20c rev 1.38; SCREENS_B RPT-14 rev 1.23): the builder's
    # header — key code columns first, the two typed-money measures, the attributes last.
    "MODIFICATION_REGISTER": [
        "contract_external_id",
        "modification_no",
        "obligation_key",
        "kind",
        "effective_date",
        "created_at",
        "status",
        "proposed_treatment",
        "chosen_treatment",
        "treatment_override",
        "judgement_no",
        "added_goods_distinct",
        "priced_at_ssp",
        "remaining_goods_distinct_from_transferred",
        "currency",
        "tp_change",
        "catch_up_amount",
        "approval_request_no",
        "approved_at",
        "impact_preview_sha256",
        "applied_event_key",
        "reference",
        "kind_label",
        "proposed_treatment_label",
        "chosen_treatment_label",
        "preparer",
        "approvers",
    ],
    "MANUAL_ADJUSTMENT_REGISTER": [
        "adjustment_no",
        "kind",
        "contract_external_id",
        "obligation_key",
        "entity_code",
        "effective_date",
        "status",
        "reason_code",
        "memo",
        "currency",
        "amount_functional_abs",
        "preparer",
        "approvers",
    ],
}


def _side(
    lock_id: UUID, balances: bytes, manifest: str | None, cert: list[dict[str, object]]
) -> LockSide:
    return LockSide(
        lock_id=lock_id,
        snapshot_manifest_sha256=manifest,
        certification=cert,
        datasets={
            "CONTRACT_BALANCES": DatasetSide(
                "CONTRACT_BALANCES", "a" * 64 if balances is BEFORE else "b" * 64, 3, balances
            ),
            "RPO": DatasetSide("RPO", "c" * 64, 1, RPO),
        },
    )


def _balances(report: dict[str, object]) -> dict[str, object]:
    kinds = report["kinds"]
    assert isinstance(kinds, dict)
    return dict(kinds["CONTRACT_BALANCES"])


def test_changed_added_removed_rows_by_row_key_with_deltas() -> None:
    """The unchanged positive: one contract's asset moves 97,294.12 → 129,852.94 (+32,558.82), one
    contract removed, one added; the key is (entity_code, contract_external_id), never the name."""
    report = relock_diff.diff(
        _side(LOCK_1, BEFORE, "m1" * 32, CERT_BEFORE), _side(LOCK_2, AFTER, "m2" * 32, CERT_AFTER)
    )
    assert (report["format"], report["previous_lock_id"], report["lock_id"]) == (
        relock_diff.FORMAT,
        str(LOCK_1),
        str(LOCK_2),
    )
    assert report["manifest"] == {"previous": "m1" * 32, "current": "m2" * 32, "changed": True}
    balances = _balances(report)
    assert (
        balances["changed"],
        balances["previous_file_sha256"],
        balances["current_file_sha256"],
    ) == (
        True,
        "a" * 64,
        "b" * 64,
    )
    assert balances["key_columns"] == ["entity_code", "contract_external_id"]
    assert balances["totals"] == {
        "added": 1,
        "removed": 1,
        "changed": 1,
        "measure_changes": 1,
        "attribute_changes": 0,
    }
    (changed,) = balances["changed_rows"]  # type: ignore[misc]
    assert changed["key"] == {"entity_code": "AVM-US", "contract_external_id": "PRJ-CB-2026-01"}
    assert changed["columns"] == {
        "contract_asset": {
            "kind": "measure",
            "previous": "97294.12",
            "current": "129852.94",
            "delta": "32558.82",
        }
    }
    assert [row["key"]["contract_external_id"] for row in balances["added"]] == ["SF-ORD-10011"]  # type: ignore[index]
    assert [row["key"]["contract_external_id"] for row in balances["removed"]] == ["SF-ORD-10009"]  # type: ignore[index]
    rpo = report["kinds"]["RPO"]  # type: ignore[index]
    assert (rpo["changed"], rpo["totals"]["changed"], rpo["key_columns"]) == (
        False,
        0,
        ["entity_code", "contract_external_id", "obligation_key"],  # D-98 85: section not identity
    )
    assert report["certification"]["changed"] == []  # type: ignore[index]
    assert json.loads(relock_diff.encode(report)) == json.loads(json.dumps(report, default=str))


def test_name_only_change_is_one_changed_row_with_an_attribute_change() -> None:
    """Codex counterexample 1: only `customer_name` changed for AVM-US / PRJ-CB-2026-01 — exactly
    one changed row on a stable key, an attribute change, zero measure changes, nothing added or
    removed."""
    report = relock_diff.diff(
        _side(LOCK_1, BASE, None, CERT_BEFORE), _side(LOCK_2, NAME_ONLY, None, CERT_AFTER)
    )
    balances = _balances(report)
    assert balances["totals"] == {
        "added": 0,
        "removed": 0,
        "changed": 1,
        "measure_changes": 0,
        "attribute_changes": 1,
    }
    (changed,) = balances["changed_rows"]  # type: ignore[misc]
    assert changed["key"] == {"entity_code": "AVM-US", "contract_external_id": "PRJ-CB-2026-01"}
    assert changed["columns"] == {
        "customer_name": {
            "kind": "attribute",
            "previous": "Castellan Build Group Inc. (Demo)",
            "current": "Castellan Build Group LLC (Demo)",
        }
    }


def test_name_and_amount_change_keeps_the_delta_on_one_row() -> None:
    """Codex counterexample 2: name and asset changed together — one changed row carrying the
    `customer_name` attribute change and the 32,558.82 measure delta; nothing added or removed."""
    report = relock_diff.diff(
        _side(LOCK_1, BASE, None, CERT_BEFORE), _side(LOCK_2, NAME_AND_AMOUNT, None, CERT_AFTER)
    )
    balances = _balances(report)
    assert balances["totals"] == {
        "added": 0,
        "removed": 0,
        "changed": 1,
        "measure_changes": 1,
        "attribute_changes": 1,
    }
    (changed,) = balances["changed_rows"]  # type: ignore[misc]
    assert changed["key"] == {"entity_code": "AVM-US", "contract_external_id": "PRJ-CB-2026-01"}
    assert changed["columns"]["contract_asset"] == {
        "kind": "measure",
        "previous": "97294.12",
        "current": "129852.94",
        "delta": "32558.82",
    }
    assert changed["columns"]["customer_name"]["kind"] == "attribute"


def test_key_table_covers_every_snapshot_kind_with_headers_of_its_dataset() -> None:
    """D-98 81: one entry per E-64 kind, each key column present in that kind's fixture header, the
    provenance stated; `key_columns_of` answers the table and refuses an unknown kind by name."""
    assert sorted(relock_diff.KEY_COLUMNS) == sorted(kind.value for kind in SnapshotKind)
    assert sorted(FIXTURE_HEADERS) == sorted(kind.value for kind in SnapshotKind)
    for kind, spec in relock_diff.KEY_COLUMNS.items():
        assert spec.columns, kind
        header = set(FIXTURE_HEADERS[kind])
        assert set(spec.columns) <= header, (kind, spec.columns)
        assert spec.source in {"builder", "design"} and spec.note, kind
        assert relock_diff.key_columns_of(kind) == spec.columns
        # CLO-7a-fix-2: entity and book columns of the header are part of the key (§15.2.7); a
        # header without them says so in the provenance note.
        for column in ("entity_code", "book", "book_code"):
            if column in header:
                assert column in spec.columns, (kind, column)
        if "entity_code" not in header:
            assert "neither `entity_code`" in spec.note, kind
        if not header & {"book", "book_code"}:
            assert "book column" in spec.note, kind
        # D-98 85: display labels are attribute columns, never key.
        labels = {"line_label", "category_label", "dimension_value_label", "timing", "cause"}
        assert not labels & set(spec.columns), kind
        # D-98 87: measures are declared — non-empty where §15.2.7 lists money totals, naming only
        # header columns (or patterns matching one), disjoint from the key.
        named = set(spec.measures)
        assert named <= header, (kind, named - header)
        assert not named & set(spec.columns), kind
        matched = {column for column in header if spec.is_measure(column)}
        assert matched >= named, kind
        assert matched, (
            kind
        )  # every kind declares at least one measure (S15-R-20c for the register)
        if kind == "MODIFICATION_REGISTER":
            # CTR-17 slice 1: exactly the two typed-money columns of the builder (D-98 140-A1 Q-9;
            # F-CLO's consent conditions: headers equal typed money, KEY_COLUMNS untouched).
            assert matched == {"tp_change", "catch_up_amount"}, kind
        for pattern in spec.measure_patterns:
            assert any(re.fullmatch(pattern, column) for column in header), (kind, pattern)
    assert relock_diff.key_columns_of("JE_POPULATION") == (
        "entity_code",
        "book",
        "je_no",
        "line_no",
    )
    assert relock_diff.key_columns_of("MANUAL_ADJUSTMENT_REGISTER") == (
        "entity_code",
        "adjustment_no",
    )
    with pytest.raises(relock_diff.RelockDiffRefusal) as refused:
        relock_diff.key_columns_of("BALANCE_SHEET")
    assert (refused.value.code, refused.value.kind) == (relock_diff.KIND_UNKNOWN, "BALANCE_SHEET")


def test_missing_key_column_and_duplicate_key_refuse_by_name() -> None:
    """No inference: a header without a key column and a key that repeats within one dataset are
    refusals naming the rule and the kind, never a fallback."""
    headless = DatasetSide(
        "CONTRACT_BALANCES", "d" * 64, 1, b"customer_name,contract_asset\nA,1.00\n"
    )
    with pytest.raises(relock_diff.RelockDiffRefusal) as missing:
        relock_diff.diff_dataset("CONTRACT_BALANCES", headless, headless)
    assert (missing.value.code, missing.value.kind) == (
        relock_diff.KEY_MISSING,
        "CONTRACT_BALANCES",
    )
    assert "entity_code, contract_external_id" in str(missing.value)
    dup = (
        b"entity_code,book,je_no,line_no,amount\n"
        b"AVM-US,ASC606,JE-1,1,10.00\n"
        b"AVM-US,ASC606,JE-1,1,20.00\n"
    )
    same = DatasetSide("JE_POPULATION", "e" * 64, 2, dup)
    with pytest.raises(relock_diff.RelockDiffRefusal) as duplicate:
        relock_diff.diff_dataset("JE_POPULATION", same, same)
    assert duplicate.value.code == relock_diff.KEY_DUPLICATE


def test_missing_kind_on_one_side_and_certification_change() -> None:
    before = LockSide(LOCK_1, None, [{"gate_check_code": "JE_COMPLETE", "status": "FAILED"}], {})
    after = LockSide(
        LOCK_2,
        "n" * 64,
        [{"gate_check_code": "JE_COMPLETE", "status": "PASSED"}],
        {"RPO": DatasetSide("RPO", "c" * 64, 1, RPO)},
    )
    report = relock_diff.diff(before, after)
    rpo = report["kinds"]["RPO"]
    assert (rpo["changed"], rpo["previous_file_sha256"], rpo["current_row_count"]) == (
        True,
        None,
        1,
    )
    assert rpo["totals"]["measure_changes"] == 0
    assert report["certification"]["changed"] == [
        {"gate_check_code": "JE_COMPLETE", "previous_status": "FAILED", "current_status": "PASSED"}
    ]
    assert report["manifest"]["changed"] is True


# --- CLO-7c canonical export identity (D-98 85; Codex CLO7-DIFF-R2 / R3) --------------------------

OOP_HEADER = (
    "event_key,contract_external_id,event_type,effective_date,recorded_at,origin_period_key,"
    "posting_period_key,reason_code,origin,currency,revenue_effect,balance_effect\n"
)
OOP_BEFORE = (
    OOP_HEADER
    + "event:PRJ-CB-2026-01:7,PRJ-CB-2026-01,COST_INCURRED,2026-09-29,2026-10-03T09:00:00Z,"
    "FY2026-P09,FY2026-P10,LATE_EVENT,UI,USD,32558.82,32558.82\n"
    + "event:PRJ-CB-2026-01:8,PRJ-CB-2026-01,COST_INCURRED,2026-09-29,2026-10-03T09:05:00Z,"
    "FY2026-P09,FY2026-P10,LATE_EVENT,UI,USD,1000.00,1000.00\n"
).encode()
OOP_AFTER = (
    OOP_HEADER
    + "event:PRJ-CB-2026-01:7,PRJ-CB-2026-01,COST_INCURRED,2026-09-29,2026-10-03T09:00:00Z,"
    "FY2026-P09,FY2026-P10,LATE_EVENT,UI,USD,32558.82,32558.82\n"
    + "event:PRJ-CB-2026-01:8,PRJ-CB-2026-01,COST_INCURRED,2026-09-29,2026-10-03T09:05:00Z,"
    "FY2026-P09,FY2026-P10,LATE_EVENT,UI,USD,1500.00,1500.00\n"
).encode()
RF_HEADER = (
    "section,line_code,line_label,contract_liability,contract_asset,unbilled_receivable,"
    "contract_external_id,customer_name,currency\n"
)
RF_BEFORE = (
    RF_HEADER
    + "1,OPENING,Opening balance,120000.00,0.00,0.00,,,USD\n"
    + "1,BILLINGS,Billings,15000.00,0.00,0.00,,,USD\n"
).encode()
RF_LABEL_ONLY = (
    RF_HEADER
    + "1,OPENING,Opening balance (brought forward),120000.00,0.00,0.00,,,USD\n"
    + "1,BILLINGS,Billings,15000.00,0.00,0.00,,,USD\n"
).encode()


def test_out_of_period_events_sharing_contract_type_and_date_stay_distinct() -> None:
    """CLO7-DIFF-R2: two events of one contract with the same type and effective date but different
    stream versions are two rows keyed by `event_key`, never collapsed; a change on the second is
    one changed row and the first is untouched."""
    before = DatasetSide("OUT_OF_PERIOD_REGISTER", "1" * 64, 2, OOP_BEFORE)
    after = DatasetSide("OUT_OF_PERIOD_REGISTER", "2" * 64, 2, OOP_AFTER)
    entry = relock_diff.diff_dataset("OUT_OF_PERIOD_REGISTER", before, after)
    assert entry["key_columns"] == ["origin_period_key", "posting_period_key", "event_key"]
    assert entry["totals"] == {
        "added": 0,
        "removed": 0,
        "changed": 1,
        "measure_changes": 2,
        "attribute_changes": 0,
    }
    (changed,) = entry["changed_rows"]
    assert changed["key"] == {
        "origin_period_key": "FY2026-P09",
        "posting_period_key": "FY2026-P10",
        "event_key": "event:PRJ-CB-2026-01:8",
    }
    assert changed["columns"]["revenue_effect"]["delta"] == "500.00"
    # Both rows are keyed distinctly on each side (no KEY_DUPLICATE, nothing added / removed).
    same = relock_diff.diff_dataset("OUT_OF_PERIOD_REGISTER", before, before)
    assert same["totals"]["changed"] == 0 and same["previous_row_count"] == 2


def test_rollforward_label_only_change_is_an_attribute_change() -> None:
    """CLO7-DIFF-R3: the rollforward row is keyed by `line_code`; a relabelled `line_label` is one
    changed row with one attribute change and no measure change."""
    before = DatasetSide("CONTRACT_BALANCE_ROLLFORWARD", "3" * 64, 2, RF_BEFORE)
    after = DatasetSide("CONTRACT_BALANCE_ROLLFORWARD", "4" * 64, 2, RF_LABEL_ONLY)
    entry = relock_diff.diff_dataset("CONTRACT_BALANCE_ROLLFORWARD", before, after)
    assert entry["key_columns"] == ["line_code", "contract_external_id", "currency"]
    assert entry["totals"] == {
        "added": 0,
        "removed": 0,
        "changed": 1,
        "measure_changes": 0,
        "attribute_changes": 1,
    }
    (changed,) = entry["changed_rows"]
    assert changed["key"] == {"line_code": "OPENING", "contract_external_id": "", "currency": "USD"}
    assert changed["columns"] == {
        "line_label": {
            "kind": "attribute",
            "previous": "Opening balance",
            "current": "Opening balance (brought forward)",
        }
    }


def test_rollforward_without_line_code_refuses_by_name() -> None:
    """A rollforward dataset whose header carries only the label refuses by name — never keyed on
    `line_label` or `section`."""
    labelled = DatasetSide(
        "CONTRACT_BALANCE_ROLLFORWARD",
        "5" * 64,
        1,
        b"section,line_label,currency,contract_liability\n1,Opening balance,USD,120000.00\n",
    )
    with pytest.raises(relock_diff.RelockDiffRefusal) as refused:
        relock_diff.diff_dataset("CONTRACT_BALANCE_ROLLFORWARD", labelled, labelled)
    assert (refused.value.code, refused.value.kind) == (
        relock_diff.KEY_MISSING,
        "CONTRACT_BALANCE_ROLLFORWARD",
    )
    assert "line_code, contract_external_id" in str(refused.value)


# --- CLO-7d declared measures (D-98 87; Codex CLO7-ATTR-R1) -----------------------------------

NUMERIC_NAME_BEFORE = (
    HEADER + "PRJ-CB-2026-01,123,AVM-US,USD,0.00,97294.12\n" + PELLWORTH
).encode()
NUMERIC_NAME_AFTER = (HEADER + "PRJ-CB-2026-01,456,AVM-US,USD,0.00,97294.12\n" + PELLWORTH).encode()
LIABILITY_MOVED = (
    HEADER
    + CASTELLAN.format(asset="97294.12")
    + "SF-ORD-10001,Pellworth Logistics Inc. (Demo),AVM-US,USD,40000.00,0.00\n"
).encode()
NOT_DECIMAL = (HEADER + "PRJ-CB-2026-01,Castellan,AVM-US,USD,n/a,97294.12\n" + PELLWORTH).encode()


def test_numeric_looking_name_change_is_an_attribute_change_not_a_delta() -> None:
    """CLO7-ATTR-R1 control: `customer_name` "123" → "456" with every amount unchanged is one
    changed row, one attribute change, zero measure changes and no delta — classification is by the
    declared measures, never by value shape."""
    report = relock_diff.diff(
        _side(LOCK_1, NUMERIC_NAME_BEFORE, None, CERT_BEFORE),
        _side(LOCK_2, NUMERIC_NAME_AFTER, None, CERT_AFTER),
    )
    balances = _balances(report)
    assert balances["totals"] == {
        "added": 0,
        "removed": 0,
        "changed": 1,
        "measure_changes": 0,
        "attribute_changes": 1,
    }
    (changed,) = balances["changed_rows"]  # type: ignore[misc]
    assert changed["columns"] == {
        "customer_name": {"kind": "attribute", "previous": "123", "current": "456"}
    }
    assert "delta" not in changed["columns"]["customer_name"]


def test_declared_measure_change_carries_the_exact_delta() -> None:
    """A genuine monetary change on a declared measure: `contract_liability` 39,708.49 → 40,000.00
    is one measure change with delta 291.51 and no attribute change."""
    report = relock_diff.diff(
        _side(LOCK_1, BASE, None, CERT_BEFORE), _side(LOCK_2, LIABILITY_MOVED, None, CERT_AFTER)
    )
    balances = _balances(report)
    assert balances["totals"] == {
        "added": 0,
        "removed": 0,
        "changed": 1,
        "measure_changes": 1,
        "attribute_changes": 0,
    }
    (changed,) = balances["changed_rows"]  # type: ignore[misc]
    assert changed["key"] == {"entity_code": "AVM-US", "contract_external_id": "SF-ORD-10001"}
    assert changed["columns"] == {
        "contract_liability": {
            "kind": "measure",
            "previous": "39708.49",
            "current": "40000.00",
            "delta": "291.51",
        }
    }


def test_declared_measure_with_a_non_decimal_value_refuses_by_name() -> None:
    """A declared measure holding "n/a" is a refusal naming the rule, the kind and the column —
    never reclassified as an attribute."""
    before = DatasetSide("CONTRACT_BALANCES", "6" * 64, 2, BASE)
    after = DatasetSide("CONTRACT_BALANCES", "7" * 64, 2, NOT_DECIMAL)
    with pytest.raises(relock_diff.RelockDiffRefusal) as refused:
        relock_diff.diff_dataset("CONTRACT_BALANCES", before, after)
    assert (refused.value.code, refused.value.kind) == (
        relock_diff.MEASURE_NOT_DECIMAL,
        "CONTRACT_BALANCES",
    )
    assert "contract_liability" in str(refused.value) and "n/a" in str(refused.value)


def test_empty_measure_cell_is_absent_and_carries_no_delta() -> None:
    """An empty measure cell is an absent value: the change is a measure change without a delta,
    not a refusal and not an attribute."""
    header = "line_code,line_label,contract_external_id,currency,opening\n"
    before = DatasetSide(
        "RPO_ROLLFORWARD", "8" * 64, 1, (header + "OPENING,Opening RPO,,USD,\n").encode()
    )
    after = DatasetSide(
        "RPO_ROLLFORWARD", "9" * 64, 1, (header + "OPENING,Opening RPO,,USD,100.00\n").encode()
    )
    entry = relock_diff.diff_dataset("RPO_ROLLFORWARD", before, after)
    (changed,) = entry["changed_rows"]
    assert changed["columns"] == {
        "opening": {"kind": "measure", "previous": "", "current": "100.00"}
    }
    assert entry["totals"]["measure_changes"] == 1


# --- CLO-7e RPO band declaration (Codex CLO7-MEASURE-R1) ---------------------------------------

RPO_BANDS_HEADER = (
    "section,contract_external_id,customer_name,entity_code,currency,total,within_12_months,"
    "months_13_to_24,after_24_months,current,noncurrent,obligation_key\n"
)
# Codex's fixed input (PRODUCTION-F-CLO-CLO7D-NATIVE-RETEST-226f775.md): months_13_to_24
# 1000 → 1500, within_12_months −500, total 552,705.88 unchanged; every other column unchanged.
RPO_BANDS_BEFORE = (
    RPO_BANDS_HEADER
    + "1,PRJ-CB-2026-01,Castellan,AVM-US,USD,552705.88,551705.88,1000.00,0.00,551705.88,"
    "1000.00,O1\n"
).encode()
RPO_BANDS_AFTER = (
    RPO_BANDS_HEADER
    + "1,PRJ-CB-2026-01,Castellan,AVM-US,USD,552705.88,551205.88,1500.00,0.00,551705.88,"
    "1000.00,O1\n"
).encode()


def test_rpo_band_redistribution_is_two_measure_changes_with_opposite_deltas() -> None:
    """CLO7-MEASURE-R1 (Codex's fixed input): the builder's middle band is
    `months_<lower>_to_<upper>` (rpo.bands_of), a declared measure; `months_13_to_24` 1000 → 1500
    and `within_12_months` −500 with the total 552,705.88 unchanged are exactly two measure changes
    with deltas +500.00 / −500.00, zero attribute changes, nothing added or removed."""
    spec = relock_diff.KEY_COLUMNS["RPO"]
    bands = ("within_12_months", "months_13_to_24", "after_24_months")
    assert [spec.is_measure(column) for column in bands] == [True, True, True]
    assert not spec.is_measure("13_to_24_months")  # the reversed spelling is not a band
    before = DatasetSide("RPO", "a1" * 32, 1, RPO_BANDS_BEFORE)
    after = DatasetSide("RPO", "a2" * 32, 1, RPO_BANDS_AFTER)
    entry = relock_diff.diff_dataset("RPO", before, after)
    assert entry["totals"] == {
        "added": 0,
        "removed": 0,
        "changed": 1,
        "measure_changes": 2,
        "attribute_changes": 0,
    }
    (changed,) = entry["changed_rows"]
    assert changed["columns"] == {
        "within_12_months": {
            "kind": "measure",
            "previous": "551705.88",
            "current": "551205.88",
            "delta": "-500.00",
        },
        "months_13_to_24": {
            "kind": "measure",
            "previous": "1000.00",
            "current": "1500.00",
            "delta": "500.00",
        },
    }


# --- PRIOR_PERIOD_POB_REVENUE declared measures (ENG-C4 builder shape; team lead 2026-09-20) ---

PRIOR_HEADER = (
    "entity_code,contract_external_id,obligation_key,product_code,satisfied_period_key,cause,"
    "currency,from_price_changes,from_estimate_changes,from_modifications,from_late_events,"
    "from_other,revenue\n"
)
PRIOR_BEFORE = (
    PRIOR_HEADER
    + "AVM-US,PRJ-CB-2026-01,O1,AVM-ENG-BUILD,FY2026-P08,Estimate change,USD,0.00,-29169.29,"
    "91463.41,0.00,0.00,62294.12\n"
).encode()
PRIOR_AFTER = (
    PRIOR_HEADER
    + "AVM-US,PRJ-CB-2026-01,O1,AVM-ENG-BUILD,FY2026-P08,Estimate change,USD,0.00,-30000.00,"
    "91463.41,0.00,0.00,61463.41\n"
).encode()


def test_every_money_column_of_the_rpo_rollforward_is_a_declared_measure() -> None:
    """The re-lock difference reports a moved amount of the RPO rollforward as a measure change
    with its delta (D-98 87): every money column of the report on this tree, the line
    ``late_events`` among them (ENGINE_SPEC_B S15-R-12 rev 1.161; item RPT-RPO-ROLLFWD-1). The
    measures are a list of their own in ``relock_diff``, so a line added to the report alone would
    be compared as an attribute, without a delta; this pin ties the two, and the fixture header
    of this module to the report's columns.

    Fail-first (the line in the report, not in the list): ``late_events`` was no measure."""
    from erev_api.domain.reports.builders import rpo_rollforward

    spec = relock_diff.KEY_COLUMNS["RPO_ROLLFORWARD"]
    money = [column.key for column in rpo_rollforward.COLUMNS if column.kind == "money"]
    assert "late_events" in money
    assert [key for key in money if not spec.is_measure(key)] == []
    assert sorted(spec.measures) == sorted(money)
    assert FIXTURE_HEADERS["RPO_ROLLFORWARD"] == [column.key for column in rpo_rollforward.COLUMNS]
    header = ",".join(("line_code", "contract_external_id", "currency", "late_events"))
    before = DatasetSide("RPO_ROLLFORWARD", "c1" * 32, 1, f"{header}\n,K-01,USD,0.00\n".encode())
    after = DatasetSide("RPO_ROLLFORWARD", "c2" * 32, 1, f"{header}\n,K-01,USD,-6480.00\n".encode())
    (changed,) = relock_diff.diff_dataset("RPO_ROLLFORWARD", before, after)["changed_rows"]
    assert changed["columns"] == {
        "late_events": {
            "kind": "measure",
            "previous": "0.00",
            "current": "-6480.00",
            "delta": "-6480.00",
        }
    }


def test_prior_period_cause_components_are_declared_measures() -> None:
    """The six money columns of ENG-C4's `revenue_from_prior_period_obligations` shape are declared
    measures of PRIOR_PERIOD_POB_REVENUE: a moved `from_estimate_changes` and the `revenue` it
    carries are two measure changes with deltas (D-98 87), never attribute changes; the key stays
    (entity_code, contract_external_id, obligation_key) and `cause` / `satisfied_period_key` are
    attributes."""
    spec = relock_diff.KEY_COLUMNS["PRIOR_PERIOD_POB_REVENUE"]
    assert spec.columns == ("entity_code", "contract_external_id", "obligation_key")
    assert spec.measures == (
        "from_price_changes",
        "from_estimate_changes",
        "from_modifications",
        "from_late_events",
        "from_other",
        "revenue",
    )
    assert not spec.is_measure("cause") and not spec.is_measure("satisfied_period_key")
    before = DatasetSide("PRIOR_PERIOD_POB_REVENUE", "b1" * 32, 1, PRIOR_BEFORE)
    after = DatasetSide("PRIOR_PERIOD_POB_REVENUE", "b2" * 32, 1, PRIOR_AFTER)
    entry = relock_diff.diff_dataset("PRIOR_PERIOD_POB_REVENUE", before, after)
    assert entry["totals"] == {
        "added": 0,
        "removed": 0,
        "changed": 1,
        "measure_changes": 2,
        "attribute_changes": 0,
    }
    (changed,) = entry["changed_rows"]
    assert changed["columns"] == {
        "from_estimate_changes": {
            "kind": "measure",
            "previous": "-29169.29",
            "current": "-30000.00",
            "delta": "-830.71",
        },
        "revenue": {
            "kind": "measure",
            "previous": "62294.12",
            "current": "61463.41",
            "delta": "-830.71",
        },
    }
