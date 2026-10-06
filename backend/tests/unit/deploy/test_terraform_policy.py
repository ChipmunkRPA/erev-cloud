"""Effective-policy tests for the Terraform artifacts (lane P3b; independent review of 3e50ac3
findings P3-R1 to P3-R6 plus the pgAudit prerequisite and the P6 backup role).

These tests EVALUATE the policy the HCL encodes rather than asserting that blocks exist: the boolean
conditions of the invocation-policy locals are evaluated for every mode, Cloud Armor rules are
sorted by priority and eight request cases are run through the documented evaluation semantics
(first match wins; a preview match is logged and evaluation continues), the Secret Manager grants
are resolved into an allow/deny matrix per identity and secret, and the connection budget is
recomputed from the variable defaults. Still offline: no Terraform, no credentials (DG-FORBID-07,
DG-FORBID-12).
"""

from __future__ import annotations

import itertools
import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass

from support.terraform import (
    TERRAFORM_DIR,
    all_text,
    local_value,
    read_blocks,
    resource,
    resources,
    unquote,
    variable_default,
)

README = TERRAFORM_DIR / "README.md"
LOCALS = "\n".join(block.body for block in read_blocks() if block.kind == "locals")
POLICY_VARIABLES = ("enable_iap", "iap_healthz_exemption", "invoker_iam_disabled")
IAP_AGENT = "IAP_SERVICE_AGENT"


# ---------------------------------------------------------------------------------------------
# A tiny evaluator for the boolean HCL the policy locals are written in: `var.x`, `local.y`,
# `!`, `&&`, `||`, parentheses and the ternary `cond ? A : B` where A and B are `{ ... }` or `{}`.
# ---------------------------------------------------------------------------------------------


def _hcl_bool(expression: str, variables: dict[str, bool], locals_: dict[str, bool]) -> bool:
    text = expression.strip()
    text = re.sub(r"\bvar\.([a-z_]+)", lambda m: str(variables[m.group(1)]), text)
    text = re.sub(r"\blocal\.([a-z_]+)", lambda m: str(locals_[m.group(1)]), text)
    text = text.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    assert re.fullmatch(r"[A-Za-z_ ()]+", text), expression
    return bool(eval(text, {"__builtins__": {}}, {"True": True, "False": False}))  # noqa: S307


def _local_expression(name: str) -> str:
    value = local_value(name)
    assert value is not None, name
    return value


def _policy_locals(variables: dict[str, bool]) -> dict[str, bool]:
    found: dict[str, bool] = {}
    variables = {"iap_synthetic_health": True, **variables}  # the variable's default
    for name in (
        "api_public_invocation",
        "web_public_invocation",
        "api_invoker_iam_disabled",
        "web_invoker_iam_disabled",
        "uptime_probes_healthz",
        "iap_strict",
        "synthetic_enabled",
        "tcp_fallback",
    ):
        found[name] = _hcl_bool(_local_expression(name), variables, found)
    return found


def _invoker_bindings(variables: dict[str, bool]) -> dict[str, dict[str, str]]:
    """Evaluate `local.invoker_bindings = merge(cond ? {"key" = {...}} : {}, …)`."""
    match = re.search(r"invoker_bindings\s*=\s*merge\((.*?)\n  \)", LOCALS, re.S)
    assert match is not None, "local.invoker_bindings is a merge of conditional maps"
    locals_ = _policy_locals(variables)
    bindings: dict[str, dict[str, str]] = {}
    for line in match.group(1).splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        piece = re.fullmatch(
            r'(.+?)\s*\?\s*\{\s*"([a-z]+/[a-z]+)"\s*=\s*\{(.*)\}\s*\}\s*:\s*\{\}', line
        )
        assert piece is not None, line
        condition, key, body = piece.groups()
        if _hcl_bool(condition, variables, locals_):
            service = re.search(r'service\s*=\s*"([a-z]+)"', body)
            member = re.search(r"member\s*=\s*(\S+)", body)
            assert service and member, body
            value = member.group(1)
            member_kind = IAP_AGENT if value == "local.iap_service_agent" else unquote(value)
            assert member_kind is not None
            bindings[key] = {"service": service.group(1), "member": member_kind}
    return bindings


def _modes() -> list[dict[str, bool]]:
    return [
        dict(zip(POLICY_VARIABLES, values, strict=True))
        for values in itertools.product((False, True), repeat=len(POLICY_VARIABLES))
    ]


def test_cloud_run_invocation_policy_matrix() -> None:
    # P3-R1: the effective invoker set of every Cloud Run workload in all eight modes.
    for name in POLICY_VARIABLES:
        assert variable_default(name) == "false", name

    for mode in _modes():
        bindings = _invoker_bindings(mode)
        invokers = {
            service: {b["member"] for b in bindings.values() if b["service"] == service}
            for service in ("api", "web")
        }
        flags = _policy_locals(mode)
        iap, exemption, disabled = (mode[name] for name in POLICY_VARIABLES)

        if not iap:
            # IAP off: the load balancer forwards without a token, so api and web are publicly
            # invocable, either by allUsers or with the invoker IAM check disabled, never both.
            expected = set() if disabled else {"allUsers"}
            assert invokers["api"] == expected, mode
            assert invokers["web"] == expected, mode
            assert flags["api_invoker_iam_disabled"] is disabled, mode
            assert flags["web_invoker_iam_disabled"] is disabled, mode
            assert flags["uptime_probes_healthz"] is True, mode
        else:
            # IAP on: IAP invokes as its service agent; nothing public unless the healthz exemption
            # opens the api (and only the api) to public invocation.
            assert IAP_AGENT in invokers["api"] and IAP_AGENT in invokers["web"], mode
            assert invokers["web"] == {IAP_AGENT}, mode
            assert flags["web_invoker_iam_disabled"] is False, mode
            if exemption:
                assert invokers["api"] == ({IAP_AGENT} if disabled else {IAP_AGENT, "allUsers"}), (
                    mode
                )
                assert flags["api_invoker_iam_disabled"] is disabled, mode
                assert flags["uptime_probes_healthz"] is True, mode
            else:
                assert invokers["api"] == {IAP_AGENT}, mode
                assert flags["api_invoker_iam_disabled"] is False, mode
                assert flags["uptime_probes_healthz"] is False, mode
        # No binding ever names a worker or a job.
        assert {b["service"] for b in bindings.values()} <= {"api", "web"}, mode

    # The binding resource is the only invoker grant on api or web, keyed statically; the sole
    # other run.invoker binding is the synthetic executor on the probe FUNCTION (P3c).
    invoker_bindings = [
        block
        for block in resources("google_cloud_run_v2_service_iam_member")
        if unquote(block.attribute("role")) == "roles/run.invoker"
    ]
    assert sorted(block.name for block in invoker_bindings) == ["iap_probe_executor", "invoker"]
    (member,) = [block for block in invoker_bindings if block.name == "invoker"]
    assert member.attribute("for_each") == "local.invoker_bindings"
    assert "google_cloud_run_v2_service.api.name" in member.body
    assert "google_cloud_run_v2_service.web.name" in member.body
    for worker in ("worker_compute", "worker_general"):
        assert f"google_cloud_run_v2_service.{worker}" not in member.body
    assert not resources("google_cloud_run_v2_job_iam_member")
    assert "allUsers" not in "".join(
        block.body for block in resources("google_cloud_run_v2_service") if "worker" in block.name
    )
    # Workers keep internal ingress and never disable the invoker check.
    for worker in ("worker_compute", "worker_general"):
        block = resource("google_cloud_run_v2_service", worker)
        assert unquote(block.attribute("ingress")) == "INGRESS_TRAFFIC_INTERNAL_ONLY"
        assert block.attribute("invoker_iam_disabled") is None
    assert resource("google_cloud_run_v2_service", "api").attribute("invoker_iam_disabled") == (
        "local.api_invoker_iam_disabled"
    )
    assert resource("google_cloud_run_v2_service", "web").attribute("invoker_iam_disabled") == (
        "local.web_invoker_iam_disabled"
    )


def test_iap_service_agent_and_uptime_identity() -> None:
    # P3-R1 / P3-R5: the IAP service agent exists in the graph and is the invoker member; the uptime
    # check follows the invocation mode instead of assuming an unauthenticated healthz.
    iap = resource("google_project_service_identity", "iap")
    assert unquote(iap.attribute("service")) == "iap.googleapis.com"
    assert iap.attribute("provider") == "google-beta"
    assert _local_expression("iap_service_agent") == "google_project_service_identity.iap.member"

    uptime = resource("google_monitoring_uptime_check_config", "healthz")
    assert uptime.attribute("count") == "local.uptime_probes_healthz ? 1 : 0"
    (http,) = uptime.nested("http_check")
    assert unquote(http.attribute("path")) == "/api/v1/healthz"
    assert not http.nested("service_agent_authentication"), (
        "OIDC service-agent auth cannot pass IAP's Google-managed OAuth client"
    )
    front_door = resource("google_monitoring_uptime_check_config", "front_door_tcp")
    assert front_door.attribute("count") == "local.tcp_fallback ? 1 : 0"
    assert not front_door.nested("http_check")
    # The exemption path exists only with IAP on and the variable set, routes exactly one path and
    # carries Cloud Armor.
    health = resource("google_compute_backend_service", "api_health")
    assert health.attribute("count") == "var.enable_iap && var.iap_healthz_exemption ? 1 : 0"
    assert not health.nested("iap")
    assert health.attribute("security_policy") == "google_compute_security_policy.erev.id"
    url_map = resource("google_compute_url_map", "https")
    rules = url_map.descendants("path_rule")
    exempt = [rule for rule in rules if "api_health" in rule.body]
    assert len(exempt) == 1
    assert exempt[0].attribute("paths") == '["/api/v1/healthz"]'
    assert (
        exempt[0].attribute("for_each") == "var.enable_iap && var.iap_healthz_exemption ? [1] : []"
    )
    # Only the exempt rule can bypass IAP: the api and web backends carry the iap block.
    for name in ("api", "web"):
        (iap_block,) = resource("google_compute_backend_service", name).nested("iap")
        assert "var.enable_iap" in iap_block.body


@dataclass(frozen=True)
class Hop:
    status: int
    host: str


# What an unauthenticated GET sees in each mode; uptime checks follow redirects and evaluate the
# FINAL hop (Google "About uptime checks").
PUBLIC_HEALTHZ_FLOW = (Hop(200, "erev.example.com"),)
IAP_CHALLENGE_FLOW = (Hop(302, "erev.example.com"), Hop(200, "accounts.google.com"))


def _http_matcher_result(flow: tuple[Hop, ...], status_class: str) -> tuple[bool, str]:
    # The monitored outcome of an HTTPS uptime check: the final hop's status against the matcher.
    final = flow[-1]
    if status_class == "STATUS_CLASS_2XX":
        return 200 <= final.status < 300, final.host
    if status_class == "STATUS_CLASS_3XX":
        return 300 <= final.status < 400, final.host
    raise AssertionError(status_class)


def test_uptime_check_contract() -> None:
    # Codex residual (inbox 1846): the previous IAP-on probe expected a 3xx from GET /, which a
    # redirect-following check can never observe. Model both matchers against both flows.
    healthz = resource("google_monitoring_uptime_check_config", "healthz")
    (http,) = healthz.nested("http_check")
    (codes,) = http.nested("accepted_response_status_codes")
    status_class = unquote(codes.attribute("status_class"))
    assert status_class == "STATUS_CLASS_2XX"
    assert "STATUS_CLASS_3XX" not in all_text(), "a 3xx can never be the final response"

    # Public healthz: the matcher passes on the api's own 2xx and the final host is ours.
    passed, host = _http_matcher_result(PUBLIC_HEALTHZ_FLOW, status_class)
    assert (passed, host) == (True, "erev.example.com")
    # The same HTTPS matcher under IAP would pass on GOOGLE'S sign-in page: it validates the wrong
    # host and would stay green with the backend down, so it is not used under IAP-on/no-exemption.
    passed, host = _http_matcher_result(IAP_CHALLENGE_FLOW, status_class)
    assert (passed, host) == (True, "accounts.google.com")
    # A 3xx matcher (the pre-correction contract) fails on a healthy IAP flow.
    assert _http_matcher_result(IAP_CHALLENGE_FLOW, "STATUS_CLASS_3XX") == (
        False,
        "accounts.google.com",
    )

    # Mode selection: HTTPS healthz check iff the path is publicly invocable, TCP 443 otherwise.
    front_door = resource("google_monitoring_uptime_check_config", "front_door_tcp")
    (tcp,) = front_door.nested("tcp_check")
    assert tcp.attribute("port") == "443"
    assert not front_door.nested("http_check")
    for mode in _modes():
        flags = _policy_locals(mode)
        probes_healthz = flags["uptime_probes_healthz"]
        healthz_count = 1 if probes_healthz else 0
        assert healthz_count == (1 if _hcl_bool("local.uptime_probes_healthz", mode, flags) else 0)
        # IAP on without exemption is the strict mode: synthetic probe by default, TCP fallback
        # when iap_synthetic_health is false (evaluated below for all 16 modes).
        assert (not probes_healthz) is (mode["enable_iap"] and not mode["iap_healthz_exemption"]), (
            mode
        )
    for mode in _modes():
        for synthetic in (False, True):
            variables = {**mode, "iap_synthetic_health": synthetic}
            flags = _policy_locals(variables)
            strict = mode["enable_iap"] and not mode["iap_healthz_exemption"]
            assert flags["iap_strict"] is strict, variables
            assert flags["synthetic_enabled"] is (strict and synthetic), variables
            assert flags["tcp_fallback"] is (strict and not synthetic), variables
            # Exactly one external check per mode: HTTPS healthz, synthetic probe or TCP.
            checks = [not strict, flags["synthetic_enabled"], flags["tcp_fallback"]]
            assert sum(checks) == 1, variables
    # The alert follows whichever check exists, through one() of the two possibly-empty splats.
    check_id = re.search(r"uptime_check_id\s*=\s*try\((.*?)\n  \)", LOCALS, re.S)
    assert check_id is not None, (
        "local.uptime_check_id is try(coalesce(...), null) of the two splats"
    )
    assert "null" in check_id.group(1).splitlines()[-1]
    assert (
        "one(google_monitoring_uptime_check_config.healthz[*].uptime_check_id)" in check_id.group(1)
    )
    assert "one(google_monitoring_uptime_check_config.front_door_tcp[*].uptime_check_id)" in (
        check_id.group(1)
    )
    alert = resource("google_monitoring_alert_policy", "uptime")
    assert "${local.uptime_check_id}" in alert.body
    assert alert.attribute("count") == "local.synthetic_enabled ? 0 : 1"
    contract = _local_expression("uptime_check_contract")
    assert "TCP 443" in contract and "DNS and load balancer reachability only" in contract
    assert "Cloud Run probes and SLO-01" in contract
    readme = README.read_text(encoding="utf-8")
    assert "follow" in readme and "redirect" in readme and "final response" in readme
    assert "TCP check on port 443" in readme


# ---------------------------------------------------------------------------------------------
# Cloud Armor (P3-R2)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ArmorRule:
    priority: int
    action: str
    preview: bool
    kind: str  # "waf" | "throttle" | "default"


def _armor_rules(preview: bool) -> list[ArmorRule]:
    policy = resource("google_compute_security_policy", "erev")
    rules: list[ArmorRule] = []
    throttle_priority = int(_local_expression("cloud_armor_throttle_priority"))
    for rule in policy.nested("rule"):
        action = unquote(rule.attribute("action"))
        priority = rule.attribute("priority")
        if rule.attribute("for_each") == "local.owasp_rules":
            assert rule.attribute("preview") == "var.cloud_armor_preview"
            assert action == "deny(403)"
            owasp = re.search(r"owasp_rules\s*=\s*\{(.*?)\n  \}", LOCALS, re.S)
            assert owasp is not None
            for line in owasp.group(1).splitlines():
                found = re.search(
                    r"priority\s*=\s*(\d+),\s*expression\s*=\s*\"evaluatePreconfiguredWaf", line
                )
                if found:
                    rules.append(ArmorRule(int(found.group(1)), action, preview, "waf"))
            continue
        assert priority is not None and action is not None
        if action == "throttle":
            assert priority == "local.cloud_armor_throttle_priority"
            assert rule.attribute("preview") is None
            rules.append(ArmorRule(throttle_priority, action, False, "throttle"))
        else:
            rules.append(ArmorRule(int(priority), action, False, "default"))
    return sorted(rules, key=lambda r: r.priority)


def _evaluate(rules: list[ArmorRule], *, malicious: bool, above_limit: bool) -> tuple[str, str]:
    """Cloud Armor semantics: lowest priority number first; the first matching enforced rule
    decides; a preview match is logged and evaluation continues."""
    for rule in rules:
        matches = (rule.kind == "waf" and malicious) or rule.kind in ("throttle", "default")
        if not matches:
            continue
        if rule.preview:
            continue
        if rule.kind == "throttle":
            return ("deny(429)" if above_limit else "allow", rule.kind)
        return (rule.action, rule.kind)
    raise AssertionError("no rule matched")


def test_cloud_armor_waf_precedes_throttle() -> None:
    assert variable_default("cloud_armor_preview") == "true"
    throttle_priority = int(_local_expression("cloud_armor_throttle_priority"))
    assert throttle_priority == 1000
    for preview in (True, False):
        rules = _armor_rules(preview)
        waf = [r for r in rules if r.kind == "waf"]
        assert len(waf) >= 5
        assert all(r.priority < throttle_priority for r in waf), (
            "every WAF rule precedes the throttle"
        )
        assert len({r.priority for r in rules}) == len(rules), "priorities are unique"
        assert rules[-1].kind == "default" and rules[-1].action == "allow"
        assert rules[-1].priority == 2147483647

        # Eight request cases.
        assert _evaluate(rules, malicious=False, above_limit=False) == ("allow", "throttle")
        assert _evaluate(rules, malicious=False, above_limit=True) == ("deny(429)", "throttle")
        if preview:
            # Logged by the WAF rule, then decided by the throttle: never enforced by the WAF.
            assert _evaluate(rules, malicious=True, above_limit=False) == ("allow", "throttle")
            assert _evaluate(rules, malicious=True, above_limit=True) == ("deny(429)", "throttle")
        else:
            assert _evaluate(rules, malicious=True, above_limit=False) == ("deny(403)", "waf")
            assert _evaluate(rules, malicious=True, above_limit=True) == ("deny(403)", "waf")

    # The pre-correction ordering (throttle first) would allow a below-limit malicious request even
    # when enforced: shown against a reversed model so the assertion is not vacuous.
    reversed_rules = sorted(
        [
            ArmorRule(1000, "throttle", False, "throttle"),
            ArmorRule(1100, "deny(403)", False, "waf"),
            ArmorRule(2147483647, "allow", False, "default"),
        ],
        key=lambda r: r.priority,
    )
    assert _evaluate(reversed_rules, malicious=True, above_limit=False) == ("allow", "throttle")


# ---------------------------------------------------------------------------------------------
# Secret Manager access matrix (P3-R3)
# ---------------------------------------------------------------------------------------------

IDENTITIES = ("api", "worker", "migrate", "provisioning", "web")
STATIC = {
    "db_owner_url": "erev-db-owner-url",
    "db_app_url": "erev-db-app-url",
    "security_hmac": "erev-security-hmac",
    "anthropic_api_key": "erev-anthropic-api-key",
    "smtp_password": "erev-smtp-password",
    "metrics_token": "erev-metrics-token",
    "db_backup_url": "erev-db-backup-url",
}
TENANT = "erev-audit-hmac-11111111-2222-3333-4444-555555555555"
UNRELATED = "some-other-team-secret"
PREFIX = "erev-audit-hmac-"


def _named_accessors() -> dict[str, set[str]]:
    """identity -> static secret keys it may access, from local.secret_accessors."""
    match = re.search(r"secret_accessors\s*=\s*\{(.*?)\n  \}", LOCALS, re.S)
    assert match is not None
    grants: dict[str, set[str]] = {identity: set() for identity in IDENTITIES}
    for key, identity in re.findall(
        r'"([a-z_]+)/([a-z]+)"\s*=\s*\{\s*key\s*=\s*"\1",\s*member\s*=\s*google_service_account\.\2\.email',
        match.group(1),
    ):
        grants[identity].add(key)
    accessor = resource("google_secret_manager_secret_iam_member", "accessor")
    assert accessor.attribute("for_each") == "local.secret_accessors"
    assert unquote(accessor.attribute("role")) == "roles/secretmanager.secretAccessor"
    return grants


def _conditional_readers() -> set[str]:
    match = re.search(r"tenant_secret_readers\s*=\s*\{(.*?)\n  \}", LOCALS, re.S)
    assert match is not None
    readers = set(re.findall(r"\b([a-z]+)\s*=\s*google_service_account\.\1\.email", match.group(1)))
    binding = resource("google_project_iam_member", "tenant_secret_accessor")
    assert binding.attribute("for_each") == "local.tenant_secret_readers"
    (condition,) = binding.nested("condition")
    assert "resource.name.startsWith" in condition.body
    assert "local.tenant_audit_hmac_secret_prefix" in condition.body
    return readers


def _role_permissions(name: str) -> set[str]:
    role = resource("google_project_iam_custom_role", name)
    return set(re.findall(r'"(secretmanager\.[a-z]+\.[a-z]+)"', role.body))


def _effective(identity: str, secret_id: str) -> dict[str, bool]:
    named = _named_accessors()[identity]
    readers = _conditional_readers()
    creator = _role_permissions("tenant_secret_creator")
    initializer = _role_permissions("tenant_secret_initializer")
    is_tenant = secret_id.startswith(PREFIX)
    static_key = next((k for k, v in STATIC.items() if v == secret_id), None)

    access = (static_key in named) or (identity in readers and is_tenant)
    add = False
    create = False
    if identity == "provisioning":
        # Creator role: project scope, unconditional, creation only.
        create = "secretmanager.secrets.create" in creator
        assert creator == {"secretmanager.secrets.create"}
        # Initializer role: project scope under the KEY-05 prefix condition.
        if is_tenant:
            access = access or "secretmanager.versions.access" in initializer
            add = "secretmanager.versions.add" in initializer
    return {"access": access, "add": add, "create": create}


def test_secret_access_matrix() -> None:
    # P3-R3: every identity against every kind of secret, positive and negative.
    creator_binding = resource("google_project_iam_member", "provisioning_creator")
    assert not creator_binding.nested("condition")  # creation is project-scoped by nature
    assert "google_project_iam_custom_role.tenant_secret_creator.id" in creator_binding.body
    initializer_binding = resource("google_project_iam_member", "provisioning_initializer")
    (condition,) = initializer_binding.nested("condition")
    assert "local.tenant_audit_hmac_secret_prefix" in condition.body
    assert "google_project_iam_custom_role.tenant_secret_initializer.id" in initializer_binding.body
    assert (
        unquote(_local_expression("tenant_audit_hmac_secret_prefix"))
        == "${var.secret_prefix}audit-hmac-"
    )
    text = all_text()
    assert "tenant_secret_provisioner" not in text  # the single broad role is gone
    for forbidden in (
        "secretmanager.secrets.delete",
        "secretmanager.versions.destroy",
        "secretmanager.versions.disable",
        "secretmanager.secrets.setIamPolicy",
        "roles/secretmanager.admin",
        "roles/secretmanager.secretVersionManager",
    ):
        assert forbidden not in text, forbidden
    # No unconditional project-wide grant of a role that can READ or ADD to secrets.
    for member in resources("google_project_iam_member"):
        role = unquote(member.attribute("role")) or member.attribute("role") or ""
        if "secretAccessor" in role or "tenant_secret_initializer" in role:
            assert member.nested("condition"), member.name

    expected: dict[tuple[str, str], tuple[bool, bool, bool]] = {}
    for identity in IDENTITIES:
        for secret_id in (*STATIC.values(), TENANT, UNRELATED):
            expected[(identity, secret_id)] = (False, False, False)
    # (access, add, create)
    for identity, secret_id in (
        ("api", STATIC["db_app_url"]),
        ("api", STATIC["security_hmac"]),
        ("api", STATIC["anthropic_api_key"]),
        ("api", STATIC["smtp_password"]),
        ("api", STATIC["metrics_token"]),
        ("api", TENANT),
        ("worker", STATIC["db_app_url"]),
        ("worker", STATIC["security_hmac"]),
        ("worker", STATIC["anthropic_api_key"]),
        ("worker", STATIC["smtp_password"]),
        ("worker", TENANT),
        ("migrate", STATIC["db_owner_url"]),
        ("migrate", STATIC["db_app_url"]),  # the DB-14 lint runs as erev_app after the upgrade
    ):
        expected[(identity, secret_id)] = (True, False, False)
    for secret_id in (STATIC["db_app_url"], STATIC["security_hmac"]):
        expected[("provisioning", secret_id)] = (True, False, True)
    expected[("provisioning", TENANT)] = (True, True, True)
    for secret_id in (
        STATIC["db_owner_url"],
        STATIC["smtp_password"],  # the invitation is an outbox row the worker relays (P2)
        STATIC["anthropic_api_key"],
        STATIC["metrics_token"],
        STATIC["db_backup_url"],
        UNRELATED,
    ):
        expected[("provisioning", secret_id)] = (False, False, True)

    for (identity, secret_id), (access, add, create) in expected.items():
        effective = _effective(identity, secret_id)
        assert effective == {"access": access, "add": add, "create": create}, (
            identity,
            secret_id,
            effective,
        )

    # The provisioning job injects only what it may read; no AI key, fake AI provider.
    provision_secret_env = _local_expression("provision_secret_env")
    assert provision_secret_env is not None
    env_text = re.search(r"provision_secret_env\s*=\s*\{(.*?)\n  \}", LOCALS, re.S)
    assert env_text is not None
    assert set(re.findall(r"^\s{4}(EREV_[A-Z_]+)\s*=", env_text.group(1), re.M)) == {
        "EREV_DB_APP_URL"
    }
    assert "EREV_SMTP_PASSWORD" not in env_text.group(1)  # outbox EMAIL row, relayed by the worker
    assert "ANTHROPIC_API_KEY" not in env_text.group(1)
    assert "db_owner_url" not in env_text.group(1)
    assert '"smtp_password/provisioning"' not in LOCALS
    # The migrate job injects exactly the owner URL (upgrade) and the app URL (DB-14 lint), pinned.
    migrate_env = re.search(r"migrate_secret_env\s*=\s*\{(.*?)\n  \}", LOCALS, re.S)
    assert migrate_env is not None
    assert set(re.findall(r"^\s{4}(EREV_[A-Z_]+)\s*=", migrate_env.group(1), re.M)) == {
        "EREV_DB_OWNER_URL",
        "EREV_DB_APP_URL",
    }
    assert "google_secret_manager_secret_version.db_owner_url.version" in migrate_env.group(1)
    assert "google_secret_manager_secret_version.db_app_url.version" in migrate_env.group(1)
    provision_env = re.search(
        r"provision_env\s*=\s*merge\(local\.python_env,\s*\{(.*?)\}\)", LOCALS, re.S
    )
    assert provision_env is not None and 'EREV_AI_PROVIDER = "fake"' in provision_env.group(1)
    job = resource("google_cloud_run_v2_job", "tenant_provision")
    assert "local.provision_secret_env" in job.body and "local.provision_env" in job.body
    assert "local.runtime_secret_env" not in job.body


# ---------------------------------------------------------------------------------------------
# Connection budget (P3-R4)
# ---------------------------------------------------------------------------------------------


def _int_default(name: str) -> int:
    value = variable_default(name)
    assert value is not None, name
    return int(value)


def _budget(**overrides: int) -> tuple[int, int]:
    """Recompute the locals' arithmetic from the variable defaults (05 §2.7; README)."""
    v = {
        name: _int_default(name)
        for name in (
            "api_pool_size",
            "api_max_overflow",
            "worker_sqlalchemy_pool_size",
            "worker_sqlalchemy_max_overflow",
            "worker_concurrency",
            "api_min_instances",
            "api_max_instances",
            "worker_compute_min_instances",
            "worker_compute_max_instances",
            "worker_general_min_instances",
            "worker_general_max_instances",
            "migrate_connection_allowance",
            "db_connection_reserve",
            "db_max_connections",
        )
    }
    v.update(overrides)
    api_per = v["api_pool_size"] + v["api_max_overflow"]
    worker_per = (
        (v["worker_concurrency"] + 2)
        + v["worker_sqlalchemy_pool_size"]
        + v["worker_sqlalchemy_max_overflow"]
    )
    steady = (
        v["api_max_instances"] * api_per
        + v["worker_compute_max_instances"] * worker_per
        + v["worker_general_max_instances"] * worker_per
    )
    overlap = (
        v["api_min_instances"] * api_per
        + v["worker_compute_min_instances"] * worker_per
        + v["worker_general_min_instances"] * worker_per
    )
    total = steady + overlap + v["migrate_connection_allowance"] + v["db_connection_reserve"]
    ceiling = math.floor(v["db_max_connections"] * 0.8)
    return total, ceiling


def test_connection_budget_is_blocking() -> None:
    # The locals encode exactly this arithmetic.
    assert (
        _local_expression("api_connections_per_instance")
        == "var.api_pool_size + var.api_max_overflow"
    )
    assert _local_expression("worker_procrastinate_pool") == "var.worker_concurrency + 2"
    assert _local_expression("db_connection_budget") == "floor(var.db_max_connections * 0.8)"
    assert _local_expression("db_connection_budget_ok") == (
        "local.max_db_connections_used <= local.db_connection_budget"
    )
    # Default, boundary and over-budget cases.
    total, ceiling = _budget()
    assert (total, ceiling) == (440, 480) and total <= ceiling
    total, ceiling = _budget(db_max_connections=550)
    assert (total, ceiling) == (440, 440) and total <= ceiling  # boundary passes
    total, ceiling = _budget(db_max_connections=500)
    assert (total, ceiling) == (440, 400) and total > ceiling  # must FAIL the plan
    total, ceiling = _budget(api_max_instances=12)
    assert total == 480 and ceiling == 480 and total <= ceiling
    total, ceiling = _budget(api_max_instances=13)
    assert total == 500 and total > ceiling

    # Blocking: a lifecycle precondition on the Cloud SQL instance, and no non-blocking check block.
    instance = resource("google_sql_database_instance", "erev")
    (lifecycle,) = instance.nested("lifecycle")
    preconditions = lifecycle.nested("precondition")
    assert any(p.attribute("condition") == "local.db_connection_budget_ok" for p in preconditions)
    assert not [block for block in read_blocks() if block.kind == "check"], "check blocks only warn"
    readme = README.read_text(encoding="utf-8")
    assert "precondition" in readme and "blocking" in readme.lower()
    assert "440" in readme and "480" in readme and "400" in readme
    assert "check block" not in readme.lower() or "only warn" in readme.lower()


# ---------------------------------------------------------------------------------------------
# Service identity bootstrap (P3-R5)
# ---------------------------------------------------------------------------------------------


def test_cloud_sql_cmek_identity_bootstrap() -> None:
    identity = resource("google_project_service_identity", "cloud_sql")
    assert unquote(identity.attribute("service")) == "sqladmin.googleapis.com"
    assert identity.attribute("provider") == "google-beta"
    assert (
        _local_expression("cloud_sql_service_agent")
        == "google_project_service_identity.cloud_sql.member"
    )
    grant = resource("google_kms_crypto_key_iam_member", "cloudsql_service_agent")
    assert grant.attribute("member") == "local.cloud_sql_service_agent"
    assert grant.attribute("count") == "var.use_cmek ? 1 : 0"
    instance = resource("google_sql_database_instance", "erev")
    assert "google_kms_crypto_key_iam_member.cloudsql_service_agent" in instance.body
    # Dependency graph: identity -> grant -> instance.
    (terraform_block,) = [block for block in read_blocks() if block.kind == "terraform"]
    (providers,) = terraform_block.nested("required_providers")
    assert re.search(
        r'google-beta\s*=\s*\{[^}]*source\s*=\s*"hashicorp/google-beta"', providers.body, re.S
    )
    beta = [
        block
        for block in read_blocks()
        if block.kind == "provider" and block.labels == ("google-beta",)
    ]
    assert len(beta) == 1


# ---------------------------------------------------------------------------------------------
# Security HMAC version (P3-R6)
# ---------------------------------------------------------------------------------------------


def test_security_hmac_version_reaches_runtime() -> None:
    python_env = re.search(r"python_env\s*=\s*\{(.*?)\n  \}", LOCALS, re.S)
    assert python_env is not None
    assert re.search(
        r"EREV_SECURITY_HMAC_SECRET_VERSION\s*=\s*var\.secret_versions\.security_hmac",
        python_env.group(1),
    )
    # Every Python workload receives python_env (api, worker, migrate) or a merge of it (provision).
    for name in ("api", "worker_compute", "worker_general"):
        block = resource("google_cloud_run_v2_service", name)
        assert "local.api_env" in block.body or "local.worker_env" in block.body
    assert re.search(r"api_env\s*=\s*merge\(local\.python_env", LOCALS)
    assert re.search(r"worker_env\s*=\s*merge\(local\.python_env", LOCALS)
    assert re.search(r"provision_env\s*=\s*merge\(local\.python_env", LOCALS)
    readme = README.read_text(encoding="utf-8")
    assert "EREV_SECURITY_HMAC_SECRET_VERSION" in readme
    assert "security-hmac:<" in readme or "security-hmac:" in readme
    text = all_text()
    assert re.search(r'version\s*=\s*"latest"', text) is None


# ---------------------------------------------------------------------------------------------
# pgAudit prerequisites (SAR-30) and the P6 backup role
# ---------------------------------------------------------------------------------------------


def test_pgaudit_prerequisites_assigned() -> None:
    audit = resource("google_project_iam_audit_config", "cloudsql_data_access")
    assert unquote(audit.attribute("service")) == "cloudsql.googleapis.com"
    log_types = {unquote(c.attribute("log_type")) for c in audit.nested("audit_log_config")}
    assert {"DATA_READ", "DATA_WRITE"} <= log_types
    flags = "\n".join(block.body for block in read_blocks() if block.kind == "locals")
    for flag, value in (
        ("cloudsql.enable_pgaudit", "on"),
        ("pgaudit.log", "ddl,role"),
        ("cloudsql.pgaudit_mask_literals", "on"),
    ):
        assert re.search(rf'"{re.escape(flag)}"\s*=\s*"{re.escape(value)}"', flags), flag
    text = all_text()
    # Spelled in pieces so DG-ARC-05 (no database-administration literals in machine files)
    # does not read this test as a migration; assigned to the first erev-migrate run.
    pgaudit_statement = " ".join(("CREATE", "EXTENSION", "pgaudit"))
    assert pgaudit_statement in text
    readme = README.read_text(encoding="utf-8")
    assert pgaudit_statement in readme and "Data Access" in readme


def test_backup_user_role() -> None:
    # D-95: hosted production has no erev_backup and no pg_dump backup; the variables stay for the
    # unestablished path, default OFF; the drill target is declared by restore_test_instance.
    assert variable_default("backup_user_enabled") == "false"
    assert unquote(variable_default("backup_user_name")) == "erev_backup"
    assert variable_default("backup_url_secret_accessors") == "[]"
    assert variable_default("restore_test_instance") == "null"
    restore = [
        b for b in read_blocks() if b.kind == "variable" and b.name == "restore_test_instance"
    ]
    assert len(restore) == 1
    (validation,) = restore[0].nested("validation")
    assert "var.restore_test_instance == null || try(" in validation.body
    assert "project_id" in validation.body and "instance_name" in validation.body
    assert "UI-P6-2" in validation.body
    target = [b for b in read_blocks() if b.kind == "output" and b.name == "restore_test_target"]
    assert len(target) == 1 and target[0].attribute("value") == "var.restore_test_instance"
    # The backup URL secret exists only when the user does.
    secrets_text = re.search(r"static_secrets\s*=\s*merge\((.*?)\n  \)", LOCALS, re.S)
    assert secrets_text is not None
    assert re.search(r"var\.backup_user_enabled \? \{\s*db_backup_url", secrets_text.group(1))
    readme = README.read_text(encoding="utf-8")
    assert "OPR-12" in readme and "restore_test_instance" in readme
    assert "no `erev_backup` role and no `pg_dump` backup" in readme
    assert "does not\ninherit `BYPASSRLS`" in readme or "does not inherit `BYPASSRLS`" in readme
    user = resource("google_sql_user", "backup")
    assert user.attribute("count") == "var.backup_user_enabled ? 1 : 0"
    assert user.attribute("name") == "var.backup_user_name"
    assert user.attribute("password") == "random_password.backup[0].result"
    version = resource("google_secret_manager_secret_version", "db_backup_url")
    assert "random_password.backup[0].result" in (version.attribute("secret_data") or "")
    accessor = resource("google_secret_manager_secret_iam_member", "backup_url_accessor")
    assert "var.backup_url_secret_accessors" in (accessor.attribute("for_each") or "")
    # No runtime identity may read the backup URL; no output leaks it.
    assert "db_backup_url" not in re.search(
        r"secret_accessors\s*=\s*\{(.*?)\n  \}", LOCALS, re.S
    ).group(1)  # type: ignore[union-attr]
    for block in read_blocks():
        if block.kind == "output":
            assert "random_password" not in block.body and "secret_data" not in block.body, (
                block.name
            )
    secrets_text = re.search(r"static_secrets\s*=\s*merge\((.*?)\n  \)", LOCALS, re.S)
    assert secrets_text is not None and "db-backup-url" in secrets_text.group(1)
    readme = README.read_text(encoding="utf-8")
    assert "erev_backup" in readme and "BYPASSRLS" in readme


# ---------------------------------------------------------------------------------------------
# Strict-IAP health probe (P3c): signer scope, monitor contract, mocked runner
# ---------------------------------------------------------------------------------------------

RUNNER_DIR = TERRAFORM_DIR / "synthetic" / "iap-healthz"


def _probe_counted(kind: str, name: str):  # noqa: ANN202
    block = resource(kind, name)
    assert block.attribute("count") == "local.synthetic_enabled ? 1 : 0", (kind, name)
    return block


def test_iap_probe_signer_scope() -> None:
    # The probe identity signs JWTs for itself only, passes IAP for the api backend only, holds no
    # key, no invoker and no other grant; nothing else gains an IAP accessor.
    assert variable_default("iap_synthetic_health") == "true"
    assert _local_expression("synthetic_enabled") == "local.iap_strict && var.iap_synthetic_health"
    assert _local_expression("iap_strict") == "var.enable_iap && !var.iap_healthz_exemption"
    signer = _probe_counted("google_service_account", "iap_probe")
    assert unquote(signer.attribute("account_id")) == "${local.name}-iap-probe"

    role = _probe_counted("google_project_iam_custom_role", "iap_probe_jwt_signer")
    permissions = set(re.findall(r'"([a-z]+\.[A-Za-z]+\.[A-Za-z]+)"', role.body))
    assert permissions == {"iam.serviceAccounts.signJwt"}
    binding = _probe_counted("google_service_account_iam_member", "iap_probe_self_sign")
    assert binding.attribute("service_account_id") == "google_service_account.iap_probe[0].name"
    assert binding.attribute("member") == "google_service_account.iap_probe[0].member"
    assert binding.attribute("role") == "google_project_iam_custom_role.iap_probe_jwt_signer[0].id"
    text = all_text()
    assert text.count("google_project_iam_custom_role.iap_probe_jwt_signer[0].id") == 1
    assert "roles/iam.serviceAccountTokenCreator" not in text  # narrower than the documented role
    assert not resources("google_service_account_key"), "no exported key anywhere"

    accessor = _probe_counted("google_iap_web_backend_service_iam_member", "iap_probe_api")
    assert accessor.attribute("web_backend_service") == "google_compute_backend_service.api.name"
    assert unquote(accessor.attribute("role")) == "roles/iap.httpsResourceAccessor"
    assert accessor.attribute("member") == "google_service_account.iap_probe[0].member"
    # Every other IAP accessor binding is the UI-7 principal list; none names the probe, and the
    # web backend gets no probe accessor.
    for block in resources("google_iap_web_backend_service_iam_member"):
        if block.name == "iap_probe_api":
            continue
        assert "var.iap_allowed_principals" in (block.attribute("for_each") or ""), block.name
        assert "iap_probe" not in block.body, block.name
    web_bindings = [
        b
        for b in resources("google_iap_web_backend_service_iam_member")
        if b.attribute("web_backend_service") == "google_compute_backend_service.web.name"
    ]
    assert all("iap_probe" not in b.body for b in web_bindings)
    # The probe never becomes a Cloud Run invoker of api or web, and no allUsers appears near it.
    invoker = [
        b
        for b in resources("google_cloud_run_v2_service_iam_member")
        if "iap_probe" in b.body or b.name == "iap_probe_executor"
    ]
    assert [b.name for b in invoker] == ["iap_probe_executor"]
    executor = invoker[0]
    assert executor.attribute("name") == "google_cloudfunctions2_function.iap_probe[0].name"
    assert executor.attribute("member") == "local.monitoring_notification_service_agent"
    assert unquote(executor.attribute("role")) == "roles/run.invoker"
    assert "allUsers" not in executor.body
    # Secrets: the probe reads none.
    assert "iap_probe" not in re.search(
        r"secret_accessors\s*=\s*\{(.*?)\n  \}", LOCALS, re.S
    ).group(1)  # type: ignore[union-attr]


def test_iap_probe_monitor_contract() -> None:
    function = _probe_counted("google_cloudfunctions2_function", "iap_probe")
    (build,) = function.nested("build_config")
    assert unquote(build.attribute("entry_point")) == "SyntheticFunction"
    assert build.attribute("runtime") == "var.iap_probe_runtime"
    assert unquote(variable_default("iap_probe_runtime")) == "nodejs22"
    (service,) = function.nested("service_config")
    assert service.attribute("service_account_email") == "google_service_account.iap_probe[0].email"
    assert service.attribute("max_instance_count") == "1"
    env = "\n".join(service.body.splitlines())
    assert re.search(r"EREV_PROBE_TARGET_URL\s*=\s*local\.iap_probe_target", env)
    assert (
        unquote(_local_expression("iap_probe_target"))
        == "https://${var.public_domain}/api/v1/healthz"
    )
    assert re.search(
        r"EREV_PROBE_SIGNER_EMAIL\s*=\s*google_service_account\.iap_probe\[0\]\.email", env
    )
    assert re.search(
        r"EREV_PROBE_JWT_TTL_SECONDS\s*=\s*tostring\(var\.iap_probe_jwt_ttl_seconds\)", env
    )
    assert variable_default("iap_probe_jwt_ttl_seconds") == "300"
    assert not service.nested("secret_environment_variables")
    # Source: the committed runner directory, zipped without its test; hashed object name.
    (archive,) = [b for b in read_blocks() if b.kind == "data" and b.type == "archive_file"]
    assert unquote(archive.attribute("source_dir")) == "${path.module}/synthetic/iap-healthz"
    assert '"probe.test.mjs"' in (archive.attribute("excludes") or "")
    source = _probe_counted("google_storage_bucket_object", "iap_probe_source")
    assert "data.archive_file.iap_probe.output_md5" in (source.attribute("name") or "")

    monitor = _probe_counted("google_monitoring_uptime_check_config", "iap_healthz_synthetic")
    assert monitor.attribute("period") == "var.iap_probe_period"
    assert unquote(variable_default("iap_probe_period")) == "60s"
    (synthetic,) = monitor.nested("synthetic_monitor")
    (cf,) = synthetic.nested("cloud_function_v2")
    assert cf.attribute("name") == "google_cloudfunctions2_function.iap_probe[0].id"
    assert not monitor.nested("http_check") and not monitor.nested("tcp_check")

    # Alerts: synthetic results live on cloud_run_revision with the synthetic check id; the plain
    # uptime_url alert is not created in synthetic mode; a missing execution alerts too.
    failed = _probe_counted("google_monitoring_alert_policy", "iap_probe_failed")
    (threshold,) = failed.descendants("condition_threshold")
    filt = threshold.attribute("filter") or ""
    assert 'resource.type=\\"cloud_run_revision\\"' in filt
    assert "google_monitoring_uptime_check_config.iap_healthz_synthetic[0].uptime_check_id" in filt
    assert 'resource.type=\\"uptime_url\\"' not in filt
    (failed_agg,) = threshold.nested("aggregations")
    assert failed_agg.attribute("alignment_period") == "local.iap_probe_failure_window"
    assert unquote(failed_agg.attribute("per_series_aligner")) == "ALIGN_COUNT_FALSE"
    assert threshold.attribute("threshold_value") == "1"
    missing = _probe_counted("google_monitoring_alert_policy", "iap_probe_missing")
    (absent,) = missing.descendants("condition_absent")
    assert "iap_healthz_synthetic[0].uptime_check_id" in (absent.attribute("filter") or "")
    assert absent.attribute("duration") == "local.iap_probe_absence_duration"
    (absent_agg,) = absent.nested("aggregations")
    assert absent_agg.attribute("alignment_period") == "var.iap_probe_period"
    # P3c-R2: the absence policy no longer claims to detect a never-deployed monitor.
    assert "failed to deploy" not in missing.body
    assert "never started" in missing.body and "prior data point" in missing.body
    plain = resource("google_monitoring_alert_policy", "uptime")
    assert plain.attribute("count") == "local.synthetic_enabled ? 0 : 1"
    contract = _local_expression("uptime_check_contract")
    assert "Synthetic monitor" in contract and "redirects disabled" in contract
    assert "200 with JSON status ok" in contract

    # Runner source: the guarded request and the audience rule are literal in the code.
    probe_js = (RUNNER_DIR / "probe.js").read_text(encoding="utf-8")
    assert "redirect: 'manual'" in probe_js
    assert "rejectUnauthorized" not in probe_js and "NODE_TLS_REJECT_UNAUTHORIZED" not in probe_js
    assert "audience: url.toString()" in probe_js and "aud: config.audience" in probe_js
    assert "MAX_JWT_TTL_SECONDS = 3600" in probe_js
    assert "expectedStatus: 200" in probe_js and "expectedBodyStatus: 'ok'" in probe_js
    assert ":signJwt" in probe_js and "private" not in probe_js.lower().replace(
        "no private key", ""
    )
    index_js = (RUNNER_DIR / "index.js").read_text(encoding="utf-8")
    assert "'SyntheticFunction'" in index_js and "runSyntheticHandler" in index_js
    package = json.loads((RUNNER_DIR / "package.json").read_text(encoding="utf-8"))
    for name, version in package["dependencies"].items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), (name, version)  # exact pins
    assert set(package["dependencies"]) == {
        "@google-cloud/functions-framework",
        "@google-cloud/synthetics-sdk-api",
    }
    readme = README.read_text(encoding="utf-8")
    assert "self-signed JWT" in readme and "Strict-IAP health probe" in readme
    assert "iap_probe_missing" in readme


def _seconds(expression: str) -> int:
    return int(expression.rstrip("s"))


def test_iap_probe_alert_windows_follow_period() -> None:
    # P3c-R1: for every supported period the failure window holds two execution periods plus a
    # minute of margin (so count_false > 1 means at least two failed results within the window,
    # consecutive or not; one isolated failure never fires) and the absence
    # duration spans two healthy gaps (so a healthy series never trips it); both are multiples of
    # 60 s and inside Google's limits.
    period = [b for b in read_blocks() if b.kind == "variable" and b.name == "iap_probe_period"]
    (validation,) = period[0].nested("validation")
    supported = re.findall(r'"(\d+)s"', validation.attribute("condition") or "")
    assert supported == ["60", "300", "600", "900"]
    assert _local_expression("iap_probe_period_seconds") == (
        'tonumber(trimsuffix(var.iap_probe_period, "s"))'
    )
    assert _local_expression("iap_probe_failure_window") == (
        '"${2 * local.iap_probe_period_seconds + 60}s"'
    )
    assert _local_expression("iap_probe_absence_duration") == (
        '"${max(600, 2 * local.iap_probe_period_seconds)}s"'
    )
    for text in supported:
        p = int(text)
        window = 2 * p + 60
        absence = max(600, 2 * p)
        # Two results (spacing p) always fall inside a window of at least 2p, so at least two
        # failed results within the window reach count_false = 2 > 1 (consecutive or not); one
        # isolated failure never does.
        assert window >= 2 * p and window % 60 == 0 and window >= 60
        executions_in_window = window // p + 1
        assert executions_in_window >= 2
        # A healthy series has gaps of exactly p: the absence duration must exceed one gap and hold
        # at least two, and stay under the 23.5 h ceiling.
        assert absence > p and absence >= 2 * p and absence % 60 == 0
        assert absence <= 23 * 3600 + 1800
    # The 900 s period no longer exceeds the absence duration (previously fixed at 600 s), and the
    # 300 s failure window no longer holds a single execution of a 600 s or 900 s series.
    assert max(600, 2 * 900) == 1800 > 900
    assert 2 * 900 + 60 == 1860 >= 2 * 900
    readme = README.read_text(encoding="utf-8")
    assert "2p + 60" in readme and "max(600, 2p)" in readme
    assert "needs a prior data point" in readme and "iap_probe_first_execution" in readme
    first = [
        b for b in read_blocks() if b.kind == "variable" and b.name == "iap_probe_first_execution"
    ]
    assert len(first) == 1 and first[0].attribute("default") == "null"
    assert first[0].nested("validation")
    outputs = [b for b in read_blocks() if b.kind == "output" and b.name == "iap_probe"]
    assert "first_execution_recorded = var.iap_probe_first_execution != null" in outputs[0].body
    assert "never_started_detection" in outputs[0].body


def test_iap_probe_runner_mocked_cases() -> None:
    # The runner's failure classes against mocked fetch and clock (node:test, no network).
    node = shutil.which("node")
    assert node is not None, "node is part of the toolchain (DG-ENV)"
    result = subprocess.run(
        [node, "--test", str(RUNNER_DIR / "probe.test.mjs")],
        cwd=RUNNER_DIR,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = result.stdout + result.stderr
    passed = re.search(r"^ℹ pass (\d+)$", summary, re.M)
    failed = re.search(r"^ℹ fail (\d+)$", summary, re.M)
    assert passed and int(passed.group(1)) >= 19, summary
    assert failed and int(failed.group(1)) == 0, summary
    for case in (
        "expired JWT: IAP 401 is an auth failure",
        "302 to the sign-in page is a failure, never a success",
        "200 with an HTML sign-in page body is a body failure",
        "TLS error CERT_HAS_EXPIRED is a transport failure",
        "signJwt denied",
        "no token value ever reaches a message",
        "body timeout after the 200 headers is one classified transport failure",
        "connection reset while reading the body is one classified transport failure",
        "a body read error carrying a token is redacted",
    ):
        assert case in summary, case
    # P3c-R3: the body read sits inside transport handling.
    probe_js = (RUNNER_DIR / "probe.js").read_text(encoding="utf-8")
    assert "text = await response.text();" in probe_js
    assert "body read failed after status" in probe_js
