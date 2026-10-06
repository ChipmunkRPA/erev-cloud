"""Terraform compute, identity, registry, load balancer and monitoring (05 §8.3 DPL-31, DPL-33,
DPL-37, DPL-38, DPL-40 to DPL-42; §7.5 SLO table; hosted runtime contract of 2026-09-19;
BUILD_SPEC DEP-4). REQs completed: REQ-OPS-002, REQ-SEC-001.

Read as text (``support.terraform``); the loop never runs Terraform (DG-FORBID-07, DG-FORBID-12).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from support.terraform import (
    ROOT,
    all_text,
    local_value,
    read_blocks,
    resource,
    resources,
    unquote,
    variable_default,
)

WORKER_SERVICES = ("worker_compute", "worker_general")
# Supervisor documents that STATE the prohibition on state-changing Terraform subcommands, and
# therefore name them (DG-FORBID-07; 05 DPL-42; the DEP-4 acceptance text itself).
RULE_DOCUMENTS = (
    "docs/dev-guide.md",
    "docs/05-ARCHITECTURE.md",
    "docs/03-REQUIREMENTS.md",
    "docs/BUILD_SPEC.md",
)
RULE_DOCUMENT_DIRS = (
    "docs/build-spec/",
    "docs/reviews/loop/",
)  # review records quote the rule, they run nothing
# A command, not a Python `from support.terraform import` line or a path segment.
FORBIDDEN_COMMAND = re.compile(
    r"(?<![.\w/-])terraform(?:\s+-chdir=\S+)?\s+(?:plan|apply|import|destroy)\b"
)


def _service(name: str):  # noqa: ANN202
    return resource("google_cloud_run_v2_service", name)


def _container(block):  # noqa: ANN001, ANN202
    (template,) = block.nested("template")
    containers = template.nested("containers")
    if not containers:  # a job: template { template { containers } }
        (inner,) = template.nested("template")
        containers = inner.nested("containers")
        template = inner
    (container,) = containers
    return template, container


def _env_names(container) -> set[str]:  # noqa: ANN001
    names: set[str] = set()
    for env in container.nested("env"):
        for_each = env.attribute("for_each")
        if for_each:
            names.add(for_each)
    return names


def test_cloud_run() -> None:
    # DPL-31 shapes through variable defaults.
    assert unquote(variable_default("name_prefix")) == "erev"
    assert variable_default("api_min_instances") == "1"
    assert variable_default("api_max_instances") == "10"
    assert variable_default("api_concurrency") == "40"
    assert variable_default("worker_compute_min_instances") == "1"
    assert variable_default("worker_compute_max_instances") == "4"
    assert variable_default("worker_general_min_instances") == "1"
    assert variable_default("worker_general_max_instances") == "2"

    api = _service("api")
    assert unquote(api.attribute("name")) == "${local.name}-api"
    assert unquote(api.attribute("ingress")) == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    template, container = _container(api)
    assert template.attribute("max_instance_request_concurrency") == "var.api_concurrency"
    (scaling,) = template.nested("scaling")
    assert scaling.attribute("min_instance_count") == "var.api_min_instances"
    assert scaling.attribute("max_instance_count") == "var.api_max_instances"
    (api_resources,) = container.nested("resources")
    assert api_resources.attribute("cpu_idle") == "true"  # CPU always allocated OFF
    assert re.search(r'cpu\s*=\s*"2"', api_resources.body)
    assert re.search(r'memory\s*=\s*"2Gi"', api_resources.body)
    assert container.attribute("image") == "local.images.api"

    # Workers: services with an HTTP health listener, CPU always allocated, internal ingress,
    # startup and liveness probes (runtime contract §1 to §3; P3 package).
    compute_queues = local_value("compute_queues")
    assert compute_queues == '["compute", "close"]'
    general_queues = local_value("general_queues")
    assert general_queues is not None
    assert set(re.findall(r'"([a-z]+)"', general_queues)) == {
        "imports",
        "outbox",
        "reports",
        "maintenance",
        "integrations",
        "ai",
    }
    for name in WORKER_SERVICES:
        worker = _service(name)
        assert unquote(worker.attribute("ingress")) == "INGRESS_TRAFFIC_INTERNAL_ONLY", name
        template, container = _container(worker)
        (scaling,) = template.nested("scaling")
        minimum = scaling.attribute("min_instance_count")
        assert minimum == f"var.{name}_min_instances", name
        assert variable_default(f"{name}_min_instances") == "1"
        (limits,) = container.nested("resources")
        assert limits.attribute("cpu_idle") == "false", name  # CPU always allocated
        assert container.attribute("image") == "local.images.worker"
        args = container.attribute("args")
        assert args is not None and args.startswith('["worker", "--queues", '), name
        (startup,) = container.nested("startup_probe")
        (startup_get,) = startup.nested("http_get")
        assert unquote(startup_get.attribute("path")) == "/startupz"
        assert startup.attribute("period_seconds") == "5"
        assert startup.attribute("timeout_seconds") == "2"
        assert startup.attribute("failure_threshold") == "36"  # 180 s < Google's 240 s bound
        (liveness,) = container.nested("liveness_probe")
        (liveness_get,) = liveness.nested("http_get")
        assert unquote(liveness_get.attribute("path")) == "/livez"
        assert liveness.attribute("period_seconds") == "15"
        assert liveness.attribute("failure_threshold") == "4"
        (ports,) = container.nested("ports")
        assert ports.attribute("container_port") == "var.worker_health_port"
        (traffic,) = worker.nested("traffic")
        assert traffic.attribute("percent") == "100"
        assert "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST" in traffic.body
    compute = _service("worker_compute")
    _, compute_container = _container(compute)
    assert (
        compute_container.attribute("args")
        == '["worker", "--queues", join(",", local.compute_queues)]'
    )
    (compute_limits,) = compute_container.nested("resources")
    assert re.search(r'cpu\s*=\s*"4"', compute_limits.body)
    assert re.search(r'memory\s*=\s*"8Gi"', compute_limits.body)
    assert compute.attribute("timeout") is None  # the request timeout sits on the template
    template, _ = _container(compute)
    assert template.attribute("timeout") == '"${var.worker_request_timeout_seconds}s"'

    # erev-web service and the erev-migrate job.
    web = _service("web")
    assert unquote(web.attribute("name")) == "${local.name}-web"
    migrate = resource("google_cloud_run_v2_job", "migrate")
    assert unquote(migrate.attribute("name")) == "${local.name}-migrate"
    job_template, migrate_container = _container(migrate)
    assert migrate_container.attribute("args") == '["migrate"]'
    assert job_template.attribute("service_account") == "google_service_account.migrate.email"
    assert (
        "EREV_DB_OWNER_URL" in local_value("migrate_secret_env")
        or "EREV_DB_OWNER_URL" in all_text()
    )

    # Secrets through secret_key_ref with pinned versions; Direct VPC egress everywhere.
    text = all_text()
    assert re.search(r'version\s*=\s*"latest"', text) is None
    for block in resources("google_cloud_run_v2_service") + resources("google_cloud_run_v2_job"):
        refs = block.descendants("secret_key_ref")
        if block.name != "web":
            assert refs, block.name
            for ref in refs:
                assert ref.attribute("version") == "env.value.version", block.name
                assert ref.attribute("secret") == "env.value.secret", block.name
            (vpc,) = block.descendants("vpc_access")
            assert unquote(vpc.attribute("egress")) == "PRIVATE_RANGES_ONLY", block.name
            (interfaces,) = vpc.nested("network_interfaces")
            assert interfaces.attribute("subnetwork") == "google_compute_subnetwork.run_egress.id"
    versions = local_value("runtime_secret_env")
    assert versions is not None
    secret_env = "\n".join(block.body for block in read_blocks() if block.kind == "locals")
    assert "google_secret_manager_secret_version.db_app_url.version" in secret_env
    assert "var.secret_versions.smtp_password" in secret_env
    assert "var.secret_versions.metrics_token" in secret_env

    # DPL-05: images by digest variable, never by tag.
    images = local_value("images")
    assert images is not None
    for image in ("api", "worker", "web"):
        assert f"erev-{image}@${{var.image_digests.{image}}}" in secret_env, image
    assert ":latest" not in text
    digests = [
        block
        for block in read_blocks()
        if block.kind == "variable" and block.name == "image_digests"
    ]
    assert digests and "sha256:[0-9a-f]{64}" in digests[0].body


def test_iam_least_privilege() -> None:
    # DPL-33 plus the tenant-secret provisioning identity (runtime contract).
    accounts = {
        unquote(sa.attribute("account_id")): sa for sa in resources("google_service_account")
    }
    assert {"${local.name}-api", "${local.name}-worker", "${local.name}-migrate"} <= set(accounts)
    assert "${local.name}-provisioning" in accounts
    text = all_text()
    assert "roles/editor" not in text and "roles/owner" not in text
    assert "roles/secretmanager.admin" not in text

    cloudsql = resource("google_project_iam_member", "cloudsql_client")
    assert unquote(cloudsql.attribute("role")) == "roles/cloudsql.client"
    clients = local_value("cloudsql_clients")
    assert clients is not None
    locals_body = "\n".join(block.body for block in read_blocks() if block.kind == "locals")
    for identity in ("api", "worker", "migrate"):
        assert f"google_service_account.{identity}.email" in locals_body

    # Secret accessor on NAMED secrets only.
    accessor = resource("google_secret_manager_secret_iam_member", "accessor")
    assert unquote(accessor.attribute("role")) == "roles/secretmanager.secretAccessor"
    assert "google_secret_manager_secret.static[each.value.key].secret_id" in accessor.body
    assert '"db_owner_url/migrate"' in locals_body
    assert '"db_app_url/api"' in locals_body and '"db_app_url/worker"' in locals_body
    assert '"db_owner_url/api"' not in locals_body and '"db_owner_url/worker"' not in locals_body
    # Runtime tenant secrets: a conditional project-level accessor for api and worker only.
    tenant = resource("google_project_iam_member", "tenant_secret_accessor")
    (condition,) = tenant.nested("condition")
    assert "resource.name.startsWith" in condition.body
    assert "local.tenant_audit_hmac_secret_prefix" in condition.body
    # Only the provisioning identity may create tenant secrets: creation (project-scoped, creation
    # only) and initialisation (prefix-conditioned) are two roles (P3-R3; test_terraform_policy).
    creator = resource("google_project_iam_custom_role", "tenant_secret_creator")
    assert "secretmanager.secrets.create" in creator.body
    assert "secretmanager.versions.add" not in creator.body
    assert "secretmanager.versions.access" not in creator.body
    initializer = resource("google_project_iam_custom_role", "tenant_secret_initializer")
    assert "secretmanager.versions.add" in initializer.body
    assert "secretmanager.secrets.create" not in initializer.body
    for role in (creator, initializer):
        for forbidden in (
            "secretmanager.secrets.delete",
            "secretmanager.versions.destroy",
            "setIamPolicy",
        ):
            assert forbidden not in role.body, forbidden
    for binding_name, role_ref in (
        ("provisioning_creator", "google_project_iam_custom_role.tenant_secret_creator.id"),
        ("provisioning_initializer", "google_project_iam_custom_role.tenant_secret_initializer.id"),
    ):
        binding = resource("google_project_iam_member", binding_name)
        assert "google_service_account.provisioning.email" in binding.body
        assert role_ref in binding.body
        assert text.count(role_ref) == 1, role_ref
    assert resource("google_project_iam_member", "provisioning_initializer").nested("condition")

    # Storage and KMS grants.
    files_admin = resource("google_storage_bucket_iam_member", "files_object_admin")
    assert unquote(files_admin.attribute("role")) == "roles/storage.objectAdmin"
    assert files_admin.attribute("bucket") == "google_storage_bucket.files.name"
    creator = resource("google_storage_bucket_iam_member", "digests_object_creator")
    assert unquote(creator.attribute("role")) == "roles/storage.objectCreator"
    assert creator.attribute("bucket") == "google_storage_bucket.audit_digests.name"
    assert "google_service_account.worker.email" in creator.body
    kek = resource("google_kms_crypto_key_iam_member", "app_kek_users")
    assert unquote(kek.attribute("role")) == "roles/cloudkms.cryptoKeyEncrypterDecrypter"
    assert kek.attribute("crypto_key_id") == "google_kms_crypto_key.app_kek.id"
    # The digest bucket never receives objectAdmin (create-only immutability boundary).
    for member in resources("google_storage_bucket_iam_member"):
        if member.attribute("bucket") == "google_storage_bucket.audit_digests.name":
            assert unquote(member.attribute("role")) in (
                "roles/storage.objectCreator",
                "roles/storage.objectViewer",
            ), member.name


def test_load_balancer_https_only() -> None:
    # DPL-40; REQ-SEC-001.
    for name in ("api", "web"):
        neg = resource("google_compute_region_network_endpoint_group", name)
        assert unquote(neg.attribute("network_endpoint_type")) == "SERVERLESS"
        (cloud_run,) = neg.nested("cloud_run")
        assert cloud_run.attribute("service") == f"google_cloud_run_v2_service.{name}.name"
        backend = resource("google_compute_backend_service", name)
        assert unquote(backend.attribute("load_balancing_scheme")) == "EXTERNAL_MANAGED"
        assert backend.attribute("security_policy") == "google_compute_security_policy.erev.id"
        (iap,) = backend.nested("iap")
        assert "var.enable_iap" in iap.body
        assert "oauth2_client_secret" not in backend.body
    assert variable_default("enable_iap") == "false"

    resource("google_compute_managed_ssl_certificate", "erev")
    policy = resource("google_compute_ssl_policy", "modern")
    assert unquote(policy.attribute("profile")) == "MODERN"
    assert unquote(policy.attribute("min_tls_version")) == "TLS_1_2"
    https_proxy = resource("google_compute_target_https_proxy", "erev")
    assert https_proxy.attribute("ssl_policy") == "google_compute_ssl_policy.modern.id"
    assert "google_compute_managed_ssl_certificate.erev.id" in https_proxy.body

    redirect = resource("google_compute_url_map", "http_redirect")
    (url_redirect,) = redirect.nested("default_url_redirect")
    assert url_redirect.attribute("https_redirect") == "true"
    http_proxy = resource("google_compute_target_http_proxy", "redirect")
    assert http_proxy.attribute("url_map") == "google_compute_url_map.http_redirect.id"
    rules = {
        unquote(rule.attribute("port_range")): rule
        for rule in resources("google_compute_global_forwarding_rule")
    }
    assert set(rules) == {"80", "443"}
    assert rules["443"].attribute("target") == "google_compute_target_https_proxy.erev.id"
    assert rules["80"].attribute("target") == "google_compute_target_http_proxy.redirect.id"
    for rule in rules.values():
        assert unquote(rule.attribute("load_balancing_scheme")) == "EXTERNAL_MANAGED"
    https_map = resource("google_compute_url_map", "https")
    assert '"/api", "/api/*"' in https_map.body
    assert "google_compute_backend_service.api.id" in https_map.body

    # DPL-41, SAR-13: OWASP preconfigured rules in preview by default, throttle enforced.
    armor = resource("google_compute_security_policy", "erev")
    assert variable_default("cloud_armor_preview") == "true"
    assert local_value("cloud_armor_throttle_rpm") == "1000"
    throttle = [
        rule for rule in armor.nested("rule") if unquote(rule.attribute("action")) == "throttle"
    ]
    assert len(throttle) == 1
    (options,) = throttle[0].nested("rate_limit_options")
    assert unquote(options.attribute("enforce_on_key")) == "IP"
    assert unquote(options.attribute("exceed_action")) == "deny(429)"
    (threshold,) = options.nested("rate_limit_threshold")
    assert threshold.attribute("count") == "local.cloud_armor_throttle_rpm"
    assert threshold.attribute("interval_sec") == "60"
    assert "preview" not in throttle[0].body
    owasp = [
        rule
        for rule in armor.nested("rule")
        if "evaluatePreconfiguredWaf" in rule.body or rule.attribute("preview")
    ]
    assert owasp, "OWASP preconfigured rules"
    for rule in owasp:
        assert rule.attribute("preview") == "var.cloud_armor_preview"
    owasp_rules = local_value("owasp_rules")
    assert owasp_rules is not None
    locals_body = "\n".join(block.body for block in read_blocks() if block.kind == "locals")
    for family in (
        "sqli-v33-stable",
        "xss-v33-stable",
        "lfi-v33-stable",
        "rfi-v33-stable",
        "rce-v33-stable",
    ):
        assert f"evaluatePreconfiguredWaf('{family}'" in locals_body, family


def test_registry_and_monitoring() -> None:
    # DPL-38 with the G19 vulnerability-scanning amendment.
    registry = resource("google_artifact_registry_repository", "erev")
    assert unquote(registry.attribute("format")) == "DOCKER"
    (docker,) = registry.nested("docker_config")
    assert docker.attribute("immutable_tags") == "true"
    (scanning,) = registry.nested("vulnerability_scanning_config")
    assert (
        "var.vulnerability_scanning" in scanning.body
        or "var.vulnerability_scanning" in registry.body
    )
    assert variable_default("vulnerability_scanning") == "true"

    # DPL-37: uptime check on /api/v1/healthz; SLO alert policies; 400-day log bucket.
    uptime = resource("google_monitoring_uptime_check_config", "healthz")
    (http,) = uptime.nested("http_check")
    path = http.attribute("path")
    assert path is not None and '"/api/v1/healthz"' in path  # mode-dependent (P3-R1)
    assert http.attribute("use_ssl") == "true"
    policies = {policy.name: policy for policy in resources("google_monitoring_alert_policy")}
    names = {
        name: unquote(policy.attribute("display_name")) or "" for name, policy in policies.items()
    }
    for slo in ("SLO-01", "SLO-04", "SLO-05", "SLO-06"):
        assert any(display.startswith(slo) for display in names.values()), slo
    for name, policy in policies.items():
        assert policy.attribute("notification_channels") == "var.notification_channel_ids", name
    slo_01 = policies["slo_01_availability"]
    assert "run.googleapis.com/request_count" in slo_01.body
    assert 'response_code_class=\\"5xx\\"' in slo_01.body
    assert slo_01.body.count("condition_threshold") == 2  # 14.4x over 1 h and 6x over 6 h
    slo_04 = policies["slo_04_job_pickup"]
    assert "ALIGN_PERCENTILE_95" in slo_04.body
    assert slo_04.attributes("threshold_value") == ["60"]
    assert slo_04.attributes("duration") == ['"900s"']
    assert policies["slo_05_outbox_dead"].descendants("condition_matched_log")
    slo_06 = policies["slo_06_audit_chain"]
    assert slo_06.descendants("condition_matched_log")
    assert unquote(slo_06.attribute("severity")) == "CRITICAL"

    log_bucket = resource("google_logging_project_bucket_config", "erev")
    assert log_bucket.attribute("retention_days") == "local.log_retention_days"
    assert local_value("log_retention_days") == "400"
    sinks = {sink.name: sink for sink in resources("google_logging_project_sink")}
    assert "erev_logs" in sinks and "pgaudit_to_digests" in sinks
    assert "google_storage_bucket.audit_digests.name" in sinks["pgaudit_to_digests"].body
    pgaudit_filter = local_value("log_filter_pgaudit")
    assert pgaudit_filter is not None and "cloudsql_database" in pgaudit_filter


def _tracked_files() -> list[Path]:
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [ROOT / name.decode() for name in listing.split(b"\0") if name]


def _states_the_rule(relative: str) -> bool:
    if relative in RULE_DOCUMENTS:
        return True
    return any(relative.startswith(prefix) for prefix in RULE_DOCUMENT_DIRS)


def test_no_apply_commands() -> None:
    # DPL-42; DG-FORBID-07: no tracked file other than the supervisor documents that state the rule
    # contains a state-changing Terraform subcommand as a command. Binary and large fixtures are
    # skipped; the test file itself holds the pattern, not the phrase.
    offenders: list[str] = []
    this_file = Path(__file__).resolve()
    for path in _tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if path.resolve() == this_file or _states_the_rule(relative) or not path.is_file():
            continue
        if path.stat().st_size > 5 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_COMMAND.search(line):
                offenders.append(f"{relative}:{number}")
    assert offenders == [], offenders

    # The Makefile and every script name no such subcommand either (belt and braces on the
    # supervisor target and its script).
    for relative in ("Makefile", "scripts/tf_validate.sh"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert FORBIDDEN_COMMAND.search(text) is None, relative
        for word in ("plan", "apply", "import", "destroy"):
            assert re.search(rf"\bterraform\b[^\n]*\b{word}\b", text) is None, (relative, word)


def test_sar_20_hsts_is_set_by_the_load_balancer_on_every_backend() -> None:
    """05 SAR-20 rev 1.53 (R-34 SD-3): ``Strict-Transport-Security`` is sent by the tier that
    terminates TLS. Hosted that is the HTTPS load balancer: every backend service of its URL map
    adds the header, the HTTP listener only redirects, and the api itself sends none."""
    from erev_api.api.middleware import SECURITY_HEADERS

    assert local_value("hsts_response_headers") == (
        '["Strict-Transport-Security: max-age=31536000; includeSubDomains"]'
    )
    backends = resources("google_compute_backend_service")
    assert {backend.name for backend in backends} == {"api", "api_health", "web"}
    for backend in backends:
        assert backend.attribute("custom_response_headers") == "local.hsts_response_headers", (
            backend.name
        )
    # Every service the HTTPS URL map routes to is one of them.
    https_map = resource("google_compute_url_map", "https")
    routed = set(re.findall(r"google_compute_backend_service\.(\w+)(?:\[0\])?\.id", https_map.body))
    assert routed == {backend.name for backend in backends}
    # Not over plain HTTP, and not by the api (the compose stack is plain HTTP on loopback).
    redirect = resource("google_compute_url_map", "http_redirect")
    assert "Strict-Transport-Security" not in redirect.body
    assert "Strict-Transport-Security" not in SECURITY_HEADERS
