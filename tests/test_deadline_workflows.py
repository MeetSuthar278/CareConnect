"""Deadline retries and event contracts on an isolated database and fake broker."""
from datetime import datetime, timedelta
import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.services import overdue, timeouts
from app.services.outbox import utcnow


@pytest.fixture
def engine():
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'before_cursor_execute', retval=True)
    def sqlite_locks(connection, cursor, statement, parameters, context, executemany):
        return statement.replace(' FOR UPDATE', ''), parameters
    with engine.begin() as connection:
        for sql in [
            'CREATE TABLE service_requests(request_id INTEGER PRIMARY KEY,status TEXT,service_id INTEGER,service_area_id INTEGER,attendance_deadline DATETIME)',
            'CREATE TABLE referrals(referral_id INTEGER PRIMARY KEY,request_id INTEGER,organization_id INTEGER,status TEXT,attempt_number INTEGER,response_deadline DATETIME)',
            'CREATE TABLE organization_services(organization_service_id INTEGER PRIMARY KEY,organization_id INTEGER,service_id INTEGER,service_area_id INTEGER,current_active_referrals INTEGER)',
            'CREATE TABLE referral_status_history(history_id INTEGER PRIMARY KEY,referral_id INTEGER,old_status TEXT,new_status TEXT,notes TEXT,changed_by_user_id INTEGER)',
            'CREATE TABLE attendance_records(attendance_id INTEGER PRIMARY KEY,request_id INTEGER)',
            'CREATE TABLE event_outbox(event_id TEXT PRIMARY KEY,deduplication_key TEXT UNIQUE,event_type TEXT,event_version INTEGER,request_id INTEGER,payload JSON,created_at DATETIME,available_at DATETIME,published_at DATETIME,attempts INTEGER,last_error TEXT)',
            'CREATE TABLE roles(role_id INTEGER PRIMARY KEY,role_name TEXT)',
            'CREATE TABLE users(user_id INTEGER PRIMARY KEY,role_id INTEGER,is_active BOOLEAN)',
        ]:
            connection.execute(text(sql))
        connection.execute(text("INSERT INTO roles VALUES(1,'coordinator')"))
        connection.execute(text('INSERT INTO users VALUES(1,1,TRUE)'))
        connection.execute(text("INSERT INTO service_requests VALUES(1,'matched',1,1,:deadline)"), {'deadline': utcnow() - timedelta(hours=1)})
        connection.execute(text("INSERT INTO referrals VALUES(1,1,1,'sent',1,:deadline)"), {'deadline': utcnow() - timedelta(hours=2)})
        connection.execute(text('INSERT INTO organization_services VALUES(1,1,1,1,1)'))
    yield engine
    engine.dispose()


def test_timeout_replay_releases_capacity_once_and_preserves_deadline(engine):
    with engine.connect() as connection:
        deadline = connection.execute(text('SELECT attendance_deadline FROM service_requests')).scalar_one()
    for expected in (True, False):
        with Session(engine) as database:
            assert timeouts.expire_referral(database, 1) is expected
    with engine.connect() as connection:
        assert connection.execute(text('SELECT current_active_referrals FROM organization_services')).scalar_one() == 0
        assert connection.execute(text('SELECT status FROM referrals')).scalar_one() == 'timed_out'
        assert connection.execute(text('SELECT status FROM service_requests')).scalar_one() == 'submitted'
        assert connection.execute(text('SELECT attendance_deadline FROM service_requests')).scalar_one() == deadline
        assert connection.execute(text('SELECT COUNT(*) FROM referral_status_history')).scalar_one() == 1
        row = connection.execute(text('SELECT event_type,payload FROM event_outbox')).one()
        assert row.event_type == 'AcceptanceTimedOut'
        import json
        assert json.loads(row.payload) == {'referral_id': 1, 'organization_id': 1, 'attempt_number': 1}


def test_timeout_rolls_back_every_effect_when_outbox_fails(engine, monkeypatch):
    monkeypatch.setattr(timeouts, 'enqueue', Mock(side_effect=RuntimeError('synthetic failure')))
    with Session(engine) as database:
        with pytest.raises(RuntimeError):
            timeouts.expire_referral(database, 1)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT current_active_referrals FROM organization_services')).scalar_one() == 1
        assert connection.execute(text('SELECT status FROM referrals')).scalar_one() == 'sent'


def test_deadline_discovery_is_bounded_read_only_and_filters_ids(engine):
    with Session(engine) as database:
        assert timeouts.expired_referral_ids(database, 10, [1]) == [1]
        assert timeouts.expired_referral_ids(database, 10, [999]) == []
    with engine.connect() as connection:
        assert connection.execute(text('SELECT COUNT(*) FROM event_outbox')).scalar_one() == 0
    result = timeouts.scan_once(lambda: Session(engine), 10, [1])
    assert result == {'processed': 1, 'skipped': 0, 'failed': 0}


def test_overdue_event_is_unique_and_has_stable_notification_replay_key(engine, monkeypatch):
    for expected in (True, False):
        with Session(engine) as database:
            assert overdue.mark_overdue(database, 1) is expected
    with Session(engine) as database:
        assert overdue.overdue_request_ids(database) == []
        assert database.execute(text('SELECT COUNT(*) FROM event_outbox')).scalar_one() == 1
    notify = Mock()
    monkeypatch.setattr(overdue, 'notify', notify)
    for _ in range(2):
        with Session(engine) as database:
            assert overdue.handle_attendance_overdue(database, {'request_id': 1}) == 'notified'
    assert notify.call_args_list[0].args[3] == notify.call_args_list[1].args[3] == 'attendance-overdue:1'
    with engine.begin() as connection:
        connection.execute(text('INSERT INTO attendance_records VALUES(1,1)'))
    with Session(engine) as database:
        assert overdue.handle_attendance_overdue(database, {'request_id': 1}) == 'resolved'
    assert notify.call_count == 2


@pytest.mark.parametrize('module', ['worker', 'notification_worker', 'sla_worker', 'coordinator_worker',
                                  'feedback_worker', 'outbox_dispatcher', 'deadline_checker'])
def test_required_worker_entrypoints_import_without_starting_services(module):
    importlib.import_module(module)


def test_matching_fetches_partner_metrics_once_without_changing_ranking(monkeypatch):
    from app.services import matching
    candidates = [SimpleNamespace(organization_id=number, organization_service_id=number,
                                  current_active_referrals=1 if number < 3 else 2) for number in (1, 2, 3)]
    eligible = Mock(return_value=candidates)
    monkeypatch.setattr(matching, 'eligible_offerings', eligible)
    create = Mock(return_value='matched')
    monkeypatch.setattr(matching, 'create_referral_locked', create)
    database = Mock()
    database.execute.return_value.mappings.return_value.all.return_value = [
        {'organization_id': 1, 'acceptance': 0.8, 'on_time': 0.5},
        {'organization_id': 2, 'acceptance': 0.8, 'on_time': 0.9},
        {'organization_id': 3, 'acceptance': 1.0, 'on_time': 1.0},
    ]
    request = SimpleNamespace(attendance_deadline=utcnow() + timedelta(hours=1))
    assert matching._match_locked(database, request, 1) == 'matched'
    assert create.call_args.args[2].organization_id == 2
    assert database.execute.call_count == 1
    assert 'GROUP BY r.organization_id' in str(database.execute.call_args.args[0])


@pytest.mark.parametrize('action', ['accept', 'reject'])
def test_pending_organization_cannot_respond_through_business_service(action):
    from app.services.referrals import AcceptanceError, RejectionError, accept_referral, reject_referral
    database = MagicMock()
    values = [1, SimpleNamespace(status='matched'), SimpleNamespace(organization_id=1), 1, 'pending']
    results = []
    for value in values:
        result = Mock()
        result.scalar_one_or_none.return_value = value
        results.append(result)
    database.execute.side_effect = results
    with pytest.raises((AcceptanceError, RejectionError)) as caught:
        if action == 'accept':
            accept_referral(database, 1, 1)
        else:
            reject_referral(database, 1, 1, 'Cannot provide this service')
    assert caught.value.status == 403
    database.add.assert_not_called()


@pytest.mark.parametrize('outcome,expected', [('success', 'ack'), ('malformed', 'reject'), ('failure', 'nack')])
def test_consumer_acknowledges_only_successful_processing(monkeypatch, outcome, expected):
    import json
    from app.messaging import event_consumer
    channel = Mock()
    connection = Mock(is_open=True)
    connection.channel.return_value = channel
    monkeypatch.setattr(event_consumer, 'get_rabbitmq_connection', lambda: connection)
    event_consumer.consume_events('matching_queue', Mock(side_effect=RuntimeError() if outcome == 'failure' else None))
    callback = channel.basic_consume.call_args.kwargs['on_message_callback']
    body = b'not-json' if outcome == 'malformed' else json.dumps({
        'event_id': 'synthetic', 'event_type': 'ServiceRequestCreated', 'event_version': 1,
        'timestamp': datetime.now().isoformat(), 'request_id': 1, 'payload': {},
    }).encode()
    if outcome == 'failure':
        with pytest.raises(RuntimeError):
            callback(channel, SimpleNamespace(delivery_tag=1), None, body)
    else:
        callback(channel, SimpleNamespace(delivery_tag=1), None, body)
    assert getattr(channel, 'basic_' + expected).call_count == 1
    if expected == 'nack':
        assert channel.basic_nack.call_args.kwargs['requeue'] is True
    if expected == 'reject':
        assert channel.basic_reject.call_args.kwargs['requeue'] is False
