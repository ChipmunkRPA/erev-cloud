"""Setting and policy resolution KRN-REG (dev-guide §5.15 DG-KRN-REG-01; 04 T-PLT-32; POLICIES
§0.5).

``resolve`` returns the first value found among the APPROVED T-CON-23 overrides of the levels
``OBLIGATION`` and ``CONTRACT`` and the PUBLISHED versions of the levels ``BOOK``, ``ENTITY`` and
``TENANT``, skipping levels the parameter does not allow, and otherwise the framework default of the
book. A version counts at ``known_at`` when it was published at or before that instant and its
effective range holds it; a SUPERSEDED version still answers for instants before its
``effective_to``. A version that does not hold the parameter passes to the next level. An override
counts when it was approved at or before ``known_at``; the latest approved answers, so a SUPERSEDED
override answers for the instants before its successor's approval (BUILD_SPEC CTR-15).

The POB template and product levels are still not consulted here: their scope arguments are accepted
and ignored (SPEC-Q-178).

``PERIOD_PINNED`` names the parameters a bundle hands to each period — pin ``P`` of the policy
catalogue, derived, never written out. A close run records a digest of their values for its
period, read through ``known_versions`` and ``resolve_among`` as a bundle reads them, and the
gate of the period compares it with the same read later (item CLO-RATE-AFTER-RUN-1; 04 T-CLS-01
"What a run read", rev 1.291, third row; ``domain.close.run_inputs``).

``resolve_among`` answers the version levels for an instant other than the one the versions were
read at (05 RCP-15; item PINP-PERIOD-VALUE-1): the bundle builder reads the versions known at its
``known_at`` once (``known_versions``) and asks, per entity and period, for the value in force at
the period's last instant. A version without ``effective_from`` has no lower bound in its row.
The first version of its scope has none in fact: it answers for every earlier instant. A later
one begins at its own publication — ``lifecycle.publish`` closed its predecessor at that
instant — and answers for no instant before it, whether or not another version holds that
instant. Should two versions of one scope still hold an instant, the one whose range ends first
answers. At the instant the versions were read at, the answer is ``resolve``'s for the version
levels.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import ColumnElement, RowMapping, func, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables.contracts import policy_override
from erev_api.db.tables.platform import registry_version
from erev_api.enums import BookCode, ConfigStatus, RegistryScope
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.policies import POLICY_PARAMETERS, RegistryParameterSpec

Level = Literal["O", "C", "P", "B", "E", "T", "DEFAULT"]


@dataclass(frozen=True, slots=True)
class ResolvedValue:
    code: str
    value: Any
    level: Level
    source_id: UUID | None


@dataclass(frozen=True, slots=True)
class ObligationScope:
    obligation_key: str | None  # None = contract level
    obligation_id: UUID | None
    product_id: UUID | None
    pob_template_version_id: UUID | None


# T-PLT-31: the accounting parameters of POLICIES §1 and the platform parameters, by code.
PARAMETERS: Final[Mapping[str, RegistryParameterSpec]] = MappingProxyType(
    {**POLICY_PARAMETERS, **PLATFORM_PARAMETERS}
)
# T-PLT-32 resolution order of the version levels, most specific first.
VERSION_LEVELS: Final[tuple[tuple[RegistryScope, Level], ...]] = (
    (RegistryScope.BOOK, "B"),
    (RegistryScope.ENTITY, "E"),
    (RegistryScope.TENANT, "T"),
)
_IN_FORCE: Final = (ConfigStatus.PUBLISHED.value, ConfigStatus.SUPERSEDED.value)
# T-CON-23 resolution order of the override levels, most specific first (POLICIES §0.5 rule 2).
OVERRIDE_LEVELS: Final[tuple[tuple[RegistryScope, Level], ...]] = (
    (RegistryScope.OBLIGATION, "O"),
    (RegistryScope.CONTRACT, "C"),
)
_OVERRIDE_IN_FORCE: Final = (ConfigStatus.APPROVED.value, ConfigStatus.SUPERSEDED.value)
# The policy parameters a bundle hands to each period of each entity, at the value in force at
# the earlier of its cutoff and the period's last instant (``contracts.bundles._period_rows``:
# pin ``P``; a contract-pinned parameter, pin ``K``, is carried by the contract version). Derived
# from the catalogue's own pin: a parameter joins by being declared.
PERIOD_PINNED: Final[tuple[str, ...]] = tuple(
    code for code, spec in sorted(POLICY_PARAMETERS.items()) if spec.pin == "P"
)


def parameter(code: str) -> RegistryParameterSpec:
    """The catalogue row of ``code``; an unknown code raises ``LookupError`` (XR-12)."""
    spec = PARAMETERS.get(code)
    if spec is None:
        raise LookupError(f"unknown registry parameter {code!r}")
    return spec


def is_forced(spec: RegistryParameterSpec, book_code: BookCode) -> bool:
    """POLICIES "FORCED" for the book; ``LEGACY`` follows the ASC 606 flags (SPEC-Q-178)."""
    return spec.is_forced_ifrs15 if book_code is BookCode.IFRS15 else spec.is_forced_asc606


def framework_default(spec: RegistryParameterSpec, book_code: BookCode) -> ResolvedValue:
    """``default_ifrs15`` for an IFRS 15 book when it is set, else ``default_asc606`` (T-PLT-31)."""
    value = spec.default_asc606
    if book_code is BookCode.IFRS15 and spec.default_ifrs15 is not None:
        value = spec.default_ifrs15
    return ResolvedValue(code=spec.code, value=value, level="DEFAULT", source_id=None)


def _admitted(known_at: datetime) -> tuple[ColumnElement[bool], ...]:
    """A version counts at ``known_at``: it is PUBLISHED or SUPERSEDED, was published at or
    before that instant, and its effective range holds it (``version_in_force``)."""
    table = registry_version
    return (
        table.c.status.in_(_IN_FORCE),
        table.c.published_at <= known_at,
        or_(table.c.effective_from.is_(None), table.c.effective_from <= known_at),
        or_(table.c.effective_to.is_(None), table.c.effective_to > known_at),
    )


def version_in_force(
    session: Session,
    spec: RegistryParameterSpec,
    *,
    scope: RegistryScope,
    book_code: BookCode,
    entity_id: UUID | None,
    known_at: datetime,
) -> RowMapping | None:
    """The version of the parameter's category at ``scope`` in force at ``known_at``."""
    table = registry_version
    statement = select(table.c.id, table.c["values"]).where(
        table.c.category == spec.category.value,
        table.c.scope == scope.value,
        *_admitted(known_at),
    )
    if scope is RegistryScope.BOOK:
        statement = statement.where(table.c.book_code == book_code.value)
    if scope is RegistryScope.ENTITY:
        statement = statement.where(table.c.entity_id == entity_id)
    ordered = statement.order_by(table.c.published_at.desc(), table.c.version_no.desc()).limit(1)
    return session.execute(ordered).mappings().one_or_none()


def override_in_force(
    session: Session,
    spec: RegistryParameterSpec,
    *,
    contract_id: UUID,
    obligation_id: UUID | None,
    known_at: datetime,
) -> RowMapping | None:
    """The T-CON-23 override of the parameter for the contract (``obligation_id`` None) or for the
    obligation that was approved last at or before ``known_at``."""
    table = policy_override
    subject = (
        table.c.obligation_id.is_(None)
        if obligation_id is None
        else table.c.obligation_id == obligation_id
    )
    statement = select(table.c.id, table.c.value).where(
        table.c.contract_id == contract_id,
        subject,
        table.c.policy_key == spec.code,
        table.c.status.in_(_OVERRIDE_IN_FORCE),
        table.c.approved_at <= known_at,
    )
    ordered = statement.order_by(table.c.approved_at.desc()).limit(1)
    return session.execute(ordered).mappings().one_or_none()


def override_subjects(
    spec: RegistryParameterSpec, *, contract_id: UUID | None, obligation_id: UUID | None
) -> list[tuple[RegistryScope, Level, UUID | None]]:
    """The override levels ``resolve`` consults for the scope: the allowed levels whose subject is
    named, each with the obligation id its override names (None at CONTRACT level)."""
    if contract_id is None:
        return []
    found: list[tuple[RegistryScope, Level, UUID | None]] = []
    for scope, level in OVERRIDE_LEVELS:
        if scope not in spec.allowed_levels:
            continue
        if scope is RegistryScope.OBLIGATION:
            if obligation_id is not None:
                found.append((scope, level, obligation_id))
        else:
            found.append((scope, level, None))
    return found


def resolve(
    session: Session,
    code: str,
    *,
    book_code: BookCode,
    entity_id: UUID | None = None,
    product_id: UUID | None = None,
    pob_template_version_id: UUID | None = None,
    contract_id: UUID | None = None,
    obligation_id: UUID | None = None,
    known_at: datetime,
) -> ResolvedValue:
    """The value of ``code`` for the session's tenant (DG-KRN-REG-01). Forced defaults are never
    overridden; the override levels need ``contract_id`` (and ``obligation_id`` for OBLIGATION);
    the ENTITY level needs ``entity_id``."""
    spec = parameter(code)
    if is_forced(spec, book_code):
        return framework_default(spec, book_code)
    for _scope, level, subject_id in override_subjects(
        spec, contract_id=contract_id, obligation_id=obligation_id
    ):
        assert contract_id is not None  # override_subjects answers nothing without a contract
        override = override_in_force(
            session, spec, contract_id=contract_id, obligation_id=subject_id, known_at=known_at
        )
        if override is not None:
            return ResolvedValue(
                code=code, value=override["value"], level=level, source_id=override["id"]
            )
    for scope, level in VERSION_LEVELS:
        if scope not in spec.allowed_levels or (
            scope is RegistryScope.ENTITY and entity_id is None
        ):
            continue
        found = version_in_force(
            session, spec, scope=scope, book_code=book_code, entity_id=entity_id, known_at=known_at
        )
        if found is not None and code in found["values"]:
            return ResolvedValue(
                code=code, value=found["values"][code], level=level, source_id=found["id"]
            )
    return framework_default(spec, book_code)


def known_versions(session: Session, *, known_at: datetime) -> tuple[Mapping[str, Any], ...]:
    """Every registry version published at or before ``known_at`` that is or was in force, the
    latest published first: what a computation at ``known_at`` may read, whatever instant it asks
    about (``resolve_among``)."""
    table = registry_version
    statement = (
        select(
            table.c.id,
            table.c.category,
            table.c.scope,
            table.c.book_code,
            table.c.entity_id,
            table.c["values"],
            table.c.effective_from,
            table.c.effective_to,
            table.c.published_at,
        )
        .where(table.c.status.in_(_IN_FORCE), table.c.published_at <= known_at)
        .order_by(table.c.published_at.desc(), table.c.version_no.desc(), table.c.id)
    )
    return tuple(dict(row) for row in session.execute(statement).mappings())


def _version_at(
    versions: Sequence[Mapping[str, Any]],
    spec: RegistryParameterSpec,
    *,
    scope: RegistryScope,
    book_code: BookCode,
    entity_id: UUID | None,
    at: datetime,
) -> Mapping[str, Any] | None:
    """``version_in_force`` among ``versions`` for the instant ``at``. A version without
    ``effective_from`` begins at its own publication when the scope has an earlier version, and
    has no lower bound when it is the scope's first (module docstring). Of several versions of the
    scope that still hold ``at`` the one whose range ends first answers; ``versions`` come the
    latest published first, which decides between equal ends."""
    of_scope = [
        row
        for row in versions
        if row["category"] == spec.category.value
        and row["scope"] == scope.value
        and (scope is not RegistryScope.BOOK or row["book_code"] == book_code.value)
        and (scope is not RegistryScope.ENTITY or str(row["entity_id"]) == str(entity_id))
    ]
    holding: list[Mapping[str, Any]] = []
    for position, row in enumerate(of_scope):
        begins = row["effective_from"]
        if begins is None and position < len(of_scope) - 1:
            begins = row["published_at"]  # a successor nobody dated: from its publication
        if (begins is None or begins <= at) and (
            row["effective_to"] is None or row["effective_to"] > at
        ):
            holding.append(row)
    return min(
        holding,
        key=lambda row: (row["effective_to"] is None, row["effective_to"] or at),
        default=None,
    )


def resolve_among(
    versions: Sequence[Mapping[str, Any]],
    code: str,
    *,
    book_code: BookCode,
    entity_id: UUID | None = None,
    at: datetime,
) -> ResolvedValue:
    """The value of ``code`` in force at the instant ``at`` among ``versions`` (the rows of
    ``known_versions``): ``resolve`` over the levels ``BOOK``, ``ENTITY`` and ``TENANT``, without
    a query. Forced defaults are never overridden; the override levels are not consulted — a
    period's value is a version's (05 RCP-15)."""
    spec = parameter(code)
    if is_forced(spec, book_code):
        return framework_default(spec, book_code)
    for scope, level in VERSION_LEVELS:
        if scope not in spec.allowed_levels or (
            scope is RegistryScope.ENTITY and entity_id is None
        ):
            continue
        found = _version_at(
            versions, spec, scope=scope, book_code=book_code, entity_id=entity_id, at=at
        )
        if found is not None and code in found["values"]:
            return ResolvedValue(
                code=code, value=found["values"][code], level=level, source_id=found["id"]
            )
    return framework_default(spec, book_code)


def setting(session: Session, code: str, *, known_at: datetime | None = None) -> Any:
    """The tenant value of a setting at ``known_at``, by default the transaction timestamp.

    [J] SPEC-Q-178: ``known_at`` is keyword-only and optional, so callers holding a request or job
    clock resolve at that instant. Platform parameters are not book-specific; ASC606 applies.
    """
    at = known_at if known_at is not None else session.execute(select(func.now())).scalar_one()
    return resolve(session, code, book_code=BookCode.ASC606, known_at=at).value
