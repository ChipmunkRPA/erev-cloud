"""Legacy v1 template emitters (04 T-IMP-01 ``LEGACY_V1``, §17.3, §17.4; ENGINE_SPEC §1.4 S01-R-05
to S01-R-09; BUILD_SPEC DIN-4 to DIN-6).

Each module groups the validated rows of its template into command plans and applies them through
the command services, in the ``csv_v2.framework.CsvTemplate`` shape the dry-run diff and the commit
run. ``ROW_RULES`` are the template rules of table 15.4-A that read one row, and ``CROSS_RULES`` the
cross-row and cross-file rules that read stored state (L4-1-Q-28). DIN-4 builds ``legacy_sku_ssp``
and ``legacy_contract_setup``, DIN-5 ``legacy_progress_tracking`` and DIN-6
``legacy_contract_modification``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final

from erev_api.approvals import subjects
from erev_api.domain.imports import legacy_templates
from erev_api.domain.imports.csv_v2.framework import CsvTemplate
from erev_api.domain.imports.legacy_v1 import (
    contract_setup,
    headers,
    modification,
    progress,
    sku_ssp,
)

__all__ = ["CROSS_RULES", "ROW_RULES", "TEMPLATES", "CrossRule", "RowRule"]

type RowRule = Callable[[Mapping[str, Any]], Sequence[headers.RowFinding]]
# (session, [(row number, normalized row)], *, known_at, parameters) -> findings by row number
type CrossRule = Callable[..., Mapping[int, Sequence[headers.RowFinding]]]

TEMPLATES: Final[Mapping[str, CsvTemplate]] = MappingProxyType(
    {
        module.TEMPLATE.code: module.TEMPLATE
        for module in (sku_ssp, contract_setup, progress, modification)  # DIN-4 to DIN-6
    }
)
# 04 §16.10 rev 1.65 (D-98 candidate 135 amendment 1): the contract-keyed legacy templates name the
# contract of each row from the normalized `Contract Unique Name` column — registered with the
# kernel here, so `approvals.subjects.import_contract_keys` never parses the display business key.
for _module in (contract_setup, progress, modification):
    subjects.register_import_contract_column(_module.TEMPLATE.code, legacy_templates.CONTRACT)

ROW_RULES: Final[Mapping[str, tuple[RowRule, ...]]] = MappingProxyType(
    {
        sku_ssp.CODE: sku_ssp.ROW_RULES,
        contract_setup.CODE: contract_setup.ROW_RULES,
        progress.CODE: progress.ROW_RULES,
        modification.CODE: modification.ROW_RULES,
    }
)
CROSS_RULES: Final[Mapping[str, CrossRule]] = MappingProxyType(
    {
        sku_ssp.CODE: sku_ssp.cross_findings,  # DIN-7
        contract_setup.CODE: contract_setup.cross_findings,
        progress.CODE: progress.cross_findings,
        modification.CODE: modification.cross_findings,
    }
)
