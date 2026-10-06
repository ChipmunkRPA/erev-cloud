"""The lock-table settings the deployment artefacts ship (05 §2.7 lock budget; DPL-10, DPL-32).

Read from the files, never from a running server: ``deploy/compose.yaml`` starts the compose
PostgreSQL with ``max_locks_per_transaction`` on its command line, and the Terraform variable
``db_max_locks_per_transaction`` sets the Cloud SQL flag and refuses a value under its floor.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from support.terraform import variable_default, variables

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "deploy" / "compose.yaml"
SETTING = "max_locks_per_transaction"
VARIABLE = "db_max_locks_per_transaction"


def compose_postgres_command() -> list[str]:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    command = document["services"]["postgres"]["command"]
    assert isinstance(command, list), "the postgres command is a list (no shell)"
    return [str(part) for part in command]


def compose_max_locks() -> int:
    """The ``-c max_locks_per_transaction=<n>`` of the compose ``postgres`` service."""
    command = compose_postgres_command()
    settings = [
        command[index + 1].split("=", 1)
        for index, part in enumerate(command[:-1])
        if part == "-c" and command[index + 1].startswith(f"{SETTING}=")
    ]
    assert len(settings) == 1, command
    return int(settings[0][1])


def terraform_max_locks_default() -> int:
    value = variable_default(VARIABLE)
    assert value is not None, f"{VARIABLE} has a default"
    return int(value)


def terraform_max_locks_floor() -> int:
    """The smallest value the variable's validation admits."""
    (validation,) = variables()[VARIABLE].nested("validation")
    condition = validation.attribute("condition")
    assert condition is not None
    match = re.fullmatch(
        rf"var\.{VARIABLE} >= (\d+) && floor\(var\.{VARIABLE}\) == var\.{VARIABLE}", condition
    )
    assert match is not None, condition
    return int(match.group(1))
