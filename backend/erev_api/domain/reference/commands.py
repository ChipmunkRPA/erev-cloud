"""Reference area commands (dev-guide DG-LAY-04, DG-CMD-11): fiscal calendars and period generation
(04 API-R-18, T-REF-04, T-REF-05, DB-05, AUD-CMD; BUILD_SPEC RFD-1); GL accounts and dimensions
(04 API-R-20, API-R-21, T-REF-13, T-REF-16, T-REF-17, DB-12; BUILD_SPEC RFD-6).

``POST /calendars`` and ``POST /calendars/{id}/generate-year`` need any of ``masterdata.maintain``
and ``settings.manage`` for all entities (API-R-18; API-C-03 rev 1.276): a calendar is the
workspace's; a refusal audits ``DENIED`` and returns 403. Inserting a calendar audits
``fiscal_calendar.create``, and each inserted period ``period.generate``: one event per affected
object (AUD-CMD), so a repeated generation writes none. ``ensure_fiscal_year`` carries no
authorisation, so a command that creates periods on its caller's behalf (entity creation, RFD-2)
can reuse it; it writes the period states of every kept book on the calendar whoever calls it.

The account and dimension commands are authorised by their routes' single-code guards
(``config.author`` for accounts, ``masterdata.maintain`` for dimensions). Each insert or update
writes one AUD-CMD event with field-level ``before`` and ``after`` of the changed members.

Legal entities, books and entity books (04 API-R-17; BUILD_SPEC RFD-2) need any of
``masterdata.maintain`` and ``settings.manage`` — for all entities to create an entity or change
a book of the workspace, for the entity itself to change it or the books it keeps ("what a grant
for named entities does not open" below). An entity keeps the primary book from creation and
gets its gapless ``JE`` numbering series. A kept, enabled book has one ``future`` period state per
period of the entity's calendar from the book's first period, each with its NULL → ``future``
transition: entity creation, ``PUT /entities/{id}/books/{code}`` and ``generate-year`` insert the
missing ones, and one AUD-FACT summary names the transitions (period states are AUD-OPS).
``POST /periods/{id}/open`` needs ``period.close``, or ``settings.manage`` while setup is incomplete
(API-R-18).

Currencies and FX rate sets (04 API-R-19; BUILD_SPEC RFD-3): ``PUT /tenant-currencies`` is guarded
by ``settings.manage``; rate sets and versions need any of ``config.author`` and
``masterdata.maintain``. A version is edited while DRAFT, and submission derives the inverses, sets
``rate_count`` and the content hash, walks DRAFT → TESTED → SUBMITTED and opens an
``FX_RATE_SET_VERSION`` request; the approval callbacks live in ``approvals.subjects``.

Customers and related-party groups (04 API-R-22; BUILD_SPEC RFD-8) are authorised by their routes'
``masterdata.maintain`` guard. A customer's external id is unique per source system (REQ-REF-010);
each insert or update writes one AUD-CMD event with field-level ``before`` and ``after``.

Account mapping versions (04 API-R-20, T-REF-14, T-REF-15; BUILD_SPEC RFD-7) are authorised by
their routes' ``config.author`` guard. Rules change while the version is DRAFT or TESTED; ``/test``
runs the publish lint and records DRAFT → TESTED; ``/submit`` attaches the simulation report and
opens an ``ACCOUNT_MAPPING_VERSION`` request, whose approval publishes the version
(``domain.reference.mapping``).

Products and bundle components (04 API-R-23; BUILD_SPEC RFD-9) are authorised by their routes'
``masterdata.maintain`` guard. A product's ``principal_agent`` changes only through a
``PRINCIPAL_AGENT_CHANGE`` request (``domain.reference.products``); each insert, update or delete
of a product or component row writes one AUD-CMD event.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from erev_api import numbering
from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects
from erev_api.audit import writer as audit_writer
from erev_api.auth import entity_scope
from erev_api.db import new_id
from erev_api.db.session import every_entity_scope
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    approval_request,
    book,
    combination_group,
    contract,
    currency,
    customer,
    dimension_definition,
    dimension_value,
    entity_book,
    fiscal_calendar,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    gl_account,
    legal_entity,
    period,
    period_state,
    period_state_transition,
    product,
    product_bundle_component,
    related_party_group,
    tenant,
    tenant_currency,
)
from erev_api.domain.close import rate_changes, rate_reach
from erev_api.domain.platform import provisioning, setup, users
from erev_api.domain.platform.attachments import authorize
from erev_api.domain.policies import lifecycle, simulation, templates
from erev_api.domain.reference import (
    accounts,
    books,
    calendars,
    customers,
    dimensions,
    entities,
    fx,
    mapping,
    period_redirty,
    products,
    queries,
)
from erev_api.domain.reference import periods as period_rules
from erev_api.enums import (
    AccountType,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    CalendarPattern,
    ConfigStatus,
    ContractStatus,
    Distinctness,
    PeriodState,
    PrincipalKind,
    RateType,
    SourceSystem,
)
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.account_mappings import AccountMappingIn, AccountMappingRuleIn
from erev_api.schemas.accounts import GlAccountIn, GlAccountOut
from erev_api.schemas.calendars import (
    CalendarIn,
    CalendarOut,
    CalendarPeriodOut,
    GenerateYearIn,
    GenerateYearOut,
)
from erev_api.schemas.currencies import (
    FxRateSetIn,
    FxRateSetOut,
    FxRateSetVersionCommandIn,
    FxRateSetVersionDetailOut,
    FxRateSetVersionIn,
    FxRateSetVersionUpdateIn,
    TenantCurrenciesIn,
    TenantCurrencyOut,
)
from erev_api.schemas.customers import (
    CustomerIn,
    CustomerOut,
    RelatedPartyGroupIn,
    RelatedPartyGroupOut,
)
from erev_api.schemas.dimensions import (
    DimensionIn,
    DimensionOut,
    DimensionValueIn,
    DimensionValueOut,
)
from erev_api.schemas.entities import BookOut, EntityBookIn, EntityBookOut, EntityIn, EntityOut
from erev_api.schemas.periods import PeriodOpenIn, PeriodOut
from erev_api.schemas.products import (
    BundleComponentsIn,
    BundleComponentsOut,
    PolicyValuesChangeIn,
    PolicyValuesChangeOut,
    PrincipalAgentChangeIn,
    PrincipalAgentChangeOut,
    ProductIn,
    ProductOut,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.uow import UnitOfWork

MAINTAIN_PERMISSIONS: Final = frozenset({"masterdata.maintain", "settings.manage"})
CALENDAR_OBJECT: Final = "fiscal_calendar"
PERIOD_OBJECT: Final = "period"
CREATE_ACTION: Final = "fiscal_calendar.create"
GENERATE_ACTION: Final = "period.generate"
RULE_CONTIGUOUS: Final = "DB-05"
# TY-06 ``erev.code``.
CODE_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.:/#()+-]{0,127}$")
CODE_FORMAT: Final = (
    "Use 1 to 128 letters, digits, spaces or the characters _ . : / # ( ) + -, starting with a "
    "letter or digit."
)
CODE_TAKEN: Final = "Another calendar already uses this code."
PERIODS_DIFFER: Final = "The periods of FY{year} differ from this calendar's rule."
GENERATE_FIRST: Final = "Generate FY{year} first: the periods of a calendar are contiguous."


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


# --- what a grant for named entities does not open ------------------------------------------------
#
# 03 REQ-PLT-012; 04 API-C-03 (rev 1.276); PRD ACT-44, BR-UX-06; the supervisor's ruling of
# 2026-10-02 on lane F-RPS-REG's measurement (item SCOPE-WORKSPACE-LISTS-1, part (d)).
# ``authorize`` asks whether one of the two permissions is held at all. An act on what the
# WORKSPACE owns — a new entity, a book, a fiscal calendar and its years — reaches every entity
# and asks the permission for ALL entities; an act on one entity's row asks it FOR that entity,
# not for another entity and some role on this one (``entity_scope.holds_for``; ruling R-28).
# Measured before, as a Revenue Accountant of AVM-DE alone: she disabled the book US01 keeps (the
# guard read the keepers her session saw: none), and generated a fiscal year whose period states
# were written for AVM-DE alone, so that an invoice of US01 dated into it was quarantined on
# CV-13; with a second role that showed her US01 she renamed it and stopped its IFRS 15 book.
# Each refusal is by name — 403 ``forbidden``, rule ``T-PLT-10`` — after one ``DENIED`` event
# under the command's action, and says who makes the change.
ENTITY_CREATE_BEYOND_SCOPE: Final = (
    "A new legal entity is the workspace's. Your own access covers named entities only; an "
    "administrator of all entities must create it."
)
ENTITY_BEYOND_SCOPE: Final = (
    "Your access to maintain entities does not cover this entity. An administrator whose access "
    "covers it must make this change."
)
BOOK_BEYOND_SCOPE: Final = (
    "A book is the workspace's, and every entity that keeps it follows a change. Your own access "
    "covers named entities only; an administrator of all entities must make this change."
)
BOOK_ENABLE_BEYOND_SCOPE: Final = (
    "The {book} book is not enabled for the workspace, and keeping it would enable it. Your own "
    "access covers named entities only; an administrator of all entities must enable the book."
)
CALENDAR_BEYOND_SCOPE: Final = (
    "A fiscal calendar is the workspace's, and every entity on it follows a change. Your own "
    "access covers named entities only; an administrator of all entities must make this change."
)


def _holds_workspace(uow: UnitOfWork) -> bool:
    """Whether the caller holds one of the two permissions for all entities."""
    return any(entity_scope.holds_all(uow.principal, code) for code in MAINTAIN_PERMISSIONS)


def _scope_denied(uow: UnitOfWork, *, all_entities: bool) -> dict[str, Any]:
    """What a scope refusal of this module hands ``audit_writer.record_denied`` beside its action
    and its object (DG-KRN-AUTH-05): the two permissions and the detail of the rule. Each command
    writes the event itself, under its own object type, so that the lists of the audit key read
    the type where it is written (DG-KRN-AUD-09); then it raises ``users.beyond_scope``."""
    return {
        "permission": "|".join(sorted(MAINTAIN_PERMISSIONS)),
        "detail": users.scope_denial(all_entities=all_entities),
        "keyring": uow.keyring,
    }


def _lacks_workspace(
    uow: UnitOfWork, *, action: str, object_type: str, object_id: UUID | None
) -> bool:
    """The guard of an act on what the workspace owns: any of ``masterdata.maintain`` and
    ``settings.manage`` FOR ALL ENTITIES. A caller who holds neither is refused here, as before
    (``authorize``); for one who holds either for named entities alone the answer is True, and
    the command records the refusal and raises it by name."""
    authorize(
        uow.ctx,
        MAINTAIN_PERMISSIONS,
        keyring=uow.keyring,
        action=action,
        object_type=object_type,
        object_id=object_id,
    )
    return not _holds_workspace(uow)


def _lacks_entity(uow: UnitOfWork, entity_id: UUID) -> bool:
    """The guard of a command on a row of one entity: whether the caller holds neither permission
    FOR ``entity_id``. Asked after the row was found — an entity the session does not read is
    404."""
    return not entity_scope.holds_for(uow.principal, sorted(MAINTAIN_PERMISSIONS), entity_id)


def create_calendar(uow: UnitOfWork, *, body: CalendarIn) -> CalendarOut:
    """``POST /calendars``: 422 ``validation-failed`` lists every finding (DG-CMD-03). A
    calendar is the workspace's: the permission for all entities."""
    if _lacks_workspace(uow, action=CREATE_ACTION, object_type=CALENDAR_OBJECT, object_id=None):
        audit_writer.record_denied(
            uow.ctx,
            action=CREATE_ACTION,
            object_type=CALENDAR_OBJECT,
            object_id=None,
            **_scope_denied(uow, all_entities=True),
        )
        raise users.beyond_scope(CALENDAR_BEYOND_SCOPE)
    session = uow.session
    rule_id = calendars.RULE_CALENDAR
    errors: list[ProblemError] = []
    if not CODE_PATTERN.fullmatch(body.code):
        errors.append(ProblemError(field="code", rule_id=rule_id, message=CODE_FORMAT))
    else:
        taken = select(fiscal_calendar.c.id).where(fiscal_calendar.c.code == body.code).limit(1)
        if session.execute(taken).first() is not None:
            errors.append(ProblemError(field="code", rule_id=rule_id, message=CODE_TAKEN))
    label = body.name.strip()
    if len(label) not in provisioning.LABEL_LENGTH:
        errors.append(ProblemError(field="name", rule_id=rule_id, message=users.NAME_LENGTH))
    rule = calendars.CalendarRule(
        pattern=body.pattern,
        fiscal_year_start_month=body.fiscal_year_start_month,
        week_end_day=body.week_end_day,
        year_end_anchor=body.year_end_anchor,
    )
    errors += calendars.rule_errors(rule)
    if errors:
        raise Problem("validation-failed", errors=errors)

    calendar_id = new_id()
    values: dict[str, Any] = {
        "code": body.code,
        "name": label,
        "pattern": body.pattern.value,
        "fiscal_year_start_month": body.fiscal_year_start_month,
        "week_end_day": body.week_end_day,
        "year_end_anchor": body.year_end_anchor,
    }
    session.execute(
        insert(fiscal_calendar).values(
            tenant_id=uow.principal.tenant_id, id=calendar_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=CREATE_ACTION,
        object_type=CALENDAR_OBJECT,
        object_id=calendar_id,
        object_version="1",
        after=values,
    )
    return CalendarOut.model_validate(queries.calendar_row(session, calendar_id))


def generate_year(uow: UnitOfWork, *, calendar_id: UUID, body: GenerateYearIn) -> GenerateYearOut:
    """``POST /calendars/{id}/generate-year``: authorise — the permission for all entities:
    the year is every entity's on the calendar — then ``ensure_fiscal_year``."""
    if _lacks_workspace(
        uow, action=GENERATE_ACTION, object_type=CALENDAR_OBJECT, object_id=calendar_id
    ):
        audit_writer.record_denied(
            uow.ctx,
            action=GENERATE_ACTION,
            object_type=CALENDAR_OBJECT,
            object_id=calendar_id,
            **_scope_denied(uow, all_entities=True),
        )
        raise users.beyond_scope(CALENDAR_BEYOND_SCOPE)
    return ensure_fiscal_year(uow, calendar_id=calendar_id, fiscal_year=body.fiscal_year)


def _fiscal_year_problem(message: str) -> Problem:
    error = ProblemError(field="fiscal_year", rule_id=RULE_CONTIGUOUS, message=message)
    return Problem("validation-failed", errors=[error])


def ensure_fiscal_year(uow: UnitOfWork, *, calendar_id: UUID, fiscal_year: int) -> GenerateYearOut:
    """Insert the missing periods of ``fiscal_year`` and return all of them; idempotent.

    The calendar row is locked first, as the DB-05 trigger does, so generations of one calendar
    serialise. 404 ``not-found`` for a calendar the caller cannot see; 422 on ``fiscal_year`` when
    the year does not adjoin the generated years (DB-05) or its stored periods differ from the rule.
    ``inserted_state_count`` says how many period states the call wrote: a year whose periods
    exist can still lack states — a book kept since, or a year generated before the states
    were written for every entity — and the same call fills them.
    """
    session = uow.session
    locked = (
        select(
            fiscal_calendar.c.pattern,
            fiscal_calendar.c.fiscal_year_start_month,
            fiscal_calendar.c.week_end_day,
            fiscal_calendar.c.year_end_anchor,
        )
        .where(fiscal_calendar.c.id == calendar_id)
        .with_for_update(key_share=True)
    )
    row = session.execute(locked).mappings().first()
    if row is None:
        raise Problem("not-found")
    rule = calendars.CalendarRule(
        pattern=CalendarPattern(row["pattern"]),
        fiscal_year_start_month=int(row["fiscal_year_start_month"]),
        week_end_day=row["week_end_day"],
        year_end_anchor=row["year_end_anchor"],
    )
    specs = {spec.period_no: spec for spec in calendars.generate_periods(rule, fiscal_year)}
    stored = queries.fiscal_year_periods(session, calendar_id, fiscal_year)
    existing = {int(found["period_no"]): found for found in stored}
    for number, found in existing.items():
        spec = specs.get(number)
        if spec is None or (found["start_date"], found["end_date"]) != (
            spec.start_date,
            spec.end_date,
        ):
            raise _fiscal_year_problem(PERIODS_DIFFER.format(year=fiscal_year))
    missing = [spec for number, spec in specs.items() if number not in existing]
    descending = False
    if missing and not existing:
        bounds = select(func.min(period.c.fiscal_year), func.max(period.c.fiscal_year)).where(
            period.c.calendar_id == calendar_id
        )
        first, last = session.execute(bounds).one()
        if last is not None and fiscal_year > last + 1:
            raise _fiscal_year_problem(GENERATE_FIRST.format(year=last + 1))
        if first is not None and fiscal_year < first - 1:
            raise _fiscal_year_problem(GENERATE_FIRST.format(year=first - 1))
        # A year before the first generated year grows the calendar backwards: inserting its last
        # period first keeps every inserted row adjoining the calendar (DB-05).
        descending = first is not None and fiscal_year < first
    for spec in reversed(missing) if descending else missing:
        _insert_period(uow, calendar_id, spec)
    # RFD-2: the entity books kept on this calendar get their missing period states.
    states = _sync_calendar_states(uow, calendar_id)
    periods = queries.fiscal_year_periods(session, calendar_id, fiscal_year)
    return GenerateYearOut(
        calendar_id=calendar_id,
        fiscal_year=fiscal_year,
        inserted_count=len(missing),
        inserted_state_count=states,
        periods=[CalendarPeriodOut.model_validate(found) for found in periods],
    )


def _insert_period(uow: UnitOfWork, calendar_id: UUID, spec: calendars.PeriodSpec) -> None:
    period_id = new_id()
    values: dict[str, Any] = {
        "calendar_id": calendar_id,
        "fiscal_year": spec.fiscal_year,
        "period_no": spec.period_no,
        "quarter_no": spec.quarter_no,
        "period_key": spec.period_key,
        "name": spec.name,
        "start_date": spec.start_date,
        "end_date": spec.end_date,
    }
    uow.session.execute(
        insert(period).values(
            tenant_id=uow.principal.tenant_id, id=period_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=GENERATE_ACTION,
        object_type=PERIOD_OBJECT,
        object_id=period_id,
        object_version="1",
        after={
            **values,
            "calendar_id": str(calendar_id),
            "start_date": spec.start_date.isoformat(),
            "end_date": spec.end_date.isoformat(),
        },
    )


# --- GL accounts and dimensions (04 API-R-20, API-R-21; BUILD_SPEC RFD-6) -------------------------

ACCOUNT_OBJECT: Final = "gl_account"
ACCOUNT_CREATE_ACTION: Final = "gl_account.create"
ACCOUNT_UPDATE_ACTION: Final = "gl_account.update"
DIMENSION_OBJECT: Final = "dimension_definition"
DIMENSION_CREATE_ACTION: Final = "dimension_definition.create"
VALUE_OBJECT: Final = "dimension_value"
VALUE_CREATE_ACTION: Final = "dimension_value.create"
VALUE_UPDATE_ACTION: Final = "dimension_value.update"
VALUE_REQUIRED: Final = "Send a value or leave the member out."
ACCOUNT_EDITABLE: Final = (
    "name",
    "account_type",
    "normal_balance",
    "entity_ids",
    "required_dimensions",
    "is_active",
)
VALUE_NOT_NULL: Final = ("name", "is_active")
# --- the entities an account and a posting rule name ----------------------------------------------
#
# 03 REQ-PLT-012; 04 T-REF-13 and T-REF-15 (rev 1.319); supervisor ruling R-28; the supervisor's
# ruling of 2026-10-03 on lane QA-BE's line, part 3 (item READ-SCOPE-BY-PERMISSION-1, register
# index 301; lane SECFIX-APR's reading of the accounts family). ``gl_account`` and
# ``account_mapping_rule`` are the workspace's tables (RLS-T): every author reads every row, and
# a row that NAMES entities is still one of those entities. A command on it asks
# ``config.author`` FOR the entities it names (``entity_scope.held_scope``): an account's
# ``entity_ids`` as they stand, each entity a request adds to them, the entity of a rule that is
# deleted. Measured before: ``entity_ids`` was checked for repetition alone — any id was stored,
# whether or not it named an entity — an author of one entity deactivated or re-scoped an account
# available to another entity alone, and deleted the rule by which another entity posts. The
# entity of a rule that is ADDED needs no check of its own: it is looked up in the command's
# transaction, which reads under the scope of ``config.author`` (04 API-C-03 rev 1.319). An
# account available to every entity, and a rule that names none, stay the workspace's — any
# author's, as the versions themselves are. The answer is the one every command gives for a row
# outside the scope of its permission (04 API-C-03 rev 1.319; the supervisor's word of
# 2026-10-03): 404 ``not-found``, as for an id that names nothing, and no ``DENIED`` event — the
# caller may read the row through ``config.read`` and is not told by the command that it is
# there. An entity a request adds that the caller's permission does not cover answers as one
# that does not exist (422, the table's rule).
CONFIG_AUTHOR: Final = "config.author"


def _authors_for(uow: UnitOfWork, entity_ids: Sequence[Any]) -> bool:
    """Whether the caller holds ``config.author`` for every entity of ``entity_ids`` — the
    entities a stored row names. SYSTEM (an import, a seed) holds it for all entities."""
    held = entity_scope.held_scope(uow.principal, CONFIG_AUTHOR)
    return held == "*" or {UUID(str(value)) for value in entity_ids} <= held


def _jsonable(value: Any) -> Any:
    """An audit ``before`` or ``after`` member: ids as strings, enumerations as literals."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


def _audit_members(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in values.items()}


def _label(value: Any, *, field: str, rule_id: str, errors: list[ProblemError]) -> str:
    """A TY-07 label with surrounding spaces removed; appends the finding when it is invalid."""
    if value is None:
        errors.append(ProblemError(field=field, rule_id=rule_id, message=VALUE_REQUIRED))
        return ""
    label = str(value).strip()
    if len(label) not in provisioning.LABEL_LENGTH:
        errors.append(ProblemError(field=field, rule_id=rule_id, message=users.NAME_LENGTH))
    return label


def _account_source(uow: UnitOfWork) -> SourceSystem:
    """[J] E-38 of an account entered through the API: ``API`` for an API client, otherwise
    ``MANUAL_UI`` (L1-1-Q-8)."""
    if uow.principal.kind is PrincipalKind.API_CLIENT:
        return SourceSystem.API
    return SourceSystem.MANUAL_UI


def _entity_ids_errors(
    session: Session, entity_ids: Sequence[UUID], *, stored: Sequence[Any] = ()
) -> list[ProblemError]:
    """``entity_ids`` of a GL account (04 T-REF-13 rev 1.319): each entity once, and each entity
    the request ADDS — one that is not among ``stored``, the ids of the row as it stands — names
    a legal entity the command's transaction reads. That transaction reads under the scope of
    ``config.author`` (04 API-C-03), so an entity the caller's permission does not cover answers
    as one that does not exist (REQ-PLT-012)."""
    field, rule_id = "entity_ids", accounts.RULE_ACCOUNT
    if len(set(entity_ids)) != len(entity_ids):
        return [ProblemError(field=field, rule_id=rule_id, message=accounts.ENTITY_REPEATED)]
    added = sorted(set(entity_ids) - {UUID(str(value)) for value in stored}, key=str)
    if not added:
        return []
    known = session.scalars(select(legal_entity.c.id).where(legal_entity.c.id.in_(added))).all()
    if len(known) == len(added):
        return []
    return [ProblemError(field=field, rule_id=rule_id, message=entity_scope.ENTITY_UNKNOWN)]


def _required_dimensions_errors(session: Session, codes: Sequence[str]) -> list[ProblemError]:
    """Each code names an active dimension of the tenant, once (REQ-REF-009)."""
    field, rule_id = "required_dimensions", accounts.RULE_ACCOUNT
    if len(set(codes)) != len(codes):
        return [ProblemError(field=field, rule_id=rule_id, message=accounts.DIMENSION_REPEATED)]
    active = select(dimension_definition.c.code).where(dimension_definition.c.is_active.is_(True))
    known = {str(code) for code in session.execute(active).scalars()}
    unknown = [code for code in codes if code not in known]
    if not unknown:
        return []
    message = accounts.DIMENSION_UNKNOWN.format(codes=", ".join(unknown))
    return [ProblemError(field=field, rule_id=rule_id, message=message)]


def _account_out(session: Session, account_id: UUID) -> GlAccountOut:
    row = queries.gl_account_row(session, account_id)
    if row is None:
        raise Problem("not-found")
    return GlAccountOut.model_validate(row)


def create_gl_account(
    uow: UnitOfWork, *, body: GlAccountIn, source_system: SourceSystem | None = None
) -> GlAccountOut:
    """``POST /gl-accounts``: 422 ``validation-failed`` lists every finding (DG-CMD-03).

    ``source_system`` names the channel of an import or adapter sync; by default the principal kind
    decides (L1-1-Q-8). Codes are text, so legacy numbers such as ``21001`` keep their digits
    (LM-CL-11). Each entity of ``entity_ids`` is one the command's transaction reads
    (``_entity_ids_errors``).
    """
    session = uow.session
    rule_id = accounts.RULE_ACCOUNT
    errors: list[ProblemError] = []
    if not CODE_PATTERN.fullmatch(body.code):
        errors.append(ProblemError(field="code", rule_id=rule_id, message=CODE_FORMAT))
    else:
        taken = select(gl_account.c.id).where(gl_account.c.code == body.code).limit(1)
        if session.execute(taken).first() is not None:
            errors.append(ProblemError(field="code", rule_id=rule_id, message=accounts.CODE_TAKEN))
    label = _label(body.name, field="name", rule_id=rule_id, errors=errors)
    errors += _entity_ids_errors(session, body.entity_ids)
    errors += _required_dimensions_errors(session, body.required_dimensions)
    if errors:
        raise Problem("validation-failed", errors=errors)

    account_id = new_id()
    values: dict[str, Any] = {
        "code": body.code,
        "name": label,
        "account_type": body.account_type.value,
        "normal_balance": body.normal_balance,
        "entity_ids": list(body.entity_ids),
        "required_dimensions": list(body.required_dimensions),
        "source_system": (source_system or _account_source(uow)).value,
        "is_active": body.is_active,
    }
    session.execute(
        insert(gl_account).values(
            tenant_id=uow.principal.tenant_id, id=account_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=ACCOUNT_CREATE_ACTION,
        object_type=ACCOUNT_OBJECT,
        object_id=account_id,
        object_version="1",
        after=_audit_members(values),
    )
    return _account_out(session, account_id)


def update_gl_account(
    uow: UnitOfWork,
    *,
    account_id: UUID,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> GlAccountOut:
    """``PATCH /gl-accounts/{id}``: lock the row, apply ``If-Match`` through ``check_version``,
    validate the members sent, then write and audit the changed members. 404 ``not-found`` for an
    account the caller cannot see, and for one available to entities the caller's
    ``config.author`` does not cover (``_authors_for``; rev 1.319) — before the row's version is
    told; an unchanged request writes nothing."""
    session = uow.session
    locked = (
        select(*queries.GL_ACCOUNT_COLUMNS).where(gl_account.c.id == account_id).with_for_update()
    )
    current = session.execute(locked).mappings().first()
    if current is None or not _authors_for(uow, current["entity_ids"]):
        raise Problem("not-found")
    check_version(int(current["row_version"]))
    rule_id = accounts.RULE_ACCOUNT
    errors: list[ProblemError] = []
    values: dict[str, Any] = {}
    for key in ACCOUNT_EDITABLE:
        if key in changes and changes[key] is None:
            errors.append(ProblemError(field=key, rule_id=rule_id, message=VALUE_REQUIRED))
    if changes.get("name") is not None:
        values["name"] = _label(changes["name"], field="name", rule_id=rule_id, errors=errors)
    if changes.get("account_type") is not None:
        values["account_type"] = AccountType(changes["account_type"]).value
    if changes.get("normal_balance") is not None:
        values["normal_balance"] = str(changes["normal_balance"])
    if changes.get("entity_ids") is not None:
        entity_ids = [UUID(str(item)) for item in changes["entity_ids"]]
        errors += _entity_ids_errors(session, entity_ids, stored=current["entity_ids"])
        values["entity_ids"] = entity_ids
    if changes.get("required_dimensions") is not None:
        codes = [str(code) for code in changes["required_dimensions"]]
        errors += _required_dimensions_errors(session, codes)
        values["required_dimensions"] = codes
    if changes.get("is_active") is not None:
        values["is_active"] = bool(changes["is_active"])
    if errors:
        raise Problem("validation-failed", errors=errors)
    changed = {key: value for key, value in values.items() if value != current[key]}
    if changed:
        principal = uow.principal
        session.execute(
            update(gl_account)
            .where(gl_account.c.id == account_id)
            .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
        )
        uow.audit(
            action=ACCOUNT_UPDATE_ACTION,
            object_type=ACCOUNT_OBJECT,
            object_id=account_id,
            object_version=str(int(current["row_version"]) + 1),
            before=_audit_members({key: current[key] for key in changed}),
            after=_audit_members(changed),
        )
    return _account_out(session, account_id)


def _lock_custom_dimensions(uow: UnitOfWork) -> None:
    """Serialise custom-dimension writers of the tenant with the DB-12 trigger's advisory lock."""
    key = dimensions.CUSTOM_LIMIT_LOCK.format(tenant_id=uow.principal.tenant_id)
    uow.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


def create_dimension(uow: UnitOfWork, *, body: DimensionIn) -> DimensionOut:
    """``POST /dimensions``: a tenant-defined dimension. A sixth custom dimension returns 422
    ``validation-failed`` with the SCREENS_B §9.5 detail (DB-12)."""
    session = uow.session
    _lock_custom_dimensions(uow)
    rule_id = dimensions.RULE_DIMENSION
    errors: list[ProblemError] = []
    custom = (
        select(func.count())
        .select_from(dimension_definition)
        .where(dimension_definition.c.is_builtin.is_(False))
    )
    limit_reached = int(session.execute(custom).scalar_one()) >= dimensions.MAX_CUSTOM_DIMENSIONS
    if limit_reached:
        errors.append(
            ProblemError(
                rule_id=dimensions.RULE_CUSTOM_LIMIT, message=dimensions.CUSTOM_LIMIT_REACHED
            )
        )
    if not dimensions.DIMENSION_CODE.fullmatch(body.code):
        errors.append(
            ProblemError(field="code", rule_id=rule_id, message=dimensions.DIMENSION_CODE_FORMAT)
        )
    else:
        taken = (
            select(dimension_definition.c.id)
            .where(dimension_definition.c.code == body.code)
            .limit(1)
        )
        if session.execute(taken).first() is not None:
            errors.append(
                ProblemError(field="code", rule_id=rule_id, message=dimensions.DIMENSION_CODE_TAKEN)
            )
    label = _label(body.name, field="name", rule_id=rule_id, errors=errors)
    if errors:
        detail = dimensions.CUSTOM_LIMIT_REACHED if limit_reached else None
        raise Problem("validation-failed", detail, errors=errors)

    position = body.position
    if position is None:
        last = select(func.max(dimension_definition.c.position))
        position = int(session.execute(last).scalar_one() or 0) + 1
    dimension_id = new_id()
    values: dict[str, Any] = {
        "code": body.code,
        "name": label,
        "is_builtin": False,
        "position": position,
        "is_active": body.is_active,
    }
    session.execute(
        insert(dimension_definition).values(
            tenant_id=uow.principal.tenant_id, id=dimension_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=DIMENSION_CREATE_ACTION,
        object_type=DIMENSION_OBJECT,
        object_id=dimension_id,
        object_version="1",
        after=values,
    )
    row = queries.dimension_row(session, dimension_id)
    return DimensionOut.model_validate(row)


def _dimension_id(session: Session, code: str) -> UUID:
    """The id of dimension ``code``; 404 ``not-found`` for an unknown dimension."""
    statement = select(dimension_definition.c.id).where(dimension_definition.c.code == code)
    found = session.execute(statement).scalar_one_or_none()
    if found is None:
        raise Problem("not-found")
    return UUID(str(found))


def _parent_errors(
    session: Session, *, definition_id: UUID, parent_value_id: UUID, value_id: UUID | None
) -> list[ProblemError]:
    """The parent is a value of the same dimension, and not the value itself or below it."""
    field, rule_id = "parent_value_id", dimensions.RULE_VALUE
    statement = select(dimension_value.c.id, dimension_value.c.parent_value_id).where(
        dimension_value.c.dimension_definition_id == definition_id
    )
    parents = {row["id"]: row["parent_value_id"] for row in session.execute(statement).mappings()}
    if parent_value_id not in parents:
        return [ProblemError(field=field, rule_id=rule_id, message=dimensions.PARENT_UNKNOWN)]
    ancestor: UUID | None = parent_value_id
    seen: set[UUID] = set()
    while ancestor is not None and ancestor not in seen:
        if ancestor == value_id:
            return [ProblemError(field=field, rule_id=rule_id, message=dimensions.PARENT_CYCLE)]
        seen.add(ancestor)
        ancestor = parents.get(ancestor)
    return []


def _value_out(session: Session, value_id: UUID) -> DimensionValueOut:
    row = queries.dimension_value_row(session, value_id)
    if row is None:
        raise Problem("not-found")
    return DimensionValueOut.model_validate(row)


def create_dimension_value(
    uow: UnitOfWork, *, dimension_code: str, body: DimensionValueIn
) -> DimensionValueOut:
    """``POST /dimensions/{code}/values``: 404 ``not-found`` for an unknown dimension; 422
    ``validation-failed`` for ``product`` and ``customer``, whose values are the product and
    customer codes and are not stored (T-REF-17)."""
    session = uow.session
    definition_id = _dimension_id(session, dimension_code)
    rule_id = dimensions.RULE_VALUE
    if dimension_code in dimensions.UNSTORED_VALUE_DIMENSIONS:
        message = dimensions.values_not_stored(dimension_code)
        raise Problem(
            "validation-failed", message, errors=[ProblemError(rule_id=rule_id, message=message)]
        )
    errors: list[ProblemError] = []
    if not CODE_PATTERN.fullmatch(body.code):
        errors.append(ProblemError(field="code", rule_id=rule_id, message=CODE_FORMAT))
    else:
        taken = (
            select(dimension_value.c.id)
            .where(
                dimension_value.c.dimension_definition_id == definition_id,
                dimension_value.c.code == body.code,
            )
            .limit(1)
        )
        if session.execute(taken).first() is not None:
            errors.append(
                ProblemError(field="code", rule_id=rule_id, message=dimensions.VALUE_CODE_TAKEN)
            )
    label = _label(body.name, field="name", rule_id=rule_id, errors=errors)
    if body.parent_value_id is not None:
        errors += _parent_errors(
            session,
            definition_id=definition_id,
            parent_value_id=body.parent_value_id,
            value_id=None,
        )
    if errors:
        raise Problem("validation-failed", errors=errors)

    value_id = new_id()
    values: dict[str, Any] = {
        "dimension_definition_id": definition_id,
        "code": body.code,
        "name": label,
        "parent_value_id": body.parent_value_id,
        "is_active": body.is_active,
    }
    session.execute(
        insert(dimension_value).values(
            tenant_id=uow.principal.tenant_id, id=value_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=VALUE_CREATE_ACTION,
        object_type=VALUE_OBJECT,
        object_id=value_id,
        object_version="1",
        after=_audit_members(values),
    )
    return _value_out(session, value_id)


def update_dimension_value(
    uow: UnitOfWork,
    *,
    dimension_code: str,
    value_id: UUID,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> DimensionValueOut:
    """``PATCH /dimensions/{code}/values/{id}``: rename a value, move it under another value of the
    same dimension or remove its parent, or (de)activate it. 404 ``not-found`` unless the value
    belongs to dimension ``code``; ``If-Match`` through ``check_version``."""
    session = uow.session
    definition_id = _dimension_id(session, dimension_code)
    locked = (
        select(*queries.DIMENSION_VALUE_COLUMNS)
        .where(
            dimension_value.c.id == value_id,
            dimension_value.c.dimension_definition_id == definition_id,
        )
        .with_for_update()
    )
    current = session.execute(locked).mappings().first()
    if current is None:
        raise Problem("not-found")
    check_version(int(current["row_version"]))
    rule_id = dimensions.RULE_VALUE
    errors: list[ProblemError] = []
    values: dict[str, Any] = {}
    for key in VALUE_NOT_NULL:
        if key in changes and changes[key] is None:
            errors.append(ProblemError(field=key, rule_id=rule_id, message=VALUE_REQUIRED))
    if changes.get("name") is not None:
        values["name"] = _label(changes["name"], field="name", rule_id=rule_id, errors=errors)
    if "parent_value_id" in changes:
        parent = changes["parent_value_id"]
        parent_id = None if parent is None else UUID(str(parent))
        if parent_id is not None:
            errors += _parent_errors(
                session, definition_id=definition_id, parent_value_id=parent_id, value_id=value_id
            )
        values["parent_value_id"] = parent_id
    if changes.get("is_active") is not None:
        values["is_active"] = bool(changes["is_active"])
    if errors:
        raise Problem("validation-failed", errors=errors)
    changed = {key: value for key, value in values.items() if value != current[key]}
    if changed:
        principal = uow.principal
        session.execute(
            update(dimension_value)
            .where(dimension_value.c.id == value_id)
            .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
        )
        uow.audit(
            action=VALUE_UPDATE_ACTION,
            object_type=VALUE_OBJECT,
            object_id=value_id,
            object_version=str(int(current["row_version"]) + 1),
            before=_audit_members({key: current[key] for key in changed}),
            after=_audit_members(changed),
        )
    return _value_out(session, value_id)


# --- customers and related-party groups (04 API-R-22; BUILD_SPEC RFD-8) -------------------------

CUSTOMER_OBJECT: Final = "customer"
CUSTOMER_CREATE_ACTION: Final = "customer.create"
CUSTOMER_UPDATE_ACTION: Final = "customer.update"
GROUP_OBJECT: Final = "related_party_group"
GROUP_CREATE_ACTION: Final = "related_party_group.create"
GROUP_UPDATE_ACTION: Final = "related_party_group.update"
CUSTOMER_NOT_NULL: Final = ("code", "name", "is_active")
CUSTOMER_FREE_TEXT: Final = ("credit_grade", "segment")
GROUP_NOT_NULL: Final = ("code", "name")


def _optional_text(value: Any) -> str | None:
    """A free-text member with surrounding spaces removed; a blank value is none."""
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _customer_code_errors(
    session: Session, code: str, *, customer_id: UUID | None
) -> list[ProblemError]:
    """TY-06, unique in the workspace (``ux_customer__code``; SCREENS §9.5 copy)."""
    rule_id = customers.RULE_CUSTOMER
    if not CODE_PATTERN.fullmatch(code):
        return [ProblemError(field="code", rule_id=rule_id, message=CODE_FORMAT)]
    taken = select(customer.c.id).where(customer.c.code == code)
    if customer_id is not None:
        taken = taken.where(customer.c.id != customer_id)
    if session.execute(taken.limit(1)).first() is None:
        return []
    message = customers.CODE_TAKEN.format(code=code)
    return [ProblemError(field="code", rule_id=rule_id, message=message)]


def _group_code_errors(session: Session, code: str, *, group_id: UUID | None) -> list[ProblemError]:
    """TY-06, unique in the workspace (``ux_related_party_group__code``)."""
    rule_id = customers.RULE_GROUP
    if not CODE_PATTERN.fullmatch(code):
        return [ProblemError(field="code", rule_id=rule_id, message=CODE_FORMAT)]
    taken = select(related_party_group.c.id).where(related_party_group.c.code == code)
    if group_id is not None:
        taken = taken.where(related_party_group.c.id != group_id)
    if session.execute(taken.limit(1)).first() is None:
        return []
    return [ProblemError(field="code", rule_id=rule_id, message=customers.GROUP_CODE_TAKEN)]


def _group_errors(session: Session, group_id: UUID) -> list[ProblemError]:
    """The related-party group exists (REQ-REF-011)."""
    statement = select(related_party_group.c.id).where(related_party_group.c.id == group_id)
    if session.execute(statement).first() is not None:
        return []
    return [
        ProblemError(
            field="related_party_group_id",
            rule_id=customers.RULE_CUSTOMER,
            message=customers.GROUP_UNKNOWN,
        )
    ]


def _parent_customer_errors(
    session: Session, *, parent_id: UUID, customer_id: UUID | None
) -> list[ProblemError]:
    """The parent is an existing customer, and neither the customer itself nor one below it. One
    recursive query collects the parent and its ancestors; ``UNION`` stops at a loop."""
    field, rule_id = "parent_customer_id", customers.RULE_CUSTOMER
    chain = (
        select(customer.c.id, customer.c.parent_customer_id)
        .where(customer.c.id == parent_id)
        .cte("parent_chain", recursive=True)
    )
    previous = chain.alias("previous")
    step = customer.alias("step")
    chain = chain.union(
        select(step.c.id, step.c.parent_customer_id).where(
            step.c.id == previous.c.parent_customer_id
        )
    )
    ancestors = {UUID(str(value)) for value in session.execute(select(chain.c.id)).scalars()}
    if not ancestors:
        return [ProblemError(field=field, rule_id=rule_id, message=customers.PARENT_UNKNOWN)]
    if customer_id is not None and customer_id in ancestors:
        return [ProblemError(field=field, rule_id=rule_id, message=customers.PARENT_CYCLE)]
    return []


def _external_id_errors(
    session: Session, source_system: SourceSystem, external_id: str
) -> list[ProblemError]:
    """A sent external id is not blank, and is unique per source system (REQ-REF-010). The id is
    kept exactly as sent, because adapters match it literally."""
    field, rule_id = "external_id", customers.RULE_CUSTOMER
    if not external_id.strip():
        return [ProblemError(field=field, rule_id=rule_id, message=customers.EXTERNAL_ID_BLANK)]
    taken = select(customer.c.id).where(
        customer.c.source_system == source_system.value, customer.c.external_id == external_id
    )
    if session.execute(taken.limit(1)).first() is None:
        return []
    message = customers.EXTERNAL_ID_TAKEN.format(
        source_system=source_system.value, external_id=external_id
    )
    return [ProblemError(field=field, rule_id=rule_id, message=message)]


def _customer_out(session: Session, customer_id: UUID) -> CustomerOut:
    row = queries.customer_row(session, customer_id)
    if row is None:
        raise Problem("not-found")
    return CustomerOut.model_validate(row)


def _group_out(session: Session, group_id: UUID) -> RelatedPartyGroupOut:
    row = queries.related_party_group_row(session, group_id)
    if row is None:
        raise Problem("not-found")
    return RelatedPartyGroupOut.model_validate(row)


def create_related_party_group(
    uow: UnitOfWork, *, body: RelatedPartyGroupIn
) -> RelatedPartyGroupOut:
    """``POST /related-party-groups``: 422 ``validation-failed`` lists every finding (DG-CMD-03)."""
    session = uow.session
    errors = _group_code_errors(session, body.code, group_id=None)
    label = _label(body.name, field="name", rule_id=customers.RULE_GROUP, errors=errors)
    if errors:
        raise Problem("validation-failed", errors=errors)

    group_id = new_id()
    values: dict[str, Any] = {
        "code": body.code,
        "name": label,
        "description": _optional_text(body.description),
    }
    session.execute(
        insert(related_party_group).values(
            tenant_id=uow.principal.tenant_id, id=group_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=GROUP_CREATE_ACTION,
        object_type=GROUP_OBJECT,
        object_id=group_id,
        object_version="1",
        after=_audit_members(values),
    )
    return _group_out(session, group_id)


def update_related_party_group(
    uow: UnitOfWork,
    *,
    group_id: UUID,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> RelatedPartyGroupOut:
    """``PATCH /related-party-groups/{id}``: change a group's code, name or description. 404
    ``not-found`` for a group the caller cannot see; ``If-Match`` through ``check_version``; an
    unchanged request writes nothing."""
    session = uow.session
    locked = (
        select(*queries.RELATED_PARTY_GROUP_COLUMNS)
        .where(related_party_group.c.id == group_id)
        .with_for_update()
    )
    current = session.execute(locked).mappings().first()
    if current is None:
        raise Problem("not-found")
    check_version(int(current["row_version"]))
    rule_id = customers.RULE_GROUP
    errors: list[ProblemError] = []
    values: dict[str, Any] = {}
    for key in GROUP_NOT_NULL:
        if key in changes and changes[key] is None:
            errors.append(ProblemError(field=key, rule_id=rule_id, message=VALUE_REQUIRED))
    if changes.get("code") is not None and changes["code"] != current["code"]:
        values["code"] = str(changes["code"])
        errors += _group_code_errors(session, values["code"], group_id=group_id)
    if changes.get("name") is not None:
        values["name"] = _label(changes["name"], field="name", rule_id=rule_id, errors=errors)
    if "description" in changes:
        values["description"] = _optional_text(changes["description"])
    if errors:
        raise Problem("validation-failed", errors=errors)
    changed = {key: value for key, value in values.items() if value != current[key]}
    if changed:
        principal = uow.principal
        session.execute(
            update(related_party_group)
            .where(related_party_group.c.id == group_id)
            .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
        )
        uow.audit(
            action=GROUP_UPDATE_ACTION,
            object_type=GROUP_OBJECT,
            object_id=group_id,
            object_version=str(int(current["row_version"]) + 1),
            before=_audit_members({key: current[key] for key in changed}),
            after=_audit_members(changed),
        )
    return _group_out(session, group_id)


def create_customer(
    uow: UnitOfWork, *, body: CustomerIn, source_system: SourceSystem | None = None
) -> CustomerOut:
    """``POST /customers``: 422 ``validation-failed`` lists every finding (DG-CMD-03).

    ``source_system`` names the channel of an import or adapter sync, such as
    ``LEGACY_TEMPLATE_V1`` (T-REF-19 legacy note), and takes precedence over the request member.
    Without either, the principal kind decides, as for accounts (L1-1-Q-8).
    """
    session = uow.session
    rule_id = customers.RULE_CUSTOMER
    errors = _customer_code_errors(session, body.code, customer_id=None)
    label = _label(body.name, field="name", rule_id=rule_id, errors=errors)
    if body.related_party_group_id is not None:
        errors += _group_errors(session, body.related_party_group_id)
    if body.parent_customer_id is not None:
        errors += _parent_customer_errors(
            session, parent_id=body.parent_customer_id, customer_id=None
        )
    errors += customers.country_code_errors(body.country_code)
    channel = source_system or body.source_system or _account_source(uow)
    if body.external_id is not None:
        errors += _external_id_errors(session, channel, body.external_id)
    if errors:
        raise Problem("validation-failed", errors=errors)

    customer_id = new_id()
    values: dict[str, Any] = {
        "code": body.code,
        "name": label,
        "related_party_group_id": body.related_party_group_id,
        "parent_customer_id": body.parent_customer_id,
        "credit_grade": _optional_text(body.credit_grade),
        "segment": _optional_text(body.segment),
        "country_code": body.country_code,
        "source_system": channel.value,
        "external_id": body.external_id,
        "is_active": body.is_active,
    }
    session.execute(
        insert(customer).values(
            tenant_id=uow.principal.tenant_id, id=customer_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=CUSTOMER_CREATE_ACTION,
        object_type=CUSTOMER_OBJECT,
        object_id=customer_id,
        object_version="1",
        after=_audit_members(values),
    )
    return _customer_out(session, customer_id)


def update_customer(
    uow: UnitOfWork,
    *,
    customer_id: UUID,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> CustomerOut:
    """``PATCH /customers/{id}``: change a customer's code, name, group, parent, credit grade,
    segment or country, or (de)activate it; ``source_system`` and ``external_id`` do not change.
    404 ``not-found`` for a customer the caller cannot see; ``If-Match`` through
    ``check_version``; an unchanged request writes nothing."""
    session = uow.session
    locked = select(*queries.CUSTOMER_COLUMNS).where(customer.c.id == customer_id).with_for_update()
    current = session.execute(locked).mappings().first()
    if current is None:
        raise Problem("not-found")
    check_version(int(current["row_version"]))
    rule_id = customers.RULE_CUSTOMER
    errors: list[ProblemError] = []
    values: dict[str, Any] = {}
    for key in CUSTOMER_NOT_NULL:
        if key in changes and changes[key] is None:
            errors.append(ProblemError(field=key, rule_id=rule_id, message=VALUE_REQUIRED))
    if changes.get("code") is not None and changes["code"] != current["code"]:
        values["code"] = str(changes["code"])
        errors += _customer_code_errors(session, values["code"], customer_id=customer_id)
    if changes.get("name") is not None:
        values["name"] = _label(changes["name"], field="name", rule_id=rule_id, errors=errors)
    if "related_party_group_id" in changes:
        group = changes["related_party_group_id"]
        group_id = None if group is None else UUID(str(group))
        if group_id is not None:
            errors += _group_errors(session, group_id)
        values["related_party_group_id"] = group_id
    if "parent_customer_id" in changes:
        parent = changes["parent_customer_id"]
        parent_id = None if parent is None else UUID(str(parent))
        if parent_id is not None:
            errors += _parent_customer_errors(session, parent_id=parent_id, customer_id=customer_id)
        values["parent_customer_id"] = parent_id
    for key in CUSTOMER_FREE_TEXT:
        if key in changes:
            values[key] = _optional_text(changes[key])
    if "country_code" in changes:
        errors += customers.country_code_errors(changes["country_code"])
        values["country_code"] = changes["country_code"]
    if changes.get("is_active") is not None:
        values["is_active"] = bool(changes["is_active"])
    if errors:
        raise Problem("validation-failed", errors=errors)
    changed = {key: value for key, value in values.items() if value != current[key]}
    if changed:
        principal = uow.principal
        session.execute(
            update(customer)
            .where(customer.c.id == customer_id)
            .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
        )
        uow.audit(
            action=CUSTOMER_UPDATE_ACTION,
            object_type=CUSTOMER_OBJECT,
            object_id=customer_id,
            object_version=str(int(current["row_version"]) + 1),
            before=_audit_members({key: current[key] for key in changed}),
            after=_audit_members(changed),
        )
    return _customer_out(session, customer_id)


# --- legal entities, books and period states (04 API-R-17, API-R-18; BUILD_SPEC RFD-2) ---------

ENTITY_OBJECT: Final = "legal_entity"
ENTITY_CREATE_ACTION: Final = "legal_entity.create"
ENTITY_UPDATE_ACTION: Final = "legal_entity.update"
BOOK_OBJECT: Final = "book"
BOOK_UPDATE_ACTION: Final = "book.update"
ENTITY_BOOK_OBJECT: Final = "entity_book"
ENTITY_BOOK_CREATE_ACTION: Final = "entity_book.create"
ENTITY_BOOK_UPDATE_ACTION: Final = "entity_book.update"
ENTITY_NOT_NULL: Final = ("name", "functional_currency", "time_zone", "is_active")
BOOK_NOT_NULL: Final = ("name", "is_enabled", "posting_target")
VersionCheck = Callable[[int], None]


def _authorize_reference(
    uow: UnitOfWork, *, action: str, object_type: str, object_id: UUID | None
) -> None:
    """Any of ``masterdata.maintain`` and ``settings.manage`` (API-R-17, API-R-18)."""
    authorize(
        uow.ctx,
        MAINTAIN_PERMISSIONS,
        keyring=uow.keyring,
        action=action,
        object_type=object_type,
        object_id=object_id,
    )


def _currency_errors(session: Session, code: str) -> list[ProblemError]:
    statement = select(currency.c.code).where(
        currency.c.code == code, currency.c.is_active.is_(True)
    )
    if session.execute(statement).first() is not None:
        return []
    return [
        ProblemError(
            field="functional_currency",
            rule_id=entities.RULE_ENTITY,
            message=entities.CURRENCY_UNKNOWN,
        )
    ]


def _parent_entity_errors(
    session: Session, *, parent_id: UUID, entity_id: UUID | None
) -> list[ProblemError]:
    """The parent is a visible entity, and not the entity itself or below it."""
    field, rule_id = "parent_entity_id", entities.RULE_ENTITY
    statement = select(legal_entity.c.id, legal_entity.c.parent_entity_id)
    parents = {row["id"]: row["parent_entity_id"] for row in session.execute(statement).mappings()}
    if parent_id not in parents:
        return [ProblemError(field=field, rule_id=rule_id, message=entities.PARENT_UNKNOWN)]
    ancestor: UUID | None = parent_id
    seen: set[UUID] = set()
    while ancestor is not None and ancestor not in seen:
        if ancestor == entity_id:
            return [ProblemError(field=field, rule_id=rule_id, message=entities.PARENT_CYCLE)]
        seen.add(ancestor)
        ancestor = parents.get(ancestor)
    return []


def _first_period(
    session: Session, *, calendar_id: UUID, period_key: str | None, empty_field: str
) -> tuple[dict[str, Any] | None, list[ProblemError]]:
    """Period ``period_key`` of the calendar, by default its earliest period (T-REF-03)."""
    columns = (period.c.id, period.c.period_key, period.c.start_date)
    if period_key is not None:
        statement = select(*columns).where(
            period.c.calendar_id == calendar_id, period.c.period_key == period_key
        )
        row = session.execute(statement).mappings().first()
        if row is None:
            error = ProblemError(
                field="first_period_key",
                rule_id=books.RULE_ENTITY_BOOK,
                message=books.PERIOD_UNKNOWN,
            )
            return None, [error]
        return dict(row), []
    earliest = (
        select(*columns)
        .where(period.c.calendar_id == calendar_id)
        .order_by(period.c.start_date)
        .limit(1)
    )
    row = session.execute(earliest).mappings().first()
    if row is None:
        error = ProblemError(
            field=empty_field, rule_id=entities.RULE_ENTITY, message=entities.CALENDAR_EMPTY
        )
        return None, [error]
    return dict(row), []


def _first_period_errors(
    session: Session,
    *,
    entity_id: UUID,
    code: BookCode,
    first_key: str,
    first_start: date,
    field: str = "first_period_key",
) -> list[ProblemError]:
    """04 T-REF-03 rev 1.123 (PRD ERR-61; supervisor ruling R-58 (b)): a book an entity begins to
    keep, or keeps again, does not start after a contract of the entity began.

    A computation's calendar starts at its group's inception period (05 RCP-15), the periods before
    a book's first period carry no state for it (T-REF-06), and the engine refuses such a period
    (ENGINE_SPEC CV-13), so the contract could not be computed in any book. The date is the earlier
    of the contract's inception and its combination group's; contracts of every status count.
    """
    grouped = contract.outerjoin(
        combination_group,
        and_(
            combination_group.c.tenant_id == contract.c.tenant_id,
            combination_group.c.id == contract.c.combination_group_id,
        ),
    )
    began = func.least(contract.c.inception_date, combination_group.c.inception_date)
    earliest = session.execute(
        select(contract.c.external_id, began.label("began"), legal_entity.c.code)
        .select_from(
            grouped.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == contract.c.tenant_id,
                    legal_entity.c.id == contract.c.contracting_entity_id,
                ),
            )
        )
        .where(contract.c.contracting_entity_id == entity_id)
        .order_by(began, contract.c.external_id)
        .limit(1)
    ).first()
    if earliest is None or first_start <= earliest.began:
        return []
    message = books.FIRST_PERIOD_AFTER_CONTRACT.format(
        entity=earliest.code,
        date=earliest.began.isoformat(),
        contract=earliest.external_id,
        period_key=first_key,
        book=books.BOOK_NAMES[code],
    )
    return [ProblemError(field=field, rule_id=books.RULE_ENTITY_BOOK, message=message)]


def _step1_gate_errors(
    session: Session, *, entity_id: UUID, code: BookCode, field: str = "code"
) -> list[ProblemError]:
    """04 T-REF-03 rev 1.123 (PRD ERR-62; supervisor ruling R-61 (f), STEP1-BOOK-ADOPTION-1): an
    entity does not begin to keep a book, or keep it again, while a contract that would be computed
    in that book is behind the not-a-contract gate (header ``NOT_A_CONTRACT``).

    A group is computed in every enabled book kept by an entity of the group, and the whole stream
    is replayed there; the gate's assessments name the books that existed, so in the new book the
    engine would activate the contract at its next event with no approved activation (R-20 (d)).
    The contracts are those of every combination group with a member the entity contracts.
    """
    groups = select(contract.c.combination_group_id).where(
        contract.c.contracting_entity_id == entity_id
    )
    gated = session.execute(
        select(contract.c.external_id)
        .where(
            contract.c.combination_group_id.in_(groups),
            contract.c.status == ContractStatus.NOT_A_CONTRACT.value,
        )
        .order_by(contract.c.external_id)
        .limit(1)
    ).scalar_one_or_none()
    if gated is None:
        return []
    entity_code = session.execute(
        select(legal_entity.c.code).where(legal_entity.c.id == entity_id)
    ).scalar_one()
    message = books.CONTRACT_BEHIND_GATE.format(
        contract=gated, entity=entity_code, book=books.BOOK_NAMES[code]
    )
    return [ProblemError(field=field, rule_id=books.RULE_ENTITY_BOOK, message=message)]


def _adoption_errors(
    session: Session,
    *,
    entity_id: UUID,
    code: BookCode,
    first_key: str,
    first_start: date,
    field: str | None = None,
) -> list[ProblemError]:
    """The refusals of 04 T-REF-03 rev 1.123 when an entity begins to keep a book or keeps it
    again: a contract behind the not-a-contract gate (ERR-62), then a first period that starts
    after a contract began (ERR-61). ``field`` names the request member of a route without
    ``first_period_key`` (``PATCH /books/{code}``: ``is_enabled``).

    Both read the contracts as fresh statements after the caller locked the tenant's ``book`` row
    ``FOR UPDATE`` (supervisor ruling R-80): a gate decision holds every ``book`` row ``FOR SHARE``
    to its commit, so the two never interleave. No combination-group or contract row is locked
    here or later in the transaction (dev-guide DG-KRN-DB-08).
    """
    gate = {} if field is None else {"field": field}
    return [
        *_step1_gate_errors(session, entity_id=entity_id, code=code, **gate),
        *_first_period_errors(
            session,
            entity_id=entity_id,
            code=code,
            first_key=first_key,
            first_start=first_start,
            **gate,
        ),
    ]


def _sync_period_states(
    uow: UnitOfWork, *, entity_id: UUID, book_code: str, calendar_id: UUID, first_start: date
) -> int:
    """Insert the missing ``future`` states of a kept book from its first period on, each with its
    NULL → ``future`` transition, and audit the transitions in one AUD-FACT summary. Answers how
    many states it wrote."""
    session = uow.session
    principal = uow.principal
    statement = (
        select(period.c.id, period.c.end_date)
        .where(period.c.calendar_id == calendar_id, period.c.start_date >= first_start)
        .order_by(period.c.start_date)
    )
    rows = [
        {
            "tenant_id": principal.tenant_id,
            "id": new_id(),
            "entity_id": entity_id,
            "book_code": book_code,
            "period_id": found["id"],
            "period_end_date": found["end_date"],
            "state": PeriodState.FUTURE.value,
            "state_changed_at": uow.now,
            "updated_at": uow.now,
            "updated_by": principal.id,
            "updated_by_kind": principal.kind.value,
        }
        for found in session.execute(statement).mappings()
    ]
    if not rows:
        return 0
    inserted = session.execute(
        pg_insert(period_state)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["tenant_id", "entity_id", "book_code", "period_id"])
        .returning(period_state.c.id, period_state.c.period_id)
    ).all()
    if not inserted:
        return 0
    transitions = [
        {
            "tenant_id": principal.tenant_id,
            "id": new_id(),
            "period_state_id": state_id,
            "entity_id": entity_id,
            "book_code": book_code,
            "period_id": period_id,
            "from_state": None,
            "to_state": PeriodState.FUTURE.value,
            "created_at": uow.now,
            "created_by": principal.id,
            "created_by_kind": principal.kind.value,
        }
        for state_id, period_id in inserted
    ]
    session.execute(insert(period_state_transition), transitions)
    audit_writer.record_facts(
        uow,
        action=period_rules.CREATE_TRANSITIONS_ACTION,
        object_type=period_rules.TRANSITION_OBJECT,
        ids=[row["id"] for row in transitions],
        detail={
            "entity_id": str(entity_id),
            "book_code": book_code,
            "to_state": PeriodState.FUTURE.value,
        },
    )
    return len(inserted)


def _sync_calendar_states(uow: UnitOfWork, calendar_id: UUID) -> int:
    """``_sync_period_states`` for every enabled entity book on the calendar, WHOEVER asks, and
    how many states that wrote.

    The periods of a year are the calendar's and every entity on it computes into them, so the
    write is complete by its own statement and not by what the caller's session reads: the kept
    books are read, and their states written, under the tenant's scope
    (``every_entity_scope``; dev-guide DG-KRN-DB-05, DG-ARC-16). Until the supervisor's ruling
    of 2026-10-02 the statement ran under the caller's entity scope ([J] L1-1-Q-18): a year
    generated by a member of one entity left every other entity's periods without a state, and
    the engine quarantined the first contract dated into one (ENGINE_SPEC CV-13). Nothing of
    another entity is answered to the caller: a count."""
    with every_entity_scope(uow.session, uow.principal.db_context):
        return _calendar_states(uow, calendar_id)


def _calendar_states(uow: UnitOfWork, calendar_id: UUID) -> int:
    statement = (
        select(entity_book.c.entity_id, entity_book.c.book_code, period.c.start_date)
        .select_from(
            entity_book.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == entity_book.c.tenant_id,
                    legal_entity.c.id == entity_book.c.entity_id,
                ),
            ).join(
                period,
                and_(
                    period.c.tenant_id == entity_book.c.tenant_id,
                    period.c.id == entity_book.c.first_period_id,
                ),
            )
        )
        .where(legal_entity.c.calendar_id == calendar_id, entity_book.c.is_enabled.is_(True))
        .order_by(entity_book.c.entity_id, entity_book.c.book_code)
    )
    kept = [dict(row) for row in uow.session.execute(statement).mappings()]
    return sum(
        _sync_period_states(
            uow,
            entity_id=found["entity_id"],
            book_code=str(found["book_code"]),
            calendar_id=calendar_id,
            first_start=found["start_date"],
        )
        for found in kept
    )


def _entity_out(session: Session, entity_id: UUID) -> EntityOut:
    row = queries.entity_row(session, entity_id)
    if row is None:
        raise Problem("not-found")
    return EntityOut.model_validate(row)


def _keep_book(
    uow: UnitOfWork,
    *,
    entity_id: UUID,
    book_code: str,
    first_period: Mapping[str, Any],
    calendar_id: UUID,
) -> None:
    """Insert the T-REF-03 row of a newly kept book and its period states."""
    values: dict[str, Any] = {
        "entity_id": entity_id,
        "book_code": book_code,
        "first_period_id": first_period["id"],
        "is_enabled": True,
    }
    entity_book_id = new_id()
    uow.session.execute(
        insert(entity_book).values(
            tenant_id=uow.principal.tenant_id, id=entity_book_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=ENTITY_BOOK_CREATE_ACTION,
        object_type=ENTITY_BOOK_OBJECT,
        object_id=entity_book_id,
        object_version="1",
        after=_audit_members({**values, "first_period_key": first_period["period_key"]}),
    )
    _sync_period_states(
        uow,
        entity_id=entity_id,
        book_code=book_code,
        calendar_id=calendar_id,
        first_start=first_period["start_date"],
    )


def create_entity(uow: UnitOfWork, *, body: EntityIn) -> EntityOut:
    """``POST /entities``: 422 ``validation-failed`` lists every finding (DG-CMD-03). The entity
    keeps the primary book from ``first_period_key``, by default the calendar's earliest period,
    and gets its gapless ``JE`` series (04 §14.3). A new entity is the workspace's: the
    permission for all entities, asked before the body is read — so the check of the code sees
    every entity."""
    if _lacks_workspace(
        uow, action=ENTITY_CREATE_ACTION, object_type=ENTITY_OBJECT, object_id=None
    ):
        audit_writer.record_denied(
            uow.ctx,
            action=ENTITY_CREATE_ACTION,
            object_type=ENTITY_OBJECT,
            object_id=None,
            **_scope_denied(uow, all_entities=True),
        )
        raise users.beyond_scope(ENTITY_CREATE_BEYOND_SCOPE)
    session = uow.session
    rule_id = entities.RULE_ENTITY
    errors: list[ProblemError] = []
    if not CODE_PATTERN.fullmatch(body.code):
        errors.append(ProblemError(field="code", rule_id=rule_id, message=CODE_FORMAT))
    else:
        taken = select(legal_entity.c.id).where(legal_entity.c.code == body.code).limit(1)
        if session.execute(taken).first() is not None:
            errors.append(ProblemError(field="code", rule_id=rule_id, message=entities.CODE_TAKEN))
    label = _label(body.name, field="name", rule_id=rule_id, errors=errors)
    errors += _currency_errors(session, body.functional_currency)
    errors += entities.time_zone_errors(body.time_zone)
    first: dict[str, Any] | None = None
    calendar = select(fiscal_calendar.c.id).where(fiscal_calendar.c.id == body.calendar_id)
    if session.execute(calendar).first() is None:
        errors.append(
            ProblemError(field="calendar_id", rule_id=rule_id, message=entities.CALENDAR_UNKNOWN)
        )
    else:
        first, first_errors = _first_period(
            session,
            calendar_id=body.calendar_id,
            period_key=body.first_period_key,
            empty_field="calendar_id",
        )
        errors += first_errors
    if body.parent_entity_id is not None:
        errors += _parent_entity_errors(session, parent_id=body.parent_entity_id, entity_id=None)
    errors += entities.country_code_errors(body.country_code)
    if errors or first is None:
        raise Problem("validation-failed", errors=errors)

    entity_id = new_id()
    values: dict[str, Any] = {
        "code": body.code,
        "name": label,
        "functional_currency": body.functional_currency,
        "time_zone": body.time_zone,
        "calendar_id": body.calendar_id,
        "parent_entity_id": body.parent_entity_id,
        "country_code": body.country_code,
        "tax_id": body.tax_id,
        "is_active": body.is_active,
    }
    session.execute(
        insert(legal_entity).values(
            tenant_id=uow.principal.tenant_id, id=entity_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=ENTITY_CREATE_ACTION,
        object_type=ENTITY_OBJECT,
        object_id=entity_id,
        object_version="1",
        after=_audit_members(values),
    )
    numbering.ensure_entity_series(uow, entity_id, body.code)
    _keep_book(
        uow,
        entity_id=entity_id,
        book_code=queries.primary_book_code(session),
        first_period=first,
        calendar_id=body.calendar_id,
    )
    setup.evaluate_setup_completion(uow)  # BR-PLT-02 (BUILD_SPEC RFD-19)
    return _entity_out(session, entity_id)


def update_entity(
    uow: UnitOfWork,
    *,
    entity_id: UUID,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> EntityOut:
    """``PATCH /entities/{id}``: lock the row, apply ``If-Match`` through ``check_version``,
    validate the members sent, then write and audit the changed members.

    ``functional_currency`` and ``time_zone`` change while no posting of the entity exists; CTR-3
    adds the DB-05 freeze (BS3-D-07). 404 ``not-found`` outside the principal's scope; 403 by
    name for an entity the caller reads and holds neither permission for (``_lacks_entity``).
    """
    _authorize_reference(
        uow, action=ENTITY_UPDATE_ACTION, object_type=ENTITY_OBJECT, object_id=entity_id
    )
    session = uow.session
    locked = select(*queries.ENTITY_COLUMNS).where(legal_entity.c.id == entity_id).with_for_update()
    current = session.execute(locked).mappings().first()
    if current is None:
        raise Problem("not-found")
    if _lacks_entity(uow, entity_id):
        audit_writer.record_denied(
            uow.ctx,
            action=ENTITY_UPDATE_ACTION,
            object_type=ENTITY_OBJECT,
            object_id=entity_id,
            **_scope_denied(uow, all_entities=False),
        )
        raise users.beyond_scope(ENTITY_BEYOND_SCOPE)
    check_version(int(current["row_version"]))
    rule_id = entities.RULE_ENTITY
    errors: list[ProblemError] = []
    values: dict[str, Any] = {}
    for key in ENTITY_NOT_NULL:
        if key in changes and changes[key] is None:
            errors.append(ProblemError(field=key, rule_id=rule_id, message=VALUE_REQUIRED))
    if changes.get("name") is not None:
        values["name"] = _label(changes["name"], field="name", rule_id=rule_id, errors=errors)
    if changes.get("functional_currency") is not None:
        values["functional_currency"] = str(changes["functional_currency"])
        errors += _currency_errors(session, values["functional_currency"])
    if changes.get("time_zone") is not None:
        values["time_zone"] = str(changes["time_zone"])
        errors += entities.time_zone_errors(values["time_zone"])
    if "parent_entity_id" in changes:
        parent = changes["parent_entity_id"]
        parent_id = None if parent is None else UUID(str(parent))
        if parent_id is not None:
            errors += _parent_entity_errors(session, parent_id=parent_id, entity_id=entity_id)
        values["parent_entity_id"] = parent_id
    if "country_code" in changes:
        values["country_code"] = changes["country_code"]
        errors += entities.country_code_errors(changes["country_code"])
    if "tax_id" in changes:
        values["tax_id"] = changes["tax_id"]
    if changes.get("is_active") is not None:
        values["is_active"] = bool(changes["is_active"])
    if errors:
        raise Problem("validation-failed", errors=errors)
    changed = {key: value for key, value in values.items() if value != current[key]}
    if changed:
        principal = uow.principal
        session.execute(
            update(legal_entity)
            .where(legal_entity.c.id == entity_id)
            .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
        )
        uow.audit(
            action=ENTITY_UPDATE_ACTION,
            object_type=ENTITY_OBJECT,
            object_id=entity_id,
            object_version=str(int(current["row_version"]) + 1),
            before=_audit_members({key: current[key] for key in changed}),
            after=_audit_members(changed),
        )
    return _entity_out(session, entity_id)


def _enable_tenant_book(uow: UnitOfWork, tenant_book: Mapping[Any, Any]) -> None:
    """[J] Keeping a book enables it for the tenant (SCREENS_B SF-15:entities binds only
    ``PUT /entities/{id}/books/{code}``; L1-1-Q-14)."""
    if tenant_book["is_enabled"]:
        return
    principal = uow.principal
    uow.session.execute(
        update(book)
        .where(book.c.id == tenant_book["id"])
        .values(is_enabled=True, updated_by=principal.id, updated_by_kind=principal.kind.value)
    )
    uow.audit(
        action=BOOK_UPDATE_ACTION,
        object_type=BOOK_OBJECT,
        object_id=tenant_book["id"],
        object_version=str(int(tenant_book["row_version"]) + 1),
        before={"is_enabled": False},
        after={"is_enabled": True},
    )


def update_book(
    uow: UnitOfWork,
    *,
    code: BookCode,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> BookOut:
    """``PATCH /books/{code}``: rename a book, change its posting target or (de)activate it.

    The Legacy book posts nothing (T-REF-02 check); the primary book stays enabled; a book an
    enabled entity book keeps is not disabled. Enabling a book that entity rows still keep is an
    adoption for each of those entities and takes the guards of ``put_entity_book`` (04 T-REF-03
    rev 1.123; supervisor ruling R-80): 422 ``validation-failed`` on ``is_enabled``. A book is
    the workspace's: the permission for all entities, so the guards read every entity that
    keeps it.
    """
    if _lacks_workspace(uow, action=BOOK_UPDATE_ACTION, object_type=BOOK_OBJECT, object_id=None):
        audit_writer.record_denied(
            uow.ctx,
            action=BOOK_UPDATE_ACTION,
            object_type=BOOK_OBJECT,
            object_id=None,
            **_scope_denied(uow, all_entities=True),
        )
        raise users.beyond_scope(BOOK_BEYOND_SCOPE)
    session = uow.session
    locked = select(*queries.BOOK_COLUMNS).where(book.c.code == code.value).with_for_update()
    current = session.execute(locked).mappings().first()
    if current is None:
        raise Problem("not-found")
    check_version(int(current["row_version"]))
    rule_id = books.RULE_BOOK
    errors: list[ProblemError] = []
    values: dict[str, Any] = {}
    for key in BOOK_NOT_NULL:
        if key in changes and changes[key] is None:
            errors.append(ProblemError(field=key, rule_id=rule_id, message=VALUE_REQUIRED))
    if changes.get("name") is not None:
        values["name"] = _label(changes["name"], field="name", rule_id=rule_id, errors=errors)
    if changes.get("posting_target") is not None:
        values["posting_target"] = str(changes["posting_target"])
        errors += books.posting_target_errors(code, values["posting_target"])
    if changes.get("is_enabled") is False:
        if current["is_primary"]:
            errors.append(
                ProblemError(field="is_enabled", rule_id=rule_id, message=books.PRIMARY_ENABLED)
            )
        else:
            keeping = (
                select(legal_entity.c.code)
                .select_from(
                    entity_book.join(
                        legal_entity,
                        and_(
                            legal_entity.c.tenant_id == entity_book.c.tenant_id,
                            legal_entity.c.id == entity_book.c.entity_id,
                        ),
                    )
                )
                .where(entity_book.c.book_code == code.value, entity_book.c.is_enabled.is_(True))
                .order_by(legal_entity.c.code)
            )
            kept_by = [str(found) for found in session.execute(keeping).scalars()]
            if kept_by:
                message = books.BOOK_KEPT.format(codes=", ".join(kept_by))
                errors.append(
                    ProblemError(
                        field="is_enabled", rule_id=books.RULE_ENTITY_BOOK, message=message
                    )
                )
    if changes.get("is_enabled") is True and not current["is_enabled"] and not errors:
        # Supervisor ruling R-80: enabling a tenant book that entity rows still keep is the same
        # adoption as ``PUT /entities/{id}/books/{code}`` and takes the same guards, read after
        # the ``book`` row lock above (04 T-REF-03 rev 1.123; PRD ERR-61, ERR-62).
        keeping = (
            queries.entity_book_select()
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == entity_book.c.tenant_id,
                    legal_entity.c.id == entity_book.c.entity_id,
                ),
            )
            .where(entity_book.c.book_code == code.value, entity_book.c.is_enabled.is_(True))
            .order_by(legal_entity.c.code)
        )
        for kept in session.execute(keeping).mappings().all():
            errors += _adoption_errors(
                session,
                entity_id=UUID(str(kept["entity_id"])),
                code=code,
                first_key=str(kept["first_period_key"]),
                first_start=kept["first_period_start_date"],
                field="is_enabled",
            )
    if changes.get("is_enabled") is not None:
        values["is_enabled"] = bool(changes["is_enabled"])
    if errors:
        raise Problem("validation-failed", errors=errors)
    changed = {key: value for key, value in values.items() if value != current[key]}
    if changed:
        principal = uow.principal
        session.execute(
            update(book)
            .where(book.c.id == current["id"])
            .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
        )
        uow.audit(
            action=BOOK_UPDATE_ACTION,
            object_type=BOOK_OBJECT,
            object_id=current["id"],
            object_version=str(int(current["row_version"]) + 1),
            before=_audit_members({key: current[key] for key in changed}),
            after=_audit_members(changed),
        )
    row = queries.book_row(session, code.value)
    if row is None:
        raise Problem("not-found")
    return BookOut.model_validate(row)


def put_entity_book(
    uow: UnitOfWork, *, entity_id: UUID, code: BookCode, body: EntityBookIn
) -> EntityBookOut:
    """``PUT /entities/{id}/books/{code}``: keep, re-enable or disable a book for an entity.

    A newly kept book starts at ``first_period_key``, by default the calendar's earliest period, and
    gets its period states; a kept book's first period does not change, and the primary book stays
    kept (L1-1-Q-14). Enabling fills missing states. A book that begins to be kept, or is kept
    again, does not start after a contract of the entity began, and is not kept while a contract
    that would be computed in it is behind the not-a-contract gate (04 T-REF-03 rev 1.123): 422
    ``validation-failed`` on ``first_period_key`` or ``code``. 404 ``not-found`` outside the
    principal's scope; 403 by name for an entity the caller reads and holds neither permission
    for. Keeping a book enables it for the workspace where it is not enabled
    (``_enable_tenant_book``): that is the workspace's act and asks the permission for all
    entities; where the workspace's book is enabled, the entity's permission suffices.
    """
    _authorize_reference(
        uow, action=ENTITY_BOOK_UPDATE_ACTION, object_type=ENTITY_BOOK_OBJECT, object_id=None
    )
    session = uow.session
    entity = (
        session.execute(
            select(legal_entity.c.id, legal_entity.c.calendar_id).where(
                legal_entity.c.id == entity_id
            )
        )
        .mappings()
        .first()
    )
    if entity is None:
        raise Problem("not-found")
    if _lacks_entity(uow, entity_id):
        audit_writer.record_denied(
            uow.ctx,
            action=ENTITY_BOOK_UPDATE_ACTION,
            object_type=ENTITY_BOOK_OBJECT,
            object_id=None,
            **_scope_denied(uow, all_entities=False),
        )
        raise users.beyond_scope(ENTITY_BEYOND_SCOPE)
    calendar_id = UUID(str(entity["calendar_id"]))
    tenant_book = (
        session.execute(
            select(*queries.BOOK_COLUMNS).where(book.c.code == code.value).with_for_update()
        )
        .mappings()
        .first()
    )
    if tenant_book is None:
        raise Problem("not-found")
    if body.is_enabled and not tenant_book["is_enabled"] and not _holds_workspace(uow):
        audit_writer.record_denied(
            uow.ctx,
            action=ENTITY_BOOK_UPDATE_ACTION,
            object_type=BOOK_OBJECT,
            object_id=tenant_book["id"],
            **_scope_denied(uow, all_entities=True),
        )
        raise users.beyond_scope(BOOK_ENABLE_BEYOND_SCOPE.format(book=books.BOOK_NAMES[code]))
    rule_id = books.RULE_ENTITY_BOOK
    current = (
        session.execute(
            queries.entity_book_select()
            .where(entity_book.c.entity_id == entity_id, entity_book.c.book_code == code.value)
            .with_for_update(of=entity_book)
        )
        .mappings()
        .first()
    )
    if current is None:
        if not body.is_enabled:
            error = ProblemError(field="is_enabled", rule_id=rule_id, message=books.NOT_KEPT)
            raise Problem("validation-failed", errors=[error])
        first, errors = _first_period(
            session,
            calendar_id=calendar_id,
            period_key=body.first_period_key,
            empty_field="first_period_key",
        )
        if errors or first is None:
            raise Problem("validation-failed", errors=errors)
        errors = _adoption_errors(
            session,
            entity_id=entity_id,
            code=code,
            first_key=str(first["period_key"]),
            first_start=first["start_date"],
        )
        if errors:
            raise Problem("validation-failed", errors=errors)
        _enable_tenant_book(uow, tenant_book)
        _keep_book(
            uow,
            entity_id=entity_id,
            book_code=code.value,
            first_period=first,
            calendar_id=calendar_id,
        )
    else:
        errors = []
        if (
            body.first_period_key is not None
            and body.first_period_key != current["first_period_key"]
        ):
            errors.append(
                ProblemError(
                    field="first_period_key", rule_id=rule_id, message=books.FIRST_PERIOD_FIXED
                )
            )
        if tenant_book["is_primary"] and not body.is_enabled:
            errors.append(
                ProblemError(field="is_enabled", rule_id=rule_id, message=books.PRIMARY_KEPT)
            )
        if not errors and body.is_enabled and not current["is_enabled"]:
            # Kept again: contracts booked while the book was disabled may begin before it, or
            # stand behind the not-a-contract gate.
            errors = _adoption_errors(
                session,
                entity_id=entity_id,
                code=code,
                first_key=str(current["first_period_key"]),
                first_start=current["first_period_start_date"],
            )
        if errors:
            raise Problem("validation-failed", errors=errors)
        if body.is_enabled != current["is_enabled"]:
            principal = uow.principal
            session.execute(
                update(entity_book)
                .where(entity_book.c.id == current["id"])
                .values(
                    is_enabled=body.is_enabled,
                    updated_by=principal.id,
                    updated_by_kind=principal.kind.value,
                )
            )
            uow.audit(
                action=ENTITY_BOOK_UPDATE_ACTION,
                object_type=ENTITY_BOOK_OBJECT,
                object_id=current["id"],
                object_version=str(int(current["row_version"]) + 1),
                before={"is_enabled": bool(current["is_enabled"])},
                after={"is_enabled": body.is_enabled},
            )
        if body.is_enabled:
            _enable_tenant_book(uow, tenant_book)
            _sync_period_states(
                uow,
                entity_id=entity_id,
                book_code=code.value,
                calendar_id=calendar_id,
                first_start=current["first_period_start_date"],
            )
    row = queries.entity_book_row(session, entity_id, code.value)
    if row is None:
        raise Problem("not-found")
    return EntityBookOut.model_validate(row)


def open_period(
    uow: UnitOfWork, *, state_id: UUID, body: PeriodOpenIn, check_version: Callable[[int], None]
) -> PeriodOut:
    """``POST /periods/{id}/open``: ``future`` → ``open`` with one transition row (DB-07).

    Authorised by ``period.close``, or by ``settings.manage`` while setup is incomplete — the
    stamp is not set and the conditions of PRD BR-PLT-02 do not hold (``setup.rule_ended``;
    API-R-18). 404 ``not-found`` outside the principal's scope; ``If-Match`` through
    ``check_version``; 409 ``invalid-transition`` unless the state is ``future``, the entity keeps
    the book enabled and the previous period of the entity and book is not ``future`` (PRD
    SM-07).
    """
    # The setup rule ends when the conditions of PRD BR-PLT-02 hold, stamped or not (04
    # T-PLT-01; item APR-SETUP-RULE-2): the command asks them where it asked the stamp.
    completed = setup.rule_ended(uow)
    authorize(
        uow.ctx,
        period_rules.open_permissions(setup_completed=completed),
        keyring=uow.keyring,
        action=period_rules.OPEN_ACTION,
        object_type=period_rules.STATE_OBJECT,
        object_id=state_id,
    )
    return open_future_period(
        uow,
        state_id=state_id,
        comment=body.comment,
        check_version=check_version,
        held_for=period_rules.open_permissions(setup_completed=completed),
    ).period


def _previous_period_future(
    session: Any, *, entity_id: UUID, book_code: str, period_id: UUID
) -> bool:
    """PRD SM-07 guard on ``future → open``: whether the period state that precedes the period
    for the same entity and book is ``future``. The first period a book keeps has no previous
    state and opens freely."""
    start_date = session.execute(
        select(period.c.start_date).where(period.c.id == period_id)
    ).scalar_one()
    previous = session.execute(
        select(period_state.c.state)
        .select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            )
        )
        .where(
            period_state.c.entity_id == entity_id,
            period_state.c.book_code == book_code,
            period.c.start_date < start_date,
        )
        .order_by(period.c.start_date.desc())
        .limit(1)
    ).scalar_one_or_none()
    return previous is not None and PeriodState(str(getattr(previous, "value", previous))) is (
        PeriodState.FUTURE
    )


@dataclass(frozen=True, slots=True)
class PeriodOpening:
    """What one ``future`` → ``open`` transition did: the opened period and the number of clean
    combination groups it re-marked dirty (SCH-06; ``period_redirty``)."""

    period: PeriodOut
    redirtied: int


def open_future_period(
    uow: UnitOfWork,
    *,
    state_id: UUID,
    comment: str | None,
    check_version: Callable[[int], None] | None = None,
    held_for: frozenset[str] | None = None,
) -> PeriodOpening:
    """The shared ``future`` → ``open`` transition body: one T-REF-07 row with ``reason_code``
    null (04 requires a reason only for closing → open and closed → reopened), the state row
    bumped, one audit event, BR-PLT-02 re-evaluated. ``open_period`` (POST /periods/{id}/open)
    calls it after authorisation with the ``If-Match`` check; SCH-05 ``period_auto_open`` calls
    it as SYSTEM without either (05 §SCH; record §4.29). 404 ``not-found`` for an unknown or
    hidden state; 409 ``invalid-transition`` unless the state is ``future``, the entity keeps the
    book enabled and the previous period of the entity and book is not ``future`` (PRD SM-07
    guard; supervisor ruling R-58 (d), item PERIOD-OPEN-GUARD-1): the periods of a book open in
    order, so no ``future`` period ever lies below a postable or closed one — the engine's
    posting stage stops at the first ``future`` period, and a book opened out of order posted
    nothing in any period."""
    session = uow.session
    locked = (
        select(
            period_state.c.entity_id,
            period_state.c.book_code,
            period_state.c.period_id,
            period_state.c.state,
            period_state.c.row_version,
        )
        .where(period_state.c.id == state_id)
        .with_for_update()
    )
    current = session.execute(locked).mappings().first()
    if current is None:
        raise Problem("not-found")
    # REQ-PLT-012 (supervisor ruling R-28; security finding S18): the command needs its permission
    # FOR the period's entity. A caller who sees the row through another role and holds the
    # permission for another entity alone is answered as for a row it does not see.
    if held_for is not None and not entity_scope.holds_for(
        uow.principal, sorted(held_for), UUID(str(current["entity_id"]))
    ):
        raise Problem("not-found")
    if check_version is not None:
        check_version(int(current["row_version"]))
    shown = queries.period_row(session, state_id)
    if shown is None:
        raise Problem("not-found")
    state = PeriodState(current["state"])
    if state is not PeriodState.FUTURE:
        message = period_rules.NOT_FUTURE.format(
            period_key=shown["period"]["period_key"], state=state.value
        )
        error = ProblemError(rule_id=period_rules.RULE_TRANSITION, message=message)
        raise Problem("invalid-transition", message, errors=[error])
    kept = session.execute(
        select(entity_book.c.is_enabled).where(
            entity_book.c.entity_id == current["entity_id"],
            entity_book.c.book_code == current["book_code"],
        )
    ).scalar_one_or_none()
    if kept is not True:
        message = period_rules.BOOK_NOT_KEPT.format(
            entity=shown["entity"]["code"], book=books.BOOK_NAMES[BookCode(current["book_code"])]
        )
        error = ProblemError(rule_id=books.RULE_ENTITY_BOOK, message=message)
        raise Problem("invalid-transition", message, errors=[error])
    if _previous_period_future(
        session,
        entity_id=UUID(str(current["entity_id"])),
        book_code=str(current["book_code"]),
        period_id=UUID(str(current["period_id"])),
    ):
        message = period_rules.PREVIOUS_FUTURE.format(
            entity=shown["entity"]["code"],
            book=str(current["book_code"]),
            period_key=shown["period"]["period_key"],
        )
        error = ProblemError(rule_id=period_rules.RULE_TRANSITION, message=message)
        raise Problem("invalid-transition", message, errors=[error])

    principal = uow.principal
    transition_id = new_id()
    session.execute(
        insert(period_state_transition).values(
            tenant_id=principal.tenant_id,
            id=transition_id,
            period_state_id=state_id,
            entity_id=current["entity_id"],
            book_code=current["book_code"],
            period_id=current["period_id"],
            from_state=PeriodState.FUTURE.value,
            to_state=PeriodState.OPEN.value,
            reason_code=None,
            comment=comment,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
        )
    )
    session.execute(
        update(period_state)
        .where(period_state.c.id == state_id)
        .values(
            state=PeriodState.OPEN.value,
            state_changed_at=uow.now,
            row_version=int(current["row_version"]) + 1,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    uow.audit(
        action=period_rules.OPEN_ACTION,
        object_type=period_rules.TRANSITION_OBJECT,
        object_id=transition_id,
        object_version="1",
        after={
            "period_state_id": str(state_id),
            "entity_id": str(current["entity_id"]),
            "book_code": str(current["book_code"]),
            "period_id": str(current["period_id"]),
            "from_state": PeriodState.FUTURE.value,
            "to_state": PeriodState.OPEN.value,
        },
        comment=comment,
    )
    # SCH-06 in the SAME transaction, on every path (Codex production-20260922-0349 §1): the
    # groups with events in the period, and the deferred closed origins for which this period is
    # the first later postable one, are re-marked dirty (RCP-04; T-PLT-46 partial-origin rule).
    bounds = session.execute(
        select(period.c.start_date, period.c.end_date).where(period.c.id == current["period_id"])
    ).one()
    entity_id = UUID(str(current["entity_id"]))
    book_code = str(current["book_code"])
    gap = period_redirty.deferred_gap(
        period_redirty.period_states_of(session, entity_id=entity_id, book_code=book_code),
        opened_start=bounds.start_date,
    )
    redirtied = period_redirty.redirty_groups(
        uow,
        entity_id=entity_id,
        book_code=book_code,
        period_id=UUID(str(current["period_id"])),
        start_date=bounds.start_date,
        end_date=bounds.end_date,
        gap_period_ids=gap,
    )
    setup.evaluate_setup_completion(uow)  # BR-PLT-02 (BUILD_SPEC RFD-19)
    opened = queries.period_row(session, state_id)
    if opened is None:
        raise Problem("not-found")
    return PeriodOpening(period=PeriodOut.model_validate(opened), redirtied=redirtied)


# --- currencies and FX rate sets (04 API-R-19, T-REF-09 to T-REF-12, DB-04; BUILD_SPEC RFD-3) ---

FX_PERMISSIONS: Final = frozenset({"config.author", "masterdata.maintain"})
RATES_OUTSIDE_COVERAGE: Final = "Some rates of the version lie outside this coverage."
# 04 T-REF-11 "The groups a changed rate reaches" (rev 1.297; item FX-REPUBLISH-DIRTY-1) and "A
# rate changed after a lock" (rev 1.291; item CLO-RATE-AFTER-RUN-1): what the approval of a
# version marks, and what it raises for the periods already closed. Registered here, where
# every version is submitted, so that no process decides a version without them — the mark
# FIRST: it takes contract group rows and the finding takes period-state rows, and group rows
# come before period-state rows, as a computation takes them (dev-guide DG-KRN-DB-08).
subjects.register_fx_rate_version_approved(rate_reach.marked)
subjects.register_fx_rate_version_approved(rate_changes.approved)


def _authorize_fx(uow: UnitOfWork, *, action: str, object_id: UUID | None) -> None:
    """Any of ``config.author`` and ``masterdata.maintain`` (API-R-19)."""
    object_type = fx.SET_OBJECT if action == fx.SET_CREATE else fx.VERSION_OBJECT
    authorize(
        uow.ctx,
        FX_PERMISSIONS,
        keyring=uow.keyring,
        action=action,
        object_type=object_type,
        object_id=object_id,
    )


def put_tenant_currencies(uow: UnitOfWork, *, body: TenantCurrenciesIn) -> list[TenantCurrencyOut]:
    """``PUT /tenant-currencies``: enable the listed currencies and disable the others (T-REF-09).

    The route's ``settings.manage`` guard authorises. Every finding is reported at once; the
    reporting currency must stay listed. Rows are inserted or updated, never deleted (IM-M), and
    each changed row writes one AUD-CMD event.
    """
    session = uow.session
    principal = uow.principal
    codes = list(body.currency_codes)
    errors: list[ProblemError] = []
    active = fx.active_currencies(session, codes)
    seen: set[str] = set()
    for index, code in enumerate(codes):
        field = f"currency_codes.{index}"
        if code not in active:
            message = fx.CURRENCY_UNKNOWN
        elif code in seen:
            message = fx.CURRENCY_TWICE
        else:
            seen.add(code)
            continue
        errors.append(ProblemError(field=field, rule_id=fx.RULE_TENANT_CURRENCY, message=message))
    reporting = str(
        session.execute(
            select(tenant.c.reporting_currency).where(tenant.c.id == principal.tenant_id)
        ).scalar_one()
    )
    if reporting not in codes:
        errors.append(
            ProblemError(
                field="currency_codes",
                rule_id=fx.RULE_TENANT_CURRENCY,
                message=fx.REPORTING_KEPT.format(code=reporting),
            )
        )
    if errors:
        raise Problem("validation-failed", errors=errors)

    existing = {
        str(code): bool(enabled)
        for code, enabled in session.execute(
            select(tenant_currency.c.currency_code, tenant_currency.c.is_enabled)
            .order_by(tenant_currency.c.currency_code)
            .with_for_update()
        ).tuples()
    }
    for code in sorted(seen - set(existing)):
        inserted = session.execute(
            pg_insert(tenant_currency)
            .values(
                tenant_id=principal.tenant_id, currency_code=code, is_enabled=True, **_stamps(uow)
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "currency_code"])
            .returning(tenant_currency.c.currency_code)
        ).scalar_one_or_none()
        if inserted is not None:
            uow.audit(
                action=fx.TENANT_CURRENCY_CREATE,
                object_type=fx.TENANT_CURRENCY_OBJECT,
                object_id=None,
                object_version="1",
                after={"currency_code": code, "is_enabled": True},
            )
    for code, enabled in existing.items():
        wanted = code in seen
        if enabled == wanted:
            continue
        session.execute(
            update(tenant_currency)
            .where(tenant_currency.c.currency_code == code)
            .values(
                is_enabled=wanted,
                updated_at=uow.now,
                updated_by=principal.id,
                updated_by_kind=principal.kind.value,
            )
        )
        uow.audit(
            action=fx.TENANT_CURRENCY_UPDATE,
            object_type=fx.TENANT_CURRENCY_OBJECT,
            object_id=None,
            before={"currency_code": code, "is_enabled": enabled},
            after={"currency_code": code, "is_enabled": wanted},
        )
    return [TenantCurrencyOut.model_validate(row) for row in queries.tenant_currency_rows(session)]


def create_fx_rate_set(uow: UnitOfWork, *, body: FxRateSetIn) -> FxRateSetOut:
    """``POST /fx-rate-sets``: 422 ``validation-failed`` lists every finding (DG-CMD-03)."""
    _authorize_fx(uow, action=fx.SET_CREATE, object_id=None)
    session = uow.session
    errors: list[ProblemError] = []
    if not CODE_PATTERN.fullmatch(body.code):
        errors.append(ProblemError(field="code", rule_id=fx.RULE_SET, message=CODE_FORMAT))
    else:
        taken = select(fx_rate_set.c.id).where(fx_rate_set.c.code == body.code).limit(1)
        if session.execute(taken).first() is not None:
            errors.append(
                ProblemError(field="code", rule_id=fx.RULE_SET, message=fx.SET_CODE_TAKEN)
            )
    label = _label(body.name, field="name", rule_id=fx.RULE_SET, errors=errors)
    errors += fx.source_errors(body.source)
    if errors:
        raise Problem("validation-failed", errors=errors)

    set_id = new_id()
    values: dict[str, Any] = {
        "code": body.code,
        "name": label,
        "rate_type": body.rate_type.value,
        "source": body.source,
    }
    session.execute(
        insert(fx_rate_set).values(
            tenant_id=uow.principal.tenant_id, id=set_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=fx.SET_CREATE,
        object_type=fx.SET_OBJECT,
        object_id=set_id,
        object_version="1",
        after=values,
    )
    return FxRateSetOut.model_validate(queries.fx_rate_set_row(session, set_id))


def _coverage_errors(coverage_from: date, coverage_to: date) -> list[ProblemError]:
    if coverage_to >= coverage_from:
        return []
    return [ProblemError(field="coverage_to", rule_id=fx.RULE_VERSION, message=fx.COVERAGE_ORDER)]


def _insert_rates(
    uow: UnitOfWork, version_id: UUID, rate_type: RateType, rows: Sequence[fx.RateRow]
) -> None:
    """Insert rates of a DRAFT version with one AUD-FACT summary naming them (T-REF-12)."""
    if not rows:
        return
    tenant_id = uow.principal.tenant_id
    ids = [new_id() for _ in rows]
    values: list[dict[str, Any]] = [
        {
            "tenant_id": tenant_id,
            "id": rate_id,
            "fx_rate_set_version_id": version_id,
            "rate_type": rate_type.value,
            "base_currency": row.base_currency,
            "quote_currency": row.quote_currency,
            "effective_date": row.effective_date,
            "period_id": row.period_id,
            "rate": row.rate,
            "is_derived": row.is_derived,
        }
        for rate_id, row in zip(ids, rows, strict=True)
    ]
    uow.session.execute(insert(fx_rate), values)
    audit_writer.record_facts(
        uow,
        action=fx.RATE_CREATE,
        object_type=fx.RATE_OBJECT,
        ids=ids,
        detail={
            "fx_rate_set_version_id": str(version_id),
            "is_derived": rows[0].is_derived,
        },
    )


def _locked_version(session: Session, version_id: UUID) -> dict[str, Any]:
    """The version row under ``FOR UPDATE`` with its set's code and rate type; 404 when it is not
    visible."""
    row = (
        session.execute(
            select(fx_rate_set_version)
            .where(fx_rate_set_version.c.id == version_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if row is None:
        raise Problem("not-found")
    rate_set = (
        session.execute(
            select(fx_rate_set.c.code, fx_rate_set.c.rate_type).where(
                fx_rate_set.c.id == row["fx_rate_set_id"]
            )
        )
        .mappings()
        .one()
    )
    return {
        **row,
        "fx_rate_set_code": rate_set["code"],
        "rate_type": RateType(rate_set["rate_type"]),
    }


def _entered_rates(session: Session, version_id: UUID) -> list[fx.RateRow]:
    statement = (
        select(
            fx_rate.c.base_currency,
            fx_rate.c.quote_currency,
            fx_rate.c.effective_date,
            fx_rate.c.period_id,
            fx_rate.c.rate,
        )
        .where(fx_rate.c.fx_rate_set_version_id == version_id, fx_rate.c.is_derived.is_(False))
        .order_by(fx_rate.c.effective_date, fx_rate.c.base_currency, fx_rate.c.quote_currency)
    )
    return [
        fx.RateRow(
            base_currency=str(row.base_currency),
            quote_currency=str(row.quote_currency),
            effective_date=row.effective_date,
            period_id=row.period_id,
            rate=row.rate,
        )
        for row in session.execute(statement)
    ]


def _version_out(session: Session, version_id: UUID) -> FxRateSetVersionDetailOut:
    return FxRateSetVersionDetailOut.model_validate(
        queries.fx_rate_set_version_row(session, version_id)
    )


def _require_draft(current: Mapping[str, Any], *, submitting: bool = False) -> None:
    status = str(current["status"])
    if status == ConfigStatus.DRAFT.value:
        return
    if submitting:
        message = fx.NOT_SUBMITTABLE.format(status=status)
        error = ProblemError(field="status", rule_id=fx.RULE_LIFECYCLE, message=message)
        raise Problem("invalid-transition", message, errors=[error])
    message = fx.NOT_DRAFT.format(status=status)
    error = ProblemError(field="status", rule_id=fx.RULE_FROZEN, message=message)
    raise Problem("configuration-frozen", message, errors=[error])


def create_fx_rate_set_version(
    uow: UnitOfWork, *, set_id: UUID, body: FxRateSetVersionIn
) -> FxRateSetVersionDetailOut:
    """``POST /fx-rate-sets/{id}/versions``: a DRAFT version numbered after the set's latest, with
    its entered rates; 404 for an unknown set; 422 lists every finding."""
    _authorize_fx(uow, action=fx.VERSION_CREATE, object_id=None)
    session = uow.session
    found = session.execute(
        select(fx_rate_set.c.rate_type).where(fx_rate_set.c.id == set_id).with_for_update()
    ).scalar_one_or_none()
    if found is None:
        raise Problem("not-found")
    rate_type = RateType(found)
    errors = _coverage_errors(body.coverage_from, body.coverage_to)
    rows, rate_errors = fx.rate_rows(
        session,
        rate_type=rate_type,
        coverage_from=body.coverage_from,
        coverage_to=body.coverage_to,
        rates=body.rates,
    )
    errors += rate_errors
    if errors:
        raise Problem("validation-failed", errors=errors)

    latest = session.execute(
        select(func.max(fx_rate_set_version.c.version_no)).where(
            fx_rate_set_version.c.fx_rate_set_id == set_id
        )
    ).scalar_one()
    version_no = int(latest or 0) + 1
    version_id = new_id()
    session.execute(
        insert(fx_rate_set_version).values(
            tenant_id=uow.principal.tenant_id,
            id=version_id,
            fx_rate_set_id=set_id,
            coverage_from=body.coverage_from,
            coverage_to=body.coverage_to,
            rate_count=0,
            import_upload_id=None,
            **_stamps(uow),
            version_no=version_no,
            status=ConfigStatus.DRAFT.value,
        )
    )
    _insert_rates(uow, version_id, rate_type, rows)
    uow.audit(
        action=fx.VERSION_CREATE,
        object_type=fx.VERSION_OBJECT,
        object_id=version_id,
        object_version="1",
        after={
            "fx_rate_set_id": str(set_id),
            "version_no": version_no,
            "status": ConfigStatus.DRAFT.value,
            "coverage_from": body.coverage_from.isoformat(),
            "coverage_to": body.coverage_to.isoformat(),
            "entered_rate_count": len(rows),
        },
    )
    return _version_out(session, version_id)


def update_fx_rate_set_version(
    uow: UnitOfWork,
    *,
    version_id: UUID,
    body: FxRateSetVersionUpdateIn,
    check_version: VersionCheck,
) -> FxRateSetVersionDetailOut:
    """``PATCH /fx-rate-set-versions/{id}``: change the coverage or replace the entered rates of a
    DRAFT version (DB-04); 409 ``configuration-frozen`` outside DRAFT."""
    _authorize_fx(uow, action=fx.VERSION_UPDATE, object_id=version_id)
    session = uow.session
    current = _locked_version(session, version_id)
    check_version(int(current["row_version"]))
    _require_draft(current)
    sent = body.model_fields_set
    errors = [
        ProblemError(field=member, rule_id=fx.RULE_VERSION, message=VALUE_REQUIRED)
        for member in ("coverage_from", "coverage_to", "rates")
        if member in sent and getattr(body, member) is None
    ]
    if errors:
        raise Problem("validation-failed", errors=errors)
    coverage_from: date = body.coverage_from or current["coverage_from"]
    coverage_to: date = body.coverage_to or current["coverage_to"]
    rate_type: RateType = current["rate_type"]
    errors += _coverage_errors(coverage_from, coverage_to)
    rows: list[fx.RateRow] = []
    if body.rates is not None:
        rows, rate_errors = fx.rate_rows(
            session,
            rate_type=rate_type,
            coverage_from=coverage_from,
            coverage_to=coverage_to,
            rates=body.rates,
        )
        errors += rate_errors
    elif not errors:
        outside = [
            row
            for row in _entered_rates(session, version_id)
            if not coverage_from <= row.effective_date <= coverage_to
        ]
        if outside:
            member = "coverage_from" if "coverage_from" in sent else "coverage_to"
            errors.append(
                ProblemError(field=member, rule_id=fx.RULE_VERSION, message=RATES_OUTSIDE_COVERAGE)
            )
    if errors:
        raise Problem("validation-failed", errors=errors)

    principal = uow.principal
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for member, value in (("coverage_from", coverage_from), ("coverage_to", coverage_to)):
        if value != current[member]:
            before[member] = current[member].isoformat()
            after[member] = value.isoformat()
    session.execute(
        update(fx_rate_set_version)
        .where(fx_rate_set_version.c.id == version_id)
        .values(
            coverage_from=coverage_from,
            coverage_to=coverage_to,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    detail: dict[str, Any] | None = None
    if body.rates is not None:
        removed = (
            session.execute(
                delete(fx_rate)
                .where(fx_rate.c.fx_rate_set_version_id == version_id)
                .returning(fx_rate.c.id)
            )
            .scalars()
            .all()
        )
        if removed:
            audit_writer.record_facts(
                uow,
                action=fx.RATE_DELETE,
                object_type=fx.RATE_OBJECT,
                ids=[UUID(str(value)) for value in removed],
                detail={"fx_rate_set_version_id": str(version_id)},
            )
        _insert_rates(uow, version_id, rate_type, rows)
        detail = {"rates_removed": len(removed), "entered_rate_count": len(rows)}
    uow.audit(
        action=fx.VERSION_UPDATE,
        object_type=fx.VERSION_OBJECT,
        object_id=version_id,
        object_version=str(int(current["row_version"]) + 1),
        before=before,
        after=after,
        detail=detail,
    )
    return _version_out(session, version_id)


def submit_fx_rate_set_version(
    uow: UnitOfWork,
    *,
    version_id: UUID,
    body: FxRateSetVersionCommandIn,
    check_version: VersionCheck,
) -> FxRateSetVersionDetailOut:
    """``POST /fx-rate-set-versions/{id}/submit``: DRAFT → TESTED → SUBMITTED with the derived
    inverses, ``rate_count`` and the content hash, then an ``FX_RATE_SET_VERSION`` request
    (REQ-REF-006; PRD SM-04). 409 ``invalid-transition`` unless the version is DRAFT; 422 without
    rates or when an inverse rounds to zero."""
    _authorize_fx(uow, action=fx.VERSION_SUBMIT, object_id=version_id)
    session = uow.session
    current = _locked_version(session, version_id)
    check_version(int(current["row_version"]))
    _require_draft(current, submitting=True)
    # A version back in DRAFT after a rejection or withdrawal derives its inverses again.
    session.execute(
        delete(fx_rate).where(
            fx_rate.c.fx_rate_set_version_id == version_id, fx_rate.c.is_derived.is_(True)
        )
    )
    entered = _entered_rates(session, version_id)
    if not entered:
        error = ProblemError(field="rates", rule_id=fx.RULE_VERSION, message=fx.RATES_REQUIRED)
        raise Problem("validation-failed", errors=[error])
    derived, zero = fx.derived_inverses(entered)
    if zero:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field=f"rates.{index}.rate", rule_id=fx.RULE_RATE, message=fx.INVERSE_ZERO
                )
                for index in zero
            ],
        )
    rate_type: RateType = current["rate_type"]
    _insert_rates(uow, version_id, rate_type, derived)
    content_sha256 = sha256_hex(subjects.fx_rate_set_version_content(session, version_id))
    rate_count = len(entered) + len(derived)
    principal = uow.principal
    where = fx_rate_set_version.c.id == version_id
    session.execute(
        update(fx_rate_set_version)
        .where(where)
        .values(
            rate_count=rate_count,
            content_sha256=content_sha256,
            status=ConfigStatus.TESTED.value,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    session.execute(
        update(fx_rate_set_version).where(where).values(status=ConfigStatus.SUBMITTED.value)
    )
    uow.audit(
        action=fx.VERSION_SUBMIT,
        object_type=fx.VERSION_OBJECT,
        object_id=version_id,
        before={
            "status": ConfigStatus.DRAFT.value,
            "rate_count": int(current["rate_count"]),
            "content_sha256": current["content_sha256"],
        },
        after={
            "status": ConfigStatus.SUBMITTED.value,
            "rate_count": rate_count,
            "content_sha256": content_sha256,
        },
        detail={
            "lifecycle": [
                ConfigStatus.DRAFT.value,
                ConfigStatus.TESTED.value,
                ConfigStatus.SUBMITTED.value,
            ],
            "derived_rate_count": len(derived),
        },
        comment=body.comment,
    )
    approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.FX_RATE_SET_VERSION,
        subject_id=version_id,
        summary=(
            f"Publish version {int(current['version_no'])} of FX rate set "
            f"{current['fx_rate_set_code']}"
        ),
        comment=body.comment,
    )
    return _version_out(session, version_id)


def withdraw_fx_rate_set_version(
    uow: UnitOfWork,
    *,
    version_id: UUID,
    body: FxRateSetVersionCommandIn,
    check_version: VersionCheck,
) -> FxRateSetVersionDetailOut:
    """``POST /fx-rate-set-versions/{id}/withdraw``: the preparer withdraws the pending request and
    the version returns to DRAFT (``SubjectSpec.on_voided``). 409 ``invalid-transition`` without a
    pending request; 403 for anyone but the preparer (PRD SM-01)."""
    _authorize_fx(uow, action=fx.VERSION_WITHDRAW, object_id=version_id)
    session = uow.session
    current = _locked_version(session, version_id)
    check_version(int(current["row_version"]))
    pending = session.execute(
        select(approval_request.c.id).where(
            approval_request.c.subject_type == ApprovalSubjectType.FX_RATE_SET_VERSION.value,
            approval_request.c.subject_id == version_id,
            approval_request.c.status == ApprovalRequestStatus.PENDING.value,
        )
    ).scalar_one_or_none()
    if current["status"] != ConfigStatus.SUBMITTED.value or pending is None:
        error = ProblemError(field="status", rule_id=fx.RULE_LIFECYCLE, message=fx.NOT_PENDING)
        raise Problem("invalid-transition", fx.NOT_PENDING, errors=[error])
    approvals.withdraw(
        uow,
        approval_request_id=UUID(str(pending)),
        comment=body.comment,
        through_subject=True,
    )
    return _version_out(session, version_id)


# --- account mappings (04 API-R-20, T-REF-14, T-REF-15; BUILD_SPEC RFD-7) ------------------------

MAPPING_KIND: Final = mapping.ACCOUNT_MAPPING_VERSION_KIND
MAPPING_VERSION_CREATE: Final = "account_mapping_version.create"
MAPPING_VERSION_UPDATE: Final = "account_mapping_version.update"
MAPPING_RULE_CREATE: Final = "account_mapping_rule.create"
MAPPING_RULE_DELETE: Final = "account_mapping_rule.delete"
MAPPING_RULE_COLUMNS: Final = (
    "account_role",
    "clearing_purpose",
    "entity_id",
    "book_code",
    "product_id",
    "revenue_category",
    "gl_account_id",
    "default_dimensions",
    "priority",
)
# [J] Copy the documents leave open.
MAPPING_VERSION_OPEN: Final = "Another mapping version is open. Publish or reject it first."
MAPPING_SOURCE_UNKNOWN: Final = "Choose a mapping version to copy."
MAPPING_NOT_TESTABLE: Final = "Only a draft or tested version can run its tests."
MAPPING_RULES_REQUIRED: Final = "Add at least one rule before running the tests."
MAPPING_ENTITY_UNKNOWN: Final = "Choose an existing entity."
MAPPING_PRODUCT_UNKNOWN: Final = "Choose an existing product."
MAPPING_ACCOUNT_UNKNOWN: Final = "Choose an active GL account."
MAPPING_ACCOUNT_ENTITY: Final = "This GL account is not available to the rule's entity."
MAPPING_DIMENSION_UNKNOWN: Final = "Use the code of an active dimension."
MAPPING_DIMENSION_VALUE: Final = "Use the code of an active value of this dimension."


def _mapping_error(field: str, message: str, *, rule_id: str = mapping.RULE_RULE) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _copy_mapping_rules(
    uow: UnitOfWork, *, source_version_id: UUID, version_id: UUID
) -> list[UUID]:
    """Copy the rules of ``source_version_id`` into the new DRAFT version."""
    session = uow.session
    ids: list[UUID] = []
    for row in mapping.rule_rows(session, source_version_id):
        rule_id = new_id()
        session.execute(
            insert(account_mapping_rule).values(
                tenant_id=uow.principal.tenant_id,
                id=rule_id,
                account_mapping_version_id=version_id,
                **{name: row[name] for name in MAPPING_RULE_COLUMNS},
            )
        )
        ids.append(rule_id)
    return ids


def create_account_mapping_version(uow: UnitOfWork, *, body: AccountMappingIn) -> UUID:
    """``POST /account-mappings``: the next version as DRAFT (PRD SM-04).

    409 ``invalid-transition`` (rule SM-04) while another version is DRAFT, TESTED, SUBMITTED or
    APPROVED; 422 collects the findings on ``name`` and ``source_version_id``. The version names the
    PUBLISHED version with the highest number as the one it supersedes, and copies the rules of
    ``source_version_id``. The tenant's versions are serialised by an advisory lock, because the
    first version has no row to lock.
    """
    session = uow.session
    tenant_id = uow.principal.tenant_id
    mapping.serialise_versions(uow)
    versions = (
        session.execute(
            select(
                account_mapping_version.c.id,
                account_mapping_version.c.version_no,
                account_mapping_version.c.status,
            )
        )
        .mappings()
        .all()
    )
    if any(row["status"] in lifecycle.OPEN for row in versions):
        error = _mapping_error("status", MAPPING_VERSION_OPEN, rule_id=lifecycle.RULE_OPEN_VERSION)
        raise Problem("invalid-transition", errors=[error])
    errors: list[ProblemError] = []
    name = _label(body.name, field="name", rule_id=mapping.RULE_VERSION, errors=errors)
    source_id = body.source_version_id
    if source_id is not None and all(row["id"] != source_id for row in versions):
        errors.append(
            _mapping_error(
                "source_version_id", MAPPING_SOURCE_UNKNOWN, rule_id=mapping.RULE_VERSION
            )
        )
    if errors:
        raise Problem("validation-failed", errors=errors)
    published = [row for row in versions if row["status"] == ConfigStatus.PUBLISHED.value]
    supersedes = max(published, key=lambda row: int(row["version_no"]))["id"] if published else None
    version_no = max((int(row["version_no"]) for row in versions), default=0) + 1
    version_id = new_id()
    values = {
        "name": name,
        "notes": _optional_text(body.notes),
        "effective_from": body.effective_from,
    }
    session.execute(
        insert(account_mapping_version).values(
            tenant_id=tenant_id,
            id=version_id,
            **values,
            **_stamps(uow),
            version_no=version_no,
            status=ConfigStatus.DRAFT.value,
            supersedes_version_id=supersedes,
        )
    )
    copied = (
        []
        if source_id is None
        else _copy_mapping_rules(uow, source_version_id=source_id, version_id=version_id)
    )
    uow.audit(
        action=MAPPING_VERSION_CREATE,
        object_type=mapping.OBJECT_VERSION,
        object_id=version_id,
        after=_audit_members(
            {
                **values,
                "version_no": version_no,
                "status": ConfigStatus.DRAFT.value,
                "supersedes_version_id": supersedes,
            }
        ),
        detail={
            "source_version_id": None if source_id is None else str(source_id),
            "rules_copied": len(copied),
        },
    )
    if copied:
        audit_writer.record_facts(
            uow,
            action=MAPPING_RULE_CREATE,
            object_type=mapping.OBJECT_RULE,
            ids=copied,
            detail={"account_mapping_version_id": str(version_id)},
        )
    return version_id


def update_account_mapping_version(
    uow: UnitOfWork,
    version_id: UUID,
    *,
    changes: Mapping[str, Any],
    check_version: VersionCheck,
) -> None:
    """``PATCH /account-mappings/{id}``: 404; 428 or 412 for ``If-Match``; 409
    ``configuration-frozen`` outside DRAFT and TESTED (a REJECTED or WITHDRAWN version reopens as
    DRAFT, E-12); 422 for a blank name."""
    session = uow.session
    version = lifecycle.lock(session, MAPPING_KIND, version_id)
    check_version(int(version["row_version"]))
    version = lifecycle.require_editable(uow, MAPPING_KIND, version)
    errors: list[ProblemError] = []
    values: dict[str, Any] = {}
    if "name" in changes:
        values["name"] = _label(
            changes["name"], field="name", rule_id=mapping.RULE_VERSION, errors=errors
        )
    if "notes" in changes:
        values["notes"] = _optional_text(changes["notes"])
    if "effective_from" in changes:
        values["effective_from"] = changes["effective_from"]
    if errors:
        raise Problem("validation-failed", errors=errors)
    changed = {name: value for name, value in values.items() if version[name] != value}
    if not changed:
        return
    principal = uow.principal
    session.execute(
        update(account_mapping_version)
        .where(account_mapping_version.c.id == version_id)
        .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
    )
    uow.audit(
        action=MAPPING_VERSION_UPDATE,
        object_type=mapping.OBJECT_VERSION,
        object_id=version_id,
        before=_audit_members({name: version[name] for name in changed}),
        after=_audit_members(changed),
    )


def _default_dimensions_errors(session: Session, values: Mapping[str, Any]) -> list[ProblemError]:
    """Default dimensions name active dimensions; each value is a code, of an active stored value
    where the dimension stores values (T-REF-15, T-REF-17)."""
    if not values:
        return []
    definitions = {
        str(code): UUID(str(definition_id))
        for code, definition_id in session.execute(
            select(dimension_definition.c.code, dimension_definition.c.id).where(
                dimension_definition.c.is_active
            )
        )
    }
    errors: list[ProblemError] = []
    for code in sorted(values):
        where = f"default_dimensions.{code}"
        value = values[code]
        if code not in definitions:
            errors.append(_mapping_error(where, MAPPING_DIMENSION_UNKNOWN))
        elif not isinstance(value, str) or not value.strip():
            errors.append(_mapping_error(where, VALUE_REQUIRED))
        elif code not in dimensions.UNSTORED_VALUE_DIMENSIONS:
            found = session.execute(
                select(dimension_value.c.id).where(
                    dimension_value.c.dimension_definition_id == definitions[code],
                    dimension_value.c.code == value,
                    dimension_value.c.is_active,
                )
            ).first()
            if found is None:
                errors.append(_mapping_error(where, MAPPING_DIMENSION_VALUE))
    return errors


def add_account_mapping_rule(
    uow: UnitOfWork, version_id: UUID, *, body: AccountMappingRuleIn
) -> UUID:
    """``POST /account-mappings/{id}/rules``: the new rule's id.

    404; 409 ``configuration-frozen`` outside DRAFT and TESTED (DB-04); 422 collects the findings
    in field order: reserved role and clearing purpose (D-14a), entity, product (an existing
    product, RFD-9), revenue category, the product-or-category check, GL account (active, and
    available to the rule's entity) and default dimensions. ``specificity`` is generated.
    """
    session = uow.session
    version = lifecycle.lock(session, MAPPING_KIND, version_id)
    lifecycle.require_editable(uow, MAPPING_KIND, version)
    role = body.account_role.value
    purpose = None if body.clearing_purpose is None else body.clearing_purpose.value
    errors = mapping.role_errors(role, purpose)
    if body.entity_id is not None:
        found = session.execute(
            select(legal_entity.c.id).where(legal_entity.c.id == body.entity_id)
        ).first()
        if found is None:
            errors.append(_mapping_error("entity_id", MAPPING_ENTITY_UNKNOWN))
    if body.product_id is not None:
        found = session.execute(select(product.c.id).where(product.c.id == body.product_id)).first()
        if found is None:
            errors.append(_mapping_error("product_id", MAPPING_PRODUCT_UNKNOWN))
    category = None if body.revenue_category is None else body.revenue_category.strip()
    if category is not None and not CODE_PATTERN.fullmatch(category):
        errors.append(_mapping_error("revenue_category", CODE_FORMAT))
    errors += mapping.key_errors(body.product_id, category)
    account = (
        session.execute(
            select(gl_account.c.is_active, gl_account.c.entity_ids).where(
                gl_account.c.id == body.gl_account_id
            )
        )
        .mappings()
        .first()
    )
    if account is None or not account["is_active"]:
        errors.append(_mapping_error("gl_account_id", MAPPING_ACCOUNT_UNKNOWN))
    elif (
        body.entity_id is not None
        and account["entity_ids"]
        and body.entity_id not in account["entity_ids"]
    ):
        errors.append(_mapping_error("gl_account_id", MAPPING_ACCOUNT_ENTITY))
    errors += _default_dimensions_errors(session, body.default_dimensions)
    if errors:
        raise Problem("validation-failed", errors=errors)
    rule_id = new_id()
    session.execute(
        insert(account_mapping_rule).values(
            tenant_id=uow.principal.tenant_id,
            id=rule_id,
            account_mapping_version_id=version_id,
            account_role=role,
            clearing_purpose=purpose,
            entity_id=body.entity_id,
            book_code=None if body.book_code is None else body.book_code.value,
            product_id=body.product_id,
            revenue_category=category,
            gl_account_id=body.gl_account_id,
            default_dimensions=dict(body.default_dimensions),
            priority=body.priority,
        )
    )
    audit_writer.record_facts(
        uow,
        action=MAPPING_RULE_CREATE,
        object_type=mapping.OBJECT_RULE,
        ids=[rule_id],
        detail={
            "account_mapping_version_id": str(version_id),
            "account_role": role,
            "clearing_purpose": purpose,
        },
    )
    return rule_id


def delete_account_mapping_rule(uow: UnitOfWork, version_id: UUID, rule_id: UUID) -> None:
    """``DELETE /account-mappings/{id}/rules/{rule_id}``: 404 for a rule outside the version, and
    for a rule that names an entity the caller's ``config.author`` does not cover
    (``_authors_for``; rev 1.319); 409 ``configuration-frozen`` outside DRAFT and TESTED."""
    session = uow.session
    version = lifecycle.lock(session, MAPPING_KIND, version_id)
    found = session.execute(
        select(account_mapping_rule.c.account_role, account_mapping_rule.c.entity_id).where(
            account_mapping_rule.c.id == rule_id,
            account_mapping_rule.c.account_mapping_version_id == version_id,
        )
    ).one_or_none()
    if found is None:
        raise Problem("not-found")
    if found.entity_id is not None and not _authors_for(uow, [found.entity_id]):
        raise Problem("not-found")
    role = found.account_role
    lifecycle.require_editable(uow, MAPPING_KIND, version)
    session.execute(delete(account_mapping_rule).where(account_mapping_rule.c.id == rule_id))
    audit_writer.record_facts(
        uow,
        action=MAPPING_RULE_DELETE,
        object_type=mapping.OBJECT_RULE,
        ids=[rule_id],
        detail={"account_mapping_version_id": str(version_id), "account_role": str(role)},
    )


def run_account_mapping_tests(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /account-mappings/{id}/test``: the publish lint over the rules (REQ-POL-002).

    409 ``invalid-transition`` unless DRAFT or TESTED; 422 without rules or with lint findings, and
    the status stays. When the lint passes, a DRAFT version becomes TESTED with its content hash,
    and a TESTED version records the hash of the new run (L1-4-Q-4).
    """
    session = uow.session
    version = lifecycle.lock(session, MAPPING_KIND, version_id)
    if version["status"] not in lifecycle.EDITABLE:
        raise lifecycle.refused(MAPPING_NOT_TESTABLE)
    rules = mapping.rule_rows(session, version_id)
    if not rules:
        raise Problem("validation-failed", errors=[_mapping_error("rules", MAPPING_RULES_REQUIRED)])
    findings = mapping.lint_findings(rules)
    if findings:
        raise Problem("validation-failed", errors=findings)
    lifecycle.mark_tested(
        uow,
        MAPPING_KIND,
        version,
        content_sha256=lifecycle.current_sha256(session, MAPPING_KIND, version_id),
        detail={"rule_count": len(rules), "lint_status": "PASS"},
    )


def submit_account_mapping_version(
    uow: UnitOfWork, version_id: UUID, *, comment: str | None
) -> None:
    """``POST /account-mappings/{id}/submit``: TESTED → SUBMITTED with the simulation report and an
    ``ACCOUNT_MAPPING_VERSION`` request (PRD BR-POL-01; REQ-POL-006).

    422 when the TESTED version has no ``effective_from``, which freezes at submission (DB-04); 409
    ``invalid-transition`` unless TESTED, or when the content changed after ``/test`` (REQ-POL-003).
    """
    session = uow.session
    version = lifecycle.lock(session, MAPPING_KIND, version_id)
    if version["status"] == ConfigStatus.TESTED.value and version["effective_from"] is None:
        error = _mapping_error(
            "effective_from", mapping.EFFECTIVE_REQUIRED, rule_id=mapping.RULE_VERSION
        )
        raise Problem("validation-failed", errors=[error])

    def attach(current: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        report = simulation.simulate(
            uow,
            simulation.SimulationSubject(
                subject_type=mapping.SUBJECT_TYPE,
                subject_id=version_id,
                content_sha256=str(current["content_sha256"]),
            ),
        )
        return (
            {"impact_simulation_file_id": report.file_id},
            {"impact_simulation": {"file_id": report.file_id, "summary": report.summary}},
        )

    lifecycle.submit(uow, MAPPING_KIND, version, comment=comment, attach=attach)


def publish_account_mapping_version(uow: UnitOfWork, version_id: UUID) -> None:
    """``POST /account-mappings/{id}/publish``: the publish lint first, whatever the status (422
    ``validation-failed``, REQ-POL-002; L2-1-Q-3); then a PUBLISHED version answers as it is, any
    status but APPROVED returns 409 ``invalid-transition``, and publication may return 409
    ``configuration-overlap`` (DB-04)."""
    session = uow.session
    version = lifecycle.lock(session, MAPPING_KIND, version_id)
    findings = mapping.lint_findings(mapping.rule_rows(session, version_id))
    if findings:
        raise Problem("validation-failed", errors=findings)
    mapping.publish(
        uow,
        version,
        approval_request_id=version["approval_request_id"],
        published_by=uow.principal.id,
    )


# --- products and bundle components (04 API-R-23; BUILD_SPEC RFD-9) ------------------------------

PRODUCT_CREATE_ACTION: Final = "product.create"
PRODUCT_UPDATE_ACTION: Final = "product.update"
COMPONENT_OBJECT: Final = "product_bundle_component"
COMPONENT_CREATE_ACTION: Final = "product_bundle_component.create"
COMPONENT_UPDATE_ACTION: Final = "product_bundle_component.update"
COMPONENT_DELETE_ACTION: Final = "product_bundle_component.delete"
PRODUCT_NOT_NULL: Final = (
    "code",
    "name",
    "disaggregation",
    "distinctness_default",
    "unit_of_measure",
    "is_bundle",
    "is_franchisor_preopening_service",
    "policy_values",
    "is_active",
)
PRODUCT_FREE_TEXT: Final = ("sku_number", "product_family")
PRODUCT_FLAGS: Final = ("is_franchisor_preopening_service", "is_active")
COMPONENT_VALUES: Final = (
    "quantity_per_bundle",
    "split_basis",
    "split_ratio",
    "sequence",
    "valid_to",
)


def _exact(value: str | None) -> Decimal | None:
    """An API-C-06 decimal string as ``Decimal``."""
    return None if value is None else Decimal(value)


def _exact_audit(values: Mapping[str, Any]) -> dict[str, Any]:
    """Audit members with decimals as API-C-06 text."""
    return _audit_members(
        {
            key: products.exact_text(value) if isinstance(value, Decimal) else value
            for key, value in values.items()
        }
    )


def _product_code_errors(
    session: Session, code: str, *, product_id: UUID | None
) -> list[ProblemError]:
    """TY-06, unique in the workspace (``ux_product__code``)."""
    rule_id = products.RULE_PRODUCT
    if not CODE_PATTERN.fullmatch(code):
        return [ProblemError(field="code", rule_id=rule_id, message=CODE_FORMAT)]
    taken = select(product.c.id).where(product.c.code == code)
    if product_id is not None:
        taken = taken.where(product.c.id != product_id)
    if session.execute(taken.limit(1)).first() is None:
        return []
    message = products.CODE_TAKEN.format(code=code)
    return [ProblemError(field="code", rule_id=rule_id, message=message)]


def _revenue_category(value: Any, errors: list[ProblemError]) -> str | None:
    """A TY-06 revenue category with surrounding spaces removed, or none."""
    category = _optional_text(value)
    if category is not None and not CODE_PATTERN.fullmatch(category):
        errors.append(
            ProblemError(
                field="revenue_category", rule_id=products.RULE_PRODUCT, message=CODE_FORMAT
            )
        )
    return category


def _unit_of_measure(value: Any, errors: list[ProblemError]) -> str:
    unit = _optional_text(value)
    if unit is None:
        errors.append(
            ProblemError(
                field="unit_of_measure",
                rule_id=products.RULE_PRODUCT,
                message=products.UNIT_REQUIRED,
            )
        )
        return ""
    return unit


def _template_errors(session: Session, template_id: UUID | None) -> list[ProblemError]:
    """[J] ``default_pob_template_id`` names a visible obligation template with a PUBLISHED version
    (T-REF-20 FK; L2-1-Q-15 resolved by RFD-10, L2-1-Q-48)."""
    if template_id is None or templates.has_published_version(session, template_id):
        return []
    return [
        ProblemError(
            field="default_pob_template_id",
            rule_id=products.RULE_PRODUCT,
            message=products.TEMPLATE_UNKNOWN,
        )
    ]


def _product_out(session: Session, product_id: UUID) -> ProductOut:
    row = queries.product_row(session, product_id)
    if row is None:
        raise Problem("not-found")
    return ProductOut.model_validate(row)


def create_product(uow: UnitOfWork, *, body: ProductIn) -> ProductOut:
    """``POST /products``: 422 ``validation-failed`` lists every finding (DG-CMD-03). The initial
    ``principal_agent`` is recorded as sent; later changes need approval (L2-1-Q-18)."""
    session = uow.session
    rule_id = products.RULE_PRODUCT
    errors = _product_code_errors(session, body.code, product_id=None)
    label = _label(body.name, field="name", rule_id=rule_id, errors=errors)
    category = _revenue_category(body.revenue_category, errors)
    errors += _template_errors(session, body.default_pob_template_id)
    errors += products.disaggregation_errors(body.disaggregation)
    unit = _unit_of_measure(body.unit_of_measure, errors)
    cost = _exact(body.assurance_cost_per_unit)
    errors += products.assurance_cost_errors(cost)
    errors += products.policy_values_errors(body.policy_values)
    if errors:
        raise Problem("validation-failed", errors=errors)

    product_id = new_id()
    values: dict[str, Any] = {
        "code": body.code,
        "sku_number": _optional_text(body.sku_number),
        "name": label,
        "product_family": _optional_text(body.product_family),
        "revenue_category": category,
        "default_pob_template_id": body.default_pob_template_id,
        "disaggregation": dict(body.disaggregation),
        "principal_agent": body.principal_agent.value,
        "distinctness_default": body.distinctness_default.value,
        "unit_of_measure": unit,
        "is_bundle": body.is_bundle,
        "assurance_cost_per_unit": cost,
        "is_franchisor_preopening_service": body.is_franchisor_preopening_service,
        "policy_values": dict(body.policy_values),
        "is_active": body.is_active,
    }
    session.execute(
        insert(product).values(
            tenant_id=uow.principal.tenant_id, id=product_id, **values, **_stamps(uow)
        )
    )
    uow.audit(
        action=PRODUCT_CREATE_ACTION,
        object_type=subjects.PRODUCT_OBJECT,
        object_id=product_id,
        object_version="1",
        after=_exact_audit(values),
    )
    return _product_out(session, product_id)


def _has_components(session: Session, product_id: UUID) -> bool:
    statement = select(product_bundle_component.c.id).where(
        product_bundle_component.c.bundle_product_id == product_id
    )
    return session.execute(statement.limit(1)).first() is not None


def update_product(
    uow: UnitOfWork,
    *,
    product_id: UUID,
    changes: Mapping[str, Any],
    check_version: Callable[[int], None],
) -> ProductOut:
    """``PATCH /products/{id}``: 404 ``not-found`` for a product the caller cannot see;
    ``If-Match`` through ``check_version``; an unchanged request writes nothing. A
    ``principal_agent`` other than the stored one returns 422 on ``principal_agent`` with rule
    REQ-REF-012 (``propose-principal-agent-change`` changes it), and ``policy_values`` that differ
    from the stored ones return 422 on each changed key with rule REQ-POL-003
    (``propose-policy-values-change`` changes them; 04 API-R-23 rev 1.110); a changed ``code`` of
    a product that a contract line, an SSP entry or an account mapping rule names returns 422 on
    ``code`` with rule DB-05 (item PRODUCT-CODE-FREEZE-1); clearing ``is_bundle`` while components
    exist returns 422."""
    session = uow.session
    locked = select(*queries.PRODUCT_COLUMNS).where(product.c.id == product_id).with_for_update()
    current = session.execute(locked).mappings().first()
    if current is None:
        raise Problem("not-found")
    check_version(int(current["row_version"]))
    rule_id = products.RULE_PRODUCT
    errors: list[ProblemError] = []
    values: dict[str, Any] = {}
    if "principal_agent" in changes and changes["principal_agent"] != current["principal_agent"]:
        errors.append(
            ProblemError(
                field="principal_agent",
                rule_id=products.RULE_PRINCIPAL_AGENT,
                message=products.PRINCIPAL_AGENT_BY_APPROVAL,
            )
        )
    for key in PRODUCT_NOT_NULL:
        if key in changes and changes[key] is None:
            errors.append(ProblemError(field=key, rule_id=rule_id, message=VALUE_REQUIRED))
    if changes.get("code") is not None and changes["code"] != current["code"]:
        values["code"] = str(changes["code"])
        errors += _product_code_errors(session, values["code"], product_id=product_id)
        errors += products.code_frozen_errors(session, product_id)
    if changes.get("name") is not None:
        values["name"] = _label(changes["name"], field="name", rule_id=rule_id, errors=errors)
    for key in PRODUCT_FREE_TEXT:
        if key in changes:
            values[key] = _optional_text(changes[key])
    if "revenue_category" in changes:
        values["revenue_category"] = _revenue_category(changes["revenue_category"], errors)
    if "default_pob_template_id" in changes:
        template = changes["default_pob_template_id"]
        template_id = None if template is None else UUID(str(template))
        errors += _template_errors(session, template_id)
        values["default_pob_template_id"] = template_id
    if changes.get("disaggregation") is not None:
        errors += products.disaggregation_errors(changes["disaggregation"])
        values["disaggregation"] = dict(changes["disaggregation"])
    if changes.get("distinctness_default") is not None:
        values["distinctness_default"] = Distinctness(changes["distinctness_default"]).value
    if changes.get("unit_of_measure") is not None:
        values["unit_of_measure"] = _unit_of_measure(changes["unit_of_measure"], errors)
    if changes.get("is_bundle") is not None:
        values["is_bundle"] = bool(changes["is_bundle"])
        if not values["is_bundle"] and _has_components(session, product_id):
            errors.append(
                ProblemError(
                    field="is_bundle",
                    rule_id=products.RULE_COMPONENT,
                    message=products.BUNDLE_HAS_COMPONENTS,
                )
            )
    if "assurance_cost_per_unit" in changes:
        cost = _exact(changes["assurance_cost_per_unit"])
        errors += products.assurance_cost_errors(cost)
        values["assurance_cost_per_unit"] = cost
    if changes.get("policy_values") is not None:
        invalid = products.policy_values_errors(changes["policy_values"])
        named = {error.field for error in invalid}
        errors += invalid
        errors += [
            error
            for error in products.policy_values_by_request(
                current["policy_values"] or {}, changes["policy_values"]
            )
            if error.field not in named
        ]
        values["policy_values"] = dict(changes["policy_values"])
    for key in PRODUCT_FLAGS:
        if changes.get(key) is not None:
            values[key] = bool(changes[key])
    if errors:
        raise Problem("validation-failed", errors=errors)
    changed = {key: value for key, value in values.items() if value != current[key]}
    if changed:
        principal = uow.principal
        session.execute(
            update(product)
            .where(product.c.id == product_id)
            .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
        )
        uow.audit(
            action=PRODUCT_UPDATE_ACTION,
            object_type=subjects.PRODUCT_OBJECT,
            object_id=product_id,
            object_version=str(int(current["row_version"]) + 1),
            before=_exact_audit({key: current[key] for key in changed}),
            after=_exact_audit(changed),
        )
    return _product_out(session, product_id)


def propose_principal_agent_change(
    uow: UnitOfWork, *, product_id: UUID, body: PrincipalAgentChangeIn
) -> PrincipalAgentChangeOut:
    """``POST /products/{id}/propose-principal-agent-change``: a ``PRINCIPAL_AGENT_CHANGE``
    request whose approval by a ``config.approve`` holder other than the proposer sets the
    conclusion (PRD §2.5; REQ-REF-012; CTL-031).

    404; 422 for the current conclusion or a blank rationale; 409 ``invalid-transition`` while a
    request for the product is PENDING. The product keeps its conclusion until approval.
    """
    session = uow.session
    current = (
        session.execute(
            select(product.c.code, product.c.principal_agent)
            .where(product.c.id == product_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if current is None:
        raise Problem("not-found")
    rule_id = products.RULE_PRINCIPAL_AGENT
    errors: list[ProblemError] = []
    if body.principal_agent.value == current["principal_agent"]:
        errors.append(
            ProblemError(
                field="principal_agent", rule_id=rule_id, message=products.PRINCIPAL_AGENT_UNCHANGED
            )
        )
    rationale = body.rationale.strip()
    if not rationale:
        errors.append(
            ProblemError(field="rationale", rule_id=rule_id, message=products.RATIONALE_REQUIRED)
        )
    if errors:
        raise Problem("validation-failed", errors=errors)
    code = str(current["code"])
    before = {
        "object_type": subjects.PRODUCT_OBJECT,
        "product_id": str(product_id),
        "product_code": code,
        "principal_agent": str(current["principal_agent"]),
    }
    after = subjects.principal_agent_proposal(
        product_id=product_id,
        product_code=code,
        principal_agent=body.principal_agent.value,
        rationale=rationale,
    )
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE,
        subject_id=product_id,
        summary=f"Principal or agent change for {code}",
        impact_preview=approvals.ImpactPreview(before=before, after=after),
        comment=rationale,
    )
    return PrincipalAgentChangeOut(approval_request_id=request["id"])


def propose_policy_values_change(
    uow: UnitOfWork, *, product_id: UUID, body: PolicyValuesChangeIn
) -> PolicyValuesChangeOut:
    """``POST /products/{id}/propose-policy-values-change``: a ``PRINCIPAL_AGENT_CHANGE`` request
    whose approval by a ``config.approve`` holder other than the proposer stores the proposed
    level-P values (04 API-R-23 rev 1.110; POLICIES §0.6; REQ-POL-003; CTL-031; security ruling
    R-21).

    404; 422 for a value the product level does not admit (the findings of ``POST /products``), a
    map equal to the stored one or a blank rationale; 409 ``invalid-transition`` while a request
    for the product is PENDING. The product keeps its values until approval, and a contract past
    DRAFT keeps the values it was first computed with afterwards too (``bundles.ProductPins``).
    """
    session = uow.session
    current = (
        session.execute(
            select(product.c.code, product.c.policy_values)
            .where(product.c.id == product_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if current is None:
        raise Problem("not-found")
    rule_id = products.RULE_POLICY_VALUES
    stored = dict(current["policy_values"] or {})
    proposed = dict(body.policy_values)
    errors = products.policy_values_errors(proposed)
    if not errors and not products.changed_policy_values(stored, proposed):
        errors.append(
            ProblemError(
                field="policy_values", rule_id=rule_id, message=products.POLICY_VALUES_UNCHANGED
            )
        )
    rationale = body.rationale.strip()
    if not rationale:
        errors.append(
            ProblemError(field="rationale", rule_id=rule_id, message=products.RATIONALE_REQUIRED)
        )
    if errors:
        raise Problem("validation-failed", errors=errors)
    code = str(current["code"])
    before = {
        "object_type": subjects.PRODUCT_OBJECT,
        "product_id": str(product_id),
        "product_code": code,
        subjects.POLICY_VALUES: dict(sorted(stored.items())),
    }
    after = subjects.policy_values_proposal(
        product_id=product_id, product_code=code, policy_values=proposed, rationale=rationale
    )
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE,
        subject_id=product_id,
        summary=f"Policy values change for {code}",
        impact_preview=approvals.ImpactPreview(before=before, after=after),
        comment=rationale,
    )
    return PolicyValuesChangeOut(approval_request_id=request["id"])


def put_bundle_components(
    uow: UnitOfWork, *, product_id: UUID, body: BundleComponentsIn
) -> BundleComponentsOut:
    """``PUT /products/{id}/bundle-components``: replace the bundle's component rows (T-REF-21).

    404; 422 lists every finding: the product is not a bundle, row findings (component unknown or
    equal to the bundle, quantity, split ratio, validity, duplicate component or sequence in a
    set) and set findings (one split basis; fixed percentages total 1, REQ-REF-013). Rows are keyed
    by component and ``valid_from``; ``valid_to`` is derived (L2-1-Q-17). Rows not sent are
    deleted, changed rows updated and new rows inserted, each with one AUD-CMD event.
    [J] No contract references a bundle before CTR, so every row stays editable (L2-1-Q-17).
    """
    session = uow.session
    is_bundle = session.execute(
        select(product.c.is_bundle).where(product.c.id == product_id).with_for_update()
    ).scalar_one_or_none()
    if is_bundle is None:
        raise Problem("not-found")
    drafts = [
        products.ComponentDraft(
            component_product_id=item.component_product_id,
            quantity_per_bundle=Decimal(item.quantity_per_bundle),
            split_basis=item.split_basis,
            split_ratio=_exact(item.split_ratio),
            sequence=item.sequence,
            valid_from=item.valid_from,
            valid_to=item.valid_to,
        )
        for item in body.components
    ]
    errors: list[ProblemError] = []
    if drafts and not is_bundle:
        errors.append(
            ProblemError(
                field="is_bundle", rule_id=products.RULE_COMPONENT, message=products.NOT_A_BUNDLE
            )
        )
    wanted_ids = {draft.component_product_id for draft in drafts}
    known = (
        {
            UUID(str(value))
            for value in session.execute(
                select(product.c.id).where(product.c.id.in_(sorted(wanted_ids)))
            ).scalars()
        }
        if wanted_ids
        else set()
    )
    errors += products.component_errors(drafts, product_id, known)
    if errors:
        raise Problem("validation-failed", errors=errors)

    stored = {
        (UUID(str(row["component_product_id"])), row["valid_from"]): row
        for row in session.execute(
            select(product_bundle_component)
            .where(product_bundle_component.c.bundle_product_id == product_id)
            .with_for_update()
        ).mappings()
    }
    wanted = {
        (draft.component_product_id, draft.valid_from): draft
        for draft in products.with_derived_valid_to(drafts)
    }
    principal = uow.principal
    for key in sorted(set(stored) - set(wanted), key=lambda item: (item[1], str(item[0]))):
        row = stored[key]
        session.execute(
            delete(product_bundle_component).where(product_bundle_component.c.id == row["id"])
        )
        uow.audit(
            action=COMPONENT_DELETE_ACTION,
            object_type=COMPONENT_OBJECT,
            object_id=row["id"],
            before=_exact_audit(
                {
                    "bundle_product_id": product_id,
                    "component_product_id": row["component_product_id"],
                    "valid_from": row["valid_from"],
                    **{name: row[name] for name in COMPONENT_VALUES},
                }
            ),
        )
    for key, draft in wanted.items():
        values: dict[str, Any] = {
            "quantity_per_bundle": draft.quantity_per_bundle,
            "split_basis": draft.split_basis,
            "split_ratio": draft.split_ratio,
            "sequence": draft.sequence,
            "valid_to": draft.valid_to,
        }
        existing = stored.get(key)
        if existing is None:
            component_id = new_id()
            identity = {
                "bundle_product_id": product_id,
                "component_product_id": draft.component_product_id,
                "valid_from": draft.valid_from,
            }
            session.execute(
                insert(product_bundle_component).values(
                    tenant_id=principal.tenant_id,
                    id=component_id,
                    **identity,
                    **values,
                    **_stamps(uow),
                )
            )
            uow.audit(
                action=COMPONENT_CREATE_ACTION,
                object_type=COMPONENT_OBJECT,
                object_id=component_id,
                object_version="1",
                after=_exact_audit({**identity, **values}),
            )
            continue
        changed = {name: value for name, value in values.items() if value != existing[name]}
        if changed:
            session.execute(
                update(product_bundle_component)
                .where(product_bundle_component.c.id == existing["id"])
                .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
            )
            uow.audit(
                action=COMPONENT_UPDATE_ACTION,
                object_type=COMPONENT_OBJECT,
                object_id=existing["id"],
                object_version=str(int(existing["row_version"]) + 1),
                before=_exact_audit({name: existing[name] for name in changed}),
                after=_exact_audit(changed),
            )
    return BundleComponentsOut.model_validate(queries.bundle_components_of(session, product_id))
