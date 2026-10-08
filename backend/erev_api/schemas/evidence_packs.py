"""API-S-EvidencePackCreate (04 §16.14; BUILD_SPEC RPS-16).

Each kind has exactly its documented selectors. The discriminated union also exposes
these requirements in generated API documentation. Source existence, permissions and
lock consistency must be checked by the command within its unit of work.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from erev_api.enums import BookCode, RunStatus


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("A selector must not be blank.")
    # Business identifiers are exact keys; do not silently trim or normalise them.
    return value


type Identifier = Annotated[str, Field(min_length=1), AfterValidator(_nonblank)]


class _PackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClosePackCreateIn(_PackCreate):
    """A specific lock's entity, book and period; no implicit current-lock selection."""

    kind: Literal["CLOSE"]
    entity_code: Annotated[Identifier, Field(max_length=64)]
    book: BookCode
    period_key: Annotated[Identifier, Field(max_length=16)]
    period_lock_id: UUID


class ContractSamplePackCreateIn(_PackCreate):
    """One to fifty distinct contracts, with an explicit effective-date cutoff."""

    kind: Literal["CONTRACT_SAMPLE"]
    contract_external_ids: Annotated[list[Identifier], Field(min_length=1, max_length=50)]
    as_of: date

    @model_validator(mode="after")
    def distinct_contracts(self) -> Self:
        if len(set(self.contract_external_ids)) != len(self.contract_external_ids):
            raise ValueError("contract_external_ids must not contain duplicates.")
        return self


class ChangePackCreateIn(_PackCreate):
    """Changes in an inclusive date range, including a single day."""

    kind: Literal["CHANGE"]
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.to_date < self.from_date:
            raise ValueError("to_date must be on or after from_date.")
        return self


class AccessPackCreateIn(_PackCreate):
    """Access evidence as of an explicit date."""

    kind: Literal["ACCESS"]
    as_of: date


type EvidencePackCreateIn = Annotated[
    ClosePackCreateIn | ContractSamplePackCreateIn | ChangePackCreateIn | AccessPackCreateIn,
    Field(discriminator="kind"),
]


class EvidenceManifestFileOut(BaseModel):
    path: str
    sha256: str
    bytes: int
    report_run_id: UUID | None


class EvidenceManifestOut(BaseModel):
    files: list[EvidenceManifestFileOut]


class ClosePackOut(BaseModel):
    """Retained CLOSE pack header and manifest; source bindings are not rewritten on read."""

    id: UUID
    pack_no: str
    kind: Literal["CLOSE"]
    status: RunStatus
    entity_id: UUID
    book: BookCode
    period_id: UUID
    period_lock_id: UUID
    job_id: UUID | None
    report_run_ids: list[UUID]
    manifest: EvidenceManifestOut | None
    manifest_sha256: str | None
    created_at: datetime
    updated_at: datetime
    download_href: str | None
