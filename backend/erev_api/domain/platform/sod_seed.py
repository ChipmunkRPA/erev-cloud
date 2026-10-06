"""Default separation-of-duties rules SoD-1 to SoD-7 (BUILD_SPEC BS1-D-26; 04 T-PLT-13, §14.3).

Provisioning inserts these as PUBLISHED version 1 of each code. They are seed content only:
``erev_api.auth.sod`` reads rules from PUBLISHED ``sod_rule`` rows, never from this module
(DG-KRN-PERM-03). Names are the ERR-22 descriptions and serve as the rationale (SPEC-Q-149).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.auth.permissions import CATALOGUE
from erev_api.db import new_id
from erev_api.enums import ConfigStatus


@dataclass(frozen=True, slots=True)
class SodRuleSeed:
    code: str
    name: str
    function_a: frozenset[str]
    function_b: frozenset[str]


# SoD-1 function A: the six access-administration permissions of T-PLT-11.
ACCESS_ADMINISTRATION: Final = frozenset(p.code for p in CATALOGUE if p.is_access_admin)

DEFAULT_SOD_RULES: Final[tuple[SodRuleSeed, ...]] = (
    SodRuleSeed(
        code="SoD-1",
        name="user administration with transaction or approval permissions",
        function_a=ACCESS_ADMINISTRATION,
        function_b=frozenset(
            {
                "contract.create",
                "contract.approve",
                "contract.void",
                "modification.create",
                "modification.approve",
                "event.record",
                "event.approve",
                "estimate.create",
                "estimate.approve",
                "judgement.create",
                "judgement.review",
                "config.author",
                "config.approve",
                "ssp.create",
                "ssp.approve",
                "adjustment.create",
                "adjustment.approve",
                "journal.run",
                "journal.approve",
                "journal.export",
                "masterdata.maintain",
                "import.upload",
                "import.approve",
                "exception.resolve",
                "exception.waive",
                "period.close",
                "period.lock",
                "period.reopen_request",
                "period.reopen_approve",
                "recon.prepare",
                "recon.signoff",
                "migration.run",
                "migration.approve",
            }
        ),
    ),
    SodRuleSeed(
        code="SoD-2",
        name="creating and approving the same SSP book version",
        function_a=frozenset({"ssp.create"}),
        function_b=frozenset({"ssp.approve"}),
    ),
    SodRuleSeed(
        code="SoD-3",
        name=(
            "Revenue Accountant with Revenue Reviewer lets one person create and approve the same "
            "contract or modification"
        ),
        function_a=frozenset(
            {
                "contract.create",
                "modification.create",
                "event.record",
                "estimate.create",
                "judgement.create",
                "adjustment.create",
                "import.upload",
            }
        ),
        function_b=frozenset(
            {
                "contract.approve",
                "modification.approve",
                "event.approve",
                "estimate.approve",
                "judgement.review",
                "adjustment.approve",
                "import.approve",
            }
        ),
    ),
    SodRuleSeed(
        code="SoD-4",
        name="preparing manual adjustments or journal runs with locking periods",
        function_a=frozenset({"adjustment.create", "journal.run"}),
        function_b=frozenset({"period.lock"}),
    ),
    SodRuleSeed(
        code="SoD-5",
        name="authoring and approving the same configuration",
        function_a=frozenset({"config.author"}),
        function_b=frozenset({"config.approve"}),
    ),
    SodRuleSeed(
        code="SoD-6",
        name="preparing postings with locking or reopening periods",
        function_a=frozenset({"import.upload"}),
        function_b=frozenset({"period.lock"}),
    ),
    SodRuleSeed(
        code="SoD-7",
        name="managing integrations with signing reconciliations",
        function_a=frozenset({"integration.manage"}),
        function_b=frozenset({"recon.signoff"}),
    ),
)


def content_sha256(rule: SodRuleSeed) -> str:
    """SC-V ``content_sha256``: the §5.17 ``sha256_hex`` of the rule content."""
    return sha256_hex(
        {
            "code": rule.code,
            "function_a_permissions": sorted(rule.function_a),
            "function_b_permissions": sorted(rule.function_b),
            "name": rule.name,
            "rationale": rule.name,
        }
    )


def sod_rule_rows(
    tenant_id: UUID, *, stamp: Mapping[str, Any], published_by: UUID | None, published_at: datetime
) -> list[dict[str, Any]]:
    """The seven T-PLT-13 rows of a new tenant: version 1, PUBLISHED, in force from the start."""
    return [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "code": rule.code,
            "name": rule.name,
            "function_a_permissions": sorted(rule.function_a),
            "function_b_permissions": sorted(rule.function_b),
            "rationale": rule.name,
            **stamp,
            "version_no": 1,
            "status": ConfigStatus.PUBLISHED.value,
            "effective_from": None,
            "effective_to": None,
            "content_sha256": content_sha256(rule),
            "approval_request_id": None,
            "published_at": published_at,
            "published_by": published_by,
            "supersedes_version_id": None,
        }
        for rule in DEFAULT_SOD_RULES
    ]
