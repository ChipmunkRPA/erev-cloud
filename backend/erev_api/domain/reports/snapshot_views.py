"""Currency variants within one immutable, manifest-hashed machine CSV.

Metadata rows authenticate each variant's controls, including empty variants.
Legacy CSVs remain readable on their original default basis.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping
from typing import Any

from erev_engine.canonical import canonical_bytes
from erev_engine.stages.s15_disclosures import snapshots as engine

KINDS = frozenset({"WATERFALL", "CONTRACT_BALANCES", "RPO"})
VIEWS = ("transaction", "functional", "reporting")
VIEW = "__erev_currency_view_v1"
META = "__erev_currency_metadata_v1"


def raw(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    return list(reader.fieldnames or []), [dict(row) for row in reader]


def pack(variants: Mapping[str, engine.Encoded]) -> engine.Encoded:
    if set(variants) != set(VIEWS):
        raise ValueError("A currency snapshot requires all three bases.")
    first = variants["transaction"]
    decoded = {view: raw(variants[view].content) for view in VIEWS}
    headers = list(dict.fromkeys(h for view in VIEWS for h in decoded[view][0]))
    if first.kind not in KINDS or VIEW in headers or META in headers:
        raise ValueError("Unsupported currency snapshot schema.")
    rows: list[dict[str, object]] = []
    for view in VIEWS:
        variant = variants[view]
        columns, items = decoded[view]
        if (
            variant.kind != first.kind
            or len(items) != variant.row_count
            or len(columns) != len(set(columns))
        ):
            raise ValueError("Currency variants have inconsistent schemas or row counts.")
        if variant.control_totals.get("currency_view", view) != view:
            raise ValueError("Currency snapshot controls identify another basis.")
        prefix = f"currency:{view}:"
        rows.append(
            {
                **dict.fromkeys(headers, ""),
                "row_key": f"currency:{view}",
                VIEW: view,
                META: canonical_bytes(
                    {
                        "row_count": len(items),
                        "columns": columns,
                        "controls": {"currency_view": view, **variant.control_totals},
                    }
                ).decode(),
            }
        )
        rows.extend(
            {
                **dict.fromkeys(headers, ""),
                **row,
                "row_key": prefix + row["row_key"],
                VIEW: view,
                META: "",
            }
            for row in items
        )
    return engine.encode(
        engine.Dataset(
            first.kind, tuple(engine.Column(h, "text") for h in [*headers, VIEW, META]), tuple(rows)
        ),
        {**first.control_totals, "available_currency_views": list(VIEWS)},
    )


def select(
    content: bytes, view: str | None = None
) -> tuple[list[str], list[dict[str, str]], dict[str, Any] | None]:
    headers, rows = raw(content)
    if VIEW not in headers and META not in headers:
        if view not in (None, "transaction"):
            raise ValueError(
                "This historical lock has no retained dataset for the requested currency view."
            )
        return headers, rows, None
    if len(headers) != len(set(headers)) or not {"row_key", VIEW, META} <= set(headers):
        raise ValueError("Incomplete currency snapshot header.")
    requested = view or "transaction"
    if requested not in VIEWS:
        raise ValueError("Unknown frozen currency view.")
    plain = [h for h in headers if h not in (VIEW, META)]
    groups: dict[str, list[dict[str, str]]] = {basis: [] for basis in VIEWS}
    metadata: dict[str, dict[str, Any]] = {}
    identities: set[str] = set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed currency snapshot row.")
        basis = row[VIEW]
        key = row["row_key"]
        if basis not in VIEWS or not key or key in identities:
            raise ValueError("Unknown or duplicate currency snapshot identity.")
        identities.add(key)
        if row[META]:
            if (
                key != f"currency:{basis}"
                or basis in metadata
                or any(row[h] for h in plain if h != "row_key")
            ):
                raise ValueError("Invalid currency snapshot metadata row.")
            record = json.loads(row[META])
            if (
                not isinstance(record, dict)
                or type(record.get("row_count")) is not int
                or not isinstance(record.get("controls"), dict)
            ):
                raise ValueError("Invalid currency snapshot controls.")
            if record["controls"].get("currency_view") != basis:
                raise ValueError("Currency snapshot metadata identifies another basis.")
            metadata[basis] = record
        else:
            prefix = f"currency:{basis}:"
            if not key.startswith(prefix) or not key[len(prefix) :]:
                raise ValueError("Invalid currency snapshot data key.")
            groups[basis].append({**{h: row[h] for h in plain}, "row_key": key[len(prefix) :]})
    if set(metadata) != set(VIEWS) or any(
        metadata[b]["row_count"] != len(groups[b]) for b in VIEWS
    ):
        raise ValueError("Currency snapshot variants are missing or incomplete.")
    for basis in VIEWS:
        columns = metadata[basis].get("columns")
        if (
            not isinstance(columns, list)
            or not columns
            or columns[0] != "row_key"
            or any(not isinstance(h, str) for h in columns)
            or len(columns) != len(set(columns))
            or not set(columns) <= set(plain)
        ):
            raise ValueError("Invalid currency snapshot column schema.")
        if any(row[h] for row in groups[basis] for h in plain if h not in columns):
            raise ValueError("Currency snapshot row contains undeclared values.")
    selected = metadata[requested]["columns"]
    return (
        selected,
        [{h: row[h] for h in selected} for row in groups[requested]],
        metadata[requested]["controls"],
    )
