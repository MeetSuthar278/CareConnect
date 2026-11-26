# Frontend integration

Flask serves Jinja templates from `frontend/`. HTML, CSS, JavaScript and Bootstrap provide the interface. No Node build is required.

| Page group | Purpose |
|---|---|
| `/`, `/services`, `/get-connected` | Public information and service discovery |
| `/login`, `/signup` | Authentication and registration |
| `/member` | Member profile, requests, tracking and feedback |
| `/organization` | Organization profile, services and referrals |
| `/coordinator` | Approvals, request management and reports |

The frontend uses Flask routes and APIs. Firebase handles browser authentication. The backend checks permissions and validates data before saving it. Request filtering, sorting and pagination are handled in SQL.

The interface uses preferred time frame instead of emergency-style priority wording. The legacy `/demo/request` interface is restricted to local debug/testing and is disabled in hosted mode.

The final developer browser run recorded 97 checks. This is separate from human usability testing.
