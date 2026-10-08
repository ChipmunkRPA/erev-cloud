"""D-98 candidate 143 GUARD-TRN-1 — revision 0069 re-renders the six installed DB-03 transition
functions and 0068 carries the regenerated ``modification`` literal (dev-guide 1.62 DG-KRN-DB-09;
DG-ARC-07; DG-MIG-12 literals). CPU-only: the literals are compared with the renderer and with the
installing revisions' bodies; the database proof is ``tests/pg/test_transitions_drift.py`` and
``tests/pg/test_transition_pair_guard.py`` (NOT RUN in the CTR-17 slice)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Final

from erev_api.db.transitions import TRANSITIONS, transition_trigger_sql

VERSIONS: Final = Path(__file__).resolve().parents[3] / "backend/erev_api/db/migrations/versions"
# table → (installing revision, the name of its literal)
INSTALLERS: Final = {
    "contract": ("0042_ctr_7_judgement_records", "CONTRACT_TRANSITION_BODY"),
    "estimate_version": ("0051_ctr_12_estimates", "TRANSITION_BODY"),
    "event_submission": ("0038_ctr_1_contracts_streams", "SUBMISSION_TRANSITION_BODY"),
    "judgement_record": ("0042_ctr_7_judgement_records", "JUDGEMENT_TRANSITION_BODY"),
    "manual_adjustment": ("0046_journal_tables", "MANUAL_ADJUSTMENT_TRANSITION_BODY"),
    "policy_override": ("0045_ctr_15_policy_overrides", "TRANSITION_BODY"),
}


ADJUSTMENT_PAIRS: Final = "0093_clo_12_manual_adjustment_pairs"
ESTIMATE_DISCARD: Final = "0114_secfix_act_index_97"
JUDGEMENT_DISCARD: Final = "0118_secfix_act_index_174"
IMPORT_DIFF_FAILED: Final = "0122_import_diff_failed_pair"
PROPOSAL_DISCARD: Final = "0126_combination_proposal_discard"
WAIVER_PAIRS: Final = "0130_clo_waiver_covers_later_1_item_pairs"
REPUBLISH_TRIGGER: Final = "0128_fx_republish_dirty_1_dirty_trigger"


def _load(stem: str) -> Any:
    spec = importlib.util.spec_from_file_location(stem, VERSIONS / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0069_replaces_exactly_the_six_installed_editable_specs() -> None:
    revision = _load("0069_transition_pair_guard_rerender")
    assert (revision.revision, revision.down_revision) == ("0069", "0068")
    editable = {name for name, spec in TRANSITIONS.items() if spec.editable_while}
    assert set(revision.TABLES) == set(revision.BODIES) == set(revision.PREVIOUS)
    assert set(revision.TABLES) == editable - {"modification"}  # 0068 creates the seventh
    for table in revision.TABLES:
        status = TRANSITIONS[table].status_column
        if table == "contract":
            # 0070 (D-98 candidate 143 AMENDMENT 1) re-rendered contract's function after the spec
            # gained (DRAFT, ACTIVE); 0069's contract body is the installed PREVIOUS of 0070.
            assert revision.BODIES[table] == _load("0070_contract_activation_pair").PREVIOUS
        elif table == "manual_adjustment":
            # 0093 (BUILD_SPEC CLO-12; ruling R-51 (b)) re-rendered the function after the spec
            # gained the T-CON-06 pairs; 0069's body is the installed PREVIOUS of 0093.
            assert revision.BODIES[table] == _load(ADJUSTMENT_PAIRS).PREVIOUS
        elif table == "estimate_version":
            # 0114 (lane SECFIX-ACT, register index 97; ruling R-119 (e), item EST-DISCARD-1)
            # re-rendered the function after the spec gained (DRAFT, VOIDED); 0069's body is the
            # installed PREVIOUS of 0114.
            assert revision.BODIES[table] == _load(ESTIMATE_DISCARD).PREVIOUS
        elif table == "judgement_record":
            # 0118 (lane SECFIX-ACT, register index 174; the supervisor's ruling of 2026-10-01
            # on question J1 (a), the discard of a judgement record) re-rendered the function
            # after the spec gained (DRAFT, VOIDED); 0069's body is the installed PREVIOUS of 0118.
            assert revision.BODIES[table] == _load(JUDGEMENT_DISCARD).PREVIOUS
        else:
            assert revision.BODIES[table] == transition_trigger_sql(table), table  # DG-ARC-07
        installer, name = INSTALLERS[table]
        assert revision.PREVIOUS[table] == getattr(_load(installer), name), table  # verbatim
        assert revision.PREVIOUS[table] != revision.BODIES[table], table
        # the corrected order: pair guard before the editable return; the previous order after it
        new, old = revision.BODIES[table], revision.PREVIOUS[table]
        guard, early = (
            f"IF NEW.{status} IS DISTINCT FROM OLD.{status}",
            f"IF OLD.{status}::text = ANY (",
        )
        assert new.index(guard) < new.index(early), table
        assert old.index(guard) > old.index(early), table
        assert "$fn$" not in new and "$fn$" not in old


def test_0068_carries_the_regenerated_modification_literal() -> None:
    created = _load("0068_ctr_17_modifications")
    body = created.TRANSITION_BODY
    assert body == transition_trigger_sql("modification")
    assert body.index("IF NEW.status IS DISTINCT FROM OLD.status") < body.index(
        "IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN"
    )


def test_specs_without_an_editable_status_render_as_before() -> None:
    """The reordering is scoped to the seven editable specs: every other installed literal still
    equals the fresh rendering (a sample of installers; DG-ARC-07 covers all on a database)."""
    assert _load("0067_lmg_t_mig_04_05").TRANSITION_BODY == transition_trigger_sql(
        "migration_batch"
    )
    # 0111 (item CLO-GATE-RUN-1; 04 T-CON-03 rev 1.172) re-rendered the function of
    # ``combination_group`` after the spec gained ``period_ends_open``, and 0038's literal is
    # the installed PREVIOUS it replaces, verbatim. 0126 (item
    # COMBINATION-PROPOSAL-DISCARD-1; 04 E-95 rev 1.289) re-rendered it again after the spec
    # gained (PROPOSED, VOIDED), and 0111's BODY is the installed PREVIOUS of 0126
    # (``test_0126_re_renders_the_combination_group_pair``).
    gate_run = _load("0111_clo_gate_run_1_close_run_gate")
    assert gate_run.BODY == _load(PROPOSAL_DISCARD).PREVIOUS
    assert gate_run.PREVIOUS == _load("0038_ctr_1_contracts_streams").GROUP_TRANSITION_BODY
    assert gate_run.BODY.replace("'period_ends_open', ", "") == gate_run.PREVIOUS
    # 0128 (item FX-REPUBLISH-DIRTY-1; 04 T-CON-03 rev 1.297) re-rendered it a third time, after
    # the spec gained ``dirty_trigger``: its BODY is the fresh rendering, and 0126's BODY is the
    # installed PREVIOUS it replaces, verbatim — the pair (PROPOSED, VOIDED) stands in both.
    republish = _load(REPUBLISH_TRIGGER)
    assert (republish.revision, republish.TABLE) == ("0128", "combination_group")
    assert republish.BODY == transition_trigger_sql("combination_group")
    assert republish.PREVIOUS == _load(PROPOSAL_DISCARD).BODY
    assert republish.BODY.replace("'dirty_trigger', ", "") == republish.PREVIOUS
    assert "'PROPOSED>VOIDED'" in republish.BODY and "'PROPOSED>VOIDED'" in republish.PREVIOUS
    assert "$fn$" not in republish.BODY
    assert _load("0062_snp_1_tenant_snapshot").TRANSITION_BODY == transition_trigger_sql(
        "tenant_snapshot"
    )
    # 0127 (item CLO-RATE-AFTER-RUN-1; 04 T-CLS-01 rev 1.291) re-rendered the function of
    # ``close_run`` after the spec gained ``rates_read`` and ``registry_read``, each written
    # once: its BODY is the fresh rendering, and 0047's literal is the installed PREVIOUS it
    # replaces, verbatim. A succeeded run stays frozen but for the LOCK element of ``steps``.
    run_inputs = _load("0127_clo_rate_after_run_1_close_run_inputs")
    assert (run_inputs.revision, run_inputs.TABLE) == ("0127", "close_run")
    assert run_inputs.BODY == transition_trigger_sql("close_run")
    assert run_inputs.PREVIOUS == _load("0047_close_tables").CLOSE_RUN_TRANSITION_BODY
    spec = TRANSITIONS["close_run"]
    assert {"rates_read", "registry_read"} <= spec.updatable_columns & spec.set_once
    for column in ("rates_read", "registry_read"):
        assert f"OLD.{column} IS NOT NULL AND NEW.{column} IS DISTINCT FROM" in run_inputs.BODY
        assert column not in run_inputs.PREVIOUS
    frozen = run_inputs.BODY.split("IF OLD.status::text = ANY (ARRAY['SUCCEEDED']")[1]
    assert "rates_read" not in frozen.split("END IF;")[0]  # not among what a succeeded run moves
    assert "$fn$" not in run_inputs.BODY


def test_0070_admits_the_stored_activation_pair_for_contract() -> None:
    """D-98 candidate 143 AMENDMENT 1: the ``contract`` spec admits (DRAFT, ACTIVE) — the STORED
    move of the approved SM-02 / SYSTEM activation (L4-1-Q-18) — and 0070 re-renders exactly
    ``tg_contract__transition``: its BODY is the fresh rendering (DG-ARC-07), its PREVIOUS is 0069's
    contract literal verbatim, the only difference is the pair, and the guard stays before the
    editable early-return (GUARD-TRN-1 not weakened). Fail-first: before the spec change the pair
    was absent and every approved activation raised EREV-TRN-001 (main 0959b560)."""
    revision = _load("0070_contract_activation_pair")
    assert (revision.revision, revision.down_revision) == ("0070", "0069")
    assert revision.TABLE == "contract"
    assert ("DRAFT", "ACTIVE") in TRANSITIONS["contract"].pairs
    assert ("PENDING_REVIEW", "ACTIVE") in TRANSITIONS["contract"].pairs  # kept for CTR-9
    assert revision.BODY == transition_trigger_sql("contract")  # DG-ARC-07
    assert revision.PREVIOUS == _load("0069_transition_pair_guard_rerender").BODIES["contract"]
    assert "'DRAFT>ACTIVE'" in revision.BODY and "'DRAFT>ACTIVE'" not in revision.PREVIOUS
    assert revision.BODY.replace("'DRAFT>ACTIVE', ", "") == revision.PREVIOUS
    guard, early = "IF NEW.status IS DISTINCT FROM OLD.status", "IF OLD.status::text = ANY ("
    assert revision.BODY.index(guard) < revision.BODY.index(early)
    assert "$fn$" not in revision.BODY


def test_0093_re_renders_the_manual_adjustment_pairs() -> None:
    """BUILD_SPEC CLO-12 (ruling R-51 (b); 04 T-SL-05 rev 1.120; PRD SM-10 rev 1.49): revision
    0093 carries the fresh rendering of ``tg_manual_adjustment__transition`` — the five pairs of
    SM-10 with (SUBMITTED, DRAFT), (REJECTED, DRAFT) and (DRAFT, VOIDED) — and restores the 0069
    literal on the way down; nothing but the pair list differs."""
    revision = _load(ADJUSTMENT_PAIRS)
    assert revision.revision == "0093" and revision.TABLE == "manual_adjustment"
    assert revision.BODY == transition_trigger_sql("manual_adjustment")  # DG-ARC-07
    previous = _load("0069_transition_pair_guard_rerender").BODIES["manual_adjustment"]
    assert revision.PREVIOUS == previous  # verbatim (DG-MIG-04)
    changed = [
        (old, new)
        for old, new in zip(previous.splitlines(), revision.BODY.splitlines(), strict=True)
        if old != new
    ]
    [(old, new)] = changed
    added = "'DRAFT>VOIDED', 'REJECTED>DRAFT', 'SUBMITTED>DRAFT'"
    assert all(pair in new and pair not in old for pair in added.split(", "))
    assert TRANSITIONS["manual_adjustment"].pairs == {
        ("DRAFT", "SUBMITTED"),
        ("SUBMITTED", "DRAFT"),
        ("SUBMITTED", "APPROVED"),
        ("APPROVED", "POSTED"),
        ("SUBMITTED", "REJECTED"),
        ("REJECTED", "DRAFT"),
        ("DRAFT", "VOIDED"),
        ("POSTED", "VOIDED"),
    }
    assert "$fn$" not in revision.BODY and "$fn$" not in revision.PREVIOUS


def test_0114_re_renders_the_estimate_version_pair() -> None:
    """Item EST-DISCARD-1 (supervisor ruling R-119 (e); 04 E-12, T-CON-13 rev 1.210; PRD SM-04):
    revision 0114 carries the fresh rendering of ``tg_estimate_version__transition`` — the seven
    pairs of SM-04 with (DRAFT, VOIDED), a discarded draft — and restores the 0069 literal on the
    way down; nothing but the pair list differs, and the guard stays before the editable
    early-return (GUARD-TRN-1 not weakened)."""
    revision = _load(ESTIMATE_DISCARD)
    assert revision.revision == "0114" and revision.VERSION == "estimate_version"
    assert revision.BODY == transition_trigger_sql("estimate_version")  # DG-ARC-07
    previous = _load("0069_transition_pair_guard_rerender").BODIES["estimate_version"]
    assert revision.PREVIOUS == previous  # verbatim (DG-MIG-04)
    changed = [
        (old, new)
        for old, new in zip(previous.splitlines(), revision.BODY.splitlines(), strict=True)
        if old != new
    ]
    [(old, new)] = changed
    assert "'DRAFT>VOIDED'" in new and "'DRAFT>VOIDED'" not in old
    assert new.replace("'DRAFT>VOIDED', ", "") == old
    assert TRANSITIONS["estimate_version"].pairs == {
        ("DRAFT", "SUBMITTED"),
        ("SUBMITTED", "APPROVED"),
        ("SUBMITTED", "REJECTED"),
        ("SUBMITTED", "WITHDRAWN"),
        ("APPROVED", "SUPERSEDED"),
        ("REJECTED", "DRAFT"),
        ("WITHDRAWN", "DRAFT"),
        ("DRAFT", "VOIDED"),
    }
    guard, early = "IF NEW.status IS DISTINCT FROM OLD.status", "IF OLD.status::text = ANY ("
    assert revision.BODY.index(guard) < revision.BODY.index(early)
    assert "$fn$" not in revision.BODY and "$fn$" not in revision.PREVIOUS
    # the status check is re-created over the status as text (the 0060 precedent): the label is
    # added by this same revision and is no enum literal before the transaction commits
    assert revision.STATUSES_0051 == (
        "DRAFT",
        "SUBMITTED",
        "APPROVED",
        "SUPERSEDED",
        "REJECTED",
        "WITHDRAWN",
    )


def test_0118_re_renders_the_judgement_record_pair() -> None:
    """The discard of a judgement record (the supervisor's ruling of 2026-10-01 on the lane's
    question J1 (a); 04 E-57, T-CON-19 rev 1.242; PRD SM-10): revision 0118 carries the fresh
    rendering of ``tg_judgement_record__transition`` — the five pairs of SM-10 with (DRAFT,
    VOIDED), a discarded draft — and restores the 0069 literal on the way down; nothing but the
    pair list differs, no pair leaves VOIDED, and the guard stays before the editable
    early-return (GUARD-TRN-1 not weakened)."""
    revision = _load(JUDGEMENT_DISCARD)
    assert revision.revision == "0118" and revision.RECORD == "judgement_record"
    assert (revision.ENUM, revision.VALUE) == ("judgement_status", "VOIDED")
    assert revision.BODY == transition_trigger_sql("judgement_record")  # DG-ARC-07
    previous = _load("0069_transition_pair_guard_rerender").BODIES["judgement_record"]
    assert revision.PREVIOUS == previous  # verbatim (DG-MIG-04)
    changed = [
        (old, new)
        for old, new in zip(previous.splitlines(), revision.BODY.splitlines(), strict=True)
        if old != new
    ]
    [(old, new)] = changed
    assert "'DRAFT>VOIDED'" in new and "'DRAFT>VOIDED'" not in old
    assert new.replace("'DRAFT>VOIDED', ", "") == old
    pairs = TRANSITIONS["judgement_record"].pairs
    assert pairs == {
        ("DRAFT", "SUBMITTED"),
        ("SUBMITTED", "REVIEWED"),
        ("SUBMITTED", "REJECTED"),
        ("REJECTED", "DRAFT"),
        ("REVIEWED", "SUPERSEDED"),
        ("DRAFT", "VOIDED"),
    }
    assert not [pair for pair in pairs if pair[0] == "VOIDED"]
    guard, early = "IF NEW.status IS DISTINCT FROM OLD.status", "IF OLD.status::text = ANY ("
    assert revision.BODY.index(guard) < revision.BODY.index(early)
    assert "$fn$" not in revision.BODY and "$fn$" not in revision.PREVIOUS


def test_0122_re_renders_the_import_upload_pair() -> None:
    """ACCT backlog row 4 (supervisor rulings R-108 (2) and R-105 (2) and the supervisor's ruling
    of 2026-10-02; 04 T-IMP-02 rev 1.270; PRD SM-05 rev 1.186): revision 0122 carries the fresh
    rendering of ``tg_import_upload__transition`` — the pairs of SM-05 with (DIFFING, INVALID),
    the end of a dry run whose job ended FAILED — and restores the 0087 literal on the way down;
    nothing but the pair list differs."""
    revision = _load(IMPORT_DIFF_FAILED)
    assert revision.revision == "0122"
    assert revision.TRANSITION_BODY == transition_trigger_sql("import_upload")  # DG-ARC-07
    previous = _load("0087_secfix_imp_named_entities").TRANSITION_BODY
    assert revision.TRANSITION_BODY_0087 == previous  # verbatim (DG-MIG-04)
    changed = [
        (old, new)
        for old, new in zip(
            previous.splitlines(), revision.TRANSITION_BODY.splitlines(), strict=True
        )
        if old != new
    ]
    [(old, new)] = changed
    assert "'DIFFING>INVALID'" in new and "'DIFFING>INVALID'" not in old
    assert new.replace("'DIFFING>INVALID', ", "") == old
    assert ("DIFFING", "INVALID") in TRANSITIONS["import_upload"].pairs
    assert "$fn$" not in revision.TRANSITION_BODY and "$fn$" not in revision.TRANSITION_BODY_0087


def test_0126_re_renders_the_combination_group_pair() -> None:
    """The discard of a proposed combination (item COMBINATION-PROPOSAL-DISCARD-1; 04 E-95,
    T-CON-03 rev 1.289): revision 0126 re-rendered
    ``tg_combination_group__transition`` — the four pairs of E-95 with (PROPOSED, VOIDED), a
    proposal given up before its submission — and restores the 0111 literal on the way
    down; nothing but the pair list differs, and no pair leaves VOIDED. Its body was the fresh
    rendering until the spec gained ``dirty_trigger`` (rev 1.297, item FX-REPUBLISH-DIRTY-1):
    revision 0128 carries that now, and 0126's BODY is the installed PREVIOUS of 0128."""
    revision = _load(PROPOSAL_DISCARD)
    assert revision.revision == "0126" and revision.GROUP == "combination_group"
    assert (revision.ENUM, revision.VALUE) == ("combination_status", "VOIDED")
    assert revision.BODY == _load(REPUBLISH_TRIGGER).PREVIOUS  # the rendering 0128 replaced
    previous = _load("0111_clo_gate_run_1_close_run_gate").BODY
    assert revision.PREVIOUS == previous  # verbatim (DG-MIG-04)
    changed = [
        (old, new)
        for old, new in zip(previous.splitlines(), revision.BODY.splitlines(), strict=True)
        if old != new
    ]
    [(old, new)] = changed
    assert "'PROPOSED>VOIDED'" in new and "'PROPOSED>VOIDED'" not in old
    assert new.replace("'PROPOSED>VOIDED', ", "") == old
    pairs = TRANSITIONS["combination_group"].pairs
    assert pairs == {
        ("PROPOSED", "SUBMITTED"),
        ("PROPOSED", "VOIDED"),
        ("SUBMITTED", "APPROVED"),
        ("APPROVED", "APPLIED"),
        ("SUBMITTED", "REJECTED"),
    }
    assert not [pair for pair in pairs if pair[0] == "VOIDED"]
    assert "$fn$" not in revision.BODY and "$fn$" not in revision.PREVIOUS


def test_0130_re_renders_the_checklist_item_pairs() -> None:
    """Item CLO-WAIVER-COVERS-LATER-1 (the supervisor's ruling of 2026-10-02 17:32; 04 T-CLS-03 and
    E-60 rev 1.305): revision 0130 carries the fresh rendering of
    ``tg_close_checklist_item__transition`` — the pairs of E-60 with (WAIVED, FAILED), a gate that
    counts more than its waiver covered, and (WAIVED, NOT_STARTED), the reopen of the period — and
    restores 0047's literal on the way down; nothing but the pair list differs, and no pair leads
    out of ``NOT_APPLICABLE``."""
    revision = _load(WAIVER_PAIRS)
    # the number is the register's; the parent is not pinned here — the chain follows merge order
    # (supervisor rulings R-68 (e), R-117 (h))
    assert (revision.revision, revision.TABLE) == ("0130", "close_checklist_item")
    assert revision.BODY == _load("0135_close_task_signoffs").PREVIOUS  # historical body
    previous = _load("0047_close_tables").CLOSE_CHECKLIST_ITEM_TRANSITION_BODY
    assert revision.PREVIOUS == previous  # verbatim (DG-MIG-04)
    changed = [
        (old, new)
        for old, new in zip(previous.splitlines(), revision.BODY.splitlines(), strict=True)
        if old != new
    ]
    [(old, new)] = changed
    assert new.replace(", 'WAIVED>FAILED', 'WAIVED>NOT_STARTED'", "") == old
    assert TRANSITIONS["close_checklist_item"].pairs - {("PASSED", "NOT_STARTED")} == {
        ("NOT_STARTED", "IN_PROGRESS"),
        ("NOT_STARTED", "PASSED"),
        ("NOT_STARTED", "FAILED"),
        ("NOT_STARTED", "WAIVED"),
        ("NOT_STARTED", "NOT_APPLICABLE"),
        ("IN_PROGRESS", "PASSED"),
        ("IN_PROGRESS", "FAILED"),
        ("IN_PROGRESS", "WAIVED"),
        ("IN_PROGRESS", "NOT_APPLICABLE"),
        ("FAILED", "IN_PROGRESS"),
        ("FAILED", "PASSED"),
        ("FAILED", "WAIVED"),
        ("PASSED", "FAILED"),
        ("WAIVED", "FAILED"),
        ("WAIVED", "NOT_STARTED"),
    }
    assert "$fn$" not in revision.BODY and "$fn$" not in revision.PREVIOUS


def test_0135_adds_only_the_passed_task_reopen_pair() -> None:
    """The current rendering adds reopen; downgrade restores the exact 0130 body."""
    revision = _load("0135_close_task_signoffs")
    assert revision.revision == "0135"
    assert revision.BODY == transition_trigger_sql("close_checklist_item")
    assert revision.PREVIOUS == _load(WAIVER_PAIRS).BODY
    changed = [
        (old, new)
        for old, new in zip(revision.PREVIOUS.splitlines(), revision.BODY.splitlines(), strict=True)
        if old != new
    ]
    [(old, new)] = changed
    assert new.replace(", 'PASSED>NOT_STARTED'", "") == old
    assert ("PASSED", "NOT_STARTED") in TRANSITIONS["close_checklist_item"].pairs
