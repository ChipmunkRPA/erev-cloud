"""RPT-19 to RPT-22 SSP report builders — CPU witnesses (BUILD_SPEC RPS-9; SCREENS_B §5.6.4). The
specification grids are parsed from SCREENS_B, so a specification edit or a builder column drift
fails here; the row shaping is proven on pure inputs. The acceptance over worlds built through the
product's commands is ``tests/domain/reports/test_ssp_reports.py`` (database).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import allocations_by_ssp_version as allocations
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.builders import ssp_change_log as change_log
from erev_api.domain.reports.builders import ssp_override_listing as overrides
from erev_api.domain.reports.builders import ssp_version_diff as version_diff
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.domain.ssp import books
from erev_api.problems import Problem
from support import report_specs

MAYA: UUID = UUID("00000000-0000-4000-8000-00000000000a")
PRIYA: UUID = UUID("00000000-0000-4000-8000-00000000000b")
MARCUS: UUID = UUID("00000000-0000-4000-8000-00000000000c")
BOOK: UUID = UUID("00000000-0000-4000-8000-0000000000b0")
H1: UUID = UUID("00000000-0000-4000-8000-0000000000b1")
H2: UUID = UUID("00000000-0000-4000-8000-0000000000b2")
NAMES = {MAYA: "Maya Chen", PRIYA: "Priya Raman", MARCUS: "Marcus Webb"}
AT: datetime = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
MODULES = (
    (19, change_log),
    (20, version_diff),
    (21, allocations),
    (22, overrides),
)


# --- specification and registration ---------------------------------------------------------------


@pytest.mark.parametrize(("number", "module"), MODULES)
def test_columns_are_the_specification_grid(number: int, module: Any) -> None:
    """SCREENS_B §5.6.4: the builder's columns are the grid's fields in its order; RPT-21 adds the
    REQ-SSP-011 value row id ``ssp_entry_id`` (export and API only; SCREENS_B rev 1.25)."""
    keys = [column.key for column in module.COLUMNS]
    assert keys == report_specs.fields(number, module.CODE)
    assert len(set(keys)) == len(keys) and "row_key" not in keys
    headers = {column.key: column.header for column in module.COLUMNS}
    for header, names in report_specs.grid(number, module.CODE):
        if len(names) == 1:
            assert headers[names[0]] == header.replace(" (<ISO>)", ""), names


def test_rpt_20_paired_headers_and_change_literals() -> None:
    """RPT-20: a "before" and an "after" column per compared value; the four change literals."""
    section = report_specs.section(20, version_diff.CODE)
    assert '"Added", "Removed", "Changed", "Unchanged"' in section
    assert version_diff.CHANGES == ("Added", "Removed", "Changed", "Unchanged")
    headers = {column.key: column.header for column in version_diff.COLUMNS}
    for header, names in report_specs.grid(20, version_diff.CODE):
        if len(names) == 2 and names[0].endswith("_before"):
            label = header.replace(" (<ISO>)", "")
            assert (headers[names[0]], headers[names[1]]) == (f"{label} before", f"{label} after")
    assert '| `only_changes` | "Only changed entries" | checkbox | true | none |' in section
    assert framework.PARAMETER_DEFAULTS[version_diff.CODE] == {"only_changes": True}


@pytest.mark.parametrize(("number", "module"), MODULES)
def test_registration_and_catalogue(number: int, module: Any) -> None:
    """``framework.BUILDERS`` admits the four codes with an ``open`` source contract that names
    what it reads; each definition's kind and row key are the specification's."""
    assert framework.BUILDERS[module.CODE] is module.build
    contract = framework.SOURCE_CONTRACTS[module.CODE]
    assert contract.strategy == "open" and len(contract.open) == 1
    assert f"RPT-{number}" in contract.open[0]
    definition = DEFINITIONS_BY_CODE[module.CODE]
    section = report_specs.section(number, module.CODE)
    assert f"| Kind, formats | `{definition.kind}`;" in section
    assert f"`row_key` `{module.ROW_KEY_PREFIX}" in section


# --- shared reads ---------------------------------------------------------------------------------


def test_rate_and_ratio_text_never_round() -> None:
    assert support.rate_text(Decimal("85000"), "USD") == "85000.00"
    assert support.rate_text(Decimal("0.1"), "USD") == "0.10"
    assert support.rate_text(Decimal("0.333333333333333333"), "USD") == "0.333333333333333333"
    assert support.rate_text(Decimal("50000000.000"), "JPY") == "50000000"
    assert support.rate_text(Decimal("-0.00"), "USD") == "0.00"
    assert support.rate_text(None, "USD") is None
    assert support.ratio_text(Decimal("0.120000000000000000")) == "0.12"
    assert support.ratio_text(Decimal("1.000")) == "1"
    assert support.ratio_text(Decimal("0E-18")) == "0"


def test_request_status_at_a_cutoff_is_derived_from_its_timestamps() -> None:
    """T-PLT-17: APPROVED with ``decided_at`` after the cutoff was PENDING at the cutoff; a request
    withdrawn by the cutoff keeps its stored status and has no decision instant."""
    later = AT + timedelta(hours=1)
    approved = {"status": "APPROVED", "decided_at": later, "voided_at": None}
    assert support.status_at(approved, AT) == ("PENDING", None)
    assert support.status_at(approved, later) == ("APPROVED", later)
    withdrawn = {"status": "WITHDRAWN", "decided_at": None, "voided_at": AT}
    assert support.status_at(withdrawn, AT) == ("WITHDRAWN", None)
    assert support.status_at(withdrawn, AT - timedelta(seconds=1)) == ("PENDING", None)
    pending = {"status": "PENDING", "decided_at": None, "voided_at": None}
    assert support.status_at(pending, AT) == ("PENDING", None)


def test_instants_are_whole_utc_days_and_changed_after_needs_a_historical_read() -> None:
    start, end = support.instants(date(2026, 9, 1), date(2026, 9, 30))
    assert (start, end) == (
        datetime(2026, 9, 1, tzinfo=UTC),
        datetime(2026, 10, 1, tzinfo=UTC),
    )
    assert support.within(end - timedelta(microseconds=1), (start, end))
    assert not support.within(end, (start, end)) and not support.within(None, (start, end))
    rows = [{"updated_at": AT + timedelta(minutes=1)}]
    assert support.changed_after(rows, cutoff=AT, historical=True) is rows[0]
    assert support.changed_after(rows, cutoff=AT, historical=False) is None


def _request(
    *,
    status: str = "APPROVED",
    approvers: tuple[UUID | None, ...] = (PRIYA,),
    decided_at: datetime | None = AT,
    comment: str | None = "Supported by the study.",
    request_no: str = "APR-000002",
) -> support.Request:
    decisions = tuple(
        support.Decision(
            id=UUID(int=index + 1),
            decision="APPROVE" if approver is not None else "AUTO_APPROVE",
            approver_id=approver,
            approver_kind="USER" if approver is not None else "SYSTEM",
            on_behalf_of_id=None,
            step_no=index + 1,
            step_name="Approval",
            decided_at=AT,
            comment=None,
            subject_content_sha256="0" * 64,
            auto_rule_id=None,
            auto_rule_set_version_id=None,
        )
        for index, approver in enumerate(approvers)
    )
    return support.Request(
        id=UUID(int=99),
        request_no=request_no,
        subject_type="SSP_BOOK_VERSION",
        subject_id=H2,
        status=status,
        summary="Approve version 2 of SSP book US-LIST",
        entity_id=None,
        amount_functional=None,
        amount_currency=None,
        flags=("ABOVE_THRESHOLD",),
        preparer_id=MAYA,
        preparer_kind="USER",
        submitted_at=AT - timedelta(minutes=2),
        decided_at=decided_at,
        comment=comment,
        subject_content_sha256="0" * 64,
        decisions=decisions,
    )


# --- RPT-19 ---------------------------------------------------------------------------------------


def _version(**over: Any) -> change_log.Source:
    base: dict[str, Any] = dict(
        book_code="US-LIST",
        version_no=2,
        legacy_version_label="2026-H2",
        status="APPROVED",
        effective_from_date=date(2026, 10, 1),
        effective_to_date=None,
        methodology_label="Observable standalone sales, Jan-Aug 2026",
        is_methodology_change=False,
        entry_count=7,
        diff_summary={"against_version_id": str(H1), "added": 0, "removed": 0, "changed": 1},
        created_at=AT - timedelta(minutes=3),
        created_by=(MAYA, "USER"),
        requests=(_request(approvers=(PRIYA, MARCUS)),),
        successor_label=None,
        superseded_at=None,
        study_file_names=("ssp-study-2026.pdf",),
    )
    base.update(over)
    return change_log.Source(**base)


def test_change_log_row_shape() -> None:
    """J-02-AC-6 as a row: preparer, approvers in decision order, effective dates, the diff."""
    (row,) = change_log.dataset_rows([_version()], NAMES)
    assert row["row_key"] == "ssp:US-LIST:2"
    assert (row["ssp_book_code"], row["version_label"], row["status"]) == (
        "US-LIST",
        "2026-H2",
        "APPROVED",
    )
    assert (row["effective_from_date"], row["effective_to_date"]) == (date(2026, 10, 1), None)
    assert (
        row["diff_summary.added"],
        row["diff_summary.removed"],
        row["diff_summary.changed"],
    ) == (0, 0, 1)
    assert (row["preparer"], row["approvers"]) == ("Maya Chen", "Priya Raman, Marcus Webb")
    assert (row["approved_at"], row["study_file_name"]) == (AT, "ssp-study-2026.pdf")
    # a draft never submitted: the creator prepares, nothing else is known yet
    draft = _version(
        version_no=3, legacy_version_label=None, status="DRAFT", requests=(), diff_summary=None
    )
    (row,) = change_log.dataset_rows([draft], NAMES)
    assert (row["version_label"], row["preparer"], row["approvers"], row["approved_at"]) == (
        "v3",
        "Maya Chen",
        None,
        None,
    )
    assert row["diff_summary.changed"] is None
    # a pending second step shows the first approver and no approval instant
    pending = _version(requests=(_request(status="PENDING", decided_at=None),), status="SUBMITTED")
    (row,) = change_log.dataset_rows([pending], NAMES)
    assert (row["approvers"], row["approved_at"]) == ("Priya Raman", None)


def test_change_log_range_covers_every_lifecycle_transition() -> None:
    """A version is listed when it was created, submitted, decided or superseded in the range."""
    september = support.instants(date(2026, 9, 1), date(2026, 9, 30))
    august = support.instants(date(2026, 8, 1), date(2026, 8, 31))
    assert change_log.in_range(_version(), september)
    assert not change_log.in_range(_version(), august)
    earlier = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    submitted_in_january = replace(_request(decided_at=earlier), submitted_at=earlier)
    first = _version(
        version_no=1,
        created_at=earlier,
        requests=(submitted_in_january,),
        successor_label="2026-H2",
        superseded_at=AT,
    )
    assert change_log.in_range(first, september)  # superseded in September
    unsuperseded = replace(first, successor_label=None, superseded_at=None)
    assert not change_log.in_range(unsuperseded, september)


def test_successor_is_the_approved_version_that_starts_the_day_after() -> None:
    """BR-SSP-02: H1 ending 30 Sep 2026 is superseded by the approved H2 effective 1 Oct 2026; a
    draft with that date, or a version of another book, is not a successor."""
    rows = [
        {
            "id": H1,
            "ssp_book_id": BOOK,
            "version_no": 1,
            "status": "APPROVED",
            "effective_from_date": date(2026, 1, 1),
            "effective_to_date": date(2026, 9, 30),
            "published_at": AT - timedelta(days=200),
        },
        {
            "id": H2,
            "ssp_book_id": BOOK,
            "version_no": 2,
            "status": "APPROVED",
            "effective_from_date": date(2026, 10, 1),
            "effective_to_date": None,
            "published_at": AT,
        },
    ]
    assert change_log.successors(rows) == {H1: rows[1]}
    draft = {**rows[1], "status": "DRAFT", "published_at": None}
    assert change_log.successors([rows[0], draft]) == {}
    other_book = {**rows[1], "ssp_book_id": UUID(int=7)}
    assert change_log.successors([rows[0], other_book]) == {}


# --- RPT-20 ---------------------------------------------------------------------------------------


def _entry(
    code: str, *, method: str = "observable", basis: str = "AMOUNT", **band: str | None
) -> dict[str, Any]:
    values = {"point_value": None, "low_value": None, "mid_value": None, "high_value": None}
    values.update(band)
    return {
        "id": str(uuid5(NAMESPACE_URL, f"{code}:{sorted(band.items())}")),
        "product_code": code,
        "stratification": "",
        "region": None,
        "channel": None,
        "segment": None,
        "deal_size_band": None,
        "term_band": None,
        "currency": "USD",
        "method": method,
        "value_basis": basis,
        "quantity_unit": None,
        "unit_list_price": None,
        "midpoint_discount_ratio": None,
        "range_ratio": None,
        "cost_basis": None,
        "margin_ratio": None,
        "observable_point": None,
        "revenue_account_code": None,
        "distinctness": "distinct",
        "ranges": [{"band_dimension": "NONE", "band_from": None, "band_to": None, **values}],
    }


PLATFORM_H1 = _entry("AVM-PLAT-100", low_value="85000", mid_value="100000", high_value="115000")
PLATFORM_H2 = _entry("AVM-PLAT-100", low_value="95200", mid_value="112000", high_value="128800")
ENTERPRISE = _entry("AVM-PLAT-ENT", point_value="132000")
BUILD = _entry("AVM-ENG-BUILD", method="cost_plus_margin", basis="PERCENT_OF_LIST", point_value="1")


def test_version_diff_rows_j02_ac2() -> None:
    """J-02-AC-2 on pure entries: the changed band, the +12.0% mid change, "Unchanged" others."""
    rows, totals = version_diff.dataset_rows(
        [PLATFORM_H2, ENTERPRISE, BUILD], [PLATFORM_H1, ENTERPRISE, BUILD], only_changes=False
    )
    by_product = {row["product_code"]: row for row in rows}
    assert [row["product_code"] for row in rows] == [
        "AVM-ENG-BUILD",
        "AVM-PLAT-100",
        "AVM-PLAT-ENT",
    ]
    platform = by_product["AVM-PLAT-100"]
    assert platform["row_key"] == "entry:AVM-PLAT-100::||||:USD"
    assert (platform["change"], platform["mid_change_ratio"]) == ("Changed", "0.12")
    assert (platform["low_before"], platform["low_after"]) == ("85000.00", "95200.00")
    assert (platform["mid_before"], platform["mid_after"]) == ("100000.00", "112000.00")
    assert (platform["high_before"], platform["high_after"]) == ("115000.00", "128800.00")
    assert by_product["AVM-PLAT-ENT"]["change"] == "Unchanged"
    assert by_product["AVM-PLAT-ENT"]["point_after"] == "132000.00"
    assert by_product["AVM-ENG-BUILD"]["point_after"] == "1"  # a PERCENT_OF_LIST ratio
    assert totals == {"added": 0, "removed": 0, "changed": 1}
    only, same_totals = version_diff.dataset_rows(
        [PLATFORM_H2, ENTERPRISE, BUILD], [PLATFORM_H1, ENTERPRISE, BUILD], only_changes=True
    )
    assert [row["product_code"] for row in only] == ["AVM-PLAT-100"] and same_totals == totals


def test_version_diff_added_removed_and_encoded_keys() -> None:
    regional = {**_entry("SKU:1", point_value="10"), "region": "EMEA|North", "stratification": "A"}
    rows, totals = version_diff.dataset_rows([regional], [ENTERPRISE], only_changes=True)
    assert len(rows) == 2
    by_change = {row["change"]: row for row in rows}
    assert by_change["Added"]["row_key"] == "entry:SKU%3A1:A:EMEA%7CNorth||||:USD"
    assert (by_change["Added"]["point_before"], by_change["Added"]["point_after"]) == (
        None,
        "10.00",
    )
    assert by_change["Removed"]["mid_change_ratio"] is None
    assert totals == {"added": 1, "removed": 1, "changed": 0}
    assert books.key_of(regional).region == "EMEA|North"


def _stored(version_id: UUID, number: int, **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": version_id,
        "ssp_book_id": BOOK,
        "book_code": "US-LIST",
        "version_no": number,
        "legacy_version_label": f"2026-H{number}",
        "status": "APPROVED",
        "published_at": AT,
        "updated_at": AT,
    }
    row.update(over)
    return row


def test_version_diff_compares_with_the_prior_approved_version_by_default() -> None:
    versions = {H1: _stored(H1, 1), H2: _stored(H2, 2)}
    chosen, other = version_diff.compared_versions(
        versions, version_id=H2, against_id=None, cutoff=AT
    )
    assert (chosen["id"], other and other["id"]) == (H2, H1)
    first, nothing = version_diff.compared_versions(
        versions, version_id=H1, against_id=None, cutoff=AT
    )
    assert (first["id"], nothing) == (H1, None)  # no prior version: every entry is "Added"
    with pytest.raises(Problem) as missing:
        version_diff.compared_versions(versions, version_id=None, against_id=None, cutoff=AT)
    assert missing.value.errors[0].field == "parameters.ssp_book_version_id"
    assert missing.value.errors[0].message == "Choose a version."
    elsewhere = UUID(int=5)
    versions[elsewhere] = _stored(elsewhere, 1, ssp_book_id=UUID(int=6))
    with pytest.raises(Problem) as other_book:
        version_diff.compared_versions(versions, version_id=H2, against_id=elsewhere, cutoff=AT)
    assert other_book.value.errors[0].message == "Choose a version of the same SSP book."
    # a version approved after the cutoff is not yet "the prior approved version"
    late = {H1: _stored(H1, 1, published_at=AT + timedelta(days=1)), H2: _stored(H2, 2)}
    _, none = version_diff.compared_versions(late, version_id=H2, against_id=None, cutoff=AT)
    assert none is None


def test_version_diff_historical_read_needs_frozen_entries() -> None:
    later = AT + timedelta(hours=1)
    assert version_diff.frozen_by(_stored(H2, 2, updated_at=later), AT)  # approved by the cutoff
    assert not version_diff.frozen_by(
        _stored(H2, 2, status="DRAFT", published_at=None, updated_at=later), AT
    )
    assert version_diff.frozen_by(_stored(H2, 2, status="DRAFT", published_at=None), AT)


# --- RPT-21 ---------------------------------------------------------------------------------------


def _obligation_version(version_no: int, boundary: int = 0, **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "contract_external_id": "SF-ORD-20417",
        "obligation_key": "O1",
        "version_no": version_no,
        "combination_group_id": UUID(int=1),
        "modification_boundary_no": boundary,
        "product_code": "AVM-PLAT-100",
        "txn_currency": "USD",
        "ssp_book_version_id": H1,
        "ssp_book_code": "US-LIST",
        "ssp_legacy_version_label": "2026-H1",
        "ssp_version_no": 1,
        "ssp_entry_id": UUID(int=41),
        "ssp_method": "observable",
        "ssp_override_approval_request_id": None,
        "original_ssp_low": Decimal("85000"),
        "original_ssp_mid": Decimal("100000"),
        "original_ssp_high": Decimal("115000"),
        "original_ssp_selected": Decimal("96000"),
        "original_stated_price": Decimal("96000.00"),
        "original_allocated_amount": Decimal("97627.12"),
        "stated_price": Decimal("96000.00"),
        "remaining_ssp": Decimal("96000"),
        "allocation_weight": Decimal("0.813559322033898305"),
        "allocated_amount": Decimal("97627.12"),
        "allocation_adjustment": Decimal("1627.12"),
        "cause_event_ids": [],
        "inception_date": date(2026, 9, 1),
        "effective_date": date(2026, 9, 1),
    }
    row.update(over)
    return row


def test_allocation_segments_open_at_inception_and_at_each_boundary() -> None:
    """One segment per allocation event; each is read from its latest version."""
    versions = [
        _obligation_version(1),
        _obligation_version(2),
        _obligation_version(3, boundary=1),
        _obligation_version(4, boundary=1),
    ]
    inception, modified = allocations.segments_of(versions)
    assert (inception.cause, inception.created) == ("Inception", True)
    assert (inception.first["version_no"], inception.latest["version_no"]) == (1, 2)
    assert (modified.cause, modified.created) == ("Modification", False)
    assert (modified.first["version_no"], modified.latest["version_no"]) == (3, 4)
    # an obligation a boundary created: its first segment is a modification it was priced at
    (added,) = allocations.segments_of([_obligation_version(3, boundary=1)])
    assert (added.cause, added.created) == ("Modification", True)
    assert allocations.segments_of([]) == []


def test_allocation_reads_the_group_the_obligation_is_in() -> None:
    joined = UUID(int=2)
    versions = [
        _obligation_version(1),
        _obligation_version(1, combination_group_id=joined),
        _obligation_version(2, combination_group_id=joined),
    ]
    kept = allocations.current_group(versions)
    assert [row["combination_group_id"] for row in kept] == [joined, joined]


def test_allocation_row_wld_x_23_and_the_reallocation_row() -> None:
    """WLD-X-23 O1 as a row; a reallocation of an existing obligation carries no older range."""
    (segment,) = allocations.segments_of([_obligation_version(1)])
    item = allocations.allocation(segment, allocation_date=date(2026, 9, 1))
    rows, control = allocations.dataset_rows([item])
    row, total = rows
    assert row["row_key"] == "allocation:SF-ORD-20417:O1:1"
    assert (row["cause"], row["ssp_version_label"], row["range_status"]) == (
        "Inception",
        "US-LIST 2026-H1",
        "INSIDE",
    )
    assert row["ssp_entry_id"] == str(UUID(int=41))
    assert (row["ssp_low"], row["ssp_mid"], row["ssp_high"]) == (
        {"amount": "85000.00", "currency": "USD"},
        {"amount": "100000.00", "currency": "USD"},
        {"amount": "115000.00", "currency": "USD"},
    )
    assert row["selected_ssp"] == {"amount": "96000.00", "currency": "USD"}
    assert row["allocation_weight"] == "0.813559322033898305"
    assert row["allocated_amount"] == {"amount": "97627.12", "currency": "USD"}
    assert row["allocation_adjustment"] == {"amount": "1627.12", "currency": "USD"}
    assert total["row_key"] == "TOTAL:USD" and total["allocated_amount"]["amount"] == "97627.12"
    assert control == {
        "row_count": 1,
        "stated_price_total": {"USD": "96000.00"},
        "allocated_amount_total": {"USD": "97627.12"},
        "allocation_adjustment_total": {"USD": "1627.12"},
    }
    _, reallocated = allocations.segments_of(
        [
            _obligation_version(1),
            _obligation_version(
                2,
                boundary=1,
                remaining_ssp=Decimal("155000"),
                stated_price=Decimal("240000.00"),
                allocated_amount=Decimal("228273.97"),
                allocation_adjustment=Decimal("-11726.03"),
            ),
        ]
    )
    later = allocations.allocation(reallocated, allocation_date=date(2026, 9, 16))
    assert (later.cause, later.ssp_low, later.ssp_mid, later.ssp_high, later.range_status) == (
        "Modification",
        None,
        None,
        None,
        None,
    )
    assert (later.selected_ssp, later.allocated_amount) == (
        Decimal("155000"),
        Decimal("228273.97"),
    )
    # a point entry has no range to check; an override is flagged
    (point,) = allocations.segments_of(
        [
            _obligation_version(
                1,
                original_ssp_low=None,
                original_ssp_high=None,
                ssp_override_approval_request_id=UUID(int=9),
            )
        ]
    )
    flagged = allocations.allocation(point, allocation_date=date(2026, 9, 1))
    assert (flagged.range_status, flagged.is_override) == (None, True)


# --- RPT-22 ---------------------------------------------------------------------------------------


def test_override_default_pin_is_the_latest_version_without_an_override() -> None:
    obligation_id, request_id, second = UUID(int=11), UUID(int=12), UUID(int=13)

    def version(pin: UUID, request: UUID | None) -> dict[str, Any]:
        return {
            "obligation_id": obligation_id,
            "book_code": "ASC606",
            "ssp_book_version_id": pin,
            "ssp_override_approval_request_id": request,
        }

    third = UUID(int=14)
    found = overrides.first_overrides(
        [
            version(H1, None),
            version(H2, request_id),
            version(H2, request_id),  # later versions repeat the request: one row
            version(third, second),  # a second override keeps the un-overridden default
        ]
    )
    assert list(found) == [(obligation_id, request_id), (obligation_id, second)]
    assert found[(obligation_id, request_id)][1] == H1
    assert found[(obligation_id, second)][1] == H1


def test_override_row_shape() -> None:
    source = overrides.Source(
        contract_external_id="SF-ORD-10002",
        obligation_key="O1",
        product_code="AVM-SEAT-MO",
        default_version_label="US-LIST 2026-H1",
        override_version_label="US-LIST 2026-H2",
        request=_request(comment="Negotiated under the second-half list.", request_no="APR-000007"),
    )
    (row,) = overrides.dataset_rows([source], NAMES)
    assert row["row_key"] == "override:SF-ORD-10002:O1:APR-000007"
    assert (row["default_version_label"], row["override_version_label"]) == (
        "US-LIST 2026-H1",
        "US-LIST 2026-H2",
    )
    assert (row["justification"], row["requested_by"], row["approved_by"], row["approved_at"]) == (
        "Negotiated under the second-half list.",
        "Maya Chen",
        "Priya Raman",
        AT,
    )


def test_a_given_start_after_its_end_is_refused() -> None:
    params = ReportParams(
        report_code=change_log.CODE,
        report_version=1,
        parameters={"from_date": "2026-10-01", "to_date": "2026-09-30"},
        entity_ids=(),
        known_at=AT,
    )
    with pytest.raises(Problem) as refused:
        support.date_range(None, params)  # type: ignore[arg-type]
    assert refused.value.errors[0].message == "Start date must be on or before end date."
