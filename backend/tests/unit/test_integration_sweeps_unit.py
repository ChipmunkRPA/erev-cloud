"""SCH-09 and the DIN-13 sync additions, CPU only (05 §5.7 SCH-09; 04 table 15.4-A / 15.4-B
``CONTRACT_NOT_FOUND`` / ``SOURCE_VERSION_GAP``; PRD §5.5 IMP-20, IMP-126; 03 REQ-INT-007;
BUILD_SPEC DIN-13): the six-hour bucket of a sweep request, the periodic's registration, the
exception copy against the PRD rows, and the document event items against the §16.3 payloads. The
database behaviour is in ``tests/domain/integrations``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api import worker
from erev_api.domain.integrations import commands, documents, ports, sweeps, sync
from erev_api.domain.integrations.outbox import sync_request_key
from erev_api.enums import ContractEventType, SourceObjectType, SourceSystem, TenantKind
from erev_api.events import payloads

PRD = Path(__file__).resolve().parents[3] / "docs" / "02-PRD.md"


def test_bucket_of_is_the_six_hour_utc_bucket() -> None:
    assert sweeps.bucket_of(datetime(2026, 9, 12, 12, 0, tzinfo=UTC)) == "2026-09-12T12"
    assert sweeps.bucket_of(datetime(2026, 9, 12, 17, 59, 59, tzinfo=UTC)) == "2026-09-12T12"
    assert sweeps.bucket_of(datetime(2026, 9, 12, 18, 0, tzinfo=UTC)) == "2026-09-12T18"
    assert sweeps.bucket_of(datetime(2026, 9, 12, 5, 30, tzinfo=UTC)) == "2026-09-12T00"
    # an instant stated in another zone is bucketed in UTC
    pacific = timezone(timedelta(hours=-7))
    assert sweeps.bucket_of(datetime(2026, 9, 12, 23, 30, tzinfo=pacific)) == "2026-09-13T06"
    connection = UUID(int=0xC1)
    assert sync_request_key(connection, sweeps.KIND, "2026-09-12T12") == (
        f"sync:{connection}:RECONCILIATION_SWEEP:2026-09-12T12"
    )


def test_sch_09_periodic_runs_every_bucket_on_maintenance() -> None:
    """05 SCH-09: ``integration_sweeps`` at ``0 */6 * * *``; the dedupe bucket is the cron's
    period, so each firing asks once and no firing is skipped."""
    periodic = {
        key[0]: task.cron for key, task in worker.app.periodic_registry.periodic_tasks.items()
    }
    assert periodic[worker.INTEGRATION_SWEEPS_TASK] == f"0 */{sweeps.BUCKET_HOURS} * * *"
    task = worker.app.tasks[worker.INTEGRATION_SWEEPS_TASK]
    assert (task.queue, task.queueing_lock) == ("maintenance", "erev.integration_sweeps")
    assert sweeps.KIND in commands.INBOUND_KINDS  # a kind ``/sync`` admits for inbound adapters


def _prd_copy(row_id: str) -> str:
    [line] = [
        text
        for text in PRD.read_text(encoding="utf-8").splitlines()
        if text.startswith(f"| {row_id} |")
    ]
    cell = line.rstrip().rstrip("|").rsplit("|", 1)[1].strip()
    assert cell.startswith('"') and cell.endswith('"'), cell
    return cell[1:-1]


def _as_template(copy: str) -> str:
    return re.sub(r"<([a-z ]+)>", lambda found: "{" + found.group(1).replace(" ", "_") + "}", copy)


def test_gap_and_contract_not_found_copy_is_the_prd_copy() -> None:
    """PRD IMP-126 and IMP-20: the message the sync raises is the catalogue copy, placeholder for
    placeholder."""
    assert _as_template(_prd_copy("IMP-126")) == sync.GAP_MESSAGE
    assert _as_template(_prd_copy("IMP-20")) == sync.CONTRACT_NOT_FOUND_MESSAGE
    assert sync.GAP_MESSAGE.format(
        source_system="STRIPE", object="INVOICE", external_id="in_DEMO0001", version="2"
    ) == (
        "STRIPE INVOICE in_DEMO0001 version 2 had not been received when the reconciliation sweep"
        " found it. The sweep recorded it and processed it as a delivered version."
    )


def _draft(kind: str, **over: object) -> ports.NormalisedInvoiceDraft:
    values: dict[str, object] = {
        "source_system": SourceSystem.STRIPE,
        "external_invoice_id": "in_DEMO0001",
        "external_version": "2",
        "document_kind": kind,
        "invoice_number": "QUAY-0001",
        "issue_date": date(2026, 9, 1),
        "customer_external_id": "cus_DEMO0001",
        "currency": "USD",
        "lines": (
            ports.NormalisedInvoiceLine(
                line_external_id="il_DEMO0001",
                product_code="QUAY-PLAT",
                amount=Decimal("1200.00"),
                service_period_start=date(2026, 9, 1),
                service_period_end=date(2027, 8, 31),
                contract_ref="sub_DEMO0001",
            ),
        ),
        "due_date": date(2026, 10, 1),
    }
    values.update(over)
    return ports.NormalisedInvoiceDraft(**values)  # type: ignore[arg-type]


def test_document_event_items_are_the_16_3_payloads() -> None:
    """04 §16.3: an invoice line is a ``BILLING_RECORDED`` with its service period as the hint and
    the stored document's id; a credit note line a ``CREDIT_MEMO_RECORDED`` naming the credited
    invoice by NUMBER; both parse as the latest payload model and are effective on the issue
    date."""
    invoice_id = UUID(int=0x51)
    invoice = _draft("INVOICE")
    [billing] = documents.event_items(
        invoice, invoice.lines, source_invoice_id=invoice_id, credited_invoice_number=None
    )
    assert billing.event_type is ContractEventType.BILLING_RECORDED
    assert billing.effective_date == date(2026, 9, 1) and billing.obligation_key is None
    assert billing.payload == {
        "invoice_number": "QUAY-0001",
        "line_external_id": "il_DEMO0001",
        "amount": {"amount": "1200.00", "currency": "USD"},
        "issue_date": "2026-09-01",
        "due_date": "2026-10-01",
        "service_period_start": "2026-09-01",
        "service_period_end": "2027-08-31",
        "source_invoice_id": str(invoice_id),
    }
    note = _draft(
        "CREDIT_MEMO",
        external_invoice_id="cn_DEMO0001",
        external_version="1",
        invoice_number="QUAY-CN-0001",
        issue_date=date(2026, 9, 6),
        due_date=None,
        credited_invoice_external_id="in_DEMO0001",
        lines=(
            ports.NormalisedInvoiceLine(
                line_external_id="cnli_DEMO0001", product_code="QUAY-PLAT", amount=Decimal("100.00")
            ),
        ),
    )
    assert format(note.total, "f") == "-100.00"  # the billing movement; the event amount is > 0
    [credit] = documents.event_items(
        note, note.lines, source_invoice_id=invoice_id, credited_invoice_number="QUAY-0001"
    )
    assert credit.event_type is ContractEventType.CREDIT_MEMO_RECORDED
    assert credit.payload == {
        "credit_memo_number": "QUAY-CN-0001",
        "credited_invoice_number": "QUAY-0001",
        "amount": {"amount": "100.00", "currency": "USD"},
        "issue_date": "2026-09-06",
    }
    for item in (billing, credit):
        payloads.parse_payload(
            item.event_type, payloads.LATEST_SCHEMA_VERSION[item.event_type], dict(item.payload)
        )
    assert documents.object_type_of(invoice) is SourceObjectType.INVOICE
    assert documents.object_type_of(note) is SourceObjectType.CREDIT_MEMO
    assert documents.LINK_ROLE == "INVOICE"


def test_counts_state_the_sweep_and_document_outcomes() -> None:
    counts = sync.Counts(gaps=2, documents=3, billing_events=4, credit_memo_events=1)
    stated = counts.as_json()
    assert (stated["gaps"], stated["documents"]) == (2, 3)
    assert (stated["billing_events"], stated["credit_memo_events"]) == (4, 1)


class _Uow:
    """The slice of a unit of work ``sweeps.run`` uses."""

    def __init__(self, tenant_id: UUID, kind: TenantKind, now: datetime) -> None:
        self.session = tenant_id  # the fakes below key their answers by tenant
        self.ctx = SimpleNamespace(tenant_kind=kind)
        self.now = now
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def test_sch_09_asks_once_per_connection_and_skips_sandboxes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SCH-09, SBX-08: per ACTIVE tenant, one request per ACTIVE inbound connection not yet
    asked for in the bucket, committed per tenant; a sandbox's connections are counted and
    skipped (the relay would refuse them 403 ``sandbox-restricted``); a tenant without connections
    commits nothing."""
    now = datetime(2026, 9, 12, 13, 0, tzinfo=UTC)
    production, sandbox, empty = UUID(int=1), UUID(int=2), UUID(int=3)
    found = {
        production: [UUID(int=0xA1), UUID(int=0xA2), UUID(int=0xA3)],
        sandbox: [UUID(int=0xB1)],
        empty: [],
    }
    kinds = {
        production: TenantKind.PRODUCTION,
        sandbox: TenantKind.SANDBOX,
        empty: TenantKind.PRODUCTION,
    }
    opened: dict[UUID, _Uow] = {}
    asked: list[tuple[UUID, str, str]] = []

    @contextmanager
    def unit(runtime: Any, principal: Any, *, request_id: str) -> Iterator[_Uow]:
        assert request_id == sweeps.REQUEST_ID
        opened[principal.tenant_id] = _Uow(principal.tenant_id, kinds[principal.tenant_id], now)
        yield opened[principal.tenant_id]

    monkeypatch.setattr(sweeps, "active_tenants", lambda runtime, *, request_id, only: list(found))
    monkeypatch.setattr(sweeps, "system_unit_of_work", unit)
    monkeypatch.setattr(sweeps, "sweepable_connections", lambda session: found[session])
    monkeypatch.setattr(
        sweeps, "_asked", lambda session, connection_id, bucket: connection_id == UUID(int=0xA2)
    )
    monkeypatch.setattr(
        sweeps,
        "enqueue_sync_request",
        lambda uow, *, connection_id, kind, bucket: asked.append((connection_id, kind, bucket)),
    )
    report = sweeps.run(SimpleNamespace())  # type: ignore[arg-type]
    assert report == sweeps.SweepReport(
        tenants=3, connections=4, requested=2, repeated=1, sandbox_skipped=1
    )
    assert asked == [
        (UUID(int=0xA1), "RECONCILIATION_SWEEP", "2026-09-12T12"),
        (UUID(int=0xA3), "RECONCILIATION_SWEEP", "2026-09-12T12"),
    ]
    assert {tenant: uow.commits for tenant, uow in opened.items()} == {
        production: 1,
        sandbox: 0,
        empty: 0,
    }


def test_checkpoint_states_swept_at_only_once_a_sweep_completed() -> None:
    """04 T-INT-01 ``checkpoint`` (rev 1.103): ``swept_at`` is absent until a sweep ran to
    completion, so the checkpoints adapters answer and the stored JSON of a connection that never
    swept are what they were; once set it round-trips."""
    never = ports.Checkpoint(replay_id=5, replay_at=datetime(2026, 9, 12, 12, 0, tzinfo=UTC))
    assert "swept_at" not in never.as_json()
    assert ports.Checkpoint.from_json(never.as_json()) == never
    swept = ports.Checkpoint(replay_id=5, swept_at=datetime(2026, 9, 12, 18, 0, tzinfo=UTC))
    assert swept.as_json()["swept_at"] == "2026-09-12T18:00:00+00:00"
    assert ports.Checkpoint.from_json(swept.as_json()) == swept
    assert ports.Checkpoint.from_json({}).swept_at is None
    # an explicit sweep keeps the marker: force_sweep changes what makes a sweep due, nothing else
    assert sync.force_sweep(swept).swept_at == swept.swept_at
