"""CLO-10 journal line validation (03 REQ-JE-022; BUILD_SPEC CLO-10; 04 §15.2 ``unmapped-account-
role``, ``missing-fx-rate``; §15.4 ``ACCOUNT_MAPPING_MISSING``, ``FX_RATE_MISSING``; PRD ERR-46,
ERR-36; F-CLO record §25.18).

Journal generation validates every detail line before a run is written: the account exists, is
active and applies to the entity; the account's mandatory dimensions are present; currency codes
are active and the stamped functional currency agrees with the entity; a line in a
currency other than the entity's functional currency carries an FX rate that converts it — an
in-force rate (APPROVED or SUPERSEDED version) from the line's currency to the functional currency
(Codex production-20260921-1054 R4: ``ck_subledger_line__fx`` already refuses a sealed foreign-
currency line without rate ids, so the id-less branch is a defensive validation boundary, not the
database acceptance path; the admitted boundary is a rate that does not convert). A failing line
is a
``LineFinding`` naming contract, obligation, role and account; ``line_findings`` is the pure rule
over the lines and the account facts, ``validate_lines`` loads the facts. The caller fails the
generation with ``problem_of`` (422 ``unmapped-account-role`` or ``missing-fx-rate``) after writing
one exception item per finding in its own unit of work — so no journal run or line is committed
and no line is silently dropped.

Codes: ``ACCOUNT_MAPPING_MISSING`` for an account that is missing, inactive or of other entities;
``DIMENSION_MISSING_CODE`` for a mandatory dimension — raised under ``ACCOUNT_MAPPING_MISSING`` with
the dimension named until the supervisor rules a dedicated §15.4 row (record §25.18);
``FX_RATE_MISSING`` for the rate; ``JOURNAL_CURRENCY_INVALID`` for currencies.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final
from uuid import UUID

from erev_engine.currencies import ISO_4217
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    currency,
    fx_rate,
    fx_rate_set_version,
    gl_account,
    obligation,
)
from erev_api.enums import ConfigStatus
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.domain.journals.summarise import DetailLine

ACCOUNT_MAPPING_MISSING: Final = "ACCOUNT_MAPPING_MISSING"  # 04 table 15.4-A
FX_RATE_MISSING: Final = "FX_RATE_MISSING"
CURRENCY_INVALID: Final = "JOURNAL_CURRENCY_INVALID"
DIMENSION_MISSING_CODE: Final = ACCOUNT_MAPPING_MISSING  # pending a §15.4 ruling (record §25.18)
UNMAPPED_PROBLEM: Final = "unmapped-account-role"
FX_PROBLEM: Final = "missing-fx-rate"
ACCOUNT_MISSING: Final = (
    "Journal line for role {role} names no account of this workspace (account id {account})."
)
ACCOUNT_INACTIVE: Final = "Journal line for role {role} names inactive account {code}."
ACCOUNT_OTHER_ENTITY: Final = (
    "Journal line for role {role} names account {code}, which does not apply to this entity."
)
DIMENSIONS_MISSING: Final = (
    "Journal line for role {role} to account {code} lacks the mandatory dimension(s) {dimensions}."
)
RATE_MISSING: Final = (
    "Journal line for role {role} in {currency} has no FX rate to the functional currency "
    "{functional}."
)
RATE_UNUSABLE: Final = (
    "Journal line for role {role} in {currency} names FX rate {rate} ({pair}; version {status}), "
    "which is not an in-force rate from {currency} to the functional currency {functional}."
)
RATE_UNKNOWN: Final = (
    "Journal line for role {role} in {currency} names FX rate {rate}, which this workspace does "
    "not hold."
)
IN_FORCE: Final = frozenset({ConfigStatus.APPROVED.value, ConfigStatus.SUPERSEDED.value})


@dataclass(frozen=True, slots=True)
class AccountFacts:
    """What validation needs of a T-REF-13 account."""

    id: UUID
    code: str
    is_active: bool
    entity_ids: frozenset[UUID]  # empty = every entity
    required_dimensions: frozenset[str]


@dataclass(frozen=True, slots=True)
class RateFacts:
    """What validation needs of a T-REF-12 rate: its pair and its version's status."""

    id: UUID
    base_currency: str
    quote_currency: str
    version_status: str

    @property
    def in_force(self) -> bool:
        return self.version_status in IN_FORCE

    def converts(self, currency: str, functional: str) -> bool:
        return self.base_currency == currency and self.quote_currency == functional


@dataclass(frozen=True, slots=True)
class LineFinding:
    """One failing line: its code, the problem slug the generation fails with, and its names."""

    code: str
    problem: str
    line_id: UUID
    account_role: str
    account_code: str
    message: str
    contract_id: UUID | None
    obligation_id: UUID | None
    missing_dimensions: tuple[str, ...] = ()


def _finding(
    findings: list[LineFinding],
    line: DetailLine,
    code: str,
    problem: str,
    message: str,
    missing: tuple[str, ...] = (),
) -> None:
    findings.append(
        LineFinding(
            code=code,
            problem=problem,
            line_id=line.id,
            account_role=line.account_role,
            account_code=line.gl_account_code,
            message=message,
            contract_id=line.contract_id,
            obligation_id=line.obligation_id,
            missing_dimensions=missing,
        )
    )


def line_findings(
    lines: Sequence[DetailLine],
    accounts: Mapping[UUID, AccountFacts],
    *,
    entity_id: UUID,
    functional_currency: str,
    rates: Mapping[UUID, RateFacts] | None = None,
    currencies: Collection[str] | None = None,
) -> list[LineFinding]:
    """The pure rule: every finding of every line, in line order; a line may carry several.
    ``rates`` are the facts of the rates the lines name; ``None`` means the caller loaded none
    (a named rate is then taken as present — the unit-rule callers), an empty mapping means none of
    the named rates exists."""
    active_currencies = ISO_4217 if currencies is None else currencies
    findings: list[LineFinding] = []
    for line in lines:
        found = partial(_finding, findings, line)
        invalid = sorted(
            {
                code
                for code in (line.txn_currency, line.functional_currency, functional_currency)
                if code not in active_currencies
            }
        )
        if invalid:
            found(
                CURRENCY_INVALID,
                "validation-failed",
                f"Journal line for role {line.account_role} names inactive or unknown "
                f"currency code(s): {', '.join(repr(code) for code in invalid)}.",
            )
        if line.functional_currency != functional_currency:
            found(
                CURRENCY_INVALID,
                "validation-failed",
                f"Journal line for role {line.account_role} has functional currency "
                f"{line.functional_currency}; this entity requires {functional_currency}.",
            )
        account = accounts.get(line.gl_account_id)
        if account is None:
            found(
                ACCOUNT_MAPPING_MISSING,
                UNMAPPED_PROBLEM,
                ACCOUNT_MISSING.format(role=line.account_role, account=line.gl_account_id),
            )
        elif not account.is_active:
            found(
                ACCOUNT_MAPPING_MISSING,
                UNMAPPED_PROBLEM,
                ACCOUNT_INACTIVE.format(role=line.account_role, code=account.code),
            )
        elif account.entity_ids and entity_id not in account.entity_ids:
            found(
                ACCOUNT_MAPPING_MISSING,
                UNMAPPED_PROBLEM,
                ACCOUNT_OTHER_ENTITY.format(role=line.account_role, code=account.code),
            )
        else:
            missing = tuple(
                sorted(
                    code
                    for code in account.required_dimensions
                    if not str(line.dimensions.get(code) or "").strip()
                )
            )
            if missing:
                found(
                    DIMENSION_MISSING_CODE,
                    UNMAPPED_PROBLEM,
                    DIMENSIONS_MISSING.format(
                        role=line.account_role, code=account.code, dimensions=", ".join(missing)
                    ),
                    missing,
                )
        if line.txn_currency != functional_currency:
            if line.fx_rate_id is None:
                # Defensive: ck_subledger_line__fx keeps such a line out of the ledger (1054 R4).
                found(
                    FX_RATE_MISSING,
                    FX_PROBLEM,
                    RATE_MISSING.format(
                        role=line.account_role,
                        currency=line.txn_currency,
                        functional=functional_currency,
                    ),
                )
            elif rates is not None:
                rate = rates.get(line.fx_rate_id)
                if rate is None:
                    found(
                        FX_RATE_MISSING,
                        FX_PROBLEM,
                        RATE_UNKNOWN.format(
                            role=line.account_role, currency=line.txn_currency, rate=line.fx_rate_id
                        ),
                    )
                elif not (rate.in_force and rate.converts(line.txn_currency, functional_currency)):
                    found(
                        FX_RATE_MISSING,
                        FX_PROBLEM,
                        RATE_UNUSABLE.format(
                            role=line.account_role,
                            currency=line.txn_currency,
                            rate=rate.id,
                            pair=f"{rate.base_currency}->{rate.quote_currency}",
                            status=rate.version_status,
                            functional=functional_currency,
                        ),
                    )
    return findings


def problem_of(findings: Sequence[LineFinding]) -> Problem:
    """The 422 the generation fails with: the first finding's slug, every finding as an error."""
    if not findings:
        raise ValueError("problem_of needs at least one finding")
    first = findings[0]
    return Problem(
        first.problem,
        first.message,
        errors=[
            ProblemError(field=f"lines.{item.line_id}", rule_id=item.code, message=item.message)
            for item in findings
        ],
    )


class JournalValidationFailed(Exception):
    """Raised inside ``calculate`` so the run's unit of work rolls back; the task writes the
    exception items in a unit of work of their own, then re-raises ``problem``."""

    def __init__(self, findings: Sequence[LineFinding]) -> None:
        self.findings = tuple(findings)
        self.problem = problem_of(self.findings)
        super().__init__(self.problem.detail)


def account_facts(session: Session, account_ids: Sequence[UUID]) -> dict[UUID, AccountFacts]:
    if not account_ids:
        return {}
    rows = session.execute(
        select(
            gl_account.c.id,
            gl_account.c.code,
            gl_account.c.is_active,
            gl_account.c.entity_ids,
            gl_account.c.required_dimensions,
        ).where(gl_account.c.id.in_(list(set(account_ids))))
    ).all()
    return {
        UUID(str(row[0])): AccountFacts(
            id=UUID(str(row[0])),
            code=str(row[1]),
            is_active=bool(row[2]),
            entity_ids=frozenset(UUID(str(value)) for value in (row[3] or ())),
            required_dimensions=frozenset(str(value) for value in (row[4] or ())),
        )
        for row in rows
    }


def rate_facts(session: Session, rate_ids: Sequence[UUID]) -> dict[UUID, RateFacts]:
    """The pair and version status of each named T-REF-12 rate (in force = APPROVED or SUPERSEDED,
    the statuses ``contracts.bundles`` admits when stamping a line's rate)."""
    ids = list({rate_id for rate_id in rate_ids})
    if not ids:
        return {}
    rows = session.execute(
        select(
            fx_rate.c.id,
            fx_rate.c.base_currency,
            fx_rate.c.quote_currency,
            fx_rate_set_version.c.status,
        )
        .select_from(
            fx_rate.join(
                fx_rate_set_version,
                and_(
                    fx_rate_set_version.c.tenant_id == fx_rate.c.tenant_id,
                    fx_rate_set_version.c.id == fx_rate.c.fx_rate_set_version_id,
                ),
            )
        )
        .where(fx_rate.c.id.in_(ids))
    ).all()
    return {
        UUID(str(row[0])): RateFacts(
            id=UUID(str(row[0])),
            base_currency=str(row[1]).strip(),
            quote_currency=str(row[2]).strip(),
            version_status=str(row[3]),
        )
        for row in rows
    }


def validate_lines(
    session: Session, lines: Sequence[DetailLine], *, entity_id: UUID, functional_currency: str
) -> list[LineFinding]:
    """``line_findings`` over the lines' accounts and rates as stored (BUILD_SPEC CLO-10)."""
    accounts = account_facts(session, [line.gl_account_id for line in lines])
    rates = rate_facts(session, [line.fx_rate_id for line in lines if line.fx_rate_id is not None])
    codes = {functional_currency} | {
        code for line in lines for code in (line.txn_currency, line.functional_currency)
    }
    active = set(
        session.scalars(
            select(currency.c.code).where(
                currency.c.code.in_(codes), currency.c.is_active.is_(True)
            )
        )
    )
    return line_findings(
        lines,
        accounts,
        entity_id=entity_id,
        functional_currency=functional_currency,
        rates=rates,
        currencies=active,
    )


def names_of(
    session: Session, findings: Sequence[LineFinding]
) -> dict[UUID, tuple[str | None, str | None]]:
    """(contract external id, obligation key) per finding line id, for the exception items.
    The two lists are bound as one value each (``summarise.among``): the findings of a
    generation have no bound on their number."""
    from erev_api.domain.journals.summarise import among  # ``summarise`` imports this module

    contract_ids = {item.contract_id for item in findings if item.contract_id is not None}
    obligation_ids = {item.obligation_id for item in findings if item.obligation_id is not None}
    externals: dict[UUID, str] = {}
    if contract_ids:
        externals = {
            UUID(str(row[0])): str(row[1])
            for row in session.execute(
                select(contract.c.id, contract.c.external_id).where(
                    among(contract.c.id, sorted(contract_ids, key=str))
                )
            ).all()
        }
    keys: dict[UUID, str] = {}
    if obligation_ids:
        keys = {
            UUID(str(row[0])): str(row[1])
            for row in session.execute(
                select(obligation.c.id, obligation.c.obligation_key).where(
                    among(obligation.c.id, sorted(obligation_ids, key=str))
                )
            ).all()
        }
    return {
        item.line_id: (
            None if item.contract_id is None else externals.get(item.contract_id),
            None if item.obligation_id is None else keys.get(item.obligation_id),
        )
        for item in findings
    }
