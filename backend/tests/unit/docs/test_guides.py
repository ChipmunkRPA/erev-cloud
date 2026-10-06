"""Operational guides: the release documentation contract (PHASES BS-D-13; BUILD_SPEC DEP-6,
DEP-7, DMO-11, PRF-6; 05 §7.7 RB-01 to RB-16; REQ-OPS-003, REQ-OPS-004, REQ-OPS-013, REQ-SEC-002).

BS4-D-17 places the document presence tests in ``backend/tests/unit/docs/``, and DEP-6, DEP-7,
DMO-11 and PRF-6 name their tests at this path. They were written in ``tests/unit/test_guides.py``
(lanes P6 and P8, "until the supervisor rules on the location") and moved here unchanged by lane OPS
(package of 2026-09-29); the FND-18 and FR-M tests stay in that module, the path their items name.
Shared readers: ``support.guides``.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from support.guides import GUIDES, ROOT
from support.guides import headings as _headings
from support.guides import section as _section
from support.guides import titles as _titles

# DEP-7: one section per rail area (SCREENS SCR-IA-01), the extract datasets (SCREENS_B §5.6.8),
# evidence packs, sandboxes and scenarios, AI assistance, the DMO-11 map and the demo workspaces.
RAIL_AREAS = (
    "Home",
    "Contracts",
    "Schedules",
    "Close",
    "Journals",
    "Reports",
    "Policies",
    "Data",
    "Approvals",
    "Settings",
)
USER_GUIDE_SECTIONS = (
    *RAIL_AREAS,
    "Close and lock",
    "Export journals",
    "Report runs",
    "Data extracts",
    "Evidence packs",
    "Sandboxes and scenarios",
    "AI assistance",
    "Coming from eRev desktop",
    "Demo workspaces",
)
EXTRACT_CODES = (
    "extract_contracts",
    "extract_obligations",
    "extract_contract_versions",
    "extract_schedule_lines",
    "extract_subledger_lines",
    "extract_journal_lines",
    "extract_balances",
    "extract_events",
    "extract_legacy_contract_live",
)
MIGRATION_GUIDE_SECTIONS = (
    "Mode (a): opening balances with a cutover",
    "Mode (b): replay into a sandbox, then promotion",
    "Migration reconciliation report (RPT-41)",
    "The legacy-parity preset",
    "Source file handling and SHA-256",
    "Legacy field mapping (04 §17.2)",
    "Parallel-run comparison (RPT-42)",
    "Acquired contracts and onboarding from other systems",
    "Legacy fixtures and provenance",
)
ROUTER = ROOT / "frontend" / "src" / "app" / "router.tsx"
ROUTE_LITERAL = re.compile(r'path:\s*"(/[^"]*)"')
ROUTE_CONSTANT = re.compile(r"path:\s*([A-Z][A-Z0-9_]+)\b")
CONSTANT_VALUE = re.compile(r'export const ([A-Z][A-Z0-9_]+) = "(/[^"]*)"')
# An in-app route named in a guide: a backticked absolute path of route characters; API paths
# (`/api/v1/…`) and templated paths (`{id}`) are not routes of the web application.
GUIDE_ROUTE = re.compile(r"`(/[a-z][a-z0-9\-/:]*)`")
# 05 §7.7: one runbook heading per entry; its section names its id as "Runbook entry RB-nn".
RUNBOOK_ENTRIES = {
    "RB-01": "Start and stop by PID files",
    "RB-02": "Migrations",
    "RB-03": "erev doctor",
    "RB-04": "Backup and restore",
    "RB-05": "Master-key backup and key rotation",
    "RB-06": "Restore-test procedure and record",
    "RB-07": "Job monitoring",
    "RB-08": "Chain verification failure response",
    "RB-09": "Replay verification mismatch",
    "RB-10": "Incident handling and break-glass access",
    "RB-11": "erev_owner holders and the pipeline identity",
    "RB-12": "Partition window and ANALYZE",
    "RB-13": "Locking the digest bucket retention policy",
    "RB-14": "Personal data erasure",
    "RB-15": "Adapter credentials",
    "RB-16": "Upgrade validation before a new engine release",
}
MAKE_TARGET = re.compile(r"`make ([a-z][a-z0-9-]*)")
MAKEFILE_RULE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_-]*):(?![:=])", re.MULTILINE)
# Targets the runbook documents ahead of their build, each with its DG-MK row in the dev guide:
# the PHASES §13 PRF targets (PRF-6 test_runbook_perf_storage requires `make perf-seed`) and the
# SOP-2 / DEP-5 targets lane P1 builds on sprint/l2 (release-manifest, docker-build). Remove an
# entry once its target is on main.
# Targets the runbook names before their phase ships. `docker-build` left this set when DEP-5 landed
# (lane P6, D-98 148 A2 (3)); `release-manifest` (SOP-2) stays until its owner removes it.
LATER_PHASE_TARGETS = frozenset({"perf", "perf-seed", "release-manifest"})


def test_user_guide_sections() -> None:
    """DEP-7 (REQ-OPS-004): one section per rail area, the nine extract datasets, evidence packs,
    sandboxes and scenarios, AI assistance, the desktop map and the demo workspaces."""
    titles = _titles("user-guide.md")
    for heading in USER_GUIDE_SECTIONS:
        assert heading in titles, heading
    extracts = _section("user-guide.md", "Data extracts")
    for code in EXTRACT_CODES:
        assert f"`{code}`" in extracts, code
    assert "schema_version" in extracts and "row_count" in extracts
    rail = _section("user-guide.md", "Home")
    assert "`/home`" in rail


def test_user_guide_legacy_map() -> None:
    """DMO-11 (REQ-UX-019 ART; PRD §7.1, §7.2): the 14 desktop buttons and the four templates,
    each with its eRev Cloud feature."""
    section = (GUIDES / "user-guide.md").read_text(encoding="utf-8")
    assert "## Coming from eRev desktop" in section and "## Demo workspaces" in section
    start = section.index("## Coming from eRev desktop")
    end = section.index("## Demo workspaces")
    rows = [line for line in section[start:end].splitlines() if line.startswith("| LTM-")]
    buttons = [row for row in rows if not row.startswith("| LTM-T")]
    templates = [row for row in rows if row.startswith("| LTM-T")]
    assert [row.split("|")[1].strip() for row in buttons] == [f"LTM-{n:02d}" for n in range(1, 15)]
    assert [row.split("|")[1].strip() for row in templates] == [f"LTM-T{n}" for n in range(1, 5)]
    for row in rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert cells[2] and cells[3], row  # the desktop behaviour and the eRev Cloud feature
    assert "Legacy v1: SKU SSP" in section[start:end]
    assert "`legacy_contract_modification`" in section[start:end]


def test_user_guide_demo_workspaces_keep_their_month_as_the_code_keeps_it() -> None:
    """Demo world slice A (PRD rev 1.153 WLD-P-02 and WLD-U-R2; 05 SCH-05 rev 1.163): what the
    guide's "Demo workspaces" says of the month of a demo workspace, of the persona who signs off
    and of a contract dated today is read from the code that makes it so."""
    import inspect
    from datetime import date

    from erev_api.domain.demo import personas
    from erev_api.domain.demo.avenmoor import reference
    from erev_api.domain.reference import period_auto_open

    section = _section("user-guide.md", "Demo workspaces")
    assert "tenant.c.is_demo.is_(False)" in inspect.getsource(period_auto_open.candidates)
    assert (
        "The scheduler that opens a period on its start date leaves the demo workspaces alone"
        in section
    )
    assert (
        "opens it by hand (`POST /periods/{id}/open`) or when the period before it is locked"
        in (section)
    )
    assert personas.SIGN_OFF_PERSONAS == {"maya"}
    assert "as is Maya Chen, who prepares the reconciliations of the close" in section
    # The limitation that stays: "today" is the wall clock, and the seeded rates end with September.
    assert "**Dating a contract today (known limitation).**" in section
    assert reference.COVERAGE_TO == date(2026, 9, 30)
    assert "the seeded rates end on 30 September 2026" in section
    assert set(reference.RATE_PAIRS) == {"EUR", "GBP", "JPY"}
    assert "a contract in GBP, EUR or JPY finds no exchange rate for that date" in section


def test_user_guide_demo_workspaces_say_what_a_seed_closes_when_it_is_asked() -> None:
    """Demo world item 12 (PRD rev 1.162 WLD-P-02; BUILD_SPEC CLO-22; dev-guide DG-MK-seed rev
    1.221): what the guide's "Demo workspaces" says of the seeded close — the command, the entity,
    the book, the months, who does what and the refusal — is read from the code that closes."""
    from erev_api.domain.demo import close_history, seed
    from erev_api.enums import BookCode

    section = _section("user-guide.md", "Demo workspaces")
    assert close_history.CLOSED == (("AVM-US", BookCode.ASC606),)
    assert (close_history.PERIOD_KEYS[0], close_history.PERIOD_KEYS[-1]) == (
        "FY2026-P01",
        "FY2026-P08",
    )
    assert (
        "`make seed CLOSE=1` (`erev seed demo --with-close`) also closes January to August 2026 "
        "for Avenmoor Inc. (`AVM-US`) in its primary book, `ASC606`" in section
    )
    cast = close_history.CAST
    assert (cast.preparer, cast.reviewer, cast.controller) == ("maya", "priya", "marcus")
    assert (
        "Maya Chen runs the close, exports the journal as a CSV file, records the document "
        "reference of the ledger and reconciles, Priya Raman approves the journal and reviews the "
        "reconciliations, and Marcus Webb locks the month" in section
    )
    # Without the flag nothing is closed, and the guide still says so.
    assert "its periods January to September 2026 are open" in section
    assert seed.CLOSE_REFUSED.endswith("run make seed RESET=1 CLOSE=1")
    assert "the command says so and names `make seed RESET=1 CLOSE=1`" in section


def test_migration_guide_sections() -> None:
    """DEP-7 (REQ-OPS-004; REQ-MIG-001 to 009): both modes, the reconciliation report, the preset,
    source file handling, the field mapping, the parallel run and acquired contracts."""
    titles = _titles("migration-guide.md")
    for heading in MIGRATION_GUIDE_SECTIONS:
        assert heading in titles, heading
    source = _section("migration-guide.md", "Source file handling and SHA-256")
    assert "duplicate-import" in source and "SHA-256" in source
    report = _section("migration-guide.md", "Migration reconciliation report (RPT-41)")
    assert "`migration_reconciliation`" in report and "0.0001" in report


def built_routes() -> frozenset[str]:
    """Every absolute route path of the web application's router (literals and the exported
    path constants); child segments are relative and not collected."""
    text = ROUTER.read_text(encoding="utf-8")
    constants = dict(CONSTANT_VALUE.findall(text))
    routes = set(ROUTE_LITERAL.findall(text))
    for name in ROUTE_CONSTANT.findall(text):
        assert name in constants, f"router.tsx: path constant {name} is not exported with a literal"
        routes.add(constants[name])
    return frozenset(routes)


def unbuilt_routes(text: str, routes: frozenset[str]) -> list[str]:
    named = GUIDE_ROUTE.findall(text)
    return sorted(
        {route for route in named if not route.startswith("/api/") and route not in routes}
    )


def test_guide_routes_built() -> None:
    """DEP-7: every in-app route path named in the guides exists in the router's route list
    (a guide never describes a screen the application does not route)."""
    routes = built_routes()
    assert {"/home", "/contracts", "/schedules", "/close", "/journals", "/reports"} <= routes
    assert unbuilt_routes("`/home` and `/nowhere/:id` but not `/api/v1/x`", routes) == [
        "/nowhere/:id"
    ], "negative control: an invented route must be reported"
    for name in ("user-guide.md", "migration-guide.md"):
        text = (GUIDES / name).read_text(encoding="utf-8")
        assert unbuilt_routes(text, routes) == [], name
        assert GUIDE_ROUTE.search(text), f"{name} names no in-app route"


def _runbook() -> str:
    return (GUIDES / "runbook.md").read_text(encoding="utf-8")


def test_runbook_entries() -> None:
    # DEP-6, REQ-OPS-003: one heading per RB-01 to RB-16, whose section names its entry id.
    titles = {title for level, title in _headings(_runbook()) if level >= 2}
    for entry, title in RUNBOOK_ENTRIES.items():
        assert title in titles, (entry, title)
        section = _section("runbook.md", title)
        assert f"Runbook entry {entry}" in section, (entry, title)
    assert len(RUNBOOK_ENTRIES) == 16


def test_runbook_recovery_objectives() -> None:
    # REQ-OPS-013; 05 OPR-08, OPR-12: the hosted objectives and the restore-test cadence.
    objectives = _section("runbook.md", "Recovery objectives")
    assert "RPO ≤ 15 minutes" in objectives and "RTO ≤ 4 hours" in objectives
    assert "point-in-time recovery" in objectives
    assert objectives in _section("runbook.md", "Backup and restore")
    tests = _section("runbook.md", "Restore-test procedure and record")
    assert "Quarterly" in tests and "isolated instance in a separate project" in tests
    assert "latest production backup" in tests
    assert "Annually" in tests and "full DR exercise" in tests and "cutover in staging" in tests
    assert "RTO" in tests
    # OPR-11: never in place; clone and cutover.
    restore = _section("runbook.md", "Backup and restore")
    assert "never restored in place" in restore
    assert "clone" in restore and "cut over" in restore


def test_runbook_encryption_at_rest() -> None:
    # REQ-SEC-002; 05 SAR-04: the CMEK names of the Terraform artifacts and the self-hoster's duty.
    section = _section("runbook.md", "Encryption at rest")
    assert "erev-cloudsql" in section and "erev-gcs" in section
    assert "use_cmek" in section
    assert "self-hoster is obliged to encrypt at rest" in section
    assert "database volume" in section and "backups" in section


def test_runbook_commands_exist() -> None:
    # DEP-6: every `make <target>` the runbook names is a Makefile rule, except the PRF targets
    # documented ahead of their phase, which must carry their DG-MK row in the dev guide.
    rules = set(MAKEFILE_RULE.findall((ROOT / "Makefile").read_text(encoding="utf-8")))
    dev_guide = (ROOT / "docs" / "dev-guide.md").read_text(encoding="utf-8")
    named = set(MAKE_TARGET.findall(_runbook()))
    assert named, "the runbook names no make targets"
    missing = sorted(named - rules - LATER_PHASE_TARGETS)
    assert missing == [], missing
    for target in sorted(named & LATER_PHASE_TARGETS):
        assert f"| DG-MK-{target} |" in dev_guide, target
    for target in ("backup", "restore-verify", "migrate", "doctor", "db-reset"):
        assert target in named, target


def test_runbook_perf_storage() -> None:
    # PRF-6: the reclaim procedure is `make db-reset` followed by `make perf-seed`.
    section = _section("runbook.md", "Reclaiming performance sandbox storage")
    reset, seed = section.index("`make db-reset`"), section.index("`make perf-seed`")
    assert reset < seed
    assert "perf-run-" in section


def test_runbook_production_checks_table_names_every_check() -> None:
    """RB-03: the runbook's production-checks table has one row per SAR-40 check of
    ``erev doctor``, in the order the command prints them, and its introduction counts them."""
    from erev_api.controls.doctor import CHECK_NAMES, PRODUCTION_CHECK_NAMES

    lines = (GUIDES / "runbook.md").read_text(encoding="utf-8").splitlines()
    start = lines.index("### Production checks (05 SAR-40)")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    rows = [
        match.group(1)
        for line in lines[start:end]
        if (match := re.match(r"\| `([a-z-]+)`(?: \(warning\))? \|", line))
    ]
    assert rows == list(PRODUCTION_CHECK_NAMES)
    body = _section("runbook.md", "Production checks (05 SAR-40)")
    # + index-conditions (05 SAR-40 rev 1.156)
    assert len(PRODUCTION_CHECK_NAMES) == 15 and len(CHECK_NAMES) == 6
    assert "fifteen further checks follow the six above" in body
    listed = body.split("in this order:", 1)[1].split("Outside `production`", 1)[0]
    assert re.findall(r"`([a-z-]+)`", listed) == list(PRODUCTION_CHECK_NAMES)


def test_runbook_lock_table_section() -> None:
    """05 §2.7 lock budget for operators (RB-12; SAR-40 ``lock-budget``): the requirement, where
    each deployment sets it, that only a restart applies it, and what SQLSTATE 53200 means."""
    from support.lock_budget import compose_max_locks, terraform_max_locks_floor

    assert "PostgreSQL lock table" in _titles("runbook.md")
    body = _section("runbook.md", "PostgreSQL lock table")
    assert (
        "max_locks_per_transaction × (max_connections + max_prepared_transactions) ≥ ⌊0.8 × "
        "max_connections⌋ × partition lock footprint + relations of the database"
    ) in body
    assert f"`-c max_locks_per_transaction={compose_max_locks()}`" in body
    assert f"the variable refuses less than {terraform_max_locks_floor()}" in body
    assert "**restart the server**" in body and "`pg_reload_conf()` does not apply it" in body
    assert "SQLSTATE 53200" in body and "`ERROR: out of shared memory`" in body
    assert "transaction rolls back as a whole" in body
    assert "FAIL lock-budget: max_locks_per_transaction 64 × (max_connections 100" in body
    # 04 API-C-05 rev 1.114 (ruling R-53 (5)): what the api answers, as the code answers it.
    from erev_api import problems
    from erev_api.db import errors as db_errors

    assert f"503 and `Retry-After: {problems.SERVER_UNAVAILABLE_RETRY_AFTER_SECONDS}`" in body
    assert "`http.server_unavailable`" in body and "records no result" in body
    named = sorted(db_errors.SERVER_UNAVAILABLE_STATES)
    assert "SQLSTATE class 53, " + ", ".join(f"`{state}`" for state in named) in body
    # The section lives under RB-12, whose window extensions raise the footprint.
    assert "### PostgreSQL lock table" in _section("runbook.md", "Partition window and ANALYZE")


def test_runbook_compose_section_matches_the_compose_file() -> None:
    """The compose bootstrap as the runbook tells it (05 DPL-10 to DPL-16 rev 1.53; R-34): the
    example file ships no master key and the runbook says how to generate them; owner-only
    commands run through ``migrate``, the one service with the owner URL; production refuses the
    fake email backend; cookie ``Secure`` and ``Strict-Transport-Security`` follow the TLS
    set-up."""
    import yaml

    body = _section("runbook.md", "Compose stack: start, first operator and first workspace")
    compose = yaml.safe_load((ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    holders = [
        name
        for name, service in services.items()
        if "EREV_DB_OWNER_URL" in service.get("environment", {})
    ]
    assert holders == ["migrate"]
    assert "The `migrate` service alone holds the `erev_owner` URL" in body
    for command in (
        "run --rm migrate migrate",
        "run --rm migrate idp create",
        "run --rm migrate doctor --analyze",
    ):
        assert command in body, command
    example = (ROOT / "deploy" / "compose.env.example").read_text(encoding="utf-8")
    for line in example.splitlines():
        if line and not line.startswith("#"):
            assert f"`{line.split('=', 1)[0]}`" in body, line.split("=", 1)[0]
    assert "import secrets; print(secrets.token_hex(32))" in body
    assert (
        "refuse to start on a placeholder (a key with fewer than 16 distinct byte values)" in body
    )
    assert "`production` refuses the fake email backend" in body
    assert "log event `startup.refused`" in body
    assert "`Secure` unless `EREV_PUBLIC_ORIGIN` is an `http` origin on a loopback host" in body
    assert "`Secure` exactly when" not in body
    # The fake outbox on the worker's tmpfs is gone from the procedure.
    assert ".eml" not in body and "glob.glob" not in body
    https = _section("runbook.md", "Serving over HTTPS")
    assert "Strict-Transport-Security: max-age=31536000; includeSubDomains" in https
    assert "never by the api" in https and "Do not add it at server level" in https
    email = _section("runbook.md", "Outbox and email")
    assert "Under `production` the api and the worker refuse to start on `fake`" in email
    assert "credentials are sent only inside the TLS session" in email
    # 05 SAR-15, CFG-18 rev 1.53 (ruling R-39): the operator's opt-in for a private relay.
    assert "`EREV_SMTP_PRIVATE_RELAY=true` also admits loopback" in email
    assert "relaxes neither STARTTLS nor certificate verification" in email
    assert "`EREV_SMTP_CA_FILE`" in email and "`WARN email-backend`" in email
    relay = _section("runbook.md", "A relay on the stack's own network")
    for name in (
        "EREV_COMPOSE_SMTP_PRIVATE_RELAY=true",
        "EREV_COMPOSE_SMTP_CA_FILE=/etc/erev/smtp-ca.pem",
        "-f deploy/compose.yaml -f relay.override.yaml",
        "The opt-in covers the SMTP relay only",
    ):
        assert name in relay, name
    # The override mounts the bundle into both services that read it when they start.
    # The sections above are read with their whitespace collapsed; the YAML is read as written.
    raw = (ROOT / "docs" / "guides" / "runbook.md").read_text(encoding="utf-8")
    block = raw.split("### A relay on the stack's own network\n", 1)[1]
    override = yaml.safe_load(textwrap.dedent(block.split("```yaml\n", 1)[1].split("```", 1)[0]))
    assert sorted(override["services"]) == ["api", "relay", "worker"]
    for service in ("api", "worker"):
        (mount,) = override["services"][service]["volumes"]
        assert mount.endswith(":/etc/erev/smtp-ca.pem:ro"), service


def test_runbook_restore_drill_section_matches_the_target() -> None:
    """RB-06 rehearsal (dev-guide DG-MK-restore-drill): the runbook names the target with its
    three variables, the project and the port the script uses, the report fields and the final
    lines the script writes, and says what the rehearsal does not prove."""
    body = _section("runbook.md", "Rehearsal on a throwaway server")
    script = (ROOT / "scripts" / "restore_drill.sh").read_text(encoding="utf-8")
    (project,) = re.findall(r'(?m)^PROJECT="([^"]+)"', script)
    (port,) = re.findall(r'(?m)^PORT="\$\{DRILL_PORT:-(\d+)\}"', script)
    assert f"compose project `{project}` on `127.0.0.1:{port}`" in body
    for command in (
        "make restore-drill TENANTS=avenmoor",
        "make restore-drill RESET=1",
        "make restore-drill DRILL_PORT=<port>",
        "cat .run/reports/restore-drill/report.json",
    ):
        assert command in body, command
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    gate = makefile.split("\nrestore-drill-gate:\n", 1)[1].split("\n\n", 1)[0]
    for variable in ("DRILL_PORT", "RESET", "TENANTS"):
        assert f'{variable}="$({variable})"' in gate, variable
    for field in (
        "tables_missing_in_clone",
        "tables_with_fewer_rows",
        "tables_with_more_rows",
        "restore_test_record",
        "backup.report.json",
        "restore-verify.report.json",
        "row-counts.json",
    ):
        assert field in body and field in script, field
    assert "`result` is `verified`" in body and 'write_report 0 "verified"' in script
    for fragment in (
        "of another drill",
        f"127.0.0.1:{port} is in use",
        "the clone does not hold what the source held",
    ):
        assert fragment in body, fragment
    assert "of another drill" in script and "is in use" in script
    assert "the clone does not hold what the source held" in script
    assert "never reaches `.data/backups/`" in body and ".data/backups" not in gate
    assert "not a deployment's backup" in body
    assert "`make restore-verify` of its latest backup" in body
    compose = _section("runbook.md", "Compose stack: start, first operator and first workspace")
    assert "the release manifest names another schema revision" in compose


def test_runbook_says_that_web_follows_a_recreated_api() -> None:
    """05 DPL-12 rev 1.53: nginx resolves the api upstream when it proxies. The runbook no longer
    needs a restart of ``web`` after the api container was recreated, and the documented TLS
    server carries the variable its locations pass to."""
    compose = _section("runbook.md", "Compose stack: start, first operator and first workspace")
    assert "`web` needs no restart" in compose
    assert "follows a new address within ten seconds" in compose
    https = _section("runbook.md", "Serving over HTTPS")
    assert "`set $erev_api http://api:8080;`" in https
    config = (ROOT / "deploy" / "docker" / "nginx" / "default.conf").read_text(encoding="utf-8")
    assert "resolver 127.0.0.11 valid=10s ipv6=off;" in config
    assert "    set $erev_api http://api:8080;" in config


def test_runbook_says_what_the_web_image_does_hosted() -> None:
    """05 DPL-40 rev 1.53: hosted, the load balancer routes ``/api`` to the api service, so the
    web image's proxy locations are never reached and need no setting; the runbook says so, and
    that it cannot be verified without a deployment."""
    https = _section("runbook.md", "Serving over HTTPS")
    assert "sends `/api` and `/api/*` to the api service" in https
    assert "Not verifiable without a deployment" in https
    terraform = (ROOT / "deploy" / "terraform" / "gcp" / "load_balancer.tf").read_text("utf-8")
    assert 'paths   = ["/api", "/api/*"]' in terraform
    cloud_run = (ROOT / "deploy" / "terraform" / "gcp" / "cloud_run.tf").read_text("utf-8")
    web = cloud_run.split('resource "google_cloud_run_v2_service" "web"', 1)[1].split(
        "\nresource ", 1
    )[0]
    assert 'ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"' in web
    assert "env {" not in web, "the hosted web service sets no variable: the image needs none"


def test_runbook_building_images_row() -> None:
    """Rulings R-53 (4) and R-37 (b) (05 DPL-05, SAR-33 rev 1.53): the operator reads that the build
    target leaves the checkout alone, that the compose path still needs the root manifest, and what
    a hardening failure means; the evidence column names the new report field."""
    lines = (GUIDES / "runbook.md").read_text(encoding="utf-8").splitlines()
    (row,) = [line for line in lines if line.startswith("| Building images |")]
    assert "neither reads nor writes `release-manifest.json` at the repository root" in row
    assert "under the run directory" in row
    assert "`make release-manifest EMBEDDED=1`" in row and "`docker compose build`" in row
    assert "`pip`" in row and "setuid or setgid" in row and "`hardening`" in row
    assert "`hardened`" in row.rsplit(" | ", 1)[1]


def test_runbook_says_that_operator_commands_refuse_and_where_commands_log() -> None:
    """05 SAR-40 and OPR-20 rev 1.53 (rulings R-53 (6) and R-37 (c)): the runbook quotes the
    refusal's closing line as the CLI prints it, names the exempt commands, and says where a
    command's log lines go."""
    from erev_api import cli

    compose = _section("runbook.md", "Compose stack: start, first operator and first workspace")
    assert f"`{cli.STARTUP_REFUSED}`" in compose
    assert f"exit {cli.STARTUP_REFUSED_EXIT}" in compose
    assert "`erev doctor` and `erev verify` always run" in compose
    assert "`erev migrate` is not refused" in compose
    assert "writes its log lines as JSON on stderr" in compose
    checks = _section("runbook.md", "Production checks (05 SAR-40)")
    assert "operator commands other than `erev doctor` and `erev verify`" in checks


def test_runbook_environment_block_generates_the_database_passwords() -> None:
    """05 DPL-10 rev 1.53 (ruling R-53 (6)): the role-init script refuses the example's
    placeholders, so the block the runbook gives for a local stack generates the three passwords
    as well as the three keys, and the table quotes the refusal as the script raises it."""
    raw = (GUIDES / "runbook.md").read_text(encoding="utf-8")
    section = raw.split("### The environment file", 1)[1].split("### Start", 1)[0]
    (block,) = re.findall(r"```sh\n(.*?)```", section, re.S)
    loops = re.findall(r"for name in ([A-Z_ ]+); do\n  sed [^\n]*secrets\.(\w+)\((\d+)\)", block)
    assert loops == [
        (
            "EREV_COMPOSE_ENCRYPTION_KEY EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY "
            "EREV_COMPOSE_SECURITY_EVENT_HMAC_KEY",
            "token_hex",
            "32",
        ),
        (
            "EREV_COMPOSE_POSTGRES_PASSWORD EREV_COMPOSE_OWNER_PASSWORD EREV_COMPOSE_APP_PASSWORD",
            "token_urlsafe",
            "24",
        ),
    ]
    script = (ROOT / "deploy" / "compose" / "initdb" / "01-roles.sql").read_text(encoding="utf-8")
    (refusal,) = re.findall(r"RAISE EXCEPTION '([^']*change-me[^']*)'", script)
    assert f"`{refusal}`" in section
    assert "remove the volume (`docker compose … down -v`)" in section
    # 05 DPL-10 rev 1.106 (item 6 of ruling R-108 (b)): what the operator sees next is the
    # database's own health check, a sign-in as the application role - read from compose.yaml,
    # with the time it takes to give up.
    import yaml

    compose = yaml.safe_load((ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8"))
    check = compose["services"]["postgres"]["healthcheck"]
    probe = check["test"]
    assert probe[1] == "psql" and probe[probe.index("-U") + 1] == "erev_app"
    assert probe[probe.index("-d") + 1] == "erev"
    assert "The health check signs in as `erev_app` on `erev` and cannot" in section
    seconds = {key: int(str(check[key]).removesuffix("s")) for key in ("interval", "start_period")}
    assert seconds["start_period"] + check["retries"] * seconds["interval"] == 160
    assert "after about two and a half minutes the container is `unhealthy`" in section
    assert "`dependency failed to start: container <project>-postgres-1 is unhealthy`" in section
    assert compose["services"]["migrate"]["depends_on"] == {
        "postgres": {"condition": "service_healthy"}
    }
    assert "`migrate`, the api, the worker and the web are not started" in section


def test_runbook_explains_the_task_row_a_dead_attempt_leaves() -> None:
    """05 JOB-06 rev 1.53 (ruling R-37 (e)): the ``doing`` Procrastinate row of an attempt whose
    worker died is documented as inert, with the query that lists such rows; the facts it rests on
    are read from the code and from Procrastinate's schema."""
    section = _section("runbook.md", "Stuck and failed jobs")
    assert (
        "keeps status `doing` for good" in section and "It is inert and needs no action" in section
    )
    assert "where t.status = 'doing' and not exists" in section
    assert "j.procrastinate_job_id = t.id" in section
    assert "ten minutes without an update" in section
    # The ten-minute rule and the replacement by a new task (jobs/sweeper.py, jobs/registry.py).
    from erev_api.jobs import sweeper

    assert sweeper.STALL_AGE.total_seconds() == 600
    registry = (ROOT / "backend" / "erev_api" / "jobs" / "registry.py").read_text("utf-8")
    settle = registry.split("def fail_attempt(", 1)[1].split("\ndef ", 1)[0]
    assert "dispatch(" in settle and "retry_job_by_id" not in settle, "a new task, not in place"
    # No Procrastinate `lock` is in use, and the queueing lock binds `todo` rows only.
    sources = [registry, (ROOT / "backend" / "erev_api" / "worker.py").read_text("utf-8")]
    assert not any(re.search(r"[(,]\s*lock\s*=", source) for source in sources)
    import procrastinate

    schema = (Path(procrastinate.__file__).parent / "sql" / "schema.sql").read_text("utf-8")
    assert (
        "CREATE UNIQUE INDEX procrastinate_jobs_queueing_lock_idx_v1 ON procrastinate_jobs "
        "(queueing_lock) WHERE status = 'todo';" in schema
    )


def test_runbook_names_where_the_connection_url_rule_is_enforced() -> None:
    """05 SAR-40 rev 1.53 with SAR-15 rev 1.54 (rulings R-39 (1), R-45 (c)): ``integration-urls`` is
    a rollout gate; the runbook says where the rule is enforced instead, and the refusal it
    describes is the integrations module's."""
    checks = _section("runbook.md", "Production checks (05 SAR-40)")
    assert "`integration-urls` is not applied at startup" in checks
    assert (
        "cannot be created or updated with a base URL that is not a public `https` address"
        in checks
    )
    assert "422 `validation-failed` on `base_url`" in checks
    from erev_api.domain.integrations import commands

    assert commands.BASE_URL_REFUSED.startswith("Enter a public https address as the base URL")
    assert commands.base_url_refusal("https://10.0.0.8/api") is not None
    assert commands.base_url_refusal("https://api.provider.example") is None


def test_runbook_tells_the_operator_how_to_issue_the_first_invitation_again() -> None:
    """04 §14.3 step 5 rev 1.114 (ruling R-37 (d)): the runbook names the command as the CLI
    registers it, what it prints, its evidence and its refusals."""
    from erev_api import cli

    section = _section("runbook.md", "Tenant provisioning")
    assert "`erev tenant resend-invitation --code <code> --admin <email>`" in section
    registered = [info.name for info in cli.tenant_app.registered_commands]
    assert registered == ["create", "resend-invitation"]
    assert "`{admin_membership_id, invitation_expires_at, tenant: {code, id}}`" in section
    assert "`tenant_membership.resend_invitation` by principal kind `OPERATOR`" in section
    assert "422 `validation-failed`" in section and "409 `invalid-transition`" in section
    assert "stops working at once" in section


def test_runbook_says_that_up_runs_migrate_again_and_how_to_avoid_it() -> None:
    """Ruling R-53 (9), observed on the stack: ``docker compose … up -d worker`` starts the
    service's dependencies, and ``api`` and ``worker`` depend on the one-shot ``migrate`` job, so
    it runs again first. The runbook says what that run does and names ``--no-deps``."""
    import yaml

    compose = yaml.safe_load((ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8"))
    for service in ("api", "worker"):
        depends = compose["services"][service]["depends_on"]
        assert depends["migrate"] == {"condition": "service_completed_successfully"}, service
    assert compose["services"]["migrate"]["restart"] == "no"
    section = _section("runbook.md", "Compose stack: start, first operator and first workspace")
    assert "runs the one-shot `migrate` job again before it starts the service" in section
    assert "the run changes nothing and exits 0" in section
    assert "`docker compose … up -d --no-deps worker`" in section
    # And what writes the root manifest since rev 1.53 (R-53 (4)).
    assert "`make docker-build` does not: it keeps its manifest under the run directory" in section
    assert "the three keys and three database passwords it generates for the run" in section


def test_runbook_says_that_a_hosted_sandbox_copy_fails_closed() -> None:
    """Ruling R-60 (d), item OPS-SBX-KEY-1: until the hosted identity that creates a sandbox
    workspace's audit key is decided, the runbook says the copy fails closed and why. The reason
    is read from the Terraform text: only the provisioning identity holds the creating role."""
    section = _section("runbook.md", "Sandbox copies on a hosted deployment")
    assert "a hosted sandbox copy fails closed" in section and "OPS-SBX-KEY-1" in section
    assert "Not verifiable without a deployment" in section
    terraform = (ROOT / "deploy" / "terraform" / "gcp" / "main.tf").read_text(encoding="utf-8")
    holders = re.findall(
        r'resource "google_project_iam_member" "(\w+)" \{[^}]*?'
        r"role\s*=\s*google_project_iam_custom_role\.tenant_secret_creator\.id[^}]*?"
        r'member\s*=\s*"serviceAccount:\$\{google_service_account\.(\w+)\.email\}"',
        terraform,
    )
    assert holders == [("provisioning_creator", "provisioning")]
    assert "`provisioning_creator` and `provisioning_initializer`" in section
    # Lane F-SNP's SNP-3 (05 SBX-02, SBX-07): every job that makes a sandbox workspace asks for
    # its key the same way, and the refusal the section quotes is the one the code raises.
    from erev_api.domain.platform import sandboxes

    refusal = sandboxes.key_provisioning_denied()
    assert (refusal.slug, refusal.status) == ("precondition-failed", 412)
    assert [error.rule_id for error in refusal.errors] == [sandboxes.RULE_KEY_DENIED]
    assert f"412 `precondition-failed`, rule `{sandboxes.RULE_KEY_DENIED}`" in section
    quoted = sandboxes.KEY_DENIED.split(" No workspace was created")[0]
    assert quoted.endswith("is not allowed to create one.") and f'"{quoted}"' in section
    assert "sandbox copies, restores and empty resets are unavailable" in section
    assert "creates no tenant and no secret, and leaves nothing to clean up" in section


def test_runbook_not_now_answers_are_those_of_the_code() -> None:
    """Runbook "Requests answered 409 lock-conflict, 409 period-closed or 503" (dev-guide
    DG-KRN-IDEM-03 and DG-KRN-ERR-06 rev 1.127; supervisor rulings R-94 (e), R-97 (6), R-103 (c)):
    the answers the section names, their ``Retry-After`` values, the log lines an operator is
    sent to and the two limits it quotes are read from the code that produces them."""
    import inspect

    from erev_api import problems, uow
    from erev_api.api import deps
    from erev_api.db import session
    from erev_api.domain.reference import period_auto_open

    section = _section(
        "runbook.md", "Requests answered 409 lock-conflict, 409 period-closed or 503"
    )
    assert deps.UNSTORED_SLUGS == {"lock-conflict", "period-closed"}
    for slug in deps.UNSTORED_SLUGS:
        assert f"| 409 `{slug}`" in section and problems.PROBLEMS[slug].status == 409
    assert "None of them is kept for the request's `Idempotency-Key`" in section
    unnamed, named = (
        problems.SERVER_UNAVAILABLE_RETRY_AFTER_SECONDS,
        problems.STATEMENT_TIMEOUT_RETRY_AFTER_SECONDS,
    )
    assert f"| 503 with `Retry-After: {unnamed}` and no problem slug" in section
    assert f"| 503 `statement-timeout` with `Retry-After: {named}`" in section
    assert problems.PROBLEMS["statement-timeout"].status == 503
    assert f"`driver_error_class` `{problems.POOL_TIMEOUT_CLASS}`" in section
    handlers = inspect.getsource(problems)
    for event in ("http.server_unavailable", "http.statement_timeout"):
        assert f"`{event}`" in section and f'"{event}"' in handlers
    tick = inspect.getsource(period_auto_open)
    assert set(period_auto_open.NOT_NOW_EVENTS) == {"lock-conflict", "statement-timeout"}
    for event in (*period_auto_open.NOT_NOW_EVENTS.values(), "period_auto_open.refused"):
        assert f"`{event}`" in section and f'"{event}"' in tick
    assert "a period opens only after the one before it" in section
    # The tick's re-deferral of a failed re-marking job is isolated on the same two answers.
    assert set(period_auto_open.REDEFER_NOT_NOW_EVENTS) == set(period_auto_open.NOT_NOW_EVENTS)
    for event in period_auto_open.REDEFER_NOT_NOW_EVENTS.values():
        assert f"`{event}`" in section and f'"{event}"' in tick
    # Every other failure of one opening or one deferral is passed over too (05 SCH-05 rev 1.106;
    # supervisor ruling R-118 (k)); only the server's own state ends the run.
    assert (period_auto_open.FAILED_EVENT, period_auto_open.REDEFER_FAILED_EVENT) == (
        "period_auto_open.failed",
        "period_open_redirty.failed",
    )
    assert (
        "is logged at error level — `period_auto_open.failed` or `period_open_redirty.failed`, "
        "with the period or period state and the error's class — and the run goes on with the "
        "others" in section
    )
    assert (
        "Only when the database cannot serve at all (the errors answered 503 without a slug, "
        "above) does the run end" in section
    )
    assert "error_class=type(error).__name__" in tick
    # 05 SCH-05 rev 1.139 (supervisor ruling of 2026-10-01 on R-118 (k)): a workspace whose due
    # periods or failed re-marking jobs cannot be read is skipped for that step, and every error
    # line of the run names the place its error was raised.
    assert (period_auto_open.READ_FAILED_EVENT, period_auto_open.REDEFER_READ_FAILED_EVENT) == (
        "period_auto_open.read_failed",
        "period_open_redirty.read_failed",
    )
    assert (
        "the run logs `period_auto_open.read_failed` or `period_open_redirty.read_failed` at "
        "error level with the workspace, leaves that step out for it and goes on with the next "
        "workspace; `period_auto_open.completed` counts such workspaces in `tenants_skipped`"
        in section
    )
    assert period_auto_open.AutoOpenReport().tenants_skipped == 0
    assert (
        "Each of these error lines carries `error_class` and `error_at`, the module and line of "
        "the code where the error was raised, and never the error's message" in section
    )
    assert tick.count("error_at=raised_at(error)") == 3
    # The two limits the section quotes: the lock timeout and a unit of work's statement timeout.
    assert "(10 seconds; rule `LOCK_TIMEOUT`)" in section
    assert inspect.signature(session.tenant_session).parameters["lock_timeout_ms"].default == 10_000
    assert "at the 60-second limit of a unit of work" in section
    assert inspect.signature(uow.unit_of_work).parameters["statement_timeout_ms"].default == 60_000
    # R-94 (e): a refused or conflicting lock decision is decided again; nothing is gated.
    assert "is simply decided again" in section
    assert "There is no gate on imports or posting jobs in progress" in section
    # The coverage guard's refusal is another 409, and that one IS kept: a new key is needed.
    assert "rule `S15-R-18c`" in section and "a new `Idempotency-Key`" in section
    assert "invalid-transition" not in deps.UNSTORED_SLUGS


def test_runbook_names_the_re_marking_job_as_the_code_does() -> None:
    """Lane FIX-D2's CLO-LOCK-OPEN-REDIRTY-1 (supervisor rulings R-101 (a), R-106 (a); 05 SCH-06
    and §5.6 rev 1.79), written into the runbook by lane OPS: the gate's name and reading, the job
    kind and its attempts, the log event of the scheduler's re-deferral and the retry profile
    line are read from the code."""
    import inspect

    from erev_api.domain.close import gates
    from erev_api.domain.platform import provisioning
    from erev_api.domain.reference import period_auto_open, period_redirty_job
    from erev_api.enums import JobKind

    section = _section("runbook.md", "Re-marking after a lock opened the next period")
    assert period_redirty_job.JOB is JobKind.PERIOD_OPEN_REDIRTY
    assert f"`GET /api/v1/jobs?kind={JobKind.PERIOD_OPEN_REDIRTY.value}`" in section
    assert period_redirty_job.RETRY.max_attempts == 3 and "queue `close`, 3 attempts" in section
    assert f'reads "{gates.REMARK_PENDING_DETAIL}"' in section
    assert dict(provisioning.SYSTEM_CLOSE_GATES)["NO_DIRTY_GROUPS"] == "All contracts computed"
    assert 'gate "All contracts computed"' in section
    assert "`period_open_redirty.redeferred`" in section
    assert '"period_open_redirty.redeferred"' in inspect.getsource(period_auto_open)
    assert "the period cannot be locked until one job succeeds" in section
    jobs = _section("runbook.md", "Stuck and failed jobs")
    assert "`AUDIT_CHAIN_VERIFY` and `PERIOD_OPEN_REDIRTY` 3 attempts" in jobs


def test_runbook_says_that_hosted_adapter_secrets_are_not_granted() -> None:
    """Item OPS-IAM-ADAPTER-SECRETS-1 (supervisor ruling R-108 (b) (4)): the first release ships
    no live adapter, so no hosted identity reads the workspace namespace of 05 KEY-09 and a hosted
    connection fails closed. The runbook says so, and the reason is read from the Terraform text:
    the only name prefix an IAM condition admits is the tenant audit keys'."""
    section = _section("runbook.md", "Adapter credentials")
    assert "OPS-IAM-ADAPTER-SECRETS-1" in section and "fails closed there" in section
    assert "Do not grant it by hand" in section and "Not verifiable without a deployment" in section
    terraform = (ROOT / "deploy" / "terraform" / "gcp" / "main.tf").read_text(encoding="utf-8")
    admitted = set(re.findall(r"/secrets/\$\{local\.(\w+)\}", terraform))
    assert admitted == {"tenant_audit_hmac_secret_prefix"}
    assert 'tenant_audit_hmac_secret_prefix = "${var.secret_prefix}audit-hmac-"' in terraform
    # Lane F-SNP's SNP-4 (05 SBX-08; 04 DB-15): a sandbox holds no secret of its own.
    assert "nobody provisions secrets under `tenant-<sandbox tenant id>-`" in section
    assert "nothing in a sandbox can use one" in section and "(05 SBX-08; 04 DB-15)" in section


def test_runbook_job_events_that_isolate_a_failure_name_its_place() -> None:
    """dev-guide DG-KRN-JOB-06 rev 1.183 (supervisor ruling of 2026-10-01 on R-118 (k)): the
    fan-out's and the sweeper's isolation events carry the class of the exception and the place
    it was raised, as the period tick's do; the runbook says so, and the fields are read from the
    code that logs them."""
    import inspect

    from erev_api.jobs import registry, sweeper

    section = _section("runbook.md", "Job monitoring")
    assert sweeper.SWEEP_FAILED == "job.sweep_failed"
    assert '"job.fan_out_failed"' in inspect.getsource(registry)
    for event in ("job.fan_out_failed", sweeper.SWEEP_FAILED):
        assert f"`{event}`" in section
    isolation = inspect.getsource(registry.isolated)
    assert "error_class=type(error).__name__" in isolation
    assert "error_at=raised_at(error)" in isolation
    assert (
        "Both lines carry `error_class` and `error_at`, the module and line of the code where the "
        "error was raised, and never its message" in section
    )


def test_runbook_tells_a_job_that_is_passed_over_and_what_ends_it() -> None:
    """05 JOB-06 rev 1.200 (item JOB-STALL-COMMIT-RACE-1): RB-07 says how an operator reads a
    job the sweeper passes over and what ends it, and no longer says of a failed job or a
    stopped attempt what the job's row alone could tell. The line's name and fields and the
    key of the lock are read from the code; the statement the runbook gives is followed as
    written in ``tests/domain/platform/test_job_stall_rule.py``."""
    import inspect
    from uuid import UUID

    from erev_api.jobs import registry
    from erev_api.jobs.context import unit_lock_key

    section = _section("runbook.md", "Stuck and failed jobs")
    settle = inspect.getsource(registry.fail_attempt)
    assert '"job.sweep_passed_over"' in settle
    assert "`job.sweep_passed_over` (info level)" in section
    for field in ("job_id", "job_kind", "attempt", "silent_seconds"):
        assert f"{field}=" in settle, field
        assert f"`{field}`" in section, field
    assert "is passed over, not stopped" in section
    assert unit_lock_key(UUID(int=0)) == f"erev-job-unit:{UUID(int=0)}"
    assert "hashtextextended('erev-job-unit:<job id>', 0)" in section
    assert "l.mode = 'ShareLock'" in section
    assert "`select pg_terminate_backend(<pid>)`" in section
    assert "no alert is raised for it: the log line is the signal" in section
    assert '"job.attempt_lost"' in inspect.getsource(registry)
    assert "`job.attempt_lost` (warning)" in section
    # The two sentences that were true of the job's row and not of its work.
    assert "records nothing when it returns" not in section
    monitoring = _section("runbook.md", "Job monitoring")
    assert "start the operation anew once the cause is fixed" not in monitoring
    assert "read the record the job worked on" in monitoring


def test_runbook_says_what_bounds_a_demo_seed() -> None:
    """Item AUDIT-LIST-PLAN-1 (the supervisor's word of 2026-10-02): a demo seed is bounded by 60
    seconds a statement, and on a server starved of CPU the first statement to meet the limit
    reads a partitioned table. The limit and the number of partitions are read from the code."""
    import inspect

    from erev_api import uow
    from erev_api.db import migration_ops as ops

    section = _section("runbook.md", "Reset the dev database")
    assert "A demo seed runs every statement under the 60 seconds of a unit of work" in section
    assert inspect.signature(uow.unit_of_work).parameters["statement_timeout_ms"].default == 60_000
    assert "hold 181 partitions each, one a month and a default" in section
    with ops.recording() as statements:
        ops.create_monthly_partitions("audit_event")
    assert len(statements) == 181
    assert "`canceling statement due to statement timeout`" in section
    assert "seed again from a reset (`make seed RESET=1`)" in section


def _runbook_row(first_cell: str) -> str:
    """The one table row of the runbook whose first cell is ``first_cell``."""
    (row,) = [line for line in _runbook().splitlines() if line.startswith(f"| {first_cell} |")]
    return row


def test_runbook_tells_the_operator_how_to_change_a_providers_domains() -> None:
    """05 SAR-27 rev 1.156 with 04 T-PLT-03 rev 1.217 (item OPS-IDP-DOMAINS-1): the runbook
    names the command as the CLI registers it, what it prints and its evidence as the code
    writes them, and the bounds the code refuses by."""
    from erev_api import cli
    from erev_api.auth import oidc

    row = _runbook_row("Change a provider's domains")
    assert (
        "`backend/.venv/bin/erev idp domains --code <code> [--add <domain> …] "
        "[--remove <domain> …]`" in row
    )
    registered = [info.name for info in cli.idp_app.registered_commands]
    assert registered == [
        "list",
        "create",
        "invite",
        "domains",
        "disable",
        "enable",
        "end-sessions",
    ]
    assert oidc.DOMAINS_COMMAND == "idp.domains"
    assert f"`detail.command` `{oidc.DOMAINS_COMMAND}`" in row
    for member in ("added", "removed", "identities_outside"):
        assert f"`{member}`" in row, member
    assert "The provider keeps 1 to 20 domains" in row
    assert oidc.DOMAINS_COUNT == "An identity provider keeps 1 to 20 email domains."
    assert "the change holds from the next sign-in" in row
    assert "Refused with exit 1 and rule `T-PLT-03`" in row
    # The row stands with the other commands of the provider, behind the invitation.
    lines = _runbook().splitlines()
    assert lines.index(row) == lines.index(_runbook_row("Invite an identity")) + 1
    # The row of the provider's creation said that no command changes its domains.
    created = _runbook_row("Add a provider")
    assert "has no command" not in created
    assert "until `erev idp domains --add` binds it to one" in created


def test_runbook_tells_the_operator_where_to_read_a_providers_code() -> None:
    """05 SAR-27 rev 1.201 (a rider of item INVITE-ACCEPT-SESSION-1): the other ``erev idp``
    commands take a provider's code and name none when they refuse an unknown one. The runbook
    names the command that lists the providers as the CLI registers it, the role it connects
    as and the members it prints as the code returns them, before the rows of the commands that
    take a code."""
    import inspect

    from erev_api import cli
    from erev_api.auth import oidc

    row = _runbook_row("List the providers")
    assert "`backend/.venv/bin/erev idp list` connects as `erev_app`" in row
    assert [info.name for info in cli.idp_app.registered_commands][0] == "list"
    source = inspect.getsource(oidc.list_providers)
    members = ("code", "kind", "display_name", "issuer_url", "email_domains", "is_enabled")
    for member in members:
        assert f'"{member}":' in source, member
        assert f"`{member}`" in row, member
    assert source.count('":') == len(members) + 1  # the members and the list that holds them
    assert "`providers`" in row and '"providers":' in source
    # A read as the application's role: no owner connection, no event.
    assert "identity_session(" in source and "owner_engine" not in source
    assert "record_security_event" not in source
    assert "writes no row and leaves no event" in row
    lines = _runbook().splitlines()
    assert lines.index(row) == lines.index(_runbook_row("Add a provider")) - 1


def test_runbook_tells_the_operator_how_to_take_a_provider_out_of_sign_in() -> None:
    """05 SAR-27 rev 1.156 with 04 T-PLT-03 rev 1.217 (item OPS-IDP-DOMAINS-1 with the
    supervisor's ruling of 2026-10-01): the runbook names the two commands as the CLI registers
    them, what a disabled provider answers, the evidence as the code writes it and what stays
    as it is; the callback's refusals name the disabled provider, and the operator commands
    that refuse a failing startup subset name the ``idp`` commands as a family."""
    from erev_api import cli
    from erev_api.auth import oidc

    row = _runbook_row("Take a provider out of sign-in")
    assert "`backend/.venv/bin/erev idp disable --code <code>`" in row
    assert "`erev idp enable --code <code>` puts the provider back" in row
    registered = [info.name for info in cli.idp_app.registered_commands]
    assert registered[-3:-1] == ["disable", "enable"]
    assert (oidc.DISABLE_COMMAND, oidc.ENABLE_COMMAND) == ("idp.disable", "idp.enable")
    assert f"`detail.command` `{oidc.DISABLE_COMMAND}` or `{oidc.ENABLE_COMMAND}`" in row
    assert f"`detail.reason` `{oidc.PROVIDER_DISABLED}`" in row
    assert "its start route answers 404 `not-found`" in row
    assert (
        "its callback answers 401 `unauthenticated` without sending anything to the provider" in row
    )
    assert "sign in with their passwords" in row
    assert "stays open until it ends or expires" in row
    lines = _runbook().splitlines()
    assert lines.index(row) == lines.index(_runbook_row("Change a provider's domains")) + 1
    refusal = _runbook_row("Refusal")
    assert "so does the callback of a provider the operator disabled" in refusal
    assert f"`{oidc.PROVIDER_DISABLED}`" in refusal
    compose = _section("runbook.md", "Compose stack: start, first operator and first workspace")
    assert (
        "`operator create`, the `idp` commands, `support-grant request`, `restore-applied`, "
        "`seed demo` and `perf seed` print the `FAIL` lines" in compose
    )


def test_runbook_tells_the_operator_what_to_do_with_a_provider_that_cannot_be_trusted() -> None:
    """05 SAR-27 rev 1.178 with 04 T-PLT-08 rev 1.249 (item OPS-IDP-SESSIONS-1): the runbook
    names the command that ends a disabled provider's sessions as the CLI registers it, the role
    it connects as, its answer and its evidence as the code writes them, and what it refuses;
    the row of the disable points at it; and the incident's row names the two commands in
    their order and the three reads that follow, each by a name the code has."""
    from erev_api import cli
    from erev_api.api.v1.audit import EVENT_LIST
    from erev_api.auth import oidc
    from erev_api.enums import SecurityEventKind, SessionEndReason

    row = _runbook_row("End the sessions of a disabled provider")
    assert "`backend/.venv/bin/erev idp end-sessions --code <code>` connects as `erev_app`" in row
    registered = [info.name for info in cli.idp_app.registered_commands]
    assert registered[-3:] == ["disable", "enable", "end-sessions"]
    assert oidc.END_SESSIONS_COMMAND == "idp.end-sessions"
    assert f"`detail.command` `{oidc.END_SESSIONS_COMMAND}`" in row
    for member in ("provider", "identities", "sessions_ended"):
        assert f"`{member}`" in row, member
    assert f"`end_reason` `{SessionEndReason.REVOKED.value}`" in row
    assert "A session the same person opened with a password stays" in row
    assert "Refused with exit 1 and rule `T-PLT-03`: an unknown provider, and a provider" in row
    assert "and a provider that is enabled" in row
    assert "A second run ends nothing and is answered as done" in row
    lines = _runbook().splitlines()
    disable = _runbook_row("Take a provider out of sign-in")
    assert lines.index(row) == lines.index(disable) + 1
    assert "unless `erev idp end-sessions` ends it" in disable
    assert "refused as well, with `LOGIN_FAILED` on the identity" in disable
    incident = _runbook_row("A provider that can no longer be trusted")
    assert lines.index(incident) == lines.index(row) + 1
    assert "Disable it, then end its sessions" in incident
    for kind in (SecurityEventKind.LOGIN_SUCCEEDED, SecurityEventKind.MFA_ENROLLED):
        assert f"`{kind.value}`" in incident, kind
    assert "`GET /api/v1/audit-events?actor_id=<user id>&from=<time>`" in incident
    assert {"actor_id", "from"} <= set(EVENT_LIST.filters)
    assert "it cannot set or change a password, which asks for the current one" in incident


def test_runbook_says_what_a_development_database_is() -> None:
    """dev-guide DG-ENV-13 rev 1.200 (supervisor ruling R-120 (i)): ``make db-reset`` resets
    the development database the environment names; the runbook says what makes a database one
    and quotes the refusal as the command prints it. The ITGC guide says the same of resets."""
    from erev_api.config import Environment
    from erev_api.controls import reset

    section = _section("runbook.md", "Reset the dev database")
    assert "in the development database the environment names, as `erev_owner`" in section
    assert (
        "A development database is `erev` or an `erev_rv_*` database under `EREV_ENV=dev` in "
        "which every tenant carries the demo marker (a sandbox counts by its source)" in section
    )
    assert f"`{reset.refused_for_tenants('<database>', 1)}`" in section
    assert "and drops nothing" in section
    assert "It never touches `erev_test` or `erev_e2e`" in section
    for database, resettable in (
        ("erev", True),
        ("erev_rv_l2_dev", True),
        ("erev_test", False),
        ("erev_e2e", False),
    ):
        refusal = reset.refused_before_connecting(Environment.DEV, database)
        assert (refusal is None) is resettable, (database, refusal)
    assert reset.refused_before_connecting(Environment.TEST, "erev") is not None
    itgc = (GUIDES / "itgc-guide.md").read_text(encoding="utf-8")
    assert (
        "through `make db-reset` in the dev environment on a development database: `erev` or an "
        "`erev_rv_*` database in which no tenant lacks the demo marker (DG-ENV-13)" in itgc
    )


def test_runbook_index_conditions_row_reads_as_the_catalogue_check_words_it() -> None:
    """05 SAR-40 rev 1.156 (§2.7; 04 NC-20; dev-guide DG-KRN-DB-10): ``index-conditions`` is
    the last production check and a warning. The runbook names the two forms of its line as the
    catalogue check words them, says that the command still exits 0, gives the remedy, and
    lists the index keys among what the command collects."""
    from erev_api.controls.doctor import (
        PRODUCTION_CHECK_NAMES,
        IndexConditionsObservation,
        index_conditions,
    )
    from erev_api.db.index_conditions import ALLOWED, IndexFinding, findings

    assert PRODUCTION_CHECK_NAMES[-1] == "index-conditions"
    checks = _section("runbook.md", "Production checks (05 SAR-40)")
    assert "`master-keys` and the warning-only `index-conditions`" in checks
    assert (
        "and the index keys (what the catalogue check of 04 NC-20 answers for the indexes of the "
        "tables with a row-level-security policy, read as `erev_app`" in checks
    )
    row = _runbook_row("`index-conditions` (warning)")
    # The two forms of a line: an index the check names by its table, and an entry of its list.
    assert "the line names `<table>.<index>` and why" in row
    assert str(IndexFinding("contract", "ix_by_hand", "why")) == "contract.ix_by_hand: why"
    assert "the line starts with `-.<index>`" in row

    class _NoIndex:
        """A schema without any index of a table with a policy: every entry of the list is one
        the schema does not have."""

        def execute(self, statement: object) -> list[object]:
            return []

    missing = tuple(str(finding) for finding in findings(_NoIndex()))  # type: ignore[arg-type]
    assert len(missing) == len(ALLOWED) and all(line.startswith("-.") for line in missing)
    warned = index_conditions(IndexConditionsObservation(missing, len(ALLOWED)))
    assert warned.ok
    assert all(line.startswith("WARN index-conditions: -.") for line in warned.lines())
    assert "The command still exits 0 and a rollout goes on" in row
    assert "`DROP INDEX CONCURRENTLY erev.<index>`" in row
    assert "(see `release-stamp`)" in row and "dev-guide DG-KRN-DB-10" in row


def test_runbook_names_the_log_lines_the_hosted_alerts_read() -> None:
    """05 DPL-37 rev 1.162 (item DEPLOY-ALERT-NAMES-1): the runbook names the two log lines the
    hosted alert policies match - the relay's line for a message recorded DEAD, with the other
    outcomes it can carry, and the operator alert of a failed chain verification by its kinds."""
    from erev_api.controls.operator_alerts import OperatorAlertKind
    from erev_api.enums import OutboxStatus
    from erev_api.events import outbox

    dead = _section("runbook.md", "Dead letters of JOURNAL_EXPORT")
    assert f"the line `outbox.dispatch_failed` with `outcome` `{OutboxStatus.DEAD.value}`" in dead
    assert f"reads `{OutboxStatus.FAILED.value}`" in dead and f"`{outbox.UNSETTLED}`" in dead
    assert "a hosted deployment pages on that line (SLO-05)" in dead
    chain = _section("runbook.md", "Chain verification failure response")
    assert "paged from the log line `operator_alert.raised` of either failure" in chain
    for kind in (
        OperatorAlertKind.AUDIT_CHAIN_VERIFICATION_FAILED,
        OperatorAlertKind.SECURITY_CHAIN_VERIFICATION_FAILED,
    ):
        assert f"`{kind.value}`" in chain


def test_runbook_says_whom_a_failed_job_is_told_to() -> None:
    """05 JOB-07 rev 1.165 (item JOB-FAILED-ITEM-1): the runbook's "Stuck and failed jobs" names
    the three ways a failed job is told — the initiator's notification, the operator alert of a
    job that no person started with the fields the alert carries, and the exception item of the
    record's entity, which is information and is dismissed with a comment — and no longer says
    that a job started by the system notifies no one."""
    from erev_api.controls.operator_alerts import RUNBOOK, OperatorAlertKind
    from erev_api.domain.imports.exceptions import JOB_FAILED

    section = _section("runbook.md", "Stuck and failed jobs")
    assert "Jobs started by the system notify no one" not in section
    assert 'receives the notification "Job failed: <job label>"' in section
    assert RUNBOOK[OperatorAlertKind.JOB_FAILED] == "RB-07"
    assert f"raises the operator alert `{OperatorAlertKind.JOB_FAILED.value}` instead" in section
    assert "the log line `operator_alert.raised` (warning level)" in section
    for named in (
        "the tenant id",
        "the job id",
        "its kind",
        "its queue",
        "the attempt",
        "the slug of its problem",
        "the kind of its initiator",
    ):
        assert named in section, named
    assert f"leaves the exception item `{JOB_FAILED}` in the queue of that entity" in section
    assert "It is information and holds no close" in section
    assert "a holder of `exception.resolve` dismisses it with a comment" in section


def test_runbook_says_what_becomes_of_a_shred_that_is_decided_and_not_completed() -> None:
    """05 PRV-07 b, OPR-24 and SCH-16 rev 1.171 (item FILE-SHRED-DURABLE-ORDER-1): RB-14 names
    the two instants of a shred and the two audit actions, what the administrator sees and does
    while the completion is owed, the sweep by its task, period and limits as the code holds
    them, and the operator alert by its kind, its fields and the log line a failed attempt
    leaves — and no longer says that the decision's event carries the store's report."""
    from erev_api import worker
    from erev_api.controls.operator_alerts import RUNBOOK, SEVERITY, OperatorAlertKind
    from erev_api.domain.platform import privacy, shred_completion

    section = _section("runbook.md", "Personal data erasure")
    kind = OperatorAlertKind.FILE_SHRED_INCOMPLETE
    assert (RUNBOOK[kind], SEVERITY[kind]) == ("RB-14", "WARNING")
    # The administrator: both columns, both events, and the repeat of step 4.
    assert "`GET /api/v1/files/{id}` then shows `shred_completed_at`" in section
    assert "send the command again with a new `Idempotency-Key`, which completes" in section
    assert f"`{privacy.SHRED_ACTION}` — the decision" in section
    assert f"`{privacy.COMPLETE_ACTION}` — when the key was destroyed" in section
    assert f"the `{privacy.COMPLETE_ACTION}` audit event's `detail.irreversible_after`" in section
    assert f"the `{privacy.SHRED_ACTION}` audit event's `detail.irreversible_after`" not in section
    # The sweep, as the worker and the module hold it.
    minutes = int(shred_completion.GRACE.total_seconds() // 60)
    assert f"The worker task `{worker.FILE_SHRED_COMPLETION_TASK}` runs every 10 minutes" in section
    assert f"whose decision is at least {minutes} minutes old" in section
    assert f"at most {shred_completion.BATCH} per workspace and run" in section
    # The operator: the alert, what it carries, and the line that names a failed attempt.
    overdue = int(shred_completion.OVERDUE.total_seconds() // 60)
    assert f"{overdue} minutes after its decision raises the operator alert `{kind.value}`" in (
        section
    )
    assert "the log line `operator_alert.raised` (warning level)" in section
    for named in ("the tenant id", "the number of files", "the age of the oldest decision"):
        assert named in section, named
    assert "it names no file" in section
    assert "the worker's log line `file_shred.completion_failed`" in section
    for module in (privacy, shred_completion):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        assert '"file_shred.completion_failed"' in source, module.__name__
    assert "no `.dek` is deleted by hand" in section


def test_runbook_says_how_an_api_client_is_requested_approved_and_given_its_secret() -> None:
    """Item GUIDES-API-CLIENT-APPROVAL-1 (register index 304; supervisor ruling R-38 (iii); 03
    REQ-PLT-033; 04 T-PLT-15): the runbook describes an API client as the code makes one — a
    request that waits for another person's approval, the first secret issued by
    ``rotate-secret``, the four states with the sentence each refusal gives, the reach rule and
    what no command changes. The routes, the states, the sentences, the permissions and the
    audit actions are read from the code. Before, the section described a client that is
    created with its secret, and the rate-limit section sent the operator to a ``PATCH`` route
    that never existed."""
    from erev_api.api.v1 import api_clients as routes
    from erev_api.approvals import subjects
    from erev_api.auth import api_clients, entity_scope, mfa
    from erev_api.enums import ApiClientStatus, ApprovalSubjectType
    from fastapi.routing import APIRoute

    section = _section("runbook.md", "API clients and access tokens")
    served = {
        (method, route.path)
        for route in routes.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert served == {
        ("GET", "/api/v1/api-clients"),
        ("POST", "/api/v1/api-clients"),
        ("GET", "/api/v1/api-clients/{api_client_id}"),
        ("POST", "/api/v1/api-clients/{api_client_id}/rotate-secret"),
        ("POST", "/api/v1/api-clients/{api_client_id}/revoke"),
    }
    for named in (
        "`GET /api/v1/api-clients`",
        "`POST /api/v1/api-clients`",
        "`GET /api/v1/api-clients/<id>`",
        "`POST /api/v1/api-clients/<id>/rotate-secret`",
        "`POST /api/v1/api-clients/<id>/revoke`",
    ):
        assert named in section, named
    # The request, who decides it, and the step-up of the two commands that issue a secret.
    assert routes.PERMISSION == api_clients.MANAGE_PERMISSION == "api_client.manage"
    grant = subjects.SUBJECTS[ApprovalSubjectType.ROLE_ASSIGNMENT]
    assert grant.required_permission == "access.approve"
    assert "Another person who holds `access.approve` for the client's entities" in section
    assert "`POST /api/v1/approvals/<request id>/approve` or `/reject`" in section
    assert "(403 `self-approval`)" in section
    assert mfa.STEP_UP_WINDOW.total_seconds() == 300
    assert section.count("a TOTP verification at most five minutes old") == 2
    assert "201 with `status` `PENDING_APPROVAL`, `client_secret` null" in section
    assert "rule `AUTO-BOOTSTRAP`" in section
    # The four states, and the sentence of each refusal of a command on a client that is not
    # ACTIVE (R-122 (b): what the operator finds and does in each).
    assert {status.value for status in ApiClientStatus} == {
        "PENDING_APPROVAL",
        "ACTIVE",
        "REJECTED",
        "REVOKED",
    }
    for status in ApiClientStatus:
        assert f"`{status.value}`" in section, status
    for sentence in (
        api_clients.WAITING_FOR_APPROVAL,
        api_clients.REQUEST_REJECTED,
        api_clients.NOT_ACTIVE,
    ):
        assert f'"{sentence}"' in section, sentence
    assert "answer 409 `invalid-transition` with the sentence of its state" in section
    assert "`POST /api/v1/approvals/<request id>/withdraw`" in section
    assert "until its `expires_at`, which no command moves" in section
    assert section.count("request another client") == 3
    # The first secret, the reach rule and the events.
    assert "The first secret: once the client is `ACTIVE`" in section
    assert "Until then `has_secret` is false" in section
    assert api_clients.MIN_REASON_LENGTH == 10
    assert "needs a reason of at least 10 characters" in section
    assert "is not listed and answers 404 `not-found`" in section
    assert "write a `DENIED` audit event under the client" in section
    for action in (
        api_clients.CREATE_ACTION,
        api_clients.ROTATE_ACTION,
        api_clients.REVOKE_ACTION,
        subjects.API_CLIENT_ACTIVATE,
        subjects.API_CLIENT_REJECT,
    ):
        assert f"`{action}`" in section, action
    assert "No command changes a client's scopes, entities, expiry or rate limit" in section
    # Entities are named by code, and a client that is not ACTIVE gets no token.
    assert "Named entities are refused until legal entities exist" not in section
    assert f'("{entity_scope.ENTITY_UNKNOWN}")' in section
    assert "or a client that is not `ACTIVE`" in section
    assert "are shown in the create and rotate responses only" not in section
    # The limit of a client: set with the request, and no route changes it.
    limits = _section("runbook.md", "Rate limits and metrics")
    assert "PATCH /api/v1/api-clients" not in _runbook()
    assert "is set when the client is requested (`rate_limit_per_minute`)" in limits
    assert "no command changes it afterwards" in limits


def test_itgc_guide_names_the_api_client_routes_and_evidence_as_the_code_does() -> None:
    """Item GUIDES-API-CLIENT-APPROVAL-1 (register index 304; supervisor ruling R-38 (iii)):
    control CU-12 names the route and the audit action of a rotation as the code spells them —
    the guide said ``/rotate`` and ``api_client.rotate``, neither of which exists — and the
    control the ruling added: a client's scopes are an access grant another person approves,
    evidenced by the grant's approval request and by the ``DENIED`` events."""
    from erev_api.approvals import subjects
    from erev_api.auth import api_clients

    section = _section(
        "itgc-guide.md", "CU-12 Safeguard and rotate API keys and service account credentials"
    )
    assert "(`POST /api/v1/api-clients/{id}/rotate-secret`, `/revoke`; T-PLT-15)" in section
    assert "/rotate`" not in section
    assert "`api_client.rotate`" not in section
    for action in (
        api_clients.CREATE_ACTION,
        api_clients.ROTATE_ACTION,
        api_clients.REVOKE_ACTION,
        subjects.API_CLIENT_ACTIVATE,
        subjects.API_CLIENT_REJECT,
    ):
        assert f"`{action}`" in section, action
    assert "approved by another person who holds `access.approve` for its entities" in section
    assert "named by the client's `approval_request_id`" in section
    assert "`DENIED` audit events" in section


def test_user_guide_says_that_a_new_api_client_waits_for_approval() -> None:
    """Item GUIDES-API-CLIENT-APPROVAL-1 (register index 304): the user guide's line on the
    developer settings says that a new API client waits for approval and how its first secret
    is issued, in the words the screen shows (the status chip of E-103 and the row action)."""
    import json

    section = _section("user-guide.md", "Settings")
    chips = (ROOT / "frontend" / "src" / "components" / "ui" / "StatusChip.tsx").read_text(
        encoding="utf-8"
    )
    assert 'PENDING_APPROVAL: "Pending approval"' in chips
    messages = json.loads(
        (ROOT / "frontend" / "src" / "messages" / "en.json").read_text(encoding="utf-8")
    )
    assert messages["developer.clients.rotate"] == "Rotate secret"
    assert (
        "a new API client is Pending approval until another person who holds `access.approve` "
        "for its entities approves the request, and its first secret is then issued with Rotate "
        "secret"
    ) in section
