"""Rebuild exact allocation inputs at an estimate's date from verified retained input.

The caller must verify the saved computation's input/output and authorization first. This
module never fetches latest configuration or treats a current obligation version as history.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from decimal import localcontext
from fractions import Fraction

from erev_api.problems import Problem
from erev_engine import ENGINE_VERSION, fold_book, guards, money
from erev_engine.bundle import InputBundle
from erev_engine.stages import s01_canonicalize, s13_books
from erev_engine.trace import TraceBuilder


@dataclass(frozen=True, slots=True)
class Basis:
    subject_key: str
    contract_key: str
    obligation_key: str
    currency: str
    ssp: Fraction
    entitlement: Fraction
    effective_date: date
    redemption_eligible: bool = False


def from_bundle(
    bundle: InputBundle,
    book_code: str,
    effective_date: date,
    subjects: Collection[str],
) -> dict[str, Basis]:
    """End-of-day basis after all accepted boundaries on the estimate effective date.

    A retained computation has today's admitted population. Historical regrouping cannot be
    inferred from it: requested original-member subjects must remain individually represented.
    Likewise, an opening migration cannot prove a basis before its cutover.
    """
    if bundle.engine_version != ENGINE_VERSION:
        raise Problem(
            "validation-failed", "Historical allocation needs a supported engine version."
        )
    requested = set(subjects)
    if not requested or len(requested) != len(subjects):
        raise Problem("validation-failed", "Historical allocation needs unique original targets.")
    guards.no_floats(bundle)
    book = next((item for item in bundle.books if item.book_code == book_code), None)
    if book is None or book_code == "LEGACY":
        raise Problem(
            "validation-failed", "Historical allocation requires a retained ASC606 or IFRS15 book."
        )
    with localcontext(money.DECIMAL_CONTEXT):
        trace = TraceBuilder(engine_version=ENGINE_VERSION)
        canonical = s01_canonicalize.run(bundle, trace)
        # Inception folding admits every booked member. A later member must not contaminate
        # an earlier population, even when the requested subject itself already existed.
        if any(
            item.header.inception_date > effective_date for item in canonical.contracts.values()
        ):
            raise Problem(
                "validation-failed",
                "The saved group includes members created after the estimate date.",
            )
        state = fold_book(
            s13_books.book_context(canonical, book),
            canonical,
            trace,
            boundary_cutoff=effective_date,
        )
    if any(item.severity == "ERROR" for item in state.findings):
        raise Problem("validation-failed", "The historical allocation fold has blocking findings.")
    merged = {
        node.id.split(":")[1]
        for node in trace.build(root_measures={}).nodes
        if node.measure == "original_quantity" and node.formula_id == "pob.merge.v1"
    }
    result = {}
    for ob in state.obligations:
        if ob.subject_key not in requested:
            continue
        if ob.combined_component_keys or ob.subject_key in merged:
            raise Problem(
                "validation-failed", "A combined host cannot supply an original member entitlement."
            )
        segments = [segment for segment in ob.segments if segment.component == "FIXED"]
        if (
            not segments
            or segments[0].effective_date > effective_date
            or (ob.terminated_on is not None and ob.terminated_on <= effective_date)
            or ob.scope_flag != "IN_SCOPE_606"
        ):
            raise Problem("validation-failed", "A target is unavailable on the estimate date.")
        segment = segments[-1]
        ssp = segment.remaining_ssp
        if ssp < 0 or ob.quantity < 0:
            raise Problem(
                "validation-failed", "Historical SSP and entitlement must be nonnegative."
            )
        result[ob.subject_key] = Basis(
            ob.subject_key,
            ob.contract_key,
            ob.obligation_key,
            bundle.group.transaction_currency,
            ssp,
            ob.quantity,
            effective_date,
            ob.recognition_method == "REDEMPTION_PATTERN"
            or (
                ob.material_right is not None
                and ob.material_right.terms.option_type == "LOYALTY_POINTS"
            ),
        )
    if set(result) != requested:
        raise Problem(
            "validation-failed",
            "Original targets are missing at the estimate date; "
            "combined aliases cannot substitute.",
        )
    return result
