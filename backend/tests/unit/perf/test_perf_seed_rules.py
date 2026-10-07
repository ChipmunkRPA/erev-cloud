"""PRF-2 pure rules of ``erev perf seed`` (dev-guide DG-MK-perf-seed step 3; 05 PERF-11; rulings
D-98
148 AMENDMENT 5): the up-to-date / other-version / resume decision and its messages, the
``perf:<16 hex>`` cluster validation, the resume-ledger comment parser, the report document, and the
personas' role split (approver never the preparer). CPU only; the seed itself is Ray-side."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from erev_api.domain.contracts import events as contract_events
from erev_api.domain.demo import builders, closing, perf_seed, volume
from erev_api.domain.imports import exceptions
from erev_api.enums import (
    AccountRole,
    AccountType,
    ClearingPurpose,
    ContractEventType,
    PeriodState,
)


@pytest.fixture(scope="module")
def small() -> volume.VolumeManifest:
    return volume.manifest(Fraction(1, 1000))


def _ledger(manifest: volume.VolumeManifest, **overrides: object) -> perf_seed.Ledger:
    base: dict[str, object] = {
        "calendar": True,
        "products": len(manifest.products),
        "templates": len(manifest.templates),
        "contracts": frozenset(c.external_id for c in manifest.contracts),
        "months_appended": {c.external_id: frozenset(range(1, 24)) for c in manifest.contracts},
        "months_locked": frozenset(range(1, 24)),
        "seed_snapshot": uuid4(),
    }
    base.update(overrides)
    return perf_seed.Ledger(**base)  # type: ignore[arg-type]


def test_decision_up_to_date_other_version_resume_and_fresh(small: volume.VolumeManifest) -> None:
    facts = perf_seed.TenantFacts(uuid4(), small.industry_cluster, True, "PRODUCTION")
    done = perf_seed.decide(facts, _ledger(small), small)
    assert done == perf_seed.Decision("up_to_date", "perf-volume up to date", 0)
    assert perf_seed.decide(facts, _ledger(small), small, snapshot_only=True) == done
    other = perf_seed.TenantFacts(uuid4(), "perf:0000000000000000", True, "PRODUCTION")
    for mode in (False, True):
        assert perf_seed.decide(other, _ledger(small), small, snapshot_only=mode) == (
            perf_seed.Decision(
                "other_version",
                "perf tenant built from another generator version; run make db-reset",
                2,
            )
        )
    assert perf_seed.decide(None, None, small).outcome == "seeded"
    # Steps 1-3 complete, step 5 pending: the seed phase is a no-op that names the next step; the
    # snapshot phase takes the snapshot (D-98 148 A5 Q6: ANALYZE runs between them).
    locked = _ledger(small, seed_snapshot=None)
    pending = perf_seed.decide(facts, locked, small)
    assert pending.outcome == "locked" and pending.exit_code == 0
    assert "erev perf seed --snapshot-only" in pending.message
    assert perf_seed.decide(facts, locked, small, snapshot_only=True) == perf_seed.Decision(
        "snapshot", "taking the stored snapshot of perf-volume", 0
    )
    for partial in (
        _ledger(small, months_locked=frozenset(range(1, 23))),
        _ledger(small, contracts=frozenset()),
        _ledger(small, calendar=False),
        _ledger(small, products=0),
        _ledger(small, templates=len(small.templates) - 1),
    ):
        resumed = perf_seed.decide(facts, partial, small)
        assert resumed.outcome == "resumed" and resumed.exit_code == 0
        refused = perf_seed.decide(facts, partial, small, snapshot_only=True)
        assert refused == perf_seed.Decision(
            "refused",
            "perf-volume is not locked through month 23; run erev perf seed before --snapshot-only",
            1,
        )
    assert perf_seed.decide(None, None, small, snapshot_only=True).outcome == "refused"
    assert perf_seed.EXIT_UP_TO_DATE == 0 and perf_seed.EXIT_OTHER_VERSION == 2
    assert perf_seed.EXIT_PRECONDITION == 1
    assert perf_seed.SEED_MONTHS == 23  # month 24 is held back for make perf


def test_cluster_pattern_and_manifest_binding(small: volume.VolumeManifest) -> None:
    """05 PERF-11: the volume tenant's cluster is exactly perf:<first 16 hex of the SHA-256>."""
    assert perf_seed.cluster_valid(small.industry_cluster)
    assert small.industry_cluster == f"perf:{small.sha256[:16]}"
    assert perf_seed.cluster_valid(None) and perf_seed.cluster_valid("saas-cluster")
    for bad in (
        "perf:",
        "perf:XYZ",
        "perf:0123456789abcde",
        "perf:0123456789abcdef0",
    ):
        assert not perf_seed.cluster_valid(bad), bad


def test_resume_ledger_reads_volume_append_comments() -> None:
    read = perf_seed._appended_month  # noqa: SLF001
    cluster = "perf:0123456789abcdef"
    assert read(f"Volume month 7 ({cluster})", cluster) == 7
    assert read(f"Volume month 24 ({cluster})", cluster) == 24
    assert read("Volume month 7 (perf:fedcba9876543210)", cluster) is None  # another manifest
    assert read("Ready for review.", cluster) is None
    assert read("", cluster) is None


def test_personas_are_sod_clean_and_cover_the_seed(small: volume.VolumeManifest) -> None:
    """Codex 0105 P7-PRF2-PERSONA-1 (pure part): the admin is the provisioning Tenant Admin and
    nothing else; the accountant prepares — a month's close too: the soft close, the close run,
    the journal run and its export, the lock request, the waiver request of a late event (item
    PERF-SEED-LOCK-1) —, the controller opens the periods, decides the locks and takes the
    snapshot, the reviewer approves; no persona meets both functions of any default SoD rule (so
    the invitations pass
    ``sod.assert_assignments_allowed``); every permission the seed uses as a persona is granted by
    that persona's default roles; the approver is never the preparer. The EFFECTIVE grants are
    read back by ``_require_grants`` (DB witness in tests/domain/demo/test_perf_seed.py)."""
    admin, accountant, controller, reviewer = perf_seed.CAST
    assert (admin.key, accountant.key, controller.key, reviewer.key) == (
        volume.PERF_CAST.admin,
        volume.PERF_CAST.accountant,
        volume.PERF_CAST.controller,
        volume.PERF_CAST.reviewer,
    )
    assert len({p.key for p in perf_seed.CAST}) == 4 and len({p.email for p in perf_seed.CAST}) == 4
    assert admin.roles_in("journey") == ("tenant_admin",)
    for persona in perf_seed.CAST:
        assert perf_seed.sod_conflicts(persona) == (), persona.key
        held = perf_seed.expected_permissions(persona)
        assert perf_seed.REQUIRED_PERMISSIONS[persona.key] <= held, persona.key
        assert set(persona.roles_in("industry")) == set(persona.roles_in("journey"))
    # The seed's command guards, by persona (volume.py constants), and the approval subjects'
    # required permissions the reviewer decides (approvals/subjects.py).
    accountant_held = perf_seed.expected_permissions(accountant)
    for permission in (
        volume.MASTERDATA_MAINTAIN,
        volume.CONFIG_AUTHOR,
        volume.SSP_CREATE,
        volume.CONTRACT_CREATE,
        volume.EVENT_RECORD,
        volume.MODIFICATION_CREATE,
        volume.JUDGEMENT_CREATE,
        # A month's close as its preparer, by the route guards of the helper's commands, and the
        # waiver request of a late event.
        closing.CLOSE,
        closing.JOURNAL_RUN,
        closing.JOURNAL_EXPORT,
        exceptions.RESOLVE_PERMISSION,
    ):
        assert permission in accountant_held, permission
        assert permission in perf_seed.REQUIRED_PERMISSIONS[accountant.key], permission
    assert volume.SETTINGS_MANAGE in perf_seed.expected_permissions(admin)
    controller_held = perf_seed.expected_permissions(controller)
    assert {"period.close", "period.lock", "tenant.snapshot"} <= controller_held
    from erev_api.approvals.subjects import SUBJECTS
    from erev_api.enums import ApprovalSubjectType as S

    # The lock is decided by the controller, who prepared nothing of the month; the reviewer, who
    # approved its journal run, is asked no lock permission.
    lock = SUBJECTS[S.PERIOD_LOCK].required_permission
    assert lock in controller_held and lock in perf_seed.REQUIRED_PERMISSIONS[controller.key]
    assert lock not in perf_seed.REQUIRED_PERMISSIONS[reviewer.key]
    # A second step held by a Controller — of an estimate version, of an activation of USD
    # 1,000,000.00 and more (PRD §2.5) — is decided by the cast's controller, who decides no
    # first step.
    from erev_api.approvals.subjects import CONTROLLER_ROLE

    assert CONTROLLER_ROLE in controller.roles_in("journey")
    for subject in (S.ESTIMATE_VERSION, S.CONTRACT_ACTIVATION):
        assert SUBJECTS[subject].second_step_role == CONTROLLER_ROLE, subject.value
        needed = SUBJECTS[subject].required_permission
        assert needed in controller_held, subject.value
        assert needed in perf_seed.REQUIRED_PERMISSIONS[controller.key], subject.value
    reviewer_held = perf_seed.expected_permissions(reviewer)
    for subject in (
        S.FX_RATE_SET_VERSION,
        S.POB_TEMPLATE_VERSION,
        S.SSP_BOOK_VERSION,
        S.JUDGEMENT_RECORD,
        S.CONTRACT_ACTIVATION,
        S.ESTIMATE_VERSION,
        S.MODIFICATION,
        S.PRINCIPAL_AGENT_CHANGE,
        S.ACCOUNT_MAPPING_VERSION,
        S.REGISTRY_VERSION,  # the CLOSE version: no reconciliation is asked at a lock
        S.JOURNAL_RUN,
        S.EXCEPTION_WAIVER,
    ):
        assert SUBJECTS[subject].required_permission in reviewer_held, subject.value
    for subject in (S.REGISTRY_VERSION, S.JOURNAL_RUN, S.EXCEPTION_WAIVER):
        needed = SUBJECTS[subject].required_permission
        assert needed in perf_seed.REQUIRED_PERMISSIONS[reviewer.key], subject.value
    # Preparer / approver separation: nothing the accountant prepares can the accountant approve.
    assert not (accountant_held & {SUBJECTS[s].required_permission for s in SUBJECTS})
    assert "user.manage" not in accountant_held | reviewer_held


def test_report_document_and_warning(tmp_path: Path, small: volume.VolumeManifest) -> None:
    result = perf_seed.PerfSeedResult(
        outcome="seeded",
        exit_code=0,
        message="seeded",
        manifest_sha256=small.sha256,
        industry_cluster=small.industry_cluster,
        contracts=len(small.contracts),
        obligations=small.counts.obligations,
        events_appended=100,
        events_reused=7,
        events_deferred=2,
        months_locked=23,
        snapshot_id=str(uuid4()),
        seconds=3_601.0,
        warning="perf seed took 3601 s, above 3,600 s (05 PERF-04)",
    )
    written = perf_seed.write_report(result, tmp_path)
    body = json.loads(written.read_text(encoding="utf-8"))
    assert written == tmp_path / "perf-seed" / "report.json"
    assert body["manifest_sha256"] == small.sha256 and body["months_locked"] == 23
    assert body["warning"].startswith("perf seed took") and body["events_deferred"] == 2
    assert body["phase"] == "seed"
    assert perf_seed.WARN_SECONDS == 3_600.0
    # The step-5 phase merges into the seed phase's document: counts kept, snapshot added.
    snapshot = perf_seed.PerfSeedResult(
        outcome="snapshot",
        exit_code=0,
        message=perf_seed.TAKING_SNAPSHOT,
        manifest_sha256=small.sha256,
        industry_cluster=small.industry_cluster,
        contracts=len(small.contracts),
        obligations=small.counts.obligations,
        events_appended=0,
        events_reused=0,
        events_deferred=0,
        months_locked=23,
        snapshot_id=str(uuid4()),
        seconds=12.5,
        phase="snapshot",
    )
    merged = json.loads(perf_seed.write_report(snapshot, tmp_path).read_text(encoding="utf-8"))
    assert merged["phase"] == "snapshot" and merged["snapshot_id"] == snapshot.snapshot_id
    assert merged["events_appended"] == 100 and merged["events_deferred"] == 2  # kept
    assert merged["events_reused"] == 7 and body["events_reused"] == 7
    assert merged["seconds"] == 3_601.0 and merged["snapshot_seconds"] == 12.5
    assert merged["warning"].startswith("perf seed took")  # the seed phase's warning survives
    assert perf_seed.merge_report(None, snapshot.document()) == snapshot.document()
    assert perf_seed.merge_report(body, result.document()) == result.document()  # seed phase


def test_provisioning_validates_a_perf_cluster(small: volume.VolumeManifest) -> None:
    """DG-KRN-TEN-03 (D-98 148 A5 (1)): the optional provisioning member accepts the manifest's
    cluster and free text, and refuses a malformed ``perf:`` value with INDUSTRY_CLUSTER_FORMAT;
    the perf seed's own predicate agrees with the provisioning rule."""
    from erev_api.domain.platform import provisioning

    def request(cluster: str | None) -> provisioning.TenantProvisionRequest:
        return provisioning.TenantProvisionRequest(
            code="perf-volume",
            display_name="Volume tenant (performance)",
            reporting_currency="USD",
            is_demo=True,
            admin_email="perf-admin@demo.erev",
            industry_cluster=cluster,
        )

    assert provisioning.validation_errors(request(None)) == []
    assert provisioning.validation_errors(request(small.industry_cluster)) == []
    assert provisioning.validation_errors(request("saas-cluster")) == []
    assert provisioning.validation_errors(request("Fintech / lending (EU)")) == []  # TY-07 text
    for bad in ("perf:", "perf:XYZ", "perf:0123456789abcde", "x" * 401):
        (error,) = provisioning.validation_errors(request(bad))
        assert (error.field, error.rule_id) == ("industry_cluster", "INDUSTRY_CLUSTER_FORMAT"), bad
        assert perf_seed.cluster_valid(bad) is (not bad.startswith("perf:"))
    assert (
        provisioning.TenantProvisionRequest.__dataclass_fields__["industry_cluster"].default is None
    )


def test_deferred_types_after_ruling(small: volume.VolumeManifest) -> None:
    """D-98 148 A5 (4) and the F-CTR landing (main 0959b560): ESTIMATE_CHANGED goes through the
    estimate commands and CONTRACT_AMENDED through the CTR-17 modification commands. Record §4.26
    (the sixth measurement): MATERIAL_RIGHT_EXERCISED / EXPIRED are counted, not appended, until
    their own command lands — `record_events` refuses them (API-R-30) and ENB-5 is unbuilt; the
    recipe binds the set."""
    from erev_api.domain.contracts.events import RECORDED_TYPES
    from erev_api.enums import ContractEventType as T

    assert volume.DEFERRED_EVENT_TYPES == frozenset(
        {T.MATERIAL_RIGHT_EXERCISED.value, T.MATERIAL_RIGHT_EXPIRED.value}
    )
    assert not {T(value) for value in volume.DEFERRED_EVENT_TYPES} & RECORDED_TYPES
    assert small.recipe.deferred_event_types == tuple(sorted(volume.DEFERRED_EVENT_TYPES))
    assert '"deferred_event_types"' in small.to_json().decode("ascii")
    assert T.ESTIMATE_CHANGED.value not in volume.DEFERRED_EVENT_TYPES
    assert T.CONTRACT_AMENDED.value not in volume.DEFERRED_EVENT_TYPES
    assert volume.SEPARATE_OUTCOME.startswith("CONTRACT_AMENDED")
    assert volume.MODIFICATION_CREATE == "modification.create"


def test_modification_bodies_bind_to_ctr17_lines(small: volume.VolumeManifest) -> None:
    """The CONTRACT_AMENDED seed path builds API-S-Modification create bodies from the manifest,
    pure: CHANGE lines name an existing obligation of the contract, ADD lines name a product,
    money is in the contract's currency (T-CON-06), the reference is unique per event, and the
    real request model validates every body."""
    from datetime import date

    from erev_api.schemas.modifications import ModificationCreateIn

    spec = small.contracts[0]
    keys = {o.key for o in spec.obligations}
    products = {p.code for p in small.products}
    seen: set[str] = set()
    for seq, treatment in ((7, "PROSPECTIVE"), (11, "CUMULATIVE_CATCH_UP")):
        event = volume.VolumeEvent(
            seq=seq,
            contract_seq=spec.seq,
            obligation_key=None,
            event_type="CONTRACT_AMENDED",
            effective_month=6,
            effective_date=date(2025, 6, 15),
            recorded_month=6,
            late=False,
            detail=(("treatment", treatment),),
        )
        body = volume.modification_body(small, spec, event)
        model = ModificationCreateIn.model_validate(body)  # the real request model
        assert body["reference"] not in seen and body["reference"].startswith(spec.external_id)
        seen.add(body["reference"])
        (line,) = model.lines
        assert line.consideration_delta is not None
        assert line.consideration_delta.currency == spec.currency
        if treatment == "CUMULATIVE_CATCH_UP":
            assert model.kind.value == "PRICE_CHANGE" and line.action == "CHANGE"
            assert line.obligation_key in keys and line.quantity_delta == "0"
        else:
            assert model.kind.value == "ADD_OBLIGATION" and line.action == "ADD"
            assert line.product_code in products and line.obligation_key not in keys
            # twelve whole months from the effective month, aligned like the contract lines
            assert line.start_date == date(2025, 6, 15) and line.end_date == date(2026, 5, 31)
    assert "treatment" in body["rationale"]


def test_prospective_modification_kind_passes_the_s06_r_19_shape_gate(
    full: volume.VolumeManifest,
) -> None:
    """Lane FIX-A (supervisor ruling of 2026-09-29; record §4.27): the seed's PROSPECTIVE body is
    one ADD line running twelve months from the effective month. The engine's own S06-R-19 gate
    (``subscriptions.check``, the refusal ``/classify`` answers 422 for — 04 §16.14 rev 1.84, PRD
    ERR-55) admits every such body of the FULL manifest (275) under the generic kind the seed
    sends and refuses every one under ``UPGRADE`` (a CHANGE line on the subscription obligation)
    — what version 3 sent, so none of its PROSPECTIVE modifications could be classified.
    ``CO_TERM`` (an ADD line ending on an original end date) fits only the 25 bodies whose twelve
    months happen to end with a booked line, which is why the seed does not send it."""
    from datetime import date

    from erev_api.enums import ModificationKind
    from erev_engine.stages.s06_modifications import subscriptions
    from erev_engine.stages.s06_modifications.classify import ModificationLine, ModificationView

    def view(body: dict[str, Any], kind: str) -> ModificationView:
        (line,) = body["lines"]
        return ModificationView(
            contract_key="VOL",
            modification_key=str(body["reference"]),
            effective_date=date.fromisoformat(body["effective_date"]),
            kind=kind,
            template_mode=None,
            questionnaire={},
            lines=(
                ModificationLine(
                    obligation_key=line["obligation_key"],
                    action=line["action"],
                    product_code=line["product_code"],
                    quantity_delta=Fraction(line["quantity_delta"]),
                    consideration_delta=Fraction(line["consideration_delta"]["amount"]),
                    members={"start_date": line["start_date"], "end_date": line["end_date"]},
                ),
            ),
            price_change_amount=None,
            event=None,
        )

    def booked(spec: volume.VolumeContract) -> list[Any]:
        # the members of ObligationState the gate reads: the key and the booked end date
        lines = [volume._line(o, spec) for o in spec.obligations]  # noqa: SLF001 — the booking
        return [
            SimpleNamespace(
                obligation_key=line["obligation_key"],
                end_date=date.fromisoformat(line["end_date"]) if "end_date" in line else None,
            )
            for line in lines
        ]

    assert ModificationKind.ADD_OBLIGATION.value not in subscriptions.KINDS
    co_terminous: list[bool] = []
    for event in full.events():
        if event.event_type != "CONTRACT_AMENDED":
            continue
        if dict(event.detail).get("treatment", "PROSPECTIVE") != "PROSPECTIVE":
            continue
        spec = full.contracts[event.contract_seq - 1]
        assert spec.seq == event.contract_seq
        body = volume.modification_body(full, spec, event)
        existing = booked(spec)
        assert body["kind"] == ModificationKind.ADD_OBLIGATION.value
        subscriptions.check(view(body, body["kind"]), existing)  # admitted: no refusal
        with pytest.raises(ValueError, match=r"does not have the UPGRADE shape \(S06-R-19\)"):
            subscriptions.check(view(body, "UPGRADE"), existing)
        ends_with_a_booked_line = date.fromisoformat(body["lines"][0]["end_date"]) in {
            ob.end_date for ob in existing
        }
        if ends_with_a_booked_line:
            subscriptions.check(view(body, "CO_TERM"), existing)
        else:
            with pytest.raises(ValueError, match=r"does not have the CO_TERM shape \(S06-R-19\)"):
                subscriptions.check(view(body, "CO_TERM"), existing)
        co_terminous.append(ends_with_a_booked_line)
    assert (len(co_terminous), sum(co_terminous)) == (275, 25)


def test_estimate_versions_resume_by_a_per_event_marker(small: volume.VolumeManifest) -> None:
    """Codex 0105 RESUME-1, the same seam checked in the event paths: an interrupted month re-runs
    its events, so the estimate path must find the version it already created rather than create
    a second one — the version's rationale is unique per manifest event (its seq) and stable
    across runs; the modification path keys on the per-event reference the same way."""
    from datetime import date

    seen: set[str] = set()
    for seq in (3, 4, 250, 251):
        event = volume.VolumeEvent(
            seq=seq,
            contract_seq=1,
            obligation_key="POB-01",
            event_type="ESTIMATE_CHANGED",
            effective_month=6,
            effective_date=date(2025, 6, 30),
            recorded_month=6,
            late=False,
            detail=(("estimate_kind", "EAC"), ("amount", "1000.00"), ("currency", "USD")),
        )
        marker = volume.estimate_rationale(event)
        assert marker == volume.estimate_rationale(event)  # stable across runs
        assert f"event {seq}," in marker and marker not in seen
        seen.add(marker)
    spec = small.contracts[0]
    references = {
        volume.modification_body(
            small,
            spec,
            volume.VolumeEvent(
                seq, spec.seq, None, "CONTRACT_AMENDED", 6, date(2025, 6, 15), 6, False, ()
            ),
        )["reference"]
        for seq in (3, 4)
    }
    assert len(references) == 2
    assert volume.DONE_CONFIG == {"APPROVED", "PUBLISHED", "SUPERSEDED"}
    assert volume.STUCK_CONFIG == {"REJECTED", "WITHDRAWN"}


def test_tally_separates_applied_reused_and_separate() -> None:
    """Codex 0206 §5: the counter rule, isolated. A reused effect (a complete estimate version, an
    APPLIED modification, an already-appended batch found again on resume) is never reported as
    appended; a SEPARATE_CONTRACT modification is never reported as an amendment."""
    assert volume.tally([]) == (0, 0, 0)
    assert volume.tally([volume.APPLIED, volume.APPLIED, volume.REUSED, volume.SEPARATE]) == (
        2,
        1,
        1,
    )
    assert volume.tally([volume.REUSED] * 3) == (0, 3, 0)
    with pytest.raises(ValueError, match="unknown event outcome"):
        volume.tally(["appended"])
    month = volume.MonthTally(appended=5, reused=2, deferred={volume.SEPARATE_OUTCOME: 1})
    assert (month.appended, month.reused, sum(month.deferred.values())) == (5, 2, 1)
    assert {volume.APPLIED, volume.REUSED, volume.SEPARATE} == {"applied", "reused", "separate"}
    fields = volume.SeedReport.__dataclass_fields__
    assert ("events_appended", "events_reused", "events_deferred") <= tuple(fields)
    assert "events_reused" in perf_seed.PerfSeedResult.__dataclass_fields__


def test_append_outcome_counts_deferred_computation_as_appended() -> None:
    """Codex 0233 APPEND-OUTCOME-1: ``record_events`` appends the events and then returns EITHER
    the appended events with a synchronous computation OR ``appended = None`` with the job of a
    DEFERRED computation — both are fresh appends; only a ``submission`` (routed for approval)
    appended nothing, and the seed refuses it by name. The computation payload never decides."""
    from types import SimpleNamespace

    synchronous = SimpleNamespace(
        appended=SimpleNamespace(events=[object(), object(), object()]), job=None, submission=None
    )
    assert volume.append_outcome(synchronous, 3) == 3
    deferred = SimpleNamespace(appended=None, job=SimpleNamespace(id="job"), submission=None)
    assert volume.append_outcome(deferred, 7) == 7  # appended; the computation runs in the job
    routed = SimpleNamespace(appended=None, job=None, submission=SimpleNamespace(id="sub"))
    with pytest.raises(LookupError, match="routed for approval"):
        volume.append_outcome(routed, 2)
    with pytest.raises(LookupError, match="neither"):
        volume.append_outcome(SimpleNamespace(appended=None, job=None, submission=None), 1)


def test_resume_ledger_binds_to_durable_appends() -> None:
    """Codex 0246 §1–§2: an ordinary ``record_events`` writes no event_submission row; its durable
    effects are the contract_event rows and the audit detail carrying the Volume comment and the
    appended event ids. The ledger marks (contract, month) done only when the comment names THIS
    manifest's month AND every appended event id still persists; a comment alone, another
    manifest's comment, or an audit whose events are gone marks nothing."""
    from uuid import uuid4

    cluster = "perf:0123456789abcdef"
    c1, c2 = uuid4(), uuid4()
    e1, e2, e3, e4 = (str(uuid4()) for _ in range(4))
    rows = [
        (c1, {"comment": f"Volume month 3 ({cluster})", "event_ids": [e1, e2]}),  # persisted
        (c1, {"comment": f"Volume month 4 ({cluster})", "event_ids": [e3, e4]}),  # e4 gone
        (c2, {"comment": f"Volume month 3 ({cluster})", "event_ids": []}),  # nothing appended
        (c2, {"comment": "Volume month 3 (perf:fedcba9876543210)", "event_ids": [e1]}),  # other
        (c2, {"comment": "Attribute change", "event_ids": [e1]}),  # not a volume append
        (c2, None),
    ]
    done = perf_seed.months_from_audit(rows, {e1, e2, e3}, cluster)
    assert done == {str(c1): {3}}
    assert perf_seed.months_from_audit(rows, {e1, e2, e3, e4}, cluster) == {str(c1): {3, 4}}
    assert perf_seed.months_from_audit([], {e1}, cluster) == {}


def test_distinct_reviews_needed_follow_the_activation_checklist(
    small: volume.VolumeManifest,
) -> None:
    """First DB measurement (2026-09-22): the activation checklist's DISTINCT_REVIEW item ([J]
    L4-1-Q-19) wants a REVIEWED POB_DISTINCT_OVERRIDE record for every obligation of a two-or-more
    obligation contract whose template concludes distinct / nondistinct; series templates and
    single-obligation contracts need none. The pure rule the seed follows; the demo scaffold
    reviewer is marcus, who holds config.approve for the FX rate set and template approvals."""
    distinctness = {t.code: str(t.outputs.get("distinctness")) for t in small.templates}
    assert set(distinctness.values()) == {"series", "distinct"}  # no nondistinct template
    for spec in small.contracts:
        needed = volume.distinct_reviews_needed(small, spec)
        if len(spec.obligations) < 2:
            assert needed == ()
            continue
        expected = tuple(
            ob.key for ob in spec.obligations if distinctness[ob.template_code] == "distinct"
        )
        assert needed == expected
        assert all(
            distinctness[ob.template_code] == "series"
            for ob in spec.obligations
            if ob.key not in needed
        )
    assert any(volume.distinct_reviews_needed(small, c) for c in small.contracts)
    assert volume.DEMO_CAST.reviewer == "marcus" and volume.DEMO_CAST.accountant == "maya"
    # A request of two steps is decided by the reviewer, then by the controller: two people.
    for cast in (volume.DEMO_CAST, volume.PERF_CAST):
        assert cast.controller != cast.reviewer
    from erev_api.auth.permissions import DEFAULT_ROLES
    from erev_api.domain.demo.personas import PERSONAS

    marcus = next(p for p in PERSONAS if p.key == "marcus")
    held = frozenset().union(*(DEFAULT_ROLES[c] for c in marcus.roles_in("journey")))
    assert {"config.approve", "ssp.approve", "judgement.review", "contract.approve"} <= held
    # The controller slot decides a second step and opens the periods: the world's other Controller.
    second = next(p for p in PERSONAS if p.key == volume.DEMO_CAST.controller)
    assert "controller" in second.roles_in("journey")
    assert {"estimate.approve", "contract.approve", "period.close"} <= frozenset().union(
        *(DEFAULT_ROLES[c] for c in second.roles_in("journey"))
    )


@pytest.fixture(scope="module")
def full() -> volume.VolumeManifest:
    return volume.manifest()


def test_chart_and_wildcard_mapping_cover_the_enums_exactly_once(
    small: volume.VolumeManifest,
) -> None:
    """Record §4.22 (ruled, 2026-09-22): ONE role-kind table covers every ``AccountRole`` member
    exactly once with a valid account type; the synthetic GL codes are unique and the normal
    balance follows the type; the wildcard rules are every non-reserved role once and
    ``BILLING_CLEARING`` once per ``ClearingPurpose`` (D-14a: reserved roles accept no rule; only
    BILLING_CLEARING names a purpose), keys unique; the recipe binds the chart, the rules and the
    mapping name; the seed says what the configuration is — synthetic, not an accounting
    judgement."""
    from erev_api.domain.reference.mapping import RESERVED_ROLES

    roles = [role for role, _ in volume.ROLE_KIND]
    assert sorted(r.value for r in roles) == sorted(m.value for m in AccountRole)
    assert len(roles) == len(set(roles)) == len(AccountRole)
    assert {kind for _, kind in volume.ROLE_KIND} <= set(AccountType)
    chart = volume.chart_rows()
    assert len(chart) == len(AccountRole) and len({code for _, code, _, _ in chart}) == len(chart)
    for role, code, name, kind in chart:
        assert code[0] == volume.KIND_PREFIX[AccountType(kind)] and len(code) == 4, (role, code)
        assert name and AccountType(kind) is dict(volume.ROLE_KIND)[AccountRole(role)]
        assert volume.normal_balance(kind) == (
            "D" if kind in (AccountType.ASSET.value, AccountType.EXPENSE.value) else "C"
        )
    rules = volume.mapping_rule_keys()
    expected = [
        r.value
        for r in roles
        if r.value not in RESERVED_ROLES and r is not AccountRole.BILLING_CLEARING
    ] + [f"BILLING_CLEARING:{purpose.value}" for purpose in ClearingPurpose]
    assert sorted(rules) == sorted(expected) and len(set(rules)) == len(rules)
    assert all(
        r.value in RESERVED_ROLES or r.value in {k.partition(":")[0] for k in rules} for r in roles
    )
    assert small.recipe.chart == chart and small.recipe.mapping_rules == rules
    assert small.recipe.mapping_name == volume.MAPPING_NAME
    assert "not an accounting judgement" in volume.MAPPING_NOTES
    assert "no chart of accounts is certified" in volume.MAPPING_NOTES


# Item PERF-SEED-LOCK-1's part of the pin below, in one place: the generator's version as that
# item raised it — a contract-month sent by effective date — and the identity of the full manifest
# under the version before it. Other lanes raise the number as well: where the heads are joined
# these two are restated, with the constant and its comment in volume.py (the supervisor's word
# of 2026-10-02).
SENT_BY_DATE_VERSION = 10
IDENTITY_BEFORE_SENT_BY_DATE = "0a627e3e94cde52daafde7ecde3135455ae44f5285fa324e3dd895dc7435ed30"


def test_generator_version_3_binds_the_chart_and_keeps_the_event_set(
    full: volume.VolumeManifest,
) -> None:
    """Record §4.22 (c): GENERATOR_VERSION 3 — the chart and rules enter the recipe, the identity
    changes with them, and the event set is unchanged at 1,262,407 events (the ruled pin).
    Record §4.27: version 4 — the PROSPECTIVE modification kind (the seeded state changes with
    it); the recipe and the event set are those of version 3. Version 5 (BUILD_SPEC CTR-6): a
    contract-month that holds a manual event is appended by the event reviewer's approval of the
    accountant's request, so the seeded state changes again — event submissions, ``MANUAL_EVENT``
    requests, rows appended as SYSTEM — while the recipe's other members and the event set stay
    those of version 3 (the bump follows the constant's own rule, MANIFEST-BINDING-1). Version 6
    (item EVT-USAGE-MANUAL-1; 05 PERF-15 rev 1.187): a usage report is a manual event, so the
    contract-months that hold one wait for the event reviewer too; the seeded state changes in
    the same way and the event set stays. Version 7
    (BUILD_SPEC CTR-12; 04 §16.14 rev 1.241): an estimate version is submitted with its evidence
    document and, for the variable-consideration bonus, its reviewed ``CONSTRAINT`` record, so
    the seeded state changes again — files, attachments, judgement records with their requests
    and decisions — while the recipe's other members and the event set stay those of version 3.
    Version 8 (item EVT-EVIDENCE-1; 05 PERF-15 rev 1.192): the approval of a contract-month
    attaches the entity's evidence document to every event it appends, so the seeded state
    changes once more — an attachment per event of a request sent with the document — and
    the event set stays. Version 9 (item ACT-FLAGS-1; 05 PERF-15 rev 1.204): every generated
    contract states its two terms and the request of an activation states the flags of its
    record and its amount in US dollars, so the seeded state changes — the requests' flags,
    amounts and steps — while the manifest and the event set stay. Version 10 (item
    PERF-SEED-LOCK-1, ``SENT_BY_DATE_VERSION``; 05 PERF-15 rev 1.182): a contract-month is
    sent by effective date, so the order in which a contract's events are recorded and the
    LATE_EVENT items change; the recipe's other members and the event set stay those of
    version 3. Version 11 (item ENG-COST-READBACK-1; 04 T-SL-04 ``subject_key``): a ledger line
    stores the subject of its entry and the read-back answers it, so the seeded ledger no
    longer holds the pairs a later computation posted again for a cost asset, a
    refund-liability component and a contract-level loss unit; the recipe's other members
    and the event set are unchanged by it. Version 13 (item USAGE-REPORT-PERIOD-ENDED-1; 04
    §16.3 "The usage period of a report", rev 1.320; 05 PERF-15 rev 1.214): a usage report ends
    its usage period at its own date where it named the whole month, which the door refuses,
    so the fee of a report is realised on the report's date and the version rows of a usage
    obligation hold it from then; the manifest and the event set do not hold the period and
    stay. Version 12 was withdrawn with register index 87 and never seeded. Version 14 (item
    ENG-USAGE-FIXED-SCHEDULE-1, register index 87, returned behind register index 306;
    ENGINE_SPEC_B S09-R-45 rev 1.126; 05 PERF-15 rev 1.212): the engine calls the fixed fee of a
    usage obligation deterministic, so a seed stores every usage obligation with its remainder
    scheduled, with schedule lines to its term end and with those lines flagged as released at
    close; the manifest, the recipe's other members and the event set stay. Version 15 preserves
    exact fractional delivery quantities instead of independently rounding the batches to whole
    units. Event counts stay the same; event facts and the dataset identity change."""
    assert SENT_BY_DATE_VERSION < volume.GENERATOR_VERSION
    assert volume.GENERATOR_VERSION == 16 == full.recipe.generator_version
    assert full.counts.events == 1_262_407
    assert full.industry_cluster == f"perf:{full.sha256[:16]}"
    encoded = full.to_json().decode("ascii")
    assert volume.MAPPING_NAME in encoded and '"mapping_rules"' in encoded and '"chart"' in encoded
    # Another generator version or another configuration is another identity: the version-2
    # identity and the interim mapping-only identity (superseded before any run) differ.
    assert full.sha256 != "aa2a3aa9d5a3a63a2cd0429a943e7f6268a4c00b5932e174e08b411da5971781"
    assert full.sha256 != "92534af010a80e2f9b7f8c3b763c33e040386c4dbdbfc1b23286bdd16b399922"
    # The single-currency-entries identity ran once (185bf505) and was refused FX_RATE_MISSING.
    assert full.sha256 != "27c5129c1636ca124d60bb9329945eb1d41dc8af2bdc86897426fbb42429e3a5"
    # The pre-sweep identity (A+ only): superseded by the folds and the inception clamp (§4.25).
    assert full.sha256 != "f6cd567bbe77611d63b6951737d548f7172cc84aa9e071b4bc5fe95a4b6e259b"
    # The version-4 identity: the same recipe seeded by a persona's direct appends (before CTR-6).
    assert full.sha256 != "4b4ac3dab345388aaf8eb237d607e536d110780afb67bd9429649b3cc711b4c3"
    # The version-5 identity: usage reports still appended by the accountant alone.
    assert full.sha256 != "86d14c2d803327b07d0f0a5f02ca6a85de9cd603d9106c5e279a9fde189fde94"
    # The version-6 identity: the same recipe with estimate versions submitted bare (before the
    # evidence and the CONSTRAINT record of 04 §16.14 rev 1.241).
    assert full.sha256 != "8f279b2663f4524f9963722574abf8b59bab0b4c2b89633a2b7c15ce3947f256"
    # The version-7 identity: the evidence document on the approval request alone.
    assert full.sha256 != "ea853a880c0214525cdab32fcb83f0ee0233016b3f0b21b430f9f4ada686fe35"
    # The version-8 identity: the same recipe with activations routed by four flags and the
    # booking's total in the transaction currency (before item ACT-FLAGS-1).
    assert full.sha256 != "1a1aae4e70a8cf3c2068f86d77aca7ad21a16ee41119c2d6503d2280fc9bec37"
    # The version-9 identity, the version before item PERF-SEED-LOCK-1's: the same recipe with
    # a contract-month sent as the manifest lists it.
    assert full.sha256 != IDENTITY_BEFORE_SENT_BY_DATE
    # The version-10 identity: the same recipe, its ledger with the pairs a later computation
    # posted again for a cost asset, a refund-liability component and a contract-level loss
    # unit (before item ENG-COST-READBACK-1).
    assert full.sha256 != "4c8875b75a5f4572778102740497510df7d54e6c399d27de1f17106e3178420c"
    # The version-11 identity: the same recipe, every usage report naming its whole month and
    # dated inside it (before item USAGE-REPORT-PERIOD-ENDED-1).
    assert full.sha256 != "af194365bd7bd14a852dec914c2f5dd7828cf52894272ca3615afa136a9f81f7"
    # The version-12 identity: withdrawn with register index 87 (ENG-USAGE-FIXED-SCHEDULE-1,
    # taken back on 2026-10-03) and never seeded; its number is not reused.
    assert full.sha256 != "0bc88938e0f1019cd3c50e305de7397fc4ccca913a5d7a9f8751eeae949b8724"
    # The version-13 identity: the same recipe, the stated price of a usage obligation stored
    # as awaiting trigger, its schedule lines ending at the horizon (before the return of item
    # ENG-USAGE-FIXED-SCHEDULE-1).
    assert full.sha256 != "4dd7a7bbcd5a79f26fdc869dc0e61fe05ab566197dbb570b15ea3dc50ed39a81"
    assert '"ssp_book_scope":null' in encoded  # compact JSON separators


def test_a_usage_report_of_the_dataset_ends_its_period_at_its_own_date(
    full: volume.VolumeManifest,
) -> None:
    """04 §16.3 "The usage period of a report" (rev 1.320; item USAGE-REPORT-PERIOD-ENDED-1; 05
    PERF-15 rev 1.214): the door refuses a usage report whose usage period ends after its date,
    so every usage report the generator sends — the year-end true-up too — starts its period on
    the first day of its month and ends it at its own date, and the door's rule passes it.
    Until generator version 11 a report named the whole month: 55,879 of the 55,991 were dated
    before its last day."""
    contracts = {contract.seq: contract for contract in full.contracts}
    reports = before_month_end = 0
    for event in full.events():
        if event.event_type != ContractEventType.USAGE_REPORTED.value:
            continue
        body = volume.payload(event, contracts[event.contract_seq])
        assert body is not None
        start = date.fromisoformat(body["usage_period_start"])
        end = date.fromisoformat(body["usage_period_end"])
        assert (start, end) == (volume.month_start(event.effective_month), event.effective_date)
        assert contract_events.usage_period_refusal(start, end, event.effective_date) is None
        reports += 1
        before_month_end += event.effective_date < volume.month_end(event.effective_month)
    assert (reports, before_month_end) == (55_991, 55_879)


def test_ssp_book_has_no_currency_scope_so_every_currency_resolves(
    small: volume.VolumeManifest,
) -> None:
    """Record §4.22 (folded): ``SspBookIn.currency`` is the book's SCOPE and S05-R-02 keeps only
    books whose non-null scope members equal the line facts, so the seed's one book must carry no
    currency scope — the manifest has contracts in GBP and EUR besides USD, whose USD entries
    convert at inception spot (POL-079 default). The scope value is bound by the recipe."""
    assert small.recipe.ssp_book_scope is None
    assert small.ssp_currency == "USD"
    # Record §4.24: every transaction currency of the manifest has an entry per product, so
    # S05-R-04 picks the transaction-currency entry and S05-R-05 never needs a bundle FX rate.
    assert set(small.recipe.ssp_entry_currencies) == set(volume.TENANT_CURRENCIES)
    assert {c.currency for c in small.contracts} <= set(small.recipe.ssp_entry_currencies)
    assert '"ssp_entry_currencies"' in small.to_json().decode("ascii")
    currencies = {contract.currency for contract in small.contracts}
    assert {"USD", "GBP", "EUR"} <= currencies, currencies
    assert "ssp_book_scope" in small.to_json().decode("ascii")


def test_fx_pairs_cover_every_ordered_pair_and_bind_the_recipe(
    small: volume.VolumeManifest,
) -> None:
    """Record §4.25 (G1): stage 12 reads a (transaction, functional) pair exactly as stored, so the
    seed publishes every ordered pair of the tenant currencies; the ``→ USD`` legs equal the
    ``fx_rates`` recipe member, USD → X is the inverse leg, and the recipe binds the table."""
    pairs = small.recipe.fx_pairs
    expected = {
        f"{b}/{q}" for b in volume.TENANT_CURRENCIES for q in volume.TENANT_CURRENCIES if b != q
    }
    assert set(pairs) == expected and len(expected) == 6
    for base, rates in small.recipe.fx_rates.items():
        assert pairs[f"{base}/USD"] == rates
    assert all(len(rates) == small.months for rates in pairs.values())
    assert volume.fx_pair_rate("GBP", "EUR", 1) == "1.154545"  # 1.270000 ÷ 1.100000, six decimals
    assert '"fx_pairs"' in small.to_json().decode("ascii")
    # Every currency pair a manifest contract needs (transaction → functional, and the performing
    # entity's functional currency) is published.
    functional = {e.code: e.functional_currency for e in small.entities}
    for contract in small.contracts:
        f = functional[contract.entity_code]
        if contract.currency != f:
            assert f"{contract.currency}/{f}" in pairs
        for ob in contract.obligations:
            if ob.performing_entity_code and functional[ob.performing_entity_code] != f:
                assert f"{f}/{functional[ob.performing_entity_code]}" in pairs


def test_suggestion_rationale_is_synthetic_and_long_enough() -> None:
    """Record §4.25 (G2): the dismissal rationale satisfies the schema's minimum length and states
    that the data is synthetic and not an accounting judgement."""
    from erev_api.schemas.combinations import SuggestionDismissIn

    body = SuggestionDismissIn(rationale=volume.SUGGESTION_RATIONALE)
    assert len(body.rationale) >= 10
    assert "synthetic" in body.rationale and "not an accounting judgement" in body.rationale


def test_no_event_precedes_its_contract_inception(full: volume.VolumeManifest) -> None:
    """Record §4.25 (A): S01-R-15 refuses an event dated before its contract's inception, so the
    generator clamps inception-month events to the inception date; the count is unchanged."""
    from datetime import date

    inception = {c.seq: date.fromisoformat(c.inception_date) for c in full.contracts}
    assert all(ev.effective_date >= inception[ev.contract_seq] for ev in full.events())
    assert full.counts.events == 1_262_407


def test_every_manifest_event_type_is_recorded_routed_or_deferred(
    full: volume.VolumeManifest,
) -> None:
    """Record §4.26 (the routing pin the supervisor asked for): every event type the manifest
    produces is either appended through ``record_events`` (API-R-30 ``RECORDED_TYPES``), routed to
    its own command by ``_append_month`` (ESTIMATE_CHANGED → the estimate commands,
    CONTRACT_AMENDED → the CTR-17 modification commands) or deferred (``DEFERRED_EVENT_TYPES``) —
    so a type the product refuses at the generic append can no longer reach a database run
    unnoticed. The three sets are disjoint."""
    from erev_api.domain.contracts.events import RECORDED_TYPES
    from erev_api.enums import ContractEventType as T

    recorded = {member.value for member in RECORDED_TYPES}
    routed = {
        T.ESTIMATE_CHANGED.value,
        T.CONTRACT_AMENDED.value,
    }  # _append_month's own-command routes
    deferred = set(volume.DEFERRED_EVENT_TYPES)
    assert not (recorded & routed) and not (recorded & deferred) and not (routed & deferred)
    produced = set(full.counts.events_by_type)
    assert produced, "the manifest produces events"
    unrouted = produced - recorded - routed - deferred
    assert unrouted == set(), unrouted
    assert deferred <= produced  # the deferred types are ones the manifest actually produces


def test_ctr_6_manual_event_months_wait_for_the_event_reviewer(
    small: volume.VolumeManifest,
) -> None:
    """BUILD_SPEC CTR-6 (pure part; 04 §16.3 "Manual events"): a contract-month that holds a
    manual event — a delivery, a return, a milestone, a cost or, since generator version 6, a
    usage report (04 rev 1.238) — is the accountant's request and waits for
    another user holding ``event.approve`` — the cast's event reviewer, who is never the
    accountant. In the demo cast that is priya: marcus, the reviewer of everything else, does not
    hold the permission. Evidence is sent where the product asks for it; the month's evidence
    document of an entity is CSV, one row per manual event; and the resume ledger reads an
    APPLIED submission in the shape of an append's audit detail."""
    from datetime import date

    from erev_api.auth.permissions import DEFAULT_ROLES
    from erev_api.domain.contracts.events import MANUAL_TYPES
    from erev_api.domain.demo.personas import PERSONAS
    from erev_api.enums import ContractEventType as T
    from erev_api.schemas.events import EventAppendItemIn

    def held(key: str, cast: tuple[Any, ...]) -> frozenset[str]:
        persona = next(p for p in cast if p.key == key)
        return frozenset().union(*(DEFAULT_ROLES[c] for c in persona.roles_in("journey")))

    for cast, personas in ((volume.PERF_CAST, perf_seed.CAST), (volume.DEMO_CAST, PERSONAS)):
        assert cast.event_reviewer != cast.accountant
        assert "event.approve" in held(cast.event_reviewer, personas)
        assert "event.record" in held(cast.accountant, personas)
        assert "event.approve" not in held(cast.accountant, personas)
    assert volume.DEMO_CAST.event_reviewer == "priya"
    assert "event.approve" not in held(volume.DEMO_CAST.reviewer, PERSONAS)
    assert "event.approve" in perf_seed.REQUIRED_PERMISSIONS[volume.PERF_CAST.event_reviewer]

    def item(event_type: T, **payload: Any) -> EventAppendItemIn:
        return EventAppendItemIn(
            event_type=event_type, effective_date=date(2025, 3, 9), payload=payload
        )

    delivery = item(T.DELIVERY_RECORDED, obligation_key="POB-01", quantity="3", trigger="DELIVERY")
    accepted = item(
        T.DELIVERY_RECORDED, obligation_key="POB-01", quantity="3", trigger="ACCEPTANCE"
    )
    returned = item(T.RETURN_RECORDED, obligation_key="POB-01", quantity="1", reason="RMA")
    milestone = item(T.MILESTONE_ACHIEVED, obligation_key="POB-02", milestone_code="M1")
    cost = item(T.COST_INCURRED, purpose="COST_TO_OBTAIN")
    billing = item(T.BILLING_RECORDED, invoice_number="INV-1")
    assert not volume.needs_evidence([billing, delivery, returned])
    for needing in (accepted, milestone, cost):
        assert volume.needs_evidence([billing, needing])
    # every manual type the manifest produces is one the seed has approved
    produced = {e.event_type for e in small.events()}
    manual = {member.value for member in MANUAL_TYPES}
    assert produced & manual, "the small manifest holds manual events"

    by_seq = {c.seq: c for c in small.contracts}
    month = min(e.recorded_month for e in small.events() if e.event_type in manual)
    entity = next(
        by_seq[e.contract_seq].entity_code
        for e in small.events_for_month(month)
        if e.event_type in manual
    )
    rows = [
        (by_seq[e.contract_seq].external_id, e)
        for e in small.events_for_month(month)
        if e.event_type in manual and by_seq[e.contract_seq].entity_code == entity
    ]
    document = volume.evidence_document(rows)
    assert document == volume.evidence_document(rows)  # deterministic
    lines = document.decode("utf-8").split("\n")
    assert lines[0] == volume.EVIDENCE_HEADER == "contract,event_type,effective_date,obligation_key"
    assert lines[-1] == "" and len(lines) == len(rows) + 2
    first_id, first = rows[0]
    assert lines[1] == ",".join(
        (first_id, first.event_type, first.effective_date.isoformat(), first.obligation_key or "")
    )
    assert volume.evidence_filename("VOL-US", 3) == "volume-vol-us-month-03-evidence.csv"

    # the resume ledger: an APPLIED submission is read as (contract, {comment, event_ids})
    cluster = small.industry_cluster
    contract_id, e1, e2 = uuid4(), str(uuid4()), str(uuid4())
    applied = [(contract_id, {"comment": f"Volume month 3 ({cluster})", "event_ids": [e1, e2]})]
    assert perf_seed.months_from_audit(applied, {e1, e2}, cluster) == {str(contract_id): {3}}
    assert perf_seed.months_from_audit(applied, {e1}, cluster) == {}


def test_ctr_12_an_estimate_version_is_submitted_with_its_evidence_and_its_record(
    small: volume.VolumeManifest,
) -> None:
    """BUILD_SPEC CTR-12 (pure part; 04 §16.14 "Estimates" rev 1.241; items
    EST-EVIDENCE-AT-SUBMIT-1 and the constraint's judgement record): the seed gives every
    estimate version what its submission asks — one evidence document of its own and, for the
    variable-consideration bonus, a ``CONSTRAINT`` record the cast's reviewer reviews. The
    accountant prepares both and reviews neither; the reviewer is never the accountant. The
    document is CSV, one row: the contract, the element, the effective date and the manifest
    event; it and the record's words say that they are generated, not a judgement."""
    from erev_api.auth.permissions import DEFAULT_ROLES
    from erev_api.domain.demo.personas import PERSONAS
    from erev_api.enums import ContractEventType as T

    def held(key: str, cast: tuple[Any, ...]) -> frozenset[str]:
        persona = next(p for p in cast if p.key == key)
        return frozenset().union(*(DEFAULT_ROLES[c] for c in persona.roles_in("journey")))

    for cast, personas in ((volume.PERF_CAST, perf_seed.CAST), (volume.DEMO_CAST, PERSONAS)):
        assert cast.reviewer != cast.accountant
        prepares, reviews = held(cast.accountant, personas), held(cast.reviewer, personas)
        assert {"estimate.create", "judgement.create"} <= prepares
        assert not {"estimate.approve", "judgement.review"} & prepares
        assert {"estimate.approve", "judgement.review"} <= reviews
    assert {"estimate.create", "judgement.create"} <= perf_seed.REQUIRED_PERMISSIONS[
        volume.PERF_CAST.accountant
    ]
    assert "judgement.review" in perf_seed.REQUIRED_PERMISSIONS[volume.PERF_CAST.reviewer]

    by_seq = {c.seq: c for c in small.contracts}
    changes = [e for e in small.events() if e.event_type == T.ESTIMATE_CHANGED.value]
    assert changes, "the small manifest holds estimate changes"
    event = changes[0]
    external_id = by_seq[event.contract_seq].external_id
    document = volume.estimate_evidence_document(external_id, "VC-BONUS", event)
    assert document == volume.estimate_evidence_document(external_id, "VC-BONUS", event)
    lines = document.decode("utf-8").split("\n")
    assert lines == [
        volume.ESTIMATE_EVIDENCE_HEADER,
        f"{external_id},VC-BONUS,{event.effective_date.isoformat()},{event.seq}",
        "",
    ]
    assert volume.ESTIMATE_EVIDENCE_HEADER == "contract,element,effective_date,manifest_event"
    # one file per version: the name carries the manifest event, as the version's rationale does
    names = {volume.estimate_evidence_filename(external_id, e) for e in changes}
    assert len(names) == len({e.seq for e in changes}) == len(changes)
    assert volume.estimate_evidence_filename(external_id, event) == (
        f"volume-{external_id.lower()}-estimate-event-{event.seq}-evidence.csv"
    )
    assert volume.ESTIMATE_VERSION_SUBJECT == "estimate_version"
    assert "not an accounting judgement" in volume.CONSTRAINT_RATIONALE
    assert "Generated" in volume.ESTIMATE_EVIDENCE_NOTE


# --- PERF-SEED-LOCK-1: the order of a contract-month and its resume ledger -----------------------


def _as_listed(manifest: volume.VolumeManifest, through_month: int | None = None) -> int:
    """The late arrivals of the order before: a contract-month's commands of their own first, then
    its other events as the manifest lists them, in one append."""
    contracts = {contract.seq: contract for contract in manifest.contracts}
    months: dict[tuple[int, int], list[volume.VolumeEvent]] = {}
    for event in manifest.events():
        if through_month is None or event.recorded_month <= through_month:
            months.setdefault((event.recorded_month, event.contract_seq), []).append(event)
    late = 0
    latest: dict[int, Any] = {}
    for month, seq in sorted(months):
        sent = volume.sent_events(contracts[seq], months[month, seq])
        own = [e for e in sent if e.event_type in volume.OWN_COMMAND]
        for event in [*own, *(e for e in sent if e.event_type not in volume.OWN_COMMAND)]:
            top = latest.get(seq)
            if top is not None and event.effective_date < top:
                late += 1
            else:
                latest[seq] = event.effective_date
    return late


def test_a_contract_month_is_sent_by_date_so_only_the_deliberately_late_events_arrive_late(
    small: volume.VolumeManifest,
) -> None:
    """05 PERF-14 plans 0.5 % late events. The engine answers an event that arrives after a
    later-dated event of its contract with a LATE_EVENT item, and an open item holds every lock
    of its entity. Sent as the seed sent them — the commands first, then the month as the manifest
    lists it — 1,122 of the 1,877 events of the 1/1000 manifest arrived late (measured on the
    seeded tenant for month 1: two items, as this count gives); sent by date, the six that do are
    events the generator recorded a month late."""
    assert sum(1 for _ in small.events()) == 1_877
    assert _as_listed(small) == 1_122
    assert _as_listed(small, 1) == 2
    late = volume.late_arrivals(small)
    assert len(late) == 6 and all(event.late for event in late)
    # A seventh event is recorded a month late and arrives before anything later of its contract.
    assert sum(1 for event in small.events() if event.late) == 7
    assert volume.late_arrivals(small, 1) == []
    assert len(volume.late_arrivals(small, 23)) == 6
    # The test-scale story of tests/domain/demo/test_perf_seed.py: seven months, six locked.
    seven = volume.manifest(Fraction(1, 1000), months=7)
    (one,) = volume.late_arrivals(seven, 6)
    assert (one.event_type, one.effective_date.isoformat(), one.recorded_month, one.late) == (
        "PAYMENT_RECEIVED",
        "2025-02-04",
        3,
        True,
    )


def test_the_waivers_of_the_dataset_are_counted_on_the_full_manifest(
    full: volume.VolumeManifest,
) -> None:
    """05 PERF-15 (rev 1.182), what waits beyond the test scale: a seed asks one waiver and one
    decision for each late event that arrives after a later-dated event of its contract. On the
    manifest of the dataset that is 4,124 of the 5,721 events PERF-14 records a month late, and
    3,820 of them are recorded in the months a seed locks — 1 to 23, which hold 1,161,456 of the
    1,262,407 events. The count is the manifest's; no seed of that size has run."""
    arriving = volume.late_arrivals(full)
    assert all(event.late for event in arriving)
    assert (full.counts.events, full.counts.late_events, len(arriving)) == (1_262_407, 5_721, 4_124)
    # An event is late against what was recorded before it, so the months a seed locks hold
    # their own share of the whole count.
    assert sum(1 for event in arriving if event.recorded_month <= perf_seed.SEED_MONTHS) == 3_820
    assert sum(full.counts.events_by_month[: perf_seed.SEED_MONTHS]) == 1_161_456


def test_the_requests_of_the_dataset_are_counted_as_the_seed_sends_them(
    full: volume.VolumeManifest,
) -> None:
    """05 PERF-15 (rev 1.182): what the order of a contract-month makes of the requests of the
    dataset's seed. A contract-month that a command of its own divides — an estimate change or an
    amendment at its place among the dates — is several appends (``month_steps``). Each waits for
    the event reviewer where it holds a manual event, and is sent with the entity's evidence
    document only where its own events ask for it (``needs_evidence``); the approval attaches
    that document to every event of the request. Counted whole, a contract-month as one request,
    the same walk gives the figures PERF-15 stated at rev 1.187 and rev 1.192; month 24 is the
    harness's, which sends a contract-month whole. The count is the manifest's; no seed of that
    size has run."""
    from types import SimpleNamespace

    from erev_api.domain.contracts import events as contract_events
    from erev_api.enums import ContractEventType

    manual = {member.value for member in contract_events.MANUAL_TYPES}
    by_seq = {contract.seq: contract for contract in full.contracts}
    months = len(full.periods)
    assert months == perf_seed.SEED_MONTHS + 1

    def counted(requests: list[list[Any]]) -> tuple[int, int, int, int, int]:
        """(requests, those that wait, those with the document, their events, all events)."""
        waiting = [request for request in requests if any(kind in manual for kind, _ in request)]
        documented = [
            request for request in requests if volume.needs_evidence(item for _, item in request)
        ]
        return (
            len(requests),
            len(waiting),
            len(documented),
            sum(len(request) for request in documented),
            sum(len(request) for request in requests),
        )

    # A contract-month is the events of one contract the seed records in one month. The stream is
    # walked once: ``events_for_month`` walks it whole for every month it is asked.
    grouped: dict[tuple[int, int], list[volume.VolumeEvent]] = {}
    for event in full.events():
        grouped.setdefault((event.recorded_month, event.contract_seq), []).append(event)
    last: dict[int, list[int]] = {}
    for event in full.events_for_month(months):  # as ``_append_month`` groups a month
        last.setdefault(event.contract_seq, []).append(event.seq)
    assert last == {
        seq: [event.seq for event in events]
        for (month, seq), events in grouped.items()
        if month == months
    }

    whole: dict[bool, list[list[Any]]] = {True: [], False: []}  # by "a month the seed sends"
    divided: list[list[Any]] = []
    months_divided = manual_months = 0
    for (month, seq), events in grouped.items():
        seeded = month <= perf_seed.SEED_MONTHS
        spec = by_seq[seq]
        manual_months += any(event.event_type in manual for event in events)
        sent = volume.sent_events(spec, events)
        items = {
            event.seq: (
                event.event_type,
                SimpleNamespace(
                    event_type=ContractEventType(event.event_type),
                    payload=volume.payload(event, spec) or {},
                ),
            )
            for event in sent
            if event.event_type not in volume.OWN_COMMAND
        }
        if items:
            whole[seeded].append(list(items.values()))
        if not seeded:
            continue
        parts = [step for step in volume.month_steps(sent) if step.part]
        months_divided += len(parts) > 1
        divided.extend([items[event.seq] for event in step.events] for step in parts)
    contract_months = len(grouped)

    # What asks for the document in this dataset is a cost or a milestone: it holds no delivery
    # on acceptance and no progress event, so those clauses of the product's rule count nothing.
    asking = {
        kind
        for request in (*whole[True], *whole[False])
        for kind, item in request
        if volume.needs_evidence([item])
    }
    assert asking == {"COST_INCURRED", "MILESTONE_ACHIEVED"}
    # The control: counted whole, the walk gives PERF-15's figures of rev 1.187 and rev 1.192.
    assert (contract_months, manual_months) == (122_493, 95_013)
    assert counted(whole[True]) == (112_678, 87_411, 26_101, 343_807, 1_152_045)
    # Month 24 is the harness's, sent whole.
    assert counted(whole[False]) == (9_771, 7_602, 2_645, 34_289, 100_045)
    # As the seed sends months 1 to 23 since the order of a contract-month.
    assert months_divided == 5_794
    assert counted(divided) == (118_740, 90_259, 26_689, 318_985, 1_152_045)


def test_an_event_is_late_when_it_is_dated_before_the_latest_date_recorded_before_it() -> None:
    """``late_among`` is the engine's out-of-order clause (ENGINE_SPEC S08-R-10): of a contract's
    events in the order they are recorded, one is late when it is dated before the latest date
    recorded before it. The latest date only rises — an event that follows a late one is measured
    against the same date —, an event of that very date is not late, and the first never is. The
    engine's own function gives the same answer for the same order."""
    from datetime import date

    from erev_engine.stages.s08_estimates_late_events import late as engine_late

    days = (10, 5, 7, 10, 12, 11, 12)
    dates = [date(2025, 3, day) for day in days]
    assert volume.late_among(dates) == [False, True, True, False, False, True, False]
    assert volume.late_among([]) == [] and volume.late_among(dates[:1]) == [False]
    assert volume.late_among(sorted(dates, reverse=True)) == [
        False,
        False,
        True,
        True,
        True,
        True,
        True,
    ]
    events = [
        SimpleNamespace(
            record_seq=number, event_key=f"E-{number}", contract_key="VOL-C", effective_date=on
        )
        for number, on in enumerate(dates, start=1)
    ]
    earlier = engine_late._recorded_earlier_latest(  # noqa: SLF001
        SimpleNamespace(events=events)  # type: ignore[arg-type]
    )
    assert [
        event.event_key in earlier and event.effective_date < earlier[event.event_key]
        for event in events
    ] == volume.late_among(dates)


def test_a_command_of_its_own_stands_at_its_place_among_the_dates(
    small: volume.VolumeManifest,
) -> None:
    """``month_steps``: an ESTIMATE_CHANGED or a CONTRACT_AMENDED is sent through its own command
    between the events dated before it and those dated on or after it; the events on either side
    are appends of their own, the last under the month's plain comment; a month without such a
    command is one append, as before."""
    contracts = {contract.seq: contract for contract in small.contracts}
    months: dict[tuple[int, int], list[volume.VolumeEvent]] = {}
    for event in small.events():
        months.setdefault((event.contract_seq, event.recorded_month), []).append(event)
    plans = {
        key: volume.month_steps(volume.sent_events(contracts[key[0]], events))
        for key, events in months.items()
    }
    cluster = small.industry_cluster
    divided = 0
    for (seq, month), steps in plans.items():
        sent = volume.sent_events(contracts[seq], months[seq, month])
        flat = [event for step in steps for event in step.events]
        assert sorted(e.seq for e in flat) == sorted(e.seq for e in sent)  # every event once
        assert [e.effective_date for e in flat] == sorted(e.effective_date for e in flat)
        appends = [step for step in steps if step.part]
        assert [step.part for step in appends] == list(range(1, len(appends) + 1))
        assert {step.parts for step in steps} <= {len(appends)}
        for step in steps:
            if step.part == 0:
                (event,) = step.events
                assert event.event_type in volume.OWN_COMMAND
            else:
                assert not {e.event_type for e in step.events} & volume.OWN_COMMAND
        if not any(step.part == 0 for step in steps):
            assert len(steps) <= 1  # an undivided month is one append
        divided += len(appends) > 1
        comments = [volume.append_comment(month, cluster, s.part, s.parts) for s in appends]
        assert len(set(comments)) == len(comments)
        if comments:
            assert comments[-1] == f"Volume month {month} ({cluster})"
            assert perf_seed._appended_month(comments[-1], cluster) == month  # noqa: SLF001
        for comment in comments[:-1]:
            assert perf_seed._appended_month(comment, cluster) is None  # noqa: SLF001
    assert sum(1 for steps in plans.values() if any(s.part == 0 for s in steps)) == 15
    assert divided == 11
    # VOL-C-000004, month 9: two events before the estimate change of 12 September, six on or
    # after it — the command stands before the other events of its day.
    nine = plans[4, 9]
    assert [(s.part, s.parts, len(s.events)) for s in nine] == [(1, 2, 2), (0, 2, 1), (2, 2, 6)]
    assert {e.effective_date.isoformat() for e in nine[0].events} == {"2025-09-05"}
    assert min(e.effective_date for e in nine[2].events).isoformat() == "2025-09-12"
    assert nine[1].events[0].effective_date.isoformat() == "2025-09-12"
    assert volume.append_comment(9, cluster, 1, 2) == f"Volume month 9 part 1 of 2 ({cluster})"


def test_the_part_ledger_binds_to_durable_appends() -> None:
    """``parts_from_audit``: an earlier append of a divided month is done only when its comment
    names this manifest and every event id of the append still persists — the month's own rule
    (``months_from_audit``), which reads the last append and none of the parts."""
    cluster = "perf:0123456789abcdef"
    c1, c2 = uuid4(), uuid4()
    e1, e2, e3, e4 = (str(uuid4()) for _ in range(4))
    rows = [
        (c1, {"comment": f"Volume month 9 part 1 of 2 ({cluster})", "event_ids": [e1, e2]}),
        (c1, {"comment": f"Volume month 9 ({cluster})", "event_ids": [e3]}),
        (c1, {"comment": f"Volume month 12 part 1 of 3 ({cluster})", "event_ids": [e4]}),  # gone
        (c2, {"comment": f"Volume month 9 part 1 of 2 ({cluster})", "event_ids": []}),
        (c2, {"comment": "Volume month 9 part 1 of 2 (perf:fedcba9876543210)", "event_ids": [e1]}),
        (c2, {"comment": "Volume month 9 part one of two", "event_ids": [e1]}),
        (c2, None),
    ]
    persisted = {e1, e2, e3}
    assert perf_seed.parts_from_audit(rows, persisted, cluster) == {str(c1): {(9, 1)}}
    assert perf_seed.months_from_audit(rows, persisted, cluster) == {str(c1): {9}}
    assert perf_seed.parts_from_audit(rows, {*persisted, e4}, cluster) == {
        str(c1): {(9, 1), (12, 1)}
    }
    assert perf_seed.parts_from_audit([], persisted, cluster) == {}


def test_a_resumed_month_sends_no_append_the_ledger_holds(
    small: volume.VolumeManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_append_month`` on a resume: an undivided contract-month in the ledger is skipped whole;
    a divided one is walked step by step — its last durable step may be a command that follows
    its last append — and an append the ledger holds is counted REUSED and not sent, while a
    command finds its own version or modification."""
    contracts = {contract.seq: contract for contract in small.contracts}
    ids = {seq: uuid4() for seq in contracts}
    names = {ids[seq]: contract.external_id for seq, contract in contracts.items()}
    cluster = small.industry_cluster
    calls: list[tuple[str, str, object]] = []
    outcome = {"estimate": volume.APPLIED}

    def record_batch(ctx: Any, cast: Any, contract_id: Any, items: Any, **named: Any) -> int:
        calls.append((names[contract_id], str(named["comment"]), len(items)))
        return len(items)

    def apply_estimate(ctx: Any, cast: Any, contract_id: Any, spec: Any, event: Any) -> str:
        calls.append((names[contract_id], "estimate", event.seq))
        # The other contracts' months are done: their versions are found again.
        return outcome["estimate"] if names[contract_id] == name else volume.REUSED

    monkeypatch.setattr(volume, "_record_batch", record_batch)
    monkeypatch.setattr(volume, "_apply_estimate", apply_estimate)
    month = 9  # VOL-C-000004: two events, the estimate change, six events
    events = list(small.events_for_month(month))
    name = contracts[4].external_id
    others = {contracts[e.contract_seq].external_id for e in events} - {name}
    estimate = next(e for e in events if e.contract_seq == 4 and e.event_type == "ESTIMATE_CHANGED")

    def run(done: dict[str, frozenset[int]], parts: dict[str, frozenset[tuple[int, int]]]) -> Any:
        calls.clear()
        return volume._append_month(  # noqa: SLF001
            None,  # type: ignore[arg-type]
            small,
            volume.PERF_CAST,
            ids,
            month,
            250,
            done=done,
            parts_done=parts,
        )

    def of_four() -> list[tuple[str, str, object]]:
        return [call for call in calls if call[0] == name]

    # Every other contract-month of the month is in the ledger, with its parts.
    everyone_else = {external_id: frozenset({month}) for external_id in others}
    their_parts = {external_id: frozenset({(month, 1)}) for external_id in others}
    first, last = f"Volume month 9 part 1 of 2 ({cluster})", f"Volume month 9 ({cluster})"
    fresh = run(dict(everyone_else), dict(their_parts))
    assert of_four() == [(name, first, 2), (name, "estimate", estimate.seq), (name, last, 6)]
    # Of the others, an undivided month is skipped whole and a divided one is walked: no append
    # is sent again, and each command is asked.
    assert {call[1] for call in calls if call[0] != name} == {"estimate"}
    assert (fresh.appended, fresh.reused) == (9, len(events) - 9)

    outcome["estimate"] = volume.REUSED
    # Interrupted after the first append: it is in the ledger, the rest is sent.
    after_first = run(dict(everyone_else), {**their_parts, name: frozenset({(month, 1)})})
    assert of_four() == [(name, "estimate", estimate.seq), (name, last, 6)]
    assert (after_first.appended, after_first.reused) == (6, len(events) - 6)
    # The whole month is in the ledger: nothing is appended, and the command is still asked — it
    # may be the step an interruption left undone.
    whole = run(
        {**everyone_else, name: frozenset({month})},
        {**their_parts, name: frozenset({(month, 1)})},
    )
    assert of_four() == [(name, "estimate", estimate.seq)]
    assert {call[1] for call in calls} == {"estimate"}
    assert (whole.appended, whole.reused) == (0, len(events))


# --- PERF-SEED-LOCK-1: the months, the close as its people do it, the waiver ----------------------


def test_a_manifest_of_fewer_months_is_locked_through_its_months_less_one(
    small: volume.VolumeManifest,
) -> None:
    """Only a test seeds fewer than 24 months (tests/domain/demo/test_perf_seed.py: seven). The
    seed locks every month but the manifest's last, and its decision and messages name that
    month; the dataset of 24 keeps its 23."""
    seven = volume.manifest(Fraction(1, 1000), months=7)
    assert perf_seed.seed_months(small) == perf_seed.SEED_MONTHS == 23
    assert perf_seed.seed_months(seven) == 6
    assert seven.industry_cluster != small.industry_cluster  # another horizon, another dataset
    assert seven.periods == small.periods[:7]
    facts = perf_seed.TenantFacts(uuid4(), seven.industry_cluster, True, "PRODUCTION")
    six = frozenset(range(1, 7))
    assert perf_seed.decide(facts, _ledger(seven, months_locked=six), seven).outcome == "up_to_date"
    pending = perf_seed.decide(facts, _ledger(seven, months_locked=six, seed_snapshot=None), seven)
    assert pending == perf_seed.Decision(
        "locked",
        "perf-volume seeded and locked through month 6; snapshot pending "
        "(make perf-seed runs ANALYZE, then erev perf seed --snapshot-only)",
        0,
    )
    five = _ledger(seven, months_locked=frozenset(range(1, 6)))
    assert perf_seed.decide(facts, five, seven).outcome == "resumed"
    assert perf_seed.decide(facts, five, seven, snapshot_only=True) == perf_seed.Decision(
        "refused",
        "perf-volume is not locked through month 6; run erev perf seed before --snapshot-only",
        1,
    )
    assert perf_seed.decide(None, None, seven, snapshot_only=True).message.startswith(
        "perf-volume is not locked through month 6;"
    )

    # One contract of the story's manifest is booked at a million or more, so its activation takes
    # the Controller's second step in the story (PRD §2.5); none of the 24 months' manifest at
    # this scale is, which is why no run met that step before.
    def booked(contract: volume.VolumeContract) -> Decimal:
        return sum((Decimal(str(o.total_price)) for o in contract.obligations), Decimal(0))

    million = Decimal("1000000.00")
    assert [c.external_id for c in seven.contracts if booked(c) >= million] == ["VOL-C-000003"]
    assert [c.external_id for c in small.contracts if booked(c) >= million] == []
    # A run appends and locks through the month its caller names, by default every month but
    # the manifest's last, and never beyond the manifest (``erev perf seed --through-month``).
    assert perf_seed.last_month(small, None) == 23 and perf_seed.last_month(seven, None) == 6
    assert perf_seed.last_month(seven, 5) == 5 and perf_seed.last_month(small, 24) == 24
    assert perf_seed.last_month(seven, 23) == 7
    # The dataset's own messages are unchanged.
    assert perf_seed.LOCKED_PENDING_SNAPSHOT == perf_seed.locked_pending_snapshot(23)
    assert perf_seed.SNAPSHOT_PRECONDITION == (
        "perf-volume is not locked through month 23; run erev perf seed before --snapshot-only"
    )


def test_the_months_are_closed_in_order_for_every_entity_and_book_by_the_three_personas(
    small: volume.VolumeManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_close_and_lock`` hands every unlocked month, in order, entity by entity and book by
    book, to the helper of the demo world's close (``closing.close_period``): perf-accountant
    prepares, perf-reviewer reviews, perf-controller decides the lock. The certification says
    what this tenant's lock rests on — no reconciliation is asked — and the late events are
    waived before each lock is asked."""
    calls: list[dict[str, Any]] = []

    def close_period(ctx: Any, cast: Any, **named: Any) -> None:
        calls.append({"ctx": ctx, "cast": cast, **named})

    monkeypatch.setattr(closing, "close_period", close_period)
    context = object()
    ledger = _ledger(small, months_locked=frozenset({1, 2}))
    assert perf_seed._close_and_lock(context, small, 4, ledger) == 4  # type: ignore[arg-type]  # noqa: SLF001
    books = [(entity.code, book) for entity in small.entities for book in entity.books]
    assert books == [
        ("VOL-US", "ASC606"),
        ("VOL-UK", "ASC606"),
        ("VOL-UK", "IFRS15"),
        ("VOL-DE", "ASC606"),
    ]
    assert [(c["entity_code"], c["book"].value, c["period_key"]) for c in calls] == [
        (code, book, key) for key in ("FY2025-P03", "FY2025-P04") for code, book in books
    ]
    for call in calls:
        cast = call["cast"]
        assert (cast.preparer, cast.reviewer, cast.controller) == (
            "perf-accountant",
            "perf-reviewer",
            "perf-controller",
        )
        assert call["ctx"] is context and call["certification"] == perf_seed.CERTIFICATION
        hook = call["before_lock"]
        assert hook.func is perf_seed._waive_late_events and hook.args == (context,)  # noqa: SLF001
        name = f"{call['entity_code']} {call['book'].value} {call['period_key']}"
        assert hook.keywords == {"name": name}
    assert "reconcil" not in perf_seed.CERTIFICATION.lower()
    # Nothing to lock: no close is asked, and the months count as locked.
    calls.clear()
    done = _ledger(small, months_locked=frozenset(range(1, 24)))
    assert perf_seed._close_and_lock(context, small, 23, done) == 23  # type: ignore[arg-type]  # noqa: SLF001
    assert calls == []
    # A first run holds no ledger: every month of the horizon asked is closed.
    assert perf_seed._close_and_lock(context, small, 2, None) == 2  # type: ignore[arg-type]  # noqa: SLF001
    assert [c["period_key"] for c in calls] == ["FY2025-P01"] * 4 + ["FY2025-P02"] * 4


def test_the_bulk_recompute_is_due_only_while_every_month_is_open() -> None:
    """05 PERF-15 (rev 1.182): the bulk recompute is made with every period of the manifest's
    months open. One period in another state — a soft close, a lock, a reopening — shows that a
    close began, which a seed starts only after the recompute: it is not due a second time."""
    open_ = PeriodState.OPEN.value
    assert volume.recompute_due([open_] * 28)
    assert volume.recompute_due([PeriodState.OPEN] * 28)  # a member reads as its value
    for state in PeriodState:
        if state is not PeriodState.OPEN:
            assert not volume.recompute_due([open_] * 27 + [state.value]), state
            assert not volume.recompute_due([state.value] + [open_] * 27), state


def test_a_seed_that_finds_a_month_closed_does_not_recompute_every_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``volume.seed`` reads the period states of the manifest's months after its last append and
    recomputes every group only when all are open (``recompute_due``): a first run does, and a
    run that finds a month in soft close or locked — resumed after its lock phase began, or
    extending an earlier ``through_month`` — does not. The story's second database run met the
    other order: its completion recomputed every group behind five locked months, and the close
    run of the sixth stopped at its dataset freeze over lines without a source event
    (ENGINE_SPEC_B S15-R-18b). Those lines are the engine's defect, item ENG-COST-READBACK-1,
    which has its own witness in the engine's lane; this order is PERF-15's own condition and
    does not answer it."""
    order: list[str] = []
    found: list[str] = []

    def step(name: str, answer: Any = None) -> Any:
        def call(*_: Any, **__: Any) -> Any:
            order.append(name)
            return answer

        return call

    monkeypatch.setattr(builders, "refuse_non_demo", lambda ctx: None)
    for name in (
        "_reference",
        "_chart_and_mapping",
        "_create_products",
        "_bind_default_templates",
        "_assess_products",
        "_ssp",
    ):
        monkeypatch.setattr(volume, name, step(name))
    for name in ("_customers", "_templates", "_contracts"):
        monkeypatch.setattr(volume, name, step(name, {}))
    monkeypatch.setattr(volume, "_append_month", step("_append_month", volume.MonthTally(0, 0, {})))
    monkeypatch.setattr(volume, "_recompute_all", step("_recompute_all", 10))

    def month_states(ctx: Any, m: volume.VolumeManifest) -> list[str]:
        order.append("_month_states")
        assert m.months == 7  # the manifest's months, the held-back last one among them
        return list(found)

    monkeypatch.setattr(volume, "_month_states", month_states)
    context: Any = object()

    def seed() -> volume.SeedReport:
        order.clear()
        return volume.seed(
            context, months=7, scale=Fraction(1, 1000), through_month=6, runtime=context
        )

    open_ = PeriodState.OPEN.value
    found[:] = [open_] * 28
    first = seed()
    assert (first.months_appended, first.groups_recomputed) == (6, 10)
    assert order[-8:] == ["_append_month"] * 6 + ["_month_states", "_recompute_all"]
    for state in (PeriodState.CLOSING, PeriodState.CLOSED):
        found[:] = [state.value] + [open_] * 27
        again = seed()
        assert (again.months_appended, again.groups_recomputed) == (6, 0), state
        assert order[-7:] == ["_append_month"] * 6 + ["_month_states"], state
        assert "_recompute_all" not in order, state


def test_the_helper_calls_the_seed_s_hook_between_the_close_and_the_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``closing.close_period``: ``before_lock`` is called with the period state's id after the
    close run and the journal run and before the reconciliations — nothing stands between the
    review of a reconciliation and the lock, because what is recorded for the period after a
    review makes the gate ask for the reconciliation again — and the lock request carries the
    caller's certification; a period already locked asks neither."""
    from erev_api.enums import BookCode, PeriodState

    state_id = uuid4()
    order: list[Any] = []

    def period(state: str) -> Any:
        return SimpleNamespace(
            state=state, state_id=state_id, name="VOL-US ASC606 FY2025-P01", row_version=1
        )

    states = iter([PeriodState.OPEN.value, PeriodState.CLOSED.value])
    monkeypatch.setattr(closing, "_period", lambda *_: period(next(states)))
    for step in ("_start_close", "_close_run", "_journal", "_reconcile", "_sign_tasks"):
        monkeypatch.setattr(closing, step, lambda *_, step=step: order.append(step))
    monkeypatch.setattr(
        closing, "_lock", lambda _ctx, _cast, _at, certification: order.append(certification)
    )
    cast = closing.ClosingCast(preparer="a", reviewer="r", controller="c")
    closing.close_period(
        None,  # type: ignore[arg-type]
        cast,
        entity_code="VOL-US",
        book=BookCode.ASC606,
        period_key="FY2025-P01",
        certification="No reconciliation is asked.",
        before_lock=lambda found: order.append(("before_lock", found)),
    )
    assert order == [
        "_start_close",
        "_close_run",
        "_journal",
        ("before_lock", state_id),
        "_reconcile",
        "_sign_tasks",
        "No reconciliation is asked.",
    ]
    # Without a hook the helper is the demo world's: its own certification, nothing between.
    order.clear()
    states = iter([PeriodState.OPEN.value, PeriodState.CLOSED.value])
    closing.close_period(
        None,  # type: ignore[arg-type]
        cast,
        entity_code="VOL-US",
        book=BookCode.ASC606,
        period_key="FY2025-P01",
    )
    assert order[-2:] == ["_sign_tasks", closing.CERTIFICATION]
    # A locked period is left alone: no step, no hook.
    order.clear()
    states = iter([PeriodState.CLOSED.value])
    closing.close_period(
        None,  # type: ignore[arg-type]
        cast,
        entity_code="VOL-US",
        book=BookCode.ASC606,
        period_key="FY2025-P01",
        before_lock=lambda found: order.append(("before_lock", found)),
    )
    assert order == []


def _item(number: int, code: str, source: str, severity: str = "WARNING") -> Any:
    return SimpleNamespace(
        id=uuid4(),
        exception_no=f"EXC-{number:06d}",
        code=code,
        source=source,
        severity=severity,
        message=f"finding {number}",
    )


def test_only_a_late_event_of_the_engine_is_waived_and_anything_else_stops_the_seed_by_name() -> (
    None
):
    """PRD BR-DAT-04: the input of a late event is committed, so its clearance by a person is a
    waiver, and the seed asks one for the engine's ``LATE_EVENT`` items alone — the events the
    generator records a month late (05 PERF-14). Any other open item that holds a lock is not
    the seed's to clear: it is named, with its number, code, source, severity and message."""
    late = _item(1, "LATE_EVENT", "ENGINE")
    assert perf_seed.foreign_items([late, _item(2, "LATE_EVENT", "ENGINE")]) == []
    unmapped = _item(3, "PRODUCT_UNMAPPED", "IMPORT", "BLOCKING")
    # The code alone does not make it the generator's: an import's finding of the same code, and
    # another finding of the engine, are both left to a person.
    imported = _item(4, "LATE_EVENT", "IMPORT")
    quarantined = _item(5, "ENGINE_INVARIANT_VIOLATION", "ENGINE", "BLOCKING")
    assert perf_seed.foreign_items([late, unmapped, imported, quarantined]) == [
        unmapped,
        imported,
        quarantined,
    ]
    name = "VOL-US ASC606 FY2025-P01"
    assert perf_seed.stopped_message(name, [unmapped, imported]) == (
        "VOL-US ASC606 FY2025-P01 cannot be locked: 2 open exception item(s) hold it that are "
        "not late events of the generator — EXC-000003 PRODUCT_UNMAPPED (IMPORT, BLOCKING): "
        "finding 3; EXC-000004 LATE_EVENT (IMPORT, WARNING): finding 4. The seed waives nothing "
        "else: clear them and run it again."
    )
    many = [_item(number, "SSP_MISSING", "ENGINE", "BLOCKING") for number in range(10, 17)]
    message = perf_seed.stopped_message(name, many)
    assert "7 open exception item(s)" in message and message.count("SSP_MISSING") == 5
    assert "EXC-000014 SSP_MISSING" in message and "EXC-000015" not in message
    assert "; and 2 more. The seed waives nothing else" in message
    assert perf_seed.ITEMS_NAMED == 5 and perf_seed.LATE_EVENT == "LATE_EVENT"
    # The comment of a waiver names the generator and the plan it follows.
    assert "volume generator" in perf_seed.WAIVER_COMMENT and "PERF-14" in perf_seed.WAIVER_COMMENT
    assert issubclass(perf_seed.SeedStopped, RuntimeError)


def test_the_command_registers_the_csv_ledger_adapter_and_names_a_stopped_seed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``erev perf seed`` runs the jobs of a close in its own process, so it registers the CSV
    general-ledger adapter as the worker does (DG-LAY-03) — for the seed phase, not for
    ``--snapshot-only`` —, and a stopped seed is one line on stderr with exit 1, no report."""
    from erev_api import cli, config, worker
    from erev_api.controls import release
    from erev_api.domain.journals import ports as gl_ports
    from erev_api.enums import GlAdapter
    from pydantic import SecretStr
    from typer.testing import CliRunner

    monkeypatch.setattr(gl_ports, "GL_ADAPTERS", {})
    services = cli.CliServices(
        clock=object(),  # type: ignore[arg-type]
        keyring=object(),  # type: ignore[arg-type]
        files=object(),  # type: ignore[arg-type]
        env=config.Environment.TEST,
        run_dir=tmp_path,
    )
    monkeypatch.setattr(cli, "cli_services", lambda **_: services)
    settings = SimpleNamespace(
        demo_password=SecretStr("not-a-password"), demo_totp_secret=None, run_dir=tmp_path
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(release, "stamp_release", lambda *_, **__: None)
    monkeypatch.setattr(worker, "build_runtime", lambda *_, **__: object())
    seen: list[tuple[bool, bool, Any]] = []
    stopped = "VOL-US ASC606 FY2025-P01 cannot be locked: 1 open exception item(s) hold it"

    def run(_services: Any, **named: Any) -> Any:
        seen.append(
            (GlAdapter.CSV in gl_ports.GL_ADAPTERS, named["snapshot_only"], named["through_month"])
        )
        raise perf_seed.SeedStopped(stopped)

    monkeypatch.setattr(perf_seed, "run", run)
    result = CliRunner().invoke(cli.app, ["perf", "seed", "--scale", "1/1000"])
    assert result.exit_code == 1 and seen == [(True, False, 23)]
    assert result.stderr.strip() == stopped and result.stdout == ""
    assert not (tmp_path / "reports").exists()
    # Step 5 exports no journal: the snapshot phase registers nothing. A snapshot whose job does
    # not succeed stops it the same way.
    monkeypatch.setattr(gl_ports, "GL_ADAPTERS", {})
    seen.clear()
    result = CliRunner().invoke(cli.app, ["perf", "seed", "--snapshot-only"])
    assert seen == [(False, True, 23)]
    assert result.exit_code == 1 and result.stderr.strip() == stopped and result.stdout == ""


# --- PERF-SEED-LOCK-1, step 5: the stored snapshot ------------------------------------------------


def test_step_5_asks_a_stored_backup_which_the_product_takes_without_a_sandbox() -> None:
    """DG-MK-perf-seed (5), 05 PERF-15 (rev 1.182): the snapshot of step 5 is a ``STORED_BACKUP``
    — the product stores it and loads nothing. A ``SANDBOX_SEED`` request is asked the name of
    the sandbox it creates and loads that sandbox in the same job (04 API-R-04 rev 1.67; SNP-2):
    the seed asked that purpose without a name and was refused before any export — the third
    database run of the story stopped there. The perf harness restores the row the seed stores."""
    from datetime import UTC, datetime

    from erev_api.domain.platform import snapshots
    from erev_api.enums import TenantKind
    from erev_api.problems import Problem
    from perf.support import tenant

    now = datetime(2026, 12, 1, 12, tzinfo=UTC)
    assert perf_seed.SNAPSHOT_PURPOSE == "STORED_BACKUP"
    assert perf_seed.SNAPSHOT_PURPOSE not in snapshots.SANDBOX_PURPOSES
    accepted = snapshots.check_request(
        kind=TenantKind.PRODUCTION, known_at=now, purpose=perf_seed.SNAPSHOT_PURPOSE, now=now
    )
    assert (accepted.purpose, accepted.sandbox_name) == ("STORED_BACKUP", None)
    with pytest.raises(Problem) as refused:
        snapshots.check_request(
            kind=TenantKind.PRODUCTION, known_at=now, purpose="SANDBOX_SEED", now=now
        )
    assert [error.message for error in refused.value.errors] == [
        "a sandbox copy or seed names the sandbox it creates (SNP-2)."
    ]
    assert tenant.SEED_PURPOSE == perf_seed.SNAPSHOT_PURPOSE


def test_a_snapshot_that_does_not_succeed_stops_step_5_with_the_job_s_own_sentence() -> None:
    """A snapshot that is not ``SUCCEEDED`` when its job returns stops the command
    (``SeedStopped``: stderr, exit 1), and the sentence is the one of the state its job is in.
    The job ended: what the job said — here the refusal the export gives until a retention
    policy is confirmed (PRD ERR-77), as the job stores it — once, and what the operator does.
    The job is still ``QUEUED`` or ``RUNNING``: it did not run in the command, nothing has
    ended, and the next run uses the snapshot once it has succeeded."""
    from erev_api.domain.platform import snapshot_retention
    from erev_api.jobs import registry

    stored = registry.failure_problem(snapshot_retention.refusal(None), uuid4())
    said = perf_seed.snapshot_stopped("FAILED", stored, job_state="FAILED")
    assert said == (
        "the snapshot of perf-volume ended FAILED: "
        "No snapshot retention policy is confirmed yet. A Tenant Admin sets the retention "
        "families and a second person approves them; sandbox copies are possible from the time "
        "the approved policy takes effect. Nothing of it is used: clear the cause and run make "
        "perf-seed again, which asks a new one."
    )
    # The detail and the message of its one error are one sentence; an error that adds to the
    # detail follows it, once.
    more = {
        "title": "Record changed",
        "detail": None,
        "errors": [{"message": "Reload it."}, {"message": "Reload it."}, {"message": None}],
    }
    assert perf_seed.snapshot_stopped("FAILED", more, job_state="FAILED").startswith(
        "the snapshot of perf-volume ended FAILED: Record changed Reload it. Nothing of it"
    )
    # A job that ended and left no problem says the state alone.
    assert perf_seed.snapshot_stopped("FAILED", None, job_state="FAILED").startswith(
        "the snapshot of perf-volume ended FAILED. Nothing of it is used"
    )
    # The job did not run here (jobs.registry.run_job leaves a job a worker took and one without
    # a free slot): nothing ended and nothing is discarded, whatever the job's problem holds.
    for status, job_state in (("QUEUED", "QUEUED"), ("QUEUED", "RUNNING"), ("RUNNING", "RUNNING")):
        assert perf_seed.snapshot_stopped(status, more, job_state=job_state) == (
            f"the snapshot of perf-volume is {status}: its job is {job_state} and did not run in "
            "this command — a worker beside the seed holds it or fills the job slots of the "
            "workspace. Run make perf-seed again: a snapshot that has succeeded by then is used, "
            "and otherwise a new one is asked."
        )
    assert perf_seed.JOB_UNFINISHED == {"QUEUED", "RUNNING"}


def test_the_seed_states_its_two_settings_as_versions_its_reviewer_approves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The volume tenant's two settings are registry versions of scope TENANT that
    perf-accountant authors and perf-reviewer approves (``_publish_setting``). The CLOSE version
    asks no reconciliation at a lock. The PLATFORM version states the five retention families
    with the literals of the product's own catalogue, which the export of a snapshot asks with a
    named human approval (PRD ERR-77; the parameter never approves automatically): the seed's
    confirmation of a proposal for its own synthetic dataset."""
    from erev_api.domain.close import gates
    from erev_api.domain.platform import snapshot_dataset
    from erev_api.enums import RegistryCategory
    from erev_api.registry import platform as catalogue

    asked: list[dict[str, Any]] = []
    monkeypatch.setattr(perf_seed, "_publish_setting", lambda ctx, **named: asked.append(named))
    context: Any = object()
    perf_seed._lock_without_reconciliations(context)  # noqa: SLF001
    perf_seed._confirm_retention(context)  # noqa: SLF001
    close, retention = asked
    assert (close["category"], close["values"], close["comment"], close["what"]) == (
        RegistryCategory.CLOSE,
        {gates.REQUIRE_RECONCILIATIONS: False},
        perf_seed.PARAMETER_COMMENT,
        gates.REQUIRE_RECONCILIATIONS,
    )
    assert (retention["category"], retention["comment"], retention["what"]) == (
        RegistryCategory.PLATFORM,
        perf_seed.RETENTION_COMMENT,
        "platform.snapshot_retention_families",
    )
    assert retention["values"] == {
        "platform.snapshot_retention_families": {
            "file_object": "FILE_RETENTION",
            "import_row": "AUDIT_RETENTION_YEARS",
            "source_record": "AUDIT_RETENTION_YEARS",
            "contract_event": "AUDIT_RETENTION_YEARS",
            "manual_adjustment": "AUDIT_RETENTION_YEARS",
        }
    }
    families = retention["values"]["platform.snapshot_retention_families"]
    assert families == dict(snapshot_dataset.RETENTION_FAMILIES)
    assert set(families.values()) <= set(snapshot_dataset.RETENTION_LITERALS)
    assert "platform.snapshot_retention_families" in catalogue.HUMAN_APPROVAL_REQUIRED
    assert "synthetic" in perf_seed.RETENTION_COMMENT
