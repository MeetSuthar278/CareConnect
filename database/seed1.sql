-- ============================================================================
-- CareConnect: Comprehensive Seed Data Script
-- Course: ENSF 608 — Database Systems | University of Calgary | SDG 17
-- Group 4 | Lead Database Engineer: Raj Jigneshkumar Patel
-- Engine: MySQL 8.0+ (InnoDB)
-- Populates all 20 relational tables with realistic Calgary domain data
-- ============================================================================

USE careconnect_db;

SET FOREIGN_KEY_CHECKS = 0;

DELETE FROM notifications;
DELETE FROM feedback;
DELETE FROM service_completions;
DELETE FROM attendance_records;
DELETE FROM referral_status_history;
DELETE FROM referrals;
DELETE FROM service_requests;
DELETE FROM organization_availability;
DELETE FROM service_priority_support;
DELETE FROM organization_services;
DELETE FROM priority_levels;
DELETE FROM service_areas;
DELETE FROM services;
DELETE FROM service_categories;
DELETE FROM organization_applications;
DELETE FROM organization_representatives;
DELETE FROM organizations;
DELETE FROM member_profiles;
DELETE FROM users;
DELETE FROM roles;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================================
-- 1. ROLES
-- ============================================================================
INSERT INTO roles (role_id, role_name, description) VALUES
(1, 'member', 'Community member seeking non-medical wellness and social support services'),
(2, 'representative', 'Authorized representative of a partner service organization'),
(3, 'coordinator', 'CareConnect administrative coordinator managing partner approvals and routing');

-- ============================================================================
-- 2. USERS
-- ============================================================================
-- Passwords hashed with bcrypt placeholder
INSERT INTO users (user_id, role_id, email, password_hash, is_active, created_at) VALUES
-- Coordinators
(1, 3, 'raj.patel@careconnect.ca', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-01 08:00:00'),
(2, 3, 'mansi.radadiya@careconnect.ca', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-01 08:05:00'),
(3, 3, 'meet.suthar@careconnect.ca', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-01 08:10:00'),

-- Organization Representatives
(4, 2, 'sarah.connor@calgaryfoodbank.com', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-05 09:00:00'),
(5, 2, 'david.lee@distresscentre.com', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-05 09:15:00'),
(6, 2, 'brenda.vance@kerbycentre.com', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-06 10:00:00'),
(7, 2, 'marcus.thorne@trellis.org', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-06 10:30:00'),
(8, 2, 'lisa.wong@horizonwellness.org', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-10 11:00:00'),

-- Community Members
(9,  1, 'john.doe@gmail.com', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-12 14:00:00'),
(10, 1, 'alice.smith@yahoo.ca', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-12 15:30:00'),
(11, 1, 'carlos.mendez@outlook.com', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-15 09:45:00'),
(12, 1, 'emily.white@gmail.com', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-16 11:10:00'),
(13, 1, 'fatima.alzahra@hotmail.com', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-18 13:20:00'),
(14, 1, 'robert.chen@gmail.com', '$2y$10$e8bM6l5F7O1i6VwG9jKlOeL6oPn9sY1xQe3uR8tK1vL5mN7oP9qRe', TRUE, '2026-09-20 16:00:00');

-- ============================================================================
-- 3. MEMBER_PROFILES
-- ============================================================================
INSERT INTO member_profiles (profile_id, user_id, first_name, last_name, phone, address, city, preferred_contact_method) VALUES
(1, 9,  'John',   'Doe',     '403-555-0101', '124 8th Ave SW',       'Calgary', 'phone'),
(2, 10, 'Alice',  'Smith',   '403-555-0102', '742 Centre St N',      'Calgary', 'email'),
(3, 11, 'Carlos', 'Mendez',  '403-555-0103', '523 17th Ave SE',      'Calgary', 'sms'),
(4, 12, 'Emily',  'White',   '403-555-0104', '310 Crowfoot Way NW',  'Calgary', 'email'),
(5, 13, 'Fatima', 'Al-Zahra','403-555-0105', '88 Sunpark Plaza SE',  'Calgary', 'phone'),
(6, 14, 'Robert', 'Chen',    '403-555-0106', '910 Bow Valley Trail', 'Calgary', 'email');

-- ============================================================================
-- 4. ORGANIZATIONS
-- ============================================================================
INSERT INTO organizations (organization_id, name, contact_email, contact_phone, address, city, status, created_at) VALUES
(1, 'Calgary Food Bank',          'referrals@calgaryfoodbank.com',  '403-253-2055', '5000 11 St SE',     'Calgary', 'approved',  '2026-09-02 09:00:00'),
(2, 'Distress Centre Calgary',    'partnerships@distresscentre.com','403-266-4357', '300 6th Ave SE',     'Calgary', 'approved',  '2026-09-02 09:30:00'),
(3, 'Kerby Centre for Seniors',   'intake@kerbycentre.com',         '403-265-0661', '1133 7th Ave SW',    'Calgary', 'approved',  '2026-09-03 10:00:00'),
(4, 'Trellis Society for Youth',  'connect@trellis.org',            '403-201-1960', '1010 1st St SW',     'Calgary', 'approved',  '2026-09-03 11:00:00'),
(5, 'Horizon Wellness Network',   'contact@horizonwellness.org',    '403-555-8910', '404 4th St SW',      'Calgary', 'pending',   '2026-09-25 14:00:00'),
(6, 'Community Outreach Hub',     'info@communityhub.org',          '403-555-3344', '12 Forest Lawn SE',  'Calgary', 'suspended', '2026-08-15 10:00:00');

-- ============================================================================
-- 5. ORGANIZATION_REPRESENTATIVES
-- ============================================================================
INSERT INTO organization_representatives (representative_id, user_id, organization_id, full_name, job_title, phone, is_primary_contact) VALUES
(1, 4, 1, 'Sarah Connor', 'Client Intake Lead',          '403-253-2059', TRUE),
(2, 5, 2, 'David Lee',    'Crisis Response Coordinator', '403-266-4359', TRUE),
(3, 6, 3, 'Brenda Vance', 'Seniors Wellness Navigator',  '403-265-0665', TRUE),
(4, 7, 4, 'Marcus Thorne','Youth Services Manager',      '403-201-1965', TRUE),
(5, 8, 5, 'Lisa Wong',    'Program Director',            '403-555-8912', TRUE);

-- ============================================================================
-- 6. ORGANIZATION_APPLICATIONS
-- ============================================================================
INSERT INTO organization_applications (application_id, organization_id, submitted_by_user_id, reviewed_by_user_id, status, submission_notes, decision_notes, decided_at, created_at) VALUES
(1, 1, 4, 1, 'approved', 'Annual re-registration for Calgary Food Bank non-medical hampers.', 'Verified registered charity status and capacity limits.', '2026-09-03 11:00:00', '2026-09-02 09:30:00'),
(2, 2, 5, 1, 'approved', 'Distress Centre 24/7 peer support connection program.', 'Accredited non-medical crisis line. Approved.', '2026-09-03 11:15:00', '2026-09-02 10:00:00'),
(3, 3, 6, 2, 'approved', 'Seniors social connection and mobility assistance application.', 'Documentation approved for Kerby Centre.', '2026-09-04 14:00:00', '2026-09-03 10:30:00'),
(4, 4, 7, 2, 'approved', 'Trellis youth and family non-medical mentorship initiative.', 'All criteria verified.', '2026-09-04 14:30:00', '2026-09-03 11:30:00'),
(5, 5, 8, NULL, 'submitted', 'New wellness clinic seeking community referral onboarding.', 'Application pending background credential check.', NULL, '2026-09-25 14:15:00');

-- ============================================================================
-- 7. SERVICE_CATEGORIES
-- ============================================================================
INSERT INTO service_categories (category_id, name, description, is_active) VALUES
(1, 'Food Assistance',       'Nutritional hampers, grocery delivery, and community food pantries', TRUE),
(2, 'Peer Support',          'Non-clinical peer listening, emotional check-ins, and support circles', TRUE),
(3, 'Seniors\' Activities',   'Social companionship, digital literacy, and active aging workshops', TRUE),
(4, 'Youth & Family Support','After-school mentoring, life skills, and family wellness navigation', TRUE);

-- ============================================================================
-- 8. SERVICES
-- ============================================================================
INSERT INTO services (service_id, category_id, name, description, delivery_mode, is_active) VALUES
(1, 1, 'Emergency Food Hamper',     '7-day emergency food hamper pickup for individuals and families', 'in-person', TRUE),
(2, 1, 'Mobile Grocery Delivery',    'Delivery of pantry essentials for homebound or isolated members',  'in-person', TRUE),
(3, 2, 'Peer Support Check-In',      'Scheduled phone check-in and active listening with a peer buddy', 'phone',     TRUE),
(4, 2, 'Virtual Support Circle',     'Weekly online group peer wellness discussion sessions',           'online',    TRUE),
(5, 3, 'Senior Companionship Visit', 'In-person social visit and wellness check for elderly citizens',  'in-person', TRUE),
(6, 3, 'Senior Tech Tutoring',       'One-on-one phone and tablet guidance to stay connected',          'in-person', TRUE),
(7, 4, 'Youth Mentorship Match',     'Positive role-modeling and after-school guidance for youth',       'in-person', TRUE);

-- ============================================================================
-- 9. SERVICE_AREAS
-- ============================================================================
INSERT INTO service_areas (area_id, city, region_name, is_active) VALUES
(1, 'Calgary', 'Downtown',  TRUE),
(2, 'Calgary', 'North',     TRUE),
(3, 'Calgary', 'South',     TRUE),
(4, 'Calgary', 'East',      TRUE),
(5, 'Calgary', 'West',      TRUE);

-- ============================================================================
-- 10. ORGANIZATION_SERVICES
-- ============================================================================
INSERT INTO organization_services (organization_service_id, organization_id, service_id, service_area_id, status, active_referral_limit, current_active_referrals) VALUES
-- Calgary Food Bank
(1, 1, 1, 1, 'active', 15, 2), -- Hamper in Downtown
(2, 1, 1, 2, 'active', 12, 1), -- Hamper in North
(3, 1, 1, 3, 'active', 10, 0), -- Hamper in South
(4, 1, 2, 1, 'active',  8, 1), -- Delivery in Downtown

-- Distress Centre Calgary
(5, 2, 3, 1, 'active', 20, 3), -- Peer Check-In in Downtown
(6, 2, 3, 2, 'active', 15, 1), -- Peer Check-In in North
(7, 2, 4, 1, 'active', 25, 2), -- Support Circle Downtown
(8, 2, 4, 3, 'active', 20, 0), -- Support Circle South

-- Kerby Centre for Seniors
(9,  3, 5, 1, 'active', 10, 1), -- Senior Companionship Downtown
(10, 3, 5, 5, 'active',  8, 0), -- Senior Companionship West
(11, 3, 6, 1, 'paused',  6, 0), -- Tech Tutoring Downtown (Currently Paused)

-- Trellis Society
(12, 4, 7, 1, 'active', 12, 1), -- Youth Mentorship Downtown
(13, 4, 7, 4, 'active', 10, 2), -- Youth Mentorship East
(14, 4, 1, 4, 'active', 10, 1); -- Backup Hamper provider in East

-- ============================================================================
-- 11. PRIORITY_LEVELS
-- ============================================================================
INSERT INTO priority_levels (priority_id, level_name, deadline_hours, description) VALUES
(1, 'High',    6, 'Critical non-medical need; partner must attend within 6 hours'),
(2, 'Medium', 12, 'Urgent request; partner must attend within 12 hours'),
(3, 'Low',    24, 'Standard support request; partner must attend within 24 hours');

-- ============================================================================
-- 12. SERVICE_PRIORITY_SUPPORT
-- ============================================================================
INSERT INTO service_priority_support (support_id, organization_service_id, priority_id, is_supported) VALUES
-- Food Bank supports High, Medium, Low in Downtown
(1, 1, 1, TRUE), (2, 1, 2, TRUE), (3, 1, 3, TRUE),
-- Food Bank North supports Medium, Low
(4, 2, 2, TRUE), (5, 2, 3, TRUE),
-- Food Bank South supports Low
(6, 3, 3, TRUE),
-- Distress Centre supports all priorities everywhere
(7, 5, 1, TRUE), (8, 5, 2, TRUE), (9, 5, 3, TRUE),
(10, 6, 1, TRUE), (11, 6, 2, TRUE), (12, 6, 3, TRUE),
(13, 7, 2, TRUE), (14, 7, 3, TRUE),
-- Kerby Centre supports Medium and Low
(15, 9, 2, TRUE), (16, 9, 3, TRUE),
(17, 10, 3, TRUE),
-- Trellis supports High, Medium, Low
(18, 12, 1, TRUE), (19, 12, 2, TRUE), (20, 12, 3, TRUE),
(21, 13, 2, TRUE), (22, 13, 3, TRUE),
(23, 14, 1, TRUE), (24, 14, 2, TRUE);

-- ============================================================================
-- 13. ORGANIZATION_AVAILABILITY
-- ============================================================================
INSERT INTO organization_availability (availability_id, organization_service_id, action, reason, recorded_at, recorded_by_user_id) VALUES
(1, 11, 'pause',  'Instructor sick leave; temporary suspension of tech classes', '2026-09-28 09:00:00', 6),
(2, 1,  'pause',  'Warehouse inventory count day',                               '2026-09-10 08:00:00', 4),
(3, 1,  'resume', 'Inventory complete; resuming normal intake',                  '2026-09-11 08:00:00', 4);

-- ============================================================================
-- 14. SERVICE_REQUESTS
-- ============================================================================
-- Notice attendance deadlines: created_at + deadline_hours
INSERT INTO service_requests (request_id, member_id, service_id, service_area_id, priority_id, title, description, status, attendance_deadline, created_at) VALUES
-- Request 1: Food hamper needed urgently Downtown (High priority - 6h deadline)
(1, 9,  1, 1, 1, 'Emergency grocery box needed', 'Lost job last week, empty fridge, need emergency nutrition.', 'completed', '2026-10-01 14:00:00', '2026-10-01 08:00:00'),

-- Request 2: Peer support check-in Downtown (Medium priority - 12h deadline)
(2, 10, 3, 1, 2, 'Anxiety peer buddy request',   'Feeling overwhelmed with exams and relocation. Looking for someone to talk to.', 'completed', '2026-10-02 21:00:00', '2026-10-02 09:00:00'),

-- Request 3: Senior companionship visit (Low priority - 24h deadline)
(3, 11, 5, 1, 3, 'Companionship for elderly mother', 'Mother lives alone in Chinatown and would love a weekly friendly visitor.', 'completed', '2026-10-03 10:00:00', '2026-10-02 10:00:00'),

-- Request 4: Food hamper North (High priority - 6h deadline) - Rescued by backup partner!
(4, 12, 1, 1, 1, 'Immediate food hamper for family', 'Family of 4 without groceries for dinner today.', 'completed', '2026-10-04 15:00:00', '2026-10-04 09:00:00'),

-- Request 5: Youth mentorship Downtown (Medium priority - 12h deadline) - In progress
(5, 13, 7, 1, 2, 'After-school mentorship for son', '14-year-old son needs positive community mentor and tutoring guidance.', 'in_progress', '2026-10-05 22:00:00', '2026-10-05 10:00:00'),

-- Request 6: Peer support circle Downtown (Medium priority - 12h deadline) - Missed deadline!
(6, 14, 4, 1, 2, 'Virtual grief support group',   'Recent loss in family, looking for group wellness circle.', 'completed', '2026-10-06 20:00:00', '2026-10-06 08:00:00'),

-- Request 7: Delivery hamper Downtown (Low priority - 24h deadline) - Matched
(7, 9,  2, 1, 3, 'Mobility assistance pantry box', 'Recovering from knee surgery, cannot walk to food bank.', 'matched', '2026-10-07 11:00:00', '2026-10-06 11:00:00');

-- ============================================================================
-- 15. REFERRALS
-- ============================================================================
INSERT INTO referrals (referral_id, request_id, organization_id, attempt_number, is_backup, status, response_deadline, responded_at, rejection_reason, created_at) VALUES
-- Request 1 -> Calgary Food Bank (Attempt 1: Accepted & Attended On Time)
(1, 1, 1, 1, FALSE, 'completed', '2026-10-01 10:00:00', '2026-10-01 08:45:00', NULL, '2026-10-01 08:05:00'),

-- Request 2 -> Distress Centre (Attempt 1: Accepted & Attended On Time)
(2, 2, 2, 1, FALSE, 'completed', '2026-10-02 11:00:00', '2026-10-02 09:30:00', NULL, '2026-10-02 09:05:00'),

-- Request 3 -> Kerby Centre (Attempt 1: Accepted & Attended On Time)
(3, 3, 3, 1, FALSE, 'completed', '2026-10-02 12:00:00', '2026-10-02 10:30:00', NULL, '2026-10-02 10:05:00'),

-- Request 4 -> First Choice: Organization 6 (Community Hub - Suspended/Timed Out)
(4, 4, 6, 1, FALSE, 'timed_out', '2026-10-04 10:00:00', NULL, 'No response within response window', '2026-10-04 09:05:00'),

-- Request 4 -> Backup Choice: Calgary Food Bank (Attempt 2: Rescued by backup partner!)
(5, 4, 1, 2, TRUE,  'completed', '2026-10-04 11:00:00', '2026-10-04 10:15:00', NULL, '2026-10-04 10:05:00'),

-- Request 5 -> Trellis (Attempt 1: Accepted, currently in progress)
(6, 5, 4, 1, FALSE, 'attended',  '2026-10-05 12:00:00', '2026-10-05 10:45:00', NULL, '2026-10-05 10:10:00'),

-- Request 6 -> Distress Centre (Attempt 1: Accepted, Attended LATE - missed attendance deadline)
(7, 6, 2, 1, FALSE, 'completed', '2026-10-06 10:00:00', '2026-10-06 09:10:00', NULL, '2026-10-06 08:10:00'),

-- Request 7 -> Calgary Food Bank (Attempt 1: Sent, awaiting response)
(8, 7, 1, 1, FALSE, 'sent',      '2026-10-06 13:00:00', NULL, NULL, '2026-10-06 11:15:00');

-- ============================================================================
-- 16. REFERRAL_STATUS_HISTORY
-- ============================================================================
INSERT INTO referral_status_history (history_id, referral_id, old_status, new_status, changed_by_user_id, notes, changed_at) VALUES
-- Referral 1 History
(1, 1, NULL,       'sent',      1, 'Automated routing to primary partner',       '2026-10-01 08:05:00'),
(2, 1, 'sent',      'accepted',  4, 'Sarah Connor accepted referral',            '2026-10-01 08:45:00'),
(3, 1, 'accepted',  'attended',  4, 'Hamper packaged and handed to member',      '2026-10-01 11:30:00'),
(4, 1, 'attended',  'completed', 4, 'Service delivery fully closed',             '2026-10-01 13:00:00'),

-- Referral 4 & 5 (Timed out -> Backup partner rescue)
(5, 4, NULL,       'sent',      1, 'Automated routing attempt 1',                '2026-10-04 09:05:00'),
(6, 4, 'sent',      'timed_out', 1, 'System timeout: partner did not respond',    '2026-10-04 10:00:00'),
(7, 5, NULL,       'sent',      1, 'Auto backup re-route to Calgary Food Bank',  '2026-10-04 10:05:00'),
(8, 5, 'sent',      'accepted',  4, 'Sarah Connor accepted backup rescue',       '2026-10-04 10:15:00'),
(9, 5, 'accepted',  'attended',  4, 'Emergency food hamper dispatched',          '2026-10-04 12:00:00'),
(10, 5, 'attended', 'completed', 4, 'Backup service successfully delivered',     '2026-10-04 14:00:00'),

-- Referral 7 (Attended LATE)
(11, 7, NULL,      'sent',      1, 'Routing to Distress Centre',                 '2026-10-06 08:10:00'),
(12, 7, 'sent',     'accepted',  5, 'David Lee accepted request',                '2026-10-06 09:10:00'),
(13, 7, 'accepted', 'attended',  5, 'Peer facilitator connected with member',    '2026-10-06 21:15:00'), -- Attended AFTER 20:00 deadline!
(14, 7, 'attended', 'completed', 5, 'Intake session finished',                   '2026-10-06 22:00:00');

-- ============================================================================
-- 17. ATTENDANCE_RECORDS
-- ============================================================================
-- Request 1: Deadline 14:00, attended 11:30 -> ON TIME (TRUE)
-- Request 2: Deadline 21:00, attended 14:00 -> ON TIME (TRUE)
-- Request 3: Deadline 10:00 (next day), attended 16:00 -> ON TIME (TRUE)
-- Request 4: Deadline 15:00, attended 12:00 -> ON TIME (TRUE via backup!)
-- Request 5: Deadline 22:00, attended 16:30 -> ON TIME (TRUE)
-- Request 6: Deadline 20:00, attended 21:15 -> MISSED DEADLINE (FALSE)
INSERT INTO attendance_records (attendance_id, request_id, referral_id, attended_by_representative_id, first_attended_at, is_on_time, notes, created_at) VALUES
(1, 1, 1, 1, '2026-10-01 11:30:00', TRUE,  'Member picked up family hamper at warehouse.', '2026-10-01 11:35:00'),
(2, 2, 2, 2, '2026-10-02 14:00:00', TRUE,  'Completed 45-min phone support session.',      '2026-10-02 14:15:00'),
(3, 3, 3, 3, '2026-10-02 16:00:00', TRUE,  'Navigator visited client mother at home.',    '2026-10-02 16:30:00'),
(4, 4, 5, 1, '2026-10-04 12:00:00', TRUE,  'Rescued request: grocery voucher issued.',     '2026-10-04 12:15:00'),
(5, 5, 6, 4, '2026-10-05 16:30:00', TRUE,  'Introductory mentor matching meeting held.',   '2026-10-05 16:45:00'),
(6, 6, 7, 2, '2026-10-06 21:15:00', FALSE, 'High intake volume caused delay past deadline.','2026-10-06 21:20:00');

-- ============================================================================
-- 18. SERVICE_COMPLETIONS
-- ============================================================================
INSERT INTO service_completions (completion_id, request_id, referral_id, completed_at, outcome, summary_notes, created_at) VALUES
(1, 1, 1, '2026-10-01 13:00:00', 'successful', 'Member received 7 days worth of food staples.', '2026-10-01 13:05:00'),
(2, 2, 2, '2026-10-02 15:00:00', 'successful', 'Member feels grounded and scheduled follow-up call.', '2026-10-02 15:05:00'),
(3, 3, 3, '2026-10-02 17:30:00', 'successful', 'Companionship schedule established for twice monthly.', '2026-10-02 17:35:00'),
(4, 4, 5, '2026-10-04 14:00:00', 'successful', 'Emergency grocery support successfully provided by backup.', '2026-10-04 14:10:00'),
(5, 6, 7, '2026-10-06 22:00:00', 'partially_successful', 'Group session completed, member prefers 1-on-1 support.', '2026-10-06 22:05:00');

-- ============================================================================
-- 19. FEEDBACK
-- ============================================================================
-- Note: Request 6 provides negative feedback for distress centre service
INSERT INTO feedback (feedback_id, request_id, member_id, organization_id, is_helpful, rating, comment, submitted_at) VALUES
(1, 1, 9,  1, TRUE,  5, 'The food hamper was a blessing for our family. Fast and polite!', '2026-10-01 15:00:00'),
(2, 2, 10, 2, TRUE,  5, 'Felt heard and supported. Great peer listener.',                  '2026-10-02 16:30:00'),
(3, 3, 11, 3, TRUE,  4, 'My mother was very happy with the volunteer visitor.',             '2026-10-03 09:00:00'),
(4, 4, 12, 1, TRUE,  5, 'Thank goodness for the backup partner. Very grateful!',            '2026-10-04 16:00:00'),
(5, 6, 14, 2, FALSE, 2, 'Attended well past the deadline and group format did not help.',  '2026-10-07 09:00:00');

-- ============================================================================
-- 20. NOTIFICATIONS
-- ============================================================================
INSERT INTO notifications (notification_id, user_id, type, title, message, is_read, related_request_id, created_at) VALUES
(1, 9,  'referral_accepted',   'Referral Accepted',   'Calgary Food Bank has accepted your request.', TRUE,  1, '2026-10-01 08:45:00'),
(2, 4,  'referral_sent',       'New Referral Request', 'You have a new High priority referral.',      TRUE,  1, '2026-10-01 08:05:00'),
(3, 12, 'backup_rescue',       'Backup Partner Engaged','Calgary Food Bank has been engaged as backup partner.', TRUE, 4, '2026-10-04 10:05:00'),
(4, 1,  'deadline_missed',     'SLA Deadline Missed',  'Request #6 missed attendance deadline with Distress Centre.', FALSE, 6, '2026-10-06 20:05:00'),
(5, 14, 'feedback_invitation', 'Share Your Feedback',  'Please let us know how your referral experience went.', FALSE, 6, '2026-10-06 22:05:00');
