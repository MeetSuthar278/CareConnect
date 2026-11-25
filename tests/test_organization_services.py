"""Availability/limits: disposable offerings, no live partner changes."""
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.serving import make_server

from app.services.offerings import OfferingError,update_offering
from app.services.matching import handle_request_created
from app.services.referrals import accept_referral
from conftest import LocalSession
from test_member_workflow import member_engine
from test_organization_workflow import org_engine,client,signed_in
from test_login_ui import login_browser


@pytest.fixture
def services_engine(org_engine):
    with org_engine.begin() as connection:
        for sql in [
            "ALTER TABLE services ADD COLUMN description TEXT DEFAULT 'Shared catalog description'",
            '''CREATE TABLE organization_availability(availability_id INTEGER PRIMARY KEY,
                organization_service_id INTEGER NOT NULL,action TEXT NOT NULL,reason TEXT,
                recorded_at DATETIME,recorded_by_user_id INTEGER NOT NULL)''',
            "INSERT INTO service_areas VALUES(2,'Calgary','Second area',1)",
            "INSERT INTO organization_services VALUES(3,1,1,2,'active',10,0)",
        ]:
            connection.execute(text(sql))
    return org_engine


def scalar(engine,sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def availability(database,status,expected_status='active',version=0,**kwargs):
    return update_offering(database,1,4,status=status,expected_status=expected_status,
                           availability_version=version,**kwargs)


def form(client,settings=False):
    page=client.get('/organization/services')
    assert page.status_code==200
    html=page.get_data(as_text=True)
    with client.session_transaction() as session:
        csrf=session['organization_csrf']
    if settings:
        return dict(csrf_token=csrf,organization_service_id='1',status='Active',max_referrals='10',
                    expected_status='active',expected_limit='10',availability_version='0')
    return dict(csrf_token=csrf,target_status='paused',expected_status='active',availability_version='0')


def test_pause_resume_idempotent_and_stale_cycle_guard(services_engine):
    with LocalSession(services_engine) as database:
        assert not availability(database,'paused')['already_processed']
        assert availability(database,'paused')['already_processed']
        assert scalar(services_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1')==1
        version=scalar(services_engine,'SELECT MAX(availability_id) FROM organization_availability')
        assert not availability(database,'active','paused',version)['already_processed']
        with pytest.raises(OfferingError,match='changed'):
            availability(database,'paused')
    assert scalar(services_engine,'SELECT COUNT(*) FROM organization_availability')==2
    assert scalar(services_engine,"SELECT COUNT(*) FROM organization_availability WHERE action='pause'")==1
    assert scalar(services_engine,"SELECT COUNT(*) FROM organization_availability WHERE action='resume'")==1
    assert scalar(services_engine,'SELECT recorded_by_user_id FROM organization_availability LIMIT 1')==4
    assert scalar(services_engine,'SELECT status FROM organization_services WHERE organization_service_id=3')=='active'


def test_limit_cannot_drop_below_locked_reservations(services_engine):
    with services_engine.begin() as connection:
        connection.execute(text('UPDATE organization_services SET current_active_referrals=3 WHERE organization_service_id=1'))
    with LocalSession(services_engine) as database:
        with pytest.raises(OfferingError,match='below current'):
            availability(database,'active',referral_limit=2,expected_limit=10)
        assert scalar(services_engine,'SELECT active_referral_limit FROM organization_services WHERE organization_service_id=1')==10
        assert not availability(database,'active',referral_limit=3,expected_limit=10)['already_processed']
        assert availability(database,'active',referral_limit=3,expected_limit=10)['already_processed']
        with pytest.raises(OfferingError,match='changed'):
            availability(database,'active',referral_limit=4,expected_limit=10)
    assert scalar(services_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1')==3
    assert scalar(services_engine,'SELECT COUNT(*) FROM organization_availability')==0


@pytest.mark.parametrize('value',[0,-1,1001,True,1.5,'5'])
def test_limit_range_and_types(services_engine,value):
    with LocalSession(services_engine) as database:
        with pytest.raises(OfferingError) as error:
            availability(database,'active',referral_limit=value,expected_limit=10)
        assert error.value.status==400


@pytest.mark.parametrize('actor,offering',[(9,1),(1,1),(4,2),(4,999)])
def test_actor_and_offering_ownership_enforced(services_engine,actor,offering):
    with LocalSession(services_engine) as database:
        with pytest.raises(OfferingError) as error:
            update_offering(database,offering,actor,status='paused',expected_status='active',availability_version=0)
        assert error.value.status==404
    assert scalar(services_engine,'SELECT COUNT(*) FROM organization_availability')==0


def test_history_failure_rolls_back_status_and_limit_then_retry(services_engine):
    with LocalSession(services_engine) as database:
        with patch('app.services.offerings.utcnow',side_effect=OperationalError('injected',{},Exception())):
            with pytest.raises(OperationalError):
                availability(database,'paused',referral_limit=5,expected_limit=10)
        assert scalar(services_engine,'SELECT status FROM organization_services WHERE organization_service_id=1')=='active'
        assert scalar(services_engine,'SELECT active_referral_limit FROM organization_services WHERE organization_service_id=1')==10
        assert scalar(services_engine,'SELECT COUNT(*) FROM organization_availability')==0
        assert not availability(database,'paused',referral_limit=5,expected_limit=10)['already_processed']


@pytest.mark.parametrize('sql',['UPDATE users SET is_active=0 WHERE user_id=4',
    'UPDATE users SET role_id=1 WHERE user_id=4',
    'UPDATE organization_representatives SET organization_id=2 WHERE user_id=4'])
def test_permission_changes_rechecked_inside_offering_transaction(services_engine,sql):
    with services_engine.begin() as connection:
        connection.execute(text(sql))
    with LocalSession(services_engine) as database:
        with pytest.raises(OfferingError) as error:
            availability(database,'paused')
        assert error.value.status==404
    assert scalar(services_engine,'SELECT status FROM organization_services WHERE organization_service_id=1')=='active'
    assert scalar(services_engine,'SELECT COUNT(*) FROM organization_availability')==0


def test_pause_excludes_new_matching_but_preserves_existing_reserved_work(services_engine):
    with LocalSession(services_engine) as database:
        availability(database,'paused')
        assert handle_request_created(database,{'request_id':2})=='matched'
        assert scalar(services_engine,'SELECT organization_id FROM referrals WHERE request_id=2')==2
        assert scalar(services_engine,'SELECT status FROM referrals WHERE request_id=1')=='sent'
        assert accept_referral(database,1,4)['status']=='accepted'
        assert scalar(services_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1')==1


def test_page_disables_shared_fields_and_new_service_and_identifies_area_offerings(client,services_engine):
    assert client.get('/organization/services').status_code==302
    signed_in(client)
    page=client.get('/organization/services')
    assert page.status_code==200 and page.headers['Cache-Control']=='no-store'
    html=page.get_data(as_text=True)
    assert '/organization/services/1/availability' in html and '/organization/services/3/availability' in html
    assert '/organization/services/2/availability' not in html
    assert 'id="status_1"' in html and 'id="status_3"' in html
    assert '<td>2 hours</td>' in html
    assert 'id="add-service-form"' in html
    assert '/organization/services/add' in html


def test_native_csrf_shared_tampering_duplicate_and_limit_save(client,services_engine):
    signed_in(client)
    data=form(client)
    url='/organization/services/1/availability'
    assert client.post(url,data=dict(data,csrf_token='wrong')).status_code==403
    assert client.post('/organization/services/2/availability',data=data).status_code==404
    assert client.post(url,data=data).status_code==303
    assert client.post(url,data=data).status_code==303
    assert scalar(services_engine,'SELECT COUNT(*) FROM organization_availability')==1
    settings=form(client,True)
    settings.update(expected_status='paused',availability_version='1',status='Paused',max_referrals='5')
    assert client.post('/organization/services',data=dict(settings,service_name='Do not change shared catalog')).status_code==400
    assert client.post('/organization/services',data=dict(settings,response_hours='24')).status_code==400
    assert client.post('/organization/services',data=settings).status_code==303
    assert scalar(services_engine,'SELECT active_referral_limit FROM organization_services WHERE organization_service_id=1')==5
    assert scalar(services_engine,'SELECT name FROM services WHERE service_id=1')=='Demo service'
    assert scalar(services_engine,'SELECT delivery_mode FROM services WHERE service_id=1')=='in-person'
    assert scalar(services_engine,'SELECT current_active_referrals FROM organization_services WHERE organization_service_id=1')==1
    assert scalar(services_engine,'SELECT COUNT(*) FROM service_priority_support')==2
    assert scalar(services_engine,'SELECT COUNT(*) FROM event_outbox')==1


def test_settings_cannot_add_service_and_unauthorized_cookie_denied(client,services_engine):
    signed_in(client)
    data=form(client,True)
    assert client.post('/organization/services',data={'csrf_token':data['csrf_token']}).status_code==400
    assert scalar(services_engine,'SELECT COUNT(*) FROM services')==1
    with patch('app.organization.cookie_claims',return_value={'uid':'synthetic-member','email_verified':True}):
        assert client.get('/organization/services').status_code==302


def test_browser_pause_activate_and_limit_edit(client,services_engine,login_browser):
    from playwright.sync_api import expect
    from app.organization import COOKIE
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':1280,'height':1000})
    context.add_cookies([{'name':COOKIE,'value':'synthetic-org-cookie','url':base}])
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(base+'/organization')
        page.get_by_role('link',name='My Services',exact=True).click()
        expect(page.locator('h1')).to_have_text('My Services')
        expect(page.get_by_role('button',name='Add Service',exact=True)).to_be_enabled()
        expect(page.locator('#service_name_1')).to_be_disabled()
        expect(page.locator('#response_hours_1')).to_be_disabled()
        assert page.locator('#response_hours_1').input_value()=='2'
        page.get_by_role('button',name='Pause',exact=True).first.click()
        expect(page.get_by_role('button',name='Activate',exact=True)).to_be_visible()
        page.get_by_role('button',name='Activate',exact=True).click()
        expect(page.get_by_role('button',name='Pause',exact=True)).to_have_count(2)
        details=page.locator('details').first
        details.locator('summary').focus();details.locator('summary').press('Enter')
        page.locator('#max_referrals_1').fill('1')
        details.get_by_role('button',name='Save Settings',exact=True).click()
        expect(page.locator('#page-messages')).to_contain_text('Service settings saved.')
        assert scalar(services_engine,'SELECT active_referral_limit FROM organization_services WHERE organization_service_id=1')==1
        assert scalar(services_engine,'SELECT COUNT(*) FROM organization_availability')==2
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()


@pytest.mark.parametrize('status',['pending','suspended'])
def test_unapproved_organization_blocked_from_page_and_posts(client,services_engine,status):
    signed_in(client)
    settings=form(client,True)
    toggle=form(client)
    with services_engine.begin() as connection:
        connection.execute(text('UPDATE organizations SET status=:status WHERE organization_id=1'),{'status':status})
    response=client.get('/organization/services')
    assert response.status_code==302 and response.location=='/organization'
    dashboard=client.get('/organization')
    assert dashboard.status_code==200
    assert b'My Services is available only while your organization is approved.' in dashboard.data
    assert client.post('/organization/services',data=settings).status_code==403
    assert client.post('/organization/services/1/availability',data=toggle).status_code==403
    assert scalar(services_engine,'SELECT COUNT(*) FROM organization_availability')==0
    assert scalar(services_engine,'SELECT active_referral_limit FROM organization_services WHERE organization_service_id=1')==10
    # Access changes immediately after approval/reactivation; no new login needed.
    with services_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET status='approved' WHERE organization_id=1"))
    assert client.get('/organization/services').status_code==200


@pytest.mark.parametrize('status',['pending','suspended'])
def test_offering_service_rechecks_organization_approval(services_engine,status):
    with services_engine.begin() as connection:
        connection.execute(text('UPDATE organizations SET status=:status WHERE organization_id=1'),{'status':status})
    with LocalSession(services_engine) as database:
        with pytest.raises(OfferingError) as error:
            availability(database,'paused')
        assert error.value.status==403
        # Even an otherwise idempotent settings request must pass current approval.
        with pytest.raises(OfferingError) as error:
            availability(database,'active')
        assert error.value.status==403
    assert scalar(services_engine,'SELECT status FROM organization_services WHERE organization_service_id=1')=='active'
    assert scalar(services_engine,'SELECT COUNT(*) FROM organization_availability')==0
