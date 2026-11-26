# Final submission checklist

| Deliverable | Status | Evidence / next action |
| --- | --- | --- |
| Existing features and teammate accounts | PASS | Current 17 users / four coordinators preserved; no deletes, provisioning or role reduction in this pass. |
| Regression tests | PASS | 112 ordinary tests; opt-in integration results recorded separately. |
| Real MySQL/RabbitMQ integration | PASS | Disposable containers, actual workers and synthetic data; see final test/event reports. |
| Registration password validation | PASS locally | All examples/mismatch/empty guards; Live policy also validated. Login complexity unchanged. |
| Email verification / role boundaries | PASS automated | Controlled provider/browser tests plus real SQL ownership checks. |
| Live Firebase accounts/config read | PASS | Three mapped users verified/enabled; correct project, email sign-in, localhost and enumeration protection. |
| Requested Firebase password policy | PASS | Live SDK accepted both supplied examples. |
| Live capacity caches | PASS | Eight corrections reported by owner. Read-only reconciliation found zero mismatches. |
| Real inbox / cross-device links / live role sign-ins | NOT TESTED | Team completes using owned accounts without changing teammates' credentials. |
| Human ad-hoc testing | MANUAL ACTION REQUIRED | Run checklist with participants; record actual anonymous observations, not automated results. |
| SQL requirement | PASS | 206 qualifying families; 150 active application families. Standalone academic file has 10 queries. |
| Referral normalization | PASS, owner verified live | Migration 003 rehearsed and applied. All 21 table fingerprints matched and the stored flag and index were removed. See the normalization review for remaining normal-form qualifications. |
| Live application startup | PASS, owner verified | 9/9 managed processes. Flask creation, seven worker entry points and 36 templates verified. MySQL, Firebase configuration and RabbitMQ topology passed. |
| Live worker backlog | PASS, owner verified | 10 published events and zero pending outbox items, publication errors or deadline candidates. |
| Current diagrams/schema docs | PASS | Final logical mapping supplements preserved historical JPEG/PDF artifacts and includes 21 tables/34 FKs. |
| Container build / local image smoke | PASS | Gunicorn, non-root/read-only root, localhost-only HTTP and read-only MySQL checks. |
| Full hosted Compose / public TLS | NOT TESTED | Config validated only; deployment requires review and separate provisioning. |
| Migration rehearsal | PASS, owner verified | Live migration rehearsal completed and all 21 fingerprints matched after migration. Production-scale load and reboot remain unverified. |
| Repository secret pattern scan | PASS scan completed | Historical public development credentials remain a remediation action; no private key pattern found. |
| Credential rotation | MANUAL ACTION REQUIRED | Coordinate reused DB/broker password rotation and env updates; no history rewrite or credential change done. |
| Git publication | MANUAL ACTION REQUIRED | Review all pre-existing deletions/untracked recovered files and exact staged diff; no commit/push/merge performed. |

ENSF 607: implementation and tested local integration are ready for team review;
submission sign-off remains MANUAL ACTION REQUIRED for usability and real inbox checks. ENSF 608: query-count, schema
and isolated initialization evidence pass; formal normalization claims and the
professor's exact standalone-query expectations require review. Neither course is
represented as unconditionally submission-ready while these items remain.

## Recommended staging and publication

See the [exact file lists and Git commands](testing/PUBLICATION_REVIEW.md).
