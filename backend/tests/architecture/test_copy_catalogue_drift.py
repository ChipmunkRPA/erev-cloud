"""Copy catalogue drift DG-ARC-13 (dev-guide §6.8; PRD §5.5; 04 §15.2, §15.4; BUILD_SPEC FND-9).

The tests read docs/02-PRD.md and docs/04-DATA_MODEL.md read-only. ERR rows give problem copy for
every §15.2 slug; IMP rows give finding copy for every §15.4 code.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRD = ROOT / "docs" / "02-PRD.md"
DATA_MODEL = ROOT / "docs" / "04-DATA_MODEL.md"

SLUG = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
CODE = re.compile(r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
SEVERITIES = frozenset({"ERROR", "WARNING", "INFO"})
# Convention rows: validation-failed with the rule id of an API-C convention (BS1-D-09).
# CTR-17 (D-98 140; PRD 1.14): the two REQ rule ids of a modification submission.
CONVENTION_ROWS = {
    "ERR-05": "API-C-04",
    "ERR-35": "API-C-06",
    "ERR-53": "REQ-PLT-015",
    "ERR-54": "REQ-MOD-002",
    # MAIN DEFECT 3 (PRD 1.18; 04 1.84): the ENGINE_SPEC rule id of the S06-R-19 shape refusal.
    "ERR-55": "S06-R-19",
    # Supervisor ruling R-42 (b) (PRD 1.42): the three ENGINE_SPEC_B rule ids lane FIX-D2's
    # refusals return as ``errors[].rule_id`` — the period balance a trace cannot answer, a dataset
    # the lock cannot freeze, a freeze cutoff that does not cover the period.
    "ERR-58": "S15-R-07a",
    "ERR-59": "S15-R-18",
    "ERR-60": "S15-R-18c",
    # Rulings R-58 (b) and R-61 (f) (PRD 1.52; 04 1.123): the two refusals of an entity-book
    # adoption, both under the rule id of T-REF-03.
    "ERR-61": "T-REF-03",
    "ERR-62": "T-REF-03",
    # BUILD_SPEC CLO-15 (PRD 1.74; 04 1.145): the three refusals of a journal run calculation
    # that the entity's general ledger connection decides.
    "ERR-67": "T-SL-07",
    "ERR-68": "S14-R-21",
    "ERR-69": "S14-R-21",
    # Item ADJ-VOID-REFUSE-1 (supervisor ruling R-112 (b); PRD 1.87; 04 1.158): the refused void of
    # a posted adjustment's event and the edit by anyone but the creator, both under PRD SM-10.
    "ERR-70": "SM-10",
    "ERR-71": "SM-10",
    # The period pin (supervisor rulings R-105 (3) and of 2026-10-01; PRD 1.86; 04 1.157): a
    # command that recorded an event before a period lock and would write after it.
    "ERR-72": "PERIOD_STATE_MOVED",
    # Supervisor rulings R-112 (e) and R-114 (d) (PRD 1.84; 04 1.155): the close commands refuse
    # a period of the LEGACY book, which follows the close of the primary book.
    "ERR-76": "LEGACY_FOLLOWS_PRIMARY",
    # Item CFG-BACKDATE-1 (supervisor rulings R-112 (i) and R-113 (b); PRD 1.89; 04 §16.5 rev
    # 1.160): a configuration version that supersedes a published one is refused an effective
    # date that reaches back, under the rule id of the requirement it serves.
    "ERR-75": "REQ-POL-007",
    # Supervisor ruling R-116 (h) (PRD 1.111; 04 1.182): the lock decision's refusal when the
    # `future` next period, which it would open, is held by another request.
    "ERR-78": "NEXT_PERIOD_HELD",
    "ERR-85": "EARLIER_PERIOD_HELD",
    # Item JRN-FAILED-CANCEL-1 (supervisor ruling R-112 (c); PRD 1.88; 04 1.159): the ledger holds
    # a failed batch, a run partly in a ledger is not cancelled (both E-34), and a rendered batch
    # whose lines changed after its approval is not downloaded.
    "ERR-73": "E-34",
    "ERR-74": "E-34",
    "ERR-79": "BATCH_RECOUNT",
    # Item MOD-DISCARD-1 (supervisor ruling R-118 (e); PRD 1.117; 04 1.188): the discard of a
    # draft modification refused while a review of its own judgement record is pending,
    # under the rule id of PRD SM-03.
    "ERR-82": "SM-03",
    # BUILD_SPEC SNP-5 (PRD 1.106; 04 1.177; item CFG-PLATFORM-PIN-1): the refusing default of the
    # snapshot retention policy, named in ``errors[].rule_id``.
    "ERR-77": "RETENTION_UNSET",
    # Items MOD-LINKED-ESTIMATES-1 and EST-DISCARD-1 (supervisor rulings R-118 (e) and R-119 (e);
    # PRD 1.139; 04 1.210): a modification's discard while a linked estimate version waits for
    # approval, its submission (and, as the backstop, its approval) while a linked version is not
    # approved — both under PRD SM-03 — and the submission of an estimate version whose
    # modification was discarded, under PRD SM-04.
    "ERR-83": "SM-03",
    "ERR-87": "SM-03",
    "ERR-88": "SM-04",
    # Items REG-VERSION-WHOLE-SET-1 and CFG-PLATFORM-PIN-1 (supervisor rulings R-115 (e) and
    # R-117 (b); PRD 1.112; 04 §16.5 rev 1.183): a policy version that would take effect at or
    # before the published version of its scope key, dated (ERR-80) or without a date (ERR-81).
    "ERR-80": "REGISTRY_EFFECTIVE_ORDER",
    "ERR-81": "REGISTRY_EFFECTIVE_ORDER",
    # Item JR-CLOSED-PERIOD-GUARD-1 (supervisor ruling R-97 (7); PRD 1.134; 04 1.205): a journal
    # run is neither calculated nor cancelled in a closed period.
    "ERR-86": "RUN_PERIOD_CLOSED",
    # Item REG-VERSION-WHOLE-SET-1 (the supervisor's ruling of 2026-10-01 on the item's report;
    # PRD 1.112; 04 T-PLT-32 rev 1.183): a rejected or withdrawn policy version is not reopened
    # once another version of its scope key has been published since its last submit.
    "ERR-92": "REGISTRY_BASIS_SUPERSEDED",
    # Items EST-ONE-OPEN-VERSION-1 and the constraint's judgement record (the supervisor's
    # rulings of 2026-10-01; PRD 1.168; 04 T-CON-13, §16.14 rev 1.241): a second open version of
    # an estimated element, and the approval of a variable-consideration version whose
    # CONSTRAINT record is not reviewed — both under PRD SM-04.
    "ERR-93": "SM-04",
    "ERR-94": "SM-04",
    # Item JRN-EMPTY-RUN-1 (the supervisor's ruling of 2026-10-01; PRD 1.174; 04 1.248): where a
    # journal run of the period that is not cancelled stands, no further run is made without a line.
    "ERR-96": "RUN_NOTHING_PENDING",
    # Item MOD-LINKED-JUDGEMENTS-1 (the supervisor's rulings of 2026-10-01; PRD 1.169; 04 §16.14
    # rev 1.242): the submission of a modification (and, as the backstop, its approval) while
    # a judgement record whose subject it is stands DRAFT or SUBMITTED — under PRD SM-03.
    "ERR-95": "SM-03",
    # Item RPT-PERIOD-KEY-CALENDARS-1 (the supervisor's rulings of 2026-10-02; PRD 1.180; 04
    # T-RPT-01 rule 6 rev 1.264): a report run over entities of more than one fiscal calendar
    # that names a period by key, or of a report whose columns are period keys.
    "ERR-97": "CALENDARS_DIFFER",
    # Finding F4 of the independent review of 2026-10-01 (the supervisor's ruling of 2026-10-02;
    # PRD 1.187; 04 §14.1 DB-07 rev 1.229): a transaction that holds a ledger chain head meets a
    # period state row a lock decision holds, and does not wait for it.
    "ERR-98": "PERIOD_LOCK_IN_FLIGHT",
    # Item SUBLEDGER-LINE-JOURNAL-RUN-1 (the supervisor's ruling of 2026-10-02; PRD 1.195; 04
    # T-SL-06 drill-back 1.288): the drill of a journal line of a run whose record of the lines
    # it left out cannot be read.
    "ERR-101": "RUN_RECORD_UNREADABLE",
    # Item POLICY-OVERRIDE-WITHDRAW-1 (supervisor ruling R-126 (b) (4) and (c); PRD 1.209; 04
    # T-CON-23 "Not offered in release 1.0" rev 1.322): every creation of a policy override, on
    # the slug of a level POLICIES does not allow — in release 1.0 no parameter allows C or O.
    "ERR-102": "POLICY_OVERRIDE_NOT_OFFERED",
    # Item PRODUCT-POLICY-VALUE-NOT-READ-1 (supervisor ruling R-126 (c) and the supervisor's
    # rulings of 2026-10-03; PRD 1.210; 04 T-REF-20 and T-REF-23 rev 1.323): a product or an
    # obligation template states a value of a parameter the engine reads for a contract, which
    # no computation would read.
    "ERR-103": "POLICY_PRODUCT_LEVEL_NOT_READ",
}
# The slug of a convention row that is not ``validation-failed`` (R-42 (b): the lock decision's
# refusals are 409 ``invalid-transition`` with a governed rule id).
CONVENTION_SLUGS = {
    "ERR-59": "invalid-transition",
    "ERR-60": "invalid-transition",
    "ERR-70": "invalid-transition",
    "ERR-71": "forbidden",
    "ERR-72": "lock-conflict",
    "ERR-76": "invalid-transition",
    "ERR-73": "invalid-transition",
    "ERR-74": "invalid-transition",
    "ERR-77": "precondition-failed",  # a job refusal on the 412 slug
    "ERR-78": "lock-conflict",
    "ERR-79": "invalid-transition",
    "ERR-82": "invalid-transition",
    "ERR-83": "invalid-transition",
    "ERR-85": "lock-conflict",
    "ERR-86": "period-closed",
    "ERR-87": "invalid-transition",
    "ERR-88": "invalid-transition",
    "ERR-92": "invalid-transition",
    "ERR-93": "invalid-transition",
    "ERR-94": "invalid-transition",
    "ERR-96": "invalid-transition",
    "ERR-95": "invalid-transition",
    "ERR-98": "lock-conflict",
    "ERR-101": "invalid-transition",
    "ERR-102": "policy-level-not-allowed",
}
# Tables 15.4-A onward; H holds withdrawn codes and S synonyms.
CODE_TABLES = ("A", "B", "C", "D", "E", "F", "G", "I", "H", "S")


@dataclass(frozen=True, slots=True)
class ErrRow:
    id: str
    slug: str | None
    slug_cell: str
    status: int


@dataclass(frozen=True, slots=True)
class ImpRow:
    id: str
    code_cell: str
    severity: str


@cache
def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _unescaped(cell: str) -> str:
    """The ONE seam of PRD rev 1.19's copy-cell convention (COPY-ESCAPE-1): exactly ``\\|`` → ``|``
    and ``\\"`` → ``"``; no other escape is interpreted."""
    return cell.replace("\\|", "|").replace('\\"', '"')


def _cells(line: str) -> list[str]:
    """A table row's cells: split on UNESCAPED pipes only (one leading and one trailing pipe
    removed), each cell stripped and unescaped through ``_unescaped`` (PRD rev 1.19)."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [_unescaped(cell.strip()) for cell in UNESCAPED_PIPE.split(body)]


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def _copy_section() -> str:
    return _between(_text(PRD), "\n### 5.5 User-facing copy", "\n### 5.6 ")


def err_rows() -> list[ErrRow]:
    rows: list[ErrRow] = []
    for line in _copy_section().splitlines():
        cells = _cells(line) if line.startswith("|") else []
        # two or three digits, as the IMP rows below: ERR-101 is the first of three (PRD 1.195)
        if not cells or not re.fullmatch(r"ERR-\d{2,3}", cells[0]):
            continue
        first = re.match(r"^`([^`]+)`", cells[1])
        slug = first.group(1) if first and SLUG.fullmatch(first.group(1)) else None
        rows.append(ErrRow(cells[0], slug, cells[1], int(cells[2])))
    return rows


def imp_rows() -> list[ImpRow]:
    rows: list[ImpRow] = []
    for line in _copy_section().splitlines():
        cells = _cells(line) if line.startswith("|") else []
        if cells and re.fullmatch(r"^IMP-\d{2,3}$", cells[0]):
            rows.append(ImpRow(cells[0], cells[1], cells[2]))
    return rows


def problem_slugs() -> dict[str, int]:
    section = _between(_text(DATA_MODEL), "\n### 15.2 Problem catalogue", "\n**Table 15.2-S")
    slugs: dict[str, int] = {}
    for line in section.splitlines():
        if line.startswith("| `"):
            cells = _cells(line)
            literal = re.fullmatch(r"`([a-z0-9-]+)`", cells[0])
            assert literal is not None, line
            slugs[literal.group(1)] = int(cells[1])
    return slugs


def slug_synonyms() -> set[str]:
    section = _between(_text(DATA_MODEL), "\n**Table 15.2-S", "\n### 15.3 ")
    canonical = problem_slugs()
    synonyms: set[str] = set()
    for line in section.splitlines()[1:]:
        if not line.startswith("|"):
            continue
        for token in re.findall(r"`([^`]+)`", _cells(line)[0]):
            if SLUG.fullmatch(token) and token not in canonical:
                synonyms.add(token)
    return synonyms


def code_tables() -> dict[str, dict[str, str]]:
    """Codes of each lettered 04 §15.4 table with their severity cells, in document order."""
    section = _between(_text(DATA_MODEL), "\n### 15.4 Finding", "\n## 16. ")
    tables: dict[str, dict[str, str]] = {}
    letter: str | None = None
    for line in section.splitlines():
        heading = re.match(r"^\*\*Table 15\.4-([A-Z]) ", line)
        if heading:
            letter = heading.group(1)
            tables[letter] = {}
            continue
        if letter is None or not line.startswith("| `"):
            continue
        cells = _cells(line)
        literal = re.fullmatch(r"`([^`]+)`", cells[0])
        if literal and CODE.fullmatch(literal.group(1)):
            assert literal.group(1) not in tables[letter], line
            tables[letter][literal.group(1)] = cells[1]
    return tables


def test_dg_arc_13_err_rows_cover_slugs() -> None:
    slugs = problem_slugs()
    synonyms = slug_synonyms()
    # + the two SYNC-PROBLEM-SHAPE-1 slugs (04 1.90; PRD 1.20)
    # + earlier-period-open (supervisor ruling R-6; 04 1.106; PRD 1.35)
    # + statement-timeout (supervisor ruling R-97 (6); 04 1.144; PRD 1.73)
    assert len(slugs) == 53
    assert len(synonyms) == 14
    rows = err_rows()
    # 52 + ERR-53 / ERR-54 (CTR-17; D-98 140; PRD 1.14) + ERR-55 (MAIN DEFECT 3; PRD 1.18)
    # + ERR-56 / ERR-57 (SYNC-PROBLEM-SHAPE-1; PRD 1.20).
    # + ERR-58 to ERR-60 (supervisor ruling R-42 (b); PRD 1.42): S15-R-07a, S15-R-18, S15-R-18c.
    # + ERR-61 / ERR-62 (rulings R-58 (b) and R-61 (f); PRD 1.52).
    # + ERR-65 earlier-period-open (supervisor ruling R-6; PRD 1.35; number assigned by the
    # supervisor).
    # + ERR-64 (the slug-less 503) and ERR-66 (statement-timeout; PRD 1.73; rulings R-97 (6),
    # R-103 (c), R-108 (b) (3)).
    # + ERR-67 to ERR-69 (BUILD_SPEC CLO-15; PRD 1.74).
    # + ERR-70 / ERR-71 (item ADJ-VOID-REFUSE-1; ruling R-112 (b); PRD 1.87).
    # + ERR-76 LEGACY_FOLLOWS_PRIMARY (rulings R-112 (e) and R-114 (d); PRD 1.84; number assigned
    # by the supervisor — the numbers between are other items' and join at their merges).
    # + ERR-64, ERR-66 (lane OPS, the kernel's error mapping; PRD 1.73). The gap is a number the
    # supervisor assigned to another lane whose row is not in the table yet: ERR-63 (lane
    # FIX-D2's parked slice) joins this list with its row.
    # + ERR-75 (item CFG-BACKDATE-1; rulings R-112 (i) and R-113 (b); PRD 1.89; number assigned by
    # the supervisor), in number order before ERR-76.
    # + ERR-78 NEXT_PERIOD_HELD (ruling R-116 (h); PRD 1.111; number assigned by the supervisor).
    # + ERR-85 EARLIER_PERIOD_HELD (ruling R-119 (d); PRD 1.111; number assigned by the supervisor).
    # + ERR-73 / ERR-74 / ERR-79 (item JRN-FAILED-CANCEL-1; ruling R-112 (c); PRD 1.88); ERR-72
    # and ERR-77 are other lanes' numbers and join at their merges.
    # + ERR-82 (item MOD-DISCARD-1; supervisor ruling R-118 (e); PRD 1.117; number assigned by
    # the supervisor).
    # + ERR-77 RETENTION_UNSET (BUILD_SPEC SNP-5; PRD 1.106; number assigned by the supervisor).
    # + ERR-83, ERR-87, ERR-88 (items MOD-LINKED-ESTIMATES-1 and EST-DISCARD-1; PRD 1.139; numbers
    # assigned by the supervisor, register indexes 97 and 119).
    # + ERR-80 / ERR-81 REGISTRY_EFFECTIVE_ORDER (items REG-VERSION-WHOLE-SET-1 and
    # CFG-PLATFORM-PIN-1; rulings R-115 (e) and R-117 (b); PRD 1.112; numbers assigned by the
    # supervisor).
    # + ERR-92 REGISTRY_BASIS_SUPERSEDED (item REG-VERSION-WHOLE-SET-1; the supervisor's ruling of
    # 2026-10-01 on the item's report; PRD 1.112; number assigned by the supervisor).
    # + ERR-72 PERIOD_STATE_MOVED (the period pin; rulings R-105 (3) and of 2026-10-01; PRD 1.86;
    # number assigned by the supervisor, register index 66), in number order before ERR-73.
    # + ERR-86 RUN_PERIOD_CLOSED (item JR-CLOSED-PERIOD-GUARD-1; ruling R-97 (7); PRD 1.134; number
    # assigned by the supervisor), in number order; ERR-84 is another lane's and not on main.
    # + ERR-93 / ERR-94 (items EST-ONE-OPEN-VERSION-1 and the constraint's judgement record; the
    # supervisor's rulings of 2026-10-01; PRD 1.168; numbers assigned by the supervisor, register
    # index 173).
    # + ERR-96 RUN_NOTHING_PENDING (item JRN-EMPTY-RUN-1; the supervisor's ruling of 2026-10-01;
    # PRD 1.174; number assigned by the supervisor, register index 185).
    # + ERR-95 (item MOD-LINKED-JUDGEMENTS-1; the supervisor's rulings of 2026-10-01; PRD 1.169;
    # number assigned by the supervisor, register index 174).
    # + ERR-97 CALENDARS_DIFFER (item RPT-PERIOD-KEY-CALENDARS-1; the supervisor's rulings of
    # 2026-10-02; PRD 1.180; number assigned by the supervisor, register index 216); the numbers
    # between ERR-94 and it are other items' and join at their merges.
    # + ERR-98 PERIOD_LOCK_IN_FLIGHT (finding F4; the supervisor's ruling of 2026-10-02; PRD 1.187;
    # number assigned by the supervisor, register index 150).
    # + ERR-101 RUN_RECORD_UNREADABLE (item SUBLEDGER-LINE-JOURNAL-RUN-1; the supervisor's
    # ruling of 2026-10-02; PRD 1.195; number assigned by the supervisor, register index 265);
    # ERR-99 and ERR-100 are another item's numbers and join at its merge.
    # + ERR-102 POLICY_OVERRIDE_NOT_OFFERED (item POLICY-OVERRIDE-WITHDRAW-1; supervisor ruling
    # R-126 (b) (4) and (c); PRD 1.209; number assigned by the supervisor, register index 308).
    # + ERR-103 POLICY_PRODUCT_LEVEL_NOT_READ (item PRODUCT-POLICY-VALUE-NOT-READ-1; supervisor
    # ruling R-126 (c) and the supervisor's rulings of 2026-10-03; PRD 1.210; number assigned by
    # the supervisor, register index 309).
    assert [row.id for row in rows] == [
        f"ERR-{n:02d}"
        for n in (
            *range(1, 63),
            *(64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83),
            *(85, 86, 87, 88, 92, 93, 94, 95, 96, 97, 98, 101, 102, 103),
        )
    ]
    for row in rows:
        if row.slug is None:
            continue
        assert row.slug in slugs, row.id
        assert row.slug not in synonyms, row.id
        assert row.status == slugs[row.slug], row.id
    by_id = {row.id: row for row in rows}
    for err_id, rule_id in CONVENTION_ROWS.items():
        assert by_id[err_id].slug == CONVENTION_SLUGS.get(err_id, "validation-failed")
        assert f'rule_id = "{rule_id}"' in by_id[err_id].slug_cell
    # Two rows carry no slug, keyed by status: an unhandled error (500) and "the server could not
    # do it now" (503), whose copy must not say that nothing was saved (PRD 1.73).
    assert {row.id: row.status for row in rows if row.slug is None} == {
        "ERR-34": 500,
        "ERR-64": 503,
    }
    counts = Counter(row.slug for row in rows if row.slug and row.id not in CONVENTION_ROWS)
    assert counts == Counter(set(slugs))


def test_dg_arc_13_imp_rows_cover_codes() -> None:
    tables = code_tables()
    assert tuple(tables) == CODE_TABLES
    withdrawn = set(tables["H"])
    active: dict[str, str] = {}
    for letter, codes in tables.items():
        if letter in ("H", "S"):
            continue
        assert not set(codes) & set(active), letter
        active.update(codes)
    assert withdrawn == {"TERM_NOT_WHOLE_MONTHS"}
    # 107 + IMP-108 (C5) + IMP-109..111 (ENG-C6; D-97 (15), (27), (28)) + IMP-112..113 (ENG-C5
    # phase 3, D-97 (11) / onboarding: ONBOARDING_CUTOVER_NOT_PERIOD_END and
    # ONBOARDING_MEMBER_MISSING) + IMP-114 (ENC-6; D-98 candidate 37).
    # + IMP-115 (F-CTR; D-97 (30) INVOICE_IDENTITY_REPEATED).
    # + IMP-116 (F-SNP SNP-2; D-98 candidate 137 (3) SANDBOX_REPLAY_BLOCKED).
    # + IMP-117..122 (F-DIN; D-97 (3), (3a): the six ssp_values declaration codes,
    # 04 1.74 table 15.4-A).
    # + IMP-124 / IMP-125 (F-ADM on F-DIN's branch, DIN-12; team-lead's ruling on the
    # amendment-basis refusals BASIS_STALE / BASIS_UNSUPPORTED_TRANSFORMATION; PRD 1.17 in place,
    # 04 1.81).
    # + IMP-126 (F-DIN, DIN-13; REQ-INT-007: SOURCE_VERSION_GAP, the reconciliation-sweep
    # exception; PRD 1.32 / 04 1.103).
    # + IMP-127 (lane SECFIX-IMP; ruling R-29, SC-2: IMPORT_ENTITY_NOT_AVAILABLE, 04 1.107
    # table 15.4-B / PRD 1.36; the number is the supervisor's).
    # + IMP-128 (lane SECFIX-IMP; rulings R-30 and R-49, SC-6: FILE_EVIDENCE_HELD, 04 1.107
    # table 15.4-B / PRD 1.36; the number is the supervisor's).
    # + IMP-130 (F-CLO-A, CLO-14; ruling R-71 (c): JOURNAL_EXPORT_FAILED, the refused journal
    # batch; PRD 1.56 / 04 1.127).
    # + IMP-132 (lane F-CLO-B, CLO-19; supervisor ruling R-79: CLOSE_RUN_FAILED, 04 1.134 table
    # 15.4-D / PRD 1.63; the number is the supervisor's).
    # + IMP-134 (lane SECFIX-IMP; rulings R-98 (10) and R-109 (b), (c):
    # IMPORT_CONTRACT_INCOMPLETE, 04 1.147 table 15.4-B / PRD 1.76; the number is the
    # supervisor's).
    # + IMP-131 (SECFIX-ACT; supervisor rulings R-77 (2), R-82 (g):
    # STEP1_ASSESSMENT_NOT_IN_FORCE, table 15.4-I; PRD 1.67 / 04 1.138).
    # + IMP-133 (SECFIX-ACT; supervisor ruling R-102 (a), Q1: STEP1_REENTRY_OTHER_REASON, table
    # 15.4-I; PRD 1.79 / 04 1.150).
    # + IMP-135 (SECFIX-ACT; supervisor rulings R-113 (f), R-115 (f): STEP1_CRITERION_NOT_MET,
    # table 15.4-I; the same revisions, amended in place).
    # + IMP-129 (lane SECFIX-IMP part B; rulings R-49 (a) and R-86:
    # FILE_SHRED_APPROVAL_REQUIRED, 04 1.142 table 15.4-B / PRD 1.71; the number is the
    # supervisor's): the ids read 1 to 135.
    # + IMP-137 (lane OPS, item JOB-FAILED-ITEM-1; supervisor ruling R-121 (n) and the rulings
    # of 2026-10-01: JOB_FAILED, 04 1.226 table 15.4-D / PRD 1.157; the number is the
    # supervisor's).
    # + IMP-136 (SECFIX-ACT; item STEP1-HOLD-RELEASE-1, the supervisor's ruling of 2026-10-01 on
    # the lane's question Q-H2: STEP1_CHANGE_NOT_FLAGGED, table 15.4-I; PRD 1.138 / 04 1.209; the
    # number is the supervisor's, register index 118): the ids read 1 to 137.
    # + IMP-138 to IMP-141 (SECFIX-ACT; items EST-EVIDENCE-AT-SUBMIT-1 and the constraint's
    # judgement record, the supervisor's rulings of 2026-10-01: ESTIMATE_EVIDENCE_REQUIRED,
    # ESTIMATE_ATTESTATION_REASON, ESTIMATE_CONSTRAINT_RECORD, ESTIMATE_ATTESTATION_VALUES, table
    # 15.4-D; PRD 1.168 / 04 1.241; the numbers are the supervisor's, register index 173).
    # + IMP-145 (SECFIX-ACT; item JDG-REJECTED-EXIT-1, the supervisor's rulings of 2026-10-02:
    # JUDGEMENT_RECORD_REJECTED, table 15.4-I; PRD 1.199 / 04 1.296; the number is the
    # supervisor's, register index 274).
    # + IMP-143 (SECFIX-ACT; item STEP1-CITE-LATEST-1, the supervisor's rulings of 2026-10-02:
    # STEP1_RECORD_OVERTAKEN, table 15.4-I; PRD 1.193 / 04 1.285; the number is the
    # supervisor's, register index 258).
    # + IMP-144 (lane F-CLO-B, item CLO-RATE-AFTER-RUN-1, second part; the supervisor's ruling of
    # 2026-10-02 11:08: FX_RATE_CHANGED_AFTER_LOCK, 04 1.291 table 15.4-D / PRD 1.197; the number
    # is the supervisor's, register index 272).
    # + IMP-147 (lane API-GAPS; item IMPORT-HEADER-CELL-CONFLICT-1, the supervisor's ruling
    # of 2026-10-02: HEADER_VALUE_CONFLICT, 04 1.310 table 15.4-B / PRD 1.204; the number is
    # the supervisor's, register index 295).
    # + IMP-148 (lane SECFIX-CLO; item USAGE-REPORT-PERIOD-ENDED-1, the supervisor's rulings of
    # 2026-10-03: USAGE_PERIOD_NOT_ENDED, 04 1.320 table 15.4-B / PRD 1.208; the number is the
    # supervisor's, register index 306).
    assert len(active) == 146
    rows = imp_rows()
    # + IMP-123 (F-ADM on F-DIN's branch, DIN-12; D-98 candidate 146 amendment 1 Q-B:
    # MODIFICATION_CANDIDATE_UNAPPLIED; PRD 1.17 / 04 1.77).
    # IMP-129 arrived with lane SECFIX-IMP's part B: every number to IMP-137 has its row.
    # IMP-147 follows them (lane API-GAPS, register index 295) and IMP-148 (lane SECFIX-CLO,
    # register index 306); IMP-142 and IMP-146 have no row on this branch.
    assert [row.id for row in rows] == [
        f"IMP-{n:02d}" for n in (*range(1, 142), 143, 144, 145, 147, 148)
    ]
    named: list[str] = []
    for row in rows:
        literal = re.fullmatch(r"`([A-Z0-9_]+)`", row.code_cell)
        assert literal is not None and CODE.fullmatch(literal.group(1)), row.id
        code = literal.group(1)
        assert code in active and code not in withdrawn, row.id
        if active[code] in SEVERITIES:
            leading = re.match(r"^(ERROR|WARNING|INFO)\b", row.severity)
            assert leading is not None and leading.group(1) == active[code], row.id
        named.append(code)
    assert Counter(named) == Counter(set(active))


# --- PRD rev 1.19 (COPY-ESCAPE-1): the copy-cell escape convention and its readers ----------------

COPY_ROW_CELLS: dict[str, int] = {"ERR": 5, "IMP": 4}
COPY_ROW = re.compile(r"^\| (ERR|IMP)-\d+ \|")
# a backslash not followed by `|` or `"` — the only escapes the convention admits
FOREIGN_ESCAPE = re.compile(r'\\(?![|"])')


def _copy_rows() -> list[str]:
    return [line for line in _copy_section().splitlines() if COPY_ROW.match(line)]


def test_dg_arc_13_copy_cells_are_commonmark_escaped() -> None:
    """PRD rev 1.19 (COPY-ESCAPE-1; team-lead's ruling of 2026-09-22): every ERR row has 5 cells
    and every IMP row 4 when a row is split on UNESCAPED pipes; a copy row admits no backslash
    other than ``\\|`` and ``\\"``; the readers unescape exactly those two. The synthetic row holds
    a literal pipe and inner quotes — under the pre-1.19 splitter it counted 5 cells
    (fail-first)."""
    rows = _copy_rows()
    # 57 ERR + 126 IMP at PRD 1.32 (IMP-126, DIN-13); + ERR-58 to ERR-60 at PRD 1.42 (R-42 (b));
    # + ERR-61, ERR-62 at PRD 1.52 (R-58 (b), R-61 (f)); + IMP-127, IMP-128 at PRD 1.36
    # (SECFIX-IMP); + IMP-130 at PRD 1.56 (CLO-14); + IMP-132 at PRD 1.63 (CLO-19); + ERR-65 at PRD
    # 1.35 (R-6); + IMP-134 at PRD 1.76 (SECFIX-IMP; R-98 (10), R-109 (b)); + ERR-67 to ERR-69 at
    # PRD 1.74 (CLO-15); + ERR-70, ERR-71 at PRD 1.87 (ADJ-VOID-REFUSE-1); + ERR-76 at PRD 1.84
    # (R-112 (e), R-114 (d)); + ERR-64, ERR-66 at PRD 1.73 (lane OPS, the kernel's error
    # mapping); + ERR-75 at PRD 1.89 (CFG-BACKDATE-1; R-113 (b)); + IMP-131 at PRD 1.67
    # (R-77 (2), R-82 (g)); + IMP-133 and IMP-135 at PRD 1.79 (R-102 (a), R-113 (f)); + ERR-78
    # and ERR-85 at PRD 1.111 (R-116 (h), R-119 (d)); + ERR-73, ERR-74, ERR-79 at PRD 1.88
    # (JRN-FAILED-CANCEL-1); + ERR-82 at PRD 1.117 (MOD-DISCARD-1; R-118 (e)); + ERR-77 at PRD 1.106
    # (SNP-5); + IMP-129 at PRD 1.71 (SECFIX-IMP part B; R-49 (a), R-86); + ERR-83, ERR-87,
    # ERR-88 at PRD 1.139 (MOD-LINKED-ESTIMATES-1; R-118 (e), R-119 (e)); + ERR-80, ERR-81 at
    # PRD 1.112 (REG-VERSION-WHOLE-SET-1, CFG-PLATFORM-PIN-1; R-115 (e), R-117 (b)), with ERR-92
    # by the ruling of 2026-10-01 on that item's report; + IMP-137 at PRD 1.157 (lane OPS, item
    # JOB-FAILED-ITEM-1); + ERR-72 at PRD 1.86 (the period pin; R-105 (3)); + ERR-86 at PRD 1.134
    # (JR-CLOSED-PERIOD-GUARD-1; R-97 (7)); + IMP-136 at PRD 1.138 (STEP1-HOLD-RELEASE-1):
    # 87 ERR + 137 IMP
    # + ERR-93, ERR-94 and IMP-138 to IMP-141 at PRD 1.168 (SECFIX-ACT, the estimate items of
    # register index 173): two ERR and four IMP rows more
    # + ERR-96 at PRD 1.174 (JRN-EMPTY-RUN-1, lane F-CLO-A, register index 185): 90 ERR + 141 IMP
    # + ERR-95 at PRD 1.169 (SECFIX-ACT, item MOD-LINKED-JUDGEMENTS-1, register index 174): one
    # ERR row more
    # + IMP-145 at PRD 1.199 (SECFIX-ACT, item JDG-REJECTED-EXIT-1, register index 274): one
    # IMP row more
    # + IMP-143 at PRD 1.193 (SECFIX-ACT, item STEP1-CITE-LATEST-1, register index 258): one
    # IMP row more
    # + ERR-97 at PRD 1.180 (RPT-PERIOD-KEY-CALENDARS-1; the rulings of 2026-10-02); + ERR-98 at
    # PRD 1.187 (finding F4; the ruling of 2026-10-02):
    # + IMP-144 at PRD 1.197 (CLO-RATE-AFTER-RUN-1, second part, lane F-CLO-B, register index
    # 272): one IMP row more
    # + ERR-101 at PRD 1.195 (SUBLEDGER-LINE-JOURNAL-RUN-1, lane F-CLO-A, register index 265):
    # one ERR row more
    # + IMP-147 at PRD 1.204 (IMPORT-HEADER-CELL-CONFLICT-1, lane API-GAPS, register index
    # 295): one IMP row more
    # + IMP-148 at PRD 1.208 (USAGE-REPORT-PERIOD-ENDED-1, lane SECFIX-CLO, register index 306):
    # one IMP row more
    # + ERR-102 at PRD 1.209 (POLICY-OVERRIDE-WITHDRAW-1, lane SECFIX-PLT, register index 308):
    # one ERR row more
    # 95 ERR + 146 IMP
    # + ERR-103 at PRD 1.210 (PRODUCT-POLICY-VALUE-NOT-READ-1, lane SECFIX-CLO, register index
    # 309): one ERR row more
    # 96 ERR + 146 IMP
    assert len(rows) == 242
    for line in rows:
        kind = line[2:5]
        assert len(_cells(line)) == COPY_ROW_CELLS[kind], line[:40]
        assert not FOREIGN_ESCAPE.search(line), line[:40]
    synthetic = '| IMP-999 | `X_Y` | ERROR | "A \\| B, and \\"C\\"." |'
    assert _cells(synthetic) == ["IMP-999", "`X_Y`", "ERROR", '"A | B, and "C"."']


def _quoted(cell: str, *, after: str | None = None) -> str:
    """The quoted copy of an (unescaped) cell: the text between the outer quotes, optionally of
    the part after a marker such as the ``errors[].message`` label of an ERR row."""
    text = cell if after is None else cell[cell.index(after) + len(after) :]
    text = text.strip()
    assert text.startswith('"') and text.endswith('"'), text
    return text[1:-1]


def _placeholders(copy: str) -> set[str]:
    return set(re.findall(r"<([a-z][a-z ]*)>", copy))


def _fields(template: str) -> set[str]:
    return set(re.findall(r"\{([a-z_]+)\}", template))


def test_dg_arc_13_copy_equals_code_for_the_escaped_quote_rows() -> None:
    """COPY-ESCAPE-1: the three rows whose copy carries an inner quote AND has a code mirror equal
    the code copy after unescaping — ERR-35 ``money.MONEY_MESSAGE``, IMP-02
    ``imports.validate.not_numeric``, IMP-10 ``legacy_v1.sku_ssp.FLAG_MESSAGE``. Placeholders map
    ``<name>`` ↔ ``{name}`` ONLY for identical names: a name or word difference is a FINDING (the
    owner of the text decides; nothing here is edited to pass). IMP-72 (``VC_REASSESSMENT_MISSING``)
    has NO code mirror — the engine emits the gap and erev_api carries only its title — so it is
    not compared (recorded as a fact in F-DIN-prep)."""
    import inspect

    from erev_api.domain.imports import validate
    from erev_api.domain.imports.legacy_v1 import sku_ssp
    from erev_api.money import MONEY_MESSAGE

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}  # keyed by the parsed id
    err_35 = _quoted(cells["ERR-35"][4], after="`errors[].message`")
    assert _placeholders(err_35) == set() == _fields(MONEY_MESSAGE)
    assert err_35 == MONEY_MESSAGE
    imp_02 = _quoted(cells["IMP-02"][3])
    template_02 = inspect.getsource(validate.not_numeric)
    assert _placeholders(imp_02) == _fields(template_02) == {"column", "value"}
    assert imp_02 == validate.not_numeric("<column>", "<value>")
    imp_10 = _quoted(cells["IMP-10"][3])
    assert _placeholders(imp_10) == _fields(sku_ssp.FLAG_MESSAGE) == {"value"}
    assert imp_10 == sku_ssp.FLAG_MESSAGE.format(value="<value>")


def test_dg_arc_13_copy_equals_code_for_the_entity_book_rows() -> None:
    """Rulings R-58 (b) and R-61 (f) (PRD 1.52; 04 T-REF-03 rev 1.123): the two refusals of
    ``PUT /entities/{id}/books/{code}`` answer the PRD rows ERR-61 and ERR-62 word for word
    (``reference.books``). A placeholder ``<two words>`` is the template field ``{two_words}``."""
    from erev_api.domain.reference import books

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    bound = {
        "ERR-61": (
            books.FIRST_PERIOD_AFTER_CONTRACT,
            {"entity", "date", "contract", "period_key", "book"},
        ),
        "ERR-62": (books.CONTRACT_BEHIND_GATE, {"contract", "entity", "book"}),
    }
    for row_id, (template, fields) in bound.items():
        copy = _quoted(cells[row_id][4], after="`errors[].message`")
        assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields, row_id
        assert _fields(template) == fields, row_id
        assert template.format(**{name: f"<{name.replace('_', ' ')}>" for name in fields}) == copy


def test_dg_arc_13_copy_equals_code_for_the_general_ledger_rows() -> None:
    """BUILD_SPEC CLO-15 (PRD 1.74; 04 T-SL-07 "General ledger and chunks", rev 1.145): the three
    refusals of a journal run calculation answer the PRD rows ERR-67 to ERR-69 word for word
    (``journals.summarise``), and the two reasons of ERR-69 are the two the code gives. A
    placeholder ``<two words>`` is the template field ``{two_words}``."""
    from uuid import UUID

    from erev_api.domain.journals import summarise

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    bound = {
        "ERR-67": (summarise.SEVERAL_CONNECTIONS, {"entity", "codes"}),
        "ERR-68": (summarise.CHUNK_SIZE_INVALID, {"code", "value"}),
        "ERR-69": (summarise.ENTRY_TOO_LARGE, {"lines", "limit", "reason"}),
    }
    for row_id, (template, fields) in bound.items():
        copy = _quoted(cells[row_id][4], after="`errors[].message`")
        assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields, row_id
        assert _fields(template) == fields, row_id
        assert template.format(**{name: f"<{name.replace('_', ' ')}>" for name in fields}) == copy
    reasons = cells["ERR-69"][4]
    contract = UUID(int=7)
    by_contract = summarise.ChunkingRefused(lines=5, limit=2, contract_id=contract, part=3)
    unbalanced = summarise.ChunkingRefused(lines=5, limit=2)
    stated = summarise.ENTRY_TOO_LARGE.format(lines=5, limit=2, reason="{reason}")
    for refusal, label, reason in (
        (by_contract, "<contract>", "the part of contract <contract> alone has <part> lines"),
        (unbalanced, None, "its lines do not balance contract by contract"),
    ):
        assert f'"{reason}"' in reasons, reason
        filled = reason.replace("<part>", "3")
        assert refusal.message(label) == stated.format(reason=filled)


def test_dg_arc_13_copy_equals_code_for_the_manual_adjustment_rows() -> None:
    """Item ADJ-VOID-REFUSE-1 (supervisor ruling R-112 (b); PRD 1.87): the refused void of a
    posted adjustment's event and the refused edit by anyone but the creator answer the PRD rows
    ERR-70 and ERR-71 word for word, each under the rule id the row names."""
    from erev_api.domain.contracts import events
    from erev_api.domain.journals import adjustments

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    void = _quoted(cells["ERR-70"][4], after="`errors[].message`")
    assert (void, _placeholders(void)) == (events.ADJUSTMENT_NOT_VOIDABLE, set())
    edit = _quoted(cells["ERR-71"][4], after="`errors[].message`")
    assert _placeholders(edit) == _fields(adjustments.NOT_CREATOR) == {"creator"}
    assert edit == adjustments.NOT_CREATOR.format(creator="<creator>")
    assert (events.RULE_ADJUSTMENT, adjustments.RULE_CREATOR) == (
        CONVENTION_ROWS["ERR-70"],
        CONVENTION_ROWS["ERR-71"],
    )


def test_dg_arc_13_copy_equals_code_for_the_legacy_book_row() -> None:
    """Rulings R-112 (e) and R-114 (d) (PRD 1.84; 04 §16.8 rev 1.155): the refusal of a close
    command on a period of the LEGACY book answers the PRD row ERR-76 word for word
    (``close.commands.LEGACY_FOLLOWS``), under the rule id the row names. A placeholder
    ``<two words>`` is the template field ``{two_words}``."""
    from erev_api.domain.close import commands

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    copy = _quoted(cells["ERR-76"][4], after="`errors[].message`")
    assert {name.replace(" ", "_") for name in _placeholders(copy)} == {"primary_book"}
    assert _fields(commands.LEGACY_FOLLOWS) == {"primary_book"}
    assert commands.LEGACY_FOLLOWS.format(primary_book="<primary book>") == copy
    assert f'rule_id = "{commands.RULE_LEGACY}"' in cells["ERR-76"][1]


def test_dg_arc_13_copy_equals_code_for_the_effective_date_row() -> None:
    """Item CFG-BACKDATE-1 (supervisor rulings R-112 (i) and R-113 (b); PRD 1.89; 04 §16.5 rev
    1.160): the refusal of a superseding version's effective date answers the PRD row ERR-75 word
    for word in both of its forms (``policies.lifecycle``), as the detail and as the message, under
    the rule id the row names."""
    from erev_api.domain.policies import lifecycle
    from erev_api.problems import ProblemError

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    stated = cells["ERR-75"][4]
    for copy in (lifecycle.EFFECTIVE_DATE_PASSED, lifecycle.EFFECTIVE_INSTANT_PASSED):
        assert _placeholders(copy) == set() == _fields(copy)
        assert f'`detail` and `errors[].message` "{copy}"' in stated
    assert lifecycle.EFFECTIVE_DATE_PASSED != lifecycle.EFFECTIVE_INSTANT_PASSED
    finding = ProblemError(
        field="effective_from",
        rule_id=lifecycle.RULE_PROSPECTIVE,
        message=lifecycle.EFFECTIVE_DATE_PASSED,
    )
    other = ProblemError(field="effective_from", rule_id="DB-04", message="Another finding.")
    assert lifecycle.invalid([other, finding]).detail == lifecycle.EFFECTIVE_DATE_PASSED
    assert lifecycle.invalid([other]).detail is None
    assert lifecycle.RULE_PROSPECTIVE == CONVENTION_ROWS["ERR-75"]
    assert f'rule_id = "{lifecycle.RULE_PROSPECTIVE}"' in cells["ERR-75"][1]


def test_dg_arc_13_copy_equals_code_for_the_registry_version_rows() -> None:
    """Items REG-VERSION-WHOLE-SET-1 and CFG-PLATFORM-PIN-1 (supervisor rulings R-115 (e) and
    R-117 (b) and the ruling of 2026-10-01 on the items' report; PRD 1.112; 04 T-PLT-32 and §16.5
    rev 1.183): the three refusals of a policy version answer their PRD rows word for word, as the
    detail and as the message, under the rule ids the rows name — the order of effective instants
    for a dated version (ERR-80) and for one without a date (ERR-81), and the reopening after
    another version of the key was published (ERR-92). ``<n>`` is the published version's number
    and ``<DD MMM YYYY>`` the UTC date of its effective instant."""
    from erev_api.domain.policies import registry_versions

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    rows = {
        "ERR-80": (registry_versions.EFFECTIVE_ORDER_DATED, registry_versions.RULE_ORDER),
        "ERR-81": (registry_versions.EFFECTIVE_ORDER_UNDATED, registry_versions.RULE_ORDER),
        "ERR-92": (registry_versions.BASIS_SUPERSEDED, registry_versions.RULE_BASIS_SUPERSEDED),
    }
    for err_id, (template, rule_id) in rows.items():
        shown = {"version_no": "<n>", "date": "<DD MMM YYYY>"}
        copy = template.format(**{name: shown[name] for name in _fields(template)})
        assert f'`detail` and `errors[].message` "{copy}"' in cells[err_id][4], err_id
        assert rule_id == CONVENTION_ROWS[err_id]
        assert f'rule_id = "{rule_id}"' in cells[err_id][1]
    assert _fields(registry_versions.BASIS_SUPERSEDED) == {"version_no"}
    assert 'on `errors[].field = "status"`' in cells["ERR-92"][1]
    for err_id in ("ERR-80", "ERR-81"):
        assert 'on `errors[].field = "effective_from"`' in cells[err_id][1]


def test_dg_arc_13_copy_equals_code_for_the_held_next_period_row() -> None:
    """Ruling R-116 (h) (PRD 1.111; 04 §14.1 DB-07 rev 1.182): the refusal of a lock decision
    whose ``future`` next period another request holds answers the PRD row ERR-78 word for word
    (``close.commands.NEXT_PERIOD_HELD``), under the rule id the row names. A placeholder
    ``<two words>`` is the template field ``{two_words}``."""
    from erev_api.domain.close import commands

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    fields = {"next_period", "period"}
    copy = _quoted(cells["ERR-78"][4], after="`errors[].message`")
    assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields
    assert _fields(commands.NEXT_PERIOD_HELD) == fields
    shown = {name: f"<{name.replace('_', ' ')}>" for name in fields}
    assert commands.NEXT_PERIOD_HELD.format(**shown) == copy
    assert f'rule_id = "{commands.RULE_NEXT_PERIOD_HELD}"' in cells["ERR-78"][1]


def test_dg_arc_13_copy_equals_code_for_the_period_state_moved_row() -> None:
    """Rulings R-105 (3) and of 2026-10-01 (PRD 1.86; 04 §14.1 "A command recorded before a lock"
    rev 1.157): a computation that holds an event recorded in its own transaction and meets a
    lock decided since answers the PRD row ERR-72 word for word
    (``problems.PERIOD_STATE_MOVED_DETAIL``), under the rule id the row names; the sentence takes
    no placeholder. Inside an approval's decision its last sentence is the one the row quotes
    after "the sentence ends" (``problems.PERIOD_STATE_MOVED_DECISION_DETAIL``; supervisor ruling
    of 2026-10-01)."""
    from erev_api import problems

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    cell = cells["ERR-72"][4]
    copy = _quoted(cell, after="`errors[].message`")
    assert _placeholders(copy) == set() and _fields(problems.PERIOD_STATE_MOVED_DETAIL) == set()
    assert problems.PERIOD_STATE_MOVED_DETAIL == copy
    assert f'rule_id = "{problems.RULE_PERIOD_STATE_MOVED}"' in cells["ERR-72"][1]
    ending = re.search(r'the sentence ends "([^"]+)"', cell)
    assert ending is not None
    command_ending = "Send it again: it is then recorded after the lock."
    assert copy.endswith(command_ending) and ending.group(1) != command_ending
    decision = copy[: -len(command_ending)] + ending.group(1)
    assert problems.PERIOD_STATE_MOVED_DECISION_DETAIL == decision
    assert problems.period_state_moved().detail == copy
    assert problems.period_state_moved(deciding=True).detail == decision


def test_dg_arc_13_copy_equals_code_for_the_calendars_row() -> None:
    """Item RPT-PERIOD-KEY-CALENDARS-1 (the supervisor's rulings of 2026-10-02; PRD 1.180; 04
    T-RPT-01 rule 6 rev 1.264): the refusal of a report run over entities of more than one fiscal
    calendar answers the PRD row ERR-97 word for word (``reports.framework.CALENDARS_DIFFER``), as
    the detail and as the message, under the rule id and on the member the row names; the
    sentence takes no placeholder. Beside another finding it is still the detail; without it the
    detail counts the fields as before."""
    from erev_api.domain.reports import framework
    from erev_api.problems import ProblemError

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    copy = framework.CALENDARS_DIFFER
    assert _placeholders(copy) == set() == _fields(copy)
    assert f'`detail` and `errors[].message` "{copy}"' in cells["ERR-97"][4]
    assert framework.RULE_CALENDARS == CONVENTION_ROWS["ERR-97"]
    assert f'rule_id = "{framework.RULE_CALENDARS}"' in cells["ERR-97"][1]
    assert 'on `errors[].field = "parameters.entity_codes"`' in cells["ERR-97"][1]
    finding = ProblemError(
        field=f"parameters.{framework.ENTITY_CODES}",
        rule_id=framework.RULE_CALENDARS,
        message=copy,
    )
    other = ProblemError(
        field="parameters.known_at",
        rule_id=framework.RULE_PARAMETERS,
        message=framework.KNOWN_AT_FUTURE,
    )
    assert framework._invalid([finding]).detail == copy
    assert framework._invalid([other, finding]).detail == copy
    assert framework._invalid([other]).detail == "1 field needs attention."
    assert framework._invalid([other, other]).detail == "2 fields need attention."


def test_dg_arc_13_copy_equals_code_for_the_lock_in_flight_row() -> None:
    """Finding F4 of the independent review of 2026-10-01 (the supervisor's ruling of 2026-10-02;
    PRD 1.187; 04 §14.1 DB-07 rev 1.229; dev-guide DG-KRN-DB-08 (1c) rev 1.218): a transaction
    that holds a ledger chain head and meets a period state row a lock decision holds answers
    the PRD row ERR-98 word for word (``problems.PERIOD_LOCK_IN_FLIGHT_DETAIL``), as the detail
    and as the message, under the rule id the row names; the sentence takes no placeholder and
    is not the kernel's sentence of a wait that ran out."""
    from erev_api import problems

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    copy = _quoted(cells["ERR-98"][4], after="`errors[].message`")
    assert _placeholders(copy) == set() == _fields(problems.PERIOD_LOCK_IN_FLIGHT_DETAIL)
    assert problems.PERIOD_LOCK_IN_FLIGHT_DETAIL == copy != problems.LOCK_TIMEOUT_DETAIL
    assert problems.RULE_PERIOD_LOCK_IN_FLIGHT == CONVENTION_ROWS["ERR-98"]
    assert f'rule_id = "{problems.RULE_PERIOD_LOCK_IN_FLIGHT}"' in cells["ERR-98"][1]
    refused = problems.period_lock_in_flight()
    assert (refused.slug, refused.detail) == ("lock-conflict", copy)
    assert [(error.rule_id, error.message) for error in refused.errors] == [
        (problems.RULE_PERIOD_LOCK_IN_FLIGHT, copy)
    ]


def test_dg_arc_13_copy_equals_code_for_the_held_earlier_period_row() -> None:
    """Ruling R-119 (d) (PRD 1.111; 04 §14.1 DB-07 rev 1.182): the refusal of a lock request, and of
    a lock decision, when another request holds an earlier period answers the PRD row ERR-85
    word for word (``close.commands.EARLIER_PERIOD_HELD``), under the rule id the row names. A
    placeholder ``<two words>`` is the template field ``{two_words}``."""
    from erev_api.domain.close import commands

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    fields = {"earlier_period", "period"}
    copy = _quoted(cells["ERR-85"][4], after="`errors[].message`")
    assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields
    assert _fields(commands.EARLIER_PERIOD_HELD) == fields
    shown = {name: f"<{name.replace('_', ' ')}>" for name in fields}
    assert commands.EARLIER_PERIOD_HELD.format(**shown) == copy
    assert f'rule_id = "{commands.RULE_EARLIER_PERIOD_HELD}"' in cells["ERR-85"][1]


def test_dg_arc_13_copy_equals_code_for_the_failed_run_rows() -> None:
    """Item JRN-FAILED-CANCEL-1 (supervisor ruling R-112 (c); PRD 1.88; 04 §16.7 rev 1.159): the
    refusal of a job that found the ledger holding a failed batch, the refused cancel of a run
    partly in a ledger and the refused download of a batch whose lines changed answer the PRD
    rows ERR-73, ERR-74 and ERR-79 word for word, each under the rule id the row names. ERR-73 has
    two endings — the cancel's is the row's copy, the hand-over's the ending the row states. A
    placeholder ``<two words>`` is the template field ``{two_words}``."""
    from erev_api.domain.journals import export, failed_exits

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    bound = {
        "ERR-73": (
            failed_exits.HELD_NOT_CANCELLED,
            {"ledger", "external_id", "document", "run_no"},
        ),
        "ERR-74": (failed_exits.PARTLY_IN_LEDGER, {"run_no", "external_id"}),
        "ERR-79": (
            export.LINES_DIFFER.replace("{consequence}", export.NOT_DOWNLOADED),
            {"external_id", "differences"},
        ),
    }
    for row_id, (template, fields) in bound.items():
        copy = _quoted(cells[row_id][4], after="`errors[].message`")
        assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields, row_id
        assert _fields(template) == fields, row_id
        assert template.format(**{name: f"<{name.replace('_', ' ')}>" for name in fields}) == copy
    # the hand-over's ending of ERR-73: the same sentence up to what is not done
    ending = "… and is not handed over."
    assert f'"{ending}"' in cells["ERR-73"][4]
    shared = "The batch is acknowledged and "
    cancel, hand_over = failed_exits.HELD_NOT_CANCELLED, failed_exits.HELD_NOT_HANDED_OVER
    assert cancel.split(shared)[0] == hand_over.split(shared)[0]
    assert hand_over.endswith(ending.removeprefix("… and ")) and _fields(hand_over) == {
        "ledger",
        "external_id",
        "document",
    }
    assert (export.RULE_STATES, export.RULE_RECOUNT) == (
        CONVENTION_ROWS["ERR-73"],
        CONVENTION_ROWS["ERR-79"],
    )
    assert CONVENTION_ROWS["ERR-74"] == export.RULE_STATES
    # one sentence, three places a batch leaves through (05 ADP-31): only the ending differs
    assert export.LINES_DIFFER.count("{consequence}") == 1
    assert {export.NOTHING_SENT, export.NOT_DOWNLOADED, failed_exits.LINES_NOT_HANDED_OVER} == {
        "Nothing was sent.",
        "It cannot be downloaded.",
        "It cannot be handed over.",
    }


def test_dg_arc_13_copy_equals_code_for_the_closed_period_run_row() -> None:
    """Item JR-CLOSED-PERIOD-GUARD-1 (supervisor ruling R-97 (7); PRD 1.134; 04 §16.7 rev 1.205):
    the refusal of a journal run's calculation and of its cancel in a closed period answers the
    PRD row ERR-86 word for word, under the rule id the row names. The row has two endings — the
    calculation's is the row's copy, the cancel's the ending the row states — and both open with
    the sentence of ERR-15: one statement of what a closed period is."""
    from erev_api import periods
    from erev_api.domain.journals import summarise

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    fields = {"period", "entity", "book"}
    copy = _quoted(cells["ERR-86"][4], after="`errors[].message`")
    assert _placeholders(copy) == fields
    calculated = summarise.RUN_PERIOD_CLOSED.replace("{consequence}", summarise.NOT_CALCULATED)
    assert _fields(calculated) == fields
    assert calculated.format(**{name: f"<{name}>" for name in fields}) == copy
    assert f'"… {summarise.NOT_CANCELLED}"' in cells["ERR-86"][4]
    assert summarise.RULE_PERIOD_CLOSED == CONVENTION_ROWS["ERR-86"]
    assert f'rule_id = "{summarise.RULE_PERIOD_CLOSED}"' in cells["ERR-86"][1]
    opening = summarise.RUN_PERIOD_CLOSED.removesuffix(" {consequence}")
    assert periods.PERIOD_CLOSED.startswith(f"{opening} ")
    assert _quoted(cells["ERR-15"][4]).startswith(opening.format(**{n: f"<{n}>" for n in fields}))
    assert summarise.CLOSED_STATES == {"closed", "permanently_locked"}


def test_dg_arc_13_copy_equals_code_for_the_nothing_pending_row() -> None:
    """Item JRN-EMPTY-RUN-1 (the supervisor's ruling of 2026-10-01; PRD 1.174; 04 §16.7
    API-S-JournalRunCreate rev 1.248): the refusal of a further journal run that would hold no
    line answers the PRD row ERR-96 word for word, 409 ``invalid-transition`` under the rule id
    the row names; the placeholders are the code's fields by the same names."""
    from erev_api.domain.journals import summarise
    from erev_api.problems import PROBLEMS

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    fields = {"run", "period", "entity", "book"}
    copy = _quoted(cells["ERR-96"][4], after="`errors[].message`")
    assert _placeholders(copy) == fields == _fields(summarise.NOTHING_PENDING)
    assert summarise.NOTHING_PENDING.format(**{name: f"<{name}>" for name in fields}) == copy
    assert summarise.RULE_NOTHING_PENDING == CONVENTION_ROWS["ERR-96"]
    assert f'rule_id = "{summarise.RULE_NOTHING_PENDING}"' in cells["ERR-96"][1]
    slug = CONVENTION_SLUGS["ERR-96"]
    assert cells["ERR-96"][1].startswith(f"`{slug}`")
    assert (cells["ERR-96"][2], cells["ERR-96"][3]) == (
        str(PROBLEMS[slug].status),
        PROBLEMS[slug].title,
    )


def test_dg_arc_13_copy_equals_code_for_the_close_run_row() -> None:
    """BUILD_SPEC CLO-19 (PRD 1.63; 04 §15.4 rev 1.134): the message of the exception item a
    failed close run raises IS the PRD row IMP-132 (``close_runs.FAILED_MESSAGE``). A placeholder
    ``<two words>`` is the template field ``{two_words}``."""
    from erev_api.domain.close import close_runs

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    fields = {"close_run_no", "entity_code", "period_label", "step_label", "reason"}
    copy = _quoted(cells["IMP-132"][3])
    assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields
    assert _fields(close_runs.FAILED_MESSAGE) == fields
    shown = {name: f"<{name.replace('_', ' ')}>" for name in fields}
    assert close_runs.FAILED_MESSAGE.format(**shown) == copy


def test_dg_arc_13_copy_equals_code_for_the_rate_changed_after_lock_row() -> None:
    """Item CLO-RATE-AFTER-RUN-1, second part (PRD 1.197; 04 §15.4 rev 1.291): the message of the
    item the approval of a rate set version raises for a closed period IS the PRD row IMP-144
    (``rate_changes.MESSAGE``), and every part the message is put together from — the two
    states, the three forms of a changed rate, the tail that counts the others, the three roads
    and the words for no postable period — is quoted by the row word for word, and nothing else
    is. A placeholder ``<two words>`` is the template field ``{two_words}``."""
    from datetime import date
    from decimal import Decimal

    from erev_api.domain.close import rate_changes

    def shown(template: str) -> str:
        return template.format(
            **{name: f"<{name.replace('_', ' ')}>" for name in _fields(template)}
        )

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    copy, parted, parts = cells["IMP-144"][3].partition('"; `<state>`')
    assert parted and copy.startswith('"')
    copy = copy[1:]
    fields = {
        "period",
        "state",
        "entity",
        "book",
        "version_no",
        "set_code",
        "count",
        "rates",
        "first",
        "more",
        "roads",
        "posting",
    }
    assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields
    assert _fields(rate_changes.MESSAGE) == fields
    assert shown(rate_changes.MESSAGE) == copy
    assert sorted(re.findall(r'"([^"]*)"', parts)) == sorted(
        [
            *rate_changes.STATES.values(),
            "rate",
            "rates",
            shown(rate_changes.CHANGED),
            shown(rate_changes.APPEARED),
            shown(rate_changes.REMOVED),
            shown(rate_changes.MORE),
            rate_changes.REOPEN_OR_ACCEPT,
            rate_changes.LATER_FIRST_OR_ACCEPT,
            rate_changes.ACCEPT_ONLY,
            rate_changes.NEXT_TO_OPEN,
        ]
    )
    assert rate_changes.message(
        period_key="FY2026-P08",
        state="closed",
        later=[],
        entity_code="AVM-US",
        book_code="ASC606",
        version_no=2,
        changes=[
            rate_changes.RateChange(
                set_code="AVM-RATES-CLOSING",
                rate_type="closing",
                base_currency="EUR",
                quote_currency="USD",
                effective_date=date(2026, 8, 31),
                before=Decimal("1.105"),
                after=Decimal("1.115"),
            )
        ],
        posting_period_key="FY2026-P09",
    ) == (
        "FY2026-P08 is closed for AVM-US in book ASC606. The approval of version 2 of rate set "
        "AVM-RATES-CLOSING changed 1 exchange rate dated in it: EUR/USD closing rate of "
        "2026-08-31 from 1.105 to 1.115. Reopen the period to restate it, or request a waiver "
        "to accept the difference. The difference is not computed here. What remains of it to post "
        "goes to FY2026-P09. The contracts the changed rates reach are recalculated by the next "
        "close run of their contracting entity or by the next change to them: what the "
        "rates change in the amounts of their events is posted with the closed period of each "
        "event as origin period, and the out-of-period register lists it as Fx republish or with "
        "the event that carried it. The close run of FY2026-P09 posts what remains of a period-end "
        "remeasurement as an amount of that period, without an origin period. Where nothing "
        "remains nothing is posted: a closing rate of a period that is followed by another closed "
        "period moves an amount between the two for a balance open through both."
    )


def test_dg_arc_13_copy_equals_code_for_the_sync_rows() -> None:
    """Ruling R-45 (c): the exception copy the sync run raises IS the PRD row — IMP-41
    ``PRODUCT_UNMAPPED`` (``sync.PRODUCT_UNMAPPED_MESSAGE``; J-23.4 quotes it), IMP-20
    ``CONTRACT_NOT_FOUND`` and IMP-126 ``SOURCE_VERSION_GAP``. A placeholder ``<two words>`` is
    the template field ``{two_words}``; any other difference of a name or a word is a finding."""
    from erev_api.domain.integrations import sync

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    bound = {
        "IMP-20": (sync.CONTRACT_NOT_FOUND_MESSAGE, {"contract"}),
        "IMP-41": (sync.PRODUCT_UNMAPPED_MESSAGE, {"order", "n", "source_product"}),
        "IMP-126": (sync.GAP_MESSAGE, {"source_system", "object", "external_id", "version"}),
    }
    for row_id, (template, fields) in bound.items():
        copy = _quoted(cells[row_id][3])
        assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields, row_id
        assert _fields(template) == fields, row_id
        assert template.format(**{name: f"<{name.replace('_', ' ')}>" for name in fields}) == copy
    assert sync.PRODUCT_UNMAPPED_MESSAGE.format(
        order="SF-ORD-Q-003", n=2, source_product="SF-PROD-X99"
    ) == ("Order SF-ORD-Q-003, line 2: product SF-PROD-X99 has no approved product record.")


def test_dg_arc_13_copy_equals_code_for_the_modification_discard_row() -> None:
    """Item MOD-DISCARD-1 (supervisor ruling R-118 (e); PRD 1.117; 04 §16.14 rev 1.188): the discard
    of a draft modification refused while a review of its own judgement record is pending answers
    the PRD row ERR-82 word for word (``modifications.REVIEW_PENDING``). The placeholder
    ``<judgement no>`` is the template field ``{judgement_no}``."""
    from erev_api.domain.contracts import modifications

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    copy = _quoted(cells["ERR-82"][4], after="`errors[].message`")
    assert {name.replace(" ", "_") for name in _placeholders(copy)} == {"judgement_no"}
    assert _fields(modifications.REVIEW_PENDING) == {"judgement_no"}
    assert modifications.REVIEW_PENDING.format(judgement_no="<judgement no>") == copy


def test_dg_arc_13_copy_equals_code_for_the_linked_estimate_rows() -> None:
    """Item MOD-LINKED-ESTIMATES-1 (supervisor rulings R-118 (e), R-119 (e); PRD 1.139; 04 §16.14
    rev 1.210): the three refusals around the estimate versions created inside a modification
    answer the PRD rows word for word — ERR-83 ``modifications.LINKED_PENDING``, ERR-87
    ``modifications.LINKED_NOT_APPROVED`` and ERR-88 ``estimates.MODIFICATION_DISCARDED``. ERR-87
    is one row for two places: the approval's backstop says the same first sentence and ends
    with the sentence the row quotes for it. A placeholder ``<two words>`` is the template field
    ``{two_words}``."""
    from erev_api.domain.contracts import estimates, modifications

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    bound = {
        "ERR-83": (modifications.LINKED_PENDING, {"element_code", "version_no"}),
        "ERR-87": (modifications.LINKED_NOT_APPROVED, {"element_code", "version_no"}),
        "ERR-88": (estimates.MODIFICATION_DISCARDED, {"modification_no"}),
    }
    for row_id, (template, fields) in bound.items():
        copy = _quoted(cells[row_id][4], after="`errors[].message`")
        assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields, row_id
        assert _fields(template) == fields, row_id
        assert template.format(**{name: f"<{name.replace('_', ' ')}>" for name in fields}) == copy
    at_submission = modifications.LINKED_NOT_APPROVED
    at_approval = modifications.LINKED_NOT_APPROVED_AT_APPROVAL
    first_sentence = at_submission.split(". ", 1)[0]
    assert at_approval.split(". ", 1)[0] == first_sentence
    ending = at_approval.split(". ", 1)[1]
    assert f'then ends "{ending}"' in cells["ERR-87"][4]


def test_dg_arc_13_copy_equals_code_for_the_estimate_submission_rows() -> None:
    """Items EST-ONE-OPEN-VERSION-1, EST-EVIDENCE-AT-SUBMIT-1 and the constraint's judgement
    record (the supervisor's rulings of 2026-10-01; PRD 1.168; 04 T-CON-13, §16.14 rev 1.241):
    what the estimate commands answer IS the PRD row, word for word — ERR-93
    ``estimates.VERSION_OPEN``, ERR-94 ``estimates.RECORD_NOT_REVIEWED`` and the four findings of
    a submission, IMP-138 to IMP-141, each under the code its row names. ERR-94 is one row for
    the approval's refusals: it quotes the sentence of a version whose evidence was voided after
    its submission (``estimates.EVIDENCE_WITHDRAWN``) as well. A placeholder ``<two words>`` is
    the template field ``{two_words}``."""
    from erev_api.domain.contracts import estimates

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    refusals = {
        "ERR-93": (estimates.VERSION_OPEN, {"element_code", "version_no"}),
        "ERR-94": (estimates.RECORD_NOT_REVIEWED, {"judgement_no"}),
    }
    for row_id, (template, fields) in refusals.items():
        assert f'rule_id = "{estimates.RULE_LIFECYCLE}"' in cells[row_id][1], row_id
        copy = _quoted(cells[row_id][4], after="`errors[].message`")
        assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields, row_id
        assert _fields(template) == fields, row_id
        assert template.format(**{name: f"<{name.replace('_', ' ')}>" for name in fields}) == copy
    assert f'"{estimates.EVIDENCE_WITHDRAWN}"' in cells["ERR-94"][4]
    findings = {
        "IMP-138": (estimates.EVIDENCE_MISSING, estimates.EVIDENCE_MISSING_MESSAGE, set()),
        "IMP-139": (estimates.ATTESTATION_REASON, estimates.ATTESTATION_REASON_MESSAGE, set()),
        "IMP-140": (
            estimates.CONSTRAINT_RECORD,
            estimates.CONSTRAINT_RECORD_MESSAGE,
            {"element_code"},
        ),
        "IMP-141": (estimates.ATTESTATION_VALUES, estimates.ATTESTATION_VALUES_MESSAGE, set()),
    }
    for row_id, (code, template, fields) in findings.items():
        assert cells[row_id][1] == f"`{code}`", row_id
        copy = _quoted(cells[row_id][3])
        assert {name.replace(" ", "_") for name in _placeholders(copy)} == fields, row_id
        assert _fields(template) == fields, row_id
        assert template.format(**{name: f"<{name.replace('_', ' ')}>" for name in fields}) == copy
    # the reason's length the row states is the one the command asks
    assert f"at least {estimates.ATTESTATION_REASON_LENGTH} characters" in _quoted(
        cells["IMP-139"][3]
    )


def test_dg_arc_13_copy_equals_code_for_the_combination_suggestions_row() -> None:
    """Item ACT-CHECKLIST-SUGGESTION-SCOPE-1 (the supervisor's rulings of 2026-10-02; PRD 1.181; 04
    table 15.4-I rev 1.265): IMP-103 is one sentence and one row with two substitutions. Its first
    quoted sentence is the checklist's line with the other contract's external id
    (``activation.SUGGESTION_MESSAGE``; the placeholder ``<external id>`` is the template field
    ``{external_id}``). The note names what stands in the id's place — for a session that does
    not read the other contract ``activation.CONTRACT_OUTSIDE``, in a stored line whose other
    contract is of another contracting entity ``activation.CONTRACT_OF_ANOTHER_ENTITY`` — and ends
    with the two sentences that result, word for word."""
    from erev_api.domain.contracts import activation

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    named, separator, note = cells["IMP-103"][3].partition('"; ')
    assert separator, cells["IMP-103"][3]
    copy = _quoted(named + '"')
    assert {name.replace(" ", "_") for name in _placeholders(copy)} == {"external_id"}
    assert _fields(activation.SUGGESTION_MESSAGE) == {"external_id"}
    assert activation.SUGGESTION_MESSAGE.format(external_id="<external id>") == copy
    substitutes = (activation.CONTRACT_OUTSIDE, activation.CONTRACT_OF_ANOTHER_ENTITY)
    sentences = [activation.SUGGESTION_MESSAGE.format(external_id=phrase) for phrase in substitutes]
    for phrase, sentence in zip(substitutes, sentences, strict=True):
        assert f'"{phrase}"' in note, phrase
        assert _placeholders(sentence) == set()
    assert note.endswith(f': "{sentences[0]}"; "{sentences[1]}"'), note


def test_dg_arc_13_copy_equals_code_for_the_modification_judgement_records_row() -> None:
    """Item MOD-LINKED-JUDGEMENTS-1 (the supervisor's rulings of 2026-10-01; PRD 1.169; 04 §16.14
    rev 1.242): what ``/submit`` of a modification answers while a judgement record of its own
    is a draft or waits for review IS the PRD row, word for word — ERR-95
    ``modifications.RECORD_NOT_REVIEWED``, under the rule id of SM-03. One row for two places:
    the approval's backstop says the same first sentence and ends with the sentence the row
    quotes for it. A placeholder ``<two words>`` is the template field ``{two_words}``."""
    from erev_api.domain.contracts import modifications

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}["ERR-95"]
    assert f'rule_id = "{modifications.RULE_STATE}"' in cells[1]
    template = modifications.RECORD_NOT_REVIEWED
    copy = _quoted(cells[4], after="`errors[].message`")
    assert {name.replace(" ", "_") for name in _placeholders(copy)} == {"judgement_no"}
    assert _fields(template) == {"judgement_no"}
    assert template.format(judgement_no="<judgement no>") == copy
    at_approval = modifications.RECORD_NOT_REVIEWED_AT_APPROVAL
    assert at_approval.split(". ", 1)[0] == template.split(". ", 1)[0]
    ending = at_approval.split(". ", 1)[1]
    assert f'then ends "{ending}"' in cells[4]


def test_dg_arc_13_copy_equals_code_for_the_header_conflict_row() -> None:
    """Item IMPORT-HEADER-CELL-CONFLICT-1 (the supervisor's ruling of 2026-10-02; PRD 1.204; 04
    table 15.4-B and §16.6 rev 1.310): the finding of a cell that a later row of an object states
    differently from its first row answers the PRD row IMP-147 word for word
    (``imports.validate.header_conflict``) — the sentence of an optional column, of a required
    one, and of a first row that leaves the cell blank. The row then names every object the
    rows of a template build together as the finding names it: the words of
    ``csv_v2.framework.Repeated.group`` and as many key parts as its ``named_by`` holds. The
    sentences are read from the row before it is unescaped: an inner quote is ``\\"`` there."""
    from erev_api.domain.imports import csv_v2, validate

    (line,) = [row for row in _copy_rows() if row.startswith("| IMP-147 |")]
    raw = UNESCAPED_PIPE.split(line.strip().strip("|"))[3]
    quoted = [_unescaped(found) for found in re.findall(r'(?<!\\)"((?:[^"\\]|\\.)*)"', raw)]
    assert all("<first row>" in text for text in quoted[:3])
    optional, required, blank_first, *objects = (
        text.replace("<first row>", "2") for text in quoted
    )
    assert (
        _placeholders(optional) == _placeholders(required) == {"object", "its value", "this value"}
    )
    assert _placeholders(blank_first) == {"object", "this value"}
    assert optional == validate.header_conflict(
        "<object>", 2, "<its value>", "<this value>", required=False
    )
    assert required == validate.header_conflict(
        "<object>", 2, "<its value>", "<this value>", required=True
    )
    for is_required in (False, True):
        assert blank_first == validate.header_conflict(
            "<object>", 2, None, "<this value>", required=is_required
        )
    named = {
        (repeat.group, len(repeat.named_by))
        for template in csv_v2.TEMPLATES.values()
        for repeat in template.repeats
    }
    assert {(text.split(" <", 1)[0], len(_placeholders(text))) for text in objects} == named
    assert len(objects) == len(named) == 7
    assert f"longer than {validate.QUOTED_LENGTH} characters" in _unescaped(raw)


def test_dg_arc_13_copy_equals_code_for_the_usage_period_row() -> None:
    """Item USAGE-REPORT-PERIOD-ENDED-1 (the supervisor's rulings of 2026-10-03; PRD 1.208; 04
    §16.3 "The usage period of a report" and table 15.4-B, rev 1.320): the refusal of a usage
    report or royalty statement whose usage period ends after the report's date answers the PRD
    row IMP-148 word for word, under the code the row names. One sentence serves the route, a
    person's request, the previews and the row of the CSV template ``usage``, which asks the same
    pure rule (``events.usage_period_refusal``): the three placeholders are the template's
    fields, and a period that has ended by the report's date has no sentence."""
    from datetime import date

    from erev_api.domain.contracts import events

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    assert cells["IMP-148"][1:3] == [f"`{events.USAGE_PERIOD}`", "ERROR"]
    copy = _quoted(cells["IMP-148"][3])
    assert _placeholders(copy) == _fields(events.USAGE_PERIOD_MESSAGE) == {"start", "end", "date"}
    assert copy == events.USAGE_PERIOD_MESSAGE.format(start="<start>", end="<end>", date="<date>")
    said = events.usage_period_refusal(date(2026, 8, 1), date(2026, 8, 31), date(2026, 8, 24))
    assert said == copy.replace("<start>", "01 Aug 2026").replace("<end>", "31 Aug 2026").replace(
        "<date>", "24 Aug 2026"
    )
    assert (
        events.usage_period_refusal(date(2026, 8, 1), date(2026, 8, 24), date(2026, 8, 24)) is None
    )


def test_dg_arc_13_copy_equals_code_for_the_policy_override_row() -> None:
    """Item POLICY-OVERRIDE-WITHDRAW-1 (supervisor ruling R-126 (b) (4) and (c); PRD 1.209; 04
    T-CON-23 "Not offered in release 1.0", rev 1.322): the refusal of every creation of a policy
    override answers the PRD row ERR-102 — the first sentence word for word, and for the second
    the forms the row quotes: one sentence of POLICIES §0.5 table 0.5-A as the example of a
    parameter that lists level C or O, and the four a parameter that lists neither, or a key the
    registry does not hold, is told. ``tests/unit/policies/test_override_not_offered.py`` holds
    the 23 sentences of the table to the code; this case holds the copy row to the code."""
    from erev_api.domain.policies import overrides

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    row = cells["ERR-102"]
    assert row[1] == (
        f'`policy-level-not-allowed` with `errors[].rule_id = "{overrides.RULE_NOT_OFFERED}"`'
    )
    assert row[2:4] == ["422", "Policy level not allowed"]
    quoted = re.findall(r'"([^"]+)"', row[4])
    assert quoted == [
        "Not offered in release 1.0",  # the paragraph of 04 T-CON-23 the row cites
        overrides.NOT_OFFERED,
        overrides.DECIDED_BY["returns.model"],
        overrides.SET_ONLY_AT.format(levels="<levels>"),
        overrides.FRAMEWORK_FIXED,
        overrides.NO_LEVEL,
        overrides.KEY_UNKNOWN,
    ]
    # The message the command builds is the two sentences, in the row's order.
    said = f"{overrides.NOT_OFFERED} {overrides.decided_instead('returns.model')}"
    assert said == (
        "Policy overrides for a contract or an obligation are not offered in this release. "
        "It is set on the product or on its obligation template."
    )
    assert _placeholders(overrides.SET_ONLY_AT.format(levels="<levels>")) == {"levels"}
    assert _fields(overrides.SET_ONLY_AT) == {"levels"}
    # ERR-47 keeps the slug's own copy for a registry value at a level its parameter does not
    # list; the two rows share the slug and the title and differ by the rule id.
    assert cells["ERR-47"][1:4] == ["`policy-level-not-allowed`", "422", row[3]]


def test_dg_arc_13_copy_equals_code_for_the_level_p_not_read_row() -> None:
    """Item PRODUCT-POLICY-VALUE-NOT-READ-1 (supervisor ruling R-126 (c) and the supervisor's
    rulings of 2026-10-03; PRD 1.210; 04 T-REF-20 and T-REF-23 rev 1.323; POLICIES §0.5 rule 1
    rev 1.125): the refusal of a level P value that no computation reads answers the PRD row
    ERR-103 word for word in both of its sentences (``reference.products``), under the rule id
    and on the member the row names. The one placeholder of each sentence, ``<key>``, is the
    template field ``{key}``: the parameter's code as the field has it after ``policy_values.``.
    Every parameter of the door's set is named in the row and refused by one of the two."""
    from erev_api.domain.reference import products

    cells = {_cells(row)[0]: _cells(row) for row in _copy_rows()}
    stated = cells["ERR-103"][4]
    sentences = (products.POLICY_NOT_READ_DEFAULT, products.POLICY_NOT_READ_REGISTRY)
    for template in sentences:
        copy = template.format(key="<key>")
        assert _placeholders(copy) == _fields(template) == {"key"}
        assert f'`errors[].message` "{copy}"' in stated
    assert products.POLICY_NOT_READ_DEFAULT != products.POLICY_NOT_READ_REGISTRY
    assert set(products.LEVEL_P_NOT_READ.values()) == set(sentences)
    for code in products.LEVEL_P_NOT_READ:
        assert f"`{code}`" in stated, code
    assert products.RULE_LEVEL_P_NOT_READ == CONVENTION_ROWS["ERR-103"]
    assert f'rule_id = "{products.RULE_LEVEL_P_NOT_READ}"' in cells["ERR-103"][1]
    assert 'on `errors[].field = "policy_values.<key>"`' in cells["ERR-103"][1]
    key = "pob.shipping_as_fulfilment"
    (error,) = products.policy_values_errors({key: "TRUE"})
    assert (error.field, error.rule_id, error.message) == (
        f"policy_values.{key}",
        products.RULE_LEVEL_P_NOT_READ,
        products.POLICY_NOT_READ_REGISTRY.format(key=key),
    )
