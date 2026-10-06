"""Item IMPORT-HEADER-CELL-CONFLICT-1 (the supervisor's ruling of 2026-10-02; 05 IPL-05 rev 1.210;
04 table 15.4-B ``HEADER_VALUE_CONFLICT``, §16.6 rev 1.310; PRD IMP-147), through the product: an
import does not store a value its file contradicts.

A CSV v2 file repeats the header members of an object on each of its rows (04 NC-19) and the
emitter reads them from the object's FIRST row; ``invoices`` and ``ssp_values`` repeat the members
of a line the same way. Measured before the change: an ``account_mapping`` file whose first row
states ``effective_from`` 1 July and whose second row states 1 October was VALIDATED, approved
and COMMITTED as a version effective 1 July — the later cell was read by nothing. Now a cell that
a later row repeats is blank or equal to the first row's, or the later row is refused at that
column with ``HEADER_VALUE_CONFLICT``, and the file loads nothing a row of it contradicts.

One witness for each template of the census — ``account_mapping``, ``contracts``, ``estimates``,
``invoices`` (the document and its line), ``ssp_values`` (the version and its entry) — outside
quarantine mode, where the upload ends INVALID, and in quarantine mode, where the object of the
refused row stays behind whole (REQ-DAT-008; rulings R-98 (10), R-109 (c), R-116 (g)); and the
boundary: an equal or a blank later cell loads as before. The pure rule and the census of every
template are ``tests/unit/imports/test_repeated_cells.py``.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    contract,
    contract_event,
    estimate,
    gl_account,
    import_row,
    source_invoice,
    source_invoice_line,
    ssp_book_version,
)
from erev_api.domain.imports.csv_v2.account_mapping import AccountMappingRowsIn
from erev_api.domain.imports.csv_v2.estimates import EstimatesIn
from erev_api.domain.imports.csv_v2.framework import flatten
from erev_api.domain.imports.csv_v2.invoices import InvoiceIn
from erev_api.domain.imports.csv_v2.ssp_values import SspValuesIn
from erev_api.enums import RegistryCategory
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.schemas.accounts import GlAccountIn
from erev_api.schemas.contracts import ContractCreateIn
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    IMPLEMENTATION_PLUS,
    K11_EXTERNAL_ID,
    PLATFORM_100,
    ImportWorld,
    J03World,
    K11World,
    Workspace,
    activated_contract,
    booked_contract,
    imported,
    j03_world,
    k11_body,
    k11_world,
    run_import_job,
)
from support.legacy_replay import job_of, shown, submit
from support.principals import Actor
from support.reference import approve, assign, get
from support.rows import publish_registry_version

CODE = "HEADER_VALUE_CONFLICT"
INCOMPLETE = "IMPORT_CONTRACT_INCOMPLETE"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def j03(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> J03World:
    world = j03_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    return world


@pytest.fixture
def k11(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K11World:
    world = k11_world(app, keyring, clock, files)
    booked = booked_contract(world.place, k11_body(world.customer_id), activate=False)
    activated_contract(world.place, booked)
    assign(world.priya.member, "revenue_reviewer")
    return world


def csv_bytes(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def importer(place: Workspace) -> ImportWorld:
    return ImportWorld(
        app=place.app,
        actor=place.author,
        runtime=JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files),
        clock=place.clock,
    )


def quarantine_mode(imports: ImportWorld) -> None:
    context = DbContext(tenant_id=imports.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=imports.tenant_id,
            category=RegistryCategory.INTEGRATION,
            values={"data.quarantine_failed_rows": True},
        )


def rows_of(imports: ImportWorld, import_id: str) -> list[tuple[int, str]]:
    return [
        (int(row["row_number"]), str(row["status"]))
        for row in imports.rows(
            select(import_row.c.row_number, import_row.c.status)
            .where(import_row.c.import_upload_id == UUID(import_id))
            .order_by(import_row.c.row_number)
        )
    ]


def findings_of(imports: ImportWorld, import_id: str) -> dict[int, list[tuple[str, str]]]:
    """row number -> (code, message) of each finding, from the import's own read."""
    listed = get(imports.app, f"/api/v1/imports/{import_id}/rows", imports.actor, {"limit": "50"})
    assert listed.status_code == 200, listed.text
    return {
        int(item["row_number"]): [
            (str(message["rule_id"]), str(message["message"])) for message in item["messages"]
        ]
        for item in listed.json()["items"]
        if item["messages"]
    }


def codes_of(imports: ImportWorld, import_id: str) -> dict[int, list[str]]:
    return {
        number: [code for code, _ in found]
        for number, found in findings_of(imports, import_id).items()
    }


def taken(imports: ImportWorld, approver: Actor, import_id: str) -> dict[str, Any]:
    """A VALIDATED upload diffed, submitted, approved and committed; API-S-Import afterwards."""
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_DIFF"))
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(imports.app, str(submitted.json()["approval_request_id"]), approver)
    assert decided.status_code == 200, decided.text
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    return shown(imports, import_id)


def conflict(row: int, column: str, group: str, first: int, expected: str, actual: str) -> str:
    """The stored sentence (PRD IMP-147, CPY-06) for a cell both rows state: what this row states
    where the first row of the same object, or of the same line of it, states another value."""
    return (
        f'Row {row}, column {column}: This row states "{actual}" where row {first} of the same '
        f'{group} states "{expected}". '
    )


# --- account_mapping ----------------------------------------------------------------------------

MAPPING_HEADERS = [column.name for column in flatten(AccountMappingRowsIn)]
JULY, OCTOBER = "2026-07-01T00:00:00Z", "2026-10-01T00:00:00Z"


def _account(imports: ImportWorld, approver: Actor) -> str:
    headers = [column.name for column in flatten(GlAccountIn)]
    values = dict.fromkeys(headers, "")
    values |= {"code": "4020", "name": "Revenue", "account_type": "REVENUE", "normal_balance": "C"}
    import_id, validated = imported(
        imports, "gl.csv", csv_bytes(headers, [list(values.values())]), "gl_accounts"
    )
    assert validated["status"] == "VALIDATED", validated
    assert taken(imports, approver, import_id)["status"] == "COMMITTED"
    return str(imports.scalar(select(gl_account.c.id).where(gl_account.c.code == "4020")))


def _rule(account_id: str, name: str, role: str, effective: str, notes: str = "") -> list[str]:
    values = dict.fromkeys(MAPPING_HEADERS, "")
    values |= {
        "name": name,
        "notes": notes,
        "effective_from": effective,
        "lines.account_role": role,
        "lines.gl_account_id": account_id,
        "lines.priority": "10",
    }
    return list(values.values())


def _versions(imports: ImportWorld, like: str) -> list[tuple[str, str, str, int]]:
    """(name, status, effective from, rules) of the mapping versions named like ``like``."""
    found = []
    for row in imports.rows(
        select(
            account_mapping_version.c.id,
            account_mapping_version.c.name,
            account_mapping_version.c.status,
            account_mapping_version.c.effective_from,
        ).where(account_mapping_version.c.name.like(like))
    ):
        rules = imports.scalar(
            select(func.count()).where(
                account_mapping_rule.c.account_mapping_version_id == row["id"]
            )
        )
        found.append(
            (
                str(row["name"]),
                str(row["status"]),
                row["effective_from"].date().isoformat(),
                int(rules),
            )
        )
    return sorted(found)


def test_a_mapping_version_is_not_stored_against_a_later_row_of_its_file(j03: J03World) -> None:
    """``account_mapping``, the three files measured. (c2) 1 July on the first row, 1 October on
    the second — COMMITTED before as a version effective 1 July: the upload is INVALID, the later
    row refused at ``effective_from`` with both rows and both values named. (c1) "first of July"
    on the later row — never read before: the same. (c3) "first of July" on the FIRST row and a
    date on the later one: the later row states another value than the row the version is read
    from, and is refused; what the first row states is the command's to judge, as before. No
    version is created. In quarantine mode the version of the refused row stays behind whole —
    its first row is refused with it, by name — and the other version of the file is created."""
    imports = importer(j03.place)
    account_id = _account(imports, j03.priya)
    for label, first, later in (
        ("C2", JULY, OCTOBER),
        ("C1", JULY, "first of July"),
        ("C3", "first of July", JULY),
    ):
        name = f"AVM-MAP-{label}"
        content = csv_bytes(
            MAPPING_HEADERS,
            [
                _rule(account_id, name, "REVENUE", first),
                _rule(account_id, name, "CONTRACT_LIABILITY", later),
            ],
        )
        import_id, validated = imported(imports, f"mapping-{label}.csv", content, "account_mapping")
        assert validated["status"] == "INVALID", (label, validated)
        assert rows_of(imports, import_id) == [(2, "VALID"), (3, "ERROR")], label
        found = findings_of(imports, import_id)
        assert sorted(found) == [3], (label, found)
        ((code, message),) = found[3]
        assert code == CODE, label
        assert message == (
            conflict(3, "Effective from", f"mapping version {name}", 2, first, later)
            + f"Repeat the value of row 2 or leave this cell blank. ({CODE})"
        ), label
    assert _versions(imports, "AVM-MAP-C%") == []

    quarantine_mode(imports)
    content = csv_bytes(
        MAPPING_HEADERS,
        [
            _rule(account_id, "AVM-MAP-Q", "REVENUE", JULY),
            _rule(account_id, "AVM-MAP-Q", "CONTRACT_LIABILITY", OCTOBER),
            _rule(account_id, "AVM-MAP-R", "REVENUE", OCTOBER),
        ],
    )
    import_id, validated = imported(imports, "mapping-q.csv", content, "account_mapping")
    assert validated["status"] == "VALIDATED", validated
    assert rows_of(imports, import_id) == [(2, "ERROR"), (3, "ERROR"), (4, "VALID")]
    assert codes_of(imports, import_id) == {2: [INCOMPLETE], 3: [CODE]}
    assert (
        "Another row of mapping version AVM-MAP-Q was refused, so none of its rows is loaded."
        in findings_of(imports, import_id)[2][0][1]
    )
    done = taken(imports, j03.priya, import_id)
    assert done["status"] == "COMMITTED", done
    assert done["control_totals"]["loaded"] == {"rows": 1, "quarantined": 2}
    assert _versions(imports, "AVM-MAP-_") == [("AVM-MAP-R", "DRAFT", "2026-10-01", 1)]


def test_an_equal_or_a_blank_later_cell_loads_as_before(j03: J03World) -> None:
    """The boundary: a later row that repeats the first row's cell, and one that leaves an
    optional cell blank, are no finding — the file validates, commits, and the version holds
    what its first row states with every row's rule."""
    imports = importer(j03.place)
    account_id = _account(imports, j03.priya)
    content = csv_bytes(
        MAPPING_HEADERS,
        [
            _rule(account_id, "AVM-MAP-OK", "REVENUE", JULY, notes="July study"),
            _rule(account_id, "AVM-MAP-OK", "CONTRACT_LIABILITY", JULY, notes="July study"),
            _rule(account_id, "AVM-MAP-OK", "CONTRACT_ASSET", "", notes=""),
        ],
    )
    import_id, validated = imported(imports, "mapping-ok.csv", content, "account_mapping")
    assert validated["status"] == "VALIDATED", validated
    assert rows_of(imports, import_id) == [(2, "VALID"), (3, "VALID"), (4, "VALID")]
    assert findings_of(imports, import_id) == {}
    assert taken(imports, j03.priya, import_id)["status"] == "COMMITTED"
    assert _versions(imports, "AVM-MAP-OK") == [("AVM-MAP-OK", "DRAFT", "2026-07-01", 3)]
    (notes,) = imports.rows(
        select(account_mapping_version.c.notes).where(
            account_mapping_version.c.name == "AVM-MAP-OK"
        )
    )
    assert notes["notes"] == "July study"


# --- contracts ----------------------------------------------------------------------------------

CONTRACT_HEADERS = [column.name for column in flatten(ContractCreateIn)]


def _contract_rows(customer_id: UUID, external_id: str, *, later_inception: str) -> list[list[str]]:
    """A contract of AVM-US on two rows; the second states ``later_inception``."""
    rows = []
    for key, product, price, start, end, inception in (
        ("O1", PLATFORM_100, "96000.00", "2026-09-01", "2027-08-31", "2026-09-01"),
        ("O2", IMPLEMENTATION_PLUS, "24000.00", "", "", later_inception),
    ):
        values = dict.fromkeys(CONTRACT_HEADERS, "")
        values |= {
            "external_id": external_id,
            "customer_id": str(customer_id),
            "contracting_entity_code": "AVM-US",
            "transaction_currency": "USD",
            "inception_date": inception,
            "document_ref": external_id,
            "lines.obligation_key": key,
            "lines.product_code": product,
            "lines.quantity": "1",
            "lines.total_price.amount": price,
            "lines.total_price.currency": "USD",
            "lines.start_date": start,
            "lines.end_date": end,
        }
        rows.append(list(values.values()))
    return rows


def _booked(imports: ImportWorld, like: str) -> list[tuple[str, str]]:
    return sorted(
        (str(row["external_id"]), row["inception_date"].isoformat())
        for row in imports.rows(
            select(contract.c.external_id, contract.c.inception_date).where(
                contract.c.external_id.like(like)
            )
        )
    )


def test_a_contract_is_not_booked_against_a_later_row_of_its_file(j03: J03World) -> None:
    """``contracts``: the second row of SF-ORD-31001 states another inception date than the
    first — the contract was booked with the first row's and nothing was said. The upload is
    INVALID, the later row refused at ``inception_date``, nothing booked. In quarantine mode
    that contract stays behind whole and the other contract of the file is booked."""
    imports = importer(j03.place)
    content = csv_bytes(
        CONTRACT_HEADERS,
        [
            *_contract_rows(j03.customer_id, "SF-ORD-31001", later_inception="2026-09-15"),
            *_contract_rows(j03.customer_id, "SF-ORD-31002", later_inception="2026-09-01"),
        ],
    )
    import_id, validated = imported(imports, "contracts-h.csv", content, "contracts")
    assert validated["status"] == "INVALID", validated
    assert rows_of(imports, import_id) == [(2, "VALID"), (3, "ERROR"), (4, "VALID"), (5, "VALID")]
    found = findings_of(imports, import_id)
    assert sorted(found) == [3], found
    assert found[3] == [
        (
            CODE,
            conflict(3, "Inception date", "contract SF-ORD-31001", 2, "2026-09-01", "2026-09-15")
            + f"Repeat the value of row 2. ({CODE})",
        )
    ]
    assert _booked(imports, "SF-ORD-3100%") == []

    quarantine_mode(imports)
    content = csv_bytes(
        CONTRACT_HEADERS,
        [
            *_contract_rows(j03.customer_id, "SF-ORD-31003", later_inception="2026-09-15"),
            *_contract_rows(j03.customer_id, "SF-ORD-31004", later_inception="2026-09-01"),
        ],
    )
    import_id, validated = imported(imports, "contracts-q.csv", content, "contracts")
    assert validated["status"] == "VALIDATED", validated
    assert rows_of(imports, import_id) == [(2, "ERROR"), (3, "ERROR"), (4, "VALID"), (5, "VALID")]
    assert codes_of(imports, import_id) == {2: [INCOMPLETE], 3: [CODE]}
    done = taken(imports, j03.priya, import_id)
    assert done["status"] == "COMMITTED", done
    assert done["control_totals"]["loaded"] == {"rows": 2, "quarantined": 2}
    assert _booked(imports, "SF-ORD-3100%") == [("SF-ORD-31004", "2026-09-01")]


# --- estimates ----------------------------------------------------------------------------------

ESTIMATE_HEADERS = [column.name for column in flatten(EstimatesIn)]


def _rebate(outcome: str, amount: str, probability: str, *, constrained: str) -> list[str]:
    values = dict.fromkeys(ESTIMATE_HEADERS, "")
    values |= {
        "contract": K11_EXTERNAL_ID,
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "element_code": "REBATE-DE-01",
        "vc_element_type": "REBATE",
        "method": "EXPECTED_VALUE",
        "effective_date": "2026-09-30",
        "parameters.refund_liability_target": "1620.00",
        "unconstrained_amount": "1620.00",
        "most_conservative_amount": "0.00",
        "constrained_amount": constrained,
        "rationale": "Hollenbrand expects to reach the 2026 volume threshold.",
        "lines.outcome": outcome,
        "lines.amount": amount,
        "lines.probability": probability,
    }
    return list(values.values())


@pytest.mark.parametrize("quarantine", [False, True], ids=["whole-file", "quarantine"])
def test_an_estimate_is_not_stored_against_a_later_row_of_its_file(
    k11: K11World, quarantine: bool
) -> None:
    """``estimates``: the two outcomes of one version of REBATE-DE-01; the second row states a
    constrained amount of 9,999.00 where the first states 1,620.00 — the version was prepared
    with the first row's. The later row is refused at ``constrained_amount`` and no element is
    created; in quarantine mode the first row is refused with it (the rows of one contract load
    whole or not at all), so the upload is INVALID in both modes."""
    imports = importer(k11.place)
    if quarantine:
        quarantine_mode(imports)
    content = csv_bytes(
        ESTIMATE_HEADERS,
        [
            _rebate("Volume threshold reached", "2700.00", "0.6", constrained="1620.00"),
            _rebate("Volume threshold missed", "0.00", "0.4", constrained="9999.00"),
        ],
    )
    import_id, validated = imported(imports, "estimates-h.csv", content, "estimates")
    assert validated["status"] == "INVALID", validated
    found = findings_of(imports, import_id)
    assert found[3] == [
        (
            CODE,
            conflict(
                3,
                "Constrained amount",
                f"estimate {K11_EXTERNAL_ID} / REBATE-DE-01",
                2,
                "1620.00",
                "9999.00",
            )
            + f"Repeat the value of row 2 or leave this cell blank. ({CODE})",
        )
    ]
    if quarantine:
        assert rows_of(imports, import_id) == [(2, "ERROR"), (3, "ERROR")]
        assert [code for code, _ in found[2]] == [INCOMPLETE]
    else:
        assert rows_of(imports, import_id) == [(2, "VALID"), (3, "ERROR")]
        assert sorted(found) == [3]
    assert (
        imports.rows(select(estimate.c.id).where(estimate.c.element_code == "REBATE-DE-01")) == []
    )


# --- invoices -----------------------------------------------------------------------------------

INVOICE_HEADERS = [column.name for column in flatten(InvoiceIn)]


def _invoice(
    number: str, line: str, key: str, product: str, quantity: str, **cells: str
) -> list[str]:
    values = dict.fromkeys(INVOICE_HEADERS, "")
    values |= {
        "contract": K11_EXTERNAL_ID,
        "document_kind": "INVOICE",
        "invoice_number": number,
        "issue_date": "2026-09-12",
        "due_date": "2026-10-12",
        "is_cancellable": "false",
        "lines.line_external_id": line,
        "lines.obligation_key": key,
        "lines.product_code": product,
        "lines.quantity": quantity,
        "lines.amount.currency": "EUR",
        "lines.tax_lines.tax_type": "VAT",
        "lines.tax_lines.jurisdiction": "DE",
        "lines.tax_lines.amount.currency": "EUR",
        "lines.tax_lines.principal_or_agent": "PRINCIPAL",
    }
    values |= cells
    return list(values.values())


def _gateway(number: str, amount: str, tax_type: str, tax: str, **cells: str) -> list[str]:
    """One row of line 1 of a document: 120 units of AVM-GW on O1, one tax line."""
    return _invoice(
        number,
        "1",
        "O1",
        "AVM-GW",
        "120",
        **{
            "lines.amount.amount": amount,
            "lines.tax_lines.tax_type": tax_type,
            "lines.tax_lines.amount.amount": tax,
        },
        **cells,
    )


def _documents(imports: ImportWorld) -> list[str]:
    return sorted(
        str(row["invoice_number"])
        for row in imports.rows(
            select(source_invoice.c.invoice_number).where(
                source_invoice.c.invoice_number.like("INV-H-%")
            )
        )
    )


@pytest.mark.parametrize("quarantine", [False, True], ids=["whole-file", "quarantine"])
def test_a_document_is_not_stored_against_a_later_row_of_its_file(
    k11: K11World, quarantine: bool
) -> None:
    """``invoices``, both levels. INV-H-1 has one line on two rows, a tax line each: the second
    row states 60,000.00 where the first states 54,000.00 — the line was billed with the first
    row's amount. INV-H-2 has two lines: the second line's row states another due date than the
    document's first row. Each later row is refused at its column; nothing is stored and no
    billing is recorded. In quarantine mode the other rows are refused with them (the rows of
    one contract load whole or not at all), so the upload is INVALID in both modes."""
    imports = importer(k11.place)
    if quarantine:
        quarantine_mode(imports)
    content = csv_bytes(
        INVOICE_HEADERS,
        [
            _gateway("INV-H-1", "54000.00", "VAT", "10260.00"),
            _gateway("INV-H-1", "60000.00", "CITY", "540.00"),
            _invoice(
                "INV-H-2",
                "1",
                "O2",
                "AVM-SUP-12",
                "1",
                **{"lines.amount.amount": "9000.00", "lines.tax_lines.amount.amount": "1710.00"},
            ),
            _invoice(
                "INV-H-2",
                "2",
                "O2",
                "AVM-SUP-12",
                "1",
                due_date="2026-11-12",
                **{"lines.amount.amount": "9000.00", "lines.tax_lines.amount.amount": "1710.00"},
            ),
        ],
    )
    import_id, validated = imported(imports, "invoices-h.csv", content, "invoices")
    assert validated["status"] == "INVALID", validated
    found = findings_of(imports, import_id)
    assert found[3] == [
        (
            CODE,
            conflict(
                3, "Lines amount amount", "document line INV-H-1 / 1", 2, "54000.00", "60000.00"
            )
            + f"Repeat the value of row 2. ({CODE})",
        )
    ]
    assert found[5] == [
        (
            CODE,
            conflict(5, "Due date", "document INV-H-2", 4, "2026-10-12", "2026-11-12")
            + f"Repeat the value of row 4 or leave this cell blank. ({CODE})",
        )
    ]
    if quarantine:
        assert rows_of(imports, import_id) == [
            (2, "ERROR"),
            (3, "ERROR"),
            (4, "ERROR"),
            (5, "ERROR"),
        ]
        assert [code for code, _ in found[2]] == [code for code, _ in found[4]] == [INCOMPLETE]
    else:
        assert rows_of(imports, import_id) == [
            (2, "VALID"),
            (3, "ERROR"),
            (4, "VALID"),
            (5, "ERROR"),
        ]
        assert sorted(found) == [3, 5]
    assert _documents(imports) == []
    assert (
        imports.rows(
            select(contract_event.c.id).where(contract_event.c.import_upload_id == UUID(import_id))
        )
        == []
    )


def test_the_rows_of_one_line_that_agree_make_one_line_with_their_tax_lines(k11: K11World) -> None:
    """The boundary for a line, and equality as the column is typed: the two rows of line 1 of
    INV-H-3 state its amount as 54000.00 and as 54000 — one number — and each a tax line. The
    file validates and commits: one line of 54,000.00 with two tax lines."""
    imports = importer(k11.place)
    content = csv_bytes(
        INVOICE_HEADERS,
        [
            _gateway("INV-H-3", "54000.00", "VAT", "10260.00"),
            _gateway("INV-H-3", "54000", "CITY", "540.00"),
        ],
    )
    import_id, validated = imported(imports, "invoices-ok.csv", content, "invoices")
    assert validated["status"] == "VALIDATED", validated
    assert findings_of(imports, import_id) == {}
    assert taken(imports, k11.priya, import_id)["status"] == "COMMITTED"
    assert _documents(imports) == ["INV-H-3"]
    (line,) = imports.rows(
        select(source_invoice_line.c.amount, source_invoice_line.c.tax_lines)
        .select_from(
            source_invoice_line.join(
                source_invoice,
                (source_invoice.c.tenant_id == source_invoice_line.c.tenant_id)
                & (source_invoice.c.id == source_invoice_line.c.source_invoice_id),
            )
        )
        .where(source_invoice.c.invoice_number == "INV-H-3")
    )
    assert Decimal(line["amount"]) == Decimal("54000.00")
    assert [item["tax_type"] for item in line["tax_lines"]] == ["VAT", "CITY"]


# --- ssp_values ---------------------------------------------------------------------------------

SSP_HEADERS = [column.name for column in flatten(SspValuesIn)]


def _entry(product: str, label: str, **members: str) -> list[str]:
    values = dict.fromkeys(SSP_HEADERS, "")
    values |= {
        "ssp_book_code": "US-LIST",
        "legacy_version_label": label,
        "effective_from_date": "2026-07-01",
        "methodology_label": "Q3 list-price study",
        "lines.product_code": product,
        "lines.currency": "USD",
        "lines.method": "observable",
        "lines.distinctness": "distinct",
        "lines.value_basis": "AMOUNT",
        "lines.ranges.low_value": "900.00",
        "lines.ranges.mid_value": "1000.00",
        "lines.ranges.high_value": "1100.00",
    }
    values |= members
    return [values[name] for name in SSP_HEADERS]


def _band(product: str, label: str, band: tuple[str, str, str], **members: str) -> list[str]:
    values = dict.fromkeys(SSP_HEADERS, "")
    values |= {
        "ssp_book_code": "US-LIST",
        "legacy_version_label": label,
        "effective_from_date": "2026-07-01",
        "methodology_label": "Q3 list-price study",
        "lines.product_code": product,
        "lines.currency": "USD",
        "lines.method": "observable",
        "lines.distinctness": "distinct",
        "lines.value_basis": "AMOUNT",
        "lines.ranges.band_dimension": "QUANTITY",
        "lines.ranges.band_from": band[0],
        "lines.ranges.band_to": band[1],
        "lines.ranges.point_value": band[2],
    }
    values |= members
    return [values[name] for name in SSP_HEADERS]


@pytest.mark.parametrize("quarantine", [False, True], ids=["whole-file", "quarantine"])
def test_an_ssp_version_is_not_stored_against_a_later_row_of_its_file(
    j03: J03World, quarantine: bool
) -> None:
    """``ssp_values``, both levels. The version H-1 on two rows: the second states another
    methodology label than the first — the version was created with the first row's. The entry
    of AVM-PLAT-100 in version H-2 on two band rows: the second states it nondistinct where the
    first states it distinct — the entry was stored as its first band row states it. Each later
    row is refused at its column and no version is created; in quarantine mode the other row of
    the book is refused with it, so the upload is INVALID in both modes."""
    imports = importer(j03.place)
    if quarantine:
        quarantine_mode(imports)
    for label, rows, column, group, expected, actual, remedy in (
        (
            "H-1",
            [
                _entry(PLATFORM_100, "H-1"),
                _entry(IMPLEMENTATION_PLUS, "H-1", methodology_label="Q4 list-price study"),
            ],
            "Methodology label",
            "SSP book version US-LIST / H-1",
            "Q3 list-price study",
            "Q4 list-price study",
            "Repeat the value of row 2.",
        ),
        (
            "H-2",
            [
                _band(PLATFORM_100, "H-2", ("0", "10", "1000.00")),
                _band(
                    PLATFORM_100,
                    "H-2",
                    ("10", "20", "900.00"),
                    **{"lines.distinctness": "nondistinct"},
                ),
            ],
            "Lines distinctness",
            f"SSP entry {PLATFORM_100}",
            "distinct",
            "nondistinct",
            "Repeat the value of row 2.",
        ),
    ):
        import_id, validated = imported(
            imports, f"ssp-{label}.csv", csv_bytes(SSP_HEADERS, rows), "ssp_values"
        )
        assert validated["status"] == "INVALID", (label, validated)
        found = findings_of(imports, import_id)
        assert found[3] == [
            (CODE, conflict(3, column, group, 2, expected, actual) + f"{remedy} ({CODE})")
        ], label
        if quarantine:
            assert rows_of(imports, import_id) == [(2, "ERROR"), (3, "ERROR")], label
            assert [code for code, _ in found[2]] == [INCOMPLETE], label
        else:
            assert rows_of(imports, import_id) == [(2, "VALID"), (3, "ERROR")], label
            assert sorted(found) == [3], label
    assert (
        imports.rows(
            select(ssp_book_version.c.id).where(ssp_book_version.c.legacy_version_label.like("H-%"))
        )
        == []
    )
