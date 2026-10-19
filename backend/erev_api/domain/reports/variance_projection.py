"""Fixed-period revenue and balance projection for the variance DRY_RUN worker.

Revenue is posted basis plus signed posting intents in the selected posting period,
as in the stage 15 waterfall; schedules are not recognized revenue. Balances are the
engine's period-end rows. All values retain contract and currency identity and are
converted from integer minor units exactly. RPO uses the shared dated disclosure
reader and retained exemption policies rather than an allocation-minus-revenue approximation.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Final, Literal

from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s01_canonicalize.convert import contract_key_from_subject

from erev_api.problems import Problem

from . import variance_rpo
from .variance_measures import MeasureKey

MEASURES: Final = frozenset({"REVENUE", "CONTRACT_LIABILITY", "CONTRACT_ASSET_AND_UNBILLED", "RPO"})


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Close variance projection: {detail}")


@dataclass(frozen=True)
class Projection:
    """Server-owned scope and posted basis, held constant across the replay steps."""

    basis: InputBundle
    entity_code: str
    book_code: str
    period_key: str
    currency_view: Literal["transaction", "functional"] = "transaction"

    def __post_init__(self) -> None:
        if self.currency_view not in {"transaction", "functional"}:
            raise _refuse("choose transaction or functional currency.")
        books = [book for book in self.basis.books if book.book_code == self.book_code]
        entities = [entity for entity in self.basis.entities if entity.code == self.entity_code]
        if len(books) != 1 or len(entities) != 1:
            raise _refuse("the source has no unique selected book/entity.")
        if self.entity_code not in books[0].entity_codes:
            raise _refuse("the entity does not participate in the selected book.")
        if len([p for p in entities[0].periods if p.period_key == self.period_key]) != 1:
            raise _refuse("the source calendar has no unique selected period.")

    def __call__(self, output: OutputBundle) -> dict[MeasureKey, Fraction]:
        if output.engine_version != self.basis.engine_version:
            raise _refuse("the output runtime differs from the source.")
        books = [book for book in output.books if book.book_code == self.book_code]
        if len(books) != 1:
            raise _refuse("the output has no unique selected book.")
        book = books[0]
        contracts = {contract.external_id: contract for contract in self.basis.contracts}
        if len(contracts) != len(self.basis.contracts):
            raise _refuse("the source contract identities are duplicated.")
        entity = next(e for e in self.basis.entities if e.code == self.entity_code)
        result: dict[MeasureKey, Fraction] = {}

        def add(contract: str, currency: str, measure: str, value: object) -> None:
            if type(value) is not int:
                raise _refuse("an engine money value is not integer minor units.")
            if contract not in contracts:
                raise _refuse("a monetary source names a contract outside the input bundle.")
            expected = (
                entity.functional_currency
                if self.currency_view == "functional"
                else contracts[contract].transaction_currency
            )
            if currency != expected or currency not in self.basis.currencies:
                raise _refuse("a monetary source has an inconsistent or unknown currency.")
            amount = Fraction(value, 10 ** self.basis.currencies[currency].minor_unit)
            key = MeasureKey(contract, currency, measure)
            result[key] = result.get(key, Fraction(0)) + amount

        suffix = "txn" if self.currency_view == "transaction" else "functional"
        currency_field = "txn_currency" if suffix == "txn" else "functional_currency"
        seen = set()
        expected_subjects = {
            contract_entity_subject_key(key, self.entity_code): key for key in contracts
        }
        for row in book.balances:
            if (
                row.period_key == self.period_key
                and row.subject_key in expected_subjects
                and row.columns.get("entity") != self.entity_code
            ):
                raise _refuse("a balance entity differs from its subject identity.")
            if row.period_key != self.period_key or row.columns.get("entity") != self.entity_code:
                continue
            contract = expected_subjects.get(row.subject_key)
            if contract is None or row.subject_key in seen:
                raise _refuse("a balance has an unknown or duplicated contract identity.")
            seen.add(row.subject_key)
            currency = str(row.columns.get(currency_field, ""))
            add(
                contract,
                currency,
                "CONTRACT_LIABILITY",
                row.columns.get(f"contract_liability_{suffix}"),
            )
            for column in ("contract_asset", "unbilled_receivable"):
                add(
                    contract,
                    currency,
                    "CONTRACT_ASSET_AND_UNBILLED",
                    row.columns.get(f"{column}_{suffix}"),
                )

        obligations = {row.subject_key for row in book.obligation_versions}
        if len(obligations) != len(book.obligation_versions):
            raise _refuse("the output obligation identities are duplicated.")

        def revenue(subject: str, currency: str, value: int) -> None:
            if subject not in obligations:
                raise _refuse("revenue has no matching output obligation; it cannot be attributed.")
            add(contract_key_from_subject(subject), currency, "REVENUE", value)

        for posted in self.basis.posted:
            if (
                posted.book_code == self.book_code
                and posted.entity_code == self.entity_code
                and posted.period_key == self.period_key
                and posted.account_role == "REVENUE"
            ):
                value = posted.amount_txn if suffix == "txn" else posted.amount_functional
                if type(value) is not int:
                    raise _refuse("posted revenue is not integer minor units.")
                currency = posted.txn_currency if suffix == "txn" else posted.functional_currency
                revenue(posted.subject_key, currency, -value)  # ledger input is debit-positive
        for intent in book.posting_intents:
            if (
                intent.book_code != self.book_code
                or intent.entity != self.entity_code
                or intent.posting_period_key != self.period_key
            ):
                continue
            for line in intent.lines:
                if line.account_role != "REVENUE":
                    continue
                if line.side not in {"D", "C"}:
                    raise _refuse("a revenue intent has an unknown debit/credit side.")
                value = line.amount_txn if suffix == "txn" else line.amount_functional
                if type(value) is not int or value < 0:
                    raise _refuse("a revenue intent must carry nonnegative integer minor units.")
                currency = line.txn_currency if suffix == "txn" else line.functional_currency
                revenue(intent.subject_key, currency, value if line.side == "C" else -value)
        result.update(
            variance_rpo.project(
                self.basis,
                book,
                entity_code=self.entity_code,
                period_key=self.period_key,
                functional=self.currency_view == "functional",
            )
        )
        return result
