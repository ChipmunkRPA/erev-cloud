"""Parser and generator of ``erev_api.registry.policies`` (dev-guide §5.15, DG-KRN-REG-04).

``erev registry-seed`` parses the POLICIES.md §1 tables and the §5.0 register entries (columns ID,
Key, Question, Options, 606, IFRS, Parity, Levels, Pin, Appr) and writes ``policies.py``
deterministically; ``--check`` exits 1 when the committed module differs (DG-MK-registry-seed,
DG-LAY-07). Each row becomes one 04 T-PLT-31 ``registry_parameter`` row (catalogue rule 1).

Value schemas are JSON Schema objects. Decimal values are strings (04 API-C-06) with
``"format": "decimal"``; their bounds use the extension keywords ``x-minimum`` and ``x-maximum``,
because JSON Schema bounds apply to numbers only. Value shapes follow 04 T-PLT-32: an option is its
literal, a parameterised option is ``{option, <parameter>}``, a structured value is an object with
the members §1 names and a list value is an array. Cell rules (PROGRESS.md SPEC-Q-27):

- a cell that starts with a literal takes that literal; the text after it says when the engine
  departs from it (POLICIES §6.3 lists these literals as the preset values);
- ``FORCED`` alone takes the single option; ``same as 606`` and ``as 606`` copy the 606 cell;
- ``n/a`` and ``not applied`` give ``None``: the ASC606 default applies (T-PLT-31);
- a cell that states a rule instead of a value (``per assessment``, ``by VC type``,
  ``derived: …``) gives ``None``: there is no single framework default and the engine applies the
  rule;
- a literal outside the Options that a default or parity cell names (``NOT_ENFORCED``) is admitted
  through an ``anyOf`` branch of the schema.

Any other cell raises ``SeedError`` naming the POL id, so a new shape in the document stops the
generator instead of producing a silent default.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from erev_api.enums import RegistryCategory, RegistryScope

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
POLICIES_PATH: Final = REPO_ROOT / "docs" / "accounting" / "POLICIES.md"
MODULE_PATH: Final = Path(__file__).resolve().parent / "policies.py"

COLUMNS: Final = (
    "ID",
    "Key",
    "Question",
    "Options",
    "606",
    "IFRS",
    "Parity",
    "Levels",
    "Pin",
    "Appr",
)
CODE_PATTERN: Final = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")  # T-PLT-31 ck on `code`
DESCRIPTION_MAX: Final = 4000  # erev.memo

# POLICIES §0.5 level codes.
LEVEL_CODES: Final[Mapping[str, RegistryScope]] = {
    "T": RegistryScope.TENANT,
    "E": RegistryScope.ENTITY,
    "B": RegistryScope.BOOK,
    "P": RegistryScope.PRODUCT,
    "C": RegistryScope.CONTRACT,
    "O": RegistryScope.OBLIGATION,
}
# Levels outside §0.5: the value lives on the import or acquisition batch (T-PLT-31 rule 1).
BATCH_LEVELS: Final = frozenset({"import batch", "acquisition"})
# T-PLT-31 catalogue rule 1: categories.
PRACTICAL_EXPEDIENTS: Final = frozenset(
    {"POL-015", "POL-021", "POL-045", "POL-046", "POL-140"}
    | {"POL-197", "POL-198", "POL-199", "POL-200", "POL-202"}
)
# POLICIES §5.0: rows that "belong to the policy register (section 1)".
ADDITIONAL_REGISTER_HEADING: Final = "\n### 5.0 Additional register entries for the topics"
DISCLOSURE_SECTION: Final = "1.12"
NOT_DISCLOSURE_ELECTIONS: Final = frozenset(
    {"POL-197", "POL-198", "POL-199", "POL-200", "POL-201", "POL-202"}
)
# Cells that state a rule rather than a value.
RULE_PREFIXES: Final = ("per ", "by ", "derived:", "ALG-", "legacy database import")

_LITERAL: Final = r"`([A-Za-z][A-Za-z0-9_]*)`"
_NUMBER: Final = r"-?\d+(?:\.\d+)?"
_DECIMAL: Final = re.compile(rf"^{_NUMBER}$")
_INTEGER: Final = re.compile(r"^-?\d+$")
_FORCED: Final = re.compile(r"\s*\bFORCED\b")
_DECIMAL_SCHEMA: Final[Mapping[str, Any]] = {"type": "string", "format": "decimal"}


class SeedError(ValueError):
    """POLICIES §1 holds a row that cannot be mapped to a registry parameter."""


@dataclass(frozen=True, slots=True)
class PolicyRow:
    """One POL row of POLICIES §1 with the generator's columns."""

    section_number: str
    section: str
    pol_id: str
    key: str
    question: str
    options: str
    asc606: str
    ifrs: str
    parity: str
    levels: str
    pin: str
    appr: str


@dataclass(frozen=True, slots=True)
class SpecData:
    """The field values of one generated ``RegistryParameterSpec``."""

    code: str
    pol_id: str
    category: RegistryCategory
    value_schema: dict[str, Any]
    default_asc606: Any
    default_ifrs15: Any
    is_forced_asc606: bool
    is_forced_ifrs15: bool
    legacy_parity_value: Any
    allowed_levels: tuple[RegistryScope, ...]
    pin: str
    approval_code: str
    description: str
    source_ref: str
    section: str


ShapeKind = Literal["literals", "integer", "decimal", "books", "object", "ordered_list", "months"]


@dataclass(frozen=True, slots=True)
class _Shape:
    kind: ShapeKind
    schema: dict[str, Any]
    literals: tuple[str, ...] = ()
    members: tuple[tuple[str, dict[str, Any]], ...] = ()


@dataclass(frozen=True, slots=True)
class _Cell:
    value: Any
    forced: bool = False
    extra: str | None = None
    named: frozenset[str] = field(default_factory=frozenset)


# --- document parsing -----------------------------------------------------------------------


def _cells(line: str) -> list[str]:
    parts = re.split(r"(?<!\\)\|", line.strip())
    return [part.strip().replace("\\|", "|") for part in parts[1:-1]]


def parse_rows(text: str) -> list[PolicyRow]:
    """The POL rows of §1.1 to §1.14, then of §5.0, in document order.

    §5.0 "Additional register entries for the topics" holds rows that belong to the §1 register
    (POL-240 to POL-246). Other tables (1.4-A) are skipped.
    """
    start = text.find("\n## 1. Policy register")
    end = text.find("\n## 2. ", start + 1)
    if start < 0 or end < 0:
        raise SeedError("POLICIES.md has no section 1 policy register")
    extra_start = text.find(ADDITIONAL_REGISTER_HEADING)
    extra_end = text.find("\n### 5.1 ", extra_start + 1)
    if extra_start < 0 or extra_end < 0:
        raise SeedError("POLICIES.md has no section 5.0 register entries")
    rows: list[PolicyRow] = []
    number: str | None = None
    title: str | None = None
    header: list[str] | None = None
    for line in (text[start:end] + text[extra_start:extra_end]).splitlines():
        heading = re.fullmatch(r"### (1\.\d+|5\.0) (.+)", line)
        if heading is not None:
            number, title = heading.group(1), heading.group(2).strip()
            header = None
            continue
        if not line.startswith("|"):
            header = None
            continue
        cells = _cells(line)
        if header is None:
            header = cells
            continue
        if set("".join(cells)) <= set("-: ") or not set(COLUMNS) <= set(header):
            continue
        if len(cells) != len(header):
            raise SeedError(
                f"row {cells[0]!r} has {len(cells)} cells; the header has {len(header)}"
            )
        if number is None or title is None:
            raise SeedError("a policy table precedes the first §1 subsection")
        value = dict(zip(header, cells, strict=True))
        if not re.fullmatch(r"POL-\d{3}", value["ID"]):
            raise SeedError(f"invalid POL id {value['ID']!r}")
        key = re.fullmatch(r"`([^`]+)`", value["Key"])
        if key is None or not CODE_PATTERN.fullmatch(key.group(1)):
            raise SeedError(f"{value['ID']}: invalid key {value['Key']!r}")
        rows.append(
            PolicyRow(
                section_number=number,
                section=title,
                pol_id=value["ID"],
                key=key.group(1),
                question=value["Question"],
                options=value["Options"],
                asc606=value["606"],
                ifrs=value["IFRS"],
                parity=value["Parity"],
                levels=value["Levels"],
                pin=value["Pin"],
                appr=value["Appr"],
            )
        )
    return rows


def _strip_remarks(text: str) -> str:
    """Remove parenthesised remarks and collapse whitespace."""
    kept: list[str] = []
    depth = 0
    for character in text:
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(depth - 1, 0)
        elif depth == 0:
            kept.append(character)
    return re.sub(r"\s+", " ", "".join(kept)).strip()


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for character in text:
        if character in "({":
            depth += 1
        elif character in ")}":
            depth -= 1
        if character == separator and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    parts.append("".join(current).strip())
    return parts


def _literal_list(pol_id: str, text: str) -> tuple[str, ...]:
    literals = tuple(re.findall(_LITERAL, text))
    if not literals or ", ".join(f"`{literal}`" for literal in literals) != text:
        raise SeedError(f"{pol_id}: invalid literal list {text!r}")
    return literals


def _enum_schema(literals: Sequence[str]) -> dict[str, Any]:
    return {"type": "string", "enum": list(literals)}


def _member(pol_id: str, segment: str) -> tuple[str, dict[str, Any]]:
    decimal = re.fullmatch(r"`([a-z_]+)` decimal", segment)
    if decimal is not None:
        return decimal.group(1), dict(_DECIMAL_SCHEMA)
    enum = re.fullmatch(r"`([a-z_]+)` ∈ \{(.+)\}", segment)
    if enum is not None:
        return enum.group(1), _enum_schema(_literal_list(pol_id, enum.group(2)))
    raise SeedError(f"{pol_id}: invalid structured member {segment!r}")


def _options_shape(pol_id: str, cell: str) -> _Shape:
    core = _strip_remarks(cell)
    if match := re.fullmatch(r"integer (-?\d+) to (-?\d+)", core):
        minimum, maximum = int(match.group(1)), int(match.group(2))
        return _Shape("integer", {"type": "integer", "minimum": minimum, "maximum": maximum})
    if match := re.fullmatch(rf"decimal ({_NUMBER}) to ({_NUMBER})", core):
        schema = {**_DECIMAL_SCHEMA, "x-minimum": match.group(1), "x-maximum": match.group(2)}
        return _Shape("decimal", schema)
    if match := re.fullmatch(rf"decimal ≥ ({_NUMBER})", core):
        return _Shape("decimal", {**_DECIMAL_SCHEMA, "x-minimum": match.group(1)})
    if match := re.fullmatch(r"set ⊆ \{(.+)\}; `primary` ∈ set", core):
        books = _enum_schema(_literal_list(pol_id, match.group(1)))
        schema = {
            "type": "object",
            "properties": {
                "set": {"type": "array", "items": books, "minItems": 1, "uniqueItems": True},
                "primary": books,
            },
            "required": ["set", "primary"],
            "additionalProperties": False,
        }
        return _Shape("books", schema, literals=tuple(books["enum"]))
    if match := re.fullmatch(r"Value `\{([a-z_]+(?:, [a-z_]+)*)\}`: (.+)", core):
        members = tuple(
            _member(pol_id, segment) for segment in _split_top_level(match.group(2), ";")
        )
        if [name for name, _ in members] != match.group(1).split(", "):
            raise SeedError(f"{pol_id}: structured members differ from {match.group(1)!r}")
        return _Shape("object", {}, members=members)
    if re.fullmatch(r"`[a-z_]+` (decimal|∈ \{.+\})(; `[a-z_]+` (decimal|∈ \{.+\}))*", core):
        members = tuple(_member(pol_id, segment) for segment in _split_top_level(core, ";"))
        return _Shape("object", {}, members=members)
    if re.fullmatch(r"`[a-z_]+`( → `[a-z_]+`)+", core):
        literals = tuple(re.findall(_LITERAL, core))
        schema = {"type": "array", "items": _enum_schema(literals), "uniqueItems": True}
        return _Shape("ordered_list", schema, literals=literals)
    if core == "ordered list of month boundaries":
        schema = {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
            "minItems": 1,
            "uniqueItems": True,
            "x-ordered": "ascending",
        }
        return _Shape("months", schema)
    return _literal_options(pol_id, cell)


def _literal_options(pol_id: str, cell: str) -> _Shape:
    literals: list[str] = []
    parameterised: list[dict[str, Any]] = []
    for item in _split_top_level(cell, ","):
        match = re.fullmatch(rf"{_LITERAL}(?: \((.+)\))?", item)
        if match is None:
            raise SeedError(f"{pol_id}: unrecognised Options cell {cell!r}")
        literal, remark = match.group(1), match.group(2)
        literals.append(literal)
        if remark is None or not remark.startswith("parameter "):
            continue
        parameter = re.fullmatch(
            rf"parameter `([a-z_]+)`, default ({_NUMBER})(?:, maximum ({_NUMBER}))?", remark
        )
        if parameter is None:
            raise SeedError(f"{pol_id}: invalid option parameter {remark!r}")
        name, default, maximum = parameter.groups()
        parameter_schema: dict[str, Any] = {**_DECIMAL_SCHEMA, "default": default}
        if maximum is not None:
            parameter_schema["x-maximum"] = maximum
        parameterised.append(
            {
                "type": "object",
                "properties": {"option": {"const": literal}, name: parameter_schema},
                "required": ["option"],
                "additionalProperties": False,
            }
        )
    plain = _enum_schema(literals)
    schema = {"anyOf": [plain, *parameterised]} if parameterised else plain
    return _Shape("literals", schema, literals=tuple(literals))


def _object_value(shape: _Shape, pol_id: str, column: str, core: str) -> _Cell:
    names = [name for name, _ in shape.members]
    schemas = dict(shape.members)
    value: dict[str, Any] = {}
    named: set[str] = set()
    for index, segment in enumerate(_split_top_level(core, ";")):
        tokens = re.findall(_LITERAL, segment)
        if len(tokens) == 2 and segment == f"`{tokens[0]}` `{tokens[1]}`" and tokens[0] in names:
            member, literal = tokens
            if literal not in schemas[member].get("enum", ()):
                raise SeedError(f"{pol_id}: {column} member {member} has no literal {literal}")
            value[member] = literal
            named.add(member)
        elif _DECIMAL.fullmatch(segment) and index < len(names):
            if schemas[names[index]].get("format") != "decimal":
                raise SeedError(f"{pol_id}: {column} member {names[index]} is not a decimal")
            value[names[index]] = segment
        elif len(tokens) == 1:
            owners = [name for name in names if tokens[0] in schemas[name].get("enum", ())]
            if len(owners) != 1:
                raise SeedError(f"{pol_id}: {column} literal {tokens[0]} names no single member")
            # A second literal for the same member is a conditional alternative (POL-047).
            value.setdefault(owners[0], tokens[0])
        else:
            raise SeedError(f"{pol_id}: unrecognised {column} segment {segment!r}")
    ordered = {name: value[name] for name in names if name in value}
    return _Cell(ordered, named=frozenset(named))


def _cell(shape: _Shape, pol_id: str, column: str, cell: str) -> _Cell:
    core = _strip_remarks(cell)
    forced = _FORCED.search(core) is not None
    core = _FORCED.sub("", core).strip()
    if core.startswith(("n/a", "not applied")):
        return _Cell(None, forced)
    if not core:
        if shape.kind == "literals" and len(shape.literals) == 1:
            return _Cell(shape.literals[0], forced)
        if shape.kind == "ordered_list":
            return _Cell(list(shape.literals), forced)
        raise SeedError(f"{pol_id}: {column} is FORCED without a single option")
    single = re.fullmatch(_LITERAL, core)
    if shape.kind == "books":
        match = re.fullmatch(rf"\{{(.+)\}}, primary {_LITERAL}", core)
        if match is None:
            raise SeedError(f"{pol_id}: unrecognised {column} cell {cell!r}")
        books = list(_literal_list(pol_id, match.group(1)))
        primary = match.group(2)
        if not set(books) <= set(shape.literals) or primary not in books:
            raise SeedError(f"{pol_id}: {column} names books outside the options")
        return _Cell({"set": books, "primary": primary}, forced)
    if shape.kind == "object":
        if single is not None:
            return _Cell(single.group(1), forced, extra=single.group(1))
        object_cell = _object_value(shape, pol_id, column, core)
        return _Cell(object_cell.value, forced, named=object_cell.named)
    if shape.kind == "integer" and _INTEGER.fullmatch(core):
        return _Cell(int(core), forced)
    if shape.kind == "decimal" and _DECIMAL.fullmatch(core):
        return _Cell(core, forced)
    if shape.kind == "months" and (match := re.match(r"\[(\d+(?:, \d+)*)\]", core)):
        return _Cell([int(month) for month in match.group(1).split(", ")], forced)
    leading = re.match(_LITERAL, core)
    if leading is not None:
        literal = leading.group(1)
        if shape.kind == "literals" and literal in shape.literals:
            return _Cell(literal, forced)
        return _Cell(literal, forced, extra=literal)
    if core.startswith(RULE_PREFIXES):
        return _Cell(None, forced)
    raise SeedError(f"{pol_id}: unrecognised {column} cell {cell!r}")


def _same_as_606(cell: str) -> bool:
    return _strip_remarks(cell) in ("same as 606", "as 606")


def _levels(pol_id: str, cell: str) -> tuple[RegistryScope, ...]:
    core = _strip_remarks(cell)
    if core in BATCH_LEVELS:
        return ()
    codes = [part.strip().removeprefix("override ").strip() for part in re.split(r"[,;]", core)]
    if any(code not in LEVEL_CODES for code in codes) or len(set(codes)) != len(codes):
        raise SeedError(f"{pol_id}: unrecognised Levels cell {cell!r}")
    scopes = {LEVEL_CODES[code] for code in codes}
    return tuple(scope for scope in RegistryScope if scope in scopes)


def _category(row: PolicyRow) -> RegistryCategory:
    if row.pol_id in PRACTICAL_EXPEDIENTS:
        return RegistryCategory.PRACTICAL_EXPEDIENT
    if row.section_number == DISCLOSURE_SECTION and row.pol_id not in NOT_DISCLOSURE_ELECTIONS:
        return RegistryCategory.DISCLOSURE_ELECTION
    return RegistryCategory.ACCOUNTING_POLICY


def _final_schema(shape: _Shape, default: _Cell, extras: Sequence[str]) -> dict[str, Any]:
    schema = shape.schema
    if shape.kind == "object":
        properties: dict[str, Any] = {}
        for name, member in shape.members:
            properties[name] = (
                {**member, "default": default.value[name]} if name in default.named else member
            )
        schema = {
            "type": "object",
            "properties": properties,
            "required": [name for name, _ in shape.members if name not in default.named],
            "additionalProperties": False,
        }
    if not extras:
        return schema
    branch = _enum_schema(extras)
    return (
        {"anyOf": [*schema["anyOf"], branch]} if "anyOf" in schema else {"anyOf": [schema, branch]}
    )


def build_spec(row: PolicyRow) -> SpecData:
    shape = _options_shape(row.pol_id, row.options)
    asc606 = _cell(shape, row.pol_id, "606", row.asc606)
    ifrs = asc606 if _same_as_606(row.ifrs) else _cell(shape, row.pol_id, "IFRS", row.ifrs)
    parity = asc606 if _same_as_606(row.parity) else _cell(shape, row.pol_id, "Parity", row.parity)
    extras = list(dict.fromkeys(c.extra for c in (asc606, ifrs, parity) if c.extra is not None))
    pin = re.match(r"([KP])\b", row.pin)
    appr = re.match(r"(CFG|OVR|EST|JDG|FIX)\b", row.appr)
    if pin is None or appr is None:
        raise SeedError(f"{row.pol_id}: invalid Pin {row.pin!r} or Appr {row.appr!r}")
    if not 1 <= len(row.question) <= DESCRIPTION_MAX:
        raise SeedError(f"{row.pol_id}: the question must hold 1 to {DESCRIPTION_MAX} characters")
    return SpecData(
        code=row.key,
        pol_id=row.pol_id,
        category=_category(row),
        value_schema=_final_schema(shape, asc606, extras),
        default_asc606=asc606.value,
        default_ifrs15=ifrs.value,
        is_forced_asc606=asc606.forced,
        is_forced_ifrs15=ifrs.forced,
        legacy_parity_value=parity.value,
        allowed_levels=_levels(row.pol_id, row.levels),
        pin=pin.group(1),
        approval_code=appr.group(1),
        description=row.question,
        source_ref=row.pol_id,
        section=row.section,
    )


def build_specs(text: str) -> list[SpecData]:
    specs = [build_spec(row) for row in parse_rows(text)]
    for attribute in ("code", "pol_id"):
        values = [getattr(spec, attribute) for spec in specs]
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise SeedError(f"duplicate {attribute} values: {', '.join(duplicates)}")
    return specs


# --- module rendering -----------------------------------------------------------------------

_MODULE_HEADER: Final = '''\
"""Policy registry parameters: POLICIES.md §1 and §5.0 rows as 04 T-PLT-31 specs (dev-guide §5.15).

Generated from ``docs/accounting/POLICIES.md`` by ``erev registry-seed`` (``registry.seed``).
Never edit by hand: ``make registry-seed CHECK=1`` fails when this file is stale
(DG-KRN-REG-04, DG-LAY-07). ``None`` in ``default_asc606`` means there is no single framework
default and the engine applies the rule the §1 cell states; ``None`` in ``default_ifrs15`` or
``legacy_parity_value`` means the ASC606 default applies.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal

from erev_api.enums import RegistryCategory, RegistryScope


@dataclass(frozen=True, slots=True)
class RegistryParameterSpec:
    """One ``registry_parameter`` row (04 T-PLT-31)."""

    code: str
    pol_id: str | None
    category: RegistryCategory
    value_schema: Mapping[str, Any]
    default_asc606: Any
    default_ifrs15: Any | None
    is_forced_asc606: bool
    is_forced_ifrs15: bool
    legacy_parity_value: Any | None
    allowed_levels: frozenset[RegistryScope]
    pin: Literal["K", "P"]
    approval_code: Literal["CFG", "OVR", "EST", "JDG", "FIX"]
    description: str
    source_ref: str
    section: str


'''


def _py_str(text: str) -> str:
    escaped = text.replace("\\", "\\\\")
    if '"' in text and "'" not in text:
        return "'" + escaped + "'"
    return '"' + escaped.replace('"', '\\"') + '"'


def _py(value: Any, indent: int) -> str:
    inner = " " * (indent + 4)
    if value is None or isinstance(value, bool):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _py_str(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        items = "".join(f"{inner}{_py(item, indent + 4)},\n" for item in value)
        return "[\n" + items + " " * indent + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = "".join(
            f"{inner}{_py_str(key)}: {_py(item, indent + 4)},\n" for key, item in value.items()
        )
        return "{\n" + items + " " * indent + "}"
    raise TypeError(f"unsupported value type {type(value).__name__}")


def _py_levels(levels: Sequence[RegistryScope], indent: int) -> str:
    if not levels:
        return "frozenset()"
    pad = " " * indent
    members = "".join(f"{pad}        RegistryScope.{scope.name},\n" for scope in levels)
    return f"frozenset(\n{pad}    {{\n{members}{pad}    }}\n{pad})"


def _render_spec(spec: SpecData) -> str:
    indent = 8
    fields = (
        ("code", _py_str(spec.code)),
        ("pol_id", _py_str(spec.pol_id)),
        ("category", f"RegistryCategory.{spec.category.name}"),
        ("value_schema", _py(spec.value_schema, indent)),
        ("default_asc606", _py(spec.default_asc606, indent)),
        ("default_ifrs15", _py(spec.default_ifrs15, indent)),
        ("is_forced_asc606", repr(spec.is_forced_asc606)),
        ("is_forced_ifrs15", repr(spec.is_forced_ifrs15)),
        ("legacy_parity_value", _py(spec.legacy_parity_value, indent)),
        ("allowed_levels", _py_levels(spec.allowed_levels, indent)),
        ("pin", _py_str(spec.pin)),
        ("approval_code", _py_str(spec.approval_code)),
        ("description", _py_str(spec.description)),
        ("source_ref", _py_str(spec.source_ref)),
        ("section", _py_str(spec.section)),
    )
    body = "".join(f"        {name}={rendered},\n" for name, rendered in fields)
    return f"    RegistryParameterSpec(\n{body}    ),\n"


def render_module(specs: Sequence[SpecData]) -> str:
    rows = "".join(_render_spec(spec) for spec in specs)
    return (
        _MODULE_HEADER
        + "_SPECS: Final[tuple[RegistryParameterSpec, ...]] = (\n"
        + rows
        + ")\n"
        + "# POLICIES.md §1 and §5.0, one spec per non-retired POL row, keyed by code.\n"
        + "POLICY_PARAMETERS: Final[Mapping[str, RegistryParameterSpec]] = MappingProxyType(\n"
        + "    {spec.code: spec for spec in _SPECS}\n"
        + ")\n"
    )


def generate(policies_path: Path = POLICIES_PATH) -> str:
    return render_module(build_specs(policies_path.read_text(encoding="utf-8")))


def write_module(policies_path: Path = POLICIES_PATH, module_path: Path = MODULE_PATH) -> Path:
    module_path.parent.mkdir(parents=True, exist_ok=True)
    with module_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(generate(policies_path))
    return module_path


def is_current(policies_path: Path = POLICIES_PATH, module_path: Path = MODULE_PATH) -> bool:
    """True when ``module_path`` equals a fresh generation byte for byte (``--check``)."""
    if not module_path.is_file():
        return False
    return module_path.read_bytes() == generate(policies_path).encode("utf-8")
