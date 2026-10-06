"""Codex production-20260921-0958 §1 — the legacy PROSPECTIVE zero-total creation seam (ENGINE_SPEC
CV-50 rev 1.29; D-98 candidate 124; DEVIATIONS DEV-054).

Contract 2 under ``LEGACY_PARITY`` with every priced obligation fully delivered before 15 May
2023, then a ``LEGACY_PROSPECTIVE`` amendment that ADDS a stratification-VC line (quantity 1,
billing 0). W = Σ RemSSP′ is 0 and the pool is 0: DEV-054 — satisfied performance, no obligation
absorbs anything, the created line takes 0, the others keep their allocations, the transaction
price and the posted totals do not move. The created obligation has NO governed ratio: no
``allocation_weight@`` node exists and no 0 ÷ 0 is manufactured; the state stamps the EXPLICIT
contract-permitted absence ``trace.ABSENT_ZERO_TOTAL`` (the stable identifier
``absent:zero-total``) in place of a node id, while the total node (Σ RemSSP′ = 0, role
``total_ssp``) is emitted and linked. A LEGACY-VC line has no SSP resolution by construction
(``legacy_templates.added_mod_ssp`` returns the zero band without a lookup), so
``original_ssp_selected`` stamps ``trace.ABSENT_NO_RESOLUTION`` (``absent:no-ssp-resolution``)
and the assembler publishes the existing non-NULL 0 through ``_selected_ssp`` (RESOLVED: 04 line
3275; NULL ``original_unit_ssp`` retained) — a representation of the constructor's state, no
node fabricated.

Side by side (the supervisor's constraint (2)): the assembler ACCEPTS a named absence only over the
column's existing 0 display and links nothing; it REFUSES a genuinely missing REQUIRED producer
(a stamped node id no one emitted) and a named absence whose column publishes a non-zero value.
Admission is real: stages 01 to 05 fold the bundle, stage 06 applies the amendment through
``s06_modifications.apply``, and ``compute`` runs the whole book — ``check_book`` with NO
exception since the guarded ``progress_ratio`` producer of ENGINE_SPEC CV-50 rev 1.31 closed
T1F-LP-PR-1 for every obligation of this never-activated world (the five-subject witness lives in
``tests/engine/kernel/test_progress_unmeasured_whole_book.py``); the trace replays.
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType

import pytest
from erev_engine import ENGINE_VERSION, _snapshot_links, compute
from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from erev_engine.trace import ABSENT_NO_RESOLUTION, ABSENT_ZERO_TOTAL, TraceBuilder, reevaluate
from support import golden_streams, trace_linkage
from support.answer_keys import loader
from test_s06_prospective import checked, obligation, usd
from test_tc_rm import amended, amendments, apply, fold, template_line

DELIVERED_ON = date(2023, 5, 10)
AMENDED_ON = date(2023, 5, 15)
ADDED = "VC #2"


def delivered(value: InputBundle, key: str, quantity: str, effective: date) -> InputBundle:
    """``value`` with one more ``DELIVERY_RECORDED`` of ``quantity`` units of ``key`` (the golden
    stream's own event shape: ``obligation_key`` / ``quantity`` / ``trigger``)."""
    header = value.contracts[0]
    sample = next(event for event in value.events if event.event_type == "DELIVERY_RECORDED")
    head = max(event.stream_version for event in value.events) + 1
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    event = dataclasses.replace(
        sample,
        event_key=f"{header.external_id}/EV-{head:06d}",
        stream_version=head,
        effective_date=effective,
        recorded_at=max(event.recorded_at for event in value.events) + timedelta(seconds=1),
        record_seq=max(event.record_seq for event in value.events) + 1,
        obligation_keys=(key,),
        payload=payload,
        payload_sha256=sha256_hex(payload),
        idempotency_key=None,
    )
    events = sorted(
        (*value.events, event), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
    )
    return dataclasses.replace(
        value, known_at=max(value.known_at, event.recorded_at), events=tuple(events)
    )


def zero_total_world() -> InputBundle:
    """Contract 2 step 07: POB #1 (Q 8, 1 delivered), POB #2 (Q 3), POB #3 (Q 1, 0.4 delivered)
    fully delivered on 10 May 2023 (VC #1 has SSP 0 and weighs nothing); then the prospective ADD
    of ``VC #2`` — a LEGACY-VC line, quantity 1, billing 0 — under ``LEGACY_PROSPECTIVE``."""
    value = golden_streams.stream("Contract 2", "07").input_bundle(preset="LEGACY_PARITY")
    for key, quantity in (("POB #1", "7"), ("POB #2", "3"), ("POB #3", "0.6")):
        value = delivered(value, key, quantity, DELIVERED_ON)
    line = template_line(value, "VC #1", "1", "0")
    add = {
        **line,
        "obligation_key": ADDED,
        "action": "ADD",
        "start_date": date(2023, 1, 1),
        "end_date": date(2023, 12, 31),
    }
    return amended(value, "MOD-ZT", AMENDED_ON, "prospective", [add], "LEGACY_PROSPECTIVE")


def _applied() -> tuple[object, object, object, object, dict[str, object]]:
    folded = fold(zero_total_world())
    before = folded.state
    (ev,) = amendments(before)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, before, ev, tb)
    assert after.findings == ()
    return folded, before, ev, after, checked(tb)


def test_zero_total_prospective_creation_names_the_absence_and_keeps_dev_054() -> None:
    """The 0958 seam through real stage 01–06 admission: W = 0 / pool 0, DEV-054 preserved; the
    total node (0) is emitted and linked; NO ratio node, the absence stamped by name; the LEGACY-VC
    line's missing resolution stamped by name; the assembler accepts both and links nothing."""
    _folded, before, ev, after, nodes = _applied()
    added = obligation(after, ADDED)
    subject = added.subject_key
    # DEV-054: the created line takes nothing, every other obligation keeps its allocation, the
    # transaction price and posted allocation basis do not move (600 + 400 + 0 − 100 = 900.00)
    assert added.segments[-1].x_exact == 0
    assert added.original_allocation.a_posted == 0
    for key in ("POB #1", "POB #2", "POB #3", "VC #1"):
        assert (
            obligation(after, key).segments[-1].x_exact
            == obligation(before, key).segments[-1].x_exact
        ), key
    assert after.tp_history[-1].allocation_basis.posted == usd("900.00")
    assert (
        after.tp_history[-1].allocation_basis.posted
        == before.tp_history[-1].allocation_basis.posted
    )
    # the total node: Σ RemSSP′ = 0 under the template's own formula, role total_ssp, linked
    total_id = f"original_total_contract_ssp@{ev.event_key}:{subject}:-"
    assert added.snapshot_producer_links["original_total_contract_ssp"] == total_id
    assert Fraction(nodes[total_id].value) == 0
    assert nodes[total_id].params["role"] == "total_ssp"
    assert added.original_total_contract_ssp == 0
    # NO ratio: the named absence, no node, no manufactured 0 ÷ 0
    assert added.snapshot_producer_links["allocation_weight"] == ABSENT_ZERO_TOTAL
    assert f"allocation_weight@{ev.event_key}:{subject}:-" not in nodes
    assert not any(
        node_id.startswith("allocation_weight@") and node_id.endswith(f":{subject}:-")
        for node_id in nodes
    )
    # the LEGACY-VC line has no SSP resolution: the named absence, no node fabricated
    assert added.ssp is None
    assert added.snapshot_producer_links["original_ssp_selected"] == ABSENT_NO_RESOLUTION
    assert not any(
        node_id.startswith("original_ssp_selected@") and node_id.endswith(f":{subject}:-")
        for node_id in nodes
    )
    assert "original_unit_ssp" not in added.snapshot_producer_links
    # the assembler's seam: the named absences are ACCEPTED over the 0 display and published AS
    # the columns' links; the total and the stated-price echo (the boundary state's node) link
    # by identity
    columns: dict[str, object] = {
        "original_ssp_selected": Fraction(0),  # _selected_ssp: ssp is None → 0
        "original_unit_ssp": None,
        "original_total_contract_ssp": added.original_total_contract_ssp,
        "original_stated_price": round(added.original_stated_price * 100),
        "original_total_contract_price": None,  # stage 13's echo is outside this seam
        "allocation_weight": Fraction(0),  # the assembler's display for the named absence
    }
    links = _snapshot_links(added, after, columns, nodes, 2)
    assert links["original_total_contract_ssp"] == total_id
    assert links["original_stated_price"] == f"original_stated_price@{ev.event_key}:{subject}:-"
    assert links["allocation_weight"] == ABSENT_ZERO_TOTAL
    assert links["original_ssp_selected"] == ABSENT_NO_RESOLUTION
    assert not any(
        link in nodes for link in (links["allocation_weight"], links["original_ssp_selected"])
    )


def test_named_absence_accepted_beside_a_missing_required_producer_refused() -> None:
    """Constraint (2) side by side on the same applied state: (a) the named absence over the 0
    display → accepted, the absence itself published as the link; (b) a REQUIRED producer stamped
    but never emitted → refused; (d) / (e) / (f) an unknown reason, a known reason on another
    column, or a marker on the REQUIRED zero total's column → refused by identity; (c) a named
    absence whose column publishes a non-zero value → refused."""
    _folded, _before, ev, after, nodes = _applied()
    added = obligation(after, ADDED)
    subject = added.subject_key
    # (a) the contract-permitted absence: accepted, the named state IS the link, nothing fabricated
    assert _snapshot_links(added, after, {"allocation_weight": Fraction(0)}, nodes, 2) == {
        "allocation_weight": ABSENT_ZERO_TOTAL
    }
    assert _snapshot_links(added, after, {"original_ssp_selected": Fraction(0)}, nodes, 2) == {
        "original_ssp_selected": ABSENT_NO_RESOLUTION
    }
    # (b) a genuinely missing REQUIRED producer: the same column, a node id no one emitted
    missing = f"allocation_weight@{ev.event_key}:{subject}:-"
    assert missing not in nodes
    doctored = dataclasses.replace(
        added,
        snapshot_producer_links=MappingProxyType(
            {**added.snapshot_producer_links, "allocation_weight": missing}
        ),
    )
    with pytest.raises(EngineError, match="absent from the trace") as refused:
        _snapshot_links(doctored, after, {"allocation_weight": Fraction(0)}, nodes, 2)
    assert refused.value.detail == {
        "rule": "CV-50",
        "column": "allocation_weight",
        "node_id": missing,
    }
    # (d) an unknown reason under the prefix, (e) a known reason on another column and (f) a marker
    # where a REQUIRED producer must exist — the real zero total node original_total_contract_ssp
    # (Codex 1054 §1 R1): refused BY IDENTITY against the one reason admitted for the column — a
    # prefix never admits anything, a zero column never excuses a required producer
    for column, marker in (
        ("allocation_weight", "absent:unknown-reason"),
        ("original_ssp_selected", ABSENT_ZERO_TOTAL),
        ("allocation_weight", ABSENT_NO_RESOLUTION),
        ("original_total_contract_ssp", ABSENT_ZERO_TOTAL),
        ("original_total_contract_ssp", ABSENT_NO_RESOLUTION),
    ):
        wrong = dataclasses.replace(
            added,
            snapshot_producer_links=MappingProxyType(
                {**added.snapshot_producer_links, column: marker}
            ),
        )
        with pytest.raises(EngineError, match="not admitted") as bad:
            _snapshot_links(wrong, after, {column: Fraction(0)}, nodes, 2)
        assert (bad.value.detail["column"], bad.value.detail["state"]) == (column, marker)
    # (c) the named absence guards its display: a non-zero column under it is refused
    with pytest.raises(EngineError, match="absent-by-contract") as nonzero:
        _snapshot_links(added, after, {"allocation_weight": Fraction(1, 3)}, nodes, 2)
    assert nonzero.value.detail["state"] == ABSENT_ZERO_TOTAL
    assert nonzero.value.detail["column"] == "allocation_weight"


def _book(bundle: InputBundle) -> BookOutput:
    output = compute(bundle)
    return next(item for item in output.books if item.book_code == "ASC606")


def _unlinked_value_columns(book: BookOutput) -> set[tuple[str, str]]:
    """Every (subject key, value column) the book publishes with a stored value and no link — the
    checker's own notion (``expected_columns``), a named absence counting as linked."""
    types = loader.obligation_columns()
    return {
        (item.subject_key, column)
        for item in book.obligation_versions
        for column in trace_linkage.expected_columns(item.columns, types) - set(item.trace_nodes)
    }


def test_zero_total_prospective_creation_whole_book() -> None:
    """The same world through ``compute``: the created row publishes the DEV-054 zeros, links the
    total node, publishes the two named absences AS its links (no ratio node, no selected-SSP
    node); whole-book ``check_book`` passes with NO exception (T1F-LP-PR-1 closed: every
    obligation's ``progress_ratio`` links the unmeasured producer under the V4 guard); the trace
    replays."""
    bundle = zero_total_world()
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    version = next(
        item for item in book.obligation_versions if item.columns["obligation_key"] == ADDED
    )
    subject = version.subject_key
    assert version.columns["allocation_weight"] == 0
    assert version.columns["original_ssp_selected"] == 0
    assert version.columns["original_total_contract_ssp"] == 0
    assert version.columns["original_allocated_amount"] == 0
    assert version.trace_nodes["allocation_weight"] == ABSENT_ZERO_TOTAL
    assert version.trace_nodes["original_ssp_selected"] == ABSENT_NO_RESOLUTION
    assert ABSENT_ZERO_TOTAL not in nodes and ABSENT_NO_RESOLUTION not in nodes
    total = version.trace_nodes["original_total_contract_ssp"]
    assert total.startswith("original_total_contract_ssp@") and total.endswith(f":{subject}:-")
    assert Fraction(nodes[total].value) == 0
    assert not any(
        node_id.startswith("allocation_weight@") and node_id.endswith(f":{subject}:-")
        for node_id in nodes
    )
    assert _unlinked_value_columns(book) == set(), _unlinked_value_columns(book)  # no gap left
    trace_linkage.check_book(book, bundle, exceptions=trace_linkage.NO_EXCEPTIONS)
    replayed = reevaluate(book.trace)
    assert replayed[total] == nodes[total].value
