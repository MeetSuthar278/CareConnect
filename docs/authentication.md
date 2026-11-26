# Authentication

CareConnect uses Firebase Authentication to verify identity. MySQL stores the user's application role and profile. A Firebase login alone does not grant coordinator or organization permissions.

## Registration and access

Members and organization representatives register with an email address and password. Email verification is required. Organization representatives also need coordinator approval before managing services or accepting referrals. Coordinator accounts are provisioned by authorized administrators.

## Password rules

- At least eight characters.
- At least one uppercase letter and one special character.
- Lowercase letters and numbers are optional.
- Password and confirmation must match.

Firebase handles password reset. The application checks identity, role, ownership and protected form actions on the server.

## Configuration

Use the approved Firebase project and private Admin credentials. Store environment settings in `.env` locally or `deploy/.env.hosting` on the server. Never commit private keys or passwords. Existing accounts without a Firebase UID need authorized account linking; do not remove them to fix login.

See [account migration plan](testing/ACCOUNT_MIGRATION_PLAN.md) and [security audit](testing/SECURITY_AUDIT.md).
