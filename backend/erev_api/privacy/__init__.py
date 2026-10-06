"""Privacy kernel module (05 §6.17 PRV-01 to PRV-08; BUILD_SPEC SOP-5).

``erev_api.privacy.CLASSIFICATION`` is the 05 PRV-01 data-classification catalogue over every column
of docs/04-DATA_MODEL.md (``classification.py``). ``erev_api.privacy.patterns`` holds the PRV-08
e-mail and phone patterns and the ``[email]`` / ``[phone]`` replacement used before any AI provider
call (REQ-AI-009). The PRV-07 erasure commands live in ``erev_api.domain.platform.privacy``.
"""

from __future__ import annotations

from erev_api.privacy.classification import (
    CLASSIFICATION,
    PERSONAL_COLUMN_PATTERN,
    TABLE_CLASSIFICATION,
    TABLES,
    Basis,
    ColumnClassification,
    CoverageReport,
    DataClass,
    Erasure,
    PendingSource,
    Recipient,
    Retention,
    Status,
    TableClassification,
    check_coverage,
    columns_of,
    data_class,
)

__all__ = [
    "CLASSIFICATION",
    "PERSONAL_COLUMN_PATTERN",
    "TABLES",
    "TABLE_CLASSIFICATION",
    "Basis",
    "ColumnClassification",
    "CoverageReport",
    "DataClass",
    "Erasure",
    "PendingSource",
    "Recipient",
    "Retention",
    "Status",
    "TableClassification",
    "check_coverage",
    "columns_of",
    "data_class",
]
