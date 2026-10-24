"""Authenticate original computation files before consuming acquisition evidence."""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import computation_evidence, contract_computation, contract_version
from erev_api.files.store import open_file
from erev_api.uow import UnitOfWork
from erev_engine import upgrade
from erev_engine.bundle import InputBundle

from . import tie_outs


def load(
    uow: UnitOfWork, version_id: UUID, book: str
) -> tuple[InputBundle, dict[str, Any], dict[str, Any]]:
    source = (
        uow.session.execute(
            select(
                computation_evidence,
                contract_computation.c.input_sha256.label("version_input"),
                contract_version.c.output_sha256.label("version_output"),
            )
            .join(
                contract_version,
                contract_version.c.contract_computation_id
                == computation_evidence.c.contract_computation_id,
            )
            .join(
                contract_computation,
                contract_computation.c.id == computation_evidence.c.contract_computation_id,
            )
            .where(
                contract_version.c.id == version_id,
                contract_version.c.book_code == book,
            )
        )
        .mappings()
        .one_or_none()
    )
    if source is None:
        raise tie_outs.invalid(
            "currency_view", "Acquisition requires original computation evidence."
        )
    data = {}
    for kind in ("input", "output"):
        metadata, stream = open_file(
            uow.session, source[f"{kind}_file_id"], files=uow.files, keyring=uow.keyring
        )
        with stream:
            content = stream.read()
        digest = hashlib.sha256(content).hexdigest()
        if (
            metadata["sha256"] != digest
            or source[f"{kind}_file_sha256"] != digest
            or metadata["size_bytes"] != len(content)
            or metadata["media_type"] != "application/json"
            or metadata["purpose"] != f"COMPUTATION_{kind.upper()}"
        ):
            raise tie_outs.invalid("currency_view", "Acquisition evidence digest differs.")
        data[kind] = content
    bundle = upgrade.decode_input(data["input"])
    output = json.loads(data["output"])
    if (
        bundle.sha256() != source["input_sha256"]
        or source["version_input"] != source["input_sha256"]
        or source["output_sha256"] != source["version_output"]
        or output["input_sha256"] != source["input_sha256"]
        or output["engine_version"] != bundle.engine_version
        or hashlib.sha256(data["output"]).hexdigest() != source["version_output"]
    ):
        raise tie_outs.invalid("currency_view", "Acquisition computation identity differs.")
    return bundle, output, dict(source)
