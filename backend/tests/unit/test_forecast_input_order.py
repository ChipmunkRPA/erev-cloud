"""Replay rejects missing or ambiguous input order instead of rearranging financial facts."""

from uuid import uuid4

import pytest
from erev_api.domain.forecast.input_order import sequence
from erev_api.problems import Problem


def test_legacy_populated_set_has_no_inferred_order() -> None:
    with pytest.raises(Problem, match="unavailable"):
        sequence({"api_commands": [{}], "import_upload_ids": [uuid4()], "input_sequence": None})
    assert sequence({"api_commands": [], "import_upload_ids": [], "input_sequence": None}) == []


@pytest.mark.parametrize(
    "entries",
    [
        [{"kind": "API_COMMAND", "index": True}],
        [{"kind": "API_COMMAND", "index": 1}, {"kind": "API_COMMAND", "index": 0}],
        [{"kind": "API_COMMAND", "index": 0}, {"kind": "API_COMMAND", "index": 0}],
    ],
)
def test_invalid_command_order_cannot_be_published(entries: list[dict[str, object]]) -> None:
    with pytest.raises(Problem):
        sequence({"api_commands": [{}, {}], "import_upload_ids": [], "input_sequence": entries})


def test_missing_file_cannot_silently_disappear_from_replay() -> None:
    with pytest.raises(Problem, match="incomplete"):
        sequence({"api_commands": [], "import_upload_ids": [uuid4()], "input_sequence": []})
