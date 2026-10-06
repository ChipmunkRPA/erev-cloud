"""GPA-4 figures that no golden parity case asserts (D-87 L6-2-Q-6; BUILD_SPEC GPA-4; legacy 07 §7
GT-13 to GT-15; docs/dev-guide.md §9.6 DG-PAR-05, DG-PAR-07).

The 23 GPA-4 cases assert contract totals and the POB #3, #2 and #1 catch-ups, but not these eight
figures. Each case reads the DG-PAR-04 world of ``support.parity.scenario`` (the session fixture of
``conftest.py``) at DG-PAR-05 precision, and passes within the DG-PAR-07 tolerance of 1/10000:

- after step 11 (GT-13): Contract 3 POB #1 remaining SSP 707 and remaining allocation 587.3033;
  Contract 4 POB #3 remaining allocation 355.2772;
- step 12 (GT-14): the modification SSP node ``mod_ssp@<event key>:<obligation>:-`` (S06-R-28) of
  the step's ``CONTRACT_AMENDED`` event, on Contract 3 POB #1 (−306) and on Contract 4 POB #3 (−75);
- after step 13 (GT-15): Contract 3 remaining allocations POB #5 1,268.1139, POB #1 678.0182 and
  POB #2 311.1106.

These are parity-marker tests, not golden cases: the release gate stays at 121 parity cases, and the
``make parity`` report counts only golden cases (D-87). Run them with
``make parity K="gpa4_unasserted or catchup-13-Contract3-POB3"``, or without the report with
``EREV_ENV=test PYTHONPATH=backend/tests pytest backend/tests/parity -m parity -k gpa4_unasserted``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Final

import pytest
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import calc_trace, contract_event, contract_version
from erev_api.explain import store
from erev_engine.stages.s01_canonicalize import contract_subject_key, obligation_subject_key
from sqlalchemy import select
from support.parity import compare, values
from support.parity.scenario import ParityScenario

pytestmark = pytest.mark.parity

AMENDED: Final = "CONTRACT_AMENDED"
MOD_SSP: Final = "mod_ssp"


@dataclass(frozen=True, slots=True)
class Figure:
    """One GPA-4 figure: the GT row, the step after which it is read, and its source."""

    gt: str
    step: str
    contract: str
    pob: str
    measure: str  # an obligation_version column, or ``mod_ssp``
    expected: str

    @property
    def id(self) -> str:
        subject = f"{self.contract}-{self.pob}".replace(" ", "")
        return f"gpa4_unasserted::{self.gt}-step{self.step}-{subject}-{self.measure}"


FIGURES: Final = (
    Figure("GT-13", "11", "Contract 3", "POB #1", "remaining_ssp", "707"),
    Figure("GT-13", "11", "Contract 3", "POB #1", "remaining_allocation", "587.3033"),
    Figure("GT-13", "11", "Contract 4", "POB #3", "remaining_allocation", "355.2772"),
    Figure("GT-14", "12", "Contract 3", "POB #1", MOD_SSP, "-306"),
    Figure("GT-14", "12", "Contract 4", "POB #3", MOD_SSP, "-75"),
    Figure("GT-15", "13", "Contract 3", "POB #5", "remaining_allocation", "1268.1139"),
    Figure("GT-15", "13", "Contract 3", "POB #1", "remaining_allocation", "678.0182"),
    Figure("GT-15", "13", "Contract 3", "POB #2", "remaining_allocation", "311.1106"),
)


def _latest(world: ParityScenario, figure: Figure) -> Fraction | None:
    """``exact(measure)`` of the latest obligation version after the figure's step (DG-PAR-05)."""
    rows, nodes = world.latest_obligation_versions(figure.contract, figure.step)
    matching = [row for row in rows if row["obligation_key"] == figure.pob]
    assert len(matching) == 1, f"{figure.id}: {len(matching)} obligation versions of {figure.pob}"
    return values.exact(matching[0], figure.measure, nodes)


def _mod_ssp(world: ParityScenario, figure: Figure) -> Fraction:
    """The ``mod_ssp`` node of the step's modification event on the obligation, read from the
    calc_trace of the contract version that the modification created."""
    row, _ = world.modification_obligation_version(figure.contract, figure.pob, figure.step)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        version = (
            session.execute(
                select(contract_version.c.calc_trace_id, contract_version.c.cause_event_ids).where(
                    contract_version.c.id == row["contract_version_id"]
                )
            )
            .mappings()
            .one()
        )
        amended = list(
            session.execute(
                select(contract_event.c.stream_version).where(
                    contract_event.c.id.in_(list(version["cause_event_ids"])),
                    contract_event.c.contract_id == row["contract_id"],
                    contract_event.c.event_type == AMENDED,
                )
            ).scalars()
        )
        trace_row = (
            session.execute(select(calc_trace).where(calc_trace.c.id == version["calc_trace_id"]))
            .mappings()
            .one()
        )
    assert len(amended) == 1, f"{figure.id}: {len(amended)} {AMENDED} events cause the version"
    event_key = f"{contract_subject_key(figure.contract)}/EV-{int(amended[0]):06d}"  # CV-22
    node_id = f"{MOD_SSP}@{event_key}:{obligation_subject_key(figure.contract, figure.pob)}:-"
    nodes = {node.id: node for node in store.trace_from_row(trace_row).nodes}
    node = nodes.get(node_id)
    named = sorted(key for key in nodes if key.startswith(f"{MOD_SSP}@"))
    assert node is not None, f"{figure.id}: {node_id} is not in the trace; mod_ssp nodes {named}"
    return values.node_exact(node)


@pytest.mark.parametrize("figure", FIGURES, ids=lambda figure: figure.id)
def test_gpa4_unasserted_figures(figure: Figure, parity_scenario: ParityScenario) -> None:
    if figure.measure == MOD_SSP:
        actual: Fraction | None = _mod_ssp(parity_scenario, figure)
    else:
        actual = _latest(parity_scenario, figure)
    assert compare.unit_equal(actual, figure.expected), (
        f"{figure.id}: expected {figure.expected}, actual {compare.render(actual)}"
    )
