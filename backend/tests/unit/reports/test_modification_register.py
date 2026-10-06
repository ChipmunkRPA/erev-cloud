"""RPT-14 ``modification_register`` pure core — the governed ``MODIFICATION_REGISTER`` dataset
(SCREENS_B §5.6.2 RPT-14 rev 1.23; ENGINE_SPEC_B §15.2.7 S15-R-20a / S15-R-20c; 04 T-CON-06;
REQ-MOD-014; BUILD_SPEC CTR-17 slice 1, RPS-8; D-98 140-A1; lane F-CTR).

No database: the sources are the K-02 upgrade ``CR-MARROWBY-2026-09`` (PRD WLD-X-06: TP change
+60,000.00, catch-up 0.00; BUILD_SPEC RPS-8 ``test_modification_register_k02``) and a two-line
Castellan modification written here; ``build`` / ``sources`` (the readers) are exercised by the
RPS-8 database test once a DB slot is admitted.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import uuid4

import pytest
from erev_api.domain.close import relock_diff
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import modification_register as register
from erev_api.domain.reports.builders.modification_register import (
    COLUMNS,
    GRID_FIELDS,
    KEY_COLUMNS,
    MEASURES,
    ModificationRegisterRefusal,
    Source,
    applied_catch_up,
    applied_event_reference,
    bind_application_version,
    check_key_columns,
    check_view,
    control_totals,
    dataset_rows,
    historical_status_refusal,
    population_filter,
    shared_catch_up,
)
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.problems import Problem
from support.architecture import read

RPT_14: Final = "##### RPT-14 `modification_register` Modification register"
_GRID_ROW: Final = re.compile(r"^\| ([A-Z][^|`]*?) \| `([a-z_0-9.]+)` \|")
ENTERED: Final = datetime(2026, 9, 16, 14, 5, tzinfo=UTC)
APPROVED: Final = datetime(2026, 9, 17, 9, 30, tzinfo=UTC)


def _source(**overrides: Any) -> Source:
    values: dict[str, Any] = {
        "modification_no": "MOD-000001",
        "reference": "CR-MARROWBY-2026-09",
        "contract_external_id": "SF-ORD-10002",
        "entity_code": "AVM-US",
        "functional_currency": "USD",
        "kind": "UPGRADE",
        "effective_date": date(2026, 9, 16),
        "created_at": ENTERED,
        "status": "APPLIED",
        "proposed_treatments": {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"},
        "chosen_treatments": {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"},
        "judgement_no": None,
        "questionnaire": {
            "added_goods_distinct": True,
            "priced_at_ssp": False,
            "remaining_goods_distinct_from_transferred": True,
        },
        "obligation_keys": ("O2",),
        "currency": "USD",
        "tp_change": Decimal("60000.00"),
        "catch_up": {"O1": Decimal("0"), "O2": Decimal("0")},
        "approval_request_no": "AR-000042",
        "approved_at": APPROVED,
        "impact_preview_sha256": "a" * 64,
        "applied_event_key": "event:SF-ORD-10002:5",
        "preparer": "Maya Chen",
        "approvers": "Priya Natarajan",
    }
    values.update(overrides)
    return Source(**values)


def test_header_is_the_governed_shape() -> None:
    """S15-R-20c: key code columns first (F-CLO's KeySpec, unchanged), then code and measure
    columns, then attributes; the two declared measures are typed money; every row carries
    ``currency``; the header carries neither ``entity_code`` nor a book column."""
    keys = [column.key for column in COLUMNS]
    assert tuple(keys[:3]) == KEY_COLUMNS
    assert relock_diff.key_columns_of("MODIFICATION_REGISTER") == KEY_COLUMNS
    spec = relock_diff.KEY_COLUMNS["MODIFICATION_REGISTER"]
    assert spec.measures == MEASURES  # F-CLO's consent: exactly the two typed-money columns
    kinds = {column.key: column.kind for column in COLUMNS}
    assert all(kinds[measure] == "money" for measure in MEASURES)
    assert "currency" in keys and "entity_code" not in keys and "book" not in keys
    assert keys[-6:] == [
        "reference",
        "kind_label",
        "proposed_treatment_label",
        "chosen_treatment_label",
        "preparer",
        "approvers",
    ]
    assert len(set(keys)) == len(keys)


def test_k02_upgrade_row_reference_figures_and_answers() -> None:
    """BUILD_SPEC RPS-8 ``test_modification_register_k02`` figures on the pure core: reference
    ``CR-MARROWBY-2026-09``, effective 16 Sep 2026, entered UTC timestamp, answers Yes / No / Yes,
    proposed and chosen treatment Prospective, approver, TP change 60,000.00, catch-up 0.00 for
    the added line O2 (PRD WLD-X-06; REQ-MOD-014)."""
    (row,) = dataset_rows([_source()])
    assert row["row_key"] == "modification:MOD-000001:O2"
    assert (row["contract_external_id"], row["modification_no"], row["obligation_key"]) == (
        "SF-ORD-10002",
        "MOD-000001",
        "O2",
    )
    assert row["reference"] == "CR-MARROWBY-2026-09"
    assert (row["effective_date"], row["created_at"]) == (date(2026, 9, 16), ENTERED)
    assert (
        row["added_goods_distinct"],
        row["priced_at_ssp"],
        row["remaining_goods_distinct_from_transferred"],
    ) == (True, False, True)
    assert (row["proposed_treatment"], row["chosen_treatment"]) == ("PROSPECTIVE", "PROSPECTIVE")
    assert (row["proposed_treatment_label"], row["treatment_override"]) == ("Prospective", False)
    assert row["kind_label"] == "Upgrade"
    assert row["tp_change"] == {"amount": "60000.00", "currency": "USD"}
    assert row["catch_up_amount"] == {"amount": "0.00", "currency": "USD"}
    assert (row["preparer"], row["approvers"], row["approved_at"]) == (
        "Maya Chen",
        "Priya Natarajan",
        APPROVED,
    )
    assert row["applied_event_key"] == "event:SF-ORD-10002:5"
    assert row["status"] == "APPLIED"


def test_rows_per_line_in_key_order_with_override_and_per_obligation_answers() -> None:
    """One row per modification × obligation line, ordered by the row key across contracts; a
    chosen treatment differing from the proposal marks ``treatment_override``; a per-obligation
    questionnaire object wins over the contract-level answer; unanswered → empty."""
    castellan = _source(
        modification_no="MOD-000002",
        reference="CR-CASTELLAN-2026-09",
        contract_external_id="PRJ-CB-2026-01",
        kind="PRICE_CHANGE",
        effective_date=date(2026, 9, 10),
        proposed_treatments={"O1": "PROSPECTIVE", "O2": "CUMULATIVE_CATCH_UP"},
        chosen_treatments={"O1": "CUMULATIVE_CATCH_UP", "O2": "CUMULATIVE_CATCH_UP"},
        judgement_no="JR-000007",
        questionnaire={"O1": {"added_goods_distinct": False}, "priced_at_ssp": True},
        obligation_keys=("O2", "O1"),
        tp_change=Decimal("0"),
        catch_up={"O1": Decimal("91463.41"), "O2": Decimal("-1200.00")},
    )
    rows = dataset_rows([_source(), castellan])
    assert [row["row_key"] for row in rows] == [
        "modification:MOD-000002:O1",
        "modification:MOD-000002:O2",
        "modification:MOD-000001:O2",
    ]  # PRJ-CB-2026-01 sorts before SF-ORD-10002; O1 before O2
    o1, o2 = rows[0], rows[1]
    assert (o1["treatment_override"], o2["treatment_override"]) == (True, False)
    assert o1["chosen_treatment_label"] == "Cumulative catch-up"
    assert o1["judgement_no"] == "JR-000007"
    assert (o1["added_goods_distinct"], o1["priced_at_ssp"]) == (False, True)
    assert (o2["added_goods_distinct"], o2["remaining_goods_distinct_from_transferred"]) == (
        None,
        None,
    )
    assert o1["catch_up_amount"] == {"amount": "91463.41", "currency": "USD"}
    assert o2["catch_up_amount"] == {"amount": "-1200.00", "currency": "USD"}
    assert o1["tp_change"] == {"amount": "0.00", "currency": "USD"}
    check_key_columns(rows)


def test_empty_measures_and_control_totals_without_total_rows() -> None:
    """A DRAFT / REJECTED / VOIDED modification carries empty measures (never 0); the totals per
    currency are control totals — ``tp_change_total`` counts each modification once, not per
    line — and the dataset carries no TOTAL row (F-RPS's registry contract)."""
    draft = _source(
        modification_no="MOD-000003",
        status="DRAFT",
        tp_change=None,
        catch_up=None,
        approval_request_no=None,
        approved_at=None,
        impact_preview_sha256=None,
        applied_event_key=None,
        approvers=None,
    )
    two_lines = _source(
        modification_no="MOD-000004",
        contract_external_id="SF-ORD-10009",
        currency="EUR",
        functional_currency="EUR",
        obligation_keys=("O1", "O2"),
        tp_change=Decimal("1000.00"),
        catch_up={"O1": Decimal("10.00"), "O2": Decimal("5.00")},
    )
    rows = dataset_rows([_source(), draft, two_lines])
    assert all(row["obligation_key"] for row in rows)
    (draft_row,) = [row for row in rows if row["modification_no"] == "MOD-000003"]
    assert (draft_row["tp_change"], draft_row["catch_up_amount"]) == (None, None)
    assert (draft_row["approvers"], draft_row["applied_event_key"]) == (None, None)
    totals = control_totals(rows)
    assert totals == {
        "row_count": 4,
        "modification_count": 3,
        "tp_change_total": {"EUR": "1000.00", "USD": "60000.00"},
        "catch_up_total": {"EUR": "15.00", "USD": "0.00"},
    }
    assert not any(str(row["modification_no"]).startswith("TOTAL") for row in rows)


def test_refusals_by_name() -> None:
    """A row without a key column, or two rows of one key, refuse by name — never a proxy, a
    default or a dropped row (S15-R-20a); the functional view refuses when a modification is not
    in its entity's functional currency (RPT-07 pattern), the transaction view never."""
    with pytest.raises(ModificationRegisterRefusal) as missing:
        check_key_columns([{"row_key": "x", "contract_external_id": "A", "modification_no": ""}])
    assert missing.value.column == "modification_no"
    row = dataset_rows([_source()])[0]
    with pytest.raises(ModificationRegisterRefusal) as twice:
        check_key_columns([row, dict(row)])
    assert "occurs twice" in str(twice.value)
    foreign = _source(currency="EUR", functional_currency="USD")
    check_view("transaction", [foreign])
    with pytest.raises(Problem) as refused:
        check_view("functional", [foreign])
    (error,) = refused.value.errors
    assert error.field == "parameters.currency_view"
    assert "functional currency view" in error.message
    check_view("functional", [_source()])


def test_rpt_14_grid_fields_are_the_builder_columns() -> None:
    """SCREENS_B RPT-14 (rev 1.23): every grid field maps to a builder column with the grid's
    header (a dotted questionnaire field to its last segment); the frozen-dataset paragraph names
    the S15-R-20c shape; the row key and the E-25 / E-23 labels are the module's."""
    section = read("docs/design/SCREENS_B.md").split(RPT_14, 1)[1].split("#####", 1)[0]
    grid = [
        (match.group(1).strip(), match.group(2))
        for line in section.splitlines()
        if (match := _GRID_ROW.match(line)) is not None
    ]
    assert grid, "the RPT-14 grid parsed"
    headers = {column.key: column.header for column in COLUMNS}
    assert {field for _, field in grid} == set(GRID_FIELDS)
    for header, field in grid:
        column = GRID_FIELDS[field]
        assert column == field.rsplit(".", 1)[-1], field
        assert headers[column] == header, (field, header, headers[column])
    assert "`row_key` `modification:<modification no>:<obligation key>`" in section
    assert "**Frozen dataset (rev 1.23; ENGINE_SPEC_B S15-R-20c; D-98 140-A1).**" in section
    for column in COLUMNS:
        assert f"`{column.key}`" in section, column.key
    for label in register.KIND_LABELS.values():
        assert f'"{label}"' in section, label
    for label in register.TREATMENT_LABELS.values():
        assert f'"{label}"' in section, label


def test_registered_with_its_defaults_and_open_source_contract() -> None:
    """``framework.BUILDERS`` admits the code (18 → 19); the SCREENS_B RPT-14 status default and
    the rev 1.23 transaction view are the run's stored defaults; the source contract is OPEN (a
    rerun is a new live evaluation) and the catalogue row is the RPT-14 definition."""
    assert framework.BUILDERS[register.CODE] is register.build
    assert framework.PARAMETER_DEFAULTS[register.CODE] == {
        "status": ["APPLIED", "APPROVED"],
        "currency_view": "transaction",
    }
    assert framework.SOURCE_CONTRACTS[register.CODE].strategy == "open"
    assert framework.SOURCE_CONTRACTS[register.CODE].open
    definition = DEFINITIONS_BY_CODE[register.CODE]
    assert definition.kind == "REGISTER"
    assert set(definition.parameters_schema["properties"]) >= {
        "entity_codes",
        "book",
        "from_date",
        "to_date",
        "status",
        "contract_external_id",
        "currency_view",
    }
    assert "period_lock_id" in definition.parameters_schema["properties"]  # CLO-8b (F-CLO)


# --- D-98 140-A8 (Codex production-20260921-1854 §2) register returns, CPU witnesses ------------


def test_register_catchup_1_catch_up_binds_the_caused_versions_obligation_rows_only() -> None:
    """REGISTER-CATCHUP-1: the persisted provenance is the contract version the applied event
    caused (``cause_event_ids``); its obligation versions of the modification's contract and line
    keys give the catch-up — zero and nonzero read as stored; a key without such a row is ABSENT
    (an empty cell), never a substituted zero; another contract's rows of the same version (a
    combined group) are ignored; ``last_modification_id`` plays no part."""
    mine, other = uuid4(), uuid4()
    version_rows = [
        {"contract_id": mine, "obligation_key": "O1", "catch_up_amount": Decimal("0.00")},
        {"contract_id": mine, "obligation_key": "O2", "catch_up_amount": Decimal("91463.41")},
        {"contract_id": other, "obligation_key": "O3", "catch_up_amount": Decimal("5.00")},
    ]
    found = applied_catch_up(version_rows, contract_id=mine, keys=["O1", "O2", "O3", "O9"])
    assert found == {"O1": Decimal("0.00"), "O2": Decimal("91463.41")}
    assert "O3" not in found and "O9" not in found  # other contract / no row → empty cells
    rows = dataset_rows([_source(obligation_keys=("O2", "O9"), catch_up=found)])
    by_key = {row["obligation_key"]: row for row in rows}
    assert by_key["O2"]["catch_up_amount"] == {"amount": "91463.41", "currency": "USD"}
    assert by_key["O9"]["catch_up_amount"] is None  # absent, not zero


def test_register_event_1_applied_event_key_names_the_events_owner() -> None:
    """REGISTER-EVENT-1: an amendment's applied event belongs to the original contract; a
    separate-contract booking's applied event belongs to the NEW contract — the key names the
    owner (CV-21-encoded) while the row key keeps the original contract; None until APPLIED."""
    assert applied_event_reference(("SF-ORD-10002", 5)) == "event:SF-ORD-10002:5"
    assert applied_event_reference(("SF-ORD-10388", 1)) == "event:SF-ORD-10388:1"
    assert applied_event_reference(("A:B|C", 2)) == "event:A%3AB%7CC:2"
    assert applied_event_reference(None) is None
    (row,) = dataset_rows([_source(applied_event_key=applied_event_reference(("SF-ORD-10388", 1)))])
    assert row["contract_external_id"] == "SF-ORD-10002"  # the original stays the row key
    assert row["applied_event_key"] == "event:SF-ORD-10388:1"
    assert row["row_key"] == "modification:MOD-000001:O2"


def test_register_cutoff_1_historical_read_refuses_a_status_that_changed_later() -> None:
    """REGISTER-CUTOFF-1: an explicit historical read whose cutoff precedes a row's last change is
    refused by name (T-CON-06 keeps no row history — the copy names status, effective date and the
    authored members, Codex 2043); a live (record-basis) run never refuses here; a historical read
    at or after every change is served."""
    changed = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    rows = [{"modification_no": "MOD-000001", "updated_at": changed}]
    before, after = changed - timedelta(minutes=1), changed + timedelta(minutes=1)
    refusal = historical_status_refusal(rows, cutoff=before, historical=True)
    assert refusal is not None and "MOD-000001" in refusal and "no row history" in refusal
    assert "effective date" in refusal and "not reconstructed, not narrowed" in refusal
    assert historical_status_refusal(rows, cutoff=after, historical=True) is None
    assert historical_status_refusal(rows, cutoff=changed, historical=True) is None
    assert historical_status_refusal(rows, cutoff=before, historical=False) is None


# --- D-98 140-A10 / A11 (Codex 1931 / 1941) register qualifications, CPU witnesses ----------


def test_a11_application_version_is_bound_to_the_owners_group_never_the_first_match() -> None:
    """REGISTER-CATCHUP-1 (A11): a later approved JOIN re-includes the applied event in the joined
    group's first version, so two versions hold it — the version of the group the owner belonged to
    at application is bound; none → no measures yet; two in that group → refused by name."""
    singleton, joined = uuid4(), uuid4()
    original = {"id": uuid4(), "combination_group_id": singleton, "transaction_price": "300000.00"}
    rejoined = {"id": uuid4(), "combination_group_id": joined, "transaction_price": "540000.00"}
    bound = bind_application_version(
        [rejoined, original], group_id=singleton, modification_no="MOD-1", book_code="ASC606"
    )
    assert bound is original  # not the first candidate
    assert (
        bind_application_version(
            [], group_id=singleton, modification_no="MOD-1", book_code="ASC606"
        )
        is None
    )
    with pytest.raises(ModificationRegisterRefusal) as refused:
        bind_application_version(
            [original, {**original, "id": uuid4()}],
            group_id=singleton,
            modification_no="MOD-1",
            book_code="ASC606",
        )
    assert refused.value.column == "catch_up_amount"
    assert "2 contract versions" in str(refused.value) and "MOD-1" in str(refused.value)


def test_a10_shared_catch_up_counts_the_modification_events_of_a_version() -> None:
    """A version caused by several modification events shares its catch-up and is never split or
    zeroed — the count above one drives the named refusal in ``_applied_measures``."""
    assert shared_catch_up(["CONTRACT_AMENDED", "BILLING_RECORDED", "DELIVERY_RECORDED"]) == 1
    assert shared_catch_up(["CONTRACT_AMENDED", "REGROUPED"]) == 2
    assert shared_catch_up(["CONTRACT_AMENDED", "CONTRACT_TERMINATED", "REGROUPED"]) == 3
    assert shared_catch_up([]) == 0


def test_a11_historical_population_is_inspected_before_the_status_filter() -> None:
    """REGISTER-CUTOFF-1 (A10 / A11; source witness — the DB witness is NOT RUN): ``sources``
    fetches the candidates without a status predicate, runs ``historical_status_refusal`` over ALL
    of them, then applies the status filter — so a SUBMITTED-then-REJECTED row is refused by name,
    never dropped from a historical ``status = [SUBMITTED]`` run."""
    import inspect

    source = inspect.getsource(register.sources)
    assert "modification.c.status.in_(" not in source
    refusal = source.index("historical_status_refusal(")
    status_filter = source.index("population_filter(")  # A13: date + status applied afterwards
    assert refusal < status_filter
    catch_up = inspect.getsource(register._applied_measures)
    assert catch_up.index("bind_application_version(") < catch_up.index("shared_catch_up(")
    assert "CATCH_UP_SHARED" in catch_up and "APPLICATION_AMBIGUOUS" in inspect.getsource(
        register.bind_application_version
    )


def test_a13_historical_population_is_inspected_before_the_mutable_date_exclusion() -> None:
    """D-98 140-A13 REGISTER-CUTOFF-1 follow-through (source + pure witness; the DB witness is
    NOT RUN): on a historical run ``sources`` reads the population WITHOUT the effective-date
    predicate, inspects it (``historical_status_refusal``), then ``population_filter`` applies the
    date range and statuses — a DRAFT PATCHed from July to August after the cutoff is refused,
    never dropped; a live run keeps the SQL date predicate (the current dates are the truth)."""
    import inspect

    source = inspect.getsource(register.sources)
    live_only = source.index("if not params.historical:")
    assert live_only < source.index("modification.c.effective_date >= from_date")
    assert source.index("historical_status_refusal(") < source.index("population_filter(")
    changed = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    rows = [
        {
            "modification_no": "MOD-1",
            "effective_date": date(2026, 8, 1),
            "status": "DRAFT",
            "updated_at": changed,
        },
        {
            "modification_no": "MOD-2",
            "effective_date": date(2026, 7, 15),
            "status": "DRAFT",
            "updated_at": changed,
        },
        {
            "modification_no": "MOD-3",
            "effective_date": date(2026, 7, 20),
            "status": "APPLIED",
            "updated_at": changed,
        },
    ]
    july = population_filter(
        rows, from_date=date(2026, 7, 1), to_date=date(2026, 7, 31), statuses=["DRAFT"]
    )
    assert [row["modification_no"] for row in july] == ["MOD-2"]
    # the refusal sees MOD-1 (moved to August after the cutoff) BEFORE the July filter drops it
    assert historical_status_refusal(rows, cutoff=changed - timedelta(minutes=1), historical=True)
    assert historical_status_refusal(rows, cutoff=changed, historical=True) is None
