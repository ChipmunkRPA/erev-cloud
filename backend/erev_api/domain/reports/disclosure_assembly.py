"""Seven disclosure chapters assembled from verified children and exact-cutoff policies.

Keeps original inputs separate from rendered suppression. This is the assembly
model; parent job publication, frozen snapshots and quarter-column layout are separate.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.domain.reports import (
    disclosure_expedients,
    disclosure_plan,
    disclosure_results,
    elections,
    framework,
)
from erev_api.domain.reports.outputs import ReportData
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

TITLES = (
    "Disaggregation of revenue",
    "Contract balances and rollforward",
    "Revenue from the opening contract liability",
    "Revenue from obligations satisfied in prior periods",
    "Remaining performance obligations",
    "Contract cost rollforward",
    "Practical expedients used",
)
SUPPRESSION = {
    "contract_balance_rollforward": elections.CONTRACT_BALANCES_RELIEF,
    "revenue_from_opening_liability": elections.CONTRACT_BALANCES_RELIEF,
    "revenue_from_prior_period_obligations": elections.CONTRACT_BALANCES_RELIEF,
    "rpo": elections.RPO_RELIEF,
    "rpo_rollforward": elections.RPO_RELIEF,
    "contract_cost_rollforward": "disclosure.nonpublic_cost_relief",
}


@dataclass(frozen=True)
class Table:
    key: str
    basis: str
    data: ReportData
    source_run_id: UUID | None
    source_sha256: str
    omitted: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Section:
    number: int
    title: str
    tables: tuple[Table, ...]
    interim_required: bool


@dataclass(frozen=True)
class Pack:
    sections: tuple[Section, ...]
    children: tuple[disclosure_results.CompletedChild, ...]
    policy_facts: Mapping[str, Any]
    policy_sha256: str


def assemble(
    parent: Mapping[str, Any], collected: disclosure_results.Collected, policies: dict[str, Any]
) -> Pack:
    if collected.pending:
        raise Problem("invalid-transition", "Disclosure child reports are still running.")
    ids = parent["entity_ids"]
    if (
        len(ids) != 1
        or policies.get("tenant_id") != str(parent["tenant_id"])
        or policies.get("entity_id") != str(ids[0])
        or policies.get("book") != parent["book_code"]
        or datetime.fromisoformat(policies["known_at"]) != parent["known_at"]
    ):
        raise Problem("validation-failed", "Disclosure policy facts differ from the parent scope.")
    quarter = bool(parent["parameters"].get("quarter"))
    expected = {
        f"{code}:{basis}"
        for code in disclosure_plan.SECTIONS
        for basis in (("PERIOD", "QUARTER_TO_DATE") if quarter else ("PERIOD",))
        if basis == "PERIOD" or code not in disclosure_plan.POINT_IN_TIME
    }
    if (
        {c.source.key for c in collected.children} != expected
        or len(collected.children) != len(expected)
        or [c.source.run_id for c in collected.children] != list(parent["child_report_run_ids"])
    ):
        raise Problem(
            "validation-failed", "The complete attached disclosure population is required."
        )
    elected = set(policies["elected_reliefs"])
    tables: dict[int, list[Table]] = {n: [] for n in range(1, 8)}
    for child in collected.children:
        run = child.run
        if (
            run["tenant_id"] != parent["tenant_id"]
            or run["entity_ids"] != ids
            or run["book_code"] != parent["book_code"]
            or run["known_at"] != parent["known_at"]
        ):
            raise Problem("validation-failed", "A disclosure child differs from the parent scope.")
        code = str(run["report_code"])
        relief = SUPPRESSION.get(code)
        omitted = relief in elected
        notes = [str(note["note"]) for note in child.data.control_totals.get("notes", ())]
        footnote = child.data.control_totals.get("footnote")
        if footnote:
            notes.append(str(footnote))
        if omitted and relief is not None:
            notes.append(elections.OMITTED.format(label=elections.RELIEFS[relief][1]))
        for number in disclosure_plan.SECTIONS[code]:
            tables[number].append(
                Table(
                    child.source.key,
                    child.source.basis,
                    ReportData(child.data.columns, (), {}) if omitted else child.data,
                    child.source.run_id,
                    child.output_sha256,
                    omitted,
                    tuple(dict.fromkeys(notes)),
                )
            )
    policy_hash = sha256_hex(policies)
    policy_data = disclosure_expedients.dataset(policies)
    tables[7].append(
        Table(
            "expedients",
            "PERIOD",
            ReportData(policy_data.columns, (), {}) if policies["omitted"] else policy_data,
            None,
            policy_hash,
            policies["omitted"],
            (policies["omission_note"],) if policies["omitted"] else (),
        )
    )
    required = (
        {1}
        if policies["interim_pack"] == elections.IAS34_16A_L
        else {
            1,
            2,
            *(() if elections.CONTRACT_BALANCES_RELIEF in elected else (4,)),
            *(() if elections.RPO_RELIEF in elected else (5,)),
        }
    )
    return Pack(
        tuple(
            Section(n, title, tuple(tables[n]), quarter and n in required)
            for n, title in enumerate(TITLES, start=1)
        ),
        collected.children,
        policies,
        policy_hash,
    )


def prepare(uow: UnitOfWork, parent_id: UUID) -> Pack | disclosure_results.Collected:
    collected = disclosure_results.collect(uow, parent_id)
    if collected.pending:
        return collected
    parent = framework.run_row(uow.session, uow.principal, parent_id, "report.run")
    policies = disclosure_expedients.capture(
        uow,
        entity_id=parent["entity_ids"][0],
        book=parent["book_code"],
        known_at=parent["known_at"],
    )
    return assemble(parent, collected, policies)
