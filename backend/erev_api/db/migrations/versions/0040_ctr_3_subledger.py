"""BUILD_SPEC item CTR-3: subledger postings, seals and ledger chains.

04 ids created: E-29 ``subledger_entry_kind`` and E-31 ``subledger_posting_kind``.

- T-SL-03 ``ledger_chain_head`` (IM-X, RLS-T): primary key ``(tenant_id, book_code)`` and the checks
  ``ck_ledger_chain_head__last_chain_seq`` and ``ck_ledger_chain_head__seal``. Provisioning writes
  one row per book (04 §14.3; BS-D-12).
- T-SL-01 ``subledger_posting`` (IM-A, RLS-T): ``ux_subledger_posting__idempotency``,
  ``ix_subledger_posting__group``, the check ``ck_subledger_posting__source`` (the "Required for"
  notes of T-SL-01) and the foreign keys to ``combination_group``, ``contract_computation`` and
  itself; DB-06 (3) ``tg_subledger_posting__sealed``, a deferred constraint trigger
  (``EREV-LED-002``).
- T-SL-04 ``subledger_line`` (IM-A, RLS-TE on ``entity_id``, PT-MPE): monthly partitions from
  2018-01 to 2032-12 and the default partition (DG-MIG-10); ``ix_subledger_line__ledger``,
  ``__contract``, ``__posting`` and ``__schedule``; the 04 checks
  ``ck_subledger_line__reserved_role`` and ``__clearing_purpose`` and the checks of the column
  notes; the generated ``dr_cr``; the foreign keys to the posting, ``legal_entity``, ``period``,
  ``gl_account``, ``currency``, ``fx_rate_set_version``, ``fx_rate``, ``contract``, ``obligation``,
  ``contract_version``, ``contract_event`` and ``calc_trace``. DB-06 (1)
  ``tg_subledger_line__insert`` (``EREV-LED-002``, ``EREV-LED-004``) and DB-07
  ``tg_subledger_line__period_guard`` (``EREV-LED-003``).
- T-SL-02 ``subledger_posting_seal`` (IM-A, RLS-T): primary key ``(tenant_id,
  subledger_posting_id)``, ``ux_subledger_posting_seal__chain``, the 04 check ``line_count >= 2``
  named ``ck_subledger_posting_seal__line_count`` and the checks ``__chain_seq``, ``__prev_seal``
  and ``__control_totals``; the foreign key to the posting; DB-06 (2)
  ``tg_subledger_posting_seal__insert`` (``EREV-LED-001``, ``EREV-LED-002``, ``EREV-LED-005``).
- DB-05 (``EREV-REF-001``): ``tg_legal_entity__frozen`` freezes ``functional_currency`` and
  ``time_zone`` once a line of the entity exists, and the body of ``tg_period__frozen`` (0029) adds
  the reference by a line (BS3-D-07).

The checks and foreign keys 04 does not name, and the keys left out (``schedule_line_id`` and
``reverses_line_id`` name partitioned rows under other column names; ``close_run_id``,
``manual_adjustment_id`` and ``contract_cost_asset_id`` wait for their tables), are L3-1-Q-28.
Every trigger returns early for a row outside the tenant context or the entity scope, so row-level
security answers 42501 (DG-TST-20; L3-1-Q-19). Five functions are added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from erev_api.db import migration_ops as ops

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

# 04 §3.4 E-29 (rev 1.2 appends RECEIVABLE_CONTRA) and E-31 (DG-MIG-06).
SUBLEDGER_ENTRY_KIND = (
    "REVENUE_RECOGNITION",
    "BILLING",
    "CREDIT_MEMO",
    "NETTING_RECLASS",
    "NETTING_RECLASS_REVERSAL",
    "REFUND_LIABILITY",
    "RETURN_ASSET",
    "DEPOSIT",
    "CONSIDERATION_PAYABLE",
    "CONTRACT_COST_CAPITALIZATION",
    "CONTRACT_COST_AMORTIZATION",
    "CONTRACT_COST_IMPAIRMENT",
    "LOSS_PROVISION",
    "WARRANTY_ACCRUAL",
    "FINANCING_INTEREST",
    "FX_REMEASUREMENT",
    "FX_ROUNDING",
    "INTERCOMPANY",
    "PRE_STANDARD_REVENUE",
    "NONCASH_CONSIDERATION",
    "SALES_TAX",
    "MANUAL_ADJUSTMENT",
    "REVERSAL",
    "RECEIVABLE_CONTRA",
)
SUBLEDGER_POSTING_KIND = (
    "ENGINE_COMPUTE",
    "CLOSE_RELEASE",
    "FX_REMEASUREMENT",
    "NETTING_RECLASS",
    "MANUAL_ADJUSTMENT",
    "VOID_REVERSAL",
)

LINE_PARTITIONS = sa.text(
    "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
    "WHERE i.inhparent = CAST(:parent AS regclass) ORDER BY c.relname"
)

# T-SL-01 "Required for" notes.
SOURCE_CHECK = (
    "(posting_kind <> 'ENGINE_COMPUTE' OR contract_computation_id IS NOT NULL) "
    "AND (posting_kind NOT IN ('CLOSE_RELEASE', 'FX_REMEASUREMENT', 'NETTING_RECLASS') "
    "OR close_run_id IS NOT NULL) "
    "AND (posting_kind <> 'MANUAL_ADJUSTMENT' OR manual_adjustment_id IS NOT NULL)"
)
# T-SL-04 ``dr_cr``.
DR_CR = (
    "CASE WHEN amount_functional > 0 OR (amount_functional = 0 AND amount_txn > 0) "
    "THEN 'D' ELSE 'C' END"
)

# DB-06 (1): a line joins an unsealed posting of its book in the posting's creating transaction,
# carries its period's end date and amounts quantized to the currency minor units.
LINE_INSERT_BODY = """
DECLARE
  posting_txid bigint;
  posting_book text;
  period_end date;
  txn_unit integer;
  functional_unit integer;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  SELECT p.created_txid, p.book_code::text INTO posting_txid, posting_book
    FROM erev.subledger_posting p
   WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.subledger_posting_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-002: subledger line %s names no posting %s',
                       NEW.id, NEW.subledger_posting_id);
  END IF;
  IF posting_txid <> txid_current() THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-002: posting %s was created by another transaction, so line %s '
                       'cannot join it', NEW.subledger_posting_id, NEW.id);
  END IF;
  IF EXISTS (
    SELECT 1 FROM erev.subledger_posting_seal s
     WHERE s.tenant_id = NEW.tenant_id AND s.subledger_posting_id = NEW.subledger_posting_id
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-002: posting %s is sealed, so line %s cannot join it',
                       NEW.subledger_posting_id, NEW.id);
  END IF;
  IF NEW.book_code::text IS DISTINCT FROM posting_book THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-002: line %s of book %s joins posting %s of book %s',
                       NEW.id, NEW.book_code, NEW.subledger_posting_id, posting_book);
  END IF;
  SELECT pe.end_date INTO period_end
    FROM erev.period pe
   WHERE pe.tenant_id = NEW.tenant_id AND pe.id = NEW.period_id;
  IF period_end IS DISTINCT FROM NEW.period_end_date THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-002: line %s carries period_end_date %s, not the end date %s of '
                       'period %s', NEW.id, NEW.period_end_date, period_end, NEW.period_id);
  END IF;
  SELECT c.minor_unit INTO txn_unit FROM erev.currency c WHERE c.code = NEW.txn_currency;
  SELECT c.minor_unit INTO functional_unit FROM erev.currency c
   WHERE c.code = NEW.functional_currency;
  IF NEW.amount_txn <> round(NEW.amount_txn, txn_unit)
     OR NEW.amount_functional <> round(NEW.amount_functional, functional_unit) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-004: line %s amounts %s %s and %s %s are not quantized to the '
                       'currency minor units', NEW.id, NEW.amount_txn, NEW.txn_currency,
                       NEW.amount_functional, NEW.functional_currency);
  END IF;
  RETURN NEW;
END
"""

# DB-07: a line posts into an open, closing or reopened period of its entity and book; an origin
# period ends before the posting period starts.
PERIOD_GUARD_BODY = """
DECLARE
  period_state_now text;
  origin_end date;
  period_start date;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  SELECT s.state::text INTO period_state_now
    FROM erev.period_state s
   WHERE s.tenant_id = NEW.tenant_id AND s.entity_id = NEW.entity_id
     AND s.book_code = NEW.book_code AND s.period_id = NEW.period_id;
  IF period_state_now IS NULL OR period_state_now NOT IN ('open', 'closing', 'reopened') THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-003: period %s of entity %s is %s in book %s, so line %s cannot '
                       'post into it', NEW.period_id, NEW.entity_id,
                       coalesce(period_state_now, 'without a state'), NEW.book_code, NEW.id);
  END IF;
  NEW.is_post_reopen := (period_state_now = 'reopened');
  IF NEW.origin_period_id IS NOT NULL THEN
    SELECT o.end_date INTO origin_end
      FROM erev.period o
     WHERE o.tenant_id = NEW.tenant_id AND o.id = NEW.origin_period_id;
    SELECT p.start_date INTO period_start
      FROM erev.period p
     WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.period_id;
    IF origin_end IS NULL OR origin_end >= period_start THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-LED-003: origin period %s of line %s does not end before period %s '
                         'starts', NEW.origin_period_id, NEW.id, NEW.period_id);
    END IF;
  END IF;
  RETURN NEW;
END
"""

# DB-06 (2): the seal counts the posting's lines, requires each entry to balance in transaction
# currency and in functional currency, overwrites the control totals, and extends the book's chain.
SEAL_INSERT_BODY = """
DECLARE
  posting_book text;
  counted integer;
  unbalanced text;
  totals jsonb;
  head_seq bigint;
  head_sha text;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id() THEN
    RETURN NEW;
  END IF;
  SELECT p.book_code::text INTO posting_book
    FROM erev.subledger_posting p
   WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.subledger_posting_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-002: the seal names no posting %s', NEW.subledger_posting_id);
  END IF;
  IF EXISTS (
    SELECT 1 FROM erev.subledger_posting_seal s
     WHERE s.tenant_id = NEW.tenant_id AND s.subledger_posting_id = NEW.subledger_posting_id
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-002: posting %s is already sealed', NEW.subledger_posting_id);
  END IF;
  IF NEW.book_code::text IS DISTINCT FROM posting_book THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-002: a seal of book %s names posting %s of book %s',
                       NEW.book_code, NEW.subledger_posting_id, posting_book);
  END IF;
  SELECT count(*) INTO counted
    FROM erev.subledger_line l
   WHERE l.tenant_id = NEW.tenant_id AND l.subledger_posting_id = NEW.subledger_posting_id;
  IF counted IS DISTINCT FROM NEW.line_count THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-001: the seal of posting %s counts %s lines, but the posting '
                       'has %s', NEW.subledger_posting_id, NEW.line_count, counted);
  END IF;
  SELECT string_agg(format('entity %s period %s entry %s %s sums %s', g.entity_id, g.period_id,
                           g.entry_no, g.txn_currency, g.total),
                    '; ' ORDER BY g.entity_id::text, g.period_id::text, g.entry_no, g.txn_currency)
    INTO unbalanced
    FROM (SELECT l.entity_id, l.period_id, l.entry_no, l.txn_currency, sum(l.amount_txn) AS total
            FROM erev.subledger_line l
           WHERE l.tenant_id = NEW.tenant_id AND l.subledger_posting_id = NEW.subledger_posting_id
           GROUP BY l.entity_id, l.book_code, l.period_id, l.entry_no, l.txn_currency
          HAVING sum(l.amount_txn) <> 0) g;
  IF unbalanced IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-001: posting %s does not balance in transaction currency: %s',
                       NEW.subledger_posting_id, unbalanced);
  END IF;
  SELECT string_agg(format('entity %s period %s entry %s sums %s', g.entity_id, g.period_id,
                           g.entry_no, g.total),
                    '; ' ORDER BY g.entity_id::text, g.period_id::text, g.entry_no)
    INTO unbalanced
    FROM (SELECT l.entity_id, l.period_id, l.entry_no, sum(l.amount_functional) AS total
            FROM erev.subledger_line l
           WHERE l.tenant_id = NEW.tenant_id AND l.subledger_posting_id = NEW.subledger_posting_id
           GROUP BY l.entity_id, l.book_code, l.period_id, l.entry_no
          HAVING sum(l.amount_functional) <> 0) g;
  IF unbalanced IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-001: posting %s does not balance in functional currency: %s',
                       NEW.subledger_posting_id, unbalanced);
  END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object(
           'entity_id', t.entity_id, 'period_id', t.period_id, 'currency', t.txn_currency,
           'debit_txn', t.debit_txn::text, 'credit_txn', t.credit_txn::text,
           'debit_functional', t.debit_functional::text,
           'credit_functional', t.credit_functional::text)
         ORDER BY t.entity_id::text, t.period_id::text, t.txn_currency), '[]'::jsonb)
    INTO totals
    FROM (SELECT l.entity_id, l.period_id, l.txn_currency,
                 coalesce(sum(l.amount_txn) FILTER (WHERE l.amount_txn > 0), 0)::numeric(24, 4)
                   AS debit_txn,
                 coalesce(-sum(l.amount_txn) FILTER (WHERE l.amount_txn < 0), 0)::numeric(24, 4)
                   AS credit_txn,
                 coalesce(sum(l.amount_functional) FILTER (WHERE l.amount_functional > 0), 0)
                   ::numeric(24, 4) AS debit_functional,
                 coalesce(-sum(l.amount_functional) FILTER (WHERE l.amount_functional < 0), 0)
                   ::numeric(24, 4) AS credit_functional
            FROM erev.subledger_line l
           WHERE l.tenant_id = NEW.tenant_id AND l.subledger_posting_id = NEW.subledger_posting_id
           GROUP BY l.entity_id, l.period_id, l.txn_currency) t;
  NEW.control_totals := totals;
  SELECT h.last_chain_seq, h.last_seal_sha256::text INTO head_seq, head_sha
    FROM erev.ledger_chain_head h
   WHERE h.tenant_id = NEW.tenant_id AND h.book_code = NEW.book_code
     FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-005: book %s has no ledger chain head', NEW.book_code);
  END IF;
  IF NEW.prev_seal_sha256::text IS DISTINCT FROM head_sha THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-005: the seal of posting %s names previous seal %s, but the %s '
                       'chain head is %s', NEW.subledger_posting_id,
                       coalesce(NEW.prev_seal_sha256::text, 'none'), NEW.book_code,
                       coalesce(head_sha, 'none'));
  END IF;
  NEW.chain_seq := head_seq + 1;
  UPDATE erev.ledger_chain_head
     SET last_chain_seq = NEW.chain_seq, last_seal_sha256 = NEW.seal_sha256, updated_at = now()
   WHERE tenant_id = NEW.tenant_id AND book_code = NEW.book_code;
  RETURN NEW;
END
"""

# DB-06 (3): at commit, every posting has its seal.
SEALED_BODY = """
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM erev.subledger_posting_seal s
     WHERE s.tenant_id = NEW.tenant_id AND s.subledger_posting_id = NEW.id
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-002: subledger posting %s of book %s is not sealed',
                       NEW.id, NEW.book_code);
  END IF;
  RETURN NULL;
END
"""

# DB-05: functional currency and time zone freeze once a line of the entity exists.
ENTITY_FROZEN_BODY = """
BEGIN
  IF (NEW.functional_currency, NEW.time_zone)
     IS NOT DISTINCT FROM (OLD.functional_currency, OLD.time_zone) THEN
    RETURN NEW;
  END IF;
  IF EXISTS (
    SELECT 1 FROM erev.subledger_line l WHERE l.tenant_id = OLD.tenant_id AND l.entity_id = OLD.id
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: functional_currency and time_zone of entity %s of %I.%I are '
                       'frozen: a subledger line of the entity exists',
                       OLD.code, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""

# DB-05 of revision 0029, restored on downgrade.
PERIOD_FROZEN_0029_BODY = """
BEGIN
  IF EXISTS (
    SELECT 1 FROM erev.period_state s
     WHERE s.tenant_id = OLD.tenant_id AND s.period_id = OLD.id AND s.state <> 'future'
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: period %s of %I.%I is frozen: a period state beyond future '
                       'references it', OLD.period_key, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
"""

# DB-05 (rev 1.3 wording): a period referenced by a non-future period state or by a line is frozen.
PERIOD_FROZEN_BODY = """
BEGIN
  IF EXISTS (
    SELECT 1 FROM erev.period_state s
     WHERE s.tenant_id = OLD.tenant_id AND s.period_id = OLD.id AND s.state <> 'future'
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: period %s of %I.%I is frozen: a period state beyond future '
                       'references it', OLD.period_key, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF EXISTS (
    SELECT 1 FROM erev.subledger_line l WHERE l.tenant_id = OLD.tenant_id AND l.period_id = OLD.id
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: period %s of %I.%I is frozen: a subledger line references it',
                       OLD.period_key, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
"""


def _replace_function(signature: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger; NC-18 attributes."""
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{signature} RETURNS trigger LANGUAGE plpgsql "
        f"SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _date(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Date(), nullable=nullable)


def _timestamp(name: str) -> sa.Column[Any]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _create_ledger_chain_head() -> None:
    ops.create_tenant_table(
        "ledger_chain_head",
        _named("book_code", "erev.book_code", nullable=False),
        sa.Column("last_chain_seq", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        _named("last_seal_sha256", "erev.sha256", nullable=True),
        _timestamp("updated_at"),
        include_id=False,
        primary_key=["tenant_id", "book_code"],
        checks=[
            ("ck_ledger_chain_head__last_chain_seq", "last_chain_seq >= 0"),
            ("ck_ledger_chain_head__seal", "(last_chain_seq = 0) = (last_seal_sha256 IS NULL)"),
        ],
    )
    ops.apply_class("ledger_chain_head", "IM-X")
    ops.enable_rls("ledger_chain_head", "RLS-T")


def _create_subledger_posting() -> None:
    table = "subledger_posting"
    ops.create_tenant_table(
        table,
        _named("book_code", "erev.book_code", nullable=False),
        _named("posting_kind", "erev.subledger_posting_kind", nullable=False),
        _uuid("combination_group_id"),
        _uuid("contract_computation_id"),
        _uuid("close_run_id"),
        _uuid("manual_adjustment_id"),
        _uuid("reverses_posting_id"),
        _text("idempotency_key", nullable=False),
        sa.Column(
            "created_txid",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("txid_current()"),
        ),
        _text("description", nullable=False),
        standard_sets=["SC-C"],
        checks=[("ck_subledger_posting__source", SOURCE_CHECK)],
        unique=[
            (
                "ux_subledger_posting__idempotency",
                ["tenant_id", "book_code", "idempotency_key"],
                None,
            )
        ],
        indexes=[
            (
                "ix_subledger_posting__group",
                ["tenant_id", "combination_group_id", "created_at"],
                None,
            )
        ],
    )
    ops.add_tenant_fk(table, "combination_group_id", "combination_group")
    ops.add_tenant_fk(table, "contract_computation_id", "contract_computation")
    ops.add_tenant_fk(table, "reverses_posting_id", "subledger_posting")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-T")
    ops.create_trigger(
        table, "sealed", SEALED_BODY, timing="AFTER", events="INSERT", deferrable=True
    )


def _create_subledger_line() -> None:
    table = "subledger_line"
    ops.create_tenant_table(
        table,
        _date("period_end_date", nullable=False),
        _uuid("id", nullable=False),
        _uuid("subledger_posting_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _uuid("entity_id", nullable=False),
        _uuid("period_id", nullable=False),
        _uuid("origin_period_id"),
        sa.Column("is_post_reopen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _date("effective_date", nullable=False),
        _timestamp("recorded_at"),
        sa.Column("entry_no", sa.Integer(), nullable=False),
        _named("entry_kind", "erev.subledger_entry_kind", nullable=False),
        _named("account_role", "erev.account_role", nullable=False),
        _named("clearing_purpose", "erev.clearing_purpose", nullable=True),
        _uuid("gl_account_id", nullable=False),
        _named("dimensions", "jsonb", nullable=False, default="'{}'::jsonb"),
        _named("dimension_set_sha256", "erev.sha256", nullable=False),
        _named("txn_currency", "erev.currency_code", nullable=False),
        _named("amount_txn", "erev.money", nullable=False),
        _named("functional_currency", "erev.currency_code", nullable=False),
        _named("amount_functional", "erev.money", nullable=False),
        sa.Column("dr_cr", sa.CHAR(1), sa.Computed(DR_CR, persisted=True), nullable=False),
        _uuid("fx_rate_set_version_id"),
        _uuid("fx_rate_id"),
        # TY-03 is the domain erev.fx_rate_value: erev.fx_rate names the T-REF-12 row type (0030).
        _named("fx_rate", "erev.fx_rate_value", nullable=True),
        _text("fx_layer_key"),
        _uuid("contract_id", nullable=False),
        _uuid("obligation_id"),
        _uuid("contract_version_id"),
        _uuid("contract_event_id"),
        _uuid("schedule_line_id"),
        _date("schedule_period_end_date"),
        _uuid("contract_cost_asset_id"),
        _uuid("counterparty_entity_id"),
        _uuid("reverses_line_id"),
        _date("reverses_period_end_date"),
        _text("reason_code"),
        _text("legacy_key"),
        _uuid("calc_trace_id"),
        _text("trace_node_id"),
        _text("description"),
        standard_sets=["SC-C"],
        include_id=False,
        partition_by="period_end_date",
        primary_key=["tenant_id", "period_end_date", "id"],
        checks=[
            (
                "ck_subledger_line__reserved_role",
                "account_role NOT IN ('RETAINED_EARNINGS', 'FINANCING_OBLIGATION')",
            ),
            (
                "ck_subledger_line__clearing_purpose",
                "(account_role = 'BILLING_CLEARING') = (clearing_purpose IS NOT NULL)",
            ),
            ("ck_subledger_line__amounts", "amount_txn <> 0 OR amount_functional <> 0"),
            (
                "ck_subledger_line__fx",
                "(txn_currency = functional_currency) "
                "OR (fx_rate_set_version_id IS NOT NULL AND fx_rate_id IS NOT NULL)",
            ),
            (
                "ck_subledger_line__schedule_line",
                "(schedule_line_id IS NULL) = (schedule_period_end_date IS NULL)",
            ),
            (
                "ck_subledger_line__counterparty",
                "(account_role IN ('INTERCOMPANY_DUE_TO', 'INTERCOMPANY_DUE_FROM')) "
                "= (counterparty_entity_id IS NOT NULL)",
            ),
            (
                "ck_subledger_line__reason_code",
                "origin_period_id IS NULL OR reason_code IS NOT NULL",
            ),
            ("ck_subledger_line__entry_no", "entry_no >= 1"),
            (
                "ck_subledger_line__reverses",
                "(reverses_line_id IS NULL) = (reverses_period_end_date IS NULL)",
            ),
        ],
        indexes=[
            (
                "ix_subledger_line__ledger",
                ["tenant_id", "period_end_date", "entity_id", "book_code", "account_role"],
                None,
            ),
            ("ix_subledger_line__contract", ["tenant_id", "contract_id", "period_end_date"], None),
            ("ix_subledger_line__posting", ["tenant_id", "subledger_posting_id"], None),
            (
                "ix_subledger_line__schedule",
                ["tenant_id", "period_end_date", "schedule_line_id"],
                None,
            ),
        ],
    )
    ops.create_monthly_partitions(table)
    ops.add_tenant_fk(table, "subledger_posting_id", "subledger_posting")
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    ops.add_tenant_fk(table, "origin_period_id", "period")
    ops.add_tenant_fk(table, "gl_account_id", "gl_account")
    ops.add_global_fk(table, "txn_currency", "currency", target_column="code")
    ops.add_global_fk(table, "functional_currency", "currency", target_column="code")
    ops.add_tenant_fk(table, "fx_rate_set_version_id", "fx_rate_set_version")
    ops.add_tenant_fk(table, "fx_rate_id", "fx_rate")
    ops.add_tenant_fk(table, "contract_id", "contract")
    ops.add_tenant_fk(table, "obligation_id", "obligation")
    ops.add_tenant_fk(table, "contract_version_id", "contract_version")
    ops.add_tenant_fk(table, "contract_event_id", "contract_event")
    ops.add_tenant_fk(table, "counterparty_entity_id", "legal_entity")
    ops.add_tenant_fk(table, "calc_trace_id", "calc_trace")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")
    ops.create_trigger(table, "insert", LINE_INSERT_BODY, timing="BEFORE", events="INSERT")
    ops.create_trigger(table, "period_guard", PERIOD_GUARD_BODY, timing="BEFORE", events="INSERT")


def _create_subledger_posting_seal() -> None:
    table = "subledger_posting_seal"
    ops.create_tenant_table(
        table,
        _uuid("subledger_posting_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        sa.Column("chain_seq", sa.BigInteger(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        _named("control_totals", "jsonb", nullable=False),
        _named("prev_seal_sha256", "erev.sha256", nullable=True),
        _named("seal_sha256", "erev.sha256", nullable=False),
        _timestamp("sealed_at"),
        standard_sets=["SC-C"],
        include_id=False,
        primary_key=["tenant_id", "subledger_posting_id"],
        checks=[
            ("ck_subledger_posting_seal__line_count", "line_count >= 2"),
            ("ck_subledger_posting_seal__chain_seq", "chain_seq >= 1"),
            (
                "ck_subledger_posting_seal__prev_seal",
                "(chain_seq = 1) = (prev_seal_sha256 IS NULL)",
            ),
            (
                "ck_subledger_posting_seal__control_totals",
                "jsonb_typeof(control_totals) = 'array'",
            ),
        ],
        unique=[
            ("ux_subledger_posting_seal__chain", ["tenant_id", "book_code", "chain_seq"], None)
        ],
    )
    ops.add_tenant_fk(table, "subledger_posting_id", "subledger_posting")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-T")
    ops.create_trigger(table, "insert", SEAL_INSERT_BODY, timing="BEFORE", events="INSERT")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("subledger_entry_kind", SUBLEDGER_ENTRY_KIND)
    ops.create_enum("subledger_posting_kind", SUBLEDGER_POSTING_KIND)
    _create_ledger_chain_head()
    _create_subledger_posting()
    _create_subledger_line()
    _create_subledger_posting_seal()
    ops.create_trigger(
        "legal_entity",
        "frozen",
        ENTITY_FROZEN_BODY,
        timing="BEFORE",
        events="UPDATE OF functional_currency, time_zone",
    )
    _replace_function("tg_period__frozen()", PERIOD_FROZEN_BODY)


def _drop_line_partitions() -> None:
    """[J] L3-1-Q-33: one ``DROP TABLE erev.subledger_line`` locks its 181 partitions with their
    indexes and TOAST relations in one transaction, which exceeds the shared lock table
    (``max_locks_per_transaction``; L3-1-Q-24), so each partition is dropped in its own transaction
    first. The statements before this step commit when the autocommit block opens."""
    names = [
        str(name)
        for (name,) in op.get_bind().execute(LINE_PARTITIONS, {"parent": "erev.subledger_line"})
    ]
    with op.get_context().autocommit_block():
        for name in names:
            ops.execute(f"DROP TABLE erev.{name}")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    _replace_function("tg_period__frozen()", PERIOD_FROZEN_0029_BODY)
    ops.execute("DROP TRIGGER tg_legal_entity__frozen ON erev.legal_entity")
    ops.execute("DROP FUNCTION erev.tg_legal_entity__frozen()")
    ops.drop_tenant_table("subledger_posting_seal")
    _drop_line_partitions()
    ops.drop_tenant_table("subledger_line")
    ops.drop_tenant_table("subledger_posting")
    ops.drop_tenant_table("ledger_chain_head")
    ops.drop_enum("subledger_posting_kind")
    ops.drop_enum("subledger_entry_kind")
