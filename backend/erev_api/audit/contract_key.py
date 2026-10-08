"""The contract key of an audit event (04 T-PLT-19 and §1.7, rev 1.154; dev-guide DG-KRN-AUD-09;
supervisor ruling R-108).

An auditor asks for every event of one contract. T-PLT-19 keys an event by the table and the id of
its object, and most objects of a contract are rows of another table, so the event itself names the
contract: ``detail.contract_id`` when it concerns one contract, ``detail.contract_ids`` — the
contracts it concerns at the time of the event, sorted — when it concerns several (a combination
group's commands and judgements, a computation or a posting of a group with more than one member).
The writer of the event passes the key, because it holds the contract: ``contract_id=`` or
``contract_ids=`` of ``audit.writer``. Nothing is looked up when an event is appended, and
``detail`` is a hashed column already, so the chain's canonical form is what it was. The append
writes the key a second time as plain columns — one ``audit_event_contract`` row a contract
(04 T-PLT-48) — because a read by contract needs an index, and under row-level security an index
serves only conditions on columns (``named`` reads the key back for that).

``ALWAYS``, ``WHERE_NAMED`` and ``OTHER`` are closed and disjoint, and together they are every
object type an audit event is written for:

- ``ALWAYS``: every event of the type concerns a contract, and an event without a key is refused
  when it is built (``ValueError``: the command fails rather than write an event the contract's
  trail would miss). A ``DENIED`` event is the exception: a permission is refused before the
  object is read, so its writer names the contract only where it holds one, and a refusal is
  never turned into an error for want of a key;
- ``WHERE_NAMED``: the row may name a contract (an estimate of a portfolio names none); its writer
  passes ``contract_id=``, which may be None;
- ``OTHER``: not an object of a contract.

An object type in none of them fails ``tests/architecture/test_audit_contract_key.py`` (every
writer in the code) and the audit-coverage walk (every command route, CTL-038).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final
from uuid import UUID

__all__ = [
    "ALWAYS",
    "CONTRACT_ID",
    "CONTRACT_IDS",
    "OTHER",
    "WHERE_NAMED",
    "keyed",
    "named",
    "scoped",
]

CONTRACT_ID: Final = "contract_id"
CONTRACT_IDS: Final = "contract_ids"

ALWAYS: Final = frozenset(
    {
        "contract",
        "obligation",
        "modification",
        "event_submission",
        # the stream appends (AUD-FACT): one event per contract and append
        "contract_event",
        "contract_hold",
        "policy_override",
        "manual_adjustment",
        "contract_source_link",
        "combination_group_member",
        # the outputs of a computation, which is keyed by group: the members at the time of it
        "contract_version",
        "obligation_version",
        "contract_version_balance",
        "fx_layer_movement",
        "loss_provision_version",
        "loss_provision_eac",
        "schedule",
        "schedule_line",
        "calc_trace",
    }
)
WHERE_NAMED: Final = frozenset(
    {
        "evidence_pack",  # sample packs name contracts; period/access/change packs may not
        "estimate",  # an estimate of a portfolio names no contract (T-CON-12)
        "estimate_version",
        "judgement_record",  # T-CON-19 ``contract_id`` is null for a record about no contract
        "exception_item",  # T-IMP-05 ``contract_id`` is null for an item about no contract
        # a combination group and a computation of one name the group's members at the time of
        # the event (the contracts a proposal names, while the group is proposed); a group
        # without a member names none
        "combination_group",
        "contract_computation",
        # a posting names the contracts of its lines; a posting without a line names none
        "subledger_posting",
        "subledger_line",
        "subledger_posting_seal",
    }
)
OTHER: Final = frozenset(
    {
        # identity, access and the workspace
        "tenant",
        "tenant_membership",
        "app_user",
        "user_mfa_factor",
        "role",
        "role_assignment",
        "sod_rule",
        "sod_exception",
        "access_review_campaign",
        "access_review_item",
        "api_client",
        "support_grant",
        "approval_delegation",
        "route",  # a refused command (DG-KRN-AUTH-05)
        # approvals: a request and its decisions get the key with item APR-REQUEST-REASON-1, when
        # ``approvals/engine.py`` is open again (ruling R-108 (a) point 4); until then a contract's
        # trail does not show them
        "approval_request",
        # configuration and reference data
        "registry_version",
        "rule_set",
        "rule_set_version",
        "rule",
        "rule_test_case",
        "pob_template",
        "pob_template_version",
        "account_mapping_version",
        "account_mapping_rule",
        "ssp_book",
        "ssp_book_version",
        "ssp_entry",
        "ssp_range",
        "ssp_calculator_run",
        "ssp_calculator_result",
        "ssp_calculator_exclusion",
        "import_mapping_profile",
        "fiscal_calendar",
        "period",
        "control_execution",  # control observations reference their run/period, not one contract
        "period_state",
        "period_state_transition",
        "legal_entity",
        "book",
        "entity_book",
        "customer",
        "related_party_group",
        "product",
        "product_bundle_component",
        "gl_account",
        "dimension_definition",
        "dimension_value",
        "tenant_currency",
        "fx_rate_set",
        "fx_rate_set_version",
        "fx_rate",
        # imports, integrations and migration: an import's or a sync run's own events; the contract
        # it touched is named by the stream append of that contract, which carries
        # ``import_upload_id`` or ``sync_run_id``
        "import_upload",
        "source_record",
        "source_order",
        "source_order_line",
        "source_invoice",
        "source_invoice_line",
        "integration_connection",
        "sync_run",
        "external_id_map",
        "migration_batch",
        # close, journals and reports: objects of an entity, a book and a period
        "period_lock",
        "close_run",
        "close_checklist_item",
        "close_checklist_template",
        "reconciliation",
        "reconciliation_item",
        "journal_run",
        "journal_batch",
        "journal_entry",
        "journal_line",
        "posting_ack",
        "report_run",
        # files, jobs, webhooks and the log itself
        "file_object",
        "file_attachment",
        "job",  # its start, finish and cancellation; what a job did is audited by what it wrote
        "webhook_endpoint",
        "webhook_delivery",
        "audit_chain_verification",
        "tenant_snapshot",
        "missing_object",
    }
)


def scoped(object_type: str) -> bool:
    """Whether ``object_type`` belongs to a contract."""
    return object_type in ALWAYS or object_type in WHERE_NAMED


def named(detail: Mapping[str, Any] | None) -> list[UUID]:
    """The contracts the key of ``detail`` names, ascending: what ``keyed`` put there. The chain
    append writes one T-PLT-48 row for each (``audit.chain.append_events``)."""
    given = detail or {}
    one = given.get(CONTRACT_ID)
    several = given.get(CONTRACT_IDS) or ()
    return sorted({UUID(str(value)) for value in ([one] if one is not None else several)})


def keyed(
    object_type: str,
    detail: Mapping[str, Any] | None,
    *,
    contract_id: UUID | None = None,
    contract_ids: Iterable[UUID] | None = None,
    required: bool = True,
) -> dict[str, Any]:
    """``detail`` with the contract key of an event of ``object_type``.

    One contract is stated as ``contract_id``, several as ``contract_ids`` (sorted, distinct) —
    whichever keyword the writer used, so that one contract always reads the same. ``detail`` may
    not carry either member itself: the key has one way in. An event of an ``ALWAYS`` type without a
    contract is refused, unless ``required`` is false (a ``DENIED`` event)."""
    given = dict(detail or {})
    if CONTRACT_ID in given or CONTRACT_IDS in given:
        raise ValueError(
            f"the contract key of a {object_type} event is passed as contract_id= or "
            "contract_ids=, not inside detail"
        )
    if contract_id is not None and contract_ids is not None:
        raise ValueError("an audit event names one contract or several, not both")
    named = sorted(
        {str(value) for value in ([contract_id] if contract_id is not None else contract_ids or ())}
    )
    if not named:
        if required and object_type in ALWAYS:
            raise ValueError(f"an audit event of {object_type} names its contract (04 T-PLT-19)")
        return given
    if len(named) == 1:
        return {**given, CONTRACT_ID: named[0]}
    return {**given, CONTRACT_IDS: named}
