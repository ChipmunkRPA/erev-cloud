"""Stage 03 material rights: option records, option SSP and expiry triggers.

ENGINE_SPEC S03-R-07; S03-INV-04; CV-27 (RCP-10); formula ``pob.option_ssp.v1`` and trace node
``option_ssp:<ob>:-``; POLICIES ALG-05 §2.6.1 (CHK-054), POL-026, POL-029. Private to stage 03.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, MutableSequence, Sequence
from datetime import date, timedelta
from fractions import Fraction
from typing import Final

from erev_engine.bundle import ContractInput, EstimateVersionInput, MaterialRightInput, TimeTrigger
from erev_engine.dates import add_months
from erev_engine.enums import ObligationKind, RecognitionMethod
from erev_engine.money import format_exact, round_half_up, to_fraction
from erev_engine.stages.s01_canonicalize import contract_subject_key, obligation_subject_key
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import bundles
from erev_engine.stages.s03_pob_builder.templates import PobDraft
from erev_engine.stages.state import BookContext, Finding
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "DISCOUNT_X_LIKELIHOOD",
    "ENTERED_AMOUNT",
    "EXPIRY_TRIGGER",
    "FORMULA",
    "NOT_MATERIAL",
    "RENEWAL_ALTERNATIVE",
    "build",
    "emit",
    "not_material",
    "terms_of",
    "triggers",
]

DISCOUNT_X_LIKELIHOOD: Final = "DISCOUNT_X_LIKELIHOOD"
RENEWAL_ALTERNATIVE: Final = "RENEWAL_ALTERNATIVE"
ENTERED_AMOUNT: Final = "ENTERED_AMOUNT"
EXPIRY_TRIGGER: Final = "MATERIAL_RIGHT_EXPIRY"  # CV-27: the only trigger kind in 1.0
NOT_MATERIAL: Final = "NOT_MATERIAL"  # 606-10-55-43: an incremental discount of 0
FORMULA: Final = "pob.option_ssp.v1"
UPFRONT_FEE_POLICY: Final = "upfront_fee.recognition_period"  # POL-029
EXPECTED_BENEFIT_PERIOD: Final = "EXPECTED_BENEFIT_PERIOD"
RENEWAL_OPTION: Final = "RENEWAL_OPTION"  # E-92
_CLOSING_EVENTS: Final = frozenset({"MATERIAL_RIGHT_EXERCISED", "MATERIAL_RIGHT_EXPIRED"})
_STAGE: Final = 3


def terms_of(header: ContractInput, obligation_key: str) -> MaterialRightInput | None:
    """The T-CON-14 option record of an obligation of the contract, or ``None``."""
    return next(
        (right for right in header.material_rights if right.obligation_key == obligation_key),
        None,
    )


def build(
    ctx: BookContext, st: IdentifiedState, draft: PobDraft, findings: MutableSequence[Finding]
) -> PobDraft | None:
    """S03-R-07 for one line: the option record and option SSP at the pricing date.

    ``DISCOUNT_X_LIKELIHOOD``: SSP_opt = ``expected_purchase_amount`` ×
    ``incremental_discount_ratio`` × L, with L the ``rate`` of the ``EXERCISE_LIKELIHOOD`` pin at
    the pricing date. L outside
    [0, 1] or a negative ratio yields ``NON_FINITE_AMOUNT`` (``ERROR``); a ratio of 0 is not a
    material right, so the line creates no obligation (``None``). ``RENEWAL_ALTERNATIVE``: no option
    SSP; the expected renewal line keeps its template terms and SSP entry with the option record
    (606-10-55-45; ALG-05 §2.6.1). ``ENTERED_AMOUNT``: the SSP entry's point at quantity (or
    the range midpoint), and the obligation is units-delivered; an entry that stage 03 cannot read
    leaves the option SSP to stage 05. A line without an option record keeps its template terms
    (L2-2-Q-1). A missing member or pin raises ``ValueError`` (CV-45).
    """
    if draft.obligation_kind != ObligationKind.MATERIAL_RIGHT:
        return draft
    header = st.canonical.contracts[draft.contract_key].header
    terms = terms_of(header, draft.obligation_key)
    if terms is None:
        return draft
    method = terms.ssp_method
    if method == RENEWAL_ALTERNATIVE:
        # ALG-05 §2.6.1: the contract includes the expected renewals, so the renewal line the
        # preparer books stays an obligation with its own SSP entry; no option SSP (L5-5-Q-19).
        return dataclasses.replace(draft, material_right=terms)
    if method == ENTERED_AMOUNT:
        point = bundles.point_ssp(ctx, st, draft.line)
        return dataclasses.replace(
            draft,
            material_right=terms,
            option_ssp=point,
            recognition_method=RecognitionMethod.UNITS_DELIVERED,
        )
    if method != DISCOUNT_X_LIKELIHOOD:
        raise ValueError(f"{draft.subject_key}: {method!r} is not a POL-026 option")
    likelihood, ratio, _ = _factors(st, terms, draft.pricing_date)
    if not 0 <= likelihood <= 1 or ratio < 0:
        detail = {
            "incremental_discount_ratio": format_exact(ratio),
            "likelihood": format_exact(likelihood),
            "obligation_key": draft.obligation_key,
            "rule": "S03-R-07",
        }
        findings.append(
            Finding("NON_FINITE_AMOUNT", "ERROR", draft.subject_key, detail, _STAGE, None)
        )
        return dataclasses.replace(draft, material_right=terms)
    if ratio == 0:
        return None
    value = _amount(terms) * ratio * likelihood
    return _benefit_period(
        ctx, st, dataclasses.replace(draft, material_right=terms, option_ssp=value)
    )


def not_material(st: IdentifiedState, draft: PobDraft) -> bool:
    """A ``DISCOUNT_X_LIKELIHOOD`` option whose incremental discount is 0 (606-10-55-43)."""
    header = st.canonical.contracts[draft.contract_key].header
    terms = terms_of(header, draft.obligation_key)
    return (
        draft.obligation_kind == ObligationKind.MATERIAL_RIGHT
        and terms is not None
        and terms.ssp_method == DISCOUNT_X_LIKELIHOOD
        and terms.incremental_discount_ratio is not None
        and to_fraction(terms.incremental_discount_ratio) == 0
    )


def triggers(st: IdentifiedState, obligations: Sequence[PobDraft]) -> tuple[TimeTrigger, ...]:
    """CV-27: ``TimeTrigger("MATERIAL_RIGHT_EXPIRY", expiry_date, subject key)`` per open option.

    An option is open while the stream holds no ``MATERIAL_RIGHT_EXERCISED`` or
    ``MATERIAL_RIGHT_EXPIRED`` event naming it. Triggers are sorted by (date, kind, subject key).
    """
    closed = {
        key
        for event in st.canonical.events
        if event.event_type in _CLOSING_EVENTS
        for key in _named(event.contract_key, event.obligation_subject_keys, event.payload)
    }
    found = [
        TimeTrigger(EXPIRY_TRIGGER, ob.material_right.expiry_date, ob.subject_key)
        for ob in obligations
        if ob.obligation_kind == ObligationKind.MATERIAL_RIGHT
        and ob.material_right is not None
        and ob.material_right.expiry_date is not None
        and ob.subject_key not in closed
    ]
    return tuple(sorted(found, key=lambda t: (t.date, t.kind, t.subject_key)))


def emit(
    ctx: BookContext,
    st: IdentifiedState,
    tb: TraceBuilder,
    draft: PobDraft,
    event_key: str | None,
    *,
    reason: str | None = None,
) -> None:
    """Node ``option_ssp:<ob>:-`` (§3.4; ``pob.option_ssp.v1``), posted in the transaction currency.

    ``reason = NOT_MATERIAL`` records 0 for an option with no incremental discount.
    """
    terms = draft.material_right or terms_of(
        st.canonical.contracts[draft.contract_key].header, draft.obligation_key
    )
    if terms is None:
        return
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    value = Fraction(0) if reason == NOT_MATERIAL else draft.option_ssp
    if value is None:
        return
    params = {"method": terms.ssp_method, "option_type": terms.option_type}
    inputs: list[str | SourceRef] = []
    if reason is not None:
        params["reason"] = reason
    elif terms.ssp_method == DISCOUNT_X_LIKELIHOOD:
        likelihood, ratio, pin = _factors(st, terms, draft.pricing_date)
        params["expected_purchase_amount"] = format_exact(_amount(terms))
        params["incremental_discount_ratio"] = format_exact(ratio)
        params["likelihood"] = format_exact(likelihood)
        inputs.append(
            SourceRef("estimate_version", pin.version_key, {"value": format_exact(likelihood)})
        )
    else:
        entry = bundles.ssp_entry(ctx, st, draft.line)
        if entry is not None:
            inputs.append(SourceRef("ssp_entry", entry.entry_key, {"value": format_exact(value)}))
    if event_key is not None:
        detail = {"line": draft.obligation_key, "value": format_exact(draft.quantity)}
        inputs.append(SourceRef("contract_event", event_key, detail))
    tb.node(
        measure="option_ssp",
        subject_key=draft.subject_key,
        period_key=None,
        value=round_half_up(value, minor_unit),
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=FORMULA,
        inputs=inputs,
        params=params,
        exact=value,
        narrative_key=FORMULA.rsplit(".v", 1)[0],
    )


def _amount(terms: MaterialRightInput) -> Fraction:
    if terms.expected_purchase_amount is None:
        raise ValueError(f"{terms.obligation_key}: DISCOUNT_X_LIKELIHOOD needs its amounts")
    return to_fraction(terms.expected_purchase_amount)


def _factors(
    st: IdentifiedState, terms: MaterialRightInput, at: date
) -> tuple[Fraction, Fraction, EstimateVersionInput]:
    """(L, incremental discount ratio, the pinned ``EXERCISE_LIKELIHOOD`` version) at ``at``."""
    if terms.incremental_discount_ratio is None or terms.expected_purchase_amount is None:
        raise ValueError(f"{terms.obligation_key}: DISCOUNT_X_LIKELIHOOD needs its amounts")
    if terms.likelihood_estimate_key is None:
        raise ValueError(f"{terms.obligation_key}: DISCOUNT_X_LIKELIHOOD needs a likelihood")
    pin = st.canonical.estimates.pin(terms.likelihood_estimate_key, at)
    if pin is None or pin.rate is None:
        raise ValueError(f"{terms.likelihood_estimate_key}: no EXERCISE_LIKELIHOOD pin at {at}")
    return to_fraction(pin.rate), to_fraction(terms.incremental_discount_ratio), pin


def _benefit_period(ctx: BookContext, st: IdentifiedState, draft: PobDraft) -> PobDraft:
    """POL-029 ``EXPECTED_BENEFIT_PERIOD``: a renewal option ends at start + ``amortization_months``
    of the latest ``RENEWAL_EXPECTATION`` pin of the contract at the pricing date, less one day
    (L2-2-Q-2)."""
    terms = draft.material_right
    if terms is None or terms.option_type != RENEWAL_OPTION or draft.start_date is None:
        return draft
    try:
        period = ctx.policies.value(UPFRONT_FEE_POLICY, contract=draft.contract_key)
    except ValueError:  # POL-029 is not declared in the bundle (CV-17)
        return draft
    if period != EXPECTED_BENEFIT_PERIOD:
        return draft
    prefix = f"{contract_subject_key(draft.contract_key)}/"
    pins = st.canonical.estimates
    latest: EstimateVersionInput | None = None
    for key in sorted(pins.pins):
        if not key.startswith(prefix):
            continue
        version = pins.pin(key, draft.pricing_date)
        if version is None or version.estimate_kind != "RENEWAL_EXPECTATION":
            continue
        if version.amortization_months is None:
            continue
        if latest is None or (version.effective_date, version.version_no) > (
            latest.effective_date,
            latest.version_no,
        ):
            latest = version
    if latest is None or latest.amortization_months is None:
        return draft
    end = add_months(draft.start_date, latest.amortization_months) - timedelta(days=1)
    return dataclasses.replace(draft, end_date=end)


def _named(
    contract_key: str, subject_keys: Sequence[str], payload: Mapping[str, object]
) -> tuple[str, ...]:
    """Obligation subject keys an event names: its subject keys and payload ``obligation_key``."""
    value = payload.get("obligation_key")
    extra = (obligation_subject_key(contract_key, value),) if isinstance(value, str) else ()
    return (*subject_keys, *extra)
