-- ============================================================================
-- CareConnect: Analytical & Operational Queries
-- Course: ENSF 608 — Database Systems | University of Calgary | SDG 17
-- Group 4 | Lead Database Engineer: Raj Jigneshkumar Patel
-- Engine: MySQL 8.0+ (InnoDB)
--
-- This script contains the 8 official queries defined in Section 4 of the
-- CareConnect Database Proposal, plus the SDG 17 Network Impact Report.
-- ============================================================================

USE careconnect_db;

-- ============================================================================
-- QUESTION 1:
-- Which approved organizations offer a service in a member's area and support
-- the chosen priority?
-- Example test parameters: Service = 'Emergency Food Hamper' (ID 1),
-- Area = 'Downtown' (ID 1), Priority = 'High' (ID 1).
-- ============================================================================
SELECT 
    o.organization_id,
    o.name AS organization_name,
    s.name AS service_name,
    sa.region_name AS service_area,
    pl.level_name AS supported_priority,
    pl.deadline_hours,
    os.status AS service_offering_status,
    os.active_referral_limit,
    os.current_active_referrals,
    (os.active_referral_limit - os.current_active_referrals) AS available_slots
FROM organizations o
JOIN organization_services os 
    ON o.organization_id = os.organization_id
JOIN services s 
    ON os.service_id = s.service_id
JOIN service_areas sa 
    ON os.service_area_id = sa.area_id
JOIN service_priority_support sps 
    ON os.organization_service_id = sps.organization_service_id
JOIN priority_levels pl 
    ON sps.priority_id = pl.priority_id
WHERE o.status = 'approved'
  AND os.status = 'active'
  AND sps.is_supported = TRUE
  AND s.service_id = 1           -- Emergency Food Hamper
  AND sa.area_id = 1             -- Downtown
  AND pl.level_name = 'High'     -- High priority supported
ORDER BY available_slots DESC;


-- ============================================================================
-- QUESTION 2:
-- Which eligible partner currently has the fewest active referrals?
-- (Used by the automatic routing engine to balance partner workloads)
-- ============================================================================
SELECT 
    o.organization_id,
    o.name AS organization_name,
    s.name AS service_name,
    sa.region_name AS area_name,
    os.current_active_referrals,
    os.active_referral_limit,
    (os.active_referral_limit - os.current_active_referrals) AS remaining_capacity
FROM organization_services os
JOIN organizations o 
    ON os.organization_id = o.organization_id
JOIN services s 
    ON os.service_id = s.service_id
JOIN service_areas sa 
    ON os.service_area_id = sa.area_id
WHERE o.status = 'approved'
  AND os.status = 'active'
  AND os.current_active_referrals < os.active_referral_limit
ORDER BY os.current_active_referrals ASC, remaining_capacity DESC
LIMIT 5;


-- ============================================================================
-- QUESTION 3:
-- Which requests missed their attendance deadline, and which referral was responsible?
-- (Identifies partner SLA breaches for coordinator follow-up)
-- ============================================================================
SELECT 
    sr.request_id,
    sr.title AS request_title,
    pl.level_name AS priority,
    sr.attendance_deadline,
    ar.first_attended_at,
    TIMESTAMPDIFF(MINUTE, sr.attendance_deadline, ar.first_attended_at) AS delay_minutes,
    ref.referral_id,
    ref.attempt_number,
    ref.is_backup,
    o.name AS responsible_organization,
    ar.notes AS attendance_notes
FROM attendance_records ar
JOIN service_requests sr 
    ON ar.request_id = sr.request_id
JOIN priority_levels pl 
    ON sr.priority_id = pl.priority_id
JOIN referrals ref 
    ON ar.referral_id = ref.referral_id
JOIN organizations o 
    ON ref.organization_id = o.organization_id
WHERE ar.is_on_time = FALSE 
   OR ar.first_attended_at > sr.attendance_deadline
ORDER BY delay_minutes DESC;


-- ============================================================================
-- QUESTION 4:
-- How many referrals did each organization accept, reject or let time out this month?
-- ============================================================================
SELECT 
    o.organization_id,
    o.name AS organization_name,
    COUNT(r.referral_id) AS total_referrals_sent,
    SUM(CASE WHEN r.status IN ('accepted', 'attended', 'completed') THEN 1 ELSE 0 END) AS accepted_count,
    SUM(CASE WHEN r.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
    SUM(CASE WHEN r.status = 'timed_out' THEN 1 ELSE 0 END) AS timed_out_count,
    ROUND(
        (SUM(CASE WHEN r.status IN ('accepted', 'attended', 'completed') THEN 1 ELSE 0 END) * 100.0) / 
        NULLIF(COUNT(r.referral_id), 0), 1
    ) AS acceptance_rate_percent
FROM organizations o
LEFT JOIN referrals r 
    ON o.organization_id = r.organization_id
    AND r.created_at >= '2026-10-01 00:00:00'
GROUP BY o.organization_id, o.name
ORDER BY total_referrals_sent DESC;


-- ============================================================================
-- QUESTION 5:
-- What percentage of each organization's requests were attended on time?
-- (Core SLA reliability scorecard)
-- ============================================================================
SELECT 
    o.organization_id,
    o.name AS organization_name,
    COUNT(ar.attendance_id) AS total_attended_requests,
    SUM(CASE WHEN ar.is_on_time = TRUE THEN 1 ELSE 0 END) AS on_time_attendances,
    SUM(CASE WHEN ar.is_on_time = FALSE THEN 1 ELSE 0 END) AS late_attendances,
    ROUND(
        (SUM(CASE WHEN ar.is_on_time = TRUE THEN 1 ELSE 0 END) * 100.0) / 
        NULLIF(COUNT(ar.attendance_id), 0), 2
    ) AS on_time_attendance_rate_percent
FROM organizations o
JOIN referrals r 
    ON o.organization_id = r.organization_id
JOIN attendance_records ar 
    ON r.referral_id = ar.referral_id
GROUP BY o.organization_id, o.name
ORDER BY on_time_attendance_rate_percent DESC, total_attended_requests DESC;


-- ============================================================================
-- QUESTION 6:
-- Which service categories receive the most requests, by priority and area?
-- (Community demand analysis for service resource allocation)
-- ============================================================================
SELECT 
    sc.name AS service_category,
    sa.region_name AS service_area,
    pl.level_name AS priority_level,
    COUNT(sr.request_id) AS request_count
FROM service_requests sr
JOIN services s 
    ON sr.service_id = s.service_id
JOIN service_categories sc 
    ON s.category_id = sc.category_id
JOIN service_areas sa 
    ON sr.service_area_id = sa.area_id
JOIN priority_levels pl 
    ON sr.priority_id = pl.priority_id
GROUP BY sc.name, sa.region_name, pl.level_name
ORDER BY request_count DESC, sc.name ASC;


-- ============================================================================
-- QUESTION 7:
-- How many requests were rescued by a backup partner this month?
-- (SDG 17 Resilience Metric: requests saved after primary partner failure)
-- ============================================================================
SELECT 
    COUNT(DISTINCT sr.request_id) AS total_rescued_requests,
    GROUP_CONCAT(DISTINCT CONCAT('Request #', sr.request_id, ' (', o_rescue.name, ')') SEPARATOR '; ') AS rescued_details
FROM referrals r_rescue
JOIN service_requests sr 
    ON r_rescue.request_id = sr.request_id
JOIN organizations o_rescue 
    ON r_rescue.organization_id = o_rescue.organization_id
WHERE r_rescue.is_backup = TRUE
  AND r_rescue.attempt_number > 1
  AND r_rescue.status IN ('accepted', 'attended', 'completed')
  AND r_rescue.created_at >= '2026-10-01 00:00:00';


-- Detailed Breakdown of Rescued Requests:
SELECT 
    sr.request_id,
    sr.title AS request_title,
    o_initial.name AS failed_primary_partner,
    r_initial.status AS primary_failure_status,
    o_rescue.name AS rescue_partner,
    r_rescue.status AS rescue_status,
    ar.first_attended_at,
    ar.is_on_time
FROM service_requests sr
JOIN referrals r_initial 
    ON sr.request_id = r_initial.request_id AND r_initial.attempt_number = 1
JOIN organizations o_initial 
    ON r_initial.organization_id = o_initial.organization_id
JOIN referrals r_rescue 
    ON sr.request_id = r_rescue.request_id AND r_rescue.attempt_number > 1
JOIN organizations o_rescue 
    ON r_rescue.organization_id = o_rescue.organization_id
LEFT JOIN attendance_records ar 
    ON sr.request_id = ar.request_id
WHERE r_initial.status IN ('timed_out', 'rejected')
  AND r_rescue.status IN ('accepted', 'attended', 'completed');


-- ============================================================================
-- QUESTION 8:
-- Which organizations received repeated 'not helpful' feedback for the same service?
-- (Quality assurance to identify underperforming partner services)
-- ============================================================================
SELECT 
    o.organization_id,
    o.name AS organization_name,
    s.name AS service_name,
    COUNT(f.feedback_id) AS total_feedback_received,
    SUM(CASE WHEN f.is_helpful = FALSE THEN 1 ELSE 0 END) AS not_helpful_count,
    ROUND(AVG(f.rating), 2) AS average_rating,
    GROUP_CONCAT(f.comment SEPARATOR ' | ') AS member_comments
FROM feedback f
JOIN service_requests sr 
    ON f.request_id = sr.request_id
JOIN services s 
    ON sr.service_id = s.service_id
JOIN organizations o 
    ON f.organization_id = o.organization_id
WHERE f.is_helpful = FALSE
GROUP BY o.organization_id, o.name, s.name
HAVING not_helpful_count >= 1
ORDER BY not_helpful_count DESC;


-- ============================================================================
-- BONUS: SDG 17 NETWORK IMPACT REPORT
-- Comprehensive ecosystem partnership performance summary
-- ============================================================================
SELECT 
    (SELECT COUNT(*) FROM organizations WHERE status = 'approved') AS total_approved_partners,
    (SELECT COUNT(*) FROM service_requests) AS total_community_requests,
    (SELECT COUNT(*) FROM referrals WHERE is_backup = TRUE AND status IN ('accepted', 'attended', 'completed')) AS requests_rescued_by_backups,
    ROUND(
        (SELECT COUNT(*) FROM attendance_records WHERE is_on_time = TRUE) * 100.0 / 
        NULLIF((SELECT COUNT(*) FROM attendance_records), 0), 1
    ) AS network_on_time_attendance_rate_percent,
    ROUND(
        (SELECT COUNT(*) FROM feedback WHERE is_helpful = TRUE) * 100.0 / 
        NULLIF((SELECT COUNT(*) FROM feedback), 0), 1
    ) AS positive_feedback_satisfaction_percent;
