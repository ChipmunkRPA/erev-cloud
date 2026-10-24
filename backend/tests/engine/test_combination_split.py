"""Prospective split basis uses dated SSP and preserves original posted revenue."""

from dataclasses import replace
from datetime import date

import pytest
from support import bundles

from erev_engine.combination_split import prepare
from tests.engine.s06_modifications.test_s06_prospective import ex_09_a, point_entry


def combined():
    value = ex_09_a()
    first = replace(value.contracts[0], modifications=())
    second = replace(first, external_id="SPLIT-B")
    original = next(e for e in value.events if e.event_type == "CONTRACT_BOOKED")
    line = {**original.payload["lines"][0], "product_code": "SKU-SEATS"}
    events = (
        original,
        bundles.event(
            second.external_id,
            1,
            "CONTRACT_BOOKED",
            original.effective_date,
            {**original.payload, "lines": [line]},
            obligation_keys=["POB-01"],
        ),
    )
    v1, v2 = value.ssp_versions
    v1 = replace(v1, entries=(*v1.entries, point_entry(v1.version_key, "SKU-SEATS", "120000")))
    v2 = replace(
        v2,
        entries=tuple(
            point_entry(v2.version_key, "SKU-SEATS", "155000")
            if e.product_code == "SKU-SEATS"
            else e
            for e in v2.entries
        ),
    )
    return replace(
        value,
        evidence_revision=48,
        group=replace(
            value.group,
            member_contract_keys=tuple(sorted((first.external_id, second.external_id))),
            criterion="25_9_A",
        ),
        contracts=tuple(sorted((first, second), key=lambda c: c.external_id)),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(v1, v2),
    )


def test_split_uses_effective_remaining_ssp_preserving_original_income():
    value = combined()
    targets = {c.external_id: c.external_id for c in value.contracts}
    digest = value.sha256()
    result = prepare(
        value, book_code="ASC606", destinations=targets, effective_date=date(2026, 9, 16)
    )
    a, b = result.members
    assert a.remaining_ssp == b.remaining_ssp
    assert abs(a.remaining_after_minor - b.remaining_after_minor) <= 1
    assert (a.recognized_minor, b.recognized_minor) == (11_309_589, 5_654_795)
    assert (a.remaining_after_minor, b.remaining_after_minor) == (15_517_808, 15_517_808)
    assert a.remaining_before_minor != b.remaining_before_minor
    assert sum(m.remaining_after_minor for m in result.members) == result.unrecognized_minor
    assert sum(m.recognized_minor for m in result.members) == result.recognized_minor
    assert all(
        sum(v for _, v in m.obligation_shares) == m.remaining_after_minor for m in result.members
    )
    assert all(m.original[0].remaining_ssp_sources for m in result.members)
    assert value.sha256() == digest == result.input_sha256
    assert (
        prepare(
            value,
            book_code="ASC606",
            destinations=dict(reversed(list(targets.items()))),
            effective_date=date(2026, 9, 16),
        )
        == result
    )


@pytest.mark.parametrize("targets", [{}, {"SPLIT-B": "new"}])
def test_split_refuses_omitting_original_members(targets):
    with pytest.raises(ValueError, match="every original"):
        prepare(
            combined(), book_code="ASC606", destinations=targets, effective_date=date(2026, 9, 16)
        )
