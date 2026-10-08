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
