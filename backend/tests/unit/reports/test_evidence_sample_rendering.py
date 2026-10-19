"""Evidence values must survive workbook limits and the PDF standard font."""

import json

from erev_api.domain.reports.evidence_sample_rendering import CELL_CHARS, _rows


def test_exact_values_and_long_unicode_text_are_reconstructable() -> None:
    original = {
        "amount": "35669.7200000000000001",
        "empty": [],
        "null": None,
        "a/b~c": "合同\n" + "x" * (CELL_CHARS * 2),
        "formula": "=1+1",
    }
    rows = _rows(original)
    restored = {}
    for key in original:
        pointer = "/" + key.replace("~", "~0").replace("/", "~1")
        parts = sorted((row for row in rows if row["pointer"] == pointer), key=lambda r: r["part"])
        assert all(len(row["value"]) <= CELL_CHARS for row in parts)
        restored[key] = json.loads("".join(row["value"] for row in parts))
    assert restored == original
    assert len({row["row_key"] for row in rows}) == len(rows)
