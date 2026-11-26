"""Actual MySQL 8 / RabbitMQ tests. Run ONLY via run_isolated_integration.py.

All identities, queues, processes and records here belong to disposable Docker
containers. Firebase itself is never mutated. No SQLite SQL substitutions.
"""
from contextlib import contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.getenv('CC_ISOLATED_INTEGRATION') != '1',
                                reason='Requires disposable Docker services; use tools/run_isolated_integration.py')


@pytest.fixture(scope='module')
def database():
    container = os.environ['CC_TEST_MYSQL_CONTAINER']
    # Fail closed: do not accept an arbitrary database URL or existing container.
    metadata = json.loads(subprocess.check_output(['docker', 'inspect', container], text=True))[0]
    assert metadata['Name'].startswith('/careconnect-test-')
    assert metadata['Config']['Labels'].get('careconnect.test')

    def mysql(sql):
        result = subprocess.run(['docker', 'exec', '-i', container, 'sh', '-c',
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4'],
            input=sql, text=True, capture_output=True)
        assert result.returncode == 0, 'Disposable schema initialization: ' + result.stderr

    # The destructive baseline/seed are used exclusively inside OUR container.
    mysql((ROOT / 'database/schema.sql').read_text(encoding='utf-8'))
    mysql((ROOT / 'database/seed.sql').read_text(encoding='utf-8'))
    mysql((ROOT / 'database/migrations/001_checkin_workflow.sql').read_text(encoding='utf-8'))
    engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
    # Current baseline already includes 002. Prove the legacy upgrade separately.
    old = subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(),
                                   'show', 'abad5c82c1b33441ec37ec672d629a34a5f82047:database/schema.sql'],
                                  text=True, cwd=ROOT)
    old = old.replace('careconnect_db', 'cc_legacy_migration')
    mysql(old)
    mysql('USE cc_legacy_migration;\n' +
          (ROOT / 'database/migrations/002_firebase_authentication.sql').read_text(encoding='utf-8'))
    # Verify the alternative non-destructive baseline in its own fresh database.
    mysql('CREATE DATABASE cc_safe_schema;\n' +
          (ROOT / 'database/schema_safe.sql').read_text(encoding='utf-8').replace('USE careconnect_db;', 'USE cc_safe_schema;'))
    yield engine
    engine.dispose()


def scalar(database, sql, **params):
    with database.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def write(database, sql, **params):
    with database.begin() as connection:
        return connection.execute(text(sql), params).lastrowid


def call(database, function, *args, **kwargs):
    with Session(database) as session:
        return function(session, *args, **kwargs)


def wait_for(predicate, description):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.1)
    pytest.fail('Timed out waiting for ' + description)


@pytest.fixture(scope='module')
def network(database, tmp_path_factory):
    from app.messaging.rabbitmq_config import setup_rabbitmq
    setup_rabbitmq()
    logs = tmp_path_factory.mktemp('careconnect-workers')
    children, handles = [], []
    files = ['worker.py', 'notification_worker.py', 'sla_worker.py',
             'coordinator_worker.py', 'feedback_worker.py', 'outbox_dispatcher.py']
    try:
        for file in files:
            handle = (logs / (file + '.log')).open('w', encoding='utf-8')
            handles.append(handle)
            process = subprocess.Popen([sys.executable, file], cwd=ROOT, stdout=handle,
                                       stderr=subprocess.STDOUT, env=os.environ.copy(),
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            children.append(process)
        from app.messaging.rabbitmq_connection import get_rabbitmq_connection
        from app.messaging.rabbitmq_config import QUEUE_BINDINGS
        def consumers_ready():
            connection = get_rabbitmq_connection()
            try:
                return all(connection.channel().queue_declare(queue=name, passive=True).method.consumer_count == 1
                           for name in QUEUE_BINDINGS)
            finally:
                connection.close()
        wait_for(consumers_ready, 'one real consumer on each isolated queue')
        assert all(child.poll() is None for child in children)
        yield children
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        for handle in handles:
            handle.close()


@pytest.fixture(scope='module')
def scenario(database, network):
    # A separate service and fresh members/partners avoid dependencies on seed
    # capacity/history and allow repeatable matching assertions.
    category = write(database, "INSERT INTO service_categories(name) VALUES('Integration category')")
    service = write(database, "INSERT INTO services(category_id,name) VALUES(:c,'Integration support')", c=category)
    area = write(database, "INSERT INTO service_areas(city,region_name) VALUES('Calgary','Integration area')")
    member = write(database, "INSERT INTO users(role_id,email,firebase_uid) SELECT role_id,'synthetic-member@example.invalid','test-member' FROM roles WHERE role_name='member'")
    write(database, "INSERT INTO member_profiles(user_id,first_name,last_name,phone,address,city) VALUES(:id,'Synthetic','Member','4035550100','Test address','Calgary')", id=member)
    coordinator = write(database, "INSERT INTO users(role_id,email,firebase_uid) SELECT role_id,'synthetic-coordinator@example.invalid','test-coordinator' FROM roles WHERE role_name='coordinator'")
    partners = []
    for index in range(3):
        org = write(database, "INSERT INTO organizations(name,contact_email,contact_phone,status) VALUES(:name,'synthetic@example.invalid','4035550100','approved')", name='Integration partner ' + str(index))
        user = write(database, "INSERT INTO users(role_id,email,firebase_uid) SELECT role_id,:email,:uid FROM roles WHERE role_name='representative'", email=f'synthetic-partner-{index}@example.invalid', uid=f'test-partner-{index}')
        write(database, "INSERT INTO organization_representatives(user_id,organization_id,full_name,is_primary_contact) VALUES(:u,:o,'Synthetic representative',TRUE)", u=user, o=org)
        offering = write(database, "INSERT INTO organization_services(organization_id,service_id,service_area_id,active_referral_limit) VALUES(:o,:s,:a,100)", o=org, s=service, a=area)
        write(database, "INSERT INTO service_priority_support(organization_service_id,priority_id) SELECT :o,priority_id FROM priority_levels", o=offering)
        partners.append((org, user, offering))
    return dict(service=service, area=area, member=member, coordinator=coordinator, partners=partners)


def make_request(database, scenario):
    from app.services.guest_requests import create_guest_request
    request, owner = call(database, create_guest_request, {
        'contact_name': 'Synthetic Member', 'contact_email': 'synthetic-member@example.invalid',
        'contact_phone': '4035550100', 'contact_address': 'Test address', 'contact_city': 'Calgary',
        'details': 'Synthetic integration assistance', 'service_id': scenario['service'],
        'delivery_method': 'In person', 'priority': 'Low'}, scenario['member'], 'integration:' + uuid.uuid4().hex)
    assert owner == scenario['member']
    return request


def latest(database, request):
    with database.connect() as connection:
        row = connection.execute(text('SELECT referral_id,organization_id,attempt_number,status FROM referrals WHERE request_id=:r ORDER BY attempt_number DESC LIMIT 1'), {'r': request}).mappings().one_or_none()
        return dict(row) if row else None


def representative(scenario, referral):
    return next(user for org, user, _ in scenario['partners'] if org == referral['organization_id'])


def test_fresh_schema_migrations_constraints_and_academic_queries(database):
    from deploy.check_schema import verify
    from tools.audit_sql_inventory import split_sql
    verify(database)
    assert scalar(database, 'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()') == 21
    assert scalar(database, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='cc_legacy_migration' AND table_name='users' AND column_name='firebase_uid'") == 1
    assert scalar(database, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='cc_safe_schema'") == 20
    assert scalar(database, '''SELECT COUNT(*) FROM organization_services os LEFT JOIN
        (SELECT r.organization_id,s.service_id,s.service_area_id,COUNT(*) n FROM referrals r
         JOIN service_requests s USING(request_id) WHERE r.status IN ('sent','accepted','attended')
         GROUP BY r.organization_id,s.service_id,s.service_area_id) actual
        ON actual.organization_id=os.organization_id AND actual.service_id=os.service_id
        AND actual.service_area_id=os.service_area_id
        WHERE os.current_active_referrals<>COALESCE(actual.n,0)''') == 0
    queries = [sql for sql, _ in split_sql((ROOT / 'database/queries.sql').read_text(encoding='utf-8')) if sql.startswith('SELECT')]
    assert len(queries) == 10
    with database.connect() as connection:
        for sql in queries:
            connection.execute(text(sql)).all()
    with pytest.raises(IntegrityError):
        write(database, 'INSERT INTO users(role_id,email) VALUES(999999,\'bad-fk@example.invalid\')')
    with pytest.raises(OperationalError) as caught:
        write(database, 'UPDATE organization_services SET current_active_referrals=-1 LIMIT 1')
    assert caught.value.orig.args[0] == 3819  # MySQL CHECK violation, not connection failure.


def test_real_request_notification_attendance_completion_feedback_and_replay(database, scenario):
    from app.services.referrals import accept_referral, AcceptanceError
    from app.services.attendance import record_attendance
    from app.services.completions import complete_referral
    from app.services.feedback import submit_feedback, FeedbackError
    from app.messaging.event_publisher import publish_event
    request = make_request(database, scenario)
    referral = wait_for(lambda: latest(database, request), 'automatic matching')
    wait_for(lambda: scalar(database, "SELECT COUNT(*) FROM notifications WHERE related_request_id=:r AND deduplication_key LIKE 'referral-created:%'", r=request), 'real ReferralCreated notification')
    user = representative(scenario, referral)
    with pytest.raises(AcceptanceError) as caught:
        call(database, accept_referral, referral['referral_id'], scenario['member'])
    assert caught.value.status == 404
    assert not call(database, accept_referral, referral['referral_id'], user)['already_processed']
    assert call(database, accept_referral, referral['referral_id'], user)['already_processed']
    call(database, record_attendance, referral['referral_id'], user)
    call(database, record_attendance, referral['referral_id'], user)
    assert scalar(database, 'SELECT COUNT(*) FROM attendance_records WHERE request_id=:r', r=request) == 1
    call(database, complete_referral, referral['referral_id'], user)
    assert call(database, complete_referral, referral['referral_id'], user)['already_processed']
    with pytest.raises(FeedbackError) as caught:
        call(database, submit_feedback, request, user, False)
    assert caught.value.status == 404
    call(database, submit_feedback, request, scenario['member'], False, 'Synthetic follow-up')
    assert call(database, submit_feedback, request, scenario['member'], False, 'Synthetic follow-up')['already_processed']
    wait_for(lambda: scalar(database, "SELECT COUNT(*) FROM notifications WHERE related_request_id=:r AND deduplication_key LIKE 'feedback-negative:%'", r=request), 'negative-feedback coordinator notification')
    with database.connect() as connection:
        before = connection.execute(text('SELECT COUNT(*) FROM notifications WHERE related_request_id=:r'), {'r': request}).scalar_one()
        events = connection.execute(text('SELECT event_type,payload,event_id FROM event_outbox WHERE request_id=:r'), {'r': request}).mappings().all()
    for event in events:
        payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
        publish_event(event['event_type'], request, payload, event_id=event['event_id'])
    time.sleep(2)
    assert scalar(database, 'SELECT COUNT(*) FROM referrals WHERE request_id=:r', r=request) == 1
    assert scalar(database, 'SELECT COUNT(*) FROM notifications WHERE related_request_id=:r', r=request) == before
    assert scalar(database, 'SELECT current_active_referrals FROM organization_services WHERE organization_id=:o AND service_id=:s', o=referral['organization_id'], s=scenario['service']) == 0


def test_rejection_timeout_three_attempts_and_escalation(database, scenario):
    from app.services.referrals import reject_referral
    from app.services.timeouts import expire_referral
    from app.services.outbox import utcnow
    request = make_request(database, scenario)
    first = wait_for(lambda: latest(database, request), 'first matching')
    call(database, reject_referral, first['referral_id'], representative(scenario, first), 'Synthetic rejection')
    second = wait_for(lambda: (row if (row := latest(database, request)) and row['attempt_number'] == 2 else None), 'backup after rejection')
    write(database, 'UPDATE referrals SET response_deadline=:past WHERE referral_id=:id', past=utcnow()-timedelta(seconds=5), id=second['referral_id'])
    assert call(database, expire_referral, second['referral_id']) is True
    assert call(database, expire_referral, second['referral_id']) is False
    third = wait_for(lambda: (row if (row := latest(database, request)) and row['attempt_number'] == 3 else None), 'backup after timeout')
    call(database, reject_referral, third['referral_id'], representative(scenario, third), 'Synthetic rejection')
    wait_for(lambda: scalar(database, 'SELECT status FROM service_requests WHERE request_id=:r', r=request) == 'unmatched', 'exhausted-attempt escalation')
    assert len({first['organization_id'], second['organization_id'], third['organization_id']}) == 3
    assert scalar(database, "SELECT COUNT(*) FROM notifications WHERE related_request_id=:r AND deduplication_key LIKE 'unmatched:%'", r=request) >= 1


def test_no_capacity_manual_rescue_overdue_and_late_attendance(database, scenario):
    from app.services.manual_assignment import assign_request
    from app.services.referrals import accept_referral
    from app.services.attendance import record_attendance
    from app.services.overdue import mark_overdue
    from app.services.outbox import utcnow
    request = make_request(database, scenario)
    # Lock the outbox and pause only our offerings before the dispatcher can match.
    # If matching already won, make a fresh request with capacity paused instead.
    write(database, "UPDATE organization_services SET status='paused' WHERE service_id=:s", s=scenario['service'])
    if latest(database, request):
        from app.services.referrals import reject_referral
        row = latest(database, request)
        call(database, reject_referral, row['referral_id'], representative(scenario, row), 'Pause for isolated test')
    wait_for(lambda: scalar(database, 'SELECT status FROM service_requests WHERE request_id=:r', r=request) == 'unmatched', 'no-capacity coordinator escalation')
    write(database, "UPDATE organization_services SET status='active' WHERE service_id=:s", s=scenario['service'])
    prior = latest(database, request)
    chosen = next(org for org, _, _ in scenario['partners'] if not prior or org != prior['organization_id'])
    assigned = call(database, assign_request, request, chosen, scenario['coordinator'], prior['referral_id'] if prior else 0)
    referral = latest(database, request)
    assert assigned['referral_id'] == referral['referral_id']
    user = representative(scenario, referral)
    call(database, accept_referral, referral['referral_id'], user)
    write(database, 'UPDATE service_requests SET attendance_deadline=:past WHERE request_id=:r', past=utcnow()-timedelta(seconds=10), r=request)
    call(database, mark_overdue, request)
    call(database, mark_overdue, request)
    wait_for(lambda: scalar(database, "SELECT COUNT(*) FROM notifications WHERE related_request_id=:r AND deduplication_key LIKE 'attendance-overdue:%'", r=request), 'AttendanceOverdue coordinator notification')
    call(database, record_attendance, referral['referral_id'], user)
    wait_for(lambda: scalar(database, "SELECT COUNT(*) FROM notifications WHERE related_request_id=:r AND deduplication_key LIKE 'attendance-late:%'", r=request), 'late RequestAttended notification')


def test_verified_registration_approval_and_offering_management(database, scenario):
    from app.services.member_registration import register_member
    from app.services.organization_registration import register_organization, RegistrationError
    from app.services.organization_approvals import decide_application
    from app.services.offerings import add_offering, update_offering, OfferingError
    profile = dict(first_name='Synthetic', last_name='Registrant', phone='4035550101', address='Test', city='Calgary')
    assert not call(database, register_member, 'test-new-member', 'new-member@example.invalid', profile)['already_processed']
    assert call(database, register_member, 'test-new-member', 'new-member@example.invalid', profile)['already_processed']
    fields = dict(org_name='Synthetic applicant', address='Test', service_area='Calgary', city='Calgary', contact_name='Synthetic Applicant', phone='4035550101')
    application = call(database, register_organization, 'test-new-rep', 'new-rep@example.invalid', fields)
    assert call(database, register_organization, 'test-new-rep', 'new-rep@example.invalid', fields)['already_processed']
    user = scalar(database, "SELECT user_id FROM users WHERE firebase_uid='test-new-rep'")
    org = scalar(database, "SELECT organization_id FROM organization_representatives WHERE user_id=:u", u=user)
    app_id = scalar(database, 'SELECT application_id FROM organization_applications WHERE organization_id=:o', o=org)
    with pytest.raises(OfferingError) as caught:
        call(database, add_offering, user, service_id=scenario['service'], area_id=scenario['area'], status='active', referral_limit=10)
    assert caught.value.status == 403
    call(database, decide_application, org, app_id, scenario['coordinator'], 'approve')
    assert call(database, decide_application, org, app_id, scenario['coordinator'], 'approve')['already_processed']
    offering = call(database, add_offering, user, service_id=scenario['service'], area_id=scenario['area'], status='active', referral_limit=10)
    call(database, update_offering, offering['organization_service_id'], user, status='paused', expected_status='active', availability_version=0)
    assert scalar(database, 'SELECT status FROM organization_services WHERE organization_service_id=:o', o=offering['organization_service_id']) == 'paused'
    assert scalar(database, 'SELECT COUNT(*) FROM organization_availability WHERE organization_service_id=:o', o=offering['organization_service_id']) == 1
    with pytest.raises(RegistrationError):
        call(database, register_organization, 'test-new-member', 'new-member@example.invalid', fields)


def test_routes_roles_csrf_ownership_and_xss_on_real_mysql(database, scenario, monkeypatch):
    from app import create_app
    app = create_app({'TESTING': True})
    claims = {'member': {'uid': 'test-member', 'email': 'synthetic-member@example.invalid', 'email_verified': True},
              'organization': {'uid': 'test-partner-0', 'email': 'synthetic-partner-0@example.invalid', 'email_verified': True},
              'coordinator': {'uid': 'test-coordinator', 'email': 'synthetic-coordinator@example.invalid', 'email_verified': True}}
    # Only identity-provider signatures are faked; real MySQL resolves roles,
    # ownership, lists, joins and object detail data.
    for module in ('app.member', 'app.organization', 'app.coordinator'):
        monkeypatch.setattr(module + '.cookie_claims', lambda cookie: claims[cookie])
    anonymous = app.test_client()
    for path in ('/member', '/organization', '/coordinator'):
        assert anonymous.get(path).status_code == 302
    paths = {'member': ['/member', '/member/requests', '/member/profile'],
             'organization': ['/organization', '/organization/requests', '/organization/services', '/organization/profile'],
             'coordinator': ['/coordinator', '/coordinator/requests', '/coordinator/organizations', '/coordinator/approvals', '/coordinator/reports']}
    for role, pages in paths.items():
        client = app.test_client()
        client.set_cookie('careconnect_' + role, role)
        for path in pages:
            assert client.get(path).status_code == 200, path
        if role != 'coordinator':
            assert client.get('/coordinator/requests').status_code == 302
    member = app.test_client()
    member.set_cookie('careconnect_member', 'member')
    # Seed request 1 belongs to another member; no existence disclosure.
    assert member.get('/member/requests/1').status_code == 404
    assert member.post('/member/profile', data={'first_name': 'Injected'}).status_code == 403
    attacker = '<script>window.injected=true</script>'
    response = anonymous.get('/services', query_string={'search': attacker})
    assert response.status_code == 200
    assert attacker.encode() not in response.data
    assert anonymous.get('/services', query_string={'sort': 'DROP TABLE users'}).status_code == 400
    for role in ('member', 'organization'):
        claims[role]['email_verified'] = False
        client = app.test_client()
        client.set_cookie('careconnect_' + role, role)
        assert client.get(paths[role][0]).status_code == 302


def test_profile_updates_rejected_application_and_owned_cancellation(database, scenario):
    from app.services.member_profiles import update_profile
    from app.services.organization_profiles import update_organization_profile, OrganizationProfileError
    from app.services.organization_registration import register_organization
    from app.services.organization_approvals import decide_application
    from app.services.cancellations import cancel_request, CancellationError
    data = dict(full_name='Synthetic Member', phone='4035550100', address='Test address', city='Calgary')
    call(database, update_profile, scenario['member'], dict(data, address='Updated test address'))
    call(database, update_profile, scenario['member'], data)
    org, user, _ = scenario['partners'][0]
    contact = dict(contact_name='Updated Synthetic Representative', phone='4035550100', address='Updated test address', city='Calgary')
    call(database, update_organization_profile, user, org, contact)
    other_org = scenario['partners'][1][0]
    before = scalar(database, 'SELECT address FROM organizations WHERE organization_id=:o', o=other_org)
    with pytest.raises(OrganizationProfileError) as caught:
        call(database, update_organization_profile, user, other_org, contact)
    assert caught.value.status == 403
    assert scalar(database, 'SELECT address FROM organizations WHERE organization_id=:o', o=other_org) == before
    fields = dict(org_name='Rejected synthetic applicant', address='Test', service_area='Calgary', city='Calgary', contact_name='Applicant', phone='4035550100')
    call(database, register_organization, 'test-rejected', 'rejected@example.invalid', fields)
    rejected = scalar(database, "SELECT organization_id FROM organizations WHERE name='Rejected synthetic applicant'")
    application = scalar(database, 'SELECT application_id FROM organization_applications WHERE organization_id=:o', o=rejected)
    call(database, decide_application, rejected, application, scenario['coordinator'], 'reject', 'Synthetic decision')
    assert scalar(database, 'SELECT status FROM organization_applications WHERE application_id=:a', a=application) == 'rejected'
    assert scalar(database, 'SELECT status FROM organizations WHERE organization_id=:o', o=rejected) == 'pending'
    request = write(database, '''INSERT INTO service_requests(member_id,service_id,service_area_id,priority_id,title,description,status,attendance_deadline)
        VALUES(:m,:s,:a,3,'Synthetic cancellation','Synthetic cancellation','unmatched',DATE_ADD(UTC_TIMESTAMP(),INTERVAL 1 DAY))''', m=scenario['member'],s=scenario['service'],a=scenario['area'])
    with pytest.raises(CancellationError) as caught:
        call(database, cancel_request, request, user)
    assert caught.value.status == 404
    call(database, cancel_request, request, scenario['member'])
    assert call(database, cancel_request, request, scenario['member'])['already_processed']
    assert scalar(database, 'SELECT status FROM service_requests WHERE request_id=:r', r=request) == 'cancelled'


def test_positive_feedback_notifies_partner_without_negative_alert(database, scenario):
    from app.services.referrals import accept_referral
    from app.services.attendance import record_attendance
    from app.services.completions import complete_referral
    from app.services.feedback import submit_feedback
    request = make_request(database, scenario)
    referral = wait_for(lambda: latest(database, request), 'positive feedback matching')
    user = representative(scenario, referral)
    call(database, accept_referral, referral['referral_id'], user)
    call(database, record_attendance, referral['referral_id'], user)
    call(database, complete_referral, referral['referral_id'], user)
    call(database, submit_feedback, request, scenario['member'], True)
    wait_for(lambda: scalar(database, "SELECT COUNT(*) FROM notifications WHERE related_request_id=:r AND deduplication_key LIKE 'feedback-submitted:%'", r=request), 'positive-feedback partner notification')
    assert scalar(database, "SELECT COUNT(*) FROM notifications WHERE related_request_id=:r AND deduplication_key LIKE 'feedback-negative:%'", r=request) == 0


def test_concurrent_matching_does_not_overbook_mysql_capacity(database, scenario):
    from concurrent.futures import ThreadPoolExecutor
    from app.services.matching import handle_request_created
    service = write(database, "INSERT INTO services(category_id,name) SELECT category_id,'Concurrent synthetic support' FROM services WHERE service_id=:s", s=scenario['service'])
    org, _, _ = scenario['partners'][0]
    offering = write(database, 'INSERT INTO organization_services(organization_id,service_id,service_area_id,active_referral_limit) VALUES(:o,:s,:a,1)', o=org,s=service,a=scenario['area'])
    write(database, 'INSERT INTO service_priority_support(organization_service_id,priority_id) VALUES(:o,3)', o=offering)
    requests = [write(database, '''INSERT INTO service_requests(member_id,service_id,service_area_id,priority_id,title,description,attendance_deadline)
        VALUES(:m,:s,:a,3,'Concurrent test','Concurrent test',DATE_ADD(UTC_TIMESTAMP(),INTERVAL 1 DAY))''',m=scenario['member'],s=service,a=scenario['area']) for _ in range(2)]
    def match(request):
        for attempt in range(3):
            try:
                return call(database, handle_request_created, {'request_id':request})
            except OperationalError as error:
                # Match the consumer's transaction retry after a MySQL deadlock.
                if error.orig.args[0] not in (1213,1205) or attempt == 2:
                    raise
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(match, requests))
    assert sorted(results) == ['matched','unmatched']
    assert scalar(database, 'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=:o', o=offering) == 1
    assert scalar(database, 'SELECT COUNT(*) FROM referrals WHERE request_id IN (:a,:b)', a=requests[0],b=requests[1]) == 1
    chosen = next(request for request in requests if latest(database,request))
    with pytest.raises(IntegrityError) as caught:
        write(database, '''INSERT INTO referrals(request_id,organization_id,attempt_number,status,response_deadline)
            VALUES(:r,:o,2,'sent',DATE_ADD(UTC_TIMESTAMP(),INTERVAL 1 HOUR))''',r=chosen,o=org)
    assert caught.value.orig.args[0] == 1062


def test_outbox_failure_rolls_back_and_retry_keeps_event_id(database, scenario, network, monkeypatch):
    from app.services import guest_requests, outbox
    from unittest.mock import Mock
    before = scalar(database, 'SELECT COUNT(*) FROM service_requests')
    monkeypatch.setattr(guest_requests, 'enqueue', Mock(side_effect=RuntimeError('Synthetic rollback test')))
    with pytest.raises(RuntimeError):
        make_request(database, scenario)
    assert scalar(database, 'SELECT COUNT(*) FROM service_requests') == before
    monkeypatch.undo()
    # Hold the specific row in a transaction. The real dispatcher cannot consume
    # it concurrently; force the publisher failure through the production function.
    from app.services.outbox import enqueue, utcnow
    wait_for(lambda: scalar(database, 'SELECT COUNT(*) FROM event_outbox WHERE published_at IS NULL') == 0, 'outbox drained before failure test')
    network[-1].terminate()
    network[-1].wait(timeout=5)
    request = scalar(database, 'SELECT MIN(request_id) FROM service_requests')
    with Session(database) as session, session.begin():
        event = enqueue(session, 'ServiceRequestCreated', request, {}, 'integration:retry')
        event.available_at = utcnow()
        session.flush()
        event_id = event.event_id
    original = outbox.publish_event
    publisher = Mock(side_effect=TimeoutError('Synthetic broker outage'))
    monkeypatch.setattr(outbox, 'publish_event', publisher)
    assert call(database, outbox.dispatch_one)
    with database.connect() as connection:
        row = connection.execute(text('SELECT event_id,attempts,published_at,available_at FROM event_outbox WHERE event_id=:e'), {'e': event_id}).mappings().one()
    assert row['event_id'] == event_id and row['attempts'] == 1 and row['published_at'] is None
    assert row['available_at'] > utcnow()
    write(database, 'UPDATE event_outbox SET available_at=:now WHERE event_id=:e', now=utcnow(), e=event_id)
    monkeypatch.setattr(outbox, 'publish_event', original)
    assert call(database, outbox.dispatch_one)
    assert scalar(database, 'SELECT published_at IS NOT NULL FROM event_outbox WHERE event_id=:e', e=event_id)


def test_supervisor_start_health_duplicate_and_owned_stop(database, scenario, network, tmp_path):
    import socket
    for child in network:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    def runtime(action):
        return subprocess.run([sys.executable, 'tools/local_runtime.py', action,
            '--port', str(port), '--state-dir', str(tmp_path), '--process-pending'],
            cwd=ROOT, capture_output=True, text=True, timeout=55)
    try:
        started = runtime('start')
        if started.returncode:
            pytest.fail('Supervisor failed: ' + (tmp_path / 'supervisor.log').read_text(encoding='utf-8'))
        again = runtime('start')
        assert again.returncode == 0 and 'Already running' in again.stdout
        assert runtime('health').returncode == 0
        assert runtime('stop').returncode == 0
        assert unrelated.poll() is None
        assert not (tmp_path / 'runtime.json').exists()
    finally:
        if (tmp_path / 'runtime.json').exists():
            runtime('stop')
        unrelated.terminate()
        unrelated.wait(timeout=5)


def test_fresh_demo_and_referral_normalization(database):
    from tools.audit_sql_inventory import split_sql
    from app.models import Referral
    from deploy.check_schema import verify
    from sqlalchemy import select

    # Independent fresh schema on the runner-owned container, free of other
    # integration fixtures and workers. Keep the commit in this test only.
    container = os.environ['CC_TEST_MYSQL_CONTAINER']
    def run_sql(source, expected_error=None):
        result = subprocess.run(['docker', 'exec', '-i', container, 'sh', '-c',
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4'],
            input=source, text=True, capture_output=True)
        if expected_error:
            assert result.returncode != 0 and expected_error in result.stderr, result.stderr
        else:
            assert result.returncode == 0, result.stderr

    for relative in ('schema.sql', 'seed.sql', 'migrations/001_checkin_workflow.sql'):
        run_sql((ROOT / 'database' / relative).read_text(encoding='utf-8').replace(
            'careconnect_db', 'cc_demo_rehearsal'))
    demo = create_engine(database.url.set(database='cc_demo_rehearsal'))
    try:
        with demo.begin() as connection:
            for sql in (
                """INSERT INTO users(user_id,role_id,email) VALUES
                    (15,1,'demo-member@example.invalid'),(16,2,'demo-rep@example.invalid'),
                    (17,3,'demo-coordinator@example.invalid')""",
                """INSERT INTO member_profiles(user_id,first_name,last_name,phone)
                    VALUES(15,'Demo','Member','4035550101')""",
                """INSERT INTO organizations(organization_id,name,contact_email,contact_phone,status)
                    VALUES(7,'Demo partner','partner@example.invalid','4035550102','approved')""",
                """INSERT INTO organization_representatives(user_id,organization_id,full_name,is_primary_contact)
                    VALUES(16,7,'Demo representative',TRUE)""",
                "UPDATE organizations SET status='approved' WHERE organization_id=5",
                """INSERT INTO organization_services(organization_id,service_id,service_area_id)
                    SELECT 7,service_id,1 FROM services WHERE service_id<>6""",
                """INSERT INTO organization_services(organization_id,service_id,service_area_id)
                    VALUES(5,6,1),(7,1,2),(7,1,3),(7,1,4),(7,1,5)""",
                """INSERT INTO service_priority_support(organization_service_id,priority_id)
                    SELECT organization_service_id,priority_id FROM organization_services
                    CROSS JOIN priority_levels WHERE organization_id IN (5,7)""",
            ):
                connection.execute(text(sql))
        run_sql('USE cc_demo_rehearsal;\n' +
                (ROOT / 'database/demo_data.sql').read_text(encoding='utf-8') + '\nCOMMIT;')
        assert scalar(demo, 'SELECT COUNT(*) FROM users') == 17
        assert scalar(demo, 'SELECT COUNT(*) FROM users WHERE role_id=3') == 4
        assert scalar(demo, 'SELECT COUNT(*) FROM organizations') == 7
        assert scalar(demo, 'SELECT COUNT(*) FROM organization_services') == 25
        assert scalar(demo, 'SELECT COUNT(*) FROM service_requests') == 40
        assert scalar(demo, 'SELECT COUNT(*) FROM referrals') == 29
        verify(demo)
        assert scalar(demo, """SELECT COUNT(*) FROM organization_services os
            WHERE os.current_active_referrals <> (
                SELECT COUNT(*) FROM referrals r JOIN service_requests sr USING(request_id)
                WHERE r.organization_id=os.organization_id AND sr.service_id=os.service_id
                AND sr.service_area_id=os.service_area_id
                AND r.status IN ('sent','accepted','attended'))""") == 0
        baseline = 'abad5c82c1b33441ec37ec672d629a34a5f82047'
        original = subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(),
            'show', baseline + ':database/queries.sql'], cwd=ROOT).decode('utf-8')
        updated = (ROOT / 'database/queries.sql').read_text(encoding='utf-8')
        original_queries = [sql for sql, _ in split_sql(original) if sql.startswith('SELECT')]
        updated_queries = [sql for sql, _ in split_sql(updated) if sql.startswith('SELECT')]
        assert len(original_queries) == len(updated_queries) == 10
        tables = ('referrals', 'referral_status_history', 'attendance_records',
                  'service_completions', 'feedback', 'users', 'organizations',
                  'organization_services', 'service_requests')
        def snapshot():
            with demo.connect() as connection:
                return {table: connection.execute(text(f'SELECT * FROM {table} ORDER BY 1')).all()
                        for table in tables}
        before = snapshot()

        # Recreate the exact legacy flag and index on disposable data.
        write(demo, 'ALTER TABLE referrals ADD is_backup BOOLEAN NOT NULL DEFAULT FALSE, ADD INDEX idx_ref_is_backup (is_backup)')
        write(demo, 'UPDATE referrals SET is_backup=(attempt_number>1),updated_at=updated_at')
        with pytest.raises(RuntimeError, match='Legacy referral flag'):
            verify(demo)
        with demo.connect() as connection:
            legacy_results = [connection.execute(text(sql)).all() for sql in original_queries]
        migration = 'USE cc_demo_rehearsal;\n' + (ROOT / 'database/migrations/003_derive_referral_backup.sql').read_text(encoding='utf-8')
        write(demo, 'UPDATE referrals SET is_backup=TRUE,updated_at=updated_at WHERE referral_id=1')
        run_sql(migration, 'Referral flag or attempt history mismatch')
        assert scalar(demo, 'SELECT is_backup FROM referrals WHERE referral_id=1') == 1
        run_sql('USE cc_demo_rehearsal; DROP PROCEDURE careconnect_migrate_003;')
        write(demo, 'UPDATE referrals SET is_backup=FALSE,updated_at=updated_at WHERE referral_id=1')
        run_sql(migration)
        verify(demo)
        assert snapshot() == before
        with demo.connect() as connection:
            assert [connection.execute(text(sql)).all() for sql in updated_queries] == legacy_results
        with Session(demo) as session:
            backups = session.scalars(select(Referral).where(Referral.is_backup)).all()
            assert len(backups) == 3 and all(referral.is_backup for referral in backups)
            assert session.get(Referral, 1).is_backup is False
        run_sql(migration, 'Expected legacy referral schema missing')
    finally:
        demo.dispose()
