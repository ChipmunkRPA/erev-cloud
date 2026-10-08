"""Data-model drift DG-ARC-09 (dev-guide §6.8; 04 §3, T-PLT-11, §15.2; BUILD_SPEC FND-7, 9; EKC-5).

The tests read docs/04-DATA_MODEL.md and docs/02-PRD.md read-only and compare them with the Python
mirrors: the StrEnums of ``erev_api.enums`` and ``erev_engine.enums``, the permission catalogue,
``PROBLEMS`` and the ``erev_api.db.tables`` columns.
The ``pg_enum`` part lives in ``backend/tests/pg/test_data_model_drift_pg.py``.
"""

from __future__ import annotations

import enum
import re
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType

from erev_api import enums
from erev_api.auth.permissions import CATALOGUE
from erev_api.db import tables
from erev_api.problems import PROBLEMS
from erev_engine import enums as engine_enums

ROOT = Path(__file__).resolve().parents[3]
# 04 §3 enumerations the engine reads (BUILD_SPEC EKC-5).
ENGINE_ENUMERATIONS = frozenset(
    {
        1,
        2,
        3,
        4,
        11,
        17,
        18,
        19,
        21,
        22,
        23,
        27,
        28,
        31,
        47,
        49,
        55,
        56,
        77,
        86,
        87,
        89,
        90,
        91,
        105,
        131,
    }
)
DATA_MODEL = ROOT / "docs" / "04-DATA_MODEL.md"
PRD = ROOT / "docs" / "02-PRD.md"
WITHDRAWN = frozenset({35, 48})
_ERROR_CODE = re.compile(r"EREV-[A-Z]{2,3}-\d{3}")

_LITERAL = re.compile(r"^`([A-Za-z0-9_]+)`$")
_SUBSECTION = re.compile(r"^### 3\.\d+ E-(\d+) `([a-z_]+)`", re.MULTILINE)
# 04 §1.3 standard column sets in physical order.
STANDARD_SETS: dict[str, tuple[str, ...]] = {
    "SC-T": ("tenant_id", "id"),
    "SC-C": ("created_at", "created_by", "created_by_kind"),
    "SC-M": ("updated_at", "updated_by", "updated_by_kind", "row_version"),
    "SC-V": (
        "version_no",
        "status",
        "effective_from",
        "effective_to",
        "content_sha256",
        "approval_request_id",
        "published_at",
        "published_by",
        "supersedes_version_id",
    ),
}


@dataclass(frozen=True, slots=True)
class Enumeration:
    number: int
    name: str  # "withdrawn" for E-35 and E-48
    values: tuple[str, ...]
    api_only: bool


@cache
def data_model() -> str:
    return DATA_MODEL.read_text(encoding="utf-8")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def enumerations() -> list[Enumeration]:
    """E-01 to E-124 as tabled in 04 §3.1 to §3.4, in id order."""
    section = _between(data_model(), "\n## 3. Enumerations", "\n## 4. Platform tables")
    found: list[Enumeration] = []
    for match in _SUBSECTION.finditer(section):
        values: list[str] = []
        body = section[match.end() : section.find("\n### ", match.end())]
        for line in body.splitlines():
            if not line.startswith("|"):
                continue
            literal = next(
                (m.group(1) for cell in _cells(line) if (m := _LITERAL.match(cell))), None
            )
            if literal is not None:
                values.append(literal)
        found.append(Enumeration(int(match.group(1)), match.group(2), tuple(values), False))
    for line in section[section.index("### 3.4 Other enumerations") :].splitlines():
        cells = _cells(line) if line.startswith("| E-") else []
        if not cells or not re.fullmatch(r"E-\d+", cells[0]):
            continue
        number = int(cells[0].removeprefix("E-"))
        if cells[1] == "withdrawn":
            found.append(Enumeration(number, "withdrawn", (), False))
            continue
        name = _LITERAL.match(cells[1])
        assert name is not None, line
        values = tuple(re.findall(r"`([A-Za-z0-9_]+)`", cells[2]))
        found.append(Enumeration(number, name.group(1), values, cells[3].startswith("API only")))
    return sorted(found, key=lambda enumeration: enumeration.number)


def class_name(enum_name: str) -> str:
    return "".join(part.capitalize() for part in enum_name.split("_"))


def str_enums(module: ModuleType = enums) -> dict[str, type[enum.StrEnum]]:
    return {
        name: value
        for name, value in vars(module).items()
        if isinstance(value, type)
        and issubclass(value, enum.StrEnum)
        and value.__module__ == module.__name__
    }


def table_columns(table: str) -> list[str]:
    """Column names of the 04 table specification ``### T-…-nn `<table>```, SC sets expanded."""
    text = data_model()
    match = re.search(rf"^### T-[A-Z]+-\d+ `{re.escape(table)}`$", text, re.MULTILINE)
    assert match is not None, f"04 has no table specification for {table}"
    lines = text[match.end() : text.find("\n### ", match.end())].splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("| Column |"))
    columns: list[str] = []
    for line in lines[header + 2 :]:
        if not line.startswith("|"):
            break
        first = _cells(line)[0]
        if first.startswith("SC-"):
            for standard_set in first.split(","):
                columns += STANDARD_SETS[standard_set.strip()]
            continue
        column = re.fullmatch(r"`([a-z0-9_]+)`", first)
        assert column is not None, line
        columns.append(column.group(1))
    return columns


def test_dg_arc_09_enums_match_data_model() -> None:
    rows = enumerations()
    # E-125 to E-130: P5 (D-96); E-131: ENG-C1b `ssp_quantity_unit`; E-132: SECFIX-ACT
    # `step1_gate_reason` (API only; supervisor rulings R-77 (6), R-84 (b); 04 rev 1.138)
    assert [row.number for row in rows] == list(range(1, 133))
    assert {row.number for row in rows if row.name == "withdrawn"} == WITHDRAWN
    defined = str_enums()
    expected_names: set[str] = set()
    for row in rows:
        if row.number in WITHDRAWN:
            continue
        name = class_name(row.name)
        expected_names.add(name)
        assert name in defined, f"E-{row.number:02d} {row.name}: no StrEnum {name}"
        assert tuple(member.value for member in defined[name]) == row.values, name
        assert getattr(defined[name], "API_ONLY", False) is row.api_only, name
    assert set(defined) == expected_names
    assert [row.number for row in rows if row.api_only] == [*range(111, 125), 132]
    assert len(enums.AccountRole) == 33
    # 04 rev 1.72: MIGRATION_SSP_REPLAY; rev 1.142: EVIDENCE_SHRED (rulings R-49 (a), R-86)
    assert len(enums.ApprovalSubjectType) == 33
    assert len(enums.JobKind) == 27  # 04 rev 1.164: PERIOD_OPEN_REDIRTY (revision 0098)
    assert len(enums.NotificationKind) == 13
    # 04 rev 1.108 (revision 0092; ruling R-50 (b)): MFA_ENROLMENT_STARTED and
    # RECOVERY_CODES_REGENERATED; rev 1.189 (revision 0103; ruling R-111 (6)):
    # MFA_CHALLENGE_PASSED and MFA_PENDING_DENIED.
    assert len(enums.SecurityEventKind) == 20
    assert len(enums.ReasonCode) == 11


def test_engine_enums_equal_data_model() -> None:
    rows = {class_name(row.name): row for row in enumerations() if row.number not in WITHDRAWN}
    defined = str_enums(engine_enums)
    assert set(defined) <= set(rows), sorted(set(defined) - set(rows))
    assert {rows[name].number for name in defined} == ENGINE_ENUMERATIONS
    for name, strenum in defined.items():
        values = tuple(member.value for member in strenum)
        assert values == rows[name].values, name
        assert values == tuple(member.value for member in getattr(enums, name)), name
    assert sorted(engine_enums.__all__) == sorted(defined)
    assert len(engine_enums.AccountRole) == 33
    assert {"RETAINED_EARNINGS", "FINANCING_OBLIGATION"} <= set(engine_enums.AccountRole)
    assert set(engine_enums.RatableConvention) == {"DAILY", "MONTHLY_EVEN", "MID_MONTH"}
    assert set(engine_enums.Distinctness) == {"distinct", "nondistinct", "series"}
    assert set(engine_enums.RuleSetKind) == {
        "POB_ASSIGNMENT",
        "SSP_ASSIGNMENT",
        "APPROVAL_ROUTING",
        "AUTO_APPROVAL",
        "COMBINATION_DETECTION",
        "HOLD",
        "DATA_QUALITY",
    }


def test_dg_arc_09_catalogue_equals_t_plt_11() -> None:
    section = _between(data_model(), "\n### T-PLT-11 `permission`", "\n### T-PLT-12 ")
    rows: list[tuple[str, str, bool, bool, bool]] = []
    for line in section[section.index("Seeded catalogue") :].splitlines():
        if not line.startswith("| `"):
            continue
        code, area, *flags = _cells(line)
        assert all(flag in ("yes", "no") for flag in flags), line
        literal = re.fullmatch(r"`([a-z_]+(?:\.[a-z_]+)+)`", code)
        assert literal is not None, line
        approval, access_admin, mfa = (flag == "yes" for flag in flags)
        rows.append((literal.group(1), area, approval, access_admin, mfa))
    catalogue = [
        (p.code, p.area, p.is_approval, p.is_access_admin, p.requires_mfa) for p in CATALOGUE
    ]
    assert catalogue == rows
    assert len(CATALOGUE) == 52
    assert sum(p.is_approval for p in CATALOGUE) == 17
    assert sum(p.is_access_admin for p in CATALOGUE) == 6
    assert sum(p.requires_mfa for p in CATALOGUE) == 24
    for permission in CATALOGUE:
        assert re.fullmatch(r"^[a-z_]+(\.[a-z_]+)+$", permission.code)
        assert 1 <= len(permission.description) <= 400


def problem_catalogue() -> list[tuple[str, int, frozenset[str]]]:
    """04 §15.2 rows: slug, status and §14 codes, in catalogue order."""
    section = _between(data_model(), "\n### 15.2 Problem catalogue", "\n**Table 15.2-S")
    rows: list[tuple[str, int, frozenset[str]]] = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        slug, status, _raised_when, codes = _cells(line)
        literal = re.fullmatch(r"`([a-z0-9-]+)`", slug)
        assert literal is not None, line
        rows.append((literal.group(1), int(status), frozenset(_ERROR_CODE.findall(codes))))
    return rows


def error_codes_14_1() -> set[str]:
    section = _between(data_model(), "\n### 14.1 Invariants", "\n### 14.2 ")
    codes: set[str] = set()
    for line in section.splitlines():
        if line.startswith("| DB-"):
            codes |= set(_ERROR_CODE.findall(_cells(line)[3]))
    return codes


def err_titles() -> list[tuple[str, str, str]]:
    """PRD §5.5 ERR rows naming a slug: ERR id, slug and title."""
    text = PRD.read_text(encoding="utf-8")
    section = _between(text, "\n### 5.5 User-facing copy", "\n### 5.6 ")
    rows: list[tuple[str, str, str]] = []
    for line in section.splitlines():
        cells = _cells(line) if line.startswith("| ERR-") else []
        slug = re.match(r"^`([a-z0-9-]+)`", cells[1]) if cells else None
        if slug is not None:
            rows.append((cells[0], slug.group(1), cells[3]))
    return rows


def test_dg_arc_09_problems_equal_15_2() -> None:
    catalogue = problem_catalogue()
    # + release-validation-pending (D-96; PRD ERR-51) + lock-conflict (D-98 101c; PRD ERR-52)
    # + sync-objects-not-applied / connection-test-failed (SYNC-PROBLEM-SHAPE-1; 04 1.90; PRD
    # ERR-56 / ERR-57) + earlier-period-open (supervisor ruling R-6; 04 1.106; PRD ERR-65) = 52;
    # + statement-timeout (04 1.144; PRD ERR-66; ruling R-97 (6)) = 53.
    assert len(catalogue) == 53
    assert PROBLEMS["statement-timeout"].status == 503
    assert [(spec.slug, spec.status, spec.db_codes) for spec in PROBLEMS.values()] == catalogue
    assert all(slug == spec.slug for slug, spec in PROBLEMS.items())
    assert PROBLEMS["account-locked"].status == 423
    assert PROBLEMS["release-mismatch"].status == 503
    assert PROBLEMS["ledger-integrity"].status == 500
    # + EREV-JE-003 (04 DB-16 rev 1.205, revision 0104; supervisor ruling R-112 (b) (6)): a journal
    # line for a batch that is not draft.
    assert PROBLEMS["ledger-integrity"].db_codes == {
        "EREV-LED-002",
        "EREV-LED-005",
        "EREV-JE-002",
        "EREV-JE-003",
        "EREV-AUD-001",
    }
    titles = err_titles()
    for err_id, slug, title in titles:
        assert PROBLEMS[slug].title == title, err_id
    assert {slug for _, slug, _ in titles} == set(PROBLEMS)
    owners = Counter(code for spec in PROBLEMS.values() for code in spec.db_codes)
    assert set(owners) <= error_codes_14_1()
    assert all(count == 1 for count in owners.values())


def test_dg_arc_09_table_columns_match() -> None:
    names = {table.name for table in tables.metadata.sorted_tables}
    assert {"currency", "permission"} <= names
    for table in tables.metadata.sorted_tables:
        assert table.schema == "erev"
        assert list(table.columns.keys()) == table_columns(table.name), table.name


def test_dg_arc_09_every_database_enum_has_a_migration_type() -> None:
    """The reverse direction of DG-ARC-09, statically (slice 1b, Codex 0515): every database-
    candidate StrEnum has a ``CREATE TYPE`` in the committed revisions — replayed under the
    statement recorder, no database — or a D-98 66 reconciliation entry: ``PENDING_ENUM_TYPES`` (the
    later-phase table's item owes the type), ``TEXT_CHECK_ENUM_TYPES`` (E-04: text + CHECK by
    ruling) or ``VALUE_ONLY_ENUM_TYPES`` (E-82: no typed column). Shrink-only: an entry whose type
    has landed must be removed; every entry is a mirror and names its E-id, table, owning item and
    planned revision. Fail-first on the pre-1b tree: the six E-125 to E-130 mirrors had no type."""

    from support.enum_mirrors import (
        PENDING_ENUM_TYPES,
        RECONCILED_ENUM_TYPES,
        TEXT_CHECK_ENUM_TYPES,
        VALUE_ONLY_ENUM_TYPES,
        database_enums,
        migration_enum_types,
        type_gaps,
    )

    created = migration_enum_types()
    assert type_gaps(created) == []
    mirrors = database_enums()
    assert set(RECONCILED_ENUM_TYPES) <= set(mirrors)
    assert not set(RECONCILED_ENUM_TYPES) & set(created)
    assert len(created) + len(RECONCILED_ENUM_TYPES) == len(mirrors)
    assert set(TEXT_CHECK_ENUM_TYPES) == {"period_state"}
    assert set(VALUE_ONLY_ENUM_TYPES) == {"reporting_entity_type"}
    for name, entry in PENDING_ENUM_TYPES.items():
        assert entry.enumeration.startswith("E-") and entry.table.startswith("T-"), name
        assert entry.item and entry.revision.endswith(".py"), name
    for name in (
        "verification_outcome",
        "release_validation_status",
        "validation_attempt_status",
        "posting_attribution_cause",
        "validation_group_orchestration_state",
        "upgrade_processing_state",
    ):
        assert created[name].startswith("0055_"), (name, created.get(name))


def test_revision_0055_enum_literals_equal_the_mirrors() -> None:
    """Revision 0055's ``ENUM_TYPES`` literals are the 04 §3.4 labels of E-125 to E-130
    (the enums drift test already pins the StrEnums to 04)."""
    from support.enum_mirrors import VERSIONS_DIR, database_enums, load_revision

    (path,) = VERSIONS_DIR.glob("0055_*.py")
    module = load_revision(path)
    literals: dict[str, tuple[str, ...]] = module.ENUM_TYPES  # type: ignore[attr-defined]
    mirrors = database_enums()
    assert set(literals) == {
        "verification_outcome",
        "release_validation_status",
        "validation_attempt_status",
        "posting_attribution_cause",
        "validation_group_orchestration_state",
        "upgrade_processing_state",
    }
    for name, labels in literals.items():
        assert list(labels) == [member.value for member in mirrors[name]], name
