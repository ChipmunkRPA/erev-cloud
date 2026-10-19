"""Verified application order for replaying published scenario inputs."""

from collections.abc import Mapping
from typing import Any

from erev_api.problems import Problem


def sequence(values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Require every file and command exactly once, in each source list's own order.

    Legacy empty sets can acquire an empty sequence. Populated sets without order evidence
    cannot be replayed or extended: timestamps do not prove transactional application order.
    """
    commands = values["api_commands"]
    uploads = values["import_upload_ids"]
    entries = values.get("input_sequence")
    if entries is None and not commands and not uploads:
        return []
    if not isinstance(entries, list):
        raise Problem(
            "invalid-transition",
            "Input order is unavailable. Create a forecast input set with a new code.",
        )
    command_index = 0
    upload_index = 0
    for entry in entries:
        valid = False
        if isinstance(entry, dict):
            if entry.get("kind") == "API_COMMAND" and set(entry) == {"kind", "index"}:
                valid = (
                    type(entry["index"]) is int
                    and entry["index"] == command_index
                    and command_index < len(commands)
                )
                command_index += 1
            elif entry.get("kind") == "IMPORT_UPLOAD" and set(entry) == {"kind", "id"}:
                valid = upload_index < len(uploads) and entry["id"] == str(uploads[upload_index])
                upload_index += 1
        if not valid:
            raise Problem(
                "validation-failed", "The forecast input order does not match its captured inputs."
            )
    if command_index != len(commands) or upload_index != len(uploads):
        raise Problem("validation-failed", "The forecast input order is incomplete.")
    if len({str(identity) for identity in uploads}) != len(uploads):
        raise Problem("validation-failed", "A forecast input file is listed more than once.")
    return [dict(entry) for entry in entries]
