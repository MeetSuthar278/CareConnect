"""Completion tests use disposable SQL with mocked Firebase, never live data."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.auth import Identity
from app.services.completions import complete_referral, CompletionError, OUTCOMES
from app.services.matching import handle_request_created
from app.services.referrals import accept_referral
from app.services.outbox import utcnow
from conftest import LocalSession


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def change(engine, sql):
    with engine.begin() as connection:
        connection.execute(text(sql))


@pytest.fixture(autouse=True)
def completion_tables(engine):
    # These are existing production fields/tables, created only in disposable SQLite.
    change(engine, 'ALTER TABLE attendance_records ADD COLUMN request_id INTEGER')
    change(engine, '''CREATE TABLE service_completions(
        completion_id INTEGER PRIMARY KEY, request_id INTEGER NOT NULL UNIQUE,
        referral_id INTEGER NOT NULL, completed_at DATETIME NOT NULL,
        outcome TEXT NOT NULL, summary_notes TEXT)''')


@pytest.fixture
def attended(session, engine, event):
    handle_request_created(session, event)
    referral = scalar(engine, 'SELECT referral_id FROM referrals')
    accept_referral(session, referral, 4)
    change(engine, "UPDATE referrals SET status='attended'")
    change(engine, "UPDATE service_requests SET status='in_progress'")
    with engine.begin() as connection:
        connection.execute(text('''INSERT INTO attendance_records(attendance_id,request_id,referral_id,first_attended_at)
            VALUES(1,1,:referral,:now)'''), {'referral': referral, 'now': utcnow() - timedelta(minutes=1)})
    return referral


@pytest.mark.parametrize('outcome', sorted(OUTCOMES))
def test_completion_commits_preserves_history_and_releases_once(session, engine, attended, outcome):
    deadline = scalar(engine, 'SELECT attendance_deadline FROM service_requests')
    first_attended = scalar(engine, 'SELECT first_attended_at FROM attendance_records')
    result = complete_referral(session, attended, 4, outcome, ' Synthetic notes ')
    assert result['status'] == 'completed' and not result['already_processed']
    assert scalar(engine, 'SELECT outcome FROM service_completions') == outcome
    assert scalar(engine, 'SELECT summary_notes FROM service_completions') == 'Synthetic notes'
    assert scalar(engine, 'SELECT completed_at FROM service_completions') is not None
    assert scalar(engine, 'SELECT status FROM referrals') == 'completed'
    assert scalar(engine, 'SELECT status FROM service_requests') == 'completed'
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 0
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=2') == 1
    assert scalar(engine, "SELECT changed_by_user_id FROM referral_status_history WHERE new_status='completed'") == 4
    assert scalar(engine, 'SELECT attendance_deadline FROM service_requests') == deadline
    assert scalar(engine, 'SELECT first_attended_at FROM attendance_records') == first_attended
    assert scalar(engine, 'SELECT priority_id FROM service_requests') == 1
    assert scalar(engine, 'SELECT COUNT(*) FROM event_outbox') == 1  # Existing ReferralCreated only.
    saved_time = scalar(engine, 'SELECT completed_at FROM service_completions')
    repeated = complete_referral(session, attended, 4, outcome, 'Synthetic notes')
    assert repeated['already_processed'] and repeated['completion_id'] == result['completion_id']
    assert scalar(engine, 'SELECT completed_at FROM service_completions') == saved_time
    assert scalar(engine, 'SELECT COUNT(*) FROM service_completions') == 1
    assert scalar(engine, "SELECT COUNT(*) FROM referral_status_history WHERE new_status='completed'") == 1
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 0


def test_repeat_different_details_conflicts(session, engine, attended):
    complete_referral(session, attended, 4)
    with pytest.raises(CompletionError, match='different details'):
        complete_referral(session, attended, 4, 'unsuccessful')
    assert scalar(engine, 'SELECT outcome FROM service_completions') == 'successful'


@pytest.mark.parametrize('sql', [
    'UPDATE users SET is_active=0 WHERE user_id=4',
    'UPDATE users SET role_id=1 WHERE user_id=4',
    'UPDATE organization_representatives SET organization_id=2 WHERE user_id=4',
    'DELETE FROM organization_representatives WHERE user_id=4',
])
def test_rechecks_authorization_even_for_completed_retry(session, engine, attended, sql):
    complete_referral(session, attended, 4)
    change(engine, sql)
    with pytest.raises(CompletionError) as error:
        complete_referral(session, attended, 4)
    assert error.value.status == 404


@pytest.mark.parametrize('status', ['sent', 'accepted', 'rejected', 'timed_out', 'completed'])
def test_requires_attended_referral(session, engine, attended, status):
    change(engine, f"UPDATE referrals SET status='{status}'")
    with pytest.raises(CompletionError):
        complete_referral(session, attended, 4)
    assert scalar(engine, 'SELECT COUNT(*) FROM service_completions') == 0
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 1


@pytest.mark.parametrize('sql', [
    "UPDATE service_requests SET status='cancelled'",
    'DELETE FROM attendance_records',
    'UPDATE attendance_records SET referral_id=999',
    "UPDATE attendance_records SET first_attended_at='2099-01-01'",
    'UPDATE organization_services SET current_active_referrals=0 WHERE organization_id=1',
    'DELETE FROM organization_services WHERE organization_id=1',
])
def test_inconsistent_data_fails_closed(session, engine, attended, sql):
    change(engine, sql)
    with pytest.raises(CompletionError):
        complete_referral(session, attended, 4)
    assert scalar(engine, 'SELECT COUNT(*) FROM service_completions') == 0
    assert scalar(engine, 'SELECT status FROM referrals') == 'attended'


def test_history_failure_rolls_back_completion_status_and_capacity(session, engine, attended):
    with patch.object(session, 'add', side_effect=OperationalError('injected', {}, Exception())):
        with pytest.raises(OperationalError):
            complete_referral(session, attended, 4)
    assert scalar(engine, 'SELECT COUNT(*) FROM service_completions') == 0
    assert scalar(engine, 'SELECT status FROM referrals') == 'attended'
    assert scalar(engine, 'SELECT status FROM service_requests') == 'in_progress'
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 1
    assert not complete_referral(session, attended, 4)['already_processed']


def test_inconsistent_existing_completion_rejected(session, engine, attended):
    complete_referral(session, attended, 4)
    change(engine, 'UPDATE service_completions SET referral_id=999')
    with pytest.raises(CompletionError, match='inconsistent'):
        complete_referral(session, attended, 4)
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 0


def test_missing_referral(session):
    with pytest.raises(CompletionError) as error:
        complete_referral(session, 999, 4)
    assert error.value.status == 404


@pytest.mark.parametrize('outcome,notes', [(None,None),(True,None),('invalid',None),('successful',True),('successful','x'*2001)])
def test_validation(session, outcome, notes):
    with pytest.raises(CompletionError) as error:
        complete_referral(session, 1, 4, outcome, notes)
    assert error.value.status == 400


@pytest.fixture
def client(engine):
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:'})
    with patch('app.auth.verify_token', return_value={'uid': 'synthetic', 'email': 'rep@example.test', 'email_verified': True}), \
         patch('app.auth.resolve_identity', return_value=(Identity(4, 'rep@example.test', 'representative', 1), None)), \
         patch('app.referrals.Session', side_effect=lambda unused: LocalSession(engine)):
        yield app.test_client()


def test_api_auth_success_duplicate_and_failures(client, engine, attended):
    url = f'/api/referrals/{attended}/complete'
    headers = {'Authorization': 'Bearer synthetic'}
    assert client.post(url, json={}).status_code == 401
    with patch('app.auth.resolve_identity', return_value=(Identity(9, 'member@example.test', 'member'), None)):
        assert client.post(url, json={}, headers=headers).status_code == 403
    assert client.post(url, json=[], headers=headers).status_code == 400
    assert client.post(url, headers=headers).status_code == 400
    assert client.post(url, json={'outcome': 'bad'}, headers=headers).status_code == 400
    with patch('app.referrals.complete_referral', side_effect=OperationalError('test', {}, Exception())):
        assert client.post(url, json={}, headers=headers).status_code == 503
    response = client.post(url, json={}, headers=headers)
    assert response.status_code == 200 and response.json['outcome'] == 'successful'
    assert client.post(url, json={}, headers=headers).json['already_processed']
    assert client.post(url, json={'outcome': 'unsuccessful'}, headers=headers).status_code == 409
    assert client.post('/api/referrals/999/complete', json={}, headers=headers).status_code == 404
    change(engine, 'UPDATE organization_representatives SET organization_id=2 WHERE user_id=4')
    assert client.post(url, json={'organization_id': 1}, headers=headers).status_code == 404
