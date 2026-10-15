"""Retain and reconstruct confirmed opening-balance choices for promotion reproduction."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any
from uuid import UUID

from erev_engine.bundle import InputBundle, MaterialRightInput
from erev_engine.canonical import sha256_hex

from erev_api.domain.contracts.bundles import engine_payload
from erev_api.domain.migration import capture, field_mapping, opening_balances
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.events.payloads import payload_json
from erev_api.problems import Problem, ProblemError


def _refuse(message: str) -> Problem:
    return Problem(
        "invalid-transition",
        message,
        errors=[
            ProblemError(field="migration_id", rule_id="MIGRATION_OPENING_PLAN", message=message)
        ],
    )


def _staging_digest(staging: opening_balances.Staging) -> str:
    return sha256_hex(
        [
            {
                "booking": opening_balances.booking_payload(contract),
                "opening": opening_balances.opening_payload(contract, staging.cutover_date),
                "options": opening_balances.option_records(contract),
            }
            for contract in staging.contracts
        ]
    )


def record(
    staging: opening_balances.Staging,
    parameters: field_mapping.BatchParameters,
    entity_codes: Mapping[str, str],
) -> dict[str, Any]:
    body = {
        "version": 1,
        "batch_parameters": parameters.as_mapping(),
        "entity_mapping": dict(sorted(entity_codes.items())),
        "staging_sha256": _staging_digest(staging),
    }
    return {**body, "sha256": sha256_hex(body)}


def restore(
    rows: Iterable[LegacyRow], cutover: date, document: Mapping[str, Any] | None
) -> opening_balances.Staging:
    """Require a complete retained choice set; never fall back to today's defaults."""
    from erev_api.domain.migration.jobs import batch_parameters

    if (
        not isinstance(document, Mapping)
        or set(document)
        != {"version", "batch_parameters", "entity_mapping", "staging_sha256", "sha256"}
        or type(document.get("version")) is not int
        or document.get("version") != 1
    ):
        raise _refuse(
            "The import has no supported confirmed opening plan; re-import before promotion."
        )
    body = {key: value for key, value in document.items() if key != "sha256"}
    try:
        digest = sha256_hex(body)
    except (TypeError, ValueError) as error:
        raise _refuse("The confirmed opening plan has an invalid representation.") from error
    if digest != document["sha256"]:
        raise _refuse("The confirmed opening plan does not match its retained hash.")
    values = document["batch_parameters"]
    entities = document["entity_mapping"]
    if not isinstance(values, Mapping) or set(values) != set(
        field_mapping.BatchParameters().as_mapping()
    ):
        raise _refuse("The confirmed opening plan has an incomplete parameter set.")
    if not isinstance(entities, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in entities.items()
    ):
        raise _refuse("The confirmed opening plan has an invalid entity mapping.")
    staging = opening_balances.stage(rows, cutover, batch_parameters(values), entity_codes=entities)
    if _staging_digest(staging) != document["staging_sha256"]:
        raise _refuse("The retained source no longer reproduces the confirmed opening plan.")
    return staging


def verify_inputs(
    staging: opening_balances.Staging,
    batch: Mapping[str, Any],
    verified_bundles: Iterable[InputBundle],
) -> None:
    """Match reconstructed booking/opening/option facts to the verified producing input.

    This is not output reproduction or approval. Callers must separately check current policy,
    activation, configurations and the recomputed accounting result before live promotion.
    """
    bundles = tuple(verified_bundles)
    expected_keys = {contract.external_id for contract in staging.contracts}
    actual_keys = [header.external_id for bundle in bundles for header in bundle.contracts]
    if len(actual_keys) != len(expected_keys) or set(actual_keys) != expected_keys:
        raise _refuse("The opening plan and captured contract population differ.")
    for contract in staging.contracts:
        bundle, header = next(
            (bundle, header)
            for bundle in bundles
            for header in bundle.contracts
            if header.external_id == contract.external_id
        )
        if header.customer_code != f"{capture.CUSTOMER_PREFIX}{contract.external_id}":
            raise _refuse("The captured customer does not match the migration's customer identity.")
        booked = [
            event
            for event in bundle.events
            if event.contract_key == contract.external_id and event.event_type == "CONTRACT_BOOKED"
        ]
        openings = [
            event
            for event in bundle.events
            if event.contract_key == contract.external_id
            and event.event_type == "OPENING_BALANCE_ESTABLISHED"
        ]
        if len(booked) != 1 or len(openings) != 1:
            raise _refuse(
                "The capture must contain one booking and opening event per planned contract."
            )
        if (
            booked[0].effective_date != contract.inception_date
            or openings[0].effective_date
            != capture.opening_effective_date(contract, staging.cutover_date)
            or booked[0].origin != "MIGRATION"
            or openings[0].origin != "MIGRATION"
        ):
            raise _refuse("The captured event dates or origins do not match the opening plan.")
        try:
            customer_id = UUID(str(booked[0].payload.get("customer_id")))
        except ValueError as error:
            raise _refuse("The captured booking has no customer identity.") from error
        booking = capture.booking_body(
            contract, batch=batch, currency=header.transaction_currency, customer_id=customer_id
        )
        opening = capture.opening_body(contract, batch=batch, currency=header.transaction_currency)
        for expected, actual in ((booking, booked[0]), (opening, openings[0])):
            if sha256_hex(engine_payload(payload_json(expected))) != sha256_hex(actual.payload):
                raise _refuse(
                    f"The confirmed facts of {contract.external_id} differ from captured input."
                )
        options = tuple(
            MaterialRightInput(
                obligation_key=row.mapped.obligation_key,
                option_type="OTHER",
                incremental_discount_ratio=None,
                is_discount_available_without_contract=False,
                expected_purchase_amount=None,
                currency=header.transaction_currency,
                ssp_method="ENTERED_AMOUNT",
                expiry_date=None,
                likelihood_estimate_key=None,
                is_legacy_quantity_ssp_dollars=False,
                entered_ssp_amount=row.mapped.option.option_ssp,
            )
            for row in contract.rows
            if row.mapped.option is not None
        )
        if sorted(options, key=lambda right: right.obligation_key) != sorted(
            header.material_rights, key=lambda right: right.obligation_key
        ):
            raise _refuse(
                f"The confirmed option terms of {contract.external_id} differ from captured input."
            )
