"""Stage 03 principal versus agent: conclusion, retained consideration and gross memo.

ENGINE_SPEC S03-R-09; S03-INV-05; finding ``PRINCIPAL_AGENT_NOT_ASSESSED``; formula
``pob.agent_net.v1``; trace nodes ``stated_price:<ob>:-`` (agent retained amount) and
``gross_amount_memo:<ob>:-``; 606-10-55-36 to 55-40, 606-10-32-2; POLICIES POL-030, JET-02;
03 REQ-POB-009. Private to stage 03. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import MutableSequence
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import ContractInput, JudgementInput
from erev_engine.enums import PrincipalAgent
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, largest_remainder, round_half_up, to_fraction
from erev_engine.stages.s01_canonicalize import contract_subject_key, obligation_subject_key
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import templates
from erev_engine.stages.s03_pob_builder.templates import PobDraft
from erev_engine.stages.state import BookContext, Finding
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["BASES", "FORMULA", "POLICY", "apply", "emit"]

POLICY: Final = "pob.principal_or_agent"  # POL-030, levels P and O
FORMULA: Final = "pob.agent_net.v1"
COMMISSION_RATE: Final = "COMMISSION_RATE"
FIXED_FEE: Final = "FIXED_FEE"
SUPPLIER_COST: Final = "SUPPLIER_COST"
BASES: Final = frozenset({COMMISSION_RATE, FIXED_FEE, SUPPLIER_COST})
_LEVELS: Final = frozenset({"O", "P"})
_STAGE: Final = 3


def apply(
    ctx: BookContext, st: IdentifiedState, draft: PobDraft, findings: MutableSequence[Finding]
) -> PobDraft:
    """S03-R-09 for one line.

    ``principal_agent`` = the resolved ``pob.principal_or_agent`` at level O or P, else the
    reviewed ``PRINCIPAL_AGENT`` conclusion, else the product value (L2-2-Q-3). ``NOT_ASSESSED`` on
    a contract whose latest status is not ``DRAFT`` yields ``PRINCIPAL_AGENT_NOT_ASSESSED``
    (``ERROR``).
    ``AGENT``: the retained consideration R from the reviewed record (``COMMISSION_RATE`` ρ →
    ``largest_remainder(P_minor, [ρ, 1 − ρ], [retained, supplier])[0]``; ``FIXED_FEE`` → amount;
    ``SUPPLIER_COST`` → P − amount) becomes the stated price, ``gross_amount_memo`` = P, and the
    supplier share P − R leaves the transaction price. An agent line without a reviewed basis
    raises ``ValueError`` (CV-45); R outside [0, P] raises
    ``EngineError("ENGINE_INVARIANT_VIOLATED")`` (S03-INV-05).
    """
    header = st.canonical.contracts[draft.contract_key].header
    record = _record(header, ctx.book_code, draft)
    conclusion = _resolved(ctx, st, draft)
    if conclusion is None and record is not None and record.outcome.get("conclusion"):
        conclusion = PrincipalAgent(record.outcome["conclusion"])
    if conclusion is None:
        conclusion = draft.principal_agent
    if conclusion == PrincipalAgent.NOT_ASSESSED:
        if _latest_status(st, draft.contract_key) != "DRAFT":
            detail = {
                "obligation_key": draft.obligation_key,
                "product_code": draft.product_code,
                "rule": "S03-R-09",
            }
            findings.append(
                Finding(
                    "PRINCIPAL_AGENT_NOT_ASSESSED", "ERROR", draft.subject_key, detail, _STAGE, None
                )
            )
        return dataclasses.replace(draft, principal_agent=conclusion)
    if conclusion != PrincipalAgent.AGENT:
        return dataclasses.replace(draft, principal_agent=conclusion)
    if record is None:
        raise ValueError(
            f"{draft.subject_key}: an agent line needs a reviewed PRINCIPAL_AGENT record"
        )
    basis = record.outcome.get("gross_to_net_basis")
    if basis not in BASES:
        raise ValueError(f"{record.judgement_key}: gross_to_net_basis is not a S03-R-09 basis")
    gross = draft.stated_price
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    members: dict[str, str] = {"basis": basis}
    if basis == COMMISSION_RATE:
        rate = _member(record, "rate")
        if not 0 <= rate <= 1:
            raise _invariant(draft, "the commission rate lies outside [0, 1]")
        retained_minor = largest_remainder(
            round_half_up(gross, minor_unit), [rate, 1 - rate], ["retained", "supplier"]
        )[0]
        retained = Fraction(retained_minor, scale)
        members["rate"] = format_exact(rate)
    else:
        amount = _member(record, "amount")
        retained = amount if basis == FIXED_FEE else gross - amount
        members["amount"] = format_exact(amount)
    if not 0 <= retained <= gross:
        raise _invariant(draft, "the retained consideration lies outside [0, P]")
    members.update(
        gross=format_exact(gross),
        judgement_key=record.judgement_key,
        retained=format_exact(retained),
        supplier=format_exact(gross - retained),
    )
    own = [
        dataclasses.replace(member, stated_price=retained)
        if member.subject_key == draft.subject_key
        else member
        for member in draft.members
    ]
    return dataclasses.replace(
        draft,
        principal_agent=conclusion,
        stated_price=retained,
        original_stated_price=retained,
        gross_amount_memo=gross,
        gross_to_net=MappingProxyType(dict(sorted(members.items()))),
        members=tuple(own),
        price_basis=templates.PRICE_LINE if draft.split is None else draft.price_basis,
    )


def emit(ctx: BookContext, tb: TraceBuilder, draft: PobDraft, event_key: str | None) -> None:
    """Nodes ``stated_price:<ob>:-`` (retained R) and ``gross_amount_memo:<ob>:-`` (P) (§3.4)."""
    basis = draft.gross_to_net
    gross = draft.gross_amount_memo
    if basis is None or gross is None:
        return
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    line: list[str | SourceRef] = []
    if event_key is not None:
        detail = {"line": draft.obligation_key, "value": format_exact(gross)}
        line.append(SourceRef("contract_event", event_key, detail))
    memo_id = tb.node(
        measure="gross_amount_memo",
        subject_key=draft.subject_key,
        period_key=None,
        value=round_half_up(gross, minor_unit),
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=FORMULA,
        inputs=line,
        params={"role": "gross"},
        exact=gross,
        narrative_key=FORMULA.rsplit(".v", 1)[0],
    )
    exact = (
        gross * to_fraction(basis["rate"])
        if basis["basis"] == COMMISSION_RATE
        else (draft.stated_price)
    )
    tb.node(
        measure="stated_price",
        subject_key=draft.subject_key,
        period_key=None,
        value=round_half_up(draft.stated_price, minor_unit),
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=FORMULA,
        inputs=[memo_id],
        params={"role": "retained", **basis},
        exact=exact,
        narrative_key=FORMULA.rsplit(".v", 1)[0],
    )


def _resolved(ctx: BookContext, st: IdentifiedState, draft: PobDraft) -> PrincipalAgent | None:
    """POL-030 at level O (an obligation override) or P (product or template value)."""
    try:
        resolved = ctx.policies.resolved(
            POLICY,
            contract=draft.contract_key,
            obligation=draft.subject_key,
            entity=draft.performing_entity,
        )
    except ValueError:  # no framework default and no level sets it (POLICIES §0.4)
        resolved = None
    if resolved is not None and resolved.level in _LEVELS and isinstance(resolved.value, str):
        return PrincipalAgent(resolved.value)
    product = st.canonical.group.products.get(draft.product_code)
    template = templates.template_version(st, draft.template_code, draft.line.template_date)
    for values in (
        None if product is None else product.policy_values,
        None if template is None else template.policy_values,
    ):
        literal = None if values is None else values.get(POLICY)
        if literal is not None:
            return PrincipalAgent(literal)
    return None


def _record(header: ContractInput, book_code: str, draft: PobDraft) -> JudgementInput | None:
    """The reviewed ``PRINCIPAL_AGENT`` record for the line: one naming ``obligation_key`` governs
    one naming ``product_code``; of several, the greatest ``judgement_key`` (bundle order)."""
    contract = header.external_id
    subjects = {
        contract,
        contract_subject_key(contract),
        f"{contract}/{draft.obligation_key}",
        obligation_subject_key(contract, draft.obligation_key),
    }
    by_line: JudgementInput | None = None
    by_product: JudgementInput | None = None
    for record in header.judgements:
        if (
            record.topic != "PRINCIPAL_AGENT"
            or record.subject_key not in subjects
            or record.book_code not in (None, book_code)
        ):
            continue
        key = record.outcome.get("obligation_key")
        if key == draft.obligation_key:
            by_line = record
        elif key is None and record.outcome.get("product_code") == draft.product_code:
            by_product = record
    return by_line or by_product


def _member(record: JudgementInput, name: str) -> Fraction:
    value = record.outcome.get(name)
    if value is None:
        raise ValueError(f"{record.judgement_key}: outcome member {name} is required")
    return to_fraction(value)


def _latest_status(st: IdentifiedState, contract_key: str) -> str:
    segments = st.timelines.get(contract_key, ())
    return segments[-1].status if segments else "DRAFT"


def _invariant(draft: PobDraft, message: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=draft.subject_key,
        detail={"invariant": "S03-INV-05"},
    )
