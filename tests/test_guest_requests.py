"""Latest-team form integration: disposable SQL, no live profiles or requests."""
from unittest.mock import patch
import pytest
from sqlalchemy import text
from app import create_app
from app.services.guest_requests import create_guest_request, GuestRequestError, service_choices
from conftest import LocalSession


@pytest.fixture
def guest_engine(engine):
    with engine.begin() as c:
        for sql in [
            "CREATE TABLE service_categories(category_id INTEGER PRIMARY KEY,name TEXT,is_active BOOLEAN)",
            "INSERT INTO service_categories VALUES(1,'Food Assistance',1)",
            "ALTER TABLE services ADD COLUMN delivery_mode TEXT DEFAULT 'in-person'",
            "CREATE TABLE member_profiles(profile_id INTEGER PRIMARY KEY,user_id INTEGER UNIQUE,first_name TEXT,last_name TEXT,phone TEXT,address TEXT,city TEXT)",
            "CREATE UNIQUE INDEX uq_test_user_email ON users(email)",
        ]: c.execute(text(sql))
    return engine


@pytest.fixture
def guest_client(guest_engine):
    app=create_app({"TESTING":True,"SQLALCHEMY_DATABASE_URI":"sqlite:///:memory:"})
    with patch('app.frontend.Session',side_effect=lambda unused:LocalSession(guest_engine)), \
         patch('app.requests.Session',side_effect=lambda unused:LocalSession(guest_engine)):
        yield app.test_client()


@pytest.fixture
def fields():
    return dict(service_id='1',priority='High',delivery_method='In person',
                details='Synthetic groceries needed\nExtra detail',contact_name='Demo Visitor',
                contact_email='visitor@example.test',contact_phone='403-555-0111',
                contact_city='Calgary',contact_address='1 Demo Street')


def scalar(engine,sql):
    with engine.connect() as c:return c.execute(text(sql)).scalar()


def csrf_form(client,fields):
    import re
    page=client.get('/get-connected')
    assert page.status_code==200
    html=page.get_data(as_text=True)
    values=dict(fields)
    for key in ['csrf_token','submission_nonce']:
        values[key]=re.search('name="'+key+'" value="([^"]+)"',html).group(1)
    return values


def test_team_template_and_native_transaction(guest_client,guest_engine,fields):
    payload=csrf_form(guest_client,fields)
    response=guest_client.post('/api/guest/requests',data=payload)
    assert response.status_code==303
    assert scalar(guest_engine,"SELECT COUNT(*) FROM users")==4
    assert scalar(guest_engine,"SELECT COUNT(*) FROM member_profiles")==1
    assert scalar(guest_engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='ServiceRequestCreated'")==1
    assert scalar(guest_engine,"SELECT title FROM service_requests WHERE request_id<>1")=='Synthetic groceries needed'
    assert scalar(guest_engine,"SELECT service_area_id FROM service_requests WHERE request_id<>1")==1
    assert scalar(guest_engine,"SELECT email FROM users WHERE user_id=9")=='member@example.test'
    assert guest_client.get(response.location).status_code==200
    assert b'How CareConnect Works' not in guest_client.get('/get-connected').data
    assert b'/team-static/css/style.css' in guest_client.get('/get-connected').data


def test_same_post_and_refresh_do_not_duplicate(guest_client,guest_engine,fields):
    payload=csrf_form(guest_client,fields)
    first=guest_client.post('/api/guest/requests',data=payload)
    second=guest_client.post('/api/guest/requests',data=payload)
    assert first.location==second.location
    assert scalar(guest_engine,"SELECT COUNT(*) FROM service_requests")==2
    assert scalar(guest_engine,"SELECT COUNT(*) FROM member_profiles")==1
    for _ in range(3): assert guest_client.get(first.location).status_code==200
    assert scalar(guest_engine,"SELECT COUNT(*) FROM service_requests")==2


def test_ownership_never_falls_back_to_demo_member(guest_client,guest_engine,fields):
    assert guest_client.get('/api/guest/requests/1').status_code==404
    payload=csrf_form(guest_client,fields)
    response=guest_client.post('/api/guest/requests',data=payload)
    rid=int(response.location.rsplit('-',1)[1])
    assert guest_client.get(f'/api/guest/requests/{rid}').status_code==200
    assert guest_client.get('/api/guest/requests/1').status_code==404
    with guest_client.session_transaction() as s:s.clear()
    assert guest_client.get(response.location).status_code==404
    assert guest_client.get(f'/api/guest/requests/{rid}').status_code==404


def test_existing_email_never_links_or_overwrites(guest_client,guest_engine,fields):
    fields['contact_email']='member@example.test'
    payload=csrf_form(guest_client,fields)
    assert guest_client.post('/api/guest/requests',data=payload).status_code==409
    assert scalar(guest_engine,"SELECT COUNT(*) FROM users")==3
    assert scalar(guest_engine,"SELECT COUNT(*) FROM service_requests")==1


def test_csrf_and_nonce_are_required(guest_client,guest_engine,fields):
    assert guest_client.post('/api/guest/requests',data=fields).status_code==403
    payload=csrf_form(guest_client,fields);payload['submission_nonce']='bad'
    assert guest_client.post('/api/guest/requests',data=payload).status_code==400
    assert scalar(guest_engine,"SELECT COUNT(*) FROM service_requests")==1


@pytest.mark.parametrize('changes',[
    {'service_id':'999'},{'priority':'Urgent'},{'delivery_method':'Online'},
    {'details':'   '},{'contact_phone':'abc'},{'contact_email':'invalid'},
    {'contact_name':'x'*51+' Visitor'},{'contact_city':'Other City'},
])
def test_validation_has_no_partial_writes(guest_client,guest_engine,fields,changes):
    fields.update(changes)
    payload=csrf_form(guest_client,fields)
    assert guest_client.post('/api/guest/requests',data=payload).status_code==400
    assert scalar(guest_engine,"SELECT COUNT(*) FROM users")==3
    assert scalar(guest_engine,"SELECT COUNT(*) FROM event_outbox")==0


def test_ambiguous_area_is_not_guessed(guest_client,guest_engine,fields):
    with guest_engine.begin() as c:
        c.execute(text("INSERT INTO service_areas VALUES(2,'Calgary','North',1)"))
        c.execute(text("INSERT INTO organization_services VALUES(3,2,1,2,'active',10,0)"))
    payload=csrf_form(guest_client,fields)
    assert guest_client.post('/api/guest/requests',data=payload).status_code==400
    assert scalar(guest_engine,"SELECT COUNT(*) FROM users")==3
    with LocalSession(guest_engine) as s:assert service_choices(s)==[]


def test_outbox_failure_rolls_back_guest_profile_and_request(guest_engine,fields):
    with LocalSession(guest_engine) as s,patch('app.services.guest_requests.enqueue',side_effect=RuntimeError('injected')):
        with pytest.raises(RuntimeError):create_guest_request(s,fields,None,'test-key')
    assert scalar(guest_engine,"SELECT COUNT(*) FROM users")==3
    assert scalar(guest_engine,"SELECT COUNT(*) FROM member_profiles")==0
    assert scalar(guest_engine,"SELECT COUNT(*) FROM service_requests")==1


def test_same_session_can_reuse_profile_without_overwriting(guest_client,guest_engine,fields):
    guest_client.post('/api/guest/requests',data=csrf_form(guest_client,fields))
    changed=dict(fields,details='Another synthetic request')
    assert guest_client.post('/api/guest/requests',data=csrf_form(guest_client,changed)).status_code==303
    assert scalar(guest_engine,"SELECT COUNT(*) FROM users")==4
    changed['contact_name']='Different Person'
    assert guest_client.post('/api/guest/requests',data=csrf_form(guest_client,changed)).status_code==409
    assert scalar(guest_engine,"SELECT first_name FROM member_profiles")=='Demo'


def test_confirmation_and_polling_reflect_real_matching(guest_client,guest_engine,fields):
    from app.services.matching import handle_request_created
    response=guest_client.post('/api/guest/requests',data=csrf_form(guest_client,fields))
    rid=int(response.location.rsplit('-',1)[1])
    with LocalSession(guest_engine) as s:
        handle_request_created(s,{'request_id':rid})
    data=guest_client.get(f'/api/guest/requests/{rid}').json
    assert data['status']=='matched' and data['display_status']=='Assigned'
    assert data['response_deadline'] is not None
    assert b'Assigned' in guest_client.get(response.location).data


@pytest.fixture(scope='module')
def guest_browser():
    playwright=pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        yield browser
        browser.close()


@pytest.fixture
def guest_page(guest_engine,guest_browser):
    import threading
    from werkzeug.serving import make_server
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    with patch('app.frontend.Session',side_effect=lambda unused:LocalSession(guest_engine)), \
         patch('app.requests.Session',side_effect=lambda unused:LocalSession(guest_engine)):
        thread.start()
        context=guest_browser.new_context(viewport={'width':1280,'height':1000})
        page=context.new_page()
        page.goto(f'http://127.0.0.1:{server.server_port}/get-connected')
        yield page
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()


def browser_fill(page):
    page.locator('#service_id').select_option('1')
    page.locator('#priority').select_option('High')
    for field,value in dict(details='Synthetic browser guest request',contact_name='Demo Browser',
        contact_phone='403-555-0112',contact_email='browser@example.test',
        contact_city='Calgary',contact_address='2 Demo Street').items():
        page.locator('#'+field).fill(value)


def test_browser_native_submit_duplicate_and_real_status_poll(guest_page,guest_engine):
    from playwright.sync_api import expect
    from app.services.matching import handle_request_created
    browser_fill(guest_page)
    posts=[];errors=[]
    guest_page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
    guest_page.on('pageerror',lambda error:errors.append(str(error)))
    guest_page.locator('#team-request-form button[type=submit]').evaluate('b => {b.click();b.click();}')
    guest_page.wait_for_url('**/get-connected/done/CC-*')
    rid=int(guest_page.locator('#request-confirmation').get_attribute('data-request-id'))
    expect(guest_page.locator('#request-status')).to_have_text('Pending')
    with LocalSession(guest_engine) as s:handle_request_created(s,{'request_id':rid})
    expect(guest_page.locator('#request-status')).to_have_text('Assigned',timeout=10000)
    assert len(posts)==1 and not errors
    guest_page.reload()
    expect(guest_page.locator('#request-status')).to_have_text('Assigned')
    assert scalar(guest_engine,'SELECT COUNT(*) FROM service_requests')==2


def test_browser_validation_and_mobile_layout(guest_page,guest_engine):
    browser_fill(guest_page)
    guest_page.set_viewport_size({'width':390,'height':844})
    assert guest_page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    guest_page.locator('#contact_name').fill('   ')
    guest_page.locator('#team-request-form button[type=submit]').click()
    assert scalar(guest_engine,'SELECT COUNT(*) FROM service_requests')==1
    assert guest_page.locator('#contact_name').get_attribute('aria-invalid')=='true'
    assert guest_page.locator('link[rel=stylesheet]').first.get_attribute('href').startswith('/team-static/')


def test_browser_existing_email_error_uses_existing_message_component(guest_page,guest_engine):
    from playwright.sync_api import expect
    browser_fill(guest_page)
    guest_page.locator('#contact_email').fill('member@example.test')
    guest_page.locator('#team-request-form button[type=submit]').click()
    expect(guest_page.locator('#page-messages .alert-danger')).to_contain_text('cannot be used')
    assert scalar(guest_engine,'SELECT COUNT(*) FROM users')==3


def test_guest_choice_delivery_and_category_are_not_fabricated(guest_client,guest_engine):
    data=guest_client.get('/get-connected').get_data(as_text=True)
    assert 'Demo service' in data and 'Food Assistance' in data
    assert 'In person' in data and 'Downtown, Calgary' in data


def test_committed_post_recoverable_if_response_cookie_was_lost(guest_client,guest_engine,fields):
    payload=csrf_form(guest_client,fields)
    first=guest_client.post('/api/guest/requests',data=payload)
    with guest_client.session_transaction() as s:s.pop('guest_member_id')
    second=guest_client.post('/api/guest/requests',data=payload)
    assert first.location==second.location
    assert guest_client.get(second.location).status_code==200
    assert scalar(guest_engine,'SELECT COUNT(*) FROM service_requests')==2


def test_browser_polling_errors_keep_last_real_state(guest_page,guest_engine):
    from playwright.sync_api import expect
    browser_fill(guest_page)
    guest_page.route('**/api/guest/requests/*',lambda route:route.fulfill(status=503,json={'error':'offline'}))
    guest_page.locator('#team-request-form button[type=submit]').click()
    guest_page.wait_for_url('**/get-connected/done/CC-*')
    expect(guest_page.locator('#status-update-message')).to_contain_text('Unable to refresh',timeout=10000)
    expect(guest_page.locator('#request-status')).to_have_text('Pending')
    assert scalar(guest_engine,'SELECT COUNT(*) FROM service_requests')==2


def test_title_is_derived_without_discarding_description(guest_client,guest_engine,fields):
    fields['details']='x'*200+'\nSecond line'
    response=guest_client.post('/api/guest/requests',data=csrf_form(guest_client,fields))
    assert response.status_code==303
    assert len(scalar(guest_engine,'SELECT title FROM service_requests WHERE request_id<>1'))==150
    assert scalar(guest_engine,'SELECT description FROM service_requests WHERE request_id<>1')==fields['details']


def test_disabled_guest_loses_reference_and_replay_access(guest_client,guest_engine,fields):
    payload=csrf_form(guest_client,fields)
    response=guest_client.post('/api/guest/requests',data=payload)
    rid=int(response.location.rsplit('-',1)[1])
    with guest_engine.begin() as c:
        c.execute(text('UPDATE users SET is_active=0 WHERE user_id=(SELECT member_id FROM service_requests WHERE request_id=:id)'),{'id':rid})
    assert guest_client.get(response.location).status_code==404
    assert guest_client.get(f'/api/guest/requests/{rid}').status_code==404
    assert guest_client.post('/api/guest/requests',data=payload).status_code==404
