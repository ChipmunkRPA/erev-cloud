"""D-98 candidate 89 (04 §17.1 rules 4 and 4a rev 1.75; SCREENS_B RPT-10 rev 1.24;
DG-PAR-05; Codex production-20260921-1155 §1 (c); lane F-LMG record §27): the seven legacy-named
columns of the legacy export, measured against the shipped legacy database
``backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db`` (read-only; DG-LAY-11) for
Contracts 1 and 2 at setup (golden step 02, rank 1) and after the 2023-01-31 deliveries (golden
step 04, rank 3),
through the product's ``exact_sources`` reader over each computed version's OWN trace and the
``legacy_columns`` Values:

- the six exact-sourced columns (LM-CL-35 / 50 / 61 / 66 / 67 / 68) match the shipped unrounded
  values within DG-PAR-07's 1/10000 on every version — including the largest batch-#5 Δ, Contract 1
  POB #2 rank 3 (legacy 118.53320118929634; posted 118.54; exact 118.533201189296333003);
- ``Previous Remaining Allocation`` at rank 3 is the rank-1 version's OWN node;
- ``Current Rev Rec`` (LM-CL-55) is the exact ACTIVITY under rule 4a (D-98 89 RULING 2 +
  AMENDMENT 1; D-98 candidate 149): the OWN serialized value of the companion the posted
  ``revenue_amount`` node names in ``params["exact_node"]`` (ENG-T1F's T1F-89-1, main 74899034),
  validated by the shared checker under full replay — the four activity cells batch #5 named
  (asserted BY NAME as misses until this consumer) now match within the same tolerance; every
  golden activity is SUPPORTED (no ``exact_basis``), asserted per row.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.migration import legacy_db
from erev_api.domain.migration.reconciliation import exact_decimal_text
from erev_api.domain.reports import exact_sources, legacy_columns
from erev_engine import compute
from erev_engine.money import format_exact
from erev_engine.trace import Trace, exact_companion_failures, reevaluate
from support import golden_streams, intent_totals

FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "legacy_db" / "ASC606-shipped-step04.db"
)
MANIFEST = FIXTURE.parents[1] / "manifest.json"
TOLERANCE = Fraction(1, 10_000)  # DG-PAR-07
CASES = (
    ("Contract 1", "02", date(2023, 1, 1)),
    ("Contract 1", "04", date(2023, 1, 31)),
    ("Contract 2", "02", date(2023, 1, 1)),
    ("Contract 2", "04", date(2023, 1, 31)),
)
EXACT_NAMES = (
    "Current Remaining Allocation",
    "Current Rev Rec - Cumulative",
    "Current Contract Position - POB",
    "Current Contract Position - Contract Level",
    "Current Reclass to UAR",
)
ACTIVITY = "Current Rev Rec"
PREVIOUS = "Previous Remaining Allocation"
# batch #5's four activity cells (rank 3): the operand Codex 1155 named absent — ENG-T1F's
# T1F-89-1 companion supplies it and rule 4a's consumer writes it; asserted closed by name
ACTIVITY_CELLS_CLOSED = {
    ("Contract 1", "04", "POB #1"),
    ("Contract 1", "04", "POB #2"),
    ("Contract 1", "04", "POB #3"),
    ("Contract 2", "04", "POB #1"),
}
MONEY = (
    "revenue_amount",
    "remaining_allocation",
    "revenue_cum",
    "position_obligation",
    "position_contract_entity",
    "netting_reclass_amount",
)


def _legacy_rows() -> dict[tuple[str, str, date], Mapping[str, str | None]]:
    pinned = next(
        item["sha256"]
        for item in json.loads(MANIFEST.read_text())
        if item["path"] == "legacy_db/ASC606-shipped-step04.db"
    )
    assert legacy_db.file_sha256(FIXTURE) == pinned
    found: dict[tuple[str, str, date], Mapping[str, str | None]] = {}
    for row in legacy_db.load_legacy_rows(FIXTURE):
        period = date.fromisoformat(str(row["Current Period"])[:10])
        found[(str(row["Contract Unique Name"]), str(row["POB Unique ID"]), period)] = row
    return found


def _version_id(contract: str, step: str) -> UUID:
    return UUID(int=int(step) * 16 + int(contract[-1]))


def _computed(contract: str, step: str) -> tuple[dict[str, dict[str, Any]], Trace]:
    """The export-shaped rows of the computed obligation versions (money in major units as the
    database holds them; ``trace_nodes`` and a version id) and the book's trace."""
    stream = golden_streams.stream(contract, step)
    bundle = intent_totals.activated(stream.input_bundle(preset="LEGACY_PARITY", books=("ASC606",)))
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    rows: dict[str, dict[str, Any]] = {}
    for item in book.obligation_versions:
        columns = dict(item.columns)
        row: dict[str, Any] = {
            "id": f"{contract}/{step}/{columns['obligation_key']}",
            "contract_version_id": _version_id(contract, step),
            "trace_nodes": dict(item.trace_nodes),
            "obligation_key": columns["obligation_key"],
            "txn_currency": columns["txn_currency"],
            # the database holds the erev.exact quota at the TY-02 scale (format_exact, 18 places)
            "original_allocated_exact": Decimal(
                format_exact(Fraction(columns["original_allocated_exact"]))
            ),
        }
        for name in MONEY:
            row[name] = Decimal(int(columns[name])).scaleb(-2)  # minor units → the stored money
        rows[str(columns["obligation_key"])] = row
    return rows, book.trace


def _column(name: str) -> legacy_columns.LegacyColumn:
    return next(column for column in legacy_columns.CONTRACT_LIVE if column.name == name)


def _within(text: str | None, legacy: str | None) -> bool:
    if text is None or legacy is None:
        return text is None and legacy is None
    return abs(Fraction(Decimal(text)) - Fraction(Decimal(str(legacy)))) <= TOLERANCE


@pytest.mark.parametrize("contract", ("Contract 1", "Contract 2"))
def test_legacy_export_exact_columns_and_activity_equal_the_shipped_rows(
    contract: str,
) -> None:
    legacy = _legacy_rows()
    computed = {step: _computed(contract, step) for step in ("02", "04")}
    traces = {_version_id(contract, step): trace for step, (_rows, trace) in computed.items()}
    for rows, _trace in computed.values():
        loaded = exact_sources.attach_exact_texts(
            None, list(rows.values()), loader=lambda _s, version_id: traces[version_id]
        )
        assert loaded == 1  # one trace per contract version
    # Codex 1521 §3 (a) — the linkage is actual: every rendered node is the one the row's OWN
    # trace_nodes binds, found in the trace of the row's OWN contract version, in the version's
    # transaction currency; the book is fixed by that version (the ASC606 book of the golden world)
    for rows, trace in computed.values():
        nodes = {node.id: node for node in trace.nodes}
        for row in rows.values():
            for column in legacy_columns.EXACT_COLUMNS:
                node = nodes[row["trace_nodes"][column]]
                assert node.measure == column
                assert node.currency == row["txn_currency"] == "USD"
                assert node.id.startswith(f"{column}:")
    misses: list[tuple[str, str, str, str, str | None, str | None]] = []
    checked = 0
    for contract_name, step, period in CASES:
        if contract_name != contract:
            continue
        rows = computed[step][0]
        for key, row in sorted(rows.items()):
            shipped = legacy[(contract, key, period)]
            previous = computed["02"][0][key] if step == "04" else None
            for name in (*EXACT_NAMES, ACTIVITY, PREVIOUS):
                text = _column(name).value(row, previous)
                checked += 1
                if not _within(text, shipped[name]):
                    misses.append((contract, step, key, name, text, shipped[name]))
    assert checked >= 7 * 7
    # rule 4a (rev 1.75): batch #5's four activity cells match too — no miss remains, and every
    # named cell is in the measured population
    assert misses == []
    measured = {(contract, "04", key) for key in computed["04"][0]}
    assert {cell for cell in ACTIVITY_CELLS_CLOSED if cell[0] == contract} <= measured
    # every golden activity is SUPPORTED: the posted node names its OWN companion and no
    # exact_basis, the shared checker reports nothing under full replay, and the attached text is
    # the companion's own serialized value — never the posted node's value + residue
    for rows, trace in computed.values():
        nodes = {node.id: node for node in trace.nodes}
        assert exact_companion_failures(trace, reevaluate(trace)) == []
        for row in rows.values():
            posted = nodes[row["trace_nodes"]["revenue_amount"]]
            # CL55-BINDING-1: the binding itself — measure and populated matching currency on
            # the posted node and on its companion (Codex 0233 §2–§3)
            assert posted.measure == "revenue_amount"
            assert posted.currency == row["txn_currency"] == "USD"
            assert "exact_basis" not in posted.params
            companion = nodes[posted.params["exact_node"]]
            assert companion.id == f"revenue_amount_exact:{posted.id.split(':', 1)[1]}"
            assert companion.measure == "revenue_amount_exact"
            assert companion.currency == "USD"
            assert companion.rounding_residue is None
            assert row[legacy_columns.EXACT_TEXT_KEY]["revenue_amount"] == exact_decimal_text(
                Fraction(Decimal(companion.value))
            )
    if contract == "Contract 1":
        row = computed["04"][0]["POB #2"]
        assert _column("Current Remaining Allocation").value(row, None) == "118.533201189296333003"
        # the batch-#5 activity cell: the companion's 118.533201189296333003, not the posted 118.53
        assert _column(ACTIVITY).value(row, None) == "118.533201189296333003"
    else:
        row = computed["04"][0]["POB #1"]
        assert _column(ACTIVITY).value(row, None) == "58.846153846153846154"  # posted 58.85


def test_rule_4_currency_is_populated_and_matching_across_the_golden_population() -> None:
    # CL55-RULE4-CURRENCY-1 (04 §17.1 rule 4 rev 1.87; Codex 0431 §4): the consumer now refuses a
    # NULL node or version currency on the five exact columns — the golden world is UNCHANGED: every
    # golden contract at every golden step that computes attaches without a finding, and every
    # bound rule-4 node carries the version's populated currency (the read-only measurement of
    # 2026-09-22 — 50 computed versions, 1,010 bindings, 0 NULL, 0 mismatch — as a test; a change
    # in these counts is a golden-population change, not a currency defect)
    versions = bindings = rows_visited = nulls = mismatches = 0
    for contract in [f"Contract {i}" for i in range(1, 9)]:
        for step in [s.number for s in golden_streams.steps("99")]:
            try:
                rows, trace = _computed(contract, step)
            except ValueError:
                continue  # a contract without rows at that step, or a step that does not compute
            versions += 1
            # the consumer itself: any NULL / mismatched currency would refuse the whole run here
            exact_sources.attach_exact_texts(
                None, list(rows.values()), loader=lambda _s, _v, t=trace: t
            )
            nodes = {node.id: node for node in trace.nodes}
            for row in rows.values():
                rows_visited += 1
                for column in legacy_columns.EXACT_COLUMNS:
                    node = nodes[row["trace_nodes"][column]]
                    bindings += 1
                    if row["txn_currency"] is None or node.currency is None:
                        nulls += 1
                    elif node.currency != row["txn_currency"]:
                        mismatches += 1
    # the structural invariant FIRST (supervisor ruling 2026-09-22): every visited row binds all
    # five exact columns and none is NULL or mismatched — a failure HERE is a currency defect
    assert len(legacy_columns.EXACT_COLUMNS) == 5
    assert bindings == 5 * rows_visited
    assert (nulls, mismatches) == (0, 0)
    # THEN the population pin — it changes only by a recorded ruling (the snapshot 24 → 25
    # precedent); a failure here alone is a golden-population change, not a currency defect
    assert (versions, bindings) == (50, 1010)
