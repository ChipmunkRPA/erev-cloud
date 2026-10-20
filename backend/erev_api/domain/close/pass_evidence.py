"""Immutable engine-pass evidence, stored atomically with its sealed posting.

These are the actual pass inputs/outputs, not a reconstruction from the latest
contract version. The pass name is explicit because it is outside InputBundle's
canonical hash. This internal reader does not grant access to a group's raw data.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID

from erev_engine import upgrade
from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.trace import TraceNode
from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.tables import close_pass_evidence, subledger_line, subledger_posting
from erev_api.domain.reports.fx_paid_periods import paid_origins
from erev_api.domain.reports.fx_subjects import retained_subject
from erev_api.domain.reports.liability_fx_trace import LayerDelta, PostingDelta, from_pass
from erev_api.enums import FilePurpose
from erev_api.explain.store import MAX_TRACE_BYTES, trace_document, trace_from_row
from erev_api.files.store import open_file, store_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

LINE_FIELDS = (
    "entry_no",
    "entity_id",
    "period_id",
    "origin_period_id",
    "effective_date",
    "contract_id",
    "entry_kind",
    "account_role",
    "trace_node_id",
    "subject_key",
    "txn_currency",
    "functional_currency",
    "amount_txn",
    "amount_functional",
)


def _line_values(line: Mapping[str, Any]) -> dict[str, Any]:
    values = {key: line[key] for key in LINE_FIELDS}
    for key in ("amount_txn", "amount_functional"):
        value = Decimal(values[key])
        values[key] = str(value.normalize()) if value else "0"
    return values


def capture(
    bundle: InputBundle,
    output: BookOutput,
    pass_name: str,
    lines: Sequence[Mapping[str, Any]],
    *,
    posted_lines: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    trace = output.trace
    document = {
        "format_version": 2,
        "pass_name": pass_name,
        "input_sha256": bundle.sha256(),
        "input": json.loads(upgrade.encode_input(bundle)),
        "book_output_sha256": sha256_hex(output),
        "book_output": output,
        "trace_record": {
            "format_version": trace.format_version,
            "engine_version": trace.engine_version,
            "trace_sha256": trace.sha256(),
            "root_measures": trace.root_measures,
            "trace": trace_document(trace),
        },
        "entries": sorted({int(line["entry_no"]) for line in lines}),
        "selected_lines": [_line_values(line) for line in lines],
        "posted_lines": list(posted_lines),
    }
    content = canonical_bytes(document)
    if len(content) > MAX_TRACE_BYTES:
        raise Problem(
            "eng-trace-too-large", "Close-pass evidence exceeds the retained trace limit."
        )
    return dict(json.loads(content))


def persist(
    uow: UnitOfWork,
    *,
    posting_id: UUID,
    group_id: UUID,
    document: Mapping[str, Any],
) -> None:
    stored = store_file(
        uow,
        purpose=FilePurpose.COMPUTATION_OUTPUT,
        stream=BytesIO(canonical_bytes(document)),
        original_filename="close-pass-evidence.json",
        media_type="application/json",
    )
    uow.session.execute(
        insert(close_pass_evidence).values(
            tenant_id=uow.principal.tenant_id,
            id=new_id(),
            subledger_posting_id=posting_id,
            combination_group_id=group_id,
            pass_name=document["pass_name"],
            entry_numbers=list(document["entries"]),
            file_id=stored["id"],
            document_sha256=sha256_hex(document),
            created_at=uow.now,
            created_by=uow.principal.id,
            created_by_kind=uow.principal.kind.value,
        )
    )


def read_for_line(uow: UnitOfWork, line_id: UUID) -> dict[str, Any] | None:
    """Read within the caller's line scope, validating hashes and posting identity.

    None denotes a historical posting without retained pass evidence. Callers
    must not replace it with a newer contract computation. Raw output may name
    other group members; external disclosure needs full group authorization.
    """
    session = uow.session
    line = (
        session.execute(select(subledger_line).where(subledger_line.c.id == line_id))
        .mappings()
        .one_or_none()
    )
    if line is None:
        return None
    records = session.execute(
        select(close_pass_evidence, subledger_posting.c.book_code, subledger_posting.c.posting_kind)
        .join(
            subledger_posting,
            (subledger_posting.c.tenant_id == close_pass_evidence.c.tenant_id)
            & (subledger_posting.c.id == close_pass_evidence.c.subledger_posting_id),
        )
        .where(close_pass_evidence.c.subledger_posting_id == line["subledger_posting_id"])
    ).mappings()
    matches = []
    for record in records:
        if int(line["entry_no"]) not in record["entry_numbers"]:
            continue
        meta, stream = open_file(session, record["file_id"], files=uow.files, keyring=uow.keyring)
        with stream:
            content = stream.read(MAX_TRACE_BYTES + 1)
        if (
            len(content) > MAX_TRACE_BYTES
            or meta["purpose"] != FilePurpose.COMPUTATION_OUTPUT
            or meta["media_type"] != "application/json"
            or meta["size_bytes"] != len(content)
            or meta["sha256"] != record["document_sha256"]
            or hashlib.sha256(content).hexdigest() != record["document_sha256"]
        ):
            raise ValueError("Close-pass evidence differs from its retained file/hash.")
        document = dict(json.loads(content))
        if document["entries"] != record["entry_numbers"]:
            raise ValueError("Close-pass entry index differs from its retained file.")
        selected = canonical_bytes(_line_values(dict(line)))
        if sum(canonical_bytes(item) == selected for item in document["selected_lines"]) != 1:
            raise ValueError("Close-pass selected line differs from its sealed ledger line.")
        output = document["book_output"]
        if (
            document["format_version"] not in {1, 2}
            or document["pass_name"] != record["pass_name"]
            or document["pass_name"]
            != str(getattr(record["posting_kind"], "value", record["posting_kind"]))
            or output["book_code"]
            != str(getattr(record["book_code"], "value", record["book_code"]))
            or upgrade.decode_input(canonical_bytes(document["input"])).sha256()
            != document["input_sha256"]
            or sha256_hex(output) != document["book_output_sha256"]
        ):
            raise ValueError("Close-pass input/output binding is inconsistent.")
        trace = trace_from_row({"id": record["id"], **document["trace_record"]})
        if sha256_hex(output["trace"]) != trace.sha256():
            raise ValueError("Close-pass output and retained trace differ.")
        if line["trace_node_id"] not in {node.id for node in trace.nodes}:
            raise ValueError("Close-pass line target is absent from its retained trace.")
        matches.append({"id": str(record["id"]), "sha256": record["document_sha256"], **document})
    if len(matches) > 1:
        raise ValueError("Close-pass line has ambiguous retained evidence.")
    if matches:
        return matches[0]
    from erev_api.domain.reports import command_fx_evidence

    return command_fx_evidence.read(uow, dict(line))


def liability_attribution(
    uow: UnitOfWork,
    line_id: UUID,
    *,
    owners: Mapping[str, UUID],
    paid: Sequence[LayerDelta] | None = None,
    _active: frozenset[UUID] = frozenset(),
    _cache: dict[UUID, PostingDelta] | None = None,
) -> PostingDelta | None:
    """Resolve one retained FX control line to its actual signed layer delta.

    With no explicit paid projection, recurse through the retained source-line
    population. Each historical line must still match the authorized ledger and
    have its own calculation evidence. None means missing historical evidence.
    This internal operation exposes no additional document permissions.
    """
    from erev_api.db.tables import legal_entity, period

    if line_id in _active:
        raise ValueError("Cycle in retained FX posting history.")
    cache = {} if _cache is None else _cache
    if line_id in cache:
        return cache[line_id]
    source = (
        uow.session.execute(
            select(subledger_line, legal_entity.c.code.label("entity_code"), period.c.period_key)
            .join(legal_entity, legal_entity.c.id == subledger_line.c.entity_id)
            .join(period, period.c.id == subledger_line.c.period_id)
            .where(subledger_line.c.id == line_id)
        )
        .mappings()
        .one_or_none()
    )
    if source is None:
        return None
    if source["entry_kind"] != "FX_REMEASUREMENT" or source["account_role"] != "CONTRACT_LIABILITY":
        raise ValueError("Liability FX attribution requires an FX control line.")
    document = read_for_line(uow, line_id)
    if document is None:
        return None
    trace = trace_from_row({"id": document["id"], **document["trace_record"]})
    candidates = [
        node
        for node in trace.nodes
        if node.formula_id == "post.delta.v1"
        and node.inputs
        and node.inputs[0] == source["trace_node_id"]
        and node.id.endswith(":" + source["period_key"])
        and node.currency == str(source["functional_currency"]).strip()
        and Decimal(node.value) == Decimal(source["amount_functional"])
    ]
    if len(candidates) != 1:
        raise ValueError("The retained FX line does not identify one posting delta.")
    paid_ids: tuple[UUID, ...] = ()
    evidence: tuple[tuple[UUID, str], ...] = ()
    if paid is None:
        paid, paid_ids, evidence = _paid_layers(
            uow, dict(source), document, candidates[0], owners, _active | {line_id}, cache
        )
    result = from_pass(
        document,
        delta_node_id=candidates[0].id,
        entity_code=source["entity_code"],
        owners=owners,
        paid=paid,
    )
    result = replace(
        result,
        paid_line_ids=paid_ids,
        evidence=tuple(sorted(set((*result.evidence, *evidence)), key=str)),
    )
    cache[line_id] = result
    return result


def capture_posted_lines(
    uow: UnitOfWork,
    contract_ids: Sequence[UUID],
    book_code: str,
    *,
    ledger_cutoff: int | None = None,
    revenue: bool = False,
) -> list[dict[str, Any]]:
    """Freeze the exact FX control or revenue population visible to this group's pass.

    Record identities even for lines that net to zero: they can transfer the
    attribution between layers without changing the aggregate paid amount.
    """
    from erev_api.db.tables import period, subledger_posting_seal
    from erev_api.domain.journals.subledger import POSTING_CLASSES

    origin = period.alias("fx_history_origin")
    rows = uow.session.execute(
        select(
            subledger_line,
            period.c.period_key,
            origin.c.period_key.label("origin_key"),
            subledger_posting.c.posting_kind,
        )
        .join(subledger_posting, subledger_posting.c.id == subledger_line.c.subledger_posting_id)
        .join(
            subledger_posting_seal,
            subledger_posting_seal.c.subledger_posting_id == subledger_posting.c.id,
        )
        .join(period, period.c.id == subledger_line.c.period_id)
        .outerjoin(origin, origin.c.id == subledger_line.c.origin_period_id)
        .where(
            subledger_line.c.contract_id.in_(contract_ids),
            subledger_line.c.book_code == book_code,
            subledger_line.c.entry_kind.in_(
                ("REVENUE_RECOGNITION", "INTERCOMPANY") if revenue else ("FX_REMEASUREMENT",)
            ),
            subledger_line.c.account_role == ("REVENUE" if revenue else "CONTRACT_LIABILITY"),
            *(
                (subledger_posting_seal.c.chain_seq <= ledger_cutoff,)
                if ledger_cutoff is not None
                else ()
            ),
        )
        .order_by(subledger_line.c.recorded_at, subledger_line.c.entry_no, subledger_line.c.id)
    ).mappings()
    return [
        {
            **_line_values(dict(row)),
            "id": str(row["id"]),
            "book_code": str(row["book_code"]),
            "period_key": row["period_key"],
            "origin_key": row["origin_key"],
            "reason_code": row["reason_code"],
            "posting_class": POSTING_CLASSES[str(row["posting_kind"])],
        }
        for row in rows
    ]


def _paid_layers(
    uow: UnitOfWork,
    line: Mapping[str, Any],
    document: Mapping[str, Any],
    delta: TraceNode,
    owners: Mapping[str, UUID],
    active: frozenset[UUID],
    cache: dict[UUID, PostingDelta],
) -> tuple[tuple[LayerDelta, ...], tuple[UUID, ...], tuple[tuple[UUID, str], ...]]:
    from erev_engine.trace import SourceRef

    if document["format_version"] < 2 or "posted_lines" not in document:
        raise ValueError("This historical pass did not retain its paid-line population.")
    source = delta.inputs[-1]
    if not isinstance(source, SourceRef):
        raise ValueError("FX delta has no retained paid source.")
    target_period = source.ref_id.rsplit("/", 2)[-2]
    prior_period = (
        str(delta.inputs[1]).rsplit(":", 1)[-1] if delta.params["previous"] == "true" else None
    )
    bundle = upgrade.decode_input(canonical_bytes(document["input"]))
    entity = next(item for item in bundle.entities if item.code == line["entity_code"])
    basis = delta.params["class"]
    origins = paid_origins(
        entity.periods,
        book=str(line["book_code"]),
        target=target_period,
        previous=prior_period,
        basis=basis,
    )
    subject = retained_subject(line["subject_key"], bundle, line["entity_code"])
    base = f"posting_target:{subject}/FX_REMEASUREMENT/CONTRACT_LIABILITY"
    target_subject = str(delta.inputs[0]).rsplit(":", 1)[0]
    if target_subject == base:
        split = False
    elif target_subject == base + "/" + (
        str(line["reason_code"]) if line["reason_code"] else "UNTAGGED"
    ):
        split = True
    else:
        raise ValueError("FX paid-source subject differs from the retained role key.")
    selected: list[LayerDelta] = []
    dependencies: set[UUID] = set()
    evidence: set[tuple[UUID, str]] = set()
    identities: set[UUID] = set()
    for saved in document["posted_lines"]:
        identity = UUID(saved["id"])
        if identity in identities:
            raise ValueError("Duplicate line in retained FX history.")
        identities.add(identity)
        if (
            saved["entity_id"] != str(line["entity_id"])
            or saved["book_code"] != str(line["book_code"])
            or retained_subject(saved["subject_key"], bundle, line["entity_code"]) != subject
            or saved["txn_currency"] != str(line["txn_currency"]).strip()
            or saved["functional_currency"] != str(line["functional_currency"]).strip()
            or (basis != "ALL" and saved["posting_class"] != basis)
            or (split and saved["reason_code"] != line["reason_code"])
        ):
            continue
        origin = saved["origin_key"] or saved["period_key"]
        if origin not in origins:
            continue
        if UUID(saved["contract_id"]) not in owners.values():
            raise ValueError("FX history includes a contract outside the authorized owners.")
        current = (
            uow.session.execute(select(subledger_line).where(subledger_line.c.id == identity))
            .mappings()
            .one_or_none()
        )
        if current is None or canonical_bytes(_line_values(dict(current))) != canonical_bytes(
            {key: saved[key] for key in LINE_FIELDS}
        ):
            raise ValueError("Retained paid line differs from the authorized ledger.")
        attributed = liability_attribution(
            uow, identity, owners=owners, _active=active, _cache=cache
        )
        if attributed is None:
            raise ValueError("A paid FX line lacks retained calculation evidence.")
        selected.extend(attributed.movements)
        dependencies.update((identity, *attributed.paid_line_ids))
        evidence.update(attributed.evidence)
    return tuple(selected), tuple(sorted(dependencies, key=str)), tuple(sorted(evidence, key=str))
