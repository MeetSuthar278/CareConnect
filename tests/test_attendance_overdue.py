"""Overdue tests use disposable SQL only; no live scans or data changes."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app import create_app
from app.services.overdue import (
    overdue_request_ids, flag_overdue, scan_overdue_once, handle_attendance_overdue,
)
from conftest import LocalSession


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def change(engine, sql):
    with engine.begin() as connection:
        connection.execute(text(sql))


@pytest.fixture(autouse=True)
def overdue_fixture(engine):
    # Add the existing production request_id field only to this disposable fixture.
    change(engine, 'ALTER TABLE attendance_records ADD COLUMN request_id INTEGER')
    # Match SQLAlchemy's SQLite DateTime serialization at exact equality.
    change(engine, "UPDATE service_requests SET attendance_deadline='2030-01-01 12:00:00.000000'")
    with patch('app.services.overdue.utcnow', return_value=datetime(2030, 1, 1, 13)):
        yield


def event():
    return dict(event_id='overdue-event', event_type='AttendanceOverdue', request_id=1,
                payload={'attendance_deadline': '2030-01-01T12:00:00Z'})


def attend(engine, timestamp):
    change(engine, f"INSERT INTO attendance_records(attendance_id,request_id,referral_id,first_attended_at) VALUES(1,1,1,'{timestamp}')")


def test_missing_attendance_is_detected_without_referral_and_flagged_once(session, engine):
    assert overdue_request_ids(session) == [1]
    session.rollback()
    assert flag_overdue(session, 1)
    first_id = scalar(engine, 'SELECT event_id FROM event_outbox')
    assert not flag_overdue(session, 1)
    assert scalar(engine, 'SELECT event_id FROM event_outbox') == first_id
    assert scalar(engine, 'SELECT COUNT(*) FROM event_outbox') == 1
    assert scalar(engine, 'SELECT deduplication_key FROM event_outbox') == 'attendance-overdue:1'
    assert scalar(engine, 'SELECT status FROM service_requests') == 'submitted'
    assert scalar(engine, 'SELECT priority_id FROM service_requests') == 1
    assert scalar(engine, 'SELECT COUNT(*) FROM referrals') == 0
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=2') == 1
    assert overdue_request_ids(session) == []


@pytest.mark.parametrize('status', ['submitted', 'matched', 'in_progress', 'unmatched'])
def test_open_states_are_preserved(session, engine, status):
    change(engine, f"UPDATE service_requests SET status='{status}'")
    assert flag_overdue(session, 1)
    assert handle_attendance_overdue(session, event()) == 'alerted'
    assert scalar(engine, 'SELECT status FROM service_requests') == status


@pytest.mark.parametrize('status', ['completed', 'cancelled'])
def test_terminal_states_excluded_from_discovery_and_stale_delivery(session, engine, status):
    assert flag_overdue(session, 1)
    change(engine, f"UPDATE service_requests SET status='{status}'")
    assert overdue_request_ids(session) == []
    session.rollback()
    assert not flag_overdue(session, 1)
    assert handle_attendance_overdue(session, event()) == 'stale'
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 0


@pytest.mark.parametrize('offset,eligible', [(-1, False), (0, False), (1, True)])
def test_deadline_boundary(session, engine, offset, eligible):
    with patch('app.services.overdue.utcnow', return_value=datetime(2030, 1, 1, 12) + timedelta(seconds=offset)):
        assert bool(overdue_request_ids(session)) == eligible
        session.rollback()
        assert flag_overdue(session, 1) == eligible


@pytest.mark.parametrize('timestamp', ['2030-01-01 11:59:59', '2030-01-01 12:00:00', '2030-01-01 12:00:01'])
def test_any_attendance_excludes_new_scans(session, engine, timestamp):
    attend(engine, timestamp)
    assert overdue_request_ids(session) == []
    session.rollback()
    assert not flag_overdue(session, 1)


def test_candidate_recheck_after_attendance_arrives(session, engine):
    assert overdue_request_ids(session) == [1]
    session.rollback()
    attend(engine, '2030-01-01 12:00:00')
    assert not flag_overdue(session, 1)
    assert scalar(engine, 'SELECT COUNT(*) FROM event_outbox') == 0


@pytest.mark.parametrize('timestamp,outcome', [('2030-01-01 12:00:00', 'stale'), ('2030-01-01 12:00:01', 'alerted')])
def test_delayed_consumer_checks_timely_attendance(session, engine, timestamp, outcome):
    flag_overdue(session, 1)
    attend(engine, timestamp)
    assert handle_attendance_overdue(session, event()) == outcome
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == (outcome == 'alerted')


def test_coordinator_alert_deduplicates_changed_envelope(session, engine):
    flag_overdue(session, 1)
    assert handle_attendance_overdue(session, event()) == 'alerted'
    duplicate = dict(event(), event_id='different-envelope')
    assert handle_attendance_overdue(session, duplicate) == 'alerted'
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 1
    assert scalar(engine, 'SELECT user_id FROM notifications') == 1
    assert scalar(engine, 'SELECT type FROM notifications') == 'deadline_missed'
    assert scalar(engine, 'SELECT deduplication_key FROM notifications') == 'attendance-overdue:1'


def test_missing_coordinator_retries_without_losing_flag(session, engine):
    flag_overdue(session, 1)
    change(engine, 'UPDATE users SET is_active=0 WHERE user_id=1')
    with pytest.raises(RuntimeError, match='coordinator'):
        handle_attendance_overdue(session, event())
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 0
    assert scalar(engine, 'SELECT COUNT(*) FROM event_outbox') == 1
    change(engine, 'UPDATE users SET is_active=1 WHERE user_id=1')
    assert handle_attendance_overdue(session, event()) == 'alerted'


def test_notification_failure_rolls_back_all_recipients(session, engine):
    from app.services.notifications import notify
    change(engine, "INSERT INTO users VALUES(2,3,'coord2@example.test','demo',1)")
    flag_overdue(session, 1)
    def fail_after_first(session, users, request_id, key, title, message, kind):
        notify(session, users[:1], request_id, key, title, message, kind)
        raise RuntimeError('injected')
    with patch('app.services.overdue.notify', side_effect=fail_after_first):
        with pytest.raises(RuntimeError):
            handle_attendance_overdue(session, event())
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 0
    handle_attendance_overdue(session, event())
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 2


def test_producer_failure_rolls_back_and_retries(session, engine):
    with patch('app.services.overdue.enqueue', side_effect=RuntimeError('injected')):
        with pytest.raises(RuntimeError):
            flag_overdue(session, 1)
    assert scalar(engine, 'SELECT COUNT(*) FROM event_outbox') == 0
    assert flag_overdue(session, 1)


def test_batch_failure_isolation_and_target_filter(engine):
    change(engine, '''INSERT INTO service_requests(request_id,member_id,service_id,service_area_id,priority_id,title,description,status,attendance_deadline)
        VALUES(2,9,1,1,1,'Synthetic','Test','submitted','2030-01-01 11:00:00')''')
    def process(session, request_id):
        if request_id == 1:
            raise RuntimeError('injected')
        return flag_overdue(session, request_id)
    with patch('app.services.overdue.flag_overdue', side_effect=process):
        assert scan_overdue_once(lambda: LocalSession(engine)) == dict(examined=2, flagged=1, skipped=0, failed=1)
    with LocalSession(engine) as session:
        assert overdue_request_ids(session, request_ids=[2]) == []
    assert scan_overdue_once(lambda: LocalSession(engine), request_ids=[1])['flagged'] == 1
    assert scan_overdue_once(lambda: LocalSession(engine))['examined'] == 0


def test_missing_future_and_forged_events(session):
    assert not flag_overdue(session, 999)
    with pytest.raises(RuntimeError):
        handle_attendance_overdue(session, dict(event(), request_id=999))
    with pytest.raises(ValueError):
        handle_attendance_overdue(session, dict(event(), payload={}))
    with patch('app.services.overdue.utcnow', return_value=datetime(2029, 1, 1)):
        with pytest.raises(RuntimeError, match='not passed'):
            handle_attendance_overdue(session, event())


def test_batch_validation(session):
    for limit in (0, 1001):
        with pytest.raises(ValueError):
            overdue_request_ids(session, limit)


def test_cli_preview_targeted_apply_and_mode_safety():
    import deadline_checker
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with patch.object(deadline_checker, 'create_app', return_value=app), \
         patch.object(deadline_checker, 'overdue_request_ids', return_value=[1]) as discover, \
         patch.object(deadline_checker, 'scan_overdue_once', return_value={'failed': 0}) as scanner, \
         patch.object(deadline_checker, 'scan_once') as acceptance:
        assert deadline_checker.main(['--kind', 'attendance', '--once', '--request-id', '1']) == 0
        discover.assert_called_once()
        scanner.assert_not_called()
        assert deadline_checker.main(['--kind', 'attendance', '--apply', '--once', '--request-id', '1']) == 0
        assert scanner.call_args.args[2] == [1]
        acceptance.assert_not_called()
    for argv in (['--kind', 'attendance', '--referral-id', '1'], ['--request-id', '1']):
        with pytest.raises(SystemExit):
            deadline_checker.main(argv)


def test_worker_dispatch():
    import runpy
    with patch('app.messaging.worker_runtime.run_consumer') as consumer:
        runpy.run_path('coordinator_worker.py', run_name='__main__')
    consumer.assert_called_once_with('coordinator_queue', 'AttendanceOverdue', handle_attendance_overdue)
