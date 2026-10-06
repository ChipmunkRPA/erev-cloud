"""Registry generator and parameter catalogues (DG-KRN-REG-04; 04 T-PLT-31; BUILD_SPEC FND-8)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from erev_api.cli import app
from erev_api.enums import RegistryCategory, RegistryScope
from erev_api.registry import seed
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.policies import POLICY_PARAMETERS, RegistryParameterSpec
from typer.testing import CliRunner

CODE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
DATA_MODEL = seed.REPO_ROOT / "docs" / "04-DATA_MODEL.md"


def _by_pol_id() -> dict[str, RegistryParameterSpec]:
    return {spec.pol_id: spec for spec in POLICY_PARAMETERS.values() if spec.pol_id is not None}


def test_krn_reg_04_generated_module_current(tmp_path: Path) -> None:
    runner = CliRunner()
    regenerated = tmp_path / "policies.py"
    result = runner.invoke(app, ["registry-seed", "--out", str(regenerated)])
    assert result.exit_code == 0, result.output
    assert regenerated.read_bytes() == seed.MODULE_PATH.read_bytes()
    result = runner.invoke(app, ["registry-seed", "--check"])
    assert result.exit_code == 0, result.output

    text = seed.POLICIES_PATH.read_text(encoding="utf-8")
    pol_004 = "| `ERP`, `ENGINE` | `ERP` | `ERP` | `ERP` |"
    assert text.count(pol_004) == 1
    changed = tmp_path / "POLICIES-pol-004-default-changed.md"
    changed.write_text(
        text.replace(pol_004, "| `ERP`, `ENGINE` | `ENGINE` | `ERP` | `ERP` |"), encoding="utf-8"
    )
    result = runner.invoke(app, ["registry-seed", "--check", "--policies", str(changed)])
    assert result.exit_code == 1
    assert "stale" in result.output


def test_policy_parameters_cover_section_1() -> None:
    text = seed.POLICIES_PATH.read_text(encoding="utf-8")
    section = text[text.index("\n## 1. Policy register") : text.index("\n## 2. Algorithms")]
    # §5.0 "These rows belong to the policy register (section 1)": POL-240 to POL-246.
    extra = text[text.index("\n### 5.0 Additional register") : text.index("\n### 5.1 ")]
    rows = re.findall(r"^\| (POL-\d{3}) \| `([^`]+)` \|", section + extra, re.MULTILINE)
    ids = [pol_id for pol_id, _ in rows]
    assert len(ids) == len(set(ids))
    assert ids[-7:] == [f"POL-24{n}" for n in range(7)]
    assert len(POLICY_PARAMETERS) == len(rows) == 131
    assert {spec.pol_id: code for code, spec in POLICY_PARAMETERS.items()} == dict(rows)
    for code, spec in POLICY_PARAMETERS.items():
        assert spec.code == code
        assert CODE.fullmatch(code), code
        assert spec.source_ref == spec.pol_id
        assert 1 <= len(spec.description) <= 4000


def test_billing_posting_spec() -> None:
    spec = POLICY_PARAMETERS["billing.posting"]
    assert spec.pol_id == "POL-004"
    assert spec.value_schema["enum"] == ["ERP", "ENGINE"]
    assert spec.default_asc606 == "ERP"
    assert spec.default_ifrs15 == "ERP"
    assert spec.legacy_parity_value == "ERP"
    assert spec.allowed_levels == frozenset({RegistryScope.TENANT})
    assert spec.pin == "P"
    assert spec.approval_code == "CFG"
    assert spec.category is RegistryCategory.ACCOUNTING_POLICY
    assert spec.section == "Platform, books, posting and rounding"


def test_forced_and_parity_values() -> None:
    rounding = POLICY_PARAMETERS["rounding.posting_mode"]
    assert rounding.is_forced_asc606 is True
    assert rounding.is_forced_ifrs15 is True
    assert rounding.default_asc606 == "HALF_UP"
    assert POLICY_PARAMETERS["je.summarization"].legacy_parity_value == "LEGACY_CONTRACT_POB"
    assert POLICY_PARAMETERS["je.posting_mode"].allowed_levels == frozenset(
        {RegistryScope.TENANT, RegistryScope.ENTITY}
    )


def test_category_rules_t_plt_31() -> None:
    by_id = _by_pol_id()
    expedients = {"POL-015", "POL-021", "POL-045", "POL-046", "POL-140"}
    expedients |= {"POL-197", "POL-198", "POL-199", "POL-200", "POL-202"}
    elections = {f"POL-{number}" for number in range(190, 197)} | {"POL-203", "POL-204"}
    assert len(expedients) == 10
    assert len(elections) == 9
    categories = {pol_id: spec.category for pol_id, spec in by_id.items()}
    assert {i for i, c in categories.items() if c is RegistryCategory.PRACTICAL_EXPEDIENT} == (
        expedients
    )
    assert {i for i, c in categories.items() if c is RegistryCategory.DISCLOSURE_ELECTION} == (
        elections
    )
    assert by_id["POL-201"].code == "rpo.time_bands"
    assert by_id["POL-201"].category is RegistryCategory.ACCOUNTING_POLICY
    others = set(by_id) - expedients - elections
    assert all(categories[pol_id] is RegistryCategory.ACCOUNTING_POLICY for pol_id in others)


def test_import_batch_levels_empty() -> None:
    by_id = _by_pol_id()
    for number in range(210, 215):
        assert by_id[f"POL-{number}"].allowed_levels == frozenset()


def test_platform_parameters_t_plt_31() -> None:
    assert len(PLATFORM_PARAMETERS) == 24  # F-SNP I-5: platform.snapshot_retention_families
    for spec in PLATFORM_PARAMETERS.values():
        assert spec.allowed_levels == frozenset({RegistryScope.TENANT})
        assert spec.pin == "P"
        assert spec.approval_code == "CFG"
        assert spec.pol_id is None
        assert spec.section == "Platform"
        assert CODE.fullmatch(spec.code)
    style = PLATFORM_PARAMETERS["ui.negative_number_style"]
    assert style.value_schema["enum"] == ["PARENTHESES", "MINUS"]
    assert style.default_asc606 == "PARENTHESES"
    idle = PLATFORM_PARAMETERS["platform.session_idle_minutes"]
    assert dict(idle.value_schema) == {"type": "integer", "minimum": 5, "maximum": 240}
    assert idle.default_asc606 == 30
    concurrency = PLATFORM_PARAMETERS["platform.job_concurrency"]
    assert dict(concurrency.value_schema) == {"type": "integer", "minimum": 1, "maximum": 16}
    assert concurrency.default_asc606 == 4
    assert PLATFORM_PARAMETERS["ai.model"].default_asc606 == "claude-opus-5"
    grouping = PLATFORM_PARAMETERS["integration.grouping_fields"]
    assert grouping.legacy_parity_value == ["contract_unique_name"]
    assert not set(PLATFORM_PARAMETERS) & set(POLICY_PARAMETERS)


def test_platform_parameters_match_04_table() -> None:
    text = DATA_MODEL.read_text(encoding="utf-8")
    section = text[text.index("2. **Platform parameters**") : text.index("\n### T-PLT-32 ")]
    rows: list[tuple[str, str, object, object]] = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        code, category, _values, default, parity, _source = (
            cell.strip() for cell in re.split(r"(?<!\\)\|", line)[1:-1]
        )
        default_value = json.loads(default.strip("`"))
        parity_value = default_value if parity == "same" else json.loads(parity.strip("`"))
        rows.append((code.strip("`"), category, default_value, parity_value))
    assert [
        (spec.code, spec.category.value, spec.default_asc606, spec.legacy_parity_value)
        for spec in PLATFORM_PARAMETERS.values()
    ] == rows


def test_value_shapes_follow_t_plt_32() -> None:
    books = POLICY_PARAMETERS["books.enabled"]
    assert books.default_asc606 == {"set": ["ASC606"], "primary": "ASC606"}
    assert books.default_ifrs15 == {"set": ["IFRS15"], "primary": "IFRS15"}
    assert books.legacy_parity_value == {"set": ["ASC606", "LEGACY"], "primary": "ASC606"}

    window = POLICY_PARAMETERS["combination.detection_window_days"]
    assert dict(window.value_schema) == {"type": "integer", "minimum": 0, "maximum": 365}
    assert (window.default_asc606, window.legacy_parity_value) == (30, 0)

    relief = POLICY_PARAMETERS["pob.immaterial_promise_relief"]
    plain, parameterised = relief.value_schema["anyOf"]
    assert plain == {"type": "string", "enum": ["ASSESS_ALL", "APPLY_RELIEF"]}
    assert parameterised["properties"]["option"] == {"const": "APPLY_RELIEF"}
    assert parameterised["properties"]["immaterial_threshold_pct"] == {
        "type": "string",
        "format": "decimal",
        "default": "0.01",
        "x-maximum": "0.05",
    }
    assert relief.is_forced_ifrs15 is True

    financing = POLICY_PARAMETERS["sfc.discount_rate_basis"]
    assert financing.value_schema["required"] == ["basis", "annual_rate"]
    assert financing.value_schema["properties"]["compounding"]["default"] == "MONTHLY"
    assert financing.default_asc606 == {"basis": "CUSTOMER_CREDIT_RATE", "compounding": "MONTHLY"}
    assert financing.legacy_parity_value is None

    validation = POLICY_PARAMETERS["ssp.range_validation"]
    assert validation.default_asc606 == {
        "max_half_width_pct": "0.20",
        "min_coverage_pct": "0.50",
        "mode": "WARN",
    }
    assert validation.value_schema["anyOf"][1] == {"type": "string", "enum": ["NOT_ENFORCED"]}
    assert validation.legacy_parity_value == "NOT_ENFORCED"

    hierarchy = POLICY_PARAMETERS["ssp.method_hierarchy"]
    assert hierarchy.default_asc606 == [
        "observable",
        "adjusted_market",
        "cost_plus_margin",
        "residual",
    ]
    assert hierarchy.is_forced_asc606 is True
    assert hierarchy.legacy_parity_value == "legacy_range"

    bands = POLICY_PARAMETERS["rpo.time_bands"]
    assert bands.default_asc606 == bands.default_ifrs15 == bands.legacy_parity_value == [12, 24]

    principal = POLICY_PARAMETERS["pob.principal_or_agent"]
    assert (principal.default_asc606, principal.legacy_parity_value) == (None, "PRINCIPAL")
    assert POLICY_PARAMETERS["mod.mixed_allocation"].legacy_parity_value == "TOTAL_TP"
    assert POLICY_PARAMETERS["ssp.version_basis"].allowed_levels == frozenset(
        {RegistryScope.TENANT, RegistryScope.OBLIGATION}
    )
    assert _by_pol_id()["POL-216"].allowed_levels == frozenset()
    assert POLICY_PARAMETERS["step1.term_with_termination_rights"].approval_code == "OVR"


def _row(**cells: str) -> seed.PolicyRow:
    values = {
        "section_number": "1.1",
        "section": "Platform, books, posting and rounding",
        "pol_id": "POL-999",
        "key": "probe.parameter",
        "question": "Probe?",
        "options": "`A`, `B`",
        "asc606": "`A`",
        "ifrs": "same as 606",
        "parity": "n/a",
        "levels": "T",
        "pin": "P",
        "appr": "CFG",
    }
    values.update(cells)
    return seed.PolicyRow(**values)


def test_seed_rejects_unrecognised_cells() -> None:
    assert seed.build_spec(_row()).default_ifrs15 == "A"
    with pytest.raises(seed.SeedError, match="POL-999"):
        seed.build_spec(_row(options="some prose"))
    with pytest.raises(seed.SeedError, match="POL-999: unrecognised 606 cell"):
        seed.build_spec(_row(asc606="roughly half"))
    with pytest.raises(seed.SeedError, match="POL-999: unrecognised Levels cell"):
        seed.build_spec(_row(levels="T, X"))
