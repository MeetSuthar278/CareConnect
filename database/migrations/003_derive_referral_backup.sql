-- MySQL 8.0.16+ only. Run on the selected, existing legacy database, with
-- writers stopped and a verified backup. Fresh schemas already omit is_backup.
-- Use the mysql client with DELIMITER support. Never use --force.
-- ALTER TABLE commits implicitly. See docs/database/REFERRAL_MIGRATION_RUNBOOK.md.

DELIMITER $$
CREATE PROCEDURE careconnect_migrate_003()
BEGIN
    IF DATABASE() IS NULL OR VERSION() LIKE '%MariaDB%'
       OR CAST(SUBSTRING_INDEX(VERSION(), '.', 1) AS UNSIGNED) <> 8 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Select the reviewed MySQL 8 database';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema=DATABASE() AND table_name='referrals' AND engine='InnoDB'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema=DATABASE() AND table_name='referrals'
          AND column_name='is_backup' AND data_type='tinyint' AND is_nullable='NO'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema=DATABASE() AND table_name='referrals'
          AND column_name='active_slot' AND extra LIKE '%VIRTUAL GENERATED%'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema=DATABASE() AND table_name='referrals'
          AND index_name='idx_ref_is_backup' AND column_name='is_backup' AND non_unique=1
    ) OR NOT EXISTS (
        SELECT index_name FROM information_schema.statistics
        WHERE table_schema=DATABASE() AND table_name='referrals'
          AND index_name='uq_referral_active_request' AND non_unique=0
        GROUP BY index_name
        HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index)='request_id,active_slot'
    ) OR NOT EXISTS (
        SELECT index_name FROM information_schema.statistics
        WHERE table_schema=DATABASE() AND table_name='referrals'
          AND index_name='uq_request_attempt' AND non_unique=0
        GROUP BY index_name
        HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index)='request_id,attempt_number'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Expected legacy referral schema missing; inspect before proceeding';
    END IF;

    IF EXISTS (
        SELECT 1 FROM referrals WHERE NOT (is_backup <=> (attempt_number > 1))
    ) OR EXISTS (
        SELECT request_id FROM referrals GROUP BY request_id
        HAVING MIN(attempt_number) <> 1 OR MAX(attempt_number) <> COUNT(*)
            OR COUNT(DISTINCT attempt_number) <> COUNT(*) OR MAX(attempt_number) > 3
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Referral flag or attempt history mismatch; no ALTER performed';
    END IF;

    ALTER TABLE referrals DROP INDEX idx_ref_is_backup, DROP COLUMN is_backup;
END$$
DELIMITER ;
CALL careconnect_migrate_003();
DROP PROCEDURE careconnect_migrate_003;
