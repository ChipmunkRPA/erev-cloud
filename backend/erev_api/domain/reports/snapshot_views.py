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

KINDS = frozenset(
    {
        "WATERFALL",
        "BALANCE_AGING",
        "CONTRACT_BALANCES",
        "RPO",
        "CONTRACT_BALANCE_ROLLFORWARD",
        "RPO_ROLLFORWARD",
        "DISAGGREGATION",
        "COST_ROLLFORWARD",
    }
)
VIEWS = ("transaction", "functional", "reporting")
VIEW = "__erev_currency_view_v1"
META = "__erev_currency_metadata_v1"
ASSETS = "__erev_cost_assets_v1"
COST_VIEWS = (*VIEWS, *(f"asset:{view}" for view in VIEWS))


def raw(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    return list(reader.fieldnames or []), [dict(row) for row in reader]


def pack(variants: Mapping[str, engine.Encoded]) -> engine.Encoded:
    views = COST_VIEWS if set(variants) == set(COST_VIEWS) else VIEWS
    if set(variants) != set(views):
        raise ValueError("A currency snapshot requires all three bases.")
    first = variants["transaction"]
    decoded = {view: raw(variants[view].content) for view in views}
    headers = list(dict.fromkeys(h for view in views for h in decoded[view][0]))
    if first.kind not in KINDS or VIEW in headers or META in headers or ASSETS in headers:
        raise ValueError("Unsupported currency snapshot schema.")
    if views == COST_VIEWS and first.kind != "COST_ROLLFORWARD":
        raise ValueError("Asset variants require a cost dataset.")
    rows: list[dict[str, object]] = []
    for view in views:
        variant = variants[view]
        columns, items = decoded[view]
        if (
            variant.kind != first.kind
            or len(items) != variant.row_count
            or len(columns) != len(set(columns))
        ):
            raise ValueError("Currency variants have inconsistent schemas or row counts.")
        if variant.control_totals.get("currency_view", view.split(":")[-1]) != view.split(":")[-1]:
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
                        "controls": {
                            "currency_view": view.split(":")[-1],
                            **variant.control_totals,
                            **(
                                {
                                    "granularity": "asset"
                                    if view.startswith("asset:")
                                    else "category"
                                }
                                if views == COST_VIEWS
                                else {}
                            ),
                        },
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
    if views == COST_VIEWS:
        for row in rows:
            row[ASSETS] = "1"
    return engine.encode(
        engine.Dataset(
            first.kind,
            tuple(
                engine.Column(h, "text")
                for h in [*headers, VIEW, META, *([ASSETS] if views == COST_VIEWS else [])]
            ),
            tuple(rows),
        ),
        {**first.control_totals, "available_currency_views": list(VIEWS)},
    )


def select(
    content: bytes, view: str | None = None
) -> tuple[list[str], list[dict[str, str]], dict[str, Any] | None]:
    headers, rows = raw(content)
    if VIEW not in headers and META not in headers:
        if ASSETS in headers:
            raise ValueError("Incomplete cost-asset snapshot schema.")
        if view not in (None, "transaction"):
            raise ValueError(
                "This historical lock has no retained dataset for the requested currency view."
            )
        return headers, rows, None
    if len(headers) != len(set(headers)) or not {"row_key", VIEW, META} <= set(headers):
        raise ValueError("Incomplete currency snapshot header.")
    views = COST_VIEWS if ASSETS in headers else VIEWS
    if ASSETS in headers and any(row.get(ASSETS) != "1" for row in rows):
        raise ValueError("Incomplete cost-asset snapshot marker.")
    requested = view or "transaction"
    if requested not in views:
        raise ValueError("Unknown frozen currency view.")
    plain = [h for h in headers if h not in (VIEW, META, ASSETS)]
    groups: dict[str, list[dict[str, str]]] = {basis: [] for basis in views}
    metadata: dict[str, dict[str, Any]] = {}
    identities: set[str] = set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed currency snapshot row.")
        basis = row[VIEW]
        key = row["row_key"]
        if basis not in views or not key or key in identities:
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
            if record["controls"].get("currency_view") != basis.split(":")[-1]:
                raise ValueError("Currency snapshot metadata identifies another basis.")
            if views == COST_VIEWS and record["controls"].get("granularity") != (
                "asset" if basis.startswith("asset:") else "category"
            ):
                raise ValueError("Cost snapshot metadata identifies another granularity.")
            metadata[basis] = record
        else:
            prefix = f"currency:{basis}:"
            if not key.startswith(prefix) or not key[len(prefix) :]:
                raise ValueError("Invalid currency snapshot data key.")
            groups[basis].append({**{h: row[h] for h in plain}, "row_key": key[len(prefix) :]})
    if set(metadata) != set(views) or any(
        metadata[b]["row_count"] != len(groups[b]) for b in views
    ):
        raise ValueError("Currency snapshot variants are missing or incomplete.")
    for basis in views:
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
