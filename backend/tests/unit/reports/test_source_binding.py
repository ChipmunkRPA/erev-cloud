"""frps3b — CUTOFF-R1 consumed-source binding (record §44; 04 T-RPT-02 ``source_binding`` rev 1.55;
ENGINE_SPEC_B S15-R-24; Codex 2131 / 2154 / 2202). CPU pins of the binding's pure parts and of the
framework's derivations; the database boundaries (build → persist → rerun → explain) are the
authored DB cases in ``tests/domain/reports/test_source_binding_db.py`` (not run — databases not
provisioned).

Fail-first: written before the code; red on the docs-first tree (no ``SourceBinding``).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.domain.reports import framework, tie_outs
from erev_api.domain.reports.builders import (
    ADAPTER,
    BINDING_VERSION,
    OPEN,
    RETAINED,
    ReportParams,
    SourceBinding,
    SourceCollector,
    api_client_inventory,
)
from erev_api.problems import Problem
from erev_api.schemas.reports import ReportRunSourcesOut

K = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
V1, V2, V3 = (uuid5(NAMESPACE_URL, f"erev://tests/version/{n}") for n in (1, 2, 3))
CUST_A = uuid5(NAMESPACE_URL, "erev://tests/customer/a")
PROD_P = uuid5(NAMESPACE_URL, "erev://tests/product/p")
BINDING = SourceBinding(
    cutoff=K,
    versions={"ASC606": (V1, V2)},
    labels={"customer_segment": {str(CUST_A): "Enterprise"}, "product_family": {str(PROD_P): None}},
    row_keys=frozenset({"customer_segment:Enterprise", "total:USD"}),
)


def _params(**over: Any) -> ReportParams:
    base: dict[str, Any] = {
        "report_code": "rpo",
        "report_version": 1,
        "parameters": {"row_dimension": "CUSTOMER_SEGMENT"},
        "entity_ids": (uuid5(NAMESPACE_URL, "erev://tests/entity/US01"),),
        "known_at": K,
        "book_code": "ASC606",
    }
    base.update(over)
    return ReportParams(**base)


def _row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "report_run_no": "RPT-000042",
        "report_code": "rpo",
        "status": "SUCCEEDED",
        "source_binding": None,
        "period_lock_id": None,
    }
    base.update(over)
    return base


class _Session:
    """A session whose ``execute(...).scalars()`` yields fixed ids; records whether it was asked."""

    def __init__(self, ids: tuple[UUID, ...], transaction_at: datetime) -> None:
        self.ids = ids
        self.transaction_at = transaction_at
        self.executed = 0

    def execute(self, statement: Any) -> Any:
        self.executed += 1
        text = str(statement)
        if "transaction_timestamp" in text:
            return SimpleNamespace(scalar_one=lambda: self.transaction_at)
        return SimpleNamespace(scalars=lambda: iter(self.ids))


def test_binding_round_trips_through_its_stored_form() -> None:
    stored = BINDING.to_stored()
    assert stored["binding_version"] == BINDING_VERSION == 1
    assert stored["cutoff"] == "2026-03-31T12:00:00Z"
    assert stored["versions"] == {"ASC606": [str(V1), str(V2)]}
    assert stored["labels"] == {
        "customer_segment": {str(CUST_A): "Enterprise"},
        "product_family": {str(PROD_P): None},
    }
    assert stored["row_keys"] == ["customer_segment:Enterprise", "total:USD"]
    assert (stored["strategy"], stored["members"], stored["open"], stored["dataset"]) == (
        ADAPTER,
        {},
        [],
        None,
    )
    assert stored["evidence"] == {}
    again = SourceBinding.from_stored(stored)
    assert again == BINDING
    assert SourceBinding.from_stored(None) is None
    with pytest.raises(ValueError, match="binding_version"):
        SourceBinding.from_stored({**stored, "binding_version": 2})


def test_binding_summary_counts_versions_labels_members_and_rows() -> None:
    assert BINDING.summary() == {
        "bound": True,
        "kind": "bound",
        "strategy": ADAPTER,
        "cutoff": K,
        "versions": 2,
        "labels": 2,
        "members": 0,
        "rows": 2,
        "open": [],
    }
    assert BINDING.version_ids("ASC606") == (V1, V2)
    assert BINDING.version_ids("IFRS15") == ()
    assert BINDING.label("customer_segment", str(CUST_A)) == (True, "Enterprise")
    assert BINDING.label("product_family", str(PROD_P)) == (True, None)
    assert BINDING.label("customer_segment", "missing") == (False, None)


def test_collector_records_what_a_live_build_consumes_and_freezes_it() -> None:
    collector = SourceCollector()
    collector.record_cutoff(K)
    collector.record_versions("ASC606", (V2, V1))
    collector.record_versions("ASC606", (V2,))  # a second consumer of the same book: a set
    collector.record_label("customer_segment", str(CUST_A), "Enterprise")
    collector.record_members("journal_run", [V3, V3])
    binding = collector.binding(
        row_keys=["total:USD", "customer_segment:Enterprise"],
        strategy=RETAINED,
        open=("x",),
        report_version=3,
        dataset={"output_sha256": "f" * 64, "format": "JSON"},
    )
    assert binding.cutoff == K
    assert binding.version_ids("ASC606") == tuple(sorted((V1, V2), key=str))
    assert binding.label("customer_segment", str(CUST_A)) == (True, "Enterprise")
    assert binding.member_ids("journal_run") == (str(V3),)
    assert binding.row_keys == frozenset({"total:USD", "customer_segment:Enterprise"})
    assert (binding.strategy, binding.open, binding.report_version) == (RETAINED, ("x",), 3)
    assert SourceBinding.from_stored(binding.to_stored()) == binding
    assert binding.summary()["kind"] == "retained" and binding.summary()["members"] == 1
    assert binding.summary()["bound"] is True
    opened = collector.binding(row_keys=[], strategy=OPEN)
    assert (opened.summary()["kind"], opened.summary()["bound"]) == (OPEN, False)
    with pytest.raises(ValueError, match="cutoff"):
        SourceCollector().binding(row_keys=[])


def test_the_bound_cutoff_keeps_its_exact_instant_to_the_microsecond() -> None:
    """Codex 2216 (A): a cutoff of 12:00:00.800000Z that included a version stamped at
    12:00:00.500000Z must not become 12:00:00Z on the bound read — the truncated boundary would
    EXCLUDE that bound version; the stored form and the restored instant are exact."""
    exact = datetime(2026, 3, 31, 12, 0, 0, 800000, tzinfo=UTC)
    inside = datetime(2026, 3, 31, 12, 0, 0, 500000, tzinfo=UTC)
    binding = replace(BINDING, cutoff=exact)
    stored = binding.to_stored()
    assert stored["cutoff"] == "2026-03-31T12:00:00.800000Z"
    restored = SourceBinding.from_stored(stored)
    assert restored is not None and restored.cutoff == exact
    assert inside <= restored.cutoff  # the version inside the second stays selected
    truncated = exact.replace(microsecond=0)
    assert not inside <= truncated  # what the truncated form would have done
    session = _Session((), transaction_at=datetime(2026, 4, 9, tzinfo=UTC))
    assert tie_outs.cutoff_for(session, _params(binding=restored)) == exact


def test_cutoff_for_a_bound_run_is_the_bound_cutoff_never_the_transaction_time() -> None:
    later = datetime(2026, 4, 9, 9, 30, tzinfo=UTC)
    session = _Session((), transaction_at=later)
    bound = _params(binding=BINDING)  # a record-basis run whose build applied K
    assert tie_outs.cutoff_for(session, bound) == K
    assert session.executed == 0  # no transaction_timestamp() read
    collector = SourceCollector()
    live = _params(sources=collector)
    assert tie_outs.cutoff_for(session, live) == later  # record basis: max(K, transaction time)
    assert collector.cutoff == later


def test_versions_for_a_bound_run_are_the_bound_ids_never_a_new_latest_query() -> None:
    session = _Session((V3,), transaction_at=K)  # today's "latest" would be V3
    bound = _params(binding=BINDING)
    assert tie_outs.versions_for(session, bound, book_code="ASC606", cutoff=K) == (V1, V2)
    assert session.executed == 0
    collector = SourceCollector()
    live = _params(sources=collector)
    assert tie_outs.versions_for(session, live, book_code="ASC606", cutoff=K) == (V3,)
    assert session.executed == 1 and collector.versions == {"ASC606": {V3}}


def test_label_for_a_bound_run_is_the_bound_value_never_the_live_join() -> None:
    bound = _params(binding=BINDING)
    assert tie_outs.label_for(bound, "customer_segment", CUST_A, "SMB") == "Enterprise"  # A → B
    assert tie_outs.label_for(bound, "product_family", PROD_P, "Platform") is None
    # Codex 2216 (B): a binding without the label is refused by NAME — never a silent live value.
    with pytest.raises(Problem) as incomplete:
        tie_outs.label_for(bound, "customer_segment", uuid5(NAMESPACE_URL, "other"), "SMB")
    assert "holds no customer_segment" in str(incomplete.value.detail)
    collector = SourceCollector()
    live = _params(sources=collector)
    assert tie_outs.label_for(live, "customer_segment", CUST_A, "SMB") == "SMB"
    assert collector.labels == {"customer_segment": {str(CUST_A): "SMB"}}
    assert tie_outs.label_for(live, "customer_segment", None, "x") == "x"  # no key: not recorded
    assert "None" not in collector.labels["customer_segment"]


def test_members_of_a_bound_run_restrict_a_non_version_read_and_a_live_build_records_them() -> None:
    """Codex 2154 (2): subledger-line and journal-run memberships are bound, not re-read."""
    from sqlalchemy import column

    bound = _params(
        binding=replace(BINDING, members={"journal_run": (str(V3),), "subledger_line": ()})
    )
    (predicate,) = tie_outs.bound_member_where(bound, "journal_run", column("id"))
    rendered = str(predicate.compile(compile_kwargs={"literal_binds": True}))
    assert V3.hex in rendered.replace("-", "")  # the bound run id, rendered as a literal
    # an explicit EMPTY membership reads nothing; an ABSENT kind refuses by name (Codex 1004 R1)
    (none,) = tie_outs.bound_member_where(bound, "subledger_line", column("id"))
    assert str(none.compile()).strip().lower() in ("false", "0 = 1")
    absent = _params(binding=replace(BINDING, members={"journal_run": (str(V3),)}))
    with pytest.raises(Problem) as refused:
        tie_outs.bound_member_where(absent, "subledger_line", column("id"))
    assert "members.subledger_line" in str(refused.value.detail)
    assert tie_outs.bound_member_where(_params(), "journal_run", column("id")) == []
    collector = SourceCollector()
    tie_outs.record_members(_params(sources=collector), "subledger_line", [V1, V2])
    assert collector.members == {"subledger_line": {str(V1), str(V2)}}
    tie_outs.record_members(bound, "subledger_line", [V1])  # a bound run records nothing


def test_report_params_carries_the_stored_binding_and_none_for_an_unbound_run() -> None:
    row = {
        "report_code": "rpo",
        "report_version": 1,
        "parameters": {"row_dimension": "CUSTOMER_SEGMENT", "known_at": "2026-03-31T12:00:00Z"},
        "entity_ids": [],
        "known_at": K,
        "book_code": "ASC606",
        "as_of_date": None,
        "period_lock_id": None,
        "output_format": "JSON",
        "source_binding": BINDING.to_stored(),
    }
    assert framework.report_params(row).binding == BINDING
    assert framework.report_params({**row, "source_binding": None}).binding is None
    assert framework.report_params(row).sources is None  # collectors are the job's, per build


def test_sources_out_summarises_a_bound_run_and_classifies_every_other_lifecycle_state() -> None:
    bound = framework.sources_out(_row(source_binding=BINDING.to_stored()))
    assert bound == ReportRunSourcesOut(
        bound=True,
        kind="bound",
        strategy=ADAPTER,
        cutoff=K,
        versions=2,
        labels=2,
        members=0,
        rows=2,
        open=[],
    )
    legacy = framework.sources_out(_row())
    assert (legacy.bound, legacy.kind, legacy.strategy, legacy.open) == (
        False,
        framework.KIND_LEGACY,
        ADAPTER,
        list(framework.SOURCE_CONTRACTS["rpo"].open),  # the declared qualification (2245 (d))
    )
    assert framework.sources_out(_row(status="QUEUED")).kind == framework.KIND_PENDING
    assert framework.sources_out(_row(status="RUNNING")).kind == framework.KIND_PENDING
    assert framework.sources_out(_row(status="FAILED")).kind == framework.KIND_FAILED
    locked = framework.sources_out(_row(period_lock_id=uuid5(NAMESPACE_URL, "l")))
    assert (locked.bound, locked.kind) == (False, framework.KIND_AS_LOCKED)
    inventory = framework.sources_out(_row(report_code="api_client_inventory", status="QUEUED"))
    assert (inventory.kind, inventory.strategy) == (framework.KIND_PENDING, RETAINED)
    assert inventory.open == list(framework.SOURCE_CONTRACTS["api_client_inventory"].open)
    # An OPEN-strategy run carries a record but is not source-bound: kind `open`, bound False.
    opened = framework.sources_out(
        _row(
            report_code="legacy_je_summary",
            source_binding=replace(BINDING, strategy=OPEN, versions={}).to_stored(),
        )
    )
    assert (opened.bound, opened.kind, opened.strategy) == (False, framework.KIND_OPEN, OPEN)


def test_every_registered_live_builder_states_its_source_contract() -> None:
    """Codex 2202: the same-source promise covers all 15 registered builders — each declares its
    strategy, what its adapter binds and what stays OPEN; an empty capture is never 'complete'."""
    assert set(framework.SOURCE_CONTRACTS) == set(framework.BUILDERS)
    assert (
        len(framework.BUILDERS) == 37
    )  # 15 at the design + ENG-C6's two E-64 producers (7bf044a5) + F-CTR's modification_register
    # (CTR-17 slice 1, D-98 140-A1) + F-CLO's manual_adjustment_register (RPS-8 RPT-18; S15-R-20d)
    # + the four SSP reports of BUILD_SPEC RPS-9 (RPT-19 to RPT-22; lane F-RPS-REG) + the six
    # registers of BUILD_SPEC RPS-10 (RPT-23 to RPT-26, RPT-43, RPT-44; lane F-RPS-REG) + the
    # three registers of BUILD_SPEC RPS-11 (RPT-28 to RPT-30; RPT-31 waits for CTR-14) + the
    # three analysis reports of BUILD_SPEC RPS-12 (RPT-33 to RPT-35; RPT-36 waits for its source)
    # + the late-entry report of BUILD_SPEC RPS-8 (RPT-17; lane F-RPS-REG)
    for code in ("je_population", "out_of_period_register", "modification_register"):
        assert framework.SOURCE_CONTRACTS[code].strategy == OPEN, code
        assert framework.SOURCE_CONTRACTS[code].open, code  # re-execution OPEN, declared
    for code, contract in framework.SOURCE_CONTRACTS.items():
        assert contract.strategy in (ADAPTER, RETAINED, OPEN), code
        assert contract.bound, code  # nothing is bound "by a JSON object existing"
        if contract.strategy == OPEN:
            assert contract.open, code  # an open builder names what it does not bind
    adapters = {code for code, c in framework.SOURCE_CONTRACTS.items() if c.strategy == ADAPTER}
    assert {"rpo", "revenue_waterfall", "contract_history", "rpo_rollforward"} <= adapters
    assert framework.SOURCE_CONTRACTS["api_client_inventory"].strategy == RETAINED
    # ENG-C4's eighteenth builder is an adapter: the bound cutoff, its selected versions and its
    # historical membership candidates; open = the reference-line population (frps3c-1 retained
    # the configuration, so that qualification is gone).
    c4 = framework.SOURCE_CONTRACTS["revenue_from_prior_period_obligations"]
    assert c4.strategy == ADAPTER and len(c4.open) == 1
    assert c4.open[0].startswith("subledger-line REFERENCE population")
    opened = {code for code, c in framework.SOURCE_CONTRACTS.items() if c.strategy == OPEN}
    assert opened == {
        "legacy_contract_history_export",
        "latest_contract_status",
        "legacy_latest_contract_export",
        "legacy_je_summary",
        "migration_reconciliation",
        "je_population",
        "out_of_period_register",
        "modification_register",  # F-CTR CTR-17 slice 1 (D-98 140-A1): reads live, no adapter yet
        "manual_adjustment_register",  # F-CLO RPS-8 RPT-18 (S15-R-20d): reads live, no adapter yet
        # BUILD_SPEC RPS-9 (lane F-RPS-REG): the SSP reports read live, no adapter yet
        "ssp_change_log",
        "ssp_version_diff",
        "allocations_by_ssp_version",
        "ssp_override_listing",
        # BUILD_SPEC RPS-10 (lane F-RPS-REG): the access, configuration, approvals and audit
        # registers read live, no adapter yet
        "config_change_register",
        "user_access_listing",
        "sod_conflict_report",
        "approvals_register",
        "audit_log_export",
        "chain_verification_report",
        # BUILD_SPEC RPS-11 (lane F-RPS-REG): the judgement, estimate-change and scope-exclusion
        # registers read live, no adapter yet
        "judgement_register",
        "estimate_change_listing",
        "scope_exclusion_register",
        # BUILD_SPEC RPS-12 (lane F-RPS-REG): the book bridge, the adoption bridge and the
        # intercompany pairs read live, no adapter yet
        "book_bridge",
        "adoption_bridge",
        "intercompany_pairs",
        # BUILD_SPEC RPS-8 (lane F-RPS-REG): the late-entry report reads live, no adapter yet
        "late_entry_report",
    }
    # The registered explainers bind every SOURCE dimension and, since frps3c-1 retained the
    # consumed configuration as evidence, declare NOTHING open; no adapter names configuration as
    # open any more (Codex 2245 (d) closed by the actual reader, not by declaration).
    for code in ("rpo", "revenue_waterfall", "rpo_rollforward", "contract_history"):
        assert framework.SOURCE_CONTRACTS[code].open == (), code
    for code, contract in framework.SOURCE_CONTRACTS.items():
        if contract.strategy == ADAPTER:
            assert not any(o.startswith("consumed-configuration") for o in contract.open), code
            assert any("consumed configuration retained" in o for o in contract.bound), code


def test_an_unbound_live_run_is_refused_by_name_on_rerun_and_explain() -> None:
    row = _row()
    with pytest.raises(Problem) as rerun_refusal:
        framework.require_bound(row, framework.RERUN_UNBOUND, "invalid-transition")
    assert rerun_refusal.value.slug == "invalid-transition"
    assert "RPT-000042" in str(rerun_refusal.value.detail)
    assert "created before source binding" in str(rerun_refusal.value.detail)
    with pytest.raises(Problem) as explain_refusal:
        framework.require_bound(row, framework.EXPLAIN_UNBOUND, "not-found")
    assert explain_refusal.value.slug == "not-found"
    # As-locked runs carry no binding by design and are not refused here (S15-R-19 rules apply).
    framework.require_bound(
        {**row, "period_lock_id": uuid5(NAMESPACE_URL, "l")},
        framework.RERUN_UNBOUND,
        "invalid-transition",
    )
    framework.require_bound(
        {**row, "source_binding": BINDING.to_stored()},
        framework.RERUN_UNBOUND,
        "invalid-transition",
    )
    # Codex 2154 (4): a FAILED original (nothing captured) is not "legacy" — it may rerun as a NEW
    # evaluation; QUEUED / RUNNING runs are pending, not legacy.
    framework.require_bound(
        {**row, "status": "FAILED"}, framework.RERUN_UNBOUND, "invalid-transition"
    )
    assert framework.run_kind({**row, "status": "FAILED"}) == framework.KIND_FAILED
    assert framework.run_kind({**row, "status": "RUNNING"}) == framework.KIND_PENDING
    # A legacy run of an OPEN-strategy builder reruns as a NEW live evaluation: not refused.
    framework.require_bound(
        {**row, "report_code": "legacy_je_summary"}, framework.RERUN_UNBOUND, "invalid-transition"
    )
    # A binding this release cannot read refuses by name too (implementation contract).
    with pytest.raises(Problem) as incompatible:
        framework.require_bound(
            {**row, "source_binding": {**BINDING.to_stored(), "binding_version": 99}},
            framework.RERUN_UNBOUND,
            "invalid-transition",
        )
    assert "cannot read" in str(incompatible.value.detail)


def test_a_row_key_the_original_did_not_hold_is_refused_by_name() -> None:
    with pytest.raises(Problem) as refused:
        framework.require_original_row(BINDING, "customer_segment:SMB")
    assert refused.value.slug == "validation-failed"
    (finding,) = refused.value.errors
    assert finding.field == "filters.row_key" and "customer_segment:SMB" in finding.message
    framework.require_original_row(BINDING, "customer_segment:Enterprise")  # held: no refusal


class _NoQueries:
    """A session that refuses every query: a bound retained-inputs build reads NO live row."""

    def execute(self, statement: Any) -> Any:
        raise AssertionError(f"live query under a bound run: {str(statement)[:60]}")


def _inventory_evidence(status: str = "ACTIVE") -> dict[str, Any]:
    return {
        "rows": [
            {
                "name": "Binding witness",
                "client_id": "erev_ak_witness",
                "status": status,
                "scopes": ["contract.read"],
                "is_all_entities": False,
                "entity_ids": [str(uuid5(NAMESPACE_URL, "erev://tests/entity/US01"))],
                "rate_limit_per_minute": 600,
                "expires_at": None,
                "last_used_at": "2026-03-31T11:59:00+00:00",
                "secret_rotated_at": None,
                "created_by": str(CUST_A),
                "created_by_kind": "USER",
                "created_at": "2026-03-01T09:00:00+00:00",
            }
        ],
        "codes": {str(uuid5(NAMESPACE_URL, "erev://tests/entity/US01")): "US01"},
        "names": {str(CUST_A): "Maya Chen"},
    }


def test_a_retained_inputs_builder_rebuilds_from_its_evidence_without_reading_live_rows() -> None:
    """Codex 2225: retained evidence SUPPLIES INPUTS to the real builder logic — the bound rebuild
    runs the same code over the retained rows (no live query), changed current data is ignored,
    and a changed input changes the output (it is computed, not copied)."""
    binding = replace(
        BINDING,
        strategy=RETAINED,
        versions={},
        labels={},
        evidence={api_client_inventory.EVIDENCE: _inventory_evidence()},
    )
    params = _params(report_code="api_client_inventory", parameters={}, binding=binding)
    uow = SimpleNamespace(session=_NoQueries())
    data = api_client_inventory.build(uow, params)  # type: ignore[arg-type]
    (row,) = data.rows
    assert row["row_key"] == "client:binding-witness"
    assert (row["status"], row["entity_scope"], row["created_by"]["display_name"]) == (
        "ACTIVE",
        ("US01",),
        "Maya Chen",
    )
    assert data.control_totals == {api_client_inventory.CONTROL_TOTAL: 1}
    # The revoke happened live after the run: the retained inputs still say ACTIVE (ignored).
    revoked = replace(
        binding, evidence={api_client_inventory.EVIDENCE: _inventory_evidence("REVOKED")}
    )
    (changed,) = api_client_inventory.build(
        uow,  # type: ignore[arg-type]
        _params(report_code="api_client_inventory", parameters={}, binding=revoked),
    ).rows
    assert changed["status"] == "REVOKED"  # computed from the inputs it is given
    # A binding without the evidence is refused by name — never completed from live rows.
    with pytest.raises(Problem) as incomplete:
        api_client_inventory.build(
            uow,  # type: ignore[arg-type]
            _params(
                report_code="api_client_inventory",
                parameters={},
                binding=replace(binding, evidence={}),
            ),
        )
    assert "holds no api_client_inventory" in str(incomplete.value.detail)


def test_the_inventory_shows_the_grant_of_each_client() -> None:
    """Supervisor ruling R-38 (iii) (03 REQ-PLT-033 rev 1.83; SCREENS_B §5.6.5 RPT-27 rev 1.48;
    CTL-037 evidence): a client's scopes are an access grant, and the inventory shows it — the
    request, who approved it and when; ``Rule <key>`` when a rule approved it at submission; and
    nothing while it is pending, after a rejection, or for a client that has no request. The
    columns are computed from the retained inputs like every other."""
    approver = str(uuid5(NAMESPACE_URL, "erev://tests/user/grace"))
    evidence = _inventory_evidence()
    (template,) = evidence["rows"]
    grants: dict[str, dict[str, Any] | None] = {
        "by a person": {
            "request_no": "APR-000007",
            "approved_at": "2026-03-02T10:00:00+00:00",
            "approvers": [[approver, "USER"]],
            "rule_key": None,
        },
        "by the rule": {
            "request_no": "APR-000001",
            "approved_at": "2026-03-01T09:00:00+00:00",
            "approvers": [],
            "rule_key": "AUTO-BOOTSTRAP",
        },
        "pending": {
            "request_no": "APR-000009",
            "approved_at": None,
            "approvers": [],
            "rule_key": None,
        },
        "without a request": None,
    }
    evidence["rows"] = [
        {**template, "name": name, "grant": grant} for name, grant in grants.items()
    ]
    evidence["names"] = {**evidence["names"], approver: "Grace Lin"}
    binding = replace(
        BINDING,
        strategy=RETAINED,
        versions={},
        labels={},
        evidence={api_client_inventory.EVIDENCE: evidence},
    )
    data = api_client_inventory.build(
        SimpleNamespace(session=_NoQueries()),  # type: ignore[arg-type]
        _params(report_code="api_client_inventory", parameters={}, binding=binding),
    )
    shown = {
        row["name"]: (row["approval"], row["approved_by"], row["approved_at"]) for row in data.rows
    }
    assert shown == {
        "by a person": ("APR-000007", "Grace Lin", datetime(2026, 3, 2, 10, tzinfo=UTC)),
        "by the rule": ("APR-000001", "Rule AUTO-BOOTSTRAP", datetime(2026, 3, 1, 9, tzinfo=UTC)),
        "pending": ("APR-000009", None, None),
        "without a request": (None, None, None),
    }
    headers = [(column.key, column.header, column.empty_text) for column in data.columns]
    assert ("secret_rotated_at", "Secret issued", "Not issued") in headers
    assert [key for key, _, _ in headers][-5:] == [
        "approval",
        "approved_by",
        "approved_at",
        "created_by",
        "created_at",
    ]
    # Evidence retained before the columns existed carries no grant: the cells are empty.
    older = replace(binding, evidence={api_client_inventory.EVIDENCE: _inventory_evidence()})
    (row,) = api_client_inventory.build(
        SimpleNamespace(session=_NoQueries()),  # type: ignore[arg-type]
        _params(report_code="api_client_inventory", parameters={}, binding=older),
    ).rows
    assert (row["approval"], row["approved_by"], row["approved_at"]) == (None, None, None)


class _CapturingSession:
    """Records the SQL of every statement; ``scalars()`` yields the fixed ids."""

    def __init__(self, ids: tuple[UUID, ...]) -> None:
        self.ids = ids
        self.statements: list[str] = []

    def execute(self, statement: Any) -> Any:
        self.statements.append(str(statement))
        return SimpleNamespace(scalars=lambda: iter(self.ids))


def test_the_journal_run_capture_is_scoped_exactly_as_the_summed_population() -> None:
    """Codex 2245 (c): the recorded ``journal_run`` members are CONTRIBUTORS — runs whose REVENUE
    lines lie in the summed population (book, entities, periods) — not the broader eligible set; the
    capture applies the very predicates the sum applies, and a bound run applies none of the live
    rule (its membership is the bound ids)."""
    from erev_api.db.tables import journal_line

    period_id = uuid5(NAMESPACE_URL, "erev://tests/period/2026-09")
    entity_id = uuid5(NAMESPACE_URL, "erev://tests/entity/US01")
    scope = [
        journal_line.c.book_code == "ASC606",
        journal_line.c.entity_id.in_([entity_id]),
        journal_line.c.period_id.in_([period_id]),
    ]
    run_id = uuid5(NAMESPACE_URL, "erev://tests/journal-run/1")
    collector = SourceCollector()
    live = tie_outs._journal_run_membership(
        _CapturingSession((run_id,)),  # type: ignore[arg-type]
        _params(sources=collector),
        K,
        scope=scope,
    )
    # Supervisor ruling R-52 (a), superseding D-87 L6-3-Q-32: not cancelled and created by
    # known_at — the run's mode is no part of the rule since a seal is journalised by one run only
    # (04 DB-16 rev 1.106).
    assert len(live) == 2
    session_sql = _CapturingSession((run_id,))
    tie_outs._journal_run_membership(
        session_sql,  # type: ignore[arg-type]
        _params(sources=collector),
        K,
        scope=scope,
    )
    (sql,) = session_sql.statements
    assert "journal_run.mode" not in sql
    assert "journal_line.account_role" in sql
    assert "journal_line.book_code" in sql and "journal_line.period_id IN" in sql
    assert "journal_line.entity_id IN" in sql and "journal_run.created_at <=" in sql
    assert collector.members["journal_run"] == {str(run_id)}
    # Bound: the membership IS the bound ids; nothing live is applied and nothing is queried.
    bound = tie_outs._journal_run_membership(
        _NoQueries(),  # type: ignore[arg-type]
        _params(binding=replace(BINDING, members={"journal_run": (str(run_id),)})),
        K,
        scope=scope,
    )
    assert len(bound) == 1 and "journal_run.id IN" in str(bound[0])
