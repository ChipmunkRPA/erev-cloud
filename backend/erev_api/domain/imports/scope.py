"""Entity scope of an import (supervisor rulings R-28, R-29, R-38 (ii), R-41 (5), R-92, R-98;
security findings SC-2 and SC-3; 04 rev 1.107 and 1.147 T-IMP-02 ``named_entity_ids``, table
15.4-B ``IMPORT_ENTITY_NOT_AVAILABLE``, API-R-43, §16.6; 05 rev 1.46 and 1.86 IPL-05, IPL-07,
IPL-10; dev-guide rev 1.90 DG-KRN-DB-05; 03 REQ-PLT-012).

An import runs as SYSTEM on behalf of its uploader WITHIN the uploader's entity scope for the
template's write permission — the permission the equivalent API command needs. The lane decision
L5-1-Q-11 ("the command services an import runs, for every entity") is narrowed by R-29: neither
the upload permission nor the approval says anything about the entities a file names.

``TEMPLATE_SCOPES`` is the table the rulings ask for: per template its write permission, where its
rows name a legal entity (an entity code or id column, the contract a row names, the SSP book a row
names) and what its commit puts in force (R-38 (ii)). A template without an entity source is
tenant-level data.

- ``resolve`` reads, with the job's own every-entity session, the entities EVERY data row names;
  the validation job stores them on the upload (``named_entity_ids``). A key is looked up as the
  exact text of its cell, as the templates' own rules read it — nothing is stripped (ruling R-98
  (2)): a key the scope resolved after stripping and a template then matched unstripped would be
  two different objects. A row that names a reference which does not resolve — an entity code or
  id, the contract of a template that books none, an SSP book — leaves the upload UNRESOLVED
  (``Resolution.unresolved``; stored NULL): "names something unknown" is not "names no entity".
- ``uploader_bounds`` reads the uploader's grants when it is called (validation, dry run, commit):
  ``allowed`` is the scope for the write permission (nothing when the uploader does not hold it)
  and ``db_scope`` the entity scope the job transaction is narrowed to — ``allowed`` for every
  template whose rows can name an entity, whatever the rows of one file name (ruling R-98 (2):
  never the union of the uploader's roles); for a tenant-level template the uploader's own
  entity scope (``Grants.entity_scope``): the union of the entities of a person's roles, the
  entities of an API client. Until 05 rev 1.213 this read "the scope of the uploader's own
  session, as the equivalent API command has it"; since 04 API-C-03 rev 1.319 an API command
  runs under the scope of its own permission, and the job of a tenant-level template is not
  narrowed to it.
- ``narrowed`` re-issues the transaction context with that scope (DG-KRN-DB-05) and restores the
  job's own afterwards, so the cross-file rules, the diff's ``before`` and the command services
  of a template whose rows can name an entity read and write exactly what the equivalent API
  command of the uploader could: a transaction of the write permission (04 API-C-03 rev
  1.319).
- ``findings`` raises ``IMPORT_ENTITY_NOT_AVAILABLE`` for a row naming an entity outside
  ``allowed`` — with the same copy for an entity that does not exist, so the finding never tells
  whether an entity exists (REQ-PLT-012). A contract of such an entity in a contract-keyed
  template needs no finding here: under ``narrowed`` the template's own rule answers
  ``CONTRACT_NOT_FOUND`` exactly as for an unknown contract.
- ONE SET, THE CONTRACTING ENTITIES (supervisor ruling R-114 (g) and the supervisor's word of
  2026-10-01; 04 T-IMP-02 rev 1.256; 05 IPL-08 rev 1.186): the entities an upload names — in
  the row's finding, in the uploader's cover at submit and commit and in the request's named
  entities alike — are the entities its rows WRITE for. A performing entity is none of them:
  the CSV contract line's ``lines.performing_entity_code``, the legacy ``Selling Entity`` of
  a contract's later rows and of a modification's added line. It must exist and need not be
  covered (``TemplateScope.performing_code_columns``), as the booking command itself reads
  it (``contracts.commands._validate``; 05 RCP-18; ruling R-95): who may write a contract
  writes its lines, whichever entity performs them.
- ``visible`` / ``require_visible`` scope the import reads by the caller's ``contract.read``.
- ``named_entity_ids`` is what the ``IMPORT_COMMIT`` approval subject resolves its entities from
  (R-25): ``request_entities`` states it to the approvals kernel, which the subject's lifecycle
  registers (``commit``; supervisor ruling R-87 (1)). ``preparer_entities`` states the entities
  the uploader is held to at submission: those of the rows that commit (R-64 (6)).
- ``approval_floor`` states the approvals the commit of an upload performs by itself (R-38 (ii):
  "an import commit never stands in for a stricter approval") — per underlying subject its
  permission, the upload's entities, the routing flags of the file's content as the dry run
  evaluated them (``CsvTemplate.underlying``) and whether the subject's second step applies.
- ``approver_slots`` routes each of those approvals as a request of the underlying subject would
  be routed now — the subject's own steps, raised by the workspace's PUBLISHED routing rules —
  and counts its approvers in order (supervisor rulings R-92, R-98). ``floor_steps`` and
  ``decider_refusals`` state them to the approvals kernel, which the subject's lifecycle
  registers (``commit``): the ``IMPORT_COMMIT`` request keeps its own step, whose approver
  answers for the first approver of every approval the commit performs, and gains one step per
  further approver; the n-th approver of the request holds, in their own right and for every
  entity of the request, what the n-th approver of each of those approvals needs — checked at
  every decision. ``require_floor_met`` stays the backstop at the decision that approves: an
  approval that does not satisfy the underlying subjects' own steps is refused by name and
  nothing is approved.
- ``UnderlyingApproval.instances`` (item IMP-FLOOR-AMOUNT-1) states, per approval the commit
  performs, the routing facts a request of the underlying subject would carry on its own path —
  its flags and its functional amount — so that the floor is the highest step count any of them
  would have drawn on its own. An instance the dry run could not evaluate says so, and counts
  as the strictest outcome of whatever rule reads it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from erev_engine.currencies import ISO_4217
from sqlalchemy import ColumnElement, Select, and_, or_, select, true
from sqlalchemy.orm import Session

from erev_api.approvals import engine, routing, subjects
from erev_api.auth.permissions import Grants, api_client_grants, effective_grants
from erev_api.auth.principal import Principal
from erev_api.db.session import DbContext, set_tenant_context, tenant_session
from erev_api.db.tables import (
    api_client,
    approval_decision,
    approval_request,
    approval_step,
    contract,
    import_row,
    import_upload,
    legal_entity,
    role,
    role_assignment,
    ssp_book,
    tenant_membership,
)
from erev_api.domain.imports import legacy_templates
from erev_api.domain.imports.csv_v2.framework import Performed
from erev_api.domain.imports.legacy_v1.headers import RowFinding
from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalSubjectType,
    ImportRowStatus,
    MembershipStatus,
    PrincipalKind,
)
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "CODE",
    "CONTRACT_UNIT",
    "READ_PERMISSION",
    "TEMPLATE_SCOPES",
    "UNDERLYING_MEMBER",
    "VERSION_UNIT",
    "ApproverSlot",
    "Bounds",
    "Resolution",
    "TemplateScope",
    "UnderlyingApproval",
    "UnderlyingInstance",
    "approval_floor",
    "approver_slots",
    "committing_entity_ids",
    "covers",
    "decider_refusals",
    "findings",
    "floor_steps",
    "import_principal",
    "key_text",
    "named_contract",
    "named_entity_ids",
    "narrowed",
    "outside",
    "preparer_entities",
    "request_entities",
    "require_covered",
    "require_floor_met",
    "require_visible",
    "resolve",
    "scope_of",
    "stored",
    "underlying_record",
    "uploader_bounds",
    "usable_rows",
    "visible",
    "writing_rows",
]

type Scope = Literal["*"] | frozenset[UUID]

CODE: Final = "IMPORT_ENTITY_NOT_AVAILABLE"  # 04 table 15.4-B (rev 1.107); PRD IMP-127
READ_PERMISSION: Final = "contract.read"  # the guard of the import reads (04 §15.3 API-R-43)
# PRD IMP-127. One copy for an entity outside the uploader's scope and for one that does not
# exist; the name is the text the uploader typed, never a looked-up value.
ENTITY_NOT_AVAILABLE: Final = (
    "Legal entity {entity} is not available for this import. "
    "Upload these rows under a role that covers the entity."
)
NAMED_NOT_AVAILABLE: Final = "{kind} {name} is not available for this import."
CONTRACT_KIND: Final = "Contract"
SSP_BOOK_KIND: Final = "SSP book"
# 05 IPL-10 (rev 1.46): the uploader's scope is read again when the commit runs.
SCOPE_LOST: Final = (
    "Your role no longer covers every legal entity this import names. "
    "Ask an administrator, or upload the rows of each entity under a role that covers it."
)
# The rows a commit loads: VALID and WARNING rows, and AGGREGATED rows with their lead row.
USABLE: Final = (
    ImportRowStatus.VALID.value,
    ImportRowStatus.WARNING.value,
    ImportRowStatus.AGGREGATED.value,
)
# 04 §16.6 API-S-Import ``diff_summary`` (rev 1.107; ruling R-38 (ii)).
UNDERLYING_MEMBER: Final = "underlying_approvals"
# R-38 (ii): the refusals of an approval that does not satisfy the underlying subject's own steps.
FLOOR_PERSON: Final = "Committing this import {act}. It needs the approval of a person."
FLOOR_PERMISSION: Final = (
    "Committing this import {act}. Its approval needs an approver who holds {permission} "
    "for every legal entity the import names."
)
FLOOR_SECOND_STEP: Final = (
    "Committing this import {act}, which needs a second approval{holder}. "
    "It cannot be approved in one step."
)
FLOOR_ROLE_HOLDER: Final = " by a {role}"
# What a quarantine-mode refusal calls the subject a row belongs to (``TemplateScope.unit``).
CONTRACT_UNIT: Final = "contract"
VERSION_UNIT: Final = "SSP version"
# Supervisor ruling R-116 (g): the other objects a file builds from several rows
# (``TemplateScope.object_column``) — each named by the key its rows repeat.
BUNDLE_UNIT: Final = "bundle"
MAPPING_UNIT: Final = "mapping version"
BOOK_UNIT: Final = "SSP book"
RATE_SET_UNIT: Final = "rate set"
# R-92: the refusals of a person who may not give one approval of the request — the first
# approver's is ``FLOOR_PERMISSION``.
FLOOR_LATER_PERMISSION: Final = (
    "Committing this import {act}. Its {nth} approval needs an approver who holds {permission} "
    "for every legal entity the import names."
)
FLOOR_ROLE: Final = (
    "Committing this import {act}. Its {nth} approval needs a holder of the {role} role "
    "for every legal entity the import names."
)
# 05 IPL-09 (rev 1.46): the rule a refused approval of an import is recorded under.
RULE_FLOOR: Final = "IPL-09"
_NTH: Final[Mapping[int, str]] = MappingProxyType(
    {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}
)
# The further steps of the request, as an approver reads them (``floor_steps``).
_STEP_NAMES: Final[Mapping[int, str]] = MappingProxyType(
    {2: "Second approval", 3: "Third approval"}
)


@dataclass(frozen=True, slots=True)
class TemplateScope:
    """Where a template's rows name a legal entity and what guards and follows its commit."""

    write_permission: str  # the permission of the equivalent API command
    entity_code_columns: tuple[str, ...] = ()  # a legal entity code the rows write for
    # A legal entity code a row names without writing for that entity: the performing entity
    # of a contract line. It must exist and need not be covered, and it is no named entity
    # of the upload (ruling R-114 (g): one set, the contracting entities).
    performing_code_columns: tuple[str, ...] = ()
    # ``entity_code_columns`` name the entity a row writes for on the FIRST row of a contract
    # only: the legacy contract setup, whose ``Selling Entity`` is the contracting entity on
    # a contract's first row and the line's performing entity on every row
    # (``legacy_v1.contract_setup._book``).
    contracting_on_first_row: bool = False
    entity_id_columns: tuple[str, ...] = ()  # a legal entity id
    contract_column: str | None = None  # a contract: its contracting entity
    creates_contracts: bool = False  # a contract template: the key may name no contract yet
    ssp_book_column: str | None = None  # an SSP book: its entity, when it has one
    # R-38 (ii): the approval subjects whose act the commit itself performs. Empty for a template
    # that writes transactional data of a source or DRAFT objects that take their own approval.
    puts_in_force: tuple[ApprovalSubjectType, ...] = ()
    # The SSP book version the rows build and the commit approves (the legacy SKU SSP template):
    # the unit of quarantine mode, as the contract is elsewhere (``unit``). It names no entity.
    version_column: str | None = None
    # The object the rows build together where it is neither a contract nor the legacy SSP
    # version, as (the column whose text names it, what a refusal calls it): the bundle whose
    # component rows a ``bundles`` file replaces, the DRAFT version an ``account_mapping`` file
    # builds, the DRAFT version an ``ssp_values`` file builds for a book, the rate set version
    # an ``fx_rates`` file submits (supervisor ruling R-116 (g)). The unit of quarantine mode
    # for those templates (``unit``). It names no entity.
    object_column: tuple[str, str] | None = None

    @property
    def tenant_level(self) -> bool:
        """No row can name a legal entity: tenant-level data (R-41 (5))."""
        return not (
            self.entity_code_columns
            or self.entity_id_columns
            or self.contract_column
            or self.ssp_book_column
        )

    @property
    def unit(self) -> tuple[str, str] | None:
        """The column that names the approval or accounting subject the rows of the template
        build, with what a refusal calls it (supervisor rulings R-98 (10), R-109 (c) and R-116
        (g)): the contract of a template with a contract column, the SSP book version of the
        legacy SKU SSP template, and the object of a template whose rows build one together
        (``object_column``: a bundle, a mapping version, the version of an SSP book, a rate set
        version). In quarantine mode that subject loads whole or not at all — the reviewer of a
        DRAFT sees what the version holds, not what the file meant to put there, and a bundle's
        components are in force at once. A template each of whose rows is an object of its own
        (customers, products, GL accounts) has none and keeps the row-by-row semantics of
        REQ-DAT-008."""
        if self.contract_column is not None:
            return self.contract_column, CONTRACT_UNIT
        if self.version_column is not None:
            return self.version_column, VERSION_UNIT
        return self.object_column


_EVENTS: Final = TemplateScope("event.record", contract_column="contract")
_MASTER_DATA: Final = TemplateScope("masterdata.maintain")
# Every template POST /imports accepts (``validate.ROW_MODELS``); a unit test keeps the two equal.
TEMPLATE_SCOPES: Final[Mapping[str, TemplateScope]] = {
    # --- legacy v1 (04 §17.3, §17.4)
    # the book LEGACY-SKU-SSP has no entity; the commit approves the version (S01-R-05)
    "legacy_sku_ssp": TemplateScope(
        "ssp.create",
        puts_in_force=(ApprovalSubjectType.SSP_BOOK_VERSION,),
        version_column=legacy_templates.SSP_VERSION,
    ),
    # Selling Entity is the contracting entity (first row) and each line's performing entity
    # (every row; R-114 (g): the later rows' must exist and need not be covered); the
    # commit activates the contract (BR-DAT-06), reviews its BS3-D-23 judgement records and
    # approves the VC element versions of its VC rows (S01-R-06)
    "legacy_contract_setup": TemplateScope(
        "contract.create",
        entity_code_columns=(legacy_templates.SELLING_ENTITY,),
        performing_code_columns=(legacy_templates.SELLING_ENTITY,),
        contracting_on_first_row=True,
        contract_column=legacy_templates.CONTRACT,
        creates_contracts=True,
        puts_in_force=(
            ApprovalSubjectType.CONTRACT_ACTIVATION,
            ApprovalSubjectType.JUDGEMENT_RECORD,
            ApprovalSubjectType.ESTIMATE_VERSION,
        ),
    ),
    "legacy_progress_tracking": TemplateScope(
        "event.record", contract_column=legacy_templates.CONTRACT
    ),
    # an ADD row names its selling entity, the performing entity of the line it adds — the
    # contract it changes is the one its key names (R-114 (g)); the import approval approves
    # the modification (L5-1-Q-27)
    "legacy_contract_modification": TemplateScope(
        "modification.create",
        performing_code_columns=(legacy_templates.SELLING_ENTITY,),
        contract_column=legacy_templates.CONTRACT,
        puts_in_force=(ApprovalSubjectType.MODIFICATION,),
    ),
    # --- CSV v2 (04 T-IMP-01, NC-19)
    "customers": _MASTER_DATA,
    "products": _MASTER_DATA,
    # the rows of one bundle replace its component rows (``put_bundle_components``)
    "bundles": TemplateScope("masterdata.maintain", object_column=("product_code", BUNDLE_UNIT)),
    # a DRAFT version of the named book, which follows its own lifecycle
    "ssp_values": TemplateScope(
        "ssp.create",
        ssp_book_column="ssp_book_code",
        object_column=("ssp_book_code", BOOK_UNIT),
    ),
    # DRAFT contracts, which take their own activation approval
    "contracts": TemplateScope(
        "contract.create",
        entity_code_columns=("contracting_entity_code",),
        performing_code_columns=("lines.performing_entity_code",),
        contract_column="external_id",
        creates_contracts=True,
    ),
    "invoices": _EVENTS,
    "progress_events": _EVENTS,
    "usage": _EVENTS,
    "cost_events": _EVENTS,
    "pre_standard_revenue": _EVENTS,
    # DRAFT estimate versions, which take their own approval
    "estimates": TemplateScope("estimate.create", contract_column="contract"),
    # a rate set version submitted for its own FX_RATE_SET_VERSION approval (CTL-031)
    "fx_rates": TemplateScope(
        "masterdata.maintain", object_column=("fx_rate_set_code", RATE_SET_UNIT)
    ),
    # an imported account is available to every entity (``entity_ids`` is no column, L5-1-Q-4)
    "gl_accounts": _MASTER_DATA,
    # a DRAFT mapping version whose rules may name an entity
    "account_mapping": TemplateScope(
        "config.author",
        entity_id_columns=("lines.entity_id",),
        object_column=("name", MAPPING_UNIT),
    ),
}


def scope_of(template_code: str) -> TemplateScope:
    """The scope row of a template; ``LookupError`` for a template without one (fail closed)."""
    found = TEMPLATE_SCOPES.get(template_code)
    if found is None:
        raise LookupError(f"import template {template_code} declares no entity scope")
    return found


def covers(scope: Scope, entity_ids: frozenset[UUID]) -> bool:
    """Whether ``scope`` covers every entity of ``entity_ids``."""
    return scope == "*" or entity_ids <= scope


# --- what the rows name ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Resolution:
    """The entities the data rows name, as the every-entity session resolves them."""

    entity_ids: frozenset[UUID]  # every existing entity any row names
    codes: Mapping[str, UUID]  # entity code → id
    ids: frozenset[UUID]  # the existing entity ids an id column names
    contracts: Mapping[str, UUID]  # existing contract → its contracting entity
    books: Mapping[str, UUID | None]  # existing SSP book → its entity
    # Ruling R-98 (2): a row names a reference that does not resolve — the upload names
    # something this job could not place, so it is not resolved (stored NULL: every entity).
    unresolved: bool = False
    # existing contract → its id: what a finding on a row of that contract names
    # (``named_contract``; item EXC-IMPORT-SCOPE-1)
    contract_ids: Mapping[str, UUID] = dataclasses.field(
        default_factory=lambda: MappingProxyType({})
    )

    @property
    def named(self) -> frozenset[UUID] | None:
        """What the upload stores (04 T-IMP-02 ``named_entity_ids``): the entities the rows name,
        or None when a reference of a row does not resolve."""
        return None if self.unresolved else self.entity_ids


def key_text(value: Any) -> str | None:
    """The exact text of a cell that names something; None for a blank cell. Keys are exact text
    (LM-CL-01) and the templates' own rules read them so (``legacy_v1.headers.text``,
    ``csv_v2.recorded``): nothing is stripped here either (ruling R-98 (2))."""
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _uuid(value: Any) -> UUID | None:
    text = key_text(value)
    if text is None:
        return None
    try:
        return UUID(text)
    except ValueError:
        return None


def _values(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> set[str]:
    found: set[str] = set()
    for row in rows:
        for column in columns:
            text = key_text(row.get(column))
            if text is not None:
                found.add(text)
    return found


def writing_rows(template_code: str, rows: Sequence[Mapping[str, Any]]) -> list[bool]:
    """Per row of ``rows`` (in file order), whether its ``entity_code_columns`` name an entity
    the row writes for: every row — except in a template whose contracting entity stands on
    the first row of each contract (``contracting_on_first_row``), where it is the first row
    that carries each contract key, and a row without a key."""
    spec = scope_of(template_code)
    if not spec.contracting_on_first_row or spec.contract_column is None:
        return [True] * len(rows)
    seen: set[str] = set()
    writing: list[bool] = []
    for cells in rows:
        key = key_text(cells.get(spec.contract_column))
        writing.append(key is None or key not in seen)
        if key is not None:
            seen.add(key)
    return writing


def resolve(session: Session, template_code: str, rows: Sequence[Mapping[str, Any]]) -> Resolution:
    """The entities ``rows`` (each row's cells by template header, in file order) name. The
    caller's session must see every entity: the result is what readers and approvers are
    scoped by. A performing entity is looked up — it must exist — and is no named entity
    (ruling R-114 (g): one set, the contracting entities)."""
    spec = scope_of(template_code)
    codes: dict[str, UUID] = {}
    writing = writing_rows(template_code, rows)
    written = _values(
        [cells for cells, writes in zip(rows, writing, strict=True) if writes],
        spec.entity_code_columns,
    )
    named = written | _values(rows, spec.performing_code_columns)
    if named:
        codes = {
            str(code): UUID(str(entity_id))
            for code, entity_id in session.execute(
                select(legal_entity.c.code, legal_entity.c.id).where(
                    legal_entity.c.code.in_(sorted(named))
                )
            )
        }
    wanted = {value for text in _values(rows, spec.entity_id_columns) if (value := _uuid(text))}
    ids: frozenset[UUID] = frozenset()
    if wanted:
        ids = frozenset(
            UUID(str(entity_id))
            for entity_id in session.scalars(
                select(legal_entity.c.id).where(legal_entity.c.id.in_(sorted(wanted, key=str)))
            )
        )
    contracts: dict[str, UUID] = {}
    contract_ids: dict[str, UUID] = {}
    keys = _values(rows, () if spec.contract_column is None else (spec.contract_column,))
    if keys:
        for external_id, entity_id, contract_id in session.execute(
            select(contract.c.external_id, contract.c.contracting_entity_id, contract.c.id).where(
                contract.c.external_id.in_(sorted(keys))
            )
        ):
            contracts[str(external_id)] = UUID(str(entity_id))
            contract_ids[str(external_id)] = UUID(str(contract_id))
    books: dict[str, UUID | None] = {}
    book_codes = _values(rows, () if spec.ssp_book_column is None else (spec.ssp_book_column,))
    if book_codes:
        books = {
            str(code): None if entity_id is None else UUID(str(entity_id))
            for code, entity_id in session.execute(
                select(ssp_book.c.code, ssp_book.c.entity_id).where(
                    ssp_book.c.code.in_(sorted(book_codes))
                )
            )
        }
    entity_ids = (
        frozenset(entity_id for code, entity_id in codes.items() if code in written)
        | ids
        | frozenset(contracts.values())
        | frozenset(entity_id for entity_id in books.values() if entity_id is not None)
    )
    stated = _values(rows, spec.entity_id_columns)
    unresolved = (
        bool(named - set(codes))
        or any(_uuid(text) not in ids for text in stated)
        # a contract template's key may name no contract yet: the row books it
        or (not spec.creates_contracts and bool(keys - set(contracts)))
        or bool(book_codes - set(books))
    )
    return Resolution(entity_ids, codes, ids, contracts, books, unresolved, contract_ids)


# --- what the uploader may write ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Bounds:
    """The uploader's scope for one template, read at one instant."""

    allowed: Scope  # for the template's write permission; empty when the permission is not held
    db_scope: Scope  # what the job transaction is narrowed to while the file is processed


_NOTHING: Final = Grants(
    roles=(), permissions=frozenset(), permission_scopes=MappingProxyType({}), entity_scope=()
)


def _uploader_grants(session: Session, upload: Mapping[str, Any], *, at: datetime) -> Grants | None:
    """The uploader's grants in force at ``at``; None for an upload no principal created (a system
    path), which no role restricts.

    An API client's upload is held to the narrower of the client's grants and what the access
    token that created the upload carried (supervisor rulings R-98 and R-109 (a); 04 rev 1.147
    T-IMP-02 ``uploader_scopes``): the client's scopes, status, expiry and entities are read NOW,
    and only the codes the creating token carried count — a scope the client gains after the
    upload widens nothing. An upload stored without them (created before revision 0102) holds
    nothing: fail closed."""
    created_by = upload["created_by"]
    if created_by is None:
        return None
    tenant_id = UUID(str(upload["tenant_id"]))
    kind = str(getattr(upload["created_by_kind"], "value", upload["created_by_kind"]))
    if kind == PrincipalKind.API_CLIENT.value:
        carried = upload.get("uploader_scopes")
        known = session.execute(
            select(api_client.c.id).where(
                api_client.c.tenant_id == tenant_id, api_client.c.id == created_by
            )
        ).scalar_one_or_none()
        if known is None or carried is None:
            return _NOTHING
        return api_client_grants(
            session, UUID(str(created_by)), token_scopes=[str(code) for code in carried], at=at
        )
    return _user_grants(session, tenant_id, UUID(str(created_by)), at=at)


def _user_grants(session: Session, tenant_id: UUID, user_id: UUID, *, at: datetime) -> Grants:
    """The grants of a person's ACTIVE membership of the tenant in force at ``at``; nothing
    without one. The tenant is named: ``tenant_membership`` is RLS-TM (04 §2.3), so a person's
    own session also reads that person's memberships of other workspaces, which give nothing
    here."""
    membership_id = session.execute(
        select(tenant_membership.c.id).where(
            tenant_membership.c.tenant_id == tenant_id,
            tenant_membership.c.user_id == user_id,
            tenant_membership.c.status == MembershipStatus.ACTIVE.value,
        )
    ).scalar_one_or_none()
    if membership_id is None:
        return _NOTHING
    return effective_grants(session, UUID(str(membership_id)), at=at)


def uploader_bounds(
    session: Session, upload: Mapping[str, Any], template_code: str, *, at: datetime
) -> Bounds:
    """The uploader's bounds for ``template_code`` at ``at``. The caller's session must read the
    tenant's role assignments (the job's own session does).

    Ruling R-98 (2): the transaction of a template whose rows can name an entity is narrowed to
    the scope of the template's WRITE permission — whatever the rows of this file name, and never
    to the union of the uploader's roles. The contract-event, legacy progress and legacy
    modification emitters check no entity permission of their own: the narrowed scope is their
    guard, so a role that only reads another entity must not let a file write there.

    A tenant-level template is not narrowed so: its transaction runs under the uploader's own
    entity scope (``Grants.entity_scope``; 05 IPL-05 rev 1.213) — wider than the scope of the
    write permission, under which the equivalent API command runs since 04 API-C-03 rev
    1.319, wherever a second role of the uploader names more entities."""
    spec = scope_of(template_code)
    grants = _uploader_grants(session, upload, at=at)
    if grants is None:
        return Bounds(allowed="*", db_scope="*")
    held = grants.permission_scopes.get(spec.write_permission)
    allowed: Scope = frozenset() if held is None else held
    if spec.tenant_level:
        # no row of the template can name an entity: tenant-level data (R-41 (5)), processed
        # under the uploader's own entity scope — the union of the entities of a person's
        # roles, the entities of an API client
        union = grants.entity_scope
        return Bounds(allowed=allowed, db_scope="*" if union == "*" else frozenset(union))
    return Bounds(allowed=allowed, db_scope=allowed)


@contextmanager
def narrowed(uow: UnitOfWork, scope: Scope) -> Iterator[None]:
    """Run the block with the transaction's entity scope narrowed to ``scope`` and the job's own
    context re-issued afterwards (DG-KRN-DB-05 rev 1.90). ``"*"`` changes nothing, and a scope is
    only ever narrowed: a caller already inside ``scope`` keeps its own context."""
    own = uow.principal.db_context
    if scope == "*" or (own.entity_scope != "*" and frozenset(own.entity_scope) <= scope):
        yield
        return
    if own.entity_scope != "*":
        scope = scope & frozenset(own.entity_scope)
    narrow = DbContext(
        tenant_id=own.tenant_id, user_id=own.user_id, entity_scope=tuple(sorted(scope))
    )
    set_tenant_context(uow.session, narrow)
    # No ``finally``: when the block raises, the caller rolls back (the transaction, or a savepoint
    # and then the transaction) and the setting dies with it; until then the scope stays the
    # NARROW one, so nothing ever continues wider than the block left it.
    yield
    set_tenant_context(uow.session, own)


def import_principal(base: Principal, permissions: frozenset[str], scope: Scope) -> Principal:
    """``base`` (the SYSTEM principal on behalf of the uploader) with the import's command
    permissions held for ``scope`` only."""
    return dataclasses.replace(
        base,
        permissions=permissions,
        permission_scopes=MappingProxyType(dict.fromkeys(sorted(permissions), scope)),
        entity_scope="*" if scope == "*" else tuple(sorted(scope)),
    )


# --- findings (04 table 15.4-B) -------------------------------------------------------------------


def findings(
    template_code: str,
    rows: Sequence[tuple[int, Mapping[str, Any]]],
    resolution: Resolution,
    bounds: Bounds,
) -> dict[int, list[RowFinding]]:
    """``IMPORT_ENTITY_NOT_AVAILABLE`` by row number for ``rows`` (row number, cells by header):

    - an entity code or id the row states that is outside ``bounds.allowed`` — or names no entity,
      with the same copy;
    - a performing entity code that names no entity, with that copy too: it must exist and
      need not be covered (ruling R-114 (g));
    - in a contract template, a key that names an existing contract of such an entity (the row
      would replace or collide with a contract the uploader cannot write);
    - an SSP book whose entity is outside ``bounds.allowed`` — or that does not exist, with the
      same copy.
    """
    spec = scope_of(template_code)
    allowed = bounds.allowed
    found: dict[int, list[RowFinding]] = {}

    def add(number: int, column: str, message: str) -> None:
        found.setdefault(number, []).append(RowFinding(CODE, "ERROR", message, column))

    def inside(entity_id: UUID | None) -> bool:
        return entity_id is not None and (allowed == "*" or entity_id in allowed)

    writing = writing_rows(template_code, [cells for _, cells in rows])
    for (number, cells), writes in zip(rows, writing, strict=True):
        refused: set[str] = set()
        for column in spec.entity_code_columns if writes else ():
            code = key_text(cells.get(column))
            if code is not None and not inside(resolution.codes.get(code)):
                add(number, column, ENTITY_NOT_AVAILABLE.format(entity=code))
                refused.add(column)
        for column in spec.performing_code_columns:
            code = key_text(cells.get(column))
            if code is not None and code not in resolution.codes and column not in refused:
                add(number, column, ENTITY_NOT_AVAILABLE.format(entity=code))
        for column in spec.entity_id_columns:
            text = key_text(cells.get(column))
            if text is None:
                continue
            entity_id = _uuid(text)
            if entity_id is None or entity_id not in resolution.ids or not inside(entity_id):
                add(number, column, ENTITY_NOT_AVAILABLE.format(entity=text))
        if spec.creates_contracts and spec.contract_column is not None:
            key = key_text(cells.get(spec.contract_column))
            owner = None if key is None else resolution.contracts.get(key)
            if key is not None and owner is not None and not inside(owner):
                add(
                    number,
                    spec.contract_column,
                    NAMED_NOT_AVAILABLE.format(kind=CONTRACT_KIND, name=key),
                )
        if spec.ssp_book_column is not None:
            book = key_text(cells.get(spec.ssp_book_column))
            if book is not None:
                owner = resolution.books.get(book)
                if book not in resolution.books or (owner is not None and not inside(owner)):
                    add(
                        number,
                        spec.ssp_book_column,
                        NAMED_NOT_AVAILABLE.format(kind=SSP_BOOK_KIND, name=book),
                    )
    return found


def outside(
    template_code: str,
    cells: Mapping[str, Any],
    resolution: Resolution,
    bounds: Bounds,
    *,
    writes: bool = True,
) -> frozenset[UUID]:
    """The entities one row WRITES for that ``bounds.allowed`` does not cover. The validation
    job calls it for every row it is about to keep as usable: such a row naming an entity
    outside the uploader's scope means a rule above did not refuse it, and the job fails
    closed. ``writes`` is the row's entry of ``writing_rows``; a performing entity is not
    written for and does not count (ruling R-114 (g))."""
    if bounds.allowed == "*":
        return frozenset()
    spec = scope_of(template_code)
    named: set[UUID] = set()
    for column in spec.entity_code_columns if writes else ():
        code = key_text(cells.get(column))
        if code is not None and code in resolution.codes:
            named.add(resolution.codes[code])
    for column in spec.entity_id_columns:
        entity_id = _uuid(cells.get(column))
        if entity_id is not None and entity_id in resolution.ids:
            named.add(entity_id)
    if spec.contract_column is not None:
        key = key_text(cells.get(spec.contract_column))
        if key is not None and key in resolution.contracts:
            named.add(resolution.contracts[key])
    if spec.ssp_book_column is not None:
        book = key_text(cells.get(spec.ssp_book_column))
        owner = None if book is None else resolution.books.get(book)
        if owner is not None:
            named.add(owner)
    return frozenset(named) - bounds.allowed


def named_contract(
    template_code: str, cells: Mapping[str, Any], resolution: Resolution, bounds: Bounds
) -> tuple[UUID, UUID] | None:
    """The existing contract one row names and that contract's contracting entity — what a
    finding on the row states (04 T-IMP-05 "An item that names no entity", rev 1.218; item
    EXC-IMPORT-SCOPE-1; supervisor ruling R-121 (k)) — when the contract exists AND lies inside
    the scope the upload writes with (``bounds.allowed``). None for a template without a
    contract column, for a key that names no contract yet, and for a contract of an entity
    outside that scope: such a finding names neither, so that the uploader reads the finding
    on her own row and an existing contract answers exactly as an unknown one
    (REQ-PLT-012)."""
    spec = scope_of(template_code)
    if spec.contract_column is None:
        return None
    key = key_text(cells.get(spec.contract_column))
    if key is None:
        return None
    contract_id, entity_id = resolution.contract_ids.get(key), resolution.contracts.get(key)
    if contract_id is None or entity_id is None:
        return None
    if bounds.allowed != "*" and entity_id not in bounds.allowed:
        return None
    return contract_id, entity_id


# --- the stored set (04 T-IMP-02 ``named_entity_ids``) --------------------------------------------


def stored(upload: Mapping[str, Any]) -> frozenset[UUID] | None:
    """``named_entity_ids`` of an upload row: None = not resolved, empty = tenant-level."""
    value = upload.get("named_entity_ids")
    return None if value is None else frozenset(UUID(str(item)) for item in value)


def named_entity_ids(session: Session, upload_id: UUID) -> frozenset[UUID] | None:
    """The legal entities the upload's rows name: the entities of its ``IMPORT_COMMIT`` request
    (R-25, R-41 (5)). Empty = a tenant-level upload, decidable by any holder of the permission;
    None = not resolved, which only an all-entities scope covers. ``LookupError`` when the upload
    is not visible."""
    row = (
        session.execute(
            select(import_upload.c.id, import_upload.c.named_entity_ids).where(
                import_upload.c.id == upload_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise LookupError(f"import upload {upload_id} is not visible")
    return stored(dict(row))


def request_entities(session: Session, upload_id: UUID) -> subjects.SubjectEntities:
    """``named_entity_ids`` as the approvals kernel freezes it on the ``IMPORT_COMMIT`` request
    (04 §16.10 rev 1.104; R-41 (5), R-87 (1)): the named entities; no entity for a tenant-level
    upload, which any holder of the step's permission decides; every entity for an upload that is
    not resolved. An upload the session cannot read answers 404 — a bound subject never becomes a
    tenant-level request (REQ-PLT-012)."""
    try:
        named = named_entity_ids(session, upload_id)
    except LookupError as error:
        raise Problem("not-found") from error
    return subjects.ALL_ENTITIES if named is None else subjects.SubjectEntities(named)


def usable_rows(upload_id: Any) -> Select[Any]:
    """The usable rows of an upload IN FILE ORDER, whatever order the table holds them in: in
    a template whose contracting entity stands on the first row of a contract
    (``writing_rows``) the order decides which row names it (ruling R-114 (g))."""
    return (
        select(import_row.c.raw, import_row.c.normalized)
        .where(import_row.c.import_upload_id == upload_id, import_row.c.status.in_(USABLE))
        .order_by(import_row.c.sheet_name, import_row.c.row_number)
    )


def committing_entity_ids(upload: Mapping[str, Any]) -> frozenset[UUID] | None:
    """The legal entities named by the rows an upload will COMMIT — what the uploader's scope has
    to cover when the file is submitted and when it is committed (05 IPL-08, IPL-10). Every data
    row of an upload outside quarantine mode is usable once it is VALIDATED, so the set is the
    stored one (None = not resolved). In quarantine mode the refused rows stay behind
    (REQ-DAT-008) — among them the rows that named an entity outside the uploader's scope — so the
    set is read again from the usable rows, in a read-only session over every entity."""
    if not upload["is_quarantine_mode"]:
        return stored(upload)
    context = DbContext(tenant_id=upload["tenant_id"], user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        rows = session.execute(usable_rows(upload["id"]))
        cells = [{**dict(raw or {}), **dict(normalized or {})} for raw, normalized in rows]
        return resolve(session, str(upload["template_code"]), cells).named


def preparer_entities(session: Session, upload_id: UUID) -> subjects.SubjectEntities:
    """The entities the uploader is held to when the upload's ``IMPORT_COMMIT`` request is
    submitted (``SubjectSpec.preparer_entities``; supervisor ruling R-64 (6) with R-29; 05
    IPL-08): those named by the rows that will COMMIT (``committing_entity_ids``) — in quarantine
    mode the usable rows, so an uploader submits a file whose refused rows name an entity outside
    their scope. The request stays bound to every entity any row names (``request_entities``):
    readers and approvers are scoped by that. 404 for an upload the session cannot read."""
    row = (
        session.execute(select(import_upload).where(import_upload.c.id == upload_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    named = committing_entity_ids(dict(row))
    return subjects.ALL_ENTITIES if named is None else subjects.SubjectEntities(named)


def require_covered(named: frozenset[UUID] | None, bounds: Bounds) -> None:
    """403 ``forbidden`` unless ``bounds.allowed`` covers ``named``, the entities the rows to
    commit name (``committing_entity_ids``; 05 IPL-08, IPL-10 rev 1.46: the uploader's scope is
    read when the file is submitted and when it is committed). An unresolved set (None) needs an
    all-entities scope."""
    if bounds.allowed == "*":
        return
    if named is None or not named <= bounds.allowed:
        raise Problem("forbidden", SCOPE_LOST)


# --- the approvals a commit performs (ruling R-38 (ii)) ------------------------------------------

# What the commit performs, as a refusal names it.
_ACTS: Final[Mapping[ApprovalSubjectType, str]] = MappingProxyType(
    {
        ApprovalSubjectType.SSP_BOOK_VERSION: "approves its SSP book version",
        ApprovalSubjectType.CONTRACT_ACTIVATION: "activates its contracts",
        ApprovalSubjectType.JUDGEMENT_RECORD: "reviews the judgement records of its contracts",
        ApprovalSubjectType.ESTIMATE_VERSION: "approves its variable consideration estimates",
        ApprovalSubjectType.MODIFICATION: "approves its contract modifications",
    }
)


@dataclass(frozen=True, slots=True)
class UnderlyingApproval:
    """One approval the commit of an upload performs by itself (R-38 (ii)): the underlying
    subject's own step, which the ``IMPORT_COMMIT`` approval has to satisfy."""

    subject_type: ApprovalSubjectType
    permission: str  # the underlying subject's step permission
    min_approvers: int
    entity_ids: frozenset[UUID] | None  # the upload's named entities; None = every entity
    flags: frozenset[str]  # the subject's routing flags of the file's content
    evaluated: bool  # False: the file did not let the flags be evaluated
    second_step: bool  # the subject's second step applies, or cannot be ruled out
    second_step_role: str | None  # the role code that narrows that step, when it has one
    # Item IMP-FLOOR-AMOUNT-1: the distinct routing facts among the approvals of this subject
    # the commit performs — what each would carry as a request of its own.
    instances: tuple[UnderlyingInstance, ...] = ()


@dataclass(frozen=True, slots=True)
class UnderlyingInstance:
    """The routing facts of ``count`` approvals of one subject that the commit performs, as a
    request of that subject would carry them on its own path (item IMP-FLOOR-AMOUNT-1). An
    instance that is not evaluated counts as the strictest outcome of a rule that reads the
    fact: its flags as the subject's second-step flags, its amount as every routing some amount
    could reach (``approver_slots``; ruling R-109 (d) as answered on 2026-10-01)."""

    flags: frozenset[str]
    evaluated: bool  # False: the flags could not be evaluated
    amount: tuple[Decimal, str] | None  # the request's functional amount; None = it has none
    amount_evaluated: bool  # False: the amount could not be stated
    count: int


# An approval of which nothing was stated: an upload diffed before the dry run recorded it.
_UNSTATED: Final = UnderlyingInstance(
    flags=frozenset(), evaluated=False, amount=None, amount_evaluated=False, count=1
)


def _money_text(amount: Decimal, currency: str) -> str:
    """``amount`` as the API writes money (API-C-06): at the minor unit of ``currency`` — unless
    it carries finer digits, which are kept: a routing fact is never rounded here."""
    known = ISO_4217.get(currency)
    if known is not None:
        at_minor_unit = amount.quantize(Decimal(1).scaleb(-known.minor_unit))
        if at_minor_unit == amount:
            return format(at_minor_unit, "f")
    return format(amount, "f")


def _instance_record(item: Performed, count: int) -> dict[str, Any]:
    return {
        "flags": sorted(item.flags or ()),
        "evaluated": item.flags is not None,
        "amount": (
            None
            if item.amount is None
            else {"amount": _money_text(*item.amount), "currency": item.amount[1]}
        ),
        "amount_evaluated": item.amount_evaluated,
        "count": count,
    }


def _instance_order(record: Mapping[str, Any]) -> tuple[Any, ...]:
    amount = record["amount"]
    return (
        record["evaluated"],
        record["flags"],
        record["amount_evaluated"],
        amount is not None,
        "" if amount is None else amount["currency"],
        Decimal(0) if amount is None else Decimal(amount["amount"]),
    )


def underlying_record(
    performed: Mapping[ApprovalSubjectType, Sequence[Performed]],
) -> list[dict[str, Any]]:
    """``diff_summary.underlying_approvals`` (04 §16.6 rev 1.147): what the dry run found the
    commit to perform. Per approval subject: ``flags``, the union of the routing flags of its
    approvals; ``evaluated``, false when the flags of one of them could not be evaluated; and
    ``instances`` (item IMP-FLOOR-AMOUNT-1), the distinct routing facts among those approvals —
    flags, functional amount, whether each was evaluated — with the number of approvals that
    carry them, in a fixed order (the diff file's hash is part of the approved content)."""
    record: list[dict[str, Any]] = []
    for subject, items in sorted(performed.items(), key=lambda item: item[0].value):
        counts: dict[Performed, int] = {}
        for item in items:
            counts[item] = counts.get(item, 0) + 1
        record.append(
            {
                "subject_type": subject.value,
                "flags": sorted({flag for item in items for flag in item.flags or ()}),
                "evaluated": all(item.flags is not None for item in items),
                "instances": sorted(
                    (_instance_record(item, count) for item, count in counts.items()),
                    key=_instance_order,
                ),
            }
        )
    return record


def _instances(item: Mapping[str, Any]) -> tuple[UnderlyingInstance, ...]:
    """The instances an ``underlying_approvals`` entry states. An entry written before the member
    existed states one approval with the entry's flags and no amount: its amount is not
    evaluated (fail closed)."""
    stated = item.get("instances")
    if not isinstance(stated, list) or not stated:
        return (
            UnderlyingInstance(
                flags=frozenset(str(flag) for flag in item.get("flags") or ()),
                evaluated=item.get("evaluated") is True,
                amount=None,
                amount_evaluated=False,
                count=1,
            ),
        )
    found: list[UnderlyingInstance] = []
    for entry in stated:
        amount = entry.get("amount")
        found.append(
            UnderlyingInstance(
                flags=frozenset(str(flag) for flag in entry.get("flags") or ()),
                evaluated=entry.get("evaluated") is True,
                amount=(
                    None
                    if not isinstance(amount, Mapping)
                    else (Decimal(str(amount["amount"])), str(amount["currency"]))
                ),
                amount_evaluated=entry.get("amount_evaluated") is True,
                count=int(entry.get("count") or 1),
            )
        )
    return tuple(found)


def approval_floor(session: Session, upload_id: UUID) -> tuple[UnderlyingApproval, ...]:
    """The approvals the commit of the upload performs by itself, each with the underlying
    subject's own permission, the upload's entities, the flags of the file's content and whether
    the subject's second step applies (R-38 (ii)). Empty for a template whose commit writes
    transactional data or DRAFT objects that take their own approval.

    The dry run states what the commit performs (``diff_summary.underlying_approvals``); an upload
    without that statement answers for every approval its template can perform, unevaluated. A
    second step applies when the evaluated flags meet the subject's second-step flags, and — so
    that nothing is approved short — whenever the flags were not evaluated and the subject has a
    second step at all. ``instances`` passes on what each of those approvals would carry as a
    request of its own (item IMP-FLOOR-AMOUNT-1). ``LookupError`` when the upload is not
    visible."""
    row = (
        session.execute(
            select(
                import_upload.c.template_code,
                import_upload.c.named_entity_ids,
                import_upload.c.diff_summary,
            ).where(import_upload.c.id == upload_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise LookupError(f"import upload {upload_id} is not visible")
    declared = scope_of(str(row["template_code"])).puts_in_force
    if not declared:
        return ()
    recorded = (row["diff_summary"] or {}).get(UNDERLYING_MEMBER)
    performed: dict[ApprovalSubjectType, frozenset[str] | None]
    stated: dict[ApprovalSubjectType, tuple[UnderlyingInstance, ...]] = {}
    if isinstance(recorded, list):
        performed = {
            ApprovalSubjectType(str(item["subject_type"])): (
                frozenset(str(flag) for flag in item.get("flags") or ())
                if item.get("evaluated") is True
                else None
            )
            for item in recorded
        }
        stated = {
            ApprovalSubjectType(str(item["subject_type"])): _instances(item) for item in recorded
        }
    else:
        performed = dict.fromkeys(declared)
    named = stored(dict(row))
    floor: list[UnderlyingApproval] = []
    for subject in (*declared, *(item for item in performed if item not in declared)):
        if subject not in performed:
            continue
        flags = performed[subject]
        spec = subjects.spec_for(subject)
        second = (
            bool(spec.second_step_flags) if flags is None else bool(flags & spec.second_step_flags)
        )
        floor.append(
            UnderlyingApproval(
                subject_type=subject,
                permission=spec.required_permission,
                min_approvers=spec.min_approvers,
                entity_ids=named,
                flags=frozenset() if flags is None else flags,
                evaluated=flags is not None,
                second_step=second,
                second_step_role=spec.second_step_role if second else None,
                instances=stated.get(subject, (_UNSTATED,)),
            )
        )
    return tuple(floor)


# --- the approvers of a request (rulings R-92, R-98) ------------------------------------------


@dataclass(frozen=True, slots=True)
class ApproverSlot:
    """One approver an approval the commit performs takes (supervisor ruling R-92): the
    underlying subject, the permission of the step that approver decides there and the code of
    the role that narrows the step, when it names one."""

    subject_type: ApprovalSubjectType
    permission: str
    role: str | None


def approver_slots(
    session: Session, upload_id: UUID, entities: subjects.SubjectEntities, *, at: datetime
) -> tuple[tuple[ApproverSlot, ...], ...]:
    """Per approval the commit of the upload performs (``approval_floor``), the approvers a
    request of the underlying subject would take now, one slot per approver in step order
    (supervisor rulings R-38 (ii), R-92, R-98 and R-109 (d); item IMP-FLOOR-AMOUNT-1): the
    subject's own steps raised by the workspace's PUBLISHED routing rules, exactly as
    ``engine.routed_steps`` routes a request with the facts the dry run states for that approval
    (``UnderlyingApproval.instances``) — the subject type, the codes of ``entities`` (the
    entities of the ``IMPORT_COMMIT`` request), its flags and its functional amount. Every
    distinct instance is a list of its own: nothing is reduced to the longest, because two lists
    of one length can ask for different permissions or roles. What the dry run could not state
    counts as the strictest outcome: unevaluated flags as the subject's second-step flags, and an
    unevaluated amount as every routing some amount could reach
    (``engine.possible_routed_steps``), each a list of its own. The caller reads under the
    tenant's SYSTEM scope. ``subjects.SubjectNotVisible`` when the upload row is gone."""
    try:
        floor = approval_floor(session, upload_id)
    except LookupError as error:
        known = session.execute(
            select(import_upload.c.id).where(import_upload.c.id == upload_id)
        ).first()
        if known is None:
            raise subjects.SubjectNotVisible(str(error)) from error
        raise
    if not floor:
        return ()
    codes = engine.entity_codes(session, entities)
    found: list[tuple[ApproverSlot, ...]] = []
    for item in floor:
        spec = subjects.spec_for(item.subject_type)
        for instance in item.instances:
            flags = sorted(instance.flags if instance.evaluated else spec.second_step_flags)
            if instance.amount_evaluated:
                amount = None if instance.amount is None else instance.amount[0]
                routings: tuple[routing.Routing, ...] = (
                    engine.routed_steps(
                        session, spec, entity_codes=codes, amount=amount, flags=flags, at=at
                    ),
                )
            else:
                routings = engine.possible_routed_steps(
                    session, spec, entity_codes=codes, flags=flags, at=at
                )
            for routed in routings:
                roles = engine.role_codes(session, routed.steps)
                slots = tuple(
                    ApproverSlot(
                        subject_type=item.subject_type,
                        permission=step.permission,
                        role=None if step.role_id is None else roles[step.role_id],
                    )
                    for step in routed.steps
                    for _ in range(step.min_approvers)
                )
                if slots not in found:
                    found.append(slots)
    return tuple(found)


def floor_steps(
    session: Session, upload_id: UUID, entities: subjects.SubjectEntities, at: datetime
) -> tuple[subjects.FloorStep, ...]:
    """The further steps of the upload's ``IMPORT_COMMIT`` request (``SubjectSpec.floor``;
    supervisor ruling R-92). The request keeps its own step, whose approver answers for the
    first approver of every approval the commit performs (``decider_refusals``); what one step
    cannot hold — a further approver of any of those approvals: the underlying subject's second
    step, a step a routing rule adds to it — becomes one step each, with the permission and the
    role of the first approval, in template order, that takes such an approver. Two approvals
    that both take a second approver therefore share ONE further step and one person, who holds
    what both ask (``decider_refusals``): the import asks for as many people as the direct path,
    never more. Empty for an upload whose commit performs no approval."""
    slots = approver_slots(session, upload_id, entities, at=at)
    depth = max((len(item) for item in slots), default=0)
    steps: list[subjects.FloorStep] = []
    for ordinal in range(2, depth + 1):
        slot = next(item[ordinal - 1] for item in slots if len(item) >= ordinal)
        steps.append(
            subjects.FloorStep(
                name=_STEP_NAMES.get(ordinal, f"Approval {ordinal}"),
                permission=slot.permission,
                role=slot.role,
            )
        )
    return tuple(steps)


def approvers_in_order(session: Session, approval_request_id: UUID) -> list[UUID]:
    """The persons who approved the request, in the order of their approvals: by step, then by
    the instant of the decision — and by its id, which is time-ordered, for two decisions of
    one instant."""
    return [
        UUID(str(approver_id))
        for approver_id in session.scalars(
            select(approval_decision.c.approver_id)
            .select_from(
                approval_decision.join(
                    approval_step,
                    and_(
                        approval_step.c.tenant_id == approval_decision.c.tenant_id,
                        approval_step.c.id == approval_decision.c.approval_step_id,
                    ),
                )
            )
            .where(
                approval_decision.c.approval_request_id == approval_request_id,
                approval_decision.c.decision == ApprovalDecisionKind.APPROVE.value,
                approval_decision.c.approver_kind == PrincipalKind.USER.value,
                approval_decision.c.approver_id.is_not(None),
            )
            .order_by(
                approval_step.c.step_no,
                approval_decision.c.decided_at,
                approval_decision.c.id,
            )
        )
    ]


def answering_approvers(
    session: Session, upload_id: UUID, approval_request_id: UUID, *, at: datetime
) -> dict[ApprovalSubjectType, UUID]:
    """Per approval subject the commit of the upload performs, the person who answered for it
    (supervisor ruling R-98 (9) as refined on 2026-10-01; 04 §16.10 rev 1.198): the approver of
    the request's approval number k, where k is the number of approvers a request of that
    subject takes for this upload — the longest of its lists (``approver_slots``) — and the
    request's approvals are counted in the order they were given. A subject with one approver
    is answered for by the FIRST approver of the request, whom ``decider_refusals`` held to that
    subject's permission, and not by whoever decided the request's last step. Where the routing
    in force now asks for more approvers than the request took — a rule published after the
    decision — the last approver stands. Empty for a request no person approved. The caller
    reads under the tenant's SYSTEM scope."""
    request = (
        session.execute(
            select(approval_request).where(approval_request.c.id == approval_request_id)
        )
        .mappings()
        .one_or_none()
    )
    if request is None:
        return {}
    approvers = approvers_in_order(session, approval_request_id)
    if not approvers:
        return {}
    depth: dict[ApprovalSubjectType, int] = {}
    entities = engine.request_entities(dict(request))
    for slots in approver_slots(session, upload_id, entities, at=at):
        if slots:
            subject = slots[0].subject_type
            depth[subject] = max(depth.get(subject, 0), len(slots))
    return {subject: approvers[min(count, len(approvers)) - 1] for subject, count in depth.items()}


def _nth(ordinal: int) -> str:
    return _NTH.get(ordinal, f"{ordinal}th")


def _slot_refusal(
    session: Session,
    tenant_id: UUID,
    slot: ApproverSlot,
    ordinal: int,
    *,
    role: bool,
) -> subjects.DeciderRefusal:
    """The refusal of a person who lacks what ``slot`` asks — its permission, or (``role``) its
    role — with the facts its ``DENIED`` audit event records."""
    act = _ACTS[slot.subject_type]
    if role and slot.role is not None:
        detail = FLOOR_ROLE.format(
            act=act, nth=_nth(ordinal), role=_role_name(session, tenant_id, slot.role)
        )
    elif ordinal == 1:
        detail = FLOOR_PERMISSION.format(act=act, permission=slot.permission)
    else:
        detail = FLOOR_LATER_PERMISSION.format(
            act=act, nth=_nth(ordinal), permission=slot.permission
        )
    return subjects.DeciderRefusal(
        problem=Problem("forbidden", detail),
        permission=slot.permission,
        detail={
            "rule_id": RULE_FLOOR,
            "underlying_subject_type": slot.subject_type.value,
            "approval": ordinal,
            "role": slot.role if role else None,
        },
    )


def decider_refusals(
    session: Session,
    upload_id: UUID,
    entities: subjects.SubjectEntities,
    ordinal: int,
    user_ids: Collection[UUID],
    at: datetime,
) -> dict[UUID, subjects.DeciderRefusal]:
    """``SubjectSpec.deciders`` of ``IMPORT_COMMIT`` (supervisor ruling R-92; 05 IPL-09): the
    person who gives approval number ``ordinal`` of the request answers for approver number
    ``ordinal`` of every approval the commit performs (``approver_slots``), so they hold — in
    their own right, in this workspace, for every entity of the request (``entities``) — the
    permission of that step and its role, when it names one. A delegation conveys
    ``import.approve``, the permission of the request's own step, and nothing of the underlying
    subject. Per person of ``user_ids`` who does not: the refusal by name. Nobody is refused for
    an approval none of the commit's approvals takes, nor for an upload whose commit performs
    none. The grants are read now, as the uploader's scope is (05 IPL-10)."""
    needed = [
        item[ordinal - 1]
        for item in approver_slots(session, upload_id, entities, at=at)
        if len(item) >= ordinal
    ]
    if not needed:
        return {}
    tenant_id = UUID(
        str(
            session.execute(
                select(import_upload.c.tenant_id).where(import_upload.c.id == upload_id)
            ).scalar_one()
        )
    )
    refused: dict[UUID, subjects.DeciderRefusal] = {}
    for user_id in user_ids:
        grants = _user_grants(session, tenant_id, user_id, at=at)
        for slot in needed:
            held = grants.permission_scopes.get(slot.permission)
            if held is None or not entities.covered_by(held):
                refused[user_id] = _slot_refusal(session, tenant_id, slot, ordinal, role=False)
                break
            if slot.role is None:
                continue
            scope = _role_scope(session, tenant_id, user_id, slot.role, at=at)
            if scope is None or not entities.covered_by(scope):
                refused[user_id] = _slot_refusal(session, tenant_id, slot, ordinal, role=True)
                break
    return refused


def _held(scope: Scope | None, entity_ids: frozenset[UUID] | None) -> bool:
    """Whether a scope a person holds covers the upload's entities: an unresolved upload (None)
    needs every entity, a tenant-level one (empty) any holder (R-41 (5))."""
    if scope is None:
        return False
    return scope == "*" or (entity_ids is not None and entity_ids <= scope)


def _role_scope(
    session: Session, tenant_id: UUID, user_id: UUID, role_code: str, *, at: datetime
) -> Scope | None:
    """The entities the person's assignments of the role in the tenant in force at ``at`` cover
    (R-25: a role requirement is met only by an assignment that covers the subject's entities);
    None without one. A role the person holds in another workspace counts for nothing."""
    rows = session.execute(
        select(role_assignment.c.is_all_entities, role_assignment.c.entity_ids)
        .select_from(
            role_assignment.join(
                role,
                and_(
                    role.c.tenant_id == role_assignment.c.tenant_id,
                    role.c.id == role_assignment.c.role_id,
                ),
            ).join(
                tenant_membership,
                and_(
                    tenant_membership.c.tenant_id == role_assignment.c.tenant_id,
                    tenant_membership.c.id == role_assignment.c.membership_id,
                ),
            )
        )
        .where(
            role_assignment.c.tenant_id == tenant_id,
            tenant_membership.c.user_id == user_id,
            tenant_membership.c.status == MembershipStatus.ACTIVE.value,
            role.c.code == role_code,
            role.c.is_active.is_(True),
            role_assignment.c.revoked_at.is_(None),
            role_assignment.c.valid_from <= at,
            or_(role_assignment.c.valid_to.is_(None), role_assignment.c.valid_to > at),
        )
    ).all()
    if not rows:
        return None
    if any(item.is_all_entities for item in rows):
        return "*"
    return frozenset(UUID(str(value)) for item in rows for value in item.entity_ids or ())


def _role_name(session: Session, tenant_id: UUID, role_code: str) -> str:
    found = session.execute(
        select(role.c.name).where(role.c.tenant_id == tenant_id, role.c.code == role_code)
    ).scalar()
    return role_code if found is None else str(found)


def require_floor_met(
    session: Session, upload_id: UUID, approval_request_id: UUID, *, at: datetime
) -> None:
    """The backstop of R-38 (ii) at the decision that would approve the ``IMPORT_COMMIT`` request
    (the caller is the subject's approval hook, so a refusal undoes the decision and nothing is
    approved): every approval the commit performs is satisfied by the people who approved the
    request — one of them holds the underlying subject's permission for every entity the upload
    names, and where that subject's second step applies a second one does too, holding the step's
    role over those entities when it names one. 403 ``forbidden`` by name otherwise. The grants
    are read now, as the scope of the uploader is (05 IPL-10)."""
    floor = approval_floor(session, upload_id)
    if not floor:
        return
    tenant_id = UUID(
        str(
            session.execute(
                select(import_upload.c.tenant_id).where(import_upload.c.id == upload_id)
            ).scalar_one()
        )
    )
    approvers = [
        UUID(str(approver_id))
        for approver_id in session.scalars(
            select(approval_decision.c.approver_id)
            .where(
                approval_decision.c.approval_request_id == approval_request_id,
                approval_decision.c.decision == ApprovalDecisionKind.APPROVE.value,
                approval_decision.c.approver_kind == PrincipalKind.USER.value,
                approval_decision.c.approver_id.is_not(None),
            )
            .distinct()
        )
    ]
    if not approvers:
        raise Problem("forbidden", FLOOR_PERSON.format(act=_ACTS[floor[0].subject_type]))
    grants = {approver: _user_grants(session, tenant_id, approver, at=at) for approver in approvers}
    for item in floor:
        act = _ACTS[item.subject_type]
        qualified = [
            approver
            for approver in approvers
            if _held(grants[approver].permission_scopes.get(item.permission), item.entity_ids)
        ]
        if len(qualified) < item.min_approvers:
            raise Problem("forbidden", FLOOR_PERMISSION.format(act=act, permission=item.permission))
        if not item.second_step:
            continue
        role_code = item.second_step_role
        seconded = [
            approver
            for approver in qualified
            if role_code is None
            or _held(_role_scope(session, tenant_id, approver, role_code, at=at), item.entity_ids)
        ]
        if len(qualified) < item.min_approvers + 1 or not seconded:
            holder = (
                ""
                if role_code is None
                else FLOOR_ROLE_HOLDER.format(role=_role_name(session, tenant_id, role_code))
            )
            raise Problem("forbidden", FLOOR_SECOND_STEP.format(act=act, holder=holder))


# --- reads (04 §15.3 API-R-43) --------------------------------------------------------------------


def visible(principal: Principal) -> ColumnElement[bool]:
    """The ``import_upload`` rows ``principal`` may read: its own uploads, and the uploads whose
    every named entity its ``contract.read`` scope covers. A tenant-level upload (empty set) is
    readable by every holder; an unresolved one (NULL) by an all-entities holder only."""
    scope = principal.permission_scopes.get(READ_PERMISSION)
    if scope == "*":
        return true()
    own = import_upload.c.created_by == principal.id
    if scope is None:
        return own
    covered: ColumnElement[bool] = import_upload.c.named_entity_ids.contained_by(
        sorted(scope, key=str)
    )
    return own | covered


def require_visible(principal: Principal, upload: Mapping[str, Any]) -> None:
    """404 ``not-found`` unless ``principal`` may read ``upload`` — exactly the answer of an
    unknown id (REQ-PLT-012)."""
    scope = principal.permission_scopes.get(READ_PERMISSION)
    if scope == "*":
        return
    if upload["created_by"] is not None and upload["created_by"] == principal.id:
        return
    named = stored(upload)
    if scope is None or named is None or not named <= scope:
        raise Problem("not-found")
