"""Modern CSV v2 templates (04 T-IMP-01 ``CSV_V2``, NC-19; BUILD_SPEC DIN-3, DIN-9).

Each template module flattens the API command request of its target (``framework.flatten``),
groups rows into command plans and applies them through the command services. DIN-3 builds
``customers`` and ``contracts``; DIN-9 adds ``products``, ``bundles``, ``ssp_values``, ``invoices``,
``progress_events``, ``usage``, ``fx_rates``, ``cost_events``, ``pre_standard_revenue``,
``gl_accounts`` and ``account_mapping``; since D-86 it adds ``estimates`` on the CTR-12 estimate
commands. ``modifications`` waits for CTR-17, which R-RC-1 moves post-rc (L5-1-Q-23, D-86), so it
has no emitter and ``POST /imports`` refuses it.

``ROW_MODELS`` are the per-row models validation registers, and ``CROSS_RULES`` the cross-file rules
that read stored state (``CONTRACT_NOT_FOUND`` for the templates that name a contract).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel

from erev_api.approvals import subjects
from erev_api.domain.imports.csv_v2 import (
    account_mapping,
    bundles,
    contracts,
    cost_events,
    customers,
    estimates,
    fx_rates,
    gl_accounts,
    invoices,
    pre_standard_revenue,
    products,
    progress_events,
    ssp_values,
    usage,
)
from erev_api.domain.imports.csv_v2.framework import CsvTemplate
from erev_api.domain.imports.legacy_v1.headers import RowFinding

__all__ = ["CROSS_RULES", "ROW_MODELS", "TEMPLATES"]

_MODULES: Final = (
    customers,
    products,
    bundles,
    ssp_values,
    contracts,
    invoices,
    progress_events,
    usage,
    estimates,
    fx_rates,
    cost_events,
    pre_standard_revenue,
    gl_accounts,
    account_mapping,
)
TEMPLATES: Final[Mapping[str, CsvTemplate]] = MappingProxyType(
    {module.TEMPLATE.code: module.TEMPLATE for module in _MODULES}
)
# 04 §16.10 rev 1.65 (D-98 candidate 135 amendment 1): a CSV v2 template whose target is a contract,
# a contract event or a modification names the contract of each row from its own `key_column` in the
# normalized row — registered with the kernel here (`estimates` targets an estimate version and is
# not registered: its approval revalidates its own basis).
for _module in _MODULES:
    if _module.TEMPLATE.target_type in ("contract", "contract_event", "modification"):
        subjects.register_import_contract_column(_module.TEMPLATE.code, _module.TEMPLATE.key_column)

ROW_MODELS: Final[Mapping[str, type[BaseModel]]] = MappingProxyType(
    {module.TEMPLATE.code: module.ROW_MODEL for module in _MODULES}
)
CROSS_RULES: Final[Mapping[str, Callable[..., Mapping[int, Sequence[RowFinding]]]]] = (
    MappingProxyType(
        {
            module.TEMPLATE.code: module.CROSS_RULE
            for module in (
                invoices,
                progress_events,
                usage,
                estimates,
                cost_events,
                pre_standard_revenue,
                ssp_values,
            )
        }
    )
)
