"""The entity source of every approval subject, over real rows (04 §16.10 rev 1.104 "Entity scope
of a request"; dev-guide DG-KRN-APR-07; REQ-PLT-012; supervisor ruling R-25 on the security review's
findings SN-4 and SC-5).

One tenant, two legal entities with one contract each. For each E-08 subject bound to a legal
entity a row is written on the contract (run, version, item) of entity B, and
``engine.subject_entities`` — what ``submit`` freezes on the request — must name B: the family
sweep of the finding, which named eleven subjects that answered "no entity". The subjects that can
span several entities are read the same way, including the two fail-closed answers (a member the
caller cannot read, an import whose entities cannot be stated), and the rows that name no contract
stay tenant-level.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine
from erev_api.approvals.subjects import ALL_ENTITIES, TENANT_LEVEL, SubjectEntities, spec_for
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    close_checklist_item,
    combination_group,
    combination_group_member,
    contract,
    contract_event,
    estimate,
    estimate_version,
    event_submission,
    exception_item,
    file_object,
    gl_account,
    import_row,
    import_upload,
    judgement_record,
    legal_entity,
    manual_adjustment,
    modification,
    obligation,
    period,
    policy_override,
    product,
    registry_version,
)
from erev_api.domain.imports import commit, csv_v2, legacy_v1
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    FilePurpose,
    RegistryCategory,
    RegistryScope,
)
from erev_api.problems import Problem
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    ROW_BUILDERS,
    ContractRows,
    RowContext,
    account_mapping_rule_values,
    account_mapping_version_values,
    combination_group_member_values,
    combination_group_values,
    contract_event_values,
    estimate_values,
    estimate_version_values,
    event_submission_values,
    exception_item_values,
    file_object_values,
    gl_account_values,
    import_row_values,
    import_upload_values,
    insert_app_user,
    insert_approval_request,
    insert_contract_rows,
    insert_journal_rows,
    judgement_record_values,
    manual_adjustment_values,
    modification_values,
    obligation_values,
    period_values,
    policy_override_values,
    product_values,
    registry_version_values,
)

_S = ApprovalSubjectType
# The registrations of the normalized-row contract column happen when the template packages load,
# and the imports domain registers the entity source of ``IMPORT_COMMIT`` with its lifecycle.
assert csv_v2.TEMPLATES and legacy_v1 is not None and commit.submit_import is not None


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    user_id: UUID
    a: ContractRows  # the contract chain of entity A
    b: ContractRows  # the contract chain of entity B
    events: dict[UUID, UUID]  # contract id → its first event (stream version 1)

    @property
    def row_context(self) -> RowContext:
        return RowContext(self.tenant_id, self.user_id)

    def all_entities(self) -> DbContext:
        return DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")

    def only(self, *entity_ids: UUID) -> DbContext:
        return DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope=tuple(entity_ids))


@pytest.fixture
def world(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> World:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    with identity_session(request_id="tests-approval-subject-entities") as session:
        user_id = insert_app_user(session)
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    events: dict[UUID, UUID] = {}
    with tenant_session(context) as session:
        a = insert_contract_rows(session, tenant_id, head_stream_version=1)
        b = insert_contract_rows(session, tenant_id, head_stream_version=1)
        for chain in (a, b):
            event = contract_event_values(
                tenant_id,
                contract_id=chain.contract_id,
                contracting_entity_id=chain.entity_id,
                stream_version=1,
            )
            session.execute(insert(contract_event).values(**event))
            events[chain.contract_id] = UUID(str(event["id"]))
    assert a.entity_id != b.entity_id
    return World(tenant_id=tenant_id, user_id=user_id, a=a, b=b, events=events)


def _entities(session: Session, subject_type: ApprovalSubjectType, subject_id: UUID) -> Any:
    return engine.subject_entities(session, spec_for(subject_type), subject_id)


def _of(*entity_ids: UUID) -> SubjectEntities:
    return SubjectEntities(frozenset(entity_ids))


def _put(session: Session, table: Any, row: dict[str, Any]) -> UUID:
    session.execute(insert(table).values(**row))
    return UUID(str(row["id"]))


def _adjustment(session: Session, world: World, chain: ContractRows) -> UUID:
    """A DRAFT manual adjustment (T-SL-05) of ``chain``'s contract, in a period of its entity's
    calendar."""
    calendar_id = session.execute(
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == chain.entity_id)
    ).scalar_one()
    period_id = _put(session, period, period_values(world.tenant_id, calendar_id=calendar_id))
    return _put(
        session,
        manual_adjustment,
        manual_adjustment_values(
            world.tenant_id,
            contract_id=chain.contract_id,
            entity_id=chain.entity_id,
            period_id=period_id,
        ),
    )


def test_contract_bound_subjects_name_the_contracting_entity(world: World) -> None:
    """SN-4: ``CONTRACT_ACTIVATION``, ``CONTRACT_VOID``, ``MANUAL_EVENT``, ``ATTRIBUTE_CHANGE``,
    ``POLICY_OVERRIDE``, ``SSP_OVERRIDE``, ``ESTIMATE_VERSION``, a ``JUDGEMENT_RECORD`` that names
    a contract and a ``MANUAL_ADJUSTMENT`` resolve the contracting entity of their contract — B,
    never "no entity" and never A."""
    tenant_id, b = world.tenant_id, world.b
    with tenant_session(world.all_entities()) as session:
        override_id = _put(
            session, policy_override, policy_override_values(tenant_id, contract_id=b.contract_id)
        )
        submission_id = _put(
            session,
            event_submission,
            event_submission_values(
                tenant_id, contract_id=b.contract_id, contracting_entity_id=b.entity_id
            ),
        )
        product_id = _put(session, product, product_values(tenant_id))
        obligation_id = _put(
            session,
            obligation,
            obligation_values(
                tenant_id,
                contract_id=b.contract_id,
                product_id=product_id,
                created_by_event_id=world.events[b.contract_id],
            ),
        )
        element_id = _put(session, estimate, estimate_values(tenant_id, contract_id=b.contract_id))
        version_id = _put(
            session, estimate_version, estimate_version_values(tenant_id, estimate_id=element_id)
        )
        judgement_id = _put(
            session,
            judgement_record,
            judgement_record_values(tenant_id, subject_id=b.contract_id, contract_id=b.contract_id),
        )
        product_judgement_id = _put(
            session,
            judgement_record,
            judgement_record_values(tenant_id, subject_type="product", subject_id=product_id),
        )
        adjustment_id = _adjustment(session, world, b)
        expected = _of(b.entity_id)
        for subject_type, subject_id in (
            (_S.CONTRACT_ACTIVATION, b.contract_id),
            (_S.CONTRACT_VOID, b.contract_id),
            (_S.POLICY_OVERRIDE, override_id),
            (_S.MANUAL_EVENT, submission_id),
            (_S.ATTRIBUTE_CHANGE, submission_id),
            (_S.SSP_OVERRIDE, obligation_id),
            (_S.ESTIMATE_VERSION, version_id),
            (_S.JUDGEMENT_RECORD, judgement_id),
            (_S.MANUAL_ADJUSTMENT, adjustment_id),
        ):
            assert _entities(session, subject_type, subject_id) == expected, subject_type
        # A judgement record that names no contract belongs to no entity.
        assert _entities(session, _S.JUDGEMENT_RECORD, product_judgement_id) == TENANT_LEVEL
        subjects = (
            (_S.POLICY_OVERRIDE, override_id),
            (_S.SSP_OVERRIDE, obligation_id),
            (_S.ESTIMATE_VERSION, version_id),
            (_S.JUDGEMENT_RECORD, judgement_id),
            (_S.MANUAL_ADJUSTMENT, adjustment_id),
        )

    # The contract of B is outside the scope of a session for entity A: the rows that carry no
    # entity of their own (RLS-T) are readable there, the contract is not — and the adjustment,
    # which carries B, is not either — 404, never a tenant-level request that any approver of A
    # would decide.
    with tenant_session(world.only(world.a.entity_id), read_only=True) as session:
        for subject_type, subject_id in subjects:
            with pytest.raises(Problem) as excinfo:
                _entities(session, subject_type, subject_id)
            assert (excinfo.value.slug, excinfo.value.status) == ("not-found", 404), subject_type


def test_run_version_and_item_subjects_name_their_entity(world: World) -> None:
    """SC-5 and the rest of the family: ``JOURNAL_RUN`` names the run's entity, an entity-scope
    ``REGISTRY_VERSION`` that entity, an ``EXCEPTION_WAIVER`` the item's entity — of a checklist
    item, of an exception item, or of the contract an exception item names — and every entity
    for an exception item about the workspace, which holds every entity's close (04 §16.10 rev
    1.218, item EXC-IMPORT-SCOPE-1; a tenant-level request before, which any holder decided).
    A tenant-scope and a book-scope ``REGISTRY_VERSION`` name every entity too: the first
    answers for every entity that states no value of its own, the second for every entity that
    keeps the book, ahead of the entity's own (04 §16.10 rev 1.309, item
    POLICY-TENANT-SCOPE-ALL-ENTITIES-1; a tenant-level request before, which an approver of one
    entity decided for the workspace)."""
    tenant_id, b = world.tenant_id, world.b
    with tenant_session(world.all_entities()) as session:
        journal = insert_journal_rows(session, tenant_id)
        run_entity = UUID(str(journal.run["entity_id"]))
        assert _entities(session, _S.JOURNAL_RUN, UUID(str(journal.run["id"]))) == _of(run_entity)

        scoped = registry_version_values(
            tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            scope=RegistryScope.ENTITY,
            entity_id=b.entity_id,
        )
        tenant_wide = registry_version_values(tenant_id, category=RegistryCategory.CLOSE)
        book_wide = registry_version_values(
            tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            scope=RegistryScope.BOOK,
            book_code=BookCode.ASC606,
        )
        assert _entities(session, _S.REGISTRY_VERSION, _put(session, registry_version, scoped)) == (
            _of(b.entity_id)
        )
        for of_the_workspace in (tenant_wide, book_wide):
            assert _entities(
                session, _S.REGISTRY_VERSION, _put(session, registry_version, of_the_workspace)
            ) == (ALL_ENTITIES)

        checklist = ROW_BUILDERS["close_checklist_item"](world.row_context, session)
        checklist_id = _put(session, close_checklist_item, dict(checklist))
        assert _entities(session, _S.EXCEPTION_WAIVER, checklist_id) == _of(
            UUID(str(checklist["entity_id"]))
        )
        named = _put(
            session, exception_item, exception_item_values(tenant_id, entity_id=b.entity_id)
        )
        by_contract = _put(
            session, exception_item, exception_item_values(tenant_id, contract_id=b.contract_id)
        )
        unbound = _put(session, exception_item, exception_item_values(tenant_id))
        assert _entities(session, _S.EXCEPTION_WAIVER, named) == _of(b.entity_id)
        assert _entities(session, _S.EXCEPTION_WAIVER, by_contract) == _of(b.entity_id)
        assert _entities(session, _S.EXCEPTION_WAIVER, unbound) == ALL_ENTITIES


def test_account_mapping_version_names_the_entities_of_its_rules(world: World) -> None:
    """R-41 (4); 04 §16.10 rev 1.104 row ``ACCOUNT_MAPPING_VERSION``: the request of a mapping
    version is bound to the entities its rules name (T-REF-15 ``entity_id``) — one entity, or
    several — so the approver needs ``config.approve`` for each; a version whose rules name no
    entity is tenant configuration. The rules are tenant rows, so the answer does not depend on the
    reader's scope. Before the ruling every mapping version answered "no entity"."""
    tenant_id, a, b = world.tenant_id, world.a, world.b

    numbers = iter(range(1, 5))

    def version(session: Session, *entity_ids: UUID | None) -> UUID:
        version_id = _put(
            session,
            account_mapping_version,
            account_mapping_version_values(tenant_id, version_no=next(numbers)),
        )
        for entity_id in entity_ids:
            account_id = _put(session, gl_account, gl_account_values(tenant_id))
            _put(
                session,
                account_mapping_rule,
                account_mapping_rule_values(
                    tenant_id,
                    account_mapping_version_id=version_id,
                    gl_account_id=account_id,
                    entity_id=entity_id,
                ),
            )
        return version_id

    with tenant_session(world.all_entities()) as session:
        general = version(session, None)
        for_b = version(session, None, b.entity_id)
        for_both = version(session, a.entity_id, b.entity_id, b.entity_id)
        empty = version(session)
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, general) == TENANT_LEVEL
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, empty) == TENANT_LEVEL
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, for_b) == _of(b.entity_id)
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, for_both) == _of(
            a.entity_id, b.entity_id
        )
        with pytest.raises(Problem) as missing:
            _entities(session, _S.ACCOUNT_MAPPING_VERSION, new_id())
        assert missing.value.slug == "not-found"
    with tenant_session(world.only(a.entity_id), read_only=True) as session:
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, for_both) == _of(
            a.entity_id, b.entity_id
        )
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, for_b) == _of(b.entity_id)


def test_modification_names_both_entities_of_a_regroup_pair(world: World) -> None:
    """A ``MODIFICATION`` names its contracting entity; the ONE spanning request of a
    regroup-after-posting pair names both (04 §16.10 rev 1.70 / 1.104)."""
    tenant_id, a, b = world.tenant_id, world.a, world.b
    regroup_id = new_id()
    with tenant_session(world.all_entities()) as session:
        alone = _put(
            session,
            modification,
            modification_values(
                tenant_id, contract_id=a.contract_id, contracting_entity_id=a.entity_id
            ),
        )
        first = _put(
            session,
            modification,
            modification_values(
                tenant_id,
                contract_id=a.contract_id,
                contracting_entity_id=a.entity_id,
                regroup_id=regroup_id,
            ),
        )
        _put(
            session,
            modification,
            modification_values(
                tenant_id,
                contract_id=b.contract_id,
                contracting_entity_id=b.entity_id,
                regroup_id=regroup_id,
            ),
        )
        assert _entities(session, _S.MODIFICATION, alone) == _of(a.entity_id)
        assert _entities(session, _S.MODIFICATION, first) == _of(a.entity_id, b.entity_id)


def test_modification_names_the_entities_of_every_member_of_its_group(world: World) -> None:
    """R-41 (1), (4) on a subject whose CONTENT reaches past its own entity (the second
    independent review): a ``MODIFICATION`` hashes the state of every member of the contract's
    combination group, read in the decider's session, and its approval recomputes the group. A
    modification of A's contract, which shares its group with a contract of B, is bound to both
    entities — an approver for A alone would hash the group without B's contract and void the
    request as stale. A preparer who cannot read B's contract cannot name its entity: the request
    spans every entity. A contract alone in its group keeps its own entity."""
    tenant_id, a, b = world.tenant_id, world.a, world.b
    with tenant_session(world.all_entities()) as session:
        subject = _put(
            session,
            modification,
            modification_values(
                tenant_id, contract_id=a.contract_id, contracting_entity_id=a.entity_id
            ),
        )
        assert _entities(session, _S.MODIFICATION, subject) == _of(a.entity_id)  # a singleton

        session.execute(
            update(contract)
            .where(contract.c.id == b.contract_id)
            .values(combination_group_id=a.group_id)
        )
        for chain in (a, b):
            _put(
                session,
                combination_group_member,
                combination_group_member_values(
                    tenant_id,
                    combination_group_id=a.group_id,
                    contract_id=chain.contract_id,
                    join_event_id=world.events[chain.contract_id],
                ),
            )
        assert _entities(session, _S.MODIFICATION, subject) == _of(a.entity_id, b.entity_id)
        # What the request hashes: both members, which is what a decider must be able to read.
        content = spec_for(_S.MODIFICATION).content(session, subject)
        (item,) = content["modifications"]
        assert sorted(member["contract_id"] for member in item["members"]) == sorted(
            [str(a.contract_id), str(b.contract_id)]
        )

    # A reader of entity A alone sees the membership (T-CON-04) and not B's contract.
    with tenant_session(world.only(a.entity_id), read_only=True) as session:
        assert _entities(session, _S.MODIFICATION, subject) == ALL_ENTITIES
        (item,) = spec_for(_S.MODIFICATION).content(session, subject)["modifications"]
        assert [member["contract_id"] for member in item["members"]] == [str(a.contract_id)]


def _proposed_group(session: Session, world: World, contract_ids: list[UUID]) -> UUID:
    """A combination as its commands leave it at the submission (04 T-CON-19 "The
    `COMBINATION` topic", rev 1.283; item COMBINATION-PROPOSAL-RECORD-1): the group SUBMITTED,
    and the SUBMITTED ``COMBINATION`` record of action ``JOIN`` naming ``contract_ids`` that
    the group names as its proposal. Before the item the rows were a PROPOSED group that named
    no record and a record of action "COMBINE" — a state no command writes, which the content
    read as "the latest record of the topic"."""
    group = combination_group_values(
        world.tenant_id, is_singleton=False, status="SUBMITTED", criterion="25_9_A"
    )
    record_id = _put(
        session,
        judgement_record,
        judgement_record_values(
            world.tenant_id,
            topic="COMBINATION",
            subject_type="combination_group",
            subject_id=group["id"],
            status="SUBMITTED",
            questionnaire={
                "action": "JOIN",
                "contract_ids": [str(value) for value in contract_ids],
            },
        ),
    )
    return _put(session, combination_group, {**group, "judgement_record_id": record_id})


def test_combination_group_names_the_entities_of_every_reallocated_contract(world: World) -> None:
    """A ``COMBINATION_GROUP`` request names the contracting entities of the proposal's contracts
    and of the members of the groups they would leave; a member the caller cannot read makes the
    subject span every entity instead of dropping the entity it cannot name."""
    tenant_id, a, b = world.tenant_id, world.a, world.b
    with tenant_session(world.all_entities()) as session:
        across = _proposed_group(session, world, [a.contract_id, b.contract_id])
        assert _entities(session, _S.COMBINATION_GROUP, across) == _of(a.entity_id, b.entity_id)

        # The proposal names A's contract alone, but A's contract shares its current group with a
        # contract of B (a member, T-CON-04): leaving that group re-allocates B's contract too.
        session.execute(
            update(contract)
            .where(contract.c.id == b.contract_id)
            .values(combination_group_id=a.group_id)
        )
        for chain in (a, b):
            _put(
                session,
                combination_group_member,
                combination_group_member_values(
                    tenant_id,
                    combination_group_id=a.group_id,
                    contract_id=chain.contract_id,
                    join_event_id=world.events[chain.contract_id],
                ),
            )
        leaving = _proposed_group(session, world, [a.contract_id])
        assert _entities(session, _S.COMBINATION_GROUP, leaving) == _of(a.entity_id, b.entity_id)

    # A preparer whose scope is entity A reads the group and its memberships (RLS-T) and not the
    # contract of B: the request spans every entity.
    with tenant_session(world.only(a.entity_id), read_only=True) as session:
        assert _entities(session, _S.COMBINATION_GROUP, leaving) == ALL_ENTITIES
        assert (
            session.execute(select(contract.c.id).where(contract.c.id == b.contract_id)).first()
            is None
        )


def _upload(
    session: Session,
    world: World,
    template_code: str,
    keys: list[str | None],
    *,
    named: Sequence[UUID] | None = None,
) -> UUID:
    """An upload of ``template_code`` with one VALID row per key in the template's contract
    column (None: a row without the column). ``named`` is what the validation job stores as the
    entities the rows name (T-IMP-02 ``named_entity_ids``; None: not resolved)."""
    file_id = _put(
        session, file_object, file_object_values(world.tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
    )
    upload_id = _put(
        session,
        import_upload,
        import_upload_values(
            world.tenant_id,
            file_object_id=file_id,
            template_code=template_code,
            template_version=1,
            named_entity_ids=None if named is None else list(named),
        ),
    )
    for number, key in enumerate(keys, start=2):
        normalized = {"quantity": "1"} if key is None else {"contract": key, "quantity": "1"}
        _put(
            session,
            import_row,
            import_row_values(
                world.tenant_id,
                import_upload_id=upload_id,
                sheet_name="CSV",
                row_number=number,
                raw=normalized,
                normalized=normalized,
            ),
        )
    return upload_id


def test_import_commit_names_the_entities_the_imports_domain_stored(world: World) -> None:
    """SC-5; supervisor rulings R-29, R-41 (5) and R-87 (1): an ``IMPORT_COMMIT`` request names
    the entities the imports domain resolved for the upload at validation and stored on it
    (T-IMP-02 ``named_entity_ids``) — the named set; no entity for a tenant-level upload, which
    any holder of the step's permission decides; every entity while the set is not resolved. The
    kernel reads it through the lifecycle the imports domain registers and names no column of a
    template; what each template's rows name is that domain's own test
    (``tests/unit/test_import_scope.py``). The set is stored, so the answer does not depend on
    the reader's scope, and an upload that does not exist answers 404."""
    a, b = world.a, world.b
    with tenant_session(world.all_entities()) as session:
        external = {
            chain.contract_id: str(
                session.execute(
                    select(contract.c.external_id).where(contract.c.id == chain.contract_id)
                ).scalar_one()
            )
            for chain in (a, b)
        }
        key_a, key_b = external[a.contract_id], external[b.contract_id]
        usage_a = _upload(session, world, "usage", [key_a, key_a], named=[a.entity_id])
        usage_both = _upload(
            session, world, "usage", [key_a, key_b], named=[a.entity_id, b.entity_id]
        )
        customers = _upload(session, world, "customers", [None], named=[])
        unresolved = _upload(session, world, "usage", [key_a])

        assert _entities(session, _S.IMPORT_COMMIT, usage_a) == _of(a.entity_id)
        assert _entities(session, _S.IMPORT_COMMIT, usage_both) == _of(a.entity_id, b.entity_id)
        assert _entities(session, _S.IMPORT_COMMIT, customers) == TENANT_LEVEL
        assert _entities(session, _S.IMPORT_COMMIT, unresolved) == ALL_ENTITIES
        with pytest.raises(Problem) as missing:
            _entities(session, _S.IMPORT_COMMIT, new_id())
        assert (missing.value.slug, missing.value.status) == ("not-found", 404)

    with tenant_session(world.only(a.entity_id), read_only=True) as session:
        assert _entities(session, _S.IMPORT_COMMIT, usage_both) == _of(a.entity_id, b.entity_id)
        assert _entities(session, _S.IMPORT_COMMIT, usage_a) == _of(a.entity_id)


def _publish_mapping(session: Session, tenant_id: UUID, version_id: UUID) -> None:
    """Walk a mapping version DRAFT → TESTED → SUBMITTED → APPROVED → PUBLISHED, as its commands
    do (DB-04: the E-12 pairs; APPROVED only with an APPROVED request)."""
    where = account_mapping_version.c.id == version_id

    def move(**columns: Any) -> None:
        session.execute(update(account_mapping_version).where(where).values(**columns))

    move(status="TESTED", content_sha256="c" * 64)
    move(status="SUBMITTED")
    request_id = insert_approval_request(
        session,
        tenant_id=tenant_id,
        status=ApprovalRequestStatus.APPROVED,
        subject_type=_S.ACCOUNT_MAPPING_VERSION.value,
        subject_id=version_id,
    )
    move(status="APPROVED", approval_request_id=request_id)
    move(status="PUBLISHED", published_at=datetime(2026, 7, 1, tzinfo=UTC))


def _combine(session: Session, world: World) -> None:
    """B's contract joins the combination group of A's contract (T-CON-03, T-CON-04)."""
    session.execute(
        update(contract)
        .where(contract.c.id == world.b.contract_id)
        .values(combination_group_id=world.a.group_id)
    )
    for chain in (world.a, world.b):
        _put(
            session,
            combination_group_member,
            combination_group_member_values(
                world.tenant_id,
                combination_group_id=world.a.group_id,
                contract_id=chain.contract_id,
                join_event_id=world.events[chain.contract_id],
            ),
        )


def test_contract_subjects_name_every_member_of_their_combination_group(world: World) -> None:
    """Supervisor rulings R-64 (1) and R-70 (b); 04 §16.10 rev 1.104 part 6: every contract
    subject — not the modification alone — is bound to the contracting entities of every current
    member of the contract's combination group, because its approval recomputes or reverses the
    whole group (in its hook, or through the events it appends and the next computation). Each
    subject of A's contract names A while the contract is alone in its group, and A and B once
    B's contract shares the group: an approver for A alone no longer decides a change that moves
    B's figures. Before the ruling every one of them but the modification named A alone. A
    reader who cannot read the other member cannot name its entity: every entity."""
    tenant_id, a, b = world.tenant_id, world.a, world.b
    with tenant_session(world.all_entities()) as session:
        key_a = str(
            session.execute(
                select(contract.c.external_id).where(contract.c.id == a.contract_id)
            ).scalar_one()
        )
        product_id = _put(session, product, product_values(tenant_id))
        element_id = _put(session, estimate, estimate_values(tenant_id, contract_id=a.contract_id))
        subjects = (
            (_S.CONTRACT_ACTIVATION, a.contract_id),
            (_S.CONTRACT_VOID, a.contract_id),
            (
                _S.MODIFICATION,
                _put(
                    session,
                    modification,
                    modification_values(
                        tenant_id, contract_id=a.contract_id, contracting_entity_id=a.entity_id
                    ),
                ),
            ),
            (
                _S.MANUAL_EVENT,
                _put(
                    session,
                    event_submission,
                    event_submission_values(
                        tenant_id, contract_id=a.contract_id, contracting_entity_id=a.entity_id
                    ),
                ),
            ),
            (
                _S.POLICY_OVERRIDE,
                _put(
                    session,
                    policy_override,
                    policy_override_values(tenant_id, contract_id=a.contract_id),
                ),
            ),
            (
                _S.SSP_OVERRIDE,
                _put(
                    session,
                    obligation,
                    obligation_values(
                        tenant_id,
                        contract_id=a.contract_id,
                        product_id=product_id,
                        created_by_event_id=world.events[a.contract_id],
                    ),
                ),
            ),
            (
                _S.ESTIMATE_VERSION,
                _put(
                    session,
                    estimate_version,
                    estimate_version_values(tenant_id, estimate_id=element_id),
                ),
            ),
            (
                _S.JUDGEMENT_RECORD,
                _put(
                    session,
                    judgement_record,
                    judgement_record_values(
                        tenant_id, subject_id=a.contract_id, contract_id=a.contract_id
                    ),
                ),
            ),
            (_S.IMPORT_COMMIT, _upload(session, world, "usage", [key_a], named=[a.entity_id])),
            # CLO-12 at the merge of main 2cbd093d: the approval of an adjustment appends to the
            # contract and recomputes its group; before, the request named A alone.
            (_S.MANUAL_ADJUSTMENT, _adjustment(session, world, a)),
        )
        subjects += ((_S.ATTRIBUTE_CHANGE, dict(subjects)[_S.MANUAL_EVENT]),)
        for subject_type, subject_id in subjects:  # alone in its group: its own entity
            assert _entities(session, subject_type, subject_id) == _of(a.entity_id), subject_type

        _combine(session, world)
        for subject_type, subject_id in subjects:
            assert _entities(session, subject_type, subject_id) == _of(a.entity_id, b.entity_id), (
                subject_type
            )

    # A reader of entity A alone reads the memberships (T-CON-04) and not B's contract.
    with tenant_session(world.only(a.entity_id), read_only=True) as session:
        for subject_type, subject_id in subjects:
            assert _entities(session, subject_type, subject_id) == ALL_ENTITIES, subject_type
    # A reader of entity B alone cannot read the subject's own contract: 404, as before.
    with tenant_session(world.only(b.entity_id), read_only=True) as session:
        for subject_type, subject_id in subjects:
            if subject_type is _S.IMPORT_COMMIT:
                # The upload is a tenant row and its stored set is read; the contract it names is
                # not, so nothing is joined (the engine reads under the tenant's SYSTEM scope).
                assert _entities(session, subject_type, subject_id) == _of(a.entity_id)
                continue
            with pytest.raises(Problem) as excinfo:
                _entities(session, subject_type, subject_id)
            assert (excinfo.value.slug, excinfo.value.status) == ("not-found", 404), subject_type


def test_account_mapping_version_names_the_entities_of_the_version_it_ends(world: World) -> None:
    """Supervisor ruling R-64 (2): a superseding version binds what it ends. A mapping version is
    bound to the entities its own rules name AND to the entities named by the PUBLISHED version
    in force at its ``effective_from`` — the version its approval supersedes or closes. Dropping
    an entity's rules is that entity's change: a version that names A alone, or no entity at
    all, and ends a version with rules for A and B names both. A version that takes effect
    before the one in force began ends nothing of it, and neither does a version without an
    effective date, which publication refuses. Before the ruling the version it ended was not
    read."""
    tenant_id, a, b = world.tenant_id, world.a, world.b
    january, july, october = (datetime(2026, month, 1, tzinfo=UTC) for month in (1, 7, 10))
    numbers = iter(range(1, 12))

    def version(
        session: Session,
        *entity_ids: UUID | None,
        effective_from: datetime | None = None,
        published: bool = False,
    ) -> UUID:
        version_id = _put(
            session,
            account_mapping_version,
            account_mapping_version_values(
                tenant_id, version_no=next(numbers), effective_from=effective_from
            ),
        )
        for entity_id in entity_ids:
            account_id = _put(session, gl_account, gl_account_values(tenant_id))
            _put(
                session,
                account_mapping_rule,
                account_mapping_rule_values(
                    tenant_id,
                    account_mapping_version_id=version_id,
                    gl_account_id=account_id,
                    entity_id=entity_id,
                ),
            )
        if published:
            _publish_mapping(session, tenant_id, version_id)
        return version_id

    with tenant_session(world.all_entities()) as session:
        # In force from July, without an end: rules for A and for B.
        version(session, a.entity_id, b.entity_id, effective_from=july, published=True)
        keeps_a = version(session, a.entity_id, effective_from=october)
        general = version(session, None, effective_from=october)
        earlier = version(session, a.entity_id, effective_from=january)
        undated = version(session, a.entity_id)
        both = _of(a.entity_id, b.entity_id)
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, keeps_a) == both
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, general) == both
        # Before the version in force began: nothing of it ends.
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, earlier) == _of(a.entity_id)
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, undated) == _of(a.entity_id)
    # The answer is the same for a reader of entity A alone: the rules are tenant rows.
    with tenant_session(world.only(a.entity_id), read_only=True) as session:
        assert _entities(session, _S.ACCOUNT_MAPPING_VERSION, keeps_a) == both


def test_real_content_and_entities_are_the_same_for_every_reader(world: World) -> None:
    """Supervisor rulings R-64 (1) and R-70 (b) on REAL subjects — the case the independent review
    found and the probe subjects cannot reach, because their content ignores row-level security.
    A ``MODIFICATION`` of A's contract, whose combination group also holds B's contract, hashes
    the state of every member; a ``CONTRACT_VOID`` hashes the contract's stream. The engine reads
    both under the tenant's SYSTEM scope (``engine.current_content_sha256``,
    ``engine.current_entities``), so the hash and the entity set are the same in a session
    scoped to entity A as in one that reads everything — and the caller's own scope is given
    back. Before the ruling the scoped session hashed the group without B's member (another
    hash: the request was voided as stale by whoever decided it) and answered "every entity"."""
    tenant_id, a, b = world.tenant_id, world.a, world.b
    with tenant_session(world.all_entities()) as session:
        subject = _put(
            session,
            modification,
            modification_values(
                tenant_id, contract_id=a.contract_id, contracting_entity_id=a.entity_id
            ),
        )
        _combine(session, world)
    subjects_read = ((_S.MODIFICATION, subject), (_S.CONTRACT_VOID, a.contract_id))

    def reading(context: DbContext) -> list[tuple[str, Any, int]]:
        with tenant_session(context, read_only=True) as session:
            uow = SimpleNamespace(session=session)
            found = [
                (
                    engine.current_content_sha256(
                        uow,  # type: ignore[arg-type]
                        spec_for(subject_type),
                        {"id": None, "subject_id": subject_id},
                    ),
                    engine.current_entities(
                        uow,  # type: ignore[arg-type]
                        spec_for(subject_type),
                        {"id": None, "subject_id": subject_id},
                    ),
                    # What the caller itself reads afterwards: its own scope again.
                    len(session.scalars(select(contract.c.id)).all()),
                )
                for subject_type, subject_id in subjects_read
            ]
        return found

    everything = reading(world.all_entities())
    scoped = reading(world.only(a.entity_id))
    both = _of(a.entity_id, b.entity_id)
    assert [entities for _, entities, _ in everything] == [both, both]
    assert [(sha, entities) for sha, entities, _ in scoped] == [
        (sha, entities) for sha, entities, _ in everything
    ]
    assert [count for _, _, count in everything] == [2, 2]
    assert [count for _, _, count in scoped] == [1, 1]
