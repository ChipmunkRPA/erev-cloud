"""``erev db reset``: what makes a database a development database (dev-guide DG-ENV-13 rev
1.200, DG-MK-db-reset; supervisor ruling R-120 (i)).

The command drops schema ``erev`` of the database the environment names. Three things together
make that a development database, and the command names the one that does not hold:

- the environment's name: ``EREV_ENV=dev``;
- the database's name: ``erev`` or an ``erev_rv_*`` database - a review database or a lane's own
  (DG-ENV-13) - and never ``erev_test`` or ``erev_e2e``, which their gates rebuild; the server
  must answer the same name for ``current_database()``;
- its tenants: none lacks the demo marker (``tenant.is_demo``; 02 WLD-R-04). A sandbox is always
  created without the marker and counts by its source tenant. A database without the ``tenant``
  table holds no tenant. Where the table exists and the tenants cannot be counted, the command
  refuses: it does not reset what it could not judge.

The tenants are counted through ``platform_session("tenant_directory")`` as the application role:
``erev_owner`` is under the tables' policies like every role, and the platform session is the one
door across tenants (05 TXN-07).
"""

from __future__ import annotations

import re
from typing import Final

from sqlalchemy import Connection, case, false, func, not_, select

from erev_api.auth.keyring import KeyRing
from erev_api.config import Environment
from erev_api.db.session import platform_session
from erev_api.db.tables import tenant
from erev_api.enums import TenantKind

# The names `erev db reset` may reset: a subset of the DG-ENV-13 allow-list.
RESETTABLE: Final = re.compile(r"^(erev|erev_rv_[a-z0-9_]+)$")
REQUEST_ID: Final = "cli-db-reset"


def refused_before_connecting(env: Environment, database: str) -> str | None:
    """The refusal the environment's name or the database's name gives, else None."""
    if env is not Environment.DEV:
        return f"erev db reset runs only with EREV_ENV=dev; this environment is {env.value}"
    if RESETTABLE.fullmatch(database) is None:
        return (
            "erev db reset resets a development database, erev or erev_rv_*; "
            f"the environment names {database}"
        )
    return None


def refused_by_server(database: str, answered: str) -> str | None:
    """The refusal when the server is connected to another database than the one named."""
    if answered != database:
        return f"refusing to reset: the server answers database {answered}, not {database}"
    return None


def refused_for_tenants(database: str, unmarked: int) -> str | None:
    """The refusal when a tenant of the database lacks the demo marker."""
    if unmarked:
        return (
            f"refusing to reset {database}: {unmarked} tenant(s) carry no demo marker, so it is "
            "not a development database"
        )
    return None


def tenant_table_exists(connection: Connection) -> bool:
    """Whether the database holds the ``tenant`` table at all (a fresh or a dropped schema does
    not)."""
    return bool(connection.execute(select(func.to_regclass("erev.tenant").is_not(None))).scalar())


def unmarked_tenants(*, keyring: KeyRing, request_id: str = REQUEST_ID) -> int:
    """The tenants that lack the demo marker: a tenant with ``is_demo`` false, and a sandbox
    whose source tenant has it false or is gone."""
    source = tenant.alias("source")
    marked = case(
        (tenant.c.kind == TenantKind.SANDBOX.value, func.coalesce(source.c.is_demo, false())),
        else_=tenant.c.is_demo,
    )
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=request_id, keyring=keyring
    ) as db:
        return int(
            db.execute(
                select(func.count())
                .select_from(tenant.outerjoin(source, source.c.id == tenant.c.source_tenant_id))
                .where(not_(marked))
            ).scalar_one()
        )
