# Phase 6: acceptance criteria to tests

Built in session 9 (P6-10a) for the Phase 6 summary and the Local MVP DoD run of session 11. Every criterion of `docs/product/acceptance-criteria.md` is listed: AC-A1 to AC-G5 and AC-X1 to AC-X8. Paths are relative to `backend/` unless they start with `frontend/`. `::name` continues the file named before it. A citation is a real test; a script checked that every `file::test` below exists when this file was written.

How to read the last column: **(manual)** is a check no automated test can do (a person, a phone, the owner's CI). A UI-level part is proven by the Playwright specs in the third column (all closed in session 10); the backend part of the same criterion is proven by the tests in the second column. Where `acceptance-criteria.md` names a different file than the one below, the file below is the real one (noted in the last column).

**Result.** No backend-closable GAP is left open. One gap was closed in session 9: AC-B2 had a test for the event and the job, but none that ran the draft job after three deliveries (`test_ac_b2_the_same_webhook_three_times_gives_one_message_and_one_draft`). Session 10 closed the browser-level items with the Playwright specs `scenario-e.spec.ts`, `scenario-g.spec.ts`, `i18n.spec.ts` and `a11y.spec.ts` (AC-E3, AC-E5, AC-G1, AC-G3 banner, AC-X2 badges, AC-X3, AC-X4). What remains is for the owner:

| Open item | Why it is not an automated test | Where |
|---|---|---|
| AC-X8 the full CI pipeline | Nothing is pushed, so CI has never run | **(manual)**, owner (plan section 6) |
| DoD items 2, 3 and 4 | A person on Windows, a real phone, the invariant review | **(manual)**, session 11 and the owner |

## Scenario A: business setup

| AC | Backend tests | UI tests | Note |
|---|---|---|---|
| AC-A1 | `tests/integration/test_seed.py::test_seed_creates_the_documented_demo_data` (workspace, facts and the mock account the Home card reads) | `frontend/src/features/home/home.test.tsx` ("shows the connection, the simulation badge and the AI mode"); `frontend/e2e/scenario-a.spec.ts` (A1); `frontend/e2e/phase1.spec.ts` (simulation banner) | The banner itself is UI: no backend test |
| AC-A2 | `tests/integration/knowledge/test_facts_api.py::test_owner_creates_a_verified_fact_with_version_and_audit` (source and last-verified date); `::test_listing_filters_and_template_checklist` | `frontend/e2e/scenario-a.spec.ts` (A2) | doc names `test_facts_list` |
| AC-A3 | `tests/integration/knowledge/test_facts_api.py::test_verifying_an_unverified_fact` | `frontend/e2e/scenario-a.spec.ts` (A3) | doc names `test_verify.py` |
| AC-A4 | `tests/integration/knowledge/test_facts_api.py::test_staff_cannot_verify`; `::test_staff_cannot_archive_or_restore_either`; `tests/integration/knowledge/test_candidates_api.py::test_a_staff_edit_becomes_a_contest_candidate_and_the_fact_stays_unchanged` | `frontend/e2e/scenario-a.spec.ts` (A5) | doc names `test_permissions.py` |
| AC-A5 | `tests/unit/knowledge/test_readiness.py::test_everything_present_and_an_account_connected_is_ready`; `::test_without_a_connected_account_the_level_is_ready_for_drafts`; `::test_a_missing_draft_requirement_is_not_ready_and_listed`; `::test_missing_ready_requirement_downgrades_to_ready_for_drafts`; `tests/integration/knowledge/test_usable_readiness_settings.py::test_readiness_api_lists_what_is_missing_then_reaches_ready_for_drafts` | | |
| AC-A6 | `tests/integration/knowledge/test_extraction.py::test_ac_a6_pasted_prices_become_candidates_with_excerpts_and_no_fact_changes` | `frontend/e2e/scenario-c.spec.ts` (A6) | |

## Scenario B: customer inquiry answered

| AC | Backend tests | UI tests | Note |
|---|---|---|---|
| AC-B1 | `tests/integration/inbox/test_reply_workflow.py::test_ac_b1_one_message_gives_one_event_one_message_and_one_draft` | | doc names `test_ingest.py` |
| AC-B2 | `tests/integration/inbox/test_reply_workflow.py::test_ac_b2_the_same_webhook_three_times_gives_one_message_and_one_draft` (**added in session 9**: three deliveries, jobs run, one message and one draft); `tests/integration/inbox/test_webhook_ingest.py::test_the_same_webhook_three_times_is_one_event_and_one_job` | | doc names `test_dedup.py` |
| AC-B3 | `tests/integration/inbox/test_reply_workflow.py::test_a_price_question_becomes_a_grounded_draft_waiting_for_approval`; `tests/integration/inbox/test_drafting_pipeline.py::test_a_price_question_gets_the_verified_price_through_a_placeholder` | | doc names `test_draft_grounding.py` |
| AC-B4 | `tests/integration/inbox/test_reply_workflow.py::test_the_approval_is_bound_to_the_exact_text_and_expires_before_the_window`; `tests/unit/policy/test_reply_rules.py::test_the_default_policy_requires_approval` | | doc names `test_policy.py` |
| AC-B5 | `tests/integration/inbox/test_send.py::test_ac_b5_an_approved_reply_is_sent_once_and_recorded_everywhere` | `frontend/e2e/scenario-b.spec.ts` (B5) | |
| AC-B6 | `tests/unit/policy/test_reply_rules.py::test_ac_b6_a_complaint_stays_human_even_when_the_model_says_it_is_fine`; `tests/integration/inbox/test_reply_workflow.py::test_ac_b6_a_complaint_goes_to_a_person_even_if_the_model_says_needs_human_false` | `frontend/e2e/scenario-b.spec.ts` (B6) | |
| AC-B7 | `tests/integration/inbox/test_reply_workflow.py::test_ac_b7_an_injection_attempt_never_yields_a_sendable_discount`; `tests/integration/inbox/test_drafting_pipeline.py::test_an_injection_attempt_is_flagged_and_never_yields_a_discount`; `tests/unit/evals/test_eval_harness.py::test_the_fake_provider_passes_every_case_strictly` (the `injection` cases) | `frontend/e2e/scenario-b.spec.ts` (B7) | doc names `test_injection.py` |
| AC-B8 | `tests/integration/inbox/test_reply_workflow.py::test_ac_b8_an_unverified_price_is_never_in_a_draft`; `tests/integration/inbox/test_drafting_pipeline.py::test_an_unverified_price_is_never_offered`; `::test_a_contested_price_is_not_usable` | | doc names `test_unusable_fact.py` |
| AC-B9 | `tests/integration/inbox/test_send.py::test_ac_b9_running_the_send_again_sends_nothing_more`; `tests/integration/inbox/test_reply_workflow.py::test_ac_b9_a_second_decision_is_a_conflict_and_queues_nothing_more` | | doc names `test_double_decision.py` |
| AC-B10 | `tests/integration/inbox/test_reply_workflow.py::test_ac_b10_a_decision_after_the_window_closed_is_expired_and_sends_nothing` | | doc names `test_window.py` |

## Scenario C: business fact change

| AC | Backend tests | UI tests | Note |
|---|---|---|---|
| AC-C1 | `tests/integration/commands/test_update_fact.py::test_ac_c1_the_command_reaches_a_confirmation_with_old_and_new_values` | `frontend/e2e/scenario-c.spec.ts` (C1/C2) | |
| AC-C2 | `tests/integration/commands/test_update_fact.py::test_ac_c2_confirming_updates_the_fact_and_keeps_the_history` | `frontend/e2e/scenario-c.spec.ts` (C1/C2) | |
| AC-C3 | `tests/integration/inbox/test_approved_answers_and_impact.py::test_ac_c5_a_pending_draft_is_superseded_and_drafted_again_with_the_new_price` (the redraft carries `7.000 ₺`); `tests/integration/inbox/test_simulator.py::test_demo_a_price_change_alters_the_next_draft` | | doc names `test_draft_after_update.py` |
| AC-C4 | `tests/integration/content/test_fact_impact.py::test_ac_c4_a_price_change_by_command_holds_the_scheduled_post`; `::test_the_author_who_cannot_approve_is_told_too`; `::test_a_post_waiting_for_a_retry_is_held_and_its_waiting_operation_cancelled`; `::test_an_item_waiting_for_approval_goes_back_to_a_draft_and_its_approval_is_cancelled`; `::test_published_and_publishing_items_are_untouched` | `frontend/e2e/scenario-c.spec.ts` ("fact change holds the scheduled post") | |
| AC-C5 | `tests/integration/inbox/test_approved_answers_and_impact.py::test_ac_c5_a_pending_draft_is_superseded_and_drafted_again_with_the_new_price`; `::test_ac_c5_a_message_that_was_already_sent_is_unchanged` | | doc names `tests/integration/knowledge/test_impact_drafts.py` |
| AC-C6 | `tests/integration/commands/test_clarification_and_expiry.py::test_ac_c6_an_ambiguous_price_asks_which_fact_and_changes_nothing` | `frontend/e2e/scenario-c.spec.ts` (C6) | doc names `test_clarification.py` |
| AC-C7 | `tests/integration/commands/test_clarification_and_expiry.py::test_ac_c7_an_unconfirmed_command_expires_after_30_minutes` | | doc names `test_expiry.py` |

## Scenario D: create and schedule a Story

| AC | Backend tests | UI tests | Note |
|---|---|---|---|
| AC-D1 | `tests/integration/content/test_generate.py::test_ac_d1_the_draft_has_its_placeholders_rendered_and_its_references_stored`; `::test_a_story_is_generated_without_a_caption` | `frontend/e2e/scenario-d.spec.ts` (D1/D2/D4) | |
| AC-D2 | `tests/integration/content/test_media_upload.py::test_a_png_becomes_a_ready_jpeg_without_exif`; `::test_a_text_file_is_rejected_whatever_its_name_and_type` | `frontend/e2e/scenario-d.spec.ts` (D1/D2/D4) | doc names `test_media.py` |
| AC-D3 | `tests/unit/content/test_validation.py::test_ac_d3_a_story_without_media_fails_with_content_media_required` | | |
| AC-D4 | `tests/integration/content/test_schedule.py::test_ac_d4_an_owner_approving_and_scheduling_19_00_istanbul_gets_16_00_utc` | `frontend/e2e/scenario-d.spec.ts` (D1/D2/D4) | |
| AC-D5 | `tests/integration/content/test_publish.py::test_ac_d5_advancing_the_clock_past_scheduled_at_publishes_the_item_once` | `frontend/e2e/scenario-d.spec.ts` (D5) | |
| AC-D6 | `tests/integration/content/test_schedule.py::test_ac_d6_editing_after_scheduling_voids_the_approval_and_the_job`; `tests/integration/content/test_edit_after_approval.py::test_editing_a_scheduled_item_returns_it_to_draft_and_voids_the_approval`; `tests/integration/content/test_publish.py::test_a_job_of_an_old_version_publishes_nothing_after_an_edit` | `frontend/e2e/scenario-d.spec.ts` (D6) | |
| AC-D7 | `tests/integration/content/test_cancel.py::test_ac_d7_cancelling_a_scheduled_item_cancels_it_and_its_job`; `tests/integration/content/test_publish.py::test_an_item_that_is_no_longer_scheduled_is_not_published` | | |
| AC-D8 | `tests/integration/content/test_staff_submit.py::test_ac_d8_staff_submission_creates_a_pending_authorisation`; `::test_only_owner_and_manager_can_approve` | `frontend/e2e/scenario-d.spec.ts` (D8, two tests) | |

## Scenario E: review the day

| AC | Backend tests | UI tests | Note |
|---|---|---|---|
| AC-E1 | `tests/integration/reporting/test_daily_report.py::test_ac_e1_every_metric_has_its_exact_known_value`; `::test_registry_has_the_twenty_v1_metrics`; `::test_records_of_another_workspace_change_no_metric` | | |
| AC-E2 | `tests/integration/reporting/test_daily_report.py::test_ac_e2_records_on_the_local_day_boundaries` (Europe/Istanbul, Europe/Lisbon in summer time and on both DST change days); `::test_a_period_computed_in_utc_would_get_lisbon_wrong`; `tests/unit/reporting/test_periods.py::test_a_dst_day_is_23_or_25_hours_long` | | |
| AC-E3 | `tests/integration/reporting/test_daily_report.py::test_rows_count_equals_value` (all 20 metrics); `tests/integration/reporting/test_report_api.py::test_the_drill_down_has_as_many_rows_as_the_number`; `::test_every_metric_link_leads_to_the_drill_down`; `::test_a_past_day_comes_back_complete_with_a_link_on_every_number` | `frontend/e2e/scenario-e.spec.ts` (every nonzero number of today's report and of yesterday's seeded report opens a list with exactly that many rows; a median is checked for at least one row); Vitest `frontend/src/features/home/home.test.tsx` ("shows the day's numbers as links to their records") | doc names an E2E spec only; the equality itself is a backend fact |
| AC-E4 | `tests/integration/commands/test_activity_query.py::test_ac_e4_the_answer_equals_the_reports_number_at_the_same_instant` | | |
| AC-E5 | `tests/integration/reporting/test_report_api.py::test_a_past_day_comes_back_complete_with_a_link_on_every_number` (`has_simulated_data`); `tests/integration/test_simulation_flag.py::test_ac_x2_a_report_over_simulated_records_is_flagged_everywhere` (**added in session 9**); `tests/integration/test_simulation_flag.py::test_ac_x2_a_report_over_real_records_is_not_flagged` | `frontend/e2e/scenario-e.spec.ts` (the SİMÜLASYON badge on the report, today and yesterday) | |

## Scenario F: publishing failure handling

| AC | Backend tests | UI tests | Note |
|---|---|---|---|
| AC-F1 | `tests/integration/content/test_publish_retry.py::test_ac_f1_transient_twice_retries_with_backoff_and_publishes_once_on_the_third_attempt` | | |
| AC-F2 | `tests/integration/content/test_publish_retry.py::test_ac_f2_transient_always_ends_failed_after_the_attempts_and_notifies` | | |
| AC-F3 | `tests/integration/content/test_publish_reconcile.py::test_ac_f3_a_timeout_after_the_publish_is_reconciled_to_published_without_a_second_post` | | |
| AC-F4 | `tests/integration/content/test_publish_crash_commits.py::test_ac_f4_commits_a_crash_right_after_the_container_commit_publishes_once_with_the_stored_id`; `tests/integration/content/test_publish_reconcile.py::test_ac_f4_a_worker_killed_between_container_and_publish_publishes_once_with_the_stored_id` | | |
| AC-F5 | `tests/integration/jobs/test_concurrency.py::test_ac_f5_the_same_publish_executed_by_two_threads_publishes_once`; `::test_ac_f5_two_workers_running_due_jobs_publish_once` | | |
| AC-F6 | `tests/integration/content/test_publish_permanent.py::test_ac_f6_media_rejected_when_creating_the_container_is_not_retried` | `frontend/e2e/scenario-f.spec.ts` (F6) | |
| AC-F7 | `tests/integration/content/test_publish_retry.py::test_the_retry_is_visible_in_the_api_with_its_next_attempt_time` | `frontend/e2e/scenario-f.spec.ts` (F6, F7) | |

## Scenario G: integration failure

| AC | Backend tests | UI tests | Note |
|---|---|---|---|
| AC-G1 | `tests/integration/integrations/test_reauth.py::test_send_revoked_token_then_reconnect_sends_the_reply_once` (account `needs_reauth`, `critical` notification, reply sent once after the reconnect, the revoked rule gone); `::test_publish_revoked_token_holds_the_item_and_a_due_post_is_held_too` (items `on_hold`, no post, notification); `::test_reauthorize_only_removes_revoked_token_rules` | `frontend/src/features/home/home.test.tsx` ("shows the red reauth banner with the renew link, driven by the account status"); `frontend/e2e/scenario-g.spec.ts` G1 (`send` with `auth_revoked`: red Home banner, critical notification, system health shows the status, a post that fell due reads *Beklemede*, reconnect on the connections screen clears the banner and the reply is *Gönderildi* once, the held post stays held) | |
| AC-G2 | `tests/integration/integrations/test_rate_limit.py::test_the_retry_waits_for_retry_after_and_the_account_stays_healthy`; `::test_a_rate_limit_that_never_ends_stops_at_the_attempt_budget` | | |
| AC-G3 | `tests/integration/integrations/test_circuit.py::test_five_failures_within_ten_minutes_open_the_circuit`; `::test_five_failures_spread_over_eleven_minutes_do_not`; `::test_a_success_resets_the_counter`; `::test_degraded_account_gets_no_provider_calls_and_recovery_resumes_the_replies`; `::test_a_publish_is_rescheduled_not_held_while_degraded_and_goes_out_after_recovery`; `::test_the_health_check_job_is_enqueued_for_degraded_accounts_only`; `::test_the_dev_route_runs_the_health_check_now` | `frontend/src/features/home/home.test.tsx` ("shows the amber degraded banner without an action"); `frontend/e2e/scenario-g.spec.ts` G3 (five transient send failures driven through the API give the amber banner and the "until" time; removing the rules and the dev health check clears it) | |
| AC-G4 | `tests/integration/inbox/test_webhook_ingest.py::test_an_invalid_signature_is_401_stores_nothing_and_is_counted`; `::test_every_signature_failure_is_counted`; `tests/integration/operations/test_system_health.py::test_webhook_numbers_and_the_system_wide_signature_counter` | | doc names `test_webhook_signature.py` |
| AC-G5 | `tests/integration/inbox/test_reconcile.py::test_ac_g5_the_echo_confirms_the_send`; `::test_ac_g5_without_an_echo_or_a_lookup_it_is_reported_unconfirmed_and_never_resent`; `::test_a_timeout_after_success_is_an_unknown_outcome_not_a_failure` | `frontend/e2e/scenario-b.spec.ts` ("a reply sent through a timeout is checked, then confirmed by the echo") | doc names `test_send_reconcile.py` |

## Cross-cutting (X)

| AC | Backend tests | UI tests | Note |
|---|---|---|---|
| AC-X1 | `tests/isolation/test_workspace_isolation.py::test_every_workspace_route_returns_404_for_a_foreign_workspace` (every `/workspaces/{id}/...` route, B's ids from `foreign_ids`); `::test_every_workspace_route_is_guarded_by_require_membership`; `::test_listings_never_contain_the_other_workspaces_rows`; `tests/security/test_api_security.py::test_every_workspace_and_dev_route_requires_a_session`. Phase 6 routes: `tests/isolation/test_reports_isolation.py::test_the_three_report_routes_are_404_for_a_foreign_workspace_and_write_nothing` (reports, drill-down, generate); `::test_the_numbers_of_a_never_include_the_records_of_b`; `::test_b_operation_is_not_found_through_any_workspace_url` (operations); `tests/isolation/test_activity_isolation.py::test_the_feed_of_a_never_shows_b_rows_or_b_labels` (activity); `tests/isolation/test_phase6_isolation.py::test_members_of_b_are_neither_listed_nor_changed_through_a` (members); `::test_invites_of_b_are_neither_listed_nor_revoked_nor_created_through_a` (invites); `::test_the_system_health_of_a_never_counts_the_rows_of_b` (system health); `::test_the_dev_reset_and_health_check_of_b_are_404_through_a_and_change_nothing` (dev reset, health check); `::test_the_dev_job_listing_of_a_never_shows_the_jobs_of_b` (**the last four added in session 9**: A's own workspace with B's ids, and the listings read for leaks). Phase 6 jobs: `tests/integration/retention/test_promotion_notices.py::test_each_workspace_is_served_at_its_own_9_in_the_morning` (the per-workspace job notifies only its own members) | `frontend/e2e/phase1.spec.ts` ("tenant isolation") | `foreign_ids` already holds `operation_id` and `invite_id` (added in sessions 2 and 7) |
| AC-X2 | `tests/integration/test_simulation_flag.py::test_ac_x2_a_mock_publish_flags_every_record_it_produces`; `::test_ac_x2_the_api_exposes_the_flag_on_every_content_response`; `::test_an_item_for_a_real_provider_account_is_not_flagged`; Phase 6 additions (**session 9**): `::test_ac_x2_a_report_over_simulated_records_is_flagged_everywhere` (stored `daily_reports.has_simulated_data`, the `report.daily_ready` notification, the `report.generated` audit entry, the drill-down items), `::test_ac_x2_a_report_over_real_records_is_not_flagged`, `::test_ac_x2_the_activity_feed_flags_what_the_mock_produced` (`is_simulated` on activity entries, `false` for a member change), `::test_ac_x2_the_account_notifications_and_audit_follow_the_provider_kind` (`account.*` notifications and `social_account.*` audit); `tests/integration/demo/test_history_seed.py::test_every_history_row_is_simulated` (the seeded history); `tests/integration/demo/test_history_seed.py::test_yesterdays_report_is_exact`; `tests/integration/inbox/test_send.py::test_every_row_a_simulated_send_produces_is_marked_simulated` | `frontend/src/features/home/home.test.tsx`, `frontend/e2e/scenario-d.spec.ts` (D5 shows SİMÜLASYON); `frontend/e2e/scenario-b.spec.ts` (inbox and draft card); `frontend/e2e/scenario-e.spec.ts` (command answer, report, activity feed); `frontend/e2e/scenario-g.spec.ts` (notification, connections) | Media assets are not tied to an account, so they carry no flag; the item that uses one does (Phase 5 Q6, open) |
| AC-X3 | `npm run i18n:check` (catalog parity; `frontend/scripts/check-i18n.mjs`); `tests/unit/test_activity_templates.py` (tr and en text for every audit action); `tests/unit/core/test_clock_i18n_errors.py` | `frontend/e2e/phase1.spec.ts` (English switch); `frontend/e2e/i18n.spec.ts` (tr, en, tr on Home, Inbox, Content, Approvals, Knowledge, Reports, Activity, Notifications, Members, Connections and System health: known strings, no raw catalog key or `{{` on screen) | |
| AC-X4 | | `frontend/e2e/phase1.spec.ts` ("every main screen fits a 360x740 phone without horizontal scroll, in both languages"); Playwright projects in `frontend/e2e/playwright.config.ts`; `expectNoHorizontalScroll` in `frontend/e2e/helpers.ts`, called on every main screen by `frontend/e2e/a11y.spec.ts` (all three projects, so 390 x 844, 412 wide and desktop), `i18n.spec.ts`, `scenario-e.spec.ts` and `scenario-g.spec.ts`. `a11y.spec.ts` also runs axe on those screens plus the login and invite pages: no serious or critical violation | Backend n/a |
| AC-X5 | `tests/integration/jobs/test_restart.py::test_a_new_worker_instance_picks_up_queued_and_scheduled_jobs`; `::test_ac_x5_a_scheduled_publish_survives_a_worker_restart`; `::test_a_job_interrupted_by_a_worker_stop_is_recovered_by_the_next_instance`. Phase 6 periodic jobs hold no memory state: `tests/integration/retention/test_retention.py::test_one_job_per_utc_day_from_02_00` | | |
| AC-X6 | `tests/unit/core/test_settings_safety.py::test_demo_tools_enabled_is_refused_in_production`; `::test_fake_llm_is_refused_in_production`; `::test_missing_secret_key_is_refused`; `::test_all_problems_are_reported_together`; `tests/integration/test_cli.py::test_cli_refuses_to_start_on_an_unsafe_production_configuration`; `::test_api_and_worker_refuse_to_start_on_an_unsafe_production_configuration`. Phase 6 settings (**session 9**): `tests/unit/core/test_settings_safety.py::test_the_retention_defaults_are_the_documented_ones_in_every_environment`; `::test_a_retention_period_below_one_day_is_refused`; `::test_there_is_no_audit_retention_setting`; `::test_retention_periods_are_read_from_the_environment`; `::test_every_retention_variable_is_in_the_example_env_and_the_docs`. The reset route is absent without demo tools: `tests/integration/demo/test_reset.py::test_the_reset_route_is_absent_without_demo_tools` (INV-20) | | The retention and `CIRCUIT_*` settings are safe in production by default, so they add no refusal |
| AC-X7 | `tests/unit/core/test_redaction.py::test_sensitive_keys_are_masked`; `::test_json_logging_pipeline_redacts_end_to_end`; `tests/security/test_api_security.py::test_no_response_schema_exposes_secret_fields` (every response schema, including the Phase 6 routes). Invites (**session 9**): `tests/security/test_invite_secrets.py::test_the_invite_response_models_are_allow_lists`; `::test_the_invite_token_is_never_logged_audited_notified_or_queued`; `tests/integration/identity/test_members_and_invites.py::test_pending_invites_are_listed_without_their_token`. Retention settings: `tests/unit/core/test_settings_safety.py::test_retention_settings_are_public_numbers_not_secrets`. System health carries no payload: `tests/integration/operations/test_system_health.py::test_the_response_carries_no_payload_or_text` | | |
| AC-X8 | | | **(manual)** The pipeline has never run (nothing is pushed). Session 11 runs every check locally; a CI run needs the owner to push (plan section 6) |

## Definition of Done (local MVP)

| DoD item | Where it is proven |
|---|---|
| 1. AC-A1 to AC-G5 and AC-X1 to AC-X8 pass in CI | The tables above; the full local run is session 11. AC-X8 itself is **(manual)** |
| 2. The `local-development.md` walkthrough on Windows, unassisted | **(manual)**, session 11 follows the doc literally |
| 3. A walkthrough on a real phone over the LAN | **(manual)**, owner; session 11 writes the checklist |
| 4. No open issue against any invariant | Open decisions that touch an invariant: the audit purge (INV-12, plan H17, not built) and media assets without `is_simulated` (INV-09, Phase 5 Q6). Also noted: the retention job writes `messages.text` and `reply_drafts.text` after creation, the one sanctioned exception to INV-17 (plan H17), which `docs/invariants.md` does not mention yet |
| 5. Each phase summary lists its limitations | Session 11 |

## Mutation spot-checks (session 9, all reverted)

Plan section 5. Each mutation was applied to the source, the named test folders were run, and the file was restored (`git diff` of `app/` is empty afterwards). Every one turned at least one named test red; none survived, so no test had to be added for a survivor.

| # | Mutation | Tests that went red |
|---|---|---|
| 1 | Report period computed in UTC instead of the workspace timezone (`reporting/periods.py::day_bounds` uses `ZoneInfo("UTC")`) | 25 failed, among them `tests/integration/reporting/test_daily_report.py::test_ac_e2_records_on_the_local_day_boundaries` (all four parameters), `::test_a_period_computed_in_utc_would_get_lisbon_wrong`, `::test_ac_e1_every_metric_has_its_exact_known_value`; `tests/unit/reporting/test_periods.py::test_a_local_day_in_a_fixed_offset_zone`, `::test_a_dst_day_is_23_or_25_hours_long`; `tests/integration/commands/test_activity_query.py::test_a_day_boundary_in_the_workspace_timezone_decides_yesterday` |
| 2 | The inbound-message row set without its `workspace_id` filter (`reporting/definitions.py::_inbound_filter`) | `tests/integration/reporting/test_daily_report.py::test_records_of_another_workspace_change_no_metric`; `tests/integration/reporting/test_report_api.py::test_a_workspace_with_no_records_has_the_empty_text`; `tests/isolation/test_reports_isolation.py::test_the_numbers_of_a_never_include_the_records_of_b` |
| 3 | The send and publish executors ignore the open circuit (`degraded` guard disabled in `operations/send.py` and `operations/publish.py`) | `tests/integration/integrations/test_circuit.py::test_degraded_account_gets_no_provider_calls_and_recovery_resumes_the_replies`; `::test_a_publish_is_rescheduled_not_held_while_degraded_and_goes_out_after_recovery` |
| 4 | Invite acceptance without the "already used" check (`identity/invites.py`) | `tests/integration/identity/test_members_and_invites.py::test_every_dead_token_returns_the_same_invite_invalid` |
| 5 | The last owner can be demoted or removed (both `LAST_OWNER_REQUIRED` checks disabled) | `tests/integration/identity/test_members_and_invites.py::test_the_last_owner_cannot_be_demoted_or_removed` |
| 6 | Demo reset without the `is_demo` check (`demo/reset.py`) | `tests/integration/demo/test_reset.py::test_reset_refuses_a_workspace_that_is_not_a_demo_workspace` |
| 7 | Retention nulls message text at 364 days (`retention/cleanup.py`) | `tests/integration/retention/test_retention.py::test_message_and_draft_text_is_nulled_at_365_days_and_the_metadata_kept` |
