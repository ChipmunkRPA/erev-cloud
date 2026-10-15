"""Reviewed prompt-file digests (AIA-08). Existing entries are append-only.

Changes to a retained template require a new version and a new manifest entry.
Program change review must preserve every previously published version and digest.
"""

from types import MappingProxyType

TEMPLATE_SHA256 = MappingProxyType(
    {
        ("contract-review", 1): "4de950f30eada9f839897c8daf6e8bbbcacc5ba57eb02841adec1cf86686593f",
    }
)
