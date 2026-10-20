"""Adapt authorized, retained contract-computation evidence for FX attribution.

The immutable ledger cutoff bounds historical lines. No input or exchange rate
is rebuilt from current contract configuration. Version identity remains distinct
from a close-pass evidence row.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from erev_engine import upgrade
from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.money import minor_to_decimal
from sqlalchemy import select

from erev_api.db.tables import (
    contract,
    contract_version,
    legal_entity,
    period,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.reports import computation_sources
from erev_api.enums import PrincipalKind
from erev_api.explain.store import load_trace, trace_document
from erev_api.uow import UnitOfWork


def read(uow: UnitOfWork, line: Mapping[str, Any]) -> dict[str, Any] | None:
    from erev_api.domain.close.pass_evidence import _line_values, capture_posted_lines

    if (
        line["contract_version_id"] is None
        or line["entry_kind"] != "FX_REMEASUREMENT"
        or line["account_role"] != "CONTRACT_LIABILITY"
    ):
        return None
    version = (
        uow.session.execute(
            select(contract_version).where(contract_version.c.id == line["contract_version_id"])
        )
        .mappings()
        .one_or_none()
    )
    posting = (
        uow.session.execute(
            select(subledger_posting, subledger_posting_seal.c.chain_seq)
            .join(
                subledger_posting_seal,
                subledger_posting_seal.c.subledger_posting_id == subledger_posting.c.id,
            )
            .where(subledger_posting.c.id == line["subledger_posting_id"])
        )
        .mappings()
        .one_or_none()
    )
    if version is None or posting is None:
        raise ValueError("FX line has no retained version or sealed posting.")
    if posting["contract_computation_id"] != version["contract_computation_id"]:
        raise ValueError("FX line version differs from its posting computation.")
    source = computation_sources.read_for_report(
        uow,
        version["contract_computation_id"],
        system_snapshot=uow.principal.kind == PrincipalKind.SYSTEM,
    )
    book_code = str(line["book_code"])
    books = [book for book in source.output["books"] if book["book_code"] == book_code]
    if len(books) != 1 or int(posting["chain_seq"]) <= source.ledger_cutoff[book_code]:
        raise ValueError("FX posting does not follow its retained input ledger cutoff.")
    book = books[0]
    trace = load_trace(uow.session, version["id"])
    if trace is None or sha256_hex(book["trace"]) != trace.sha256():
        raise ValueError("FX computation output differs from its retained version trace.")
    entity_code = uow.session.execute(
        select(legal_entity.c.code).where(legal_entity.c.id == line["entity_id"])
    ).scalar_one()
    period_key = uow.session.execute(
        select(period.c.period_key).where(period.c.id == line["period_id"])
    ).scalar_one()
    origin_key = (
        None
        if line["origin_period_id"] is None
        else uow.session.execute(
            select(period.c.period_key).where(period.c.id == line["origin_period_id"])
        ).scalar_one()
    )
    matches = []
    for intent in book["posting_intents"]:
        if (
            intent["entity"] != entity_code
            or intent["book_code"] != book_code
            or intent["subject_key"] != line["subject_key"]
            or intent["entry_kind"] != str(line["entry_kind"])
            or intent["posting_period_key"] != period_key
            or intent["origin_period_key"] != origin_key
            or intent["reason_code"] != line["reason_code"]
        ):
            continue
        for candidate in intent["lines"]:
            if candidate["side"] not in {"D", "C"}:
                raise ValueError("Retained FX intent has an invalid side.")
            sign = 1 if candidate["side"] == "D" else -1
            if (
                candidate["trace_node_id"] == line["trace_node_id"]
                and candidate["account_role"] == str(line["account_role"])
                and candidate["txn_currency"] == str(line["txn_currency"]).strip()
                and candidate["functional_currency"] == str(line["functional_currency"]).strip()
                and all(
                    sign
                    * minor_to_decimal(
                        candidate[name], source.bundle.currencies[candidate[currency]].minor_unit
                    )
                    == Decimal(line[name])
                    for name, currency in (
                        ("amount_txn", "txn_currency"),
                        ("amount_functional", "functional_currency"),
                    )
                )
            ):
                matches.append(candidate)
    if len(matches) != 1:
        raise ValueError("FX ledger line does not identify one retained computation intent.")
    members = (
        uow.session.execute(
            select(contract.c.id).where(
                contract.c.external_id.in_(source.bundle.group.member_contract_keys)
            )
        )
        .scalars()
        .all()
    )
    document = {
        "format_version": 2,
        "source_kind": "CONTRACT_VERSION",
        "id": str(version["id"]),
        "sha256": source.output_sha256,
        "pass_name": source.bundle.trigger,
        "input": json.loads(upgrade.encode_input(source.bundle)),
        "input_sha256": source.bundle.sha256(),
        "book_output": book,
        "book_output_sha256": sha256_hex(book),
        "trace_record": {
            "format_version": trace.format_version,
            "engine_version": trace.engine_version,
            "trace_sha256": trace.sha256(),
            "root_measures": trace.root_measures,
            "trace": trace_document(trace),
        },
        "entries": [int(line["entry_no"])],
        "selected_lines": [_line_values(line)],
        "posted_lines": capture_posted_lines(
            uow, members, book_code, ledger_cutoff=source.ledger_cutoff[book_code]
        ),
    }

    # Match persisted close envelopes: UUIDs and dates use canonical JSON values.
    return dict(json.loads(canonical_bytes(document)))
