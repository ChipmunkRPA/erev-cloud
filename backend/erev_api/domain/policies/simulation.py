"""Impact simulation of configuration changes: the provider registry (PRD BR-POL-01; 04 §16.2
API-S-SimulationSummary; REQ-POL-006; BUILD_SPEC RFD-5, BS3-D-05, BS3-D-17).

A provider measures the effect of a configuration version on one population and returns a
``ProviderResult``. ``simulate`` runs every registered provider in name order, stores the report as
a ``REPORT_OUTPUT`` file and returns the file id with API-S-SimulationSummary. With no provider
registered there is no contract to affect, so the report states "No contracts affected" (BS3-D-05).
CTR-16 registers the contract provider.

The ``POLICY_SIMULATION`` job handler is registered here (BS3-D-17): ``POST /policies/{id}/test``
returns such a job. It runs the test runner a configuration module registered for the job's
``subject_type`` through ``register_test_runner``, in one unit of work (BUILD_SPEC RFD-11).
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import registry_version
from erev_api.domain.imports.job_items import failed_item
from erev_api.enums import ExceptionSource, FilePurpose, JobKind
from erev_api.files.store import open_file, store_file
from erev_api.jobs.registry import FailedSubject, JobOutcome, task

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.files.store import FileStore
    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

NO_CONTRACTS_AFFECTED: Final = "No contracts affected"  # PRD BR-POL-01
REPORT_FORMAT: Final = "erev.impact_simulation.v1"
MEDIA_TYPE: Final = "application/json"


@dataclass(frozen=True, slots=True)
class SimulationSubject:
    """The configuration version a simulation measures (04 T-REF-27 ``subject_type`` literals)."""

    subject_type: str
    subject_id: UUID
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """One provider's part of API-S-SimulationSummary; amounts are Money in the tenant reporting
    currency."""

    contracts_affected: int
    revenue_delta_by_period: tuple[Mapping[str, Any], ...] = ()
    balance_delta: tuple[Mapping[str, Any], ...] = ()
    journal_delta: tuple[Mapping[str, Any], ...] = ()


type Provider = Callable[[UnitOfWork, SimulationSubject], ProviderResult]

# Registered providers by name; later items add theirs through ``register_provider``.
PROVIDERS: Final[dict[str, Provider]] = {}


def register_provider(name: str, provider: Provider) -> None:
    """Register ``provider`` under ``name``; a name is registered once."""
    if name in PROVIDERS:
        raise ValueError(f"simulation provider {name} is registered already")
    PROVIDERS[name] = provider


@dataclass(frozen=True, slots=True)
class Simulation:
    file_id: UUID
    summary: Mapping[str, Any]


def statement(contracts_affected: int) -> str:
    """The sentence the report states (PRD BR-POL-01)."""
    if contracts_affected == 0:
        return NO_CONTRACTS_AFFECTED
    noun = "contract" if contracts_affected == 1 else "contracts"
    return f"{contracts_affected} {noun} affected"


def summarise(results: Sequence[ProviderResult]) -> dict[str, Any]:
    """API-S-SimulationSummary of the provider results, with the report's ``statement``."""
    affected = sum(result.contracts_affected for result in results)
    return {
        "contracts_affected": affected,
        "revenue_delta_by_period": [
            dict(item) for result in results for item in result.revenue_delta_by_period
        ],
        "balance_delta": [dict(item) for result in results for item in result.balance_delta],
        "journal_delta": [dict(item) for result in results for item in result.journal_delta],
        "statement": statement(affected),
    }


def simulate(uow: UnitOfWork, subject: SimulationSubject) -> Simulation:
    """Run every registered provider and store the report as a ``REPORT_OUTPUT`` file."""
    names = sorted(PROVIDERS)
    summary = summarise([PROVIDERS[name](uow, subject) for name in names])
    document = {
        "format": REPORT_FORMAT,
        "subject_type": subject.subject_type,
        "subject_id": str(subject.subject_id),
        "content_sha256": subject.content_sha256,
        "generated_at": uow.now,
        "providers": names,
        "summary": summary,
    }
    row = store_file(
        uow,
        purpose=FilePurpose.REPORT_OUTPUT,
        stream=io.BytesIO(canonical_bytes(document)),
        original_filename=None,
        media_type=MEDIA_TYPE,
    )
    return Simulation(file_id=UUID(str(row["id"])), summary=summary)


def read_summary(
    session: Session, file_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    """The API-S-SimulationSummary stored in a simulation report file."""
    _, stream = open_file(session, file_id, files=files, keyring=keyring)
    with stream:
        document = json.loads(stream.read(), parse_float=Decimal)
    summary = document.get("summary") if isinstance(document, dict) else None
    if not isinstance(summary, dict):
        raise LookupError(f"file {file_id} holds no simulation report")
    return summary


# --- the POLICY_SIMULATION job (BS3-D-17) ---------------------------------------------------------

type TestRunner = Callable[[UnitOfWork, UUID, Mapping[str, Any]], Mapping[str, Any]]

# Test runners by T-REF-27 subject type; configuration modules register theirs when imported.
TEST_RUNNERS: Final[dict[str, TestRunner]] = {}


def register_test_runner(subject_type: str, runner: TestRunner) -> None:
    """Register the runner of ``subject_type``; it returns the job result ``{href, counts}``."""
    if subject_type in TEST_RUNNERS:
        raise ValueError(f"configuration subject {subject_type} has a test runner already")
    TEST_RUNNERS[subject_type] = runner


REGISTRY_VERSION_SUBJECT: Final = "registry_version"  # 04 T-PLT-27 ``subject_type``


def failed_simulation(
    session: Session, subject_type: str | None, subject_id: UUID, params: Mapping[str, Any]
) -> FailedSubject | None:
    """05 JOB-07 rev 1.165: what the exception item of a failed test run names — the entity of a
    registry version of entity scope (04 T-REF-27 ``entity_id``). A version of the workspace's
    scope, and the configuration versions of the other subject types, name no entity and raise
    no item."""
    if subject_type != REGISTRY_VERSION_SUBJECT:
        return None
    entity_id = session.execute(
        select(registry_version.c.entity_id).where(registry_version.c.id == subject_id)
    ).scalar_one_or_none()
    return None if entity_id is None else FailedSubject(entity_id=UUID(str(entity_id)))


@task(
    JobKind.POLICY_SIMULATION,
    failed_item=failed_item(ExceptionSource.ENGINE, failed_simulation),
)
def policy_simulation(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``POLICY_SIMULATION``: test the configuration version named by ``params.subject_type`` and
    ``params.subject_id``. The runner validates the version, runs the providers and records TESTED
    in one unit of work; a refusal fails the job with its problem and changes nothing."""
    subject_type = str(params["subject_type"])
    runner = TEST_RUNNERS.get(subject_type)
    if runner is None:
        raise LookupError(f"configuration subject {subject_type} has no test runner")
    with jc.unit_of_work() as uow:
        result = runner(uow, UUID(str(params["subject_id"])), params)
        uow.commit()
    return JobOutcome(state="SUCCEEDED", result=result)
