"""Tenant accounting policy set: registry versions, their lifecycle, the legacy-parity preset and
resolution (04 T-PLT-31, T-PLT-32, §15.3 API-R-13, §16.5; POLICIES §0.5, §1.12, §6.3; dev-guide
DG-KRN-REG-01, DG-KRN-REG-05, DG-KRN-REG-06; PRD SM-04, BR-POL-01, BR-POL-02; 03 REQ-POL-004,
REQ-POL-005, REQ-POL-011, REQ-REF-016; CTL-031; BUILD_SPEC RFD-11, BS3-D-17).

The whole value set (04 T-PLT-32 "Whole value set", §16.5 rev 1.183; supervisor ruling R-117 (b);
``registry.versions``). A version past TESTED holds the whole value set of its category at its
scope key. A DRAFT or TESTED version holds its author's statement: the values it states and the
codes it returns to the next level (``unset``, stored as JSON ``null`` members of ``values``). A
request may state ``basis = "DEFAULTS"`` — the values sent are the whole set — and the server then
names in ``unset`` every code the predecessor holds that the request does not state. The
predecessor is the PUBLISHED version of the scope key: one version of a key is open at a time (PRD
SM-04) and a version never takes effect before the effective instant of the PUBLISHED one, nor
together with it unless that version names no date (``order_errors``; PRD ERR-80, ERR-81), so it
is the version in force immediately before the draft takes effect — or, at such a tie, the
version the draft supersedes at the instant both start. ``submit_policy`` stores, in the TESTED →
SUBMITTED statement that DB-04 allows, the predecessor's values overlaid with the stated ones less
``unset``, and the predecessor as ``supersedes_version_id``. The approval hook re-checks that
basis under the row locks of the version and of its predecessor
(``approvals.assert_own_fresh_basis``): another predecessor voids the request ``STALE_SUBJECT``
with 409 ``stale-approval``. An ENTITY or BOOK version overlays the predecessor of its own key
only; a code it does not hold passes to the next level as before.
The one yield of the order (step 4: before the first legal entity, against a PUBLISHED version
that names no date) leaves the predecessor what it is for the value of a period: the first
version of a scope answers for every earlier period (04 T-PLT-32).

Validation (``require_valid``) of the WHOLE set, at every write and at the submit, in order:

1. The scope key (``scope_key``): an ENTITY version names a legal entity of the workspace, a BOOK
   version a book, and no other version names either (422 ``validation-failed``).
2. Values. [J] L3-1-Q-2: a code forced for the book of a BOOK version is refused with
   ``POLICY_VALUE_INVALID`` before its level is checked, because the framework fixes it (REQ-POL-011
   "US-only flags are disabled in the IFRS15 book"). The other codes follow
   ``registry.versions.validation_problem``: level errors first (422 ``policy-level-not-allowed``),
   then value errors (422 ``validation-failed``).
3. Nonpublic elections (REQ-REF-016; POL-190 gates POL-191 to POL-196 and POL-202): a value other
   than the public entity's value needs ``entity.reporting_type = NONPUBLIC``. [J] L3-1-Q-10: the
   whole set of a ``DISCLOSURE_ELECTION`` version holds the entity type — the one it states or
   the one its predecessor holds (absent: the default ``PBE``); a version of another category
   (POL-202) reads the entity type resolved for its entity.
4. The ``effective_from`` of a version that holds, or returns to the default, a ``pin = 'P'``
   parameter is the first day of a future open period (04 §16.5; POLICIES §0.5 rule 3). [J]
   L3-1-Q-3: for every active legal entity in scope, the date of ``effective_from`` in the entity's
   time zone is the start date of a period of its calendar that has not started and whose state for
   the book (a BOOK version's book, otherwise the primary book) is ``future`` or ``open``. Without
   entities it is later than now. A version of a settings category — ``PLATFORM``, ``CLOSE``,
   ``INTEGRATION``, ``SECURITY``, ``AI`` — is not held to it and needs no effective date: without
   one it takes effect at its publication (``INSTANT_CATEGORIES``; supervisor ruling R-115 (e),
   item CFG-PLATFORM-PIN-1, and the ruling of 2026-10-01 on its pre-build line); PRD ERR-75's
   instant form stands.
   Before the workspace's first legal entity a version of an accounting category
   (``ENTITY_BOUND_CATEGORIES``) takes any date, and PRD ERR-75 lets it supersede with a date
   that has passed (rev 1.178; item PINP-PERIOD-VALUE-1, supervisor ruling of 2026-10-01):
   nothing has been computed, and a tenant that migrates dates its policies at the first day of
   its history, so that every period of it takes them (05 RCP-15 "The value of a period"). The
   order of effective instants yields there too, against a PUBLISHED version that names no date
   and against no other (``order_errors``; PRD ERR-80 rev 1.178, the supervisor's ruling of
   2026-10-02).

Authoring validates on create and on every change, so a refusal answers the request itself.
``request_test`` validates again and defers ``POLICY_SIMULATION``. Its runner ``run_test`` checks
that the content is what the request saw, validates, runs the simulation providers and records
DRAFT → TESTED with ``test_evidence`` and ``impact_simulation_file_id``. ``submit_policy`` needs
``effective_from`` outside ``INSTANT_CATEGORIES``, checks the order of effective instants,
validates, stores the whole set, attaches a simulation report when the version holds none and
requests approval of subject ``REGISTRY_VERSION`` (``config.approve``). Approval publishes the
version and supersedes the PUBLISHED version of its scope key (``lifecycle``). ``withdraw_policy``
withdraws the pending request and returns the version to DRAFT; a version reopened after a
withdrawal or a rejection holds the whole set of its last submit as its statement — every value
stated and, as ``unset``, every code the PUBLISHED version of its key holds beyond them
(``_restate``): the submit dropped the nulls of the statement it replaced, and without them the
next submit would carry what the version had returned to the default. A version is reopened only
while the version it stood on is still the PUBLISHED one of its key (``_reopenable``; PRD
ERR-92): once another version has been published since its last submit, the stored set no longer
tells what its author meant to change from what it would now revert, and a new version starts
from the published values.

A create decides its statement under the lock of its key (``presets.claim_key``): the lock, then
the look for an open version, then the predecessor — so the ``unset`` of ``basis = "DEFAULTS"``,
the preset the draft carries and its ``supersedes_version_id`` are all of one version; with no
open version of the key and the lock held, no other version of the key can be published before
the create commits.

``resolution`` answers API-S-PolicyResolution: the levels ``registry.resolve`` consults in order,
the version in force at each and whether it holds the key.

Who authors a version (04 §15.3 API-R-13 rev 1.309; PRD BR-UX-06 rev 1.203; the supervisor's
ruling of 2026-10-02; item POLICY-TENANT-SCOPE-ALL-ENTITIES-1). The routes guard the lifecycle
commands with ``config.author`` held for any entity; each command then asks that permission FOR
THE VERSION'S SCOPE (``require_authority``): a TENANT or BOOK version is the workspace's — a
TENANT version's values answer for every entity that states none of its own, a BOOK version's
for every entity that keeps the book, ahead of the entity's own (``registry.resolve`` reads B
before E) — so its author holds the permission for all entities; an ENTITY version is its
entity's, so the permission covers that entity, not another one beside a role that merely
reads this one. A caller the scope does not cover is
refused 403 ``forbidden`` by name, after one ``DENIED`` audit event of the command
(DG-KRN-AUTH-05) — on a create once the scope key is known, on every other command after the
version is found and before its state is told. Since 04 API-C-03 rev 1.319 (item
READ-SCOPE-BY-PERMISSION-1) a route's transaction runs under the scope of ``config.author``,
so no route reaches the refusal for an ENTITY version: the version of an entity the caller's
permission does not name is not found there (404), and at a create its code names no entity
(422). That half stays the command's own statement, for a caller no route narrowed
(``tests/unit/policies/test_registry_authority.py``). The request of a submitted version names
the same entities (``subjects.registry_version_entities``), so the kernel asks the decider's
``config.approve`` for them. Measured before: an accountant and a Controller of one entity
created, tested, submitted and approved a TENANT version of each of the five settings
categories and of an accounting policy, and a BOOK version,
and a member whose ``config.author`` named one entity authored the version of another entity
that a second role let her session read.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Protocol
from uuid import UUID

from sqlalchemy import Select, and_, select, update
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects
from erev_api.audit import writer as audit_writer
from erev_api.auth import entity_scope
from erev_api.clock import to_entity_date
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    approval_request,
    book,
    contract,
    legal_entity,
    obligation,
    period,
    period_state,
    registry_version,
)
from erev_api.domain.integrations import grouping
from erev_api.domain.platform import actors
from erev_api.domain.policies import lifecycle, simulation
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ConfigStatus,
    JobKind,
    PeriodState,
    RegistryCategory,
    RegistryScope,
)
from erev_api.jobs import registry as job_registry
from erev_api.problems import Problem, ProblemError
from erev_api.registry import presets
from erev_api.registry import resolve as registry
from erev_api.registry.effective import EFFECTIVE_REGISTRY_PARAMETER
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_api.registry.versions import (
    ADDED,
    BASIS_DEFAULTS,
    BASIS_PREDECESSOR,
    CHANGED,
    DEFAULT_PRESET,
    OBJECT_TYPE,
    POLICY_VALUE_INVALID,
    RETURNED_TO_DEFAULT,
    STATEMENT_STATUSES,
    VERSION_SCOPES,
    difference,
    draft_values,
    predecessor_of,
    preset_of,
    published_of_key,
    stated_values,
    unset_codes,
    validation_problem,
    whole_set,
    whole_values,
)

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import RequestContext
    from erev_api.files.store import FileStore
    from erev_api.uow import UnitOfWork


class Page(Protocol):
    @property
    def items(self) -> list[Mapping[str, Any]]: ...


SUBJECT_TYPE: Final = "registry_version"  # T-REF-27 subject type; the job subject
UPDATE_ACTION: Final = "registry_version.update"
TEST_REQUEST_ACTION: Final = "registry_version.test_requested"
# The audit actions of the three lifecycle transitions a command asks for: a refusal for scope
# is recorded under them (``lifecycle.transition`` writes ``<object type>.<status>``).
SUBMIT_ACTION: Final = "registry_version.submitted"
WITHDRAW_ACTION: Final = "registry_version.withdrawn"
PUBLISH_ACTION: Final = "registry_version.published"
AUTHOR_PERMISSION: Final = "config.author"  # 04 API-R-13: authoring and the lifecycle commands
RULE_VERSION: Final = "T-PLT-32"
RULE_PARAMETER: Final = "T-PLT-31"
RULE_ENTITY: Final = "T-REF-01"
RULE_CONTRACT: Final = "T-CON-01"
RULE_OBLIGATION: Final = "T-CON-10"
FRAMEWORK_DEFAULT: Final = "FRAMEWORK_DEFAULT"
REPORTING_TYPE: Final = "entity.reporting_type"  # POL-190
NONPUBLIC: Final = "NONPUBLIC"
# POL-190 gates these elections; the value of a public entity is the framework default.
GATED_POL_IDS: Final = frozenset(
    {"POL-191", "POL-192", "POL-193", "POL-194", "POL-195", "POL-196", "POL-202"}
)
NONPUBLIC_GATED: Final[Mapping[str, Any]] = MappingProxyType(
    {
        spec.code: spec.default_asc606
        for spec in registry.PARAMETERS.values()
        if spec.pol_id in GATED_POL_IDS
    }
)
OPEN_FOR_EFFECT: Final = frozenset({PeriodState.FUTURE.value, PeriodState.OPEN.value})
# PRD ERR-75 rev 1.178: the categories every parameter of which is read by a computation or by an
# act on a legal entity's data — the accounting categories that hold no platform parameter. A
# platform parameter is read by acts that precede any entity (a product's mandatory attributes,
# the snapshot retention), so its categories keep the rule whatever the workspace holds.
ENTITY_BOUND_CATEGORIES: Final = frozenset(
    {spec.category for spec in POLICY_PARAMETERS.values()}
    - {spec.category for spec in PLATFORM_PARAMETERS.values()}
)
# Supervisor ruling R-115 (e), item CFG-PLATFORM-PIN-1, widened by the ruling of 2026-10-01 on the
# item's pre-build line: a version of one of these categories takes the instant form alone —
# effective at its publication when it names no date, or at a later instant — and is not held to
# a period start. They hold workspace settings, none of them a POL: every parameter is read by
# ``registry.setting`` or ``registry.resolve`` at the instant of an act (a session check, an
# upload, an ingestion, a gate, a monitor run, a report) and never through the period rows of a
# computation bundle, which resolves ``POLICY_PARAMETERS`` only (``contracts.bundles``). A
# retention policy is no accounting policy. ``DISCLOSURE_ELECTION`` stays dated.
INSTANT_CATEGORIES: Final = frozenset(
    {
        RegistryCategory.PLATFORM,
        RegistryCategory.CLOSE,
        RegistryCategory.INTEGRATION,
        RegistryCategory.SECURITY,
        RegistryCategory.AI,
    }
)
RULE_ORDER: Final = "REGISTRY_EFFECTIVE_ORDER"  # PRD ERR-80, ERR-81
RULE_BASIS_SUPERSEDED: Final = "REGISTRY_BASIS_SUPERSEDED"  # PRD ERR-92
# A version in one of these statuses was published: its difference is to the version it superseded.
PUBLISHED_STATUSES: Final = frozenset({ConfigStatus.PUBLISHED.value, ConfigStatus.SUPERSEDED.value})
RETURNED_NAMED: Final = 3  # the codes a request summary names before "and N more"
# The checks a passing test run records in ``test_evidence`` (T-PLT-32; L3-1-Q-5).
TEST_CHECKS: Final = (
    "allowed_levels",
    "forced_values",
    "value_schema",
    "nonpublic_elections",
    "effective_from",
)
# [J] Copy the documents leave open.
SCOPE_UNSUPPORTED: Final = "Choose the tenant, entity or book scope."
ENTITY_REQUIRED: Final = "Choose the legal entity of an entity version."
ENTITY_UNKNOWN: Final = "Choose a legal entity of this workspace."
ENTITY_NOT_ALLOWED: Final = "Only an entity version names a legal entity."
BOOK_REQUIRED: Final = "Choose the book of a book version."
BOOK_NOT_ALLOWED: Final = "Only a book version names a book."
FORCED_FOR_BOOK: Final = "The framework fixes this value in the {book} book."
NONPUBLIC_REQUIRED: Final = "This relief is available only when the entity type is Nonpublic."
PERIOD_START_REQUIRED: Final = (
    "Choose the first day of a future open period: this version holds period-scoped parameters."
)
EFFECTIVE_REQUIRED: Final = "Choose the date this version takes effect."
# PRD §5.5 ERR-80 (a dated version) and ERR-81 (a version without a date).
EFFECTIVE_ORDER_DATED: Final = (
    "Version {version_no} takes effect on {date}. Choose an effective date after it."
)
EFFECTIVE_ORDER_UNDATED: Final = (
    "Version {version_no} takes effect on {date}. Choose an effective date after it, or submit "
    "this version once version {version_no} is in effect."
)
# PRD §5.5 ERR-92: the number is that of the PUBLISHED version of the key.
BASIS_SUPERSEDED: Final = (
    "Version {version_no} was published after this version was submitted. Create a new version: "
    "it starts from the published values."
)
VALUE_NULL: Final = "State a value, or name the parameter in unset."
UNSET_AND_STATED: Final = "State a value for this parameter or unset it, not both."
# No full stop of its own: a summary ends as its reader ends it (the approvals toast adds one).
RETURNS_TO_DEFAULT: Final = " Returns to default: {codes}"
NOT_TESTABLE: Final = "Only a draft or tested version can be tested."
CHANGED_SINCE_REQUEST: Final = (
    "This version changed after its test was requested. Run the tests again."
)
NOT_PENDING: Final = "Only a submitted version with a pending request can be withdrawn."
KEY_UNKNOWN: Final = "Choose a registry parameter."
# PRD BR-UX-06 rev 1.203 (item POLICY-TENANT-SCOPE-ALL-ENTITIES-1): the two refusals by name.
WORKSPACE_BEYOND_SCOPE: Final = (
    "A tenant or book policy version applies to every entity. Your own access covers named "
    "entities only; a member whose access covers all entities must author it."
)
ENTITY_BEYOND_SCOPE: Final = (
    "Your access to author policies does not cover the entity of this version. A member whose "
    "access covers it must author it."
)
CONTRACT_UNKNOWN: Final = "Choose a contract of this workspace."
OBLIGATION_UNKNOWN: Final = "Choose an obligation of the contract."
OBLIGATION_NEEDS_CONTRACT: Final = "Choose the contract of the obligation."


def _uuid(value: Any) -> UUID | None:
    return None if value is None else UUID(str(value))


def _book(value: Any) -> BookCode | None:
    return None if value is None else BookCode(str(value))


def _error(field: str, message: str, rule_id: str = RULE_VERSION) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _entity_by_ref(session: Session, ref: str) -> Mapping[str, Any] | None:
    """The visible legal entity whose id or code is ``ref``."""
    try:
        condition = legal_entity.c.id == UUID(ref)
    except ValueError:
        condition = legal_entity.c.code == ref
    row = (
        session.execute(select(legal_entity.c.id, legal_entity.c.code).where(condition))
        .mappings()
        .first()
    )
    return None if row is None else MappingProxyType(dict(row))


def _contract_by_ref(session: Session, ref: str) -> Mapping[str, Any] | None:
    """The visible contract whose id or external id is ``ref``."""
    try:
        condition = contract.c.id == UUID(ref)
    except ValueError:
        condition = contract.c.external_id == ref
    row = (
        session.execute(select(contract.c.id, contract.c.contracting_entity_id).where(condition))
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def _obligation_by_ref(session: Session, contract_id: UUID, ref: str) -> UUID | None:
    """The obligation of the contract whose id or key is ``ref``."""
    try:
        condition = obligation.c.id == UUID(ref)
    except ValueError:
        condition = obligation.c.obligation_key == ref
    found = session.execute(
        select(obligation.c.id).where(obligation.c.contract_id == contract_id, condition)
    ).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def primary_book(session: Session) -> BookCode:
    """The tenant's primary book; ``ASC606`` when none is marked."""
    found = session.execute(select(book.c.code).where(book.c.is_primary.is_(True))).scalar()
    return BookCode.ASC606 if found is None else BookCode(str(found))


# --- validation ----------------------------------------------------------------------------------


def scope_key(
    session: Session,
    *,
    scope: RegistryScope,
    entity_code: str | None,
    book_code: BookCode | None,
    default_book: BookCode | None = None,
) -> tuple[UUID | None, BookCode | None]:
    """The ``entity_id`` and ``book_code`` of a version of ``scope``; 422 ``validation-failed``
    collects the scope, entity and book findings."""
    errors: list[ProblemError] = []
    if scope not in VERSION_SCOPES:
        errors.append(_error("scope", SCOPE_UNSUPPORTED))
    entity_id: UUID | None = None
    if scope is RegistryScope.ENTITY:
        if entity_code is None:
            errors.append(_error("entity_code", ENTITY_REQUIRED))
        else:
            found = session.execute(
                select(legal_entity.c.id).where(legal_entity.c.code == entity_code)
            ).scalar_one_or_none()
            if found is None:
                errors.append(_error("entity_code", ENTITY_UNKNOWN, RULE_ENTITY))
            else:
                entity_id = UUID(str(found))
    elif entity_code is not None:
        errors.append(_error("entity_code", ENTITY_NOT_ALLOWED))
    resolved: BookCode | None = None
    if scope is RegistryScope.BOOK:
        resolved = book_code if book_code is not None else default_book
        if resolved is None:
            errors.append(_error("book", BOOK_REQUIRED))
    elif book_code is not None:
        errors.append(_error("book", BOOK_NOT_ALLOWED))
    if errors:
        raise Problem("validation-failed", errors=errors)
    return entity_id, resolved


def election_errors(
    session: Session,
    *,
    category: RegistryCategory,
    entity_id: UUID | None,
    values: Mapping[str, Any],
    known_at: datetime,
) -> list[ProblemError]:
    """REQ-REF-016: nonpublic elections need the entity type ``NONPUBLIC`` (module docstring,
    step 3)."""
    electing = sorted(
        code
        for code, public in NONPUBLIC_GATED.items()
        if code in values and values[code] != public
    )
    if not electing:
        return []
    reporting = registry.parameter(REPORTING_TYPE)
    if REPORTING_TYPE in values:
        reporting_type = values[REPORTING_TYPE]
    elif category is reporting.category:
        reporting_type = reporting.default_asc606
    elif entity_id is not None:
        reporting_type = registry.resolve(
            session,
            REPORTING_TYPE,
            book_code=BookCode.ASC606,
            entity_id=entity_id,
            known_at=known_at,
        ).value
    else:
        reporting_type = registry.parameter(REPORTING_TYPE).default_asc606
    if reporting_type == NONPUBLIC:
        return []
    return [_error(f"values.{code}", NONPUBLIC_REQUIRED, POLICY_VALUE_INVALID) for code in electing]


def values_problem(
    session: Session,
    *,
    category: RegistryCategory,
    scope: RegistryScope,
    book_code: BookCode | None,
    entity_id: UUID | None,
    values: Mapping[str, Any],
    known_at: datetime,
) -> Problem | None:
    """The DG-KRN-REG-06 problem of a version's values, or None (module docstring, steps 2, 3).

    BUILD_SPEC DIN-10: ``integration.grouping_fields`` holds at most five canonical order fields,
    and the refusal's detail is the SCREENS_B §9.6 copy "Choose at most five fields."."""
    forced: list[ProblemError] = []
    others: dict[str, Any] = {}
    grouped = grouping.setting_errors(values) if category is RegistryCategory.INTEGRATION else []
    if grouped:
        return Problem("validation-failed", grouped[0].message, errors=grouped)
    for code in sorted(values):
        spec = registry.PARAMETERS.get(code)
        if (
            scope is RegistryScope.BOOK
            and book_code is not None
            and spec is not None
            and spec.category is category
            and registry.is_forced(spec, book_code)
        ):
            message = FORCED_FOR_BOOK.format(book=book_code.value)
            forced.append(_error(f"values.{code}", message, POLICY_VALUE_INVALID))
        else:
            others[code] = values[code]
    problem = validation_problem(category=category, scope=scope, book_code=book_code, values=others)
    if problem is not None and problem.slug == "policy-level-not-allowed":
        return problem
    errors = [*forced, *(() if problem is None else problem.errors)]
    if not errors:
        errors = election_errors(
            session, category=category, entity_id=entity_id, values=values, known_at=known_at
        )
    if not errors:
        return None
    return Problem("validation-failed", errors=sorted(errors, key=lambda error: str(error.field)))


def period_scoped(codes: Iterable[str]) -> bool:
    """Whether the codes name a ``pin = 'P'`` parameter (POLICIES §0.5 rule 3)."""
    return any(
        spec.pin == "P" for code in codes if (spec := registry.PARAMETERS.get(code)) is not None
    )


def statement_problem(
    *, category: RegistryCategory, values: Mapping[str, Any], unset: Iterable[str]
) -> Problem | None:
    """The refusal of a statement that cannot be read (04 §16.5 API-S-Policy ``unset``): a stated
    value of JSON ``null``, an ``unset`` code that is no parameter of the version's category, or
    a code both stated and unset in one request. 422 ``validation-failed``."""
    errors = [
        _error(f"values.{code}", VALUE_NULL, POLICY_VALUE_INVALID)
        for code in sorted(values)
        if values[code] is None
    ]
    for code in sorted(set(unset)):
        spec = registry.PARAMETERS.get(code)
        if spec is None or spec.category is not category:
            message = f"Use a parameter of category {category.value}."
            errors.append(_error(f"unset.{code}", message, POLICY_VALUE_INVALID))
        elif code in values:
            errors.append(_error(f"unset.{code}", UNSET_AND_STATED, POLICY_VALUE_INVALID))
    return Problem("validation-failed", errors=errors) if errors else None


def order_errors(
    version: Mapping[str, Any],
    predecessor: Mapping[str, Any] | None,
    *,
    now: datetime,
    before_first_entity: bool = False,
) -> list[ProblemError]:
    """PRD ERR-80 and ERR-81 (04 §16.5 "Order of effective instants", rev 1.183; supervisor ruling
    R-117 (b) rule 4 and the ruling of 2026-10-01 on the tie): a version never takes effect before
    the effective instant of the PUBLISHED version of its scope key, and takes effect together
    with it only when that version names no date. The effective instant of a version without an
    effective date is its publication — ``now`` for the version being checked.

    The tie. A PUBLISHED version that names no date is in effect from its own publication
    instant, so a successor may start at that very instant and supersede it there: the superseded
    version's interval is then empty (its ``effective_to`` is the instant its successor starts),
    and no instant is answered by both. On a real clock the tie does not arise; a world built on
    one frozen instant — every seed world — meets it at its first settings version. A tie with a
    DATED version stays refused, as ``lifecycle.publish`` refuses it (DB-04).

    Before the first legal entity (PRD ERR-80 rev 1.178; 04 §16.5 rev 1.227; item
    PINP-PERIOD-VALUE-1, the supervisor's ruling of 2026-10-02). A version without a date is
    read in two ways: for the ORDER of versions it is in effect from its publication; for the
    VALUE of a period the first version of a scope answers for every earlier period
    (``registry.resolve_among``; 04 T-PLT-32, candidate AD-79). ``before_first_entity`` — the
    workspace has no legal entity and the version is of an accounting category
    (``ENTITY_BOUND_CATEGORIES``) — is where the two meet: a dated version may then start
    before the publication instant of a PUBLISHED version that names no date, the default
    provisioning writes, so that a tenant that migrates dates its policies at the first day of
    its history. Against a DATED published version the order stands there too: publication
    closes the predecessor at the successor's instant, and a successor dated before a dated
    predecessor would leave it an interval that ends before it begins."""
    if predecessor is None:
        return []
    dated: datetime | None = predecessor["effective_from"]
    theirs: datetime = dated or predecessor["published_at"]
    mine: datetime | None = version["effective_from"]
    instant = now if mine is None else mine
    if instant > theirs or (dated is None and instant == theirs):
        return []
    if before_first_entity and dated is None and mine is not None:
        return []  # the first version of a scope answers for every earlier period
    copy = EFFECTIVE_ORDER_UNDATED if mine is None else EFFECTIVE_ORDER_DATED
    message = copy.format(
        version_no=predecessor["version_no"], date=theirs.astimezone(UTC).strftime("%d %b %Y")
    )
    return [ProblemError(field="effective_from", rule_id=RULE_ORDER, message=message)]


def period_start_errors(
    session: Session,
    *,
    category: RegistryCategory,
    scope: RegistryScope,
    book_code: BookCode | None,
    entity_id: UUID | None,
    effective_from: datetime,
    now: datetime,
) -> list[ProblemError]:
    """04 §16.5 ``effective_from`` of a period-scoped version (module docstring, step 4)."""
    refused = [_error("effective_from", PERIOD_START_REQUIRED)]
    columns = (legal_entity.c.id, legal_entity.c.calendar_id, legal_entity.c.time_zone)
    if scope is RegistryScope.ENTITY:
        statement = select(*columns).where(legal_entity.c.id == entity_id)
    else:
        statement = select(*columns).where(legal_entity.c.is_active.is_(True))
    entities = session.execute(statement.order_by(legal_entity.c.code)).mappings().all()
    if not entities:
        if category in ENTITY_BOUND_CATEGORIES and not lifecycle.has_legal_entity(session):
            return []  # before the first legal entity: any date (PRD ERR-75 rev 1.178)
        return [] if effective_from > now else refused
    target = (
        book_code
        if scope is RegistryScope.BOOK and book_code is not None
        else primary_book(session)
    )
    joined = period.join(
        period_state,
        and_(
            period_state.c.tenant_id == period.c.tenant_id, period_state.c.period_id == period.c.id
        ),
    )
    for found in entities:
        time_zone = str(found["time_zone"])
        first_day = to_entity_date(effective_from, time_zone)
        if first_day <= to_entity_date(now, time_zone):
            return refused
        state = session.execute(
            select(period_state.c.state)
            .select_from(joined)
            .where(
                period.c.calendar_id == found["calendar_id"],
                period.c.start_date == first_day,
                period_state.c.entity_id == found["id"],
                period_state.c.book_code == target.value,
            )
        ).scalar_one_or_none()
        if state not in OPEN_FOR_EFFECT:
            return refused
    return []


def require_valid(
    session: Session,
    *,
    now: datetime,
    category: RegistryCategory,
    scope: RegistryScope,
    book_code: BookCode | None,
    entity_id: UUID | None,
    values: Mapping[str, Any],
    effective_from: datetime | None,
    returned: Iterable[str] = (),
) -> None:
    """Raise the first refusal of steps 2 to 4 of the module docstring. ``values`` is the WHOLE
    value set and ``returned`` the codes it returns to the default."""
    problem = values_problem(
        session,
        category=category,
        scope=scope,
        book_code=book_code,
        entity_id=entity_id,
        values=values,
        known_at=now,
    )
    if problem is not None:
        raise problem
    if (
        effective_from is not None
        and category not in INSTANT_CATEGORIES
        and (period_scoped(values) or period_scoped(returned))
    ):
        errors = period_start_errors(
            session,
            category=category,
            scope=scope,
            book_code=book_code,
            entity_id=entity_id,
            effective_from=effective_from,
            now=now,
        )
        if errors:
            raise Problem("validation-failed", errors=errors)


def _values_of(predecessor: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return {} if predecessor is None else predecessor["values"]


def _require_valid_version(uow: UnitOfWork, version: Mapping[str, Any]) -> None:
    """``require_valid`` of the whole value set of ``version`` — for a DRAFT or TESTED version
    the set the server stores at the submit."""
    predecessor = predecessor_of(uow.session, version)
    whole = whole_values(version, predecessor)
    require_valid(
        uow.session,
        now=uow.now,
        category=RegistryCategory(version["category"]),
        scope=RegistryScope(version["scope"]),
        book_code=_book(version["book_code"]),
        entity_id=_uuid(version["entity_id"]),
        values=whole,
        effective_from=version["effective_from"],
        returned=difference(_values_of(predecessor), whole)["returned_to_default"],
    )


def _statement(
    values: Mapping[str, Any],
    unset: Iterable[str],
    *,
    basis: str,
    predecessor: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """The ``values`` column of a draft: the stated values and ``null`` for every code it
    returns to the next level — the ones ``unset`` names and, with ``basis = "DEFAULTS"``, every
    code the predecessor holds that the statement does not state."""
    names = set(unset)
    if basis == BASIS_DEFAULTS:
        names |= set(_values_of(predecessor)) - set(values)
    return draft_values(values, sorted(names))


def _carried_preset(predecessor: Mapping[str, Any] | None, basis: str) -> str | None:
    """The preset a new draft's value set stands on (T-PLT-32 ``preset_code``): the predecessor's
    when the draft is made on the predecessor basis and that preset is not ``DEFAULT``, so that a
    ``LEGACY_PARITY`` tenant stays one through later versions (``ssp.resolution.tenant_preset``
    reads the code of the version in force); none for a draft whose values are the whole set."""
    if predecessor is None or basis == BASIS_DEFAULTS:
        return None
    code = predecessor["preset_code"]
    return None if code is None or code == DEFAULT_PRESET else str(code)


def _restate(uow: UnitOfWork, version: Mapping[str, Any]) -> Mapping[str, Any]:
    """``lifecycle.reopen`` for a registry version (04 T-PLT-32 "Whole value set"): a version
    reopened after a rejection or a withdrawal holds the whole set of its last submit as its
    statement. The row stores that set without the JSON nulls of the statement the submit
    replaced, so the draft names again, as ``unset``, every code the PUBLISHED version of its key
    holds beyond the set — the version its last submit stood on (``_reopenable``). The next
    submit then stores the set of the last one, and the request names what it returns to the
    default; read as stated values alone, the row would carry those codes with the predecessor's
    values."""
    predecessor = predecessor_of(uow.session, version)
    return {
        "values": _statement(version["values"], (), basis=BASIS_DEFAULTS, predecessor=predecessor)
    }


def _reopenable(uow: UnitOfWork, version: Mapping[str, Any]) -> None:
    """``lifecycle.reopen`` for a registry version, under the lock of its key (PRD ERR-92; 04
    T-PLT-32 "Whole value set"; the supervisor's ruling of 2026-10-01 on the report of item
    REG-VERSION-WHOLE-SET-1): a rejected or withdrawn version is reopened only while the version
    its last submit stood on — SC-V ``supersedes_version_id`` — is still the PUBLISHED version of
    its key. The row holds the whole set of that submit and no longer its author's statement, so
    on another predecessor what the author meant to change cannot be told from what the version
    would now revert, and a visible reversal of someone else's published version is still not
    what the author stated. 409 ``invalid-transition`` by name, the message as the problem's
    detail too; a new version starts from the published values."""
    current = published_of_key(
        uow.session,
        category=str(version["category"]),
        scope=str(version["scope"]),
        book_code=None if version["book_code"] is None else str(version["book_code"]),
        entity_id=version["entity_id"],
        other_than=version["id"],
    )
    # A key keeps its PUBLISHED version until another one supersedes it (DB-04), so a key without
    # one never had one: the version stood on none and stands on none.
    if current is None or UUID(str(current["id"])) == _uuid(version["supersedes_version_id"]):
        return
    message = BASIS_SUPERSEDED.format(version_no=current["version_no"])
    raise Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(field="status", rule_id=RULE_BASIS_SUPERSEDED, message=message)],
    )


# --- commands ------------------------------------------------------------------------------------


def require_authority(
    uow: UnitOfWork,
    *,
    scope: RegistryScope | str,
    entity_id: UUID | None,
    action: str,
    version_id: UUID | None = None,
) -> None:
    """Pass when the caller holds ``config.author`` FOR THE VERSION'S SCOPE (module docstring,
    "Who authors a version"; PRD BR-UX-06 rev 1.203): for all entities when the version is a
    TENANT or BOOK version, for the version's entity when it is an ENTITY version. Otherwise
    403 ``forbidden`` by name (rule ``T-PLT-10``), after one ``DENIED`` audit event of the
    command in a transaction of its own (DG-KRN-AUTH-05): ``action`` is the command's audit
    action, the object the version where one exists, and the detail states the rule and, for
    the workspace's version, the scope asked — like the answer it names no entity. SYSTEM —
    provisioning, a seed, a job — holds every permission for all entities
    (``entity_scope.held_scope``). A scope that is not ENTITY, or names no entity, is the
    workspace's: the check fails closed."""
    principal = uow.principal
    workspace = RegistryScope(scope) is not RegistryScope.ENTITY or entity_id is None
    if workspace:
        covered = entity_scope.holds_all(principal, AUTHOR_PERMISSION)
    else:
        covered = entity_scope.holds_for(principal, (AUTHOR_PERMISSION,), UUID(str(entity_id)))
    if covered:
        return
    audit_writer.record_denied(
        uow.ctx,
        action=action,
        object_type=OBJECT_TYPE,
        object_id=version_id,
        permission=AUTHOR_PERMISSION,
        detail=scope_denial(all_entities=workspace),
        keyring=uow.keyring,
    )
    raise beyond_scope(WORKSPACE_BEYOND_SCOPE if workspace else ENTITY_BEYOND_SCOPE)


def beyond_scope(message: str) -> Problem:
    """403 ``forbidden`` by name under rule ``T-PLT-10`` — the answer of
    ``platform.users.beyond_scope``, built here because this module is imported on the way to
    that one (DG-ARC-17). ``tests/unit/policies/test_registry_authority.py`` holds the two
    equal."""
    return Problem(
        "forbidden",
        message,
        errors=[ProblemError(rule_id=entity_scope.RULE_OWN_SCOPE, message=message)],
    )


def scope_denial(*, all_entities: bool) -> dict[str, str]:
    """The detail of the ``DENIED`` event of ``require_authority``: the rule and, where the
    permission is asked for all entities, the scope — ``platform.users.scope_denial``, held
    equal by the same unit test. Like the answer it names no entity."""
    return {"rule_id": entity_scope.RULE_OWN_SCOPE, **({"scope": "*"} if all_entities else {})}


def _require_authority_over(uow: UnitOfWork, version: Mapping[str, Any], *, action: str) -> None:
    """``require_authority`` for a stored version, asked right after it is found."""
    require_authority(
        uow,
        scope=str(version["scope"]),
        entity_id=_uuid(version["entity_id"]),
        action=action,
        version_id=UUID(str(version["id"])),
    )


def create_policy(
    uow: UnitOfWork,
    *,
    category: RegistryCategory,
    scope: RegistryScope,
    entity_code: str | None,
    book_code: BookCode | None,
    values: Mapping[str, Any],
    effective_from: datetime | None,
    unset: Sequence[str] = (),
    basis: str = BASIS_PREDECESSOR,
) -> UUID:
    """``POST /policies``: a validated DRAFT version (``presets.create_draft_version``) holding
    the statement ``values``, ``unset`` and ``basis`` make (module docstring); the whole set it
    would store is validated now. The key is claimed before the predecessor is read
    (``presets.claim_key``): 409 ``invalid-transition`` while another version of it is open."""
    session = uow.session
    entity_id, resolved = scope_key(
        session, scope=scope, entity_code=entity_code, book_code=book_code
    )
    require_authority(uow, scope=scope, entity_id=entity_id, action=presets.CREATE_ACTION)
    problem = statement_problem(category=category, values=values, unset=unset)
    if problem is not None:
        raise problem
    presets.claim_key(uow, category=category, scope=scope, book_code=resolved, entity_id=entity_id)
    predecessor = published_of_key(
        session,
        category=category.value,
        scope=scope.value,
        book_code=None if resolved is None else resolved.value,
        entity_id=entity_id,
    )
    stored = _statement(values, unset, basis=basis, predecessor=predecessor)
    whole = whole_set(_values_of(predecessor), stored)
    require_valid(
        session,
        now=uow.now,
        category=category,
        scope=scope,
        book_code=resolved,
        entity_id=entity_id,
        values=whole,
        effective_from=effective_from,
        returned=difference(_values_of(predecessor), whole)["returned_to_default"],
    )
    return presets.create_draft_version(
        uow,
        category=category,
        scope=scope,
        book_code=resolved,
        entity_id=entity_id,
        values=stored,
        preset_code=_carried_preset(predecessor, basis),
        effective_from=effective_from,
    )


def create_legacy_parity_preset(
    uow: UnitOfWork,
    *,
    scope: RegistryScope,
    entity_code: str | None,
    book_code: BookCode | None,
) -> UUID:
    """``POST /policies/presets/legacy-parity``: the DRAFT ``LEGACY_PARITY`` version of the scope
    (DG-KRN-REG-05); a BOOK version defaults to the ``ASC606`` book. A preset is a whole value
    set: the draft returns to the default every code the predecessor holds that the preset does
    not state (``basis = "DEFAULTS"``)."""
    session = uow.session
    entity_id, resolved = scope_key(
        session,
        scope=scope,
        entity_code=entity_code,
        book_code=book_code,
        default_book=BookCode.ASC606,
    )
    require_authority(uow, scope=scope, entity_id=entity_id, action=presets.CREATE_ACTION)
    values = presets.legacy_parity_values(scope=scope, book_code=resolved)
    presets.claim_key(
        uow, category=presets.PRESET_CATEGORY, scope=scope, book_code=resolved, entity_id=entity_id
    )
    predecessor = published_of_key(
        session,
        category=presets.PRESET_CATEGORY.value,
        scope=scope.value,
        book_code=None if resolved is None else resolved.value,
        entity_id=entity_id,
    )
    stored = _statement(values, (), basis=BASIS_DEFAULTS, predecessor=predecessor)
    require_valid(
        session,
        now=uow.now,
        category=presets.PRESET_CATEGORY,
        scope=scope,
        book_code=resolved,
        entity_id=entity_id,
        values=values,
        effective_from=None,
        returned=unset_codes(stored),
    )
    return presets.create_preset_version(
        uow, scope=scope, book_code=resolved, entity_id=entity_id, unset=unset_codes(stored)
    )


def update_policy(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> None:
    """``PATCH /policies/{id}``: change the statement (``values``, ``unset``, ``basis``) or
    ``effective_from`` of a DRAFT or TESTED version; a REJECTED or WITHDRAWN version is reopened
    first (E-12) and then holds the whole set of its last submit as its statement (``_restate``)
    — refused once another version of its key has been published since that submit (409
    ``invalid-transition``, PRD ERR-92; ``_reopenable``).
    A request replaces the member it names: a code it states leaves the stored ``unset`` and a
    code it unsets leaves the stated values. A request that states ``basis = "DEFAULTS"`` makes
    the values sent the whole set, which no preset made: it clears ``preset_code``, so that a
    workspace leaves ``LEGACY_PARITY`` with its values and never in name only; no other request
    changes the code. 404; 428 or 412; 409 ``configuration-frozen``; 422 for the validation of
    the changed version."""
    session = uow.session
    version = lifecycle.lock(session, KIND, version_id)
    _require_authority_over(uow, version, action=UPDATE_ACTION)
    check_version(int(version["row_version"]))
    version = lifecycle.require_editable(uow, KIND, version)
    columns: dict[str, Any] = {}
    if "effective_from" in changes:
        columns["effective_from"] = changes["effective_from"]
    if changes.keys() & {"values", "unset", "basis"}:
        sent: Mapping[str, Any] = changes.get("values", {})
        named: Sequence[str] = changes.get("unset", ())
        problem = statement_problem(
            category=RegistryCategory(version["category"]), values=sent, unset=named
        )
        if problem is not None:
            raise problem
        stored: Mapping[str, Any] = version["values"]
        basis = changes.get("basis", BASIS_PREDECESSOR)
        stated = dict(sent) if "values" in changes else stated_values(stored)
        if "unset" in changes:
            unset = set(named)
        else:
            # With DEFAULTS the stored codes are named again from the predecessor (``_statement``).
            unset = set() if basis == BASIS_DEFAULTS else set(unset_codes(stored))
        if "values" not in changes:
            stated = {code: value for code, value in stated.items() if code not in unset}
        columns["values"] = _statement(
            stated,
            unset - set(stated),
            basis=basis,
            predecessor=predecessor_of(session, version),
        )
        if basis == BASIS_DEFAULTS and version["preset_code"] is not None:
            columns["preset_code"] = None
    _require_valid_version(uow, {**version, **columns})
    principal = uow.principal
    session.execute(
        update(registry_version)
        .where(registry_version.c.id == version_id)
        .values(
            **columns,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    if "effective_from" in columns:
        before["effective_from"] = version["effective_from"]
        after["effective_from"] = columns["effective_from"]
    if "values" in columns:
        before["values"] = stated_values(version["values"])
        after["values"] = stated_values(columns["values"])
        unset_before, unset_after = unset_codes(version["values"]), unset_codes(columns["values"])
        if unset_before or unset_after:
            before["unset"] = unset_before
            after["unset"] = unset_after
    if "preset_code" in columns:
        before["preset_code"] = version["preset_code"]
        after["preset_code"] = columns["preset_code"]
    uow.audit(
        action=UPDATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=version_id,
        before=before,
        after=after,
    )


def request_test(uow: UnitOfWork, version_id: UUID, *, run_simulation: bool) -> UUID:
    """``POST /policies/{id}/test``: validate, then defer ``POLICY_SIMULATION``; returns the job id.
    409 ``invalid-transition`` unless DRAFT or TESTED; 422 for the validation."""
    session = uow.session
    version = lifecycle.lock(session, KIND, version_id)
    _require_authority_over(uow, version, action=TEST_REQUEST_ACTION)
    if version["status"] not in lifecycle.EDITABLE:
        raise lifecycle.refused(NOT_TESTABLE)
    _require_valid_version(uow, version)
    digest = lifecycle.current_sha256(session, KIND, version_id)
    params = {
        "subject_type": SUBJECT_TYPE,
        "subject_id": str(version_id),
        "run_simulation": run_simulation,
        "content_sha256": digest,
    }
    job = job_registry.defer(
        uow, JobKind.POLICY_SIMULATION, params, subject_type=SUBJECT_TYPE, subject_id=version_id
    )
    uow.audit(
        action=TEST_REQUEST_ACTION,
        object_type=OBJECT_TYPE,
        object_id=version_id,
        detail={
            "job_id": str(job["id"]),
            "run_simulation": run_simulation,
            "content_sha256": digest,
        },
    )
    return UUID(str(job["id"]))


def run_test(uow: UnitOfWork, version_id: UUID, params: Mapping[str, Any]) -> dict[str, Any]:
    """The ``POLICY_SIMULATION`` runner of registry versions (``simulation.register_test_runner``).

    The version must still be DRAFT or TESTED with the content the request saw (409
    ``invalid-transition``), and valid (422). The simulation report is attached when
    ``run_simulation`` is true; otherwise ``/submit`` attaches one (PRD BR-POL-01).
    """
    session = uow.session
    version = lifecycle.lock(session, KIND, version_id)
    if version["status"] not in lifecycle.EDITABLE:
        raise lifecycle.refused(NOT_TESTABLE)
    digest = lifecycle.current_sha256(session, KIND, version_id)
    if digest != params.get("content_sha256"):
        raise lifecycle.refused(CHANGED_SINCE_REQUEST, rule_id=lifecycle.RULE_LIFECYCLE)
    _require_valid_version(uow, version)
    report = None
    if bool(params.get("run_simulation", True)):
        report = simulation.simulate(
            uow,
            simulation.SimulationSubject(
                subject_type=SUBJECT_TYPE, subject_id=version_id, content_sha256=digest
            ),
        )
    values = whole_values(version, predecessor_of(session, version))
    evidence = {
        "result": "PASS",
        "parameters": len(values),
        "checks": list(TEST_CHECKS),
        "example_cases": 0,
        "content_sha256": digest,
        "tested_at": uow.now.isoformat(),
    }
    impact = None if report is None else {"file_id": str(report.file_id), "summary": report.summary}
    lifecycle.mark_tested(
        uow,
        KIND,
        version,
        content_sha256=digest,
        detail={"test_evidence": evidence, "impact_simulation": impact},
    )
    principal = uow.principal
    session.execute(
        update(registry_version)
        .where(registry_version.c.id == version_id)
        .values(
            test_evidence=evidence,
            impact_simulation_file_id=None if report is None else report.file_id,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    counts: dict[str, int] = {"parameters": len(values)}
    if report is not None:
        counts["contracts_affected"] = int(report.summary["contracts_affected"])
    return {"href": f"/api/v1/policies/{version_id}", "counts": counts}


def submit_policy(uow: UnitOfWork, version_id: UUID, *, comment: str | None) -> None:
    """``POST /policies/{id}/submit``: TESTED → SUBMITTED with the simulation report and an approval
    request of subject ``REGISTRY_VERSION`` (PRD BR-POL-01, BR-PLT-04).

    409 ``invalid-transition`` unless TESTED, and with rule REQ-POL-003 when the content changed
    after the test — the predecessor too; 422 without ``effective_from`` outside
    ``INSTANT_CATEGORIES``, for the order of effective instants (PRD ERR-80, ERR-81) and for the
    validation. The statement in which the version becomes SUBMITTED stores the whole value set
    and the predecessor (module docstring); the audit event carries both and the difference.
    """
    session = uow.session
    version = lifecycle.lock(session, KIND, version_id)
    _require_authority_over(uow, version, action=SUBMIT_ACTION)

    def attach(current: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        dated = current["effective_from"] is not None
        if not dated and RegistryCategory(current["category"]) not in INSTANT_CATEGORIES:
            raise Problem(
                "validation-failed", errors=[_error("effective_from", EFFECTIVE_REQUIRED)]
            )
        predecessor = predecessor_of(session, current)
        errors = order_errors(
            current,
            predecessor,
            now=uow.now,
            before_first_entity=_entity_bound(current) and not lifecycle.has_legal_entity(session),
        )
        if errors:
            raise Problem("validation-failed", errors[0].message, errors=errors)
        _require_valid_version(uow, current)
        whole = whole_values(current, predecessor)
        predecessor_id = None if predecessor is None else UUID(str(predecessor["id"]))
        columns: dict[str, Any] = {"values": whole, "supersedes_version_id": predecessor_id}
        preset = preset_of(current, predecessor)
        if preset != current["preset_code"]:
            # The statement keeps values of a preset predecessor: the version stands on it.
            columns["preset_code"] = preset
        detail: dict[str, Any] = {
            "predecessor_version_id": None if predecessor_id is None else str(predecessor_id),
            "changes": difference(_values_of(predecessor), whole),
        }
        file_id = current["impact_simulation_file_id"]
        if file_id is not None:
            return columns, {**detail, "impact_simulation_file_id": str(file_id)}
        report = simulation.simulate(
            uow,
            simulation.SimulationSubject(
                subject_type=SUBJECT_TYPE,
                subject_id=version_id,
                content_sha256=str(current["content_sha256"]),
            ),
        )
        return (
            {**columns, "impact_simulation_file_id": report.file_id},
            {
                **detail,
                "impact_simulation": {"file_id": str(report.file_id), "summary": report.summary},
            },
        )

    lifecycle.submit(uow, KIND, version, comment=comment, attach=attach)


def withdraw_policy(uow: UnitOfWork, version_id: UUID, *, comment: str | None) -> None:
    """``POST /policies/{id}/withdraw``: the preparer withdraws the pending request (SUBMITTED →
    WITHDRAWN) and the version returns to DRAFT without test evidence. 409 ``invalid-transition``
    without a pending request; 403 for anyone but the preparer (PRD SM-01). A preparer whose
    ``config.author`` no longer covers the version's scope does not withdraw it here, like any
    other author: a TENANT or BOOK version is refused before that (``require_authority``), and an
    ENTITY version is not read by this command's transaction at all (404; 04 API-C-03 rev
    1.319). The request stays theirs to withdraw through the approvals API, which carries no
    permission guard and asks a preparer for no permission (``approvals.withdraw``), where their
    roles still read the request."""
    session = uow.session
    version = lifecycle.lock(session, KIND, version_id)
    _require_authority_over(uow, version, action=WITHDRAW_ACTION)
    pending = session.execute(
        select(approval_request.c.id).where(
            approval_request.c.subject_type == ApprovalSubjectType.REGISTRY_VERSION.value,
            approval_request.c.subject_id == version_id,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        )
    ).scalar_one_or_none()
    if version["status"] != ConfigStatus.SUBMITTED.value or pending is None:
        raise lifecycle.refused(NOT_PENDING)
    approvals.withdraw(
        uow, approval_request_id=UUID(str(pending)), comment=comment, through_subject=True
    )
    lifecycle.reopen(uow, KIND, lifecycle.lock(session, KIND, version_id))
    principal = uow.principal
    session.execute(
        update(registry_version)
        .where(registry_version.c.id == version_id)
        .values(
            test_evidence=None,
            impact_simulation_file_id=None,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )


def auto_approval_allowed(changes: Mapping[str, Any] | None) -> bool:
    """Ruling D-98 candidate 86 (``lifecycle.human_approval_required``): a registry version that
    changes a parameter of ``HUMAN_APPROVAL_REQUIRED`` — states it for the first time, changes it
    or returns it to the default — is never auto-approved: its CFG approval needs a named human
    approver, so the submit withholds the ``AUTO_APPROVAL`` rules for it. ``changes`` is the
    difference the submit records; a version that only carries the parameter changes nothing."""
    return not lifecycle.human_approval_required(changes)


def publish_policy(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /policies/{id}/publish``: publishes a version left APPROVED; a PUBLISHED version
    answers as it is (04 §16.5 publish note). 409 ``invalid-transition`` otherwise."""
    version = lifecycle.lock(uow.session, KIND, version_id)
    _require_authority_over(uow, version, action=PUBLISH_ACTION)
    lifecycle.publish(
        uow,
        KIND,
        version,
        approval_request_id=_uuid(version["approval_request_id"]),
        published_by=uow.principal.id,
    )


# --- queries -------------------------------------------------------------------------------------


def _same(before: Any, after: Any) -> bool:
    """JSON equality: ``True`` never equals ``1``."""
    return json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)


def diff(current: Mapping[str, Any], values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """``diff_against_current``: every code whose value differs between two whole value sets, in
    code order, with what the second does to it — ``CHANGED``, ``ADDED`` or
    ``RETURNED_TO_DEFAULT`` (the next level of the resolution for an ENTITY or BOOK version)."""
    found: list[dict[str, Any]] = []
    for code in sorted(set(current) | set(values)):
        if code not in current:
            change = ADDED
        elif code not in values:
            change = RETURNED_TO_DEFAULT
        elif _same(current[code], values[code]):
            continue
        else:
            change = CHANGED
        found.append(
            {
                "code": code,
                "before": current.get(code),
                "after": values.get(code),
                "change": change,
            }
        )
    return found


# The ``actors.named`` values ``policy_select`` reads with each row (dev-guide DG-API-11).
CREATED_BY_NAMED: Final = "created_by__named"
PUBLISHED_BY_NAMED: Final = "published_by__named"


def policy_select() -> Select[Any]:
    """The T-PLT-32 rows ``policy_outs`` takes: every column, with who created and who published
    each version read in the same statement."""
    tenant_id = registry_version.c.tenant_id
    return select(
        registry_version,
        actors.named(registry_version.c.created_by, tenant_id=tenant_id).label(CREATED_BY_NAMED),
        actors.named(registry_version.c.published_by, tenant_id=tenant_id).label(
            PUBLISHED_BY_NAMED
        ),
    )


type ScopeKey = tuple[str, str, str | None, UUID | None]


def _key_of(row: Mapping[str, Any]) -> ScopeKey:
    book_code = None if row["book_code"] is None else str(row["book_code"])
    return (str(row["category"]), str(row["scope"]), book_code, _uuid(row["entity_id"]))


def _published(session: Session, keys: Iterable[ScopeKey]) -> dict[ScopeKey, Mapping[str, Any]]:
    wanted = set(keys)
    rows = session.execute(
        select(
            registry_version.c.id,
            registry_version.c.category,
            registry_version.c.scope,
            registry_version.c.book_code,
            registry_version.c.entity_id,
            registry_version.c["values"],
            registry_version.c.preset_code,
        ).where(registry_version.c.status == ConfigStatus.PUBLISHED.value)
    ).mappings()
    published: dict[ScopeKey, Mapping[str, Any]] = {}
    for found in rows:
        row: Mapping[str, Any] = dict(found)
        if _key_of(row) in wanted:
            published[_key_of(row)] = row
    return published


def policy_outs(
    session: Session, rows: Sequence[Mapping[str, Any]], *, files: FileStore, keyring: KeyRing
) -> list[dict[str, Any]]:
    """API-S-Policy of each ``policy_select`` row. ``published_by`` is null until the version is
    published; a version published without a publisher (automatic approval, the provisioned
    defaults) names the system. A DRAFT or TESTED version answers its statement — ``values``
    stated and ``unset`` — and ``diff_against_current`` of the whole set the server would store;
    a later version answers the whole set it holds and no ``unset``. ``diff_against_current`` is
    read against the PUBLISHED version of the key while a version is not published, and for a
    PUBLISHED or SUPERSEDED version against the version it superseded: the difference it made —
    the ``changes`` of its content — and not every value it carried as one it added."""
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    superseded_ids = {
        UUID(str(row["supersedes_version_id"]))
        for row in rows
        if str(row["status"]) in PUBLISHED_STATUSES and row["supersedes_version_id"] is not None
    }
    superseded: dict[UUID, Mapping[str, Any]] = (
        {
            UUID(str(found_id)): held
            for found_id, held in session.execute(
                select(registry_version.c.id, registry_version.c["values"]).where(
                    registry_version.c.id.in_(superseded_ids)
                )
            ).tuples()
        }
        if superseded_ids
        else {}
    )
    entity_ids = {row["entity_id"] for row in rows if row["entity_id"] is not None}
    codes = {
        UUID(str(entity_id)): str(code)
        for entity_id, code in session.execute(
            select(legal_entity.c.id, legal_entity.c.code).where(legal_entity.c.id.in_(entity_ids))
        ).tuples()
    }
    pending = {
        UUID(str(subject_id)): UUID(str(request_id))
        for subject_id, request_id in session.execute(
            select(approval_request.c.subject_id, approval_request.c.id).where(
                approval_request.c.subject_type == ApprovalSubjectType.REGISTRY_VERSION.value,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                approval_request.c.subject_id.in_(ids),
            )
        ).tuples()
    }
    published = _published(session, (_key_of(row) for row in rows))
    outs: list[dict[str, Any]] = []
    for row in rows:
        version_id = UUID(str(row["id"]))
        current = published.get(_key_of(row))
        current_values: Mapping[str, Any] = (
            {} if current is None or UUID(str(current["id"])) == version_id else current["values"]
        )
        stored: Mapping[str, Any] = row["values"]
        is_statement = str(row["status"]) in STATEMENT_STATUSES
        whole = whole_set(current_values, stored) if is_statement else dict(stored)
        compared = current_values
        if str(row["status"]) in PUBLISHED_STATUSES:
            stood_on = _uuid(row["supersedes_version_id"])
            compared = {} if stood_on is None else superseded.get(stood_on, {})
        file_id = row["impact_simulation_file_id"]
        impact = (
            None
            if file_id is None
            else {
                "file_id": file_id,
                "summary": simulation.read_summary(session, file_id, files=files, keyring=keyring),
            }
        )
        entity_id = _uuid(row["entity_id"])
        outs.append(
            {
                "id": version_id,
                "category": row["category"],
                "scope": row["scope"],
                "entity_id": entity_id,
                "entity_code": None if entity_id is None else codes.get(entity_id),
                "book": row["book_code"],
                "values": stated_values(stored) if is_statement else dict(stored),
                "unset": unset_codes(stored) if is_statement else [],
                "preset_code": preset_of(row, current if is_statement else None),
                "version_no": row["version_no"],
                "status": row["status"],
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "test_evidence": row["test_evidence"],
                "impact_simulation": impact,
                "approval_request_id": row["approval_request_id"],
                "pending_approval_request_id": pending.get(version_id),
                "content_sha256": row["content_sha256"],
                "published_at": row["published_at"],
                "published_by": None
                if row["published_at"] is None
                else actors.actor(row["published_by"], None, row[PUBLISHED_BY_NAMED]),
                "supersedes_version_id": row["supersedes_version_id"],
                "diff_against_current": diff(compared, whole),
                "created_by": actors.actor(
                    row["created_by"], row["created_by_kind"], row[CREATED_BY_NAMED]
                ),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "row_version": row["row_version"],
            }
        )
    return outs


def policy_out(
    session: Session, version_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    row = (
        session.execute(policy_select().where(registry_version.c.id == version_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return policy_outs(session, [dict(row)], files=files, keyring=keyring)[0]


def get_policy(
    ctx: RequestContext, version_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return policy_out(session, version_id, files=files, keyring=keyring)


def list_policies[P: Page](
    ctx: RequestContext,
    *,
    entity_ref: str | None,
    page: Callable[[Session, Select[Any]], P],
    files: FileStore,
    keyring: KeyRing,
) -> tuple[P, list[dict[str, Any]]]:
    """One page of registry versions; ``entity`` (code or id) keeps the versions of that entity."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        statement = policy_select()
        if entity_ref is not None:
            found = _entity_by_ref(session, entity_ref)
            if found is None:
                raise Problem(
                    "validation-failed", errors=[_error("entity", ENTITY_UNKNOWN, RULE_ENTITY)]
                )
            statement = statement.where(registry_version.c.entity_id == found["id"])
        result = page(session, statement)
        return result, policy_outs(session, result.items, files=files, keyring=keyring)


def list_parameters[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of the T-PLT-31 catalogue (DG-KRN-REG-04) read through the effective relation of
    rule 3 (04 rev 1.59): the latest T-PLT-47 correction of each code over its seeded row."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, select(EFFECTIVE_REGISTRY_PARAMETER))
        return result, [dict(item) for item in result.items]


def resolution(
    session: Session,
    *,
    key: str,
    book_code: BookCode,
    entity_id: UUID | None,
    known_at: datetime,
    contract_id: UUID | None = None,
    obligation_id: UUID | None = None,
) -> dict[str, Any]:
    """API-S-PolicyResolution of ``registry.resolve`` with its chain (DG-KRN-REG-01; REQ-POL-004).

    [J] L3-1-Q-6: ``chain`` lists the levels consulted in resolution order, each with the version in
    force at ``known_at`` (``source_id``, null when none) and whether it holds the key, up to the
    level that answers; the framework default closes a chain that no version answers, and is the
    only link of a forced parameter. CTR-15: the OBLIGATION and CONTRACT override levels come first
    when the scope names their subject, each with the approved override in force (``source_id``).
    """
    spec = registry.parameter(key)
    chain: list[dict[str, Any]] = []
    forced = registry.is_forced(spec, book_code)
    if not forced and contract_id is not None:
        for scope, _level, subject_id in registry.override_subjects(
            spec, contract_id=contract_id, obligation_id=obligation_id
        ):
            override = registry.override_in_force(
                session, spec, contract_id=contract_id, obligation_id=subject_id, known_at=known_at
            )
            override_id = None if override is None else UUID(str(override["id"]))
            link = {"level": scope.value, "found": override is not None, "source_id": override_id}
            chain.append(link)
            if override is not None:
                return {
                    "key": key,
                    "value": override["value"],
                    "level": scope.value,
                    "source": {"type": "policy_override", "id": override_id},
                    "is_forced": False,
                    "known_at": known_at,
                    "chain": chain,
                }
    if not forced:
        for scope, _level in registry.VERSION_LEVELS:
            if scope not in spec.allowed_levels or (
                scope is RegistryScope.ENTITY and entity_id is None
            ):
                continue
            found = registry.version_in_force(
                session,
                spec,
                scope=scope,
                book_code=book_code,
                entity_id=entity_id,
                known_at=known_at,
            )
            source_id = None if found is None else UUID(str(found["id"]))
            holds = found is not None and key in found["values"]
            chain.append({"level": scope.value, "found": holds, "source_id": source_id})
            if found is not None and holds:
                return {
                    "key": key,
                    "value": found["values"][key],
                    "level": scope.value,
                    "source": {"type": "registry_version", "id": source_id},
                    "is_forced": False,
                    "known_at": known_at,
                    "chain": chain,
                }
    default = registry.framework_default(spec, book_code)
    chain.append({"level": FRAMEWORK_DEFAULT, "found": True, "source_id": None})
    return {
        "key": key,
        "value": default.value,
        "level": FRAMEWORK_DEFAULT,
        "source": {"type": "framework_default", "id": None},
        "is_forced": forced,
        "known_at": known_at,
        "chain": chain,
    }


def resolve_policy(
    ctx: RequestContext,
    *,
    key: str,
    entity_ref: str | None,
    book_code: BookCode | None,
    contract: str | None,
    obligation: str | None,
    known_at: datetime,
) -> dict[str, Any]:
    """``GET /policies/resolve``: 422 ``validation-failed`` for an unknown key, contract (id or
    external id) or entity, and for an obligation (id or key) the contract does not hold or that
    names no contract. ``book`` defaults to the primary book and ``entity`` to the contracting
    entity of ``contract``; the scope reaches the T-CON-23 override levels (BUILD_SPEC CTR-15)."""
    errors: list[ProblemError] = []
    if key not in registry.PARAMETERS:
        errors.append(_error("key", KEY_UNKNOWN, RULE_PARAMETER))
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        contract_id: UUID | None = None
        obligation_id: UUID | None = None
        entity_id: UUID | None = None
        if contract is not None:
            found_contract = _contract_by_ref(session, contract)
            if found_contract is None:
                errors.append(_error("contract", CONTRACT_UNKNOWN, RULE_CONTRACT))
            else:
                contract_id = UUID(str(found_contract["id"]))
                entity_id = UUID(str(found_contract["contracting_entity_id"]))
        if obligation is not None:
            if contract is None:
                errors.append(_error("obligation", OBLIGATION_NEEDS_CONTRACT, RULE_OBLIGATION))
            elif contract_id is not None:
                obligation_id = _obligation_by_ref(session, contract_id, obligation)
                if obligation_id is None:
                    errors.append(_error("obligation", OBLIGATION_UNKNOWN, RULE_OBLIGATION))
        if entity_ref is not None:
            found = _entity_by_ref(session, entity_ref)
            if found is None:
                errors.append(_error("entity", ENTITY_UNKNOWN, RULE_ENTITY))
            else:
                entity_id = UUID(str(found["id"]))
        if errors:
            raise Problem("validation-failed", errors=errors)
        resolved = primary_book(session) if book_code is None else book_code
        return resolution(
            session,
            key=key,
            book_code=resolved,
            entity_id=entity_id,
            known_at=known_at,
            contract_id=contract_id,
            obligation_id=obligation_id,
        )


# --- lifecycle -----------------------------------------------------------------------------------


def _snapshot(session: Session, version_id: UUID) -> dict[str, Any]:
    """The field-level ``before`` and ``after`` of publication audits: the whole value set and
    the effective date — the content a publication changes, entry by entry, which is what the
    configuration change register counts (RPT-23 ``changed_field_count``). The three lists of the
    difference are not part of it: they restate what the values already show and would be
    counted again; ``registry_version.submitted`` carries them in its detail."""
    content = subjects.registry_version_content(session, version_id)
    return {"values": content["values"], "effective_from": content["effective_from"]}


def _no_errors(_session: Session, _version: Mapping[str, Any]) -> list[ProblemError]:
    return []


def _summary(session: Session, version: Mapping[str, Any]) -> str:
    category = str(version["category"]).replace("_", " ").lower()
    scope = RegistryScope(version["scope"])
    if scope is RegistryScope.ENTITY:
        code = session.execute(
            select(legal_entity.c.code).where(legal_entity.c.id == version["entity_id"])
        ).scalar_one_or_none()
        where = f"entity {code}"
    elif scope is RegistryScope.BOOK:
        where = f"book {version['book_code']}"
    else:
        where = "the workspace"
    summary = f"Publish {category} version {version['version_no']} for {where}"
    predecessor = predecessor_of(session, version)
    whole = whole_values(version, predecessor)
    returned = difference(_values_of(predecessor), whole)["returned_to_default"]
    if not returned:
        return summary
    # The request says by name what an approval returns to the default (ruling R-117 (b) rule 2).
    named = ", ".join(returned[:RETURNED_NAMED])
    if len(returned) > RETURNED_NAMED:
        named += f" and {len(returned) - RETURNED_NAMED} more"
    return f"{summary}.{RETURNS_TO_DEFAULT.format(codes=named)}"


def _serialise(uow: UnitOfWork, version: Mapping[str, Any]) -> None:
    """The scope key's advisory lock ``presets.create_draft_version`` takes, for a version that
    becomes open again (``lifecycle.reopen``; PRD SM-04)."""
    presets.serialise_key(
        uow.session,
        uow.principal.tenant_id,
        category=RegistryCategory(version["category"]),
        scope=RegistryScope(version["scope"]),
        book_code=_book(version["book_code"]),
        entity_id=_uuid(version["entity_id"]),
    )


def _chosen_by(_version: Mapping[str, Any]) -> str:
    """A registry version answers at the ``known_at`` of a computation or the instant of an act
    (DG-KRN-REG-03), so a superseding version never takes effect in the past (PRD ERR-75); rule 4
    of the module docstring stands beside it for a period-scoped version."""
    return lifecycle.BY_INSTANT


def _entity_bound(version: Mapping[str, Any]) -> bool:
    """A version of an accounting category is read by computations and by acts on a legal
    entity's data only, so nothing can have chosen while the workspace has no legal entity
    (``ENTITY_BOUND_CATEGORIES``; PRD ERR-75 rev 1.178)."""
    return RegistryCategory(version["category"]) in ENTITY_BOUND_CATEGORIES


REGISTRY_VERSION_KIND: Final = lifecycle.ConfigVersionKind(
    table=registry_version,
    subject_type=ApprovalSubjectType.REGISTRY_VERSION,
    scope_columns=("category", "scope", "book_code", "entity_id"),
    content=subjects.registry_version_content,
    snapshot=_snapshot,
    submit_errors=_no_errors,
    publish_errors=_no_errors,
    summary=_summary,
    chosen_by=_chosen_by,
    entity_bound=_entity_bound,
    serialise=_serialise,
    restate=_restate,
    reopenable=_reopenable,
)
KIND: Final = REGISTRY_VERSION_KIND


def _on_approved(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    """Approve and publish under the basis the approver reviewed (DG-KRN-APR-05; supervisor ruling
    R-117 (b) rule 3): with the version and the PUBLISHED version of its scope key locked, the
    content — the whole set and the predecessor it stands on — still hashes to the request's;
    otherwise ``StaleBasis``, which voids the request ``STALE_SUBJECT`` (409 ``stale-approval``)."""
    version = lifecycle.lock(uow.session, KIND, subject_id)
    predecessor_of(uow.session, version, for_update=True)
    approvals.assert_own_fresh_basis(
        uow,
        approval_request_id,
        subject_type=ApprovalSubjectType.REGISTRY_VERSION,
        subject_id=subject_id,
    )
    lifecycle.approve(uow, KIND, subject_id, approval_request_id)


def _on_rejected(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(uow, KIND, subject_id, approval_request_id, to_status=ConfigStatus.REJECTED)


def _on_voided(uow: UnitOfWork, subject_id: UUID, approval_request_id: UUID) -> None:
    lifecycle.close(uow, KIND, subject_id, approval_request_id, to_status=ConfigStatus.WITHDRAWN)


subjects.register_lifecycle(
    ApprovalSubjectType.REGISTRY_VERSION,
    subjects.SubjectLifecycle(
        on_approved=_on_approved, on_rejected=_on_rejected, on_voided=_on_voided
    ),
)
simulation.register_test_runner(SUBJECT_TYPE, run_test)
