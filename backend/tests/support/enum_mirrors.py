"""DG-ARC-09 enum mirrors, shared by the architecture (CPU) and pg halves of the drift test
(dev-guide §6.8; 04 §3.4; lane P5 slices 1b and 1c after Codex 0515
``PRODUCTION-MAIN-PG-FAILURE-6e33ef27``; D-98 66).

``database_enums()`` — the StrEnums of ``erev_api.enums`` that mirror a PostgreSQL enum type
(``API_ONLY`` classes excluded), keyed by the 04 type name.

``migration_enum_types()`` — the ``erev.<type>`` enum types the committed Alembic revisions create,
obtained by replaying every ``upgrade()`` under ``migration_ops.recording()``: no database, the DDL
the helpers would run is captured and the ``CREATE TYPE … AS ENUM`` names are read from it.

The D-98 66 **exemption lists** — explicit and shrink-only. Every name below IS exempt from the
missing-type finding (Codex retest 9b6cb85, correction 1), so each entry carries its disposition —
the owning BUILD_SPEC item and the planned revision, or the D-98 67 / 68 representation ruling — and
no green count rests on an unexplained exemption. No entry is added without a recorded ruling; an
entry whose type lands must be removed (``type_gaps`` reports it); every entry is a mirror:

- ``PENDING_ENUM_TYPES`` — enumerations whose 04 table is later-phase and not built; each entry
  names the enumeration, the owning table and column, the BUILD_SPEC item that builds the table and
  the revision expected to create the type (04 §3.4 rows carry "PostgreSQL type pending (owed by
  …)").
- ``TEXT_CHECK_ENUM_TYPES`` — E-04 ``period_state``: the deliberate TEXT + CHECK representation
  (D-98 67, 04 rev 1.29): T-REF-06 ``state`` and T-REF-07 ``from_state`` / ``to_state`` are ``text``
  with ``CHECK`` ∈ the E-04 literals (revision 0029, L1-1-Q-20; the migration's CHECK labels equal
  E-04 / Python); the PostgreSQL row type ``erev.period_state`` belongs to table T-REF-06, so an
  enum type of that name cannot exist and none is owed.
- ``VALUE_ONLY_ENUM_TYPES`` — E-82 ``reporting_entity_type``: value list only (D-98 68, 04 rev
  1.29): no 04 column is typed with it (REQ-REF-016 policy-registry values, T-PLT-31 / T-PLT-32), so
  no type is owed unless a column appears (a ruling then).

E-125 to E-130 are deliberately absent — revision 0055 creates them.
"""

from __future__ import annotations

import enum
import importlib.util
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from erev_api import enums
from erev_api.db import migration_ops as ops

VERSIONS_DIR: Final = Path(ops.__file__).parent / "migrations" / "versions"
_CREATE_TYPE: Final = re.compile(r"CREATE TYPE erev\.(\w+) AS ENUM")


@dataclass(frozen=True, slots=True)
class ReconciledEnumType:
    """The disposition of an exempted mirror: why it has no PostgreSQL type (D-98 66 / 67 / 68)."""

    enumeration: str  # 04 §3.4 id
    table: str  # the 04 table (and column) that types with it
    item: str  # the BUILD_SPEC item / lane that builds the table, or the ruling
    revision: str  # the migration expected to create the type, or the ruling reference


_CTR_14 = ("CTR-14", "NNNN_ctr_14_costs_material_rights_loss_fx.py")
PENDING_ENUM_TYPES: Final[Mapping[str, ReconciledEnumType]] = {
    "ai_proposal_kind": ReconciledEnumType(
        "E-73", "T-AI-01 ai_proposal.kind", "AIX-1", "NNNN_ai_tables.py"
    ),
    "ai_proposal_status": ReconciledEnumType(
        "E-74", "T-AI-01 ai_proposal.status", "AIX-1", "NNNN_ai_tables.py"
    ),
    "cost_kind": ReconciledEnumType("E-83", "T-CON-15 contract_cost_asset.cost_kind", *_CTR_14),
    "amortization_pattern": ReconciledEnumType(
        "E-84", "T-CON-15 contract_cost_asset.amortization_pattern", *_CTR_14
    ),
    "loss_unit": ReconciledEnumType("E-85", "T-CON-17 loss_provision_version.unit", *_CTR_14),
    "option_type": ReconciledEnumType("E-92", "T-CON-14 material_right.option_type", *_CTR_14),
    "scenario_status": ReconciledEnumType(
        "E-100", "T-FC-01 scenario.status", "FCS-1", "NNNN_forecast_tables.py"
    ),
}
TEXT_CHECK_ENUM_TYPES: Final[Mapping[str, ReconciledEnumType]] = {
    "period_state": ReconciledEnumType(
        "E-04",
        "T-REF-06 period_state.state; T-REF-07 period_state_transition.from_state / to_state",
        "D-98 67 / RFD-2: TEXT + CHECK ∈ the E-04 literals (revision 0029, L1-1-Q-20)",
        "0029_entities_books_period_states.py — no enum type owed: the row type erev.period_state "
        "belongs to table T-REF-06; the CHECK labels equal E-04 / Python",
    ),
}
VALUE_ONLY_ENUM_TYPES: Final[Mapping[str, ReconciledEnumType]] = {
    "reporting_entity_type": ReconciledEnumType(
        "E-82",
        "no 04 column is typed with it (REQ-REF-016 value list; policy registry T-PLT-31/32)",
        "D-98 68: value list only (REQ-REF-016; policy registry)",
        "none owed unless a column appears (a ruling then)",
    ),
}
RECONCILED_ENUM_TYPES: Final[Mapping[str, ReconciledEnumType]] = {
    **PENDING_ENUM_TYPES,
    **TEXT_CHECK_ENUM_TYPES,
    **VALUE_ONLY_ENUM_TYPES,
}


def database_enums() -> dict[str, type[enum.StrEnum]]:
    """StrEnums with a PostgreSQL type, keyed by the 04 enum name (API-only enums excluded)."""
    return {
        re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower(): value
        for name, value in vars(enums).items()
        if isinstance(value, type)
        and issubclass(value, enum.StrEnum)
        and value.__module__ == enums.__name__
        and not getattr(value, "API_ONLY", False)
    }


def load_revision(path: Path) -> object:
    """Import one revision file by path (their names start with digits)."""
    spec = importlib.util.spec_from_file_location(f"erev_revision_{path.stem}", path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def migration_enum_types(versions_dir: Path = VERSIONS_DIR) -> dict[str, str]:
    """``{type name: revision file}`` for every enum type the committed ``upgrade()``s create."""
    created: dict[str, str] = {}
    for path in sorted(versions_dir.glob("[0-9]*.py")):
        module = load_revision(path)
        with ops.recording() as statements:
            module.upgrade()  # type: ignore[attr-defined]
        for statement in statements:
            for name in _CREATE_TYPE.findall(statement):
                created.setdefault(name, path.name)
    return created


def type_gaps(
    created: Iterable[str], mirrors: Mapping[str, type[enum.StrEnum]] | None = None
) -> list[str]:
    """The reverse direction of DG-ARC-09: mirrors with neither a created type nor an exemption
    entry; entries whose type has landed (shrink: remove them); entries naming no mirror."""
    present = set(created)
    classes = database_enums() if mirrors is None else mirrors
    findings = [
        f"erev.{name}: no PostgreSQL enum type for {classes[name].__name__}"
        for name in sorted(classes)
        if name not in present and name not in RECONCILED_ENUM_TYPES
    ]
    findings += [
        f"erev.{name}: type created ({RECONCILED_ENUM_TYPES[name].enumeration}) — remove it from "
        "the D-98 66 reconciliation list"
        for name in sorted(RECONCILED_ENUM_TYPES)
        if name in present
    ]
    findings += [
        f"erev.{name}: the reconciliation list names no database-candidate StrEnum"
        for name in sorted(RECONCILED_ENUM_TYPES)
        if name not in classes
    ]
    return findings
