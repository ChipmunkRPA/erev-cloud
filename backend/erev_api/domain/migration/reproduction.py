"""Reproduce complete opening outputs without retaining temporary contracts or audits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from erev_engine.bundle import OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError, PrincipalAgentInputError
from erev_engine.upgrade import decode_input

from erev_api.domain.contracts import computation
from erev_api.domain.migration import activation_review, capture, opening_balances, repository
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork


def _refuse(message: str) -> Problem:
    return Problem(
        "invalid-transition",
        message,
        errors=[
            ProblemError(field="migration_id", rule_id="MIGRATION_REPRODUCTION", message=message)
        ],
    )


def result_digest(output: OutputBundle) -> str:
    """Include every output field except the input identity hash.

    Fresh booking has new database identities and a new observation time. Its input hash is
    checked by retained-input replay; no book, trace, schedule, posting or diagnostic is
    omitted here.
    """
    return sha256_hex(replace(output, input_sha256=""))


def verify(
    uow: UnitOfWork,
    batch: Mapping[str, Any],
    staging: opening_balances.Staging,
    captures: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Replay retained input, then rebook against live configuration inside a savepoint.

    This is preflight, not activation admission or approval. A future promotion command must
    hold its lifecycle/configuration locks and enforce those separate gates before commit.
    """
    run = computation.default_engine()
    expected: dict[str, str] = {}
    for row in captures:
        bundle = repository.verify_input_evidence(row)
        if len(bundle.contracts) != 1:
            raise _refuse("Opening reproduction requires one captured contract per computation.")
        key = bundle.contracts[0].external_id
        if key in expected:
            raise _refuse("The captured reproduction population contains a duplicate contract.")
        try:
            output = run(bundle)
        except PrincipalAgentInputError as error:
            raise _refuse(f"Retained agent assessment inputs are incomplete for {key}.") from error
        except EngineError as error:
            raise _refuse(f"Retained output replay failed for {key}: {error.code}.") from error
        if output.sha256() != str(row["output_sha256"]):
            raise _refuse(f"The current engine does not reproduce the retained output of {key}.")
        expected[key] = result_digest(output)
    keys = [item.external_id for item in staging.contracts]
    if len(keys) != len(expected) or set(keys) != set(expected):
        raise _refuse("The reproduction plan and retained output population differ.")
    reviewed: dict[str, dict[str, Any]] = {}
    child = capture.migration_unit(uow)
    savepoint = child.session.begin_nested()
    try:
        for contract in staging.contracts:
            applied = capture.platform_applier.apply(child, batch=batch, contract=contract)
            try:
                fresh_input = decode_input(applied.input_evidence)
                fresh = run(fresh_input)
            except PrincipalAgentInputError as error:
                raise _refuse(
                    f"Fresh agent assessment inputs are incomplete for {contract.external_id}."
                ) from error
            except EngineError as error:
                raise _refuse(
                    f"Fresh output replay failed for {contract.external_id}: {error.code}."
                ) from error
            if result_digest(fresh) != expected[contract.external_id]:
                raise _refuse(
                    "Current configuration does not reproduce all outputs of "
                    f"{contract.external_id}."
                )
            reviewed[contract.external_id] = {
                "output_sha256": expected[contract.external_id],
                "activation": activation_review.preview(fresh_input, contract.external_id),
            }
    finally:
        savepoint.rollback()
        child.drain_audit_events()
    return reviewed
