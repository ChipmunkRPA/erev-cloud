"""05 PRV-01 classification coverage (BUILD_SPEC SOP-5; 04 every table; 03 REQ-SEC-007).

The tests compare ``erev_api.privacy.CLASSIFICATION`` with the ``erev_api.db.tables`` metadata and
with docs/04-DATA_MODEL.md (read-only), so that a column without a classification, a stale entry,
or a ``PENDING`` entry whose column has landed fails the unit suite. No database is needed.

04 declares columns in three section formats, each parsed explicitly (Codex review P8-F1: no
word-membership fallback): the literal column table (``| Column | Type | Null | Default |
Constraints and notes |``), the D-96 hybrid table (``| Column | Notes |`` whose cells hold
``\\`name\\` type N|Y`` declarations) and the D-96 prose line (``Columns (…): SC-T; \\`name\\` …``).
Only top-level declarations in the section's own declaration positions count (P8-F1-R1): the
first cells of the section's column table and its own ``Columns (…):`` line are authoritative;
a typed declaration in a hybrid Notes cell counts only when it leads a depth-0 segment and names
another table only as its FK target (``→ T-…``); a typed declaration in a literal section's
paragraphs (the 04 pending-column form) counts only when no other table is referenced in the same
clause; a ``PRIMARY KEY (…)`` counts only on the section's own key lines (header bullets, ``Keys``
lines, the ``Columns (…)`` line) and not after a reference to another table. Standard sets are
expanded; parenthesised notes, JSON members and referenced objects' fields are not declarations;
typed-declaration or primary-key syntax in any other position, and a section in none of the three
formats, raise ``UnsupportedSectionFormat`` instead of being guessed. For prose and hybrid
sections the declared set and the catalogued set must be equal in both directions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

import pytest
from erev_api.db import tables
from erev_api.privacy.classification import (
    CLASSIFICATION,
    PERSONAL_COLUMN_PATTERN,
    RULES,
    TABLE_CLASSIFICATION,
    TABLES,
    Basis,
    DataClass,
    Erasure,
    PendingSource,
    Status,
    check_coverage,
    columns_of,
    data_class,
)

ROOT = Path(__file__).resolve().parents[3]
DATA_MODEL = ROOT / "docs" / "04-DATA_MODEL.md"
# BUILD_SPEC SOP-5 ``test_prv_01_every_personal_column_classified``: the five named C3 columns.
SPEC_NAMED_C3: Final = frozenset(
    {
        ("app_user", "email"),
        ("app_user", "display_name"),
        ("security_event", "ip_address"),
        ("audit_event", "source_ip"),
        ("access_review_item", "user_email_snapshot"),
    }
)
# 05 PRV-01 "C3 columns in 1.0" (the named columns).
PRV_01_C3: Final = SPEC_NAMED_C3 | frozenset(
    {
        ("app_user", "external_id"),
        # 05 PRV-01 rev 1.47 (R-48 (d); REQ-PLT-006): the OIDC subject an identity is bound to.
        ("app_user", "identity_provider_subject"),
        ("security_event", "email_sha256"),
        ("security_event", "user_agent"),
        ("user_session", "ip_address"),
        ("user_session", "user_agent"),
        ("file_object", "original_filename"),
        # 05 PRV-01 rev 1.128 (04 T-PLT-49; ruling R-111 (5)): each uploader's own file name.
        ("file_upload", "original_filename"),
        ("contract_cost_asset", "payee"),
    }
)
# Lane P8 proposals beyond the PRV-01 list (Basis.PROPOSED; R05 credentials, R07 IP address). Any
# change to the C3 population must be made here as well, so that it is reviewed.
PROPOSED_C3: Final = frozenset(
    {
        ("app_user", "password_hash"),
        ("user_mfa_factor", "secret_ciphertext"),
        ("user_recovery_code", "code_hash"),
        ("user_session", "token_sha256"),
        ("user_session", "csrf_token_sha256"),
        ("tenant_membership", "invitation_token_sha256"),
        ("password_reset_token", "token_sha256"),
        ("password_reset_token", "ip_address"),
    }
)
PUBLIC_TABLES: Final = frozenset({"currency", "permission"})
STANDARD_SETS: Final[dict[str, tuple[str, ...]]] = {
    "SC-T": ("tenant_id", "id"),
    "SC-C": ("created_at", "created_by", "created_by_kind"),
    "SC-M": ("updated_at", "updated_by", "updated_by_kind", "row_version"),
    "SC-V": (
        "version_no",
        "status",
        "effective_from",
        "effective_to",
        "content_sha256",
        "approval_request_id",
        "published_at",
        "published_by",
        "supersedes_version_id",
    ),
}
LITERAL_HEADER: Final = ["Column", "Type", "Null", "Default", "Constraints and notes"]
HYBRID_HEADER: Final = ["Column", "Notes"]
_HEADING: Final = re.compile(r"^### (T-[A-Z]+-\d+) `([a-z0-9_]+)`$", re.MULTILINE)
_SC_LIST: Final = re.compile(r"(SC-[TCMV](,\s*)?)+")
_LITERAL_CELL: Final = re.compile(r"`([a-z0-9_]+)`")
# A segment of a prose line or a hybrid first cell declares the identifier it begins with.
_LEADING_IDENT: Final = re.compile(r"^`([a-z][a-z0-9_]*)`(?:\s|$|\()")
# 04 column types; a declaration outside a first cell is "`name` type N|Y" and nothing else.
_TYPE: Final = (
    r"(?:uuid\[\]|text\[\]|uuid|text|jsonb|integer|bigint|smallint|boolean|timestamptz|date|"
    r"inet|bytea|numeric|erev\.[a-z_]+)"
)
_TYPED_DECLARATION: Final = re.compile(rf"`([a-z][a-z0-9_]*)`\s+{_TYPE}\s+[NY]\b")
# A section's own primary key names its own columns (the T-CON-25 draft declares
# ``contract_computation_id`` only there); it is read only from the section's own key positions.
_PRIMARY_KEY: Final = re.compile(r"PRIMARY KEY \(([a-z0-9_, ]+)\)")
_OWN_KEY_LINE_PREFIXES: Final = ("- **", "Keys", "Columns (")
_TABLE_ID: Final = re.compile(r"\bT-[A-Z]+-\d+\b")
# The only permitted mention of another table inside a Notes declaration: its FK target.
_FK_TARGET: Final = re.compile(r"(?:FK\s+)?→\s+T-[A-Z]+-\d+\b")
_CLAUSE_BOUNDARY: Final = re.compile(r"[.;:]\s")


class UnsupportedSectionFormat(AssertionError):
    """A 04 section (or passage) in none of the declaration forms; never reduced to a guess."""


@dataclass(frozen=True, slots=True)
class Declarations:
    """The top-level column declarations of one 04 section."""

    format: str  # "literal", "hybrid" or "prose"
    columns: tuple[str, ...]  # declared columns in document order, standard sets expanded
    # Literal sections only: typed declarations in the paragraphs around the column table (the
    # 04 "pending column" form, for example T-PLT-38 ``validation_level`` text N).
    paragraph: tuple[str, ...]


def code_columns() -> frozenset[tuple[str, str]]:
    return frozenset(
        (table.name, column.name)
        for table in tables.metadata.sorted_tables
        for column in table.columns
    )


@cache
def data_model() -> str:
    return DATA_MODEL.read_text(encoding="utf-8")


@cache
def doc_sections() -> dict[str, tuple[str, str]]:
    """04 table name → (table id, section text) for every ``### T-…-nn `<table>``` heading."""
    text = data_model()
    matches = list(_HEADING.finditer(text))
    sections: dict[str, tuple[str, str]] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        body = body[: body.find("\n## ")] if "\n## " in body else body
        sections[match.group(2)] = (match.group(1), body)
    return sections


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _split_declarations(text: str) -> list[str]:
    """Split a prose line or a hybrid cell into declaration segments: on ``;`` at parenthesis
    depth 0, and on ``,`` at depth 0 only when a declaration or a standard set follows."""
    parts: list[str] = []
    current = ""
    depth = 0
    for i, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        starts_next = text[i + 1 :].lstrip().startswith(("`", "SC-"))
        if depth == 0 and (char == ";" or (char == "," and starts_next)):
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [part.strip().rstrip(".").strip() for part in parts if part.strip(" .")]


def _clause_prefix(text: str, index: int) -> str:
    """``text[:index]`` since the last sentence or clause boundary."""
    return _CLAUSE_BOUNDARY.split(text[:index])[-1]


def _names_other_table(text: str, own_ref: str | None) -> bool:
    return any(match.group(0) != own_ref for match in _TABLE_ID.finditer(text))


def _segment_columns(text: str, where: str) -> list[str]:
    """Columns declared by the segments of an own declaration position (a prose line or a hybrid
    first cell); a segment that is neither a standard set nor led by a backticked identifier is
    an unsupported format."""
    columns: list[str] = []
    for segment in _split_declarations(text):
        if re.fullmatch(r"SC-[TCMV]", segment):
            columns += STANDARD_SETS[segment]
            continue
        lead = _LEADING_IDENT.match(segment)
        if lead is None:
            raise UnsupportedSectionFormat(f"{where}: {segment[:80]!r}")
        columns.append(lead.group(1))
    return columns


def _notes_columns(notes: str, own_ref: str | None, where: str) -> list[str]:
    """Typed declarations in a hybrid Notes cell: only one that leads a depth-0 segment and
    names another table only as its FK target; typed-declaration syntax elsewhere in the cell is
    reference text of ambiguous scope and is refused (P8-F1-R1)."""
    columns: list[str] = []
    for segment in _split_declarations(notes):
        leading = _TYPED_DECLARATION.match(segment)
        if leading is not None:
            remainder = _FK_TARGET.sub("", segment[leading.end() :])
            if _names_other_table(remainder, own_ref):
                raise UnsupportedSectionFormat(
                    f"{where}: Notes declaration {leading.group(1)!r} names another table: "
                    f"{segment[:80]!r}"
                )
            columns.append(leading.group(1))
        elif _TYPED_DECLARATION.search(segment) is not None:
            raise UnsupportedSectionFormat(
                f"{where}: typed declaration syntax in a reference position: {segment[:80]!r}"
            )
    return columns


def _paragraph_columns(outside: str, own_ref: str | None, where: str) -> tuple[str, ...]:
    """Typed declarations in a literal section's paragraphs (the 04 pending-column form); one that
    follows a reference to another table in the same clause is refused (P8-F1-R1)."""
    found: list[str] = []
    for match in _TYPED_DECLARATION.finditer(outside):
        prefix = _clause_prefix(outside, match.start())
        if _names_other_table(prefix, own_ref):
            raise UnsupportedSectionFormat(
                f"{where}: typed declaration {match.group(1)!r} follows a reference to another "
                f"table: {prefix[-80:]!r}"
            )
        found.append(match.group(1))
    return tuple(found)


def _own_primary_key_columns(lines: list[str], own_ref: str | None, where: str) -> list[str]:
    """Columns of ``PRIMARY KEY (…)`` clauses on the section's own key lines; a clause anywhere
    else, or after a reference to another table in the same clause, is refused (P8-F1-R1)."""
    columns: list[str] = []
    for line in lines:
        for match in _PRIMARY_KEY.finditer(line):
            own_position = line.startswith(_OWN_KEY_LINE_PREFIXES)
            prefix = _clause_prefix(line, match.start())
            if not own_position or _names_other_table(prefix, own_ref):
                raise UnsupportedSectionFormat(
                    f"{where}: PRIMARY KEY outside the section's own key position or after a "
                    f"reference to another table: {line[:80]!r}"
                )
            columns += [column.strip() for column in match.group(1).split(",")]
    return columns


def extract_declarations(body: str, where: str, own_ref: str | None = None) -> Declarations:
    """The top-level column declarations of a 04 section body, by its format. ``own_ref`` is the
    section's table id (``T-…-nn``); any other table id is a foreign reference."""
    lines = body.splitlines()
    header_index = next((i for i, line in enumerate(lines) if line.startswith("| Column |")), None)
    if header_index is None:
        prose = [line for line in lines if line.startswith("Columns (")]
        if len(prose) != 1:
            raise UnsupportedSectionFormat(f"{where}: no column table and no 'Columns (…):' line")
        line = prose[0]
        depth = 0
        end = len("Columns")
        for end in range(len("Columns"), len(line)):
            if line[end] == "(":
                depth += 1
            elif line[end] == ")":
                depth -= 1
                if depth == 0:
                    break
        if depth != 0 or not line[end + 1 :].startswith(":"):
            raise UnsupportedSectionFormat(f"{where}: malformed 'Columns (…):' line")
        columns = _segment_columns(line[end + 2 :], f"{where} prose line")
        if len(columns) != len(set(columns)):
            raise UnsupportedSectionFormat(f"{where}: duplicate declaration in the prose line")
        pk = _own_primary_key_columns(lines, own_ref, where)
        return Declarations("prose", tuple(columns + sorted(set(pk) - set(columns))), ())
    header = _cells(lines[header_index])
    rows: list[str] = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(line)
    outside_lines = lines[:header_index] + lines[header_index + 2 + len(rows) :]
    if header == LITERAL_HEADER:
        columns = []
        for row in rows:
            first = _cells(row)[0]
            if _SC_LIST.fullmatch(first):
                for standard_set in first.split(","):
                    columns += STANDARD_SETS[standard_set.strip()]
                continue
            literal = _LITERAL_CELL.fullmatch(first)
            if literal is None:
                raise UnsupportedSectionFormat(f"{where}: literal table first cell {first!r}")
            columns.append(literal.group(1))
        paragraph = _paragraph_columns("\n".join(outside_lines), own_ref, where)
        return Declarations("literal", tuple(columns), paragraph)
    if header == HYBRID_HEADER:
        columns = []
        for row in rows:
            cells = _cells(row)
            columns += _segment_columns(cells[0], f"{where} hybrid first cell")
            columns += _notes_columns(cells[1] if len(cells) > 1 else "", own_ref, where)
        if len(columns) != len(set(columns)):
            raise UnsupportedSectionFormat(f"{where}: duplicate declaration in the hybrid table")
        pk = _own_primary_key_columns(outside_lines, own_ref, where)
        return Declarations("hybrid", tuple(columns + sorted(set(pk) - set(columns))), ())
    raise UnsupportedSectionFormat(f"{where}: unknown column table header {header}")


def section_declarations(table: str) -> Declarations:
    ref, body = doc_sections()[table]
    return extract_declarations(body, table, own_ref=ref)


def catalogue_columns(table: str, *, pending_only: bool = False) -> frozenset[str]:
    """Catalogued columns of ``table``; with ``pending_only`` the columns of an ACTIVE table that
    are still PENDING are excluded, and vice versa."""
    entries = [entry for entry in CLASSIFICATION.values() if entry.table == table]
    if pending_only:
        return frozenset(e.column for e in entries if e.status is Status.PENDING)
    return frozenset(e.column for e in entries if e.status is Status.ACTIVE)


def declaration_mismatch(
    declared: frozenset[str], catalogued: frozenset[str]
) -> tuple[frozenset[str], frozenset[str]]:
    """(declared but not catalogued, catalogued but not declared)."""
    return declared - catalogued, catalogued - declared


def test_prv_01_every_personal_column_classified() -> None:
    """BUILD_SPEC SOP-5: every code column matching the PRV-01 pattern has a classification, and the
    five named columns are C3."""
    personal = {key for key in code_columns() if PERSONAL_COLUMN_PATTERN.search(key[1])}
    assert len(personal) >= 50, "the PRV-01 pattern should match the membership_id family too"
    unclassified = sorted(key for key in personal if key not in CLASSIFICATION)
    assert unclassified == [], unclassified
    for key in sorted(SPEC_NAMED_C3):
        assert data_class(*key) is DataClass.C3, key
        assert CLASSIFICATION[key].basis is Basis.SPEC, key
    for key in sorted(PRV_01_C3):
        entry = CLASSIFICATION[key]
        assert entry.data_class is DataClass.C3 and entry.basis is Basis.SPEC, key
        assert entry.rule == "SPEC-C3", key
    assert CLASSIFICATION[("contract_cost_asset", "payee")].status is Status.PENDING


def test_prv_01_catalogue_covers_every_code_column() -> None:
    """Every column of ``erev_api.db.tables`` has an ACTIVE entry (fails on an omitted or new
    column)."""
    report = check_coverage(code_columns())
    assert report.missing == (), f"unclassified code columns: {report.missing}"
    assert len(code_columns()) == sum(
        1 for entry in CLASSIFICATION.values() if entry.status is Status.ACTIVE
    )


def test_prv_01_catalogue_names_only_existing_columns() -> None:
    """Every ACTIVE entry names a column that exists in the code (fails on a typo or a dropped
    column)."""
    report = check_coverage(code_columns())
    assert report.unknown == (), f"catalogue entries naming no code column: {report.unknown}"
    for name, table in TABLE_CLASSIFICATION.items():
        if table.status is Status.ACTIVE:
            assert name in {t.name for t in tables.metadata.sorted_tables}, name


def test_prv_01_pending_entries_reconcile() -> None:
    """PENDING entries stay absent from the code until reconciled; a wholly pending table's
    catalogued columns equal its 04 top-level declarations in both directions; a DOC_04 pending
    column of an active table is a typed declaration in its section's paragraphs; a LANE_BRANCH
    entry names its lane and is not declared on main."""
    report = check_coverage(code_columns())
    assert report.landed == (), (
        f"pending catalogue entries have landed in the code and must be reconciled: {report.landed}"
    )
    pending = [entry for entry in CLASSIFICATION.values() if entry.status is Status.PENDING]
    assert pending, "the D-96 tables are pending at this revision (lane P2's columns reconciled)"
    for name, table in TABLE_CLASSIFICATION.items():
        if table.status is Status.PENDING:
            declared = section_declarations(name)
            assert declared.format in ("literal", "hybrid", "prose"), name
            doc_only, cat_only = declaration_mismatch(
                frozenset(declared.columns), catalogue_columns(name, pending_only=True)
            )
            assert not doc_only, f"{name}: declared in 04, not catalogued: {sorted(doc_only)}"
            assert not cat_only, f"{name}: catalogued, not declared in 04: {sorted(cat_only)}"
    for entry in pending:
        assert entry.pending is not None, (entry.table, entry.column)
        if TABLE_CLASSIFICATION[entry.table].status is Status.PENDING:
            assert entry.pending is PendingSource.DOC_04, (entry.table, entry.column)
            continue
        declared = section_declarations(entry.table)
        assert declared.format == "literal", entry.table
        if entry.pending is PendingSource.DOC_04:
            assert entry.column in declared.paragraph, (entry.table, entry.column)
        else:
            assert entry.pending is PendingSource.LANE_BRANCH
            assert "lane" in entry.note, (entry.table, entry.column)
            assert entry.column not in declared.columns + declared.paragraph, (
                f"{entry.table}.{entry.column} is declared on main: flip it to DOC_04"
            )
    lane_branch = sorted(
        (e.table, e.column) for e in pending if e.pending is PendingSource.LANE_BRANCH
    )
    # Lane P2's two T-PLT-06 columns were the LANE_BRANCH entries; reconciled at its merge (0061).
    assert lane_branch == []


def test_prv_01_catalogue_matches_04_tables() -> None:
    """Every 04 table heading is catalogued under its table id, in 04 order; literal sections list
    exactly the catalogued active columns; every typed declaration in a literal section's
    paragraphs is either a table column or a catalogued PENDING column; prose and hybrid sections
    declare exactly the catalogued columns (both directions)."""
    sections = doc_sections()
    assert set(sections) == set(TABLE_CLASSIFICATION), set(sections) ^ set(TABLE_CLASSIFICATION)
    formats: dict[str, int] = {}
    for name, table in TABLE_CLASSIFICATION.items():
        ref, _ = sections[name]
        assert table.ref == ref, (name, table.ref, ref)
        declared = section_declarations(name)
        formats[declared.format] = formats.get(declared.format, 0) + 1
        assert len(declared.columns) == len(set(declared.columns)), name
        if declared.format == "literal":
            expected = (
                catalogue_columns(name)
                if table.status is Status.ACTIVE
                else catalogue_columns(name, pending_only=True)
            )
            doc_only, cat_only = declaration_mismatch(frozenset(declared.columns), expected)
            assert not doc_only and not cat_only, (name, sorted(doc_only), sorted(cat_only))
            for column in declared.paragraph:
                if column not in declared.columns:
                    assert column in catalogue_columns(name, pending_only=True), (
                        f"{name}: 04 declares pending column {column} without a catalogue entry"
                    )
        else:
            doc_only, cat_only = declaration_mismatch(
                frozenset(declared.columns), catalogue_columns(name, pending_only=True)
            )
            assert not doc_only and not cat_only, (name, sorted(doc_only), sorted(cat_only))
    # 154 (incl. T-PLT-47, 04 1.59) + T-MIG-04 / T-MIG-05 (04 rev 1.60, lane F-LMG) = 156 literal
    # column tables; + T-PLT-48 audit_event_contract (04 rev 1.154, lane API-GAPS) = 157;
    # + T-PLT-49 file_upload (04 rev 1.189, lane SECFIX-PLT) = 158
    assert formats == {"literal": 158, "hybrid": 2, "prose": 5}, formats
    assert [t.name for t in TABLES] == list(sections), "catalogue follows 04 document order"


def test_prv_01_entries_consistent() -> None:
    """Rules, bases, classes and erasure values agree with the catalogue's own contract."""
    rule_ids = {rule.id for rule in RULES}
    assert len(rule_ids) == len(RULES)
    c3 = {(e.table, e.column) for e in columns_of(DataClass.C3)}
    assert c3 == PRV_01_C3 | PROPOSED_C3, c3 ^ (PRV_01_C3 | PROPOSED_C3)
    c0 = {e.table for e in columns_of(DataClass.C0)}
    assert c0 == PUBLIC_TABLES
    for entry in CLASSIFICATION.values():
        assert entry.rule in rule_ids, entry
        if entry.basis is Basis.SPEC:
            assert entry.rule.startswith("SPEC-"), entry
        else:
            assert re.fullmatch(r"R0[1-8]", entry.rule), entry
        if entry.data_class is DataClass.C3:
            assert entry.erasure is not Erasure.NONE, (
                f"{entry.table}.{entry.column}: C3 without erasure"
            )
        if entry.erasure in (Erasure.AUDIT_HMAC, Erasure.TOKENISED):
            assert entry.data_class is DataClass.C2, entry
        elif entry.erasure is not Erasure.NONE:
            assert entry.data_class is DataClass.C3, entry
        assert entry.purpose.endswith("."), entry
        if entry.table in PUBLIC_TABLES:
            assert entry.data_class is DataClass.C0, entry
        else:
            assert entry.data_class is not DataClass.C0, entry
    proposed = sum(1 for e in CLASSIFICATION.values() if e.basis is Basis.PROPOSED)
    spec = sum(1 for e in CLASSIFICATION.values() if e.basis is Basis.SPEC)
    assert spec >= 500 and proposed >= 2000, (spec, proposed)
    no_path = sorted(
        (e.table, e.column) for e in CLASSIFICATION.values() if e.erasure is Erasure.NO_PATH
    )
    assert no_path == [
        ("access_review_item", "user_email_snapshot"),
        ("contract_cost_asset", "payee"),
        ("file_object", "original_filename"),
        ("file_upload", "original_filename"),
        ("user_mfa_factor", "secret_ciphertext"),
        ("user_recovery_code", "code_hash"),
    ], no_path


# ---- P8-F1 negative controls (Codex review PRODUCTION-P8-CLASSIFICATION-REVIEW-6abdd98 §F1).
# Each mutation was accepted by the word-membership predicate of the reviewed test and must be
# detected by the declaration comparison above.


def test_p8_f1_control_deleted_pending_entry_is_detected() -> None:
    """Mutation 1: delete the pending entry ``release_validation_attempt.population`` from the
    catalogue; 04 line "Columns (draft §4b verbatim): … `population` jsonb N (…)" still declares
    it, so the comparison reports a declared-but-not-catalogued column."""
    declared = section_declarations("release_validation_attempt")
    assert declared.format == "prose"
    assert "population" in declared.columns
    mutated = catalogue_columns("release_validation_attempt", pending_only=True) - {"population"}
    doc_only, cat_only = declaration_mismatch(frozenset(declared.columns), mutated)
    assert doc_only == {"population"} and cat_only == frozenset()
    # JSON members of the declaration's note are not declarations.
    assert not {"groups", "open_activity", "remaining", "strata"} & set(declared.columns)


def test_p8_f1_control_added_declared_column_is_detected() -> None:
    """Mutation 2: declare ``new_personal_email`` text Y in a prose line and in a hybrid table
    without a catalogue entry; the comparison reports a declared-but-not-catalogued column."""
    ref, prose_body = doc_sections()["release_validation"]
    assert prose_body.count("SC-C, SC-M.") == 1
    mutated_prose = prose_body.replace("SC-C, SC-M.", "`new_personal_email` text Y; SC-C, SC-M.")
    declared = extract_declarations(mutated_prose, "release_validation (mutated)", own_ref=ref)
    doc_only, cat_only = declaration_mismatch(
        frozenset(declared.columns), catalogue_columns("release_validation", pending_only=True)
    )
    assert doc_only == {"new_personal_email"} and cat_only == frozenset()

    ref, hybrid_body = doc_sections()["computation_evidence"]
    assert hybrid_body.count("\n| SC-C | |\n") == 1
    mutated_hybrid = hybrid_body.replace(
        "\n| SC-C | |\n", "\n| `new_personal_email` text Y | a note |\n| SC-C | |\n"
    )
    declared = extract_declarations(mutated_hybrid, "computation_evidence (mutated)", own_ref=ref)
    doc_only, cat_only = declaration_mismatch(
        frozenset(declared.columns), catalogue_columns("computation_evidence", pending_only=True)
    )
    assert doc_only == {"new_personal_email"} and cat_only == frozenset()


def test_p8_f1_control_cross_table_mention_is_not_a_declaration() -> None:
    """Mutation 3: invent ``computation_evidence.shred_reason`` in the catalogue. The section
    mentions `shred_reason` in its retention paragraph (a T-PLT-29 column), which is not a
    top-level declaration, so the comparison reports a catalogued-but-not-declared column."""
    _, body = doc_sections()["computation_evidence"]
    assert "shred_reason" in body, "the control relies on the cross-table mention at 04 T-CON-25"
    declared = section_declarations("computation_evidence")
    assert declared.format == "hybrid"
    assert "shred_reason" not in declared.columns
    # Referenced objects' fields in the hybrid notes are not declarations either.
    assert not {"last_chain_seq", "chain_seq", "previous_stream_heads"} & set(declared.columns)
    mutated = catalogue_columns("computation_evidence", pending_only=True) | {"shred_reason"}
    doc_only, cat_only = declaration_mismatch(frozenset(declared.columns), mutated)
    assert doc_only == frozenset() and cat_only == {"shred_reason"}


def test_p8_f1_control_unsupported_format_fails() -> None:
    """A section in none of the three formats, a hybrid first cell that does not start with a
    declaration, or a prose segment that is bare text fails instead of degrading to word
    membership."""
    with pytest.raises(UnsupportedSectionFormat):
        extract_declarations("- **Purpose.** Words `email` and `name` only.\n", "synthetic")
    with pytest.raises(UnsupportedSectionFormat):
        extract_declarations(
            "| Column | Notes |\n|---|---|\n| SC-T; see `other_table` for the rest | |\n",
            "synthetic hybrid",
        )
    with pytest.raises(UnsupportedSectionFormat):
        extract_declarations(
            "Columns (draft): SC-T; `a` uuid N; the rest as in T-CON-07; SC-C.\n",
            "synthetic prose",
        )
    with pytest.raises(UnsupportedSectionFormat):
        extract_declarations(
            "| Column | Kind |\n|---|---|\n| `a` | uuid |\n", "synthetic unknown header"
        )


# ---- P8-F1-R1 negative controls (Codex retest PRODUCTION-P8-F1-RETEST-20ae32a §R1): reference
# text carrying declaration syntax must not become an own-table column. Both passages were
# extracted as declarations by the test at 0a82c07 (rejecting the correct catalogue and accepting
# an invented entry); they are refused now, and the legitimate declarations survive.

_R1_NOTES_ANCHOR: Final = "source of `previous_stream_heads`"
_R1_NOTES_PASSAGE: Final = (
    "; reference only: T-PLT-29 declares `shred_reason` text Y (not a column of this table)"
)
_R1_PK_PASSAGE: Final = (
    "Reference only: T-PLT-29 has PRIMARY KEY (tenant_id, foreign_object_id); those fields are "
    "not declarations of this table."
)


def test_p8_f1_r1_control_referenced_notes_declaration_is_refused() -> None:
    """R1 passage 1: a typed foreign ``shred_reason`` inside T-CON-25's Notes with reference-only
    wording is refused as ambiguous rather than extracted; a leading-position variant naming the
    other table is refused too; the legitimate Notes declarations still count."""
    ref, body = doc_sections()["computation_evidence"]
    assert body.count(_R1_NOTES_ANCHOR) == 1
    with pytest.raises(UnsupportedSectionFormat, match="reference position"):
        extract_declarations(
            body.replace(_R1_NOTES_ANCHOR, _R1_NOTES_ANCHOR + _R1_NOTES_PASSAGE),
            "computation_evidence (R1 passage 1)",
            own_ref=ref,
        )
    leading_variant = _R1_NOTES_ANCHOR + "; `shred_reason` text Y of T-PLT-29 (reference only)"
    with pytest.raises(UnsupportedSectionFormat, match="names another table"):
        extract_declarations(
            body.replace(_R1_NOTES_ANCHOR, leading_variant),
            "computation_evidence (R1 passage 1, leading)",
            own_ref=ref,
        )
    declared = section_declarations("computation_evidence")
    assert {"book_codes", "backfill_verification_id"} <= set(declared.columns)
    assert "shred_reason" not in declared.columns
    # A typed declaration following a foreign reference in a literal section's paragraph is
    # refused the same way, while a section's own pending declaration still counts. T-PLT-38's
    # ``validation_level`` was that pending paragraph until 04 rev 1.29 lifted it into a column row
    # (lane P5 integration slice 1), so the paragraph form is exercised on a synthetic copy of the
    # rev 1.13 wording and the lifted column is asserted where it now lives.
    ref, literal_body = doc_sections()["engine_release"]
    lifted = extract_declarations(literal_body, "engine_release", ref)
    assert "validation_level" in lifted.columns and "validation_level" not in lifted.paragraph
    pending_form = (
        "\n\nRev 1.13 pending column (D-96; rev pending lanes P1 and P5): "
        "`validation_pending_probe` text N, default `'PATCH'` — the author's declaration from the "
        "REL-01 manifest.\n"
    )
    own_pending = extract_declarations(
        literal_body.rstrip("\n") + pending_form, "engine_release (rev 1.13 form)", own_ref=ref
    )
    assert "validation_pending_probe" in own_pending.paragraph
    with pytest.raises(UnsupportedSectionFormat, match="reference to another table"):
        extract_declarations(
            literal_body.rstrip("\n")
            + "\n\nReference only: T-PLT-06 gains `hmac_key_id` text Y in rev 1.12.\n",
            "engine_release (R1 paragraph variant)",
            own_ref=ref,
        )


def test_p8_f1_r1_control_foreign_primary_key_is_refused() -> None:
    """R1 passage 2: a foreign ``PRIMARY KEY (tenant_id, foreign_object_id)`` reference is refused
    whether it stands as its own paragraph or is appended to the section's own key bullet; the
    own primary key still declares ``contract_computation_id``."""
    ref, body = doc_sections()["computation_evidence"]
    with pytest.raises(UnsupportedSectionFormat, match="PRIMARY KEY"):
        extract_declarations(
            body.rstrip("\n") + "\n\n" + _R1_PK_PASSAGE + "\n",
            "computation_evidence (R1 passage 2)",
            own_ref=ref,
        )
    own_bullet = "`PRIMARY KEY (tenant_id, contract_computation_id)`."
    assert body.count(own_bullet) == 1
    with pytest.raises(UnsupportedSectionFormat, match="PRIMARY KEY"):
        extract_declarations(
            body.replace(own_bullet, own_bullet + " " + _R1_PK_PASSAGE),
            "computation_evidence (R1 passage 2, on the own key line)",
            own_ref=ref,
        )
    declared = section_declarations("computation_evidence")
    assert "contract_computation_id" in declared.columns
    assert "foreign_object_id" not in declared.columns
    # The prose form's own key (T-SL-11, inside its Columns line) still counts as well.
    assert "subledger_posting_id" in section_declarations("posting_attribution").columns
