"""Real SQL list tests on synthetic SQLite data; never touch project services."""
import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app import create_app, db
from app.pagination import Pagination
from app.services.service_browsing import SERVICE_SORTS, public_services
from app.services.guest_requests import service_choices


@pytest.fixture
def listing_app(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'list-tests-only')
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('FIREBASE_PROJECT_ID', 'careconnect-bfb9e')
    monkeypatch.setenv('HOSTED_MODE', '0')
    app = create_app({'TESTING': True})
    claims = {
        'member': {'uid': 'member-1', 'email_verified': True},
        'organization': {'uid': 'representative-2', 'email_verified': True},
        'coordinator': {'uid': 'coordinator-3', 'email_verified': True},
        'pending': {'uid': 'representative-5', 'email_verified': True},
    }
    for module in ('app.member', 'app.organization', 'app.coordinator'):
        monkeypatch.setattr(module + '.cookie_claims', lambda cookie: claims[cookie])
    with app.app_context():
        @event.listens_for(db.engine, 'connect')
        def sqlite_mysql_functions(connection, record):
            # MySQL CONCAT is used by coordinator search; this is test-only.
            connection.create_function('CONCAT', -1, lambda *parts: ''.join('' if part is None else str(part) for part in parts))
        schema = [
            'CREATE TABLE roles(role_id INTEGER PRIMARY KEY,role_name TEXT)',
            'CREATE TABLE users(user_id INTEGER PRIMARY KEY,role_id INTEGER,email TEXT,firebase_uid TEXT,is_active BOOLEAN)',
            'CREATE TABLE member_profiles(user_id INTEGER PRIMARY KEY,first_name TEXT,last_name TEXT,phone TEXT,address TEXT,city TEXT)',
            'CREATE TABLE organizations(organization_id INTEGER PRIMARY KEY,name TEXT,status TEXT,contact_email TEXT,contact_phone TEXT,address TEXT,city TEXT,created_at DATETIME)',
            'CREATE TABLE organization_representatives(user_id INTEGER PRIMARY KEY,organization_id INTEGER,full_name TEXT,is_primary_contact BOOLEAN)',
            'CREATE TABLE organization_applications(application_id INTEGER PRIMARY KEY,organization_id INTEGER,submitted_by_user_id INTEGER,status TEXT,created_at DATETIME)',
            'CREATE TABLE service_categories(category_id INTEGER PRIMARY KEY,name TEXT,is_active BOOLEAN)',
            'CREATE TABLE services(service_id INTEGER PRIMARY KEY,name TEXT,description TEXT,category_id INTEGER,delivery_mode TEXT,is_active BOOLEAN)',
            'CREATE TABLE service_areas(area_id INTEGER PRIMARY KEY,region_name TEXT,city TEXT,is_active BOOLEAN)',
            'CREATE TABLE organization_services(organization_service_id INTEGER PRIMARY KEY,organization_id INTEGER,service_id INTEGER,service_area_id INTEGER,status TEXT,current_active_referrals INTEGER,active_referral_limit INTEGER)',
            'CREATE TABLE organization_availability(availability_id INTEGER PRIMARY KEY,organization_service_id INTEGER)',
            'CREATE TABLE priority_levels(priority_id INTEGER PRIMARY KEY,level_name TEXT,deadline_hours INTEGER)',
            'CREATE TABLE service_requests(request_id INTEGER PRIMARY KEY,member_id INTEGER,service_id INTEGER,priority_id INTEGER,status TEXT,created_at DATETIME,description TEXT,attendance_deadline DATETIME)',
            'CREATE TABLE referrals(referral_id INTEGER PRIMARY KEY,request_id INTEGER,organization_id INTEGER,status TEXT,attempt_number INTEGER,response_deadline DATETIME)',
            'CREATE TABLE referral_status_history(history_id INTEGER PRIMARY KEY,referral_id INTEGER,new_status TEXT,changed_at DATETIME)',
            'CREATE TABLE attendance_records(attendance_id INTEGER PRIMARY KEY,request_id INTEGER)',
            'CREATE TABLE feedback(feedback_id INTEGER PRIMARY KEY,request_id INTEGER,is_helpful BOOLEAN)',
            'CREATE TABLE notifications(notification_id INTEGER PRIMARY KEY,user_id INTEGER,message TEXT,created_at DATETIME,is_read BOOLEAN)',
        ]
        with db.engine.begin() as connection:
            for sql in schema:
                connection.execute(text(sql))
            connection.execute(text("INSERT INTO roles VALUES(1,'member'),(2,'representative'),(3,'coordinator')"))
            connection.execute(text("INSERT INTO users VALUES(1,1,'member@example.test','member-1',TRUE),(2,2,'rep@example.test','representative-2',TRUE),(3,3,'coord@example.test','coordinator-3',TRUE),(4,1,'other@example.test','other-4',TRUE),(5,2,'pending@example.test','representative-5',TRUE)"))
            connection.execute(text("INSERT INTO member_profiles VALUES(1,'Test','Member','4035550101','Test Street','Calgary'),(4,'Other','Member','4035550199','Other Street','Calgary')"))
            connection.execute(text("INSERT INTO organizations VALUES(1,'Partner One','approved','rep@example.test','4035550101','Test Street','Calgary','2026-01-01'),(2,'Partner Two','approved','two@example.test','4035550102','Second Street','Calgary','2026-01-01'),(3,'Pending Partner','pending','pending@example.test','4035550103','Third Street','Calgary','2026-01-01')"))
            connection.execute(text("INSERT INTO organization_representatives VALUES(2,1,'Test Representative',TRUE),(5,3,'Pending Representative',TRUE)"))
            connection.execute(text("INSERT INTO organization_applications VALUES(1,3,5,'submitted','2026-01-01')"))
            connection.execute(text("INSERT INTO service_categories VALUES(1,'Community',TRUE),(2,'Wellness',TRUE)"))
            connection.execute(text("INSERT INTO service_areas VALUES(1,'North','Calgary',TRUE),(2,'South','Edmonton',TRUE)"))
            connection.execute(text("INSERT INTO priority_levels VALUES(1,'High',6),(2,'Medium',12),(3,'Low',24)"))
            for number in range(1, 46):
                connection.execute(text("INSERT INTO services VALUES(:id,:name,'Community support',:category,'phone',TRUE)"), {'id': number, 'name': f'Service {number:02}', 'category': 1 if number % 2 else 2})
                connection.execute(text("INSERT INTO organization_services VALUES(:id,1,:id,1,'active',0,10)"), {'id': number})
            for number in range(1, 51):
                completed = number % 3 == 0
                connection.execute(text("INSERT INTO service_requests VALUES(:id,:owner,1,2,:status,'2026-01-01','Test request','2030-01-01')"),
                                   {'id': number, 'owner': 1 if number <= 45 else 4, 'status': 'completed' if completed else 'matched'})
                connection.execute(text("INSERT INTO referrals VALUES(:id,:id,:org,:status,1,'2030-01-01')"),
                                   {'id': number, 'org': 1 if number <= 45 else 2, 'status': 'completed' if completed else 'sent'})
        yield app
        db.session.remove()
        db.engine.dispose()


def signed_client(app, role):
    client = app.test_client()
    cookie = 'careconnect_organization' if role == 'pending' else 'careconnect_' + role
    client.set_cookie(cookie, role)
    return client


@pytest.mark.parametrize('query', ['page=0', 'page=-1', 'page=no', 'page=100001', 'page_size=1000', 'page_size=abc', 'sort=DROP+TABLE+users'])
def test_pagination_rejects_invalid_parameters(listing_app, query):
    assert listing_app.test_client().get('/services?' + query).status_code == 400


def test_public_sql_pages_sort_and_filter_complete_dataset(listing_app):
    with listing_app.test_request_context('/services?page=2&sort=name_desc&category=Community&delivery=Phone&search=Service'):
        pagination = Pagination.from_request(SERVICE_SORTS, 'name')
        with Session(db.engine) as database:
            records = public_services(database, pagination=pagination, category='Community', delivery='Phone', search='Service')
        assert [row['service_id'] for row in records] == [5, 3, 1]
        assert not pagination.has_next
        assert 'category=Community' in pagination.url(1) and 'sort=name_desc' in pagination.url(1)
        assert 'search=Service' in pagination.url(1)
    client = listing_app.test_client()
    first = client.get('/services')
    assert first.status_code == 200
    assert b'Service 20' in first.data and b'Service 21' not in first.data
    assert b'rel="next"' in first.data and b'rel="prev"' not in first.data
    last = client.get('/services?page=3')
    assert b'Service 41' in last.data and b'Service 45' in last.data and b'rel="next"' not in last.data
    assert b'No services found' in client.get('/services?search=does-not-exist').data
    assert b'No records on this page' in client.get('/services?page=999').data


def test_catalog_eligibility_has_one_query_and_preserves_one_area_rule(listing_app):
    with listing_app.app_context():
        with db.engine.begin() as connection:
            connection.execute(text("INSERT INTO organization_services VALUES(46,2,45,2,'active',0,10)"))
        queries = []
        event.listen(db.engine, 'before_cursor_execute', lambda *args: queries.append(args[2]))
        with Session(db.engine) as database:
            choices = service_choices(database)
        assert len(queries) == 1
        assert len(choices) == 44 and all(row['service_id'] != 45 for row in choices)


@pytest.mark.parametrize('role,path,marker', [
    ('member', '/member/requests', b'CC-45'),
    ('organization', '/organization/requests', b'CC-45'),
    ('coordinator', '/coordinator/requests', b'CC-50'),
    ('coordinator', '/coordinator/organizations', b'Partner One'),
    ('coordinator', '/coordinator/approvals', b'Pending Partner'),
    ('organization', '/organization/services', b'Service 01'),
])
def test_protected_list_templates_and_pagination(listing_app, role, path, marker):
    response = signed_client(listing_app, role).get(path)
    assert response.status_code == 200
    assert marker in response.data
    assert b'Records per page' in response.data and b'Page 1' in response.data


def test_owner_filters_and_status_apply_before_pagination(listing_app):
    member = signed_client(listing_app, 'member')
    response = member.get('/member/requests?status=Completed&sort=oldest&page_size=10&page=2')
    assert response.status_code == 200
    assert b'CC-33' in response.data and b'CC-45' in response.data
    assert b'CC-48' not in response.data and b'CC-3<' not in response.data
    org = signed_client(listing_app, 'organization')
    assert b'CC-50' not in org.get('/organization/requests').data
    assert org.get('/organization/requests/50').status_code == 404
    assert member.get('/member/requests/50').status_code == 404


@pytest.mark.parametrize('role,path', [('member', '/member'), ('organization', '/organization'), ('coordinator', '/coordinator')])
def test_dashboard_templates_have_global_counts_and_bounded_summaries(listing_app, role, path):
    response = signed_client(listing_app, role).get(path)
    assert response.status_code == 200
    if role == 'member':
        assert b'>30<' in response.data and b'>15<' in response.data


def test_coordinator_lists_do_not_query_all_history_or_assignment_choices(listing_app):
    statements = []
    with listing_app.app_context():
        event.listen(db.engine, 'before_cursor_execute', lambda *args: statements.append(args[2]))
        response = signed_client(listing_app, 'coordinator').get('/coordinator/requests')
        assert response.status_code == 200
        assert not any('referral_status_history' in sql for sql in statements)
        assert not any('service_priority_support' in sql for sql in statements)
        assert any('LIMIT ? OFFSET ?' in sql for sql in statements)
        detail = signed_client(listing_app, 'coordinator').get('/coordinator/requests/50')
        assert detail.status_code == 200 and b'Status history' in detail.data


def test_pending_organization_and_other_roles_cannot_bypass_access(listing_app):
    pending = signed_client(listing_app, 'pending')
    assert pending.get('/organization').status_code == 200
    assert pending.get('/organization/services').status_code == 302
    assert pending.post('/organization/services/add').status_code == 403
    assert pending.get('/organization/requests').status_code == 403
    assert signed_client(listing_app, 'member').get('/coordinator').status_code == 302
    assert signed_client(listing_app, 'organization').get('/member').status_code == 302


def test_reports_aggregate_entire_dataset(listing_app):
    response = signed_client(listing_app, 'coordinator').get('/coordinator/reports?page=2')
    assert response.status_code == 200
    assert b'>50<' in response.data and b'>16<' in response.data


def test_rejected_application_is_distinct_from_waiting_approval(listing_app):
    with listing_app.app_context(), db.engine.begin() as connection:
        connection.execute(text("UPDATE organization_applications SET status='rejected' WHERE application_id=1"))
    client = signed_client(listing_app, 'pending')
    response = client.get('/organization')
    assert response.status_code == 200
    assert b'Your application was rejected' in response.data
    assert b'Waiting for approval.' not in response.data
    assert client.get('/organization/requests').status_code == 403


def test_member_sees_organization_contact_after_acceptance(listing_app):
    with listing_app.app_context(), db.engine.begin() as connection:
        connection.execute(text("UPDATE referrals SET status='accepted' WHERE referral_id=1"))
    response = signed_client(listing_app, 'member').get('/member/requests/1')
    assert response.status_code == 200
    assert b'rep@example.test' in response.data
    assert b'Available after acceptance' not in response.data


def test_request_form_preserves_internal_time_frames_and_shows_notice(listing_app):
    response = listing_app.test_client().get('/get-connected')
    assert response.status_code == 200
    assert b'Preferred time frame' in response.data
    assert b'value="High"' in response.data and b'value="Medium"' in response.data and b'value="Low"' in response.data
    assert b'As soon as possible' in response.data and b'Soon' in response.data
    assert b'It is not an emergency response service.' in response.data


def test_pagination_never_forwards_url_control_arguments(listing_app):
    with listing_app.test_request_context('/services?search=food&_external=1&_scheme=javascript&_anchor=payload'):
        listing = Pagination.from_request(SERVICE_SORTS, 'name')
        target = listing.url(2)
        assert target.startswith('/services?')
        assert 'search=food' in target
        assert '_external' not in target and '_scheme' not in target and 'payload' not in target


def test_service_validation_error_preserves_second_page_and_edited_form(listing_app):
    import re
    client = signed_client(listing_app, 'organization')
    client.get('/organization/services?page=2&sort=name')
    with client.session_transaction() as session:
        csrf = session['organization_csrf']
    response = client.post('/organization/services?page=2&sort=name', data={
        'csrf_token': csrf, 'organization_service_id': '25', 'status': 'Paused',
        'max_referrals': 'invalid', 'expected_status': 'active', 'expected_limit': '10', 'availability_version': '0',
    })
    assert response.status_code == 400
    ids = re.findall(r'name="organization_service_id" value="([0-9]+)"', response.get_data(as_text=True))
    assert ids[0] == '21' and ids[-1] == '40' and '25' in ids and '1' not in ids
    assert b'Page 2' in response.data
    assert b'value="invalid"' in response.data


@pytest.mark.parametrize('role,path,list_path,sort', [
    ('member', '/member/requests/1', '/member/requests?', 'oldest'),
    ('organization', '/organization/requests/1', '/organization/requests?', 'oldest'),
    ('coordinator', '/coordinator/requests/1', '/coordinator/requests?', 'oldest'),
    (None, '/services/1', '/services?', 'name_desc'),
])
def test_detail_back_links_preserve_validated_list_context(listing_app, role, path, list_path, sort):
    import html
    client = signed_client(listing_app, role) if role else listing_app.test_client()
    response = client.get(path + '?page=2&sort=' + sort)
    assert response.status_code == 200
    rendered = html.unescape(response.get_data(as_text=True))
    assert list_path in rendered and 'sort=' + sort in rendered and 'page=2' in rendered
