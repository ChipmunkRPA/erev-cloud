"""What a close run read beside its contracts, and whether it is still what is in force (item
CLO-RATE-AFTER-RUN-1; the supervisor's ruling of 2026-10-02 08:56 on the lane's pre-build line; 04
T-CLS-01 "What a run read" and §16.8 "The close-run gate", rev 1.291; revision 0127).

A period-end pass builds one bundle per contract group at the step's record-time cutoff, and a
bundle takes from the tenant's reference data what that cutoff admits: every exchange rate of the
group's currencies in force at it and, for each period, the value of every period-pinned policy
parameter. Neither marked a group when it was published: a closing rate corrected after a
period's close run left every gate ``PASSED`` and the period locked on the earlier
remeasurement, where a second run would have posted the difference (measured before the item).
Since 04 rev 1.297 (item FX-REPUBLISH-DIRTY-1) the approval of a rate version marks the groups
its changed rates reach (``close.rate_reach``); a registry version marks none, and the gate of
this module asks nothing of a list of groups.

So the run's first period-end step READS FIRST, in its transaction, what its passes can read —
``read`` — and stores it on the run as two digests (T-CLS-01 ``rates_read``, ``registry_read``);
the gate ``CLOSE_RUN_COMPLETED`` reads a succeeded run as out of date while the same read differs
now (``close.gates``). Read first: a version that commits while the step runs is one the digest
does not hold, whatever some group's bundle read of it, and the gate then asks for a run.

Never a time. A version's ``published_at`` is the application instant of its approval's unit of
work — its START. An approval that began before the step and committed after it is "published
before" by every clock stored, and the step did not read it. The other way round as well: a
gate evaluated in a transaction that began before an approval's instant, or on a clock behind
it, would not admit by ``published_at`` a version that is committed and in force for every later
reader — a lock decision that waited for that approval is such a transaction. So the gate's read
— ``standing`` — takes the rates in force whenever their version was published; the step's read
keeps its cutoff, which is what its passes can read. A version the step's cutoff left out is
then one more thing the run did not read, and the gate asks for a run.

The rates by VALUE: set, rate type, pair, date and rate of every rate in force dated on or
before the period's last day — the rows ``contracts.bundles.fx_rates_in_force`` admits, the
statement a bundle reads its rates through — for the whole tenant. Not by version: a version
that extends a set's coverage repeats the earlier rates and asks for nothing. Every date through
the period's last day, since stage 12 runs a unit's FX book from its inception and a pass posts
cumulative target minus posted. For the whole tenant, so that the read does not depend on which
groups a step lists; its price: a correction that moves nothing for this entity costs one run
that posts nothing.

The registry by VALUE as well, and for the RUN'S PERIOD (third row of rev 1.291, with item
PINP-PERIOD-VALUE-1): the period-pinned parameters (``registry.resolve.PERIOD_PINNED``, derived
from the catalogue's pin ``P``) as a bundle hands them to that period — per legal entity, the
value in force at the earlier of the cutoff and the period's last instant in the entity's time
zone, among the versions published by the cutoff (``period_values``: ``registry.known_versions``
once, ``registry.resolve_among`` per entity, ``bundles.period_end_instant`` — the reads of
``bundles._period_rows``). By value, because a category is published as a whole set: a version
that changes a contract-pinned parameter beside them, or a setting of another category, asks for
nothing. For the period: a value that takes effect after the period's last instant is not the
period's, no pass of the period reads it, and it asks for nothing; one that takes effect inside
a period whose run was made before that asks for a run. An earlier period's value is settled —
no version takes effect at a past instant (04 §16.5) — and a later period's is its own run's.
Every legal entity, because a pass over a group that another entity contracts or performs reads
that entity's row; each at the run's last day in its own time zone.

Contract exceptions are included by effective value as well (October 7 continuation). The
same period-scoped reader used by calculation bundles supplies approved POL-163 exceptions,
including superseded rows for historical cutoffs. Only exceptions that differ from the entity
default enter the digest. Drafts, same-value successors, approvals after the entity-local period
end and framework-forced IFRS treatment leave it unchanged. An approval in the period that
changes a value asks for another close run, even when the amount in this particular run is zero.

Both reads run under the tenant's SYSTEM entity scope (supervisor ruling R-42 (d)): what a
control reads must not depend on who reads it, and a version at the level of an entity is a row
of that entity (T-PLT-32 is RLS-TE).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Select, Text, cast, func, literal, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from erev_api.db.session import system_entity_scope
from erev_api.db.tables import contract, fx_rate, legal_entity, policy_override
from erev_api.domain.contracts import bundles, policy_inputs
from erev_api.enums import BookCode
from erev_api.registry import resolve as registry

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.domain.close.gates import PeriodScope

__all__ = [
    "POLICIES",
    "RATES",
    "RunInputs",
    "changed",
    "period_values",
    "rates_statement",
    "read",
    "standing",
]

# What the gate names as changed (SCREENS_B §1.1 gate label table, rev 1.100).
RATES: Final = "exchange rates"
POLICIES: Final = "policies"


@dataclass(frozen=True, slots=True)
class RunInputs:
    """The two digests of what a period-end pass can read at one cutoff."""

    rates: str
    registry: str


def rates_statement(cutoff: datetime | None, through: date) -> Select[Any]:
    """One statement: the SHA-256, in hex, of the rates in force at ``cutoff`` dated on or before
    ``through`` — the rows of ``bundles.fx_rates_in_force``, each as set code, rate type, base,
    quote, date and rate, in that order. The version a rate comes from is not part of it.
    ``cutoff`` None: the rates in force whenever their version was published."""
    admitted = (
        bundles.fx_rates_in_force(cutoff)
        .where(fx_rate.c.effective_date <= through)
        .subquery("admitted")
    )
    row = func.concat_ws(
        "|",
        admitted.c.code,
        cast(admitted.c.rate_type, Text),
        func.trim(admitted.c.base_currency),
        func.trim(admitted.c.quote_currency),
        cast(admitted.c.effective_date, Text),
        cast(admitted.c.rate, Text),
    )
    listed = func.string_agg(row, aggregate_order_by(literal("\n"), row))
    return select(
        func.encode(func.sha256(func.convert_to(func.coalesce(listed, ""), "UTF8")), "hex")
    )


def period_values(
    session: Session, scope: PeriodScope, cutoff: datetime
) -> dict[UUID, dict[str, Any]]:
    """The value of every period-pinned parameter for the period of ``scope``, per legal entity
    of the tenant, as a bundle built at ``cutoff`` hands it to that period
    (``bundles._period_rows``): among the versions published at or before the cutoff
    (``registry.known_versions``, one statement), the value in force for the entity at the
    earlier of the cutoff and the period's last instant in the entity's time zone
    (``bundles.period_end_instant``, ``registry.resolve_among``). Two statements, whatever the
    number of entities."""
    known = registry.known_versions(session, known_at=cutoff)
    entities = session.execute(
        select(legal_entity.c.id, legal_entity.c.time_zone).order_by(legal_entity.c.id)
    ).all()
    book_code = BookCode(scope.book_code)
    found: dict[UUID, dict[str, Any]] = {}
    for entity_id, time_zone in entities:
        at = min(cutoff, bundles.period_end_instant(scope.end_date, str(time_zone)))
        found[UUID(str(entity_id))] = {
            code: registry.resolve_among(
                known, code, book_code=book_code, entity_id=UUID(str(entity_id)), at=at
            ).value
            for code in registry.PERIOD_PINNED
        }
    return found


def _registry_digest(values: dict[UUID, dict[str, Any]], own: UUID) -> str:
    """The digest of ``period_values``: the values of the run's own entity, then, per other
    entity that resolves some parameter otherwise, what it resolves otherwise. An entity that
    resolves every parameter as the run's entity does is not part of it, so a new entity, or a
    version of an entity that changes none of them, leaves the digest as it was."""
    base = values[own]
    apart = {
        str(entity_id): {
            code: value for code, value in sorted(found.items()) if value != base[code]
        }
        for entity_id, found in values.items()
        if entity_id != own
    }
    canonical = json.dumps(
        [base, {entity: found for entity, found in sorted(apart.items()) if found}],
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _contract_period_values(
    session: Session,
    scope: PeriodScope,
    cutoff: datetime,
    defaults: dict[UUID, dict[str, Any]],
) -> dict[str, Any]:
    """Effective contract exceptions by value, using the calculation reader's cutoffs.

    Read all tenant contracts, like the entity defaults, so the digest is independent of
    the caller's entity permissions or a close step's changing group population. A
    same-value successor, an unapproved row or an exception after period end changes nothing.
    """
    rows = (
        session.execute(
            select(
                policy_override,
                contract.c.external_id.label("contract_key"),
                legal_entity.c.id.label("owner_entity_id"),
                legal_entity.c.code.label("entity_code"),
                legal_entity.c.time_zone,
            )
            .join(
                contract,
                (contract.c.tenant_id == policy_override.c.tenant_id)
                & (contract.c.id == policy_override.c.contract_id),
            )
            .join(
                legal_entity,
                (legal_entity.c.tenant_id == contract.c.tenant_id)
                & (legal_entity.c.id == contract.c.contracting_entity_id),
            )
            .where(
                policy_override.c.policy_key == "fx.cl_historical_layering",
                policy_override.c.status.in_(("APPROVED", "SUPERSEDED")),
                policy_override.c.approved_at <= cutoff,
            )
        )
        .mappings()
        .all()
    )
    contracts = {
        UUID(str(row["contract_id"])): (str(row["contract_key"]), str(row["entity_code"]))
        for row in rows
    }
    entities = {
        str(row["entity_code"]): (UUID(str(row["owner_entity_id"])), str(row["time_zone"]))
        for row in rows
    }
    resolved = policy_inputs.period_scoped_inputs(
        [dict(row) for row in rows],
        book_code=scope.book_code,
        contracts=contracts,
        period_cutoffs=[
            (code, scope.period_key, bundles.period_end_instant(scope.end_date, zone))
            for code, (_, zone) in sorted(entities.items())
        ],
        known_at=cutoff,
    )
    found: dict[str, Any] = {}
    for item in resolved:
        # The key uses the same unambiguous contract/entity/period identity as the bundle.
        _, entity_code, _ = json.loads(item.subject_key)
        entity_id, _ = entities[entity_code]
        if item.value != defaults[entity_id][item.code]:
            found[item.subject_key] = item.value
    return found


def read(
    session: Session, scope: PeriodScope, known_at: datetime, *, whenever_published: bool = False
) -> RunInputs:
    """What a period-end pass of ``scope`` can read at ``known_at`` (module
    docstring): what the run's first period-end step records. The cutoff is the bundle's — the
    later of ``known_at`` and the transaction timestamp. With ``whenever_published`` the rates
    are those in force whenever their version was published: the gate's read (``standing``)."""
    cutoff = bundles.record_cutoff(session, known_at)
    with system_entity_scope(session):
        rates = session.execute(
            rates_statement(None if whenever_published else cutoff, scope.end_date)
        ).scalar_one()
        values = period_values(session, scope, cutoff)
        exceptions = _contract_period_values(session, scope, cutoff, values)
    digest = _registry_digest(values, scope.entity_id)
    if exceptions:
        canonical = json.dumps([digest, exceptions], sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return RunInputs(rates=str(rates), registry=digest)


def standing(session: Session, scope: PeriodScope, known_at: datetime) -> RunInputs:
    """The same read as the gate makes it, to compare with what a run recorded (module docstring,
    "Never a time"): the rates in force whenever their version was published, and the policy
    values of the period as a bundle built now would hand them to it — a registry version is in
    force over an effective range, and one that takes effect after the period's last instant
    changes nothing a pass of the period reads."""
    return read(session, scope, known_at, whenever_published=True)


def changed(recorded: RunInputs, now: RunInputs) -> tuple[str, ...]:
    """What differs between what a run recorded and the same read now, as the gate names it."""
    return tuple(
        name
        for name, before, after in (
            (RATES, recorded.rates, now.rates),
            (POLICIES, recorded.registry, now.registry),
        )
        if before != after
    )
