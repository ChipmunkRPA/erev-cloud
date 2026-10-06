"""D-87 L6-5-Q-16 (ENC-6): S01-R-17 over-delivery does not apply to a ``RIGHT_TO_INVOICE`` line.

A time-and-materials line is booked with quantity 1 as a rate line (POS-CHK-010, REC-CHK-014:
120 hours delivered against a booked quantity of 1, unit price 25.00) — stage 01 raises no
``PROGRESS_OVER_DELIVERY`` for it, while a genuine unit over-delivery on a ``UNITS_DELIVERED``
obligation still fires (the control). Bundles come from ``support.bundles`` (DG-ENG-11); no
database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import date

from erev_engine.bundle import ResolvedPolicyInput, RuleSetInput, TemplateInput
from test_s01_rules import POB_1, booking, bundle, delivery, run

ZERO_SHA = "0" * 64


def _template(code: str, method: str) -> TemplateInput:
    over_time = method != "UNITS_DELIVERED"
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO_SHA,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern="OVER_TIME" if over_time else "POINT_IN_TIME",
        over_time_criterion="OT_A" if over_time else "NOT_APPLICABLE",
        recognition_method=method,
        ratable_convention=None,
        start_date_rule="LINE_START",
        end_date_rule="LINE_END",
        term_months=None,
        principal_agent="PRINCIPAL",
        warranty_type="NONE",
        licence_nature="NOT_APPLICABLE",
        sfc_assessment_required=False,
        revenue_category=None,
        disaggregation={},
        account_role_overrides={},
        stratification_label=None,
        is_excluded_from_netting_attribution=False,
        policy_values={},
        effective_from=date(2020, 1, 1),
        effective_to=None,
    )


def _with_template(method: str):  # noqa: ANN202 - InputBundle of the test_s01_rules world
    # The three products of the world share the default template TPL-RATABLE (support.bundles
    # ``product``); its method decides whether the exemption applies.
    events = (
        booking(),
        delivery(2, date(2023, 1, 10), "POB #1", "3"),
        delivery(3, date(2023, 1, 20), "POB #1", "3"),
    )
    return dataclasses.replace(
        bundle(*events), pob_template_versions=(_template("TPL-RATABLE", method),)
    )


def test_d87_right_to_invoice_lines_are_exempt_from_over_delivery() -> None:
    # POB #1 is booked with quantity 5 and receives 6 units: a rate line under RIGHT_TO_INVOICE, so
    # S01-R-17 does not apply (D-87 L6-5-Q-16) and the ledger still records the deliveries.
    cb, nodes = run(_with_template("RIGHT_TO_INVOICE"))
    assert [f.code for f in cb.findings] == []
    assert nodes[f"delivered_quantity_cum:{POB_1}:-"].value == "6"


def test_s01_r17_units_over_delivery_still_fires_as_the_control() -> None:
    cb, _ = run(_with_template("UNITS_DELIVERED"))
    assert [(f.code, f.severity, f.subject_key) for f in cb.findings] == [
        ("PROGRESS_OVER_DELIVERY", "ERROR", POB_1)
    ]
    assert cb.findings[0].detail["booked"] == "5" and cb.findings[0].detail["delivered"] == "6"


def test_exemption_withheld_while_a_pob_assignment_rule_set_is_in_force() -> None:
    # The resolution is not unambiguous before stage 03 when a POB_ASSIGNMENT rule set could route
    # the line to another template: the exemption is withheld and S01-R-17 fires as today (fail
    # closed, visible).
    rule_set = RuleSetInput(
        rule_set_code="RS-ASSIGN",
        kind="POB_ASSIGNMENT",
        version_key="RS-ASSIGN@v1",
        version_no=1,
        content_sha256=ZERO_SHA,
        effective_from=date(2020, 1, 1),
        effective_to=None,
        rules=(),
    )
    value = dataclasses.replace(_with_template("RIGHT_TO_INVOICE"), rule_set_versions=(rule_set,))
    cb, _ = run(value)
    assert [f.code for f in cb.findings] == ["PROGRESS_OVER_DELIVERY"]


def test_exemption_reads_the_template_version_effective_at_inception() -> None:
    # A RIGHT_TO_INVOICE version that is no longer effective at the contract inception does not
    # exempt the line; the version in force (UNITS_DELIVERED) governs.
    retired = dataclasses.replace(
        _template("TPL-RATABLE", "RIGHT_TO_INVOICE"), effective_to=date(2022, 1, 1)
    )
    current = dataclasses.replace(
        _template("TPL-RATABLE", "UNITS_DELIVERED"),
        version_key="TPL-RATABLE@v2",
        version_no=2,
        effective_from=date(2022, 1, 1),
    )
    value = dataclasses.replace(
        _with_template("RIGHT_TO_INVOICE"), pob_template_versions=(retired, current)
    )
    cb, _ = run(value)
    assert [f.code for f in cb.findings] == ["PROGRESS_OVER_DELIVERY"]


def _with_override(method: str, value: str):  # noqa: ANN202 - InputBundle of the test_s01_rules world
    """The world with a level-O POL-091 ``recognition.measure_of_progress`` pin on POB #1."""
    value_bundle = _with_template(method)
    pin = ResolvedPolicyInput(
        "recognition.measure_of_progress", "OBLIGATION", POB_1, value, "O", "OVR-TEST", "K"
    )
    book = value_bundle.books[0]
    policies = tuple(
        sorted((*book.policies, pin), key=lambda item: (item.code, item.scope, item.subject_key))
    )
    return dataclasses.replace(value_bundle, books=(dataclasses.replace(book, policies=policies),))


def test_enc6_r2_override_away_from_rti_withholds_the_exemption() -> None:
    # ENC6-R2: the default template is RIGHT_TO_INVOICE but the book's level-O override makes the
    # obligation UNITS_DELIVERED at stage 03 — the effective method decides, so S01-R-17 fires.
    cb, _ = run(_with_override("RIGHT_TO_INVOICE", "UNITS_DELIVERED"))
    assert [(f.code, f.subject_key) for f in cb.findings] == [("PROGRESS_OVER_DELIVERY", POB_1)]


def test_enc6_r2_override_to_rti_never_grants_the_exemption() -> None:
    # A UNITS_DELIVERED template overridden TO RIGHT_TO_INVOICE keeps the refusal: the template
    # version decides the exemption, an override only ever withholds it (fail closed).
    cb, _ = run(_with_override("UNITS_DELIVERED", "RIGHT_TO_INVOICE"))
    assert [f.code for f in cb.findings] == ["PROGRESS_OVER_DELIVERY"]


def test_enc6_r2_override_to_rti_on_an_rti_template_keeps_the_exemption() -> None:
    cb, _ = run(_with_override("RIGHT_TO_INVOICE", "RIGHT_TO_INVOICE"))
    assert [f.code for f in cb.findings] == []


def test_exemption_withheld_under_the_parity_preset() -> None:
    # S03-R-18 parity templates never use the method: nothing is exempted under LEGACY_PARITY.
    cb, _ = run(
        dataclasses.replace(_with_template("RIGHT_TO_INVOICE"), tenant_preset="LEGACY_PARITY")
    )
    assert [f.code for f in cb.findings] == ["PROGRESS_OVER_DELIVERY"]


def test_exemption_withheld_for_a_future_effective_rti_template() -> None:
    # No version is effective at the inception when the RTI template starts later.
    future = dataclasses.replace(
        _template("TPL-RATABLE", "RIGHT_TO_INVOICE"), effective_from=date(2024, 1, 1)
    )
    cb, _ = run(
        dataclasses.replace(_with_template("RIGHT_TO_INVOICE"), pob_template_versions=(future,))
    )
    assert [f.code for f in cb.findings] == ["PROGRESS_OVER_DELIVERY"]
