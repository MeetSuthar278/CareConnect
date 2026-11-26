# Live referral migration 003

**Completed on the current live database.** The owner verified the restore
rehearsal and live migration. All 21 table fingerprints and retained referral
attributes matched. The redundant column and its index were removed, and 9/9
managed processes started. The postchecks reported 10 published events and zero
pending outbox events, publication errors, deadline candidates or capacity
mismatches.

Keep these commands as a maintenance and recovery reference for a separate
legacy installation. Do not rerun migration 003 on the completed database.
Fresh schemas already derive backup status from the attempt number.

## Maintenance and backup

Run these commands later, from the project root, during an approved maintenance
window. This example targets the reviewed local Docker MySQL container. For a
different installation, verify the container, database and connection separately.
Verify the private .env points to this same instance. Stop scheduled tasks and
external web or worker processes, including all dispatchers and deadline scanners,
and keep the database and broker up. Allow in-flight work to finish first. If the
managed local runtime is running, stop it with the following command.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_local.ps1
```

Capture a complete backup and row fingerprints with all writers stopped. Use a
private directory outside the checkout with access limited to the operator.
The container must have its original private MYSQL_ROOT_PASSWORD in its environment.
The following commands use it without printing the value.

```powershell
$mysql = 'careconnect_demo-om-rabbitmq-demo-mysql-1'
$dbName = 'careconnect_db'
$python = '.\.venv\Scripts\python.exe'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $env:USERPROFILE ".careconnect\backups\referral-003-$stamp"
New-Item -ItemType Directory -Path $backupDir -ErrorAction Stop | Out-Null
$before = & $python tools/snapshot_migration_003.py
if ($LASTEXITCODE -ne 0) { throw 'Pre-migration snapshot failed' }
$before | Set-Content -LiteralPath (Join-Path $backupDir 'before.json') -Encoding UTF8
$state = $before | ConvertFrom-Json
if (!$state.legacy_flag_present -or $state.legacy_flag_mismatches -ne 0) { throw 'Unexpected legacy state' }
if ($state.tables.referrals.count -ne 29 -or $state.tables.users.count -ne 17 -or
    $state.tables.organizations.count -ne 7 -or $state.tables.organization_services.count -ne 25 -or
    $state.tables.service_requests.count -ne 40) { throw 'Live totals differ from the reviewed snapshot' }
$remoteDump = "/tmp/careconnect-003-$stamp.sql"
$localDump = Join-Path $backupDir 'before.sql'
docker exec $mysql sh -ec 'umask 077; MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --quick --routines --events --triggers --no-tablespaces --set-gtid-purged=OFF --default-character-set=utf8mb4 --result-file="$1" "$2"' sh $remoteDump $dbName
if ($LASTEXITCODE -ne 0) { throw 'Backup failed' }
docker cp "${mysql}:$remoteDump" $localDump
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $localDump) -or (Get-Item -LiteralPath $localDump).Length -eq 0) { throw 'Backup copy failed' }
Get-FileHash -Algorithm SHA256 -LiteralPath $localDump | Select-Object -ExpandProperty Hash |
    Set-Content -LiteralPath (Join-Path $backupDir 'before.sql.sha256') -Encoding ASCII
docker exec $mysql rm -- $remoteDump
if ($LASTEXITCODE -ne 0) { throw 'Remove the private duplicate backup from the container before continuing' }
```

Restore the backup into a separate, empty MySQL 8 rehearsal container before the
live ALTER. Never use the existing MySQL container for this restore. Use the
same version or image digest as the live instance, and keep MySQL's event
scheduler disabled. Copy before.sql into that disposable container and load it
into a fresh database with these commands. Set rehearsalMySql to the name of
the new container you provisioned with private credentials.

```powershell
if (-not $rehearsalMySql -or $rehearsalMySql -eq $mysql) { throw 'Select a separate rehearsal container' }
$liveId = docker inspect --format '{{.Id}}' $mysql
if ($LASTEXITCODE -ne 0) { throw 'Could not identify live container' }
$rehearsalId = docker inspect --format '{{.Id}}' $rehearsalMySql
if ($LASTEXITCODE -ne 0 -or $rehearsalId -eq $liveId) { throw 'Could not verify isolated restore target' }
docker exec $rehearsalId sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -e "SET GLOBAL event_scheduler=OFF; CREATE DATABASE cc003_restore CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"'
if ($LASTEXITCODE -ne 0) { throw 'Rehearsal database creation failed' }
docker cp $localDump "${rehearsalId}:/tmp/cc003-backup.sql"
if ($LASTEXITCODE -ne 0) { throw 'Rehearsal backup copy failed' }
docker exec $rehearsalId sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4 cc003_restore < /tmp/cc003-backup.sql'
if ($LASTEXITCODE -ne 0) { throw 'Backup restore failed' }
```

Compare the rehearsal row fingerprints with before.json using the snapshot tool
and a private DATABASE_URL pointing to cc003_restore. Verify all counts and the
legacy column before rehearsing the ALTER with the same batch command below,
substituting the rehearsal container and database. Keep the backup and its
checksum private. The project integration tests rehearse the migration on
synthetic data. The project owner reported completing that rehearsal for the current live migration.

## Apply and verify

Confirm the pre-migration snapshot is still current and all writers are stopped.
Run the migration with the MySQL client in batch mode. Its preconditions reject
unexpected schema, flag mismatches or inconsistent attempt sequences. Use a
MySQL account with the required ALTER and routine privileges. Do not pass
`--force`. Record the exit status and inspect the schema even on failure.

```powershell
Get-Content -LiteralPath .\database\migrations\003_derive_referral_backup.sql -Raw -Encoding UTF8 |
    docker exec -i $mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4 "$1"' sh $dbName
if ($LASTEXITCODE -ne 0) { throw 'Migration client failed. Inspect physical schema before proceeding.' }
$after = & $python tools/snapshot_migration_003.py
if ($LASTEXITCODE -ne 0) { throw 'Post-migration snapshot failed' }
$after | Set-Content -LiteralPath (Join-Path $backupDir 'after.json') -Encoding UTF8
$postState = $after | ConvertFrom-Json
if ($postState.legacy_flag_present) { throw 'Legacy flag still present' }
if (($state.tables | ConvertTo-Json -Depth 6 -Compress) -cne ($postState.tables | ConvertTo-Json -Depth 6 -Compress)) {
    throw 'Row fingerprints differ. Keep writers stopped.'
}
& $python tools/check_submission_readiness.py --database --rabbitmq
if ($LASTEXITCODE -ne 0) { throw 'Schema or broker check failed. Keep writers stopped.' }
```

Fingerprints cover all base-table rows, sorted by their primary keys, excluding
only the removed flag. Keep the application stopped until the table counts,
fingerprints, indexes and readiness checks agree. Then start the normalized
release and check its health. If it reports pending business work, review that
work before enabling processing.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check_health.ps1
```

## Failure and recovery

MySQL DDL commits implicitly. A failed CALL may leave the helper procedure in
place, and a lost connection can hide a successful ALTER. Inspect the physical
schema and compare fingerprints before deciding which state you are in.

```powershell
"SHOW CREATE TABLE referrals; SHOW PROCEDURE STATUS WHERE Db = DATABASE() AND Name = 'careconnect_migrate_003';" |
    docker exec -i $mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot "$1"' sh $dbName
```

If the flag is intact, resolve the specific precondition failure before retrying.
Drop only the migration-owned helper if a failed attempt left it behind. If the
flag is gone and the fingerprints match, complete postchecks and use the new
release. Do not rerun the migration on that schema.

If an approved rollback needs the legacy code, keep writers stopped. Rehearse
the following inverse on a copy first. The historical precondition guarantees
that the original flag equals this expression. Adding the column and backfilling
are separate operations. Check both before restarting the previous release.

```sql
ALTER TABLE referrals
    ADD COLUMN is_backup BOOLEAN NOT NULL DEFAULT FALSE AFTER attempt_number,
    ADD INDEX idx_ref_is_backup (is_backup);
START TRANSACTION;
UPDATE referrals
SET is_backup = (attempt_number > 1), updated_at = updated_at;
SELECT COUNT(*) AS mismatches FROM referrals
WHERE NOT (is_backup <=> (attempt_number > 1));
-- COMMIT only after verifying zero mismatches in this session.
```

Recheck the row fingerprints and the restored legacy schema. If any other rows
or structure differ, keep writers stopped and investigate using the verified
backup in a separate recovery instance. Replacing the live database requires
separate authorization. Never reset it or rerun baseline, seed or earlier
migrations as a recovery step.
