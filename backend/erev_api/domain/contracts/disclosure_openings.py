"""Attach available authenticated prior-lock snapshots to the exact computation input."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import contract
from erev_api.db.session import system_entity_scope
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
                if original is None or native is None:
                    continue
                for view in native["views"]:
                    closing = view.get("obligation_closing", {})
                    if (
                        view["unit"] != f"{bundle.group.group_key}@{entity.code}"
                        or closing.get("status") != "AVAILABLE"
                        or {subject.rsplit("/", 1)[0] for subject in closing["obligations"]}
                        != names
                    ):
                        continue
                    if view["view"] == "TRANSACTION":
                        scale = 10 ** view["minor_unit"]
                        if any(
                            view["lines"][role]["CLOSING"]
                            != sum(
                                ending.rows[name].values.get(role.lower(), 0) * scale
                                for name in names
                                if name in ending.rows
                            )
                            for role in view["lines"]
                        ):
                            raise tie_outs.invalid(
                                "opening", "Native closing differs from the original lock."
                            )
                    captured.append(
                        DisclosureOpeningInput(
                            book_code=book.book_code,
                            entity=entity.code,
                            period_key=current.key,
                            view=view["view"],
                            currency=view["currency"],
                            opening_date=previous.end,
                            balances={
                                role: values["CLOSING"] for role, values in view["lines"].items()
                            },
                            obligations={
                                subject: item["liability"]
                                for subject, item in closing["obligations"].items()
                            },
                            source={
                                "lock_id": proof["lock_id"],
                                "version": native["version"],
                                "output_sha256": native["output_sha256"],
                                "source_binding_sha256": proof["source_binding_sha256"],
                            },
                        )
                    )
                if native is not None:
                    break  # One complete original same-group snapshot per entity/book.
    return replace(bundle, disclosure_openings=tuple(captured)) if captured else bundle
