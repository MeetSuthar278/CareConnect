# CareConnect ad hoc user testing

Use [the task checklist](ad_hoc_user_testing.csv) with classmates or other willing
participants to test whether CareConnect's wording and workflows are understandable.
No participant testing has been performed or feedback fabricated. The automated
and developer browser checks are recorded separately in the submission report.
The checklist now includes Automation reference and Human participant status
columns. All 40 participant outcomes remain blank/NOT TESTED; 97 developer browser
checks are documented separately in browser_smoke.json and FINAL_TEST_REPORT.md.

## Session preparation

Use a reviewed test environment, synthetic people/organizations and inboxes the
team controls. Preserve existing project accounts and records. Live registration,
referrals, decisions and feedback create real test-environment records, so agree
on the allowed synthetic data before a session. Do not reset a database to prepare
testing. Start the required services and confirm the Firebase project and email
configuration first. Pre-create approved/rejected/pending scenarios through the
authorized application workflow, not direct SQL or automatic email verification.

Record the participant's anonymous label, role, date, browser/device and environment
in a private session note. Do not record passwords, tokens or private account data.
Include a narrow mobile viewport and a keyboard-only pass.

## Running tasks

Give the participant the task objective without explaining which controls to use.
Ask them to describe what they expect the next action to do. Observe misleading
terminology, unexpected navigation, missed validation, delays and places where
assistance was needed. Keep the expected outcome column for the observer.

Complete Actual outcome, Pass/fail, Observed usability issue and Suggested
improvement for every attempted row. Leave unattempted tasks blank or explicitly
mark Not run; a passing automated test is not a participant result. Capture the
participant's interpretation of Preferred time frame and confirm they do not read
the 6/12/24-hour service targets as emergency assistance or guaranteed availability.

## Review

Group observations by registration/verification, finding services, referral work,
coordinator review and mobile/accessibility. Resolve reproducible correctness
issues first. Prefer small wording/control changes over new features. Re-test
changed tasks and retain the original observation alongside the follow-up outcome.
Add actual anonymous findings to the submission only after these sessions occur.
