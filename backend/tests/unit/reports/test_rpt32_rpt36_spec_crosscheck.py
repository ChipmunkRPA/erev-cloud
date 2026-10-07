"""RPT-32 and RPT-36 specification cross-check and registration readiness (SCREENS_B §5.6.1
RPT-32, RPT-36; catalogue definitions; `framework.BUILDERS`; supervisor ruling Q-2 of
`docs/reviews/loop/prod/F-RPS-ENG-E1-prep.md`). CPU-only, lane F-RPS + ENG-E1.

The grids are parsed from the frozen SCREENS_B text so a later specification edit or a builder
column drift fails here; the registration assertions flip when RPS-12 registers the builders after
their database tests pass, and the CTR-14 assertions flip when the catalogue sources are persisted.
"""

from __future__ import annotations

import inspect
import re
from typing import Final

from erev_api.db import tables
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import balance_aging as aging
from erev_api.domain.reports.builders import contract_cost_rollforward as costs
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from support.architecture import read

RPT_36: Final = "##### RPT-36 `balance_aging` Balance aging"
RPT_32: Final = "##### RPT-32 `contract_cost_rollforward` Contract cost rollforward"
_GRID_ROW: Final = re.compile(r"^\| ([A-Z0-9][^|`]*?) \| `([a-z_0-9]+)` \|")


def _section(title: str) -> str:
    return read("docs/design/SCREENS_B.md").split(title, 1)[1].split("#####", 1)[0]


def _grid(section: str) -> list[tuple[str, str]]:
    """(header, field) of every grid row whose first cell is a header (parameter rows start with
    a backtick and are skipped); the ``(<ISO>)`` presentation suffix is dropped."""
    rows: list[tuple[str, str]] = []
    for line in section.splitlines():
        match = _GRID_ROW.match(line)
        if match is not None:
            rows.append((match.group(1).replace(" (<ISO>)", "").strip(), match.group(2)))
    return rows


def test_rpt_36_grid_matches_the_builder_columns() -> None:
    section = _section(RPT_36)
    assert _grid(section) == [(column.header, column.key) for column in aging.COLUMNS]
    assert "`row_key` `contract:<external id>:<role>`" in section
    assert re.search(r"one per contract × balance role with a non-zero balance", section)
    labels = re.search(r"\| Balance \| `balance_role` \| ([^|]+) \|", section)
    assert labels is not None
    assert set(re.findall(r'"([^"]+)"', labels.group(1))) == set(aging.ROLE_LABELS.values())
    assert aging.ROLE_LABELS.keys() == set(aging.ROLES) == set(aging.ROLE_MEASURES)
    assert "Age of a balance amount = days from the effective date of its layer" in section
    assert (
        '"All balances", "Contract asset", "Unbilled receivable", "Contract liability"' in section
    )
    assert aging.BUCKET_FIELDS == tuple(
        key for _, key in _grid(section) if key.startswith("bucket_")
    )


def test_rpt_32_grid_matches_the_builder_columns() -> None:
    """RPT-32 rev 1.14 (D-98 85 / 97): the governed long dataset — the grid's fields are the
    builder's columns, the key columns `cost_kind` / `line_code` are codes, the eight S15-R-17 line
    codes and both category labels are named in the specification text."""
    section = _section(RPT_32)
    grid = _grid(section)
    columns = {column.key: column.header for column in costs.COLUMNS}
    assert grid == [(columns[key], key) for _, key in grid]  # every spec field with its header
    assert {key for _, key in grid} == {
        "category_label",
        "line_label",
        "amount",
        "cost_kind",
        "line_code",
        "entity_code",
    }
    assert set(costs.KEY_COLUMNS) <= {key for _, key in grid}
    assert "grid = pivot of the dataset rows, the dataset is the long form" in section
    for code in costs.LINE_CODES:
        assert f'`{code}` "{costs.LINE_LABELS[code]}"' in section, code
    assert {code: costs.CATEGORY_LABELS[code] for code in costs.COST_KINDS} == {
        "OBTAIN": "Costs to obtain a contract",
        "FULFILL": "Costs to fulfil a contract",
    }
    for code, label in costs.CATEGORY_LABELS.items():
        assert f'`{code}` "{label}"' in section
    assert "| Currency view | yes; default `functional`." in section
    assert costs.DEFAULT_CURRENCY_VIEW == "functional"
    assert 'Section 2 "By cost asset" (rev 1.7 wording, DEFERRED' in section


def test_catalogue_definitions_match_the_builders() -> None:
    """Tie-out codes, parameters and the (unpersisted) catalogue sources of the two definitions."""
    aging_def = DEFINITIONS_BY_CODE[aging.CODE]
    assert aging_def.tie_outs == (aging.TO_AGING_EQ_BALANCES,)
    properties = aging_def.parameters_schema["properties"]
    assert {
        "entity_codes",
        "book",
        "period_lock_id",
        "period_key",
        "balance_role",
        "currency_view",
    } <= set(properties)
    assert set(properties["balance_role"]["enum"]) == {"ALL", *aging.ROLES}
    assert "fx_layer_movement" in aging_def.ipe_logic["source_tables"]
    costs_def = DEFINITIONS_BY_CODE[costs.CODE]
    assert costs_def.tie_outs == (costs.TO_COST_ROLLFORWARD_BALANCES,)
    assert {"from_period_key", "to_period_key", "currency_view", "book"} <= set(
        costs_def.parameters_schema["properties"]
    )
    assert {"contract_cost_asset", "cost_asset_version"} <= set(
        costs_def.ipe_logic["source_tables"]
    )
    # CTR-14 has not persisted the catalogue sources: the interim subledger source stands
    # (ruling Q-2).

    # Revision 0131 supplies liability layers; T-ENG-03 supplies asset presentation.
    assert hasattr(tables, "fx_layer_movement")
    for name in ("contract_cost_asset", "cost_asset_version"):
        assert not hasattr(tables, name), (
            f"{name} exists: switch the builder off the interim source"
        )
    assert hasattr(tables, "subledger_line")


def test_registration_readiness() -> None:
    """Both builders satisfy the RPS-2 contract shape. Balance aging is registered after
    its database source and acceptance verification;
    `contract_cost_rollforward` is registered by the supervisor's RPS-12 dispatch (D-98 85, lane
    ENG-C8; its DB path is exercised by the admitted database test) with its non-false default
    named in PARAMETER_DEFAULTS (D-87 L6-3-Q-29)."""
    for module in (aging, costs):
        parameters = inspect.signature(module.build).parameters
        assert list(parameters) == ["uow", "params"]
        assert "UnitOfWork" in str(parameters["uow"].annotation)
        assert "ReportParams" in str(parameters["params"].annotation)
        assert module.CODE in DEFINITIONS_BY_CODE
        keys = [column.key for column in module.COLUMNS]
        assert len(set(keys)) == len(keys) and "row_key" not in keys
    assert framework.BUILDERS[aging.CODE] is aging.build
    assert framework.BUILDERS[costs.CODE] is costs.build
    assert framework.PARAMETER_DEFAULTS[costs.CODE] == {"currency_view": "functional"}
