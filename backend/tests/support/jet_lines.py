"""JET template check helpers (BUILD_SPEC END-11, END-12; lane ENG-C8).

``run_checkpoint`` builds one answer key's checkpoint bundle with the answer-key assembler
(DG-AK-40), runs ``erev_engine.compute`` and then the runner's close passes in order
(``runners.CLOSE_PASSES``: FX_REMEASUREMENT, CLOSE_RELEASE, NETTING_RECLASS; RCP-08) over the
intents posted so far. The readers sum the posting lines of a period per (entry kind, side, role
[, clearing purpose, counterparty]) so a check can name a template's lines by their Table 14-A
identity, read a T-CON-09 balance column or a contract-version column, and assert that every
entry balances in both currencies (S14-INV-01). No database, no clock (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
import decimal
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import cast

import erev_engine
from erev_engine.bundle import BookOutput, InputBundle, OutputBundle, PostingIntent
from erev_engine.money import DECIMAL_CONTEXT
from support import intent_totals
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load

__all__ = ["Line", "Posted", "per_year", "run_checkpoint"]

# (entry kind, side, account role, clearing purpose or "", counterparty entity or "")
Line = tuple[str, str, str, str, str]


@dataclass(frozen=True, slots=True)
class Posted:
    """One checkpoint of one key: compute, then the close passes, in ``outputs`` order."""

    key_id: str
    checkpoint: str
    book_code: str
    as_of: date
    bundle: InputBundle
    outputs: tuple[OutputBundle, ...]  # compute, FX_REMEASUREMENT, CLOSE_RELEASE, NETTING_RECLASS

    @property
    def compute(self) -> OutputBundle:
        return self.outputs[0]

    def book(self, output: OutputBundle, book_code: str | None = None) -> BookOutput:
        (book,) = [b for b in output.books if b.book_code == (book_code or self.book_code)]
        return book

    def intents(
        self,
        period: str,
        *,
        entity: str | None = None,
        book_code: str | None = None,
        outputs: Iterable[OutputBundle] | None = None,
    ) -> list[PostingIntent]:
        """The intents posted in ``period`` (and ``entity``) across the outputs."""
        found: list[PostingIntent] = []
        for output in self.outputs if outputs is None else outputs:
            for intent in self.book(output, book_code).posting_intents:
                if intent.posting_period_key != period:
                    continue
                if entity is not None and intent.entity != entity:
                    continue
                found.append(intent)
        return found

    def txn(
        self,
        period: str,
        *,
        entity: str | None = None,
        book_code: str | None = None,
        outputs: Iterable[OutputBundle] | None = None,
    ) -> dict[Line, int]:
        """Σ transaction amounts per line identity of the period's intents (zeros dropped)."""
        return self._sum(period, entity, book_code, outputs, functional=False)

    def functional(
        self, period: str, *, entity: str | None = None, book_code: str | None = None
    ) -> dict[Line, int]:
        """Σ functional amounts per line identity of the period's intents (zeros dropped)."""
        return self._sum(period, entity, book_code, None, functional=True)

    def _sum(
        self,
        period: str,
        entity: str | None,
        book_code: str | None,
        outputs: Iterable[OutputBundle] | None,
        *,
        functional: bool,
    ) -> dict[Line, int]:
        found: dict[Line, int] = {}
        for intent in self.intents(period, entity=entity, book_code=book_code, outputs=outputs):
            for line in intent.lines:
                key: Line = (
                    intent.entry_kind,
                    line.side,
                    line.account_role,
                    line.clearing_purpose or "",
                    line.counterparty_entity or "",
                )
                amount = line.amount_functional if functional else line.amount_txn
                found[key] = found.get(key, 0) + amount
        return {key: amount for key, amount in sorted(found.items()) if amount != 0}

    def balance(
        self, subject: str, period: str, column: str, *, book_code: str | None = None
    ) -> object:
        """A T-CON-09 column of the compute output's balance row, ``"<absent>"`` without one."""
        book = self.book(self.compute, book_code)
        (row,) = [b for b in book.balances if b.subject_key == subject and b.period_key == period]
        return row.columns.get(column, "<absent>")

    def version(self, column: str, *, book_code: str | None = None) -> object:
        """A T-CON-08 column of the compute output's contract version."""
        version = self.book(self.compute, book_code).contract_version
        assert version is not None
        return version.columns[column]

    def entries_balance(self, *, book_code: str | None = None) -> None:
        """S14-INV-01 / D-16: every intent of every output balances in both currencies."""
        for output in self.outputs:
            for intent in self.book(output, book_code).posting_intents:
                txn = sum(
                    (line.amount_txn if line.side == "D" else -line.amount_txn)
                    for line in intent.lines
                )
                functional = sum(
                    (line.amount_functional if line.side == "D" else -line.amount_functional)
                    for line in intent.lines
                )
                assert (txn, functional) == (0, 0), intent.entry_key


def _key_path(key_id: str) -> str:
    return f"{key_id.split('-', 1)[0].lower()}/{key_id}.yaml"


def run_checkpoint(key_id: str, name: str, *, states: Mapping[str, str] | None = None) -> Posted:
    """Compute and the three close passes for checkpoint ``name`` of ``key_id`` (single group).
    ``states`` overrides the E-04 state of the named periods for every book and entity (a
    late-placed variant of a world; S08-R-08)."""
    loaded = load(ANSWER_KEY_ROOT / _key_path(key_id))
    checkpoint = next(c for c in runners._build_checkpoint_bundles(loaded) if c.name == name)
    (bundle,) = checkpoint.bundles
    bundle = cast(InputBundle, bundle)
    if states:
        bundle = dataclasses.replace(
            bundle,
            entities=tuple(
                dataclasses.replace(
                    entity,
                    periods=tuple(
                        dataclasses.replace(
                            period,
                            states=tuple(
                                (book, states.get(period.period_key, state))
                                for book, state in period.states
                            ),
                        )
                        for period in entity.periods
                    ),
                )
                for entity in bundle.entities
            ),
        )
    outputs: list[OutputBundle] = [cast(OutputBundle, erev_engine.compute(bundle))]
    with decimal.localcontext(DECIMAL_CONTEXT):
        for pass_name in runners.CLOSE_PASSES:
            outputs.append(intent_totals.close_pass(bundle, outputs, pass_name))
    return Posted(key_id, name, checkpoint.book, checkpoint.as_of, bundle, tuple(outputs))


def per_year(lines: Mapping[str, Mapping[Line, int]], line: Line) -> dict[str, int]:
    """Σ of ``line`` per fiscal year over a mapping period key -> period lines."""
    out: dict[str, int] = {}
    for period_key, found in lines.items():
        year = period_key.split("-", 1)[0]
        out[year] = out.get(year, 0) + found.get(line, 0)
    return {year: amount for year, amount in sorted(out.items()) if amount != 0}
