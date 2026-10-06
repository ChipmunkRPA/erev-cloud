"""Numbering series KRN-NUM (dev-guide §5.14; 04 T-PLT-26, NC-13).

Provisioning writes one row per series code except ``JE`` (04 §14.3); the ``JE`` series exists per
entity (``ensure_entity_series``). Allocation is one ``UPDATE … RETURNING`` inside the caller's
transaction, so the numbers belong to that transaction and a rollback releases them
(DG-KRN-NUM-01, DG-KRN-NUM-02). Gapless series are allocated as late as practical by the caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from erev_api.db import new_id
from erev_api.db.tables.platform import numbering_series

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

# 04 T-PLT-26: series codes and prefixes, in catalogue order.
SERIES_PREFIXES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "CONTRACT": "CON-",
        "MODIFICATION": "MOD-",
        "APPROVAL": "APR-",
        "IMPORT": "IMP-",
        "JOURNAL_RUN": "JR-",
        "JE": "JE-",
        "ADJUSTMENT": "ADJ-",
        "RECONCILIATION": "REC-",
        "REPORT_RUN": "RPT-",
        "CLOSE_RUN": "CLS-",
        "EXCEPTION": "EXC-",
        "EVIDENCE_PACK": "EVP-",
        "MIGRATION": "MIG-",
        "JUDGEMENT": "JDG-",
    }
)
ENTITY_SERIES: Final = "JE"  # numbered per tenant and entity (scope_key = entity id)
PADDING: Final = 6

_ALLOCATE = text(
    "UPDATE erev.numbering_series SET next_value = next_value + :k "
    "WHERE tenant_id = :tenant_id AND series_code = :series_code AND scope_key = :scope_key "
    "RETURNING next_value - :k AS first_value, prefix, padding"
)


def tenant_series_rows(tenant_id: UUID, *, stamp: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The 04 §14.3 rows: every T-PLT-26 code except ``JE``, from 1, padding 6, not gapless."""
    updated = {key: stamp[key] for key in ("updated_at", "updated_by", "updated_by_kind")}
    return [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "series_code": code,
            "scope_key": "",
            "prefix": prefix,
            "next_value": 1,
            "padding": PADDING,
            "is_gapless": False,
            **updated,
        }
        for code, prefix in SERIES_PREFIXES.items()
        if code != ENTITY_SERIES
    ]


def next_numbers(uow: UnitOfWork, series_code: str, count: int, scope_key: str = "") -> list[str]:
    """``count`` consecutive numbers of a series, formatted ``prefix + value.zfill(padding)``."""
    return allocate(uow.session, uow.principal.tenant_id, series_code, count, scope_key)


def allocate(
    session: Session, tenant_id: UUID, series_code: str, count: int, scope_key: str = ""
) -> list[str]:
    """``next_numbers`` on a session without a unit of work (provisioning, 04 §14.3)."""
    if count < 1:
        raise ValueError("count must be at least 1")
    row = session.execute(
        _ALLOCATE,
        {
            "k": count,
            "tenant_id": tenant_id,
            "series_code": series_code,
            "scope_key": scope_key,
        },
    ).one_or_none()
    if row is None:
        raise LookupError(f"numbering series {series_code!r} does not exist for this tenant")
    first, prefix, padding = int(row.first_value), str(row.prefix), int(row.padding)
    return [prefix + str(first + offset).zfill(padding) for offset in range(count)]


def next_number(uow: UnitOfWork, series_code: str, scope_key: str = "") -> str:
    """The next number of a series (DG-KRN-NUM-01)."""
    return next_numbers(uow, series_code, 1, scope_key)[0]


def ensure_entity_series(uow: UnitOfWork, entity_id: UUID, entity_code: str) -> None:
    """The gapless ``JE`` series of an entity, numbering ``JE-<entity code>-000001`` (T-SL-08).

    The entity code joins the stored prefix, so allocation needs no entity lookup (SPEC-Q-165).
    An existing series is left unchanged.
    """
    principal = uow.principal
    statement = (
        insert(numbering_series)
        .values(
            tenant_id=principal.tenant_id,
            id=new_id(),
            series_code=ENTITY_SERIES,
            scope_key=str(entity_id),
            prefix=f"{SERIES_PREFIXES[ENTITY_SERIES]}{entity_code}-",
            next_value=1,
            padding=PADDING,
            is_gapless=True,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "series_code", "scope_key"])
    )
    uow.session.execute(statement)
