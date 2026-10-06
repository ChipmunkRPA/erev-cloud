# eRev Cloud: goal and definition of done

| Field | Value |
|---|---|
| Owner | Team lead (supervisor session) |
| Date | 2026-09-11 |
| Status | Binding. Changes only by the supervisor. |
| Precedence | Highest. `docs/01-DECISIONS.md` refines it; nothing overrides it. |

## 1. Goal

Build **eRev Cloud 1.0**: an open-source (MIT), multi-tenant cloud ASC 606 / IFRS 15 revenue subledger. It must:

- carry forward everything legacy eRev does;
- look and feel like a modern RightRev-class product;
- aim to be the most capable, most explainable revenue recognition engine available for any industry and any company size.

Legacy eRev (`github.com/ChipmunkRPA/eRev`, read-only clone at `~/dev/erev-legacy`) is a single-file PySide6 Windows desktop app over SQLite. It has relative-SSP allocation, delivery and billing, prospective and retrospective modifications, POB-specific variable consideration, material rights, returns, and gross or delta journal entries, all driven by four Excel templates. eRev Cloud keeps its accounting depth and its "an accountant learns it in an hour" simplicity. It replaces the desktop shell with:

- a tenant-safe, auditable, SOX-grade platform;
- a React workbench;
- a deterministic engine in which every number can be explained.

The measurable ambition is the one stated in `docs/research/03-competitive-landscape.md` §11. No product, commercial or open-source, combines all of the following:

- full ASC 606 plus ASC 340-40;
- parallel books;
- deterministic, replayable, explainable output;
- self-service configuration with a first-class UI;
- an open licence.

eRev Cloud 1.0 does.

## 2. Scope (1.0)

`docs/03-REQUIREMENTS.md` is the governing requirements register and defines the detailed P0 list. The modules in scope are:

1. **Platform.** Tenancy (pooled, forced row-level security), authentication (password + TOTP MFA, OIDC-ready), roles, SoD, the approval engine, a hash-chained audit log, notifications, and a sandbox/scenario tenant.
2. **Reference data.**
   - legal entities and calendars;
   - currencies and FX rates;
   - chart of accounts and account-role mapping;
   - customers and related-party groups;
   - products/SKUs and bundles;
   - revenue policies (POB templates and assignment rules);
   - the SSP studio (versioned SSP books, methods, ranges, the historical SSP calculator, approval).
3. **Contracts and the five-step engine.**
   - contract identification and combination;
   - performance obligations, including distinct and non-distinct POBs, series, material rights, warranties, and principal vs agent;
   - transaction price: fixed consideration; VC with estimate and constraint; financing; noncash consideration; consideration payable to a customer;
   - allocation: relative SSP, discount and VC exceptions, residual, ranges;
   - recognition: point in time; ratable daily or monthly; output measures; milestones; cost-to-cost with EAC; right to invoice; usage and royalties; bill-and-hold; breakage; holds.
4. **Modifications.** Separate contract, prospective, cumulative catch-up and mixed modifications; POB-specific VC; terminations; subscription changes (upgrade, downgrade, co-term, renew, cancel); a guided classification and impact preview.
5. **Billing and balances.** Invoice and billing ingestion; contract asset, unbilled receivable, receivable and contract liability netted per contract per entity; refund liabilities and return assets.
6. **Contract costs and loss contracts.** ASC 340-40 capitalization, amortization and impairment; ASC 605-35 loss provisions.
7. **Books and currencies.** Parallel ASC 606, IFRS 15 and LEGACY (pre-606 delta) books; multi-currency per ASC 830 / IAS 21; multi-entity with intercompany pairs.
8. **Close and journals.**
   - period states per entity and book;
   - the close cockpit;
   - journal runs (summarized, balanced per entity/book/currency/period);
   - GL export (CSV plus adapter interface, with NetSuite and QuickBooks Online adapters exercised against mocks);
   - billing and GL reconciliations;
   - reopen with dual approval.
9. **Reports and disclosures.** Revenue waterfall; deferred revenue and contract balance rollforwards; RPO with time bands and practical expedients; disaggregation; modification register; contract history (versions); JE population export; the audit evidence pack; dashboards. Every figure drills down to its source.
10. **Data in.** The legacy four Excel templates as v1, modern CSV templates, the REST API with Idempotency-Key, and mock inbound adapters (Salesforce orders, Stripe subscriptions and invoices). The flow is upload → validate → dry-run diff → approve → commit, with row lineage and an exception queue.
11. **Forecast and scenarios.** What-if runs on the same engine in a scenario tenant; a deal-desk allocation preview.
12. **AI assistance, under human control.**
    - contract-review extraction proposals;
    - explaining a number;
    - anomaly flags on schedules;
    - a revenue Q&A that cites records.

    Tests use a fake provider. The AI never posts or changes accounting data without an audited human action.
13. **Migration.** Import a legacy `ASC606.db` (opening balances plus migrated history), replay legacy templates, and apply the legacy-parity policy preset.
14. **Operability.** Demo tenants seeded per industry cluster, a guided tour, OpenAPI 3.1, a runbook, a user guide, a migration guide, Dockerfiles, compose, and Terraform for GCP Cloud Run + Cloud SQL. The Terraform is artifacts only and is never applied.

## 3. Definition of done

eRev Cloud 1.0 is done when every item below holds and the evidence is recorded in `PROGRESS.md` (loop) or `docs/qa/` (supervisor).

| # | Gate | Evidence |
|---|---|---|
| G1 | Every `docs/BUILD_SPEC.md` item is ticked with evidence | `PROGRESS.md` |
| G2 | `make ci` is green: format, lint, type-check, backend tests, engine tests, frontend unit tests, build | Command output counts |
| G3 | **Legacy parity**: all 122 cases in `docs/legacy/golden/golden-tests.json` pass under the legacy-parity preset, or pass with the documented corrected value in `docs/legacy/DEVIATIONS.md` (each deviation approved by a revenue-accountant review) | `make parity` |
| G4 | **Accounting corpus**: 100% of the machine-readable answer keys in `docs/accounting/answer-keys/` pass exactly to the currency minor unit. The corpus covers every ASC 606 topic in research 04, every industry playbook in research 05, FX, multi-entity and modification scenarios | `make answer-keys` |
| G5 | **Invariants**: the Hypothesis property suite passes (allocations sum to the transaction price; recognition never exceeds allocation at completion; debits equal credits per entity/book/currency/period; rollforward opening + activity = closing; replay determinism) | `make properties` |
| G6 | **Isolation and immutability**: the RLS isolation suite, append-only ledger/audit tests and hash-chain verification pass on PostgreSQL | `make test-pg` |
| G7 | **Controls**: every system control designated 1.0 in `docs/03-REQUIREMENTS.md` has at least one test tagged `@pytest.mark.control("<id>")` | `make controls-report` |
| G8 | **UX**: every screen in `docs/design/SCREENS.md` is built; all Playwright journeys pass; light and dark screenshots reviewed; no serious or critical axe violations | `make e2e` |
| G9 | **Performance**: a seeded volume tenant with 10,000 contracts / 50,000 POBs / 24 months runs a full monthly close (schedules + journal run + rollforward) in ≤ 10 minutes locally; contract workbench API p95 ≤ 300 ms at that volume | `make perf` |
| G10 | **Demo**: demo tenants for at least six industry clusters load with realistic data; the guided tour completes; every navigable screen renders real data | Supervisor browser QA |
| G11 | **Docs and artifacts**: OpenAPI 3.1 exported; runbook, user guide and legacy migration guide written; Dockerfiles and compose build when a Docker daemon is available (otherwise recorded as supervisor-verification-needed); `terraform validate` passes if Terraform is installed | Files + command output |
| G12 | **Supervisor verification**: multi-role browser QA (preparer, reviewer/approver, controller, auditor, admin), designer visual QA and an independent revenue-accountant review of the parity deviations and answer keys, with findings fixed | `docs/qa/*` |

## 4. Out of scope for 1.0 (designed, not built)

- Live calls to third-party APIs (Salesforce, Stripe, NetSuite, QuickBooks, Intacct, Xero, D365). Adapters are built and tested against mocks only.
- SAML SSO and SCIM provisioning (interfaces reserved), and the dedicated-database silo tier.
- ASC 842 lessor accounting, and the insurance (944) and financial-instrument scopes, which are routed out with a scope flag.
- A Salesforce-native managed package and a GraphQL API.
- Applying Terraform, deploying to any cloud, publishing images, or pushing to any remote repository.

## 5. Standing constraints

- **Licence and clean room.** MIT. Learn from public RightRev and competitor material. Never copy their code, text, names of proprietary features, logos, screenshots or art into the product. Use our own terminology (`docs/01-DECISIONS.md` D-02).
- **Accounting authority.** The Codification is the authority for accounting behaviour. Where it permits a choice, the choice is a tenant policy with a documented default. Engine outputs for the corpus are asserted exactly, never approximately.
- **Money.** `Decimal` end to end, with floats trapped in the engine. Strings on the wire. Currency minor units per ISO 4217 at posting.
- **No network in tests.** AI is exercised only through a fake or mocked client. No credentials in code.
- **Shared machine.**
  - Use the Homebrew PostgreSQL 17 on 127.0.0.1:5432, only through the databases `erev`, `erev_test` and `erev_e2e` and the roles `erev_owner` and `erev_app`.
  - Never create, drop or alter other databases, roles or server settings.
  - Ports: API 8190, Vite 5270, e2e 8199/5279, compose web 8195 and Postgres 5436.
  - Stop processes only by the PID files in `.run/`. Never write to `/tmp`.
- **Git.** Stage explicit paths and commit atomically. Never push. The supervisor documents listed in `docs/01-DECISIONS.md` §0 are read-only for the loop.
