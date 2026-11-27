# CareConnect – Software Quality

**Group 4 | ENSF 607 | University of Calgary**

## 1. Testing Objective

Testing was performed to check that CareConnect works correctly, stores data consistently and processes events as expected.

## 2. Testing Methods

| Testing Type | Purpose |
|---|---|
| Regression testing | Check existing functionality after code changes. |
| Integration testing | Check communication between Flask, MySQL and RabbitMQ. |
| Browser testing | Check forms, navigation and user interactions. |
| Database testing | Check relationships, constraints and data consistency. |
| Deployment testing | Check application startup, HTTPS and hosted access. |

## 3. Test Results

| Test | Result |
|---|---|
| Regression tests | 112 passed |
| Integration tests | 12 passed |
| Browser checks | 97 passed |
| Firebase password policy | 10 cases matched |
| Foreign-key orphan checks | 34 checks, no orphans |
| Capacity reconciliation | No mismatches |

The 12 integration tests were run separately using MySQL and RabbitMQ.

## 4. Main Features Tested

- Registration, authentication and access control.
- Service requests and organization matching.
- Referral acceptance, rejection and backup matching.
- Deadline monitoring and coordinator alerts.
- Attendance, completion and feedback.
- Duplicate event handling and publication retries.
- Database integrity and capacity management.

## 5. Event Testing

All seven implemented RabbitMQ event types were covered by the integration testing process. The tests checked event processing, backup referrals, notifications and repeated event delivery.

## 6. Testing Limitations

Browser checks used a simulated Firebase SDK. Full broker outage recovery, production load testing and actual email delivery were not verified by these automated tests.

## 7. Testing Evidence

- [Final Test Report](FINAL_TEST_REPORT.md)
- [Event Workflow Test Report](EVENT_WORKFLOW_TEST_REPORT.md)
- [Database Compliance Report](DATABASE_COMPLIANCE_REPORT.md)
- [Deployment Test Report](DEPLOYMENT_TEST_REPORT.md)
- [Test Suite](../../tests/)

## 8. Conclusion

The recorded test results show that the main application features, database operations and event workflows work as expected under the tested conditions.
