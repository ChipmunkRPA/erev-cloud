# B2 fix pass: design system

| Field | Value |
|---|---|
| Owner-editor | `fix-design-system` |
| Date | 2026-09-12 |
| Files edited | `docs/design/DESIGN_SYSTEM.md` (revision 1.1), `docs/design/tokens.css` (comments only; token values unchanged) |
| Inputs | `docs/reviews/B1-consistency.md` (B1-028 to B1-032, B1-038), `docs/01-DECISIONS.md` §7 (D-11a to D-75), `docs/dev-guide.md` §0.5, §4, §8, `docs/04-DATA_MODEL.md` E-69, API-C-11, T-PLT-24, T-PLT-29, T-PLT-31, `docs/accounting/POLICIES.md` POL-201, `docs/02-PRD.md` §3, §5.4 |
| Verification | Token verifier re-run from `.scratch/design-fix-design-system/verify_tokens.py`: 48 colour tokens, 81 contrast pairs, dark blocks identical, no failures. Self-check `.scratch/design-fix-design-system/selfcheck.py`: tables, DS id definitions and cross-document ids (see §3) |

## 1. Findings and decisions applied

| Finding or decision | Change made (file, section, id) | Status |
|---|---|---|
| B1-028 code paths | DESIGN_SYSTEM header (precedence row cites dev-guide §0.5 and §4); DS-COL-00 (`frontend/src/styles/tokens.css`, `make tokens`); DS-DEN-01 (external `/theme-init.js`, DG-FE-13, no inline script per DG-FE-12 and REQ-SEC-004); DS-LINT-00 (`scripts/design_check.py`, `scripts/design_check.toml`, scan root `frontend/src/`) plus a new §12 path table; global exclusions; DS-LINT-07 (inline SVG allowed only in the icon and chart directories; the undefined "brand directory" exemption is replaced, since the wordmark and monogram are live text); DS-LINT-14; DS-VER-06; `tokens.css` header comment (copy path, `make tokens`, `app.css`, `fonts.css`, `/theme-init.js`) | Applied |
| B1-029 vocabulary lint | DS-CPY-02 lists the union; DS-LINT-19 becomes the `make vocab-check` rule (union of REQ-UX-010 and DS-CPY-02, case-insensitive, whole words, allow-list = legacy column definitions plus the SF-26 help catalogue); DS-LINT-00 states that `design_check.py` does not implement DS-LINT-19; DS-LINT-21 fixtures exclude DS-LINT-19; DS-VER-10 adds `make vocab-check` | Applied (DS part). The dev-guide §4.3 part belongs to the dev-guide owner |
| B1-030 negative style, D-75 (PRD Q8) | DS-FMT-06 (tenant setting: parentheses by default, minus allowed; U+2212 for minus; the format module applies the style itself); DS-FMT-09, DS-FMT-10, DS-FMT-15, DS-FMT-31 (negatives per DS-FMT-06); DS-FMT-26 (XLSX format per style); DS-FMT-29 (accessible markup for both styles); §6.4 (minus-style row); DS-TYP-09; DS-CMP-21 (money input accepts U+2212); DS-I18N-03 (style is a tenant setting, not a locale property); DS-VER-03 (runs once per style, plus the XLSX writer for both styles); `tokens.css` `num-pos` comment | Applied |
| B1-031 RPO bands | DS-CH-03 "Bands" row (bands of the `rpo` report run, POL-201 `rpo.time_bands` default `[12, 24]`, no chart default, one to five bands drawn, Table view only above five); new "Band labels" row (catalogue copy built from boundaries); DS-VIZ-06 (three default bands use `--viz-rpo-1` to `--viz-rpo-3`) | Applied |
| B1-032 routes and period identifier | DS-CMP-02 rail table: destination and active set by SF id, with no route paths; default route per SCREENS.md (PRD §3 until SCREENS.md exists, DG-FE-02); context-filled route parameters; Settings opens SF-15 [J]. DS-CMP-03: `entity`, `period`, `book` carry the API-C-11 values verbatim; `period` = `period_key` (`FY2026-P09`); the pill shows the DS-FMT-19 label. DS-CMP-08: the obligation route cited by SF-03, not by path | Applied (DS part). The SCREENS.md brief belongs to the supervisor |
| B1-038 notification kinds | DS-CMP-05: items are T-PLT-24 notifications from `GET /me/notifications`; a table of the twelve E-69 kinds (including `ITEM_APPROVED`, `PERIOD_LOCKED`, `PERIOD_REOPENED`) mapped to NTF-01 to NTF-12, each with an existing registry icon and a colour; navigation by `link_path`; new empty-state copy; the ARIA announcement cites `APPROVAL_ASSIGNED`. DS-CMP-24: the jobs section of the panel is removed; outcomes are shown in place and by toast, and failures raise `JOB_FAILED` | Applied |
| B1-010 (DS OQ-04 part) | §15 OQ-04 and DS-VER-06: the gallery flag is set by `make frontend`, `make dev-up` and `make e2e`, and unset in `make build` and Docker images | Applied |
| B1-027 unprefixed OQ ids | §15 intro gives the citation form `DESIGN_SYSTEM:OQ-nn`; no id is renumbered | Applied (DS part) |
| DS OQ-01 | Resolved by D-75: default adopted (ISO codes everywhere; DS-FMT-05 unchanged) | Applied |
| DS OQ-02 | Resolved by D-75: default adopted (UTC; DS-FMT-17 unchanged) | Applied |
| DS OQ-03 | Resolved by D-75: the default deferred to the dev guide, so the dev-guide §0.5 paths bind | Applied |
| DS OQ-04 | Resolved by D-75 together with dev-guide §0.5 and D-48a (targets above) | Applied |
| DS OQ-05 | Resolved by D-75 read together with B1-031 and the supervisor brief for this pass: bands come from the API under POL-201; the five-band proposal is withdrawn because 03 and POLICIES rank above DS (D-§0) | Applied; the supervisor should confirm that D-75's blanket adoption does not revive the five-band default |
| D-48a targets | DS cites only dev-guide §4 loop targets: `make tokens`, `design-check`, `vocab-check`, `lint`, `ci`, `frontend`, `dev-up`, `e2e`, `build` | Applied |
| D-73 identifier authority | §0.1 bullets (enum literals verbatim, UI labels are copy, routes by SF id); header precedence row; DS-CMP-02, DS-CMP-03, DS-CMP-05, DS-CMP-08 | Applied |
| D-74 split screen specifications | Header precedence and companion rows; §0.1 "Screen specifications" bullet (SCREENS.md denotes the pair) | Applied |
| D-75 copyright ruling | DS-BR-05: the About dialog (SF-27) reads "eRev by Chipmunk Robotics" | Applied |
| D-75 Q10 upload limits | DS-CMP-18: maximum size per 04 T-PLT-29 by purpose (imports `IMPORT_SOURCE` 50 MiB, replacing "50 MB") | Applied |
| Canonical literal: E-69 gains `ITEM_APPROVED`, `PERIOD_LOCKED`, `PERIOD_REOPENED` | DS-CMP-05 kind table | Applied |
| Canonical literals: account roles (33), `clearing_purpose`, ratable conventions, E-25 `EARLY_RENEWAL`, registry literals, posting composition | DS contains none of these vocabularies | Not applicable |
| D-11a, D-13a, D-14a, D-17a, D-21a, D-25a, D-30a, D-40a, D-72 | No design-system content is affected | Not applicable |
| D-75 other rulings (ratable conventions, job queues, perf tenant, local keys, tenant provisioning, G4 lists, reopen approvers, M-RA-04, `CONTRACT_LIABILITY` control role, demo users, mock ports, single currency) | No design-system content is affected | Not applicable |
| DS-CMP-19 status chip vocabulary (D-73 check) | Its labels are UI copy; the table maps labels to tones and cites no enum literals, so it is unchanged | Not applicable |

## 2. Deferred items and new open questions

| Item | Reason | Owner |
|---|---|---|
| DS OQ-06: no registry parameter for the negative money style | 04 owns registry codes and literals (D-73). Recommended: T-PLT-31 platform parameter `ui.negative_money_style` ∈ {`PARENTHESES` (default), `MINUS`}, delivered by `GET /me`. Until then, parentheses | `docs/04-DATA_MODEL.md` |
| DS OQ-07: no bulk mark-read command | API-R-03 has only `POST /me/notifications/{id}/read`. Recommended: `POST /me/notifications/read-all` with `before`. Until then, "Mark all as read" is not rendered | `docs/04-DATA_MODEL.md` |
| DG-MK-design-check scans "DS-LINT-01 to DS-LINT-22" | DS-LINT-19 is now implemented only by `make vocab-check` (B1-029). The dev guide should exclude DS-LINT-19 from design-check, and DG-MK-vocab-check should adopt the union list, case-insensitive whole-word matching and the SF-26 help catalogue path | `docs/dev-guide.md` |
| RPO report result shape | 04 defines the `rpo` parameter `time_bands` but not the ordered band list, with month boundaries, that DS-CH-03 consumes | `docs/04-DATA_MODEL.md` |
| T-PLT-24 `link_path` example `/approvals/<id>` | The example hard-codes a route path that SCREENS.md owns (D-73) | `docs/04-DATA_MODEL.md` |
| Default route of each rail destination, including the Settings landing (SF-15) | SCREENS.md owns route paths (D-73); DS fixes only the SF id | `docs/design/SCREENS.md` |

## 3. Self-check

`selfcheck.py` checks the following:

- every markdown table in DESIGN_SYSTEM.md has a separator row and a consistent cell count, with a blank line before and after it;
- every DS id referenced in DESIGN_SYSTEM.md or `tokens.css` is defined;
- every cross-document id is present in its authoritative document: SF, NTF, J, WLD, LTM, REQ, CTL, POL, D, DG, API, T-*, E-, B1 and M-* ids;
- every §15 open question cited in the text exists.

The first run found one table with no blank line after it (the §12 path table), which is now fixed. The final run found 0 issues: 50 tables, 266 DS ids defined and referenced, every cross-document id present, and §15 OQ-01 to OQ-07 defined. The token verifier re-run after the `tokens.css` comment edits passed: 48 colour tokens, 81 contrast pairs, dark blocks identical, no gamut, contrast or palette failures.
