"""Disposable SQL attendance tests; never connects to the live database."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.auth import Identity
from app.services.attendance import record_attendance, handle_request_attended, AttendanceError
from app.services.matching import handle_request_created
from app.services.referrals import accept_referral
from conftest import LocalSession


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def change(engine, sql):
    with engine.begin() as connection:
        connection.execute(text(sql))


@pytest.fixture(autouse=True)
def attendance_tables(engine):
    # Expand only this disposable fixture to the existing production table shape.
    change(engine, 'ALTER TABLE organization_representatives ADD COLUMN representative_id INTEGER')
    change(engine, 'UPDATE organization_representatives SET representative_id=40 WHERE user_id=4')
    change(engine, 'DROP TABLE attendance_records')
    change(engine, '''CREATE TABLE attendance_records(
        attendance_id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL UNIQUE,
        referral_id INTEGER NOT NULL, attended_by_representative_id INTEGER NOT NULL,
        first_attended_at DATETIME NOT NULL, is_on_time BOOLEAN NOT NULL, notes TEXT)''')


@pytest.fixture
def accepted(session, engine, event):
    handle_request_created(session, event)
    referral = scalar(engine, 'SELECT referral_id FROM referrals')
    accept_referral(session, referral, 4)
    return referral


def attendance_event(engine, referral):
    return dict(event_id='attendance-test', event_type='RequestAttended', request_id=1,
                payload=dict(referral_id=referral,
                             attendance_id=scalar(engine, 'SELECT attendance_id FROM attendance_records')))


def test_success_atomic_preserves_capacity_and_sla(session, engine, accepted):
    deadline = scalar(engine, 'SELECT attendance_deadline FROM service_requests')
    responded = scalar(engine, 'SELECT responded_at FROM referrals')
    result = record_attendance(session, accepted, 4)
    assert not result['already_processed'] and result['is_on_time']
    assert scalar(engine, 'SELECT status FROM referrals') == 'attended'
    assert scalar(engine, 'SELECT status FROM service_requests') == 'in_progress'
    assert scalar(engine, 'SELECT attendance_deadline FROM service_requests') == deadline
    assert scalar(engine, 'SELECT priority_id FROM service_requests') == 1
    assert scalar(engine, 'SELECT responded_at FROM referrals') == responded
    assert scalar(engine, 'SELECT attended_by_representative_id FROM attendance_records') == 40
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 1
    assert scalar(engine, "SELECT changed_by_user_id FROM referral_status_history WHERE new_status='attended'") == 4
    assert scalar(engine, "SELECT COUNT(*) FROM event_outbox WHERE event_type='RequestAttended'") == 1
    assert handle_request_attended(session, attendance_event(engine, accepted)) == 'on_time'
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 0


def test_duplicate_keeps_first_timestamp_and_outbox_id(session, engine, accepted):
    record_attendance(session, accepted, 4)
    timestamp = scalar(engine, 'SELECT first_attended_at FROM attendance_records')
    event_id = scalar(engine, "SELECT event_id FROM event_outbox WHERE event_type='RequestAttended'")
    assert record_attendance(session, accepted, 4)['already_processed']
    assert scalar(engine, 'SELECT first_attended_at FROM attendance_records') == timestamp
    assert scalar(engine, "SELECT event_id FROM event_outbox WHERE event_type='RequestAttended'") == event_id
    assert scalar(engine, "SELECT COUNT(*) FROM referral_status_history WHERE new_status='attended'") == 1
    change(engine, "UPDATE referrals SET status='completed'")
    change(engine, "UPDATE service_requests SET status='completed'")
    assert record_attendance(session, accepted, 4)['already_processed']
    assert scalar(engine, 'SELECT status FROM service_requests') == 'completed'


def test_timestamp_uses_existing_mysql_whole_second_precision(session, engine, accepted):
    deadline = datetime(2030, 1, 1, 12)
    change(engine, "UPDATE service_requests SET attendance_deadline='2030-01-01 12:00:00'")
    with patch('app.services.attendance.utcnow', return_value=deadline + timedelta(microseconds=900000)):
        assert record_attendance(session, accepted, 4)['is_on_time']
    assert handle_request_attended(session, attendance_event(engine, accepted)) == 'on_time'


@pytest.mark.parametrize('offset,on_time', [(-1, True), (0, True), (1, False)])
def test_sla_boundary_and_late_notification(session, engine, accepted, offset, on_time):
    deadline = datetime(2030, 1, 1, 12)
    change(engine, "UPDATE service_requests SET attendance_deadline='2030-01-01 12:00:00'")
    with patch('app.services.attendance.utcnow', return_value=deadline + timedelta(seconds=offset)):
        assert record_attendance(session, accepted, 4)['is_on_time'] == on_time
    event = attendance_event(engine, accepted)
    assert handle_request_attended(session, event) == ('on_time' if on_time else 'late')
    event['event_id'] = 'redelivery-new-envelope'
    handle_request_attended(session, event)
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == (0 if on_time else 1)
    if not on_time:
        assert scalar(engine, 'SELECT deduplication_key FROM notifications') == 'attendance-late:1'
        assert scalar(engine, 'SELECT user_id FROM notifications') == 1


@pytest.mark.parametrize('sql', [
    'UPDATE users SET is_active=0 WHERE user_id=4',
    'UPDATE users SET role_id=1 WHERE user_id=4',
    'UPDATE organization_representatives SET organization_id=2 WHERE user_id=4',
    'DELETE FROM organization_representatives WHERE user_id=4',
])
def test_authorization_rechecked_even_on_retry(session, engine, accepted, sql):
    record_attendance(session, accepted, 4)
    change(engine, sql)
    with pytest.raises(AttendanceError) as error:
        record_attendance(session, accepted, 4)
    assert error.value.status == 404
    assert scalar(engine, 'SELECT COUNT(*) FROM attendance_records') == 1


@pytest.mark.parametrize('status', ['sent', 'rejected', 'timed_out', 'attended', 'completed'])
def test_requires_accepted_referral(session, engine, accepted, status):
    change(engine, f"UPDATE referrals SET status='{status}'")
    with pytest.raises(AttendanceError):
        record_attendance(session, accepted, 4)
    assert scalar(engine, 'SELECT COUNT(*) FROM attendance_records') == 0


@pytest.mark.parametrize('sql', [
    "UPDATE service_requests SET status='cancelled'",
    'UPDATE referrals SET responded_at=NULL',
    'UPDATE organization_services SET current_active_referrals=0 WHERE organization_id=1',
    'DELETE FROM organization_services WHERE organization_id=1',
])
def test_inconsistent_state_fails_closed(session, engine, accepted, sql):
    change(engine, sql)
    with pytest.raises(AttendanceError):
        record_attendance(session, accepted, 4)
    assert scalar(engine, 'SELECT COUNT(*) FROM attendance_records') == 0


def test_outbox_failure_rolls_back_every_effect_then_retry(session, engine, accepted):
    with patch('app.services.attendance.enqueue', side_effect=RuntimeError('injected')):
        with pytest.raises(RuntimeError):
            record_attendance(session, accepted, 4)
    assert scalar(engine, 'SELECT COUNT(*) FROM attendance_records') == 0
    assert scalar(engine, 'SELECT status FROM referrals') == 'accepted'
    assert scalar(engine, 'SELECT status FROM service_requests') == 'matched'
    assert scalar(engine, "SELECT COUNT(*) FROM referral_status_history WHERE new_status='attended'") == 0
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 1
    assert not record_attendance(session, accepted, 4)['already_processed']


def test_missing_referral(session):
    with pytest.raises(AttendanceError) as error:
        record_attendance(session, 999, 4)
    assert error.value.status == 404


def test_consumer_rejects_forged_events_and_sla_inconsistency(session, engine, accepted):
    record_attendance(session, accepted, 4)
    event = attendance_event(engine, accepted)
    for key, value in [('attendance_id', True), ('referral_id', 0)]:
        bad = dict(event, payload=dict(event['payload'], **{key: value}))
        with pytest.raises(ValueError):
            handle_request_attended(session, bad)
    with pytest.raises(RuntimeError):
        handle_request_attended(session, dict(event, request_id=999))
    with pytest.raises(RuntimeError):
        handle_request_attended(session, dict(event, payload=dict(event['payload'], attendance_id=999)))
    change(engine, 'UPDATE attendance_records SET is_on_time=0')
    with pytest.raises(RuntimeError, match='inconsistent'):
        handle_request_attended(session, event)


def test_late_consumer_missing_coordinator_retries(session, engine, accepted):
    change(engine, "UPDATE service_requests SET attendance_deadline='2000-01-01'")
    record_attendance(session, accepted, 4)
    change(engine, 'UPDATE users SET is_active=0 WHERE user_id=1')
    event = attendance_event(engine, accepted)
    with pytest.raises(RuntimeError, match='coordinator'):
        handle_request_attended(session, event)
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 0
    change(engine, 'UPDATE users SET is_active=1 WHERE user_id=1')
    assert handle_request_attended(session, event) == 'late'


@pytest.fixture
def client(engine):
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with patch('app.auth.verify_token', return_value={'uid': 'synthetic', 'email': 'rep@example.test', 'email_verified': True}), \
         patch('app.auth.resolve_identity', return_value=(Identity(4, 'rep@example.test', 'representative', 1), None)), \
         patch('app.referrals.Session', side_effect=lambda unused: LocalSession(engine)):
        yield app.test_client()


def test_api_auth_success_retry_and_errors(client, engine, accepted):
    url = f'/api/referrals/{accepted}/attend'
    headers = {'Authorization': 'Bearer synthetic'}
    assert client.post(url).status_code == 401
    with patch('app.auth.resolve_identity', return_value=(Identity(9, 'member@example.test', 'member'), None)):
        assert client.post(url, headers=headers).status_code == 403
    with patch('app.referrals.record_attendance', side_effect=OperationalError('test', {}, Exception())):
        assert client.post(url, headers=headers).status_code == 503
    response = client.post(url, json={'first_attended_at': '2000-01-01', 'is_on_time': False}, headers=headers)
    assert response.status_code == 200 and response.json['is_on_time']
    assert client.post(url, headers=headers).json['already_processed']
    assert client.post('/api/referrals/999/attend', headers=headers).status_code == 404


def test_attendance_worker_dispatch():
    import runpy
    with patch('app.messaging.worker_runtime.run_consumer') as consumer:
        runpy.run_path('sla_worker.py', run_name='__main__')
    consumer.assert_called_once_with('sla_queue', 'RequestAttended', handle_request_attended)
