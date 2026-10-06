"""CLO-5 data-quality monitors as pure rules (04 table 15.4-E; REQ-CLS-019; T-PLT-31; T-IMP-05
dedupe keys; E-43 severity mapping). F-CLO preparation: `docs/reviews/loop/prod/F-CLO-prep.md`
§4."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.domain.close import gates
from erev_api.domain.close import monitor_rules as mr
from erev_api.enums import ChecklistStatus, ExceptionSeverity

PERIOD_START = date(2026, 9, 1)
PERIOD_END = date(2026, 9, 30)
C1 = UUID("00000000-0000-0000-0000-000000000c01")
C2 = UUID("00000000-0000-0000-0000-000000000c02")
O1 = UUID("00000000-0000-0000-0000-000000000001")
R1 = UUID("00000000-0000-0000-0000-00000000aa01")
R2 = UUID("00000000-0000-0000-0000-00000000aa02")
E_SCOPE = UUID("00000000-0000-0000-0000-0000000000e1")
P_SCOPE = UUID("00000000-0000-0000-0000-00000000aa09")
SCOPE = f"{E_SCOPE}:{P_SCOPE}"  # D-98 57: entity and period in every DATA_QUALITY identity


def _run(inputs: mr.MonitorInputs, **kwargs: object) -> mr.MonitorOutcome:
    return mr.evaluate(
        inputs,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        entity_id=E_SCOPE,
        period_id=P_SCOPE,
        **kwargs,  # type: ignore[arg-type]
    )


def test_monitors_match_table_15_4_e() -> None:
    assert [(m.code, m.default_severity) for m in mr.MONITORS] == [
        ("DQ_DUPLICATE_INVOICE", "ERROR"),
        ("DQ_REVENUE_WITHOUT_BILLING", "WARNING"),
        ("DQ_NEGATIVE_LIABILITY_LAYER", "ERROR"),
        ("DQ_RECOGNITION_AFTER_POB_END", "WARNING"),
        ("DQ_INACTIVE_CONTRACT", "WARNING"),
        ("FX_RATE_MISSING", "ERROR"),
    ]
    by_code = {m.code: m for m in mr.MONITORS}
    assert (
        by_code["DQ_REVENUE_WITHOUT_BILLING"].setting_key == "close.dq_revenue_without_billing_days"
    )
    assert by_code["DQ_INACTIVE_CONTRACT"].setting_key == "close.dq_inactive_contract_days"
    assert mr.DEFAULT_SETTINGS == {
        "close.dq_revenue_without_billing_days": 60,
        "close.dq_inactive_contract_days": 90,
    }


def test_duplicate_invoice_one_finding_per_key() -> None:
    rows = (
        mr.SourceInvoiceRef("SFDC", "INV-US-1001", "1", R1),
        mr.SourceInvoiceRef(
            "SFDC", "INV-US-1001", "1", R2
        ),  # the same key and version twice: duplicate
        mr.SourceInvoiceRef("SFDC", "INV-US-1002", "1", R1),
        mr.SourceInvoiceRef(
            "SFDC", "INV-US-1002", "2", R2
        ),  # a later version: correction path (Q-8)
        mr.SourceInvoiceRef("STRIPE", "INV-US-1001", "1", R1),  # another system: no duplicate
        mr.SourceInvoiceRef("SFDC", "INV-US-1003", "1", R1),
        mr.SourceInvoiceRef("SFDC", "INV-US-1003", "1", R1),  # the same row twice: not a duplicate
    )
    outcome = _run(mr.MonitorInputs(invoices=rows))
    assert [f.code for f in outcome.findings] == ["DQ_DUPLICATE_INVOICE"]
    (finding,) = outcome.findings
    assert finding.severity is ExceptionSeverity.BLOCKING
    assert finding.dedupe_key == f"DATA_QUALITY:DQ_DUPLICATE_INVOICE:{SCOPE}:SFDC:INV-US-1001:1"
    assert "INV-US-1001" in finding.message and "2" in finding.message
    assert (outcome.blocking, outcome.warnings) == (1, 0)


def test_duplicate_invoice_identity_tuple() -> None:
    # Q-8 rule 2: distinct external ids with one (customer, invoice number, amount, date).
    same = dict(
        customer_ref="CUST-7",
        invoice_number="A-1001",
        amount=Decimal("1200.00"),
        issue_date=date(2026, 9, 3),
    )
    rows = (
        mr.SourceInvoiceRef("SFDC", "EXT-1", "1", R1, **same),  # type: ignore[arg-type]
        mr.SourceInvoiceRef("SFDC", "EXT-2", "1", R2, **same),  # type: ignore[arg-type]
        mr.SourceInvoiceRef(
            "SFDC",
            "EXT-3",
            "1",
            R1,
            customer_ref="CUST-7",
            invoice_number="A-1001",
            amount=Decimal("1200.00"),
        ),  # incomplete identity: the rule needs all four
        mr.SourceInvoiceRef(
            "SFDC",
            "EXT-4",
            "1",
            R2,
            customer_ref="CUST-8",
            invoice_number="A-1001",
            amount=Decimal("1200.00"),
            issue_date=date(2026, 9, 3),
        ),  # another customer
    )
    outcome = _run(mr.MonitorInputs(invoices=rows))
    (finding,) = outcome.findings
    assert finding.code == "DQ_DUPLICATE_INVOICE"
    assert (
        finding.dedupe_key
        == f"DATA_QUALITY:DQ_DUPLICATE_INVOICE:{SCOPE}:CUST-7:A-1001:1200.00:2026-09-03"
    )
    assert (
        "EXT-1" in finding.message and "EXT-2" in finding.message and "EXT-3" not in finding.message
    )
    assert mr.SourceInvoiceRef("SFDC", "EXT-3", "1", R1).identity() is None


@pytest.mark.parametrize(
    ("first_recognition", "billed", "limit", "expected"),
    [
        (date(2026, 7, 31), None, None, 1),  # 61 days > 60
        (date(2026, 8, 1), None, None, 0),  # exactly 60 days: not "more than"
        (date(2026, 7, 31), date(2026, 8, 15), None, 0),  # billed
        (date(2026, 8, 25), None, 30, 1),  # tenant setting 30: 36 days
    ],
)
def test_revenue_without_billing_threshold(
    first_recognition: date, billed: date | None, limit: int | None, expected: int
) -> None:
    settings = None if limit is None else {mr.REVENUE_WITHOUT_BILLING_DAYS: limit}
    outcome = _run(
        mr.MonitorInputs(unbilled=(mr.UnbilledRevenueRef(C1, O1, first_recognition, billed),)),
        settings=settings,
    )
    assert len(outcome.findings) == expected
    if expected:
        (finding,) = outcome.findings
        assert finding.code == "DQ_REVENUE_WITHOUT_BILLING"
        assert finding.severity is ExceptionSeverity.WARNING
        assert finding.dedupe_key == f"DATA_QUALITY:DQ_REVENUE_WITHOUT_BILLING:{SCOPE}:{O1}"
        assert finding.obligation_id == O1 and finding.contract_id == C1


def test_negative_liability_layer() -> None:
    layers = (
        mr.LiabilityLayerRef(
            C1, "CONTRACT_LIABILITY:SF-ORD-10001/EV-000003", Decimal("-0.01"), "USD"
        ),
        mr.LiabilityLayerRef(
            C1, "CONTRACT_LIABILITY:SF-ORD-10001/EV-000001", Decimal("0.00"), "USD"
        ),
        mr.LiabilityLayerRef(C2, "CONTRACT_LIABILITY:X/EV-000002", Decimal("1200"), "JPY"),
    )
    outcome = _run(mr.MonitorInputs(layers=layers))
    (finding,) = outcome.findings
    assert finding.code == "DQ_NEGATIVE_LIABILITY_LAYER"
    assert finding.severity is ExceptionSeverity.BLOCKING
    assert finding.dedupe_key.endswith(":CONTRACT_LIABILITY:SF-ORD-10001/EV-000003")
    assert "-0.01 USD" in finding.message


def test_recognition_after_pob_end() -> None:
    rows = (
        mr.RecognitionRef(C1, O1, date(2026, 8, 31), PERIOD_START, Decimal("100.00")),
        mr.RecognitionRef(C1, O1, date(2026, 8, 31), PERIOD_START, Decimal("0.00")),  # no activity
        mr.RecognitionRef(
            C1, O1, date(2026, 9, 1), PERIOD_START, Decimal("5.00")
        ),  # ends on day one
    )
    outcome = _run(mr.MonitorInputs(recognitions=rows))
    (finding,) = outcome.findings
    assert finding.code == "DQ_RECOGNITION_AFTER_POB_END"
    assert finding.severity is ExceptionSeverity.WARNING
    assert (
        finding.dedupe_key == f"DATA_QUALITY:DQ_RECOGNITION_AFTER_POB_END:{SCOPE}:{O1}:2026-09-01"
    )


@pytest.mark.parametrize(
    ("last_event", "active", "limit", "expected"),
    [
        (date(2026, 7, 1), True, None, 1),  # 91 days > 90
        (date(2026, 7, 2), True, None, 0),  # exactly 90
        (date(2026, 7, 1), False, None, 0),  # not active
        (None, True, None, 1),  # never any event
        (date(2026, 8, 1), True, 30, 1),
    ],
)
def test_inactive_contract(
    last_event: date | None, active: bool, limit: int | None, expected: int
) -> None:
    settings = None if limit is None else {mr.INACTIVE_CONTRACT_DAYS: limit}
    outcome = _run(
        mr.MonitorInputs(contracts=(mr.ContractActivityRef(C1, active, last_event),)),
        settings=settings,
    )
    assert len(outcome.findings) == expected
    if expected:
        assert outcome.findings[0].dedupe_key == f"DATA_QUALITY:DQ_INACTIVE_CONTRACT:{SCOPE}:{C1}"
        assert outcome.findings[0].severity is ExceptionSeverity.WARNING


def test_fx_rate_missing() -> None:
    rows = (
        mr.FxRequirementRef(C1, "EUR", "USD", PERIOD_END, False),
        mr.FxRequirementRef(C1, "USD", "USD", PERIOD_END, False),  # same currency: no rate needed
        mr.FxRequirementRef(C2, "GBP", "USD", PERIOD_END, True),
    )
    outcome = _run(mr.MonitorInputs(fx=rows))
    (finding,) = outcome.findings
    assert finding.code == "FX_RATE_MISSING"
    assert finding.severity is ExceptionSeverity.BLOCKING
    assert finding.dedupe_key == f"DATA_QUALITY:FX_RATE_MISSING:{SCOPE}:EUR:USD:2026-09-30"
    assert outcome.blocking == 1


def test_rerun_is_idempotent_and_sorted() -> None:
    inputs = mr.MonitorInputs(
        fx=(mr.FxRequirementRef(C1, "EUR", "USD", PERIOD_END, False),),
        invoices=(
            mr.SourceInvoiceRef("SFDC", "B", "1", R1),
            mr.SourceInvoiceRef("SFDC", "B", "1", R2),
            mr.SourceInvoiceRef("SFDC", "A", "1", R1),
            mr.SourceInvoiceRef("SFDC", "A", "1", R2),
        ),
        contracts=(mr.ContractActivityRef(C1, True, None),),
    )
    first, second = _run(inputs), _run(inputs)
    assert first == second
    assert first.dedupe_keys() == second.dedupe_keys() and len(first.dedupe_keys()) == 4
    assert [(f.code, f.subject) for f in first.findings] == [
        ("DQ_DUPLICATE_INVOICE", "SFDC:A:1"),
        ("DQ_DUPLICATE_INVOICE", "SFDC:B:1"),
        ("DQ_INACTIVE_CONTRACT", str(C1)),
        ("FX_RATE_MISSING", "EUR:USD:2026-09-30"),
    ]
    assert (first.blocking, first.warnings) == (3, 1)


def test_tenant_rule_overrides_severity() -> None:
    inputs = mr.MonitorInputs(contracts=(mr.ContractActivityRef(C1, True, None),))
    overridden = _run(inputs, overrides={"DQ_INACTIVE_CONTRACT": "ERROR"})
    assert overridden.findings[0].severity is ExceptionSeverity.BLOCKING
    assert overridden.blocking == 1
    assert mr.severity_of("DQ_DUPLICATE_INVOICE", {"DQ_DUPLICATE_INVOICE": "WARNING"}) == "WARNING"
    with pytest.raises(ValueError, match="INFO"):
        mr.severity_of("DQ_INACTIVE_CONTRACT", {"DQ_INACTIVE_CONTRACT": "INFO"})
    with pytest.raises(KeyError):
        mr.severity_of("DQ_UNKNOWN", {})


def test_e43_mapping() -> None:
    assert mr.exception_severity("ERROR") is ExceptionSeverity.BLOCKING
    assert mr.exception_severity("WARNING") is ExceptionSeverity.WARNING


def test_data_quality_gate() -> None:
    at = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    clear = mr.data_quality_gate(0, at=at)
    assert (clear.gate_check_code, clear.status, clear.count, clear.detail) == (
        gates.DATA_QUALITY_CLEAR,
        ChecklistStatus.PASSED,
        0,
        None,
    )
    failed = mr.data_quality_gate(3, at=at)
    assert (failed.status, failed.count, failed.detail, failed.evaluated_at) == (
        ChecklistStatus.FAILED,
        3,
        "Data-quality errors: 3",
        at,
    )
    with pytest.raises(ValueError):
        mr.data_quality_gate(-1, at=at)


# --- F-CLO-R3: T-PLT-31 ranges enforced locally (1-365 and 1-730 days) ---


@pytest.mark.parametrize(
    ("key", "value", "accepted"),
    [
        (mr.REVENUE_WITHOUT_BILLING_DAYS, 0, False),
        (mr.REVENUE_WITHOUT_BILLING_DAYS, 1, True),
        (mr.REVENUE_WITHOUT_BILLING_DAYS, 365, True),
        (mr.REVENUE_WITHOUT_BILLING_DAYS, 366, False),
        (mr.INACTIVE_CONTRACT_DAYS, 0, False),
        (mr.INACTIVE_CONTRACT_DAYS, 1, True),
        (mr.INACTIVE_CONTRACT_DAYS, 730, True),
        (mr.INACTIVE_CONTRACT_DAYS, 731, False),
    ],
)
def test_r3_threshold_settings_follow_t_plt_31_ranges(key: str, value: int, accepted: bool) -> None:
    assert mr.SETTING_RANGES == {
        mr.REVENUE_WITHOUT_BILLING_DAYS: (1, 365),
        mr.INACTIVE_CONTRACT_DAYS: (1, 730),
    }
    inputs = mr.MonitorInputs(contracts=(mr.ContractActivityRef(C1, True, None),))
    if accepted:
        assert _run(inputs, settings={key: value}).findings
    else:
        with pytest.raises(ValueError, match=key):
            _run(inputs, settings={key: value})
    with pytest.raises(ValueError):
        _run(inputs, settings={key: True})


# --- CLO-5 producer needs: one finding per dedupe subject; contract-level unbilled revenue ---


def test_one_finding_per_subject_across_contracts() -> None:
    # Two EUR contracts of a USD entity share one missing closing rate: one item, one dedupe key.
    rows = (
        mr.FxRequirementRef(C1, "EUR", "USD", PERIOD_END, False),
        mr.FxRequirementRef(C2, "EUR", "USD", PERIOD_END, False),
    )
    outcome = _run(mr.MonitorInputs(fx=rows))
    assert len(outcome.findings) == 1
    assert outcome.findings[0].contract_id == C1  # the first contract supplied names the item
    assert outcome.dedupe_keys() == {f"DATA_QUALITY:FX_RATE_MISSING:{SCOPE}:EUR:USD:2026-09-30"}


def test_unbilled_revenue_at_contract_level() -> None:
    # Subledger revenue lines without an obligation (contract-level) are monitored per contract.
    ref = mr.UnbilledRevenueRef(C1, None, date(2026, 7, 31), None)
    outcome = _run(mr.MonitorInputs(unbilled=(ref,)))
    (finding,) = outcome.findings
    assert finding.dedupe_key == f"DATA_QUALITY:DQ_REVENUE_WITHOUT_BILLING:{SCOPE}:{C1}"
    assert (finding.contract_id, finding.obligation_id) == (C1, None)


# --- D-98 57 (Codex CLO-5 review R1): the finding identity carries its affected scope ---

E_A = UUID("00000000-0000-0000-0000-0000000000e1")
E_B = UUID("00000000-0000-0000-0000-0000000000e2")
P_AUG = UUID("00000000-0000-0000-0000-00000000aa08")
P_SEP = UUID("00000000-0000-0000-0000-00000000aa09")


def _scoped(inputs: mr.MonitorInputs, entity: UUID, period: UUID) -> mr.MonitorOutcome:
    return mr.evaluate(
        inputs, period_start=PERIOD_START, period_end=PERIOD_END, entity_id=entity, period_id=period
    )


def test_dedupe_key_carries_entity_and_period() -> None:
    same = dict(
        customer_ref="CUST-7",
        invoice_number="A-1001",
        amount=Decimal("1200.00"),
        issue_date=date(2026, 8, 3),
    )
    inputs = mr.MonitorInputs(
        invoices=(
            mr.SourceInvoiceRef("SFDC", "EXT-1", "1", R1, **same),  # type: ignore[arg-type]
            mr.SourceInvoiceRef("SFDC", "EXT-2", "1", R2, **same),  # type: ignore[arg-type]
        )
    )
    august = _scoped(inputs, E_A, P_AUG).findings[0]
    september = _scoped(inputs, E_A, P_SEP).findings[0]
    assert august.subject == september.subject  # the same unresolved duplicate
    assert august.dedupe_key != september.dedupe_key  # a recurrence in September is its own item
    assert august.dedupe_key == (
        f"DATA_QUALITY:DQ_DUPLICATE_INVOICE:{E_A}:{P_AUG}:CUST-7:A-1001:1200.00:2026-08-03"
    )
    assert (september.entity_id, september.period_id) == (E_A, P_SEP)


def test_fx_subject_gains_the_entity() -> None:
    need = mr.FxRequirementRef(C1, "EUR", "USD", PERIOD_END, False)
    first = _scoped(mr.MonitorInputs(fx=(need,)), E_A, P_SEP).findings[0]
    second = _scoped(mr.MonitorInputs(fx=(need,)), E_B, P_SEP).findings[0]
    assert first.subject == second.subject == "EUR:USD:2026-09-30"
    assert first.dedupe_key != second.dedupe_key
    assert first.dedupe_key == f"DATA_QUALITY:FX_RATE_MISSING:{E_A}:{P_SEP}:EUR:USD:2026-09-30"


def test_same_scope_keeps_one_identity() -> None:
    # Positive control: the same finding in the same scope keeps the same key (same open item).
    inputs = mr.MonitorInputs(contracts=(mr.ContractActivityRef(C1, True, None),))
    assert _scoped(inputs, E_A, P_SEP).dedupe_keys() == _scoped(inputs, E_A, P_SEP).dedupe_keys()


def test_evaluate_requires_the_scope() -> None:
    with pytest.raises(TypeError):
        mr.evaluate(mr.MonitorInputs(), period_start=PERIOD_START, period_end=PERIOD_END)  # type: ignore[call-arg]


# --- SCH10-PERIOD-SCOPE-1 (Codex production-20260922-0505 §1 as corrected by 0511 / 0522; the
# supervisor's 2026-09-22 ruling; P1 record §4.30): a duplicate is never attributed to a period that
# ends before its earliest dated participating invoice --------------------------------------------

P_OCT = UUID("00000000-0000-0000-0000-00000000aa10")


def _bounded(inputs: mr.MonitorInputs, start: date, end: date, period: UUID) -> mr.MonitorOutcome:
    return mr.evaluate(inputs, period_start=start, period_end=end, entity_id=E_A, period_id=period)


def _september_identity_duplicate() -> mr.MonitorInputs:
    same = dict(
        customer_ref="CUST-7",
        invoice_number="A-1001",
        amount=Decimal("1200.00"),
        issue_date=date(2026, 9, 3),
    )
    return mr.MonitorInputs(
        invoices=(
            mr.SourceInvoiceRef("SFDC", "EXT-1", "1", R1, **same),  # type: ignore[arg-type]
            mr.SourceInvoiceRef("SFDC", "EXT-2", "1", R2, **same),  # type: ignore[arg-type]
        )
    )


def test_a_september_duplicate_is_not_an_earlier_periods_finding() -> None:
    inputs = _september_identity_duplicate()
    august = _bounded(inputs, date(2026, 8, 1), date(2026, 8, 31), P_AUG)
    assert august.findings == ()  # data of September never blocks August
    september = _bounded(inputs, PERIOD_START, PERIOD_END, P_SEP)
    assert [f.code for f in september.findings] == ["DQ_DUPLICATE_INVOICE"]
    assert september.findings[0].period_id == P_SEP
    october = _bounded(inputs, date(2026, 10, 1), date(2026, 10, 31), P_OCT)  # D-98 57 recurrence
    assert [f.period_id for f in october.findings] == [P_OCT]


P_JUL = UUID("00000000-0000-0000-0000-00000000aa07")
P_JUN = UUID("00000000-0000-0000-0000-00000000aa06")
P_MAY = UUID("00000000-0000-0000-0000-00000000aa05")


def _key_duplicate(*dates: date) -> mr.MonitorInputs:
    rows = tuple(
        mr.SourceInvoiceRef("SFDC", "INV-1", "1", UUID(int=100 + i), issue_date=issued)
        for i, issued in enumerate(dates)
    )
    return mr.MonitorInputs(invoices=rows)


def _found(inputs: mr.MonitorInputs, month: int, period: UUID) -> bool:
    start = date(2026, month, 1)
    end = date(2026, month + 1, 1) - date.resolution
    return [f.code for f in _bounded(inputs, start, end, period).findings] == [
        "DQ_DUPLICATE_INVOICE"
    ]


def test_a_key_duplicate_across_months_concerns_its_earliest_dated_row_onward() -> None:
    """Supervisor ruling 2026-09-22 (preventive gate, REQ-CLS-019): an open August whose own
    invoice takes part in an August + September duplicate is gated; July is not."""
    aug_sep = _key_duplicate(date(2026, 8, 3), date(2026, 9, 3))
    assert not _found(aug_sep, 7, P_JUL)
    assert _found(aug_sep, 8, P_AUG) and _found(aug_sep, 9, P_SEP)
    jun_sep = _key_duplicate(date(2026, 6, 3), date(2026, 9, 3))
    assert not _found(jun_sep, 5, P_MAY)
    assert all(
        _found(jun_sep, month, period)
        for month, period in ((6, P_JUN), (7, P_JUL), (8, P_AUG), (9, P_SEP))
    )


def test_identity_boundaries_never_form_a_rule_1_group_under_any_bounds() -> None:
    """Codex 0530 boundary controls: a different external version or source system is another
    group; the same row id repeated is not a duplicate — nothing is raised whatever the period."""
    boundary = mr.MonitorInputs(
        invoices=(
            mr.SourceInvoiceRef("SFDC", "INV-9", "1", R1, issue_date=date(2026, 8, 3)),
            mr.SourceInvoiceRef(
                "SFDC", "INV-9", "2", R2, issue_date=date(2026, 9, 3)
            ),  # later version
            mr.SourceInvoiceRef(
                "STRIPE", "INV-9", "1", UUID(int=7), issue_date=date(2026, 9, 3)
            ),  # other system
            mr.SourceInvoiceRef("SFDC", "INV-8", "1", R1, issue_date=date(2026, 8, 3)),
            mr.SourceInvoiceRef(
                "SFDC", "INV-8", "1", R1, issue_date=date(2026, 9, 3)
            ),  # same row id twice
        )
    )
    for month, period in ((7, P_JUL), (8, P_AUG), (9, P_SEP)):
        assert (
            _bounded(
                boundary, date(2026, month, 1), date(2026, month + 1, 1) - date.resolution, period
            ).findings
            == ()
        )


def test_a_partly_dated_key_duplicate_uses_its_earliest_dated_row() -> None:
    mixed = mr.MonitorInputs(
        invoices=(
            mr.SourceInvoiceRef("SFDC", "INV-1", "1", R1),  # undated row: ignored for attribution
            mr.SourceInvoiceRef("SFDC", "INV-1", "1", R2, issue_date=date(2026, 8, 3)),
        )
    )
    assert not _found(mixed, 7, P_JUL) and _found(mixed, 8, P_AUG) and _found(mixed, 9, P_SEP)


def test_a_wholly_undated_key_duplicate_still_surfaces_in_every_period() -> None:
    """The stated limitation (supervisor ruling point 3): no date → no attribution → every
    evaluated period, as before; pinned so a later ruling changes it deliberately."""
    inputs = mr.MonitorInputs(
        invoices=(
            mr.SourceInvoiceRef("SFDC", "INV-2", "1", R1),
            mr.SourceInvoiceRef("SFDC", "INV-2", "1", R2),
        )
    )
    for start, end, period in (
        (date(2026, 8, 1), date(2026, 8, 31), P_AUG),
        (PERIOD_START, PERIOD_END, P_SEP),
    ):
        assert [f.code for f in _bounded(inputs, start, end, period).findings] == [
            "DQ_DUPLICATE_INVOICE"
        ]
