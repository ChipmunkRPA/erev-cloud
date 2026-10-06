"""Security documents and the customer-operated ITGC guide (03 REQ-SEC-005, REQ-CTL-004; 05 SAR-41,
PRV-11; PHASES BS-D-13; BUILD_SPEC SOP-9). CPU only: the documents are read and their test
references resolved against the repository tree."""

from __future__ import annotations

import hashlib
import json
import re
from functools import cache
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parents[3]
SECURITY = ROOT / "docs" / "security"
GUIDES = ROOT / "docs" / "guides"
FILES: Final = {
    "threat-model.md": SECURITY / "threat-model.md",
    "ASVS-L2.md": SECURITY / "ASVS-L2.md",
    "SUBPROCESSORS.md": SECURITY / "SUBPROCESSORS.md",
    "DPA-TEMPLATE.md": SECURITY / "DPA-TEMPLATE.md",
    "itgc-guide.md": GUIDES / "itgc-guide.md",
}
STATUSES: Final = ("MET", "NOT_APPLICABLE", "ACCEPTED_RISK", "GAP")
_THR: Final = re.compile(r"\bTHR-(\d{2})\b")
_NODE: Final = re.compile(r"`((?:backend/tests|frontend)/[A-Za-z0-9_./-]+?)(?:::([A-Za-z0-9_]+))?`")
# A documentation requirement may cite a governed document instead of a test node.
_DOC: Final = re.compile(r"`(docs/[A-Za-z0-9_./-]+\.(?:md|json))`")
_ASVS_ID: Final = re.compile(r"^V\d{1,2}\.\d{1,2}\.\d{1,2}$")
# OWASP ASVS 5.0.0 (release commit 5cf9b032…, CC BY-SA 4.0): the committed L1 + L2 identifier
# inventory (ids, levels, chapters, sections; no requirement text) and its pinned hash.
ASVS_INVENTORY: Final = SECURITY / "asvs-5.0.0-l1-l2-ids.json"
ASVS_INVENTORY_SHA256: Final = "775ad22cc99e68b33882c78ca6b24a629c2d425000dadfdce266486e2b4c5aba"
ASVS_CATALOGUE_SHA256: Final = "bcdbec214d70abcfad9284a31d4f9e5134305831d628aad3aa85d7e26626cb35"
ASVS_RELEASE_COMMIT: Final = "5cf9b032440be53ce345ab3c130fda46ba1ce7a2"
_HEADING: Final = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
# 03 §6.4: the ITGCs a self-hoster operates, one section each.
ITGC_SECTIONS: Final = (
    "Logical access to infrastructure and the database",
    "Change management through the release manifest",
    "Backups and restore tests",
    "Job monitoring",
    "Secrets and key management",
    "Database logging",
)
CUEC_FEATURES: Final = {
    "CU-01": ("preventive SoD block", "role assignment approval"),
    "CU-09": ("support grant", "support session log"),
    "CU-12": ("expiry", "rotation"),
}


@cache
def text(name: str) -> str:
    return FILES[name].read_text(encoding="utf-8")


def rows(document: str, *, min_cells: int) -> list[list[str]]:
    """The body rows of every Markdown table with at least ``min_cells`` cells."""
    found: list[list[str]] = []
    for line in document.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= min_cells:
            found.append(cells)
    return found


def resolves(path: str, name: str | None) -> bool:
    """A test reference resolves when its file exists and, with ``::name``, defines that test."""
    file = ROOT / path
    if not file.is_file():
        return False
    if name is None:
        return True
    return (
        re.search(rf"^(?:async )?def {re.escape(name)}\(", file.read_text(encoding="utf-8"), re.M)
        is not None
    )


def test_bs_d_13_security_files_present() -> None:
    """BS-D-13: the four security documents and the ITGC guide exist and start with a level-1
    heading."""
    for name, path in FILES.items():
        assert path.is_file(), name
        first = next(line for line in text(name).splitlines() if line.strip())
        assert first.startswith("# "), (name, first)


def test_req_sec_005_threat_model_covers_threats() -> None:
    """``threat-model.md`` names THR-01 to THR-26 once each as table rows (THR-26: erasure across
    workspaces, Codex production-20260922-0055 EVIDENCE-1), and every test reference it holds
    resolves to an existing node id under ``backend/tests/`` or a file under ``frontend/``."""
    document = text("threat-model.md")
    threat_rows = [cells for cells in rows(document, min_cells=7) if _THR.fullmatch(cells[0])]
    assert [cells[0] for cells in threat_rows] == [f"THR-{n:02d}" for n in range(1, 27)]
    for cells in threat_rows:
        assert cells[4].strip(), f"{cells[0]}: no mitigations"
        assert cells[5].strip(), f"{cells[0]}: no evidence"
        assert cells[6].strip(), f"{cells[0]}: no residual risk"
    references = _NODE.findall(document)
    assert len(references) >= 60, "the threat model cites the evidence node ids"
    unresolved = sorted(
        {
            f"{path}::{name}" if name else path
            for path, name in references
            if not resolves(path, name or None)
        }
    )
    assert unresolved == [], unresolved
    assert "GAP" in document, "gaps are stated, not hidden"


def asvs_inventory() -> dict[str, int]:
    """id → level of every L1 + L2 requirement of the committed inventory; its bytes are pinned by
    hash."""
    raw = ASVS_INVENTORY.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ASVS_INVENTORY_SHA256, "inventory bytes changed"
    document = json.loads(raw)
    assert document["catalogue_sha256"] == ASVS_CATALOGUE_SHA256
    assert document["commit"] == ASVS_RELEASE_COMMIT and document["version"] == "5.0.0"
    requirements = document["requirements"]
    assert document["l2_inventory_count"] == len(requirements) == 253
    inventory = {str(row["id"]): int(row["level"]) for row in requirements}
    assert len(inventory) == 253, "the inventory ids are unique"
    assert all(_ASVS_ID.match(item) for item in inventory)
    assert set(inventory.values()) == {1, 2}
    assert all("Description" not in row and "Verify" not in json.dumps(row) for row in requirements)
    return inventory


def test_asvs_rows_have_status_and_evidence() -> None:
    """``ASVS-L2.md`` has exactly one row per L1 + L2 requirement id of the pinned OWASP ASVS 5.0.0
    inventory (set equality and uniqueness), carries the attribution (release commit, CC BY-SA)
    and reproduces no requirement text; every row has status MET, NOT_APPLICABLE, ACCEPTED_RISK or
    GAP; a MET row names an existing test node id (or a governed document); an ACCEPTED_RISK row
    names a THR id of the threat model and an owner; a GAP row names an owner; a NOT_APPLICABLE row
    gives a reason."""
    document = text("ASVS-L2.md")
    inventory = asvs_inventory()
    threats = set(_THR.findall(text("threat-model.md")))
    checklist = [cells for cells in rows(document, min_cells=4) if _ASVS_ID.match(cells[0])]
    listed = [cells[0] for cells in checklist]
    assert len(listed) == len(set(listed)), "every requirement id appears once"
    assert set(listed) == set(inventory), sorted(set(listed) ^ set(inventory))
    assert ASVS_RELEASE_COMMIT in document and "CC BY-SA" in document, "attribution line"
    assert ASVS_INVENTORY_SHA256 in document and ASVS_CATALOGUE_SHA256 in document
    assert "Verify that" not in document, "no requirement text is reproduced (CC BY-SA)"
    for asvs_id, level, status, evidence in (cells[:4] for cells in checklist):
        assert level == f"L{inventory[asvs_id]}", (asvs_id, level)
        assert status in STATUSES, (asvs_id, status)
        if status == "MET":
            references = _NODE.findall(evidence)
            documents = _DOC.findall(evidence)
            assert references or documents, f"{asvs_id}: MET without evidence"
            for path, name in references:
                assert resolves(path, name or None), (asvs_id, path, name)
            for path in documents:
                assert (ROOT / path).is_file(), (asvs_id, path)
        elif status == "ACCEPTED_RISK":
            thr = _THR.findall(evidence)
            assert thr and set(thr) <= threats, (asvs_id, evidence)
            assert "owner" in evidence.lower(), f"{asvs_id}: ACCEPTED_RISK without an owner"
        elif status == "GAP":
            assert "owner" in evidence.lower(), f"{asvs_id}: GAP without an owner"
            assert len(evidence) >= 30, f"{asvs_id}: GAP without a statement"
        else:
            assert len(evidence) >= 20, f"{asvs_id}: NOT_APPLICABLE without a reason"
    assert any("UPL-12" in cells[3] and cells[2] == "ACCEPTED_RISK" for cells in checklist)
    assert {cells[2] for cells in checklist if cells[0].startswith("V17.")} == {"NOT_APPLICABLE"}
    assert any(cells[2] == "GAP" for cells in checklist), "gaps are stated, not hidden"


def test_prv_11_subprocessors() -> None:
    """``SUBPROCESSORS.md`` lists Google Cloud, Anthropic (only for tenants that enable AI) and the
    configured SMTP relay, and no other sub-processor."""
    document = text("SUBPROCESSORS.md")
    table = [cells for cells in rows(document, min_cells=7) if cells[0] != "Sub-processor"]
    names = [cells[0] for cells in table]
    assert names == ["Google Cloud", "Anthropic", "Configured SMTP relay"], names
    anthropic = next(cells for cells in table if cells[0] == "Anthropic")
    assert "enabled AI" in anthropic[5] and "never" in anthropic[5]
    assert "no other sub-processor" in document
    for vendor in ("Salesforce", "Stripe", "NetSuite", "QuickBooks"):
        assert f"| {vendor}" not in document, f"{vendor} is not a sub-processor"
    assert "UI-14" in document, "counterparty identities are external inputs, not invented"


def test_req_ctl_004_itgc_guide_lists_cuecs() -> None:
    """``itgc-guide.md`` holds one section per CUEC CU-01 to CU-12, each naming at least one product
    feature (CU-01 the preventive SoD block and the role assignment approval; CU-09 support grant
    approval and the support session log; CU-12 API client expiry and rotation), and one section
    per ITGC of 03 §6.4."""
    document = text("itgc-guide.md")
    headings = [(len(level), title) for level, title in _HEADING.findall(document)]
    cuecs = [title for level, title in headings if level == 3 and title.startswith("CU-")]
    assert [title.split()[0] for title in cuecs] == [f"CU-{n:02d}" for n in range(1, 13)], cuecs
    for code, needles in CUEC_FEATURES.items():
        start = document.index(f"### {code}")
        end = document.find("\n### ", start + 1)
        section = document[start : end if end != -1 else None]
        assert "Features:" in section, code
        for needle in needles:
            assert needle.lower() in section.lower(), (code, needle)
    for code in (f"CU-{n:02d}" for n in range(1, 13)):
        start = document.index(f"### {code}")
        end = document.find("\n### ", start + 1)
        assert "Features:" in document[start : end if end != -1 else None], code
    titles = {title for _, title in headings}
    missing = [section for section in ITGC_SECTIONS if section not in titles]
    assert missing == [], missing
    logical = document[document.index("### Logical access") :]
    assert "`erev_owner`" in logical and "pipeline" in logical
