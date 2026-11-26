# ENSF 608 database compliance

PASS: independently regenerated inventory contains **206 qualifying statement
or query families**, exceeding the supplied 25-statement requirement even using
only the 150 active application families. No filler queries were added.

| Classification | Qualifying families |
| --- | ---: |
| DDL | 26 = 21 CREATE TABLE + 5 ALTER TABLE |
| Seed INSERT | 20 table families |
| Application SELECT / ORM reads | 117 |
| Application INSERT / ORM creates | 18 |
| Application UPDATE / dirty-object flushes | 15 |
| Academic SELECT | 10 |
| Meaningful DELETE | 0 |
| Total | **206** |

Across the qualifying set, operation totals are SELECT 127, INSERT 38, UPDATE 15,
CREATE 21 and ALTER 5. Overlapping SQL shapes are 62 JOIN, 22 aggregate, 10 GROUP BY,
4 HAVING and 13 subquery families. These shape counts overlap and must not be added
to the total. ORM equivalences and optional clauses are recorded in the inventory.

`sql_inventory.csv` and `.json` give source locations, SQL/equivalents, purpose,
feature, group, stable fingerprint and verification scope. The script reads sources,
not a SQL execution log; most families have not each been individually exercised
against MySQL. Ten academic SELECTs were actually executed on isolated MySQL.

## Reconciliation with the earlier audit

Migration 003 adds one qualifying ALTER, bringing the prior 205 total to 206. The final full inventory includes additional
excluded read-only audit/health queries; use the JSON's full/excluded totals for
the current source revision. Historical 253-entry figures described the previous
audit and do not imply a changed academic requirement. Maintenance/control, legacy
debug queries and transaction boundaries remain excluded. Repeated seed rows,
two schema copies, page/sort variants and nested subqueries are not counted twice.

Migration 002 and the teammate's equivalent Firebase ALTER are one family despite
column-position/constraint-name syntax differences. The reviewed normalization
matches only those two known statements, so unrelated ALTER changes are not merged.
The current users DDL already includes Firebase support; it is intentionally different
from the older Git baseline. Tests compare the exact approved transformation and
otherwise preserve all 20 original table definitions and all 10 academic queries.

The 122 HEAD application families retain the prior source-reviewed comparison:
112 unchanged normalized families and 10 preserved/refactored families, with no
feature loss found. `sql_query_comparison.csv` now includes stable fingerprints so
new ancillary inventory entries do not make numeric IDs ambiguous. Earlier report
numeric IDs are historical; use the updated CSV/current inventory together.

## Schema and initialization

PASS: existing MySQL 8.0.46 metadata has 21 PKs, 34 FKs, 18 UNIQUE constraints,
3 CHECK constraints and 83 indexes (including primary/unique/FK-support indexes).
Read-only checks found zero orphans over all 34 declared single-column FKs.
UID is nullable VARCHAR(128), ASCII/ascii_bin with uniqueness; password_hash is
nullable VARCHAR(255). Four coordinator users remain; only one is Firebase mapped.

PASS: disposable MySQL tests initialized `schema.sql`, seeded only the disposable
database and applied workflow migration 001. They independently initialized
`schema_safe.sql` into a second fresh database and upgraded the legacy users DDL
with migration 002 in a third fresh database. Migration 002 was never reapplied to
the current database or a new baseline already containing UID support. FK, capacity
CHECK and one-active-referral UNIQUE rejection are exercised on real MySQL.

The owner reports correcting eight live offering caches. The November 26 read-only
recheck independently found zero capacity mismatches. Disposable MySQL reproduced
the demo data and tested migration 003. The owner subsequently rehearsed and applied
migration 003 live. All 21 fingerprints and retained referral attributes matched.
The legacy column and dedicated index were removed. Final owner-verified counts
were 21 tables, 17 users, seven organizations, 25 offerings, 40 requests, 29
referrals and 10 published outbox events, with zero capacity mismatches.

The baselines have 20 approved domain relations; migration 001 adds the operational
outbox and workflow guards. The historical JPEG/PDF diagrams omit Firebase UID,
outbox and workflow additions. They remain unchanged as teammate artifacts; the
current [logical mapping](../database/FINAL_LOGICAL_MAPPING.md) supplies the final
21-relation/34-FK diagram and migration delta.

## Efficiency and academic limits

PASS tests: SQL filters/sorts precede LIMIT/OFFSET, default 20 records plus lookahead,
stable sort tie-breaks, coordinator access to all 250 synthetic requests across 13
pages, global counts independent of pagination and per-request full history. Partner
metrics and service eligibility use grouped queries instead of per-row retrieval.
The earlier `query_measurements.json` is a single-run SQLite comparison, not a live
MySQL benchmark. Read-only EXPLAIN on the small live demo found two full-scan plan steps for
public search and three for coordinator search. These are optimizer estimates
on a small dataset. Production-scale load testing remains unperformed. See
[MySQL plans](mysql_query_plans.json).

MANUAL ACTION REQUIRED: confirm whether the professor requires 25 statements across
the project (satisfied) or specifically in one standalone demonstration SQL file
(that file has 10). Strict all-table 3NF is not established: read the actual FD
analysis before claiming compliance. No live schema normalization is authorized
implicitly by this report.

The final inventory contains 306 entries, including 100 excluded families. The
11 SELECTs in demo_data.sql are validation, while its writes prepare a synthetic
scenario. Neither group changes the academic or baseline seed counts. The superseded proposal copy remains excluded.
