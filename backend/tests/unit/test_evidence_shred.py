"""The ``EVIDENCE_SHRED`` approval subject and its pure rules (supervisor rulings R-49 (a) and
R-86 (b), (c); 04 rev 1.142 E-08, §16.10, API-R-12; 05 rev 1.81 PRV-07 b; PRD §2.5 rev 1.71). No
database: the subject specification, the proposal, the entities the request is bound to and the
routing floor. The database witnesses are ``tests/domain/platform/test_file_evidence.py``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from erev_api.approvals import routing, subjects
from erev_api.auth import permissions
from erev_api.domain.demo.avenmoor import policies as demo_policies
from erev_api.domain.platform import evidence_shred, file_evidence
from erev_api.domain.policies import rule_sets
from erev_api.enums import ApprovalSubjectType

US = UUID(int=0x0A)
UK = UUID(int=0x0B)
FILE = UUID(int=0xF1)
UPLOAD = UUID(int=0xA1)
STUDY = UUID(int=0xA2)
FILE_ROW = {"id": FILE, "sha256": "ab" * 32 + " ", "purpose": "SSP_STUDY"}
REASON = "DSR-2026-0917 erasure"


def lifted(
    table: str, *, label: str, row_id: UUID, entities: frozenset[UUID] | None
) -> file_evidence.Hold:
    reference = next(
        item for item in file_evidence.EVIDENCE if item.approval and item.table == table
    )
    return file_evidence.Hold(reference, label, row_id, entities)


def proposed(found: list[file_evidence.Hold]) -> dict[str, Any]:
    """The proposal ``request_shred`` hashes for a file that ``found`` holds."""
    return subjects.evidence_shred_proposal(
        FILE_ROW,
        evidence_shred._described(found),
        reason=REASON,
        entity_ids=evidence_shred._entities(found),
    )


def test_the_subject_is_the_file_and_hashes_its_proposal() -> None:
    spec = subjects.spec_for(ApprovalSubjectType.EVIDENCE_SHRED)
    assert (spec.table, spec.required_permission, spec.min_approvers) == (
        subjects.EVIDENCE_SHRED_OBJECT,
        subjects.EVIDENCE_SHRED_PERMISSION,
        1,
    )
    assert (spec.table, spec.required_permission) == ("file_object", "config.approve")
    assert spec.proposal_content is not None and not spec.revenue_affecting
    assert not spec.second_step_flags and spec.second_step_role is None
    # the request is bound to the entities its proposal states (R-25, R-41 (4)): one source
    assert spec.entity_id is subjects._stated_by_proposal
    assert spec.proposal_entities is not None and spec.entities is None
    # the lifecycle is registered by the domain module the files router imports
    assert ApprovalSubjectType.EVIDENCE_SHRED in subjects.LIFECYCLES
    assert evidence_shred.SUBJECT is ApprovalSubjectType.EVIDENCE_SHRED


def test_the_step_is_a_controllers_config_approve() -> None:
    """R-49 (a) as ruled: one step, ``config.approve`` with the Controller role as the step's
    role (R-41 (7)); the permission is an approval permission that, of the default roles, only
    the Controller holds — the privacy-side administrator who requests never does (SoD)."""
    permission = subjects.EVIDENCE_SHRED_PERMISSION
    assert permissions.spec(permission).is_approval
    holders = {code for code, held in permissions.DEFAULT_ROLES.items() if permission in held}
    assert holders == {"controller"}
    spec = subjects.spec_for(ApprovalSubjectType.EVIDENCE_SHRED)
    assert spec.step_role == "controller" == subjects.CONTROLLER_ROLE
    # the subject's own step: the floor no published rule lowers (R-26 (c))
    assert routing.floor_items(spec, ()) == [
        (routing.FALLBACK_STEP_NAME, permission, 1, "controller")
    ]
    assert "settings.manage" not in permissions.DEFAULT_ROLES["controller"]
    assert permission not in permissions.DEFAULT_ROLES["tenant_admin"]


def test_the_subject_is_on_no_auto_approval_list() -> None:
    """R-26 / R-49 (a): never auto-approved — no seeded rule names the subject, the subject is on
    no allow-list, and the request is submitted with ``auto_approval=False``."""
    assert ApprovalSubjectType.EVIDENCE_SHRED not in {
        rule.subject for rule in demo_policies.AUTO_RULES
    }
    assert ApprovalSubjectType.EVIDENCE_SHRED not in routing.AUTO_APPROVABLE
    assert routing.seeded_rule_set(ApprovalSubjectType.EVIDENCE_SHRED) is None


def test_the_seeded_routing_table_carries_the_subjects_row() -> None:
    """PRD §2.5 rev 1.71: the seeded routing table has a rule for every subject row — the stored
    rules are read by ``tests/domain/demo/test_seed_avenmoor_reference.py``. This subject's rule
    is unconditional and states the subject's own step: ``config.approve`` with the Controller
    role reference (04 T-REF-26 ``role``). Without the reference the rule would lower the
    subject's approval and is refused at authoring (R-26 (c))."""
    rules = [
        rule
        for rule in demo_policies.ROUTING_RULES
        if ApprovalSubjectType.EVIDENCE_SHRED in rule.subjects
    ]
    assert [(rule.subjects, rule.extra) for rule in rules] == [
        ((ApprovalSubjectType.EVIDENCE_SHRED,), ())
    ]
    conditions = demo_policies.routing_conditions(rules[0])
    outputs = demo_policies.routing_outputs(rules[0])
    step = {
        "name": "Controller approval",
        "permission": subjects.EVIDENCE_SHRED_PERMISSION,
        "min_approvers": 1,
    }
    assert outputs == {"steps": [{**step, "role": subjects.CONTROLLER_ROLE}]}
    assert rule_sets.floor_errors(conditions, outputs) == []
    (lowered,) = rule_sets.floor_errors(conditions, {"steps": [step]})
    assert "EVIDENCE_SHRED" in lowered.message and "held by the role controller" in lowered.message


def test_the_proposal_names_the_file_the_records_their_entities_and_the_reason() -> None:
    """The hashed proposal: the file, its SHA-256, the records that hold it — in one order,
    whatever order they were found in — the legal entities of those records, the approval
    requests pending on those records (ruling R-120 (g); none here) and the reason."""
    found = [
        lifted("import_upload", label="IMP-000007", row_id=UPLOAD, entities=frozenset({US})),
        lifted("file_attachment", label="BOOK-A version 2", row_id=STUDY, entities=None),
    ]
    described = evidence_shred._described(found)
    proposal = proposed(found)
    assert proposal == proposed(list(reversed(found)))
    assert proposal == {
        "file_id": str(FILE),
        "sha256": "ab" * 32,
        "purpose": "SSP_STUDY",
        "holds": [
            {
                "table": "file_attachment",
                "column": "file_object_id",
                "record_id": str(STUDY),
                "record": "the SSP study of SSP book BOOK-A version 2, which has been submitted",
            },
            {
                "table": "import_upload",
                "column": "file_object_id",
                "record_id": str(UPLOAD),
                "record": "the source of committed import IMP-000007",
            },
        ],
        # one of the records has no entity: the request spans every entity
        "entity_ids": [],
        "is_all_entities": True,
        "pending_requests": [],
        "reason": REASON,
    }
    # Ruling R-120 (g): the requests that were pending on the holding records, by number, each
    # with its subject type and the record as the refusal names it — and nothing else of them.
    study = described[1]["record"]  # the SSP study of BOOK-A version 2
    adjustment = (
        "the supporting attachment of manual adjustment ADJ-000002, which has been submitted"
    )
    stopped = subjects.evidence_shred_proposal(
        FILE_ROW,
        described,
        reason=REASON,
        entity_ids=None,
        pending_requests=[
            {"request_no": "APR-000012", "subject_type": "SSP_BOOK_VERSION", "record": study},
            {
                "request_no": "APR-000004",
                "subject_type": "MANUAL_ADJUSTMENT",
                "record": adjustment,
                "summary": "not carried",
            },
        ],
    )
    assert stopped["pending_requests"] == [
        {"request_no": "APR-000004", "subject_type": "MANUAL_ADJUSTMENT", "record": adjustment},
        {"request_no": "APR-000012", "subject_type": "SSP_BOOK_VERSION", "record": study},
    ]
    assert {key: value for key, value in stopped.items() if key != "pending_requests"} == {
        key: value for key, value in proposal.items() if key != "pending_requests"
    }
    named = proposed(
        [
            lifted("import_upload", label="IMP-000007", row_id=UPLOAD, entities=frozenset({UK})),
            lifted("reconciliation", label="REC-000003", row_id=STUDY, entities=frozenset({US})),
        ]
    )
    assert (named["entity_ids"], named["is_all_entities"]) == ([str(US), str(UK)], False)
    # the approval lifts the holds the proposal names and no other: the comparison is by key
    assert evidence_shred._keys(proposal["holds"]) == evidence_shred._keys(described)
    assert evidence_shred._keys(described[:1]) != evidence_shred._keys(described)


def test_the_request_is_bound_to_the_union_of_the_records_entities_or_to_every_entity() -> None:
    """R-25 / R-41: the union of the records' entities; every entity as soon as one record has
    none — a migration batch, an SSP book without an entity, a tenant-level or unresolved import
    (``file_evidence`` reads an empty ``named_entity_ids`` as none). The proposal states the set
    and the kernel reads it back (``SubjectSpec.proposal_entities``); a proposal that names
    neither is malformed and spans every entity (fail closed)."""
    us = lifted("import_upload", label="IMP-1", row_id=UPLOAD, entities=frozenset({US}))
    uk = lifted("reconciliation", label="REC-1", row_id=STUDY, entities=frozenset({UK}))
    every = lifted("migration_batch", label="MIG-1", row_id=STUDY, entities=None)
    assert evidence_shred._entities([us]) == frozenset({US})
    assert evidence_shred._entities([us, uk]) == frozenset({US, UK})
    assert evidence_shred._entities([us, every]) is None
    assert evidence_shred._entities([]) is None
    assert file_evidence._entity_ids([]) is None and file_evidence._entity_ids(None) is None
    assert file_evidence._entity_ids([str(US), UK]) == frozenset({US, UK})
    assert file_evidence._entity_ids(US) == frozenset({US})

    spec = subjects.spec_for(ApprovalSubjectType.EVIDENCE_SHRED)
    assert spec.proposal_entities is not None
    cases = (
        ([us], subjects.SubjectEntities(frozenset({US}))),
        ([us, uk], subjects.SubjectEntities(frozenset({US, UK}))),
        ([us, every], subjects.ALL_ENTITIES),
    )
    for found, expected in cases:
        assert evidence_shred._bound(found) == expected
        assert spec.proposal_entities(None, proposed(found)) == expected  # type: ignore[arg-type]
    for malformed in ({}, {"entity_ids": []}, {"entity_ids": [], "is_all_entities": False}):
        entities = subjects.evidence_shred_entities(None, malformed)  # type: ignore[arg-type]
        assert entities == subjects.ALL_ENTITIES


def test_the_approval_lifts_the_records_the_request_names_under_the_entities_it_froze() -> None:
    """The decision's own check (``_still_named``): the records that hold the file now are the
    proposal's, by table, column and row — and they are bound to the entities the request froze,
    because the approver was checked against that set and no other."""
    us = lifted("import_upload", label="IMP-1", row_id=UPLOAD, entities=frozenset({US}))
    second = lifted("reconciliation", label="REC-1", row_id=STUDY, entities=frozenset({US}))
    proposal = proposed([us])

    def still(found: list[file_evidence.Hold]) -> bool:
        return evidence_shred._still_named(None, found, proposal)  # type: ignore[arg-type]

    assert still([us])
    assert not still([us, second])  # a record has come to hold the file
    assert not still([])  # the record ceased to hold it
    moved = lifted("import_upload", label="IMP-1", row_id=UPLOAD, entities=frozenset({UK}))
    assert not still([moved])  # the same record, bound to another entity
    wider = lifted("import_upload", label="IMP-1", row_id=UPLOAD, entities=frozenset({US, UK}))
    assert not still([wider])
    unbound = lifted("import_upload", label="IMP-1", row_id=UPLOAD, entities=None)
    assert not still([unbound])  # … or to none: every entity
