"""API-R-53 health schemas (05 OPR-23; BUILD_SPEC BS1-D-10)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

CheckName = Literal["database", "migrations", "files", "keys"]


class HealthOut(BaseModel):
    status: Literal["ok"]


class ReadyChecksOut(BaseModel):
    database: Literal["ok"]
    migrations: Literal["ok"]
    files: Literal["ok"]
    keys: Literal["ok"]


class ReadyOut(BaseModel):
    status: Literal["ready"]
    checks: ReadyChecksOut


class NotReadyOut(BaseModel):
    """The 503 body when a readiness check fails; a plain JSON body, not a problem (BS1-D-10)."""

    status: Literal["not_ready"]
    failed: list[CheckName]
