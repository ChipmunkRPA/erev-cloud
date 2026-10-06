"""05 §2.7 lock budget in the deployment artefacts (DPL-10, DPL-32; SAR-40 ``lock-budget``).

Files only: the loop never runs Docker or Terraform. The rule itself is ``controls.doctor
.lock_budget``; here the shipped settings are held against it with the catalogue figures of
revision 0072, and ``tests/pg/test_lock_budget.py`` holds them against a migrated database.
"""

from __future__ import annotations

import re
from pathlib import Path

from erev_api.controls.doctor import LockBudgetObservation, lock_budget
from support.lock_budget import (
    SETTING,
    VARIABLE,
    compose_max_locks,
    compose_postgres_command,
    terraform_max_locks_default,
    terraform_max_locks_floor,
)
from support.terraform import (
    TERRAFORM_DIR,
    locals_text,
    outputs,
    unquote,
    variable_default,
    variables,
)

ROOT = Path(__file__).resolve().parents[4]
ARCHITECTURE = ROOT / "docs" / "05-ARCHITECTURE.md"
README = TERRAFORM_DIR / "README.md"
# Measured at revision 0072 (lane OPS record): 1 + parent indexes + partitions × (1 + indexes per
# partition) for audit_event, schedule_line and subledger_line; every relation of the database.
FOOTPRINT = {
    "audit_event": 1 + 5 + 181 * 6,
    "schedule_line": 1 + 4 + 181 * 5,
    "subledger_line": 1 + 5 + 181 * 6,
}
RELATIONS = 5044
POSTGRES_DEFAULT = 64
COMPOSE_CONNECTIONS = 100  # the image's max_connections; the compose file does not change it


def _observation(setting: int, connections: int) -> LockBudgetObservation:
    return LockBudgetObservation(setting, connections, 0, sum(FOOTPRINT.values()), RELATIONS)


def _needed(connections: int) -> int:
    required = connections * 4 // 5 * sum(FOOTPRINT.values()) + RELATIONS
    return -(-required // connections)


def test_dpl_10_compose_postgres_starts_with_the_lock_table_setting() -> None:
    # A list command: the image's entrypoint passes it to the init server and the real one alike.
    assert compose_postgres_command() == ["postgres", "-c", f"{SETTING}=4096"]
    assert compose_max_locks() == terraform_max_locks_default() == 4096


def test_dpl_32_cloud_sql_flag_comes_from_a_variable_with_a_floor() -> None:
    assert re.search(rf'"{SETTING}"\s*=\s*tostring\(var\.{VARIABLE}\)', locals_text()), (
        "the flag is set from the variable"
    )
    block = variables()[VARIABLE]
    assert unquote(block.attribute("type")) == "number"
    assert terraform_max_locks_floor() == 3072 <= terraform_max_locks_default()
    (validation,) = block.nested("validation")
    message = unquote(validation.attribute("error_message"))
    assert message is not None and "3072" in message and "§2.7" in message
    budget = outputs()["db_lock_budget"].body
    assert f"var.{VARIABLE} * var.db_max_connections" in budget
    for name in ("staging", "production"):
        example = (TERRAFORM_DIR / "envs" / f"{name}.tfvars.example").read_text(encoding="utf-8")
        assert re.search(rf"(?m)^{VARIABLE}\s*=\s*4096$", example), name


def test_shipped_settings_satisfy_the_rule_with_the_revision_0072_catalogue() -> None:
    assert sum(FOOTPRINT.values()) == 3094
    hosted_connections = int(variable_default("db_max_connections") or 0)
    assert hosted_connections == 600
    # What the rule needs, as 05 §2.7 and the README state it.
    assert (_needed(COMPOSE_CONNECTIONS), _needed(hosted_connections)) == (2526, 2484)
    for connections in (COMPOSE_CONNECTIONS, hosted_connections):
        for setting in (compose_max_locks(), terraform_max_locks_floor()):
            result = lock_budget(_observation(setting, connections))
            assert result.ok, (setting, connections, result.lines())
        # PostgreSQL's default fails, by name, at either size.
        default = lock_budget(_observation(POSTGRES_DEFAULT, connections))
        assert not default.ok and default.lines()[0].startswith("FAIL lock-budget: ")
    # The margin of the shipped value at 100 connections: nine years of window (204 a year) or
    # ten further indexes on partitioned tables (182 each); an eleventh index exceeds it.
    total = sum(FOOTPRINT.values())
    assert lock_budget(LockBudgetObservation(4096, 100, 0, total + 9 * 204, RELATIONS)).ok
    assert lock_budget(LockBudgetObservation(4096, 100, 0, total + 10 * 182, RELATIONS)).ok
    assert not lock_budget(LockBudgetObservation(4096, 100, 0, total + 11 * 182, RELATIONS)).ok


def test_the_documents_state_the_same_arithmetic() -> None:
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    (paragraph,) = [
        line for line in architecture.splitlines() if line.startswith("Lock budget (rev 1.53")
    ]
    for figure in ("1,092", "910", "3,094", "5,044", "2,526", "2,484", "**4096**", "3072", "53200"):
        assert figure in paragraph, figure
    assert "`max_locks_per_transaction × (max_connections + max_prepared_transactions)" in paragraph
    rows = {
        line.split("|")[1].strip(): line
        for line in architecture.splitlines()
        if line.startswith(("| DPL-10 |", "| DPL-32 |", "| SAR-40 |"))
    }
    assert f"{SETTING}=4096" in rows["DPL-10"]
    assert f"`var.{VARIABLE}` (default 4096; the variable refuses less than 3072)" in rows["DPL-32"]
    assert "`lock-budget`" in rows["SAR-40"]
    readme = README.read_text(encoding="utf-8")
    for figure in ("1,092", "910", "3,094", "5,044", "1,490,164", "2,484", "2,526", "2,457,600"):
        assert figure in readme, figure
    assert 480 * 3094 + RELATIONS == 1_490_164 and 4096 * 600 == 2_457_600


def test_the_pool_table_states_the_engines_as_built() -> None:
    """05 section 2.7 rev 1.106 (the supervisor's answer of 2026-10-01 to the lane's note): the
    pool table read ``max_overflow = 5`` and ``pool_recycle = 1800`` for the api, and for the
    worker other sizes than the code has - values the code never had. The table, ``build_engine``,
    the worker's Procrastinate pool and the Terraform variables that budget connections from them
    are held together here, and the Terraform texts say that they agree."""
    import inspect

    from erev_api import worker
    from erev_api.db import session

    engine = inspect.getsource(session.build_engine)
    built = dict(re.findall(r"\n        (pool_\w+|max_overflow)=(\w+),", engine))
    assert built == {
        "pool_size": "10",
        "max_overflow": "10",
        "pool_pre_ping": "True",
        "pool_use_lifo": "True",
    }
    rows = ARCHITECTURE.read_text(encoding="utf-8").splitlines()
    (api,) = [row for row in rows if row.startswith("| api | SQLAlchemy `QueuePool`")]
    assert (
        "| `pool_size = 10`, `max_overflow = 10`, `pool_pre_ping = true`, `pool_use_lifo = true`, "
        "no `pool_recycle` (rev 1.106"
    ) in api
    (jobs,) = [row for row in rows if row.startswith("| worker | Procrastinate")]
    assert (
        "| Procrastinate `min_size = 1`, `max_size = concurrency + 2`; SQLAlchemy as the api's, "
        "`pool_size = 10`, `max_overflow = 10` (rev 1.106"
    ) in jobs
    connector = inspect.getsource(worker)
    assert "min_size=1," in connector and "max_size=settings.worker_concurrency + 2," in connector
    # The Terraform variables carry the same sizes, and their texts no longer name a difference.
    for name in ("api_pool_size", "worker_sqlalchemy_pool_size"):
        assert variable_default(name) == built["pool_size"], name
    for name in ("api_max_overflow", "worker_sqlalchemy_max_overflow"):
        assert variable_default(name) == built["max_overflow"], name
    declared = variables()
    for name in ("api_max_overflow", "worker_sqlalchemy_pool_size"):
        description = unquote(declared[name].attribute("description")) or ""
        assert "which 05 §2.7 states since rev 1.106" in description, name
    main = (TERRAFORM_DIR / "main.tf").read_text(encoding="utf-8")
    assert "the CODE's, which the §2.7 table states since 05" in main
    assert "not the §2.7 table, where they" not in main
    readme = README.read_text(encoding="utf-8")
    assert "05 §2.7 states the same since rev 1.106" in readme
    assert "not the §2.7 table, where they differ" not in readme
