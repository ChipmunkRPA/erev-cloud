"""Reviewed prompt-file digests (AIA-08). Existing entries are append-only.

Changes to a retained template require a new version and a new manifest entry.
Program change review must preserve every previously published version and digest.
"""

from types import MappingProxyType

TEMPLATE_SHA256 = MappingProxyType(
    {
        ("explain-narrative", 1): (
            "7063b8a3787bac670b97e0ec43649ce12695369ca22279281a9f0b63197c62f1"
        ),
        ("contract-review", 1): "4de950f30eada9f839897c8daf6e8bbbcacc5ba57eb02841adec1cf86686593f",
    }
)
