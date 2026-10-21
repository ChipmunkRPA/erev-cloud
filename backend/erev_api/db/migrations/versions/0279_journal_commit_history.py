"""Capture committed journal lifecycle states and immutable line availability."""

import json

from erev_api.db import migration_ops as ops

revision = "0279"
down_revision = "0278"
branch_labels = None
depends_on = None

OLD_CAPTURE = """

DECLARE expected jsonb; scoped_entity uuid;
BEGIN
  IF pg_trigger_depth() < 2 OR NEW.is_baseline THEN
    RAISE EXCEPTION 'Report source revisions are written only by source triggers'
      USING ERRCODE='23514';
  END IF;
  IF NEW.source_kind = 'contract' THEN
    SELECT to_jsonb(c) - 'tenant_id', c.contracting_entity_id INTO expected,scoped_entity
      FROM erev.contract c WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.source_id;
  ELSIF NEW.source_kind = 'customer_code' THEN
    SELECT jsonb_build_object('id',c.id,'code',c.code) INTO expected
      FROM erev.customer c WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.source_id;
  ELSIF NEW.source_kind = 'entity_code' THEN
    SELECT jsonb_build_object('id',c.id,'code',c.code) INTO expected
      FROM erev.legal_entity c WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.source_id;
  ELSIF NEW.source_kind = 'gl_reconciliation' THEN
    SELECT to_jsonb(r) - 'tenant_id', r.entity_id INTO expected,scoped_entity
      FROM erev.reconciliation r WHERE r.tenant_id=NEW.tenant_id AND r.id=NEW.source_id
      AND r.kind='SUBLEDGER_TO_GL';
  END IF;
  IF expected IS NULL OR NEW.document IS DISTINCT FROM expected
     OR NEW.entity_id IS DISTINCT FROM scoped_entity THEN
    RAISE EXCEPTION 'Report revision must equal its current source row' USING ERRCODE='23514';
  END IF;
  SELECT coalesce(max(r.revision_no),0)+1 INTO NEW.revision_no
    FROM erev.report_source_revision r WHERE r.tenant_id=NEW.tenant_id
      AND r.source_kind=NEW.source_kind AND r.source_id=NEW.source_id;
  NEW.recorded_at := clock_timestamp();
  RETURN NEW;
END
"""

NEW_CAPTURE = """

DECLARE expected jsonb; scoped_entity uuid;
BEGIN
  IF pg_trigger_depth() < 2 OR NEW.is_baseline THEN
    RAISE EXCEPTION 'Report source revisions are written only by source triggers'
      USING ERRCODE='23514';
  END IF;
  IF NEW.source_kind = 'contract' THEN
    SELECT to_jsonb(c) - 'tenant_id', c.contracting_entity_id INTO expected,scoped_entity
      FROM erev.contract c WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.source_id;
  ELSIF NEW.source_kind = 'customer_code' THEN
    SELECT jsonb_build_object('id',c.id,'code',c.code) INTO expected
      FROM erev.customer c WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.source_id;
  ELSIF NEW.source_kind = 'entity_code' THEN
    SELECT jsonb_build_object('id',c.id,'code',c.code) INTO expected
      FROM erev.legal_entity c WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.source_id;
  ELSIF NEW.source_kind = 'gl_reconciliation' THEN
    SELECT to_jsonb(r) - 'tenant_id', r.entity_id INTO expected,scoped_entity
      FROM erev.reconciliation r WHERE r.tenant_id=NEW.tenant_id AND r.id=NEW.source_id
      AND r.kind='SUBLEDGER_TO_GL';
  ELSIF NEW.source_kind = 'journal_run' THEN
    SELECT to_jsonb(r) - 'tenant_id', r.entity_id INTO expected,scoped_entity
      FROM erev.journal_run r WHERE r.tenant_id=NEW.tenant_id AND r.id=NEW.source_id;
  ELSIF NEW.source_kind = 'journal_batch' THEN
    SELECT to_jsonb(r) - 'tenant_id', r.entity_id INTO expected,scoped_entity
      FROM erev.journal_batch r WHERE r.tenant_id=NEW.tenant_id AND r.id=NEW.source_id;
  END IF;
  IF expected IS NULL OR NEW.document IS DISTINCT FROM expected
     OR NEW.entity_id IS DISTINCT FROM scoped_entity THEN
    RAISE EXCEPTION 'Report revision must equal its current source row' USING ERRCODE='23514';
  END IF;
  SELECT coalesce(max(r.revision_no),0)+1 INTO NEW.revision_no
    FROM erev.report_source_revision r WHERE r.tenant_id=NEW.tenant_id
      AND r.source_kind=NEW.source_kind AND r.source_id=NEW.source_id;
  NEW.recorded_at := clock_timestamp();
  RETURN NEW;
END
"""

OLD_STAMP = """

        CREATE OR REPLACE FUNCTION erev.tg_source_commit__stamp() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT (
                    (NEW.source_kind = 'contract_event' AND EXISTS (
                        SELECT 1 FROM erev.contract_event
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'contract_version' AND EXISTS (
                        SELECT 1 FROM erev.contract_version
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'report_source_revision' AND EXISTS (
                        SELECT 1 FROM erev.report_source_revision
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id))
                ) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Original source is required';
                END IF;
                NEW.source_transaction := pg_current_xact_id()::text;
                NEW.committed_server_at := NULL;
            ELSE
                IF OLD.committed_server_at IS NOT NULL THEN
                    RAISE EXCEPTION 'EREV-IMM-001: Commit evidence is immutable';
                END IF;
                IF NEW.committed_server_at IS NULL OR NEW.committed_server_at IS DISTINCT FROM
                    erev.source_commit_time(OLD.source_kind, OLD.source_id) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Commit evidence must match PostgreSQL';
                END IF;
            END IF;
            RETURN NEW;
        END $$
"""

NEW_STAMP = """

        CREATE OR REPLACE FUNCTION erev.tg_source_commit__stamp() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT (
                    (NEW.source_kind = 'contract_event' AND EXISTS (
                        SELECT 1 FROM erev.contract_event
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'contract_version' AND EXISTS (
                        SELECT 1 FROM erev.contract_version
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'report_source_revision' AND EXISTS (
                        SELECT 1 FROM erev.report_source_revision
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'journal_line' AND EXISTS (
                        SELECT 1 FROM erev.journal_line
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id))
                ) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Original source is required';
                END IF;
                NEW.source_transaction := pg_current_xact_id()::text;
                NEW.committed_server_at := NULL;
            ELSE
                IF OLD.committed_server_at IS NOT NULL THEN
                    RAISE EXCEPTION 'EREV-IMM-001: Commit evidence is immutable';
                END IF;
                IF NEW.committed_server_at IS NULL OR NEW.committed_server_at IS DISTINCT FROM
                    erev.source_commit_time(OLD.source_kind, OLD.source_id) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Commit evidence must match PostgreSQL';
                END IF;
            END IF;
            RETURN NEW;
        END $$
"""


def _capture_guard(body: str) -> None:
    ops.execute(
        "CREATE OR REPLACE FUNCTION erev.tg_report_source_revision__capture_only() "
        "RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER "
        "SET search_path=pg_catalog,erev AS $$" + body + "$$"
    )


def _kinds(*, undo: bool) -> None:
    revision_kinds = "'contract','customer_code','entity_code','gl_reconciliation'"
    source_kinds = "'contract_event','contract_version','report_source_revision'"
    if not undo:
        revision_kinds += ",'journal_run','journal_batch'"
        source_kinds += ",'journal_line'"
    ops.execute(
        "ALTER TABLE erev.report_source_revision DROP CONSTRAINT ck_report_source_revision__kind"
    )
    ops.execute(
        "ALTER TABLE erev.report_source_revision "
        "ADD CONSTRAINT ck_report_source_revision__kind CHECK (source_kind IN ("
        + revision_kinds
        + "))"
    )
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "DROP CONSTRAINT ck_historical_source_commit__kind"
    )
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "ADD CONSTRAINT ck_historical_source_commit__kind CHECK (source_kind IN ("
        + source_kinds
        + "))"
    )


OLD_IPE = (
    '{"revenue_waterfall":{"version":1,"source_tables":["schedule_line","subledger_line","ten'
    'ant","fx_rate","fx_rate_set","fx_rate_set_version","contract_version","obligation_versio'
    'n","contract","customer","legal_entity","product","period","journal_line","lock_snapshot'
    '","combination_group_member","contract_computation","calc_trace","contract_event","suble'
    'dger_posting_commit","historical_source_commit"],"joins":["schedule_line.contract_versio'
    'n_id = contract_version.id","schedule_line.subject_id = obligation_version.obligation_id'
    ' and schedule_line.contract_version_id = obligation_version.contract_version_id","schedu'
    'le_line.contract_id = contract.id","contract.customer_id = customer.id","schedule_line.e'
    'ntity_id = legal_entity.id","schedule_line.period_id = period.id","obligation_version.pr'
    'oduct_id = product.id","combination_group_member.combination_group_id = contract_version'
    '.combination_group_id","contract_version.contract_computation_id = contract_computation.'
    'id"],"filters":["entity code in entity_codes and within the caller\'s entity scope","book'
    '_code = book","schedule_line.subject_type = \'obligation\'","per contract, the last contra'
    "ct_version of the book known at known_at along the contract's chain of combination group"
    "s, of the versions computed with the contract among their members (combination_group_mem"
    'ber, contract_computation)","period_key from from_period_key to to_period_key","contract'
    '.external_id = contract_external_id when given","with period_lock_id, the values frozen '
    'at that lock (lock_snapshot kind WATERFALL)","historical time-based schedules freeze the'
    " original allocation segment at the reporting cut; dated projections reconcile to the re"
    'mainder and retain cut-specific drill-through","original period projections survive remo'
    "ved current schedule lines; source evidence is the contract version trace for the exact "
    'reporting cut and future period","scheduled and awaiting remainders use original period-'
    "level recognition-hold and pattern evidence reconciled to the version state; future hold"
    's do not alter earlier time-based projections","fixed-only manual releases, deferrals an'
    "d schedule overrides replay only events effective at the reporting cut; unsupported comp"
    'onent mixtures or unreproducible snapshots retain explicit projection errors","manual pr'
    "ojection freezes realized usage at the reporting cut and replays fixed plus PERIOD_VC ta"
    "rgets without proportional allocation; schedule overrides retain anchor-period realized "
    "consideration and recognize subsequent usage immediately; royalty and netted projections"
    ' remain unavailable","royalty manual projections freeze original statements and effectiv'
    "e estimate pins at the reporting cut; minimum guarantees and recognized royalty sources "
    "must remain stable over the frozen horizon; schedule overrides retain anchor royalties a"
    'nd subsequent signed royalty changes separately","Step-1 netted forecasts freeze origina'
    "l deposit recognitions and cite their attributed shares; a separate dated reporting rema"
    "inder excludes already-recognized deposit revenue while preserving contract measurement "
    'balances; projected future periods must reconcile to that net remainder","Waterfall entr'
    "y dates come from the first included contract version on its membership chain and its bo"
    "ok-specific entry event; contracts entering after the performing entity as-of period are"
    ' excluded; retained entry bindings and legacy populations remain unchanged on rerun","su'
    "bledger_commit_visibility_v1 requires original PostgreSQL posting commit time at or befo"
    "re the historical cutoff; retained commit evidence is immutable; older bindings preserve"
    ' their original seal-time interpretation","historical_source_commit_v1 retains original '
    "event and contract-version transaction commits; new event/version extracts and BBR event"
    " sources use commit cutoffs; historical version populations exclude later commits before"
    ' latest selection; bound inputs keep their original interpretation"],"parameters":["enti'
    'ty_codes","book","from_period_key","to_period_key","as_of","known_at","period_lock_id","'
    'row_dimension","granularity","measure","contract_external_id","currency_view","filters",'
    '"known_at_basis"]},"disaggregation":{"version":1,"source_tables":["subledger_line","tena'
    'nt","fx_rate","fx_rate_set","fx_rate_set_version","journal_line","journal_batch","journa'
    'l_run","obligation_version","product","dimension_value","period","lock_snapshot","subled'
    'ger_posting_commit"],"joins":["subledger_line.obligation_id = obligation_version.obligat'
    'ion_id and subledger_line.contract_version_id = obligation_version.contract_version_id",'
    '"obligation_version.product_id = product.id","subledger_line.period_id = period.id","jou'
    'rnal_line.journal_batch_id = journal_batch.id for the independent journal tie-out"],"fil'
    'ters":["entity code in entity_codes and within the caller\'s entity scope","book_code = b'
    'ook","period_key from from_period_key to to_period_key","subledger_line.account_role = \''
    'REVENUE\'; independent tie-out uses journal runs not cancelled","functional reads posted '
    "amounts; reporting translates posted functional lines at their period average rates, ret"
    'ained for reruns","grouped by dimension_code and, with include_timing, the timing of tra'
    'nsfer","with period_lock_id, the values frozen at that lock (lock_snapshot kind DISAGGRE'
    'GATION)","subledger_commit_visibility_v1 requires original PostgreSQL posting commit tim'
    "e at or before the historical cutoff; retained commit evidence is immutable; older bindi"
    'ngs preserve their original seal-time interpretation"],"parameters":["entity_codes","boo'
    'k","period_lock_id","from_period_key","to_period_key","dimension_code","include_timing",'
    '"currency_view","known_at","known_at_basis"]},"extract_journal_lines":{"version":1,"sour'
    'ce_tables":["journal_line","journal_entry","journal_batch","journal_run","period","audit'
    '_event"],"joins":["journal_line.journal_entry_id = journal_entry.id","journal_line.journ'
    'al_batch_id = journal_batch.id","journal_batch.journal_run_id = journal_run.id","journal'
    '_line.period_id = period.id","audit_event run and batch lifecycle transitions resolve ru'
    'n state at source time"],"filters":["entity code in entity_codes and within the caller\'s'
    ' entity scope","book_code = book","runs not cancelled as of known_at; unknown historical'
    ' state refuses","line/entry/batch/run created by known_at; lock datasets unsupported","m'
    "ode INCREMENTAL: rows created (recorded for events and subledger lines) after known_sinc"
    'e and at or before the source time"],"parameters":["mode","entity_codes","book","period_'
    'lock_id","known_at","known_since","known_at_basis"]},"bookings_billings_revenue":{"versi'
    'on":1,"source_tables":["contract_event","modification","combination_group_member","contr'
    'act_version","subledger_line","subledger_posting_seal","journal_line","journal_entry","j'
    'ournal_batch","journal_run","audit_event","legal_entity","period","fx_rate","fx_rate_set'
    '","fx_rate_set_version","subledger_posting_commit","historical_source_commit"],"joins":['
    '"modification applied_event_id binds its original application group and contract_version'
    '; predecessor supplies price delta","subledger_line joins its posting seal; journal line'
    's join entries, batches and runs with lifecycle evidence","entity fiscal calendars bucke'
    "t contributions; historical approved spot rates value non-functional contract and billin"
    'g amounts"],"filters":["entity code in entity_codes and within the caller\'s entity scope'
    '","book_code = book","period_key from from_period_key to to_period_key","source-time eve'
    'nt/version creation and sealed posting cutoffs; retained inputs supply reruns","activate'
    "d contract stated line values exclude bookings linked to separate-contract modifications"
    '","applied modification counted once; missing or shared valuation basis refuses","billin'
    'g identity, credit and void rules; revenue uses posting period","journal revenue exclude'
    's runs cancelled as of source time; unknown historical state refuses","functional contra'
    "ct/billing amounts use unique approved effective-day spot rate; reporting currency and l"
    'ock datasets unsupported","new retained ledger sources require actual posting commit tim'
    "e at or before known_at; commit timestamps are retained with source rows; older bound da"
    'tasets keep their original inputs and interpretation","historical_source_commit_v1 retai'
    "ns original event and contract-version transaction commits; new event/version extracts a"
    "nd BBR event sources use commit cutoffs; historical version populations exclude later co"
    'mmits before latest selection; bound inputs keep their original interpretation"],"parame'
    'ters":["entity_codes","book","period_lock_id","from_period_key","to_period_key","granula'
    'rity","currency_view","known_at","known_at_basis"]}}'
)

NEW_IPE = (
    '{"revenue_waterfall":{"version":1,"source_tables":["schedule_line","subledger_line","ten'
    'ant","fx_rate","fx_rate_set","fx_rate_set_version","contract_version","obligation_versio'
    'n","contract","customer","legal_entity","product","period","journal_line","lock_snapshot'
    '","combination_group_member","contract_computation","calc_trace","contract_event","suble'
    'dger_posting_commit","historical_source_commit","report_source_revision"],"joins":["sche'
    'dule_line.contract_version_id = contract_version.id","schedule_line.subject_id = obligat'
    "ion_version.obligation_id and schedule_line.contract_version_id = obligation_version.con"
    'tract_version_id","schedule_line.contract_id = contract.id","contract.customer_id = cust'
    'omer.id","schedule_line.entity_id = legal_entity.id","schedule_line.period_id = period.i'
    'd","obligation_version.product_id = product.id","combination_group_member.combination_gr'
    'oup_id = contract_version.combination_group_id","contract_version.contract_computation_i'
    'd = contract_computation.id"],"filters":["entity code in entity_codes and within the cal'
    'ler\'s entity scope","book_code = book","schedule_line.subject_type = \'obligation\'","per '
    "contract, the last contract_version of the book known at known_at along the contract's c"
    "hain of combination groups, of the versions computed with the contract among their membe"
    'rs (combination_group_member, contract_computation)","period_key from from_period_key to'
    ' to_period_key","contract.external_id = contract_external_id when given","with period_lo'
    'ck_id, the values frozen at that lock (lock_snapshot kind WATERFALL)","historical time-b'
    "ased schedules freeze the original allocation segment at the reporting cut; dated projec"
    'tions reconcile to the remainder and retain cut-specific drill-through","original period'
    " projections survive removed current schedule lines; source evidence is the contract ver"
    'sion trace for the exact reporting cut and future period","scheduled and awaiting remain'
    "ders use original period-level recognition-hold and pattern evidence reconciled to the v"
    'ersion state; future holds do not alter earlier time-based projections","fixed-only manu'
    "al releases, deferrals and schedule overrides replay only events effective at the report"
    "ing cut; unsupported component mixtures or unreproducible snapshots retain explicit proj"
    'ection errors","manual projection freezes realized usage at the reporting cut and replay'
    "s fixed plus PERIOD_VC targets without proportional allocation; schedule overrides retai"
    "n anchor-period realized consideration and recognize subsequent usage immediately; royal"
    'ty and netted projections remain unavailable","royalty manual projections freeze origina'
    "l statements and effective estimate pins at the reporting cut; minimum guarantees and re"
    "cognized royalty sources must remain stable over the frozen horizon; schedule overrides "
    'retain anchor royalties and subsequent signed royalty changes separately","Step-1 netted'
    " forecasts freeze original deposit recognitions and cite their attributed shares; a sepa"
    "rate dated reporting remainder excludes already-recognized deposit revenue while preserv"
    "ing contract measurement balances; projected future periods must reconcile to that net r"
    'emainder","Waterfall entry dates come from the first included contract version on its me'
    "mbership chain and its book-specific entry event; contracts entering after the performin"
    "g entity as-of period are excluded; retained entry bindings and legacy populations remai"
    'n unchanged on rerun","subledger_commit_visibility_v1 requires original PostgreSQL posti'
    "ng commit time at or before the historical cutoff; retained commit evidence is immutable"
    '; older bindings preserve their original seal-time interpretation","historical_source_co'
    "mmit_v1 retains original event and contract-version transaction commits; new event/versi"
    "on extracts and BBR event sources use commit cutoffs; historical version populations exc"
    "lude later commits before latest selection; bound inputs keep their original interpretat"
    'ion","Historical journal populations use original line commits and the latest committed '
    "journal-run/batch source revision at known_at. New journal incremental extracts use line"
    " commits in (known_since, known_at]; retained legacy bindings keep their original basis."
    '"],"parameters":["entity_codes","book","from_period_key","to_period_key","as_of","known_'
    'at","period_lock_id","row_dimension","granularity","measure","contract_external_id","cur'
    'rency_view","filters","known_at_basis"]},"disaggregation":{"version":1,"source_tables":['
    '"subledger_line","tenant","fx_rate","fx_rate_set","fx_rate_set_version","journal_line","'
    'journal_batch","journal_run","obligation_version","product","dimension_value","period","'
    'lock_snapshot","subledger_posting_commit","report_source_revision","historical_source_co'
    'mmit"],"joins":["subledger_line.obligation_id = obligation_version.obligation_id and sub'
    'ledger_line.contract_version_id = obligation_version.contract_version_id","obligation_ve'
    'rsion.product_id = product.id","subledger_line.period_id = period.id","journal_line.jour'
    'nal_batch_id = journal_batch.id for the independent journal tie-out"],"filters":["entity'
    ' code in entity_codes and within the caller\'s entity scope","book_code = book","period_k'
    "ey from from_period_key to to_period_key\",\"subledger_line.account_role = 'REVENUE'; inde"
    'pendent tie-out uses journal runs not cancelled","functional reads posted amounts; repor'
    "ting translates posted functional lines at their period average rates, retained for reru"
    'ns","grouped by dimension_code and, with include_timing, the timing of transfer","with p'
    'eriod_lock_id, the values frozen at that lock (lock_snapshot kind DISAGGREGATION)","subl'
    "edger_commit_visibility_v1 requires original PostgreSQL posting commit time at or before"
    " the historical cutoff; retained commit evidence is immutable; older bindings preserve t"
    'heir original seal-time interpretation","Historical journal populations use original lin'
    "e commits and the latest committed journal-run/batch source revision at known_at. New jo"
    "urnal incremental extracts use line commits in (known_since, known_at]; retained legacy "
    'bindings keep their original basis."],"parameters":["entity_codes","book","period_lock_i'
    'd","from_period_key","to_period_key","dimension_code","include_timing","currency_view","'
    'known_at","known_at_basis"]},"extract_journal_lines":{"version":1,"source_tables":["jour'
    'nal_line","journal_entry","journal_batch","journal_run","period","audit_event","report_s'
    'ource_revision","historical_source_commit"],"joins":["journal_line.journal_entry_id = jo'
    'urnal_entry.id","journal_line.journal_batch_id = journal_batch.id","journal_batch.journa'
    'l_run_id = journal_run.id","journal_line.period_id = period.id","audit_event run and bat'
    'ch lifecycle transitions resolve run state at source time"],"filters":["entity code in e'
    'ntity_codes and within the caller\'s entity scope","book_code = book","runs not cancelled'
    ' as of known_at; unknown historical state refuses","line/entry/batch/run created by know'
    'n_at; lock datasets unsupported","mode INCREMENTAL: rows created (recorded for events an'
    'd subledger lines) after known_since and at or before the source time","Historical journ'
    "al populations use original line commits and the latest committed journal-run/batch sour"
    "ce revision at known_at. New journal incremental extracts use line commits in (known_sin"
    'ce, known_at]; retained legacy bindings keep their original basis."],"parameters":["mode'
    '","entity_codes","book","period_lock_id","known_at","known_since","known_at_basis"]},"bo'
    'okings_billings_revenue":{"version":1,"source_tables":["contract_event","modification","'
    'combination_group_member","contract_version","subledger_line","subledger_posting_seal","'
    'journal_line","journal_entry","journal_batch","journal_run","audit_event","legal_entity"'
    ',"period","fx_rate","fx_rate_set","fx_rate_set_version","subledger_posting_commit","hist'
    'orical_source_commit","report_source_revision"],"joins":["modification applied_event_id '
    "binds its original application group and contract_version; predecessor supplies price de"
    'lta","subledger_line joins its posting seal; journal lines join entries, batches and run'
    's with lifecycle evidence","entity fiscal calendars bucket contributions; historical app'
    'roved spot rates value non-functional contract and billing amounts"],"filters":["entity '
    'code in entity_codes and within the caller\'s entity scope","book_code = book","period_ke'
    'y from from_period_key to to_period_key","source-time event/version creation and sealed '
    'posting cutoffs; retained inputs supply reruns","activated contract stated line values e'
    'xclude bookings linked to separate-contract modifications","applied modification counted'
    ' once; missing or shared valuation basis refuses","billing identity, credit and void rul'
    'es; revenue uses posting period","journal revenue excludes runs cancelled as of source t'
    'ime; unknown historical state refuses","functional contract/billing amounts use unique a'
    'pproved effective-day spot rate; reporting currency and lock datasets unsupported","new '
    "retained ledger sources require actual posting commit time at or before known_at; commit"
    " timestamps are retained with source rows; older bound datasets keep their original inpu"
    'ts and interpretation","historical_source_commit_v1 retains original event and contract-'
    "version transaction commits; new event/version extracts and BBR event sources use commit"
    " cutoffs; historical version populations exclude later commits before latest selection; "
    'bound inputs keep their original interpretation","Historical journal populations use ori'
    "ginal line commits and the latest committed journal-run/batch source revision at known_a"
    "t. New journal incremental extracts use line commits in (known_since, known_at]; retaine"
    'd legacy bindings keep their original basis."],"parameters":["entity_codes","book","peri'
    'od_lock_id","from_period_key","to_period_key","granularity","currency_view","known_at","'
    'known_at_basis"]}}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, ipe in json.loads(encoded).items():
        payload = json.dumps(ipe).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic='"  # noqa: S608 — frozen metadata
            + payload
            + "'::jsonb WHERE code='"
            + code
            + "' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    for source in ("journal_run", "journal_batch", "journal_line"):
        ops.execute(
            f"ALTER TABLE erev.{source} ADD CONSTRAINT ck_journal__0279_empty "
            "CHECK (false) NOT VALID"
        )
        ops.execute(f"ALTER TABLE erev.{source} VALIDATE CONSTRAINT ck_journal__0279_empty")
        ops.execute(f"ALTER TABLE erev.{source} DROP CONSTRAINT ck_journal__0279_empty")
    _metadata(NEW_IPE)
    _kinds(undo=False)
    _capture_guard(NEW_CAPTURE)
    ops.execute(NEW_STAMP)
    for source in ("journal_run", "journal_batch"):
        ops.create_trigger(
            source,
            "report_revision",
            """
BEGIN
  IF TG_OP='INSERT' OR to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
    INSERT INTO erev.report_source_revision
      (tenant_id,id,source_kind,source_id,entity_id,revision_no,recorded_at,is_baseline,document)
    VALUES (NEW.tenant_id,gen_random_uuid(),TG_TABLE_NAME,NEW.id,NEW.entity_id,1,
      clock_timestamp(),FALSE,to_jsonb(NEW)-'tenant_id');
  END IF;
  RETURN NEW;
END
""",
            timing="AFTER",
            events="INSERT OR UPDATE",
        )
    ops.execute(
        "CREATE TRIGGER zz_source__commit_queue AFTER INSERT ON erev.journal_line "
        "FOR EACH ROW EXECUTE FUNCTION erev.tg_source_commit__queue()"
    )


def downgrade() -> None:
    _metadata(OLD_IPE)
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.report_source_revision
                 WHERE source_kind IN ('journal_run','journal_batch'))
         OR EXISTS (SELECT 1 FROM erev.historical_source_commit
                    WHERE source_kind='journal_line') THEN
        RAISE EXCEPTION 'Retained journal commit evidence prevents downgrade';
      END IF;
    END $$""")
    ops.execute("DROP TRIGGER zz_source__commit_queue ON erev.journal_line")
    for source in ("journal_run", "journal_batch"):
        ops.execute(f"DROP TRIGGER tg_{source}__report_revision ON erev.{source}")
        ops.execute(f"DROP FUNCTION erev.tg_{source}__report_revision()")
    ops.execute(OLD_STAMP)
    _capture_guard(OLD_CAPTURE)
    _kinds(undo=True)
