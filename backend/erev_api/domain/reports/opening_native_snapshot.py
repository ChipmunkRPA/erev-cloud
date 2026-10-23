"""Read native closing evidence only from an already authenticated lock-time version."""

import hashlib
import json
from typing import Any

from sqlalchemy import select

from erev_api.db.tables import computation_evidence, contract_version
from erev_api.files.store import open_file
from erev_api.uow import UnitOfWork

from . import tie_outs


def read(
    uow: UnitOfWork, row: tie_outs.BalanceRow, period: tie_outs.PeriodRef, book: str
) -> dict[str, Any] | None:
    version = (
        uow.session.execute(
            select(contract_version).where(
                contract_version.c.id == row.version_id,
                contract_version.c.book_code == book,
            )
        )
        .mappings()
        .one_or_none()
    )
    if version is None:
        raise tie_outs.invalid("currency_view", "Original snapshot version is unavailable.")
    evidence = (
        uow.session.execute(
            select(computation_evidence).where(
                computation_evidence.c.contract_computation_id == version["contract_computation_id"]
            )
        )
        .mappings()
        .one_or_none()
    )
    if evidence is None:
        return None  # Historical computation without typed evidence; never backfill it.
    if evidence["output_sha256"] != version["output_sha256"]:
        raise tie_outs.invalid("currency_view", "Original snapshot output identity differs.")
    metadata, stream = open_file(
        uow.session, evidence["output_file_id"], files=uow.files, keyring=uow.keyring
    )
    with stream:
        content = stream.read()
    digest = hashlib.sha256(content).hexdigest()
    if any(
        value != digest
        for value in (evidence["output_sha256"], evidence["output_file_sha256"], metadata["sha256"])
    ):
        raise tie_outs.invalid("currency_view", "Original snapshot file digest differs.")
    output = json.loads(content)
    if output["input_sha256"] != evidence["input_sha256"]:
        raise tie_outs.invalid("currency_view", "Original snapshot input identity differs.")
    books = [item for item in output["books"] if item["book_code"] == book]
    if len(books) != 1:
        raise tie_outs.invalid("currency_view", "Original snapshot book population differs.")
    snapshots = [
        item
        for item in books[0].get("disclosure_rollforwards", [])
        if item["entity"] == row.entity_code and item["period_key"] == period.key
    ]
    if not snapshots:
        return None  # The original computation need not have ended in this report period.
    seen = set()
    for item in snapshots:
        key = item["view"]
        if (
            key in seen
            or key not in {"TRANSACTION", "FUNCTIONAL"}
            or item["closing_date"] != period.end.isoformat()
            or item["minor_unit"] != tie_outs.minor_unit(item["currency"])
            or (key == "TRANSACTION" and item["currency"] != row.currency)
            or item["unit"] != f"{books[0]['contract_version']['subject_key']}@{row.entity_code}"
        ):
            raise tie_outs.invalid(
                "currency_view", "Original snapshot period or currency is ambiguous."
            )
        seen.add(key)
        if item["opening_basis"] not in {"RESTATED", "FROZEN"}:
            raise tie_outs.invalid("currency_view", "Unknown native snapshot calculation basis.")
    return {
        "version": str(row.version_id),
        "computation_id": str(version["contract_computation_id"]),
        "output_file_id": str(evidence["output_file_id"]),
        "output_sha256": digest,
        "period_key": period.key,
        "closing_date": period.end.isoformat(),
        "views": snapshots,
    }
