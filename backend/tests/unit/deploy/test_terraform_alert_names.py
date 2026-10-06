"""The alert policies whose source is the application name what the application emits (item
DEPLOY-ALERT-NAMES-1; 05 DPL-37 rev 1.162, §7.5 SLO-04 to SLO-06; dev-guide DG-KRN-EVT-05 rev
1.206; item JOB-FAILED-ITEM-1, DPL-37 rev 1.165: the policy on a failed job; item
FILE-SHRED-DURABLE-ORDER-1, DPL-37 rev 1.171: the policy on a shred decided and not completed).

Five policies of ``deploy/terraform/gcp/main.tf`` read a variable each: a metric type (SLO-04)
and four log filters (SLO-05, SLO-06, a failed job, a shred that is not completed).
``terraform validate`` checks that a filter
is a string and nothing of what it names, so a default that names an event nobody logs builds a
policy that never fires. Here each default is read against the code: a live default names only
what a module under
``backend/erev_api`` emits, and an inert one says so in its description and names something that
does not exist yet - when its source arrives, this test fails until the sentence goes.
"""

from __future__ import annotations

import re
from pathlib import Path

from erev_api.controls import metrics
from erev_api.controls.operator_alerts import SEVERITY, OperatorAlertKind
from erev_api.enums import OutboxStatus
from erev_api.events import outbox
from support.terraform import ROOT, resource, unquote, variables

APPLICATION = ROOT / "backend" / "erev_api"
INERT = "Inert until "
EVENT = re.compile(r'jsonPayload\.event="([a-z_.]+)"')
MEMBER = re.compile(r'jsonPayload\.([a-z_]+)="([A-Z_]+)"')
# The variable each alert policy reads, and whether the application feeds it today.
SOURCES = {
    "slo_04_job_pickup": ("job_pickup_latency_metric_type", False),
    "slo_05_outbox_dead": ("outbox_dead_log_filter", True),
    "slo_06_audit_chain": ("audit_chain_failure_log_filter", True),
    "ops_job_failed": ("job_failed_log_filter", True),
    "ops_file_shred_incomplete": ("file_shred_incomplete_log_filter", True),
}


def _value(name: str, attribute: str) -> str:
    raw = unquote(variables()[name].attribute(attribute))
    assert raw is not None, (name, attribute)
    return raw.replace('\\"', '"')


def _logged(event: str) -> list[Path]:
    """The modules of the application that hold ``event`` as a string literal."""
    return [path for path in APPLICATION.rglob("*.py") if f'"{event}"' in path.read_text("utf-8")]


def test_deploy_alert_names_1_each_policy_reads_its_variable() -> None:
    for policy, (variable, _) in SOURCES.items():
        body = resource("google_monitoring_alert_policy", policy).body
        assert f"var.{variable}" in body, policy
    assert sorted(variable for variable, _ in SOURCES.values()) == sorted(
        name for name in variables() if name.endswith(("_log_filter", "_metric_type"))
    )


def test_deploy_alert_names_1_a_live_filter_names_what_the_application_logs() -> None:
    live = {variable for variable, fed in SOURCES.values() if fed}
    assert live == {
        "outbox_dead_log_filter",
        "audit_chain_failure_log_filter",
        "job_failed_log_filter",
        "file_shred_incomplete_log_filter",
    }
    for variable in live:
        default = _value(variable, "default")
        assert not _value(variable, "description").startswith(INERT), variable
        events = EVENT.findall(default)
        assert len(events) == 1, (variable, default)
        assert _logged(events[0]), f"{variable}: no module logs {events[0]}"

    # SLO-05: the relay's line, for a message it recorded DEAD (and for no other outcome).
    dead = _value("outbox_dead_log_filter", "default")
    assert dead == 'jsonPayload.event="outbox.dispatch_failed" AND jsonPayload.outcome="DEAD"'
    assert _logged("outbox.dispatch_failed") == [APPLICATION / "events" / "outbox.py"]
    assert MEMBER.findall(dead) == [("outcome", OutboxStatus.DEAD.value)]
    assert outbox.UNSETTLED not in {status.value for status in OutboxStatus}

    # SLO-06: the operator alert of either chain, by its kind; both kinds page (SEV-1).
    chain = _value("audit_chain_failure_log_filter", "default")
    assert EVENT.findall(chain) == ["operator_alert.raised"]
    kinds = [OperatorAlertKind(value) for name, value in MEMBER.findall(chain) if name == "kind"]
    assert kinds == [
        OperatorAlertKind.AUDIT_CHAIN_VERIFICATION_FAILED,
        OperatorAlertKind.SECURITY_CHAIN_VERIFICATION_FAILED,
    ]
    assert all(SEVERITY[kind] == "SEV-1" for kind in kinds)
    # Every kind of a chain verification is in the filter; an alert kind of another matter is not.
    assert {kind for kind in OperatorAlertKind if "CHAIN_VERIFICATION" in kind.value} == set(kinds)
    assert " AND (" in chain and chain.endswith(")")  # the two kinds are one alternative

    # A failed job that no user started: the operator alert of its own kind, a warning - the
    # chain filter above does not match it, and this one matches no chain failure.
    failed = _value("job_failed_log_filter", "default")
    assert failed == 'jsonPayload.event="operator_alert.raised" AND jsonPayload.kind="JOB_FAILED"'
    assert MEMBER.findall(failed) == [("kind", OperatorAlertKind.JOB_FAILED.value)]
    assert SEVERITY[OperatorAlertKind.JOB_FAILED] == "WARNING"
    policy = resource("google_monitoring_alert_policy", "ops_job_failed")
    assert unquote(policy.attribute("severity")) == "WARNING"
    assert "RB-07" in policy.body
    # A shred decided and not completed 60 minutes later (05 PRV-07 b, SCH-16): the operator
    # alert of its own kind, a warning under RB-14 - every reader of the workspace refuses the
    # file by its row already - which neither filter above matches.
    owed = _value("file_shred_incomplete_log_filter", "default")
    assert owed == (
        'jsonPayload.event="operator_alert.raised" AND jsonPayload.kind="FILE_SHRED_INCOMPLETE"'
    )
    assert MEMBER.findall(owed) == [("kind", OperatorAlertKind.FILE_SHRED_INCOMPLETE.value)]
    assert SEVERITY[OperatorAlertKind.FILE_SHRED_INCOMPLETE] == "WARNING"
    policy = resource("google_monitoring_alert_policy", "ops_file_shred_incomplete")
    assert unquote(policy.attribute("severity")) == "WARNING"
    assert "RB-14" in policy.body
    # Every alert kind the application raises is read by a policy or is the partition warning,
    # which no hosted policy reads (05 OPR-24: the log and the operator address carry it).
    read = (
        {kind.value for kind in kinds}
        | {value for _, value in MEMBER.findall(failed)}
        | {value for _, value in MEMBER.findall(owed)}
    )
    assert {kind.value for kind in OperatorAlertKind} - read == {
        OperatorAlertKind.PARTITION_WINDOW_NEAR_END.value
    }


def test_deploy_alert_names_1_an_inert_source_says_so_and_names_nothing_that_exists() -> None:
    inert = {variable for variable, fed in SOURCES.values() if not fed}
    assert inert == {"job_pickup_latency_metric_type"}
    description = _value("job_pickup_latency_metric_type", "description")
    assert description.startswith(INERT), description
    metric_type = _value("job_pickup_latency_metric_type", "default")
    name = metric_type.rsplit("/", 1)[-1]
    # No metric of 05 MET-01 to MET-11 measures the pickup latency, and no module names the type:
    # when one does, the policy has a source and the sentence above is untrue.
    assert name not in {definition.name for definition in metrics.METRICS}
    assert not any("pickup" in definition.name for definition in metrics.METRICS)
    assert not [
        path
        for path in APPLICATION.rglob("*.py")
        if name in path.read_text("utf-8") or metric_type in path.read_text("utf-8")
    ]
    documented = resource("google_monitoring_alert_policy", "slo_04_job_pickup").body
    assert "Inert until the application exports the metric this policy reads" in documented
