"""Demo tenant catalogue WLD-T-00 to WLD-T-07 (docs/02-PRD.md §2.4, WLD-R-03; BUILD_SPEC WEB-10).

Each demo tenant is ``production`` with ``is_demo`` true and reporting currency USD, and belongs to
one persona group of the PRD §2.3 table. ``select_codes`` resolves ``--tenants``: ``all`` or
comma-separated catalogue codes, in catalogue order. No other code is accepted, so the seed never
touches ``perf-volume`` or a ``perf-run-*`` sandbox (DG-PERF-06).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from erev_api.domain.demo import SeedRefused
from erev_api.domain.demo.personas import TenantGroup

ALL: Final = "all"
REPORTING_CURRENCY: Final = "USD"


@dataclass(frozen=True, slots=True)
class DemoTenant:
    wld_id: str
    code: str
    display_name: str
    group: TenantGroup


CATALOGUE: Final[tuple[DemoTenant, ...]] = (
    DemoTenant("WLD-T-00", "legacy-parity", "Legacy parity pack (Demo)", "legacy"),
    DemoTenant("WLD-T-01", "avenmoor", "Avenmoor Holdings (Demo)", "journey"),
    DemoTenant("WLD-T-02", "fernhill", "Fernhill Software, Inc. (Demo)", "industry"),
    DemoTenant("WLD-T-03", "bracken", "Bracken Robotics Corp. (Demo)", "industry"),
    DemoTenant("WLD-T-04", "granitefield", "Granitefield Engineering Group (Demo)", "industry"),
    DemoTenant("WLD-T-05", "juniper-street", "Juniper Street Coffee Co. (Demo)", "industry"),
    DemoTenant("WLD-T-06", "riverbend", "Riverbend Health System (Demo)", "industry"),
    DemoTenant("WLD-T-07", "wayfarer", "Wayfarer Marketplace (Demo)", "industry"),
)


def catalogue() -> tuple[DemoTenant, ...]:
    """The catalogue as it stands now (tests extend it with a fresh code)."""
    return CATALOGUE


def select_codes(text: str) -> tuple[str, ...]:
    """The tenant codes of ``--tenants`` in catalogue order; ``SeedRefused`` for any other code."""
    known = [tenant.code for tenant in catalogue()]
    if text.strip() == ALL:
        return tuple(known)
    codes = [part.strip() for part in text.split(",") if part.strip()]
    unknown = sorted({code for code in codes if code not in known})
    if not codes or unknown:
        named = ", ".join(unknown) if unknown else "none"
        raise SeedRefused(
            f"Unknown demo tenant codes: {named}. Use all or comma-separated codes of "
            f"{', '.join(known)}."
        )
    return tuple(code for code in known if code in codes)


def by_codes(codes: Sequence[str]) -> list[DemoTenant]:
    """The catalogue tenants of ``codes`` in catalogue order; ``SeedRefused`` for any other code."""
    return [tenant for tenant in catalogue() if tenant.code in select_codes(",".join(codes))]
