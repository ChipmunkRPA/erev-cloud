"""Trace linkage of every stored value column (DG-KRN-EXP-01 to 03; ENGINE_SPEC CV-50 links, CV-52,
CV-53; D-97 (8) T1-F-1 / T1-F-2 / T1-Q-3; BUILD_SPEC END-13; lane ENG-T1F).

The checker ``support.trace_linkage.check_book`` enumerates the expected value columns of every
T-CON-11 obligation version, the T-CON-08 contract version and every T-CON-09 balance row (zeros
included) and validates, per column, the link, the node's measure, subject and boundary lineage,
its stored value, unit and currency. The golden Contract 2 step 09 world (three modifications: two
reallocating boundaries) and a units world with one price-changing modification exercise both
books. The omission tests detach, mistarget and stale one link of a real output and prove the
checker names the family, subject and column. Fail-first: on main eb5546a the golden world reports
29 unlinked obligation-version columns, 5 unlinked contract-version sums plus 2 stale links and 15
unlinked balance columns (record ``docs/reviews/loop/sprint/ENG-T1F.md``). No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from types import MappingProxyType

import pytest
from erev_engine import compute
from erev_engine.bundle import BookOutput, InputBundle, OutputBundle
from support import cpc_worlds as w
from support import golden_streams, intent_totals, trace_linkage
from support.cpc_worlds import Y1

GOLDEN_BOOKS = ("ASC606", "IFRS15")
# Columns still unlinked under a documented exception (docs/reviews/loop/sprint/ENG-T1F.md). The
# supervisor rulings T1F-Q-1 (A), Q-3 (c) and Q-4 are applied; the sets are empty and this file
# stays the single inventory of documented exceptions (adding one needs a ruling).
PENDING_RULINGS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "obligation_version": frozenset(),
        "contract_version": frozenset(),
        "contract_version_balance": frozenset(),
    }
)


@functools.cache
def golden() -> tuple[InputBundle, OutputBundle]:
    stream = golden_streams.stream("Contract 2", "09")
    value = intent_totals.activated(stream.input_bundle(preset="LEGACY_PARITY", books=GOLDEN_BOOKS))
    return value, compute(value)


@functools.cache
def modified_units() -> tuple[InputBundle, OutputBundle]:
    """A units world with a 15 Jul price concession (stage 06 CREDIT_OR_REFUND): a reallocating
    boundary after inception, so ``stated_price``, ``allocation_adjustment`` and the T-CON-08
    build-up differ from their inception nodes (T1-F-2 on the obligation side)."""
    inception = date(2026, 1, 4)
    version = w.sbc_version(1, inception, True, "1000000.00", grant=inception.isoformat())
    first = w.concession("-20000.00", date(2026, 7, 15), reference="MOD-FIRST-20000", named=False)
    steps = [
        ("D", Y1, "400000"),
        ("I", Y1, "400000.00"),
        ("A", first.effective_date, first.modification_key),
    ]
    bundle = w.units_world(
        steps, [version], modifications=[first], quantity="400000", inception=inception
    )
    return bundle, compute(bundle)


@functools.cache
def answer_key_world(family: str, key_id: str, contract: str) -> tuple[InputBundle, OutputBundle]:
    """The bundle of ``contract`` at the last checkpoint of an answer key, computed."""
    from support.answer_keys.loader import ANSWER_KEY_ROOT, load
    from support.answer_keys.runners import _build_checkpoint_bundles

    loaded = load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")
    checkpoint = _build_checkpoint_bundles(loaded)[-1]
    (bundle,) = [
        item
        for item in checkpoint.bundles
        if any(header.external_id == contract for header in item.contracts)
    ]
    return bundle, compute(bundle)


def foreign_entity() -> tuple[InputBundle, OutputBundle]:
    """The FX-CHK-081 world at its last checkpoint: entity US01 (functional USD) with a EUR
    contract, so stage 12 publishes the foreign-currency ``_functional`` balance columns
    (T1F-Q-4)."""
    return answer_key_world(
        "fx", "FX-CHK-081-CONTRACT-ASSET-REMEASURED-TO-CLOSING-RATE", "C-FX-081"
    )


# Worlds whose stored figures are re-measured at the version date without a stage 06 boundary
# (Codex T1F-R3): a returns re-estimate nets the allocation (S09-R-23 REDUCE), so
# ``allocation_adjustment`` moves away from the inception node (−400.00 / −300.00).
REMEASURED_WORLDS = (
    ("ret", "RET-CHK-060-S3-EX22-REVISED", "C-RET"),
    ("fx", "FX-CHK-084-A-REFUND-LIABILITY-REMEASURED", "C-FX-084-A"),
)


def _book(output: OutputBundle, code: str) -> BookOutput:
    return next(book for book in output.books if book.book_code == code)


@pytest.mark.parametrize("code", GOLDEN_BOOKS)
def test_golden_contract_2_every_value_column_is_linked(code: str) -> None:
    value, output = golden()
    trace_linkage.check_book(_book(output, code), value, exceptions=PENDING_RULINGS)


def test_modified_units_world_every_value_column_is_linked() -> None:
    bundle, output = modified_units()
    for book in output.books:
        trace_linkage.check_book(book, bundle, exceptions=PENDING_RULINGS)


def test_foreign_entity_world_every_value_column_is_linked() -> None:
    """A foreign-currency entity: the ``_functional`` balance columns link the stage 12 member
    nodes in the functional currency (T1F-Q-4), every other column as in the golden world."""
    bundle, output = foreign_entity()
    for book in output.books:
        trace_linkage.check_book(book, bundle, exceptions=PENDING_RULINGS)
        functional_rows = [
            row
            for row in book.balances
            if row.columns["functional_currency"] != bundle.group.transaction_currency
        ]
        assert functional_rows, book.book_code
        nodes = {node.id: node for node in book.trace.nodes}
        assert any(
            nodes[node_id].formula_id == "fx.functional_member.v1"
            for row in functional_rows
            for key, node_id in row.trace_nodes.items()
            if key.endswith("_functional")
        ), book.book_code


@pytest.mark.parametrize(("family", "key_id", "contract"), REMEASURED_WORLDS)
def test_returns_remeasured_worlds_link_the_version_date_adjustment(
    family: str, key_id: str, contract: str
) -> None:
    """T1F-R3: ``allocation_adjustment`` after a returns re-estimate links the stage 09
    version-date node ``allocation_adjustment@<latest event>`` (rec.allocation_adjustment.v1 over
    the ``allocated_amount`` node and the stated-price node), never the inception node whose
    value differs; every other column links as in the golden world."""
    bundle, output = answer_key_world(family, key_id, contract)
    for book in output.books:
        trace_linkage.check_book(book, bundle, exceptions=PENDING_RULINGS)
        nodes = {node.id: node for node in book.trace.nodes}
        for item in book.obligation_versions:
            if (
                item.columns["allocation_adjustment"]
                == item.columns["allocated_amount"] - item.columns["stated_price"]
            ):
                node = nodes[item.trace_nodes["allocation_adjustment"]]
                if node.measure != "allocation_adjustment":
                    assert node.formula_id in (
                        "rec.allocation_adjustment.v1",
                        "mod.allocation_adjustment.v1",
                    )


def test_residual_candidate_links_the_residual_ssp_node_under_the_alias() -> None:
    """D-98 candidate 23 (T1F-Q-5): the residual candidate's ``original_ssp_selected`` links the
    ``residual_ssp:<ob>:-`` node that produced R (S05-R-12) — one value, one node; every other
    column links as in the golden world (SSP-FS-05: LIC-PERP priced by the residual approach)."""
    bundle, output = answer_key_world("ssp", "SSP-FS-05-PERPETUAL-LICENCE-PCS-RESIDUAL", "FS-05")
    residual_seen = False
    for book in output.books:
        trace_linkage.check_book(book, bundle, exceptions=PENDING_RULINGS)
        nodes = {node.id: node for node in book.trace.nodes}
        for item in book.obligation_versions:
            node = nodes[item.trace_nodes["original_ssp_selected"]]
            if node.measure == "residual_ssp":
                residual_seen = True
                assert node.id == f"residual_ssp:{item.subject_key}:-"
                assert f"original_ssp_selected:{item.subject_key}:-" in nodes  # keeps 0, unlinked
    assert residual_seen


def _price_modification_returns_world(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, InputBundle, OutputBundle]]:
    """The RET-CHK-029 price-modification variant of ``test_s15_rpo_returns`` (40 units, +2,000.00
    on 15 February, remaining goods not distinct, the RETURN_RATE re-pinned at the boundary): the
    version's latest event is the boundary whose stage 06 node holds the GROSS adjustment while
    the returns re-estimate nets the allocation (Codex T1F-R3 ruling: the ``returns`` qualifier)."""
    import importlib.util

    from support.answer_keys.runners import _build_checkpoint_bundles

    source = Path(__file__).parents[1] / "s15_disclosures" / "test_s15_rpo_returns.py"
    monkeypatch.syspath_prepend(str(source.parent))  # its sibling import ``test_s15_rpo``
    spec = importlib.util.spec_from_file_location("t15_rpo_returns", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    loaded = module._variant(tmp_path, "RET-CHK-029-D91-PRICE-MOD-CCU", module._price_modification)
    worlds = []
    for checkpoint in _build_checkpoint_bundles(loaded):
        for bundle in checkpoint.bundles:
            worlds.append((checkpoint.name, bundle, compute(bundle)))
    return worlds


def test_returns_netted_adjustment_beside_a_gross_boundary_node_links_the_qualified_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex T1F-R3 ruling: after the 15 February price modification the stage 06 node
    ``allocation_adjustment@<event>:<ob>:-`` holds the gross adjustment (0.00) while the stored
    column is the returns-netted −600.00; stage 09 emits
    ``allocation_adjustment@<event>:<ob>:returns`` and the assembler links it. The same boundary's
    build-up (traced as the handler measured it, at the pre-event unit rate: expected returns
    −500.00) is beside the version-date memo −600.00, so the T-CON-08 ``expected_returns_amount``
    and ``transaction_price`` link ``<column>@<event>:<group>:returns`` (stage 13 output measures)
    while ``fixed_consideration`` 12,000.00 links the boundary's own ``-`` node (T1-F-2)."""
    qualified_seen = False
    for name, bundle, output in _price_modification_returns_world(tmp_path, monkeypatch):
        for book in output.books:
            trace_linkage.check_book(book, bundle, exceptions=PENDING_RULINGS)
            nodes = {node.id: node for node in book.trace.nodes}
            for item in book.obligation_versions:
                node = nodes[item.trace_nodes["allocation_adjustment"]]
                if node.id.endswith(":returns"):
                    qualified_seen = True
                    assert name != "end-of-january"
                    assert node.formula_id == "rec.allocation_adjustment.v1"
                    gross = nodes[node.id[: -len("returns")] + "-"]
                    assert gross.formula_id == "mod.allocation_adjustment.v1"
                    assert gross.value != node.value
            version = book.contract_version
            assert version is not None
            links = version.trace_nodes
            if name == "end-of-january":
                inception = f"fixed_consideration:{version.subject_key}:-"
                assert links["fixed_consideration"] == inception
                continue
            boundary = f"@C-RET/EV-000009:{version.subject_key}:"
            assert links["fixed_consideration"] == f"fixed_consideration{boundary}-"
            for column in ("expected_returns_amount", "transaction_price"):
                assert links[column] == f"{column}{boundary}returns", (name, column, links[column])
                netted = nodes[links[column]]
                assert netted.formula_id == "books.version_adjustment.v1"
                gross = nodes[f"{column}{boundary}-"]
                assert gross.formula_id.startswith("tp.")
                assert gross.value != netted.value
                assert netted.inputs == (gross.id,)
    assert qualified_seen


def test_pending_rulings_are_the_only_unlinked_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented exceptions are exactly what stays unlinked (no silent widening, no stale
    entry once a ruling lands): the union over the golden and modified worlds and both books."""
    value, output = golden()
    bundle, modified = modified_units()
    seen: dict[str, set[str]] = {family: set() for family in PENDING_RULINGS}
    _, foreign = foreign_entity()
    remeasured = [answer_key_world(*world)[1] for world in REMEASURED_WORLDS]
    remeasured.append(
        answer_key_world("ssp", "SSP-FS-05-PERPETUAL-LICENCE-PCS-RESIDUAL", "FS-05")[1]
    )
    remeasured.extend(
        world for _, _, world in _price_modification_returns_world(tmp_path, monkeypatch)
    )
    books = (
        *output.books,
        *modified.books,
        *foreign.books,
        *(b for o in remeasured for b in o.books),
    )
    for book in books:
        for family, columns in trace_linkage.unlinked_summary(book).items():
            seen[family] |= set(columns)
    assert {family: frozenset(columns) for family, columns in seen.items()} == dict(PENDING_RULINGS)


def test_golden_families_are_enumerated() -> None:
    """The families the checker enumerates on the golden world: the 48 value-typed obligation
    columns, the 17 contract-version value columns and 18 balance value columns per row (after the
    ENG-C7 merge), zeros included."""
    value, output = golden()
    book = _book(output, "ASC606")
    otypes = trace_linkage.loader.obligation_columns()
    ctypes = trace_linkage.loader.contract_version_columns()
    assert len(book.obligation_versions) == 4
    for item in book.obligation_versions:
        assert len(trace_linkage.expected_columns(item.columns, otypes)) >= 47  # memo None
    assert book.contract_version is not None
    assert len(trace_linkage.expected_columns(book.contract_version.columns, ctypes)) == 17
    assert len(book.balances) == 24
    assert all(len(trace_linkage.balance_link_columns(row.columns)) == 18 for row in book.balances)


def test_explain_reconstruction_against_native_links() -> None:
    """T1F-Q-2 (supervisor ruling): the explain service reconstructs a contract-version node id as
    ``<measure>:<group>:-`` and a balance node id as ``<measure>:<contract>@<entity>:<period>``
    (erev_api/explain/service.py) when no persisted link exists — and only ``obligation_version``
    rows persist ``trace_nodes``. The native balance links follow that convention exactly; the
    native contract-version links diverge exactly where the stored value is a boundary or
    version-date re-measurement (``<column>@<event>`` nodes, T1-F-2). The divergence is the
    documented public / native gap until the platform persists contract-version links
    (readiness row EXPLAIN-PERSISTED-LINKS)."""
    value, output = golden()
    for book in output.books:
        version = book.contract_version
        assert version is not None
        divergent = {
            column
            for column, node_id in version.trace_nodes.items()
            if node_id != f"{column}:{version.subject_key}:-"
        }
        boundary_linked = {
            column
            for column, node_id in version.trace_nodes.items()
            if node_id.split(":", 1)[0].startswith(f"{column}@")
        }
        assert divergent == boundary_linked, (book.book_code, divergent ^ boundary_linked)
        assert {"fixed_consideration", "transaction_price"} <= divergent, book.book_code
        for row in book.balances:
            for key, node_id in row.trace_nodes.items():
                measure = key[: -len("_functional")] if key.endswith("_functional") else key
                assert node_id == f"{measure}:{row.subject_key}:{row.period_key}", (key, node_id)


def _healthy(book: BookOutput, bundle: InputBundle) -> tuple[BookOutput, dict[str, frozenset[str]]]:
    """``book`` with every link that fails the checker today detached, and the unlinked columns per
    family as exceptions, so an omission test trips on its own mutation only (the inventory
    assertions above pin the engine's own gaps). Links are dropped one at a time until the checker
    passes; the loop terminates because every iteration removes a link."""
    current = book
    while True:
        exceptions = {
            family: frozenset(columns)
            for family, columns in trace_linkage.unlinked_summary(current).items()
        }
        try:
            trace_linkage.check_book(current, bundle, exceptions=exceptions, sources=False)
        except AssertionError as failure:
            family, *_ = failure.args[0]
            column = failure.args[0][3]
            current = _without(current, family, str(column))
            continue
        return current, exceptions


def _without(book: BookOutput, family: str, column: str) -> BookOutput:
    if family == "contract_version":
        assert book.contract_version is not None
        return dataclasses.replace(book, contract_version=_detach(book.contract_version, column))  # type: ignore[arg-type]
    if family == "obligation_version":
        return dataclasses.replace(
            book,
            obligation_versions=tuple(_detach(item, column) for item in book.obligation_versions),  # type: ignore[misc]
        )
    key = column[: -len("_txn")] if column.endswith("_txn") else column
    return dataclasses.replace(book, balances=tuple(_detach(row, key) for row in book.balances))  # type: ignore[misc]


def _detach(item: object, key: str) -> object:
    links = {k: v for k, v in item.trace_nodes.items() if k != key}  # type: ignore[attr-defined]
    return dataclasses.replace(item, trace_nodes=MappingProxyType(links))  # type: ignore[type-var]


def _with_node(book: BookOutput, node_id: str, **changes: object) -> BookOutput:
    """``book`` with the trace node ``node_id`` replaced field-wise (a corruption control)."""
    nodes = tuple(
        dataclasses.replace(node, **changes) if node.id == node_id else node  # type: ignore[arg-type]
        for node in book.trace.nodes
    )
    return dataclasses.replace(book, trace=dataclasses.replace(book.trace, nodes=nodes))


def test_exact_money_columns_validate_the_node_currency() -> None:
    """T1F-Q5-G1 (Codex, supervisor ruling): the ``erev.exact`` branch checked only the number, so
    ``check_book`` accepted a USD → EUR change on the monetary selected-SSP node. Now an exact money
    column (selected SSP and every other exact node that carries money) validates the node currency
    against the transaction currency, a dimensionless exact column (quantities, weights, ratios)
    requires a currency-free node, and an exact column outside both classes fails as unclassified.
    Controls on the SSP-FS-05 residual world: valid USD passes; EUR on the ordinary point-estimate
    node (the PCS renewal, ``ssp.point.v1``), EUR on the residual alias node and EUR on the
    T-CON-08 ``total_ssp`` node fail naming the column; USD on the dimensionless ``quantity`` node
    fails too."""
    bundle, output = answer_key_world("ssp", "SSP-FS-05-PERPETUAL-LICENCE-PCS-RESIDUAL", "FS-05")
    book, allowed = _healthy(_book(output, "ASC606"), bundle)
    assert bundle.group.transaction_currency == "USD"
    trace_linkage.check_book(book, bundle, exceptions=allowed, sources=False)  # valid USD passes
    nodes = {node.id: node for node in book.trace.nodes}
    selected = {item.trace_nodes["original_ssp_selected"] for item in book.obligation_versions}
    point = sorted(node_id for node_id in selected if nodes[node_id].formula_id == "ssp.point.v1")
    alias = sorted(node_id for node_id in selected if nodes[node_id].measure == "residual_ssp")
    assert point and alias
    assert book.contract_version is not None
    total_ssp = book.contract_version.trace_nodes["total_ssp"]
    quantity = book.obligation_versions[0].trace_nodes["quantity"]
    controls = (
        (point[0], "EUR", "obligation_version", "original_ssp_selected"),
        (alias[0], "EUR", "obligation_version", "original_ssp_selected"),
        (total_ssp, "EUR", "contract_version", "total_ssp"),
        (quantity, "USD", "obligation_version", "quantity"),
    )
    for node_id, wrong, family, column in controls:
        mutated = _with_node(book, node_id, currency=wrong)
        with pytest.raises(AssertionError) as failure:
            trace_linkage.check_book(mutated, bundle, exceptions=allowed, sources=False)
        where = failure.value.args[0]
        assert (where[0], where[3]) == (family, column), (node_id, where)
        assert "currency" in str(where[-1]), (node_id, where)


def test_every_exact_column_is_classified_as_money_or_dimensionless() -> None:
    """The two classes partition the ``erev.exact`` columns of T-CON-08 and T-CON-11 (a new exact
    column must be classified before the checker accepts it)."""
    from support.answer_keys import loader

    exact = {
        column
        for table in (loader.obligation_columns(), loader.contract_version_columns())
        for column, kind in table.items()
        if kind == "erev.exact"
    }
    money, dimensionless = (
        trace_linkage.MONEY_EXACT_COLUMNS,
        trace_linkage.DIMENSIONLESS_EXACT_COLUMNS,
    )
    assert money.isdisjoint(dimensionless)
    assert money | dimensionless == exact, sorted((money | dimensionless) ^ exact)


def _relink(item: object, key: str, node_id: str) -> object:
    links = {**item.trace_nodes, key: node_id}  # type: ignore[attr-defined]
    return dataclasses.replace(item, trace_nodes=MappingProxyType(links))  # type: ignore[type-var]


def test_a_detached_obligation_link_fails_naming_the_column() -> None:
    value, output = golden()
    book, allowed = _healthy(_book(output, "ASC606"), value)
    first, *rest = book.obligation_versions
    mutated = dataclasses.replace(
        book,
        obligation_versions=(_detach(first, "revenue_cum"), *rest),  # type: ignore[arg-type]
    )
    with pytest.raises(AssertionError) as raised:
        trace_linkage.check_book(mutated, value, exceptions=allowed, sources=False)
    assert ("obligation_version", "ASC606", first.subject_key) == raised.value.args[0][:3]
    assert "revenue_cum" in raised.value.args[0][4]


def test_a_mistargeted_link_fails_on_measure_and_subject() -> None:
    value, output = golden()
    book, allowed = _healthy(_book(output, "ASC606"), value)
    first, second, *rest = book.obligation_versions
    # Another measure of the same obligation.
    wrong_measure = _relink(first, "revenue_cum", first.trace_nodes["scheduled_amount"])
    with pytest.raises(AssertionError) as raised:
        trace_linkage.check_book(
            dataclasses.replace(book, obligation_versions=(wrong_measure, second, *rest)),  # type: ignore[arg-type]
            value,
            exceptions=allowed,
            sources=False,
        )
    assert "not 'revenue_cum'" in str(raised.value.args[0][-1])
    # The same measure of another obligation.
    wrong_subject = _relink(first, "revenue_cum", second.trace_nodes["revenue_cum"])
    with pytest.raises(AssertionError) as raised:
        trace_linkage.check_book(
            dataclasses.replace(book, obligation_versions=(wrong_subject, second, *rest)),  # type: ignore[arg-type]
            value,
            exceptions=allowed,
            sources=False,
        )
    assert "not a version-state node of the obligation" in str(raised.value.args[0][-1])


def test_a_stale_contract_link_fails_on_the_value_tie() -> None:
    """T1-F-2: the inception build-up node under a column that holds the last boundary's value."""
    value, output = golden()
    book, allowed = _healthy(_book(output, "ASC606"), value)
    version = book.contract_version
    assert version is not None
    stale = _relink(version, "fixed_consideration", f"fixed_consideration:{version.subject_key}:-")
    with pytest.raises(AssertionError) as raised:
        trace_linkage.check_book(
            dataclasses.replace(book, contract_version=stale),  # type: ignore[arg-type]
            value,
            exceptions={
                **allowed,
                "contract_version": allowed["contract_version"] - {"fixed_consideration"},
            },
        )
    assert raised.value.args[0][:4] == (
        "contract_version",
        "ASC606",
        version.subject_key,
        "fixed_consideration",
    )


def test_a_detached_balance_link_fails_naming_the_column() -> None:
    value, output = golden()
    book, allowed = _healthy(_book(output, "ASC606"), value)
    first, *rest = book.balances
    mutated = dataclasses.replace(book, balances=(_detach(first, "contract_asset"), *rest))  # type: ignore[arg-type]
    with pytest.raises(AssertionError) as raised:
        trace_linkage.check_book(mutated, value, exceptions=allowed, sources=False)
    assert raised.value.args[0][0] == "contract_version_balance"
    assert "contract_asset_txn" in raised.value.args[0][-1]
