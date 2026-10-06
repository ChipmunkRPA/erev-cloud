"""The read side of the database platform (record §19, rules READ-1 to READ-6).

Everything the checkpoint comparison consumes is rebuilt from the rows the commands persisted,
field by field, through a ``TableSource`` — the real one over ``support.factories.Workspace``
(``WorkspaceRows``), a fake with rows per table in the unit tests. Nothing here derives a value a
row does not carry: a member the tables do not keep is a ``NOT_PERSISTED`` sentinel the comparison
never reads, and a block the rows cannot place (per-period balances, T-CON-09) is refused by name.

- ``PersistedReads.output_bundle``: the ``OutputBundle`` of one combination group as of a
  ``known_at`` (READ-1, READ-2) — the latest ``contract_version`` per book, its obligation versions,
  its hash-verified ``calc_trace`` under the key's group name, and the group's sealed postings
  through that cutoff as ``PostingIntent``s;
- ``approval_pairs``: the PENDING ``approval_request`` of each subject (READ-3);
- ``invitation_token``: the token of the link in the invitation email a membership was sent;
- ``period_state``: the state as of ``known_at`` from the transition history (READ-5);
- ``journal_lines`` / ``report_rows``: the persisted lines of a journal run and the JSON dataset
  of a report run (READ-6);
- ``fingerprint``: the unchanged-state digest for expected refusals (READ-4, WSA-2).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any, Final, Protocol
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.db.tables import (
    approval_request,
    audit_event,
    calc_trace,
    combination_group,
    combination_group_member,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    contract_version_balance,
    gl_account,
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    legal_entity,
    obligation,
    obligation_version,
    outbox_message,
    period,
    period_state,
    period_state_transition,
    report_run,
    role,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.db.types import MoneyType
from erev_api.domain.platform.provisioning import INVITATION_LINK
from erev_api.enums import ApprovalSubjectType, OutboxTopic
from erev_api.events import outbox
from erev_api.explain.store import trace_from_row
from erev_engine.bundle import (
    BalanceOut,
    BookOutput,
    ContractVersionOut,
    IntentLine,
    ObligationVersionOut,
    OutputBundle,
    PostingIntent,
)
from erev_engine.currencies import ISO_4217
from erev_engine.money import decimal_to_minor
from erev_engine.stages.s01_canonicalize import (
    contract_subject_key,
    encode_key,
    obligation_subject_key,
)
from erev_engine.trace import Trace
from sqlalchemy import Table, Text, Uuid, cast, func, select
from support import links
from support.answer_keys.platform_runner import JournalLine, NotProvisioned
from support.answer_keys.runners import _decode_component, _source_contracts

__all__ = [
    "LEGACY",
    "NOT_PERSISTED",
    "PENDING",
    "PersistedReads",
    "TableSource",
    "WorkspaceRows",
    "money_columns",
]

NOT_PERSISTED: Final = "<not persisted>"
PENDING: Final = "PENDING"
LEGACY: Final = "LEGACY"
STAMPS: Final = frozenset(
    {
        "tenant_id",
        "created_at",
        "created_by",
        "created_by_kind",
        "updated_at",
        "updated_by",
        "updated_by_kind",
        "row_version",
    }
)
# The columns ``computation._persist_book`` fixes beside the engine columns of a contract version.
VERSION_FIXED: Final = frozenset(
    {
        "id",
        "combination_group_id",
        "contract_computation_id",
        "book_code",
        "version_no",
        "previous_version_id",
        "known_at",
        "cause_event_ids",
        "output_sha256",
        "calc_trace_id",
        "transaction_currency",
        "pinned_policies",
    }
)
# READ-2 (amended, Q-12 → D-98 65): the T-CON-09 balance measures the stage-10 member-balance
# trace nodes carry (``<measure>:<contract>@<entity>:<period_key>``), and the five the engine's
# ``_balances`` zero-fills for every member balance.
BALANCE_MEASURES: Final = frozenset(
    {
        "contract_liability",
        "contract_liability_current",
        "contract_asset",
        "contract_asset_current",
        "unbilled_receivable",
        "accounts_receivable",
        "refund_liability",
        "return_asset",
        "deposit_liability",
        "customer_incentive_asset",
        "consideration_payable",
        "cost_asset_carrying",
        "loss_provision",
    }
)
ZERO_FILLED_MEASURES: Final = (
    "refund_liability",
    "return_asset",
    "deposit_liability",
    "customer_incentive_asset",
    "consideration_payable",
)
# Stage 11 (``s11_costs_loss/balances.py``): the member columns summed from asset / loss-unit
# grain producer nodes per (contract, period), 0 where none, no node cited, no functional column.
STAGE11_COLUMNS: Final[Mapping[str, str]] = {
    "cost_asset_carrying": "carrying_amount",
    "loss_provision": "loss_provision_required",
}
# The measures ``_balances`` sums from component / obligation grain into the member rows.
SUMMED_MEASURES: Final = frozenset(
    {
        "refund_liability",
        "return_asset",
        "accounts_receivable",
        "deposit_liability",
        "customer_incentive_asset",
        "consideration_payable",
    }
)
FINGERPRINT_TABLES: Final = (
    (audit_event, "chain_seq"),
    (contract_event, "id"),
    (approval_request, "request_no"),
    (subledger_line, "id"),
    (period_state_transition, "id"),
)


class TableSource(Protocol):
    """Rows of the tenant's tables, by equality filters; the real source is the workspace."""

    @property
    def tenant_id(self) -> UUID: ...

    def table_rows(self, table: Table, **equals: object) -> list[dict[str, Any]]: ...

    def aggregate(self, table: Table, column: str) -> tuple[int, object]:
        """``(count(*), max(column))`` of the tenant's rows."""
        ...

    def file_bytes(self, file_id: UUID) -> bytes: ...


class WorkspaceRows:
    """``TableSource`` over ``support.factories.Workspace`` (tenant-scoped read sessions)."""

    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace

    @property
    def tenant_id(self) -> UUID:
        return UUID(str(self.workspace.tenant_id))

    def table_rows(self, table: Table, **equals: object) -> list[dict[str, Any]]:
        statement = select(table)
        for name, value in equals.items():
            statement = statement.where(table.c[name] == value)
        return list(self.workspace.rows(statement))

    def aggregate(self, table: Table, column: str) -> tuple[int, object]:
        # PostgreSQL 17 has no ``max(uuid)``: a uuid column's greatest value is read through its
        # TEXT form, whose order is the value's (the ``monitors.fx_requirement_query`` precedent).
        value = table.c[column]
        greatest = func.max(cast(value, Text) if isinstance(value.type, Uuid) else value)
        statement = select(func.count().label("n"), greatest.label("m"))
        (row,) = self.workspace.rows(statement)
        return int(row["n"]), row["m"]

    def file_bytes(self, file_id: UUID) -> bytes:
        from erev_api.db.session import DbContext, tenant_session
        from erev_api.files.store import open_file

        context = DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context, read_only=True) as session:
            _, stream = open_file(
                session, file_id, files=self.workspace.files, keyring=self.workspace.keyring
            )
            return bytes(stream.read())


def money_columns(table: Table) -> frozenset[str]:
    """The ``MoneyType`` columns of ``table`` (CV-30: posted amounts, minor units in the engine)."""
    return frozenset(column.name for column in table.columns if isinstance(column.type, MoneyType))


def _minor(currency: str) -> int:
    spec = ISO_4217.get(currency)
    if spec is None:
        raise NotProvisioned(f"currency {currency!r} is not in ISO 4217", "erev_engine.currencies")
    return int(spec.minor_unit)


def _units(value: object, currency: str) -> int:
    """A persisted money value (NUMERIC) back to the engine's int minor units (XR-03)."""
    return decimal_to_minor(Decimal(str(value)), _minor(currency))


def under_group_name(trace: Trace, persisted: str, named: str) -> Trace:
    """READ-2 (amended; dev-guide rev 1.219): the trace as the comparison reads it. Every node
    whose subject is the group — by itself, or as the head of ``<group>@<entity>`` and
    ``<group>@<entity>/<KIND>/<source>`` — names it by the key's group name instead of the code
    the product gave the group. Node ids, the node ids among a node's inputs and the root
    measures are renamed alike, after the stored trace was verified by its hash; no value, formula
    or parameter moves. A node id is ``<measure>[@<event key>]:<subject>:<period key>``, and a key
    component never holds a colon (CV-21)."""
    old, new = encode_key(persisted), encode_key(named)
    if old == new:
        return trace

    def renamed(node_id: str) -> str:
        measure, first, rest = node_id.partition(":")
        subject, last, period_key = rest.rpartition(":")
        if not (first and last):
            return node_id
        if subject == old or subject.startswith((f"{old}@", f"{old}/")):
            return f"{measure}:{new}{subject[len(old) :]}:{period_key}"
        return node_id

    nodes = sorted(
        (
            dataclasses.replace(
                node,
                id=renamed(node.id),
                inputs=tuple(
                    renamed(item) if isinstance(item, str) else item for item in node.inputs
                ),
            )
            for node in trace.nodes
        ),
        key=lambda node: node.id,
    )
    roots = {measure: renamed(node_id) for measure, node_id in trace.root_measures.items()}
    return dataclasses.replace(trace, nodes=tuple(nodes), root_measures=roots)


def _uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class PersistedReads:
    """The reads of record §19 over a ``TableSource``."""

    def __init__(self, source: TableSource, keyring: KeyRing | None = None) -> None:
        self.source = source
        # The key ring an emailed link is composed with (``invitation_token``); the test
        # session's own when none is given.
        self.keyring = keyring

    # -- helpers ----------------------------------------------------------------------------------

    def _one(self, table: Table, where: str, **equals: object) -> dict[str, Any]:
        rows = self.source.table_rows(table, **equals)
        if len(rows) != 1:
            match = ", ".join(f"{name}={value}" for name, value in equals.items())
            raise NotProvisioned(
                f"{where}: {len(rows)} {table.name} rows for {match} (one expected)", table.name
            )
        return rows[0]

    def _entity(self, code: str, where: str) -> dict[str, Any]:
        return self._one(legal_entity, where, code=code)

    def _entity_codes(self) -> dict[UUID, str]:
        return {_uuid(row["id"]): str(row["code"]) for row in self.source.table_rows(legal_entity)}

    def _period_keys(self) -> dict[UUID, str]:
        return {_uuid(row["id"]): str(row["period_key"]) for row in self.source.table_rows(period)}

    def _account_codes(self) -> dict[UUID, str]:
        return {_uuid(row["id"]): str(row["code"]) for row in self.source.table_rows(gl_account)}

    def _contract_codes(self) -> dict[UUID, str]:
        return {
            _uuid(row["id"]): str(row["external_id"]) for row in self.source.table_rows(contract)
        }

    def _obligation_keys(self) -> dict[UUID, str]:
        return {
            _uuid(row["id"]): str(row["obligation_key"])
            for row in self.source.table_rows(obligation)
        }

    # -- READ-3: approvals ------------------------------------------------------------------------

    def approval_pairs(
        self, subject_type: ApprovalSubjectType, subject_ids: Sequence[UUID], *, where: str
    ) -> tuple[tuple[UUID, str], ...]:
        """The PENDING request of each subject as ``(id, subject_content_sha256)``; none or
        several for one subject refuses by name."""
        pairs: list[tuple[UUID, str]] = []
        for subject_id in subject_ids:
            rows = [
                row
                for row in self.source.table_rows(
                    approval_request, subject_type=subject_type.value, subject_id=subject_id
                )
                if str(row.get("status")) == PENDING
            ]
            if len(rows) != 1:
                raise NotProvisioned(
                    f"{where}: {len(rows)} pending approval requests for {subject_type.value} "
                    f"{subject_id} (rule READ-3; one expected)",
                    "erev_api.approvals.engine.decide",
                )
            (row,) = rows
            digest = row.get("subject_content_sha256")
            if not digest:
                raise NotProvisioned(
                    f"{where}: the pending request of {subject_type.value} {subject_id} carries "
                    "no subject_content_sha256 (rule READ-3)",
                    "erev_api.approvals.engine.decide",
                )
            pairs.append((_uuid(row["id"]), str(digest)))
        return tuple(pairs)

    def impact_preview_sha256(self, approval_request_id: UUID) -> str | None:
        """The digest of the impact preview the request shows its approver, or None when it has
        none (REQ-PLT-015): an approval of a request with a preview states that digest — the
        proof that the preview was reviewed — and is refused without it."""
        row = self._one(approval_request, "impact preview of a request", id=approval_request_id)
        digest = row.get("impact_preview_sha256")
        return None if not digest else str(digest)

    # -- the invitation a membership was sent ------------------------------------------------------

    def invitation_token(self, membership_id: UUID, *, where: str) -> str:
        """The token of the link in the one invitation email ``membership_id`` was sent
        (``provisioning.invitation_message``: the ``EMAIL`` outbox row of the membership). The
        row holds neither the token nor its hash — it keeps the place for it in ``link_path`` and
        names it in ``link_token`` (04 T-INT-03 ``payload`` rev 1.151) — so the link is composed
        as the email carries it (``support.links``, the dispatcher's own composition). The invited
        user reads it in that email, and so does the runner: no invitation message, or several,
        refuses by name."""
        prefix = INVITATION_LINK.partition(outbox.TOKEN_PLACE)[0]
        invitations = [
            payload
            for payload in (
                row.get("payload") or {}
                for row in self.source.table_rows(
                    outbox_message, aggregate_type="tenant_membership", aggregate_id=membership_id
                )
                if str(row.get("topic")) == OutboxTopic.EMAIL.value
            )
            if str(payload.get("link_path") or "") == INVITATION_LINK
        ]
        if len(invitations) != 1:
            raise NotProvisioned(
                f"{where}: {len(invitations)} invitation messages sent to membership "
                f"{membership_id} (one expected)",
                "erev_api.domain.platform.memberships.accept_invitation",
            )
        return links.emailed_token(invitations[0], self.keyring, prefix=prefix)

    # -- READ-7: roles and period-state ids -------------------------------------------------------

    def role_id(self, code: str) -> UUID:
        """The tenant's ``role`` row by code (``TenantProvisionResult`` carries no roles)."""
        return _uuid(self._one(role, f"role {code}", code=code)["id"])

    def _state_row(self, entity: str, book: str, period_key: str, where: str) -> dict[str, Any]:
        entity_row = self._entity(entity, where)
        period_row = self._one(
            period, where, calendar_id=entity_row["calendar_id"], period_key=period_key
        )
        return self._one(
            period_state,
            where,
            entity_id=entity_row["id"],
            book_code=book,
            period_id=period_row["id"],
        )

    def period_state_id(self, entity: str, book: str, period_key: str) -> UUID:
        """The ``period_state`` row of (entity, book, period) (``EntityBookOut`` carries none)."""
        where = f"period state {entity} {book} {period_key}"
        return _uuid(self._state_row(entity, book, period_key, where)["id"])

    # -- READ-5: period state as of known_at -------------------------------------------------------

    def period_state(
        self,
        entity: str,
        book: str,
        period_key: str,
        known_at: datetime,
        horizon: int | None = None,
    ) -> str:
        """READ-5 (amended, dev-guide rev 1.246): the period's state as of the checkpoint. A
        transition's ``created_at`` and the row's ``state_changed_at`` are the application
        clock's (``uow.now``), which the plan sets to an item's business time: against the
        server-time ``known_at`` every transition read as past, and a later lock would have
        answered an earlier checkpoint. A transition is placed by the transaction that wrote it
        (``period_state_transition.created_txid``, the server's ``txid_current()``; 04 DB-07):
        at or before the checkpoint when that transaction began before ``horizon``, the
        transaction horizon the runner read with the checkpoint's stamp — the rule the subledger
        read places a close run's posting by (``_intents``). Without a horizon the read is
        refused by name, and so is a state row that holds no transition: the product writes one
        with the row and with every change of its state (04 DB-07), and nothing else places it."""
        where = f"period {entity} {book} {period_key} at {known_at.isoformat()}"
        state = self._state_row(entity, book, period_key, where)
        if horizon is None:
            raise NotProvisioned(
                f"{where}: the platform kept no transaction horizon to place the period's "
                "transitions by (rule READ-5 amended; dev-guide rev 1.246)",
                "erev_api.domain.close.queries.period_view",
            )
        transitions = sorted(
            self.source.table_rows(period_state_transition, period_state_id=state["id"]),
            key=lambda row: (int(row["created_txid"]), row["created_at"], str(row["id"])),
        )
        if not transitions:
            raise NotProvisioned(
                f"{where}: the period's state row holds no transition, so nothing places its "
                "state at a checkpoint (rule READ-5 amended; 04 DB-07)",
                "erev_api.domain.close.queries.period_view",
            )
        before = [row for row in transitions if int(row["created_txid"]) < horizon]
        if before:
            return str(before[-1]["to_state"])
        earlier = transitions[0].get("from_state")
        if earlier is None:
            raise NotProvisioned(
                f"{where}: the first transition names no from_state (rule READ-5)",
                "erev_api.domain.close.queries.period_view",
            )
        return str(earlier)

    # -- READ-6: journal lines and report rows ----------------------------------------------------

    def journal_runs(self, entity: str, book: str, period_key: str) -> list[dict[str, Any]]:
        """The ``journal_run`` rows of (entity, book, period) — the key of a run's coverage (04
        DB-16) — oldest first: by creation, and the runs of one instant in the order of their
        numbers, as the product orders them (``journals.commands._later_run``). Cancelled runs
        are among them; the caller reads ``state``."""
        where = f"journal runs {entity} {book} {period_key}"
        entity_row = self._entity(entity, where)
        period_row = self._one(
            period, where, calendar_id=entity_row["calendar_id"], period_key=period_key
        )
        rows = self.source.table_rows(
            journal_run,
            entity_id=entity_row["id"],
            book_code=book,
            period_id=period_row["id"],
        )
        return sorted(
            rows, key=lambda row: (row["created_at"], len(str(row["run_no"])), str(row["run_no"]))
        )

    def sealed_to(self, book: str) -> int:
        """The greatest ``chain_seq`` sealed in ``book``, 0 when nothing is: where a journal run
        made now would end (``summarise.covered_to`` at a cutoff no seal lies after)."""
        return max(
            (
                int(row["chain_seq"])
                for row in self.source.table_rows(subledger_posting_seal, book_code=book)
            ),
            default=0,
        )

    def journal_lines(self, run_id: UUID, *, per_contract: bool) -> tuple[JournalLine, ...]:
        """The run's ``journal_line`` rows netted per (contract, GL account code, transaction
        currency), the runner's ``JournalLine`` grain (zero nets dropped)."""
        batches = self.source.table_rows(journal_batch, journal_run_id=run_id)
        entries = [
            entry
            for batch in batches
            for entry in self.source.table_rows(journal_entry, journal_batch_id=batch["id"])
        ]
        lines = [
            line
            for entry in entries
            for line in self.source.table_rows(journal_line, journal_entry_id=entry["id"])
        ]
        contracts = self._contract_codes() if per_contract else {}
        totals: dict[tuple[str | None, str, str], Fraction] = {}
        for row in lines:
            owner: str | None = None
            if per_contract and row.get("contract_id") is not None:
                owner = contracts.get(_uuid(row["contract_id"]))
                if owner is None:
                    raise NotProvisioned(
                        f"journal run {run_id}: line names contract {row['contract_id']}, which "
                        "the contract table does not hold",
                        "erev_api.domain.journals.commands.create_run",
                    )
            net = Fraction(Decimal(str(row["debit_txn"]))) - Fraction(
                Decimal(str(row["credit_txn"]))
            )
            key = (owner, str(row["gl_account_code"]), str(row["txn_currency"]))
            totals[key] = totals.get(key, Fraction(0)) + net
        return tuple(
            JournalLine(account, net, currency, owner)
            for (owner, account, currency), net in sorted(
                totals.items(), key=lambda item: (item[0][0] or "", item[0][1], item[0][2])
            )
            if net != 0
        )

    def report_rows(self, run_id: UUID, *, where: str) -> list[dict[str, Any]]:
        """The run's JSON dataset rows (``row_key`` and the column fields)."""
        run = self._one(report_run, where, id=run_id)
        if run.get("output_file_id") is None:
            raise NotProvisioned(
                f"{where}: report run {run_id} has no output (status {run.get('status')!r}, "
                f"problem {run.get('problem')!r})",
                "erev_api.domain.reports.framework.run_report",
            )
        document = json.loads(self.source.file_bytes(_uuid(run["output_file_id"])).decode("utf-8"))
        rows = document.get("rows") if isinstance(document, Mapping) else None
        if not isinstance(rows, list):
            raise NotProvisioned(
                f"{where}: the run's dataset carries no rows list", "erev_api.domain.reports"
            )
        return [dict(row) for row in rows]

    # -- READ-4: the unchanged-state digest --------------------------------------------------------

    def fingerprint(self) -> str:
        parts = []
        for table, column in FINGERPRINT_TABLES:
            count, greatest = self.source.aggregate(table, column)
            parts.append(f"{table.name}:{count}:{greatest}")
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    # -- READ-2: the checkpoint books --------------------------------------------------------------

    def output_bundle(
        self,
        *,
        group_id: UUID,
        group_key: str,
        members: Sequence[str],
        books: Sequence[str],
        known_at: datetime,
        where: str,
        as_of_periods: Mapping[str, str] | None = None,
        named_group: str | None = None,
        horizon: int | None = None,
    ) -> OutputBundle:
        """The group's computation as of ``known_at``: the latest contract version of each
        non-LEGACY book (READ-1) names the computation; every book of ``books`` is rebuilt from
        that computation's rows. ``as_of_periods`` (entity code → the checkpoint's as-of period)
        selects the T-CON-09 rows that cross-check the trace balances (READ-2 amended).

        Two things are not the as-of computation's alone (READ-2 amended, dev-guide rev 1.219).
        The posting intents are the group's sealed postings through ``known_at``, of every
        computation known by then (``_intents``): the product posts each computation's
        increments, and a checkpoint's ledger is every posting up to its cutoff — a close run's
        too, placed by the transaction ``horizon`` of the checkpoint (rev 1.246). And the books
        name the group as the key names it (``named_group``): the product numbers its groups, the
        comparison knows the key's name only, so the contract version's subject and the trace's
        group nodes are handed over under that name (``under_group_name``), as an obligation is
        handed its entity codes."""
        candidates = [
            row
            for book in books
            if book != LEGACY
            for row in self.source.table_rows(
                contract_version, combination_group_id=group_id, book_code=book
            )
            if row["known_at"] <= known_at
        ]
        if not candidates:
            raise NotProvisioned(
                f"{where}: no contract version of group {group_id} committed at or before "
                f"{known_at.isoformat()} (rule READ-1)",
                "erev_api.domain.contracts.queries.get_version",
            )
        latest = max(candidates, key=lambda row: (row["known_at"], int(row["version_no"])))
        computation_id = _uuid(latest["contract_computation_id"])
        computation = self._one(contract_computation, where, id=computation_id)
        # READ2-R2 / D-98 74: the member identities are the persisted T-CON-04 population AT the
        # cutoff (queries._members' half-open predicate, mirrored) and the group code the
        # persisted one; the plan's are compared and a difference refuses by name — never the
        # current contract.combination_group_id for a historical checkpoint, never a prefix.
        persisted_members = self.members_at(group_id, known_at)
        persisted_group = str(self._one(combination_group, where, id=group_id)["code"])
        if members and set(members) != set(persisted_members):
            raise NotProvisioned(
                f"{where}: the plan names members {sorted(members)} but the persisted group "
                f"{persisted_group} holds {list(persisted_members)} at {known_at.isoformat()} "
                "(rule READ-2, D-98 74)",
                "erev_api.domain.contracts.queries.get_version",
            )
        if group_key and group_key != persisted_group:
            raise NotProvisioned(
                f"{where}: the plan names group {group_key!r} but the persisted group code is "
                f"{persisted_group!r} (rule READ-2, READ2-R2)",
                "erev_api.domain.contracts.queries.get_version",
            )
        members = persisted_members
        group_key = persisted_group
        versions = {
            str(row["book_code"]): row
            for row in candidates
            if _uuid(row["contract_computation_id"]) == computation_id
        }
        outputs = tuple(
            self._book(
                book=book,
                version=versions.get(book),
                computation_id=computation_id,
                computation=computation,
                group_id=group_id,
                group_key=group_key,
                named_group=named_group or group_key,
                known_at=known_at,
                members=members,
                where=where,
                as_of_periods=as_of_periods or {},
                horizon=horizon,
            )
            for book in books
        )
        return OutputBundle(
            engine_version=str(computation["engine_version"]),
            input_sha256=str(computation["input_sha256"]),
            books=outputs,
            diagnostics=(),
        )

    def members_at(self, group_id: UUID, known_at: datetime) -> tuple[str, ...]:
        """D-98 74: the group's member external ids at ``known_at`` from the T-CON-04
        ``combination_group_member`` history — the predicate ``queries._members`` uses,
        ``valid_from_known_at <= known_at AND (valid_to_known_at IS NULL OR valid_to_known_at >
        known_at)``, mirrored over the row source; sorted, never the current group column."""
        contracts = self._contract_codes()
        found: set[str] = set()
        for row in self.source.table_rows(combination_group_member, combination_group_id=group_id):
            valid_to = row.get("valid_to_known_at")
            if row["valid_from_known_at"] <= known_at and (valid_to is None or valid_to > known_at):
                contract_id = _uuid(row["contract_id"])
                if contract_id not in contracts:
                    raise NotProvisioned(
                        f"membership of group {group_id} at {known_at.isoformat()} names contract "
                        f"{contract_id}, which the contract table does not hold",
                        "erev_api.domain.contracts.queries.get_version",
                    )
                found.add(contracts[contract_id])
        return tuple(sorted(found))

    def _book(
        self,
        *,
        book: str,
        version: Mapping[str, Any] | None,
        computation_id: UUID,
        computation: Mapping[str, Any],
        group_id: UUID,
        group_key: str,
        named_group: str,
        known_at: datetime,
        members: Sequence[str],
        where: str,
        as_of_periods: Mapping[str, str],
        horizon: int | None = None,
    ) -> BookOutput:
        if version is None and book != LEGACY:
            raise NotProvisioned(
                f"{where}: computation {computation_id} persisted no {book} contract version",
                "erev_api.domain.contracts.queries.get_version",
            )
        contracts = self._contract_codes()
        entities = self._entity_codes()
        contract_out: ContractVersionOut | None = None
        obligations: tuple[ObligationVersionOut, ...] = ()
        balances: tuple[BalanceOut, ...] = ()
        statuses: tuple[tuple[str, str], ...] = ()
        if version is not None:
            currency = str(version["transaction_currency"])
            contract_out = ContractVersionOut(
                subject_key=named_group,
                columns=self._columns(contract_version, version, VERSION_FIXED, currency, None),
                trace_nodes={},  # the contract_version table keeps no trace_nodes column
            )
            obligations = tuple(
                ObligationVersionOut(
                    subject_key=obligation_subject_key(
                        contracts[_uuid(row["contract_id"])], str(row["obligation_key"])
                    ),
                    columns=self._obligation_columns(row, currency, entities),
                    trace_nodes={
                        str(key): str(value)
                        for key, value in dict(row.get("trace_nodes") or {}).items()
                    },
                )
                for row in sorted(
                    self.source.table_rows(obligation_version, contract_version_id=version["id"]),
                    key=lambda row: str(row["obligation_key"]),
                )
            )
            trace = under_group_name(
                trace_from_row(self._one(calc_trace, where, contract_version_id=version["id"])),
                group_key,
                named_group,
            )
            obligation_entities = {
                obligation_subject_key(
                    contracts[_uuid(row["contract_id"])], str(row["obligation_key"])
                ): entities[_uuid(row["contracting_entity_id"])]
                for row in self.source.table_rows(
                    obligation_version, contract_version_id=version["id"]
                )
                if row.get("contracting_entity_id") is not None
            }
            balances = self.trace_balances(
                trace,
                currency=currency,
                members=members,
                group_key=named_group,
                obligation_entities=obligation_entities,
                where=where,
            )
            self._cross_check_balances(
                version, balances, contracts, entities, as_of_periods, where=where
            )
            status = version.get("status_in_book")
            if status is not None:
                statuses = tuple((member, str(status)) for member in members)
        else:
            trace = Trace(
                format_version=1,
                engine_version=str(computation["engine_version"]),
                nodes=(),
                root_measures={},
            )
        return BookOutput(
            book_code=book,
            contract_version=contract_out,
            status_in_book=statuses,
            obligation_versions=obligations,
            balances=balances,
            schedules=(),
            cost_asset_versions=(),
            loss_provision_versions=(),
            fx_layer_movements=(),
            posting_intents=self._intents(
                book,
                group_id,
                known_at,
                contracts,
                entities,
                where,
                members=members,
                horizon=horizon,
            ),
            proposals=(),
            time_triggers=(),
            trace=trace,
        )

    def trace_balances(
        self,
        trace: Trace,
        *,
        currency: str,
        members: Sequence[str] = (),
        group_key: str | None = None,
        obligation_entities: Mapping[str, str] | None = None,
        where: str,
    ) -> tuple[BalanceOut, ...]:
        """READ-2 (amended, D-98 72): the T-CON-09 member balances rebuilt by the engine's own
        ``_balances`` aggregation over the hash-verified trace — member-grain nodes open the rows
        (``<measure>:<contract>@<entity>:<period>``), component-grain refund nodes
        (``<group>@<entity>/<KIND>/<source>``) and obligation-grain nodes
        (``<contract>/<obligation>``)
        are attributed to their member row and summed as signed int minor units; the five measures
        the engine zero-fills are zero-filled, nothing else; a group subject never becomes a member
        row; an unattributable node refuses by name. Nothing is derived from the T-CON-09 row."""
        functional_of = {
            encode_key(str(row["code"])): (str(row["code"]), str(row["functional_currency"]))
            for row in self.source.table_rows(legal_entity)
            if row.get("functional_currency") is not None
        }
        member_set = set(members)
        encoded_members = {encode_key(member): member for member in members}
        encoded_group = None if group_key is None else encode_key(group_key)
        refund_heads: dict[str, str] = {}  # obligation subject named by a refund source → entity
        grouped: dict[tuple[str, str], tuple[dict[str, object], dict[str, str]]] = {}
        summed: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
        rollups: dict[tuple[str, str, str], tuple[int, str]] = {}

        def entity_of(component: str, node_id: str) -> tuple[str, str]:
            found = functional_of.get(component)
            if found is None:
                raise NotProvisioned(
                    f"{where}: balance node {node_id} names an entity the tenant does not hold",
                    "erev_api.domain.contracts.queries.balances",
                )
            return found

        def units(node: Any) -> int:
            minor = int(dict(node.params).get("minor_unit", _minor(currency)))
            return decimal_to_minor(Decimal(node.value), minor)

        balance_nodes = []
        stage11: dict[tuple[str, str, str], int] = {}  # (contract head, period, column) → sum
        stage11_names = {node_measure: column for column, node_measure in STAGE11_COLUMNS.items()}
        for node in trace.nodes:
            measure, _, rest = node.id.partition(":")
            subject, _, period_key = rest.rpartition(":")
            if measure in stage11_names:
                head = subject.partition("/")[0]
                key = (head, period_key, stage11_names[measure])
                stage11[key] = stage11.get(key, 0) + units(node)
                continue
            if measure not in BALANCE_MEASURES:
                continue
            balance_nodes.append((measure, subject, period_key, node))
        # 1. member grain — the rows.
        for measure, subject, period_key, node in balance_nodes:
            if "/" in subject or "@" not in subject:
                continue
            head, _, entity_component = subject.rpartition("@")
            if encoded_group is not None and head == encoded_group and head not in encoded_members:
                continue  # the group's own row (grain check): never a member row
            if members and head not in encoded_members:
                raise NotProvisioned(
                    f"{where}: balance node {node.id} names {_decode_component(head)!r}, neither a "
                    "member of the group nor the group (rule READ-2)",
                    "erev_api.domain.contracts.queries.balances",
                )
            entity_code, functional = entity_of(entity_component, node.id)
            if measure in SUMMED_MEASURES:
                if node.params.get("role") == "member_sum":
                    # D-97 (8) (lane ENG-T1F, DG-KRN-EXP-01): the stage 10 member-sum node IS the
                    # member row's value for the measure and period — the engine's own link —
                    # and its component nodes are its inputs, never added on top of it. A row
                    # without a member-sum node keeps the component sum (keys without rollups).
                    key = (subject, period_key, measure)
                    if key in rollups:
                        raise NotProvisioned(
                            f"{where}: two member-sum nodes for {measure} on {subject} at "
                            f"{period_key} ({rollups[key][1]}, {node.id})",
                            "erev_api.domain.contracts.queries.balances",
                        )
                    rollups[key] = (units(node), node.id)
                    continue
                summed.setdefault((subject, period_key, measure), []).append((units(node), node.id))
                continue
            columns, nodes = grouped.setdefault(
                (subject, period_key),
                (
                    {
                        "entity": entity_code,
                        "functional_currency": functional,
                        "txn_currency": currency,
                    },
                    {},
                ),
            )
            value = units(node)
            columns[f"{measure}_txn"] = value
            nodes[measure] = node.id
            if functional == currency:
                # DG-KRN-EXP-01 (lane ENG-T1F, T1F-Q-4): at rate 1 the ``_functional`` column is
                # a copy of the ``_txn`` value and links the same node (stage 10 measures; the
                # stage 11 columns publish no ``_functional`` member).
                columns[f"{measure}_functional"] = value
                if measure not in STAGE11_COLUMNS:
                    nodes[f"{measure}_functional"] = node.id
        # 2. component grain — refund liabilities per <group>@<entity>/<KIND>/<source>.
        for measure, subject, period_key, node in balance_nodes:
            head, slash, rest = subject.partition("/")
            if not slash or "@" not in head:
                continue
            head_name, _, entity_component = head.rpartition("@")
            kind, _, source = rest.partition("/")
            named = _source_contracts(kind, source.split("/")) if source else None
            if named is None:
                raise NotProvisioned(
                    f"{where}: balance node {node.id} has a component key outside the D-90 "
                    "grammar; it cannot be attributed (rule READ-2)",
                    "erev_api.domain.contracts.queries.balances",
                )
            contracts = list(dict.fromkeys(named))
            if encoded_group is None or head_name != encoded_group:
                contracts.append(_decode_component(head_name))
            contracts = list(dict.fromkeys(contracts))
            if len(contracts) != 1:
                raise NotProvisioned(
                    f"{where}: balance node {node.id} names {len(contracts)} contracts; the engine "
                    "attributes a component to one (rule READ-2)",
                    "erev_api.domain.contracts.queries.balances",
                )
            (contract_key,) = contracts
            entity_code, _ = entity_of(entity_component, node.id)
            if kind == "RETURN":
                refund_heads[source] = entity_code  # `<contract>/<obligation>` → the entity
            row_subject = f"{encode_key(contract_key)}@{entity_component}"
            summed.setdefault((row_subject, period_key, measure), []).append((units(node), node.id))
        # 3. obligation grain — <contract>/<obligation> targets at the obligation's contracting
        # entity (the persisted obligation row, else the refund component naming it).
        for measure, subject, period_key, node in balance_nodes:
            head, slash, rest = subject.partition("/")
            if not slash or "@" in head:
                continue
            entity_code = (obligation_entities or {}).get(subject) or refund_heads.get(subject)
            if entity_code is None:
                raise NotProvisioned(
                    f"{where}: balance node {node.id} is at obligation grain and no persisted "
                    "obligation row or refund component names its entity (rule READ-2)",
                    "erev_api.domain.contracts.queries.balances",
                )
            row_subject = f"{head}@{encode_key(entity_code)}"
            summed.setdefault((row_subject, period_key, measure), []).append((units(node), node.id))
        # The engine sums only into rows the member grain opened; one node cites itself. A
        # member-sum node, where one exists, is the row's value and link (its components are its
        # inputs); otherwise the component sum.
        for key in sorted(set(summed) | set(rollups)):
            subject, period_key, measure = key
            found = grouped.get((subject, period_key))
            if found is None:
                continue
            columns, nodes = found
            rollup = rollups.get(key)
            link: str | None
            if rollup is not None:
                value, link = rollup
            else:
                items = summed[key]
                value = sum(amount for amount, _ in items)
                link = items[0][1] if len(items) == 1 else None
            columns[f"{measure}_txn"] = value
            if link is not None:
                nodes[measure] = link
            if columns["functional_currency"] == currency:
                columns[f"{measure}_functional"] = value
                if link is not None and measure not in STAGE11_COLUMNS:
                    nodes[f"{measure}_functional"] = link  # rate-1 copy links the same node
        for columns, _ in grouped.values():
            same = columns["functional_currency"] == currency
            for measure in ZERO_FILLED_MEASURES:
                columns.setdefault(f"{measure}_txn", 0)
                if same:
                    columns.setdefault(f"{measure}_functional", 0)
        # Stage 11: the member row of the contract's contracting entity takes the sums; 0 where
        # no producer node exists (the T-CON-09 default the engine applies); no node cited.
        # Attribution keys are the CV-21 ENCODED components at both ends (record §26): the
        # persisted obligation subject keys and the trace node heads already are; nothing is
        # decoded for a lookup. When the persisted mapping is supplied it is authoritative; the
        # single-member-row fallback serves only a call without it.
        contract_entities: dict[str, str] = {}
        for ob_subject, entity_code in (obligation_entities or {}).items():
            contract_entities.setdefault(ob_subject.partition("/")[0], entity_code)
        rows_of: dict[str, set[str]] = {}
        for subject, _ in grouped:
            head, _, entity_component = subject.rpartition("@")
            rows_of.setdefault(head, set()).add(entity_component)
        for (head, period_key, column), value in sorted(stage11.items()):
            entity_code = contract_entities.get(head)  # encoded head → encoded key
            mapped = entity_code is not None
            if entity_code is not None:
                entity_component: str | None = encode_key(entity_code)
            elif obligation_entities is not None:
                raise NotProvisioned(
                    f"{where}: stage-11 node {column} of {_decode_component(head)!r} {period_key}: "
                    "the persisted obligation rows name no obligation of that contract (rule "
                    "READ-2; the mapping is authoritative when supplied)",
                    "erev_api.domain.contracts.queries.balances",
                )
            elif len(rows_of.get(head, ())) == 1:
                entity_component = next(iter(rows_of[head]))
            else:
                entity_component = None
            if entity_component is None:
                raise NotProvisioned(
                    f"{where}: stage-11 node {column} of {_decode_component(head)!r} {period_key} "
                    "names a contract with no single member row and no persisted obligation "
                    "mapping was supplied (rule READ-2)",
                    "erev_api.domain.contracts.queries.balances",
                )
            found = grouped.get((f"{head}@{entity_component}", period_key))
            if found is None:
                if mapped:  # F-RPS-ST11-R1: never drop the amount, never zero-fill the other row
                    raise NotProvisioned(
                        f"{where}: stage-11 {column} of {_decode_component(head)!r} {period_key} "
                        f"is mapped to entity {entity_code!r}, for which the contract opens no "
                        "member row at that period (rule READ-2, F-RPS-ST11-R1)",
                        "erev_api.domain.contracts.queries.balances",
                    )
                continue
            found[0][f"{column}_txn"] = value
        for columns, _ in grouped.values():
            for column in STAGE11_COLUMNS:
                columns.setdefault(f"{column}_txn", 0)
        for (subject, _), _ in grouped.items():
            if encoded_group is not None and subject.rpartition("@")[0] == encoded_group:
                if group_key not in member_set:
                    raise NotProvisioned(
                        f"{where}: the group subject {subject} appeared as a member row "
                        "(rule READ-2)",
                        "erev_api.domain.contracts.queries.balances",
                    )
        return tuple(
            BalanceOut(
                subject_key=subject,
                period_key=period_key,
                columns=columns,
                trace_nodes=dict(sorted(nodes.items())),
            )
            for (subject, period_key), (columns, nodes) in sorted(grouped.items())
        )

    def _cross_check_balances(
        self,
        version: Mapping[str, Any],
        balances: Sequence[BalanceOut],
        contracts: Mapping[UUID, str],
        entities: Mapping[UUID, str],
        as_of_periods: Mapping[str, str],
        *,
        where: str,
    ) -> None:
        """READ-2 (amended): a T-CON-09 ``contract_version_balance`` row (the subject's latest
        period, unnamed) cross-checks the trace balance only where that latest period is the
        checkpoint's as-of period of its entity; a differing money column refuses by name. The row
        is never the source."""
        latest: dict[str, BalanceOut] = {}
        for balance in balances:
            current = latest.get(balance.subject_key)
            if current is None or balance.period_key > current.period_key:
                latest[balance.subject_key] = balance
        money = money_columns(contract_version_balance)
        for row in self.source.table_rows(
            contract_version_balance, contract_version_id=version["id"]
        ):
            entity_code = entities[_uuid(row["entity_id"])]
            contract_key = contract_subject_key(contracts[_uuid(row["contract_id"])])
            subject = f"{contract_key}@{encode_key(entity_code)}"
            balance = latest.get(subject)
            if balance is None or balance.period_key != as_of_periods.get(entity_code):
                continue
            functional = str(row["functional_currency"])
            for name in sorted(money):
                if row.get(name) is None or name not in balance.columns:
                    continue
                unit = functional if name.endswith("_functional") else str(row["txn_currency"])
                if _units(row[name], unit) != balance.columns[name]:
                    raise NotProvisioned(
                        f"{where}: T-CON-09 {subject} {balance.period_key} {name} = "
                        f"{row[name]} differs from the trace balance (rule READ-2 amended); the "
                        "row is never the source",
                        "erev_api.domain.contracts.queries.balances",
                    )

    def _obligation_columns(
        self, row: Mapping[str, Any], currency: str, entities: Mapping[UUID, str]
    ) -> dict[str, object]:
        """The engine columns of an obligation version row. The engine names an obligation's
        entities by code and the row keeps their ids (``computation.persist`` resolves the codes
        when it writes), so the codes are read back through the entity rows — the inverse of that
        write, as money goes back to minor units. Without ``performing_entity_code`` the
        comparison cannot find the obligation's period at a checkpoint's as-of date and compares
        the version as of its own date (API-C-10): EX42's B1-SERVICE read 0.00 recognised for
        2,400.00."""
        columns = self._columns(obligation_version, row, frozenset({"id"}), currency, None)
        for side in ("performing", "contracting"):
            entity_id = row.get(f"{side}_entity_id")
            if entity_id is not None:
                columns[f"{side}_entity_code"] = entities[_uuid(entity_id)]
        return columns

    def _columns(
        self,
        table: Table,
        row: Mapping[str, Any],
        skip: frozenset[str],
        currency: str,
        functional: str | None,
    ) -> dict[str, object]:
        """The engine columns of a persisted row: money back to int minor units (``*_functional``
        columns with the functional currency's unit, the inverse of ``computation._BalanceUnits``),
        everything else as stored; stamps and the fixed columns dropped."""
        money = money_columns(table)
        columns: dict[str, object] = {}
        for name, value in row.items():
            if name in STAMPS or name in skip:
                continue
            if value is not None and name in money:
                unit = functional if functional and name.endswith("_functional") else currency
                columns[name] = _units(value, unit)
            else:
                columns[name] = value
        return columns

    def _intents(
        self,
        book: str,
        group_id: UUID,
        known_at: datetime,
        contracts: Mapping[UUID, str],
        entities: Mapping[UUID, str],
        where: str,
        *,
        members: Sequence[str] = (),
        horizon: int | None = None,
    ) -> tuple[PostingIntent, ...]:
        """READ-2 (amended, dev-guide rev 1.219 and rev 1.246): the group's sealed postings of
        ``book`` through the checkpoint, not the as-of computation's posting alone.

        The posting of an event's computation is placed by its computation's ``known_at``, the
        record time READ-1 places a contract version by: at or before ``known_at``. A posting's
        own stamps are the application clock's (``subledger.post`` writes ``uow.now``), which the
        plan sets to an item's business time, and say nothing at a server-time cutoff.

        A posting no event's computation wrote — a close run's pass, a manual adjustment — has
        those stamps only. It is placed by the transaction that wrote it
        (``subledger_posting.created_txid``, the server's ``txid_current()``; 04 DB-06): at or
        before the checkpoint when that transaction began before ``horizon``, the transaction
        horizon the runner read with the checkpoint's stamp. The plan's steps run one after
        another, so the order of their transactions is the order of the steps. Without a horizon
        such a posting is refused by name, never guessed. A close run's release posting is the
        group's; its FX and reclass postings are the entity's and name no group (05 RCP-08 (b)):
        of those the group's entries are the ones whose lines name one of ``members``, the group's
        contracts at the cutoff.

        Every posting a read sees is sealed (04 DB-06 (3) refuses the commit of one without its
        seal). An entry is keyed by its posting and its number, so two postings never share a
        key."""
        computations = {
            _uuid(row["id"]): row
            for row in self.source.table_rows(contract_computation, combination_group_id=group_id)
        }
        computed: list[tuple[datetime, str, dict[str, Any]]] = []
        others: list[tuple[int, str, dict[str, Any], bool]] = []
        for posting in self.source.table_rows(
            subledger_posting, combination_group_id=group_id, book_code=book
        ):
            writer = posting.get("contract_computation_id")
            computation = None if writer is None else computations.get(_uuid(writer))
            if computation is not None and computation["known_at"] > known_at:
                continue  # its computation is known after the cutoff: later, whatever wrote it
            if computation is not None and computation.get("close_run_id") is None:
                computed.append((computation["known_at"], str(posting["id"]), posting))
            elif self._written_before(posting, horizon, book, where):
                others.append((int(posting["created_txid"]), str(posting["id"]), posting, False))
        for posting in self.source.table_rows(subledger_posting, book_code=book):
            if posting.get("combination_group_id") is not None:
                continue  # a group's posting: its own group's read takes it
            if posting.get("close_run_id") is None:
                # The product posts for a group, or for an entity in a close run (05 RCP-08
                # (b)); a posting of neither says nothing of whose lines it holds.
                raise NotProvisioned(
                    f"{where}: posting {posting['id']} ({posting['posting_kind']}) of book {book} "
                    "names no group and no close run (rule READ-2 amended)",
                    "erev_api.domain.journals.subledger.list_lines",
                )
            if self._written_before(posting, horizon, book, where):
                others.append((int(posting["created_txid"]), str(posting["id"]), posting, True))
        if not computed and not others:
            return ()
        periods = self._period_keys()
        accounts = self._account_codes()
        obligations = self._obligation_keys()
        owned = set(members)
        intents: list[PostingIntent] = []
        ordered = [(posting, False) for _, _, posting in sorted(computed, key=lambda p: p[:2])]
        ordered += [
            (posting, shared) for _, _, posting, shared in sorted(others, key=lambda p: p[:2])
        ]
        for posting, shared in ordered:
            rows = self.source.table_rows(subledger_line, subledger_posting_id=posting["id"])
            by_entry: dict[int, list[dict[str, Any]]] = {}
            for row in rows:
                by_entry.setdefault(int(row["entry_no"]), []).append(row)
            for entry_no, lines in sorted(by_entry.items()):
                first = lines[0]
                owner = first.get("contract_id")
                if shared and (owner is None or contracts.get(_uuid(owner)) not in owned):
                    continue  # another group's entry of the entity's posting
                external = contracts[_uuid(owner)]
                obligation_id = first.get("obligation_id")
                subject = (
                    obligation_subject_key(external, obligations[_uuid(obligation_id)])
                    if obligation_id is not None
                    else contract_subject_key(external)
                )
                origin = first.get("origin_period_id")
                intents.append(
                    PostingIntent(
                        entry_key=f"{posting['posting_kind']}:{posting['id']}:{entry_no}",
                        book_code=book,
                        entity=entities[_uuid(first["entity_id"])],
                        posting_period_key=periods[_uuid(first["period_id"])],
                        origin_period_key=None if origin is None else periods[_uuid(origin)],
                        entry_kind=str(first["entry_kind"]),
                        posting_class=NOT_PERSISTED,
                        subject_key=subject,
                        reason_code=None
                        if first.get("reason_code") is None
                        else str(first["reason_code"]),
                        lines=tuple(
                            self._line(row, accounts, entities)
                            for row in sorted(lines, key=lambda row: str(row["id"]))
                        ),
                    )
                )
        return tuple(intents)

    @staticmethod
    def _written_before(
        posting: Mapping[str, Any], horizon: int | None, book: str, where: str
    ) -> bool:
        """Whether the transaction that wrote ``posting`` — one no event's computation wrote —
        began before the checkpoint's ``horizon`` (``_intents``); refused by name without one."""
        if horizon is None:
            raise NotProvisioned(
                f"{where}: posting {posting['id']} ({posting['posting_kind']}) of book {book} "
                "is not the posting of an event's computation — a close run's pass or a manual "
                "adjustment — and the platform kept no transaction horizon to place it by "
                "(rule READ-2 amended; dev-guide rev 1.246)",
                "erev_api.domain.journals.subledger.list_lines",
            )
        return int(posting["created_txid"]) < horizon

    @staticmethod
    def _line(
        row: Mapping[str, Any], accounts: Mapping[UUID, str], entities: Mapping[UUID, str]
    ) -> IntentLine:
        amount = Decimal(str(row["amount_txn"]))
        side = str(row["dr_cr"]) if row.get("dr_cr") is not None else ("D" if amount >= 0 else "C")
        counterparty = row.get("counterparty_entity_id")
        return IntentLine(
            line_key=str(row["id"]),
            side=side,
            account_role=str(row["account_role"]),
            clearing_purpose=None
            if row.get("clearing_purpose") is None
            else str(row["clearing_purpose"]),
            counterparty_entity=None if counterparty is None else entities[_uuid(counterparty)],
            account_code=accounts[_uuid(row["gl_account_id"])],
            amount_txn=abs(_units(amount, str(row["txn_currency"]))),
            amount_functional=abs(
                _units(row["amount_functional"], str(row["functional_currency"]))
            ),
            txn_currency=str(row["txn_currency"]),
            functional_currency=str(row["functional_currency"]),
            dimensions={str(k): str(v) for k, v in dict(row.get("dimensions") or {}).items()},
            source_event_key=None,
            trace_node_id=str(row["trace_node_id"])
            if row.get("trace_node_id") is not None
            else NOT_PERSISTED,
        )
