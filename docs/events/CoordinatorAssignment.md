# Coordinator assignment of unmatched requests

Coordinators may use the existing All Requests assignment controls only for unmatched
requests without active/accepted/attended/completed referrals, before the original
attendance deadline, with fewer than three attempts. Earlier providers cannot be
retried. Pending automatic matching is left to the existing worker. Existing active
referrals are never replaced: the current referral enum has no cancelled/reassigned
state, and no schema changes were approved.

The GET choices and POST both use the same eligibility query as automatic matching:
approved organization, active service/offering/area, supported request priority, exact
service/area, unused provider and available capacity. Automatic matching retains its
workload/acceptance/attendance ranking. Manual selection deliberately chooses among
eligible providers; it does not bypass eligibility or extend the SLA.

POST requires the verified coordinator cookie, CSRF and expected latest referral ID
(0 for no previous referral). Its transaction locks request -> referrals -> current
active SQL coordinator -> eligible offerings. It verifies the source history, valid
state, contiguous attempts and deadline again, conditionally reserves one slot,
creates the next referral plus history attributed to the coordinator, marks the
request matched and enqueues ReferralCreated with the existing stable business key.
All effects commit together. The normal dispatcher and notification consumer continue
delivery. No extra notification mechanism or manual publish is introduced.

An exact retry recognizes the source, chosen provider and coordinator's saved manual
history, returning the existing referral. A stale different form/source cannot create
another active referral. Existing MySQL active-referral uniqueness and attempt/capacity
constraints remain final guards. A committed assignment makes delayed old backup
events harmless under existing source/state checks. SQL failure rolls back the whole
operation. SQLite tests cannot prove MySQL contention or deadlock behavior.

Expired historical demo requests and requests that exhausted all three attempts will
have no assignment action. Do not reset their priority/deadline or edit counters to
force a demonstration. Live assignment tests require an agreed eligible synthetic
request and provider; no live assignment was executed during implementation.
