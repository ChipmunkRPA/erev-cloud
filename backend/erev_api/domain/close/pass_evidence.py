"""Immutable engine-pass evidence, stored atomically with its sealed posting.

These are the actual pass inputs/outputs, not a reconstruction from the latest
contract version. The pass name is explicit because it is outside InputBundle's
canonical hash. This internal reader does not grant access to a group's raw data.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID

from erev_engine import upgrade
from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.tables import close_pass_evidence, subledger_line, subledger_posting
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
) -> dict[str, Any]:
    trace = output.trace
    document = {
        "format_version": 1,
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
            document["format_version"] != 1
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
    return matches[0] if matches else None


def liability_attribution(
    uow: UnitOfWork,
    line_id: UUID,
    *,
    owners: Mapping[str, UUID],
    paid: Sequence[LayerDelta],
) -> PostingDelta | None:
    """Resolve one retained FX control line to its actual signed layer delta.

    Paid layers are supplied by an authorized historical-ledger reader, never
    inferred from their net amount. None means missing historical evidence.
    This internal operation exposes no additional document permissions.
    """
    from erev_api.db.tables import legal_entity, period

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
    return from_pass(
        document,
        delta_node_id=candidates[0].id,
        entity_code=source["entity_code"],
        owners=owners,
        paid=paid,
    )
