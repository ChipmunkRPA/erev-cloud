"""``LedgerResolver``: the database ``IdResolver`` over the adapter's ledger (record §17, RES-1).

Every id the platform assigns (customers, products, templates, calendars, entities, period
states, contracts, groups, obligations, estimates and their versions, judgements,
approval requests, mapping / SSP / policy / rule-set / FX versions, memberships, roles) is read
from the result of a successful committed call kept in the ledger (``LedgerEntry.result``), never
generated. The resolver is a pure function of the
ledger: the same ledger yields the same ids. A handle with no committed producer yet, an unknown
handle, or a result that does not expose the id is refused with ``UnresolvedHandle`` (a
``NotProvisioned``), so the runner marks the dependent step ``not_run``. A policy override has no
handle: the plan creates none (register index 308; ``platform_plan._contract_configuration``).

The read-side slice adds what a result cannot carry: period states beyond the entity-book result,
approval requests by subject, roles, modification ids of ``CONTRACT_AMENDED`` events.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final
from uuid import UUID

from erev_api.enums import ApprovalSubjectType
from support.answer_keys.platform_plan import OPERATOR, PRESET_HANDLER, H
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.request_models import policy_groups
from support.answer_keys.workspace_adapter import LedgerEntry
from support.answer_keys.workspace_reads import PersistedReads

__all__ = [
    "RESULT_MEMBERS",
    "SUBJECTS",
    "SUBMIT_HANDLERS",
    "LedgerResolver",
    "UnresolvedHandle",
    "result_id",
]

NO_RESULT: Final = "the committed call returned no result"
NO_ID: Final = "the committed call's result exposes no id"
# Rule RES-2: the calls whose result is the source of an approval request id and subject hash.
SUBMIT_HANDLERS: Final = frozenset(
    {
        H["submit_activation"],
        H["mapping_submit"],
        H["template_submit"],
        H["ssp_submit"],
        H["policy_submit"],
        H["judgement_submit"],
        H["distinct_review"],  # creates and submits the obligation's judgement record at once
        H["estimate_submit"],
        H["rule_set_submit"],
        H["fx_submit"],
    }
)


# Rule RES-4: the members of each submitting handler's NATIVE result that carry the approval
# request id and the subject digest — typed per handler, never searched by name. ``Submitted``
# (activation) names the request but no digest; ``EstimateVersionOut`` and
# ``FxRateSetVersionDetailOut`` carry ``content_sha256`` (the digest the approval subject hashes);
# the None-returning submits carry nothing — the read side answers them (READ-3). A judgement
# record's own ``content_sha256`` is NOT its request's digest: the subject content of a record
# that names a contract also holds that contract's group and stream head (04 §16.10 rev 1.49,
# ``subjects.judgement_record_subject_content``), and a decision sent with the record's digest is
# refused as stale and voids the request. Its digest is read from the request (READ-3).
RESULT_MEMBERS: Final[Mapping[str, tuple[str | None, str | None]]] = {
    H["submit_activation"]: ("approval_request_id", None),
    H["estimate_submit"]: ("approval_request_id", "content_sha256"),
    H["judgement_submit"]: ("approval_request_id", None),
    H["distinct_review"]: ("approval_request_id", None),  # DistinctReviewOut: no digest
    H["fx_submit"]: ("pending_approval_request_id", "content_sha256"),
    H["mapping_submit"]: (None, None),
    H["template_submit"]: (None, None),
    H["ssp_submit"]: (None, None),
    H["policy_submit"]: (None, None),
    H["rule_set_submit"]: (None, None),
}
# Rule READ-3: the approval subject each submitting call opens (the T-PLT approval_request row).
SUBJECTS: Final[Mapping[str, ApprovalSubjectType]] = {
    H["submit_activation"]: ApprovalSubjectType.CONTRACT_ACTIVATION,
    H["judgement_submit"]: ApprovalSubjectType.JUDGEMENT_RECORD,
    H["distinct_review"]: ApprovalSubjectType.JUDGEMENT_RECORD,
    H["estimate_submit"]: ApprovalSubjectType.ESTIMATE_VERSION,
    H["template_submit"]: ApprovalSubjectType.POB_TEMPLATE_VERSION,
    H["ssp_submit"]: ApprovalSubjectType.SSP_BOOK_VERSION,
    H["mapping_submit"]: ApprovalSubjectType.ACCOUNT_MAPPING_VERSION,
    H["policy_submit"]: ApprovalSubjectType.REGISTRY_VERSION,
    H["rule_set_submit"]: ApprovalSubjectType.RULE_SET_VERSION,
    H["fx_submit"]: ApprovalSubjectType.FX_RATE_SET_VERSION,
}


class UnresolvedHandle(NotProvisioned):
    """A key handle the ledger cannot resolve yet: no committed producer, unknown, or the result
    lacks the id. Named by kind and key; the resolver never invents an id."""

    def __init__(self, kind: str, key: str, reason: str) -> None:
        self.kind = kind
        self.key = key
        self.reason = reason
        super().__init__(f"{kind} {key}: {reason}")


def _member(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def result_id(result: Any, *path: str) -> UUID:
    """The UUID at ``path`` inside ``result`` (mapping keys or attributes); a bare result is the id
    itself when it is a UUID or a UUID string, else its ``id`` member. Raises ``LookupError``."""
    if result is None:
        raise LookupError(NO_RESULT)
    value: Any = result
    for name in path:
        value = _member(value, name)
        if value is None:
            raise LookupError(f"{NO_ID} ({'.'.join(path)})")
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError as error:
            raise LookupError(NO_ID) from error
    inner = _member(value, "id")
    if isinstance(inner, UUID):
        return inner
    if isinstance(inner, str):
        return UUID(inner)
    raise LookupError(NO_ID)


class LedgerResolver:
    """``IdResolver`` over ``ledger`` (a live sequence the adapter appends to); with ``reads``
    (the database platform) the approval pairs a result does not carry are read back from the
    submission's own ``approval_request`` rows (rule READ-3), never from an older entry."""

    def __init__(self, ledger: Sequence[LedgerEntry], reads: PersistedReads | None = None) -> None:
        self.ledger = ledger
        self.reads = reads

    # -- lookup ----------------------------------------------------------------------------------

    def _entries(self, handler: str, **match: object) -> list[LedgerEntry]:
        return [
            entry
            for entry in self.ledger
            if entry.call.handler == handler
            and all(entry.call.kwargs.get(name) == value for name, value in match.items())
        ]

    def _single(self, kind: str, key: str, handler: str, *path: str, **match: object) -> UUID:
        entries = self._entries(handler, **match)
        if not entries:
            raise UnresolvedHandle(
                kind, key, f"no committed {handler.rsplit('.', 1)[-1]} call for {key!r} yet"
            )
        try:
            return result_id(entries[-1].result, *path)
        except LookupError as error:
            raise UnresolvedHandle(kind, key, str(error)) from error

    def _latest_submission(self) -> LedgerEntry:
        """The latest submitting call (RES-2): the only source of the pending approval's id and
        subject hash; a decision result is never a submission."""
        for entry in reversed(self.ledger):
            if entry.call.handler in SUBMIT_HANDLERS:
                return entry
        raise UnresolvedHandle("approval", "pending", "no committed submission yet")

    def pending_subject_type(self) -> ApprovalSubjectType:
        """The approval subject the latest committed submission opened (RES-2; READ-3
        ``SUBJECTS``): what a decision decides, so ACT-2 checks that subject's approval
        permission (``step_permissions``)."""
        return SUBJECTS[self._latest_submission().call.handler]

    # -- IdResolver ------------------------------------------------------------------------------

    def customer_id(self, code: str) -> UUID:
        return self._single("customer", code, H["customer"], code=code)

    def product_id(self, code: str) -> UUID:
        return self._single("product", code, H["product"], code=code)

    def template_id(self, code: str) -> UUID:
        return self._single("template", code, H["template"], code=code)

    def template_version_id(self, code: str) -> UUID:
        return self._single("template_version", code, H["template_version"], code=code)

    def gl_account_id(self, code: str) -> UUID:
        return self._single("gl_account", code, H["gl_account"], code=code)

    def calendar_id(self, entity_code: str) -> UUID:
        return self._single("calendar", entity_code, H["calendar"], entity_code=entity_code)

    def entity_id(self, code: str) -> UUID:
        return self._single("entity", code, H["entity"], entity_code=code)

    def period_state_id(self, entity: str, book: str, period_key: str) -> UUID:
        key = f"{entity}/{book}/{period_key}"
        entries = self._entries(H["entity_book"], entity_code=entity, book=book)
        if not entries:
            raise UnresolvedHandle("period_state", key, "no committed put_entity_book call yet")
        states = _member(entries[-1].result, "period_states")
        if isinstance(states, Mapping) and period_key in states:
            try:
                return result_id(states[period_key])
            except LookupError as error:
                raise UnresolvedHandle("period_state", key, str(error)) from error
        if self.reads is not None:  # READ-7: EntityBookOut carries no period states
            return self.reads.period_state_id(entity, book, period_key)
        raise UnresolvedHandle(
            "period_state",
            key,
            "the entity-book result exposes no period states and no reads are available "
            "(rule READ-7)",
        )

    def contract_id(self, external_id: str) -> UUID:
        return self._single(
            "contract", external_id, H["book"], "contract", "id", contract=external_id
        )

    def group_id(self, external_id: str) -> UUID:
        return self._single(
            "group", external_id, H["book"], "combination_group", "id", contract=external_id
        )

    def group_code(self, external_id: str) -> str:
        """READ2-R2 by identity: the persisted group code the committed booking returned
        (`CG-<contract_no>`, system-generated), never a name the plan supplies."""
        entries = self._entries(H["book"], contract=external_id)
        if not entries:
            raise UnresolvedHandle("group", external_id, "no committed book_contract call yet")
        code = _member(_member(entries[-1].result, "combination_group"), "code")
        if not isinstance(code, str) or not code:
            raise UnresolvedHandle(
                "group", external_id, "the booking result names no combination_group.code"
            )
        return code

    def estimate_version_id(self, contract: str, element_code: str, version_no: int) -> UUID:
        return self._single(
            "estimate_version",
            f"{contract}/{element_code}/{version_no}",
            H["estimate_version"],
            contract=contract,
            element_code=element_code,
            version_no=version_no,
        )

    def modification_id(self, contract: str, reference: str) -> UUID:
        raise UnresolvedHandle(
            "modification",
            f"{contract}/{reference}",
            "no creating call; the CONTRACT_AMENDED event's modification_id is read from the "
            "platform (read-side slice)",
        )

    def judgement_id(self, contract: str, handle: str) -> UUID:
        return self._single(
            "judgement", f"{contract}/{handle}", H["judgement"], contract=contract, handle=handle
        )

    def pending_approvals(self) -> tuple[tuple[UUID, str], ...]:
        """Every ``(approval request id, subject digest)`` pair of the latest submission (RES-2):
        from the typed members of its native result (RES-4) when the result carries both for every
        request, else read back from that submission's own subjects (READ-3) — never from an older
        entry, a decision result or a name search."""
        entry = self._latest_submission()
        id_name, hash_name = RESULT_MEMBERS.get(entry.call.handler, (None, None))
        results = self._results(entry)
        if id_name and hash_name and results:
            ids = [_member(item, id_name) for item in results]
            digests = [_member(item, hash_name) for item in results]
            if all(value is not None for value in [*ids, *digests]):
                pairs: list[tuple[UUID, str]] = []
                for rid, digest in zip(ids, digests, strict=True):
                    try:
                        pairs.append((result_id(rid), str(digest)))
                    except LookupError as error:
                        raise UnresolvedHandle(
                            "approval", entry.call.step.subject, str(error)
                        ) from error
                return tuple(pairs)
        if self.reads is None:
            raise UnresolvedHandle("approval", entry.call.step.subject, self._missing(entry))
        subject_type = SUBJECTS.get(entry.call.handler)
        if subject_type is None:
            raise UnresolvedHandle(
                "approval",
                entry.call.step.subject,
                f"{entry.call.handler} opens no approval subject",
            )
        read = self.reads.approval_pairs(
            subject_type, self._subject_ids(entry), where=entry.call.step.subject
        )
        if id_name:
            named = [_member(item, id_name) for item in results]
            for rid, (read_id, _) in zip(named, read, strict=False):
                if rid is not None and result_id(rid) != read_id:
                    raise UnresolvedHandle(
                        "approval",
                        entry.call.step.subject,
                        f"the submission result names request {result_id(rid)} but the "
                        f"subject's pending request is {read_id} (rule READ-3)",
                    )
        return read

    @staticmethod
    def _results(entry: LedgerEntry) -> list[object]:
        result = entry.result
        if result is None:
            return []
        return list(result) if isinstance(result, list | tuple) else [result]

    def _missing(self, entry: LedgerEntry) -> str:
        """Why the latest submission's result yields no pair (RES-2 / RES-4), by name."""
        command = entry.call.handler.rsplit(".", 1)[-1]
        id_name, hash_name = RESULT_MEMBERS.get(entry.call.handler, (None, None))
        tail = (
            "the subject-specific read is the read-side slice — no fallback to an older submission"
        )
        results = self._results(entry)
        if not results or id_name is None:
            return f"{command} returns no approval members in its result (rule RES-4); {tail}"
        if any(_member(item, id_name) is None for item in results):
            return f"the latest submission ({command}) exposes no {id_name} (rule RES-2); {tail}"
        if hash_name is None:
            return (
                f"the latest submission ({command}) returns no subject digest in its result "
                f"(rule RES-4); {tail}"
            )
        return f"the latest submission ({command}) exposes no {hash_name} (rule RES-2); {tail}"

    def _subject_ids(self, entry: LedgerEntry) -> list[UUID]:
        """The approval subject ids of one submitting call, through this resolver's own handles."""
        kw, handler = entry.call.kwargs, entry.call.handler
        if handler == H["submit_activation"]:
            return [self.contract_id(str(kw["contract"]))]
        if handler == H["judgement_submit"]:
            return [self.judgement_id(str(kw["contract"]), str(kw["handle"]))]
        if handler == H["distinct_review"]:
            return [self.distinct_review_id(str(kw["contract"]), str(kw["obligation_key"]))]
        if handler == H["estimate_submit"]:
            return [
                self.estimate_version_id(
                    str(kw["contract"]), str(kw["element_code"]), int(kw["version_no"])
                )
            ]
        if handler == H["template_submit"]:
            return [self.template_version_id(str(kw["code"]))]
        if handler == H["ssp_submit"]:
            return [self.ssp_version_id(str(kw["code"]), int(kw["version"]))]
        if handler == H["mapping_submit"]:
            return [self.mapping_version_id()]
        if handler == H["policy_submit"]:
            if kw.get("preset"):
                return [self.policy_version_id("TENANT", "preset", str(kw["preset"]))]
            scope, code = str(kw["scope"]), str(kw["scope_code"])
            return [
                self.policy_version_id(scope, code, category.value)
                for category in policy_groups(dict(kw["values"]))
            ]
        if handler == H["rule_set_submit"]:
            return [self.rule_set_version_id(str(kw["code"]))]
        if handler == H["fx_submit"]:
            return [self.fx_version_id(str(kw["code"]))]
        raise UnresolvedHandle("approval", entry.call.step.subject, f"{handler} is no submission")

    def impact_preview_sha256(self, approval_request_id: UUID) -> str | None:
        """The digest of the request's impact preview, read from the request (REQ-PLT-015); None
        without a preview, and without reads (the mock platform decides nothing)."""
        if self.reads is None:
            return None
        return self.reads.impact_preview_sha256(approval_request_id)

    def pending_approval_id(self) -> UUID:
        """The latest submission's approval request id (RES-2): the typed member of its own result
        (RES-4), else the single pair read from its subject (READ-3); several pending requests
        refuse by name."""
        entry = self._latest_submission()
        id_name, _ = RESULT_MEMBERS.get(entry.call.handler, (None, None))
        results = self._results(entry)
        if id_name and len(results) == 1:
            value = _member(results[0], id_name)
            if value is not None:
                try:
                    return result_id(value)
                except LookupError as error:
                    raise UnresolvedHandle(
                        "approval", entry.call.step.subject, str(error)
                    ) from error
        return self._single_pair()[0]

    def subject_sha256(self) -> str:
        """The latest submission's own subject digest (RES-2): the typed member of its own result
        (RES-4), else read from its subject as one pair with the id (READ-3); never an older
        subject's."""
        entry = self._latest_submission()
        _, hash_name = RESULT_MEMBERS.get(entry.call.handler, (None, None))
        results = self._results(entry)
        if hash_name and len(results) == 1:
            value = _member(results[0], hash_name)
            if value is not None:
                return str(value)
        return self._single_pair()[1]

    def _single_pair(self) -> tuple[UUID, str]:
        pairs = self.pending_approvals()
        if len(pairs) != 1:
            raise UnresolvedHandle(
                "approval",
                self._latest_submission().call.step.subject,
                f"{len(pairs)} pending approvals; one decide step approves one (rule READ-3)",
            )
        return pairs[0]

    def mapping_version_id(self) -> UUID:
        return self._single("mapping_version", "current", H["mapping"])

    def ssp_book_id(self, code: str) -> UUID:
        return self._single("ssp_book", code, H["ssp_book"], code=code)

    def ssp_version_id(self, code: str, version_no: int) -> UUID:
        return self._single(
            "ssp_version", f"{code}/{version_no}", H["ssp_version"], code=code, version=version_no
        )

    def distinct_review_id(self, contract: str, obligation_key: str) -> UUID:
        """The judgement record the committed distinct review of that obligation created."""
        return self._single(
            "distinct_review",
            f"{contract}/{obligation_key}",
            H["distinct_review"],
            "judgement_record_id",
            contract=contract,
            obligation_key=obligation_key,
        )

    def ssp_study_id(self, code: str, version_no: int) -> UUID:
        """The file the committed study upload of that version stored."""
        return self._single(
            "ssp_study", f"{code}/{version_no}", H["ssp_study"], code=code, version=version_no
        )

    def estimate_evidence_id(self, contract: str, element_code: str, version_no: int) -> UUID:
        """The file the committed evidence upload of that estimate version stored. The
        upload is the SSP study's command: the call's own keywords — a contract, an element and
        a version, where a study names a book — tell the two apart."""
        return self._single(
            "estimate_evidence",
            f"{contract}/{element_code}/{version_no}",
            H["estimate_evidence"],
            contract=contract,
            element_code=element_code,
            version_no=version_no,
        )

    def policy_version_id(self, scope: str, code: str, category: str) -> UUID:
        key = f"{scope}/{code}/{category}"
        if code == "preset":  # RES-3: the producer's scope AND preset, exactly
            return self._single("policy_version", key, PRESET_HANDLER, scope=scope, preset=category)
        entries = self._entries(H["policy"], scope=scope, scope_code=code)
        if not entries:
            raise UnresolvedHandle("policy_version", key, "no committed create_policy call yet")
        entry = entries[-1]
        groups = list(policy_groups(dict(entry.call.kwargs.get("values", {}))))
        index = next((i for i, group in enumerate(groups) if group.value == category), None)
        if index is None:
            raise UnresolvedHandle("policy_version", key, f"category {category!r} not in that call")
        result = entry.result
        try:
            if isinstance(result, list | tuple):
                return result_id(result[index])
            if len(groups) == 1:
                return result_id(result)
        except (LookupError, IndexError) as error:
            raise UnresolvedHandle("policy_version", key, str(error)) from error
        raise UnresolvedHandle(
            "policy_version", key, "the result carries fewer versions than categories"
        )

    def role_id(self, code: str) -> UUID:
        entries = self._entries(H["provision"])
        roles = _member(entries[-1].result, "roles") if entries else None
        if isinstance(roles, Mapping) and code in roles:
            try:
                return result_id(roles[code])
            except LookupError as error:
                raise UnresolvedHandle("role", code, str(error)) from error
        if self.reads is not None:  # READ-7: TenantProvisionResult carries no roles
            return self.reads.role_id(code)
        raise UnresolvedHandle(
            "role",
            code,
            "the provisioning result exposes no roles and no reads are available (rule READ-7)",
        )

    def membership_id(self, persona: str) -> UUID:
        return self._single("membership", persona, H["invite"], display_name=persona)

    def invitation_token(self, persona: str) -> str:
        """The token of the invitation ``persona`` was sent — its committed invite's membership,
        for the operator the admin membership of the committed provisioning —, read from the
        message itself (``PersistedReads.invitation_token``): a command result never carries it,
        and it is never generated."""
        membership = (
            self._single("membership", persona, H["provision"], "admin_membership_id")
            if persona == OPERATOR
            else self.membership_id(persona)
        )
        if self.reads is None:
            raise UnresolvedHandle(
                "invitation",
                persona,
                "the token is in the invitation message, and no reads are available",
            )
        return self.reads.invitation_token(membership, where=f"invitation of {persona}")

    # -- record §18 (the FOLLOWING request models) ----------------------------------------------

    def obligation_id(self, contract: str, obligation_key: str) -> UUID:
        key = f"{contract}/{obligation_key}"
        entries = self._entries(H["book"], contract=contract)
        if not entries:
            raise UnresolvedHandle("obligation", key, "no committed book_contract call yet")
        rows = _member(entries[-1].result, "obligations")
        for row in rows or ():
            if _member(row, "obligation_key") == obligation_key:
                try:
                    return result_id(row)
                except LookupError as error:
                    raise UnresolvedHandle("obligation", key, str(error)) from error
        raise UnresolvedHandle("obligation", key, "the booking result names no such obligation")

    def estimate_id(self, contract: str, element_code: str) -> UUID:
        return self._single(
            "estimate",
            f"{contract}/{element_code}",
            H["estimate"],
            contract=contract,
            element_code=element_code,
        )

    def rule_set_id(self, code: str) -> UUID:
        return self._single("rule_set", code, H["rule_set"], code=code)

    def rule_set_version_id(self, code: str) -> UUID:
        return self._single("rule_set_version", code, H["rule_set_version"], code=code)

    def fx_set_id(self, code: str) -> UUID:
        return self._single("fx_set", code, H["fx_set"], code=code)

    def fx_version_id(self, code: str) -> UUID:
        return self._single("fx_version", code, H["fx_version"], code=code)
