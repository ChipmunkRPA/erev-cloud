"""Calculation trace store (dev-guide §5.16 DG-KRN-EXP-05; 04 T-ENG-03; BUILD_SPEC CTR-2).

One ``calc_trace`` row per ``contract_version``. The ``trace`` column holds the 04 document
``{"nodes": [...]}``: each node with ``id``, ``measure``, ``value``, ``currency``, ``formula_id``,
``inputs`` (``{"node": id}`` or ``{"ref_type", "ref_id", "detail"}``), ``params``,
``rounding_residue`` and ``narrative_key``. ``format_version``, ``engine_version`` and
``root_measures`` are columns of their own, and ``trace_sha256`` is ``Trace.sha256()`` of the
engine's trace (the canonical JSON of the dataclass), so ``load_trace`` rebuilds the same object and
checks the hash before returning it. A trace whose canonical JSON exceeds 64 MiB is refused with
``eng-trace-too-large`` (05 RCP-20).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from erev_engine.trace import SourceRef, SourceRefType, Trace, TraceNode
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from erev_api.db.tables import calc_trace
from erev_api.problems import Problem

__all__ = [
    "MAX_TRACE_BYTES",
    "TraceIntegrityError",
    "insert_trace",
    "load_trace",
    "trace_document",
    "trace_from_row",
]

MAX_TRACE_BYTES: Final = 64 * 1024 * 1024  # T-ENG-03: 64 MiB


class TraceIntegrityError(ValueError):
    """A stored trace whose rebuilt ``Trace.sha256()`` differs from ``trace_sha256``."""


def _node_document(node: TraceNode) -> dict[str, Any]:
    inputs: list[dict[str, Any]] = []
    for item in node.inputs:
        if isinstance(item, str):
            inputs.append({"node": item})
        else:
            inputs.append(
                {"ref_type": item.ref_type, "ref_id": item.ref_id, "detail": dict(item.detail)}
            )
    return {
        "id": node.id,
        "measure": node.measure,
        "value": node.value,
        "currency": node.currency,
        "formula_id": node.formula_id,
        "inputs": inputs,
        "params": dict(node.params),
        "rounding_residue": node.rounding_residue,
        "narrative_key": node.narrative_key,
    }


def trace_document(trace: Trace) -> dict[str, Any]:
    """The T-ENG-03 ``trace`` document of ``trace``, nodes in id order."""
    return {"nodes": [_node_document(node) for node in trace.nodes]}


def _node(document: Mapping[str, Any]) -> TraceNode:
    inputs: list[str | SourceRef] = []
    for item in document["inputs"]:
        if "node" in item:
            inputs.append(str(item["node"]))
        else:
            ref_type = cast(SourceRefType, str(item["ref_type"]))
            detail = {str(key): str(value) for key, value in dict(item["detail"]).items()}
            inputs.append(SourceRef(ref_type, str(item["ref_id"]), detail))
    currency = document["currency"]
    residue = document["rounding_residue"]
    return TraceNode(
        id=str(document["id"]),
        measure=str(document["measure"]),
        value=str(document["value"]),
        currency=None if currency is None else str(currency),
        formula_id=str(document["formula_id"]),
        inputs=tuple(inputs),
        params={str(key): str(value) for key, value in sorted(dict(document["params"]).items())},
        rounding_residue=None if residue is None else str(residue),
        narrative_key=str(document["narrative_key"]),
    )


def trace_from_row(row: Mapping[str, Any]) -> Trace:
    """The ``Trace`` of a stored ``calc_trace`` row; ``TraceIntegrityError`` when its hash differs
    (DG-KRN-EXP-05)."""
    trace = Trace(
        format_version=int(row["format_version"]),
        engine_version=str(row["engine_version"]),
        nodes=tuple(_node(item) for item in row["trace"]["nodes"]),
        root_measures={
            str(key): str(value) for key, value in sorted(dict(row["root_measures"]).items())
        },
    )
    if trace.sha256() != row["trace_sha256"]:
        raise TraceIntegrityError(f"calc_trace {row['id']} does not match its trace_sha256")
    return trace


def insert_trace(
    session: Session,
    *,
    values: Mapping[str, Any],
    contract_version_id: UUID,
    combination_group_id: UUID,
    book_code: str,
    trace: Trace,
) -> dict[str, Any]:
    """Insert the ``calc_trace`` row of one contract version; ``values`` carries ``tenant_id``,
    ``id`` and SC-C. 422 ``eng-trace-too-large`` above 64 MiB of canonical JSON."""
    size = len(canonical_bytes(trace))
    if size > MAX_TRACE_BYTES:
        raise Problem(
            "eng-trace-too-large",
            f"The calculation trace holds {size} bytes; the limit is {MAX_TRACE_BYTES}.",
        )
    row = {
        **values,
        "contract_version_id": contract_version_id,
        "combination_group_id": combination_group_id,
        "book_code": book_code,
        "format_version": trace.format_version,
        "engine_version": trace.engine_version,
        "trace_sha256": trace.sha256(),
        "node_count": len(trace.nodes),
        "root_measures": dict(trace.root_measures),
        "trace": trace_document(trace),
    }
    session.execute(insert(calc_trace).values(**row))
    return row


def load_trace(session: Session, contract_version_id: UUID) -> Trace | None:
    """The stored trace of a contract version in the session's tenant, or None."""
    row = (
        session.execute(
            select(calc_trace).where(calc_trace.c.contract_version_id == contract_version_id)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else trace_from_row(dict(row))
