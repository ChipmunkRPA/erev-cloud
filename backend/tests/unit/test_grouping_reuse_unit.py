"""04 §16.14 rev 1.81 (amended in place; Codex 0545 §2 R1 / 0603 §4 / 0606; team-lead's accepted
three-class design): a stored ``source_order`` identity is REUSED, never stored again; the reuse is
checked BEFORE any write — class A retained source-authored facts must equal the stored rows (the
retained tokenised payload digest, header and line members incl. the SOURCE product code) else
``SOURCE_ORDER_CONTENT_MISMATCH``; class B (the product resolution) is re-derived; class C members
derived from the current connection configuration or mapping must equal the values frozen at first
ingestion else ``SOURCE_ORDER_DERIVATION_CHANGED``. Both refusals are the object's failure record;
``record_candidate`` / ``ingest_order`` execute no INSERT on an existing identity."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects
from erev_api.domain.integrations import grouping, ports
from erev_api.domain.integrations import sync as sync_module
from erev_api.domain.reference import commands as reference_commands
from erev_api.enums import SourceObjectType, SourceSystem
from sqlalchemy.dialects import postgresql

STORED_ORDER = UUID(int=0x50)
STORED_RECORD = UUID(int=0x51)
INCOMING_RECORD = UUID(int=0x52)
CUSTOMER = UUID(int=0xC5)
NOW = datetime(2026, 9, 22, 6, 0, tzinfo=UTC)
LINE = "SF-OI-Q-010-1"
TENANT = UUID(int=0x7E)
PLAT = UUID(int=0xA1)
PRINCIPAL = SimpleNamespace(tenant_id=TENANT)  # what the reuse check reads: the tenant id


def _draft(**over: Any) -> ports.NormalisedOrderDraft:
    values: dict[str, Any] = {
        "source_system": SourceSystem.SALESFORCE,
        "external_order_id": "SF-ORD-Q-010",
        "external_version": "1",
        "order_number": "Q-010",
        "order_date": date(2026, 9, 18),
        "customer_external_id": "ACC-QUAY-1001",
        "legal_entity_code": "QUAY-US",
        "transaction_currency": "USD",
        "lines": (
            ports.NormalisedLine(
                LINE,
                "SF-PROD-X99",
                Decimal(1),
                Decimal("5000.00"),
                performing_entity_code="QUAY-US",
            ),
        ),
        "document_ref": "SF-ORD-Q-010",
        "custom_attributes": {"mapping_version": "SF-ORDERS-v1"},
    }
    values.update(over)
    return ports.NormalisedOrderDraft(**values)


def _stored(*, header: dict[str, Any] | None = None, lines: dict[str, Any] | None = None) -> Any:
    base_header: dict[str, Any] = {
        "id": STORED_ORDER,
        "source_record_id": STORED_RECORD,
        "order_number": "Q-010",
        "order_date": date(2026, 9, 18),
        "customer_external_id": "ACC-QUAY-1001",
        "customer_id": CUSTOMER,
        "legal_entity_code": "QUAY-US",
        "transaction_currency": "USD",
        "po_number": None,
        "parent_order_external_id": None,
        "amendment_reason": None,
        "document_ref": "SF-ORD-Q-010",
        "grouping_values": {},
        "custom_attributes": {"mapping_version": "SF-ORDERS-v1"},
    }
    base_header.update(header or {})
    base_line: dict[str, Any] = {
        "line_external_id": LINE,
        "product_code": "SF-PROD-X99",  # the SOURCE code — never the alias
        "product_id": None,
        "quantity": Decimal("1.0000"),
        "total_price": Decimal("5000.0000"),
        "start_date": None,
        "end_date": None,
        "performing_entity_code": "QUAY-US",
    }
    base_line.update(lines or {})
    return grouping.StoredOrder(
        id=STORED_ORDER,
        source_record_id=STORED_RECORD,
        header=base_header,
        lines={LINE: base_line},
    )


def _order(record: UUID = INCOMING_RECORD) -> grouping.NormalisedOrder:
    return grouping.NormalisedOrder(
        source_system=SourceSystem.SALESFORCE,
        source_record_id=record,
        external_order_id="SF-ORD-Q-010",
        external_version="1",
        order_number="Q-010",
        order_date=date(2026, 9, 18),
        customer_external_id="ACC-QUAY-1001",
        customer_id=CUSTOMER,
        legal_entity_code="QUAY-US",
        transaction_currency="USD",
        lines=(grouping.OrderLine(LINE, "QUAY-ADDON", Decimal(1), Decimal("5000.00")),),
    )


# --- class A --------------------------------------------------------------------------------------


def test_identical_retained_facts_have_no_conflict_even_when_the_alias_rewrites_the_code() -> None:
    # the class-A comparison reads the ORIGINAL draft: the SOURCE code SF-PROD-X99 on both sides
    assert grouping.content_conflicts(_stored(), _draft(), same_content=True) == []


def test_a_different_retained_digest_is_a_content_conflict() -> None:
    assert grouping.content_conflicts(_stored(), _draft(), same_content=False) == ["payload_sha256"]


@pytest.mark.parametrize(
    ("over", "expected"),
    [
        ({"quantity": Decimal(2)}, [f"lines.{LINE}.quantity"]),
        ({"total_price": Decimal("5100.00")}, [f"lines.{LINE}.total_price"]),
        ({"start_date": date(2026, 10, 1)}, [f"lines.{LINE}.start_date"]),
        ({"end_date": date(2027, 9, 30)}, [f"lines.{LINE}.end_date"]),
    ],
)
def test_changed_line_money_quantity_or_dates_are_named(
    over: dict[str, Any], expected: list[str]
) -> None:
    line = ports.NormalisedLine(
        LINE,
        "SF-PROD-X99",
        over.get("quantity", Decimal(1)),
        over.get("total_price", Decimal("5000.00")),
        start_date=over.get("start_date"),
        end_date=over.get("end_date"),
        performing_entity_code="QUAY-US",
    )
    assert (
        grouping.content_conflicts(_stored(), _draft(lines=(line,)), same_content=True) == expected
    )


def test_changed_header_facts_and_line_set_are_named() -> None:
    other = ports.NormalisedLine(
        "SF-OI-Q-010-9", "QUAY-SVC", Decimal(1), Decimal("1.00"), performing_entity_code="QUAY-US"
    )
    found = grouping.content_conflicts(
        _stored(),
        _draft(
            order_number="Q-010B",
            order_date=date(2026, 9, 19),
            customer_external_id="ACC-QUAY-1002",
            lines=(_draft().lines[0], other),
        ),
        same_content=True,
    )
    assert found == ["order_number", "order_date", "customer_external_id", "lines"]


def test_an_unrecorded_stored_amendment_reason_is_not_a_conflict() -> None:
    # rows stored before this revision carry NULL: "not recorded", compared only when present
    assert (
        grouping.content_conflicts(_stored(), _draft(amendment_reason="Upsell"), same_content=True)
        == []
    )
    stored = _stored(header={"amendment_reason": "Renewal"})
    assert grouping.content_conflicts(
        stored, _draft(amendment_reason="Upsell"), same_content=True
    ) == ["amendment_reason"]


# --- class C --------------------------------------------------------------------------------------


def test_unchanged_derivation_has_no_conflict() -> None:
    assert (
        grouping.derivation_conflicts(_stored(), _draft(), customer_id=CUSTOMER, grouping={}) == []
    )


def test_changed_default_entity_mapping_version_customer_and_grouping_are_named() -> None:
    line = ports.NormalisedLine(
        LINE, "SF-PROD-X99", Decimal(1), Decimal("5000.00"), performing_entity_code="QUAY-EU"
    )
    found = grouping.derivation_conflicts(
        _stored(),
        _draft(
            legal_entity_code="QUAY-EU",
            lines=(line,),
            custom_attributes={"mapping_version": "SF-ORDERS-v2"},
        ),
        customer_id=UUID(int=0xC6),
        grouping={"legal_entity_code": "QUAY-EU"},
    )
    assert found == [
        "legal_entity_code",
        f"lines.{LINE}.performing_entity_code",
        "custom_attributes.mapping_version",
        "customer_id",
        "grouping_values",
    ]


def test_an_unresolvable_current_customer_is_not_compared() -> None:
    # nothing to compare when the read-only lookup finds no customer now (no placeholder is created
    # before the check); the stored customer stands
    assert grouping.derivation_conflicts(_stored(), _draft(), customer_id=None, grouping={}) == []


# --- the lookup, the digest and the no-INSERT reuse ---------------------------------------------


class _Session:
    def __init__(
        self,
        stored: dict[str, Any] | None,
        lines: list[dict[str, Any]] | None = None,
        digests: dict[UUID, str] | None = None,
    ):
        self.stored, self.lines, self.digests = stored, lines or [], digests or {}
        self.sql: list[str] = []

    def execute(self, statement: Any, *args: Any) -> Any:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.sql.append(sql)
        if sql.startswith("INSERT"):
            return SimpleNamespace(rowcount=1)
        if "FROM erev.source_order_line" in sql:
            return SimpleNamespace(mappings=lambda: iter(self.lines))
        if "FROM erev.source_order" in sql:
            stored = self.stored

            class R:
                def mappings(self) -> Any:
                    return self

                def one_or_none(self) -> Any:
                    return stored

            return R()
        if "FROM erev.source_record" in sql:
            return iter(self.digests.items())
        raise AssertionError(sql)

    @property
    def inserts(self) -> int:
        return sum(1 for sql in self.sql if sql.startswith("INSERT"))


def _lookup(session: Any) -> Any:
    return grouping.stored_order(
        session,
        source_system=SourceSystem.SALESFORCE,
        external_order_id="SF-ORD-Q-010",
        external_version="1",
    )


def test_stored_order_lookup_returns_none_or_the_rows_by_line() -> None:
    assert _lookup(_Session(stored=None)) is None
    header = dict(_stored().header)
    found = _lookup(_Session(stored=header, lines=[dict(_stored().lines[LINE])]))
    assert (
        found is not None and found.id == STORED_ORDER and found.source_record_id == STORED_RECORD
    )
    assert set(found.lines) == {LINE} and found.header["order_number"] == "Q-010"


def test_same_digest_is_the_same_record_or_an_equal_retained_digest() -> None:
    session = _Session(stored=None)
    assert grouping.same_digest(session, STORED_RECORD, STORED_RECORD) is True  # type: ignore[arg-type]
    assert session.sql == []  # the same record: no read
    equal = _Session(stored=None, digests={STORED_RECORD: "a" * 64, INCOMING_RECORD: "a" * 64})
    assert grouping.same_digest(equal, STORED_RECORD, INCOMING_RECORD) is True  # type: ignore[arg-type]
    different = _Session(stored=None, digests={STORED_RECORD: "a" * 64, INCOMING_RECORD: "b" * 64})
    assert grouping.same_digest(different, STORED_RECORD, INCOMING_RECORD) is False  # type: ignore[arg-type]


def _uow(session: Any) -> Any:
    principal = SimpleNamespace(
        tenant_id=UUID(int=0x7E), id=UUID(int=0x11), kind=SimpleNamespace(value="SYSTEM")
    )
    return SimpleNamespace(session=session, principal=principal, now=NOW)


def test_record_candidate_reuses_the_stored_identity_and_stores_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session(stored=None)

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("an existing identity is never stored again")

    monkeypatch.setattr(grouping, "stored_order", lambda session, **kw: _stored())
    monkeypatch.setattr(grouping, "_store_order", never)
    monkeypatch.setattr(grouping, "grouping_fields", never)
    assert grouping.record_candidate(_uow(session), _order()) == STORED_ORDER
    assert session.inserts == 0


def test_ingest_order_books_on_the_reused_identity_without_storing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The all-unmapped repair: the candidate rows exist, the alias now maps the line, and the
    reprocess books the contract on the REUSED source_order (one INSERT: the T-CON-02 link)."""
    from erev_api.domain.contracts import commands as contract_commands

    session = _Session(stored=None)
    booked = SimpleNamespace(contract={"id": UUID(int=0xC7)}, event={"id": UUID(int=0xE7)})
    calls: list[dict[str, Any]] = []

    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("an existing identity is never stored again")

    monkeypatch.setattr(grouping, "stored_order", lambda session, **kw: _stored())
    monkeypatch.setattr(grouping, "_store_order", never)
    monkeypatch.setattr(grouping, "grouping_fields", lambda session, *, known_at: ())
    monkeypatch.setattr(grouping, "grouping_values", lambda order, fields: {})
    monkeypatch.setattr(grouping, "grouping_key", lambda values, fields: "k")
    monkeypatch.setattr(grouping, "matching_contract", lambda session, key, fields: None)
    monkeypatch.setattr(
        contract_commands, "book_contract", lambda uow, **kw: calls.append(kw) or booked
    )
    monkeypatch.setattr(grouping.audit_writer, "record_facts", lambda *a, **k: None)
    routed = grouping.ingest_order(_uow(session), _order(), sync_run_id=UUID(int=0x99))
    assert routed.outcome is grouping.GroupingOutcome.NEW_CONTRACT
    assert routed.source_order_id == STORED_ORDER and routed.contract_id == UUID(int=0xC7)
    assert calls[0]["source_record_id"] == INCOMING_RECORD  # the lineage is the record + event
    assert session.inserts == 1 and "contract_source_link" in session.sql[-1]


# --- the sync run: the refusal BEFORE any write ---------------------------------------------------


def _object() -> ports.SourceObject:
    return ports.SourceObject(
        source_system=SourceSystem.SALESFORCE,
        object_type=SourceObjectType.ORDER,
        external_id="SF-ORD-Q-010",
        external_version="1",
        version_order=1,
        payload={},
    )


def _never(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("no write, no resolution before the reuse check passes")


def test_content_conflict_refuses_before_any_resolution_or_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_module.grouping, "stored_order", lambda session, **kw: _stored())
    monkeypatch.setattr(sync_module.grouping, "same_digest", lambda session, a, b: False)
    for name in ("resolve_products", "resolve_customer", "_rebook_draft"):
        monkeypatch.setattr(sync_module, name, _never)
    monkeypatch.setattr(sync_module.grouping, "record_candidate", _never)
    monkeypatch.setattr(sync_module.grouping, "ingest_order", _never)
    counts = sync_module.Counts()
    sync_module.ingest_draft(
        SimpleNamespace(session=object(), now=NOW, principal=PRINCIPAL),  # type: ignore[arg-type]
        {"id": UUID(int=0xC1)},
        _draft(order_number="Q-010B"),
        _object(),
        source_record_id=INCOMING_RECORD,
        sync_run_id=UUID(int=0x99),
        counts=counts,
        reprocess=False,
    )
    [failure] = counts.failures
    assert failure["step"] == "reuse" and failure["rule_id"] == "SOURCE_ORDER_CONTENT_MISMATCH"
    assert failure["external_id"] == "SF-ORD-Q-010"
    assert failure["detail"]["members"] == ["payload_sha256", "order_number"]
    assert failure["detail"]["stored_record"] == str(STORED_RECORD)
    assert failure["detail"]["incoming_record"] == str(INCOMING_RECORD)
    assert counts.candidates == 0 and counts.contracts_booked == 0 and counts.customers_created == 0


def test_an_unanchored_alias_history_is_named_in_the_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """04 §16.14 rev 1.91 (Codex 1508 §1): when a pre-1.81 row's alias target cannot be verified
    against the code at receipt, the CURRENT code is compared (a conservative refusal, not a
    recovery) and the failure record names the state in ``history`` and in its text."""
    stored = _stored(lines={"product_code": "QUAY-PLAT", "product_id": PLAT})
    monkeypatch.setattr(sync_module.grouping, "stored_order", lambda session, **kw: stored)
    monkeypatch.setattr(sync_module.grouping, "same_digest", lambda session, a, b: True)
    unanchored = grouping.AliasLineage(
        targets={"SF-PROD-PLAT": (PLAT, "QUAY-PLAT2")},  # the current code: P was renamed
        evidence={"SF-PROD-PLAT": grouping.HistoryState.ANCHOR_MISSING},
        renames={"SF-PROD-PLAT": 0},
    )
    monkeypatch.setattr(sync_module.grouping, "alias_lineage_at", lambda *a, **k: unanchored)
    for name in ("resolve_products", "resolve_customer", "_rebook_draft"):
        monkeypatch.setattr(sync_module, name, _never)
    monkeypatch.setattr(sync_module.grouping, "record_candidate", _never)
    monkeypatch.setattr(sync_module.grouping, "ingest_order", _never)
    counts = sync_module.Counts()
    draft = _draft(
        lines=(
            ports.NormalisedLine(
                LINE,
                "SF-PROD-PLAT",
                Decimal(1),
                Decimal("5000.00"),
                performing_entity_code="QUAY-US",
            ),
        )
    )
    sync_module.ingest_draft(
        SimpleNamespace(session=object(), now=NOW, principal=PRINCIPAL),  # type: ignore[arg-type]
        {"id": UUID(int=0xC1)},
        draft,
        _object(),
        source_record_id=INCOMING_RECORD,
        sync_run_id=UUID(int=0x99),
        counts=counts,
        reprocess=True,
    )
    [failure] = counts.failures
    assert failure["rule_id"] == "SOURCE_ORDER_CONTENT_MISMATCH"
    assert failure["detail"]["members"] == [f"lines.{LINE}.product_code"]
    assert failure["detail"]["history"] == {
        "SF-PROD-PLAT": {"product_id": str(PLAT), "evidence": "anchor-missing", "renames": 0}
    }
    assert failure["error"].endswith(
        "could not be established from the audit trail (anchor-missing); compared against the"
        " current code: a conservative refusal, not a recovery"
    )
    # an ANCHORED lineage that still differs (an altered stored code) carries no history sentence
    anchored = grouping.AliasLineage(
        targets={"SF-PROD-PLAT": (PLAT, "QUAY-PLAT")},
        evidence={"SF-PROD-PLAT": grouping.HistoryState.RECEIPT_ANCHORED},
        renames={"SF-PROD-PLAT": 1},
    )
    monkeypatch.setattr(sync_module.grouping, "alias_lineage_at", lambda *a, **k: anchored)
    altered = _stored(lines={"product_code": "QUAY-OTHER", "product_id": PLAT})
    monkeypatch.setattr(sync_module.grouping, "stored_order", lambda session, **kw: altered)
    counts = sync_module.Counts()
    sync_module.ingest_draft(
        SimpleNamespace(session=object(), now=NOW, principal=PRINCIPAL),  # type: ignore[arg-type]
        {"id": UUID(int=0xC1)},
        draft,
        _object(),
        source_record_id=INCOMING_RECORD,
        sync_run_id=UUID(int=0x99),
        counts=counts,
        reprocess=True,
    )
    [failure] = counts.failures
    assert failure["detail"]["history"]["SF-PROD-PLAT"]["evidence"] == "receipt-anchored"
    assert "conservative refusal" not in failure["error"]


def test_derivation_change_refuses_by_name_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_module.grouping, "stored_order", lambda session, **kw: _stored())
    monkeypatch.setattr(sync_module.grouping, "same_digest", lambda session, a, b: True)
    monkeypatch.setattr(
        sync_module, "lookup_customer", lambda session, connection_id, draft: CUSTOMER
    )
    monkeypatch.setattr(sync_module.grouping, "grouping_fields", lambda session, *, known_at: ())
    for name in ("resolve_products", "resolve_customer", "_rebook_draft"):
        monkeypatch.setattr(sync_module, name, _never)
    monkeypatch.setattr(sync_module.grouping, "record_candidate", _never)
    monkeypatch.setattr(sync_module.grouping, "ingest_order", _never)
    counts = sync_module.Counts()
    line = ports.NormalisedLine(
        LINE, "SF-PROD-X99", Decimal(1), Decimal("5000.00"), performing_entity_code="QUAY-EU"
    )
    sync_module.ingest_draft(
        SimpleNamespace(session=object(), now=NOW, principal=PRINCIPAL),  # type: ignore[arg-type]
        {"id": UUID(int=0xC1)},
        _draft(legal_entity_code="QUAY-EU", lines=(line,)),  # the connection default changed
        _object(),
        source_record_id=STORED_RECORD,  # the same record: the retained input is unchanged
        sync_run_id=UUID(int=0x99),
        counts=counts,
        reprocess=True,
    )
    [failure] = counts.failures
    assert failure["step"] == "reuse" and failure["rule_id"] == "SOURCE_ORDER_DERIVATION_CHANGED"
    assert failure["detail"]["members"] == [
        "legal_entity_code",
        f"lines.{LINE}.performing_entity_code",
    ]
    assert counts.candidates == 0 and counts.rebooked == 0 and counts.customers_created == 0


def test_an_admitted_reuse_takes_the_stored_customer_and_re_derives_only_the_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_module.grouping, "stored_order", lambda session, **kw: _stored())
    monkeypatch.setattr(sync_module.grouping, "same_digest", lambda session, a, b: True)
    monkeypatch.setattr(
        sync_module, "lookup_customer", lambda session, connection_id, draft: CUSTOMER
    )
    monkeypatch.setattr(sync_module.grouping, "grouping_fields", lambda session, *, known_at: ())
    monkeypatch.setattr(sync_module, "resolve_customer", _never)  # class C: from the stored rows
    addon = sync_module.ResolvedProduct(UUID(int=0xAD), "QUAY-ADDON", True)
    monkeypatch.setattr(
        sync_module, "resolve_products", lambda session, cid, codes: {"SF-PROD-X99": addon}
    )
    monkeypatch.setattr(
        sync_module, "_live_link", lambda session, cid, kind, **kw: {"internal_id": UUID(int=0xC7)}
    )
    rebooked: list[grouping.NormalisedOrder] = []
    monkeypatch.setattr(
        sync_module,
        "_rebook_draft",
        lambda uow, contract_id, order, obj, **kw: rebooked.append(order) or True,
    )
    monkeypatch.setattr(
        sync_module.grouping, "record_candidate", _never
    )  # dropped after the rebook
    counts = sync_module.Counts()
    sync_module.ingest_draft(
        SimpleNamespace(session=object(), now=NOW, principal=PRINCIPAL),  # type: ignore[arg-type]
        {"id": UUID(int=0xC1)},
        _draft(),
        _object(),
        source_record_id=STORED_RECORD,
        sync_run_id=UUID(int=0x99),
        counts=counts,
        reprocess=True,
    )
    assert counts.failures == [] and len(rebooked) == 1
    assert rebooked[0].customer_id == CUSTOMER
    # class B re-derived as BOOKING data; the stored fact stays the SOURCE code (Codex 0652 §1)
    assert [line.product_code for line in rebooked[0].lines] == ["SF-PROD-X99"]
    assert [line.booked_code for line in rebooked[0].lines] == ["QUAY-ADDON"]


# --- Codex 0652 §1: the SOURCE code stays the stored fact; the booking sees the resolution --------


def test_store_writes_the_source_code_and_the_resolved_product_id() -> None:
    class Session:
        def __init__(self) -> None:
            self.inserted: list[Any] = []
            self.order_ids: list[Any] = []

        def execute(self, statement: Any, *args: Any) -> Any:
            sql = str(statement.compile(dialect=postgresql.dialect()))
            if sql.startswith("INSERT INTO erev.source_order_line"):
                self.inserted.extend(args[0])
                return SimpleNamespace(rowcount=1)
            if sql.startswith("INSERT INTO erev.source_order "):
                self.order_ids.append(statement.compile().params["id"])
                return SimpleNamespace(rowcount=1)
            if sql.startswith("INSERT"):
                return SimpleNamespace(rowcount=1)
            if "FROM erev.product" in sql:
                return iter([("QUAY-PLAT", UUID(int=0xA1))])
            raise AssertionError(sql)

    session = Session()
    order = grouping.NormalisedOrder(
        source_system=SourceSystem.SALESFORCE,
        source_record_id=INCOMING_RECORD,
        external_order_id="SF-ORD-Q-040",
        external_version="1",
        order_number="Q-040",
        order_date=date(2026, 9, 18),
        customer_external_id="ACC-QUAY-1001",
        customer_id=CUSTOMER,
        legal_entity_code="QUAY-US",
        transaction_currency="USD",
        lines=(
            grouping.OrderLine(
                "SF-OI-Q-040-1",
                "SF-PROD-PLAT",  # the SOURCE code
                Decimal(1),
                Decimal("100000.00"),
                booking_product_code="QUAY-PLAT",  # the alias target, booking data
            ),
            grouping.OrderLine("SF-OI-Q-040-2", "SF-PROD-X99", Decimal(1), Decimal("5000.00")),
        ),
    )
    import erev_api.domain.integrations.grouping as module

    facts: list[dict[str, Any]] = []
    saved = module.audit_writer.record_facts
    module.audit_writer.record_facts = lambda uow, **k: facts.append(k)  # type: ignore[assignment]
    try:
        order_id = grouping._store_order(_uow(session), order, {})
    finally:
        module.audit_writer.record_facts = saved  # type: ignore[assignment]
    # 04 §16.14 rev 1.91 (team-lead condition 1, writer ↔ reader): the receipt anchor the reader
    # looks for is what the writer writes — the inserted ``source_order.id`` is the id passed to
    # ``record_facts(ids=[…])`` under ORDER_ACTION / "source_order", and ``StoredOrder.id`` (the
    # lookup's ``row["id"]``, see the lookup witness) is the same column.
    assert session.order_ids == [order_id]
    assert [(f["action"], f["object_type"], f["ids"]) for f in facts][0] == (
        grouping.ORDER_ACTION,
        grouping.SOURCE_ORDER_OBJECT,
        [order_id],
    )
    assert [(row["product_code"], row["product_id"]) for row in session.inserted] == [
        ("SF-PROD-PLAT", UUID(int=0xA1)),  # the source fact and its resolution, two columns
        ("SF-PROD-X99", None),
    ]
    booking = grouping.booking_body(order, ["SF-OI-Q-040-1"])
    assert [line.product_code for line in booking.lines] == ["QUAY-PLAT"]  # the booking product


def test_normalised_order_keeps_the_source_code_and_carries_the_booking_code() -> None:
    draft = _draft(
        lines=(
            ports.NormalisedLine("SF-OI-Q-040-1", "SF-PROD-PLAT", Decimal(1), Decimal("100000.00")),
            ports.NormalisedLine("SF-OI-Q-040-2", "QUAY-SVC", Decimal(1), Decimal("5000.00")),
        )
    )
    resolved = {
        "SF-PROD-PLAT": sync_module.ResolvedProduct(UUID(int=0xA1), "QUAY-PLAT", True),
        "QUAY-SVC": sync_module.ResolvedProduct(UUID(int=0xA2), "QUAY-SVC", False),
    }
    order = sync_module._normalised_order(
        draft, source_record_id=INCOMING_RECORD, customer_id=CUSTOMER, resolved=resolved
    )
    assert [(line.product_code, line.booking_product_code) for line in order.lines] == [
        ("SF-PROD-PLAT", "QUAY-PLAT"),
        ("QUAY-SVC", None),  # a record's own code is not an alias
    ]


def test_a_row_stored_with_the_alias_target_is_admitted_only_through_the_lineage_at_receipt() -> (
    None
):
    stored = _stored(
        lines={"product_code": "QUAY-PLAT", "product_id": UUID(int=0xA1)}
    )  # pre-rule row
    draft = _draft(
        lines=(
            ports.NormalisedLine(
                LINE,
                "SF-PROD-PLAT",
                Decimal(1),
                Decimal("5000.00"),
                performing_entity_code="QUAY-US",
            ),
        )
    )
    lineage = {"SF-PROD-PLAT": (UUID(int=0xA1), "QUAY-PLAT")}
    assert (
        grouping.content_conflicts(stored, draft, same_content=True, aliased_at_receipt=lineage)
        == []
    )
    # no lineage at receipt, or a lineage to another product → the conflict is named
    assert grouping.content_conflicts(stored, draft, same_content=True) == [
        f"lines.{LINE}.product_code"
    ]
    other = {"SF-PROD-PLAT": (UUID(int=0xA9), "QUAY-OTHER")}
    assert grouping.content_conflicts(
        stored, draft, same_content=True, aliased_at_receipt=other
    ) == [f"lines.{LINE}.product_code"]
    # a stored line WITHOUT a product id cannot be an alias target
    unresolved = _stored(lines={"product_code": "QUAY-PLAT", "product_id": None})
    assert grouping.content_conflicts(
        unresolved, draft, same_content=True, aliased_at_receipt=lineage
    ) == [f"lines.{LINE}.product_code"]


class _All:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return self.rows

    def __iter__(self) -> Any:
        return iter(self.rows)


class _Rows:
    """A fake session for the three reads of ``alias_lineage_at``: the T-INT-04 join (``links``),
    the receipt anchor (``anchors``: chain positions) and the product's code-bearing renames after
    the anchor (``renames``: (before.code, after.code) LATEST FIRST, as the query orders them).
    Every compiled statement is kept in ``sql``."""

    def __init__(
        self,
        links: list[tuple[Any, ...]] | None = None,
        anchors: list[int] | None = None,
        renames: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self.links, self.anchors, self.renames = links or [], anchors or [], renames or []
        self.sql: list[str] = []

    def execute(self, statement: Any) -> Any:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.sql.append(sql)
        if "erev.audit_event" in sql and "@>" in sql:
            return _All([(seq,) for seq in self.anchors])
        if "erev.audit_event" in sql:
            assert "occurred_at" not in sql  # chain position, never the clock (Codex 1508 §1)
            return _All(self.renames)
        assert "erev.external_id_map JOIN erev.product" in sql
        assert "valid_from <=" in sql and "valid_to IS NULL OR" in sql
        return _All(self.links)


C1 = UUID(int=0xC1)
ORDER = UUID(int=0x0D43)
LINK = [
    ("SF-PROD-PLAT", PLAT, "QUAY-PLAT2")
]  # the alias target P, whose CURRENT code is QUAY-PLAT2


def test_receipt_anchor_is_the_unique_success_source_order_create_event() -> None:
    """04 §16.14 rev 1.91 (Codex 1508 §1): the receipt anchor is the row's own SUCCESS
    ``source_order.create`` event — tenant, action, object type, outcome and EXACT id membership
    (``detail.ids @> [row id]``; object_id is NULL). One → anchored at its chain position; none →
    anchor-missing; several → anchor-ambiguous."""
    one: Any = _Rows(anchors=[41])
    assert grouping.receipt_anchor(one, TENANT, ORDER) == (
        41,
        grouping.HistoryState.RECEIPT_ANCHORED,
    )
    [sql] = one.sql
    assert "erev.audit_event" in sql and "tenant_id = " in sql and "outcome = " in sql
    assert "action = " in sql and "object_type = " in sql and "@>" in sql and "detail" in sql
    assert "object_id" not in sql  # the anchor is NOT looked up by object_id (it is NULL)
    none: Any = _Rows(anchors=[])
    assert grouping.receipt_anchor(none, TENANT, ORDER) == (
        None,
        grouping.HistoryState.ANCHOR_MISSING,
    )
    two: Any = _Rows(anchors=[41, 57])
    assert grouping.receipt_anchor(two, TENANT, ORDER) == (
        None,
        grouping.HistoryState.ANCHOR_AMBIGUOUS,
    )
    # the writer's constants the reader binds (grouping._store_order → record_facts)
    assert grouping.ORDER_ACTION == "source_order.create"
    assert grouping.SOURCE_ORDER_OBJECT == "source_order"
    assert grouping.PRODUCT_UPDATE_ACTION == reference_commands.PRODUCT_UPDATE_ACTION
    assert grouping.PRODUCT_OBJECT == subjects.PRODUCT_OBJECT


def test_code_at_receipt_walks_back_by_chain_position_not_by_clock() -> None:
    """Codex 1508 §1's cases: the renames AFTER the receipt's chain position, latest first, walked
    back from the current code with a continuity check — the same-clock bracketing sequence (A→B,
    receipt, B→C at one instant) yields B, neither A nor C; multiple renames with an intervening
    non-code update (excluded by the two ``has_key`` predicates); a same-clock receipt → rename; no
    later rename = the current code, anchored; a disagreement or a null code = discontinuous."""
    anchored = grouping.HistoryState.RECEIPT_ANCHORED
    # one rename after the receipt: B→C; current C → B
    one: Any = _Rows(renames=[("QUAY-PLAT", "QUAY-PLAT2")])
    assert grouping.code_at_receipt(one, TENANT, PLAT, "QUAY-PLAT2", 41) == (
        "QUAY-PLAT",
        anchored,
        1,
    )
    [sql] = one.sql
    assert "object_id = " in sql and "tenant_id = " in sql and "outcome = " in sql
    assert "chain_seq > " in sql and "ORDER BY" in sql and sql.rstrip().endswith("chain_seq DESC")
    assert (
        sql.count(" ? ") == 2 and "occurred_at" not in sql
    )  # before ? code AND after ? code; no clock
    # the bracketing same-clock sequence: A→B is BEFORE the anchor (not selected), B→C after → B
    bracket: Any = _Rows(renames=[("QUAY-PLAT", "QUAY-PLAT2")])  # only the post-anchor event
    code, state, count = grouping.code_at_receipt(bracket, TENANT, PLAT, "QUAY-PLAT2", 41)
    assert (code, state, count) == ("QUAY-PLAT", anchored, 1)
    assert code not in (
        "QUAY-PLAT-A",
        "QUAY-PLAT2",
    )  # neither the pre-anchor before nor the current
    # multiple renames after the receipt, latest first (C→D, B→C): current D → B
    many: Any = _Rows(renames=[("QUAY-PLAT2", "QUAY-PLAT3"), ("QUAY-PLAT", "QUAY-PLAT2")])
    assert grouping.code_at_receipt(many, TENANT, PLAT, "QUAY-PLAT3", 41) == (
        "QUAY-PLAT",
        anchored,
        2,
    )
    # a no-op event (before == after) changes nothing
    noop: Any = _Rows(renames=[("QUAY-PLAT2", "QUAY-PLAT2"), ("QUAY-PLAT", "QUAY-PLAT2")])
    assert grouping.code_at_receipt(noop, TENANT, PLAT, "QUAY-PLAT2", 41) == (
        "QUAY-PLAT",
        anchored,
        1,
    )
    # no code-bearing rename after the receipt: the current code IS the receipt code — anchored, 0
    none: Any = _Rows(renames=[])
    assert grouping.code_at_receipt(none, TENANT, PLAT, "QUAY-PLAT", 41) == (
        "QUAY-PLAT",
        anchored,
        0,
    )
    # a disagreement (the latest event's after is not the current code) is discontinuous
    broken: Any = _Rows(renames=[("QUAY-PLAT", "QUAY-ELSE")])
    assert grouping.code_at_receipt(broken, TENANT, PLAT, "QUAY-PLAT2", 41) == (
        "QUAY-PLAT2",
        grouping.HistoryState.HISTORY_DISCONTINUOUS,
        0,
    )
    # a null code is not a proper code-bearing payload: discontinuous, nothing invented
    null: Any = _Rows(renames=[(None, "QUAY-PLAT2")])
    assert grouping.code_at_receipt(null, TENANT, PLAT, "QUAY-PLAT2", 41) == (
        "QUAY-PLAT2",
        grouping.HistoryState.HISTORY_DISCONTINUOUS,
        0,
    )


def test_alias_lineage_at_carries_the_code_at_receipt_not_the_current_code() -> None:
    """The discriminating witness at the lineage level (fail-first against 2e20f605's timestamp
    walk): the alias target from the T-INT-04 join, the receipt anchored by chain position, the
    code at receipt walked back — never the current code; unanchored history keeps the current
    code and says so."""
    anchored = grouping.HistoryState.RECEIPT_ANCHORED
    session: Any = _Rows(links=LINK, anchors=[41], renames=[("QUAY-PLAT", "QUAY-PLAT2")])
    found = grouping.alias_lineage_at(
        session, C1, {"SF-PROD-PLAT"}, NOW, tenant_id=TENANT, order_id=ORDER
    )
    assert found.targets == {"SF-PROD-PLAT": (PLAT, "QUAY-PLAT")}  # at receipt, not QUAY-PLAT2
    assert found.evidence == {"SF-PROD-PLAT": anchored} and found.renames == {"SF-PROD-PLAT": 1}
    assert found.unanchored == {}
    assert len(session.sql) == 3  # the join, the anchor, the renames
    # no rename after the receipt: the current code stands, ANCHORED (an ordinary no-rename case)
    same: Any = _Rows(links=[("SF-PROD-PLAT", PLAT, "QUAY-PLAT")], anchors=[41], renames=[])
    still = grouping.alias_lineage_at(
        same, C1, {"SF-PROD-PLAT"}, NOW, tenant_id=TENANT, order_id=ORDER
    )
    assert still.targets == {"SF-PROD-PLAT": (PLAT, "QUAY-PLAT")} and still.unanchored == {}
    # anchor missing: the current code is compared and the state is named (no rename read at all)
    missing: Any = _Rows(links=LINK, anchors=[], renames=[("QUAY-PLAT", "QUAY-PLAT2")])
    lost = grouping.alias_lineage_at(
        missing, C1, {"SF-PROD-PLAT"}, NOW, tenant_id=TENANT, order_id=ORDER
    )
    assert lost.targets == {"SF-PROD-PLAT": (PLAT, "QUAY-PLAT2")}
    assert lost.unanchored == {"SF-PROD-PLAT": "anchor-missing"} and len(missing.sql) == 2
    # no receipt row known to the caller: named, the current code compared
    unknown: Any = _Rows(links=LINK, anchors=[41])
    norow = grouping.alias_lineage_at(
        unknown, C1, {"SF-PROD-PLAT"}, NOW, tenant_id=TENANT, order_id=None
    )
    assert norow.unanchored == {"SF-PROD-PLAT": "no-receipt-row"} and len(unknown.sql) == 1
    # no codes / no receipt time / no link: the empty lineage, no read
    empty: Any = _Rows()
    assert (
        grouping.alias_lineage_at(empty, C1, set(), NOW, tenant_id=TENANT, order_id=ORDER)
        is grouping.EMPTY_LINEAGE
    )
    assert (
        grouping.alias_lineage_at(empty, C1, {"X"}, None, tenant_id=TENANT, order_id=ORDER)
        is grouping.EMPTY_LINEAGE
    )
    assert empty.sql == []
    unlinked: Any = _Rows(links=[])
    assert (
        grouping.alias_lineage_at(unlinked, C1, {"X"}, NOW, tenant_id=TENANT, order_id=ORDER)
        is grouping.EMPTY_LINEAGE
    )


def test_history_of_names_the_alias_targets_of_the_refused_lines() -> None:
    lineage = grouping.AliasLineage(
        targets={
            "SF-PROD-PLAT": (PLAT, "QUAY-PLAT2"),
            "SF-PROD-X99": (UUID(int=0xA9), "QUAY-ADDON"),
        },
        evidence={
            "SF-PROD-PLAT": grouping.HistoryState.ANCHOR_MISSING,
            "SF-PROD-X99": grouping.HistoryState.ANCHOR_MISSING,
        },
        renames={"SF-PROD-PLAT": 0, "SF-PROD-X99": 0},
    )
    draft = _draft(
        lines=(
            ports.NormalisedLine(LINE, "SF-PROD-PLAT", Decimal(1), Decimal("5000.00")),
            ports.NormalisedLine("SF-OI-Q-010-2", "SF-PROD-X99", Decimal(1), Decimal("1.00")),
        )
    )
    # only the lines named on product_code are reported; other members and lines are not
    members = [f"lines.{LINE}.product_code", "lines.SF-OI-Q-010-2.quantity", "order_number"]
    assert grouping.history_of(lineage, members, draft) == {
        "SF-PROD-PLAT": {"product_id": str(PLAT), "evidence": "anchor-missing", "renames": 0}
    }
    assert grouping.history_of(lineage, ["payload_sha256"], draft) == {}


def test_a_lawful_rename_admits_the_pre_rule_row_and_altered_content_is_refused() -> None:
    """Codex 1442 §1's counterexample as asserts on ``content_conflicts`` (unchanged): a pre-1.81
    row (P, QUAY-PLAT) against the raw code SF-PROD-PLAT — admitted with the receipt-time target
    (P, QUAY-PLAT) whatever P's code is today; the current-code target (P, QUAY-PLAT2) rev 1.81
    produced names the member (the false refusal); an altered stored code, another product or a
    line without ``product_id`` are still refused."""
    stored = _stored(lines={"product_code": "QUAY-PLAT", "product_id": PLAT})
    draft = _draft(
        lines=(
            ports.NormalisedLine(
                LINE,
                "SF-PROD-PLAT",
                Decimal(1),
                Decimal("5000.00"),
                performing_entity_code="QUAY-US",
            ),
        )
    )
    at_receipt = {"SF-PROD-PLAT": (PLAT, "QUAY-PLAT")}
    assert (
        grouping.content_conflicts(stored, draft, same_content=True, aliased_at_receipt=at_receipt)
        == []
    )
    current_code = {"SF-PROD-PLAT": (PLAT, "QUAY-PLAT2")}  # what rev 1.81's join produced
    assert grouping.content_conflicts(
        stored, draft, same_content=True, aliased_at_receipt=current_code
    ) == [f"lines.{LINE}.product_code"]
    altered = _stored(lines={"product_code": "QUAY-OTHER", "product_id": PLAT})
    assert grouping.content_conflicts(
        altered, draft, same_content=True, aliased_at_receipt=at_receipt
    ) == [f"lines.{LINE}.product_code"]
    other = {"SF-PROD-PLAT": (UUID(int=0xA9), "QUAY-PLAT")}
    assert grouping.content_conflicts(
        stored, draft, same_content=True, aliased_at_receipt=other
    ) == [f"lines.{LINE}.product_code"]
    unresolved = _stored(lines={"product_code": "QUAY-PLAT", "product_id": None})
    assert grouping.content_conflicts(
        unresolved, draft, same_content=True, aliased_at_receipt=at_receipt
    ) == [f"lines.{LINE}.product_code"]
