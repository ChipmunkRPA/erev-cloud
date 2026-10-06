"""The industry demo tenants WLD-T-02 to WLD-T-07 (PRD §2.4, §2.10; BUILD_SPEC RFD-17, BS3-D-10).

``reference`` builds each tenant's structure (calendar, currencies, entities and books, opened
periods), its chart of accounts and account mapping, Riverbend's published engine billing policy
(D-14a) and the cluster's DRAFT industry templates and policy version
(``create_industry_templates``, BR-POL-03). The PRD §2.3 personas act as in the Avenmoor builders,
the approver always another persona (WLD-R-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from erev_api.domain.demo.avenmoor import ACCOUNTANT, CONTROLLER, TENANT_ADMIN

__all__ = ["ACCOUNTANT", "CLUSTER_BY_WLD", "CONTROLLER", "TENANT_ADMIN"]

# PRD §2.4 cluster column (research 05 §26).
CLUSTER_BY_WLD: Final[Mapping[str, str]] = MappingProxyType(
    {
        "WLD-T-02": "D01",
        "WLD-T-03": "D02",
        "WLD-T-04": "D04",
        "WLD-T-05": "D05",
        "WLD-T-06": "D08",
        "WLD-T-07": "D12",
    }
)
