"""Partial disclosure excludes only dated targeted VC, with fixed consideration retained."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from erev_api.domain.reports import rpo_quotas, variance_rpo
from erev_api.domain.reports.builders import rpo
from erev_api.problems import Problem
from erev_engine import compute
from support import allocation_worlds as worlds


@pytest.mark.parametrize("target_amount, expected_cap", [("200", "200"), ("-50", "0")])
def test_real_engine_targeted_changes_keep_fixed_consideration(
    target_amount: str,
    expected_cap: str,
) -> None:
    targeted = worlds.element("100", keys=["A"])
    base = worlds.untargeted_element("0")
    bundle = worlds.with_changes(
        worlds.targeted_world(estimates=[targeted, base]),
        [
            worlds.later_version(targeted, 2, date(2026, 2, 1), target_amount),
            worlds.later_version(base, 2, date(2026, 3, 1), "100"),
        ],
        memo_on=date(2026, 3, 31),
        policies={"rpo.exemption_vc_wholly_unsatisfied": "APPLY"},
    )
    output = compute(bundle)
    book = output.books[0]
    eligibility = {
        item.version_key: item.allocation_target == "OBLIGATIONS"
        and item.parameters.get("allocation_criteria_evidence") not in (None, "")
        for item in bundle.estimate_versions
    }
    history = rpo_quotas.history(
        book.trace,
        inception={item.external_id: item.inception_date for item in bundle.contracts},
        targeted=eligibility,
    )
    points = history["K-01/A"]
    assert rpo_quotas.cap(points, date(2026, 1, 31)) == Decimal("100")
    assert rpo_quotas.cap(points, date(2026, 2, 28)) == Decimal(expected_cap)
    assert rpo_quotas.cap(points, date(2026, 3, 31)) == Decimal(expected_cap)
    entity = bundle.entities[0]
    period = next(item for item in entity.periods if item.end_date == date(2026, 3, 31))
    result = variance_rpo.project(
        bundle, book, entity_code=entity.code, period_key=period.period_key, functional=False
    )
    gross = (
        sum(
            Decimal(str(item.columns["scheduled_amount"]))
            + Decimal(str(item.columns["awaiting_trigger_amount"]))
            for item in book.obligation_versions
        )
        / 100
    )
    assert sum(result.values()) == gross - Decimal(expected_cap)
    if target_amount == "200":
        assert sum(result.values()) == 200  # fixed 100 + untargeted 100 remains
    with pytest.raises(Problem, match="retained estimate version"):
        rpo_quotas.history(
            book.trace,
            inception={item.external_id: item.inception_date for item in bundle.contracts},
            targeted={},
        )


def test_partial_exemption_apportions_bands_and_releases_after_performance() -> None:
    from erev_api.domain.contracts.to_date import ObligationAt

    vid, oid, cid, eid = (uuid4() for _ in range(4))
    ob = rpo._Ob(
        oid,
        vid,
        oid,
        cid,
        "C",
        "O",
        "Service",
        None,
        None,
        None,
        eid,
        "E",
        "USD",
        "POINT_IN_TIME",
        date(2028, 12, 31),
        date(2026, 1, 1),
        Decimal("150"),
        False,
    )
    day = date(2026, 1, 31)
    at = ObligationAt(
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal("150"),
        "UNSATISFIED",
        None,
        None,
    )
    version = rpo._Version(vid, uuid4(), 1, True, date(2026, 1, 1), frozenset())
    store = rpo.Store(
        {version.group_id: (version,)},
        {vid: (ob,)},
        {cid: (version,)},
        {(vid, day): {oid: at}},
        {vid: {"C/O": (rpo_quotas.Point(date(2026, 1, 1), Decimal(100), "quota"),)}},
    )
    (row,) = rpo.rows_at(
        store, as_of={eid: day}, bands=(12, 24), applied={eid: frozenset({"POL-200"})}
    )
    assert (row.total, row.excluded, row.partial_exemption) == (
        Decimal(50),
        Decimal(100),
        "POL-200",
    )
    assert sum(row.placed) == sum(item[2] for item in row.contributors) == row.total
    assert row.placed == (Decimal(0), Decimal(0), Decimal(50))
    store.cuts[(vid, day)] = {
        oid: replace(
            at, revenue=Decimal(1), awaiting=Decimal(149), satisfaction_status="PARTIALLY_SATISFIED"
        )
    }
    (row,) = rpo.rows_at(
        store, as_of={eid: day}, bands=(12, 24), applied={eid: frozenset({"POL-200"})}
    )
    assert (row.total, row.excluded) == (Decimal(149), Decimal(0))

    # Beginning performance releases the exclusion separately from revenue.
    end = date(2026, 2, 28)
    store.cuts[(vid, end)] = store.cuts[(vid, day)]
    store.cuts[(vid, day)] = {oid: at}
    (movement,) = rpo.rollforward_lines(
        store, ranges={eid: (day, end)}, applied={eid: frozenset({"POL-200"})}
    )
    assert movement.lines["OPENING"] == 50
    assert movement.lines["EXEMPTIONS"] == 100
    assert movement.lines["REVENUE"] == -1
    assert movement.lines["CLOSING"] == 149
    assert movement.lines["UNEXPLAINED"] == 0


@pytest.mark.parametrize(
    "original_end, revised_end, exempt",
    [
        (date(2026, 12, 31), date(2027, 12, 31), True),
        (date(2027, 12, 31), date(2026, 12, 31), False),
        (date(2027, 1, 1), date(2027, 6, 30), False),
    ],
)
def test_original_duration_survives_contract_term_changes(
    original_end: date, revised_end: date, exempt: bool
) -> None:
    from erev_api.domain.reports import rpo_duration
    from erev_engine.bundle import ModificationInput
    from support import bundles

    bundle = worlds.native(
        {**worlds.line("A", "PROD-A", "100"), "end_date": original_end},
        entries=[worlds.entry("PROD-A", point="100")],
        activated=True,
        overrides={
            worlds.TOLERANCE: "NOT_ENFORCED",
            "rpo.exemption_original_duration_one_year": "APPLY",
        },
    )
    amendment = {
        "obligation_key": "A",
        "action": "CHANGE",
        "product_code": "PROD-A",
        "quantity_delta": Decimal(0),
        "consideration_delta": Decimal(0),
        "end_date": revised_end,
    }
    effective = date(2026, 6, 1)
    modification = ModificationInput(
        modification_key="TERM",
        effective_date=effective,
        kind="CHANGE_SCOPE",
        template_mode=None,
        status="APPLIED",
        reference=None,
        questionnaire={},
        lines=(amendment,),
        price_change_amount=None,
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments={},
        treatment_summary=None,
        ssp_basis={},
        judgement_key=None,
        content_sha256=None,
    )
    changed = bundles.event(
        worlds.CONTRACT,
        3,
        "CONTRACT_AMENDED",
        effective,
        {
            "modification_id": "TERM",
            "treatments": {"A": "PROSPECTIVE"},
            "lines": [amendment],
            "ssp_basis": {},
        },
        obligation_keys=["A"],
    )
    bundle = replace(
        bundle,
        contracts=(replace(bundle.contracts[0], modifications=(modification,)),),
        events=(*bundle.events, changed),
    )
    bundle = worlds.with_changes(
        bundle, (), policies={"rpo.exemption_original_duration_one_year": "APPLY"}
    )
    output = compute(bundle)
    book = output.books[0]
    assert book.obligation_versions[0].columns["end_date"] == revised_end
    assert rpo_duration.original_ends(bundle, "ASC606")[worlds.CONTRACT] == original_end
    result = variance_rpo.project(
        bundle,
        book,
        entity_code=bundle.entities[0].code,
        period_key="FY2026-P06",
        functional=False,
    )
    assert sum(result.values()) == (0 if exempt else 100)
