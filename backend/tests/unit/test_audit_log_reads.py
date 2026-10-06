"""The audit log's reads, without a database (04 §16.14 "Audit events", rev 1.154; item
AUD-API-GAPS-1): where a read starts, what the statement of a read carries, and the closed list of
object labels. The plans are held in ``tests/pg/test_audit_log_plans.py`` and the answers in
``tests/api/test_audit_api.py``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from erev_api.audit import contract_key
from erev_api.audit.redact import PERSONAL, REDACT
from erev_api.db.tables import audit_event, audit_event_contract, metadata
from erev_api.domain.platform import audit_labels, audit_log
from sqlalchemy import Label
from sqlalchemy.dialects import postgresql
from support.architecture import ROOT

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
CONTRACT = UUID("00000000-0000-7000-8000-00000000000a")


def _sql(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


def test_a_read_starts_at_from_else_thirty_days_before_its_end() -> None:
    since, until = NOW - timedelta(days=400), NOW - timedelta(days=90)
    assert audit_log.window_start(NOW, since=None, until=None) == NOW - timedelta(days=30)
    assert audit_log.window_start(NOW, since=None, until=until) == until - timedelta(days=30)
    assert audit_log.window_start(NOW, since=since, until=None) == since
    assert audit_log.window_start(NOW, since=since, until=until) == since  # however long


def test_a_read_ends_at_to_else_one_day_after_the_request() -> None:
    """04 §16.14 rev 1.280 (item AUDIT-LIST-PLAN-1)."""
    until = NOW - timedelta(days=90)
    assert audit_log.window_end(NOW, until=None) == NOW + timedelta(days=1)
    assert audit_log.window_end(NOW, until=until) == until


def test_the_statement_adds_a_start_and_an_end_only_where_the_caller_sent_none() -> None:
    """``from`` and ``to`` are filters of the list kernel; the resource adds the default start and
    the default end (rev 1.280), and neither for a read by contract or by chain sequence."""
    start = "erev.audit_event.occurred_at >="
    end = "erev.audit_event.occurred_at <"
    default = audit_log.event_source(NOW).statement
    assert start in _sql(default) and end + " " in _sql(default)
    assert default.compile().params["occurred_at_1"] == NOW - timedelta(days=30)
    assert default.compile().params["occurred_at_2"] == NOW + timedelta(days=1)
    before = audit_log.event_source(NOW, until=NOW - timedelta(days=90)).statement
    assert before.compile().params["occurred_at_1"] == NOW - timedelta(days=120)
    assert end + " " not in _sql(before)  # `to` is the list kernel's
    since = audit_log.event_source(NOW, since=NOW - timedelta(days=400))
    assert start not in _sql(since.statement)
    assert since.statement.compile().params["occurred_at_1"] == NOW + timedelta(days=1)
    by_sequence = _sql(audit_log.event_source(NOW, by_sequence=True).statement)
    assert start not in by_sequence and end + " " not in by_sequence
    of_contract = _sql(audit_log.event_source(NOW, contract_id=CONTRACT).statement)
    assert "occurred_at >=" not in of_contract and "occurred_at <" not in of_contract
    # The log as a whole is sorted and filtered by the table's own columns.
    assert since.columns["chain_seq"] is audit_event.c.chain_seq
    assert set(since.columns) == set(audit_event.c.keys())


def test_the_trail_of_a_contract_is_the_link_and_a_lateral_lookup_of_each_event() -> None:
    """04 T-PLT-48: every condition of the read compares plain columns — no ``detail`` operator,
    which a row-level-security policy would keep out of an index condition — and the event is
    looked up LATERAL with a limit, so that the link always drives the read."""
    source = audit_log.trail_source(CONTRACT)
    sql = _sql(source.statement)
    assert sql.endswith(
        "FROM erev.audit_event_contract JOIN LATERAL (SELECT event.tenant_id AS tenant_id, "
        "event.occurred_at AS occurred_at, event.id AS id, event.chain_seq AS chain_seq, "
        "event.actor_id AS actor_id, event.actor_kind AS actor_kind, "
        "event.actor_roles AS actor_roles, event.auth_method AS auth_method, "
        "event.mfa_verified AS mfa_verified, event.on_behalf_of_id AS on_behalf_of_id, "
        "event.api_client_id AS api_client_id, event.support_grant_id AS support_grant_id, "
        "event.source_ip AS source_ip, event.request_id AS request_id, event.action AS action, "
        "event.object_type AS object_type, event.object_id AS object_id, "
        "event.object_version AS object_version, event.before AS before, event.after AS after, "
        "event.diff AS diff, event.reason_code AS reason_code, event.comment AS comment, "
        "event.approval_request_id AS approval_request_id, event.outcome AS outcome, "
        "event.detail AS detail, event.prev_hmac AS prev_hmac, event.hmac AS hmac, "
        "event.hmac_key_id AS hmac_key_id \n"
        "FROM erev.audit_event AS event \n"
        "WHERE event.tenant_id = erev.audit_event_contract.tenant_id AND "
        "event.occurred_at = erev.audit_event_contract.occurred_at AND "
        "event.id = erev.audit_event_contract.audit_event_id \n"
        " LIMIT %(param_52)s) AS trail ON true \n"
        "WHERE erev.audit_event_contract.contract_id = %(contract_id_1)s::UUID"
    ), sql[-1800:]
    assert source.statement.compile().params["param_52"] == 1
    assert "detail ->" not in sql and "@>" not in sql
    # The sequence, the instant and the id are the link's — what the list kernel sorts and
    # continues a page by (DG-LST-08); every other key is the looked-up event's.
    link = "erev.audit_event_contract"
    assert sql.startswith(
        f"SELECT {link}.occurred_at, {link}.audit_event_id AS id, {link}.chain_seq, "
        "trail.actor_id, "
    )
    assert source.columns["chain_seq"] is audit_event_contract.c.chain_seq
    assert source.columns["occurred_at"] is audit_event_contract.c.occurred_at
    identity = source.columns["id"]
    assert isinstance(identity, Label) and identity.name == "id"
    assert identity.element is audit_event_contract.c.audit_event_id
    assert str(source.columns["object_type"]) == "trail.object_type"
    assert set(source.columns) == set(audit_event.c.keys())
    # The lookups read with the row are correlated to the trail: no second read of the log.
    assert re.findall(r"FROM erev\.audit_event\b[^\n]*", sql) == ["FROM erev.audit_event AS event "]
    assert "erev.contract.id = trail.object_id" in sql
    assert "erev.tenant_membership.user_id = trail.actor_id" in sql


def test_the_key_is_read_back_as_the_writer_stated_it() -> None:
    """``contract_key.named`` is what the chain append writes T-PLT-48 rows from."""
    other = UUID("00000000-0000-7000-8000-00000000000b")
    assert contract_key.named(contract_key.keyed("modification", None, contract_id=CONTRACT)) == [
        CONTRACT
    ]
    several = contract_key.keyed("combination_group", {"x": 1}, contract_ids=[other, CONTRACT])
    assert contract_key.named(several) == [CONTRACT, other]
    assert contract_key.named(contract_key.keyed("tenant", {"x": 1})) == []
    assert contract_key.named(None) == [] and contract_key.named({}) == []
    # The key is stored as the writer states it: neither member is redacted or pseudonymised.
    assert not {contract_key.CONTRACT_ID, contract_key.CONTRACT_IDS} & (REDACT | PERSONAL)


def test_every_audited_object_type_has_a_label_or_is_listed_without_one() -> None:
    labelled, unlabelled = set(audit_labels.LABELS), set(audit_labels.NO_LABEL)
    assert not labelled & unlabelled
    audited = contract_key.ALWAYS | contract_key.WHERE_NAMED | contract_key.OTHER
    assert labelled | unlabelled == audited, sorted((labelled | unlabelled) ^ audited)
    # A label is read from the row the event names: the type is a table.
    assert all(f"erev.{name}" in metadata.tables for name in labelled)


def test_the_data_model_lists_the_labelled_types() -> None:
    """04 §16.14 "Audit event object labels" names exactly the object types the code labels."""
    text = (ROOT / "docs" / "04-DATA_MODEL.md").read_text(encoding="utf-8")
    table = text[text.index("**Audit event object labels**") :]
    table = table[: table.index("**API-S-EvidencePackCreate**")]
    rows = [line for line in table.splitlines() if line.startswith("| `")]
    documented = [name for row in rows for name in re.findall(r"`([a-z_]+)`", row.split("|")[1])]
    assert len(documented) == len(set(documented))
    assert set(documented) == set(audit_labels.LABELS), sorted(
        set(documented) ^ set(audit_labels.LABELS)
    )


def test_a_label_is_one_lookup_in_the_events_own_statement() -> None:
    statement = audit_log.event_select()
    sql = _sql(statement)
    # Every lookup is correlated to the event: the statement reads audit_event once.
    assert len(re.findall(r"FROM erev\.audit_event\b", sql)) == 1
    label = sql[sql.index("CAST(CASE WHEN (erev.audit_event.object_type") :]
    for name in audit_labels.LABELS:
        table = f"erev.{name}"
        key = (
            f"{table}.id = erev.audit_event.object_id"
            if name == "app_user"  # RLS-NONE-U: no tenant column
            else f"{table}.tenant_id = erev.audit_event.tenant_id AND {table}.id = "
            "erev.audit_event.object_id"
        )
        assert key in label, name
    # one branch a labelled type; the one WHEN more stands inside the membership's lookup — the
    # name a workspace is shown of the person (``users.SHOWN_NAME``; D-80 rule 5)
    branch = " WHEN (erev.audit_event.object_type = "
    assert label.count(branch) == len(audit_labels.LABELS)
    assert label.count(" WHEN ") == len(audit_labels.LABELS) + 1
    shown = " WHEN (erev.tenant_membership.status IN ("
    assert label.count(shown) == 1
    assert label.rstrip().endswith("ELSE NULL END AS TEXT) AS object_label \nFROM erev.audit_event")


def test_an_actors_membership_is_read_for_a_person_alone() -> None:
    sql = _sql(audit_log.event_select())
    membership = sql[sql.index("CASE WHEN (erev.audit_event.actor_kind = ") :]
    membership = membership[: membership.index("AS actor_membership_id")]
    assert "erev.tenant_membership.user_id = erev.audit_event.actor_id" in membership
    assert "erev.tenant_membership.status != " in membership
    assert membership.rstrip().endswith("ELSE NULL END")
