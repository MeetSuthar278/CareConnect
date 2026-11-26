# Final test report

## Automated results — November 26, 2026

| Test | Result |
|---|---|
| Regression | 112 passed; 12 opt-in cases skipped |
| Separate MySQL/RabbitMQ integration | 12 passed |
| Browser checks | 97 passed using a local fake Firebase SDK |
| Python and templates | 75 Python files parsed; 36 templates compiled |
| Database | 21 tables; 34 foreign-key orphan checks, no orphans |
| Firebase password policy | 10 cases matched the live policy |
| Capacity reconciliation | Zero mismatches |

Tests covered authentication, permissions, request matching, backup referrals, deadlines, attendance, completion, feedback, duplicate events and publication retries. See the JSON evidence in this folder and the [event workflow report](EVENT_WORKFLOW_TEST_REPORT.md).

## Owner verification

Migration 003 preserved all 21 table fingerprints for retained data. Local startup reached 9/9 processes. Ten outbox events were published with zero pending or failed events. Both deadline checks returned no candidates.

The owner subsequently confirmed Azure deployment, HTTPS health and successful login for the three demo roles. The owner also reported application testing complete. Individual hosted test outcomes were not supplied with the exported documentation.

## Repeat tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools/run_isolated_integration.py
.\.venv\Scripts\python.exe tools/check_submission_readiness.py --database --rabbitmq
```

## Limits

Developer browser tests are not human participant tests. Actual verification/reset inbox delivery, participant observations, full broker outage recovery and production load/security certification are not established by these results. Keep the original detailed report in Git history and retain the raw evidence files.
