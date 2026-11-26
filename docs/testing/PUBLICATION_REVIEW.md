# Publication review

The final review of feature/final-submission covers 204 changed paths,
with 163 exact staging entries and 41 exclusions.
The index was empty at review. The owner's live migration verification is recorded
in the submission reports. Git publication is a separate action.

The working-tree credential scan reported no matches. Historical development
credential references remain and still-used values should be rotated before
publication. The staging lists exclude private configuration, backups, runtime
logs and raw machine-specific evidence. Excluded deletions stay unstaged so
the historical check-in and team placeholders remain in Git.

| Path | Status | Recommendation | Reason |
| --- | --- | --- | --- |
| `.dockerignore` | M | Group 1 | Updated application, test, configuration or documentation. |
| `.env.example` | M | Group 1 | Updated application, test, configuration or documentation. |
| `.github/ISSUE_TEMPLATE/.gitkeep` | D | Exclude | Keep repository template directory placeholder. |
| `.github/PULL_REQUEST_TEMPLATE.md` | D | Exclude | Empty historical template. Leave the deletion unstaged. |
| `.gitignore` | M | Group 1 | Updated application, test, configuration or documentation. |
| `CHECKIN_PROGRESS.md` | D | Exclude | Substantive historical check-in. Leave its deletion unstaged to preserve the tracked copy. |
| `Dockerfile` | D | Group 1 | Empty root file replaced by Dockerfile.hosting. |
| `README.md` | M | Group 3 | Updated application, test, configuration or documentation. |
| `app/__init__.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/auth.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/config.py` | D | Group 1 | Empty obsolete shim. Current Flask registration and database setup live in app/__init__.py. |
| `app/coordinator.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/db.py` | D | Group 1 | Empty obsolete shim. Current Flask registration and database setup live in app/__init__.py. |
| `app/events/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/frontend.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/member.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/messaging/event_consumer.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/messaging/event_publisher.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/messaging/rabbitmq_config.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/messaging/rabbitmq_connection.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/messaging/worker_runtime.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/models.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/models/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/models/__init__.py` | D | Group 1 | Remove empty package that shadows app/models.py. |
| `app/organization.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/pagination.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/registration.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/requests.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/routes.py` | D | Group 1 | Empty obsolete shim. Current Flask registration and database setup live in app/__init__.py. |
| `app/routes/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/services/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/services/attendance.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/services/completions.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/services/guest_requests.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/services/manual_assignment.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/services/matching.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/services/member_registration.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/services/offerings.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/services/organization_approvals.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/services/outbox.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/services/overdue.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/services/referrals.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/services/service_browsing.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/services/timeouts.py` | ? | Group 1 | New source, documentation or evidence. |
| `app/static/css/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/static/css/style.css` | M | Group 1 | Updated application, test, configuration or documentation. |
| `app/static/images/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/static/js/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/static/vendor/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/templates/components/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/templates/coordinator/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/templates/individual/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/templates/member/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/templates/organization/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `app/templates/shared/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `backend/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `compose.hosting.yml` | M | Group 1 | Updated application, test, configuration or documentation. |
| `coordinator_worker.py` | ? | Group 1 | New source, documentation or evidence. |
| `database/create_demo_data.py` | M | Group 2 | Updated application, test, configuration or documentation. |
| `database/demo_data.sql` | ? | Group 1 | New source, documentation or evidence. |
| `database/migrations/001_checkin_workflow.sql` | ? | Group 1 | New source, documentation or evidence. |
| `database/migrations/002_firebase_authentication.sql` | ? | Group 1 | New source, documentation or evidence. |
| `database/migrations/003_derive_referral_backup.sql` | ? | Group 1 | Guarded migration 003. Owner verified completion on the current live database. |
| `database/proposals/003_derive_referral_backup.sql` | ? | Exclude | Superseded local proposal. Publish the guarded migration under migrations/. |
| `database/queries.sql` | M | Group 1 | Updated application, test, configuration or documentation. |
| `database/schema.sql` | M | Group 1 | Updated application, test, configuration or documentation. |
| `database/schema_safe.sql` | M | Group 1 | Updated application, test, configuration or documentation. |
| `database/seed.sql` | M | Group 1 | Updated application, test, configuration or documentation. |
| `deadline_checker.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `deploy/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `deploy/check_schema.py` | M | Group 1 | Reject the legacy referral schema before starting workers. |
| `deploy/hosting.env.example` | M | Group 1 | Updated application, test, configuration or documentation. |
| `docker-compose.yml` | M | Group 1 | Updated application, test, configuration or documentation. |
| `docs/DEPLOYMENT_GUIDE.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/FINAL_DEMO_GUIDE.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/FINAL_SUBMISSION_CHECKLIST.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/SUBMISSION_READINESS.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/architecture/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `docs/authentication.md` | M | Group 3 | Updated application, test, configuration or documentation. |
| `docs/database/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `docs/database/FINAL_LOGICAL_MAPPING.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/database/REFERRAL_MIGRATION_RUNBOOK.md` | ? | Group 3 | Backup, rehearsal, live migration and recovery commands. |
| `docs/events/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `docs/frontend_integration.md` | M | Group 3 | Updated application, test, configuration or documentation. |
| `docs/hosting/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `docs/hosting/HOSTING_RUNBOOK.md` | M | Group 3 | Updated application, test, configuration or documentation. |
| `docs/meetings/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `docs/requirements/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `docs/testing/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `docs/testing/ACCOUNT_MIGRATION_PLAN.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/DATABASE_COMPLIANCE_REPORT.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/DEPLOYMENT_TEST_REPORT.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/EVENT_WORKFLOW_TEST_REPORT.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/FINAL_TEST_REPORT.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/NORMALIZATION_REPORT.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/PUBLICATION_REVIEW.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/SECURITY_AUDIT.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/USER_TESTING_GUIDE.md` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/ad_hoc_user_testing.csv` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/browser_smoke.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/changed_files.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/container_smoke.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/database_compliance_review.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/final_changed_files.json` | ? | Exclude | Earlier checksum snapshot superseded by this branch review. |
| `docs/testing/firebase_password_policy.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/isolated_integration.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/isolated_integration.junit.xml` | ? | Exclude | Raw test XML is local evidence with machine metadata and possible tracebacks. |
| `docs/testing/live_data_invariants.json` | ? | Exclude | Earlier raw snapshot superseded by the November 26 aggregate review. |
| `docs/testing/live_environment.json` | ? | Exclude | Raw environment snapshot and identity fingerprint. Publish aggregate results in Markdown. |
| `docs/testing/mysql_query_plans.json` | ? | Group 3 | Read-only MySQL EXPLAIN evidence without sample data. |
| `docs/testing/query_measurements.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/referral_normalization_live.json` | ? | Group 3 | Sanitized pre-migration aggregates and owner-executed live postchecks. |
| `docs/testing/regression.junit.xml` | ? | Exclude | Raw test XML contains absolute installation paths or machine metadata. |
| `docs/testing/secret_scan.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/source_validation.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/sql_inventory.csv` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/sql_inventory.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/sql_inventory_head.csv` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/sql_inventory_head.json` | ? | Group 3 | New source, documentation or evidence. |
| `docs/testing/sql_query_comparison.csv` | ? | Group 3 | New source, documentation or evidence. |
| `feedback_worker.py` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/static/css/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `frontend/static/css/style.css` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/static/js/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `frontend/static/js/firebase-client.js` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/static/js/login.js` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/static/js/main.js` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/static/js/organization-actions.js` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/static/js/password-reset.js` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/static/js/register-organization.js` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/static/js/register.js` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/static/js/registration-password.js` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/static/js/registration-recovery.js` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/static/js/registration-verification.js` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/static/js/request-confirmation.js` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/static/vendor/bootstrap/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `frontend/templates/auth/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `frontend/templates/auth/_password_requirements.html` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/templates/auth/_verification_panel.html` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/templates/auth/login.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/auth/register_individual.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/auth/register_organization.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/auth/signup.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/auth/verify_email.html` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/templates/base.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/components/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `frontend/templates/components/footer.html` | D | Group 1 | Comment-only template with no remaining include. |
| `frontend/templates/components/list_controls.html` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/templates/components/macros.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/components/messages.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/components/navbar.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/components/notification_panel.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/components/pagination.html` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/templates/coordinator/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `frontend/templates/coordinator/approvals.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/coordinator/dashboard.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/coordinator/organizations.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/coordinator/reports.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/coordinator/request_details.html` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/templates/coordinator/requests.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/errors/error.html` | ? | Group 1 | New source, documentation or evidence. |
| `frontend/templates/individual/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `frontend/templates/individual/dashboard.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/individual/my_requests.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/individual/profile.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/individual/request_confirmation.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/individual/request_details.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/individual/request_form.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/organization/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `frontend/templates/organization/dashboard.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/organization/request_details.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/organization/requests.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/organization/services.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/public/.gitkeep` | D | Exclude | Empty placeholder. Keep the tracked copy by leaving this deletion unstaged. |
| `frontend/templates/public/browse_services.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/public/home.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `frontend/templates/public/service_details.html` | M | Group 1 | Updated application, test, configuration or documentation. |
| `notification_worker.py` | ? | Group 1 | New source, documentation or evidence. |
| `outbox_dispatcher.py` | ? | Group 1 | New source, documentation or evidence. |
| `requirements-browser.txt` | M | Group 2 | Updated application, test, configuration or documentation. |
| `run.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `scripts/check_health.ps1` | ? | Group 1 | New source, documentation or evidence. |
| `scripts/start_local.ps1` | ? | Group 1 | New source, documentation or evidence. |
| `scripts/stop_local.ps1` | ? | Group 1 | New source, documentation or evidence. |
| `sla_worker.py` | ? | Group 1 | New source, documentation or evidence. |
| `tests/integration/test_live_workflows.py` | ? | Group 2 | New source, documentation or evidence. |
| `tests/test_coordinator_preservation.py` | ? | Group 2 | New source, documentation or evidence. |
| `tests/test_deadline_workflows.py` | ? | Group 2 | New source, documentation or evidence. |
| `tests/test_list_queries.py` | ? | Group 2 | New source, documentation or evidence. |
| `tests/test_registration_passwords.py` | ? | Group 2 | New source, documentation or evidence. |
| `tests/test_sql_inventory.py` | ? | Group 2 | New source, documentation or evidence. |
| `tests/test_verified_registration.py` | ? | Group 2 | New source, documentation or evidence. |
| `tools/audit_live_environment.py` | ? | Group 3 | New source, documentation or evidence. |
| `tools/audit_repository_security.py` | ? | Group 3 | New source, documentation or evidence. |
| `tools/audit_sql_inventory.py` | ? | Group 3 | New source, documentation or evidence. |
| `tools/browser_smoke.py` | ? | Group 2 | New source, documentation or evidence. |
| `tools/check_container_image.py` | ? | Group 2 | New source, documentation or evidence. |
| `tools/check_firebase_password_policy.py` | ? | Group 2 | New source, documentation or evidence. |
| `tools/check_submission_readiness.py` | ? | Group 2 | New source, documentation or evidence. |
| `tools/create_firebase_test_user.py` | M | Group 1 | Updated application, test, configuration or documentation. |
| `tools/local_runtime.py` | ? | Group 1 | New source, documentation or evidence. |
| `tools/run_isolated_integration.py` | ? | Group 2 | New source, documentation or evidence. |
| `tools/snapshot_migration_003.py` | ? | Group 2 | Read-only comparison of all table rows before and after migration. |
| `worker.py` | M | Group 1 | Updated application, test, configuration or documentation. |

## Exact PowerShell publication commands

Run from the repository root after approval. Confirm the active branch is
feature/final-submission and the index is empty. Use the explicit paths below.

```powershell
git status --short --branch
git diff --cached --name-only
```

For each group, review the staged diff and confirm its paths match the listed
allowlist before running its commit command.

### Group 1

```powershell
git add -- '.dockerignore'
git add -- '.env.example'
git add -- '.gitignore'
git add -- 'Dockerfile'
git add -- 'app/__init__.py'
git add -- 'app/auth.py'
git add -- 'app/config.py'
git add -- 'app/coordinator.py'
git add -- 'app/db.py'
git add -- 'app/frontend.py'
git add -- 'app/member.py'
git add -- 'app/messaging/event_consumer.py'
git add -- 'app/messaging/event_publisher.py'
git add -- 'app/messaging/rabbitmq_config.py'
git add -- 'app/messaging/rabbitmq_connection.py'
git add -- 'app/messaging/worker_runtime.py'
git add -- 'app/models.py'
git add -- 'app/models/__init__.py'
git add -- 'app/organization.py'
git add -- 'app/pagination.py'
git add -- 'app/registration.py'
git add -- 'app/requests.py'
git add -- 'app/routes.py'
git add -- 'app/services/attendance.py'
git add -- 'app/services/completions.py'
git add -- 'app/services/guest_requests.py'
git add -- 'app/services/manual_assignment.py'
git add -- 'app/services/matching.py'
git add -- 'app/services/member_registration.py'
git add -- 'app/services/offerings.py'
git add -- 'app/services/organization_approvals.py'
git add -- 'app/services/outbox.py'
git add -- 'app/services/overdue.py'
git add -- 'app/services/referrals.py'
git add -- 'app/services/service_browsing.py'
git add -- 'app/services/timeouts.py'
git add -- 'app/static/css/style.css'
git add -- 'compose.hosting.yml'
git add -- 'coordinator_worker.py'
git add -- 'database/demo_data.sql'
git add -- 'database/migrations/001_checkin_workflow.sql'
git add -- 'database/migrations/002_firebase_authentication.sql'
git add -- 'database/migrations/003_derive_referral_backup.sql'
git add -- 'database/queries.sql'
git add -- 'database/schema.sql'
git add -- 'database/schema_safe.sql'
git add -- 'database/seed.sql'
git add -- 'deadline_checker.py'
git add -- 'deploy/check_schema.py'
git add -- 'deploy/hosting.env.example'
git add -- 'docker-compose.yml'
git add -- 'feedback_worker.py'
git add -- 'frontend/static/css/style.css'
git add -- 'frontend/static/js/firebase-client.js'
git add -- 'frontend/static/js/login.js'
git add -- 'frontend/static/js/main.js'
git add -- 'frontend/static/js/organization-actions.js'
git add -- 'frontend/static/js/password-reset.js'
git add -- 'frontend/static/js/register-organization.js'
git add -- 'frontend/static/js/register.js'
git add -- 'frontend/static/js/registration-password.js'
git add -- 'frontend/static/js/registration-recovery.js'
git add -- 'frontend/static/js/registration-verification.js'
git add -- 'frontend/static/js/request-confirmation.js'
git add -- 'frontend/templates/auth/_password_requirements.html'
git add -- 'frontend/templates/auth/_verification_panel.html'
git add -- 'frontend/templates/auth/login.html'
git add -- 'frontend/templates/auth/register_individual.html'
git add -- 'frontend/templates/auth/register_organization.html'
git add -- 'frontend/templates/auth/signup.html'
git add -- 'frontend/templates/auth/verify_email.html'
git add -- 'frontend/templates/base.html'
git add -- 'frontend/templates/components/footer.html'
git add -- 'frontend/templates/components/list_controls.html'
git add -- 'frontend/templates/components/macros.html'
git add -- 'frontend/templates/components/messages.html'
git add -- 'frontend/templates/components/navbar.html'
git add -- 'frontend/templates/components/notification_panel.html'
git add -- 'frontend/templates/components/pagination.html'
git add -- 'frontend/templates/coordinator/approvals.html'
git add -- 'frontend/templates/coordinator/dashboard.html'
git add -- 'frontend/templates/coordinator/organizations.html'
git add -- 'frontend/templates/coordinator/reports.html'
git add -- 'frontend/templates/coordinator/request_details.html'
git add -- 'frontend/templates/coordinator/requests.html'
git add -- 'frontend/templates/errors/error.html'
git add -- 'frontend/templates/individual/dashboard.html'
git add -- 'frontend/templates/individual/my_requests.html'
git add -- 'frontend/templates/individual/profile.html'
git add -- 'frontend/templates/individual/request_confirmation.html'
git add -- 'frontend/templates/individual/request_details.html'
git add -- 'frontend/templates/individual/request_form.html'
git add -- 'frontend/templates/organization/dashboard.html'
git add -- 'frontend/templates/organization/request_details.html'
git add -- 'frontend/templates/organization/requests.html'
git add -- 'frontend/templates/organization/services.html'
git add -- 'frontend/templates/public/browse_services.html'
git add -- 'frontend/templates/public/home.html'
git add -- 'frontend/templates/public/service_details.html'
git add -- 'notification_worker.py'
git add -- 'outbox_dispatcher.py'
git add -- 'run.py'
git add -- 'scripts/check_health.ps1'
git add -- 'scripts/start_local.ps1'
git add -- 'scripts/stop_local.ps1'
git add -- 'sla_worker.py'
git add -- 'tools/create_firebase_test_user.py'
git add -- 'tools/local_runtime.py'
git add -- 'worker.py'
git diff --cached --check
git diff --cached --name-status
git diff --cached
```

```powershell
git commit -m "Integrate CareConnect and normalize referral backup storage"
```

### Group 2

```powershell
git add -- 'database/create_demo_data.py'
git add -- 'requirements-browser.txt'
git add -- 'tests/integration/test_live_workflows.py'
git add -- 'tests/test_coordinator_preservation.py'
git add -- 'tests/test_deadline_workflows.py'
git add -- 'tests/test_list_queries.py'
git add -- 'tests/test_registration_passwords.py'
git add -- 'tests/test_sql_inventory.py'
git add -- 'tests/test_verified_registration.py'
git add -- 'tools/browser_smoke.py'
git add -- 'tools/check_container_image.py'
git add -- 'tools/check_firebase_password_policy.py'
git add -- 'tools/check_submission_readiness.py'
git add -- 'tools/run_isolated_integration.py'
git add -- 'tools/snapshot_migration_003.py'
git diff --cached --check
git diff --cached --name-status
git diff --cached
```

```powershell
git commit -m "Test normalized referral workflows and migration 003"
```

### Group 3

```powershell
git add -- 'README.md'
git add -- 'docs/DEPLOYMENT_GUIDE.md'
git add -- 'docs/FINAL_DEMO_GUIDE.md'
git add -- 'docs/FINAL_SUBMISSION_CHECKLIST.md'
git add -- 'docs/SUBMISSION_READINESS.md'
git add -- 'docs/authentication.md'
git add -- 'docs/database/FINAL_LOGICAL_MAPPING.md'
git add -- 'docs/database/REFERRAL_MIGRATION_RUNBOOK.md'
git add -- 'docs/frontend_integration.md'
git add -- 'docs/hosting/HOSTING_RUNBOOK.md'
git add -- 'docs/testing/ACCOUNT_MIGRATION_PLAN.md'
git add -- 'docs/testing/DATABASE_COMPLIANCE_REPORT.md'
git add -- 'docs/testing/DEPLOYMENT_TEST_REPORT.md'
git add -- 'docs/testing/EVENT_WORKFLOW_TEST_REPORT.md'
git add -- 'docs/testing/FINAL_TEST_REPORT.md'
git add -- 'docs/testing/NORMALIZATION_REPORT.md'
git add -- 'docs/testing/PUBLICATION_REVIEW.md'
git add -- 'docs/testing/SECURITY_AUDIT.md'
git add -- 'docs/testing/USER_TESTING_GUIDE.md'
git add -- 'docs/testing/ad_hoc_user_testing.csv'
git add -- 'docs/testing/browser_smoke.json'
git add -- 'docs/testing/changed_files.json'
git add -- 'docs/testing/container_smoke.json'
git add -- 'docs/testing/database_compliance_review.json'
git add -- 'docs/testing/firebase_password_policy.json'
git add -- 'docs/testing/isolated_integration.json'
git add -- 'docs/testing/mysql_query_plans.json'
git add -- 'docs/testing/query_measurements.json'
git add -- 'docs/testing/referral_normalization_live.json'
git add -- 'docs/testing/secret_scan.json'
git add -- 'docs/testing/source_validation.json'
git add -- 'docs/testing/sql_inventory.csv'
git add -- 'docs/testing/sql_inventory.json'
git add -- 'docs/testing/sql_inventory_head.csv'
git add -- 'docs/testing/sql_inventory_head.json'
git add -- 'docs/testing/sql_query_comparison.csv'
git add -- 'tools/audit_live_environment.py'
git add -- 'tools/audit_repository_security.py'
git add -- 'tools/audit_sql_inventory.py'
git diff --cached --check
git diff --cached --name-status
git diff --cached
```

```powershell
git commit -m "Record final submission evidence and publication review"
```

After review and publication approval, check the three commits and push the
feature branch. Excluded working-tree paths may still appear in status.

```powershell
git status --short --branch
git log --oneline origin/main..HEAD
git diff --stat origin/main..HEAD
git push -u origin feature/final-submission
```
