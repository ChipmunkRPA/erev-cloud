"""POB opening sources come from the authenticated lock-time balance report binding."""

from typing import Any
from dataclasses import dataclass
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select

from erev_api.db.tables import report_run
from erev_api.domain.reports import disclosure_frozen, tie_outs
from erev_api.domain.reports.builders import ADAPTER, ReportParams, SourceBinding
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class FrozenSources:
    balances: dict[UUID, tie_outs.BalanceRow]
    facts: dict[str, Any]


class Reader:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.cache: dict[tuple[UUID, UUID, str], FrozenSources] = {}

    def read(
        self,
        *,
        row: tie_outs.BalanceRow,
        previous: tie_outs.PeriodRef,
        locked: tie_outs.LockedEnd,
        book: str,
    ) -> tuple[tie_outs.BalanceRow | None, dict[str, Any]]:
        key = (locked.lock_id, row.entity_id, book)
        if key not in self.cache:
            self.cache[key] = _sources(
                self.uow, row=row, previous=previous, locked=locked, book=book
            )
        sources = self.cache[key]
        found = sources.balances.get(row.contract_id)
        held = locked.rows.get(row.external_id)
        if (found is None) != (held is None) or (
            found is not None
            and held is not None
            and (
                found.currency != held.currency
                or any(
                    found.value(name) != held.values.get(name, tie_outs.ZERO)
                    for name in tie_outs.ROLLFORWARD_BALANCES
                )
            )
        ):
            raise tie_outs.invalid(
                "currency_view", "Original obligation sources do not tie to the opening lock."
            )
        return found, {**sources.facts, "version": None if found is None else str(found.version_id)}


def _sources(
    uow: UnitOfWork,
    *,
    row: tie_outs.BalanceRow,
    previous: tie_outs.PeriodRef,
    locked: tie_outs.LockedEnd,
    book: str,
) -> FrozenSources:
    origins = list(
        uow.session.execute(
            select(report_run).where(
                report_run.c.tenant_id == uow.principal.tenant_id,
                report_run.c.period_lock_id == locked.lock_id,
                report_run.c.report_code == "disclosure_pack",
                report_run.c.job_id.is_(None),
                report_run.c.status == "SUCCEEDED",
            )
        ).mappings()
    )
    if len(origins) != 1:
        raise tie_outs.invalid(
            "currency_view", "The opening lock lacks original disclosure sources."
        )
    frozen = disclosure_frozen.read(uow.session, dict(origins[0]))
    children = [
        child for child in frozen.pack.children if child.source.key == "contract_balances:PERIOD"
    ]
    if len(children) != 1:
        raise tie_outs.invalid("currency_view", "The opening lock lacks its balance source report.")
    child = children[0]
    source = (
        uow.session.execute(
            select(report_run).where(
                report_run.c.tenant_id == uow.principal.tenant_id,
                report_run.c.id == child.source.run_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if source is None or any(
        (
            source["status"] != "SUCCEEDED",
            source["report_code"] != "contract_balances",
            source["known_at"] != locked.frozen_at,
            source["entity_ids"] != [row.entity_id],
            source["book_code"] != book,
            source["output_sha256"] != child.output_sha256,
            source["parameters"] != child.run["parameters"],
        )
    ):
        raise tie_outs.invalid("currency_view", "The frozen opening source report differs.")
    binding = SourceBinding.from_stored(source["source_binding"])
    if (
        binding is None
        or binding.cutoff != locked.frozen_at
        or not binding.versions.get(book)
        or binding.strategy != ADAPTER
        or binding.report_version != 1
        or binding.open
        or binding.dataset is None
        or binding.dataset.get("output_sha256") != child.output_sha256
    ):
        raise tie_outs.invalid("currency_view", "The frozen opening source versions are missing.")
    params = ReportParams(
        "contract_balances",
        1,
        source["parameters"],
        (row.entity_id,),
        locked.frozen_at,
        book_code=book,
        historical=True,
        binding=binding,
    )
    # Rebuild from exactly the original versions, never a current version selected at an old date.
    balances = tie_outs.balances_at(
        uow.session,
        entity_ids=(row.entity_id,),
        book_code=book,
        period_keys={row.entity_id: previous},
        cutoff=locked.frozen_at,
        params=params,
    )
    return FrozenSources(
        {item.contract_id: item for item in balances},
        {
            "lock_id": str(locked.lock_id),
            "source_run_id": str(child.source.run_id),
            "source_output_sha256": child.output_sha256,
            "source_binding_sha256": sha256_hex(source["source_binding"]),
        },
    )
