# B2 fix pass: legacy parity deviations (slug `fix-deviations`)

| Field | Value |
|---|---|
| Owner | Owner-editor, design phase B2 |
| Date | 2026-09-12 |
| Files edited | `docs/legacy/DEVIATIONS.md` (rev 1.1); `docs/legacy/golden/deviations.json` (regenerated); `research-harness/deviations/journal.py`, `build_deviations.py`, `probes_exact.py` |
| Rerun | `~/dev/erev/legacy-harness/.venv/bin/python ~/dev/erev/research-harness/deviations/build_deviations.py`: exit 0, 0 self-check failures; two runs byte-identical, `deviations.json` SHA-256 `a8ac329dccc955ca46de75f30868f668d343641612fa279fd2d1b23cfadd53ae` |
| Self-check | `.scratch/design-fix-deviations/selfcheck.py`: 32 markdown tables, undefined-id references (DEV, OQ-D, PJR, POL, ALG, CHK, JET, D, REQ, DG, E, IPL, B1, test ids, problem slugs, finding codes), JSON integrity and register-to-JSON consistency: 0 problems |

## Bottom line

- Posting rule `EXACT-CUM` (ALG-01 §2.1.3 as published) is now the default.
- Classification moved from A 48 / B 23 / C 51 to A 56 / B 9 / C 57. Journal B tests fell from 19 to 5: 8 moved to A and 6 to C.
- January 2023 now equals POLICIES.md CHK-022: gross Dr 21001 295.69 / Cr 5002 118.53, Cr 5001 187.69 (128.84 + 58.85), Cr 5003 48.32, Dr 15002 58.85; total 354.54 / 354.54.
- CHK-020 (adjustment view 240.22 / 240.22) and CHK-007 are reproduced and enforced by generator self-check 6.
- The sensitivity rule `POSTED-ALLOC` (the retired rev 1.0 composition) reproduces the rev 1.0 file exactly, with no class or non-probe value difference.

## Finding and decision register

| Finding or decision | Change made (file, section, id) | Status |
|---|---|---|
| B1-001 step 2: add posting rule `EXACT-CUM` | `journal.py` `posted_cumulative`: `EXACT-CUM` = round_half_up(X × f), bounded to [0, A] (mirrored for negative A), = A when f = 1; `DEFAULT_RULE` = `EXACT-CUM`; activation diagnostics `BOUNDED`, `ALIGNED`. `build_deviations.py` `--posting-rule` choices `EXACT-CUM` (default), `POSTED-ALLOC`, `LR-CUM`; sensitivity runs write only `.scratch/design-fix-deviations/`. Rev 1.0 label `ALG01` retired; its composition kept as `POSTED-ALLOC` | Applied |
| B1-001 step 2: rerun and replace `deviations.json` | Regenerated. Top-level `posting_rule_id` `EXACT-CUM`, `posting_rule` text, `signoff_units`, `probe_status_mapping` added; `counts` A 56, B 9, C 57 | Applied |
| B1-001 step 3: regenerate DEVIATIONS §0, §3 PJR-1, §4.2, §7.1, §9, `signoff_required` | DEVIATIONS §0 items 1, 3 to 7; §1.2, §1.3; §3 PJR-1, properties, alternatives table; §4.2 May bullets, October table, summary, changed lines, final posted revenue; §6.1 DEV-001, DEV-002; §7.1 (5 tests); §8 rows 3, 4, 5, 9 to 12, 81 to 83, 86 to 89; §9.1 counts and class moves; §9.2; §9.3; §10 C-07, C-14. `signoff_required` = 9 ids | Applied |
| B1-001: confirm January 2023 = CHK-022 and record A/B/C changes | Generator self-check 6: `je-month-2023-01` gross line items and production journal equal CHK-022; adjustment view equals CHK-020; CHK-007 118.53, then 237.07 / 118.54; completion revenue = TP = billing per contract. Class moves recorded in DEVIATIONS §9.1 and the revision log: B → A `je-step-04`, 05, 06, 11, `je-month-2023-01`, 02, 03, 07; B → C `je-step-10`, 12, 13, `je-month-2023-06`, 08, 09 | Applied |
| B1-001 step 4: PRD WLD-X-26 | New `je-month-2023-01` gross: Dr 21001 295.69, Dr 15002 58.85 / Cr 5001 187.69, Cr 5002 118.53, Cr 5003 48.32 (total 354.54). J-01.14 Mock Entity 1 batch becomes 295.69 | Not applicable (PRD owner) |
| B1-001 step 5: POLICIES JET-04a writes X′_p | none | Not applicable (POLICIES owner) |
| B1-001 step 6: BUILD_SPEC hold on `GT:journal_entry_totals` | Steps 1 to 3 for this document are complete | Not applicable (supervisor) |
| B1-002 (parity side): restate probe expectations under the DG-PAR-06 mapping | `probes_exact.py`: `committed_basis`, `progress_error_findings`; every probe upload carries `import_status`, `import_status_basis` (`e40_import_status`; `problem` {slug `duplicate-import`, status 409, `errors[0].rule_id` `IMPORT_FILE_DUPLICATE`} for the refused upload), `error_code_source` and `findings`. P3 gains one ERROR finding `PROGRESS_OVER_DELIVERY` (rows 2 and 6 aggregated); P4 second upload has no finding row. Generator self-check 7 enforces the mapping. DEVIATIONS §2.2 (import outcome, aggregated finding rows), §5 row 5 (stage `upload`), §6.2 DEV-011 and DEV-020, §7.3 | Applied |
| B1-002: DG-PAR-06 text and 05 IPL-01 `errors[]` | none | Not applicable (dev-guide and architecture owners) |
| B1-019 / D-30a: blank memo = WARNING `PROGRESS_MEMO_BLANK`, rows processed | DEVIATIONS §5 intro (blocking errors vs warnings), rows 4 and 5; §6.2 DEV-010 refs; §7.3 P1; OQ-D3; P1 note in `deviations.json` | Applied |
| B1-039 / D-17a: DEV-002 one approval class, regenerated mechanically | `build_deviations.py`: `signoff_units` (DEV-002 class: `je-step-08`, `je-step-14`, `je-month-2023-05`, `je-month-2023-10`, `je-month-2023-full-year`; DEV-052, DEV-010, DEV-050 and DEV-011 per case); per-test `signoff` text; check that every changed journal line is at most one cent. DEVIATIONS header Status, §6.1 DEV-001 and DEV-002, §9.2 | Applied |
| D-11a | As B1-001 | Applied |
| D-73 identifier authority | DEVIATIONS §5 intro: codes owned by 04 §15.4 and absorbed verbatim; severity mapping ERROR → `BLOCKING`, WARNING → `WARNING` (E-43); parity asserts finding severities | Applied. 04 §15.4 did not exist yet when this was checked (04 owner) |
| D-75: close OQ-D1 to OQ-D10 | DEVIATIONS §11: column "Status and ruling"; each marked **Resolved by D-75** with the ruling (OQ-D1 with D-11a and D-17a; OQ-D3 with D-30a) | Applied |
| New open item | DEVIATIONS §11 OQ-D11: `worksheet_row` of a finding on aggregated rows; recommended default = lowest contributing row, plus `worksheet_rows` | Open (supervisor) |
| D-40a SQLite | `shipped-db-equivalence` reads the shipped `ASC606.db` fixture only, which D-40a permits; no text change needed | Not applicable |
| D-13a, D-14a, D-21a, D-25a, D-48a, D-72, D-74 | Checked: the literals in the register (`ERP`, `MODIFICATION`, `CONTINUATION`, D-14 roles) already conform; no dependency on the other amendments | Not applicable |
| Revision log (fix-pass rule) | DEVIATIONS "Revision log" table, rev 1.0 and rev 1.1 | Applied |
| Self-check findings | Fixed the pre-existing unescaped pipes in PJR-5 (`\|negative line nets\|`) | Applied |
| dev-guide rev 1.1 (DG-PAR-03, DG-PAR-10, DG-PAR-11: "deviations.json must carry posting rule `EXACT-CUM`"; probe `detail`) | Added exact literal `posting_rule_id` = `EXACT-CUM`; P3 `detail` unchanged ("Contract 1 POB #1 Hardware 1: delivery 7 exceeds remaining quantity 5") | Deferred: the dev-guide revision log names DG-PAR-10 and DG-PAR-11, but the rows were not in `docs/dev-guide.md` when checked, so alignment of key names and the `detail` rule is unverified |

## Scratch evidence

`.scratch/design-fix-deviations/`: `baseline-rev1.0/` (pre-fix files), `run1.log`, `run2.log`, `final-run1.log`, `final-run2.log` and `.sha` files, `run-posted-alloc.log`, `deviations-POSTED-ALLOC.json`, `fragments.md`, `analysis.txt`, `selfcheck.py`.
