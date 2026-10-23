"""Cost-event coverage for explicit EAC scopes, using authenticated combination identities."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, obligation
from erev_api.domain.contracts import combined_components, queries
from erev_api.explain import store as trace_store
from erev_api.problems import Problem, ProblemError


def _invalid(message: str) -> Problem:
    return Problem(
        "validation-failed",
        message,
        errors=[
            ProblemError(
                field="parameters.eac_scope",
                rule_id="COMBINED_EAC_SCOPE",
                message=message,
            )
        ],
    )


def keys(
    session: Session, element: Mapping[str, Any], parameters: Mapping[str, Any]
) -> frozenset[str | None] | None:
    """None is the historical whole-contract filter; an explicit scope never guesses it."""
    scope = parameters.get("eac_scope")
    named_ids = set(element.get("target_obligation_ids") or ()) if scope else set()
    if element["obligation_id"] is not None:
        named_ids.add(element["obligation_id"])
    rows = session.execute(
        select(obligation.c.id, obligation.c.obligation_key).where(
            obligation.c.contract_id == element["contract_id"]
        )
    ).all()
    by_id = {UUID(str(row.id)): str(row.obligation_key) for row in rows}
    ids = {UUID(str(value)) for value in named_ids}
    if not ids <= by_id.keys():
        raise _invalid("The EAC names an obligation outside its contract.")
    named = frozenset(by_id[value] for value in ids)
    if scope is None:
        return named or None
    if scope == "MEMBERS":
        if not named:
            raise _invalid("Name the original members covered by this EAC.")
        return named | {None} if named == frozenset(by_id.values()) else named
    if scope != "COMBINATION":
        raise _invalid("Choose MEMBERS or COMBINATION for EAC coverage.")
    current = (
        session.execute(select(contract).where(contract.c.id == element["contract_id"]))
        .mappings()
        .one()
    )
    version = queries.version_at(
        session, dict(current), book_code=queries.primary_book(session), known_at=None
    )
    trace = None if version is None else trace_store.load_trace(session, UUID(str(version["id"])))
    groups = {
        frozenset(members)
        for key in by_id.values()
        if (members := combined_components.keys(trace, str(current["external_id"]), key))
    }
    candidates = [
        group
        for group in groups
        if (named and named <= group) or (not named and group == frozenset(by_id.values()))
    ]
    if len(candidates) != 1:
        raise _invalid(
            "Compute the reviewed combination and name its host or members "
            "before using whole-combination EAC coverage."
        )
    selected = candidates[0]
    return selected | {None} if selected == frozenset(by_id.values()) else selected
