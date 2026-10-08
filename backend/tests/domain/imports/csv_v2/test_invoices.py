"""DIN-9 invoices and credit memos through CSV v2 (04 T-IMP-01, NC-19, T-SRC-04, T-SRC-05
``tax_lines`` rev 1.3, §16.3 ``BILLING_RECORDED``, ``CREDIT_MEMO_RECORDED``; PRD WLD-F-22, J-04.2;
03 REQ-BIL-001; BUILD_SPEC DIN-9).

World: ``support.factories.k11_world`` with K-11 ``NS-SO-DE-5004`` booked and activated (AVM-DE,
EUR). Maya uploads, Priya (Revenue Reviewer, MFA) approves, and the jobs run as the worker runs
them.
"""

from __future__ import annotations

import copy
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
    contract_event,
    exception_item,
    import_row_lineage,
    job,
    source_invoice,
    source_invoice_line,
    source_record,
)
from erev_api.enums import RegistryCategory, RegistryScope
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.registry import presets
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    K11_EXTERNAL_ID,
    ImportWorld,
    K11World,
    activated_contract,
    booked_contract,
    imported,
    k11_body,
    k11_world,
    run_import_job,
)
from support.legacy_replay import diffed, job_of, shown, submit
from support.reference import approve, assign, get
from support.rows import publish_registry_version

HEADERS = (
    "contract",
    "document_kind",
    "invoice_number",
    "issue_date",
    "due_date",
    "is_cancellable",
    "credited_invoice_number",
    "reason",
    "lines.line_external_id",
    "lines.obligation_key",
    "lines.product_code",
    "lines.quantity",
    "lines.amount.amount",
    "lines.amount.currency",
    "lines.tax_lines.tax_type",
    "lines.tax_lines.jurisdiction",
    "lines.tax_lines.amount.amount",
    "lines.tax_lines.amount.currency",
    "lines.tax_lines.principal_or_agent",
)
# WLD-F-22 rows of K-11 and a credit memo of INV-DE-4471.
ROWS = (
    (K11_EXTERNAL_ID, "INVOICE", "INV-DE-4471", "2026-09-12", "2026-10-12", "false", "", "", "1",
     "O1", "AVM-GW", "120", "54000.00", "EUR", "VAT", "DE", "10260.00", "EUR", "PRINCIPAL"),
    (K11_EXTERNAL_ID, "INVOICE", "INV-DE-4472", "2026-09-15", "2026-10-15", "true", "", "", "1",
     "O2", "AVM-SUP-12", "1", "18000.00", "EUR", "VAT", "DE", "3420.00", "EUR", "PRINCIPAL"),
    (K11_EXTERNAL_ID, "CREDIT_MEMO", "CM-DE-0091", "2026-09-20", "", "", "INV-DE-4471",
     "Damaged units", "1", "O1", "AVM-GW", "10", "4500.00", "EUR", "", "", "", "", ""),
)  # fmt: skip


def csv_bytes(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def k11(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> K11World:
    world = k11_world(app, keyring, clock, LocalFileStore(app_settings.file_root))
    booked = booked_contract(world.place, k11_body(world.customer_id), activate=False)
    activated_contract(world.place, booked)
    assign(world.priya.member, "revenue_reviewer")
    return world


def importer(world: K11World) -> ImportWorld:
    place = world.place
    return ImportWorld(
        app=place.app,
        actor=place.author,
        runtime=JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files),
        clock=place.clock,
    )


def committed(world: K11World, name: str, content: bytes, template_code: str) -> dict[str, Any]:
    imports = importer(world)
    import_id = diffed(imports, name, content, template_code)
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), world.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == "COMMITTED", done
    return done


def test_invoices_and_credit_memos_ingested(k11: K11World) -> None:
    done = committed(k11, "avm-de-invoices-2026-09.csv", csv_bytes(HEADERS, ROWS), "invoices")
    assert done["counts"]["rows"] == 3
    checks = done["control_totals"]["loaded"]["monetary_checks"]
    assert (
        done["control_totals"]["loaded"]["amount_sums"]
        == done["control_totals"]["source"]["amount_sums"]
    )
    assert len(checks) == 3
    assert all(check["source"] == check["stored"] for check in checks)
    import_id = UUID(done["id"])
    imports = importer(k11)

    documents = imports.rows(
        select(source_invoice)
        .where(source_invoice.c.external_version == str(import_id))
        .order_by(source_invoice.c.invoice_number)
    )
    assert [
        (
            row["invoice_number"],
            row["document_kind"],
            Decimal(row["total_amount"]),
            Decimal(row["tax_amount"]),
            row["legal_entity_code"],
            str(row["currency"]).strip(),
            row["credited_invoice_external_id"],
        )
        for row in documents
    ] == [
        # 04 T-SRC-04 ``total_amount``: "Signed: credit memos negative" (ruling R-45 (c); the
        # expectation read 4500.00, the unsigned amount the template stored against 04)
        ("CM-DE-0091", "CREDIT_MEMO", Decimal("-4500.00"), Decimal("0.00"), "AVM-DE", "EUR",
         "INV-DE-4471"),
        ("INV-DE-4471", "INVOICE", Decimal("54000.00"), Decimal("10260.00"), "AVM-DE", "EUR", None),
        ("INV-DE-4472", "INVOICE", Decimal("18000.00"), Decimal("3420.00"), "AVM-DE", "EUR", None),
    ]  # fmt: skip
    by_number = {row["invoice_number"]: row for row in documents}
    lines = imports.rows(
        select(
            source_invoice_line.c.source_invoice_id,
            source_invoice_line.c.obligation_ref,
            source_invoice_line.c.amount,
            source_invoice_line.c.tax_lines,
        ).where(source_invoice_line.c.source_invoice_id.in_([row["id"] for row in documents]))
    )
    lines_of = {row["source_invoice_id"]: row for row in lines}
    first = lines_of[by_number["INV-DE-4471"]["id"]]
    assert (first["obligation_ref"], Decimal(first["amount"])) == ("O1", Decimal("54000.00"))
    # T-SRC-05 keeps the jurisdiction as evidence.
    assert first["tax_lines"] == [
        {
            "tax_type": "VAT",
            "jurisdiction": "DE",
            "amount": {"amount": "10260.00", "currency": "EUR"},
            "principal_or_agent": "PRINCIPAL",
        }
    ]

    events = imports.rows(
        select(
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.origin,
            contract_event.c.import_upload_id,
            contract_event.c.source_record_id,
            contract_event.c.payload,
        )
        .where(contract_event.c.import_upload_id == import_id)
        .order_by(contract_event.c.record_seq)
    )
    assert [(str(row["event_type"]), str(row["origin"])) for row in events] == [
        ("BILLING_RECORDED", "IMPORT"),
        ("BILLING_RECORDED", "IMPORT"),
        ("CREDIT_MEMO_RECORDED", "IMPORT"),
    ]
    assert all(row["source_record_id"] is not None for row in events)
    billing = events[0]["payload"]
    assert (
        billing["invoice_number"],
        billing["obligation_key"],
        billing["amount"],
        billing["issue_date"],
        billing["due_date"],
        billing["is_cancellable"],
        billing["source_invoice_id"],
    ) == (
        "INV-DE-4471",
        "O1",
        {"amount": "54000.00", "currency": "EUR"},
        "2026-09-12",
        "2026-10-12",
        False,
        str(by_number["INV-DE-4471"]["id"]),
    )
    assert billing["tax_amount"] == {"amount": "10260.00", "currency": "EUR"}
    # The event's tax lines carry {tax_type, amount, principal_or_agent} and sum to tax_amount.
    assert billing["tax_lines"] == [
        {
            "tax_type": "VAT",
            "amount": {"amount": "10260.00", "currency": "EUR"},
            "principal_or_agent": "PRINCIPAL",
        }
    ]
    assert sum(Decimal(item["amount"]["amount"]) for item in billing["tax_lines"]) == Decimal(
        billing["tax_amount"]["amount"]
    )
    assert (events[1]["payload"]["invoice_number"], events[1]["payload"]["is_cancellable"]) == (
        "INV-DE-4472",
        True,
    )
    credit = events[2]["payload"]
    assert (
        credit["credit_memo_number"],
        credit["credited_invoice_number"],
        credit["obligation_key"],
        credit["amount"],
        credit["reason"],
    ) == (
        "CM-DE-0091",
        "INV-DE-4471",
        "O1",
        {"amount": "4500.00", "currency": "EUR"},
        "Damaged units",
    )


def test_credit_memo_document_is_stored_signed(k11: K11World) -> None:
    """04 T-SRC-04 ``total_amount`` — "Signed: credit memos negative" — and T-SRC-05 ``amount`` —
    "Signed": the stored credit memo and its line are the negative of the amount the file states,
    an invoice and its line the positive; the ``CREDIT_MEMO_RECORDED`` amount stays the positive
    Money of §16.3 (ruling R-45 (c))."""
    done = committed(k11, "avm-de-invoices-2026-09.csv", csv_bytes(HEADERS, ROWS), "invoices")
    import_id = UUID(done["id"])
    imports = importer(k11)
    documents = imports.rows(
        select(source_invoice).where(source_invoice.c.external_version == str(import_id))
    )
    by_id = {row["id"]: str(row["invoice_number"]) for row in documents}
    assert {str(row["invoice_number"]): Decimal(row["total_amount"]) for row in documents} == {
        "CM-DE-0091": Decimal("-4500.00"),
        "INV-DE-4471": Decimal("54000.00"),
        "INV-DE-4472": Decimal("18000.00"),
    }
    assert {str(row["invoice_number"]): str(row["document_kind"]) for row in documents} == {
        "CM-DE-0091": "CREDIT_MEMO",
        "INV-DE-4471": "INVOICE",
        "INV-DE-4472": "INVOICE",
    }
    lines = imports.rows(
        select(source_invoice_line.c.source_invoice_id, source_invoice_line.c.amount).where(
            source_invoice_line.c.source_invoice_id.in_(list(by_id))
        )
    )
    assert {by_id[row["source_invoice_id"]]: Decimal(row["amount"]) for row in lines} == {
        "CM-DE-0091": Decimal("-4500.00"),
        "INV-DE-4471": Decimal("54000.00"),
        "INV-DE-4472": Decimal("18000.00"),
    }
    [credit] = imports.rows(
        select(contract_event.c.payload).where(
            contract_event.c.import_upload_id == import_id,
            contract_event.c.event_type == "CREDIT_MEMO_RECORDED",
        )
    )
    assert credit["payload"]["amount"] == {"amount": "4500.00", "currency": "EUR"}


def test_repeated_identity_refused_at_import_validation(k11: K11World) -> None:
    """D-97 (30); 04 table 15.4-B rev 1.45: after WLD-F-22 is committed, a second upload repeating
    the cancellable line INV-DE-4472 / 1 with ``is_cancellable = true`` earns
    ``INVOICE_IDENTITY_REPEATED`` and a status update of INV-DE-4471 / 1 with another amount
    ``INVOICE_STATUS_UPDATE_MISMATCH`` (PR-1.3), each on its row and column at validation; the
    upload is INVALID with two BLOCKING exception items and nothing is appended; a new identity
    flagged cancellable stays VALID."""
    committed(k11, "avm-de-invoices-2026-09.csv", csv_bytes(HEADERS, ROWS), "invoices")
    imports = importer(k11)
    repeat = (
        K11_EXTERNAL_ID,
        "INVOICE",
        "INV-DE-4472",
        "2026-09-16",
        "2026-10-16",
        "true",
        "",
        "",
        "1",
        "O2",
        "AVM-SUP-12",
        "1",
        "18000.00",
        "EUR",
        "",
        "",
        "",
        "",
        "",
    )
    mismatch = (
        K11_EXTERNAL_ID,
        "INVOICE",
        "INV-DE-4471",
        "2026-09-12",
        "2026-10-12",
        "false",
        "",
        "",
        "1",
        "O1",
        "AVM-GW",
        "120",
        "60000.00",
        "EUR",
        "",
        "",
        "",
        "",
        "",
    )
    fresh = (K11_EXTERNAL_ID, "INVOICE", "INV-DE-4473", "2026-09-18", "2026-10-18", "true", "", "",
             "1", "O2", "AVM-SUP-12", "1", "18000.00", "EUR", "", "", "", "", "")  # fmt: skip
    import_id, validated = imported(
        imports,
        "avm-de-invoices-2026-09-repeat.csv",
        csv_bytes(HEADERS, (repeat, mismatch, fresh)),
        "invoices",
    )
    assert validated["status"] == "INVALID", validated
    counts = validated["counts"]
    assert (counts["rows"], counts["valid"], counts["errors"]) == (3, 1, 2)
    assert validated["finding_counts"] == [
        {"code": "INVOICE_IDENTITY_REPEATED", "severity": "ERROR", "rows": 1},
        {"code": "INVOICE_STATUS_UPDATE_MISMATCH", "severity": "ERROR", "rows": 1},
    ]
    listed = get(k11.app, f"/api/v1/imports/{import_id}/rows", imports.actor)
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert {item["row_number"]: item["status"] for item in items} == {
        2: "ERROR",
        3: "ERROR",
        4: "VALID",
    }
    assert {
        item["row_number"]: [message["message"] for message in item["messages"]]
        for item in items
        if item["status"] == "ERROR"
    } == {
        2: [
            "Row 2, column Invoice number: Invoice INV-DE-4472, line 1 is already recorded on "
            "NS-SO-DE-5004; a re-issued cancellable invoice carries a new invoice number or line "
            "reference. (INVOICE_IDENTITY_REPEATED)"
        ],
        3: [
            "Row 3, column Lines amount amount: Invoice INV-DE-4471, line 1: the status update "
            "carries 60000.00 EUR, but the original line is 54000.00 EUR. A status update cannot "
            "change the amount; send a credit memo or a new invoice. "
            "(INVOICE_STATUS_UPDATE_MISMATCH)"
        ],
    }
    exceptions = imports.rows(
        select(exception_item.c.code, exception_item.c.severity, exception_item.c.status).where(
            exception_item.c.import_upload_id == UUID(import_id)
        )
    )
    assert sorted(
        (str(row["code"]), str(row["severity"]), str(row["status"])) for row in exceptions
    ) == [
        ("INVOICE_IDENTITY_REPEATED", "BLOCKING", "OPEN"),
        ("INVOICE_STATUS_UPDATE_MISMATCH", "BLOCKING", "OPEN"),
    ]
    assert (
        imports.rows(
            select(contract_event.c.id).where(contract_event.c.import_upload_id == UUID(import_id))
        )
        == []
    )


def test_refund_bound_reads_kept_lines_at_import_validation(k11: K11World) -> None:
    """VOID-3a at the import channel: after WLD-F-22 is committed (INV-DE-4471 line 1: 54,000.00 on
    O1, credited 4,500.00), a second upload carrying a same-amount status update of that line, a
    60,000.00 credit memo and a 40,000.00 credit memo on O1: the update adds nothing to the kept
    billing, so the 60,000.00 memo exceeds the 49,500.00 still billed and earns
    ``REFUND_EXCEEDS_BILLED`` at validation on its row; the update and the 40,000.00 memo stay
    VALID; the upload is INVALID and nothing is appended."""
    committed(k11, "avm-de-invoices-2026-09.csv", csv_bytes(HEADERS, ROWS), "invoices")
    imports = importer(k11)
    update = (
        K11_EXTERNAL_ID,
        "INVOICE",
        "INV-DE-4471",
        "2026-09-12",
        "2026-10-12",
        "false",
        "",
        "",
        "1",
        "O1",
        "AVM-GW",
        "120",
        "54000.00",
        "EUR",
        "",
        "",
        "",
        "",
        "",
    )
    over = (
        K11_EXTERNAL_ID,
        "CREDIT_MEMO",
        "CM-DE-0092",
        "2026-09-21",
        "",
        "",
        "INV-DE-4471",
        "Returned units",
        "1",
        "O1",
        "AVM-GW",
        "100",
        "60000.00",
        "EUR",
        "",
        "",
        "",
        "",
        "",
    )
    within = (
        K11_EXTERNAL_ID,
        "CREDIT_MEMO",
        "CM-DE-0093",
        "2026-09-22",
        "",
        "",
        "INV-DE-4471",
        "Price concession",
        "1",
        "O1",
        "AVM-GW",
        "0",
        "40000.00",
        "EUR",
        "",
        "",
        "",
        "",
        "",
    )
    import_id, validated = imported(
        imports,
        "avm-de-invoices-2026-09-credits.csv",
        csv_bytes(HEADERS, (update, over, within)),
        "invoices",
    )
    assert validated["status"] == "INVALID", validated
    counts = validated["counts"]
    assert (counts["rows"], counts["valid"], counts["errors"]) == (3, 2, 1)
    assert validated["finding_counts"] == [
        {"code": "REFUND_EXCEEDS_BILLED", "severity": "ERROR", "rows": 1}
    ]
    listed = get(k11.app, f"/api/v1/imports/{import_id}/rows", imports.actor)
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert {item["row_number"]: item["status"] for item in items} == {
        2: "VALID",
        3: "ERROR",
        4: "VALID",
    }
    [invalid] = [item for item in items if item["status"] == "ERROR"]
    assert [message["message"] for message in invalid["messages"]] == [
        "Row 3, column Lines amount amount: Credit of 60000.00 exceeds the 49500.00 billed on "
        "NS-SO-DE-5004, obligation O1 (AVM-GW). (REFUND_EXCEEDS_BILLED)"
    ]
    assert (
        imports.rows(
            select(contract_event.c.id).where(contract_event.c.import_upload_id == UUID(import_id))
        )
        == []
    )


def _blank_tax() -> tuple[str, ...]:
    return ("", "", "", "", "")


def _row_statuses(world: K11World, imports: ImportWorld, import_id: str) -> dict[int, str]:
    listed = get(world.app, f"/api/v1/imports/{import_id}/rows", imports.actor)
    assert listed.status_code == 200, listed.text
    return {item["row_number"]: item["status"] for item in listed.json()["items"]}


def _error_messages(world: K11World, imports: ImportWorld, import_id: str) -> list[str]:
    listed = get(world.app, f"/api/v1/imports/{import_id}/rows", imports.actor)
    assert listed.status_code == 200, listed.text
    [invalid] = [item for item in listed.json()["items"] if item["status"] == "ERROR"]
    return [message["message"] for message in invalid["messages"]]


def test_d98_103_referenced_credit_cover_at_import_validation(k11: K11World) -> None:
    """D-98 103 (BOUND-R1) at the import channel on the active K-11 (nothing billed yet): an
    invoice of 300.00 naming no obligation, a 200.00 credit on O1 (covered by the unreferenced
    billing; the own-bucket channel refused it), a 150.00 credit on O2 (only 100.00 of cover is
    left) and a 100.00 credit on O2 → rows VALID / VALID / ERROR / VALID, the refusal located on
    the third with the remaining cover named; nothing appended."""
    imports = importer(k11)
    unreferenced = (K11_EXTERNAL_ID, "INVOICE", "INV-DE-5010", "2026-09-16", "2026-10-16", "false",
                    "", "", "1", "", "", "", "300.00", "EUR", *_blank_tax())  # fmt: skip
    covered = (K11_EXTERNAL_ID, "CREDIT_MEMO", "CM-DE-5010", "2026-09-21", "", "", "INV-DE-5010",
               "Goodwill", "1", "O1", "AVM-GW", "0", "200.00", "EUR", *_blank_tax())  # fmt: skip
    over = (K11_EXTERNAL_ID, "CREDIT_MEMO", "CM-DE-5011", "2026-09-22", "", "", "INV-DE-5010",
            "Goodwill", "1", "O2", "AVM-SUP-12", "0", "150.00", "EUR", *_blank_tax())  # fmt: skip
    within = (K11_EXTERNAL_ID, "CREDIT_MEMO", "CM-DE-5012", "2026-09-23", "", "", "INV-DE-5010",
              "Goodwill", "1", "O2", "AVM-SUP-12", "0", "100.00", "EUR", *_blank_tax())  # fmt: skip
    import_id, validated = imported(
        imports,
        "avm-de-invoices-2026-09-cover.csv",
        csv_bytes(HEADERS, (unreferenced, covered, over, within)),
        "invoices",
    )
    assert validated["status"] == "INVALID", validated
    counts = validated["counts"]
    assert (counts["rows"], counts["valid"], counts["errors"]) == (4, 3, 1)
    assert _row_statuses(k11, imports, import_id) == {
        2: "VALID",
        3: "VALID",
        4: "ERROR",
        5: "VALID",
    }
    assert _error_messages(k11, imports, import_id) == [
        "Row 4, column Lines amount amount: Credit of 150.00 exceeds the 100.00 billed on "
        "NS-SO-DE-5004, obligation O2 (AVM-SUP-12). (REFUND_EXCEEDS_BILLED)"
    ]
    assert (
        imports.rows(
            select(contract_event.c.id).where(contract_event.c.import_upload_id == UUID(import_id))
        )
        == []
    )


def _parity_preset(world: K11World) -> None:
    """The TENANT accounting policy set carries ``LEGACY_PARITY`` (as ``support.legacy_replay``
    publishes it), so stage 01 and the channel treat VC-stratified lines as parity VC lines."""
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values=presets.legacy_parity_values(scope=RegistryScope.TENANT, book_code=None),
            preset_code=presets.LEGACY_PARITY,
        )


def test_d98_103_parity_vc_line_credit_is_out_of_scope_at_import_validation(
    k11: K11World,
) -> None:
    """D-98 103 (BOUND-R2; the engine's ``test_s01_vc_line_credit`` shape): under the effective
    ``LEGACY_PARITY`` preset a credit memo on a VC-stratified booking line is not bound-checked
    (stage 01 ``_vc_lines``; S03-R-18; DEV-022) and the VC line stays out of the stream an
    unreferenced credit draws on: with 200.00 billed on O1, a 100.00 credit on VC1 is VALID (the
    channel refused it before), an unreferenced 200.00 credit is VALID and an unreferenced 200.01
    credit is refused with nothing left to draw on."""
    _parity_preset(k11)
    body = {**k11_body(k11.customer_id), "external_id": "NS-SO-DE-5011"}
    body["lines"] = [
        *body["lines"],
        {
            "obligation_key": "VC1",
            "product_code": "AVM-SUP-12",
            "stratification": "VC",
            "quantity": "1",
            "total_price": {"amount": "-200.00", "currency": "EUR"},
        },
    ]
    booked_contract(k11.place, body, activate=False)
    imports = importer(k11)
    billing = ("NS-SO-DE-5011", "INVOICE", "INV-DE-5011", "2026-09-12", "2026-10-12", "false", "",
               "", "1", "O1", "AVM-GW", "10", "200.00", "EUR", *_blank_tax())  # fmt: skip
    vc_credit = ("NS-SO-DE-5011", "CREDIT_MEMO", "CM-DE-5011", "2026-09-13", "", "",
                 "INV-DE-5011", "VC true-up", "1", "VC1", "AVM-SUP-12", "0", "100.00", "EUR",
                 *_blank_tax())  # fmt: skip
    stream_credit = ("NS-SO-DE-5011", "CREDIT_MEMO", "CM-DE-5012", "2026-09-14", "", "",
                     "INV-DE-5011", "Goodwill", "1", "", "", "", "200.00", "EUR",
                     *_blank_tax())  # fmt: skip
    over = ("NS-SO-DE-5011", "CREDIT_MEMO", "CM-DE-5013", "2026-09-15", "", "", "INV-DE-5011",
            "Goodwill", "1", "", "", "", "200.01", "EUR", *_blank_tax())  # fmt: skip
    import_id, validated = imported(
        imports,
        "avm-de-invoices-2026-09-parity-vc.csv",
        csv_bytes(HEADERS, (billing, vc_credit, stream_credit, over)),
        "invoices",
    )
    assert validated["status"] == "INVALID", validated
    counts = validated["counts"]
    assert (counts["rows"], counts["valid"], counts["errors"]) == (4, 3, 1)
    assert _row_statuses(k11, imports, import_id) == {
        2: "VALID",
        3: "VALID",
        4: "VALID",
        5: "ERROR",
    }
    assert _error_messages(k11, imports, import_id) == [
        "Row 5, column Lines amount amount: Credit of 200.01 exceeds the 0.00 billed on "
        "NS-SO-DE-5011. (REFUND_EXCEEDS_BILLED)"
    ]


@pytest.mark.parametrize("corruption", ["source_amount", "event_amount", "source_tax"])
def test_monetary_mismatch_rolls_back_invoice_batch(
    k11: K11World, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    from erev_api.domain.imports.csv_v2 import invoices

    imports = importer(k11)
    import_id = diffed(imports, "amount-check.csv", csv_bytes(HEADERS, ROWS[:1]), "invoices")
    submitted = submit(imports, import_id)
    assert submitted.status_code == 200
    assert (
        approve(k11.app, str(submitted.json()["approval_request_id"]), k11.priya).status_code == 200
    )
    if corruption == "event_amount":
        original_items = invoices._items

        def changed_items(body: Any, invoice_id: Any) -> Any:
            altered = copy.deepcopy(body)
            altered["lines"][0]["amount"]["amount"] = "53999.00"
            return original_items(altered, invoice_id)

        monkeypatch.setattr(invoices, "_items", changed_items)
    else:
        original_store = invoices._store

        def changed_store(uow: Any, plan: Any, context: Any, body: Any) -> Any:
            altered = copy.deepcopy(body)
            if corruption == "source_amount":
                altered["lines"][0]["amount"]["amount"] = "53999.00"
            else:
                altered["lines"][0]["tax_lines"] = []
            return original_store(uow, plan, context, altered)

        monkeypatch.setattr(invoices, "_store", changed_store)
    run_import_job(imports, job_of(imports, UUID(import_id), "IMPORT_COMMIT"))
    done = shown(imports, import_id)
    assert done["status"] == "FAILED", done
    (finding,) = imports.rows(
        select(exception_item).where(
            exception_item.c.import_upload_id == UUID(import_id),
            exception_item.c.code == "CONTROL_TOTALS_MISMATCH",
        )
    )
    assert finding["severity"] == "BLOCKING"
    assert "Written amounts do not match the file." in finding["message"]
    (check,) = done["control_totals"]["loaded"]["monetary_checks"]
    assert check["source"] != check["stored"]
    assert (
        imports.rows(
            select(source_invoice.c.id).where(source_invoice.c.external_version == import_id)
        )
        == []
    )
    for table in (contract_event, source_record, import_row_lineage):
        assert (
            imports.rows(select(table.c.id).where(table.c.import_upload_id == UUID(import_id)))
            == []
        )
    assert (
        imports.rows(
            select(job.c.id).where(
                job.c.kind == "CONTRACT_COMPUTE",
                job.c.params["import_upload_id"].astext == import_id,
            )
        )
        == []
    )


def test_reconciliation_counts_repeated_tax_rows_without_doubling_the_invoice(
    k11: K11World,
) -> None:
    second = list(ROWS[0])
    second[HEADERS.index("lines.tax_lines.tax_type")] = "OTHER"
    second[HEADERS.index("lines.tax_lines.amount.amount")] = "100.00"
    done = committed(k11, "two-taxes.csv", csv_bytes(HEADERS, [ROWS[0], second]), "invoices")
    loaded = done["control_totals"]["loaded"]
    assert {key: Decimal(value) for key, value in loaded["amount_sums"].items()} == {
        "lines.amount.amount": Decimal("108000"),
        "lines.tax_lines.amount.amount": Decimal("10360"),
    }
    (check,) = loaded["monetary_checks"]
    assert check["source"] == check["stored"]
    assert check["stored"]["total_amount"] == "54000"
    assert check["stored"]["tax_amount"] == "10360"
    assert len(check["stored"]["lines"]) == len(check["stored"]["events"]) == 1
