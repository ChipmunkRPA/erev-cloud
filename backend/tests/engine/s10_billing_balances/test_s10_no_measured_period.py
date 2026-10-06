"""A contract booked ahead of the open periods computes (ENGINE_SPEC_B C-05, S10-R-22 and S12-R-13
rev 1.100, §10.5; ENGINE_SPEC CV-13; supervisor ruling R-107 (a) of 2026-09-30; item
ENG-S10-FUTURE-INCEPTION-1).

The defect. C-05 evaluates cumulative targets "at every period end from the group's inception
period through the horizon" and said nothing for the empty set. A contract whose inception lies
after its contracting entity's last open period — booked in April for May — has no such period
end: stage 10 raised ``IndexError`` in ``_version_period`` (the first of no measured period), and
with that reader guarded stage 12 raised ``ValueError`` in ``covering_periods`` ("end must not
precede start"). The draft form reached both through ``POST /contracts``: the contract was stored
and its provisional computation failed.

The rule. Per contracting entity without a measured period stage 10 presents no period target,
reclass entry or member balance, and each of its obligations keeps the version-date
``netting_reclass_amount`` of zero with a node of formula
``pos.reclass_attribution.no_measured_period.v1``, so that the exact-column exports bind it
(DG-PAR-05); stage 12 processes nothing for a unit whose replay would begin after the horizon. The
version's own measures are those of its date and are not postings; allocation and schedules are
as for any other contract. The period set is per contracting entity: an entity that is behind does
not stop another entity of the same group.

Worlds: frozen answer-key checkpoints put into the booked-ahead shape in memory
(``support.booked_ahead``: twelve earlier open periods, every carried period ``future``; no
database). JE-CHK-024 case B (USD, one product of 1,000.00, invoiced 31 January, paid 1 March,
delivered 31 March; ``ENGINE`` as keyed, ``ERP`` by policy; a draft is its first event alone);
REC-JS-04 (a membership of 600,000.00 recognised daily from 15 January); STP1-S1-COMBINATION-OWN
(two contracts combined under 606-10-25-9(a)); ENT-PER-ENTITY-NETTING (one combined group across
US01 and US02); FX-POL-160 (EUR 12,000.00 in a USD entity, books ASC606 and IFRS15).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from fractions import Fraction
from typing import Any, Final, cast
from uuid import UUID

import erev_engine
import pytest
from erev_api.domain.reports import exact_sources, legacy_columns
from erev_engine.bundle import BookOutput, InputBundle, ObligationVersionOut, OutputBundle
from erev_engine.formulas import FORMULAS
from erev_engine.money import format_money
from erev_engine.trace import TraceNode, reevaluate
from hypothesis import given
from support.billing_lines import checkpoint_bundle, with_policy
from support.booked_ahead import booked_ahead, horizon_end
from support.prop_worlds import WorldSpec, bundle
from support.strategies import world_specs

B38: Final = ("je", "JE-CHK-024-S9-PRESENTATION-EX38-CASEB-NONCANCELLABLE")
MEMBERSHIP: Final = ("rec", "REC-JS-04-PAID-MEMBERSHIP-DAILY", "join-month")
PACKAGE: Final = ("stp1", "STP1-S1-COMBINATION-OWN", "end-of-january")
TWO_ENTITIES: Final = ("ent", "ENT-PER-ENTITY-NETTING-IN-A-COMBINED-GROUP", "january-close")
FX_160: Final = ("fx", "FX-POL-160-IFRIC22-LAYER-DATE-ASC606-VS-IFRS15", "asc606-march-close")
NO_PERIOD: Final = "pos.reclass_attribution.no_measured_period.v1"
ATTRIBUTED: Final = "pos.reclass_attribution.pob_debit_positions.v1"
NETTING: Final = "netting_reclass_amount"
ROLE: Final = "netting_reclass_role"
VERSION_ID: Final = UUID(int=10)


def _invoiced(mode: str) -> InputBundle:
    return with_policy(checkpoint_bundle(*B38, "january-close"), "billing.posting", mode)


def _draft() -> InputBundle:
    """Booked and not activated: the stream of the draft form (``POST /contracts``)."""
    bundle = checkpoint_bundle(*B38, "january-close")
    (booked,) = bundle.events[:1]
    assert booked.event_type == "CONTRACT_BOOKED"
    return dataclasses.replace(bundle, events=(booked,))


# id -> the open form: the frozen checkpoint with its inception period inside the horizon.
SHAPES: Final[Mapping[str, Callable[[], InputBundle]]] = {
    "a draft: booked, not activated": _draft,
    "active and invoiced, subledger billing": lambda: _invoiced("ENGINE"),
    "active and invoiced, ERP billing": lambda: _invoiced("ERP"),
    "invoiced, paid and delivered": lambda: checkpoint_bundle(*B38, "march-close"),
    "a membership recognised daily": lambda: checkpoint_bundle(*MEMBERSHIP),
    "a combination of two contracts": lambda: checkpoint_bundle(*PACKAGE),
    "a combined group across two entities": lambda: checkpoint_bundle(*TWO_ENTITIES),
    "a foreign-currency contract in two books": lambda: checkpoint_bundle(*FX_160),
}


def _computed(bundle: InputBundle, *, warnings: bool = False) -> OutputBundle:
    """A public compute whose every trace node re-evaluates (PROP:P14); without a diagnostic
    unless ``warnings`` admits WARNING diagnostics."""
    output = cast(OutputBundle, erev_engine.compute(bundle))
    assert {item.severity for item in output.diagnostics} <= ({"WARNING"} if warnings else set())
    for book in output.books:
        assert reevaluate(book.trace) == {node.id: node.value for node in book.trace.nodes}
    return output


def _netting_node(book: BookOutput, version: ObligationVersionOut) -> TraceNode:
    (node,) = [item for item in book.trace.nodes if item.id == version.trace_nodes[NETTING]]
    return node


def _assert_unmeasured(book: BookOutput, version: ObligationVersionOut) -> None:
    """S10-R-22 rev 1.100: zero, no role, and the version-state node of the formula of its own."""
    assert (version.columns[NETTING], version.columns[ROLE]) == (0, None)
    node = _netting_node(book, version)
    effective = version.columns["effective_date"]
    assert (
        node.id,
        node.formula_id,
        node.inputs,
        node.value,
        node.rounding_residue,
        node.params["as_of"],
        node.params["key"],
    ) == (
        f"{NETTING}:{version.subject_key}:-",
        NO_PERIOD,
        (),
        format_money(0, int(node.params["minor_unit"])),
        "0",
        str(effective),
        version.subject_key,
    )


def _assert_presents_nothing(expected: OutputBundle, output: OutputBundle) -> None:
    """``output`` is the booked-ahead form of ``expected``: nothing presented or posted, and the
    version of the open form column for column except the reclass that no period end attributes."""
    assert [book.book_code for book in output.books] == [book.book_code for book in expected.books]
    for was, book in zip(expected.books, output.books, strict=True):
        assert (book.balances, book.posting_intents, book.fx_layer_movements) == ((), (), ())
        assert book.status_in_book == was.status_in_book
        assert was.contract_version is not None and book.contract_version is not None
        assert dict(book.contract_version.columns) == dict(was.contract_version.columns)
        assert set(book.schedules) <= set(was.schedules)
        assert len(book.obligation_versions) == len(was.obligation_versions) > 0
        for before, version in zip(was.obligation_versions, book.obligation_versions, strict=True):
            assert version.subject_key == before.subject_key
            assert dict(version.columns) == {**before.columns, NETTING: 0, ROLE: None}
            assert set(version.trace_nodes) == set(before.trace_nodes)
            _assert_unmeasured(book, version)


@pytest.mark.parametrize("shape", list(SHAPES))
def test_c05_a_contract_booked_ahead_of_the_open_periods_computes(shape: str) -> None:
    """Every horizon ends before the group's inception period. The computation succeeds; nothing
    is presented or posted — no balance row, no posting intent, no FX layer movement; the version
    is the one the same stream gives with its periods open, column for column, except that no
    period-end reclass is attributed: ``netting_reclass_amount`` is 0 with the node of its own
    formula. Every schedule line is one of the open form's."""
    open_form = SHAPES[shape]()
    ahead = booked_ahead(open_form)
    for entity in ahead.entities:
        for book_input in ahead.books:
            end = horizon_end(ahead, entity.code, book_input.book_code)
            assert end < ahead.group.inception_date
    _assert_presents_nothing(_computed(open_form), _computed(ahead))


@given(spec=world_specs())
def test_c05_generated_worlds_booked_ahead_compute_and_present_nothing(spec: WorldSpec) -> None:
    """The same on the property worlds (``support.prop_worlds``: contracts of daily, monthly and
    point-in-time lines with deliveries and billings, in the ASC606 and IFRS15 books): whatever
    the stream holds, the booked-ahead form computes, presents and posts nothing, and its
    version is that of the open form except the reclass."""
    open_form = bundle(spec, books=("ASC606", "IFRS15"))
    ahead = booked_ahead(open_form)
    _assert_presents_nothing(_computed(open_form, warnings=True), _computed(ahead, warnings=True))


def test_c05_the_deterministic_schedule_of_a_contract_booked_ahead_is_whole() -> None:
    """The membership's thirteen daily-ratable schedule lines (15 January 2026 to 14 January 2027)
    are those of the open form although no period of it is evaluated: a deterministic schedule
    extends to the period containing the subject's last end date (C-05), whatever the horizon."""
    open_form = checkpoint_bundle(*MEMBERSHIP)
    (was,) = _computed(open_form).books
    (book,) = _computed(booked_ahead(open_form)).books
    assert len(book.schedules) == 13 and book.schedules == was.schedules
    assert len(was.posting_intents) == 13 and book.posting_intents == ()


def test_c05_an_entity_that_is_behind_does_not_stop_another_entity_of_the_group() -> None:
    """One combined group across US01 and US02, both contracts dated 1 January 2026. US02's
    horizon ends on 31 December 2025; US01 has January open. US01 is presented and posted exactly
    as when both are open — its balance row, its intent, its obligation's attribution node; US02
    gets no balance row and no intent, and its obligation the zero node (the open form attributes
    7,333.33 of contract asset to it)."""
    open_form = checkpoint_bundle(*TWO_ENTITIES)
    behind = booked_ahead(open_form, entities={"US02"})
    assert str(horizon_end(behind, "US01", "ASC606")) == "2026-01-31"
    assert str(horizon_end(behind, "US02", "ASC606")) == "2025-12-31"
    (was,) = _computed(open_form).books
    (book,) = _computed(behind).books

    def of(found: BookOutput, entity: str) -> tuple[object, object]:
        balances = tuple(row for row in found.balances if row.subject_key.endswith(f"@{entity}"))
        intents = tuple(item for item in found.posting_intents if item.entity == entity)
        return balances, intents

    assert of(book, "US01") == of(was, "US01")
    assert [len(part) for part in of(was, "US01")] == [1, 1]
    assert [len(part) for part in of(was, "US02")] == [1, 1]
    assert of(book, "US02") == ((), ())
    by_key = {
        str(version.columns["obligation_key"]): version for version in book.obligation_versions
    }
    before = {
        str(version.columns["obligation_key"]): version for version in was.obligation_versions
    }
    assert dict(by_key["A1-SUPPORT"].columns) == dict(before["A1-SUPPORT"].columns)
    assert _netting_node(book, by_key["A1-SUPPORT"]) == _netting_node(was, before["A1-SUPPORT"])
    assert _netting_node(book, by_key["A1-SUPPORT"]).formula_id == ATTRIBUTED
    assert (before["B1-INSTALL"].columns[NETTING], before["B1-INSTALL"].columns[ROLE]) == (
        733333,
        "CONTRACT_ASSET",
    )
    assert dict(by_key["B1-INSTALL"].columns) == {
        **before["B1-INSTALL"].columns,
        NETTING: 0,
        ROLE: None,
    }
    _assert_unmeasured(book, by_key["B1-INSTALL"])


def _export_rows(book: BookOutput) -> list[dict[str, Any]]:
    """The obligation versions as the legacy export reads them: the links and the currency."""
    return [
        {
            "id": version.subject_key,
            "contract_version_id": VERSION_ID,
            "trace_nodes": dict(version.trace_nodes),
            "txn_currency": version.columns["txn_currency"],
        }
        for version in book.obligation_versions
    ]


@pytest.mark.parametrize(
    "shape", ["a membership recognised daily", "a combination of two contracts"]
)
def test_dg_par_05_the_exact_columns_of_a_version_booked_ahead_bind_their_nodes(shape: str) -> None:
    """Why the zero carries a node. The legacy exports take their exact columns from the nodes a
    row binds and refuse the whole run when a column binds none (04 §17.1 rule 4; DG-PAR-05).
    The product's reader attaches every exact text of the version booked ahead: the reclass is
    "0" and the other columns are the open form's texts."""
    open_form = SHAPES[shape]()
    (was,) = _computed(open_form).books
    (book,) = _computed(booked_ahead(open_form)).books
    before, rows = _export_rows(was), _export_rows(book)
    assert exact_sources.attach_exact_texts(None, before, loader=lambda _s, _v: was.trace) == 1
    assert exact_sources.attach_exact_texts(None, rows, loader=lambda _s, _v: book.trace) == 1
    for old, row in zip(before, rows, strict=True):
        texts = row[legacy_columns.EXACT_TEXT_KEY]
        assert set(texts) == set(legacy_columns.EXACT_TEXT_COLUMNS)
        assert texts == {**old[legacy_columns.EXACT_TEXT_KEY], NETTING: "0"}


def test_s10_r22_the_formula_of_an_unmeasured_obligation_is_zero_over_no_input() -> None:
    """``pos.reclass_attribution.no_measured_period.v1`` (§10.5 rev 1.100): no input, the value 0,
    params ``as_of`` and ``key``; an input or a missing parameter is refused."""
    formula = FORMULAS[NO_PERIOD]
    params = {"as_of": "2026-01-31", "key": "C-1/L1", "minor_unit": "2"}
    assert formula((), params) == 0
    with pytest.raises(ValueError, match="takes 0 inputs"):
        formula((Fraction(1),), params)
    for name in ("as_of", "key"):
        missing = {key: value for key, value in params.items() if key != name}
        with pytest.raises(ValueError, match=name):
            formula((), missing)
