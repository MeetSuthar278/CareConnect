# Firebase account mapping review

CareConnect now verifies identities against `careconnect-bfb9e`. A UID stored in
MySQL does not reveal which Firebase project issued it. Configuration consistency
therefore does not establish that existing user mappings belong to the new project.
The configured MySQL service was unavailable during the submission checks, so no
live UID mappings were inspected or changed.

## Read only inventory

Once MySQL is running, use `python tools/check_submission_readiness.py --database`
to validate the reviewed schema and count mapped/unmapped users without printing
emails or UIDs. An authorized administrator can separately inspect the specific
users requiring recovery in private, including SQL role, organization membership
and whether a profile/application already exists. Keep guest accounts with null
UIDs separate from registered identities. Do not infer ownership from an email match.

## Identity evidence and proposed mappings

For each affected SQL user ID, establish ownership through an approved team
identity-recovery process. Verify the new Firebase identity with the Admin SDK,
including issuer, audience, expiry and `email_verified=true`. A verified email on
its own is insufficient evidence to transfer an existing SQL account or its role.
Check the candidate UID directly in the correct Firebase project and confirm that
it is not already bound to another SQL user. Firebase UIDs are not portable by
changing the project's environment variable.

Prepare a private review sheet containing the SQL user ID, old and proposed UID,
evidence reference, current role/membership, collision checks and reviewer decision.
Do not save passwords, ID tokens or service-account keys in the sheet, repository,
chat or test results. Leave ambiguous cases unlinked for administrator review.

## Approval and controlled application

No migration is authorized or executed by this report. Before any update, obtain
explicit approval for the exact reviewed rows, take an approved private backup,
and define rollback and affected-session handling. Do not create/delete Firebase
accounts, automatically verify email, reset passwords, or promote roles as part of
linking. Any such operation needs its own explicit authorization.

An approved implementation should update only the chosen row's `firebase_uid`,
with a transaction and an expected-old-UID condition, require exactly one affected
row, and retain database uniqueness protections. Preserve role IDs, organization
membership, request ownership, profiles and applications. Stop and roll back on a
collision or unexpected row count; do not overwrite a conflicting account.

## Validation and rollback

After an approved update, verify sign-in, email verification, SQL-owned role,
organization approval restrictions, record ownership, and logout for that account.
Confirm that a preliminary or wrong-project token cannot access it. Rollback must
restore only the approved UID binding from the reviewed backup and must never
restore an entire database over concurrent application work.
