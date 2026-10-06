"""T-PLT-31 rule 3 (04 rev 1.59; D-98 candidate 125): the effective catalogue relation.

``registry_parameter`` is append-only with primary key ``code``; a correction of a seeded row's
metadata is appended to T-PLT-47 ``registry_parameter_correction`` as a complete snapshot by a
governed revision. The effective row of a code takes ``value_schema``, ``description``,
``source_ref`` and ``section`` from its latest correction when one exists (COALESCE over the seed)
and every behavioural column from the seed. This ONE selectable serves the catalogue list, its
filters, its search and its pagination (API-R-13) — never the seed table directly — so a corrected
section or description is filtered and searched as advertised (Codex 0408).
"""

from __future__ import annotations

from typing import Final

import sqlalchemy as sa

from erev_api.db.tables.platform import registry_parameter, registry_parameter_correction

__all__ = ["EFFECTIVE_REGISTRY_PARAMETER", "LATEST_CORRECTION", "METADATA_COLUMNS"]

# The four correctable metadata columns (04 T-PLT-47); every other column is behavioural.
METADATA_COLUMNS: Final = ("value_schema", "description", "source_ref", "section")

# One row per code: its highest correction_no (PostgreSQL DISTINCT ON).
LATEST_CORRECTION: Final = (
    sa.select(
        registry_parameter_correction.c.code,
        *(registry_parameter_correction.c[name] for name in METADATA_COLUMNS),
    )
    .distinct(registry_parameter_correction.c.code)
    .order_by(
        registry_parameter_correction.c.code,
        registry_parameter_correction.c.correction_no.desc(),
    )
    .subquery("latest_correction")
)

EFFECTIVE_REGISTRY_PARAMETER: Final = (
    sa.select(
        *(column for column in registry_parameter.c if column.name not in METADATA_COLUMNS),
        *(
            sa.func.coalesce(LATEST_CORRECTION.c[name], registry_parameter.c[name]).label(name)
            for name in METADATA_COLUMNS
        ),
    )
    .select_from(
        registry_parameter.outerjoin(
            LATEST_CORRECTION, LATEST_CORRECTION.c.code == registry_parameter.c.code
        )
    )
    .subquery("effective_registry_parameter")
)
