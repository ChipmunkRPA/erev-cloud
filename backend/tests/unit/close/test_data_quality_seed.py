"""The ``DQ-SYSTEM`` provisioning seed (04 §14.3 rev 1.21; BUILD_SPEC CLO-5 Paths
``provisioning.py``; supervisor ruling Q-4 of ``docs/reviews/loop/prod/F-CLO-prep.md``): one
``DATA_QUALITY`` rule set, version 1 PUBLISHED, one rule per table 15.4-E monitor keyed by its code.
Pure: the row builder only. Fail-first on ``4141f322``: ``data_quality_rows`` does not exist."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from erev_api.domain.close import monitor_rules
from erev_api.domain.platform import provisioning
from erev_api.domain.policies import rule_sets
from erev_api.enums import ConfigStatus, RuleSetKind
from erev_engine.canonical import sha256_hex

TENANT = UUID("00000000-0000-0000-0000-00000000f001")
ACTOR = UUID("00000000-0000-0000-0000-00000000a001")
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
STAMP = {
    "created_at": NOW,
    "created_by": ACTOR,
    "created_by_kind": "OPERATOR",
    "updated_at": NOW,
    "updated_by": ACTOR,
    "updated_by_kind": "OPERATOR",
}


def test_dq_system_rows_follow_04_14_3() -> None:
    set_row, version_row, rules = provisioning.data_quality_rows(
        TENANT, stamp=STAMP, published_at=NOW
    )
    assert (set_row["code"], set_row["kind"], set_row["name"]) == (
        provisioning.DQ_SYSTEM,
        RuleSetKind.DATA_QUALITY.value,
        "Data-quality monitors",
    )
    assert set_row["tenant_id"] == TENANT and set_row["created_by"] == ACTOR
    assert (version_row["rule_set_id"], version_row["version_no"], version_row["status"]) == (
        set_row["id"],
        1,
        ConfigStatus.PUBLISHED.value,
    )
    assert (version_row["published_at"], version_row["published_by"]) == (NOW, ACTOR)
    assert (version_row["effective_from"], version_row["effective_to"]) == (None, None)
    assert [rule["rule_key"] for rule in rules] == [m.code for m in monitor_rules.MONITORS]
    for rule, spec in zip(rules, monitor_rules.MONITORS, strict=True):
        assert rule["rule_set_version_id"] == version_row["id"]
        assert rule["conditions"] == [] and rule["specificity"] == 0 and rule["priority"] == 0
        assert rule["outputs"] == {"severity": spec.default_severity, "message": spec.description}
        assert rule_sets.output_errors(RuleSetKind.DATA_QUALITY, rule["outputs"]) == []


def test_dq_system_content_hash_covers_kind_and_rules() -> None:
    _, version_row, rules = provisioning.data_quality_rows(TENANT, stamp=STAMP, published_at=NOW)
    content = {
        "kind": RuleSetKind.DATA_QUALITY.value,
        "rules": [
            {key: rule[key] for key in ("rule_key", "priority", "specificity", "conditions")}
            | {"outputs": rule["outputs"]}
            for rule in rules
        ],
    }
    assert version_row["content_sha256"] == sha256_hex(content)
    again = provisioning.data_quality_rows(TENANT, stamp=STAMP, published_at=NOW)
    assert again[1]["content_sha256"] == version_row["content_sha256"]


def test_dq_system_is_named_in_the_seed_order() -> None:
    assert provisioning.DQ_SYSTEM == "DQ-SYSTEM"
    assert provisioning.DQ_SYSTEM != provisioning.AUTO_BOOTSTRAP
