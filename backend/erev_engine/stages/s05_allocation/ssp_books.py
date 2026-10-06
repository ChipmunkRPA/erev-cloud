"""Stage 05 SSP books: book, version and entry of a line at its pricing date.

ENGINE_SPEC S05-R-02 (book), S05-R-03 (version; POL-070 ``ssp.version_basis``), S05-R-04 (entry).
Private to stage 05. The ``SSP_ASSIGNMENT`` decision table is evaluated like S03-R-02 through the
public ``erev_engine.rules`` module. Standard library only (DG-ARC-02).

Recorded versions (S05-R-03; 05 RCP-15). The orchestrator hands back, per obligation, the versions
an earlier computation priced it from: POL-070 at OBLIGATION scope with a read-back value
``{recorded: <version key>, recorded@<event key>: <version key>, …}``. ``recorded`` is the
obligation's own pricing — its booking pricing, or its pricing in the event that adds it;
``recorded@<event key>`` is the version its weight in that modification was priced from (S06-R-11).
A caller names the pricing it makes (``Record``) and takes the version recorded for it and that
version's book: the transaction price is not reallocated for later changes in standalone selling
prices (ASC 606-10-32-43; IFRS 15.88). A pricing without a record — the first pricing of an
obligation, the weights of a modification never computed before (01-DECISIONS D-18), a correction
of the version (S06-R-26) — passes a read-back value over and resolves POL-070 below the
obligation level, as if it were absent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from erev_engine import rules
from erev_engine.bundle import ContractInput, RuleSetInput, SspEntryInput, SspVersionInput
from erev_engine.enums import SspMethod
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import RawLine
from erev_engine.stages.state import BookContext

__all__ = [
    "LATEST_APPROVED",
    "LEGACY_SSP_BOOK",
    "NAMED_VERSION",
    "RECORDED",
    "Record",
    "VersionBasis",
    "facts",
    "recorded_version",
    "select_book",
    "select_entry",
    "select_version",
    "version_basis",
]

LEGACY_SSP_BOOK: Final = "LEGACY-SKU-SSP"  # S05-R-02 (3)
LATEST_APPROVED: Final = "LATEST_APPROVED_EFFECTIVE_AT_INCEPTION"
NAMED_VERSION: Final = "NAMED_VERSION"
POLICY_CODE: Final = "ssp.version_basis"
RECORDED: Final = "recorded"  # a read-back value's member: the version of the own pricing
_RECORDED_AT: Final = RECORDED + "@"  # … of the weight in the modification event named after it
_OUTPUT: Final = "ssp_book_code"
_PARITY_PRESET: Final = "LEGACY_PARITY"


@dataclass(frozen=True, slots=True)
class Record:
    """The pricing a caller makes, by the record it reads back (S05-R-03): of obligation
    ``subject_key`` its own pricing, or with ``event_key`` its weight in that modification."""

    subject_key: str
    event_key: str | None = None


@dataclass(frozen=True, slots=True)
class VersionBasis:
    """The resolved POL-070 option and, for ``NAMED_VERSION``, the named label or version key;
    ``recorded`` when the key is the version recorded for the pricing the caller makes."""

    option: str
    named: str | None
    recorded: bool = False


def facts(st: IdentifiedState, line: RawLine) -> dict[str, object]:
    """The ``rules.FIELDS["SSP_ASSIGNMENT"]`` facts of a line (T-REF-26; S05-R-02 (1)).

    ``customer.segment`` and ``line.term_band`` are not bundle members, so they are absent and fail
    every condition on them (as at S03-R-02).
    """
    cb = st.canonical
    header = cb.contracts[line.contract_key].header
    product = cb.group.products.get(line.product_code)
    return {
        "product.code": line.product_code,
        "product.product_family": None if product is None else product.product_family,
        "bundle_parent.code": line.bundle_product_code,
        "contract.region": header.region,
        "contract.channel": header.channel,
        "customer.segment": None,
        "contract.contract_type": header.contract_type,
        "line.term_band": None,
        "contract.currency": header.transaction_currency,
        "effective_date": line.pricing_date,
    }


def _read_back(value: object) -> bool:
    """Whether a POL-070 value is the orchestrator's read-back of recorded versions."""
    return isinstance(value, Mapping) and any(
        member == RECORDED or member.startswith(_RECORDED_AT) for member in value
    )


def recorded_version(ctx: BookContext, contract_key: str, record: Record) -> str | None:
    """The version key recorded for the pricing ``record`` names; None without one."""
    value = ctx.policies.value(POLICY_CODE, contract=contract_key, obligation=record.subject_key)
    if not isinstance(value, Mapping) or not _read_back(value):
        return None
    return value.get(RECORDED if record.event_key is None else _RECORDED_AT + record.event_key)


def version_basis(ctx: BookContext, line: RawLine, *, record: Record | None = None) -> VersionBasis:
    """POL-070 for the line: the literal, or ``{option, version_key | version_label}`` of an
    approved per-obligation override (level O). ``NAMED_VERSION`` without a named member names the
    line's ``ssp_version_label``. Any other value raises ``ValueError`` (CV-45).

    ``record`` names the pricing the caller makes — every member line of a draft is priced for
    the draft's obligation. The version recorded for it, when there is one, is the answer; an
    approved override replaces the obligation's read-back value, so it wins. A caller that names
    no record, and a pricing without one, pass a read-back value over."""
    if record is not None:
        recorded = recorded_version(ctx, line.contract_key, record)
        if recorded is not None:
            return VersionBasis(NAMED_VERSION, recorded, recorded=True)
    value = ctx.policies.value(POLICY_CODE, contract=line.contract_key, obligation=line.subject_key)
    if _read_back(value):
        value = ctx.policies.value(POLICY_CODE, contract=line.contract_key)
    named: str | None = None
    if isinstance(value, str):
        option = value
    elif isinstance(value, Mapping):
        option = value.get("option", "")
        named = value.get("version_key") or value.get("version_label")
    else:
        raise ValueError(f"{POLICY_CODE} holds an unknown value shape (CV-17)")
    if option not in (LATEST_APPROVED, NAMED_VERSION):
        raise ValueError(f"{POLICY_CODE} holds an unknown option {option!r} (CV-17)")
    if option == NAMED_VERSION and named is None:
        named = line.ssp_version_label
    return VersionBasis(option, named)


def select_book(
    ctx: BookContext, st: IdentifiedState, line: RawLine, at: date, *, record: Record | None = None
) -> str | None:
    """S05-R-02: (1) the ``SSP_ASSIGNMENT`` decision at ``at``; (2) the book whose non-null scope
    members all equal the line facts, greatest count first, ties by ascending code; (3) under the
    parity preset ``LEGACY-SKU-SSP``; (4) ``None`` (the caller raises ``SSP_KEY_NOT_FOUND``).

    Scope members sit on versions, so (2) reads the version that S05-R-03 selects in each book. A
    recorded version (``record``) names its book: the rule is not evaluated again for it.
    """
    cb = st.canonical
    books = cb.ssp_books.versions
    basis = version_basis(ctx, line, record=record)
    if basis.recorded:
        return next(
            (
                code
                for code in sorted(books)
                if any(version.version_key == basis.named for version in books[code])
            ),
            None,
        )
    matched = _decision(st, line, at)
    if matched is not None:
        return matched if matched in books else None
    header = cb.contracts[line.contract_key].header
    scoped: list[tuple[int, str]] = []
    for code in sorted(books):
        version = select_version(ctx, st, line, code, at, record=record)
        if version is None:
            continue
        members = (
            (version.scope_entity_code, line.performing_entity),
            (version.scope_currency, header.transaction_currency),
            (version.scope_channel, header.channel),
            (version.scope_segment, None),
        )
        if all(value is None or value == fact for value, fact in members):
            scoped.append((-sum(value is not None for value, _ in members), code))
    if scoped:
        return min(scoped)[1]
    if ctx.tenant_preset == _PARITY_PRESET and LEGACY_SSP_BOOK in books:
        return LEGACY_SSP_BOOK
    return None


def select_version(
    ctx: BookContext,
    st: IdentifiedState,
    line: RawLine,
    book_code: str,
    at: date,
    *,
    record: Record | None = None,
) -> SspVersionInput | None:
    """S05-R-03 (POL-070; V7).

    ``LATEST_APPROVED_EFFECTIVE_AT_INCEPTION``: among versions approved at or before ``known_at``
    with ``effective_from_date ≤ at ≤ effective_to_date`` (a null bound is open), the greatest
    ``version_no``. ``NAMED_VERSION``: the greatest version whose ``legacy_version_label`` or
    ``version_key`` equals the named value. A recorded version (``record``) is the version of
    that key, whatever its dates.
    """
    cb = st.canonical
    versions = cb.ssp_books.versions.get(book_code, ())
    basis = version_basis(ctx, line, record=record)
    if basis.recorded:
        return next((version for version in versions if version.version_key == basis.named), None)
    if basis.option == NAMED_VERSION:
        named = [
            version
            for version in versions
            if basis.named is not None
            and basis.named in (version.legacy_version_label, version.version_key)
        ]
        return max(named, key=lambda version: version.version_no, default=None)
    eligible = [
        version
        for version in versions
        if version.approved_at <= cb.bundle.known_at
        and (version.effective_from_date is None or version.effective_from_date <= at)
        and (version.effective_to_date is None or at <= version.effective_to_date)
    ]
    return max(eligible, key=lambda version: version.version_no, default=None)


def select_entry(
    version: SspVersionInput, line: RawLine, header: ContractInput, currency: str
) -> SspEntryInput | None:
    """S05-R-04: entries of the line's product and stratification (``""`` when the line has none)
    whose non-null dimensions equal the facts; greatest count of non-null dimensions, then the
    entry in the transaction currency, then ascending ``entry_key``. ``formula`` never resolves."""
    facts_row = (header.region, header.channel, None, None, None)
    stratification = line.stratification or ""
    best: tuple[tuple[int, bool, str], SspEntryInput] | None = None
    for entry in version.entries:
        if entry.product_code != line.product_code or entry.stratification != stratification:
            continue
        if entry.method == SspMethod.FORMULA:
            continue
        values = (entry.region, entry.channel, entry.segment, entry.deal_size_band, entry.term_band)
        if any(v is not None and v != fact for v, fact in zip(values, facts_row, strict=True)):
            continue
        rank = (-sum(v is not None for v in values), entry.currency != currency, entry.entry_key)
        if best is None or rank < best[0]:
            best = (rank, entry)
    return None if best is None else best[1]


def _decision(st: IdentifiedState, line: RawLine, at: date) -> str | None:
    """The ``ssp_book_code`` of the best ``SSP_ASSIGNMENT`` match at ``at`` (S03-R-02 order).

    Per rule set code the greatest version with ``effective_from ≤ at < effective_to``; then the
    greatest specificity, greatest priority, ascending ``rule_key`` and ascending rule set code.
    """
    effective: dict[str, RuleSetInput] = {}
    for version in st.canonical.rule_sets.versions.get("SSP_ASSIGNMENT", ()):
        if version.effective_from <= at and (
            version.effective_to is None or at < version.effective_to
        ):
            current = effective.get(version.rule_set_code)
            if current is None or version.version_no > current.version_no:
                effective[version.rule_set_code] = version
    line_facts = facts(st, line)
    best: tuple[tuple[int, int, str, str], str] | None = None
    for code in sorted(effective):
        chosen = effective[code]
        found = rules.match(chosen, line_facts)
        if found is None:
            continue
        value = found.outputs.get(_OUTPUT)
        if not isinstance(value, str) or not value:
            raise ValueError(f"rule {found.rule_key} of {chosen.version_key} has no {_OUTPUT}")
        rank = (-found.specificity, -found.priority, found.rule_key, code)
        if best is None or rank < best[0]:
            best = (rank, value)
    return None if best is None else best[1]
