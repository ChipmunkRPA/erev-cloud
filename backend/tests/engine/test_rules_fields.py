"""Rule fields of the approval kinds are additive (BUILD_SPEC BS1-D-05, PLF-12, BS4-D-09, CLO-17;
04 T-REF-26)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from erev_engine.enums import RuleSetKind
from erev_engine.rules import FIELDS, match, validate_conditions


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_key: str
    priority: int
    specificity: int
    conditions: Sequence[Mapping[str, object]]
    outputs: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _RuleSet:
    kind: str
    rules: Sequence[_Rule]


# 04 T-REF-26 `conditions`: the POB_ASSIGNMENT fields.
POB_ASSIGNMENT_FIELDS = (
    "product.code",
    "product.product_family",
    "bundle_parent.code",
    "contract.region",
    "contract.channel",
    "customer.segment",
    "contract.contract_type",
    "line.term_band",
    "contract.currency",
    "effective_date",
)
# BS1-D-05: the AUTO_APPROVAL fields of PLF-12, in their order.
AUTO_APPROVAL_FIELDS = (
    "subject.type",
    "preparer.role_codes",
    "tenant.setup_completed",
    "source.channel",
)
# BS4-D-09: the facts of an auto-certification rule (04 T-REF-26 `conditions`).
RECONCILIATION_FIELDS = (
    "reconciliation.kind",
    "reconciliation.variance_count",
    "reconciliation.unexplained_other_amount",
)


def test_bs1_d_05_fields_are_additive() -> None:
    assert FIELDS["POB_ASSIGNMENT"] == POB_ASSIGNMENT_FIELDS
    assert FIELDS["APPROVAL_ROUTING"] == (
        "subject.type",
        "entity.code",
        "amount.functional",
        "flags",
    )
    # CLO-17 extended AUTO_APPROVAL additively (BS4-D-09): the PLF-12 fields lead, unchanged.
    assert FIELDS["AUTO_APPROVAL"] == AUTO_APPROVAL_FIELDS + RECONCILIATION_FIELDS
    # The existing kinds keep their entries: SSP book selection and the user hold rules of CTR-10
    # read the line facts, and the kinds later items build take no condition yet.
    assert FIELDS["SSP_ASSIGNMENT"] == POB_ASSIGNMENT_FIELDS
    assert FIELDS["HOLD"] == POB_ASSIGNMENT_FIELDS
    others = set(RuleSetKind) - {
        "POB_ASSIGNMENT",
        "SSP_ASSIGNMENT",
        "APPROVAL_ROUTING",
        "AUTO_APPROVAL",
        "HOLD",
    }
    assert {kind: FIELDS[kind] for kind in others} == {kind: () for kind in others}


def test_auto_approval_reconciliation_fields() -> None:
    """BUILD_SPEC CLO-17 (BS4-D-09): ``FIELDS["AUTO_APPROVAL"]`` contains the three reconciliation
    fields and every earlier field unchanged."""
    fields = FIELDS["AUTO_APPROVAL"]
    assert fields[: len(AUTO_APPROVAL_FIELDS)] == AUTO_APPROVAL_FIELDS
    assert fields[len(AUTO_APPROVAL_FIELDS) :] == RECONCILIATION_FIELDS
    assert len(set(fields)) == len(fields)
    # No other kind took a reconciliation field, and every other kind is as it was.
    assert FIELDS["POB_ASSIGNMENT"] == POB_ASSIGNMENT_FIELDS
    assert FIELDS["SSP_ASSIGNMENT"] == POB_ASSIGNMENT_FIELDS
    assert FIELDS["HOLD"] == POB_ASSIGNMENT_FIELDS
    assert FIELDS["APPROVAL_ROUTING"] == (
        "subject.type",
        "entity.code",
        "amount.functional",
        "flags",
    )
    assert FIELDS["COMBINATION_DETECTION"] == ()
    assert FIELDS["DATA_QUALITY"] == ()
    # An auto-certification rule validates, and matches the facts of a clean reconciliation only.
    conditions = [
        {"field": "reconciliation.kind", "op": "eq", "value": "BILLING_TO_SUBLEDGER"},
        {"field": "reconciliation.variance_count", "op": "eq", "value": 0},
    ]
    assert validate_conditions("AUTO_APPROVAL", conditions) == 2
    rule_set = _RuleSet(
        kind="AUTO_APPROVAL",
        rules=(
            _Rule(
                rule_key="AUTO-REC-01",
                priority=0,
                specificity=2,
                conditions=conditions,
                outputs={"auto_approve": True},
            ),
        ),
    )
    clean = {"reconciliation.kind": "BILLING_TO_SUBLEDGER", "reconciliation.variance_count": 0}
    found = match(rule_set, clean)
    assert found is not None and (found.rule_key, found.outputs) == (
        "AUTO-REC-01",
        {"auto_approve": True},
    )
    assert match(rule_set, {**clean, "reconciliation.variance_count": 1}) is None
    assert match(rule_set, {**clean, "reconciliation.kind": "SUBLEDGER_TO_GL"}) is None
    # The facts of an approval request name no reconciliation, so the rule never matches them.
    assert match(rule_set, {"subject.type": "IMPORT_COMMIT", "source.channel": "API"}) is None
    amount = [{"field": "reconciliation.unexplained_other_amount", "op": "lte", "value": "0.00"}]
    assert validate_conditions("AUTO_APPROVAL", amount) == 1
