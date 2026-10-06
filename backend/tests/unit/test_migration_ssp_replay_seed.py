"""The ``AUTO-MIG-01`` provisioning seed (04 §14.3 rev 1.72; 02-PRD §2.5 rev 1.15; D-98 133
AMENDMENT 4 option A2):
pure — the row builder only, the CLO-5 ``DQ-SYSTEM`` pattern. The provisioned rule approves a
``MIGRATION_SSP_REPLAY``
request submitted by a user at submission; the database-bound witness (a fresh tenant's ``/import``
auto-approved) is
``tests/pg/test_migration_capture_pg.py`` (WRITTEN, NOT RUN on the lane)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from erev_api.domain.platform import provisioning
from erev_api.domain.policies import rule_sets
from erev_api.enums import ApprovalSubjectType, ConfigStatus, RuleSetKind
from erev_engine.canonical import sha256_hex

TENANT = UUID(int=0x7E)
ACTOR = UUID(int=0xA0)
NOW = datetime(2026, 9, 22, 0, 0, tzinfo=UTC)
STAMP = {
    "created_at": NOW,
    "created_by": ACTOR,
    "created_by_kind": "OPERATOR",
    "updated_at": NOW,
    "updated_by": ACTOR,
    "updated_by_kind": "OPERATOR",
}


def test_auto_mig_01_rows_follow_04_14_3() -> None:
    set_row, version_row, rule_row = provisioning.auto_migration_rows(
        TENANT, stamp=STAMP, published_at=NOW
    )
    assert (set_row["code"], set_row["kind"], set_row["name"]) == (
        provisioning.AUTO_MIGRATION,
        RuleSetKind.AUTO_APPROVAL.value,
        "Legacy SSP replay",
    )
    assert set_row["tenant_id"] == TENANT and set_row["created_by"] == ACTOR
    assert (version_row["rule_set_id"], version_row["version_no"], version_row["status"]) == (
        set_row["id"],
        1,
        ConfigStatus.PUBLISHED.value,
    )
    assert (version_row["published_at"], version_row["published_by"]) == (NOW, ACTOR)
    assert (version_row["effective_from"], version_row["effective_to"]) == (None, None)
    assert rule_row["rule_set_version_id"] == version_row["id"]
    assert rule_row["rule_key"] == "AUTO-MIG-01" and rule_row["priority"] == 0
    # the two rule facts of the ruling; the content conditions are enforced by /import before
    # submission
    assert rule_row["conditions"] == [
        {
            "field": "subject.type",
            "op": "eq",
            "value": ApprovalSubjectType.MIGRATION_SSP_REPLAY.value,
        },
        {"field": "source.channel", "op": "eq", "value": "USER"},
    ]
    assert rule_row["outputs"] == {"auto_approve": True}
    assert rule_sets.output_errors(RuleSetKind.AUTO_APPROVAL, rule_row["outputs"]) == []
    assert rule_row["specificity"] == provisioning.validate_conditions(
        RuleSetKind.AUTO_APPROVAL.value, rule_row["conditions"]
    )


def test_auto_mig_01_content_hash_covers_kind_and_rule() -> None:
    _, version_row, rule_row = provisioning.auto_migration_rows(
        TENANT, stamp=STAMP, published_at=NOW
    )
    content = {
        "kind": RuleSetKind.AUTO_APPROVAL.value,
        "rules": [
            {key: rule_row[key] for key in ("rule_key", "priority", "specificity", "conditions")}
            | {"outputs": rule_row["outputs"]}
        ],
    }
    assert version_row["content_sha256"] == sha256_hex(content)
    again = provisioning.auto_migration_rows(TENANT, stamp=STAMP, published_at=NOW)
    assert again[1]["content_sha256"] == version_row["content_sha256"]


def test_auto_mig_01_is_distinct_from_the_other_seeded_sets() -> None:
    assert provisioning.AUTO_MIGRATION == "AUTO-MIG-01"
    assert provisioning.AUTO_MIGRATION not in (provisioning.AUTO_BOOTSTRAP, provisioning.DQ_SYSTEM)
