"""Transfer inputs preserve native pre-event recognition and exact reconciliation."""

from dataclasses import replace
from fractions import Fraction

import pytest

from erev_engine.boundary_basis import fixed_boundary_basis
from tests.engine.s03_pob_builder.test_combined_reassessment import continuation


def query(value, **kwargs):
    return fixed_boundary_basis(
        value,
        book_code="ASC606",
        event_key=value.events[-1].event_key,
        contract_key=value.contracts[0].external_id,
        obligation_keys=("SERVICE",),
        **kwargs,
    )


def test_boundary_basis_measures_original_delivery_before_quantity_change():
    value = continuation()
    (basis,) = query(value)
    assert basis.allocation_minor == 1_000_000
    assert basis.recognized_minor == 250_000
    assert basis.remaining_minor == 750_000
    assert basis.allocation_exact == Fraction(10000)
    assert basis.recognized_exact == Fraction(2500)
    assert basis.remaining_exact == Fraction(7500)
    assert basis.remaining_quantity == Fraction(3, 2)
    assert len(basis.input_sha256) == 64
    assert query(value) == (basis,)
    # The changed quantity is not yet applied, and subsequent receipts cannot leak in.
    delivery = value.events[-2]
    later = replace(
        delivery,
        effective_date=value.events[-1].effective_date,
        stream_version=value.events[-1].stream_version + 1,
        record_seq=value.events[-1].record_seq + 1,
        event_key=delivery.event_key + "-later",
    )
    future = replace(value, events=(*value.events[:-2], value.events[-1], later))
    (without_prior_delivery,) = query_at(future, value.events[-1].event_key)
    assert without_prior_delivery.recognized_minor == 0
    assert without_prior_delivery.remaining_minor == 1_000_000


def query_at(value, event_key):
    return fixed_boundary_basis(
        value,
        book_code="ASC606",
        event_key=event_key,
        contract_key=value.contracts[0].external_id,
        obligation_keys=("SERVICE",),
    )


@pytest.mark.parametrize("keys", [(), ("SERVICE", "SERVICE"), ("LEASE",), ("missing",)])
def test_boundary_basis_requires_unique_resolved_obligations(keys):
    value = continuation()
    with pytest.raises(ValueError):
        fixed_boundary_basis(
            value,
            book_code="ASC606",
            event_key=value.events[-1].event_key,
            contract_key=value.contracts[0].external_id,
            obligation_keys=keys,
        )


def test_time_basis_uses_service_before_effective_date_not_latest_remaining():
    from tests.engine.s03_pob_builder.test_lessor_modifications import price_change

    value = price_change()
    (basis,) = query(value)
    # January 1–14 of the original 365-day service; neither January 15 nor
    # the modification's additional consideration belongs to the pre-event basis.
    assert basis.allocation_exact == 10000
    assert basis.recognized_exact == Fraction(10000 * 14, 365)
    assert basis.recognized_minor == 38356
    assert basis.remaining_minor == 961644
    assert basis.remaining_exact + basis.recognized_exact == basis.allocation_exact


def test_proposed_date_includes_accepted_same_day_boundary_and_retains_current_terms():
    value = continuation()
    before = query(value)[0]
    at = fixed_boundary_basis(
        value,
        book_code="ASC606",
        effective_date=value.events[-1].effective_date,
        contract_key=value.contracts[0].external_id,
        obligation_keys=("SERVICE",),
    )[0]
    assert before.allocation_minor == 1_000_000
    assert at.allocation_minor == 1_100_000
    assert at.recognized_minor == before.recognized_minor == 250_000
    assert at.remaining_minor == 850_000
    assert at.remaining_quantity == Fraction(5, 2)
    assert at.boundary_event_key is None
    assert at.boundary_position == "AFTER_RETAINED_EVENTS_ON_DATE"
    assert at.service_start_date is not None
    assert at.service_end_date is not None
    assert at.input_sha256 == before.input_sha256


@pytest.mark.parametrize("both", [False, True])
def test_boundary_query_requires_exactly_one_position(both):
    value = continuation()
    kwargs = (
        {"event_key": value.events[-1].event_key, "effective_date": value.events[-1].effective_date}
        if both
        else {}
    )
    with pytest.raises(ValueError, match="exactly one"):
        fixed_boundary_basis(
            value,
            book_code="ASC606",
            contract_key=value.contracts[0].external_id,
            obligation_keys=("SERVICE",),
            **kwargs,
        )


def test_fixed_transfer_admission_preserves_plain_service_amounts():
    from tests.engine.s06_modifications.test_s06_prospective import ex_09_a

    value = ex_09_a()
    kwargs = dict(
        book_code="ASC606",
        event_key=value.events[-1].event_key,
        contract_key=value.contracts[0].external_id,
        obligation_keys=("POB-01",),
    )
    assert fixed_boundary_basis(
        value, **kwargs, require_fixed_transfer=True
    ) == fixed_boundary_basis(value, **kwargs)


def test_combined_member_basis_is_analytical_not_a_complete_transfer_basis():
    value = continuation()
    assert query(value)
    with pytest.raises(ValueError, match="Combined obligations"):
        query(value, require_fixed_transfer=True)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"is_vc_line": True}, "variable consideration"),
        ({"principal_agent": "AGENT"}, "Agent and cross-entity"),
        ({"performing_entity": "OTHER"}, "Agent and cross-entity"),
        ({"recognition_method": "COST_TO_COST"}, "progress basis"),
    ],
)
def test_fixed_transfer_refuses_incomplete_native_basis(monkeypatch, changes, reason):
    import erev_engine.boundary_basis as module
    from tests.engine.s06_modifications.test_s06_prospective import ex_09_a

    value = ex_09_a()
    native_fold = module.fold_book

    def fold(*args, **kwargs):
        state = native_fold(*args, **kwargs)
        return replace(
            state,
            obligations=tuple(
                replace(ob, **changes) if ob.obligation_key == "POB-01" else ob
                for ob in state.obligations
            ),
        )

    monkeypatch.setattr(module, "fold_book", fold)
    with pytest.raises(ValueError, match=reason):
        fixed_boundary_basis(
            value,
            book_code="ASC606",
            event_key=value.events[-1].event_key,
            contract_key=value.contracts[0].external_id,
            obligation_keys=("POB-01",),
            require_fixed_transfer=True,
        )
