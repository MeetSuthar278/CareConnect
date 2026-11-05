-- ============================================================================
-- CareConnect: Community Wellness Referral and Follow-Up System
-- Course: ENSF 608 — Database Systems | University of Calgary | SDG 17
-- Group 4 | Lead Database Engineer: Raj Jigneshkumar Patel
-- Engine: MySQL 8.0+ (InnoDB) | Charset: utf8mb4 | Collation: utf8mb4_unicode_ci
-- Specification: Exactly 20 Relational Entities as per Approved Project Proposal
-- ============================================================================

DROP DATABASE IF EXISTS careconnect_db;
CREATE DATABASE careconnect_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE careconnect_db;

-- ----------------------------------------------------------------------------
-- Disable foreign key checks during schema creation
-- ----------------------------------------------------------------------------
SET FOREIGN_KEY_CHECKS = 0;


-- ============================================================================
-- SECTION 1: PEOPLE AND ACCESS
-- ============================================================================

-- 1. ROLES TABLE
-- Role definitions: member, representative, coordinator
CREATE TABLE roles (
    role_id INT AUTO_INCREMENT PRIMARY KEY,
    role_name VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. USERS TABLE
-- Login accounts for all system participants; identifies actor for every action
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_users_role
        FOREIGN KEY (role_id) REFERENCES roles (role_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_users_role (role_id),
    INDEX idx_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. MEMBER_PROFILES TABLE
-- Member contact details and location (1:0..1 relationship with users)
CREATE TABLE member_profiles (
    profile_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    phone VARCHAR(25) NOT NULL,
    address VARCHAR(255) NULL,
    city VARCHAR(100) NOT NULL DEFAULT 'Calgary',
    preferred_contact_method ENUM('email', 'phone', 'sms') NOT NULL DEFAULT 'email',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_member_profiles_user
        FOREIGN KEY (user_id) REFERENCES users (user_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_member_city (city)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- SECTION 2: THE PARTNER NETWORK & CATALOG
-- ============================================================================

-- 4. ORGANIZATIONS TABLE
-- Approved, pending, or suspended partner service providers
CREATE TABLE organizations (
    organization_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    contact_email VARCHAR(120) NOT NULL,
    contact_phone VARCHAR(25) NOT NULL,
    address VARCHAR(255) NULL,
    city VARCHAR(100) NOT NULL DEFAULT 'Calgary',
    status ENUM('pending', 'approved', 'suspended') NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_organizations_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. ORGANIZATION_REPRESENTATIVES TABLE
-- Links a user account to the partner organization they act for
CREATE TABLE organization_representatives (
    representative_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    organization_id INT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    job_title VARCHAR(100) NULL,
    phone VARCHAR(25) NULL,
    is_primary_contact BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_org_reps_user
        FOREIGN KEY (user_id) REFERENCES users (user_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_org_reps_org
        FOREIGN KEY (organization_id) REFERENCES organizations (organization_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_org_reps_org (organization_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. ORGANIZATION_APPLICATIONS TABLE
-- Registration requests and coordinator approvals/rejections
CREATE TABLE organization_applications (
    application_id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    submitted_by_user_id INT NOT NULL,
    reviewed_by_user_id INT NULL,
    status ENUM('submitted', 'under_review', 'approved', 'rejected') NOT NULL DEFAULT 'submitted',
    submission_notes TEXT NULL,
    decision_notes TEXT NULL,
    decided_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_org_apps_org
        FOREIGN KEY (organization_id) REFERENCES organizations (organization_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_org_apps_submitted_by
        FOREIGN KEY (submitted_by_user_id) REFERENCES users (user_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_org_apps_reviewed_by
        FOREIGN KEY (reviewed_by_user_id) REFERENCES users (user_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX idx_org_apps_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. SERVICE_CATEGORIES TABLE
-- High-level grouping of support services (e.g., Food Assistance, Peer Support)
CREATE TABLE service_categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. SERVICES TABLE
-- Concrete support services with delivery modes
CREATE TABLE services (
    service_id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    name VARCHAR(150) NOT NULL,
    description TEXT NULL,
    delivery_mode ENUM('in-person', 'online', 'phone') NOT NULL DEFAULT 'in-person',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_services_category
        FOREIGN KEY (category_id) REFERENCES service_categories (category_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_services_category (category_id),
    INDEX idx_services_delivery_mode (delivery_mode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. SERVICE_AREAS TABLE
-- Predefined list of geographic zones/quadrants for localized matching
CREATE TABLE service_areas (
    area_id INT AUTO_INCREMENT PRIMARY KEY,
    city VARCHAR(100) NOT NULL DEFAULT 'Calgary',
    region_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_area_city_region (city, region_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. ORGANIZATION_SERVICES TABLE
-- Services an organization offers, with active/paused status and active referral limits
CREATE TABLE organization_services (
    organization_service_id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT NOT NULL,
    service_id INT NOT NULL,
    service_area_id INT NOT NULL,
    status ENUM('active', 'paused') NOT NULL DEFAULT 'active',
    active_referral_limit INT NOT NULL DEFAULT 10,
    current_active_referrals INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_org_svc_area (organization_id, service_id, service_area_id),
    CONSTRAINT fk_org_svc_org
        FOREIGN KEY (organization_id) REFERENCES organizations (organization_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_org_svc_svc
        FOREIGN KEY (service_id) REFERENCES services (service_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_org_svc_area
        FOREIGN KEY (service_area_id) REFERENCES service_areas (area_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_org_svc_status (status),
    INDEX idx_org_svc_counts (current_active_referrals, active_referral_limit)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. PRIORITY_LEVELS TABLE
-- High (6h), Medium (12h), or Low (24h) attendance deadline definitions
CREATE TABLE priority_levels (
    priority_id INT AUTO_INCREMENT PRIMARY KEY,
    level_name ENUM('High', 'Medium', 'Low') NOT NULL UNIQUE,
    deadline_hours INT NOT NULL,
    description VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12. SERVICE_PRIORITY_SUPPORT TABLE
-- Priorities supported by an organization for each offered service
CREATE TABLE service_priority_support (
    support_id INT AUTO_INCREMENT PRIMARY KEY,
    organization_service_id INT NOT NULL,
    priority_id INT NOT NULL,
    is_supported BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE KEY uq_orgsvc_priority (organization_service_id, priority_id),
    CONSTRAINT fk_sps_org_service
        FOREIGN KEY (organization_service_id) REFERENCES organization_services (organization_service_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_sps_priority
        FOREIGN KEY (priority_id) REFERENCES priority_levels (priority_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 13. ORGANIZATION_AVAILABILITY TABLE
-- Historical log of service pause and resume actions for partner availability reports
CREATE TABLE organization_availability (
    availability_id INT AUTO_INCREMENT PRIMARY KEY,
    organization_service_id INT NOT NULL,
    action ENUM('pause', 'resume') NOT NULL,
    reason VARCHAR(255) NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recorded_by_user_id INT NOT NULL,
    CONSTRAINT fk_org_avail_service
        FOREIGN KEY (organization_service_id) REFERENCES organization_services (organization_service_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_org_avail_user
        FOREIGN KEY (recorded_by_user_id) REFERENCES users (user_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_org_avail_action (action, recorded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- SECTION 3: REQUESTS, REFERRALS & WORKFLOW
-- ============================================================================

-- 14. SERVICE_REQUESTS TABLE
-- The central record: member requests with service, area, priority, and attendance deadline
CREATE TABLE service_requests (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    member_id INT NOT NULL,
    service_id INT NOT NULL,
    service_area_id INT NOT NULL,
    priority_id INT NOT NULL,
    title VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    status ENUM('submitted', 'matched', 'in_progress', 'completed', 'unmatched', 'cancelled') NOT NULL DEFAULT 'submitted',
    attendance_deadline DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_req_member
        FOREIGN KEY (member_id) REFERENCES users (user_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_req_service
        FOREIGN KEY (service_id) REFERENCES services (service_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_req_area
        FOREIGN KEY (service_area_id) REFERENCES service_areas (area_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_req_priority
        FOREIGN KEY (priority_id) REFERENCES priority_levels (priority_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_req_status (status),
    INDEX idx_req_deadline (attendance_deadline)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 15. REFERRALS TABLE
-- Attempt to send request to partner (attempt 1 = primary, attempt 2+ = backup partner)
CREATE TABLE referrals (
    referral_id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL,
    organization_id INT NOT NULL,
    attempt_number INT NOT NULL DEFAULT 1,
    is_backup BOOLEAN NOT NULL DEFAULT FALSE,
    status ENUM('sent', 'accepted', 'rejected', 'timed_out', 'attended', 'completed') NOT NULL DEFAULT 'sent',
    response_deadline DATETIME NOT NULL,
    responded_at DATETIME NULL,
    rejection_reason VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_request_attempt (request_id, attempt_number),
    CONSTRAINT fk_ref_request
        FOREIGN KEY (request_id) REFERENCES service_requests (request_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_ref_org
        FOREIGN KEY (organization_id) REFERENCES organizations (organization_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_ref_status (status),
    INDEX idx_ref_is_backup (is_backup),
    INDEX idx_ref_response_deadline (response_deadline)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 16. REFERRAL_STATUS_HISTORY TABLE
-- Audit log of each status transition with timestamps and responsible actors
CREATE TABLE referral_status_history (
    history_id INT AUTO_INCREMENT PRIMARY KEY,
    referral_id INT NOT NULL,
    old_status VARCHAR(50) NULL,
    new_status VARCHAR(50) NOT NULL,
    changed_by_user_id INT NULL,
    notes VARCHAR(255) NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_rsh_referral
        FOREIGN KEY (referral_id) REFERENCES referrals (referral_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_rsh_user
        FOREIGN KEY (changed_by_user_id) REFERENCES users (user_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX idx_rsh_referral (referral_id),
    INDEX idx_rsh_new_status (new_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- SECTION 4: OUTCOMES, FEEDBACK & NOTIFICATIONS
-- ============================================================================

-- 17. ATTENDANCE_RECORDS TABLE
-- Captures when partner first begins helping; proves if the deadline was met (1:0..1)
CREATE TABLE attendance_records (
    attendance_id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL UNIQUE,
    referral_id INT NOT NULL,
    attended_by_representative_id INT NOT NULL,
    first_attended_at DATETIME NOT NULL,
    is_on_time BOOLEAN NOT NULL,
    notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_att_request
        FOREIGN KEY (request_id) REFERENCES service_requests (request_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_att_referral
        FOREIGN KEY (referral_id) REFERENCES referrals (referral_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_att_rep
        FOREIGN KEY (attended_by_representative_id) REFERENCES organization_representatives (representative_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_att_is_on_time (is_on_time),
    INDEX idx_att_first_attended (first_attended_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 18. SERVICE_COMPLETIONS TABLE
-- Closes the request, records resolution outcome and unlocks feedback (1:0..1)
CREATE TABLE service_completions (
    completion_id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL UNIQUE,
    referral_id INT NOT NULL,
    completed_at DATETIME NOT NULL,
    outcome ENUM('successful', 'partially_successful', 'referred_to_external', 'unsuccessful') NOT NULL DEFAULT 'successful',
    summary_notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_comp_request
        FOREIGN KEY (request_id) REFERENCES service_requests (request_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_comp_referral
        FOREIGN KEY (referral_id) REFERENCES referrals (referral_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_comp_outcome (outcome)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 19. FEEDBACK TABLE
-- Member's 'helpful' yes/no rating and optional comment (1:0..1 per completed request)
CREATE TABLE feedback (
    feedback_id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL UNIQUE,
    member_id INT NOT NULL,
    organization_id INT NOT NULL,
    is_helpful BOOLEAN NOT NULL,
    rating TINYINT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT NULL,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_fb_request
        FOREIGN KEY (request_id) REFERENCES service_requests (request_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_fb_member
        FOREIGN KEY (member_id) REFERENCES users (user_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_fb_org
        FOREIGN KEY (organization_id) REFERENCES organizations (organization_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    INDEX idx_fb_org_helpful (organization_id, is_helpful)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 20. NOTIFICATIONS TABLE
-- In-app alerts to users regarding referrals, deadlines, and feedback invitations
CREATE TABLE notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    type ENUM('referral_sent', 'referral_accepted', 'referral_rejected', 'backup_rescue', 'deadline_approaching', 'deadline_missed', 'feedback_invitation', 'system') NOT NULL,
    title VARCHAR(150) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    related_request_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_notif_user
        FOREIGN KEY (user_id) REFERENCES users (user_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_notif_request
        FOREIGN KEY (related_request_id) REFERENCES service_requests (request_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX idx_notif_user_read (user_id, is_read)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------------------------
-- Re-enable foreign key checks
-- ----------------------------------------------------------------------------
SET FOREIGN_KEY_CHECKS = 1;

