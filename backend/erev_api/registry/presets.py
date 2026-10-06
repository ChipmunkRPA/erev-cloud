"""Registry versions created as DRAFT, and the legacy-parity preset (dev-guide §5.15 DG-KRN-REG-05;
04 T-PLT-32, §16.5; POLICIES §0.4, §0.5, §6.3; PRD SM-04, BR-POL-02; 03 REQ-POL-005; BUILD_SPEC
RFD-11).

``create_draft_version`` inserts the next DRAFT ``registry_version`` of one scope key (category,
scope, book, entity): one version of a scope key is open at a time (PRD SM-04), ``version_no``
follows the highest number of the key, and the version records the PUBLISHED version it will
supersede — the submit records it again as the predecessor its whole value set stands on (04
T-PLT-32 "Whole value set"). The caller validates the values first; ``values`` is the draft's
statement (``registry.versions.draft_values``): the audit event states the values and the codes
the draft returns to the next level apart. ``claim_key`` is the lock and the look of that create
on their own, for a command that decides the draft's statement from the predecessor
(``policies.registry_versions.create_policy`` and the preset): it reads the predecessor after
them, so the statement, the preset and ``supersedes_version_id`` are of one version.

``create_preset_version`` creates the DRAFT version of the ``LEGACY_PARITY`` preset. [J]
L3-1-Q-4: a version holds one category, and the preset request names none (04 §16.5), so the preset
is the tenant accounting policy set, category ``ACCOUNTING_POLICY``. Its values are every
parameter of that category that a version of the scope may hold, at its ``legacy_parity_value``:
the level is allowed (POLICIES §0.5 rule 1), the value is not fixed at that scope, and the value is
not ``n/a`` (the framework default applies, POLICIES §0.4). The version then follows the
configuration lifecycle like any other.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import func, insert, select

from erev_api.db import new_id
from erev_api.db.tables.platform import registry_version
from erev_api.enums import BookCode, ConfigStatus, RegistryCategory, RegistryScope
from erev_api.problems import Problem, ProblemError
from erev_api.registry.policies import RegistryParameterSpec
from erev_api.registry.resolve import PARAMETERS
from erev_api.registry.versions import OBJECT_TYPE, draft_values, stated_values, unset_codes

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.uow import UnitOfWork

LEGACY_PARITY: Final = "LEGACY_PARITY"  # T-PLT-32 `preset_code`; POLICIES §6.3
PRESET_CATEGORY: Final = RegistryCategory.ACCOUNTING_POLICY
CREATE_ACTION: Final = "registry_version.create"
RULE_OPEN_VERSION: Final = "SM-04"
# [J] The same copy as the configuration lifecycle (SCREENS §11.0).
VERSION_OPEN: Final = "Another version is open. Finish it or withdraw it first."
OPEN_STATUSES: Final = frozenset(
    {
        ConfigStatus.DRAFT.value,
        ConfigStatus.TESTED.value,
        ConfigStatus.SUBMITTED.value,
        ConfigStatus.APPROVED.value,
    }
)


def settable(
    spec: RegistryParameterSpec, *, scope: RegistryScope, book_code: BookCode | None
) -> bool:
    """Whether a version of ``scope`` may hold ``spec``: its level is allowed and its value is not
    fixed there (a BOOK version: forced for its book; a TENANT or ENTITY version: forced in both
    frameworks; SPEC-Q-178)."""
    if scope not in spec.allowed_levels:
        return False
    if scope is RegistryScope.BOOK and book_code is not None:
        forced = spec.is_forced_ifrs15 if book_code is BookCode.IFRS15 else spec.is_forced_asc606
    else:
        forced = spec.is_forced_asc606 and spec.is_forced_ifrs15
    return not forced


def legacy_parity_values(*, scope: RegistryScope, book_code: BookCode | None) -> dict[str, Any]:
    """The ``LEGACY_PARITY`` values a version of the scope holds, in code order (REQ-POL-005)."""
    return {
        code: spec.legacy_parity_value
        for code, spec in sorted(PARAMETERS.items())
        if spec.category is PRESET_CATEGORY
        and spec.legacy_parity_value is not None
        and settable(spec, scope=scope, book_code=book_code)
    }


def _lock_key(
    tenant_id: UUID,
    *,
    category: RegistryCategory,
    scope: RegistryScope,
    book_code: BookCode | None,
    entity_id: UUID | None,
) -> str:
    book = "" if book_code is None else book_code.value
    entity = "" if entity_id is None else str(entity_id)
    return f"erev.registry_version:{tenant_id}:{category.value}:{scope.value}:{book}:{entity}"


def serialise_key(
    session: Session,
    tenant_id: UUID,
    *,
    category: RegistryCategory,
    scope: RegistryScope,
    book_code: BookCode | None,
    entity_id: UUID | None,
) -> None:
    """Take the transaction-scoped advisory lock of one scope key (schema and lock name, then the
    tenant and the key, as every advisory lock of the product is named). Every command that
    makes a version of the key open takes it before it looks for an open version — the create
    here and the reopening of a rejected or withdrawn version (``policies.lifecycle.reopen``) —
    so that "one version of a scope key is open at a time" (PRD SM-04) is decided by one
    transaction at a time."""
    key = _lock_key(
        tenant_id, category=category, scope=scope, book_code=book_code, entity_id=entity_id
    )
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


def claim_key(
    uow: UnitOfWork,
    *,
    category: RegistryCategory,
    scope: RegistryScope,
    book_code: BookCode | None,
    entity_id: UUID | None,
) -> list[Mapping[str, Any]]:
    """Take a scope key for a new open version: its advisory lock (``serialise_key``), then the
    look — 409 ``invalid-transition`` with rule SM-04 while another version of the key is DRAFT,
    TESTED, SUBMITTED or APPROVED. Returns the versions of the key (id, number, status).

    What the caller reads of the key after this stands until its transaction ends: every command
    that makes a version of the key open takes the lock first, and only an open version can be
    published. So the PUBLISHED version of the key read now is the predecessor of the draft the
    caller creates (04 T-PLT-32 "One open version of a key"): a create reads it here, never
    before. The lock is the transaction's, so taking it again waits for nothing."""
    session = uow.session
    serialise_key(
        session,
        uow.principal.tenant_id,
        category=category,
        scope=scope,
        book_code=book_code,
        entity_id=entity_id,
    )
    table = registry_version
    book = (
        table.c.book_code.is_(None) if book_code is None else table.c.book_code == book_code.value
    )
    entity = table.c.entity_id.is_(None) if entity_id is None else table.c.entity_id == entity_id
    versions: list[Mapping[str, Any]] = [
        dict(row)
        for row in session.execute(
            select(table.c.id, table.c.version_no, table.c.status).where(
                table.c.category == category.value,
                table.c.scope == scope.value,
                book,
                entity,
            )
        ).mappings()
    ]
    if any(version["status"] in OPEN_STATUSES for version in versions):
        raise Problem(
            "invalid-transition",
            errors=[ProblemError(field="status", rule_id=RULE_OPEN_VERSION, message=VERSION_OPEN)],
        )
    return versions


def create_draft_version(
    uow: UnitOfWork,
    *,
    category: RegistryCategory,
    scope: RegistryScope,
    book_code: BookCode | None,
    entity_id: UUID | None,
    values: Mapping[str, Any],
    preset_code: str | None,
    effective_from: datetime | None,
) -> UUID:
    """Insert the next DRAFT version of the scope key and audit ``registry_version.create``.

    409 ``invalid-transition`` with rule SM-04 while another version of the key is DRAFT, TESTED,
    SUBMITTED or APPROVED (``claim_key``). The transaction-scoped advisory lock on the key
    serialises numbering.
    """
    session = uow.session
    principal = uow.principal
    versions = claim_key(
        uow, category=category, scope=scope, book_code=book_code, entity_id=entity_id
    )
    table = registry_version
    published = next(
        (
            UUID(str(version["id"]))
            for version in versions
            if version["status"] == ConfigStatus.PUBLISHED.value
        ),
        None,
    )
    version_no = max((int(version["version_no"]) for version in versions), default=0) + 1
    version_id = new_id()
    stamp = {"by": principal.id, "kind": principal.kind.value}
    row = {
        "category": category.value,
        "scope": scope.value,
        "book_code": None if book_code is None else book_code.value,
        "entity_id": entity_id,
        "values": dict(values),
        "preset_code": preset_code,
        "version_no": version_no,
        "status": ConfigStatus.DRAFT.value,
        "effective_from": effective_from,
        "supersedes_version_id": published,
    }
    session.execute(
        insert(table).values(
            tenant_id=principal.tenant_id,
            id=version_id,
            created_at=uow.now,
            created_by=stamp["by"],
            created_by_kind=stamp["kind"],
            updated_at=uow.now,
            updated_by=stamp["by"],
            updated_by_kind=stamp["kind"],
            **row,
        )
    )
    after: dict[str, Any] = {**row, "values": stated_values(values)}
    if unset_codes(values):
        after["unset"] = unset_codes(values)
    uow.audit(action=CREATE_ACTION, object_type=OBJECT_TYPE, object_id=version_id, after=after)
    return version_id


def create_preset_version(
    uow: UnitOfWork,
    *,
    scope: RegistryScope,
    book_code: BookCode | None,
    entity_id: UUID | None,
    preset_code: str = LEGACY_PARITY,
    unset: Iterable[str] = (),
) -> UUID:
    """DG-KRN-REG-05: the DRAFT ``LEGACY_PARITY`` version of the scope key; ``ValueError`` for any
    other preset. ``unset`` names the codes of the key's PUBLISHED version that the preset does
    not state: a preset is a whole value set."""
    if preset_code != LEGACY_PARITY:
        raise ValueError(f"registry preset {preset_code!r} is not built")
    return create_draft_version(
        uow,
        category=PRESET_CATEGORY,
        scope=scope,
        book_code=book_code,
        entity_id=entity_id,
        values=draft_values(legacy_parity_values(scope=scope, book_code=book_code), unset),
        preset_code=LEGACY_PARITY,
        effective_from=None,
    )
