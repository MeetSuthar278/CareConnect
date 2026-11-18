-- Run once against the existing database. Preserves users and their roles.
USE careconnect_db;
ALTER TABLE users
    ADD COLUMN firebase_uid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL UNIQUE,
    MODIFY COLUMN password_hash VARCHAR(255) NULL;
