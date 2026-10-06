"""Standard report catalogue (04 T-RPT-01 and table 10-T; SCREENS_B §5.6; PHASES §5.4; BUILD_SPEC
RPS-1)."""

from __future__ import annotations

import importlib.util
import re

from erev_api.domain.reports.catalogue import (
    DEFINITIONS,
    DEFINITIONS_BY_CODE,
    ENTITY_SCOPE_KEY,
    HISTORICAL_BASIS,
    KNOWN_AT_BASIS_KEY,
    KNOWN_AT_KEY,
    OUTPUT_FORMATS,
    RECORD_BASIS,
    REPORT_KINDS,
    TIE_OUT_CODES,
    seed_statement,
    unknown_parameter_keys,
)
from support.architecture import ROOT, read

VERSIONS = "backend/erev_api/db/migrations/versions"


def _seeded_codes() -> list[str]:
    """The 04 T-RPT-01 seeded codes, in the order of the specification."""
    paragraph = read("docs/04-DATA_MODEL.md").split("Seeded codes (version 1): ", 1)[1]
    return re.findall(r"`([a-z_]+)`", paragraph.split("\n", 1)[0])


def _table_10_t_codes() -> tuple[str, ...]:
    section = read("docs/04-DATA_MODEL.md").split("**Table 10-T", 1)[1].split("### T-RPT-02", 1)[0]
    return tuple(re.findall(r"^\| `(TO_[A-Z_]+)` \|", section, flags=re.MULTILINE))


def _phase_codes() -> dict[str, list[str]]:
    """PHASES §5.4 report codes per phase."""
    section = read("docs/build-spec/PHASES.md").split("### 5.4 Report codes", 1)[1]
    section = section.split("\n## ", 1)[0]
    rows = re.findall(r"^\| (RPS|LMG|FCS) \| (.+) \| \d+ \|$", section, flags=re.MULTILINE)
    return {phase: re.findall(r"`([a-z_]+)`", codes) for phase, codes in rows}


def _screens_index() -> dict[str, tuple[str, str, tuple[str, ...]]]:
    """SCREENS_B §5.6 index: code → (name, kind, formats)."""
    section = read("docs/design/SCREENS_B.md").split("**Index.**", 1)[1].split("####", 1)[0]
    rows = re.findall(
        r"^\| RPT-\d\d \| `([a-z_]+)` \| ([^|]+) \| ([A-Z_]+) \| [^|]+ \| ([^|]+) \|",
        section,
        flags=re.MULTILINE,
    )
    return {
        code: (name.strip(), kind, tuple(part.strip() for part in formats.split(",")))
        for code, name, kind, formats in rows
    }


def test_seeded_codes() -> None:
    # 04 T-RPT-01 and PHASES §5.4 (RPS-1): 56 current version-1 definitions in the seeded order,
    # 52 RPS, 2 LMG and 2 FCS codes; names, kinds and formats of SCREENS_B §5.6; tie-outs from table
    # 10-T only.
    seeded = _seeded_codes()
    assert len(seeded) == 56
    current = [definition for definition in DEFINITIONS if definition.is_current]
    assert [definition.code for definition in current] == seeded
    assert all(definition.version == 1 for definition in DEFINITIONS)
    phases = _phase_codes()
    assert {phase: len(codes) for phase, codes in phases.items()} == {"RPS": 52, "LMG": 2, "FCS": 2}
    assert sorted(code for codes in phases.values() for code in codes) == sorted(seeded)

    pack = DEFINITIONS_BY_CODE["disclosure_pack"]
    assert pack.kind == "DISCLOSURE"
    assert pack.output_formats == ("XLSX", "PDF", "JSON")
    assert list(DEFINITIONS_BY_CODE["revenue_waterfall"].tie_outs) == ["TO_WATERFALL_EQ_JE_REVENUE"]
    assert TIE_OUT_CODES == _table_10_t_codes()
    assert len(TIE_OUT_CODES) == 13
    for definition in DEFINITIONS:
        assert set(definition.tie_outs) <= set(TIE_OUT_CODES), definition.code
        assert definition.kind in REPORT_KINDS, definition.code
        assert set(definition.output_formats) <= set(OUTPUT_FORMATS), definition.code

    index = _screens_index()
    assert set(index) == set(seeded) - {"disclosure_pack"}
    for code, (name, kind, formats) in index.items():
        definition = DEFINITIONS_BY_CODE[code]
        assert (definition.name, definition.kind, definition.output_formats) == (
            name,
            kind,
            formats,
        ), code


def test_parameter_schemas_closed() -> None:
    # T-RPT-01 rule 1 (RPS-1): every parameters_schema is closed, rejects an unknown key, accepts
    # each declared key and declares known_at and the entity scope; ipe_logic documents source
    # tables, joins, filters, parameters and the definition version (REQ-RPT-027).
    for definition in DEFINITIONS:
        schema = definition.parameters_schema
        assert schema["type"] == "object", definition.code
        assert schema["additionalProperties"] is False, definition.code
        properties = schema["properties"]
        assert {KNOWN_AT_KEY, ENTITY_SCOPE_KEY, KNOWN_AT_BASIS_KEY} <= set(properties), (
            definition.code
        )
        basis = properties[KNOWN_AT_BASIS_KEY]
        assert basis["enum"] == [RECORD_BASIS, HISTORICAL_BASIS], definition.code
        declared = dict.fromkeys(properties)
        assert unknown_parameter_keys(definition, declared) == (), definition.code
        assert unknown_parameter_keys(definition, {**declared, "not_a_parameter": 1}) == (
            "not_a_parameter",
        ), definition.code
        logic = definition.ipe_logic
        assert set(logic) == {"version", "source_tables", "joins", "filters", "parameters"}
        assert logic["version"] == definition.version, definition.code
        assert logic["source_tables"] and logic["filters"], definition.code
        assert logic["parameters"] == list(properties), definition.code

    def keys(code: str) -> set[str]:
        return set(DEFINITIONS_BY_CODE[code].parameters_schema["properties"])

    assert {"time_bands", "row_dimension"} <= keys("rpo")
    assert {"from_period_lock_id", "to_period_lock_id"} <= keys("variance_between_closes")
    assert keys("api_client_inventory") == {
        "entity_codes",
        "include_revoked",
        "known_at",
        "known_at_basis",  # D-98 candidate 112: the stored read basis
    }
    assert "book" not in keys("extract_contracts") | keys("extract_events")
    rpo_rows = DEFINITIONS_BY_CODE["rpo"].parameters_schema["properties"]["row_dimension"]
    assert rpo_rows["enum"] == ["CONTRACT", "ENTITY", "PRODUCT_FAMILY", "CUSTOMER_SEGMENT"]
    mode = DEFINITIONS_BY_CODE["legacy_je_summary"].parameters_schema["properties"]["mode"]
    assert mode["enum"] == ["GROSS", "DELTA"]


def test_revision_seed_equals_fresh_rendering() -> None:
    # DG-MIG-07 with the DG-ARC-07 pattern (RPS-1; L4-2-Q-27): the revision that seeds
    # report_definition embeds exactly catalogue.seed_statement(), and its check literals equal the
    # catalogue's kinds, formats and tie-out codes.
    candidates = [
        path
        for path in sorted((ROOT / VERSIONS).glob("*.py"))
        if "REPORT_DEFINITION_SEED = " in path.read_text(encoding="utf-8")
    ]
    assert len(candidates) == 1
    spec = importlib.util.spec_from_file_location("rps_1_report_tables", candidates[0])
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.REPORT_DEFINITION_SEED == seed_statement()
    assert module.TIE_OUT_CODES == TIE_OUT_CODES
    assert module.OUTPUT_FORMATS == OUTPUT_FORMATS
    assert module.REPORT_KINDS == REPORT_KINDS
    assert len(seed_statement().splitlines()) == 1 + len(DEFINITIONS)
