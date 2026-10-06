"""The business label of an audit event's object (04 §16.14 "Object label", rev 1.154; item
AUD-API-GAPS-1).

T-PLT-19 names the object of an event by its table and id. The audit log shows what a person calls
it: a contract's external id, a run's number, a version's code and number. ``label`` is the SQL
expression that reads it inside the statement that reads the event — a ``CASE`` on the object type
with one scalar lookup on the primary key of the labelled table, of which PostgreSQL evaluates the
branch of the row's type alone — so a page costs no statement per row.

``LABELS`` and ``NO_LABEL`` are closed and disjoint, and together they are every object type an
event is written for (``audit.contract_key``): a new audited table is given a label or listed as
having none (``tests/unit/test_audit_labels.py``). The label is null where the type has none, where
the event stores no object id (an AUD-FACT summary names its rows in ``detail``), where the row is
gone, and where the reader's row-level security does not show the row: a label is read like any
other read of that table.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Final

from sqlalchemy import ColumnElement, Table, Text, case, cast, func, literal, null, select

from erev_api.db.tables import (
    access_review_campaign,
    account_mapping_version,
    api_client,
    app_user,
    approval_request,
    book,
    close_checklist_template,
    close_run,
    combination_group,
    contract,
    customer,
    dimension_definition,
    dimension_value,
    estimate,
    estimate_version,
    exception_item,
    fiscal_calendar,
    fx_rate_set,
    fx_rate_set_version,
    gl_account,
    import_mapping_profile,
    import_upload,
    integration_connection,
    journal_entry,
    journal_run,
    judgement_record,
    legal_entity,
    manual_adjustment,
    migration_batch,
    modification,
    obligation,
    period,
    period_lock,
    period_state,
    pob_template,
    pob_template_version,
    policy_override,
    product,
    reconciliation,
    related_party_group,
    report_run,
    role,
    rule_set,
    rule_set_version,
    sod_rule,
    ssp_book,
    ssp_book_version,
    ssp_calculator_run,
    tenant_membership,
)
from erev_api.domain.platform import users

__all__ = ["LABELS", "NO_LABEL", "label"]

# (the event's object id, the event's tenant id) -> the label, a text expression
type Labeller = Callable[[ColumnElement[Any], ColumnElement[Any]], ColumnElement[Any]]

VERSION: Final = " v"  # "<code> v<n>", as the version screens title a version (SCREENS §0.4)
BETWEEN: Final = " · "  # the separator of a composed title (SCREENS §0.4)


def _row(table: Table, object_id: ColumnElement[Any], tenant_id: ColumnElement[Any]) -> Any:
    """The conditions that name the labelled row by its primary key."""
    return (table.c.tenant_id == tenant_id, table.c.id == object_id)


def _own(table: Table, column: str) -> Labeller:
    """A column of the row itself: its number, code, key or name."""

    def build(object_id: ColumnElement[Any], tenant_id: ColumnElement[Any]) -> ColumnElement[Any]:
        return (
            select(cast(table.c[column], Text))
            .where(*_row(table, object_id, tenant_id))
            .scalar_subquery()
        )

    return build


def _numbered(table: Table, column: str) -> Labeller:
    """``<column> v<version_no>`` of a versioned row that carries its own code or name."""

    def build(object_id: ColumnElement[Any], tenant_id: ColumnElement[Any]) -> ColumnElement[Any]:
        return (
            select(func.concat(table.c[column], VERSION, table.c.version_no))
            .where(*_row(table, object_id, tenant_id))
            .scalar_subquery()
        )

    return build


def _version_of(version: Table, parent: Table, parent_id: str, column: str = "code") -> Labeller:
    """``<parent code> v<version_no>`` of a version row."""

    def build(object_id: ColumnElement[Any], tenant_id: ColumnElement[Any]) -> ColumnElement[Any]:
        joined = version.join(
            parent,
            (parent.c.tenant_id == version.c.tenant_id) & (parent.c.id == version.c[parent_id]),
        )
        return (
            select(func.concat(parent.c[column], VERSION, version.c.version_no))
            .select_from(joined)
            .where(*_row(version, object_id, tenant_id))
            .scalar_subquery()
        )

    return build


def _period_scope(table: Table) -> Labeller:
    """``<entity code> · <period key> · <book code>``: the three keys of the close cockpit, for a
    period state and for a lock of one."""

    def build(object_id: ColumnElement[Any], tenant_id: ColumnElement[Any]) -> ColumnElement[Any]:
        joined = table.join(
            legal_entity,
            (legal_entity.c.tenant_id == table.c.tenant_id)
            & (legal_entity.c.id == table.c.entity_id),
        ).join(
            period,
            (period.c.tenant_id == table.c.tenant_id) & (period.c.id == table.c.period_id),
        )
        return (
            select(
                func.concat(
                    legal_entity.c.code, BETWEEN, period.c.period_key, BETWEEN, table.c.book_code
                )
            )
            .select_from(joined)
            .where(*_row(table, object_id, tenant_id))
            .scalar_subquery()
        )

    return build


def _obligation(object_id: ColumnElement[Any], tenant_id: ColumnElement[Any]) -> ColumnElement[Any]:
    """``<obligation key> · <contract external id>``, as the obligation screen is titled."""
    joined = obligation.join(
        contract,
        (contract.c.tenant_id == obligation.c.tenant_id)
        & (contract.c.id == obligation.c.contract_id),
    )
    return (
        select(func.concat(obligation.c.obligation_key, BETWEEN, contract.c.external_id))
        .select_from(joined)
        .where(*_row(obligation, object_id, tenant_id))
        .scalar_subquery()
    )


def _member(object_id: ColumnElement[Any], tenant_id: ColumnElement[Any]) -> ColumnElement[Any]:
    """The name of the person behind a membership, as this workspace is shown it when the event
    is read (``users.SHOWN_NAME``, D-80 rule 5: the email until an invitation of a person who
    had an identity already is accepted; for an anonymised person the value 05 PRV-07 (a)
    wrote). The two conditions of ``_row`` are written out: the statement itself names the
    tenant of the membership (dev-guide DG-KRN-DB-12)."""
    joined = tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)
    return (
        select(users.SHOWN_NAME)
        .select_from(joined)
        .where(tenant_membership.c.tenant_id == tenant_id, tenant_membership.c.id == object_id)
        .scalar_subquery()
    )


def _user(object_id: ColumnElement[Any], tenant_id: ColumnElement[Any]) -> ColumnElement[Any]:
    """A user's name; the event's tenant is not a key of ``app_user`` (RLS-NONE-U)."""
    return select(app_user.c.display_name).where(app_user.c.id == object_id).scalar_subquery()


LABELS: Final[Mapping[str, Labeller]] = MappingProxyType(
    {
        # contracts
        "contract": _own(contract, "external_id"),
        "obligation": _obligation,
        "modification": _own(modification, "modification_no"),
        "estimate": _own(estimate, "element_code"),
        "estimate_version": _version_of(estimate_version, estimate, "estimate_id", "element_code"),
        "judgement_record": _own(judgement_record, "judgement_no"),
        "policy_override": _own(policy_override, "policy_key"),
        "manual_adjustment": _own(manual_adjustment, "adjustment_no"),
        "combination_group": _own(combination_group, "code"),
        "exception_item": _own(exception_item, "exception_no"),
        # approvals, imports and migration
        "approval_request": _own(approval_request, "request_no"),
        "import_upload": _own(import_upload, "import_no"),
        "import_mapping_profile": _numbered(import_mapping_profile, "code"),
        "migration_batch": _own(migration_batch, "migration_no"),
        "integration_connection": _own(integration_connection, "code"),
        # close, journals and reports
        "period": _own(period, "period_key"),
        "period_state": _period_scope(period_state),
        "period_lock": _period_scope(period_lock),
        "close_run": _own(close_run, "close_run_no"),
        "close_checklist_template": _own(close_checklist_template, "code"),
        "reconciliation": _own(reconciliation, "reconciliation_no"),
        "journal_run": _own(journal_run, "run_no"),
        "journal_entry": _own(journal_entry, "je_no"),
        "report_run": _own(report_run, "report_run_no"),
        # configuration and its versions
        "rule_set": _own(rule_set, "code"),
        "rule_set_version": _version_of(rule_set_version, rule_set, "rule_set_id"),
        "pob_template": _own(pob_template, "code"),
        "pob_template_version": _version_of(pob_template_version, pob_template, "pob_template_id"),
        "ssp_book": _own(ssp_book, "code"),
        "ssp_book_version": _version_of(ssp_book_version, ssp_book, "ssp_book_id"),
        "ssp_calculator_run": _own(ssp_calculator_run, "name"),
        "fx_rate_set": _own(fx_rate_set, "code"),
        "fx_rate_set_version": _version_of(fx_rate_set_version, fx_rate_set, "fx_rate_set_id"),
        "account_mapping_version": _numbered(account_mapping_version, "name"),
        "sod_rule": _numbered(sod_rule, "code"),
        # reference data
        "legal_entity": _own(legal_entity, "code"),
        "book": _own(book, "code"),
        "fiscal_calendar": _own(fiscal_calendar, "code"),
        "customer": _own(customer, "code"),
        "related_party_group": _own(related_party_group, "code"),
        "product": _own(product, "code"),
        "gl_account": _own(gl_account, "code"),
        "dimension_definition": _own(dimension_definition, "code"),
        "dimension_value": _own(dimension_value, "code"),
        # people and access
        "tenant_membership": _member,
        "app_user": _user,
        "role": _own(role, "code"),
        "api_client": _own(api_client, "name"),
        "access_review_campaign": _own(access_review_campaign, "name"),
    }
)
# Object types without a label: rows that have no identifier of their own a person would know
# (their event shows the object's values, and ``detail`` names what they belong to), rows whose
# events are AUD-FACT summaries without an object id, and what is no table (``route``,
# ``missing_object``).
NO_LABEL: Final = frozenset(
    {
        "access_review_item",
        "account_mapping_rule",
        "approval_delegation",
        "audit_chain_verification",
        "calc_trace",
        "close_checklist_item",
        "combination_group_member",
        "contract_computation",
        "contract_event",
        "contract_hold",
        "contract_source_link",
        "contract_version",
        "contract_version_balance",
        "entity_book",
        "event_submission",
        "external_id_map",
        "file_attachment",
        "file_object",
        "fx_rate",
        "job",
        "journal_batch",
        "journal_line",
        "missing_object",
        "obligation_version",
        "period_state_transition",
        "posting_ack",
        "product_bundle_component",
        "reconciliation_item",
        # a registry version is known by its category, scope and number, which are enumeration
        # literals the screen words itself; they are in the event's values
        "registry_version",
        "role_assignment",
        "route",
        "rule",
        "rule_test_case",
        "schedule",
        "schedule_line",
        "sod_exception",
        "source_invoice",
        "source_invoice_line",
        "source_order",
        "source_order_line",
        "source_record",
        "ssp_calculator_exclusion",
        "ssp_calculator_result",
        "ssp_entry",
        "ssp_range",
        "subledger_line",
        "subledger_posting",
        "subledger_posting_seal",
        "support_grant",
        "sync_run",
        "tenant",
        "tenant_currency",
        "tenant_snapshot",
        "user_mfa_factor",
        "webhook_delivery",
        "webhook_endpoint",
    }
)


def label(
    object_type: ColumnElement[Any], object_id: ColumnElement[Any], tenant_id: ColumnElement[Any]
) -> ColumnElement[Any]:
    """The label of the object an event names, null for a type of ``NO_LABEL`` and for no id. A
    column of a statement that selects the three arguments."""
    branches = [
        (object_type == literal(name), build(object_id, tenant_id))
        for name, build in LABELS.items()
    ]
    return case(*branches, else_=null()).cast(Text)
