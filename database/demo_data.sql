-- Synthetic scenario extension. Run only on a disposable, seeded schema with
-- the member/partner/catalog prerequisites in the isolated integration test.
-- This script leaves an open transaction for review. Never run against live data.
SET time_zone = '+00:00';

START TRANSACTION;

SET @demo_now = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 30 MINUTE);
INSERT INTO service_requests
(
    member_id,
    service_id,
    service_area_id,
    priority_id,
    title,
    description,
    status,
    attendance_deadline,
    created_at,
    updated_at
)
SELECT
    d.member_id,
    d.service_id,
    d.area_id,
    d.priority_id,
    CONCAT('[DEMO] ', d.title),
    'Synthetic CareConnect demonstration request.',
    d.status,
    DATE_ADD(
        DATE_ADD(@demo_now, INTERVAL d.day_offset DAY),
        INTERVAL p.deadline_hours HOUR
    ),
    DATE_ADD(@demo_now, INTERVAL d.day_offset DAY),
    @demo_now
FROM (
    -- Submitted requests
    SELECT 15 AS member_id, 1 AS service_id,
           1 AS area_id, 1 AS priority_id,
           'Food hamper request' AS title,
           'submitted' AS status, 0 AS day_offset
    UNION ALL SELECT 15,3,1,2,'Peer support request','submitted',0
    UNION ALL SELECT 9,4,1,3,'Online support session','submitted',0
    UNION ALL SELECT 10,5,1,2,'Companionship request','submitted',0
    UNION ALL SELECT 11,7,1,3,'Youth mentoring request','submitted',0

    -- Matched requests
    UNION ALL SELECT 15,1,1,2,'Grocery assistance','matched',0
    UNION ALL SELECT 15,3,1,3,'Scheduled peer check-in','matched',0
    UNION ALL SELECT 12,4,1,2,'Virtual wellness session','matched',0
    UNION ALL SELECT 13,5,1,3,'Senior social visit','matched',0
    UNION ALL SELECT 14,6,1,3,'Technology assistance','matched',0
    UNION ALL SELECT 9,7,1,2,'Mentorship appointment','matched',0
    UNION ALL SELECT 10,2,1,3,'Grocery delivery','matched',0

    -- In-progress requests
    UNION ALL SELECT 15,1,1,2,'Food support underway','in_progress',0
    UNION ALL SELECT 15,3,1,3,'Peer support underway','in_progress',0
    UNION ALL SELECT 11,5,1,3,'Companionship underway','in_progress',0
    UNION ALL SELECT 12,4,1,2,'Support circle underway','in_progress',0
    UNION ALL SELECT 13,7,1,3,'Mentoring underway','in_progress',0

    -- Completed requests
    UNION ALL SELECT 15,1,1,1,'Completed food assistance','completed',-7
    UNION ALL SELECT 15,3,1,2,'Completed peer support','completed',-6
    UNION ALL SELECT 15,4,1,3,'Completed support circle','completed',-5
    UNION ALL SELECT 9,5,1,3,'Completed companionship','completed',-4
    UNION ALL SELECT 10,6,1,2,'Completed tech tutoring','completed',-3
    UNION ALL SELECT 11,7,1,3,'Completed mentoring','completed',-2
    UNION ALL SELECT 12,2,1,2,'Completed grocery delivery','completed',-1

    -- Unmatched requests
    UNION ALL SELECT 15,1,5,1,'West food assistance','unmatched',-5
    UNION ALL SELECT 13,3,5,2,'West peer support','unmatched',-4
    UNION ALL SELECT 14,6,2,3,'North technology support','unmatched',-3
    UNION ALL SELECT 9,7,3,2,'South mentoring','unmatched',-2
    UNION ALL SELECT 10,2,4,3,'East grocery delivery','unmatched',-1

    -- Cancelled requests
    UNION ALL SELECT 15,1,1,2,'Cancelled food request','cancelled',-4
    UNION ALL SELECT 11,3,1,3,'Cancelled peer session','cancelled',-3
    UNION ALL SELECT 12,5,1,2,'Cancelled social visit','cancelled',-2
    UNION ALL SELECT 14,7,1,3,'Cancelled mentoring','cancelled',-1
) d
JOIN priority_levels p
    ON p.priority_id = d.priority_id
WHERE NOT EXISTS (
    SELECT 1
    FROM service_requests sr
    WHERE sr.title = CONCAT('[DEMO] ', d.title)
);

-- =====================================================
-- SECTION 2: PRIMARY REFERRALS
-- =====================================================

INSERT INTO referrals
(
    request_id,
    organization_id,
    attempt_number,
    status,
    response_deadline,
    responded_at,
    rejection_reason,
    created_at,
    updated_at
)
SELECT
    sr.request_id,
    7,
    1,
    CASE
        WHEN sr.status = 'matched' THEN 'accepted'
        WHEN sr.status = 'in_progress' THEN 'attended'
        WHEN sr.status = 'completed' THEN 'completed'
    END,
    DATE_ADD(sr.created_at, INTERVAL 1 HOUR),
    DATE_ADD(sr.created_at, INTERVAL 10 MINUTE),
    NULL,
    DATE_ADD(sr.created_at, INTERVAL 5 MINUTE),
    CASE
        WHEN sr.status = 'completed'
            THEN DATE_ADD(sr.created_at, INTERVAL 4 HOUR)
        WHEN sr.status = 'in_progress'
            THEN DATE_ADD(sr.created_at, INTERVAL 20 MINUTE)
        ELSE DATE_ADD(sr.created_at, INTERVAL 10 MINUTE)
    END
FROM service_requests sr
JOIN organization_services os
    ON os.organization_id = 7
    AND os.service_id = sr.service_id
    AND os.service_area_id = sr.service_area_id
JOIN service_priority_support sps
    ON sps.organization_service_id = os.organization_service_id
    AND sps.priority_id = sr.priority_id
    AND sps.is_supported = TRUE
WHERE sr.title LIKE '[DEMO] %'
AND sr.status IN ('matched', 'in_progress', 'completed')
AND os.status = 'active'
AND NOT EXISTS (
    SELECT 1
    FROM referrals r
    WHERE r.request_id = sr.request_id
);

-- =====================================================
-- SECTION 3: REMAINING PRIMARY REFERRALS
-- =====================================================

INSERT INTO referrals
(
    request_id,
    organization_id,
    attempt_number,
    status,
    response_deadline,
    responded_at,
    rejection_reason,
    created_at,
    updated_at
)
SELECT
    sr.request_id,
    o.organization_id,
    1,
    CASE
        WHEN sr.status = 'matched' THEN 'accepted'
        WHEN sr.status = 'in_progress' THEN 'attended'
        WHEN sr.status = 'completed' THEN 'completed'
    END,
    DATE_ADD(sr.created_at, INTERVAL 1 HOUR),
    DATE_ADD(sr.created_at, INTERVAL 10 MINUTE),
    NULL,
    DATE_ADD(sr.created_at, INTERVAL 5 MINUTE),
    CASE
        WHEN sr.status = 'completed'
            THEN DATE_ADD(sr.created_at, INTERVAL 4 HOUR)
        WHEN sr.status = 'in_progress'
            THEN DATE_ADD(sr.created_at, INTERVAL 20 MINUTE)
        ELSE DATE_ADD(sr.created_at, INTERVAL 10 MINUTE)
    END
FROM service_requests sr
JOIN organization_services os
    ON os.service_id = sr.service_id
    AND os.service_area_id = sr.service_area_id
JOIN organizations o
    ON o.organization_id = os.organization_id
JOIN service_priority_support sps
    ON sps.organization_service_id = os.organization_service_id
    AND sps.priority_id = sr.priority_id
WHERE sr.title LIKE '[DEMO] %'
AND sr.status IN ('matched', 'in_progress', 'completed')
AND sr.service_id = 6
AND o.organization_id = 5
AND o.status = 'approved'
AND os.status = 'active'
AND sps.is_supported = TRUE
AND NOT EXISTS (
    SELECT 1
    FROM referrals r
    WHERE r.request_id = sr.request_id
);
-- =====================================================
-- SECTION 4: BACKUP REFERRAL SCENARIOS
-- =====================================================

-- Convert selected demo referrals into backup referrals.

UPDATE referrals r
JOIN service_requests sr
    ON sr.request_id = r.request_id
SET
    r.attempt_number = 2,
    r.created_at = DATE_ADD(sr.created_at, INTERVAL 70 MINUTE),
    r.response_deadline = DATE_ADD(sr.created_at, INTERVAL 130 MINUTE),
    r.responded_at = DATE_ADD(sr.created_at, INTERVAL 80 MINUTE)
WHERE sr.title IN (
    '[DEMO] Completed food assistance',
    '[DEMO] Completed peer support'
)
AND r.organization_id = 7
AND r.attempt_number = 1
AND r.status = 'completed';


-- Insert unsuccessful primary referrals.

INSERT INTO referrals
(
    request_id,
    organization_id,
    attempt_number,
    status,
    response_deadline,
    responded_at,
    rejection_reason,
    created_at,
    updated_at
)
SELECT
    sr.request_id,
    CASE
        WHEN sr.service_id = 1 THEN 1
        WHEN sr.service_id = 3 THEN 2
    END,
    1,
    CASE
        WHEN sr.service_id = 1 THEN 'rejected'
        WHEN sr.service_id = 3 THEN 'timed_out'
    END,
    DATE_ADD(sr.created_at, INTERVAL 60 MINUTE),
    CASE
        WHEN sr.service_id = 1
        THEN DATE_ADD(sr.created_at, INTERVAL 15 MINUTE)
        ELSE NULL
    END,
    CASE
        WHEN sr.service_id = 1
        THEN 'Demo scenario: organization unable to assist.'
        ELSE NULL
    END,
    DATE_ADD(sr.created_at, INTERVAL 5 MINUTE),
    CASE
        WHEN sr.service_id = 1
        THEN DATE_ADD(sr.created_at, INTERVAL 15 MINUTE)
        ELSE DATE_ADD(sr.created_at, INTERVAL 60 MINUTE)
    END
FROM service_requests sr
WHERE sr.title IN (
    '[DEMO] Completed food assistance',
    '[DEMO] Completed peer support'
)
AND NOT EXISTS (
    SELECT 1
    FROM referrals r
    WHERE r.request_id = sr.request_id
    AND r.attempt_number = 1
);

-- =====================================================
-- SECTION 5: REFERRAL STATUS HISTORY
-- =====================================================

INSERT INTO referral_status_history
(
    referral_id,
    old_status,
    new_status,
    changed_by_user_id,
    notes,
    changed_at
)
SELECT
    r.referral_id,
    h.old_status,
    h.new_status,
    CASE
        WHEN h.new_status IN ('accepted', 'rejected',
                              'attended', 'completed')
        THEN rep.user_id
        ELSE NULL
    END,
    CONCAT('Demo: referral ', h.new_status),
    CASE h.new_status
        WHEN 'sent' THEN r.created_at
        WHEN 'accepted' THEN r.responded_at
        WHEN 'rejected' THEN r.responded_at
        WHEN 'timed_out' THEN r.response_deadline
        WHEN 'attended' THEN
            DATE_ADD(r.responded_at, INTERVAL 10 MINUTE)
        WHEN 'completed' THEN r.updated_at
    END
FROM referrals r
JOIN service_requests sr
    ON sr.request_id = r.request_id
LEFT JOIN organization_representatives rep
    ON rep.organization_id = r.organization_id
CROSS JOIN (
    SELECT NULL AS old_status, 'sent' AS new_status
    UNION ALL SELECT 'sent', 'accepted'
    UNION ALL SELECT 'sent', 'rejected'
    UNION ALL SELECT 'sent', 'timed_out'
    UNION ALL SELECT 'accepted', 'attended'
    UNION ALL SELECT 'attended', 'completed'
) h
WHERE sr.title LIKE '[DEMO] %'
AND (
    h.new_status = 'sent'
    OR (h.new_status = 'accepted'
        AND r.status IN ('accepted','attended','completed'))
    OR (h.new_status = 'attended'
        AND r.status IN ('attended','completed'))
    OR (h.new_status = 'completed'
        AND r.status = 'completed')
    OR (h.new_status = 'rejected'
        AND r.status = 'rejected')
    OR (h.new_status = 'timed_out'
        AND r.status = 'timed_out')
)
AND NOT EXISTS (
    SELECT 1
    FROM referral_status_history rh
    WHERE rh.referral_id = r.referral_id
    AND rh.new_status = h.new_status
)
ORDER BY r.referral_id, FIELD(
    h.new_status,
    'sent', 'accepted', 'rejected',
    'timed_out', 'attended', 'completed'
);
-- =====================================================
-- SECTION 6: ATTENDANCE RECORDS
-- =====================================================

INSERT INTO attendance_records
(
    request_id,
    referral_id,
    attended_by_representative_id,
    first_attended_at,
    is_on_time,
    notes,
    created_at
)
SELECT
    sr.request_id,
    r.referral_id,
    rep.representative_id,
    rh.changed_at,
    CASE
        WHEN rh.changed_at <= sr.attendance_deadline
        THEN TRUE
        ELSE FALSE
    END,
    'Synthetic demo attendance record.',
    rh.changed_at
FROM service_requests sr
JOIN referrals r
    ON r.request_id = sr.request_id
JOIN organization_representatives rep
    ON rep.organization_id = r.organization_id
JOIN referral_status_history rh
    ON rh.referral_id = r.referral_id
    AND rh.new_status = 'attended'
WHERE sr.title LIKE '[DEMO] %'
AND sr.status IN ('in_progress', 'completed')
AND r.status IN ('attended', 'completed')
AND NOT EXISTS (
    SELECT 1
    FROM attendance_records ar
    WHERE ar.request_id = sr.request_id
);
-- =====================================================
-- SECTION 7: SERVICE COMPLETIONS
-- =====================================================

INSERT INTO service_completions
(
    request_id,
    referral_id,
    completed_at,
    outcome,
    summary_notes,
    created_at
)
SELECT
    sr.request_id,
    r.referral_id,
    r.updated_at,
    CASE
        WHEN sr.title = '[DEMO] Completed tech tutoring'
            THEN 'partially_successful'
        WHEN sr.title = '[DEMO] Completed mentoring'
            THEN 'referred_to_external'
        WHEN sr.title = '[DEMO] Completed grocery delivery'
            THEN 'unsuccessful'
        ELSE 'successful'
    END,
    'Synthetic demo service completion record.',
    r.updated_at
FROM service_requests sr
JOIN referrals r
    ON r.request_id = sr.request_id
JOIN attendance_records ar
    ON ar.request_id = sr.request_id
    AND ar.referral_id = r.referral_id
WHERE sr.title LIKE '[DEMO] %'
AND sr.status = 'completed'
AND r.status = 'completed'
AND r.updated_at >= ar.first_attended_at
AND NOT EXISTS (
    SELECT 1
    FROM service_completions sc
    WHERE sc.request_id = sr.request_id
);

-- =====================================================
-- SECTION 8: FEEDBACK RECORDS
-- =====================================================

INSERT INTO feedback
(
    request_id,
    member_id,
    organization_id,
    is_helpful,
    rating,
    comment,
    submitted_at
)
SELECT
    sr.request_id,
    sr.member_id,
    r.organization_id,
    CASE
        WHEN sc.outcome = 'unsuccessful' THEN FALSE
        ELSE TRUE
    END,
    CASE sc.outcome
        WHEN 'successful' THEN 5
        WHEN 'partially_successful' THEN 3
        WHEN 'referred_to_external' THEN 4
        WHEN 'unsuccessful' THEN 2
    END,
    CASE sc.outcome
        WHEN 'successful'
            THEN 'Demo: Helpful service and good communication.'
        WHEN 'partially_successful'
            THEN 'Demo: Helpful but could be improved.'
        WHEN 'referred_to_external'
            THEN 'Demo: Received guidance for additional support.'
        WHEN 'unsuccessful'
            THEN 'Demo: Service did not meet expectations.'
    END,
    DATE_ADD(sc.completed_at, INTERVAL 30 MINUTE)
FROM service_requests sr
JOIN service_completions sc
    ON sc.request_id = sr.request_id
JOIN referrals r
    ON r.referral_id = sc.referral_id
WHERE sr.title LIKE '[DEMO] %'
AND sr.status = 'completed'
AND NOT EXISTS (
    SELECT 1
    FROM feedback f
    WHERE f.request_id = sr.request_id
);
-- =====================================================
-- SECTION 9: NOTIFICATIONS
-- =====================================================

-- Organization referral notifications

INSERT INTO notifications
(
    user_id,
    type,
    title,
    message,
    is_read,
    related_request_id,
    created_at,
    deduplication_key
)
SELECT
    rep.user_id,
    'referral_sent',
    'New demo referral',
    CONCAT('A synthetic referral was assigned: ', sr.title),
    CASE
        WHEN r.status = 'sent' THEN FALSE
        ELSE TRUE
    END,
    sr.request_id,
    r.created_at,
    CONCAT('demo-referral-sent-', r.referral_id, '-', rep.user_id)
FROM referrals r
JOIN service_requests sr
    ON sr.request_id = r.request_id
JOIN organization_representatives rep
    ON rep.organization_id = r.organization_id
WHERE sr.title LIKE '[DEMO] %'
AND NOT EXISTS (
    SELECT 1
    FROM notifications n
    WHERE n.deduplication_key =
        CONCAT('demo-referral-sent-', r.referral_id, '-', rep.user_id)
);


-- Member acceptance notifications

INSERT INTO notifications
(
    user_id,
    type,
    title,
    message,
    is_read,
    related_request_id,
    created_at,
    deduplication_key
)
SELECT
    sr.member_id,
    'referral_accepted',
    'Demo referral accepted',
    'An organization has accepted your synthetic service request.',
    CASE
        WHEN sr.status = 'completed' THEN TRUE
        ELSE FALSE
    END,
    sr.request_id,
    r.responded_at,
    CONCAT('demo-referral-accepted-', r.referral_id)
FROM referrals r
JOIN service_requests sr
    ON sr.request_id = r.request_id
WHERE sr.title LIKE '[DEMO] %'
AND r.status IN ('accepted', 'attended', 'completed')
AND NOT EXISTS (
    SELECT 1
    FROM notifications n
    WHERE n.deduplication_key =
        CONCAT('demo-referral-accepted-', r.referral_id)
);


-- Backup referral notifications

INSERT INTO notifications
(
    user_id,
    type,
    title,
    message,
    is_read,
    related_request_id,
    created_at,
    deduplication_key
)
SELECT
    sr.member_id,
    'backup_rescue',
    'Demo backup organization assigned',
    'Your synthetic request was reassigned to a backup organization.',
    TRUE,
    sr.request_id,
    r.created_at,
    CONCAT('demo-backup-', r.referral_id)
FROM referrals r
JOIN service_requests sr
    ON sr.request_id = r.request_id
WHERE sr.title LIKE '[DEMO] %'
AND r.attempt_number > 1
AND NOT EXISTS (
    SELECT 1
    FROM notifications n
    WHERE n.deduplication_key =
        CONCAT('demo-backup-', r.referral_id)
);


-- Feedback invitation notifications

INSERT INTO notifications
(
    user_id,
    type,
    title,
    message,
    is_read,
    related_request_id,
    created_at,
    deduplication_key
)
SELECT
    sr.member_id,
    'feedback_invitation',
    'Demo service feedback',
    'Your synthetic service is complete. Please share your feedback.',
    TRUE,
    sr.request_id,
    sc.completed_at,
    CONCAT('demo-feedback-', sr.request_id)
FROM service_requests sr
JOIN service_completions sc
    ON sc.request_id = sr.request_id
WHERE sr.title LIKE '[DEMO] %'
AND NOT EXISTS (
    SELECT 1
    FROM notifications n
    WHERE n.deduplication_key =
        CONCAT('demo-feedback-', sr.request_id)
);
-- =====================================================
-- SECTION 10: CAPACITY RECONCILIATION
-- =====================================================

UPDATE organization_services os
LEFT JOIN (
    SELECT
        r.organization_id,
        sr.service_id,
        sr.service_area_id,
        COUNT(*) AS active_count
    FROM referrals r
    JOIN service_requests sr
        ON sr.request_id = r.request_id
    WHERE r.status IN ('sent', 'accepted', 'attended')
    GROUP BY
        r.organization_id,
        sr.service_id,
        sr.service_area_id
) actual
    ON actual.organization_id = os.organization_id
    AND actual.service_id = os.service_id
    AND actual.service_area_id = os.service_area_id
SET os.current_active_referrals =
    COALESCE(actual.active_count, 0)
WHERE os.current_active_referrals <>
    COALESCE(actual.active_count, 0);
    -- =====================================================
-- SECTION 11: LATE ATTENDANCE SCENARIO
-- =====================================================

UPDATE service_requests sr
JOIN referrals r
    ON r.request_id = sr.request_id
JOIN attendance_records ar
    ON ar.referral_id = r.referral_id
JOIN service_completions sc
    ON sc.referral_id = r.referral_id
JOIN referral_status_history rh
    ON rh.referral_id = r.referral_id
    AND rh.new_status = 'attended'
JOIN referral_status_history ch
    ON ch.referral_id = r.referral_id
    AND ch.new_status = 'completed'
JOIN feedback f
    ON f.request_id = sr.request_id
SET
    ar.first_attended_at =
        DATE_ADD(sr.attendance_deadline, INTERVAL 30 MINUTE),
    ar.is_on_time = FALSE,
    ar.notes = 'Synthetic demo: attendance deadline missed.',
    ar.created_at =
        DATE_ADD(sr.attendance_deadline, INTERVAL 30 MINUTE),
    rh.changed_at =
        DATE_ADD(sr.attendance_deadline, INTERVAL 30 MINUTE),
    sc.completed_at =
        DATE_ADD(sr.attendance_deadline, INTERVAL 2 HOUR),
    sc.created_at =
        DATE_ADD(sr.attendance_deadline, INTERVAL 2 HOUR),
    ch.changed_at =
        DATE_ADD(sr.attendance_deadline, INTERVAL 2 HOUR),
    r.updated_at =
        DATE_ADD(sr.attendance_deadline, INTERVAL 2 HOUR),
    sr.updated_at =
        DATE_ADD(sr.attendance_deadline, INTERVAL 2 HOUR),
    f.submitted_at =
        DATE_ADD(sr.attendance_deadline, INTERVAL 150 MINUTE)
WHERE sr.title = '[DEMO] Completed food assistance'
AND r.status = 'completed';


UPDATE notifications n
JOIN service_requests sr
    ON sr.request_id = n.related_request_id
JOIN service_completions sc
    ON sc.request_id = sr.request_id
SET n.created_at = sc.completed_at
WHERE sr.title = '[DEMO] Completed food assistance'
AND n.type = 'feedback_invitation';
-- =====================================================
-- SECTION 12: SYNTHETIC QUEUE SAFETY
-- =====================================================

UPDATE service_requests sr
SET
    sr.status = 'cancelled',
    sr.updated_at = UTC_TIMESTAMP()
WHERE sr.title LIKE '[DEMO] %'
AND sr.status = 'submitted'
AND NOT EXISTS (
    SELECT 1
    FROM referrals r
    WHERE r.request_id = sr.request_id
);
-- =====================================================
-- SECTION 13: FINAL VALIDATION
-- =====================================================

-- Verify total records in each table.

SELECT 'Users' AS table_name, COUNT(*) AS total FROM users
UNION ALL
SELECT 'Organizations', COUNT(*) FROM organizations
UNION ALL
SELECT 'Service offerings', COUNT(*) FROM organization_services
UNION ALL
SELECT 'Service requests', COUNT(*) FROM service_requests
UNION ALL
SELECT 'Referrals', COUNT(*) FROM referrals
UNION ALL
SELECT 'Referral history', COUNT(*) FROM referral_status_history
UNION ALL
SELECT 'Attendance', COUNT(*) FROM attendance_records
UNION ALL
SELECT 'Completions', COUNT(*) FROM service_completions
UNION ALL
SELECT 'Feedback', COUNT(*) FROM feedback
UNION ALL
SELECT 'Notifications', COUNT(*) FROM notifications
UNION ALL
SELECT 'Outbox events', COUNT(*) FROM event_outbox;


-- Verify request status distribution.

SELECT status, COUNT(*) AS total
FROM service_requests
GROUP BY status;


-- Verify all four coordinators are preserved.

SELECT COUNT(*) AS coordinator_count
FROM users
WHERE role_id = 3;


-- Verify matched and in-progress demo requests
-- have the appropriate active referral.

SELECT sr.request_id, sr.title, sr.status
FROM service_requests sr
WHERE sr.title LIKE '[DEMO] %'
AND sr.status IN ('matched', 'in_progress')
AND NOT EXISTS (
    SELECT 1
    FROM referrals r
    WHERE r.request_id = sr.request_id
    AND (
        (sr.status = 'matched'
         AND r.status IN ('sent', 'accepted'))
        OR
        (sr.status = 'in_progress'
         AND r.status = 'attended')
    )
);


-- Verify completed requests have completion records.

SELECT sr.request_id, sr.title
FROM service_requests sr
WHERE sr.title LIKE '[DEMO] %'
AND sr.status = 'completed'
AND NOT EXISTS (
    SELECT 1
    FROM service_completions sc
    WHERE sc.request_id = sr.request_id
);


-- Verify attendance records.

SELECT sr.request_id, sr.title
FROM service_requests sr
WHERE sr.title LIKE '[DEMO] %'
AND sr.status IN ('completed', 'in_progress')
AND NOT EXISTS (
    SELECT 1
    FROM attendance_records ar
    WHERE ar.request_id = sr.request_id
);


-- Verify capacity consistency.

SELECT
    os.organization_service_id,
    os.current_active_referrals,
    COALESCE(actual.active_count, 0) AS expected_count
FROM organization_services os
LEFT JOIN (
    SELECT
        r.organization_id,
        sr.service_id,
        sr.service_area_id,
        COUNT(*) AS active_count
    FROM referrals r
    JOIN service_requests sr
        ON sr.request_id = r.request_id
    WHERE r.status IN ('sent', 'accepted', 'attended')
    GROUP BY
        r.organization_id,
        sr.service_id,
        sr.service_area_id
) actual
    ON actual.organization_id = os.organization_id
    AND actual.service_id = os.service_id
    AND actual.service_area_id = os.service_area_id
WHERE os.current_active_referrals <>
    COALESCE(actual.active_count, 0);


-- Verify capacity limits.

SELECT *
FROM organization_services
WHERE current_active_referrals > active_referral_limit
OR current_active_referrals < 0;


-- Verify attendance statistics.

SELECT is_on_time, COUNT(*) AS total
FROM attendance_records
GROUP BY is_on_time;


-- Verify future attendance timestamps.

SELECT *
FROM attendance_records
WHERE first_attended_at > UTC_TIMESTAMP();


-- Verify backup referrals.

SELECT
    sr.title,
    r.attempt_number,
    o.name AS organization_name,
    r.status,
    (r.attempt_number > 1) AS is_backup
FROM referrals r
JOIN service_requests sr
    ON sr.request_id = r.request_id
JOIN organizations o
    ON o.organization_id = r.organization_id
WHERE sr.title IN (
    '[DEMO] Completed food assistance',
    '[DEMO] Completed peer support'
)
ORDER BY sr.request_id, r.attempt_number;


-- IMPORTANT:
-- Transaction intentionally left open.
-- Do not commit until validation is reviewed.
