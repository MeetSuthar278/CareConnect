-- MySQL 8.0.16+ / InnoDB. NOT applied automatically.
-- Stop writers and back up first. Never use the mysql client's --force option.
-- Baselines schema.sql / schema_safe.sql remain unchanged.
-- Fresh install: provision baseline, optionally seed, then apply this migration.
-- Existing install: apply ONLY this migration; do not rerun baseline or seed.
-- One-time, not rerunnable. Inspect SHOW CREATE TABLE after any failure.
-- DDL implicitly commits: the complete migration is NOT atomic.
-- Requires CREATE ROUTINE / ALTER ROUTINE and CREATE / ALTER privileges.
-- Run using a MySQL client that supports DELIMITER.
USE careconnect_db;

DELIMITER $$
CREATE PROCEDURE careconnect_migrate_001()
BEGIN
    DECLARE major_version INT;
    DECLARE minor_version INT;
    DECLARE patch_version INT;
    SET major_version = CAST(SUBSTRING_INDEX(VERSION(), '.', 1) AS UNSIGNED);
    SET minor_version = CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(VERSION(), '.', 2), '.', -1) AS UNSIGNED);
    SET patch_version = CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(VERSION(), '.', 3), '.', -1) AS UNSIGNED);
    IF VERSION() LIKE '%MariaDB%' OR major_version <> 8
       OR (minor_version = 0 AND patch_version < 16) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Requires MySQL 8.0.16+ (8.x), not MariaDB';
    END IF;
    -- Abort before table changes; never repair or delete existing data.
    IF EXISTS (
        SELECT request_id FROM referrals
        WHERE status IN ('sent', 'accepted', 'attended')
        GROUP BY request_id HAVING COUNT(*) > 1
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Multiple active referrals: review existing data first';
    END IF;
    IF EXISTS (
        SELECT 1 FROM organization_services
        WHERE active_referral_limit < 0 OR current_active_referrals < 0
           OR current_active_referrals > active_referral_limit
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid capacity counts: review existing data first';
    END IF;

    -- A NULL slot permits historical attempts; slot 1 permits only one active.
    -- Expression uses status only, preserving the request FK's cascade actions.
    ALTER TABLE referrals
        ADD COLUMN active_slot TINYINT GENERATED ALWAYS AS
            (CASE WHEN status IN ('sent', 'accepted', 'attended') THEN 1 ELSE NULL END) VIRTUAL,
        ADD UNIQUE KEY uq_referral_active_request (request_id, active_slot);
    ALTER TABLE organization_services
        ADD CONSTRAINT ck_org_service_capacity CHECK
            (active_referral_limit >= 0 AND current_active_referrals >= 0
             AND current_active_referrals <= active_referral_limit);
    -- Stable business key per recipient, e.g. referral-created:<referral_id>.
    -- Existing notifications retain NULL, with no changes to their contents.
    ALTER TABLE notifications
        ADD COLUMN deduplication_key VARCHAR(100) CHARACTER SET ascii COLLATE ascii_bin NULL,
        ADD UNIQUE KEY uq_notification_delivery (user_id, deduplication_key);

    -- Business mutation and outbox insertion must commit in the same transaction.
    -- Retain event_id / business key on retries. Dispatcher locks a row, publishes
    -- with confirms, then marks published_at. Never delete the row on send.
    -- Publish-before-commit crashes can redeliver; consumers MUST be idempotent.
    CREATE TABLE event_outbox (
        event_id VARCHAR(36) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
        deduplication_key VARCHAR(100) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        event_type VARCHAR(50) NOT NULL,
        event_version INT NOT NULL DEFAULT 1,
        request_id INT NOT NULL,
        payload JSON NOT NULL,
        created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        published_at DATETIME(6) NULL,
        attempts INT NOT NULL DEFAULT 0,
        last_error TEXT NULL,
        UNIQUE KEY uq_outbox_business_event (deduplication_key),
        INDEX idx_outbox_pending (published_at, available_at),
        CONSTRAINT ck_outbox_attempts CHECK (attempts >= 0),
        CONSTRAINT fk_outbox_request FOREIGN KEY (request_id)
            REFERENCES service_requests (request_id) ON DELETE RESTRICT ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
END$$
DELIMITER ;
CALL careconnect_migrate_001();
DROP PROCEDURE careconnect_migrate_001;
