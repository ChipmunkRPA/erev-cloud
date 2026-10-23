"""Attach available authenticated prior-lock snapshots to the exact computation input."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.session import system_entity_scope
from erev_api.db.tables import contract
from erev_api.domain.reports import locked_ends, opening_relief_frozen, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.uow import UnitOfWork
from erev_engine.bundle import DisclosureOpeningInput, InputBundle


def prepare(uow: UnitOfWork, bundle: InputBundle) -> InputBundle:
    with system_entity_scope(uow.session):
        return _prepare(uow, bundle)


def _prepare(uow: UnitOfWork, bundle: InputBundle) -> InputBundle:
    if bundle.disclosure_openings is not None:
        return bundle  # Replayed inputs never consult current lock state.
    members = list(
        uow.session.execute(
            select(contract.c.id, contract.c.external_id, contract.c.contracting_entity_id).where(
                contract.c.external_id.in_(bundle.group.member_contract_keys)
            )
        ).all()
    )
    entities = tie_outs.entities(uow.session, sorted({row[2] for row in members}))
    calendars = tie_outs.calendars(uow.session, entities)
    as_of = max([bundle.group.inception_date, *(event.effective_date for event in bundle.events)])
    captured = []
    for book in bundle.books:
        if book.book_code == "LEGACY":
            continue
        for entity in entities:
            if entity.code not in book.entity_codes:
                continue
            periods = calendars[entity.id].periods
            current = next((p for p in periods if p.start <= as_of <= p.end), None)
            previous = next(
                (
                    p
                    for p in periods
                    if current is not None and p.end == current.start - timedelta(days=1)
                ),
                None,
            )
            if current is None or previous is None:
                continue
            params = ReportParams(
                "contract_balance_rollforward",
                1,
                {},
                (entity.id,),
                bundle.known_at,
                book_code=book.book_code,
                historical=True,
            )
            locked = locked_ends.Reader(
                uow,
                params,
                book_code=book.book_code,
                cutoff=bundle.known_at,
                entity_codes={entity.id: entity.code},
            )
            ending = locked.at(entity.id, previous)
            if ending is None:
                continue
            reader = opening_relief_frozen.Reader(uow, params)
            names = {row[1] for row in members if row[2] == entity.id}
            snapshots = {}
            for identity, external, owner in members:
                if owner != entity.id:
                    continue
                probe = tie_outs.BalanceRow(
                    identity,
                    external,
                    None,
                    entity.id,
                    entity.code,
                    bundle.group.transaction_currency,
                    UUID(int=0),
                )
                original, proof = reader.read(
                    row=probe, previous=previous, locked=ending, book=book.book_code
                )
                native = proof.get("native_closing")
                if original is not None and native is not None:
                    snapshots[native["version"]] = (native, proof)
            captured.extend(
                complete_openings(
                    list(snapshots.values()),
                    names,
                    ending.rows,
                    book_code=book.book_code,
                    entity=entity.code,
                    period_key=current.key,
                    opening_date=previous.end,
                )
            )
    return replace(bundle, disclosure_openings=tuple(captured)) if captured else bundle


def complete_openings(
    snapshots: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    names: set[str],
    locked_rows: Mapping[str, Any],
    *,
    book_code: str,
    entity: str,
    period_key: str,
    opening_date: date,
) -> list[DisclosureOpeningInput]:
    """Union only complete, disjoint original groups; never apportion a historic group."""
    result = []
    for view_name in ("TRANSACTION", "FUNCTIONAL"):
        covered: set[str] = set()
        balances: dict[str, int] = {}
        obligations: dict[str, int] = {}
        sources = []
        denomination = None
        for native, proof in sorted(snapshots, key=lambda item: item[0]["version"]):
            views = [view for view in native["views"] if view["view"] == view_name]
            if len(views) != 1:
                break
            view = views[0]
            closing = view.get("obligation_closing", {})
            if closing.get("status") != "AVAILABLE":
                break
            original_names = {subject.rsplit("/", 1)[0] for subject in closing["obligations"]}
            current_denomination = (view["currency"], view["minor_unit"])
            if (
                not original_names
                or not original_names <= names
                or original_names & covered
                or (denomination is not None and denomination != current_denomination)
                or (balances and set(balances) != set(view["lines"]))
            ):
                break
            if view_name == "TRANSACTION":
                scale = 10 ** view["minor_unit"]
                if not original_names <= locked_rows.keys() or any(
                    view["lines"][role]["CLOSING"]
                    != sum(
                        locked_rows[name].values.get(role.lower(), 0) * scale
                        for name in original_names
                    )
                    for role in view["lines"]
                ):
                    raise tie_outs.invalid(
                        "opening", "Native closing differs from the original lock."
                    )
            denomination = current_denomination
            covered.update(original_names)
            for role, values in view["lines"].items():
                balances[role] = balances.get(role, 0) + values["CLOSING"]
            obligations.update(
                {subject: item["liability"] for subject, item in closing["obligations"].items()}
            )
            sources.append(
                {
                    "lock_id": proof["lock_id"],
                    "version": native["version"],
                    "output_sha256": native["output_sha256"],
                    "source_binding_sha256": proof["source_binding_sha256"],
                }
            )
        else:
            if covered != names or denomination is None or not sources:
                continue
            if len(sources) == 1:
                source = sources[0]
            else:
                if len({item["lock_id"] for item in sources}) != 1:
                    continue
                encoded = json.dumps(sources, sort_keys=True, separators=(",", ":"))
                source = {
                    "lock_id": sources[0]["lock_id"],
                    "sources_json": encoded,
                    "source_set_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
                }
            result.append(
                DisclosureOpeningInput(
                    book_code=book_code,
                    entity=entity,
                    period_key=period_key,
                    view=view_name,
                    currency=denomination[0],
                    opening_date=opening_date,
                    balances=balances,
                    obligations=obligations,
                    source=source,
                )
            )
    return result
