"""Acceptance uses disposable SQL and mocked Firebase; no live data changes."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.auth import Identity
from app.services.matching import handle_request_created
from app.services.referrals import accept_referral, AcceptanceError, reject_referral, RejectionError
from app.services.timeouts import timeout_referral
from conftest import LocalSession


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def change(engine, sql):
    with engine.begin() as connection:
        connection.execute(text(sql))


@pytest.fixture
def referral(session, engine, event):
    handle_request_created(session, event)
    return scalar(engine, 'SELECT referral_id FROM referrals')


def test_acceptance_atomic_idempotent_and_preserves_reservation(session, engine, referral):
    deadline = scalar(engine, 'SELECT attendance_deadline FROM service_requests')
    result = accept_referral(session, referral, 4)
    assert result == dict(referral_id=referral, request_id=1, status='accepted', already_processed=False)
    responded = scalar(engine, 'SELECT responded_at FROM referrals')
    assert responded is not None
    assert scalar(engine, 'SELECT status FROM referrals') == 'accepted'
    assert scalar(engine, 'SELECT status FROM service_requests') == 'matched'
    assert scalar(engine, 'SELECT attendance_deadline FROM service_requests') == deadline
    assert scalar(engine, 'SELECT priority_id FROM service_requests') == 1
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 1
    assert scalar(engine, "SELECT changed_by_user_id FROM referral_status_history WHERE new_status='accepted'") == 4
    assert accept_referral(session, referral, 4)['already_processed']
    assert scalar(engine, 'SELECT responded_at FROM referrals') == responded
    assert scalar(engine, "SELECT COUNT(*) FROM referral_status_history WHERE new_status='accepted'") == 1
    assert scalar(engine, 'SELECT COUNT(*) FROM event_outbox') == 1  # Initial ReferralCreated only.
    assert not timeout_referral(session, referral)
    with pytest.raises(RejectionError):
        reject_referral(session, referral, 4, 'Cannot reject after acceptance')


@pytest.mark.parametrize('sql', [
    'UPDATE users SET is_active=0 WHERE user_id=4',
    'UPDATE users SET role_id=1 WHERE user_id=4',
    'UPDATE organization_representatives SET organization_id=2 WHERE user_id=4',
    'DELETE FROM organization_representatives WHERE user_id=4',
])
def test_rechecks_sql_authorization(session, engine, referral, sql):
    change(engine, sql)
    with pytest.raises(AcceptanceError) as error:
        accept_referral(session, referral, 4)
    assert error.value.status == 404
    assert scalar(engine, 'SELECT status FROM referrals') == 'sent'


@pytest.mark.parametrize('status', ['rejected', 'timed_out', 'attended', 'completed'])
def test_invalid_referral_states(session, engine, referral, status):
    change(engine, f"UPDATE referrals SET status='{status}'")
    with pytest.raises(AcceptanceError):
        accept_referral(session, referral, 4)
    assert scalar(engine, "SELECT COUNT(*) FROM referral_status_history WHERE new_status='accepted'") == 0


@pytest.mark.parametrize('sql', [
    "UPDATE service_requests SET status='cancelled'",
    "UPDATE service_requests SET attendance_deadline='2000-01-01'",
    "UPDATE referrals SET responded_at='2000-01-01'",
    'UPDATE organization_services SET current_active_referrals=0 WHERE organization_id=1',
    'DELETE FROM organization_services WHERE organization_id=1',
])
def test_inconsistent_or_inactive_request_fails_closed(session, engine, referral, sql):
    change(engine, sql)
    with pytest.raises(AcceptanceError):
        accept_referral(session, referral, 4)
    assert scalar(engine, 'SELECT status FROM referrals') == 'sent'


@pytest.mark.parametrize('offset,allowed', [(-1, True), (0, False), (1, False)])
def test_deadline_boundary(session, engine, referral, offset, allowed):
    deadline = datetime(2030, 1, 1, 12)
    change(engine, "UPDATE referrals SET response_deadline='2030-01-01 12:00:00'")
    with patch('app.services.referrals.utcnow', return_value=deadline + timedelta(microseconds=offset)):
        if allowed:
            assert accept_referral(session, referral, 4)['status'] == 'accepted'
        else:
            with pytest.raises(AcceptanceError, match='deadline'):
                accept_referral(session, referral, 4)


def test_history_failure_rolls_back_and_can_retry(session, engine, referral):
    with patch.object(session, 'add', side_effect=OperationalError('injected', {}, Exception())):
        with pytest.raises(OperationalError):
            accept_referral(session, referral, 4)
    assert scalar(engine, 'SELECT status FROM referrals') == 'sent'
    assert scalar(engine, 'SELECT responded_at FROM referrals') is None
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 1
    assert accept_referral(session, referral, 4)['status'] == 'accepted'


def test_acceptance_wins_and_duplicate_acceptance_after_deadline(session, engine, referral):
    accept_referral(session, referral, 4)
    change(engine, "UPDATE referrals SET response_deadline='2000-01-01'")
    assert not timeout_referral(session, referral)
    assert accept_referral(session, referral, 4)['already_processed']
    change(engine, 'UPDATE users SET is_active=0 WHERE user_id=4')
    with pytest.raises(AcceptanceError):
        accept_referral(session, referral, 4)


def test_deadline_passes_while_waiting_for_offering_lock(session, engine, referral):
    deadline = datetime(2030, 1, 1, 12)
    change(engine, "UPDATE referrals SET response_deadline='2030-01-01 12:00:00'")
    with patch('app.services.referrals.utcnow', side_effect=[deadline - timedelta(seconds=1), deadline]):
        with pytest.raises(AcceptanceError, match='deadline'):
            accept_referral(session, referral, 4)
    assert scalar(engine, 'SELECT status FROM referrals') == 'sent'
    assert scalar(engine, 'SELECT responded_at FROM referrals') is None


def test_timeout_before_acceptance(session, engine, referral):
    change(engine, "UPDATE referrals SET response_deadline='2000-01-01'")
    assert timeout_referral(session, referral)
    with pytest.raises(AcceptanceError):
        accept_referral(session, referral, 4)
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 0


def test_missing_referral(session):
    with pytest.raises(AcceptanceError) as error:
        accept_referral(session, 999, 4)
    assert error.value.status == 404


@pytest.fixture
def client(engine):
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with patch('app.auth.verify_token', return_value={'uid': 'synthetic', 'email': 'rep@example.test', 'email_verified': True}), \
         patch('app.auth.resolve_identity', return_value=(Identity(4, 'rep@example.test', 'representative', 1), None)), \
         patch('app.referrals.Session', side_effect=lambda unused: LocalSession(engine)):
        yield app.test_client()


def test_api_success_retry_and_auth(client, referral):
    url = f'/api/referrals/{referral}/accept'
    assert client.post(url).status_code == 401
    headers = {'Authorization': 'Bearer synthetic'}
    response = client.post(url, headers=headers)
    assert response.status_code == 200
    assert response.json['status'] == 'accepted'
    assert client.post(url, headers=headers).json['already_processed']
    with patch('app.auth.resolve_identity', return_value=(Identity(9, 'member@example.test', 'member'), None)):
        assert client.post(url, headers=headers).status_code == 403


def test_api_errors(client, engine, referral):
    url = f'/api/referrals/{referral}/accept'
    headers = {'Authorization': 'Bearer synthetic'}
    with patch('app.referrals.accept_referral', side_effect=OperationalError('test', {}, Exception())):
        assert client.post(url, headers=headers).status_code == 503
    change(engine, "UPDATE referrals SET response_deadline='2000-01-01'")
    assert client.post(url, headers=headers).status_code == 409
    change(engine, 'UPDATE organization_representatives SET organization_id=2 WHERE user_id=4')
    assert client.post(url, json={'organization_id': 1, 'user_id': 4}, headers=headers).status_code == 404
