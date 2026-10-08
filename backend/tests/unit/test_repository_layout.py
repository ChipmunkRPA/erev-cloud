"""Repository layout and licence contract (docs/dev-guide.md §1; BUILD_SPEC FND-1)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

ALLOWED_TOP_LEVEL = {
    "Makefile",
    "LICENSE",
    "NOTICE",
    "README.md",
    "release-manifest.json",
    ".env.example",
    ".env",
    ".gitignore",
    # 05 DPL-04: the Docker build context exclusions (BUILD_SPEC DEP-1).
    ".dockerignore",
    "PROMPT.md",
    "PROGRESS.md",
    "backend",
    "frontend",
    "deploy",
    "scripts",
    "docs",
    "legacy-harness",
    "research-harness",
    ".run",
    ".data",
    ".git",
    ".scratch",
    ".ralph",
}

ENV_EXAMPLE_NAMES = [
    "EREV_ENV",
    "EREV_DB_OWNER_URL",
    "EREV_DB_APP_URL",
    "EREV_TEST_DB_OWNER_URL",
    "EREV_TEST_DB_APP_URL",
    "EREV_E2E_DB_OWNER_URL",
    "EREV_E2E_DB_APP_URL",
    "EREV_API_PORT",
    "EREV_WEB_PORT",
    "EREV_E2E_API_PORT",
    "EREV_E2E_WEB_PORT",
    "EREV_ENCRYPTION_KEY",
    "EREV_AUDIT_HMAC_MASTER_KEY",
    "EREV_SECURITY_EVENT_HMAC_KEY",
    "EREV_DEMO_PASSWORD",
    "EREV_DEMO_TOTP_SECRET",
    "EREV_AI_PROVIDER",
    "EREV_AI_KILL_SWITCH",
    "ANTHROPIC_API_KEY",
    "EREV_FILE_ROOT",
    "EREV_LOG_LEVEL",
    "EREV_LOG_FORMAT",
    "EREV_RUN_DIR",
    "EREV_PUBLIC_ORIGIN",
    "EREV_CORS_ORIGINS",
    "EREV_TRUSTED_PROXY_HOPS",
    "EREV_WORKER_CONCURRENCY",
    "EREV_WORKER_QUEUES",
    "EREV_KEY_PROVIDER",
    "EREV_EMAIL_BACKEND",
    "EREV_METRICS_ENABLED",
    "EREV_METRICS_TOKEN",
]

GITIGNORE_REQUIRED = [
    # DG-LAY-08 additions
    ".data/",
    "backend/.hypothesis/",
    "backend/.pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "frontend/dist/",
    "frontend/e2e/.screens/",
    "frontend/e2e/.results/",
    "deploy/terraform/gcp/.terraform/",
    "*.tfstate",
    "*.tfstate.*",
    "dist/",
    "coverage/",
    "release-manifest.json",
    # existing entries that stay
    ".scratch/",
    ".run/",
    ".ralph/",
    "node_modules/",
    "__pycache__/",
    ".venv/",
    ".env",
]

NO_LICENCE_GATE_PATTERNS = [
    re.compile(r"(?i)licen[cs]e[_ -]?key"),
    re.compile(r"(?i)premium"),
    re.compile(r"(?i)trial[_ -]?expir"),
    re.compile(r"(?i)end[_ -]of[_ -]life"),
    re.compile(re.escape("2025-12-31")),
]
SCANNED_DIRECTORIES = ["backend/erev_api", "backend/erev_engine", "frontend/src", "scripts"]
SKIPPED_PARTS = {"node_modules", ".venv", "__pycache__"}


# DG-LAY-01 (supervisor ruling 2026-09-19): gitignored tool caches at the top level are build
# artefacts, not layout — exactly these three names are ignored; anything else keeps failing.
CACHE_DIRECTORIES = {".ruff_cache", ".pytest_cache", ".mypy_cache"}


def unexpected_top_level(root: Path) -> list[str]:
    entries = {path.name for path in root.iterdir()}
    return sorted(entries - ALLOWED_TOP_LEVEL - CACHE_DIRECTORIES)


def test_dg_lay_01_top_level_directories() -> None:
    assert unexpected_top_level(ROOT) == []


def test_dg_lay_01_ignores_only_the_gitignored_cache_directories(tmp_path: Path) -> None:
    # A scratch copy of the layout: the three cache directories are ignored, a stray file or
    # directory (the wrapper's old `.gate-pid` marker, an unknown directory) still fails.
    root = tmp_path / "root"
    root.mkdir()
    for name in ("backend", "frontend", "docs", ".run"):
        (root / name).mkdir()
    (root / ".gitignore").write_text(".run/\n", encoding="utf-8")
    for name in (".ruff_cache", ".pytest_cache", ".mypy_cache"):
        (root / name).mkdir()
    assert unexpected_top_level(root) == []
    (root / ".gate-pid").write_text("1\n", encoding="utf-8")
    (root / ".stray").mkdir()
    assert unexpected_top_level(root) == [".gate-pid", ".stray"]
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for name in (".ruff_cache", ".pytest_cache", ".mypy_cache"):
        assert any(line.strip().lstrip("/").rstrip("/") == name for line in ignored), name


def test_licence_is_noncommercial_with_required_notice() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("# PolyForm Noncommercial License 1.0.0")
    assert "## Noncommercial Purposes" in text
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Required Notice: Copyright (c) 2025-2026 ChipmunkRPA" in notice
    assert "Licensed under the PolyForm Noncommercial License 1.0.0" in notice


def test_env_example_names_exact() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assignments = [line.split("=", 1) for line in lines if re.match(r"^[A-Z][A-Z0-9_]*=", line)]
    names = [name for name, _ in assignments]
    values = dict(assignments)
    assert names == ENV_EXAMPLE_NAMES
    assert len(names) == 32
    assert values["EREV_DEMO_PASSWORD"] == "Demo1234!Demo"
    for key in (
        "EREV_ENCRYPTION_KEY",
        "EREV_AUDIT_HMAC_MASTER_KEY",
        "EREV_SECURITY_EVENT_HMAC_KEY",
    ):
        assert values[key] == "CHANGE_ME_64_HEX"


def test_gitignore_entries() -> None:
    entries = {
        line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    missing = [entry for entry in GITIGNORE_REQUIRED if entry not in entries]
    assert missing == []


def test_pyproject_contract() -> None:
    pyproject = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "erev_api",
        "erev_engine",
    ]
    assert pyproject["project"]["scripts"]["erev"] == "erev_api.cli:app"
    assert pyproject["project"]["requires-python"] == ">=3.12,<3.13"
    assert (ROOT / "backend" / ".python-version").read_text(encoding="utf-8").strip() == "3.12"


def test_req_sec_009_no_licence_gate_or_kill_switch() -> None:
    findings = []
    for directory in SCANNED_DIRECTORIES:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or SKIPPED_PARTS.intersection(path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in NO_LICENCE_GATE_PATTERNS:
                if pattern.search(text):
                    findings.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert findings == []
