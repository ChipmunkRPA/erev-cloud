"""Registry version validation and the TESTED transition (dev-guide §5.15 DG-KRN-REG-06; 04
T-PLT-32; POLICIES §0.5 rule 1).

``validation_problem`` checks a version's values: each code exists in the version's category, its
``allowed_levels`` contain the version's scope, a forced value is never set, and the value
validates against ``value_schema``. ``schema_errors`` implements the JSON Schema subset the
catalogue uses and raises ``ValueError`` on any other keyword, so an unsupported schema fails
closed instead of accepting a value. ``mark_tested`` runs the checks before DRAFT → TESTED.

The whole value set (04 T-PLT-32 "Whole value set", rev 1.183; supervisor ruling R-117 (b)). A
version past TESTED holds the whole value set of its category at its scope key. A DRAFT or TESTED
version holds its author's statement instead: the values it states, and as JSON ``null`` members
the codes it returns to the next level (``unset``; ``draft_values``). ``whole_set`` overlays the
statement on the values of the predecessor — the PUBLISHED version of the scope key
(``published_of_key``) — and ``difference`` names what the result changes, adds and returns to the
default. ``whole_content`` is the one content of a version: the hash of its tests, of its row and
of its approval request (``approvals.subjects.registry_version_content``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select, update

from erev_api.db.tables.platform import registry_version
from erev_api.enums import BookCode, ConfigStatus, RegistryCategory, RegistryScope
from erev_api.problems import Problem, ProblemError
from erev_api.registry.policies import RegistryParameterSpec
from erev_api.registry.resolve import PARAMETERS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.uow import UnitOfWork

# 04 T-PLT-32 `scope`: PRODUCT, CONTRACT and OBLIGATION values live outside registry versions.
VERSION_SCOPES: Final = frozenset({RegistryScope.TENANT, RegistryScope.ENTITY, RegistryScope.BOOK})
POLICY_LEVEL_NOT_ALLOWED: Final = "POLICY_LEVEL_NOT_ALLOWED"  # 04 §15.4
POLICY_VALUE_INVALID: Final = "POLICY_VALUE_INVALID"  # 04 §15.4
OBJECT_TYPE: Final = "registry_version"
TEST_ACTION: Final = "registry_version.test"
DEFAULT_PRESET: Final = "DEFAULT"  # T-PLT-32 `preset_code`
# 04 §16.5 API-S-Policy `basis` (a request member) and `diff_against_current[].change`.
BASIS_PREDECESSOR: Final = "PREDECESSOR"
BASIS_DEFAULTS: Final = "DEFAULTS"
CHANGED: Final = "CHANGED"
ADDED: Final = "ADDED"
RETURNED_TO_DEFAULT: Final = "RETURNED_TO_DEFAULT"
# A version in one of these statuses holds its author's statement, not yet the whole set.
STATEMENT_STATUSES: Final = frozenset({ConfigStatus.DRAFT.value, ConfigStatus.TESTED.value})
# The predecessor of a version in one of these statuses is the PUBLISHED version of its key; a
# version past them names the version it superseded (SC-V `supersedes_version_id`).
OPEN_STATUSES: Final = frozenset(
    {
        ConfigStatus.DRAFT.value,
        ConfigStatus.TESTED.value,
        ConfigStatus.SUBMITTED.value,
        ConfigStatus.APPROVED.value,
    }
)

_KEYWORDS: Final = frozenset(
    {
        "type",
        "enum",
        "const",
        "default",
        "minimum",
        "maximum",
        "minLength",
        "format",
        "x-minimum",
        "x-maximum",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "x-ordered",
        "properties",
        "required",
        "additionalProperties",
        "anyOf",
    }
)
_DECIMAL: Final = re.compile(r"-?[0-9]+(\.[0-9]+)?")  # ASCII digits only (D-78)


def content_sha256(
    *,
    category: RegistryCategory,
    scope: RegistryScope,
    book_code: BookCode | None,
    entity_id: UUID | None,
    values: Mapping[str, Any],
) -> str:
    """The DB-04 content hash of a version: its scope key and values (SPEC-Q-178)."""
    return sha256_hex(
        {
            "category": category.value,
            "scope": scope.value,
            "book_code": None if book_code is None else book_code.value,
            "entity_id": None if entity_id is None else str(entity_id),
            "values": dict(values),
        }
    )


def _same(value: Any, literal: Any) -> bool:
    """JSON equality: ``True`` never equals ``1``."""
    return type(value) is type(literal) and bool(value == literal)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _type_matches(expected: str, value: Any) -> bool:
    checks = {
        "string": lambda: isinstance(value, str),
        "integer": lambda: _is_integer(value),
        "boolean": lambda: isinstance(value, bool),
        "array": lambda: isinstance(value, list),
        "object": lambda: isinstance(value, Mapping),
    }
    if expected not in checks:
        raise ValueError(f"unsupported value_schema type {expected!r}")
    return checks[expected]()


def _string_errors(schema: Mapping[str, Any], value: str, path: str) -> list[str]:
    errors: list[str] = []
    if len(value) < schema.get("minLength", 0):
        errors.append(f"{path} must have at least {schema['minLength']} characters")
    form = schema.get("format")
    if form is None:
        return errors
    if form != "decimal":
        raise ValueError(f"unsupported value_schema format {form!r}")
    if not _DECIMAL.fullmatch(value):
        return [*errors, f"{path} must be a decimal string"]
    if "x-minimum" in schema and Decimal(value) < Decimal(schema["x-minimum"]):
        errors.append(f"{path} must be at least {schema['x-minimum']}")
    if "x-maximum" in schema and Decimal(value) > Decimal(schema["x-maximum"]):
        errors.append(f"{path} must be at most {schema['x-maximum']}")
    return errors


def _array_errors(schema: Mapping[str, Any], value: list[Any], path: str) -> list[str]:
    errors: list[str] = []
    if len(value) < schema.get("minItems", 0):
        errors.append(f"{path} must hold at least {schema['minItems']} items")
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        errors.append(f"{path} must hold at most {schema['maxItems']} items")
    if schema.get("uniqueItems"):
        encoded = [json.dumps(item, sort_keys=True) for item in value]
        if len(set(encoded)) != len(encoded):
            errors.append(f"{path} must not repeat items")
    if "items" in schema:
        for index, item in enumerate(value):
            errors += schema_errors(schema["items"], item, f"{path}[{index}]")
    ordering = schema.get("x-ordered")
    if ordering is not None:
        if ordering != "ascending":
            raise ValueError(f"unsupported value_schema x-ordered {ordering!r}")
        if all(_is_integer(item) for item in value) and any(b <= a for a, b in pairwise(value)):
            errors.append(f"{path} must be in ascending order")
    return errors


def _object_errors(schema: Mapping[str, Any], value: Mapping[str, Any], path: str) -> list[str]:
    errors = [
        f"{path}.{name} is required" for name in schema.get("required", ()) if name not in value
    ]
    properties: Mapping[str, Any] = schema.get("properties", {})
    for name, subschema in properties.items():
        if name in value:
            errors += schema_errors(subschema, value[name], f"{path}.{name}")
    additional = schema.get("additionalProperties", True)
    if additional is not True and additional is not False:
        raise ValueError("value_schema additionalProperties must be a boolean")
    if additional is False:
        errors += [f"{path}.{name} is not allowed" for name in sorted(set(value) - set(properties))]
    return errors


def schema_errors(schema: Mapping[str, Any], value: Any, path: str = "value") -> list[str]:
    """Messages describing how ``value`` fails ``schema``; empty when it validates."""
    unsupported = sorted(set(schema) - _KEYWORDS)
    if unsupported:
        raise ValueError(f"unsupported value_schema keywords {unsupported}")
    errors: list[str] = []
    if "anyOf" in schema and all(schema_errors(option, value, path) for option in schema["anyOf"]):
        errors.append(f"{path} matches none of the allowed shapes")
    expected = schema.get("type")
    if expected is not None and not _type_matches(expected, value):
        return [*errors, f"{path} must be of type {expected}"]
    if "const" in schema and not _same(value, schema["const"]):
        errors.append(f"{path} must be {schema['const']}")
    if "enum" in schema and not any(_same(value, literal) for literal in schema["enum"]):
        errors.append(f"{path} must be one of {', '.join(str(item) for item in schema['enum'])}")
    if _is_integer(value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path} must be at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path} must be at most {schema['maximum']}")
    if isinstance(value, str):
        errors += _string_errors(schema, value, path)
    if isinstance(value, list):
        errors += _array_errors(schema, value, path)
    if isinstance(value, Mapping):
        errors += _object_errors(schema, value, path)
    return errors


def _forced_at(
    spec: RegistryParameterSpec, scope: RegistryScope, book_code: BookCode | None
) -> bool:
    """[J] SPEC-Q-178: a BOOK version may not set a value forced for its book; a TENANT or ENTITY
    version, which serves every book, may not set a value forced in both frameworks."""
    if scope is RegistryScope.BOOK and book_code is not None:
        return spec.is_forced_ifrs15 if book_code is BookCode.IFRS15 else spec.is_forced_asc606
    return spec.is_forced_asc606 and spec.is_forced_ifrs15


def validation_problem(
    *,
    category: RegistryCategory,
    scope: RegistryScope,
    book_code: BookCode | None,
    values: Mapping[str, Any],
) -> Problem | None:
    """The DG-KRN-REG-06 problem of a version's values, or None.

    Level errors (422 ``policy-level-not-allowed``) take precedence over value errors (422
    ``validation-failed`` with ``rule_id`` ``POLICY_VALUE_INVALID``); each lists one error per
    failing code, in code order (SPEC-Q-178).
    """
    if scope not in VERSION_SCOPES:
        raise ValueError(f"registry versions have no {scope.value} scope (T-PLT-32)")
    levels: list[ProblemError] = []
    invalid: list[ProblemError] = []
    for code in sorted(values):
        field = f"values.{code}"
        spec = PARAMETERS.get(code)
        if spec is None or spec.category is not category:
            message = f"Use a parameter of category {category.value}."
            invalid.append(ProblemError(field=field, rule_id=POLICY_VALUE_INVALID, message=message))
        elif scope not in spec.allowed_levels:
            message = f"This parameter cannot be set at {scope.value} level."
            levels.append(
                ProblemError(field=field, rule_id=POLICY_LEVEL_NOT_ALLOWED, message=message)
            )
        elif _forced_at(spec, scope, book_code):
            message = "The framework fixes this value."
            invalid.append(ProblemError(field=field, rule_id=POLICY_VALUE_INVALID, message=message))
        elif messages := schema_errors(spec.value_schema, values[code], field):
            message = messages[0][:1].upper() + messages[0][1:] + "."
            invalid.append(ProblemError(field=field, rule_id=POLICY_VALUE_INVALID, message=message))
    if levels:
        return Problem("policy-level-not-allowed", errors=levels)
    if invalid:
        return Problem("validation-failed", errors=invalid)
    return None


def mark_tested(
    uow: UnitOfWork, version_id: UUID, *, test_evidence: Mapping[str, Any] | None = None
) -> str:
    """DRAFT → TESTED for a version whose values validate; returns its content hash.

    A refusal raises before any write. [J] SPEC-Q-178: the transition audits
    ``registry_version.test``; example cases (T-REF-27) are not required until the configuration
    commands of RFD define them.
    """
    session = uow.session
    principal = uow.principal
    row = (
        session.execute(
            select(registry_version)
            .where(
                registry_version.c.tenant_id == principal.tenant_id,
                registry_version.c.id == version_id,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    if row["status"] != ConfigStatus.DRAFT.value:
        raise Problem("invalid-transition", f"A {row['status']} version cannot be tested.")
    category = RegistryCategory(row["category"])
    scope = RegistryScope(row["scope"])
    book_code = None if row["book_code"] is None else BookCode(row["book_code"])
    values: Mapping[str, Any] = row["values"]
    problem = validation_problem(category=category, scope=scope, book_code=book_code, values=values)
    if problem is not None:
        raise problem
    digest = content_sha256(
        category=category,
        scope=scope,
        book_code=book_code,
        entity_id=row["entity_id"],
        values=values,
    )
    session.execute(
        update(registry_version)
        .where(
            registry_version.c.tenant_id == principal.tenant_id,
            registry_version.c.id == version_id,
        )
        .values(
            status=ConfigStatus.TESTED.value,
            content_sha256=digest,
            test_evidence=None if test_evidence is None else dict(test_evidence),
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=TEST_ACTION,
        object_type=OBJECT_TYPE,
        object_id=version_id,
        before={"status": ConfigStatus.DRAFT.value},
        after={"status": ConfigStatus.TESTED.value, "content_sha256": digest},
    )
    return digest


# --- the whole value set (04 T-PLT-32 "Whole value set"; supervisor ruling R-117 (b)) -------------


def stated_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """The values a statement states: its members that are not JSON ``null``, in code order."""
    return {code: values[code] for code in sorted(values) if values[code] is not None}


def unset_codes(values: Mapping[str, Any]) -> list[str]:
    """The codes a statement returns to the next level: its JSON ``null`` members, in order."""
    return sorted(code for code, value in values.items() if value is None)


def draft_values(values: Mapping[str, Any], unset: Iterable[str]) -> dict[str, Any]:
    """The ``values`` column of a DRAFT or TESTED version: the stated values, and ``null`` for
    every code of ``unset``."""
    return {**dict(values), **dict.fromkeys(unset)}


def whole_set(predecessor: Mapping[str, Any] | None, values: Mapping[str, Any]) -> dict[str, Any]:
    """The whole value set of a statement: the predecessor's values overlaid with the stated
    ones, less the codes the statement returns to the next level; in code order."""
    whole = dict(predecessor or {})
    for code, value in values.items():
        if value is None:
            whole.pop(code, None)
        else:
            whole[code] = value
    return dict(sorted(whole.items()))


def _json_equal(before: Any, after: Any) -> bool:
    """JSON equality: ``True`` never equals ``1``."""
    return json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)


def difference(
    predecessor: Mapping[str, Any] | None, whole: Mapping[str, Any]
) -> dict[str, list[str]]:
    """What a whole value set does to its predecessor's, by code: the values it changes, the ones
    it adds, and the ones it returns to the default — to the next level of the resolution for an
    ENTITY or BOOK version (POLICIES §0.5 rule 2)."""
    before = predecessor or {}
    return {
        "changed": sorted(
            code for code in whole if code in before and not _json_equal(before[code], whole[code])
        ),
        "added": sorted(code for code in whole if code not in before),
        "returned_to_default": sorted(code for code in before if code not in whole),
    }


def _predecessor_columns() -> tuple[Any, ...]:
    table = registry_version
    return (
        table.c.id,
        table.c.version_no,
        table.c["values"],
        table.c.preset_code,
        table.c.effective_from,
        table.c.published_at,
    )


def published_of_key(
    session: Session,
    *,
    category: str,
    scope: str,
    book_code: str | None,
    entity_id: UUID | None,
    other_than: UUID | None = None,
    for_update: bool = False,
) -> Mapping[str, Any] | None:
    """The PUBLISHED version of a scope key (DB-04 keeps one at most), other than ``other_than``:
    the predecessor of every open version of the key."""
    table = registry_version
    query = select(*_predecessor_columns()).where(
        table.c.category == category,
        table.c.scope == scope,
        table.c.book_code.is_(None) if book_code is None else table.c.book_code == book_code,
        table.c.entity_id.is_(None) if entity_id is None else table.c.entity_id == entity_id,
        table.c.status == ConfigStatus.PUBLISHED.value,
    )
    if other_than is not None:
        query = query.where(table.c.id != other_than)
    if for_update:
        query = query.with_for_update()
    row = session.execute(query).mappings().one_or_none()
    return None if row is None else dict(row)


def predecessor_of(
    session: Session, version: Mapping[str, Any], *, for_update: bool = False
) -> Mapping[str, Any] | None:
    """The version whose values ``version`` stands on: the PUBLISHED version of its scope key
    while it is open, the version it superseded afterwards; None for the first of a key."""
    if str(version["status"]) in OPEN_STATUSES:
        return published_of_key(
            session,
            category=str(version["category"]),
            scope=str(version["scope"]),
            book_code=None if version["book_code"] is None else str(version["book_code"]),
            entity_id=version["entity_id"],
            other_than=version["id"],
            for_update=for_update,
        )
    superseded = version["supersedes_version_id"]
    if superseded is None:
        return None
    row = (
        session.execute(select(*_predecessor_columns()).where(registry_version.c.id == superseded))
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def whole_values(
    version: Mapping[str, Any], predecessor: Mapping[str, Any] | None
) -> dict[str, Any]:
    """The whole value set of ``version``: computed from its statement while it is DRAFT or
    TESTED, the stored ``values`` afterwards."""
    values: Mapping[str, Any] = version["values"]
    if str(version["status"]) in STATEMENT_STATUSES:
        return whole_set(None if predecessor is None else predecessor["values"], values)
    return dict(sorted(values.items()))


def preset_of(version: Mapping[str, Any], predecessor: Mapping[str, Any] | None) -> str | None:
    """The preset the value set of ``version`` stands on (T-PLT-32 ``preset_code``): the stored
    code of a version past TESTED, and for a DRAFT or TESTED version the code the submit stores.

    A statement that leaves a value of its predecessor neither stated nor unset keeps that value,
    so the version stands on the predecessor: it carries the predecessor's code when that is a
    preset, whatever basis an earlier request stated — a ``LEGACY_PARITY`` workspace never holds
    the preset's values under no preset. A statement that leaves none to be kept is a whole set
    of its own and has the code its draft was given: none for ``basis = "DEFAULTS"``, the
    carried one for a draft that restates every value, its own for a preset version."""
    code = None if version["preset_code"] is None else str(version["preset_code"])
    if str(version["status"]) not in STATEMENT_STATUSES or predecessor is None:
        return code
    carried = predecessor["preset_code"]
    if carried is None or carried == DEFAULT_PRESET:
        return code
    statement: Mapping[str, Any] = version["values"]
    keeps = any(name not in statement for name in predecessor["values"])
    return str(carried) if keeps else code


def whole_content(session: Session, version_id: UUID) -> dict[str, Any] | None:
    """The content of a registry version, None when the row is not visible: its category, scope
    key, number, effective date and preset, the WHOLE value set — for a DRAFT or TESTED version
    the set the server stores at the submit — the predecessor it stands on and the difference to
    it by code (module docstring). The statement and the stored set of one version give one
    content, so the hash its tests recorded is the hash of its row and of its request; a
    predecessor that changes changes the content."""
    table = registry_version
    row = (
        session.execute(
            select(
                table.c.id,
                table.c.category,
                table.c.scope,
                table.c.book_code,
                table.c.entity_id,
                table.c.version_no,
                table.c.status,
                table.c.effective_from,
                table.c.preset_code,
                table.c["values"],
                table.c.supersedes_version_id,
            ).where(table.c.id == version_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    version = dict(row)
    predecessor = predecessor_of(session, version)
    whole = whole_values(version, predecessor)
    return {
        "category": str(version["category"]),
        "scope": str(version["scope"]),
        "book_code": None if version["book_code"] is None else str(version["book_code"]),
        "entity_id": None if version["entity_id"] is None else str(version["entity_id"]),
        "version_no": int(version["version_no"]),
        "effective_from": version["effective_from"],
        "preset_code": preset_of(version, predecessor),
        "values": whole,
        "predecessor_version_id": None if predecessor is None else str(predecessor["id"]),
        "changes": difference(None if predecessor is None else predecessor["values"], whole),
    }
