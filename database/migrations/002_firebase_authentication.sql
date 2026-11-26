-- Firebase authentication schema migration.
-- Apply once to an existing database without firebase_uid.
-- Existing users and their relationships are preserved.

ALTER TABLE users
    ADD COLUMN firebase_uid VARCHAR(128)
        CHARACTER SET ascii COLLATE ascii_bin
        NULL AFTER email,
    MODIFY COLUMN password_hash VARCHAR(255) NULL,
    ADD CONSTRAINT uq_users_firebase_uid UNIQUE (firebase_uid);
