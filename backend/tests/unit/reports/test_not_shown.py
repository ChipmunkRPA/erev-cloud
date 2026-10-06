"""``NOT_SHOWN`` of the report outputs (04 T-PLT-02 rev 1.316; dev-guide DG-KRN-DB-13; item
IDENTITY-WITHHELD-BY-STATUS-1) — CPU witnesses.

A report column has ONE ``empty_text``, and the user access listing's "Last login" prints "Never"
for an empty cell. Under D-80 rule 5 by the membership's status the last sign-in and the MFA state
of a person who is not a member now are not shown — and "Never" would be untrue of them. The
outputs carry a value for such a cell, ``NOT_SHOWN``:

- the API (``json_value``) answers null and CSV (``canonical``, which the frozen datasets go
  through too) writes nothing, as for an empty cell — the row's own ``membership_status`` tells
  the two meanings apart;
- XLSX (``xlsx._write_cell``, which has its own branch by kind) and PDF (``display_text``) print
  "Not shown", and "Never" keeps its meaning: an active member who never signed in.

One builder emits it, RPT-24, and by what is IN THE ROW: where the row's ``membership_status`` is
INVITED or REMOVED and nowhere else. The hash of an XLSX or PDF run is the hash of its JSON
dataset, which holds null for both meanings; the printed cell is decided by the dataset only
while the status in the row decides the sentinel (REQ-RPT-002; CTL-029). It never sits in a money
column: ``layout`` reads the currency of every money value that is not None.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime
from typing import Any, Final

import openpyxl
import pytest
from erev_api.domain.reports.builders import user_access_listing as access
from erev_api.domain.reports.outputs import (
    NOT_SHOWN,
    NOT_SHOWN_TEXT,
    Column,
    ReportData,
    RunStamp,
    display_text,
    json_rows,
    json_value,
)
from erev_api.domain.reports.outputs.csv import canonical, cell, render_csv
from erev_api.domain.reports.outputs.xlsx import render_xlsx
from erev_api.enums import MembershipStatus
from support.architecture import ROOT

AT = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
# The value or its type, anywhere in a module's text.
NAMED: Final = re.compile(r"\b(?:NOT_SHOWN|NotShown)\b")
MFA = Column("mfa_enrolled", "MFA enrolled", "boolean")
LAST_LOGIN = Column("last_login_at", "Last login", "timestamp", empty_text="Never")
COLUMNS = (Column("email", "Email", "code"), MFA, LAST_LOGIN)
DATA = ReportData(
    columns=COLUMNS,
    rows=(
        {"row_key": "a", "email": "active@x.test", "mfa_enrolled": True, "last_login_at": AT},
        {"row_key": "b", "email": "never@x.test", "mfa_enrolled": False, "last_login_at": None},
        {
            "row_key": "c",
            "email": "removed@x.test",
            "mfa_enrolled": NOT_SHOWN,
            "last_login_at": NOT_SHOWN,
        },
    ),
    control_totals={},
)
STAMP = RunStamp(
    report_code="user_access_listing",
    report_name="User access listing",
    report_version=1,
    report_run_no="RR-0001",
    parameters={},
    entity_codes=("US",),
    book=None,
    as_of=None,
    source="test",
    engine_version="0.0.0",
    build_sha="0" * 40,
    run_by="Hannah",
    run_at=AT,
    output_sha256="0" * 64,
)


def test_the_api_and_csv_give_an_empty_cell_for_what_is_not_shown() -> None:
    """Null in the API and nothing in CSV, as for an empty cell: both are raw machine values
    (DS-FMT-25), and the row's ``membership_status`` says which of the two meanings it is."""
    assert json_value(MFA, NOT_SHOWN) is None and json_value(LAST_LOGIN, NOT_SHOWN) is None
    never, removed = json_rows(DATA)[1:]
    assert (never["mfa_enrolled"], never["last_login_at"]) == (False, None)
    assert (removed["mfa_enrolled"], removed["last_login_at"]) == (None, None)
    for column in (MFA, LAST_LOGIN):
        assert canonical(column, "value", NOT_SHOWN) == cell(column, "value", NOT_SHOWN) == ""
    parsed = list(csv.reader(io.StringIO(render_csv(DATA).decode("utf-8"), newline="")))
    assert parsed[-2:] == [["never@x.test", "false", ""], ["removed@x.test", "", ""]]


def test_xlsx_and_pdf_print_not_shown_and_never_keeps_its_meaning() -> None:
    """XLSX has its own branch by kind and PDF goes through ``display_text``: both print "Not
    shown" for the value, in a boolean and in a timestamp cell, and "Never" stays the text of an
    empty last sign-in. Without its branch the XLSX run fails at the timestamp cell — the
    value is no datetime — and the PDF reads "Yes" in the boolean one."""
    assert NOT_SHOWN_TEXT == "Not shown"
    for column in (MFA, LAST_LOGIN):
        assert display_text(column, "value", NOT_SHOWN, "PARENTHESES") == "Not shown"
    assert display_text(LAST_LOGIN, "value", None, "PARENTHESES") == "Never"
    assert display_text(MFA, "value", False, "PARENTHESES") == "No"
    workbook = openpyxl.load_workbook(io.BytesIO(render_xlsx(DATA, STAMP)), read_only=True)
    printed = {
        row[0]: row[1:3]
        for sheet in workbook.worksheets
        for row in sheet.iter_rows(values_only=True)
        if isinstance(row[0], str) and row[0].endswith("@x.test")
    }
    assert printed["never@x.test"] == ("No", "Never")
    assert printed["removed@x.test"] == ("Not shown", "Not shown")
    yes, when = printed["active@x.test"]
    assert yes == "Yes" and isinstance(when, datetime)


def _member(status: str, **values: Any) -> access.Member:
    return access.Member(
        email=f"{status.lower()}@x.test",
        display_name=status.title(),
        status=status,
        mfa_enrolled=values.get("mfa_enrolled"),
        last_login_at=values.get("last_login_at"),
        grants=(),
    )


@pytest.mark.parametrize("status", [item.value for item in MembershipStatus])
def test_the_listing_emits_it_by_the_rows_own_status(status: str) -> None:
    """RPT-24 puts the value in the two cells of a row whose ``membership_status`` is INVITED or
    REMOVED and in no other row — by the status the row itself prints, whatever the member
    carries: the dataset decides the printed cell, so two runs whose datasets are equal print
    equal files (REQ-RPT-002)."""
    hidden = status in {"INVITED", "REMOVED"}
    for carried in ({}, {"mfa_enrolled": True, "last_login_at": AT}):
        [row], _ = access.dataset_rows([_member(status, **carried)])
        assert row["membership_status"] == status
        cells = (row["mfa_enrolled"], row["last_login_at"])
        if hidden:
            assert cells == (NOT_SHOWN, NOT_SHOWN)
        else:
            assert cells == (carried.get("mfa_enrolled"), carried.get("last_login_at"))


def test_one_builder_emits_it_and_never_in_a_money_column() -> None:
    """No other module of the application names the value or its type — in code, in an import or
    in a comment: a frozen dataset (``csv.canonical`` by way of ``reports.snapshots``) and every
    other report stay without it, and of the outputs only the three modules that convert a cell
    know it (PDF prints through ``display_text``). The one builder's two columns are a boolean
    and a timestamp — ``layout`` reads the currency of every money value that is not None, so
    the value has no place in a money column."""
    application = ROOT / "backend" / "erev_api"
    named = {
        path.relative_to(application).as_posix()
        for path in sorted(application.rglob("*.py"))
        if NAMED.search(path.read_text(encoding="utf-8"))
    }
    outputs = "domain/reports/outputs/"
    assert named == {
        "domain/reports/builders/user_access_listing.py",
        f"{outputs}__init__.py",
        f"{outputs}csv.py",
        f"{outputs}xlsx.py",
    }
    kinds = {column.key: column.kind for column in access.COLUMNS}
    assert (kinds["mfa_enrolled"], kinds["last_login_at"]) == ("boolean", "timestamp")
    assert "money" not in kinds.values()
