# eRev Cloud: design system

| Field | Value |
|---|---|
| Owner | Design director (design phase, slug `des-system`); revision 1.1 by owner-editor `fix-design-system`; revision 1.2 by owner-editor `fix-screens` (design phase B3); revision 1.3 by residue sweeper `doc-residue` (post-B3 residue sweep); revision 1.4 by lane F-WEB-R (PR-8.7); revision 1.5 by lane SECFIX-PLT (security review of 2026-09-29, finding P3-5); revision 1.6 by lane WEB-QA (the supervisor's ruling R-59); revision 1.7 by lane F-CTR-WEB (the supervisor's ruling R-93 (d)); revision 1.9 by lane WEB-QA (the supervisor's ruling R-104 and its ruling of 2026-09-30 on item W-22: the cue of a sticky footer); revision 1.8 by lane F-CLO-WEB (the supervisor's rulings R-83 (c) and R-100 (c): the disabled menu item of DS-CMP-28); revision 1.10 by lane F-CTR-WEB (BUILD_SPEC CTR-25; the supervisor's answer of 2026-10-01 to the lane's pre-build line: the grouped master list of DS-CMP-08, the secondary action of a modal drawer of DS-CMP-09, the formatted strip cell of DS-CMP-06); revision 1.11 by lane F-CTR-WEB (item HIST-CALC-CHIP-1; the supervisor's ruling of 2026-10-01 on the lane's point N1: the actor form "<actor> on behalf of <name>" of DS-CMP-12); revision 1.12 by lane F-CLO-WEB (BUILD_SPEC RPS-19, first head; the supervisor's rulings of 2026-10-01 14:53 and 22:52: DS-CH-06 "Category bars", the plain bars for disaggregation of DS-VIZ-00) |
| Date | 2026-10-02 (revision 1.12) |
| Status | Binding build contract. Read-only for the build loop (`docs/01-DECISIONS.md` §0). |
| Precedence | Below `docs/00-GOAL.md`, `docs/01-DECISIONS.md` and `docs/03-REQUIREMENTS.md`. Above the screen specifications `docs/design/SCREENS.md` and `docs/design/SCREENS_B.md` (one rank, D-74) for every visual, token, formatting and component rule. Code paths and make targets: `docs/dev-guide.md` §0.5 and §4 (D-48a). Enumeration literals, permission codes and problem slugs: `docs/04-DATA_MODEL.md` (D-73). Route paths: `docs/design/SCREENS.md`, by PRD SF id (D-73). |
| Companion files | `docs/design/tokens.css` (normative token source). `docs/design/SCREENS.md` and `docs/design/SCREENS_B.md` (screen composition and route paths; written separately, D-74). |
| Applies decisions | D-02 (vocabulary), D-12 (labelled balances, never a signed position), D-41 (stack), D-48a (make targets), D-60 (look and feel), D-61 (brand), D-62 (anti-slop), D-73 (identifier and route authority), D-74 (screen specification pair), D-75 (rulings on open questions), D-76 (rulings on B2 open questions), D-77 (design freeze) |
| Closes gaps | M-DES-02, M-DES-03, M-DES-04 (see §14) |
| Inputs | `docs/research/02-rightrev-ui-reference.md` (all sections and all 31 images in `docs/research/rightrev-ui/`), research 07 F-04/F-07/F-10, `docs/research/99-gaps.md`; revision 1.1: `docs/reviews/B1-consistency.md` and `docs/01-DECISIONS.md` §7; revision 1.2: `docs/01-DECISIONS.md` §8 (D-76, D-77), `docs/04-DATA_MODEL.md` rev 1.2 (API-R-03, API-S-Me, T-PLT-31, table 1.2-D), `docs/05-ARCHITECTURE.md` TZ-10, `docs/dev-guide.md` DG-FE-20, `docs/design/SCREENS.md` §16 and `docs/design/SCREENS_B.md` §18 |

## Revision log

| Rev | Date | Editor | Findings and decisions applied | Sections and ids changed |
|---|---|---|---|---|
| 1.0 | 2026-09-12 | Design director (`des-system`) | First binding issue | All |
| 1.1 | 2026-09-12 | Owner-editor (`fix-design-system`) | B1-028: code paths and commands cite `docs/dev-guide.md` §0.5 and DG-FE-13 (external `/theme-init.js`); no behaviour change | Header; DS-COL-00; DS-DEN-01; DS-LINT-00 and the §12 path table; DS-LINT-07; DS-LINT-14; DS-VER-06; `tokens.css` header comment |
| 1.1 | 2026-09-12 | Owner-editor (`fix-design-system`) | B1-029: one vocabulary list (the union, case-insensitive, whole words), implemented by `make vocab-check`, with the SF-26 help catalogue allow-listed | DS-CPY-02; DS-LINT-00; DS-LINT-19; DS-LINT-21; DS-VER-10 |
| 1.1 | 2026-09-12 | Owner-editor (`fix-design-system`) | B1-030 and D-75 (PRD Q8): the negative style is a tenant setting, default parentheses, minus allowed; verification covers both | DS-TYP-09; DS-FMT-06, DS-FMT-09, DS-FMT-10, DS-FMT-15, DS-FMT-26, DS-FMT-29, DS-FMT-31; §6.4; DS-CMP-21; DS-I18N-03; DS-VER-03; `tokens.css` `num-pos` comment; §15 OQ-06 |
| 1.1 | 2026-09-12 | Owner-editor (`fix-design-system`) | B1-031 and D-75 (DS OQ-05): DS-CH-03 renders the bands the API returns (POL-201) | DS-VIZ-06; DS-CH-03; §15 OQ-05 |
| 1.1 | 2026-09-12 | Owner-editor (`fix-design-system`) | B1-032 and D-73: rail destinations by SF id; the `period` URL parameter is the API-C-11 `period_key`; no hard-coded route paths | DS-CMP-02; DS-CMP-03; DS-CMP-08 |
| 1.1 | 2026-09-12 | Owner-editor (`fix-design-system`) | B1-038: the notifications panel lists E-69 kinds only (twelve kinds, including `ITEM_APPROVED`, `PERIOD_LOCKED` and `PERIOD_REOPENED`); no jobs section | DS-CMP-05; DS-CMP-24; §15 OQ-07 |
| 1.1 | 2026-09-12 | Owner-editor (`fix-design-system`) | B1-010 and D-48a: the gallery flag is set by `make frontend`, `make dev-up` and `make e2e` | DS-VER-06; §15 OQ-04 |
| 1.1 | 2026-09-12 | Owner-editor (`fix-design-system`) | D-74 screen specification pair; D-75 DS OQ-01 to OQ-05 closed; D-75 Q10 upload limits per 04 T-PLT-29; D-75 copyright ruling | §0.1; §15; DS-CMP-18; DS-BR-05 |
| 1.2 | 2026-09-12 | Owner-editor (`fix-screens`) | **Applied.** D-76 on DESIGN_SYSTEM:OQ-06 (the negative style is read from `ui.negative_number_style` through `GET /me` `tenant_settings`; the 04 name is kept, 04 B3-D01) and OQ-07 ("Mark all as read" sends `POST /me/notifications/read-all`) | DS-FMT-06; DS-CMP-05; §15 OQ-06, OQ-07 |
| 1.2 | 2026-09-12 | Owner-editor (`fix-screens`) | **Applied.** D-76 on SCREENS:OQ-S-05, OQ-S-06, OQ-S-11, OQ-S-12, OQ-S-13, OQ-S-20 and SCREENS_B:OQ-B-01, OQ-B-15, OQ-B-16, OQ-B-27: stepper anatomy for every multi-step flow; immutable staging rows, a read-only header match table and corrections by re-upload (inline editing and "Save mapping as preset" removed, because 04 defines neither); "Read-only access" and "Ask about revenue" in the top bar; 54 chip words; step 3 "Transaction price"; master-detail variants as examples; confidence as two-decimal text; "Accept" only for command-bound proposals; the tour popover composition | DS-CMP-01; DS-CMP-08; DS-CMP-17; DS-CMP-18; DS-CMP-19; DS-CMP-25; new DS-CMP-32 |
| 1.2 | 2026-09-12 | Owner-editor (`fix-screens`) | **Applied.** 05 TZ-10 (`05:OQ-ARC-13` resolved by D-76): a design-check rule against date construction outside the format module, aligned with DG-FE-20; DS-VER-06 names the route-error demonstration button and the tour popover of the gallery | new DS-LINT-23; §12 suppression list; DS-VER-06 |
| 1.2 | 2026-09-12 | Owner-editor (`fix-screens`) | **Decisions taken in B3.** Table 1.2-DS below (B3-DS01 to B3-DS08). No open question is raised (D-77) | Revision log |
| 1.3 | 2026-09-12 | Residue sweeper (`doc-residue`; post-B3 residue sweep, detail in `docs/reviews/B4-doc-residue.md`) | **Applied.** §15 OQ-06 names the 04 key `ui.negative_number_style` in its proposal cell, as B3-DS01 decided. DS-CMP-19 gains "Met" and "Shortfall" for the usage-commitment status literals `MET` and `SHORTFALL` of 04 API-S-UsageCommitment (04 B3-D13), which SCREENS §4.4 renders as chips. **Verified without change.** The TZ-10 date rule already has its number, DS-LINT-23, which 05 TZ-10 (rev 1.3) and DG-FE-20 now cite. **Decision taken in the sweep (D-77).** "Met" takes the positive tone and CheckCircle icon of "Satisfied"; "Shortfall" takes the warning tone and WarningCircle icon of "Not mapped", because a shortfall is billable and needs attention but is not an error | §15 OQ-06; DS-CMP-19 |
| 1.4 | 2026-09-19 | Lane F-WEB-R (PR-8.7; `docs/reviews/loop/prod/readiness-matrix.md` row PR-8.7; `L8-merge.md` run 2 observation) | **Applied.** A per-currency totals row names its ISO code: in the DS-FMT-12 Currency column of a mixed-currency grid, and, while that column is hidden, in its label "Total (<ISO>)"; a single totals row keeps the label "Total". Rendering rule only; totals still come from the API (DS-FMT-02) and are never summed across currencies. Prerequisite of the K-04 activation under the D-88 L7-6-Q-1 gate clause (CTR-20) | DS-FMT-12; DS-CMP-10 item 7 |
| 1.5 | 2026-09-30 | Lane SECFIX-PLT (security review of 2026-09-29, finding P3-5; number assigned by the supervisor) | **Applied.** DS-CMP-10 "Copy": text copied from a grid follows the formula-injection rule of the exports — a leading `=`, `+`, `-`, `@`, tab or carriage return gets an apostrophe, plain decimals of money and number cells stay numbers, and a tab or line break inside a cell becomes a space. The sentence had said "raw values" only, and `Mod C` wrote a cell that begins with `=` unchanged to the clipboard. 03 rev 1.23 (REQ-SEC-011) and 05 rev 1.47 (UPL-20, THR-13) carry the rule | DS-CMP-10 |
| 1.6 | 2026-09-30 | Lane WEB-QA (the supervisor's ruling R-59 of 2026-09-30, `docs/reviews/loop/prod/RULINGS-2026-09-29.md`; number assigned by the supervisor, register index 33) | **Applied.** Browser-QA finding Q-9 and its write side: four editors sent a picked date into a field the API types date-time and were refused, and the documents did not say which instant a picked date becomes. DS-I18N-08 now states it: where the API stores an instant and the screen works in days, the day is the UTC date of the instant (the DS-FMT-17 date part); the effective date of a versioned configuration goes on the wire as 12:00:00Z of the picked date; a validity window in platform time runs from 00:00:00Z of its first day to 23:59:59Z of its last day. Known limitation recorded: an entity beyond UTC+11 reads the next day (item CFG-EFFECTIVE-DATE-1). No token, component or format pattern changes; DS-FMT-16 and DS-FMT-17 are unchanged | DS-I18N-08 |
| 1.7 | 2026-09-30 | Lane F-CTR-WEB (BUILD_SPEC CTR-24; the supervisor's ruling R-93 (d) of 2026-09-30, `docs/reviews/loop/prod/RULINGS-2026-09-29.md`; number assigned by the supervisor) | **Applied.** DS-CMP-10 gains the form-held variant of inline editing: draft lines that a form holds in its own state and saves with the form in one body (the draft contract lines of SF-03:new and SF-03:edit; the change lines of the modification wizard) are edited in the line editor (`frontend/src/components/line-editor`), because the DataGrid reads server pages and saves cell by cell. The variant keeps the grid semantics, the keyboard and the ARIA of DS-CMP-10 and states its differences: one DS-CMP-21 control in each cell at all times, no save per cell (no spinner, no `Mod Z`), the validation message as text below the control, "Add line" and "Remove line" instead of the DataGrid toolbar, and no cell range. No token, format pattern or DataGrid behaviour changes | DS-CMP-10 |
| 1.9 | 2026-09-30 | Lane WEB-QA (item W-22; the supervisor's ruling R-104 (b) and its ruling of 2026-09-30 on the item's open point 3, `docs/reviews/loop/prod/RULINGS-2026-09-29.md`; number assigned by the supervisor; row appended at the table's tail) | **Applied.** Browser-QA finding on SF-12 at 1440 × 761: the sticky decision form covered the fourth change row with nothing to say so, and text assertions pass on covered rows. The cue that `docs/design/SCREENS.md` rev 1.18 defined for that view becomes the rule of every sticky footer: the link button "More below" as the footer's first row while content lies beneath it; the container's `scroll-padding-block-end` at the footer's height including that row, in both states; the measuring on scroll, on resize and on a change of content. The second clause comes from the whole e2e gate: a change row that took focus while the cue was not shown stopped flush with the shorter footer and was covered by 29.5 px when the cue appeared. No token, colour or component is added | DS-CMP-16 item 6; DS-CMP-18 Footer |
| 1.8 | 2026-09-30 | Lane F-CLO-WEB (the supervisor's rulings R-83 (c) and R-100 (c) of 2026-09-30, `docs/reviews/loop/prod/RULINGS-2026-09-29.md`; number assigned by the supervisor; docs first) | **Applied.** DS-CMP-28 states the disabled menu item: an item that a state of the record makes unavailable stays in the menu, disabled, with its reason in a DS-CMP-27 tooltip it is described by; it keeps its place in the arrow-key order, so the reason is reachable by keyboard, and it is never activated. Hiding stays the answer to a missing permission (SCREENS SCR-PERM-02, SCR-PERM-03). First use: "Permanently lock" behind an earlier period that is not permanently locked (SCREENS_B §1.1 rev 1.32) | DS-CMP-28 |
| 1.10 | 2026-10-01 | Lane F-CTR-WEB (BUILD_SPEC CTR-25; the supervisor's answer of 2026-10-01 to the lane's pre-build line, register index 99; number assigned by the supervisor; docs first; row appended at the table's tail) | **Applied.** The estimates workbench (SCREENS §8) needs three things of components that every screen shares, so they are stated here and built once. DS-CMP-08: a master list may list its rows under caption rows — SCREENS §8.3 groups the estimated elements under their kind — and each option names its caption; a grouped list renders every row. A row whose name is an identifier sets it in mono. DS-CMP-09: the footer of a modal drawer may hold one secondary action between "Cancel" and the primary action — SCREENS §8.4 "Save draft" beside "Submit for approval". DS-CMP-06: a strip cell may hold a percentage, a date or a quantity in its own format — SCREENS §8.4 "Progress", "Rate", "Effective date" — beside the money and count cells; such a cell is an Explain trigger where the API names its explanation | DS-CMP-06, DS-CMP-08, DS-CMP-09 |
| 1.11 | 2026-10-01 | Lane F-CTR-WEB (item HIST-CALC-CHIP-1, on main as 344b1f15; the supervisor's ruling of 2026-10-01 on point N1 of the lane's report, register index 152; number assigned by the supervisor; row appended at the table's tail) | **Applied.** DS-CMP-12 listed the forms of an event's actor without the one `docs/design/SCREENS.md` §4.7 rev 1.39 built for the audit trail of a contract: an event written for a principal names both, "<actor> on behalf of <name>" — "System on behalf of Maya Chen" for what the system wrote on a person's command. The avatar stays the actor's own: a person's initials, none for the system | DS-CMP-12 |
| 1.12 | 2026-10-02 | Lane F-CLO-WEB (BUILD_SPEC RPS-19, first head — the revenue dashboard; the supervisor's rulings of 2026-10-01 14:53, on the item's second question, and 22:52, on the chart's id; `docs/design/SCREENS_B.md` rev 1.82; number assigned by the supervisor, register index 159; docs first; row appended at the table's tail) | **Applied.** DS-VIZ-00 names "plain bars for disaggregation" among the chart forms of 1.0 and §5.3 specified none. DS-CH-06 "Category bars": one horizontal bar per category of a `disaggregation` run, the largest first, in the categorical slots in that order; at most seven are drawn and none is folded into "Other" — the browser adds no money up, so more than seven leave only the Table view, as six time bands do for DS-CH-03; the Table view ends with the total the API states. DS-VIZ-03 says so for its fold | DS-VIZ-00, DS-VIZ-03, DS-CH-06 |

**Table 1.2-DS Decisions taken in B3.**

| Id | Question | Decision | Rationale |
|---|---|---|---|
| B3-DS01 | DESIGN_SYSTEM:OQ-06 proposed `ui.negative_money_style`, while 04 already held `ui.negative_number_style` | Cite `ui.negative_number_style` and `tenant_settings.negative_number_style` | D-76 adopts a proposal "unless the owning document has renamed it"; 04 owns literals (D-73; 04 B3-D01) |
| B3-DS02 | Which `before` value "Mark all as read" sends | The `created_at` of the newest notification loaded in the panel | A notification that arrives after the panel loaded stays unread |
| B3-DS03 | 05 TZ-10 asks for a rule "over fields typed `BusinessDate`", which a dependency-free regular-expression script cannot see | DS-LINT-23 forbids `new Date(` and `Date.parse(` outside the format module and cannot be suppressed | A path rule needs no type analysis and agrees with the DG-FE-20 ESLint rule run by `make lint` |
| B3-DS04 | DS-CMP-18 said an identical re-upload "opens the existing batch"; 04 refuses it with 409 `duplicate-import` (`IMPORT_FILE_DUPLICATE`) | Follow 04: refuse and name the earlier import | 04 owns API behaviour (D-§0) |
| B3-DS05 | DS-CMP-25 forbade a confidence percentage, while the adopted SCREENS_B:OQ-B-15 shows per-field confidence | Two-decimal text with the outline chip "Check" below 0.75; never a percentage, bar or colour | Keeps the anti-reliance intent and the adopted default |
| B3-DS06 | Chip words used on screens without a "proposed" marker ("Balanced", "Denied", "Timed out", "Budget exceeded", "Disabled", "Not mapped", "Revoked", "Expired") | Added to DS-CMP-19 with the tones and icons the screens give | DS-CMP-19 is the only mapping from status to tone |
| B3-DS07 | Which value drives the "Ask about revenue" button | `GET /me` `tenant_settings.ai_enabled`, which already folds in the tenant kill switch and `EREV_AI_KILL_SWITCH` | 04 API-S-Me defines the resolved value |
| B3-DS08 | The top-bar button needs Sparkle, which DS-LINT-07 confines to the AI component directory | The button component lives in the AI component directory and the top bar imports the component | DS-LINT-07 stays unchanged |

## 0. How to use this document

### 0.1 Conformance

- Every rule has a stable id of the form `DS-<AREA>-<NN>`. Build items, tests and review findings cite these ids.
- Rules are mandatory unless marked **(guidance)**. Guidance rules describe craft intent that no automated check can prove; designer QA (G12) reviews them.
- A rule marked **[lint]** is enforced by the design-check script (§12). A rule marked **[test]** has a unit, component or Playwright test named in §13.
- Legend for claims: **[F]** fact with a cited source; **[A]** assumption; **[J]** judgement by this author, with a one-line rationale.
- **Screen specifications.** In this document, `docs/design/SCREENS.md` and "SCREENS" denote the pair `docs/design/SCREENS.md` and `docs/design/SCREENS_B.md`, which share one precedence rank (D-74). SCREENS.md owns the route path of each PRD SF id. This document names screens by SF id and hard-codes no route paths (D-73).
- **Code paths and targets.** File paths and make targets are those of `docs/dev-guide.md` §0.5 and §4 (D-48a). Enumeration literals (for example E-69 `notification_kind`) are cited verbatim from `docs/04-DATA_MODEL.md`; UI labels are copy (D-73).

### 0.2 Area codes

| Code | Area | Section |
|---|---|---|
| BR | Brand, wordmark, voice | §1 |
| COL | Colour tokens, themes, contrast | §2 |
| TYP | Typography | §3 |
| SP, DEN, RAD, ELV, MOT, ICO | Spacing and layout, density, radii, borders and elevation, motion, iconography | §4 |
| VIZ, CH | Data-visualization palettes, chart specifications | §5 |
| FMT | Numbers, money, dates | §6 |
| CMP | Components | §7 |
| A11Y | Accessibility | §8 |
| I18N | Internationalization | §9 |
| CPY | UI copy | §10 |
| AP | Anti-patterns | §11 |
| LINT | Design-check rules | §12 |
| VER | Verification | §13 |

### 0.3 Token source of truth

- **DS-COL-00.** `docs/design/tokens.css` is the only place colour, shadow, radius, font, motion and density values are defined. The web app carries a byte-identical copy at `frontend/src/styles/tokens.css` (`docs/dev-guide.md` §0.5 and §1.3), written only by `make tokens` (DG-MK-tokens). `make design-check` fails when the copy differs from `docs/design/tokens.css` (DS-LINT-14) **[lint]**. Rationale [J]: the loop cannot edit `docs/design/`, so the copy must be mechanical and verifiable.
- Components consume tokens only through Tailwind utilities generated by the `@theme inline` block in `tokens.css`, or through `var(--token)` in CSS modules and chart props. Raw colour literals are forbidden in application code (§12).

### 0.4 Relationship to the reference study

The layout class follows research 02 §2 (2026 redesign structure) as D-60 directs. Everything visual in this document is original. Nothing from `docs/research/rightrev-ui/` (screenshots, logos, colours, feature names) ships in the product (research 02 §7 note; `docs/00-GOAL.md` §5). The table below records what was taken as an idea and what was deliberately rejected.

| Observed in research 02 | Decision here |
|---|---|
| Top bar with scoped search and an open-periods chip (img 06, 24) [F] | Top bar with a context pill (entity, period, book) and Cmd-K (DS-CMP-01) |
| Icon rail plus an expandable tree (img 24, 29) [F] | One collapsible rail with ten D-02 destinations; no second navigation paradigm (DS-CMP-02) |
| Six-metric KPI strip with six unrelated value colours (img 06) [F] | KPI strip in neutral ink; colour only for state (DS-CMP-06) |
| Nested dark segmented tabs, 8 section tabs plus 7 sub-tabs (img 06, 07) [F] | Flat underline tabs, one level per region, no black pills (DS-CMP-07) |
| POB card list with mint selection tint (img 06) [F] | Dense master list with a 2 px accent selection edge (DS-CMP-08) |
| Five-step tracker with blue check circles (img 02, 29) [F] | Our own five-step tracker with evidence per step and our labels (DS-CMP-17) |
| Old value red, new value green in audit logs (img 23) [F] | Diff view with removed/added semantics carried by text markers, not red/green alone (DS-CMP-16) |
| Inconsistent number formats and five date formats (research 02 §3.2) [F] | One money, negative, percent and date format (§6) |
| Pastel donuts with dark centre discs (img 31) [F] | No donuts or pies; bars, bridges and tables (§5, DS-AP-12) |
| Smiley insight and folder clip-art empty states (img 01, 15) [F] | Text-first empty states with the next action (DS-CMP-23) |
| Blocking full-page spinner; visible query time (img 03, research 02 §4) [F] | Async jobs with progress in place; no blocking overlays (DS-CMP-24, DS-AP-09) |

## 1. Brand

### 1.1 Personality

eRev is **exact, calm and explanatory**. It should feel like a well-kept workpaper: every figure has a source, and nothing on screen competes with the numbers.

| Trait | Means in the interface | Does not mean |
|---|---|---|
| Exact | Fixed decimals, tabular figures, one format per quantity, no silent rounding, every computed number opens Explain | Decimal noise, scientific notation, "about $1M" in data views |
| Calm | Warm neutral paper, one cobalt accent, hairline borders, no decorative motion | Dull or grey-on-grey; low contrast |
| Explanatory | Labels in accounting language (D-02), provenance links, empty states that say what belongs there | Marketing copy, tooltips that restate the label |
| Controlled | Approval state, lock state and evidence visible on the record; destructive actions need a reason | Alarm colours everywhere; modal confirmations for routine actions |

- **DS-BR-01 (guidance).** The numbers are the hero. Chrome (rail, top bar, tabs, borders) recedes to neutral ink; colour appears only for interaction (accent) or state (status set).

### 1.2 Wordmark

- **DS-BR-02.** The product wordmark is the text **eRev**: lowercase `e`, uppercase `R`, lowercase `ev`. It is set in the UI sans (§3) at weight 600, tracking −0.02em, optical size display, colour `--fg-1` (light and dark). It is live text wrapped in an element with `aria-label="eRev"`, not an image.
- **DS-BR-03.** Sizes: 16 px in the top bar; 28 px on the sign-in page; never below 14 px. Clear space on every side equals the height of the lowercase `e`.
- **DS-BR-04.** The **monogram** is a lowercase `e` (weight 600, 15 px) centred in a 24 × 24 px tile, radius `--radius-md`, fill `--accent-solid`, glyph colour `--on-accent`. It is used for the favicon (SVG, generated from the same glyph outline), the collapsed rail header and the PWA icon. It is the only decorative use of the accent colour; every other use marks interaction, selection, focus, progress or unread state (DS-BR-09).
- **DS-BR-05.** "by Chipmunk Robotics" appears only in the About dialog (SF-27; D-61), below the wordmark, in `--fg-3` at the `body-sm` size, so that the dialog reads "eRev by Chipmunk Robotics" (D-75). It never appears in the top bar, sign-in page, emails or exports.
- **DS-BR-06.** Product name in copy: "eRev" in the UI; "eRev Cloud" in the About dialog, documentation and the HTML `<title>` suffix (`<page title> · eRev Cloud`).
- **DS-BR-07.** Forbidden treatments: gradients, outlines, drop shadows, rotation, recolouring outside `--fg-1`/`--fg-inverse`, taglines attached to the wordmark, any leaf, chevron or green device resembling the RightRev mark (D-61), and any RightRev feature name (D-02).

### 1.3 Accent

- **DS-BR-08.** The single accent is **eRev Cobalt**, OKLCH hue 262. It is a deep, saturated blue that sits clearly on the blue side of the blue–violet boundary. [J] Rationale: in a controls product the accent marks "you can act here"; orange, amber, red and green would collide with the status set, and green is RightRev's (D-61). Cobalt on warm paper reads as ink on a ledger.
- **DS-BR-09.** Accent is used only for: primary buttons, links, focus rings, the selection edge and selected-state tints, the active tab indicator, the active rail item indicator, the expanded step indicator of the five-step tracker, determinate progress fills, checked checkboxes and radio buttons, the current import step marker, the unread dot in the notifications panel, and the monogram (DS-BR-04). Accent is never used for data marks, status, headings, icons at rest or decoration.

### 1.4 Voice in the interface

- **DS-BR-10.** Sentence case everywhere (buttons, titles, column headers, menu items). Proper nouns and ISO codes keep their case.
- **DS-BR-11.** Buttons are verbs that name the result: "Submit for approval", "Approve change", "Lock period", "Run journals". Never "OK", "Yes", "Submit" alone, or "Click here".
- **DS-BR-12.** No exclamation marks, no emoji, no humour, no anthropomorphic AI phrasing ("I think"). AI output is labelled "Proposed" (DS-CMP-25).

## 2. Colour

### 2.1 Method

- **DS-COL-01.** Every colour token is defined in OKLCH, a perceptually uniform space. [F] Linear rebuilt its theme in LCH for perceptual uniformity, and Stripe built its colour system in a perceptual space so that contrast steps stay predictable (research 02 §6, [external website reference removed], [external website reference removed]). Every token lies inside the sRGB gamut, so no browser applies gamut mapping and the rendered colour equals the tabulated hex.
- **DS-COL-02.** The sRGB rendering of a token is computed with the OKLab-to-linear-sRGB matrices ([external website reference removed]) followed by sRGB gamma encoding and rounding to 8 bits per channel. Contrast is the WCAG 2.x ratio (L1 + 0.05) / (L2 + 0.05) of relative luminances ([external website reference removed]). The tables in §2.5 and §2.6 were generated by parsing `docs/design/tokens.css` itself; DS-VER-01 repeats the computation in CI.
- **DS-COL-03.** Light and dark themes are at parity: every token exists in both themes with the same name and role, and both themes pass the same contrast table. Components never branch on theme.

### 2.2 Neutrals

- **DS-COL-04.** Neutrals are a warm "paper" family at OKLCH hue 85 with chroma between 0.001 and 0.010. [J] A near-neutral warm grey reads as ledger paper, differs visibly from default cool UI greys (D-62), and keeps the cobalt accent vivid.
- **DS-COL-05.** Surface roles: `--bg-canvas` (page behind panels), `--bg-surface` (panels, grids, rail, top bar), `--bg-raised` (popovers, menus, drawers, modals; lighter than surface in dark), `--bg-subtle` (grid headers, group rows, skeletons, segmented tracks), `--bg-hover`, `--bg-active` (pressed and active neutral items, KPI bar track), `--bg-inverse` (unread badge).
- **DS-COL-06.** Text tiers: `--fg-1` for titles, figures and body text; `--fg-2` for secondary text and icons at rest; `--fg-3` for field labels, captions, placeholders and chart ticks. All three meet 4.5:1 on every surface, hover, active and selected fill in both themes (§2.6). `--fg-disabled` is used only for inactive controls, which WCAG 1.4.3 exempts, and never for information.
- **DS-COL-07.** Border roles: `--border-hairline` (row dividers and region edges; decorative), `--border-default` (panel outlines on canvas, header rules; decorative), `--border-control` (input edges; meets 3:1) and `--rule-total` (totals rules; meets 3:1).

### 2.3 Accent

- **DS-COL-08.** Accent tokens and their only uses (DS-BR-09):

| Token | Use |
|---|---|
| `--accent-solid`, `--accent-solid-hover`, `--accent-solid-active` | Primary button fill; active tab and tracker indicators; determinate progress fill; checked checkbox and radio; current import step marker; unread dot; monogram tile |
| `--on-accent` | Text and icons on accent and danger fills |
| `--accent-fg`, `--accent-fg-hover` | Links in prose and link buttons |
| `--accent-subtle`, `--accent-subtle-hover` | Selected row or list item fill; text selection |
| `--selection-edge` | 2 px selection bar on selected rows, list items and the active rail item |
| `--focus-ring` | Focus ring (DS-A11Y-02) |
| `--accent-border` | Decorative outline of a selected date range in the date picker only |

- **DS-COL-09.** In the dark theme the solid accent stays mid-lightness so white labels keep at least 5.4:1, while links, the selection edge and the focus ring lighten to hold 4.5:1 and 3:1 on dark surfaces.
- **DS-COL-10.** `--danger-solid`, `--danger-solid-hover` and `--danger-solid-active` fill the Danger button (DS-CMP-20) and nothing else.

### 2.4 Status colours

- **DS-COL-20.** The status set is fixed (D-61): **positive** (hue 152), **negative** (hue 27), **warning** (hue 70–85), **info** (hue 230) and **neutral**. Each tone has four tokens: `-fg` (text and icons; at least 4.5:1 on its own `-bg` and on surfaces), `-bg` (chip and banner fill), `-border` (chip and banner edge) and `-solid` (small marks that always sit beside a text label, such as a status dot or a state series in a chart). The mapping from statuses to tones is DS-CMP-19.
- **DS-COL-21.** Status colours never decorate, never encode sign (DS-FMT-30) and never identify categorical series (DS-VIZ-07).
- **DS-COL-22.** Info (hue 230, petrol blue) sits 32° from the accent hue and is never interactive, so the two blues do not compete.
- **DS-COL-23.** AI proposals have no colour of their own; they are marked by a dashed `--proposal-border` edge and the Sparkle icon (DS-CMP-25).
- **DS-COL-24.** `--diff-removed-bg` and `--diff-added-bg` alias `--negative-bg` and `--positive-bg` and are always paired with the markers in DS-CMP-16.

### 2.5 Token values

Generated from `docs/design/tokens.css`. Data-visualization tokens are in §5.

| Token | Light OKLCH | Light sRGB | Dark OKLCH | Dark sRGB |
|---|---|---|---|---|
| `--bg-canvas` | `oklch(0.970 0.003 85)` | `#f6f5f3` | `oklch(0.180 0.004 85)` | `#121110` |
| `--bg-surface` | `oklch(0.996 0.001 85)` | `#fefefd` | `oklch(0.212 0.004 85)` | `#1a1917` |
| `--bg-raised` | `oklch(0.996 0.001 85)` | `#fefefd` | `oklch(0.245 0.005 85)` | `#21201e` |
| `--bg-subtle` | `oklch(0.958 0.004 85)` | `#f2f1ee` | `oklch(0.230 0.005 85)` | `#1e1d1a` |
| `--bg-hover` | `oklch(0.942 0.005 85)` | `#edece8` | `oklch(0.265 0.006 85)` | `#272522` |
| `--bg-active` | `oklch(0.918 0.006 85)` | `#e6e4df` | `oklch(0.300 0.007 85)` | `#2f2e2a` |
| `--bg-inverse` | `oklch(0.235 0.006 85)` | `#1f1e1b` | `oklch(0.940 0.004 85)` | `#ecebe8` |
| `--border-hairline` | `oklch(0.910 0.005 85)` | `#e3e1de` | `oklch(0.295 0.006 85)` | `#2e2c29` |
| `--border-default` | `oklch(0.860 0.007 85)` | `#d3d1cc` | `oklch(0.350 0.007 85)` | `#3c3a36` |
| `--border-control` | `oklch(0.610 0.010 85)` | `#86837d` | `oklch(0.560 0.008 85)` | `#77746f` |
| `--rule-total` | `oklch(0.610 0.010 85)` | `#86837d` | `oklch(0.560 0.008 85)` | `#77746f` |
| `--fg-1` | `oklch(0.205 0.006 85)` | `#181714` | `oklch(0.950 0.004 85)` | `#f0eeeb` |
| `--fg-2` | `oklch(0.415 0.008 85)` | `#4e4b47` | `oklch(0.800 0.007 85)` | `#c0bdb9` |
| `--fg-3` | `oklch(0.500 0.009 85)` | `#66635e` | `oklch(0.705 0.008 85)` | `#a2a09a` |
| `--fg-disabled` | `oklch(0.700 0.006 85)` | `#a09e9a` | `oklch(0.490 0.006 85)` | `#62605d` |
| `--fg-inverse` | `oklch(0.985 0.002 85)` | `#fbfaf9` | `oklch(0.205 0.006 85)` | `#181714` |
| `--accent-solid` | `oklch(0.505 0.165 262)` | `#2b5ec1` | `oklch(0.530 0.160 262)` | `#3566c7` |
| `--accent-solid-hover` | `oklch(0.455 0.150 262)` | `#2451a9` | `oklch(0.490 0.150 262)` | `#2e5bb4` |
| `--accent-solid-active` | `oklch(0.415 0.135 262)` | `#1f4794` | `oklch(0.455 0.140 262)` | `#2852a3` |
| `--accent-fg` | `oklch(0.490 0.160 262)` | `#295ab9` | `oklch(0.770 0.105 262)` | `#8fb4f8` |
| `--accent-fg-hover` | `oklch(0.420 0.140 262)` | `#1e4798` | `oklch(0.830 0.080 262)` | `#abc8fc` |
| `--accent-subtle` | `oklch(0.955 0.020 262)` | `#e9f1fe` | `oklch(0.295 0.045 262)` | `#202c43` |
| `--accent-subtle-hover` | `oklch(0.930 0.030 262)` | `#dde8fd` | `oklch(0.325 0.055 262)` | `#243450` |
| `--accent-border` | `oklch(0.740 0.090 262)` | `#8cabe4` | `oklch(0.520 0.110 262)` | `#4567a8` |
| `--selection-edge` | `oklch(0.505 0.165 262)` | `#2b5ec1` | `oklch(0.720 0.125 262)` | `#79a4f3` |
| `--on-accent` | `oklch(1.000 0.000 0)` | `#ffffff` | `oklch(1.000 0.000 0)` | `#ffffff` |
| `--focus-ring` | `oklch(0.560 0.170 262)` | `#396ed6` | `oklch(0.740 0.120 262)` | `#81aaf7` |
| `--danger-solid` | `oklch(0.515 0.170 27)` | `#b5302c` | `oklch(0.540 0.165 27)` | `#bb3c35` |
| `--danger-solid-hover` | `oklch(0.465 0.155 27)` | `#9e2824` | `oklch(0.495 0.150 27)` | `#a6352f` |
| `--danger-solid-active` | `oklch(0.425 0.140 27)` | `#8b2320` | `oklch(0.455 0.135 27)` | `#93302a` |
| `--positive-fg` | `oklch(0.470 0.100 152)` | `#256a3e` | `oklch(0.790 0.110 152)` | `#82cf98` |
| `--positive-bg` | `oklch(0.960 0.028 152)` | `#e5f8e9` | `oklch(0.275 0.040 152)` | `#182d1e` |
| `--positive-border` | `oklch(0.800 0.070 152)` | `#9dcba8` | `oklch(0.460 0.070 152)` | `#386344` |
| `--positive-solid` | `oklch(0.560 0.120 152)` | `#318850` | `oklch(0.700 0.130 152)` | `#58b575` |
| `--negative-fg` | `oklch(0.500 0.165 27)` | `#ae2e2a` | `oklch(0.790 0.105 27)` | `#f7a096` |
| `--negative-bg` | `oklch(0.962 0.018 27)` | `#ffeeec` | `oklch(0.285 0.050 27)` | `#40201c` |
| `--negative-border` | `oklch(0.800 0.075 27)` | `#eaaca4` | `oklch(0.490 0.110 27)` | `#95443d` |
| `--negative-solid` | `oklch(0.555 0.185 27)` | `#c93531` | `oklch(0.660 0.170 27)` | `#e86156` |
| `--warning-fg` | `oklch(0.500 0.105 70)` | `#895709` | `oklch(0.830 0.115 80)` | `#efbf6c` |
| `--warning-bg` | `oklch(0.965 0.032 85)` | `#fdf2dc` | `oklch(0.285 0.045 80)` | `#36270e` |
| `--warning-border` | `oklch(0.800 0.095 80)` | `#deb775` | `oklch(0.490 0.080 80)` | `#785b25` |
| `--warning-solid` | `oklch(0.740 0.150 75)` | `#e19b1b` | `oklch(0.780 0.140 78)` | `#e8ab3e` |
| `--info-fg` | `oklch(0.490 0.090 230)` | `#166989` | `oklch(0.800 0.080 230)` | `#87c8e8` |
| `--info-bg` | `oklch(0.960 0.020 230)` | `#e5f5fd` | `oklch(0.275 0.035 230)` | `#142b36` |
| `--info-border` | `oklch(0.800 0.050 230)` | `#9dc4d8` | `oklch(0.480 0.060 230)` | `#376479` |
| `--info-solid` | `oklch(0.580 0.110 230)` | `#1785af` | `oklch(0.700 0.100 230)` | `#54aad1` |
| `--neutral-chip-bg` | `oklch(0.942 0.005 85)` | `#edece8` | `oklch(0.275 0.006 85)` | `#292724` |
| `--proposal-border` | `oklch(0.610 0.010 85)` | `#86837d` | `oklch(0.560 0.008 85)` | `#77746f` |

Overlay and elevation tokens (alpha colours, not contrast-checked):

| Token | Light | Dark |
|---|---|---|
| `--scrim` | `oklch(0.205 0.006 85 / 0.32)` | `oklch(0 0 0 / 0.56)` |
| `--elev-popover` | `0 1px 2px oklch(0.205 0.006 85 / 0.06), 0 4px 16px oklch(0.205 0.006 85 / 0.08)` | `0 1px 2px oklch(0 0 0 / 0.30), 0 4px 16px oklch(0 0 0 / 0.40)` |
| `--elev-overlay` | `0 2px 6px oklch(0.205 0.006 85 / 0.06), 0 16px 40px oklch(0.205 0.006 85 / 0.14)` | `0 2px 6px oklch(0 0 0 / 0.30), 0 16px 40px oklch(0 0 0 / 0.55)` |

### 2.6 Contrast table

Requirements: text 4.5:1 (WCAG 2.2 SC 1.4.3); user-interface components and graphical objects 3:1 (SC 1.4.11). Ratios are computed as in DS-COL-02. All 72 required pairs pass in both themes. The lowest text ratios are 4.71 light (`--fg-3` on `--bg-active`, C22) and 4.77 dark (`--fg-3` on `--accent-subtle-hover`, C24). The lowest UI ratios are 3.35 light (`--border-control` on `--bg-subtle`, C57) and 3.19 dark (`--danger-solid` on `--bg-surface`, C68).

| # | Foreground | Background | Use | Required | Light | Dark | Result |
|---|---|---|---|---|---|---|---|
| C01 | `--fg-1` | `--bg-canvas` | text | 4.5:1 | 16.45 | 16.29 | Pass |
| C02 | `--fg-1` | `--bg-surface` | text | 4.5:1 | 17.76 | 15.17 | Pass |
| C03 | `--fg-1` | `--bg-raised` | text | 4.5:1 | 17.76 | 14.06 | Pass |
| C04 | `--fg-1` | `--bg-subtle` | text | 4.5:1 | 15.87 | 14.56 | Pass |
| C05 | `--fg-1` | `--bg-hover` | text | 4.5:1 | 15.16 | 13.20 | Pass |
| C06 | `--fg-1` | `--bg-active` | text | 4.5:1 | 14.11 | 11.74 | Pass |
| C07 | `--fg-1` | `--accent-subtle` | text | 4.5:1 | 15.77 | 12.07 | Pass |
| C08 | `--fg-1` | `--accent-subtle-hover` | text | 4.5:1 | 14.54 | 10.78 | Pass |
| C09 | `--fg-2` | `--bg-canvas` | text | 4.5:1 | 7.96 | 10.08 | Pass |
| C10 | `--fg-2` | `--bg-surface` | text | 4.5:1 | 8.59 | 9.39 | Pass |
| C11 | `--fg-2` | `--bg-raised` | text | 4.5:1 | 8.59 | 8.70 | Pass |
| C12 | `--fg-2` | `--bg-subtle` | text | 4.5:1 | 7.68 | 9.01 | Pass |
| C13 | `--fg-2` | `--bg-hover` | text | 4.5:1 | 7.34 | 8.17 | Pass |
| C14 | `--fg-2` | `--bg-active` | text | 4.5:1 | 6.83 | 7.26 | Pass |
| C15 | `--fg-2` | `--accent-subtle` | text | 4.5:1 | 7.63 | 7.47 | Pass |
| C16 | `--fg-2` | `--accent-subtle-hover` | text | 4.5:1 | 7.04 | 6.67 | Pass |
| C17 | `--fg-3` | `--bg-canvas` | text | 4.5:1 | 5.49 | 7.21 | Pass |
| C18 | `--fg-3` | `--bg-surface` | text | 4.5:1 | 5.93 | 6.72 | Pass |
| C19 | `--fg-3` | `--bg-raised` | text | 4.5:1 | 5.93 | 6.23 | Pass |
| C20 | `--fg-3` | `--bg-subtle` | text | 4.5:1 | 5.29 | 6.45 | Pass |
| C21 | `--fg-3` | `--bg-hover` | text | 4.5:1 | 5.06 | 5.85 | Pass |
| C22 | `--fg-3` | `--bg-active` | text | 4.5:1 | 4.71 | 5.20 | Pass |
| C23 | `--fg-3` | `--accent-subtle` | text | 4.5:1 | 5.26 | 5.34 | Pass |
| C24 | `--fg-3` | `--accent-subtle-hover` | text | 4.5:1 | 4.85 | 4.77 | Pass |
| C25 | `--fg-inverse` | `--bg-inverse` | text | 4.5:1 | 15.99 | 15.04 | Pass |
| C26 | `--accent-fg` | `--bg-canvas` | text (link) | 4.5:1 | 5.92 | 9.03 | Pass |
| C27 | `--accent-fg` | `--bg-surface` | text (link) | 4.5:1 | 6.39 | 8.41 | Pass |
| C28 | `--accent-fg` | `--bg-raised` | text (link) | 4.5:1 | 6.39 | 7.79 | Pass |
| C29 | `--accent-fg` | `--bg-subtle` | text (link) | 4.5:1 | 5.71 | 8.07 | Pass |
| C30 | `--accent-fg` | `--bg-hover` | text (link) | 4.5:1 | 5.45 | 7.32 | Pass |
| C31 | `--accent-fg` | `--accent-subtle` | text (link) | 4.5:1 | 5.67 | 6.69 | Pass |
| C32 | `--accent-fg-hover` | `--bg-surface` | text (link hover) | 4.5:1 | 8.63 | 10.37 | Pass |
| C33 | `--on-accent` | `--accent-solid` | text (button) | 4.5:1 | 6.05 | 5.42 | Pass |
| C34 | `--on-accent` | `--accent-solid-hover` | text (button) | 4.5:1 | 7.43 | 6.42 | Pass |
| C35 | `--on-accent` | `--accent-solid-active` | text (button) | 4.5:1 | 8.80 | 7.43 | Pass |
| C36 | `--on-accent` | `--danger-solid` | text (button) | 4.5:1 | 6.13 | 5.51 | Pass |
| C37 | `--on-accent` | `--danger-solid-hover` | text (button) | 4.5:1 | 7.55 | 6.62 | Pass |
| C38 | `--on-accent` | `--danger-solid-active` | text (button) | 4.5:1 | 8.90 | 7.79 | Pass |
| C39 | `--positive-fg` | `--positive-bg` | text (chip, banner) | 4.5:1 | 5.90 | 7.91 | Pass |
| C40 | `--positive-fg` | `--bg-surface` | text (message) | 4.5:1 | 6.48 | 9.48 | Pass |
| C41 | `--positive-fg` | `--bg-canvas` | text (message) | 4.5:1 | 6.00 | 10.17 | Pass |
| C42 | `--negative-fg` | `--negative-bg` | text (chip, banner) | 4.5:1 | 5.80 | 7.23 | Pass |
| C43 | `--negative-fg` | `--bg-surface` | text (message) | 4.5:1 | 6.45 | 8.72 | Pass |
| C44 | `--negative-fg` | `--bg-canvas` | text (message) | 4.5:1 | 5.98 | 9.36 | Pass |
| C45 | `--warning-fg` | `--warning-bg` | text (chip, banner) | 4.5:1 | 5.51 | 8.49 | Pass |
| C46 | `--warning-fg` | `--bg-surface` | text (message) | 4.5:1 | 6.07 | 10.32 | Pass |
| C47 | `--warning-fg` | `--bg-canvas` | text (message) | 4.5:1 | 5.62 | 11.08 | Pass |
| C48 | `--info-fg` | `--info-bg` | text (chip, banner) | 4.5:1 | 5.51 | 8.02 | Pass |
| C49 | `--info-fg` | `--bg-surface` | text (message) | 4.5:1 | 6.09 | 9.58 | Pass |
| C50 | `--info-fg` | `--bg-canvas` | text (message) | 4.5:1 | 5.64 | 10.29 | Pass |
| C51 | `--fg-2` | `--neutral-chip-bg` | text (chip) | 4.5:1 | 7.34 | 7.96 | Pass |
| C52 | `--fg-1` | `--diff-removed-bg` | text (diff row) | 4.5:1 | 15.96 | 12.58 | Pass |
| C53 | `--fg-1` | `--diff-added-bg` | text (diff row) | 4.5:1 | 16.16 | 12.66 | Pass |
| C54 | `--fg-2` | `--diff-removed-bg` | text (diff old value) | 4.5:1 | 7.72 | 7.78 | Pass |
| C55 | `--border-control` | `--bg-canvas` | UI (control edge) | 3:1 | 3.47 | 4.05 | Pass |
| C56 | `--border-control` | `--bg-surface` | UI (control edge) | 3:1 | 3.75 | 3.77 | Pass |
| C57 | `--border-control` | `--bg-subtle` | UI (control edge) | 3:1 | 3.35 | 3.62 | Pass |
| C58 | `--focus-ring` | `--bg-canvas` | UI (focus ring) | 3:1 | 4.41 | 8.11 | Pass |
| C59 | `--focus-ring` | `--bg-surface` | UI (focus ring) | 3:1 | 4.76 | 7.55 | Pass |
| C60 | `--focus-ring` | `--bg-raised` | UI (focus ring) | 3:1 | 4.76 | 7.00 | Pass |
| C61 | `--focus-ring` | `--bg-subtle` | UI (focus ring) | 3:1 | 4.25 | 7.25 | Pass |
| C62 | `--focus-ring` | `--bg-hover` | UI (focus ring) | 3:1 | 4.06 | 6.57 | Pass |
| C63 | `--focus-ring` | `--accent-subtle` | UI (focus ring) | 3:1 | 4.22 | 6.01 | Pass |
| C64 | `--selection-edge` | `--bg-surface` | UI (selection edge) | 3:1 | 5.99 | 7.04 | Pass |
| C65 | `--selection-edge` | `--accent-subtle` | UI (selection edge) | 3:1 | 5.32 | 5.60 | Pass |
| C66 | `--accent-solid` | `--bg-surface` | UI (button, tab indicator) | 3:1 | 5.99 | 3.24 | Pass |
| C67 | `--accent-solid` | `--bg-canvas` | UI (button, tab indicator) | 3:1 | 5.55 | 3.48 | Pass |
| C68 | `--danger-solid` | `--bg-surface` | UI (button) | 3:1 | 6.08 | 3.19 | Pass |
| C69 | `--proposal-border` | `--bg-surface` | UI (proposal edge) | 3:1 | 3.75 | 3.77 | Pass |
| C70 | `--rule-total` | `--bg-surface` | UI (totals rule) | 3:1 | 3.75 | 3.77 | Pass |
| C71 | `--negative-fg` | `--bg-surface` | UI (invalid field edge) | 3:1 | 6.45 | 8.72 | Pass |
| C72 | `--viz-kpi-bar` | `--viz-kpi-track` | UI (KPI proportion bar) | 3:1 | 6.83 | 7.26 | Pass |
| C73 | `--positive-solid` | `--bg-surface` | mark with label | — | 4.36 | 6.93 | Not required |
| C74 | `--negative-solid` | `--bg-surface` | mark with label | — | 5.15 | 5.25 | Not required |
| C75 | `--info-solid` | `--bg-surface` | mark with label | — | 4.15 | 6.73 | Not required |
| C76 | `--warning-solid` | `--bg-surface` | mark with label | — | 2.34 | 8.64 | Not required |
| C77 | `--fg-disabled` | `--bg-surface` | exempt (inactive) | — | 2.65 | 2.80 | Not required |
| C78 | `--border-hairline` | `--bg-surface` | decorative | — | 1.29 | 1.26 | Not required |
| C79 | `--border-default` | `--bg-surface` | decorative | — | 1.51 | 1.55 | Not required |
| C80 | `--accent-border` | `--accent-subtle` | decorative | — | 2.04 | 2.50 | Not required |
| C81 | `--danger-solid-hover` | `--bg-surface` | button fill (label identifies it) | — | 7.48 | 2.65 | Not required |

Notes on the "Not required" rows:
- C73–C76: `-solid` status marks always have an adjacent text label, so the mark is not the only identifier. In light mode `--warning-solid` (2.34:1) must therefore never appear without its label; warning icons use `--warning-fg` instead.
- C77: inactive controls are exempt from SC 1.4.3 and SC 1.4.11; `aria-disabled` and a stated reason carry the meaning (DS-CMP-20).
- C78–C80: hairlines and decorative outlines separate regions that are already identified by content and spacing.
- C81: the dark Danger hover fill (2.65:1) is identified by its label (C37, 6.62:1), not by its boundary.

### 2.7 Usage rules

- **DS-COL-25.** Components use tokens as delivered. Opacity modifiers on colour utilities (`bg-accent-solid/20`) and `color-mix()` are not used; the only translucent colours are `--scrim` and the elevation shadows **[lint]**.
- **DS-COL-26.** Themes switch only through tokens. Tailwind `dark:` variants are not used **[lint]**.
- **DS-COL-27.** Colour contract for common surfaces:

| Element | Tokens |
|---|---|
| Page background | `--bg-canvas` |
| Panel, grid, rail, top bar | `--bg-surface`, edge `--border-hairline` |
| Popover, menu, drawer, modal | `--bg-raised`, edge `--border-default`, shadow per DS-ELV-03 |
| Grid header, group row | `--bg-subtle`, bottom edge `--border-default` |
| Row hover / pressed | `--bg-hover` / `--bg-active` |
| Selected row or list item | `--accent-subtle` fill plus `--selection-edge` bar |
| Input | `--bg-surface`, edge `--border-control`, focus edge `--accent-solid` plus `--focus-ring` |
| Primary button | `--accent-solid` family, label `--on-accent` |
| Link in prose / in a grid | `--accent-fg` / `--fg-1` with dotted underline in `--border-control` |
| Status chip | `--<tone>-bg`, `--<tone>-fg`, `--<tone>-border` |
| Totals rule | `--rule-total` |

## 3. Typography

### 3.1 Families

| Id | Role | Family | Licence | Source |
|---|---|---|---|---|
| DS-TYP-01 | UI sans: all interface text and all numbers | **Inter** 4.x variable (upright and italic), axes `wght` 100–900 and `opsz` (text to display) | SIL Open Font License 1.1 [F] ([external website reference removed]) | Vendored woff2 files with the licence text; no CDN |
| DS-TYP-02 | Mono: identifiers, hashes, GL account codes, formulas, code | **JetBrains Mono** variable (upright) | SIL Open Font License 1.1 [F] ([external website reference removed]) | Vendored woff2 files with the licence text; no CDN |

- **DS-TYP-03.** [J] Why Inter: it has tabular figures (`tnum`), case-sensitive forms (`case`), a slashed zero (`zero`), disambiguation variants (`cv05`, `cv08`) and an optical-size axis in one OFL family [F] ([external website reference removed]). Those features carry the finance-grade numerals D-60 requires. The personality comes from the display optical size, tight tracking on titles, the warm neutrals and the restraint of the layout, not from a novelty face.
- **DS-TYP-04.** [J] Why JetBrains Mono: large lowercase x-height, and "the zero has a dot inside. The letter 'O' does not." [F] ([external website reference removed]). Contract ids, obligation keys, hashes and account codes stay legible at 12 px.
- **DS-TYP-05.** Font files are vendored into the web app with `OFL.txt` for each family and loaded with `@font-face` (`font-display: swap`). The upright Inter file is preloaded. No request to Google Fonts or any CDN (no network in tests, and no third-party font requests from a finance app). The `NOTICE` file lists both families and the OFL 1.1. [J] Vendoring also avoids the Vite `node_modules` symlink font-serving failure seen in worktrees [A].
- **DS-TYP-06.** Font stacks (defined in `tokens.css`):
  - `--font-sans: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
  - `--font-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace`
- **DS-TYP-07.** `font-optical-sizing: auto` on `html`, so Inter selects its display cut for large titles automatically. Code ligatures in JetBrains Mono are disabled (`font-variant-ligatures: none`) because ids are data, not code.

### 3.2 Numerals

- **DS-TYP-08.** Every element that renders an amount, quantity, rate, percentage, count in a table, date in a table, period label in a table, or axis tick uses `font-variant-numeric: tabular-nums lining-nums` (the `num` utility defined in `tokens.css`; money cells use `num-money`). Proportional figures are allowed only in running prose.
- **DS-TYP-09.** Money cells additionally enable `font-feature-settings: "case" 1`, so the parentheses of negative amounts under the parentheses style (DS-FMT-06) centre on the figures.
- **DS-TYP-10.** Identifiers (contract number, obligation key, invoice number, import batch id, GL account code, hash prefixes, API ids) render in `--font-mono` at the mono size matching the surrounding text size (§3.3), left-aligned.

### 3.3 Type scale

Sizes are in px at 100% zoom; the CSS tokens are rem with a 16 px root. Line heights are absolute px so rows stay on the 4 px grid.

| Id | Token | Size / line height | Weight | Tracking | Use |
|---|---|---|---|---|---|
| DS-TYP-11 | `--text-title-lg` | 22 / 28 | 600 | −0.015em | Page title or record title (one per route, `h1`) |
| DS-TYP-12 | `--text-title-md` | 17 / 24 | 600 | −0.01em | Drawer and modal titles, report titles, the obligation header inside a detail pane (`h2`) |
| DS-TYP-13 | `--text-title-sm` | 14 / 20 | 600 | −0.005em | Panel and section titles (`h3`) |
| DS-TYP-14 | `--text-body` | 14 / 20 | 400 | 0 | Default UI text, form inputs, comfortable grid cells |
| DS-TYP-15 | `--text-body-sm` | 13 / 18 | 400 | 0 | Compact grid cells, secondary text, help text, tab labels (weight 500) |
| DS-TYP-16 | `--text-caption` | 12 / 16 | 500 | 0.01em | Field labels above values, KPI labels, chip text, axis ticks, timestamps |
| DS-TYP-17 | `--text-kpi` | 20 / 26 (comfortable), 18 / 24 (compact) | 600 | −0.01em | KPI strip values, tabular figures |
| DS-TYP-18 | `--text-mono` | 13 / 18 | 450 | 0 | Identifiers beside `body` text |
| DS-TYP-19 | `--text-mono-sm` | 12 / 16 | 450 | 0 | Identifiers in compact grids and chips |

- **DS-TYP-20.** Weights in use: 400, 450 (mono only), 500 and 600. Weights 100–300 and 700–900 are not used.
- **DS-TYP-21.** Minimum rendered text size is 12 px, including chart tick labels and chip text. [J] research 02 §5 identifies 11 px grey labels as a weakness of the reference product.
- **DS-TYP-22.** No uppercase text transforms except ISO currency and country codes, which are uppercase by nature. No letter-spaced uppercase "eyebrow" labels.
- **DS-TYP-23.** Heading levels follow document structure: one `h1` per route (the page or record title); `h2` for major regions, drawers and modals; `h3` for panels. Visual size never changes the semantic level.
- **DS-TYP-24.** Line length for prose (help text, Explain narrative, empty states) is capped at 72ch.

## 4. Space, layout, density, radii, elevation, motion, icons

### 4.1 Spacing and layout

- **DS-SP-01.** The spacing grid is 4 px. `tokens.css` keeps Tailwind's spacing multiplier `--spacing: 0.25rem`, so `p-2` is 8 px. Allowed multipliers: 0, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 16 (0 to 64 px). Other multipliers (for example `p-7`, `gap-9`, `mt-11`) are flagged **[lint]** as warnings.
- **DS-SP-02.** Arbitrary spacing and sizing values in class names (`p-[13px]`, `w-[317px]`) are errors **[lint]**. The only exceptions are `var()` references to layout tokens, for example `w-[var(--rail-w-expanded)]`.
- **DS-SP-03.** Layout dimensions (tokens in `tokens.css`):

| Token | Value | Use |
|---|---|---|
| `--topbar-h` | 48 px | App top bar (both densities) |
| `--rail-w-collapsed` | 52 px | Icon rail, collapsed |
| `--rail-w-expanded` | 232 px | Icon rail with labels |
| `--master-w` | 360 px (resizable 280–480) | Master list in master-detail layouts |
| `--explain-w` | 440 px | Explain panel (docked at ≥ 1440 px, overlay below) |
| `--drawer-w` | 480 px | Standard drawer |
| `--drawer-w-wide` | 720 px | Wide drawer (forms with grids) |
| `--modal-w-sm` | 440 px | Confirmation modal |
| `--modal-w-md` | 600 px | Form modal |
| `--modal-w-lg` | 960 px | Approval diff modal, import mapping |
| `--content-max-form` | 880 px | Settings and long forms (left-aligned, never centred) |

- **DS-SP-04.** Breakpoints (`--breakpoint-*` in `@theme`): `md` 1024 px, `lg` 1280 px, `xl` 1440 px, `2xl` 1920 px. The reference design width is 1440 px. The minimum supported width for G8 journeys is 1024 px.

| Viewport | Rail | Master-detail | Explain panel |
|---|---|---|---|
| ≥ 1440 px | User preference (default expanded) | Side by side | Docked; content reflows |
| 1280–1439 px | User preference (default collapsed) | Side by side | Overlay drawer, non-modal |
| 1024–1279 px | Collapsed | Side by side; master 300 px | Overlay drawer, non-modal |
| < 1024 px (not a G8 target) | Hidden behind a menu button | Stacked (list, then detail with a back link) | Full-width overlay |

- **DS-SP-05.** Data pages (workbench, grids, reports, close cockpit) are full-bleed with a `--gutter` page margin and no max width. Forms and settings use `--content-max-form`, aligned to the start edge. Page content is never centred horizontally inside the app shell (D-62).
- **DS-SP-06.** Vertical rhythm: `--stack-gap` between page regions; 12 px (comfortable) or 8 px (compact) between elements inside a panel; 4 px between a label and its value.
- **DS-SP-07.** A page never scrolls horizontally. Wide grids scroll inside their own viewport with a sticky first column (DS-CMP-10).

### 4.2 Density

- **DS-DEN-01.** Density is the attribute `data-density` on `<html>`: `comfortable` (default) or `compact`. It is a per-user preference stored server-side, mirrored to `localStorage` key `erev.density` and applied before first paint by the external blocking script `/theme-init.js` (`frontend/public/theme-init.js`, DG-FE-13), which applies `data-theme` from `erev.theme` in the same way. There is no inline script (DG-FE-12, REQ-SEC-004), and there is no layout shift on load. It can be changed from the user menu and from Cmd-K ("Density: compact").
- **DS-DEN-02.** Density changes only the tokens in this table. Colours, radii, title sizes and icon sizes do not change.

| Token | Comfortable | Compact | Used by |
|---|---|---|---|
| `--row-h` | 36 px | 28 px | Grid body rows, list rows, menu items |
| `--header-row-h` | 36 px | 32 px | Grid header rows |
| `--control-h` | 32 px | 28 px | Buttons, inputs, selects |
| `--control-h-sm` | 28 px | 24 px | Grid-row icon buttons, chips with actions, segmented filters |
| `--cell-px` | 12 px | 8 px | Horizontal cell padding |
| `--gutter` | 24 px | 16 px | Page margin |
| `--panel-pad` | 16 px | 12 px | Panel and drawer padding |
| `--stack-gap` | 24 px | 16 px | Gap between page regions |
| `--tab-h` | 40 px | 36 px | Tab bar height |
| `--grid-text` / `--grid-leading` | 14 px / 20 px | 13 px / 18 px | Grid cell text |
| `--kpi-text` / `--kpi-leading` | 20 px / 26 px | 18 px / 24 px | KPI strip values |

- **DS-DEN-03.** Every pointer target is at least 24 × 24 CSS px in both densities (WCAG 2.2 SC 2.5.8 Target Size (Minimum), AA [F] ([external website reference removed])) **[test]**.
- **DS-DEN-04.** Density never hides columns, truncates amounts or removes information. Compact mode shows the same content in less space.

### 4.3 Radii

| Id | Token | Value | Use |
|---|---|---|---|
| DS-RAD-01 | `--radius-sm` | 4 px | Status chips, checkboxes, tooltips, inline code, keyboard hints |
| DS-RAD-02 | `--radius-md` | 6 px | Buttons, inputs, selects, segmented controls, menu items, monogram tile |
| DS-RAD-03 | `--radius-lg` | 8 px | Panels, popovers, menus, toasts, command palette |
| DS-RAD-04 | `--radius-xl` | 12 px | Modals |
| DS-RAD-05 | `--radius-full` | 9999 px | Avatars, radio buttons, switch tracks, progress bar ends, 8 px status dots |

- **DS-RAD-06.** Drawers are flush to the viewport edge (radius 0). Grids inside a panel have radius 0; the panel clips its content (`overflow: hidden` on the panel, never on the scroll viewport's sticky ancestors).
- **DS-RAD-07.** Tailwind's radius namespace is reset in `tokens.css`, so only `rounded-sm`, `rounded-md`, `rounded-lg`, `rounded-xl`, `rounded-full` and `rounded-none` exist. Pill-shaped containers and cards are not used.

### 4.4 Borders and elevation

- **DS-ELV-01.** Regions are separated by 1 px hairlines, not shadows. Panels, the rail and the top bar sit on `--bg-surface` with a `--border-hairline` edge. Grid row dividers use `--border-hairline`. Grid header bottom edges and panel outlines on `--bg-canvas` use `--border-default`. There is no zebra striping.
- **DS-ELV-02.** Accounting rules for totals: a totals row has a 1 px top rule in `--rule-total`. The grand total of a report or rollforward has a 1 px top rule and a 3 px double bottom rule (`border-bottom: 3px double var(--rule-total)`). [J] This is the financial-statement convention accountants read as "sum" and "final sum".
- **DS-ELV-03.** Elevation levels:

| Level | Surface token | Edge | Shadow | Examples |
|---|---|---|---|---|
| E0 | `--bg-canvas` | none | none | Page background behind panels |
| E1 | `--bg-surface` | `--border-hairline` | none | Panels, grids, record header, rail, top bar |
| E2 | `--bg-raised` | `--border-default` | `--shadow-popover` | Menus, popovers, tooltips, date pickers, command palette, toasts |
| E3 | `--bg-raised` | `--border-default` | `--shadow-overlay` | Modals, drawers (with `--scrim` when modal) |

- **DS-ELV-04.** Only two shadow tokens exist: `--shadow-popover` and `--shadow-overlay`. Tailwind's `--shadow-*`, `--inset-shadow-*` and `--drop-shadow-*` namespaces are reset so that `shadow-popover` and `shadow-overlay` are the only shadow utilities **[lint]**. No glow, no inner shadow, no `backdrop-filter` blur (no glass, D-61) **[lint]**.
- **DS-ELV-05.** In the dark theme, raised layers (E2, E3) use the lighter `--bg-raised` so elevation stays visible where shadows do not.
- **DS-ELV-06.** Stacking order uses z-index tokens only: `--z-sticky` 10 (sticky grid headers and columns), `--z-rail` 20, `--z-topbar` 30, `--z-drawer` 40, `--z-modal` 50, `--z-popover` 60, `--z-toast` 70, `--z-tooltip` 80. Arbitrary `z-[n]` values are errors **[lint]**.

### 4.5 Motion

- **DS-MOT-01.** Motion tokens: `--duration-fade` 90 ms (opacity-only transitions), `--duration-fast` 90 ms, `--duration-base` 150 ms, `--duration-slow` 220 ms; `--ease-standard` `cubic-bezier(0.2, 0, 0, 1)` (enter and state changes); `--ease-exit` `cubic-bezier(0.4, 0, 1, 1)`. Exits run at the next shorter duration.

| Motion | Duration | Property |
|---|---|---|
| Hover, press, focus colour changes | fast | `background-color`, `border-color`, `color` |
| Tooltip, popover, menu open | base | `opacity`, `transform: translateY(4px → 0)` |
| Tab indicator moving between tabs | base | `transform` |
| Accordion and row-group expand | base | `grid-template-rows` or height |
| Drawer open | slow | `transform: translateX(100% → 0)` |
| Modal open | base | `opacity`, `transform: scale(0.98 → 1)` |
| Toast enter | base | `opacity`, `transform: translateY(8px → 0)` |
| Indeterminate progress | 1200 ms linear loop | `transform` of the bar segment (the only looping animation) |

- **DS-MOT-02.** Forbidden: animating numbers through intermediate values (count-up), chart entry animations (the chart wrapper sets Recharts `isAnimationActive={false}`), springs and overshoot, parallax, route transitions, animated gradients and shimmering skeletons. Skeletons are static blocks in `--bg-subtle`.
- **DS-MOT-03.** Under `@media (prefers-reduced-motion: reduce)` `--duration-fast`, `--duration-base` and `--duration-slow` fall to 0 ms, which removes every movement, while opacity transitions keep `--duration-fade` (90 ms). Components therefore transition `opacity` with `--duration-fade` and movement with the other durations. The indeterminate progress bar becomes a static full-width bar in `--accent-solid` at 40% opacity with the text "In progress" **[test]**.

### 4.6 Iconography

- **DS-ICO-01.** The only icon library is **Phosphor Icons** (`@phosphor-icons/react`), MIT licence [F] ([external website reference removed]). [J] Rationale: six weights let the active rail item switch to `fill` without a second icon set, and the family is visibly different from the Lucide-style line icons of the reference product (research 02 §3.5). Its licence goes in `NOTICE`.
- **DS-ICO-02.** All Phosphor imports go through one icon registry module that re-exports only the icons listed in DS-ICO-07. Components import icons from the registry, never from the package **[lint]**. [J] The package README warns that importing from the main module can make bundlers "eagerly transpile all 9,000+ modules" [F] ([external website reference removed]); one registry keeps the import surface small and the icon vocabulary closed.
- **DS-ICO-03.** Weights: `regular` everywhere; `fill` only for the active rail item. `thin`, `light`, `bold` and `duotone` are not used.
- **DS-ICO-04.** Sizes: 12 px (inside status chips, sort indicators), 16 px (default: buttons, inputs, grids, menus, toasts), 20 px (rail, top bar). No other sizes. The app root sets `IconContext.Provider value={{ size: 16, weight: "regular" }}`.
- **DS-ICO-05.** Icons use `currentColor` and inherit text colour: at rest `--fg-2` (or `--fg-3` in secondary positions), tone icons `--<tone>-fg`. Icons are never accent-coloured at rest.
- **DS-ICO-06.** Decorative icons have `aria-hidden="true"`. Icon-only buttons have an `aria-label` and a tooltip. An icon never carries meaning alone.
- **DS-ICO-07.** Canonical icon map (every name verified against the Phosphor core index, 1,530 icons, 2026-09-12 [F] ([external website reference removed])). Navigation icons are listed in DS-CMP-02.

| Concept | Icon | Concept | Icon |
|---|---|---|---|
| Search | MagnifyingGlass | Positive state | CheckCircle |
| Command hint | Command | Negative state | XCircle |
| Notifications | Bell | Warning state | WarningCircle |
| Help | Question | Info | Info |
| Explain a figure | Function | Pending approval | HourglassMedium |
| AI proposal | Sparkle | Stale | ClockCounterClockwise |
| Entity | Buildings | On hold | PauseCircle |
| Period | CalendarBlank | Void | Prohibit |
| Book | Books | Draft | PencilSimpleLine |
| Filter | Funnel | Locked period | LockSimple |
| Column chooser | Columns | Open period | LockSimpleOpen |
| Export | DownloadSimple | Queued | CircleDashed |
| Import, upload | UploadSimple | Running | CircleHalf |
| Refresh, recompute | ArrowsClockwise | Step not started | Circle |
| Open in new tab, exported | ArrowSquareOut | Difference | Equals |
| Copy | CopySimple | Withdraw | ArrowUUpLeft |
| More actions | DotsThree | Audit chain verified | ShieldCheck |
| Close | X | Attachment | Paperclip |
| Expand, collapse | CaretRight, CaretDown | Comment | ChatText |
| Back | CaretLeft | Keyboard shortcuts | Keyboard |
| Sort | CaretUp, CaretDown | Theme | Sun, Moon |
| Add | Plus | Sign out | SignOut |
| Remove | Minus | Toggle rail | SidebarSimple |
| Delete draft item | Trash | Group rows | TreeStructure |
| Edit | PencilSimple | Table view | Table |
| Invoice | Receipt | Chart view | ChartBar |
| Journal | Notebook | Checklist | ListChecks |

- **DS-ICO-08.** When `dir="rtl"`, these icons receive `mirrored`: CaretRight, CaretLeft, ArrowSquareOut, ArrowUUpLeft, SidebarSimple, TreeStructure. Other icons are not mirrored.

## 5. Data visualization

### 5.1 Principles

- **DS-VIZ-00.** Charts support tables; they never replace them. Every chart has a Table view with identical figures, every mark drills down to its records (D-60), all figures follow §6, and nothing animates (DS-MOT-02).
- Chart forms in 1.0: stacked columns by period (revenue waterfall, CH-01), bridges (rollforwards, CH-02), horizontal stacked bars (RPO time bands, CH-03), sparklines (CH-04), KPI proportion bars (CH-05), plain bars for disaggregation (category bars, CH-06; rev 1.12), and lines only for rates and percentages over time. Pie, donut, radial, 3D and dual-axis charts are not used (DS-AP-12).

### 5.2 Palettes and validation

- **DS-VIZ-01. Categorical palette.** Seven hue families in a fixed order, plus a neutral "Other". Slot 1 is cobalt, which relates the charts to the brand without reusing the accent tokens.

| Slot | Hue family | Light sRGB | Light contrast on `--bg-surface` | Dark sRGB | Dark contrast on `--bg-surface` |
|---|---|---|---|---|---|
| `--viz-1` | cobalt | `#377ee3` | 3.96 | `#3d84ea` | 4.76 |
| `--viz-2` | magenta | `#c84c8b` | 4.28 | `#cf5291` | 4.41 |
| `--viz-3` | orange | `#c85d00` | 4.14 | `#d16100` | 4.54 |
| `--viz-4` | teal | `#009e92` | 3.30 | `#00a093` | 5.40 |
| `--viz-5` | gold | `#9f7b00` | 3.92 | `#a68000` | 4.78 |
| `--viz-6` | violet | `#9163d5` | 4.20 | `#9769dc` | 4.49 |
| `--viz-7` | green | `#36982d` | 3.66 | `#3d9e34` | 5.14 |
| `--viz-other` | neutral | `#888681` | 3.60 | `#82807c` | 4.46 |

- **DS-VIZ-02. Validation method.** Colour-vision deficiency is simulated with the Machado, Oliveira and Fernandes (2009) model at severity 1.0 for protanopia, deuteranopia and tritanopia ([external website reference removed]). Colour difference is Euclidean distance in OKLab × 100. Gates: OKLCH lightness within the mode's band, chroma at least 0.10, adjacent-pair ΔE at least 8 under protanopia and deuteranopia, adjacent-pair ΔE at least 15 under normal vision, and marks at least 3:1 against `--bg-surface`. Tritanopia is reported but not gated. The slot order and lightness per slot were found by exhaustive search over slot orders (slot 1 fixed) and coordinate search over lightness, maximising passing gates, then marks at 3:1, then closeness to a common lightness (scratch evidence in `.scratch/design-des-system/`). Results, recomputed from `tokens.css`:

| Check | Threshold | Light | Dark | Result |
|---|---|---|---|---|
| OKLCH lightness band | light 0.43–0.77, dark 0.48–0.67 | 0.600–0.630 | 0.620–0.635 | Pass |
| Chroma floor | C ≥ 0.10 | min 0.111 | min 0.112 | Pass |
| Adjacent pairs, protanopia and deuteranopia ΔE | ≥ 8 | 13.8 | 14.1 | Pass |
| Adjacent pairs, normal vision ΔE | ≥ 15 | 16.0 | 16.2 | Pass |
| Adjacent pairs, tritanopia ΔE (reported, not gated) | — | 3.1 | 3.4 | Reported |
| Slots 1–3 all pairs, CVD ΔE / normal ΔE | ≥ 8 / ≥ 15 | 13.8 / 16.0 | 14.2 / 16.2 | Pass |
| `--viz-other` vs slot 7, CVD ΔE / normal ΔE | ≥ 8 / ≥ 15 | 9.0 / 16.7 | 9.2 / 16.8 | Pass |
| Marks vs surface | ≥ 3:1 | min 3.30 | min 4.41 | Pass |
| Nearest status colour to any categorical slot, normal ΔE | informational | 6.9 | 7.7 | Mitigated by DS-VIZ-07 |

- **DS-VIZ-03. Series cap and assignment.** Stacked bars, grouped bars and lines carry at most 7 named series. Additional categories fold into "Other" (`--viz-other`, always last). Scatter plots and small multiples, where any two series can touch, carry at most 3 series (slots 1–3 pass the all-pairs gates). Slots are assigned in order without skipping, never by value. Categories are ordered by descending total for the chart's range, and the same category keeps the same slot in every chart on a page. Rev 1.12: a chart whose API states no figure for the remainder folds nothing, because the browser adds no money up (DS-FMT-02) — DS-CH-06 leaves more than seven categories to its Table view.
- **DS-VIZ-04. Sequential ramp.** Nine cobalt steps (hue 258) for magnitude (heat grids). Lightness is monotone with a minimum step of 0.068. In the light theme step 1 is lightest; in the dark theme step 1 is darkest, so low magnitudes recede into the surface in both themes.

| Step | Light sRGB | Light L | Light contrast | Dark sRGB | Dark L | Dark contrast |
|---|---|---|---|---|---|---|
| `--viz-seq-1` | `#e8f1fe` | 0.955 | 1.13 | `#1e2e47` | 0.300 | 1.29 |
| `--viz-seq-2` | `#c7dbf7` | 0.885 | 1.40 | `#254067` | 0.370 | 1.68 |
| `--viz-seq-3` | `#a5c5f3` | 0.816 | 1.75 | `#2d5289` | 0.439 | 2.24 |
| `--viz-seq-4` | `#83aeef` | 0.745 | 2.25 | `#3565ac` | 0.509 | 3.02 |
| `--viz-seq-5` | `#6297e6` | 0.674 | 2.94 | `#417acc` | 0.581 | 4.08 |
| `--viz-seq-6` | `#4481da` | 0.606 | 3.85 | `#568fe3` | 0.649 | 5.38 |
| `--viz-seq-7` | `#2f6bc2` | 0.535 | 5.20 | `#74a6ef` | 0.720 | 7.06 |
| `--viz-seq-8` | `#2257a3` | 0.464 | 7.03 | `#97bdf4` | 0.791 | 9.12 |
| `--viz-seq-9` | `#194583` | 0.396 | 9.37 | `#b9d3f9` | 0.860 | 11.50 |

- **DS-VIZ-05. Diverging ramp.** Cobalt arm for positive values or increases, orange arm for negative values or decreases, four steps per arm with equal lightness per step (minimum step 0.119), and a neutral midpoint (`--viz-div-mid`). At step 1, values are close to zero and the two arms are deliberately close to neutral (ΔE 8.6 light, 10.5 dark under simulation). Sign is always also carried by parentheses or `+` (DS-FMT-31). Red and green are not used as diverging poles.

| Step | Light positive | Light negative | Dark positive | Dark negative |
|---|---|---|---|---|
| 1 | `#bdd3f2` (1.51) | `#efc8b3` (1.53) | `#293e5c` (1.62) | `#57331d` (1.59) |
| 2 | `#83adea` (2.28) | `#e0976d` (2.36) | `#345d9b` (2.66) | `#904613` (2.57) |
| 3 | `#4d86d9` (3.63) | `#ca6724` (3.80) | `#4780d2` (4.42) | `#c3611b` (4.22) |
| 4 | `#2460b7` (6.06) | `#9c4700` (6.28) | `#74a6ef` (7.06) | `#e38c58` (6.83) |
| mid | `#e9e8e5` | | `#363533` | |

- **DS-VIZ-06. Ordinal ramp for time bands.** `--viz-rpo-1` to `--viz-rpo-5` alias sequential steps 8, 7, 6, 5, 4, so the nearest band is the strongest mark in both themes. The weakest band meets the 2:1 ordinal floor (2.25 light, 3.02 dark) and adjacent steps differ by ΔL 0.068. A chart uses one step per band returned by the API (DS-CH-03); the POL-201 default of three bands uses `--viz-rpo-1` to `--viz-rpo-3`.
- **DS-VIZ-07. Status colours in charts.** A series that means a state (for example "Difference" in a reconciliation chart) uses the `-solid` status token with a legend label and icon. Status and categorical colours never appear in the same chart. The nearest status-to-categorical normal-vision ΔE is 6.9 light and 7.7 dark, which is why this separation is a rule rather than left to hue.
- **DS-VIZ-08. Texture.** "Awaiting trigger" marks use a 45° hatch (`<pattern>` with 6 px spacing and a 1.5 px `--viz-awaiting` stroke on a transparent fill) plus a 1.5 px dashed outline in `--viz-awaiting`. Under `forced-colors: active` every series in a chart switches to `CanvasText` strokes with distinct fills in slot order: solid, 45° hatch, 135° hatch, dots, then no fill.
- **DS-VIZ-09. Chart chrome.**

| Element | Rule |
|---|---|
| Gridlines | Horizontal only, 1 px `--viz-grid`; at most 5 ticks |
| Zero baseline | 1 px `--viz-baseline` (3.75:1 light, 3.77:1 dark) |
| Tick labels | `caption` size, tabular, `--viz-tick` (5.93:1 light, 6.72:1 dark), compact notation (DS-FMT-15) |
| Data labels | `caption` size, tabular, `--viz-label` |
| Plot background and border | None; the chart sits on its panel surface |
| Bars | Square corners; 1 px `--bg-surface` stroke between stacked segments |
| Hover | A `--bg-hover` band behind the hovered category; tooltip per DS-CMP-14 |
| Plot margins | 8 px top, 12 px inline-end, 24 px bottom; inline-start fits the widest tick label |

### 5.3 Chart specifications

**DS-CH-01 Revenue waterfall.** Revenue by accounting period, split by state, for a contract, an obligation, a customer or the portfolio in the current context (entity, book).

| Aspect | Specification |
|---|---|
| Form | Vertical stacked columns (Recharts `BarChart`, stacked `Bar` series). X: periods (DS-FMT-19). Y: amount with compact ticks. Granularity: Month, Quarter or Year; above 36 months the default is Quarter. At most 36 columns are drawn; longer ranges page with Previous/Next range buttons |
| Series (stack order from baseline) | Recognized (`--viz-recognized`, solid); Scheduled (`--viz-scheduled`, solid) |
| Awaiting trigger | One trailing category labelled "Awaiting trigger", separated by a 16 px gap and a 1 px dashed `--viz-baseline` vertical rule; hatch per DS-VIZ-08. It has no period because its timing depends on an event |
| Open period marker | The column label of the first open period is weight 600 with a caption "Open" above the plot; a 1 px `--fg-2` vertical rule sits at the boundary between the last closed period and it |
| Tooltip | Period; Recognized, Scheduled and Total (full values); for Awaiting trigger, the amount and the count of pending triggers |
| Drill-down | Selecting a segment opens Schedules filtered to that period, state and context |
| Table view | Rows: periods plus "Awaiting trigger". Columns: Recognized, Scheduled, Total, with a totals row |
| Summary text | "Revenue for <scope> from <first period> to <last period>: recognized USD <x>, scheduled USD <y>, awaiting trigger USD <z>." |
| Validation | Recognized vs Scheduled ΔE under protanopia and deuteranopia 21.2 light, 20.8 dark; normal vision 21.0 light, 21.6 dark. Recognized marks 7.03:1 light, 9.12:1 dark. Scheduled marks 2.94:1 light (relief: legend, segment stroke and Table view), 4.08:1 dark. Awaiting trigger stroke 3.85:1 light, 7.06:1 dark |

**DS-CH-02 Rollforward bridge.** Opening balance, activity and closing balance for a balance such as contract liability, contract asset or unbilled receivable over a period range.

| Aspect | Specification |
|---|---|
| Form | Floating vertical bars on a category axis (Recharts `BarChart` with a transparent base series and a visible delta series). Categories come from the rollforward API in order, for example Opening balance, Billings, Revenue recognized, FX remeasurement, Reclassification, Closing balance |
| Encodings | Opening, closing and subtotal bars start at zero in `--viz-total`. Increases use `--viz-increase`; decreases use `--viz-decrease`. A 1 px dashed `--viz-baseline` connector joins the end of each bar to the start of the next |
| Labels | Each activity bar carries its delta above the bar (DS-FMT-31, compact allowed); totals carry their value. Category labels wrap to at most two lines |
| Integrity | The chart computes nothing. If the API flags that opening plus activity does not equal closing, the chart renders a negative banner "This rollforward does not balance. Difference USD <x>." instead of the plot (G5 invariant) |
| Drill-down | Selecting a bar opens the rollforward report detail filtered to that category |
| Table view | The rollforward table with totals rules (DS-ELV-02) |
| Validation | Increase vs decrease ΔE 25.0 (simulated) and 27.8 (normal) in both themes; increase vs total 21.8 / 22.6 light and 17.4 / 20.0 dark; decrease vs total 14.8 / 22.1 light and 17.1 / 19.9 dark. Marks vs surface: increase 3.63 light, 4.42 dark; decrease 3.80 light, 4.22 dark; total 7.38 light, 7.58 dark |

**DS-CH-03 RPO time-band stacked bars.** Remaining performance obligations by expected timing of recognition (ASC 606-10-50-13).

| Aspect | Specification |
|---|---|
| Form | Horizontal stacked bars with absolute amounts. One bar per row: the total, then one per disaggregation value (entity, product line or customer segment, as chosen in the toolbar), at most 12 rows with the remainder folded into "Other" |
| Bands | The bands returned by the `rpo` report run (04 report code `rpo`, parameter `time_bands`), in the returned order, nearest first. Their month boundaries come from POL-201 `rpo.time_bands` (default `[12, 24]`, three bands; REQ-RPT-009). The chart never computes, merges, splits or re-orders bands, and has no band default of its own. One to five bands are drawn, coloured `--viz-rpo-1` onward. When the API returns more than five bands, the panel shows the Table view only, and the Chart option of the view switch is disabled with the tooltip "The chart shows at most five time bands." (DS-CMP-31) |
| Band labels | Catalogue copy with named placeholders, built from the returned boundaries: the first band "Within {months} months"; each middle band "{from} to {to} months", where `from` is the previous boundary plus 1; the last band "After {months} months"; a single band with no boundary "All remaining periods". With the POL-201 default: "Within 12 months", "13 to 24 months", "After 24 months" (PRD WLD-X-07) |
| Labels | Band legend above the plot in band order; the row total at the end of each bar; segment values in the tooltip and Table view (no labels inside segments) |
| Separation | 1 px `--bg-surface` stroke between segments |
| Footnote | When practical expedients apply (606-10-50-14), the footnote states which ones and what is excluded |
| Drill-down | Selecting a segment opens the RPO report filtered to that band and row |
| Table view | Rows as in the chart; one column per band plus Total |
| Validation | Ordinal ramp per DS-VIZ-06 |

**DS-CH-04 Sparkline.** A compact trend inside KPI cells, list rows and grid cells.

| Aspect | Specification |
|---|---|
| Size | 80 × 24 px in KPI cells; 64 × 20 px in grid cells |
| Marks | A 1.5 px line in `--viz-sparkline` (8.59:1 light, 9.39:1 dark) and a 3 px radius end dot in `--fg-1`; no axes, gridlines or fill. If the series crosses zero, a 1 px `--viz-grid` zero line is drawn |
| Interaction | None; the parent cell drills down |
| Implementation | A small SVG component inside the chart module (not Recharts), because many can render in a grid |
| Accessibility | `role="img"` with an accessible name stating the measure, range, first and last values, minimum and maximum: "Recognized revenue, Oct 2025 to Sep 2026, from USD 40,000.00 to USD 52,000.00, low USD 38,500.00, high USD 52,000.00" |

**DS-CH-05 KPI strip proportion bar.**

| Aspect | Specification |
|---|---|
| Marks | 4 px bar with `--radius-full` ends; track `--viz-kpi-track`, fill `--viz-kpi-bar` (C72: 6.83:1 light, 7.26:1 dark) |
| Value | Fill width = value ÷ reference value, capped at 100%; the reference per KPI is defined by the screen (for example, transaction price). Zero or a negative value shows an empty track. Above 100%, the bar is full and a warning chip "Over <reference label>" follows the value |
| Colour | One neutral fill for every KPI; no per-KPI colours (DS-AP-06) |
| Accessibility | `aria-hidden="true"`; the secondary text line states the proportion (DS-CMP-06) |

**DS-CH-06 Category bars (rev 1.12).** One amount per category of a disaggregation dimension, for one range and one currency — the rows of a `disaggregation` report run (04 report code `disaggregation`).

| Aspect | Specification |
|---|---|
| Form | Horizontal bars with absolute amounts on a category axis (Recharts `BarChart`, vertical layout), one bar per category. X: amount with compact ticks. No legend: each bar is named on its axis |
| Order and colour | Categories by descending amount, equal amounts in the order the API gave them (DS-VIZ-03). Each bar takes the next categorical slot in that order, `--viz-1` onward (DS-VIZ-01); under `forced-colors: active` the fills of DS-VIZ-08 in the same order |
| Cap | At most seven categories are drawn. The chart computes nothing, so it folds none into "Other", which would be a sum of its own (DS-FMT-02): with more than seven the panel shows the Table view only, and the Chart option of the view switch is disabled with the tooltip "The chart shows at most seven categories." (DS-CMP-31) |
| Labels | The category on the axis; the amount at the end of each bar, compact (DS-FMT-15); the full value in the tooltip and the Table view |
| Tooltip | Category; Amount (full value) |
| Drill-down | Selecting a bar opens the disaggregation report |
| Table view | One row per category in the chart's order: the category and "Amount (<currency>)"; a totals row with the total the API states, and none where it states none |
| Summary text | "<title>, largest first: <category> <currency> <amount>, …."; of a chart without categories, its title |
| Validation | Categorical palette per DS-VIZ-01 and DS-VIZ-02 |

## 6. Numbers, money and dates

### 6.1 Principles

- **DS-FMT-01.** One format per quantity type, everywhere in the UI. All display formatting goes through one frontend format module (`formatMoney`, `formatNumber`, `formatPercent`, `formatRate`, `formatDate`, `formatTimestamp`, `formatPeriod`, `formatCompact`) and the `<Money>`/`<Num>` components (DS-CMP-26). Calling `toFixed`, `toLocaleString` or constructing `Intl.NumberFormat` or `Intl.DateTimeFormat` outside that module is an error **[lint]**.
- **DS-FMT-02.** The browser never does arithmetic on money. Money arrives from the API as decimal strings (D-45). The format module passes the string directly to `Intl.NumberFormat.prototype.format`, which formats string input as an exact decimal (ECMA-402 Intl.NumberFormat v3), with `roundingMode: "halfExpand"`. That matches D-11 ROUND_HALF_UP, where ties round away from zero. Totals, subtotals, KPI figures and chart aggregates come from the API. `parseFloat`, `Number()` and unary `+` on money fields are forbidden; the lint flags `parseFloat(` in application code **[lint]**. [J] Floats would reintroduce the rounding defects D-11 removes.
- **DS-FMT-03.** Decimal places for money come from the currency's ISO 4217 minor unit supplied by the API currency reference (D-11), not from `Intl` defaults. For example USD 2, JPY 0, BHD 3, CLF 4.

### 6.2 Rules

| Id | Quantity | Rule | Example (en-US locale) |
|---|---|---|---|
| DS-FMT-04 | Money in grids and report tables | Number only. Minor-unit decimals. Locale grouping. Right-aligned, tabular. The currency code is in the column header (DS-FMT-12). | `1,234,567.89` |
| DS-FMT-05 | Money outside grids (record header, Explain panel, drawers, toasts, prose, tooltips) | ISO 4217 code, no-break space (U+00A0), amount. Never a currency symbol. When every value in a KPI strip shares one currency, the strip shows the code once in its label and the values omit it. [J] `$` is ambiguous across USD, CAD, AUD, SGD and others in a multi-currency subledger; auditors read ISO codes. | `USD 1,234,567.89` |
| DS-FMT-06 | Negative amounts | One negative style per tenant (REQ-UX-006; D-75), read from the tenant setting `ui.negative_number_style` (04 T-PLT-31, literals `PARENTHESES` and `MINUS`), which `GET /me` returns as `tenant_settings.negative_number_style` (04 API-S-Me; §15 OQ-06 resolved by D-76 under the 04 name, 04 B3-D01), and never varied by locale, user or screen. **Parentheses** (default): the absolute value in parentheses, no minus sign; positive values in money columns reserve the width of the closing parenthesis (utility `num-pos` in `tokens.css`: `::after { content: ")"; visibility: hidden; }`) so decimal points align. **Minus** (allowed by the tenant setting): U+2212 MINUS SIGN directly before the figures (after the currency code and no-break space outside grids), with no width reservation. Both styles: no colour change; negative zero after rounding displays as zero. The format module formats the absolute value with `Intl.NumberFormat` and applies the style itself; it never uses the sign output of `Intl`. | Parentheses `(4,000.00)`; minus `−4,000.00` |
| DS-FMT-07 | Zero | Zero with minor-unit decimals. | `0.00` |
| DS-FMT-08 | No value (null, not applicable) | Em dash U+2014 in `--fg-3`; accessible name "No value". A value still loading is a skeleton, never `0.00` or `—`. | `—` |
| DS-FMT-09 | Percent | One decimal by default. Two decimals for allocation shares and SSP ratios. Negatives per DS-FMT-06. Full precision in the Explain panel. | `12.5%`, `33.33%`, `(4.0%)` (minus style `−4.0%`) |
| DS-FMT-10 | Percentage-point change | One decimal with `pp` and an explicit sign word in the accessible name. Positive changes carry `+`; negative changes follow DS-FMT-06. | `+1.2 pp`, `(0.8) pp` (minus style `−0.8 pp`) |
| DS-FMT-11 | Quantity | Integer when integral; otherwise up to 4 decimals with trailing zeros trimmed. Right-aligned. | `12`, `2.5`, `0.3333` |
| DS-FMT-12 | Currency code in headers | Single-currency grid: `<Label> (<ISO>)`. Mixed-currency grid: a `Currency` column (mono, left-aligned) sits immediately before the first amount column, amount headers carry no code, and totals rows appear once per currency, each naming its ISO code in the Currency column (DS-CMP-10 item 7; rev 1.4). The toolbar currency view switch (Transaction / Functional / Reporting) changes the header codes. | `Allocated (USD)` |
| DS-FMT-13 | Unit prices and SSP unit rates | At least the currency minor unit, up to 6 decimals, trailing zeros beyond the minor unit trimmed. | `125.00`, `0.333333` |
| DS-FMT-14 | FX rates | 6 decimals, fixed. The header names the direction. | `Rate (EUR to USD)` → `1.083450` |
| DS-FMT-15 | Large numbers | Full value in grids, record headers, KPI strips, Explain and exports. Compact notation only for chart axis ticks, chart data labels and sparkline end labels: 3 significant digits, suffixes K, M, B, T, negatives per DS-FMT-06. The full value is in the tooltip and the accessible name. | `1.25M`, `(845K)` (minus style `−845K`) |
| DS-FMT-16 | Calendar dates (effective dates, service dates, due dates) | `DD MMM YYYY` with a two-digit day. The month abbreviation comes from `Intl.DateTimeFormat(uiLocale, { month: "short", timeZone: "UTC" })`. The date is formatted from its `YYYY-MM-DD` parts and is never shifted by the browser time zone. [J] Unambiguous across DMY and MDY conventions; aligns in tables. | `07 Sep 2026` |
| DS-FMT-17 | Timestamps (`recorded_at`, audit events, approvals) | `DD MMM YYYY HH:mm UTC`, 24-hour clock, always in UTC; seconds (`HH:mm:ss`) in the audit trail and timeline detail. The tooltip shows the viewer's local time with its zone. [J] D-19 records UTC; reviewers in different zones must see the same evidence. | `07 Sep 2026 14:05 UTC` |
| DS-FMT-18 | Relative time | Only in the notifications panel and toasts, always with the absolute timestamp in the tooltip. Never in grids, the audit trail or evidence exports. | `4 min ago` |
| DS-FMT-19 | Accounting periods | Gregorian monthly calendars: `MMM YYYY`. Other fiscal calendars (4-4-5, 13-period): `FY<YYYY> P<NN>`. Quarters: `Q<n> <YYYY>` for calendar quarters, `FY<YYYY> Q<n>` for fiscal quarters. Fiscal year: `FY<YYYY>`. | `Sep 2026`, `FY2026 P09`, `FY2026 Q3` |
| DS-FMT-20 | Ranges | En dash with spaces between endpoints of the same format. | `01 Jan 2026 – 31 Dec 2026`, `Jan 2026 – Dec 2026` |
| DS-FMT-21 | Counts | Integer with locale grouping. | `1,204 contracts` |
| DS-FMT-22 | Booleans | "Yes" / "No" text, or a check icon with the accessible name "Yes". Never `true`/`false`. | `Yes` |
| DS-FMT-23 | Identifiers | Mono (DS-TYP-10), left-aligned. Business ids (contract number, invoice number, journal batch number) are never truncated. System UUIDs and hashes show the first 8 and last 4 characters with a middle ellipsis, a copy button and the full value in the tooltip. | `c3f1a9d2…9a2e` |
| DS-FMT-24 | Durations (job progress, close timers) | Largest two units. | `2 min 14 s`, `3 h 05 min` |
| DS-FMT-25 | Exports (CSV) | Raw values: signed decimal strings with a hyphen-minus, `.` decimal separator, no grouping, ISO dates `YYYY-MM-DD`, ISO 8601 UTC timestamps. [J] Exports feed ERPs and auditors' tools, which need machine-readable values. | `-4000.00`, `2026-09-07` |
| DS-FMT-26 | Exports (XLSX) | Numeric cells with the number format of the tenant negative style (DS-FMT-06): parentheses `#,##0.00_);(#,##0.00)`, minus `#,##0.00;-#,##0.00` (decimals per currency minor unit); date cells with `dd mmm yyyy`; the currency code in the header row. | `(4,000.00)`; minus style `-4,000.00` |

### 6.3 Alignment and semantics

- **DS-FMT-27.** Right-aligned: money, quantities, percentages, rates and counts, including their column headers. For right-aligned columns the sort indicator sits on the leading side of the header label, so the label's end edge aligns with the figures. Left-aligned: text, identifiers, codes, dates, periods and statuses.
- **DS-FMT-28.** Balances follow D-12. The UI shows labelled positive balances ("Contract liability USD 1,000.00", "Contract asset USD 250.00") and never a signed net position. Parentheses express a negative in a signed measure: rollforward activity, reversals, allocation adjustments, variances and deltas.
- **DS-FMT-29.** Accessible names for negative money: under the parentheses style `<Money>` renders `<span class="sr-only">minus </span><span aria-hidden="true">(</span>4,000.00<span aria-hidden="true">)</span>`; under the minus style it renders `<span class="sr-only">minus </span><span aria-hidden="true">−</span>4,000.00`. Grid copy (Ctrl/Cmd+C) copies raw signed values from the data model, not DOM text (DS-CMP-10).
- **DS-FMT-30.** Colour never encodes sign. Colour may encode state only (for example, a reconciliation difference that is not zero is shown with a warning chip beside the amount, not by turning the amount red).
- **DS-FMT-31.** Deltas (Explain history, approval impact summaries, variance columns, bridge chart labels): positive values carry a leading `+`, negative values follow DS-FMT-06, and zero is `0.00` without a sign. Examples: `+45,000.00`, `(4,000.00)` (minus style `−4,000.00`), `0.00`.

### 6.4 Worked examples

| API value | Currency / context | Grid cell | Outside a grid | CSV |
|---|---|---|---|---|
| `"1234567.8900"` | USD | `1,234,567.89` | `USD 1,234,567.89` | `1234567.89` |
| `"-4000.0000"` | USD, rollforward activity, parentheses style (default) | `(4,000.00)` | `USD (4,000.00)` | `-4000.00` |
| `"-4000.0000"` | USD, rollforward activity, minus style | `−4,000.00` | `USD −4,000.00` | `-4000.00` |
| `"0.0000"` | USD | `0.00` | `USD 0.00` | `0.00` |
| `"-0.0040"` | USD, display of an unrounded value | `0.00` | `USD 0.00` | `-0.0040` (raw) |
| `"150000.0000"` | JPY | `150,000` | `JPY 150,000` | `150000` |
| `"12.3450"` | BHD | `12.345` | `BHD 12.345` | `12.345` |
| `null` | any | `—` | `—` | empty field |
| `"0.333333333333333333"` | allocation share | `33.33%` | `33.33%` (Explain: `0.333333333333333333`) | `0.333333333333333333` |
| `"2026-09-07"` | effective date | `07 Sep 2026` | `07 Sep 2026` | `2026-09-07` |
| `"2026-09-07T18:05:31Z"` | `recorded_at` | `07 Sep 2026 18:05 UTC` | `07 Sep 2026 18:05:31 UTC` (audit) | `2026-09-07T18:05:31Z` |

## 7. Component catalogue

Every component below is built once, in the shared component library, and reused by all screens. `docs/design/SCREENS.md` composes screens from these components and may not introduce a new visual pattern without a new DS id.

Each entry states **anatomy**, **variants**, **states**, **keyboard** behaviour and the **ARIA** pattern. Keyboard and ARIA follow the W3C ARIA Authoring Practices Guide (APG) patterns cited. "Mod" means Cmd on macOS and Ctrl elsewhere.

### 7.0 Base controls

**DS-CMP-20 Button**

- Anatomy: optional leading icon (16 px), label (`body-sm`, weight 500), optional trailing icon or keyboard hint. Height `--control-h` (or `--control-h-sm`); horizontal padding 12 px (10 px compact); radius `--radius-md`.
- Variants:

| Variant | Rest | Hover | Active | Use |
|---|---|---|---|---|
| Primary | `--accent-solid` fill, `--on-accent` text | `--accent-solid-hover` | `--accent-solid-active` | The one main action of a view (at most one per region) |
| Secondary | `--bg-surface` fill, `--border-control` edge, `--fg-1` text | `--bg-hover` | `--bg-active` | Other actions |
| Ghost | transparent, `--fg-2` text | `--bg-hover`, `--fg-1` | `--bg-active` | Toolbar and row actions, icon buttons |
| Danger | `--danger-solid` fill, `--on-accent` text | `--danger-solid-hover` | `--danger-solid-active` | Irreversible commands inside confirmations only (void, reject, reopen) |
| Link | `--accent-fg` text, underline on hover | `--accent-fg-hover` | — | Inline text actions |

- States: rest, hover, active, focus-visible (DS-A11Y-02), disabled (`--fg-disabled` text, no fill change, `aria-disabled="true"` so the button stays focusable, with the reason in a tooltip; form submit buttons also show a visible reason line, DS-CMP-21), loading (label kept, 16 px spinner replaces the leading icon, `aria-busy="true"`, the button ignores repeat presses).
- Icon-only buttons are 32 × 32 px (28 × 28 compact, never below 24 × 24), require `aria-label`, and show a tooltip with the label and shortcut.
- Keyboard: Enter and Space activate. ARIA: native `<button>`; toggle buttons use `aria-pressed`; menu buttons use `aria-haspopup="menu"` and `aria-expanded` (APG Menu Button).

**DS-CMP-27 Tooltip**

- Anatomy: E2 surface, `--radius-sm`, 6 × 8 px padding, `caption` text, max width 280 px; an optional keyboard hint in mono.
- Opens after 400 ms hover or immediately on keyboard focus; closes on blur, pointer leave or Esc. Tooltips never contain interactive content or the only copy of essential information.
- ARIA: APG Tooltip. The trigger references the tooltip with `aria-describedby` (or `aria-label` for icon-only buttons).

**DS-CMP-28 Menu**

- Anatomy: E2 surface, `--radius-lg`, 4 px padding; items `--row-h` high with an optional 16 px icon, label, and end-aligned shortcut hint; separators are 1 px hairlines; destructive items use `--negative-fg` text and appear last.
- Keyboard (APG Menu Button / Menu): Enter, Space or Down opens and focuses the first item; Up/Down move (wrapping); Home/End; type-ahead; Enter activates; Esc closes and returns focus to the trigger.
- ARIA: `role="menu"`, `role="menuitem"` (`menuitemcheckbox`/`menuitemradio` for toggles).
- Disabled item (rev 1.8): An item that a state makes unavailable is disabled: aria-disabled, in the arrow-key order, described by a DS-CMP-27 tooltip with its reason, never activated; a missing permission hides the item (SCR-PERM-02).

### 7.1 Shell and navigation

**DS-CMP-01 App shell and top bar**

- Anatomy (desktop, ≥ 1024 px): a two-column grid. Column 1 is the icon rail (DS-CMP-02), full viewport height, whose header holds the wordmark or monogram. Column 2 stacks the top bar, the global banner region, and the scrollable `main` content on `--bg-canvas`.
- Top bar (height `--topbar-h`, `--bg-surface`, bottom `--border-hairline`), start to end:
  1. Context pill (DS-CMP-03).
  2. Search trigger: a secondary-style button reading "Search or run a command" with a `Mod K` hint, 320 px wide at ≥ 1280 px, icon-only (MagnifyingGlass) below that. It opens the command palette (DS-CMP-04).
  3. Flexible space.
  4. Sandbox indicator, shown only in sandbox and scenario tenants: a warning status chip "Sandbox: <tenant name>" plus a 2 px `--warning-solid` line along the top edge of the top bar. [J] Users must never confuse a what-if tenant with production books.
  5. "Read-only access": a neutral status chip for users whose roles hold no command permission (SCREENS SCR-PERM-06).
  6. "Ask about revenue": a ghost icon button (Sparkle, 20 px; `aria-label` and tooltip "Ask about revenue") that opens the revenue Q&A docked panel (SF-28). It renders when `GET /me` returns `tenant_settings.ai_enabled = true` and the user holds `ai.use`. The button component lives in the AI component directory, so the Sparkle import stays there (DS-LINT-07). (SCREENS:OQ-S-11 resolved by D-76.)
  7. Notifications bell (DS-CMP-05).
  8. Help menu (Question icon): Keyboard shortcuts, Guided tour, User guide, About eRev Cloud.
  9. User menu (avatar with initials, 28 px): name and role, Switch tenant (when the user belongs to more than one), Theme (System, Light, Dark), Density (Comfortable, Compact), Sign out.
- Global banner region: at most one banner at a time (DS-CMP-29), for system states such as "API unreachable. Changes are not being saved." or a scheduled maintenance notice.
- A skip link "Skip to main content" is the first focusable element and becomes visible on focus.
- On route change the document title becomes `<page title> · eRev Cloud`, focus moves to the page `h1` (which carries `tabindex="-1"`), and the route name is announced by the polite live region.
- States: normal; sandbox; session expiring (a modal two minutes before expiry offers "Stay signed in"); offline (banner).
- Keyboard: `Mod K` opens the palette. `?` opens the keyboard shortcuts dialog. `[` toggles the rail. Go-to sequences: `G H` Home, `G C` Contracts, `G S` Schedules, `G L` Close, `G J` Journals, `G R` Reports, `G A` Approvals, `G P` Policies, `G D` Data. Single-key and sequence shortcuts are ignored while focus is in an editable field, and the shortcuts dialog lists them all (WCAG 2.1.4 Character Key Shortcuts: they can be turned off in the user menu).
- ARIA: `header` (banner landmark) for the top bar, `nav aria-label="Primary"` for the rail, `main id="main"`, one polite and one assertive live region mounted at the shell root (DS-A11Y-08).

**DS-CMP-02 Icon rail**

- Anatomy: header (wordmark when expanded, monogram when collapsed, collapse toggle SidebarSimple); primary group; a hairline divider; governance group; Settings pinned to the bottom. Background `--bg-surface`, inline-end `--border-hairline`.
- Items (the ten D-02 destinations; the rail has no second level). Destinations are PRD SF ids. `docs/design/SCREENS.md` owns every route path (D-73), and the router resolves each SF id to its path (DG-FE-02).

| Group | Label | Phosphor icon | Destination (SF id) | Active when the current route's SF id is |
|---|---|---|---|---|
| Work | Home | House | SF-01 | SF-01 |
| Work | Contracts | FileText | SF-02 | SF-02, SF-03, SF-07, SF-18, SF-20 |
| Work | Schedules | CalendarDots | SF-04 | SF-04 |
| Work | Close | LockKey | SF-05 | SF-05 |
| Work | Journals | Notebook | SF-06 | SF-06 |
| Work | Reports | ChartBar | SF-08 | SF-08, SF-09, SF-17 |
| Govern | Approvals | SealCheck | SF-12 | SF-12 |
| Govern | Policies | Scales | SF-13 | SF-13 |
| Govern | Data | Database | SF-10 | SF-10, SF-11, SF-19, and the integration screens of SF-16 |
| Bottom | Settings | GearSix | SF-15 | SF-14, SF-15, and the developer settings of SF-16 |

- A rail link opens the destination's default route in SCREENS.md (PRD §3 until SCREENS.md exists, DG-FE-02). Route parameters that the destination needs, for example the entity, book and period of SF-05, are filled from the current context (DS-CMP-03). [J] Settings opens SF-15 rather than SF-14 because SF-15 holds the notification preferences every user may open, while SF-14 is identity administration.
- Shell surfaces (SF-21 to SF-25, SF-27, SF-28) and the Help screen SF-26 activate no rail item.

- Item anatomy: height 36 px (both densities), 20 px icon, label (`body`, weight 500) when expanded, optional count badge (Approvals pending for the current user: `caption`, tabular, `--neutral-chip-bg` fill, `--fg-2` text; never red).
- States: rest (`--fg-2` icon and label, icon weight `regular`); hover (`--bg-hover`, `--fg-1`); active route (`--bg-active` fill, `--fg-1`, icon weight `fill`, 2 px `--selection-edge` bar on the inline-start edge); focus-visible ring. Collapsed width `--rail-w-collapsed`, expanded `--rail-w-expanded`; the choice persists per user (key `erev.rail`).
- In the collapsed state each item shows a tooltip (DS-CMP-27) with its label and go-to shortcut.
- Keyboard: items are links in the Tab order; Enter follows. The toggle is a button (`[` shortcut).
- ARIA: `nav aria-label="Primary"` containing a `ul`; active link `aria-current="page"`; collapsed links carry `aria-label` equal to the label; badge text is part of the accessible name ("Approvals, 4 pending"); toggle `aria-expanded`, `aria-controls` the rail.
- Sub-areas (for example Policies: Revenue policies, SSP books, Account mapping) are route tabs on the page (DS-CMP-07), not nested rail items.

**DS-CMP-03 Context pill (entity, period, book)**

- Anatomy: one bordered group in the top bar (`--control-h` high, `--radius-md`, `--border-default` edge, `--bg-surface`) with three segment buttons divided by 1 px hairlines:
  1. Entity: Buildings icon, entity short name (for example `US01 · eRev Demo Inc.`), or "All entities (4)" on pages that support aggregation.
  2. Period: CalendarBlank icon, period label (DS-FMT-19), and a period-state marker: "Open" (text only), "Soft close" (HourglassMedium, warning tone) or "Locked" (LockSimple, neutral tone).
  3. Book: Books icon and `ASC 606`, `IFRS 15` or `Legacy`.
- Each segment opens a popover selector: entity listbox with search; period list grouped by fiscal year with state chips; book radio list. In scenario runs a fourth segment shows "Scenario: <name>" in warning tone and opens the scenario switcher.
- The URL is the source of truth, so views are shareable. The search parameters `entity`, `period` and `book` carry the API-C-11 context values verbatim: the entity code (omitted for "All entities"); the period's `period_key` (04 table `period`, `FY<fiscal_year>-P<period_no two digits>`); and the book literal `ASC606`, `IFRS15` or `LEGACY`. Example: `?entity=US01&period=FY2026-P09&book=ASC606`. Every read passes the same values to the API. The pill displays the period label (DS-FMT-19, for example "Sep 2026"), never the key. Where a destination carries context values as path parameters (for example SF-05), the path values are the source of truth and use the same literals. The pill reflects the route; changing a segment replaces the parameters and refetches.
- States: default; loading (segments show skeleton text); dimension not used on this page (segment `aria-disabled="true"`, tooltip "Not used on this page"); period locked; scenario.
- Keyboard: segments are separate buttons in the Tab order. In a popover: Up/Down move, type-ahead, Enter selects, Esc closes and returns focus. The palette offers "Switch entity…", "Switch period…" and "Switch book…".
- ARIA: `role="group" aria-label="Accounting context"`; each segment `aria-haspopup="listbox"`, `aria-expanded`, accessible name such as "Period: Sep 2026, open"; the popover list uses APG Listbox. A context change is announced politely: "Context changed to US01, Sep 2026, ASC 606".

**DS-CMP-04 Command palette**

- Anatomy: modal dialog 640 px wide, positioned 12vh from the top, E3 with `--scrim`; search input (placeholder "Search contracts, customers, invoices, or type a command"); scope chips (All, Contracts, Customers, Invoices, Obligations, Journals, Pages, Commands); grouped results with group headings; footer with key hints. Result rows (`--row-h`): 16 px icon, primary text with matched characters in weight 600, secondary text (customer, entity, period), trailing status chip.
- Behaviour: with an empty query it lists recent records and pages. Record search starts at 2 characters, debounced 120 ms, served by the search API; identifiers match by prefix (`C-0001`). At most 8 results per group, with a "Show all results" row opening a results page. Commands cover navigation ("Go to Close"), context switches, preferences ("Theme: Dark", "Density: Compact") and role-permitted actions ("Run journals for Sep 2026…"). An action command always opens its confirmation or form; the palette never executes an accounting command directly.
- States: recent (empty query); loading (spinner at the end of the input, previous results remain); no results ("No matches for "<query>". Search by contract number, customer, invoice number or order number."); error ("Search is unavailable. Pages and commands still work.").
- Keyboard: `Mod K` toggles. Up/Down move the active option (wrapping). Enter opens. `Mod Enter` opens in a new tab. Tab moves to the scope chips and back. Esc clears a non-empty query, otherwise closes. Focus returns to the element focused before opening.
- ARIA: `role="dialog" aria-modal="true" aria-label="Command palette"`; APG Combobox with listbox popup: input `role="combobox" aria-expanded="true" aria-controls="<listbox id>" aria-activedescendant="<option id>"`; results `role="listbox"` containing `role="group"` elements labelled by their headings; options `role="option"`, `aria-selected="true"` on the active option. The result count is announced politely ("12 results").

**DS-CMP-05 Notifications bell**

- Anatomy: ghost icon button (Bell, 20 px) with an unread badge (count up to 99, then "99+"; `--bg-inverse` fill, `--fg-inverse` text, `caption` tabular). The popover panel is 400 px wide, max height 70vh, E2: header ("Notifications"; the link button "Mark all as read", rendered while the Unread tab lists at least one item; a "Notification preferences" link to SF-15), tabs "Unread" and "All" (DS-CMP-07 panel variant), list.
- Items: one per in-app notification (04 T-PLT-24, served by `GET /me/notifications`, API-R-03). The panel shows only the E-69 `notification_kind` values in the table below, cited verbatim (D-73). There are no other item types, and there is no jobs or mentions section. Titles and bodies are the PRD §5.4 copy carried by the notification.
- Item anatomy: 16 px kind icon (table below), title (`body-sm`, 500), one-line body with the record reference, relative time (DS-FMT-18), and an 8 px `--accent-solid` unread dot. The title carries the meaning; the icon never carries it alone (DS-ICO-06). The tone icon colours measure at least 5.18:1 on `--bg-raised` and `--bg-hover` in both themes (DS-COL-02 method).

| `notification_kind` (E-69) | PRD notification | Icon | Icon colour |
|---|---|---|---|
| `APPROVAL_ASSIGNED` | NTF-01 | SealCheck | `--fg-2` |
| `ITEM_APPROVED` | NTF-02 | CheckCircle | `--positive-fg` |
| `ITEM_REJECTED` | NTF-03 | XCircle | `--negative-fg` |
| `APPROVAL_VOIDED` | NTF-04 | Prohibit | `--fg-2` |
| `JOB_FAILED` | NTF-05 | XCircle | `--negative-fg` |
| `PERIOD_LOCKED` | NTF-06 | LockSimple | `--fg-2` |
| `PERIOD_REOPENED` | NTF-07 | LockSimpleOpen | `--warning-fg` |
| `CLOSE_BLOCKER_RAISED` | NTF-08 | WarningCircle | `--warning-fg` |
| `CHAIN_VERIFICATION_FAILED` | NTF-09 | XCircle | `--negative-fg` |
| `EXPORT_FAILED` | NTF-10 | XCircle | `--negative-fg` |
| `EXCEPTION_ASSIGNED` | NTF-11 | WarningCircle | `--warning-fg` |
| `SUPPORT_GRANT_REQUESTED` | NTF-12 | Info | `--info-fg` |

- Behaviour: selecting an item opens its `link_path` (T-PLT-24; PRD §5.4 Link column) and marks it read (`POST /me/notifications/{id}/read`). "Mark all as read" sends `POST /me/notifications/read-all` with `before` = the `created_at` of the newest notification loaded in the panel, so a notification that arrives afterwards stays unread; on success the badge and both tabs refetch and the polite live region announces "Marked <marked> notifications as read" (04 API-R-03, §16.12; §15 OQ-07 resolved by D-76). Approval notifications open the approval detail (SF-12); nobody approves from the notification panel (approvals require the diff and a comment, DS-CMP-16).
- States: empty ("You are up to date. Approval requests and decisions, period changes, close blockers, failures and assigned exceptions appear here."); loading (4 skeleton rows); error with retry.
- Keyboard: Enter or Space opens the panel and focuses the first item; items are links in the Tab order; Esc closes and returns focus to the bell.
- ARIA: button `aria-label="Notifications, 3 unread"`, `aria-haspopup="dialog"`, `aria-expanded`; panel `role="dialog" aria-label="Notifications"` (non-modal); list `ul`. Only a new `APPROVAL_ASSIGNED` notification for the current user is announced (politely), once.

### 7.2 Record and layout

**DS-CMP-06 Record header with KPI strip**

- Anatomy, top to bottom, on `--bg-surface` with a bottom `--border-hairline`, padding `--panel-pad` × `--gutter`:
  1. Breadcrumb (`body-sm`, `--fg-3` links): `Contracts / C-000123`.
  2. Title row: identifier (mono, copy button), the record title as the page `h1` (`--text-title-lg`), status chips (DS-CMP-19) including a neutral version chip `v3`, flexible space, secondary actions, one primary action, overflow menu (DotsThree).
  3. Meta row: inline label–value pairs (label `caption` `--fg-3`, value `body-sm` `--fg-1`), 24 px apart, wrapping. Contract example: Customer, Contracting entity, Currency, Inception date, Term, Policy version, Last computed.
  4. Five-step tracker (DS-CMP-17), contracts only.
  5. KPI strip.
- KPI strip anatomy: a caption heading at the start, "Key figures (USD, ASC 606)"; up to 6 KPI cells in one row, equal widths, separated by 1 px `--border-hairline` vertical rules. Each cell: label (`caption`, `--fg-3`); value (`--kpi-text`, weight 600, tabular, `--fg-1`, DS-FMT-04 digits without the code because the heading carries it); optional proportion bar (4 px, `--radius-full`, track `--bg-active`, fill `--fg-2`, width = value ÷ reference value, capped at 100%; over 100% shows a full bar and a warning chip "Over transaction price"); optional secondary line (`body-sm`, `--fg-3`), for example "46.2% of transaction price". Whenever a bar is shown, the secondary line states the same proportion in text.
- A cell may hold a percentage, a date, a date range or a quantity instead of money or a count, in its own format (DS-FMT-09, DS-FMT-11, DS-FMT-16, DS-FMT-20): the same label, the same value style and tabular figures, for example "Progress 59.1%" or "Rate 80.00%" of an estimate (SCREENS §8.4). Such a cell is an Explain trigger where the API names its explanation, and is printed without a trigger where it names none (rev 1.10).
- Metric values are neutral ink. Colour is never used to identify which KPI is which (DS-AP-06).
- Every computed KPI value is an Explain trigger (DS-CMP-15): the value renders as a button with no visible chrome; on hover or focus a dotted underline in `--border-control` and a 16 px Function icon appear.
- Variants: contract; obligation (compact header inside the master-detail pane: no breadcrumb, `title-md`, at most 4 KPIs); journal batch (debits, credits, difference, line count); import batch (rows, valid, errors, committed); period (the close cockpit header: entity, period state, blockers, sign-offs); customer.
- States: loading (labels visible, values as skeletons); stale (an info banner inside the header, "Figures were computed before the latest change. Recalculation is queued." with job progress, DS-CMP-24); pending approval (chip plus a banner linking to the request); period locked (chip "Sep 2026 locked" with LockSimple); void (chip "Void"; figures remain visible).
- Scroll behaviour: once the KPI strip scrolls out of view, a 48 px sticky condensed header (identifier, title, status chips, primary action) appears at the top of `main` (`--z-sticky`).
- Keyboard: Tab order is breadcrumb, copy, actions, tracker steps, KPI values. On a focused KPI value, Enter or `E` opens Explain.
- ARIA: `section aria-labelledby="<h1 id>"`; the KPI strip is a `dl` (`dt` label, `dd` value); each value button is named "Explain Recognized, USD 452,310.00"; proportion bars are `aria-hidden="true"` because the secondary line carries the proportion.

**DS-CMP-07 Tabs**

- Anatomy: tab bar `--tab-h` high with a bottom `--border-hairline`; tab labels `body-sm` weight 500 in `--fg-2`, 20 px apart; optional count (`caption`, tabular, `--fg-3`, for example "Obligations 12"); optional WarningCircle icon (`--warning-fg`) when the tab contains unresolved blockers. The active tab is `--fg-1` with a 2 px `--accent-solid` indicator along the bottom edge under the label. There are no filled or pill tabs.
- Variants:
  - **Route tabs** (page sections under a record header, and sub-areas such as Policies). Each tab is a link to a URL.
  - **Panel tabs** (inside a detail pane or popover). They switch content without changing the URL. Height `--control-h`.
- Rules: at most one tab bar per panel. At most two tab bars on screen (page and detail pane). When tabs overflow, the trailing tabs move into a "More" menu; tab bars never scroll horizontally.
- States: rest, hover (`--fg-1`), active, focus-visible, disabled (`--fg-disabled`, tooltip with the reason).
- Keyboard: route tabs are links in the Tab order. Panel tabs follow APG Tabs with automatic activation: Left/Right move and activate (mirrored in RTL), Home/End go to first/last, Tab moves into the panel.
- ARIA: route tabs `nav aria-label="<record> sections"` with `aria-current="page"` on the active link; panel tabs `role="tablist"` (labelled), `role="tab"` with `aria-selected` and `aria-controls`, `role="tabpanel"` with `aria-labelledby` and `tabindex="0"`.

**DS-CMP-08 Master-detail list with pane**

- Anatomy: master pane (`--master-w`, `--bg-surface`) and detail pane side by side, separated by a 1 px `--border-hairline` resize handle with an 8 px hit area. The master pane has a toolbar (filter input, sort menu, count "12 obligations") above the list. The detail pane holds a compact record header (DS-CMP-06 obligation variant), panel tabs and content.
- Master row (two lines, 56 px comfortable, 48 px compact; hairline dividers):
  - Line 1: name (`body`, 500, `--fg-1`, truncated with a tooltip) and, at the end, the primary amount (tabular).
  - Line 2: identifier (mono-sm, `--fg-3`), status chips (for example "Ratable", "Satisfied"), date range (DS-FMT-20).
  - Hover `--bg-hover`. Selected: `--accent-subtle` fill plus a 2 px `--selection-edge` bar at the inline-start edge. Rows are flat list rows, not cards.
  - A row whose name is an identifier (an element code) sets line 1 in mono-sm, weight 500 (rev 1.10).
- Grouped list (rev 1.10): a list may show its rows under caption rows, one per run of rows of the same group — for example the estimated elements of a contract under their kind (SCREENS §8.3). A caption row is `caption` text in `--fg-3` on `--bg-subtle` with a hairline below it; it is not an option, takes no focus and is skipped by the arrow keys, `J`/`K`, Home/End and type-ahead. Each option names its caption through `aria-describedby`. A grouped list renders every row; it is not virtualized.
- Variants (examples, not a closed list): obligations within a contract; approvals inbox (detail is the diff view DS-CMP-16); exception queue; import batches. Any master list with a detail pane uses this anatomy, for example the estimates workbench and approval delegations, and introduces no new visual pattern (SCREENS:OQ-S-20 resolved by D-76).
- States: loading (6 skeleton rows); empty list (DS-CMP-23); nothing selected (detail pane text: "Select an obligation to see its allocation, schedule and history."); error with retry; more than 100 rows (virtualized with TanStack Virtual).
- The selected item is part of the route (for obligations, the obligation route of SF-03; SCREENS.md owns the path, D-73). Pane width persists per list type (key `erev.master.<type>`).
- Keyboard (APG Listbox, single select, selection follows focus): Up/Down move and select (the detail pane loads after a 150 ms debounce); Home/End; type-ahead on the name; `J`/`K` next/previous when focus is not in a field; Enter moves focus to the detail pane heading; Esc in the detail pane returns focus to the selected row. Resize handle: Left/Right ±16 px, Home/End to min/max.
- ARIA: master list `role="listbox"` with `aria-label`; rows `role="option"` with `aria-selected`; detail pane `role="region"` named "Obligation details: <name>"; resize handle `role="separator" aria-orientation="vertical"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and `tabindex="0"`.

**DS-CMP-09 Drawer**

- Anatomy: panel attached to the inline-end viewport edge, full viewport height, `--bg-raised`, E3. Widths `--drawer-w` or `--drawer-w-wide`. Header: title (`title-md`), optional subtitle or identifier, close button (X). Scrollable body with `--panel-pad`. Sticky footer with a top hairline and end-aligned actions ("Cancel", then the primary action). A modal drawer may hold one secondary action between the two, in the secondary button style, for a form that is saved before it is submitted — "Cancel", "Save draft", "Submit for approval" (SCREENS §8.4); while the primary action runs the secondary one is unavailable (rev 1.10).
- Variants:
  - **Modal drawer** (scrim, focus trap): create and edit forms, for example "Add revenue policy" or "Edit obligation dates (draft)".
  - **Docked panel** (no scrim, no focus trap, content reflows at ≥ 1440 px, overlays below): the Explain panel (DS-CMP-15) and the column chooser for wide grids.
- States: clean; dirty (closing asks "Discard changes?" through a confirmation modal); submitting (primary button loading, fields read-only); server error (DS-CMP-29 banner at the top of the body; field errors inline, DS-CMP-21).
- Stacking: at most one drawer plus one modal above it. A drawer never opens another drawer.
- Keyboard (APG Dialog (Modal) for the modal variant): focus moves to the first field, or to the title when the drawer is informational; Tab is trapped; Esc closes (with the dirty check); focus returns to the trigger. The docked variant is a normal region in the Tab order and closes with Esc while focus is inside it.
- ARIA: modal `role="dialog" aria-modal="true" aria-labelledby="<title id>"`; docked `aside aria-labelledby="<title id>"`; close button `aria-label="Close"`.

**DS-CMP-11 Modal**

- Anatomy: dialog positioned 15vh from the top and centred horizontally over a `--scrim`; `--bg-raised`, `--radius-xl`, E3; header (title `title-md`, optional description `body-sm` `--fg-2`), body (left-aligned), footer with end-aligned actions.
- Variants:
  - **Confirmation** (`--modal-w-sm`): states the consequence in one or two sentences with the affected figures ("Locking Sep 2026 for US01 prevents new postings to that period."). High-risk commands (lock, reopen, void, reject, cancel journal run) require a reason (minimum 10 characters); pressing the action without a valid reason shows the field error (DS-CMP-21). Destructive commands use the Danger button.
  - **Form** (`--modal-w-md`): short forms of up to 6 fields; longer forms use a drawer.
  - **Diff** (`--modal-w-lg`): the approval diff (DS-CMP-16) when reviewed outside the approvals inbox.
- Use a modal only for irreversible or high-risk confirmations, unsaved-change decisions, short forms and the diff. Success is reported with a toast, never a modal.
- States: default; submitting (actions disabled, Esc ignored); error (banner in the body).
- Keyboard: APG Dialog (Modal). Initial focus goes to the least destructive action in confirmations ("Cancel") and to the first field in forms. Tab is trapped. Esc closes unless submitting. Focus returns to the trigger.
- ARIA: `role="alertdialog"` for confirmations and `role="dialog"` otherwise; `aria-modal="true"`, `aria-labelledby`, `aria-describedby` (the consequence text).

**DS-CMP-12 Timeline and activity**

- Anatomy: a vertical ordered list grouped under date headings (DS-FMT-16). Each event has a 20 px icon on a 1 px `--border-default` connector line, then: actor (20 px avatar and name, or "System", "Import batch B-2026-0042", "Proposal accepted by <name>"; where the record names the principal an event was written for, "<actor> on behalf of <name>" — "System on behalf of Maya Chen" (rev 1.11)), a verb phrase ("changed End date"), the object link, the timestamp (DS-FMT-17, with seconds), an optional inline diff (DS-CMP-16 inline variant), an optional comment (quoted block on `--bg-subtle`, `--radius-md`), and optional evidence attachments (Paperclip links).
- Audit variant header: "Audit chain verified 07 Sep 2026 14:05 UTC" with ShieldCheck, linking to the verification detail (research 07 F-03; D-43). If verification fails the header becomes a negative banner "Audit chain verification failed at event <n>" with a link to the details.
- Variants: record activity (versions, events, calculations, approvals, comments, with a comment composer); audit trail (read-only, filters by actor, event type and date range); approval history (inside the approval detail).
- Filters: event-type chips (All, Changes, Approvals, Calculations, Imports, Comments) and a "Show system events" switch.
- Paging: a "Load older activity" button; no infinite scroll.
- States: loading (3 skeleton events); empty ("No activity yet. Changes, approvals and calculations appear here."); error with retry.
- Keyboard: standard Tab order through links and buttons; the composer is a textarea with `Mod Enter` to post.
- ARIA: `ol aria-label="Activity"`; each `li` contains a `time datetime="<ISO 8601 UTC>"`; icons are `aria-hidden="true"` and the event type is in the text; no live region for incoming events.

### 7.3 Data

**DS-CMP-10 DataGrid**

Built on TanStack Table and TanStack Virtual (D-41). One implementation serves every interactive grid.

- Anatomy:
  1. Toolbar (above the grid, inside the panel): title and count ("1,204 contracts"); saved-view selector; flexible space; currency view switch (Transaction / Functional / Reporting) when the grid shows money; column chooser (Columns icon); export menu (DownloadSimple: CSV, XLSX; server-generated, DS-FMT-25/26); overflow menu. When rows are selected, the toolbar start is replaced by a selection bar: "3 selected", bulk actions permitted for the role, "Clear selection".
  2. FilterBar (DS-CMP-13) directly below the toolbar.
  3. Header row: sticky, `--header-row-h`, `--bg-subtle`, bottom `--border-default`; labels `body-sm` weight 500 `--fg-2` (never uppercase); sort indicator (CaretUp/CaretDown 12 px) on the sorted column; resize handle (4 px hit area) at each column edge; a column menu (DotsThree, visible on hover and focus) with Sort ascending, Sort descending, Group by this column, Pin to start, Pin to end, Autosize, Hide column.
  4. Body rows: `--row-h`, `--border-hairline` dividers, cell padding `--cell-px`, text `--grid-text` / `--grid-leading`, single line with truncation and a tooltip for text cells (amounts and identifiers are never truncated; their columns autosize). Optional checkbox column (40 px) and row-actions column (40 px, DotsThree visible on hover and focus).
  5. Pinned columns: when the body scrolls horizontally, pinned columns show a 1 px `--border-default` edge.
  6. Group rows (grouping, at most 3 levels): `--bg-subtle`, expand caret, group label and count, subtotals for money columns (weight 500), 16 px indent per level.
  7. Totals row: sticky at the bottom, `--bg-surface`, top rule `--rule-total` (DS-ELV-02), weight 600, label "Total" in the first column. Totals are supplied by the API (DS-FMT-02). Mixed-currency grids show one totals row per currency, never a sum across currencies; each totals row names its ISO code in the DS-FMT-12 Currency column and, while that column is hidden, in its label "Total (<ISO>)". A single totals row keeps the label "Total" (rev 1.4).
  8. Status footer (optional): "1,204 rows · 3 selected".
- Links in grid cells: `--fg-1` text with a 1 px dotted underline in `--border-control` (offset 3 px); hover gives a solid `--fg-1` underline. Business identifiers in the first column are links to their records. [J] A column of accent-coloured links would dominate the table; the dotted underline keeps links distinguishable without colour (WCAG 1.4.1).
- Column types:

| Type | Alignment | Renderer | Default width |
|---|---|---|---|
| Identifier | start | mono link (DS-FMT-23) | 128 px |
| Text | start | `body`/`grid-text`, truncation with tooltip | flex, min 160 px |
| Money | end | `<Money variant="cell">` | 144 px |
| Quantity, percent, rate, count | end | `<Num>` | 112 px |
| Date, period | start | DS-FMT-16/19, tabular | 112 px / 96 px |
| Status | start | status chip | 136 px |
| Boolean | start | "Yes"/"No" | 72 px |
| User | start | 20 px avatar and name | 160 px |
| Actions | end | ghost icon buttons | 40 px |

- Data loading: sorting, filtering and grouping are server-side. The client holds a virtual window (TanStack Virtual, overscan 10 rows) and fetches pages of 200 rows as the viewport approaches the end (TanStack Query infinite queries). `aria-rowcount` uses the total count returned by the API. A grid of 50,000 rows renders at most 120 body-row DOM nodes **[test]**.
- Column chooser: a docked popover listing columns with search, visibility checkboxes and reorder handles. Every drag has keyboard and button alternatives ("Move up", "Move down"), per WCAG 2.2 SC 2.5.7 Dragging Movements. "Reset to view default" restores the saved view's columns.
- Saved views: the selector shows the current view name and a dot when unsaved modifications exist. Its menu lists "My views" and "Shared views", then Save view, Save as new view, Rename, Set as my default, Delete. A view stores column order, widths, visibility, pinning, sort, filters, grouping and the currency view. Views are stored server-side; tenant-shared views require the view-sharing permission. The active view id and unsaved modifications are encoded in the URL.
- Inline editing is allowed **only for draft data**: import staging rows, draft SSP book versions, and draft contract lines before submission. Committed accounting data is never editable in a grid; changes go through an action with a reason and, where required, approval (D-60; research 02 §6 principle 9).
  - Editable cells show `--bg-hover` on hover and a pencil cursor. Editing starts with Enter, F2 or typing a printable character.
  - Editors match the column type: text input; decimal input that keeps a string and validates against the currency minor unit; date picker; select.
  - Enter commits and moves down; Tab commits and moves to the next cell; Esc cancels.
  - Saves are pessimistic: the cell shows a 12 px spinner until the API confirms. `Mod Z` undoes the last edit in the session.
  - A cell failing validation keeps the entered text and shows a 1 px `--negative-fg` inset edge, a WarningCircle icon and the message in a tooltip. The toolbar shows "2 errors" with a "Next error" button.
  - **Form-held lines (rev 1.7; ruling R-93 (d)).** Draft lines that a form holds in its own state and saves with the form in one body (the draft contract lines of SF-03:new and SF-03:edit; the change lines of the modification wizard) are edited in the line editor (`frontend/src/components/line-editor`), not in the DataGrid, which reads server pages and saves cell by cell. The line editor keeps the rules above and the keyboard and ARIA below, with these differences:
    - Each cell holds one DS-CMP-21 control at all times: text input, decimal input, money input, typed date (the same parsing and echo as the date editor), select or combobox. A cell that takes no input in its row is disabled and carries `aria-readonly="true"`.
    - The grid is one tab stop with a roving `tabindex` on the cells; a control is reached through its cell. Arrow keys, Home, End, Mod Home, Mod End, Page Down and Page Up move between cells. Enter, F2 or a printable character starts editing (a character replaces the value). Enter commits and moves down; Tab commits and moves to the next cell, Shift+Tab to the previous one, and from the first or last cell leaves the grid; F2 finishes editing and keeps the change; Esc restores the value the cell had when editing started and returns to the cell.
    - Nothing is saved cell by cell: there is no spinner and no `Mod Z`. The form's save sends every line, and leaving a changed form asks "Discard changes?".
    - A cell failing validation keeps the entered text and shows the inset edge, the WarningCircle icon and the message as text below the control (DS-CMP-21), linked with `aria-describedby`, instead of a tooltip. Cross-field checks and the API's `errors[].field` paths both land on cells; the toolbar shows "2 errors" with "Next error".
    - The toolbar holds the title, the line count and "Add line"; each row ends with "Remove line" in a pinned actions column, and the key column is pinned to the start as `role="rowheader"`. There is no sorting, filtering, grouping, column chooser, saved view, row selection or virtual window: a form holds at most 500 lines, all rendered.
    - `Mod C` copies the raw value of the focused cell. The cell range (Shift+Arrow) is not built in this variant: it serves read-only grids.
- Selection: checkbox column; the header checkbox selects the loaded page (tri-state), and a banner offers "Select all 1,204 matching rows". Selection persists across paging and clears when filters change.
- Copy: `Mod C` copies the selected cell range, or the focused cell, as tab-separated raw values (DS-FMT-25), with headers when whole rows are selected. A copied cell is pasted into spreadsheets, so it follows the rule of the exports (rev 1.5; 03 REQ-SEC-011; 05 UPL-20): a text cell or header that begins with `=`, `+`, `-`, `@`, a tab or a carriage return is copied with a leading apostrophe and is shown, not evaluated; a money or number cell that holds a plain decimal is copied as it is, so a negative amount pastes as a number; a tab or line break inside a cell is copied as a space.
- States: loading (header plus 10 skeleton rows); refreshing (a 2 px indeterminate progress bar along the top edge of the grid; rows stay visible); empty (DS-CMP-23 inside the grid body); no results for the filters ("No contracts match these filters." with "Clear filters"); error (inline banner with Retry; existing rows stay if any); partial failure (failed rows carry an error chip and are listed by "Next error").
- Keyboard (APG Grid, data grid; APG Treegrid when grouping is active):

| Key | Behaviour |
|---|---|
| Tab / Shift+Tab | Enter or leave the grid (one tab stop; roving `tabindex` on cells) |
| Arrow keys | Move one cell (mirrored in RTL) |
| Home / End | First / last cell in the row |
| Mod Home / Mod End | First cell of the first row / last cell of the last row |
| Page Down / Page Up | Move by the number of visible rows |
| Enter | On an identifier or row: open the record (drill down). In an editable cell: start editing. On a header: cycle sort |
| F2 | Start or finish editing an editable cell |
| Esc | Cancel editing; otherwise leave cell-range mode |
| Space | Toggle selection when focus is in the checkbox column |
| Shift+Space | Select the focused row |
| Shift+Arrow | Extend the cell range for copying |
| Mod A | Select all loaded rows |
| Mod C | Copy (see above) |
| E | Open Explain for a focused computed cell (DS-CMP-15) |
| Shift+F10 or the context-menu key | Open the column menu (header) or row menu (body) |
| Right / Left on a group row | Expand / collapse |

- ARIA: `role="grid"` (or `role="treegrid"` when grouped) with `aria-labelledby` the grid title, `aria-rowcount`, `aria-colcount` and `aria-multiselectable="true"` when selectable. Rows `role="row"` with `aria-rowindex` (and `aria-level`, `aria-expanded` for group rows); headers `role="columnheader"` with `aria-sort`; the identifier column uses `role="rowheader"`; cells `role="gridcell"` with `aria-colindex`; non-editable columns in an editable grid carry `aria-readonly="true"`; selected rows `aria-selected="true"`; invalid cells `aria-invalid="true"` with `aria-describedby` the error text.
- Static tables: a read-only table of at most 100 rows with no selection, editing or cell navigation (for example a small summary inside the Explain panel) uses a native `table` with `th scope`, `caption`, and sortable headers as buttons. It uses the same visual tokens.

**DS-CMP-13 FilterBar**

- Anatomy: a wrapping row (at most two lines, then a "+3 more" toggle) of: quick search input ("Search contracts", full text, debounced 250 ms); active filter chips; "Filter" button (Funnel + "Filter") that opens a searchable field list; "Clear all" link button when at least one filter is active.
- Filter chip anatomy: `--control-h-sm` high, `--radius-sm`, `--border-default` edge, `--bg-surface`; text "<Field> <operator> <value>" (for example "Status is Draft or Pending approval"), with values truncated after two items ("Status is Draft, Void +2"); a remove button (X, 16 px).
- Editors by field type: enum (checkbox list with search); text (contains, equals); money and number (is, between, at least, at most; string decimal validation); date (presets: This period, Last period, This fiscal year, Last 12 months, Custom range); period (period picker); user (combobox); boolean (Yes/No).
- Operator vocabulary: is, is not, contains, between, at least, at most, on or before, on or after, is empty, is not empty.
- Filters are encoded in the URL and stored in saved views.
- States: no filters; applied; invalid value (inline error inside the popover; pressing Apply reports the error); loading options.
- Keyboard: the bar is an APG Toolbar (one tab stop, Left/Right move between chips and buttons). Enter or Space opens a chip's editor (non-modal popover dialog; Esc closes and returns focus). Backspace or Delete on a focused chip removes it.
- ARIA: `role="toolbar" aria-label="Filters"`; chip buttons are named "Status is Draft or Pending approval, edit filter"; remove buttons "Remove filter: Status". Removing a filter and the resulting row count are announced politely ("Filter removed. 214 contracts.").

**DS-CMP-14 Chart panel**

- Anatomy: panel header with title (`title-sm`), subtitle (`body-sm`, `--fg-3`) stating measure, currency and book ("Revenue by period · USD · ASC 606"), controls (granularity segmented control Month / Quarter / Year; view switch Chart / Table), legend (inline at the top start: 10 px square swatches with labels; direct labels replace the legend when there are at most 3 series), plot area, footnote ("As of 07 Sep 2026 14:05 UTC").
- Every chart has a Table view showing the same figures with DS-FMT rules. Every mark drills down: selecting a bar or point opens the filtered report or grid of the records behind it (D-60).
- Tooltip (E2): heading (period or category), one row per series (swatch, label, full value per DS-FMT-05), and a total row where the series sum.
- Implementation: Recharts is imported only inside the chart module (**[lint]**). The wrapper sets `isAnimationActive={false}` on every series, keeps the Recharts 3 `accessibilityLayer` (on by default: "Tab into the chart and use the arrow keys to navigate" [F] ([external website reference removed])), and passes colours as `var(--viz-*)` strings.
- States: loading (static skeleton of the plot area); empty ("No revenue scheduled for this range."); error with retry; truncated series (more than 7 categories fold into "Other", DS-VIZ-03).
- Keyboard: Tab into the chart; Left/Right move between data points; Enter drills down on the active point; Esc returns focus to the chart panel. The view switch is a segmented control (APG Radio Group).
- ARIA: the panel is a `figure` with `aria-labelledby` the title and `aria-describedby` a generated text summary (range, total, largest and smallest period, for example "Recognized revenue Jan 2026 to Dec 2026, total USD 1,020,000.00, highest Sep 2026 USD 120,000.00"). The Table view is the complete non-visual equivalent. Chart specifications are in §5.

**DS-CMP-26 Money and number display**

- `<Money value={string} currency={ISO} variant="cell" | "inline" | "kpi" />` and `<Num value={string} kind="quantity" | "percent" | "pp" | "rate" | "fx" | "count" />` implement §6 exactly **[test]**.
- Explainable values are wrapped in `<ExplainTrigger figureRef={...}>`, which adds the hover affordance and the `E`/Enter behaviour (DS-CMP-15).
- States: loading (skeleton 8ch wide); value unavailable (em dash, DS-FMT-08); stale (the value stays visible; an Info icon with the tooltip "Recalculation queued" follows it).
- ARIA: DS-FMT-29; KPI and inline variants include the currency code in the accessible name even when it is visually carried by a heading.

### 7.4 Workflow

**DS-CMP-15 Explain panel**

Every computed number opens this panel (D-60). It renders the `/explain` endpoint for the figure (D-45) and the engine's calculation trace (D-10).

- Anatomy (docked panel variant of DS-CMP-09, width `--explain-w`):
  1. Header: "Explain" eyebrow text (`caption`, `--fg-3`), figure name (`title-md`, for example "Recognized revenue · Sep 2026"), the figure value (`--text-kpi`, DS-FMT-05), a context line (contract, obligation, book, entity), and buttons "Copy link" and Close. When the user has drilled into an input, a breadcrumb appears above the name: "Recognized › Allocated › SSP weight", with a Back button.
  2. **Formula**: one plain-language sentence, then the formula in mono with named variables, for example `recognized = round(allocated × elapsed_days ÷ term_days) − previously_recognized`, followed by the rounding rule ("ROUND_HALF_UP to 2 decimals, cumulative rounding", D-11).
  3. **Inputs**: a native table (Name, Value, Source). Values show full stored precision (for example an allocation ratio to 18 decimals). A computed input has a Function icon button that opens its own explanation in the same panel.
  4. **Calculation steps**: an ordered list from the calculation trace with intermediate values. Traces longer than 6 steps collapse behind "Show all 14 steps".
  5. **Source records**: links to events (effective date and `recorded_at`), invoices, import rows (batch id, row number, SHA-256 prefix of the source file), the SSP book version, the FX rate record and the policy.
  6. **Versions**: policy name and version, SSP book version, FX rate set, calendar, engine version, calculation version id (mono), `as_of` and `known_at`.
  7. **History**: a compact timeline (DS-CMP-12) of earlier values of this figure by calculation version, with deltas (DS-FMT-31), the approvals involved, and the origin period of any catch-up (D-19).
  8. Footer: "Open calculation trace" (full trace page and JSON download); "Ask about this figure" when AI is enabled for the tenant, which returns a proposal block (DS-CMP-25).
- Behaviour: opening Explain for another figure replaces the content and pushes onto the panel's Back stack. The panel stays open across tab changes within the same record and closes when the route leaves the record. The header value must equal the triggering figure exactly (same calculation version). If the API returns a different calculation version, the panel shows a warning banner "This figure changed after the page loaded. Refresh to see current figures." **[test]**
- States: loading (skeletons per section); input value (the figure is not computed: "This value is an input." with its source record); partially restricted ("2 source records are outside your access."); stale (banner, as DS-CMP-06); error ("The explanation could not be loaded." with Retry).
- Keyboard: on a trigger, Enter or `E` opens the panel and moves focus to its heading. Esc closes and returns focus to the trigger. `Alt+Left` or the Back button goes up one level. Tab moves through the sections.
- ARIA: `aside aria-labelledby="<figure name id>"`; each section has an `h3`; the formula is text in a `code` element (symbols ×, ÷, − read by screen readers); the Back stack is named "Back to Recognized".

**DS-CMP-16 Approval diff view**

The single maker-checker review surface for policy changes, SSP book versions, manual releases and deferrals, contract modifications, estimate versions (D-20), import commits (D-30) and period reopen (research 07 F-04, F-07).

- Anatomy:
  1. Request header: request id (mono); request type ("Revenue policy change", "SSP book version", "Import commit", "Period reopen"); status chip (Pending approval, Approved, Rejected, Withdrawn, Stale); maker (avatar, name, submitted timestamp); routing steps ("Controller approval · 1 of 1"; "Dual approval · 1 of 2 recorded"), each with approver and timestamp once recorded.
  2. Segregation-of-duties notice when the viewer is the maker or a prior approver: an info banner "You submitted this request. Another approver must review it." Approve and Reject are not rendered for that viewer.
  3. Maker's justification (quoted block).
  4. Impact summary from the dry-run API: a compact KPI strip (DS-CMP-06 variant) of affected figures, for example "Revenue Sep 2026 +45,000.00 (USD)", "Contracts affected 14", "Journal lines 28".
  5. Diff body, one of:
     - **Field diff** (configuration and single records): a native table with columns Change (marker), Field, Current, Proposed. Only changed fields show by default, with a "Show unchanged fields" switch. Removed or replaced values: marker "−", `--diff-removed-bg` row tint, current value in `--fg-2` with line-through. Added values: marker "+", `--diff-added-bg` row tint. Changed numeric fields add a Delta column (DS-FMT-31).
     - **Grid diff** (tables such as SSP book rows or import rows): a read-only DataGrid with a leading Change column (chips Added, Removed, Changed). Changed cells have a 1 px `--warning-border` inset edge and a tooltip "Was 1,200.00".
  6. Decision form (sticky footer): comment textarea "Comment (required)" with a 10-character minimum; buttons "Reject" (secondary) and "Approve" (primary). Rejecting then opens a confirmation modal (DS-CMP-11). **Sticky footer cue (rev 1.9).** A sticky footer covers the lower part of a scroll container that is taller than its viewport, and no shadow or fade may mark that edge (DS-ELV-04). While content of the container lies beneath the footer, the footer's first row, at its upper edge, is the link button "More below" (CaretDown, small) — inside the footer, so that the cue itself covers nothing. It scrolls the container by one view less the footer's height and is not rendered at the end of the container. The container's `scroll-padding-block-end` is the footer's height including that row, whether or not the row is shown (DS-A11Y-03): an element that takes focus while the cue is not shown would otherwise stop flush with the shorter footer and be covered the moment the cue appears. Whether content lies beneath is measured when the container scrolls, when the container or the footer is resized, and when the container's content changes; content that grows inside a child of fixed height resizes no observed box. The rule holds for every sticky footer of a scroll container: this decision form, the preparer's "Withdraw request" footer of the same view, and the footer of DS-CMP-18.
- Inline variant (timeline and history): "End date: 31 Dec 2026 → 30 Jun 2027"; accessible text "End date changed from 31 Dec 2026 to 30 Jun 2027".
- Colour is redundant with text: every changed row has the marker glyph, a screen-reader prefix ("Removed:", "Added:", "Changed:") and the column headers. Red and green tints alone never carry the meaning.
- States: pending; approved or rejected (read-only, decision comments shown in the routing steps); withdrawn; **stale**: when the underlying record changed after submission, the status chip is "Stale", a warning banner reads "The record changed after this request was submitted. The maker must resubmit it.", and the decision form is not rendered (research 07 F-04 stale-approval invalidation); insufficient permission (decision form not rendered; text "You do not have approval rights for this request type.").
- Validation: pressing Approve or Reject without a valid comment shows the field error and moves focus to the comment field (DS-CMP-21).
- Keyboard: `N` / `Shift+N` move to the next / previous change when focus is not in a text field. `Mod Enter` inside the comment does not submit. [J] An approval must be a deliberate button press.
- ARIA: the field diff table has a `caption` "Proposed changes (6)"; marker cells contain visually hidden prefixes; the outcome is announced through the toast (DS-CMP-22) and the status chip update.

**DS-CMP-17 Five-step contract tracker**

The spine of a contract (D-60; research 02 §6 principle 4), using our labels for the five steps of ASC 606-10-05-4.

- Steps and labels:

| # | Label | Status line example | Evidence panel contents |
|---|---|---|---|
| 1 | Contract | "Combined with C-000119" | Combination rule matched and grouped contracts; the 606-10-25-1 criteria checklist (approval and commitment, rights, payment terms, commercial substance, collectability) with evidence links; term; modification count |
| 2 | Obligations | "4 obligations · 1 material right" | Obligation summary (distinct, series, material right, warranty type), the policy rule and version that created each |
| 3 | Transaction price | "USD 1,200,000.00" | Transaction price build-up table: fixed consideration, variable consideration estimate (method, constraint, estimate version, D-20), significant financing component, noncash consideration, consideration payable to a customer, total (totals rule, DS-ELV-02) |
| 4 | Allocation | "Relative SSP · book v7" | Allocation table: obligation, SSP, weight, allocated amount, allocation adjustment (D-02), SSP method and book version, discount or VC exception flags |
| 5 | Recognition | "38.2% recognized" | Per obligation: pattern, recognized to date, scheduled, awaiting trigger, next event; link to the schedule |

- Anatomy: a horizontal row of five equal segments across the record header. Each segment is a button containing a 16 px state icon, the step number and label (`body-sm`, 500), and the status line (`caption`, `--fg-3`). Segments are joined by a 1 px `--border-default` line between icons (no arrows, no chevrons). The expanded segment has a 2 px `--accent-solid` bottom indicator. Below the row, a single evidence region shows the expanded step's panel. Every figure in an evidence panel is an Explain trigger.
- Step states (icon, tone): Complete (CheckCircle, `--positive-fg`); Needs attention (WarningCircle, `--warning-fg`), for example an estimate awaiting review; Blocked (XCircle, `--negative-fg`), for example no SSP for a product; In review (HourglassMedium, `--info-fg`); Not started (Circle, `--fg-3`). The state word is always in the accessible name and in the status line when it is not Complete.
- States of the whole tracker: loading (five skeleton segments); collapsed (no evidence region open; the default on load).
- Keyboard: segments are buttons in the Tab order; Enter or Space toggles a segment's evidence region; only one region is open at a time; Esc collapses the open region and returns focus to its segment.
- ARIA: `ol aria-label="ASC 606 steps"`; each segment button has `aria-expanded` and `aria-controls` the evidence region, and an accessible name such as "Step 3, Transaction price, complete, USD 1,200,000.00"; the evidence region is `role="region"` named after the step. Step 3 is labelled "Transaction price" (REQ-UX-015, PRD J-03.2; SCREENS:OQ-S-13 resolved by D-76).

**DS-CMP-18 Import wizard stepper with row-level errors**

Implements the D-30 flow: upload → validate → dry-run diff → maker-checker approval → atomic commit.

- Steps: 1 Upload · 2 Map columns · 3 Validate · 4 Review changes · 5 Approval · 6 Committed. For a legacy v1 template the Map step shows "Not needed: legacy template headers matched" and is skipped automatically.
- Stepper anatomy: a horizontal ordered list at the top of the page. Each item has a 20 px marker (Complete: CheckCircle `--positive-fg`; Current: step number in a 20 px circle of `--accent-solid` with `--on-accent` text; Error: XCircle `--negative-fg`; Pending: Circle `--fg-3`; Skipped: `--fg-3` dash), the label (`body-sm`, 500) and a status caption ("1,204 rows", "12 errors in 9 rows"). Completed steps are links back; future steps are not interactive.
- Scope of the anatomy: the stepper anatomy (markers, captions, completed-step links, keyboard and ARIA rules below) applies to every multi-step flow, for example the modification wizard (SF-07) and the non-interactive configuration lifecycle stepper (SF-13). The step content below belongs to imports only (SCREENS:OQ-S-05 resolved by D-76).
- **Upload**: a dropzone (1 px dashed `--border-control`, `--radius-lg`, 160 px high) reading "Drop a CSV or XLSX file here, or choose a file" with a "Choose file" button; accepted types and the maximum size for the file purpose from 04 T-PLT-29 (D-75), which for imports (`IMPORT_SOURCE`) is 50 MiB; "Download templates" links for the four legacy v1 templates and the modern CSV templates; for CSV templates, a select of published mapping profiles (04 API-S-ImportCreate `mapping_profile_id`). After upload: file name, size, SHA-256 prefix (mono), detected template ("Legacy v1: Contract Setup"). Re-uploading an identical file (same template version and SHA-256 as a committed import) is refused with 409 `duplicate-import` (`IMPORT_FILE_DUPLICATE`), and the dropzone names the earlier import.
- **Map columns**: a read-only header match table from 04 API-S-Import `header_match[]`: Source column, Sample values (first 3), Template field, Match (E-119 words "Exact", "Alias from <profile code>", "Not mapped", "Missing"). A required template field without a source column puts the step in Error with the header-mismatch finding. There is no column select and no per-import mapping: CSV headers that differ from the template need a published mapping profile, chosen on the Upload step and authored as configuration on the templates page (SF-10:templates). Legacy v1 templates skip this step.
- **Validate** (asynchronous job, DS-CMP-24): a summary strip (Rows, Valid, Warnings, Errors); finding chips that filter the grid, one per 04 API-S-Import `finding_counts[]` item ("PROGRESS_OVER_DELIVERY · 2 rows"); a read-only DataGrid of staging rows sorted errors first with columns Row (source row number), Status chip, Messages (first message plus "+2 more"), then the source columns, with invalid cells marked as in DS-CMP-10. Staging rows are immutable (04 T-IMP-03): no cell is editable, and a correction is a new upload of a corrected file. "Download error report" produces CSV (row, column, rule id, message; `GET /imports/{id}/error-report`), and a rejected file offers "Upload a corrected file" (SCREENS:OQ-S-06 resolved by D-76).
- **Review changes**: the dry-run diff: summary figures from `diff_summary` and `GET /imports/{id}/diff` `summary_counts` (contracts affected, contracts created, obligations added, obligations changed, revenue change by period) and the affected records as a grid diff (DS-CMP-16).
- **Approval**: comment (required) and "Submit for approval"; afterwards the step shows routing status and a link to the request.
- **Committed**: batch summary with links to the batch record; every created record links back to its source row (row lineage, D-30).
- Footer: sticky "Back" and "Next" buttons. "Next" validates the current step and reports what blocks it ("Validation found 2 errors. Upload a corrected file to continue."). Leaving the wizard keeps the draft batch, resumable from Data › Imports. The footer carries the sticky footer cue of DS-CMP-16 item 6 (rev 1.9).
- States per step: idle, running (job progress in place), error (banner with rule groups), complete.
- Keyboard: completed-step links in the Tab order; the dropzone is a button (Enter/Space opens the file dialog) backed by a native `input type="file"`; drag and drop is an optional alternative (WCAG 2.2 SC 2.5.7).
- ARIA: `nav aria-label="<flow> steps"` (for imports "Import steps"; for SF-07 "Modification steps") containing an `ol`; the current item has `aria-current="step"`; each item's accessible name includes position and state ("Step 3 of 6, Validate, 12 errors in 9 rows"). Validation completion is announced politely ("Validation finished: 12 errors in 9 rows.").

**DS-CMP-25 AI proposal block**

AI output is a proposal with citations; accepting it is an audited human command (D-46; `docs/00-GOAL.md` §2 item 12).

- Anatomy: container with a 1 px **dashed** `--proposal-border` edge, `--radius-lg`, `--bg-surface`, `--panel-pad`. Header: Sparkle icon (16 px, `--fg-2`), label "Proposed" (`caption`, 500), source line ("Contract review · 07 Sep 2026 14:05 UTC"; the model id and prompt hash are in a details popover). Body: the proposal (extracted fields table, narrative answer or anomaly flag). Citations: bracketed numbers `[1]` linking to a "Sources" list of record links or document page references. Actions: "Accept", "Edit and accept", "Dismiss" (dismiss requires a reason). "Accept" and "Edit and accept" render only for a proposal bound to a command; in 1.0 that is the contract-review extraction, accepted through `POST /ai/proposals/{id}/accept` with command `contract.create_draft` (04 §16.14). Every other proposal (revenue Q&A answers, proposed narratives, anomaly flags) offers a copy action ("Copy answer", "Copy summary") and "Dismiss" (SCREENS_B:OQ-B-16 resolved by D-76).
- Rules:
  - The dashed edge means "not applied". It turns into a solid `--border-hairline` once accepted.
  - The block never uses the accent colour or any violet or gradient treatment (D-61).
  - Every amount in AI text is rendered through DS-FMT rules and must carry a citation. When the backend flags an uncited amount, the block shows a warning chip "Uncited figure" and "Accept" is not rendered.
  - Nothing is applied automatically. There is no confidence percentage, bar or colour. Where a proposal carries a per-field confidence (contract review, PRD BR-AI-01), it is shown as text with two decimals ("0.72"), with the outline chip "Check" below 0.75 (SCREENS_B §8.2; SCREENS_B:OQ-B-15 resolved by D-76). [J] A percentage or a bar would invite reliance on an unverifiable score.
- States: generating (static skeleton lines, "Generating proposal", Cancel); ready; accepted (chip "Accepted by <name>", timeline entry); dismissed (collapsed single line "Dismissed by <name>: <reason>"); failed ("The assistant could not produce a proposal. No data was changed."); AI disabled for the tenant (entry points are not rendered).
- ARIA: `section aria-labelledby="<header id>" aria-describedby="<note id>"` where the visually hidden note reads "AI-generated proposal. Not applied until accepted."; `aria-busy="true"` while generating.

### 7.5 Feedback and forms

**DS-CMP-19 Status chip**

- Anatomy: 20 px high, 0 × 6 px padding, `--radius-sm`, `caption` weight 500, a 12 px leading icon, 1 px edge. Tone styles: fill `--<tone>-bg`, text and icon `--<tone>-fg`, edge `--<tone>-border`, where tone is `neutral` (fill `--neutral-chip-bg`, text `--fg-2`, edge `--border-default`), `info`, `positive`, `warning` or `negative`.
- Outline variant for classifications that are not states ("Ratable", "Point in time", "Series", "Legacy v1"): transparent fill, `--border-default` edge, `--fg-2` text, no icon.
- Fixed vocabulary (the only mapping from status to tone; SCREENS and code may not re-map):

| Status | Tone | Icon |
|---|---|---|
| Draft | neutral | PencilSimpleLine |
| Pending approval | info | HourglassMedium |
| Approved | positive | CheckCircle |
| Rejected | negative | XCircle |
| Withdrawn | neutral | ArrowUUpLeft |
| Stale | warning | ClockCounterClockwise |
| Active | neutral | Circle |
| Void | neutral | Prohibit |
| On hold | warning | PauseCircle |
| Satisfied | positive | CheckCircle |
| Valid | positive | CheckCircle |
| Warning | warning | WarningCircle |
| Error | negative | XCircle |
| Period open | neutral | LockSimpleOpen |
| Soft close | warning | HourglassMedium |
| Locked | neutral | LockSimple |
| Reopened | warning | LockSimpleOpen |
| Queued | neutral | CircleDashed |
| Running | info | CircleHalf |
| Succeeded | positive | CheckCircle |
| Failed | negative | XCircle |
| Exported | info | ArrowSquareOut |
| Posted | positive | CheckCircle |
| Reconciled | positive | CheckCircle |
| Difference | negative | Equals |
| Sandbox | warning | WarningCircle |
| Proposed | neutral, dashed edge | Sparkle |
| Abandoned | neutral | Prohibit |
| Accepted | positive | CheckCircle |
| Account locked | warning | LockSimple |
| Aggregated | neutral | TreeStructure |
| Applied | positive | CheckCircle |
| Archived | neutral | Prohibit |
| Auto-certified | positive | CheckCircle |
| Balanced | positive | CheckCircle |
| Blank | neutral | Minus |
| Blocked | warning | PauseCircle |
| Blocking | negative | XCircle |
| Budget exceeded | warning | WarningCircle |
| Calculated | neutral | PencilSimpleLine |
| Cancelled | neutral | Prohibit |
| Certified | positive | CheckCircle |
| Committed | positive | CheckCircle |
| Completed | positive | CheckCircle |
| Denied | negative | XCircle |
| Disabled | neutral | Prohibit |
| Dismissed | neutral | Prohibit |
| Expired | neutral | ClockCounterClockwise |
| Future | neutral | CalendarBlank |
| Imported | info | CheckCircle |
| In progress | info | CircleHalf |
| In review | info | CircleHalf |
| Info | info | Info |
| Invited | info | HourglassMedium |
| Met | positive | CheckCircle |
| Not a contract | neutral | Prohibit |
| Not applicable | neutral | Minus |
| Not mapped | warning | WarningCircle |
| Not passed | negative | XCircle |
| Not started | neutral | Circle |
| Open | neutral | Circle |
| Pass | positive | CheckCircle |
| Passed | positive | CheckCircle |
| Pending review | info | HourglassMedium |
| Permanently locked | neutral | LockSimple |
| Prepared | info | HourglassMedium |
| Profiled | info | CheckCircle |
| Promoted | positive | CheckCircle |
| Published | positive | CheckCircle |
| Removed | neutral | Prohibit |
| Resolved | positive | CheckCircle |
| Revocation requested | warning | WarningCircle |
| Reviewed | positive | CheckCircle |
| Revoked | neutral | Prohibit |
| Shortfall | warning | WarningCircle |
| Superseded | neutral | ClockCounterClockwise |
| Suspended | warning | PauseCircle |
| Terminated | neutral | Prohibit |
| Tested | info | CheckCircle |
| Timed out | warning | ClockCounterClockwise |
| Verification failed | negative | XCircle |
| Verified | positive | ShieldCheck |
| Waived | neutral | CheckCircle |

- Vocabulary source: the rows after "Proposed" were added in revision 1.2 from the words SCREENS §0.8 and SCREENS_B §0.4 first proposed, with the tones and icons given there, plus the chip words of SCREENS §11.6 and §15.7 and SCREENS_B §3.2, §6.3, §8.5 and §8.6 (SCREENS:OQ-S-12 and SCREENS_B:OQ-B-01 resolved by D-76). Every icon is in DS-ICO-07.
- Rules: every chip has text; colour and icon are redundant with it; status tones never decorate (D-61); chips are not interactive (use a button or filter chip for interaction).
- ARIA: the chip is text in a `span`; the icon is `aria-hidden="true"`; state changes are announced by the component that changed them.

**DS-CMP-21 Form fields and validation**

- Anatomy: label above the control (`body-sm`, 500, `--fg-1`), an "(optional)" suffix in `--fg-3` on optional fields, the control, then help text (`body-sm`, `--fg-3`) and the error message (below the control, above the help text).
- Control: height `--control-h`, `--bg-surface`, 1 px `--border-control`, `--radius-md`, 10 px horizontal padding, `body` text, placeholder in `--fg-3` (never a substitute for the label). Hover edge `--fg-3`. Focus edge `--accent-solid` plus the focus ring (DS-A11Y-02). Disabled: `--bg-subtle` fill, `--fg-disabled` text. Read-only: no edge, transparent fill, selectable `--fg-1` text.
- Field types:

| Type | Rules |
|---|---|
| Text, textarea | Textarea grows to 10 lines, then scrolls |
| Money input | Keeps a string; text right-aligned; trailing ISO code adornment in `--fg-3`; accepts pasted `(1,234.56)`, `-1,234.56`, `−1,234.56` (U+2212, the minus style of DS-FMT-06) and locale grouping; rejects more decimals than the currency minor unit; formats on blur |
| Quantity, percent, rate | String decimals; percent shows a trailing `%` adornment and stores the ratio as the API defines |
| Date | Text input plus a calendar button opening an APG Date Picker Dialog; accepts `YYYY-MM-DD`, `DD MMM YYYY` and the locale's numeric short date; echoes DS-FMT-16 on blur |
| Period | Popover list grouped by fiscal year with state chips |
| Select | APG Select-Only Combobox, up to 10 options |
| Combobox | APG Combobox with list autocomplete for longer lists (customers, products, accounts) |
| Multi-select | Combobox with selected values as removable chips |
| Checkbox, radio group | Native inputs, 16 px, `--accent-solid` when checked |
| Switch | Only for immediately-applied preferences; never inside a form that has a Save button |
| Segmented control (DS-CMP-31) | 2–5 options; APG Radio Group; `--bg-subtle` track, selected option on `--bg-surface` with a `--border-control` edge (C57) and `--fg-1` text |
| Reason field | Textarea with a live character counter and a stated minimum ("Minimum 10 characters") |

- Validation:
  - Format checks run on blur; all checks run on submit; server errors (RFC 9457 problem details, D-45) map to fields by their pointer.
  - Error style: edge `--negative-fg`; message with a 16 px WarningCircle icon in `--negative-fg`, `body-sm`, specific and actionable ("Enter an end date on or after 01 Jan 2026.").
  - With two or more errors on submit, an error summary banner (DS-CMP-29, negative) appears at the top of the form: "Fix 3 fields to continue", linking to each field; focus moves to the summary heading.
  - Submit buttons stay enabled while a form is invalid; pressing them reports the errors. [J] Disabled submit buttons hide the reason. The exception is permission: when the user may not perform the action, the button is not rendered, or is shown with `aria-disabled="true"` and a visible reason line.
  - Accounting warnings (for example a price outside the SSP range) are non-blocking and show in `--warning-fg`; submitting requires ticking "I have reviewed this warning", which is recorded with the command.
  - Unsaved changes: navigating away from a dirty form opens "Discard changes?" (DS-CMP-11).
- Layout: single column; related short fields side by side (start date and end date); field widths by type (money 200 px, date 160 px, period 140 px, text up to 480 px).
- Keyboard: native behaviour; Enter submits single-field forms only; APG patterns for combobox, date picker and radio group.
- ARIA: `label for`; `aria-describedby` lists the error id first, then help; `aria-invalid="true"` on invalid fields; `aria-required="true"` on required fields; the error summary is focused and announced through the assertive live region.

**DS-CMP-22 Toast**

- Anatomy: stacked at the bottom inline-end corner (at most 3 visible, newest at the bottom), 360 px wide, E2, `--radius-lg`, 12 px padding: 16 px tone icon, message (`body-sm`, `--fg-1`, at most 2 lines), optional single action (link button, for example "View journal run"), Close button.
- Tones: neutral, positive, warning, negative.
- Timing: positive and neutral toasts without an action dismiss after 6 s; the timer pauses on hover and focus. Toasts with an action, and warning or negative toasts, stay until dismissed (WCAG 2.2.1 Timing Adjustable).
- Rules: toasts confirm outcomes; they are never the only record of an outcome (the activity timeline records it) and never ask for a decision. No "Undo" on accounting commands.
- ARIA: a toast region `role="region" aria-label="Messages"`; positive, neutral and warning toasts `role="status"`; negative toasts `role="alert"`. Focus does not move to toasts. `Alt+T` moves focus to the newest toast and Esc returns focus to where it was; the shortcut is listed in the keyboard shortcuts dialog.

**DS-CMP-23 Empty state**

- Anatomy: placed inside the empty region, start-aligned, max width 480 px, 48 px top padding: title (`title-sm`, `--fg-1`) naming what belongs here; description (`body-sm`, `--fg-2`, at most 2 sentences) stating why it is empty and what to do; primary action (the next step); optional secondary link (for example "Load the sample SaaS dataset" in sandbox and demo tenants, or "Read the import guide"). An optional 20 px `--fg-3` icon may sit before the title. No illustrations, clip-art or large icons (research 02 §5; D-62).
- Variants: first use; no results for filters ("No contracts match these filters." with "Clear filters"); nothing to do ("No requests are waiting for you. Requests you can approve appear here."); access-limited ("You do not have access to journals for US02. Ask a tenant administrator for the Journals role.").
- Copy examples:

| Region | Title | Description | Primary action |
|---|---|---|---|
| Contracts | No contracts yet | Contracts arrive from imports, integrations or the API. Start with a template or connect a source. | Import contracts |
| Schedules | No schedules for Sep 2026 | Schedules appear once contracts in this entity and book are computed. | Go to Contracts |
| Journals | No journal runs for Sep 2026 | Run journals after schedules are computed to produce balanced entries for the GL. | Run journals |
| Approvals | No requests waiting for you | Requests you can approve appear here, oldest first. | — |
| Exception queue | No exceptions | Rows that fail validation during imports and integrations appear here for correction. | View imports |
| Policies › SSP books | No SSP book versions | An SSP book holds standalone selling prices by product and effective date. | Create SSP book |

- ARIA: the title is a heading at the region's next level; no live region.

**DS-CMP-24 Progress and background jobs**

- Long-running commands return 202 with a job resource (D-45). The UI shows progress where the result will appear; nothing blocks the page.
- Anatomy (inline job indicator): label ("Recalculating 14 contracts"), determinate bar (4 px, track `--bg-active`, fill `--accent-solid`), counts ("412 of 1,204"), elapsed time (DS-FMT-24), Cancel when the job supports it. When the total is unknown, the indeterminate bar (DS-MOT-01). On completion the indicator is replaced by the result summary and a toast.
- Job outcomes are reported in place and by a toast (DS-CMP-22). A failed job also raises a `JOB_FAILED` notification (PRD NTF-05). The notifications panel has no jobs section (DS-CMP-05).
- Spinners (16 px) appear only inside buttons, inputs and the refreshing grid bar. Full-page spinners, blocking overlays and query timings are forbidden (DS-AP-09).
- States: queued, running, succeeded, failed (negative banner with the job id and Retry), cancelled.
- ARIA: `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax` and `aria-valuetext="412 of 1,204 contracts"`; completion is announced politely and failure assertively.

**DS-CMP-29 Banner**

- Anatomy: fills its container width; `--radius-md` inside panels, square in the global region; 10 × 12 px padding; fill `--<tone>-bg`, 1 px `--<tone>-border`; 16 px tone icon; title (`body-sm`, 600) and message (`body-sm`, `--fg-1`); optional link-button actions; a dismiss button only for non-blocking info banners.
- Uses: period locked ("Sep 2026 is locked for US01. Late events post to Oct 2026 with origin period Sep 2026."; D-19), stale figures, pending approval on the record, sandbox tenant, form error summary, connectivity.
- ARIA: a banner present on load is a static element with a heading. A banner inserted after load uses `role="status"` (info, positive, warning) or `role="alert"` (negative).

**DS-CMP-30 Skeleton**

- Static `--bg-subtle` blocks, `--radius-sm`, shaped like the final content (text lines at 60–90% width, KPI values 8ch, grid rows at `--row-h`). No shimmer (DS-MOT-02). Shown only after a 150 ms delay, to avoid flashes.
- ARIA: the loading region has `aria-busy="true"` and a visually hidden "Loading <region name>" text.

**DS-CMP-31 Segmented control**

- Anatomy: a track (`--bg-subtle`, `--radius-md`, 2 px padding) holding 2 to 5 equal-width options, each `--control-h-sm` high with a `body-sm` weight 500 label and an optional 16 px icon. Rest `--fg-2`; hover `--fg-1`; the selected option has a `--bg-surface` fill, a 1 px `--border-control` edge (C57: 3.35:1 light, 3.62:1 dark) and `--fg-1` text.
- Use: mutually exclusive view switches such as Chart / Table, Month / Quarter / Year and Transaction / Functional / Reporting currency. Not for navigation (use tabs, DS-CMP-07) and not for settings that need Save.
- States: rest, hover, selected, focus-visible (ring on the focused option), disabled option (`--fg-disabled` with a tooltip giving the reason).
- Keyboard (APG Radio Group): Tab focuses the selected option; Left/Right or Up/Down move and select (mirrored in RTL); Tab leaves the group.
- ARIA: `role="radiogroup"` with `aria-label`; options `role="radio"` with `aria-checked`; roving `tabindex`.

**DS-CMP-32 Tour step popover**

A named composition for guided tours (SF-25; SCREENS_B §11.2), built from existing parts. It adds no token and no visual pattern (SCREENS_B:OQ-B-27 resolved by D-76).

- Anatomy: a non-modal dialog 360 px wide on the DS-CMP-05 panel surface (E2, `--bg-raised`, `--radius-lg`, `--shadow-popover`, `--panel-pad`), anchored beside the stop's target element, or below it when there is no room beside it. Content: the step counter "Stop <n> of <total>" (`caption`, `--fg-3`); the title (`title-sm`, `--fg-1`); the body (`body-sm`, `--fg-2`, at most three sentences); a footer with DS-CMP-20 buttons "End tour" (ghost), "Back" (secondary; not rendered on stop 1) and "Next" (primary; "Finish" on the last stop).
- Target: a 2 px `--border-control` outline with a 2 px offset on the target element, a 3:1 boundary and not an accent use (DS-BR-09). There is no scrim, and the page stays operable.
- States: stop shown; missing anchor ("This stop is not available in this workspace." with "Next"); skipped stop ("Skipped: your roles do not include <permission label>.").
- Keyboard: opening a stop moves focus to the popover heading. Tab moves through the popover buttons and then into the page, because nothing traps focus. Esc or "End tour" closes the tour and returns focus to the Help menu button.
- ARIA: `role="dialog"` without `aria-modal`, named "Stop <n> of <total>: <title>" and `aria-describedby` its body; the target carries `aria-describedby` the popover while the stop is active; each stop change is announced politely with the dialog name.

## 8. Accessibility

eRev Cloud targets **WCAG 2.2 Level AA** on every screen in `docs/design/SCREENS.md`, in both themes and both densities (D-60; closes M-DES-03).

| Id | Requirement | WCAG 2.2 | Verified by |
|---|---|---|---|
| DS-A11Y-01 | Conformance target is AA for all screens; no serious or critical axe violations (G8) | all A and AA | DS-VER-05 |
| DS-A11Y-02 | Focus ring: `:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }`. Grid cells and list rows use `outline-offset: -2px` so sticky headers and pinned columns cannot clip it. Removing outlines without this replacement is an error **[lint]** | 2.4.7, 1.4.11 | DS-LINT-13, DS-VER-01 |
| DS-A11Y-03 | Focused elements are never fully hidden by sticky headers, the condensed record header, the totals row or toasts: scroll containers set `scroll-padding-block-start` and `scroll-padding-block-end` to the sticky heights, and grids scroll the focused cell into view after accounting for pinned columns | 2.4.11 | DS-VER-04 |
| DS-A11Y-04 | Colour is never the only carrier of meaning: status chips have text and icons; grid links have dotted underlines; diffs have markers; chart series have direct labels or legends plus table views; "Awaiting trigger" marks are hatched | 1.4.1 | Review, DS-VER-06 |
| DS-A11Y-05 | Contrast: every token pair in §2.6 meets 4.5:1 (text) or 3:1 (UI and marks), in both themes | 1.4.3, 1.4.11 | DS-VER-01 |
| DS-A11Y-06 | Zoom and reflow: content works at 200% text zoom and at 320 CSS px width, except two-dimensional data grids and charts, which may scroll in both directions inside their own viewport (the 1.4.10 exception for data tables) | 1.4.4, 1.4.10 | DS-VER-05 |
| DS-A11Y-07 | Text spacing overrides (line height 1.5, paragraph spacing 2em, letter spacing 0.12em, word spacing 0.16em) cause no loss of content. Single-line grid cells may truncate but expose the full text through the tooltip on focus and through the record view | 1.4.12 | DS-VER-05 |
| DS-A11Y-08 | Live announcements: the shell mounts one polite region (`role="status"`) and one assertive region (`role="alert"`), used only through an `announce(message, politeness)` helper. Announce route changes, context changes, filter result counts (debounced 500 ms), job completion (polite) and failure (assertive), and validation summaries (assertive). Identical messages within 1 s are dropped | 4.1.3 | DS-VER-04 |
| DS-A11Y-09 | Landmarks and headings: banner, primary `nav`, `main`, `aside` for Explain, toast region; one `h1` per route; skip link first in the Tab order | 1.3.1, 2.4.1, 2.4.6 | DS-VER-05 |
| DS-A11Y-10 | Keyboard: all functionality is operable by keyboard with no traps (modal dialogs trap focus and release with Esc); every drag has a keyboard or button alternative; single-key shortcuts are off while typing and can be turned off | 2.1.1, 2.1.2, 2.1.4, 2.5.7 | DS-VER-04 |
| DS-A11Y-11 | Grid semantics: interactive grids use APG Grid or Treegrid (DS-CMP-10). Moving between columns announces the column header; moving between rows announces the row header (identifier column, `role="rowheader"`); edit mode announces "Editing <column>, <value>"; sort changes announce "Sorted by <column>, ascending"; virtualized rows keep a correct `aria-rowindex` | 1.3.1, 4.1.2 | DS-VER-04 |
| DS-A11Y-12 | Money, dates and identifiers: DS-FMT-29 for negatives; truncated UUIDs have accessible names with the full value ("ID c3f1a9d2 ending 9a2e"); tabular data keeps the currency in the accessible name where it is only visual in a heading (DS-CMP-26) | 1.3.1 | DS-VER-03 |
| DS-A11Y-13 | Charts: `figure` with a text summary, a complete Table view, keyboard point navigation, no animation, hatch pattern for Awaiting trigger | 1.1.1, 1.4.1 | DS-VER-05 |
| DS-A11Y-14 | Reduced motion: DS-MOT-03. Nothing flashes more than 3 times per second | 2.3.1 | DS-VER-07 |
| DS-A11Y-15 | Forced colours: under `@media (forced-colors: active)` borders, dividers and selection edges use system colours (`CanvasText`, `Highlight`), focus rings use `Highlight`, chips keep text and icons, chart marks switch to patterns | 1.4.11 | DS-VER-07 |
| DS-A11Y-16 | Target size of at least 24 × 24 CSS px (DS-DEN-03) | 2.5.8 | DS-VER-08 |
| DS-A11Y-17 | Accessible authentication: sign-in and TOTP fields allow paste and password managers (`autocomplete="username"`, `current-password`, `one-time-code`); no cognitive puzzles | 3.3.8 | DS-VER-04 |
| DS-A11Y-18 | Consistent help: the Help menu is in the same top-bar position on every page | 3.2.6 | Review |
| DS-A11Y-19 | Redundant entry: wizards keep entered data across steps; a failed confirmation keeps the typed reason; saved mapping presets prefill imports | 3.3.7 | DS-VER-04 |
| DS-A11Y-20 | Error prevention for financial data: commands that change accounting data are confirmed (DS-CMP-11), routed through maker-checker (DS-CMP-16), or reversible by a reversal entry | 3.3.4 | Review |
| DS-A11Y-21 | Errors are identified in text, linked to fields and suggest a correction (DS-CMP-21) | 3.3.1, 3.3.3 | DS-VER-04 |
| DS-A11Y-22 | Timing: session expiry is warned at least 2 minutes ahead with "Stay signed in"; toasts with actions do not auto-dismiss (DS-CMP-22) | 2.2.1 | DS-VER-04 |
| DS-A11Y-23 | `<html lang>` equals the UI locale; `<html dir>` equals the locale direction | 3.1.1 | DS-VER-09 |

Screen-reader smoke tests run with VoiceOver on macOS Safari for the journeys named in SCREENS.md. NVDA with Firefox is part of supervisor QA (G12) [A: the build machine is macOS].

## 9. Internationalization

Closes M-DES-04. 1.0 ships an English interface with locale-aware formats, and is structurally ready for other languages and right-to-left scripts.

| Id | Requirement |
|---|---|
| DS-I18N-01 | **UI language.** 1.0 ships `en`. Every user-facing string lives in a message catalogue (`en.json`, keys namespaced by feature, for example `contracts.list.empty.title`). Sentences are never concatenated from fragments. Placeholders are named (`{customer}`); plurals use separate keys selected with `Intl.PluralRules` (`contracts.count.one`, `contracts.count.other`). [J] No i18n library is added; the catalogue helper is a small in-house function over native `Intl`. |
| DS-I18N-02 | **Two locale settings per user.** `ui_locale` (language of strings; 1.0: `en`) and `format_locale` (BCP 47 tag for number grouping, decimal separator and first day of the week; default from `navigator.language`, editable in the profile). |
| DS-I18N-03 | **What varies by `format_locale`:** grouping and decimal separators (`1,234.56` en-US, `1.234,56` de-DE, `1 234,56` fr-FR); percent spacing as `Intl` produces it; first day of the week in date pickers. **What never varies by locale:** the negative style, which is a tenant setting (DS-FMT-06); ISO currency codes (DS-FMT-05), minor units from ISO 4217 (DS-FMT-03), the `DD MMM YYYY` date pattern (DS-FMT-16), the 24-hour UTC timestamp (DS-FMT-17), Latin digits, and the fiscal calendar (entity configuration, not locale). |
| DS-I18N-04 | **Parsing input.** Money and number inputs parse with the `format_locale` separators and echo the interpreted value on blur. Canonical API-style input (`-1234.56`, no grouping) is accepted in locales whose decimal separator is `.`. Unit tests cover en-US and de-DE, including the ambiguous `1.234` in de-DE (parsed as 1234). |
| DS-I18N-05 | **Text expansion.** Layouts tolerate strings 35% longer than English: buttons size to content; form labels wrap; tabs and grid headers truncate with tooltips; no fixed-width text containers except grid columns. |
| DS-I18N-06 | **Pseudo-localization.** Development and e2e builds accept `?pseudo=1`, which renders every catalogue string with accented characters and 35% padding. A Playwright smoke test captures three screens in pseudo mode for review (DS-VER-09). |
| DS-I18N-07 | **Right-to-left readiness.** Layout uses logical properties only (`ms-`, `me-`, `ps-`, `pe-`, `start-`, `end-`, `border-s`, `border-e`, `rounded-s`, `rounded-e`, `text-start`, `text-end`); physical directions are errors **[lint]**. `<html dir>` follows the locale. The directional icons listed in DS-ICO-08 receive Phosphor's `mirrored` prop when `dir="rtl"`. Amounts, identifiers, dates, formulas and code are isolated as LTR (`<bdi>` or `unicode-bidi: isolate; direction: ltr`). Chart time axes stay left-to-right. No RTL language ships in 1.0; the RTL smoke test (DS-VER-09) proves the shell lays out mirrored without overlap. |
| DS-I18N-08 | **Time zones.** Effective dates are plain dates in the entity's time zone (D-19) and are never converted in the browser (DS-FMT-16). Timestamps display in UTC (DS-FMT-17). **Instants picked and shown as days (rev 1.6; supervisor ruling R-59).** Where the API stores an instant and the screen works in days, the day is the UTC date of the instant (the DS-FMT-17 date part), and a picked date goes on the wire through the format module (`docs/dev-guide.md` DG-FE-20): the effective date of a versioned configuration (04 SC-V `effective_from`) as 12:00:00Z of that date, so that the date picked is the date shown and the entity-local date equals it for every zone from UTC−12 to UTC+11; a validity window in platform time (an SoD exception, 04 T-PLT-14) as 00:00:00Z of its first day to 23:59:59Z of its last day. Known limitation: an entity beyond UTC+11 reads the next day (item CFG-EFFECTIVE-DATE-1). |
| DS-I18N-09 | **Currency metadata.** Minor units and currency names come from the API currency reference. `Intl.DisplayNames(uiLocale, { type: "currency" })` may supply the display name shown in currency pickers. |
| DS-I18N-10 | **Collation.** Client-side sorting of short lists uses `Intl.Collator(format_locale, { numeric: true, sensitivity: "base" })`. Grids sort on the server. |
| DS-I18N-11 | **No text in images or icons.** Icons carry no letters; the monogram is the only glyph mark and is not translated. |

## 10. UI copy

| Id | Rule |
|---|---|
| DS-CPY-01 | Use the D-02 vocabulary: navigation labels exactly as listed; "Scheduled" and "Awaiting trigger" for amounts; "Allocation adjustment"; "Contract liability", "Contract asset", "Unbilled receivable". In labels use "obligation"; in help text spell out "performance obligation" on first use. |
| DS-CPY-02 | Forbidden terms in UI source and copy: "Revenue Desk 360", "Planned revenue", "Revenue planned", "Unplanned", "Carve", "Carves", "Carve-in", "Carve-out", "Revi", "POB's", "net position" and "Unbilled A/R", matched case-insensitively as whole words, and any signed "position" (D-02, D-12) **[lint]** (DS-LINT-19, `make vocab-check`). Legacy strings such as "Unbilled A/R" appear only in the SF-26 legacy transition help and in the legacy export and template column definitions (PRD LTM-O5; REQ-UX-010; D-33). |
| DS-CPY-03 | Sentence case (DS-BR-10). No trailing period on labels, buttons, headings or chips; full sentences in descriptions and messages end with a period. |
| DS-CPY-04 | Messages say what happened and what to do next: "Could not save the policy. Check the highlighted fields." No "Oops", no blame, no exclamation marks (warning **[lint]**), no emoji (**[lint]**). |
| DS-CPY-05 | Confirmations name the object and the consequence: "Void contract C-000123? Its schedules reverse in Sep 2026 and the change goes to approval." |
| DS-CPY-06 | Cite the Codification in help and Explain as `ASC 606-10-32-28` and IFRS as `IFRS 15.74`. |
| DS-CPY-07 | Allowed abbreviations in labels: SSP, FX, GL, RPO, VC, ISO, API, CSV, XLSX. Each is spelled out in its tooltip or help text. |
| DS-CPY-08 | AI copy never uses the first person and always identifies itself as a proposal (DS-CMP-25). |

## 11. Anti-patterns

Each anti-pattern is either linted (§12) or checked in designer QA (G12).

| Id | Anti-pattern | Instead | Detection |
|---|---|---|---|
| DS-AP-01 | Default Tailwind palette classes and the grey-card look (D-62) | Token utilities on warm neutrals with hairlines | DS-LINT-02 |
| DS-AP-02 | Identical card grids as the main layout, such as a 2 × 2 launcher of recent lists (research 02 img 15) | Worklists, KPI strips and grids with filters and counts | Review |
| DS-AP-03 | Centred hero copy or centred page content inside the app (D-62) | Start-aligned content; centred only for the modal dialog box itself | Review |
| DS-AP-04 | Decorative gradients, glass, blur, glow or neon (D-61) | Flat surfaces and hairlines | DS-LINT-04, DS-LINT-05 |
| DS-AP-05 | Emoji, smileys and clip-art illustrations (research 02 img 01, 15) | Text and Phosphor icons | DS-LINT-06, review |
| DS-AP-06 | KPI values in several unrelated colours (research 02 img 06) | Neutral ink values; colour only for state | Review |
| DS-AP-07 | Nested tab bars in one panel; filled black pill tabs | One flat underline tab bar per panel | Review |
| DS-AP-08 | Mixed number formats, currency symbols, red negatives, `true`/`false` (research 02 §3.2) | §6 through the format module | DS-LINT-09, DS-VER-03 |
| DS-AP-09 | Blocking full-page spinners and visible query timings (research 02 img 03) | Async job progress in place (DS-CMP-24) | Review |
| DS-AP-10 | Truncated amounts, identifiers or headers inside in-card horizontal scrollbars | Autosized money and id columns; grid viewport scrolling with a pinned first column | Review |
| DS-AP-11 | Meaning carried only by red and green (old and new values, in and out) | Markers, labels and parentheses plus colour | Review |
| DS-AP-12 | Pie, donut, radial, 3D, dual-axis or animated charts (research 02 img 31) | Bars, bridges, stacked time bands, sparklines, tables | DS-LINT-08 |
| DS-AP-13 | Rows as separated shadowed strips (research 02 img 23) | Hairline-divided grid rows | DS-LINT-04, review |
| DS-AP-14 | A modal to announce success; a toast that demands a decision | Toast for outcomes; modal for decisions | Review |
| DS-AP-15 | Placeholder as label; submit disabled without a stated reason | Visible labels; errors reported on submit | Review |
| DS-AP-16 | Letter-spaced uppercase eyebrow labels; text below 12 px | Sentence-case captions at 12 px or more | DS-LINT-17, review |
| DS-AP-17 | Arbitrary shadows, radii, z-index values or font sizes | Tokens | DS-LINT-04, DS-LINT-11 |
| DS-AP-18 | "AI look": violet accents, gradient borders, sparkles on non-AI surfaces, chat bubbles for accounting commands | DS-CMP-25 dashed proposal block; Sparkle only on AI surfaces | DS-LINT-07 (Sparkle import allowlist), review |
| DS-AP-19 | A signed contract "position" (D-12) | Labelled balances | Review, DS-LINT-19 |
| DS-AP-20 | Money parsed into JavaScript numbers or summed in the browser | API totals; string decimals | DS-LINT-09 |
| DS-AP-21 | Links distinguishable only by colour | Underlines (dotted in grids) | Review |
| DS-AP-22 | Mixed icon libraries, or inline SVG icons | Phosphor only | DS-LINT-07 |
| DS-AP-23 | Colour literals in inline `style` objects | Tokens through classes or `var()` | DS-LINT-01, DS-LINT-16 |
| DS-AP-24 | Count-up number animations and chart entry animations | Static figures | DS-LINT-08, review |

## 12. Design-check lint

- **DS-LINT-00.** `make design-check` (DG-MK-design-check) runs `scripts/design_check.py`, a single dependency-free Python 3.12 script, with configuration `scripts/design_check.toml` (`docs/dev-guide.md` §0.5). It is part of `make lint`, the lint stage of `make ci` (DG-MK-lint). It scans `frontend/src/**/*.{ts,tsx,css,json}` and prints `path:line:col DS-LINT-NN message`. It exits 1 on any error. Warnings are printed and counted but do not fail the run. DS-LINT-19 is the one rule in the table below that `scripts/design_check.py` does not implement: `make vocab-check` (DG-MK-vocab-check) implements it, and `make lint` runs both targets.
- Paths named by the rules (`docs/dev-guide.md` §0.5 and §8.1; `scripts/design_check.toml` states each once):

| Rule term | Path |
|---|---|
| Token copy | `frontend/src/styles/tokens.css` |
| Icon registry module | `frontend/src/components/icons/registry.ts` |
| Icon directory | `frontend/src/components/icons/` |
| Chart module directory | `frontend/src/components/charts/` |
| AI component directory | `frontend/src/components/ai/` |
| Format module | `frontend/src/lib/format/` |
| Generated API types | `frontend/src/lib/api/schema.d.ts` |
| Lint fixtures | `scripts/design_check_fixtures/` |
| Theme and density bootstrap (DS-DEN-01; not scanned) | `frontend/public/theme-init.js` |

- Suppression: a line comment `design-check-ignore DS-LINT-NN: <reason>` on the same or preceding line suppresses one rule on one line. A suppression without a reason is itself an error. DS-LINT-01 to DS-LINT-06, DS-LINT-14, DS-LINT-15 and DS-LINT-23 cannot be suppressed.
- Global exclusions: `frontend/src/styles/tokens.css` (checked by DS-LINT-14 and DS-LINT-15 instead), the generated API types, and the lint fixtures directory. Test files (`*.test.ts`, `*.test.tsx`) are excluded from DS-LINT-01 and DS-LINT-09 only.

| Id | Severity | Applies to | Detects (Python `re` patterns; `CLS` means inside a `className`/`class` string, a `cn()`/`clsx()` argument, or a `@apply` line) | Message |
|---|---|---|---|---|
| DS-LINT-01 | error | `.ts`, `.tsx`, `.css` | Colour literals: `(?<![\w&/])#(?:[0-9a-fA-F]{3,4}\|[0-9a-fA-F]{6}\|[0-9a-fA-F]{8})\b` in string literals, JSX attribute values or CSS values; `\b(?:rgba?\|hsla?\|hwb\|lab\|lch\|oklab\|oklch\|color-mix)\(`; named colours as values of `fill`, `stroke`, `color`, `background`, `backgroundColor`, `borderColor`, `stopColor`: `(?:fill\|stroke\|color\|background(?:Color)?\|borderColor\|stopColor)\s*[=:]\s*["'{\x60]\s*(?:white\|black\|red\|green\|blue\|gr[ae]y\|orange\|yellow\|purple\|pink)\b`. Allowed values: `var(--*)`, `currentColor`, `transparent`, `inherit`, and CSS system colours inside `@media (forced-colors: active)` | "Use a colour token." |
| DS-LINT-02 | error | `.ts`, `.tsx`, `.css` | Default Tailwind palette utilities in CLS: `\b(?:[\w-]+:)*!?-?(?:bg\|text\|border(?:-[xytrblse])?\|ring(?:-offset)?\|outline\|fill\|stroke\|from\|via\|to\|divide\|placeholder\|caret\|accent\|decoration\|shadow\|inset-shadow\|drop-shadow)-(?:slate\|gray\|zinc\|neutral\|stone\|taupe\|mauve\|mist\|olive\|red\|orange\|amber\|yellow\|lime\|green\|emerald\|teal\|cyan\|sky\|blue\|indigo\|violet\|purple\|fuchsia\|pink\|rose)-(?:50\|[1-9]00\|950)(?:/\d{1,3})?\b` and `\b(?:[\w-]+:)*(?:bg\|text\|border\|ring\|fill\|stroke\|outline\|divide\|decoration)-(?:white\|black)\b`. These utilities do not exist after the namespace reset in `tokens.css`, so a match is always a mistake | "Default palette class; use a token utility (for example `bg-surface`, `text-fg-2`)." |
| DS-LINT-03 | error | `.ts`, `.tsx`, `.css` | Arbitrary colour values in CLS: `\b(?:bg\|text\|border\|ring\|outline\|fill\|stroke\|from\|via\|to\|shadow\|decoration\|caret\|accent\|placeholder\|divide)-\[(?!var\(--)`, and `-(?:\[\|\()(?:#\|rgb\|hsl\|oklch)` | "Arbitrary colour value; use a token." |
| DS-LINT-04 | error | `.ts`, `.tsx`, `.css` | Shadows and blur outside tokens: CLS `\b(?:shadow\|inset-shadow\|drop-shadow)-(?!popover\b\|overlay\b\|none\b)[\w\[\]\(\)/.-]+`, `\bdrop-shadow\b`, `\bbackdrop-(?:blur\|filter)`, `\bblur(?:-[\w\[\]]+)?\b` in CLS; style objects `\bboxShadow\s*:`; CSS `box-shadow\s*:` and `backdrop-filter\s*:` and `filter\s*:\s*[^;]*blur` | "Only `shadow-popover` and `shadow-overlay` exist; no blur." |
| DS-LINT-05 | error | `.ts`, `.tsx`, `.css` | Gradients: CLS `\bbg-(?:linear\|radial\|conic\|gradient)-`; CLS `\b(?:from\|via\|to)-(?:[\w\[]\|\()`; CSS or strings `(?:linear\|radial\|conic)-gradient\(`; JSX `<(?:linearGradient\|radialGradient)\b` | "Gradients are not part of the design system." |
| DS-LINT-06 | error | `.ts`, `.tsx`, `.json` (message catalogues) | Emoji and pictographs in string literals, JSX text and catalogue values, with the pattern written using escapes: `[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u231A\u231B\u23E9-\u23F3\u23F8-\u23FA\uFE0F\u200D]` (U+1F000 to U+1FAFF includes regional-indicator flags; arrows such as U+2192 and the command glyph U+2318 are allowed) | "No emoji or pictographs in UI strings; use a Phosphor icon." |
| DS-LINT-07 | error | `.ts`, `.tsx` | Icon sources: imports from `lucide-react`, `react-icons`, `@heroicons/`, `@radix-ui/react-icons`, `@tabler/icons-react`, `@mui/icons-material`, `@fortawesome/`; inline `<svg` outside the icon directory and the chart module directory (the wordmark and monogram are live text, DS-BR-02, DS-BR-04); `@phosphor-icons/react` imported anywhere except the icon registry module (DS-ICO-02); the registry's `Sparkle` export imported outside the AI component directory | "Use the icon registry (DS-ICO-02)." |
| DS-LINT-08 | error | `.ts`, `.tsx` | Chart containment: `from ["']recharts["']` outside the chart module directory; importing `PieChart`, `Pie`, `RadialBar`, `RadialBarChart`, `Funnel`, `FunnelChart`, `Treemap`, `Sankey` from `recharts`; `isAnimationActive\s*=\s*\{?\s*true` | "Charts go through the chart module; no pies, funnels or animation." |
| DS-LINT-09 | error | `.ts`, `.tsx` | Formatting containment outside the format module: `\.toFixed\(`, `\.toLocaleString\(`, `\.toLocaleDateString\(`, `\.toLocaleTimeString\(`, `new\s+Intl\.(?:NumberFormat\|DateTimeFormat\|RelativeTimeFormat)\(`, `\bparseFloat\(`; anywhere: `new\s+Date\(\s*["'\x60]\d{4}-\d{2}-\d{2}["'\x60]\s*\)` | "Format through the format module (§6)." |
| DS-LINT-10 | error | `.ts`, `.tsx`, `.css` | Physical directions: CLS `\b(?:[\w-]+:)*-?(?:ml\|mr\|pl\|pr\|left\|right\|border-l\|border-r\|rounded-(?:l\|r\|tl\|tr\|bl\|br)\|scroll-(?:ml\|mr\|pl\|pr)\|inset-(?:l\|r))-[\w\[]`, `\b(?:text-left\|text-right\|float-left\|float-right)\b`; CSS `\b(?:margin\|padding\|border)-(?:left\|right)\s*:`, `(?<![\w-])(?:left\|right)\s*:`, `text-align\s*:\s*(?:left\|right)` (the chart module is exempt) | "Use logical properties (§9)." |
| DS-LINT-11 | error | `.ts`, `.tsx` | Arbitrary tokens: CLS `\bz-(?:\d+\|\[(?!var\(--z-))`, `\brounded-\[`, `\bfont-\[`, `\btext-\[\d`, `\btracking-\[`, `\bleading-\[` | "Use z-index, radius and type tokens." |
| DS-LINT-12 | error / warning | `.ts`, `.tsx` | Error: arbitrary spacing and sizing values in CLS `\b(?:[\w-]+:)*-?(?:p[xytrblse]?\|m[xytrblse]?\|gap(?:-[xy])?\|space-[xy]\|w\|h\|min-w\|min-h\|max-w\|max-h\|size\|inset(?:-[xy])?\|top\|bottom\|start\|end\|translate-[xy]\|basis)-\[(?!var\(--)`. Warning: spacing multipliers outside DS-SP-01 `\b(?:[\w-]+:)*-?(?:p[xytrblse]?\|m[xytrblse]?\|gap(?:-[xy])?\|space-[xy])-(?:7\|9\|11\|14\|20\|24\|28\|32\|36\|40\|44\|48\|52\|56\|60\|64\|72\|80\|96)\b` | "Use the spacing scale or a layout token." |
| DS-LINT-13 | error | `.ts`, `.tsx`, `.css` | Focus removal: CLS containing `\boutline-(?:none\|hidden)\b` or `focus:outline-none` without `focus-visible:outline` in the same class string; CSS `outline\s*:\s*(?:none\|0)\b` | "Keep the focus ring (DS-A11Y-02)." |
| DS-LINT-14 | error | repository | `frontend/src/styles/tokens.css` is not byte-identical to `docs/design/tokens.css` (SHA-256 comparison) | "Token copy differs from docs/design/tokens.css. Run make tokens." |
| DS-LINT-15 | error | `docs/design/tokens.css` | The declarations inside `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }` differ from those in `:root[data-theme="dark"] { … }` (compared as an ordered list of `name: value` pairs) | "Dark theme blocks are out of sync." |
| DS-LINT-16 | error | `.tsx` | Inline style colours: `style=\{\{[^}]*\b(?:color\|background(?:Color)?\|border(?:Color)?\|fill\|stroke\|outlineColor)\s*:\s*(?!["'\x60]?var\(--)` | "Inline colour; use a token class or `var()`." |
| DS-LINT-17 | error | `.ts`, `.tsx`, `.css` | Text below 12 px: CLS `\btext-\[(?:[0-9]\|1[01])(?:\.\d+)?px\]`; CSS `font-size\s*:\s*(?:[0-9]\|1[01])(?:\.\d+)?px` or `font-size\s*:\s*0?\.[0-6]\d*rem` | "Minimum text size is 12 px." |
| DS-LINT-18 | warning | `.json` catalogues, JSX text | A string that ends with `!` | "No exclamation marks in UI copy." |
| DS-LINT-19 | error | The `make vocab-check` scope (DG-MK-vocab-check): `frontend/src/**/*.{ts,tsx,json}` and string literals under `backend/erev_api/**/*.py` | Implemented by `scripts/vocab_check.py` through `make vocab-check`, not by `scripts/design_check.py`. One list, the union of REQ-UX-010 and DS-CPY-02, matched case-insensitively (`re.IGNORECASE`) as whole words: `\b(?:Revenue Desk 360\|Planned revenue\|Revenue planned\|Unplanned\|Carves?\|Carve-in\|Carve-out\|Revi\|POB's\|net position\|Unbilled A/R)\b`. Allow-list: the legacy export and template column definitions (D-33) and the SF-26 legacy transition help catalogue (PRD LTM-O5), at the paths DG-MK-vocab-check names | "Forbidden vocabulary (D-02, D-12)." |
| DS-LINT-20 | warning | `.css` | `!important` outside `tokens.css` | "Avoid !important." |
| DS-LINT-22 | error | `.ts`, `.tsx` | Theme branching and colour composition in CLS: `\b(?:[\w-]+:)*dark:` and opacity modifiers on colour utilities `\b(?:bg\|text\|border\|ring\|fill\|stroke\|outline\|divide\|decoration)-[\w-]+/\d{1,3}\b` | "Themes switch through tokens; no `dark:` variants or opacity modifiers (DS-COL-25, DS-COL-26)." |
| DS-LINT-23 | error | `.ts`, `.tsx` outside the format module | Date construction on business data (05 TZ-10; DG-FE-20): `\bnew\s+Date\s*\(` and `\bDate\.parse\s*\(`. `Date.now()` stays allowed for durations and timers. Business dates (API values typed `format: date`, such as effective dates, period start and end dates and `as_of`) stay `YYYY-MM-DD` strings and reach the screen only through `formatDate` and `formatPeriod`; instants reach it only through `formatTimestamp`; money values never reach `Date` or float parsing (DS-LINT-09). The DS-LINT-23 fixture calls `new Date(line.period.end_date)` and produces DS-LINT-23 alone; the DS-LINT-09 fixture line with a date literal produces DS-LINT-09 and DS-LINT-23 | "Business dates stay YYYY-MM-DD strings; construct dates only in the format module (05 TZ-10)." |

- **DS-LINT-21.** The script ships with fixtures in `scripts/design_check_fixtures/`: one violating file per rule it implements (every DS-LINT rule except DS-LINT-19) and one clean file. `make design-check` first runs a self-test asserting that each fixture produces exactly its expected rule ids and that the clean file produces none **[test]**.

## 13. Verification

| Id | Check | Tooling | Gate |
|---|---|---|---|
| DS-VER-01 | Token contrast: a unit test parses `tokens.css`, converts each OKLCH token to sRGB with the algorithm in §2.1, and asserts every pair in §2.6 meets its requirement and matches the tabulated ratio within ±0.02, for both themes | Vitest | `make ci` |
| DS-VER-02 | Data-viz palettes: categorical adjacent CVD ΔE ≥ 8 (protanopia and deuteranopia, Machado 2009 severity 1.0) and normal-vision ΔE ≥ 15; ramps monotone with ΔL ≥ 0.06; ordinal light end ≥ 2:1; both themes (§5.2) | Vitest | `make ci` |
| DS-VER-03 | Format module, run once per tenant negative style (parentheses and minus, DS-FMT-06): every row of §6.4; ties rounding half away from zero (`"2.345"` USD → `2.35`; `"-2.345"` → `(2.35)` under parentheses and `−2.35` under minus); the negative percent, percentage-point, compact and delta forms (DS-FMT-09, DS-FMT-10, DS-FMT-15, DS-FMT-31); the accessible names of DS-FMT-29; JPY, BHD and CLF minor units; de-DE separators; and a plain date that does not shift with `TZ=America/Los_Angeles` and `TZ=Pacific/Auckland`. The XLSX number formats of DS-FMT-26 are asserted for both styles on the export writer | Vitest (format module); pytest (XLSX export writer) | `make ci` |
| DS-VER-04 | Component behaviour: ARIA roles and attributes and the keyboard tables of every DS-CMP entry (DataGrid, listbox, tabs, palette, tracker, diff, drawer, modal, toast, form errors, live announcements) | Vitest + Testing Library | `make ci` |
| DS-VER-05 | Screen audit: every SCREENS.md screen in light and dark (comfortable density), plus 5 key screens in compact density, with `@axe-core/playwright` using tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`; zero serious or critical violations; 200% zoom smoke on 3 screens | Playwright | `make e2e` (G8) |
| DS-VER-06 | Design gallery: a `/design` route (DG-FE-02), compiled only when `VITE_EREV_DESIGN_GALLERY=1`, which `make frontend`, `make dev-up` and `make e2e` set and `make build` and Docker images leave unset (`docs/dev-guide.md` §0.5) renders every DS-CMP component in every state and both themes, including the DS-CMP-32 tour popover. Its section 10 "Compositions" ends with the button "Throw a render error", which mounts a child that throws during render inside a nested route error boundary, so X:route-error renders without a failing API call (SCREENS_B §13). Playwright captures light and dark screenshots of the gallery and key screens for designer QA (G8, G12), and `screens.spec.ts` captures X:route-error after pressing that button (SCREENS_B §15) | Playwright | `make e2e` |
| DS-VER-07 | Emulation: `reducedMotion: "reduce"` (no transform transitions; static progress bar) and `forcedColors: "active"` (borders and focus visible) on 3 screens | Playwright | `make e2e` |
| DS-VER-08 | Target size: a script measures every interactive element's bounding box on 5 key screens in compact density; each is at least 24 × 24 px or meets the 2.5.8 spacing exception | Playwright | `make e2e` |
| DS-VER-09 | Internationalization smoke: `dir="rtl"` shell renders without horizontal overflow and with the rail on the right; `?pseudo=1` captures 3 screens | Playwright | `make e2e` |
| DS-VER-10 | Lint self-test (DS-LINT-21), the full design-check, and the DS-LINT-19 vocabulary check (`make vocab-check`) | Python | `make ci` |

## 14. Gaps closed

| Gap | How this document closes it | Sections |
|---|---|---|
| **M-DES-02** Design system: tokens, typography, density modes, chart palette, numeric formatting rules | OKLCH token set for both themes with a numeric contrast table and `tokens.css`; Inter and JetBrains Mono (OFL) with a type scale; comfortable and compact density tokens; categorical, sequential, diverging and ordinal palettes validated for colour-vision deficiency; chart specifications; one format per quantity | §2, §3, §4, §5, §6, `tokens.css` |
| **M-DES-03** Accessibility commitment: WCAG 2.2 AA, screen-reader grids, focus order | AA target with a criterion-by-criterion table; APG Grid and Treegrid semantics for the DataGrid; focus ring, focus-not-obscured and focus return rules; live-region policy; reduced motion and forced colours; verification gates | §7 (DS-CMP-10 and each component's ARIA), §8, §13 |
| **M-DES-04** Internationalization: locale number, date and currency formats; UI language; RTL | Message catalogue with plural rules; `ui_locale` and `format_locale`; what varies and what never varies by locale; locale-aware parsing; logical properties lint and RTL smoke test; pseudo-localization | §6, §9, DS-LINT-10 |

Contributions to gaps owned by other documents (not claimed as closed here): M-DES-05 controls UX (DS-CMP-11 reason fields, DS-CMP-16 diff and stale approvals, DS-CMP-18 dry-run diff); M-DES-06 report specifications (§5 chart specifications only; column definitions belong to SCREENS.md); M-DES-07 empty states (DS-CMP-23 copy rules); M-PM-07 notification bell (DS-CMP-05); C-02 display rule (DS-FMT-28 applies D-12).

## 15. Open questions for supervisor

OQ-01 to OQ-05 are closed by D-75. OQ-06 and OQ-07, raised in revision 1.1, are closed by D-76. Revision 1.2 raises no question (D-77). Other documents cite these questions as `DESIGN_SYSTEM:OQ-nn` (B1-027).

| # | Question | Ruling or recommended default | Status |
|---|---|---|---|
| OQ-01 | Money outside grids uses ISO codes and never currency symbols (DS-FMT-05). Some single-currency SMB tenants may expect `$`. | Keep ISO codes everywhere in 1.0. DS-FMT-05 is unchanged. | Resolved by D-75 (default adopted) |
| OQ-02 | Timestamps display in UTC with local time in the tooltip (DS-FMT-17). | Keep UTC in the interface and in evidence. DS-FMT-17 is unchanged. | Resolved by D-75 (default adopted) |
| OQ-03 | Code locations of the tokens copy, the design-check script, the icon registry, the format module, the chart module and the AI components. | The default was "use the proposed `web/` and `tools/` paths unless `docs/dev-guide.md` names others". The dev guide names others, so its §0.5 values bind: `frontend/src/styles/tokens.css`; `scripts/design_check.py` with `scripts/design_check.toml`; `frontend/src/components/icons/registry.ts`; `frontend/src/lib/format/`; `frontend/src/components/charts/`; `frontend/src/components/ai/`. Applied in DS-COL-00, DS-LINT-00, the §12 path table and DS-LINT-14 (B1-028). | Resolved by D-75 |
| OQ-04 | Build flag for the `/design` component gallery (DS-VER-06). | `VITE_EREV_DESIGN_GALLERY=1`, set by `make frontend`, `make dev-up` and `make e2e`; unset in `make build` and Docker images (`docs/dev-guide.md` §0.5; D-48a; B1-010). There is no `make dev` target. | Resolved by D-75 |
| OQ-05 | RPO time-band boundaries (DS-CH-03). | DS-CH-03 renders the bands the API returns. The boundaries are POL-201 `rpo.time_bands`, default `[12, 24]`: within 12 months, 13 to 24 months, after 24 months (REQ-RPT-009). The five-band proposal of revision 1.0 is withdrawn, because band boundaries are an accounting policy and `docs/03-REQUIREMENTS.md` and `docs/accounting/POLICIES.md` rank above this document (D-§0; B1-031). | Resolved by D-75 |
| OQ-06 | REQ-UX-006 and D-75 make the negative money style a tenant setting with default parentheses, but `docs/04-DATA_MODEL.md` T-PLT-31 lists no platform parameter for it, and 04 owns the literals (D-73). | 04 T-PLT-31 adds the platform parameter `ui.negative_number_style`: category `PLATFORM`; values `PARENTHESES` and `MINUS`; default `PARENTHESES`; legacy parity `PARENTHESES`; source REQ-UX-006. The value reaches the frontend with `GET /me` (API-R-03). Until 04 defines it, the format module applies the parentheses style. | Resolved by D-76 under the 04 name: 04 T-PLT-31 already holds `ui.negative_number_style` (`PARENTHESES` default, `MINUS`), so no second key is added (04 B3-D01; rev 1.3 names the 04 key in the proposal cell); `GET /me` returns `tenant_settings.negative_number_style` (API-S-Me). Applied in DS-FMT-06 |
| OQ-07 | DS-CMP-05 offers "Mark all as read", but API-R-03 has only `POST /me/notifications/{id}/read`. | 04 API-R-03 adds `POST /me/notifications/read-all` with a `before` timestamp, which marks the caller's unread notifications created at or before it. Until that command exists, the panel does not render "Mark all as read". | Resolved by D-76 (default adopted): 04 API-R-03 `POST /me/notifications/read-all` `{before}` returns `{marked}` (§16.12). Applied in DS-CMP-05 |
