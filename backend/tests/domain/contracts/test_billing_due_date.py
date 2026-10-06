"""An invoice on ordinary payment terms computes (item ENG-S12-DUE-DATE-1; ENGINE_SPEC_B S12-R-04
rev 1.83, S12-INV-03, S10-R-06; POLICIES POL-160, ALG-08 §2.9.1 rev 1.52; supervisor ruling R-81 of
2026-09-30, amending D-87 L6-5-Q-14).

The finding, measured by lane F-RPS-REG through the public route and reproduced here before the
rule: a ``BILLING_RECORDED`` whose ``due_date`` lies in a later accounting period than its issue
date left the contract's computation ``QUARANTINED`` — ``ENGINE_INVARIANT_VIOLATION``, rule
S12-INV-03, layers −89,285.71 against a position of 10,714.29, the difference being the invoice —
and nothing posted for the contract afterwards. The position counted the invoice from its issue
date (S10-R-06) while the contract-liability layer waited for the due date (D-87 L6-5-Q-14).

The rule holds the layer date inside the accounting period in which the line enters the position,
so the invoice computes, and in one currency every figure is the one the same invoice gives
without a due date. Witnessed on the database through ``POST /contracts/{id}/events`` on K-07 (EUR
contract, EUR entity, ``billing.posting`` ``ERP``, ASC606), each shape beside its control: issued
on 31 August and due on 30 September with August open; issued on 12 September and due on 12
October; and the August invoice recorded after August is locked (a late event). The engine-level
witnesses are ``tests/engine/s13_books/test_s13_layer_period.py`` and
``tests/engine/s12_fx_entities/test_s12_layers.py``.

Maya (Revenue Accountant) records the invoice.
"""

from __future__ import annotations

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, exception_item
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import worlds
from support.billing_lines import period_balance
from support.db import TestDatabase
from support.factories import computed
from support.reference import post

AUGUST, SEPTEMBER = "FY2026-P08", "FY2026-P09"
INVOICE = "100000.00"  # EUR; the contract has recognised 89,285.71 by the end of August
LIABILITY = 1_071_429  # 100,000.00 − 89,285.71, minor units
ASSET = 8_928_571  # the unbilled revenue at the August close when the invoice is of September


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.mark.parametrize(
    ("issue", "due", "august_locked", "layer_date"),
    [
        pytest.param("2026-08-31", "2026-09-30", False, "2026-08-31", id="august_due_september"),
        pytest.param("2026-08-31", None, False, "2026-08-31", id="august_no_due_date"),
        pytest.param("2026-09-12", "2026-10-12", False, "2026-09-30", id="september_due_october"),
        pytest.param("2026-09-12", None, False, "2026-09-12", id="september_no_due_date"),
        pytest.param("2026-08-31", "2026-09-30", True, "2026-08-31", id="late_due_september"),
        pytest.param("2026-08-31", None, True, "2026-08-31", id="late_no_due_date"),
    ],
)
def test_an_invoice_on_payment_terms_computes_as_without_a_due_date(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    issue: str,
    due: str | None,
    august_locked: bool,
    layer_date: str,
) -> None:
    """EUR 100,000.00 invoiced on K-07 through the events route. With a due date in the next
    period the command's computation is ``SUCCEEDED`` and leaves no blocking exception, as without
    a due date: contract liability 10,714.29 from the period of the invoice on (an August invoice:
    August and September; a September invoice: a contract asset of 89,285.71 at the August close,
    then the liability). The layer is created inside the period in which the position counts the
    invoice — on the issue date when the due date is absent, on the period's last day when the due
    date lies beyond it — and a recompute posts nothing more. An August invoice recorded after
    August is locked is a late event in both forms (``LATE_EVENT``, a warning). Before the rule
    the three cases with a due date were ``QUARANTINED`` on S12-INV-03."""
    build = worlds.k07_august_locked if august_locked else worlds.k07_delivered
    world = build(app, keyring, clock, files)
    place = world.report.place
    head = place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == world.contract_id)
    )
    payload = {
        "invoice_number": "INV-DE-4390",
        "line_external_id": "1",
        "amount": {"amount": INVOICE, "currency": "EUR"},
        "issue_date": issue,
        **({} if due is None else {"due_date": due}),
    }
    event = {"event_type": "BILLING_RECORDED", "effective_date": issue, "payload": payload}
    sent = post(
        app,
        f"/api/v1/contracts/{world.contract_id}/events",
        world.report.maya,
        {"events": [event]},
        if_match=f'"s{int(head)}"',
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["computation"]["status"] == "SUCCEEDED", sent.text
    raised = place.rows(select(exception_item.c.code, exception_item.c.severity))
    assert [(str(row["code"]), str(row["severity"])) for row in raised] == (
        [("LATE_EVENT", "WARNING")] if august_locked else []
    )

    _, output, _ = computed(place, world.group_id)
    (book,) = output.books
    assert book.book_code == "ASC606"
    in_august = issue.startswith("2026-08")
    assert (
        period_balance(book, AUGUST, "contract_liability_txn"),
        period_balance(book, AUGUST, "contract_asset_txn"),
    ) == ((LIABILITY, 0) if in_august else (0, ASSET))
    assert (
        period_balance(book, SEPTEMBER, "contract_liability_txn"),
        period_balance(book, SEPTEMBER, "contract_asset_txn"),
    ) == (LIABILITY, 0)
    assert [
        (str(move.columns["effective_date"]), int(str(move.columns["amount_txn"])))
        for move in book.fx_layer_movements
        if move.columns.get("movement_kind") == "LIABILITY_LAYER_CREATED"
    ] == [(layer_date, LIABILITY)]
    assert book.posting_intents == ()
