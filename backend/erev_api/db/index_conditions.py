"""Index keys a row-level-security policy can use (04 NC-20 and §1.4 "Index conditions under a
policy", rev 1.181; dev-guide DG-KRN-DB-10; supervisor ruling R-116; item PERF-RLS-INDEX-1).

Under a policy PostgreSQL makes a caller's condition an index condition only when the function
behind its operator is leakproof; any other condition is evaluated after the policy, row by row.
The comparisons of ``uuid``, ``text``, the integers, ``date``, ``timestamptz`` and ``boolean``
are leakproof. Those of an enumeration, of ``numeric``, of arrays and of ``jsonb`` are not, and
only a superuser can mark a function leakproof. So in the key of an index of a table with a
policy a column of the second kind bounds no scan — and neither does any column BEHIND it,
whatever its type. Such an index is built, looks right in its revision and is entered by the
columns in front of that one alone; the cost shows only at volume.

``findings`` reads the catalogue (no table is read) and names every index of a table with a
policy that

- is not a b-tree, or has an expression in its key: no condition of ``erev_app`` this check can
  vouch for bounds it;
- has a key column the policy lets bound a scan BEHIND one it does not; or
- has nothing but ``tenant_id`` in front of the first column it does not: the index is entered
  by the tenant alone.

An index that is meant so is in ``ALLOWED`` with its reason: the columns in front select a
handful of rows, the key only keeps rows unique, or the order waits for the table's next
revision. An entry whose index has no finding any more is a finding itself, so the list cannot
outlive its reasons.

``backend/tests/pg/test_index_conditions.py`` holds the migrated schema to this, and under
``EREV_ENV=production`` ``erev doctor`` runs ``findings`` on the deployed schema as its check
``index-conditions`` (05 SAR-40 rev 1.156; ``controls.doctor.observe_index_conditions``): a
finding there is a warning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from sqlalchemy import Connection, text

__all__ = ["ALLOWED", "IndexFinding", "findings", "reason"]

TENANT: Final = "tenant_id"
BTREE: Final = "btree"

# Every index of a table with a policy: its key columns in order (NULL for an expression) and,
# for each, whether the equality of its operator class is leakproof. Strategy 3 is the b-tree's
# equality; an index of another access method is a finding before its columns are looked at.
_INDEXES: Final = text(
    """
    SELECT c.relname AS table_name,
           i.relname AS index_name,
           am.amname AS method,
           key.columns,
           key.leakproof
    FROM pg_index x
    JOIN pg_class i ON i.oid = x.indexrelid
    JOIN pg_am am ON am.oid = i.relam
    JOIN pg_class c ON c.oid = x.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL (
        SELECT array_agg(a.attname::text ORDER BY k.position) AS columns,
               array_agg(
                   a.attname IS NOT NULL AND coalesce(equality.proleakproof, false)
                   ORDER BY k.position
               ) AS leakproof
        FROM unnest(x.indkey::int2[]) WITH ORDINALITY AS k (attnum, position)
        LEFT JOIN pg_attribute a
               ON a.attrelid = x.indrelid AND a.attnum = k.attnum AND k.attnum <> 0
        LEFT JOIN LATERAL (
            SELECT p.proleakproof
            FROM pg_opclass oc
            JOIN pg_amop ao
              ON ao.amopfamily = oc.opcfamily
             AND ao.amoplefttype = oc.opcintype
             AND ao.amoprighttype = oc.opcintype
             AND ao.amopstrategy = 3
            JOIN pg_operator o ON o.oid = ao.amopopr
            JOIN pg_proc p ON p.oid = o.oprcode
            WHERE oc.oid = x.indclass[k.position - 1]
        ) AS equality ON true
        WHERE k.position <= x.indnkeyatts
    ) AS key
    WHERE n.nspname = 'erev'
      AND c.relkind IN ('r', 'p')
      AND c.relrowsecurity
      AND NOT c.relispartition
    ORDER BY c.relname, i.relname
    """
)

_FEW_A_TENANT: Final = "at most three rows a tenant: nothing to bound"
_NEXT_REVISION: Final = "reorder with the table's next revision"
# Index name -> why its key may stand as it is (04 §1.4, rev 1.181). The second group is what
# ruling R-116 (c) leaves for the next revision of each table: bounded by one entity's or one
# contract's rows today.
ALLOWED: Final[Mapping[str, str]] = MappingProxyType(
    {
        # --- meant so ---------------------------------------------------------------------
        "ux_book__code": _FEW_A_TENANT,
        "ledger_chain_head_pkey": _FEW_A_TENANT,
        "ix_tenant_snapshot__status": "tens of rows a tenant",
        "ux_registry_version__no": (
            "the versions of the registry, tens of rows a tenant; the key keeps a version number "
            "unique in its category, scope, book and entity"
        ),
        "ux_close_run__active": (
            "partial on the live statuses already — a handful of rows; the key keeps the live "
            "run of a period unique"
        ),
        "ix_disclosure_snapshot__period": "one entity's snapshots, a few a period",
        "ux_schedule_line__subject_period": (
            "one schedule and one subject select the rows; line_type and period_id keep them unique"
        ),
        "ux_signoff__signer": (
            "one subject selects the rows; role and signer keep a signature unique"
        ),
        "ux_ssp_range__band": (
            "an expression that keeps the bands of an entry unique; never a read condition"
        ),
        "ux_ssp_entry__key": (
            "the book version and the product select the rows; the expressions keep an entry "
            "unique where a dimension is absent"
        ),
        "ux_policy_override__active": (
            "the contract selects the rows, among the APPROVED ones; the expression and the "
            "policy key keep the active override of a contract or an obligation unique"
        ),
        "ux_estimate__code": (
            "the expression — the contract, or else the portfolio — keeps an element code unique "
            "in either; no read binds it"
        ),
        # --- R-116 (c): bounded per entity or per contract --------------------------------
        "ix_fx_rate__lookup": (
            "no read filters fx_rate by rate_type (rates are read by id and by set version); "
            "rate_type goes last when that lookup is written"
        ),
        "ix_journal_run__period": f"bounded by one entity's runs; {_NEXT_REVISION}",
        "ix_period_lock__period": f"bounded by one entity's locks; {_NEXT_REVISION}",
        "ix_reconciliation__period": (f"bounded by one entity's reconciliations; {_NEXT_REVISION}"),
        "ix_manual_adjustment__period": (f"bounded by one entity's adjustments; {_NEXT_REVISION}"),
        "ux_close_checklist_item__period": (
            f"bounded by one template's items of an entity; {_NEXT_REVISION}"
        ),
        "ux_contract_version__no": f"bounded by one group's versions; {_NEXT_REVISION}",
        "ix_contract_version__known": f"bounded by one group's versions; {_NEXT_REVISION}",
        "ix_obligation_version__contract": (
            f"bounded by one contract's obligation versions; {_NEXT_REVISION}"
        ),
        "ix_obligation_version__obligation": (
            f"bounded by one obligation's versions; {_NEXT_REVISION}"
        ),
        "ix_judgement_record__status": (
            "the review queue reads SUBMITTED records, a few a contract; a partial index on "
            "that value if the read is measured slow"
        ),
        "ix_estimate_version__status": (
            "the review queue reads SUBMITTED versions, a few a contract; a partial index on "
            "that value if the read is measured slow"
        ),
        "ix_contract__status": (
            "ACTIVE is most of the table, which no index helps; a partial index on DRAFT only "
            "if the drafts list proves hot"
        ),
    }
)


@dataclass(frozen=True, slots=True)
class IndexFinding:
    table: str
    index: str
    message: str

    def __str__(self) -> str:
        return f"{self.table}.{self.index}: {self.message}"


def reason(method: str, columns: Sequence[str | None], leakproof: Sequence[bool]) -> str | None:
    """Why an index key cannot serve as it stands, or None. ``columns`` are the key columns in
    order — None for an expression — and ``leakproof`` says of each whether a condition on it
    can bound a scan under a policy."""
    if method != BTREE:
        return f"access method {method}: no condition of erev_app is known to bound it"
    if None in columns:
        return "an expression in the key bounds no scan this check can vouch for"
    names = [str(column) for column in columns]
    unusable = [position for position, usable in enumerate(leakproof) if not usable]
    if not unusable:
        return None
    first = unusable[0]
    behind = [names[position] for position in range(first + 1, len(names)) if leakproof[position]]
    if behind:
        return (
            f"{', '.join(behind)} stand{'s' if len(behind) == 1 else ''} behind {names[first]}, "
            "whose comparison is not leakproof: under the policy neither bounds a scan"
        )
    if all(name == TENANT for name in names[:first]):
        return (
            f"nothing but the tenant stands in front of {names[first]}, whose comparison is not "
            "leakproof: the index is entered by the tenant alone"
        )
    return None


def findings(connection: Connection) -> list[IndexFinding]:
    """The indexes of tables with a policy whose key the policy cannot use and ``ALLOWED`` does
    not name, and the entries of ``ALLOWED`` that name no such index; empty when the schema
    passes. Reads the catalogue only, so any role may run it."""
    found: dict[str, IndexFinding] = {}
    for row in connection.execute(_INDEXES):
        message = reason(str(row.method), list(row.columns), list(row.leakproof))
        if message is not None:
            found[str(row.index_name)] = IndexFinding(
                str(row.table_name), str(row.index_name), message
            )
    unlisted = [finding for name, finding in found.items() if name not in ALLOWED]
    stale = [
        IndexFinding("-", name, "listed in ALLOWED, but its key has no finding: remove the entry")
        for name in ALLOWED
        if name not in found
    ]
    return sorted(unlisted + stale, key=lambda finding: (finding.table, finding.index))
