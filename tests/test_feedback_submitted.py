"""Feedback tests use disposable SQL and mocked Firebase only."""
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.auth import Identity
from app.services.feedback import submit_feedback, handle_feedback_submitted, FeedbackError
from app.services.matching import handle_request_created
from app.services.completions import complete_referral
from conftest import LocalSession


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def change(engine, sql):
    with engine.begin() as connection:
        connection.execute(text(sql))


@pytest.fixture(autouse=True)
def feedback_tables(engine):
    # Existing production fields/tables are mirrored only in disposable SQLite.
    change(engine, 'ALTER TABLE attendance_records ADD COLUMN request_id INTEGER')
    change(engine, '''CREATE TABLE service_completions(completion_id INTEGER PRIMARY KEY,
        request_id INTEGER NOT NULL UNIQUE,referral_id INTEGER NOT NULL,completed_at DATETIME NOT NULL,
        outcome TEXT NOT NULL,summary_notes TEXT)''')
    change(engine, '''CREATE TABLE feedback(feedback_id INTEGER PRIMARY KEY,request_id INTEGER NOT NULL UNIQUE,
        member_id INTEGER NOT NULL,organization_id INTEGER NOT NULL,is_helpful BOOLEAN NOT NULL,
        rating INTEGER,comment TEXT,submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')


@pytest.fixture
def completed(session, engine, event):
    handle_request_created(session, event)
    referral = scalar(engine, 'SELECT referral_id FROM referrals')
    change(engine, "UPDATE referrals SET status='attended',responded_at='2000-01-01'")
    change(engine, "UPDATE service_requests SET status='in_progress'")
    change(engine, f"INSERT INTO attendance_records(attendance_id,request_id,referral_id,first_attended_at) VALUES(1,1,{referral},'2000-01-01')")
    complete_referral(session, referral, 4)
    return referral


def feedback_event(engine):
    return dict(event_id='feedback-test',event_type='FeedbackSubmitted',request_id=1,
                payload={'feedback_id': scalar(engine, 'SELECT feedback_id FROM feedback')})


@pytest.mark.parametrize('helpful', [True, False])
def test_atomic_feedback_duplicate_and_notifications(session, engine, completed, helpful):
    result = submit_feedback(session, 1, 9, helpful, ' Synthetic comment ')
    assert result['is_helpful'] == helpful and not result['already_processed']
    assert scalar(engine, 'SELECT comment FROM feedback') == 'Synthetic comment'
    assert scalar(engine, 'SELECT member_id FROM feedback') == 9
    assert scalar(engine, 'SELECT organization_id FROM feedback') == 1
    assert scalar(engine, 'SELECT rating FROM feedback') is None
    saved_time = scalar(engine, 'SELECT submitted_at FROM feedback')
    event_id = scalar(engine, "SELECT event_id FROM event_outbox WHERE event_type='FeedbackSubmitted'")
    assert submit_feedback(session, 1, 9, helpful, 'Synthetic comment')['already_processed']
    assert scalar(engine, 'SELECT COUNT(*) FROM feedback') == 1
    assert scalar(engine, 'SELECT submitted_at FROM feedback') == saved_time
    assert scalar(engine, "SELECT event_id FROM event_outbox WHERE event_type='FeedbackSubmitted'") == event_id
    event = feedback_event(engine)
    handle_feedback_submitted(session, event)
    handle_feedback_submitted(session, dict(event, event_id='redelivery'))
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications WHERE user_id=4') == 1
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications WHERE user_id=1') == (0 if helpful else 1)
    assert scalar(engine, 'SELECT status FROM service_requests') == 'completed'
    assert scalar(engine, 'SELECT status FROM referrals') == 'completed'
    assert scalar(engine, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=1') == 0


def test_conflicting_repeat_does_not_overwrite(session, engine, completed):
    submit_feedback(session, 1, 9, True)
    for helpful, comment in [(False, None), (True, 'Changed')]:
        with pytest.raises(FeedbackError, match='different details'):
            submit_feedback(session, 1, 9, helpful, comment)
    assert scalar(engine, 'SELECT is_helpful FROM feedback') == 1
    assert scalar(engine, 'SELECT comment FROM feedback') is None


@pytest.mark.parametrize('sql', [
    'UPDATE users SET is_active=0 WHERE user_id=9',
    'UPDATE users SET role_id=2 WHERE user_id=9',
    'UPDATE service_requests SET member_id=1',
])
def test_rechecks_member_ownership_even_on_repeat(session, engine, completed, sql):
    submit_feedback(session, 1, 9, True)
    change(engine, sql)
    with pytest.raises(FeedbackError) as error:
        submit_feedback(session, 1, 9, True)
    assert error.value.status == 404


@pytest.mark.parametrize('status', ['submitted','matched','in_progress','unmatched','cancelled'])
def test_requires_completed_request(session, engine, completed, status):
    change(engine, f"UPDATE service_requests SET status='{status}'")
    with pytest.raises(FeedbackError):
        submit_feedback(session, 1, 9, True)
    assert scalar(engine, 'SELECT COUNT(*) FROM feedback') == 0


@pytest.mark.parametrize('sql', [
    'DELETE FROM service_completions',
    'UPDATE service_completions SET referral_id=999',
    "UPDATE referrals SET status='attended'",
])
def test_requires_consistent_completed_service(session, engine, completed, sql):
    change(engine, sql)
    with pytest.raises(FeedbackError, match='inconsistent'):
        submit_feedback(session, 1, 9, True)


@pytest.mark.parametrize('helpful,comment', [(None,None),(1,None),('yes',None),(False,True),(True,'x'*2001)])
def test_input_validation(session, helpful, comment):
    with pytest.raises(FeedbackError) as error:
        submit_feedback(session, 1, 9, helpful, comment)
    assert error.value.status == 400


def test_missing_request_and_blank_comment(session, engine, completed):
    with pytest.raises(FeedbackError) as error:
        submit_feedback(session, 999, 9, True)
    assert error.value.status == 404
    submit_feedback(session, 1, 9, True, '   ')
    assert scalar(engine, 'SELECT comment FROM feedback') is None


def test_outbox_failure_rolls_back_feedback_then_retries(session, engine, completed):
    with patch('app.services.feedback.enqueue', side_effect=RuntimeError('injected')):
        with pytest.raises(RuntimeError):
            submit_feedback(session, 1, 9, False)
    assert scalar(engine, 'SELECT COUNT(*) FROM feedback') == 0
    assert scalar(engine, "SELECT COUNT(*) FROM event_outbox WHERE event_type='FeedbackSubmitted'") == 0
    assert not submit_feedback(session, 1, 9, False)['already_processed']


def test_missing_coordinator_rolls_back_partner_notification(session, engine, completed):
    submit_feedback(session, 1, 9, False)
    change(engine, 'UPDATE users SET is_active=0 WHERE user_id=1')
    with pytest.raises(RuntimeError, match='coordinator'):
        handle_feedback_submitted(session, feedback_event(engine))
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 0
    change(engine, 'UPDATE users SET is_active=1 WHERE user_id=1')
    handle_feedback_submitted(session, feedback_event(engine))
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 2


def test_primary_recipient_and_fallback(session, engine, completed):
    change(engine, "INSERT INTO users VALUES(5,2,'rep2@example.test','demo',1)")
    change(engine, 'INSERT INTO organization_representatives VALUES(5,1,0)')
    submit_feedback(session, 1, 9, True)
    handle_feedback_submitted(session, feedback_event(engine))
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications WHERE user_id=4') == 1
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications WHERE user_id=5') == 0
    change(engine, 'UPDATE users SET is_active=0 WHERE user_id=4')
    handle_feedback_submitted(session, feedback_event(engine))
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications WHERE user_id=5') == 1


def test_missing_representative_retries(session, engine, completed):
    submit_feedback(session, 1, 9, True)
    change(engine, 'UPDATE users SET is_active=0 WHERE user_id=4')
    with pytest.raises(RuntimeError, match='representative'):
        handle_feedback_submitted(session, feedback_event(engine))
    assert scalar(engine, 'SELECT COUNT(*) FROM notifications') == 0
    change(engine, 'UPDATE users SET is_active=1 WHERE user_id=4')
    handle_feedback_submitted(session, feedback_event(engine))


def test_invalid_and_mismatched_events(session, engine, completed):
    submit_feedback(session, 1, 9, True)
    event = feedback_event(engine)
    for value in (None,True,0):
        with pytest.raises(ValueError):
            handle_feedback_submitted(session, dict(event,payload={'feedback_id':value}))
    with pytest.raises(RuntimeError):
        handle_feedback_submitted(session, dict(event,request_id=999))
    with pytest.raises(RuntimeError):
        handle_feedback_submitted(session, dict(event,payload={'feedback_id':999}))
    change(engine, 'UPDATE feedback SET organization_id=2')
    with pytest.raises(RuntimeError):
        handle_feedback_submitted(session, event)


@pytest.fixture
def client(engine):
    app = create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with patch('app.auth.verify_token',return_value={'uid':'synthetic','email':'member@example.test','email_verified':True}), \
         patch('app.auth.resolve_identity',return_value=(Identity(9,'member@example.test','member'),None)), \
         patch('app.feedback.Session',side_effect=lambda unused:LocalSession(engine)):
        yield app.test_client()


def test_api_auth_validation_success_and_errors(client, engine, completed):
    url='/api/requests/1/feedback'
    headers={'Authorization':'Bearer synthetic'}
    assert client.post(url,json={'is_helpful':True}).status_code == 401
    with patch('app.auth.resolve_identity',return_value=(Identity(4,'rep@example.test','representative',1),None)):
        assert client.post(url,json={'is_helpful':True},headers=headers).status_code == 403
    for payload in ([],{}, {'is_helpful':1}, {'is_helpful':True,'rating':5}):
        assert client.post(url,json=payload,headers=headers).status_code == 400
    with patch('app.feedback.submit_feedback',side_effect=OperationalError('test',{},Exception())):
        assert client.post(url,json={'is_helpful':True},headers=headers).status_code == 503
    response=client.post(url,json={'is_helpful':False,'member_id':4,'organization_id':2},headers=headers)
    assert response.status_code == 200 and response.json['is_helpful'] is False
    assert scalar(engine, 'SELECT member_id FROM feedback') == 9
    assert scalar(engine, 'SELECT organization_id FROM feedback') == 1
    assert client.post(url,json={'is_helpful':False},headers=headers).json['already_processed']
    assert client.post(url,json={'is_helpful':True},headers=headers).status_code == 409
    assert client.post('/api/requests/999/feedback',json={'is_helpful':True},headers=headers).status_code == 404


def test_worker_dispatch():
    import runpy
    with patch('app.messaging.worker_runtime.run_consumer') as consumer:
        runpy.run_path('feedback_worker.py',run_name='__main__')
    consumer.assert_called_once_with('feedback_queue','FeedbackSubmitted',handle_feedback_submitted)
