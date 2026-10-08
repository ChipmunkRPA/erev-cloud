# Backend baseline — October 7, 2026

Revision: `7c9b22d6cd8f0d293a0ee398be8ccd6c5653b761`, isolated checkout
`/private/tmp/erev-verification-waivers`, database `erev_rv_waivers`.
Full backend non-parity/non-answer-key/non-performance run. PID 36126 is terminal
and no longer exists. It ran uninterrupted; no reset or restart occurred.

Result: **51 failed, 9,970 passed, 1 skipped, 640 deselected, 3 xfailed** in
13,560.77 seconds (3h46m). Local evidence:
`/private/tmp/erev-verification-waivers.log` and
`/private/tmp/erev-verification-waivers.xml`.

This is historical evidence for the named revision, not verification of current main.
Subsequent changes include constraint/Step 1 review, sandbox monetary verification,
integration-owner notifications and import row coverage. Each failure below still
requires comparison with current code and a scoped rerun before disposition. Failures
may represent product defects, outdated expectations or environment differences;
none is dismissed on that basis without evidence. No deployment or accounting sign-off.

## Failures requiring triage

- `backend/tests/domain/close/test_lock_open_redirty_db.py::test_r112_j_a_waived_item_does_not_clear_the_gate_before_the_re_marking_has_succeeded`
- `backend/tests/domain/close/test_reconciliation_overtaken.py::test_an_event_recorded_and_computed_while_a_generation_runs_is_not_counted_as_read`
- `backend/tests/domain/demo/test_seed_scaffold.py::test_dg_mk_seed_requires_password`
- `backend/tests/domain/imports/test_commit_job_failed.py::test_job_failed_item_1_the_commit_hook_leaves_an_upload_that_ended_or_is_held`
- `backend/tests/domain/platform/test_audit_coverage.py::test_req_plt_019_categories_covered`
- `backend/tests/domain/platform/test_file_shred_order.py::test_file_shred_durable_order_1_a_completion_that_is_not_recorded_is_found_by_the_next_road`
- `backend/tests/domain/platform/test_file_shred_order.py::test_file_shred_durable_order_1_a_store_that_is_away_leaves_the_decision_and_alerts`
- `backend/tests/domain/platform/test_file_shred_order.py::test_file_shred_durable_order_1_a_completed_shred_is_completed_once`
- `backend/tests/domain/platform/test_sandbox_replay.py::test_recompute_runs_on_open_periods_before_the_close_replay`
- `backend/tests/domain/platform/test_sandbox_replay.py::test_a_differing_sandbox_output_is_a_determinism_mismatch`
- `backend/tests/domain/reports/test_combined_group_versions_db.py::test_the_schedule_lines_and_the_monitors_read_a_combined_member_once`
- `backend/tests/domain/reports/test_combined_group_versions_db.py::test_a_member_is_read_from_its_own_group_until_the_combined_group_is_computed`
- `backend/tests/domain/reports/test_combined_group_versions_db.py::test_a_contract_that_leaves_is_read_once_while_the_groups_await_their_computations[the leaver's group first]`
- `backend/tests/domain/reports/test_combined_group_versions_db.py::test_a_contract_that_leaves_is_read_once_while_the_groups_await_their_computations[the remaining group first]`
- `backend/tests/domain/reports/test_combined_group_versions_db.py::test_a_refused_computation_leaves_each_member_where_it_was_last_computed[failed]`
- `backend/tests/domain/reports/test_combined_group_versions_db.py::test_a_refused_computation_leaves_each_member_where_it_was_last_computed[quarantined]`
- `backend/tests/domain/reports/test_combined_group_versions_db.py::test_a_computation_job_that_fails_leaves_each_member_where_it_was_last_computed`
- `backend/tests/domain/reports/test_registers_access.py::test_audit_log_export_states_the_rows_of_the_list`
- `backend/tests/domain/reports/test_registers_close.py::test_out_of_period_register_k07`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_backup_script_keeps_the_backup_when_verification_fails`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_wrapped_restore_keeps_the_restore_directory_in_the_deployment`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_residual_restore_refuses_an_incoherent_baseline_before_any_connection`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_p2_p6_restore_binds_the_clone_pin_from_the_backup_never_the_host`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_p2_p6_restore_refuses_a_backwards_pin_before_any_mutation`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_p2_p6_operator_pin_override_moves_forward_only`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_p2_p6_restore_refuses_a_manifest_pin_that_differs_from_the_evidence`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_identity_stub_is_refused_outside_test_and_dev`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_diagnostics_never_echo_a_dsn_or_secret`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_diagnostics_sequence_under_one_pinned_second`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_r2_restore_refuses_incomplete_or_unbound_manifests`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_r1_restore_binds_owner_app_and_admin_to_one_target`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_residual_preflight_precedes_every_mutation`
- `backend/tests/unit/deploy/test_backup_restore_scripts.py::test_residual_symlinked_restore_parent_is_refused_before_any_mutation`
- `backend/tests/unit/deploy/test_docker_build.py::test_the_probe_program_reads_both_interpreters_and_the_whole_root_filesystem`
- `backend/tests/unit/deploy/test_supervisor_scripts.py::test_progress_lists_the_supervisor_targets`
- `backend/tests/unit/docs/test_artifacts.py::test_licence_and_notice`
- `backend/tests/unit/test_activation_lock_order.py::test_estimate_approval_locks_the_group_before_the_contract`
- `backend/tests/unit/test_activation_lock_order.py::test_estimate_approval_revalidates_the_basis_under_its_locks`
- `backend/tests/unit/test_audit_catalogue.py::test_sop_7_class_e_the_release_refuses_exactly_one_command_by_name`
- `backend/tests/unit/test_audit_log_reads.py::test_every_audited_object_type_has_a_label_or_is_listed_without_one`
- `backend/tests/unit/test_build_fixtures.py::test_check_mode_writes_nothing_and_detects_tamper`
- `backend/tests/unit/test_licence_check.py::test_repository_dependencies_pass`
- `backend/tests/unit/test_makefile_targets.py::test_dg_mk_00a_ok_line`
- `backend/tests/unit/test_migration_ops.py::test_dg_mk_db_reset_refuses_running_stack`
- `backend/tests/unit/test_migration_walk_entry_points.py::test_every_downgrade_under_tests_pg_starts_from_a_fresh_head`
- `backend/tests/unit/test_openapi_export.py::test_openapi_check_detects_stale_document`
- `backend/tests/unit/test_proc_sh.py::test_dg_run_10_start_reuse_stop_status`
- `backend/tests/unit/test_repository_layout.py::test_licence_is_mit_with_copyright`
- `backend/tests/unit/test_snapshot_export.py::test_monetary_state_is_the_stored_category_m_without_history`
- `backend/tests/unit/test_ssrf_guard.py::test_sar_15_private_relay_opt_in_admits_loopback_and_private_use[::ffff:10.0.0.1]`
- `backend/tests/unit/test_transition_pair_guard_revision.py::test_0130_re_renders_the_checklist_item_pairs`

## Current-main triage — October 7, 2026

The combined-group monitor case reproduces on main `2ca9791` (one failed in
17.02 seconds, `/private/tmp/combined-layer-current.log`). Its layer expectations
precede the individual-layer monitor changes in `5d48cb0` and `5b45532`.
The current reader aggregates persisted T-CON-18 movements by originating layer,
with consumption subtracted from that layer; stage 12 pools liabilities within the
combination group/entity/book and applies the configured FIFO consumption policy.

These fixture invoices are each event EV-000003. For the combined orders, September
revenue is 3,202.55 + 3,205.48 = 6,408.03. FIFO consumes this from the first invoice's
36,000 layer, leaving 29,591.97, while the second layer retains 48,000. Their total,
77,591.97, still equals 84,000 billed less 6,408.03 recognized. Contract-level report
balances remain 32,797.45 and 44,794.52; those separate assertions are retained.

Updated monitor expectations name the actual originating events and check standalone,
combined, deferred, refused, and partially recomputed membership states. No product
or financial calculation code changes. Full module verification: **17 passed in
89.20 seconds**, `/private/tmp/combined-layer-current-final.log`. Ruff and whitespace
checks pass. The seven combined-group failure entries above are resolved by these
expectation corrections; the other 44 baseline failures still require disposition.
This scoped result does not replace a full current-main baseline or accounting sign-off.

### Reconciliation timing and publication expectations

The reconciliation-generation interleaving failure reproduced on `c8fea89` in
10.98 seconds. A diagnostic assertion then demonstrated that the fixture's frozen
application time was 0.163 seconds ahead of database time. Its shared clock helper
starts one second ahead; the test incorrectly depended on setup consuming that second.
The case now sets its application time from the database before generation and asserts
both the initial ordering and the injected billing event's persisted recorded_at being
after the generated as_of_known_at. All original reconciliation and stale-gate assertions
remain. No production snapshot logic changed.

Two publication tests still asserted MIT. Updated these to validate the owner's published
PolyForm Noncommercial 1.0.0 license, the noncommercial-purpose section and required
copyright notice. Third-party component notices retain their checks; no license text changed.

All eight reconciliation timing cases initially passed in 47.59 seconds. Final run with
the additional persisted-event timestamp assertion and both complete publication test
modules: **18 passed in 44.02 seconds**,
`/private/tmp/reconciliation-and-publication-final.log`. Ruff/format/whitespace checks pass.
These three failures are resolved; **41 of the original baseline failures remain without
a current-main disposition**. This count is not a full current-main failure count.

### File-shred sweep workload isolation

The unmodified durability module on `1abb52b` passes alone: **6 passed in 70.22
seconds**, `/private/tmp/shred-order-current.log`. The original three failures
counted pending files belonging to other tests' tenants. The database fixture
retains tenants, and import-source tests intentionally mark sources shredded without
completing them. Each test also has its own temporary file store. A platform-wide
sweep therefore cannot be assumed to contain only one test's file workload.

A shared test helper now narrows the original sweep eligibility predicate to the
scenario's tenants. Durability tests retain their real storage, commit, retry and
alert code and exact assertions. The sandbox case includes BOTH production and
sandbox tenants, preserving source-key protection and archived-sandbox coverage.
No production sweep logic changed.

The first mixed run exposed the same issue in the sandbox test (3 completed versus
1): **11 passed, 1 failed**, `/private/tmp/shred-cross-suite-final.log`. After scoping
that case too, the complete import-source, durability and sandbox-shred modules pass
in one database session: **12 passed in 82.01 seconds**,
`/private/tmp/shred-cross-suite-verified.log`. Ruff/format/whitespace checks pass.
Three original failures and the newly exposed sandbox count issue are resolved;
**38 original baseline failures still await current-main disposition**.

### Audit summaries and snapshot replay

On `d90781b`, audit label coverage lacked the three new computation fact types:
fx_layer_movement, loss_provision_version and loss_provision_eac. All are written
through record_facts as aggregate summaries with null object_id, retaining their IDs
or bounded count/hash evidence in detail. They now appear explicitly in NO_LABEL;
the data-model documentation describes that convention. No financial calculation or
audit-event contents changed.

Audit-read unit tests, the complete audit API module and the two formerly failing
sandbox replay cases: **21 passed in 26.44 seconds**,
`/private/tmp/audit-labels-and-replay.log`. Those replay cases were already corrected
by dbb3e57's addition of FX/loss facts to the snapshot audit-support catalogue; this run
verifies them on current code. Three original failures resolved, leaving **35 original
failures without current-main disposition**.

The policy-override audit-catalogue failure remains open. Its database-walk fixture
uses a still-unsupported key, so that refusal proof remains valid; the catalogue also
needs to represent and exercise supported-key creation, which now writes an audit event.

### Supported policy-override creation audit coverage

The route catalogue now requires policy_override.create audit evidence for supported
creation instead of treating the whole command as refused. The real database-walk
scenario creates an obligation-level balance.right_to_consideration override.
Unsupported-key refusals have a separate case with the same exact rule, no request
audit event and no-write checks, including negative controls for extra writes and an
unexpected success. Refusal evidence cannot satisfy the successful-route walk.

Catalogue and focused database checks: **17 passed, 3 deselected in 23.49 seconds**,
`/private/tmp/policy-audit-catalogue.log`. Complete CTL-038 command-route audit walk:
**1 passed in 32.75 seconds**, `/private/tmp/policy-audit-full-route-walk.log`.
Ruff/format/whitespace checks pass. No production behavior changed.

One additional original baseline failure resolved; **34 remain without current-main
disposition**. The broader category gate's missing AI lifecycle evidence remains open;
it was not waived or marked passing by these changes.

### Estimate approval locks and SMTP literal normalization

Reproduced the two activation-lock-order failures and the IPv4-mapped SMTP
private-relay case on ef323e6: **3 failed, 117 passed in 2.53 seconds**
(`/private/tmp/lock-ssrf-before.log`). The approval stand-in did not understand
SELECT without FROM for the shared FX publication gate. It now verifies the exact
shared function, tenant namespace and hash seed and records its position before
the group/contract locks. Both approval expectations include that gate, including
at basis revalidation. The SMTP literal assertion expects canonical IP spelling;
DNS results still must equal the original checked resolver output. Refusal checks
are retained. No production changes.

Final complete two-module run: **120 passed in 2.25 seconds**,
`/private/tmp/lock-ssrf-verified.log`. In a separate process, disabling only
hold_fx_publication made both approval tests fail their order assertions as
expected (`/private/tmp/estimate-gate-negative.log`). Ruff, formatting and whitespace
checks pass. All processes are terminal. Three more original failures resolved;
**31 remain without current-main disposition**. This does not prove a green full
backend suite or independent accounting approval. No deployment.

### Backup archive portability

All 14 backup/restore-script failures shared the same earlier refusal on macOS:
BSD tar generated ._files outside files/. The existing failed-baseline restore case
reproduced on f9f5683 (1 failed in 1.74 seconds,
`/private/tmp/backup-tar-before.log`). A strengthened archive test adds explicit
macOS directory/file extended attributes, checks the exact member set and ciphertext
bytes, and invokes the real archive validator. It failed before the fix with the
same ._files refusal (1 failed in 1.15 seconds,
`/private/tmp/backup-archive-regression.log`).

The production backup command now sets COPYFILE_DISABLE=1 only for tar creation;
restore containment and link rules remain unchanged. Runbook contents are updated.
Complete script module: **29 passed in 77.31 seconds**,
`/private/tmp/backup-restore-verified.log`. Recovery validation module: **25 passed
in 0.11 seconds**, `/private/tmp/recovery-preflight-verified.log`. Bash syntax,
Ruff/format and whitespace checks pass. The 14 original script failures are resolved;
**17 original failures remain without current-main disposition**.

These tests use real archive creation/inspection in scratch directories and stub
pg_dump, verification and server identity; they are not evidence of a live recovery
drill or production readiness. No deployment or cloud changes. All runs terminal.

### Migration verification and snapshot export

On 9622f13, the scoped migration-entry/transition/snapshot modules produced
**2 failed, 42 passed in 1.56 seconds**, `/private/tmp/migration-pins-before.log`.
The task-signature downgrade test lacked a fresh-head reset. It now resets before
inserting its own histories, and the static walk inventory includes that test plus
the already-resetting Step 1 report-filter round-trip. No guard exemption added.

The historical 0130 body now compares with 0135's literal PREVIOUS. A new 0135
check compares BODY with the current renderer and requires the only changed line
to add PASSED>NOT_STARTED. Original 0130 additions and 0047 predecessor checks
remain intact. No migration or production code changes.

Final run: **47 passed in 12.62 seconds**, `/private/tmp/migration-pins-final.log`.
Includes both complete migration unit modules, all snapshot-export unit cases,
the real PostgreSQL task-signature downgrade refusal (retained rows and restored
FORCE RLS), and installed transition SQL/trigger drift verification. Snapshot
export's original failure was already fixed by dbb3e57 and is now reverified.
An intermediate run found one missing static inventory entry, corrected before
the final pass. Ruff/format/whitespace checks pass; all runs terminal.

Three original baseline failures resolved; **14 remain without current-main
disposition**. This is neither a full migration walk nor a full current-backend
baseline. Independent accounting sign-off remains open; no deployment.

### Container probe fixture and visible release gates

On d44d5c5 the container hardening-probe fixture and progress-list checks reproduced
as **2 failed in 0.16 seconds**, `/private/tmp/release-probes-before.log`.
The scratch file inherited group 0, while the test process's group is 20; macOS
silently cleared setgid. A direct local check observed 0755, then 02755 after
assigning the caller's group. The test now assigns that group to the setgid file
and directory and asserts all expected modes before invoking the unchanged probe.
Both privileged files must still be detected; the directory and symlink stay excluded.

Restored the required supervisor-target list in PROGRESS.md, explicitly outstanding
for the current release candidate. Dated October 3 results stay in the build history
and are not current verification. The list does not authorize deployment.

Complete Docker script module plus progress-list check: **20 passed in 15.36 seconds**,
`/private/tmp/release-probes-verified.log`. Ruff/format and whitespace checks pass.
Docker is stubbed; no image build or live-container verification occurred. Two
original baseline failures resolved; **12 remain without current-main disposition**.
A separate seven-case local-tooling rerun is still active in session 71400, PID 43359,
`/private/tmp/local-tooling-revalidation.log`; no result claimed yet. Preserve its
primary test database until terminal. Independent accounting sign-off remains open.

### Local tooling revalidation and required import cleanup

Session 71400 completed without interruption: **7 passed in 350.56 seconds**,
`/private/tmp/local-tooling-revalidation.log`. Demo seed setup took 326.84 seconds.
Seven original cases passed unchanged: demo-password refusal, fixture tamper/no-write
checks, dependency licensing, Makefile success output, reset refusal with a running
stack, OpenAPI stale/current checks and process start/reuse/stop. No blanket
environment exemption was added. This is targeted evidence, not their full modules.

Current import cleanup is a required failure hook. The older test expected a FAILED
job beside a locked COMMITTING upload; it now requires COMMITTING/RUNNING while held,
then a later sweep after release must produce FAILED/FAILED plus one
IMPORT_PROCESSING_FAILED item. Already committed uploads stay committed. It checks
one terminal job.failed log per job and the initial held-upload hook failure.
No production changes. Full failure-hook module: **4 passed in 15.88 seconds**,
`/private/tmp/import-failure-cleanup-verified.log`. Ruff/format/whitespace checks pass.
All processes terminal. The progress notebook's size check initially found 20,032
bytes; another historical section was archived unchanged to restore its under-20KB limit.

Eight more original failures resolved; four remain without current-main disposition:

- close/test_lock_open_redirty_db.py: waived-item freshness/re-marking case;
- platform/test_audit_coverage.py: pending AI lifecycle category;
- reports/test_registers_access.py: modification audit action expectations;
- reports/test_registers_close.py: late-billing out-of-period K07 report.

Implementation gaps, broader verification and independent accounting sign-off remain
open. No deployment or production-readiness claim.
