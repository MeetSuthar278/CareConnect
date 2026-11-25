"""Create owned offerings using disposable SQL and mocked representative identity."""
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, IntegrityError
from werkzeug.datastructures import MultiDict
from werkzeug.serving import make_server

from app.services.offerings import add_offering, OfferingError
from app.services.matching import handle_request_created
from conftest import LocalSession
from test_organization_services import services_engine,scalar,form
from test_organization_workflow import org_engine,client,signed_in
from test_member_workflow import member_engine
from test_login_ui import login_browser


@pytest.fixture
def add_engine(services_engine):
    with services_engine.begin() as connection:
        for sql in [
            'CREATE UNIQUE INDEX org_service_area ON organization_services(organization_id,service_id,service_area_id)',
            'CREATE UNIQUE INDEX offering_priority ON service_priority_support(organization_service_id,priority_id)',
            "INSERT INTO service_areas VALUES(3,'Calgary','Third area',1),(4,'Calgary','Inactive area',0)",
            "INSERT INTO priority_levels VALUES(2,'Medium',12),(3,'Low',24)",
            "INSERT INTO services(service_id,category_id,name,is_active,delivery_mode,description) VALUES(2,1,'Inactive catalog',0,'online','Unused')",
        ]:
            connection.execute(text(sql))
    return services_engine


def add(database,**changes):
    values=dict(service_id=1,area_id=3,status='active',referral_limit=5)
    values.update(changes)
    return add_offering(database,4,**values)


def payload(client):
    signed_in(client)
    data=form(client)
    return dict(csrf_token=data['csrf_token'],service_id='1',service_area_id='3',status='Active',
                max_referrals='5')


def test_add_atomic_duplicate_and_matching_preserves_reservations(add_engine):
    with LocalSession(add_engine) as database:
        result=add(database)
        offering=result['organization_service_id']
        assert not result['already_processed']
        assert add(database)['already_processed']
    assert scalar(add_engine,f'SELECT current_active_referrals FROM organization_services WHERE organization_service_id={offering}')==0
    assert scalar(add_engine,f'SELECT COUNT(*) FROM service_priority_support WHERE organization_service_id={offering} AND is_supported=TRUE')==3
    with add_engine.begin() as connection:
        connection.execute(text('''INSERT INTO service_requests
            (request_id,member_id,service_id,service_area_id,priority_id,title,status,attendance_deadline)
            VALUES(20,9,1,3,2,'New area synthetic request','submitted','2099-01-01')'''))
    with LocalSession(add_engine) as database:
        assert handle_request_created(database,{'request_id':20})=='matched'
        assert add(database)['already_processed']
    assert scalar(add_engine,f'SELECT current_active_referrals FROM organization_services WHERE organization_service_id={offering}')==1
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services WHERE organization_id=1 AND service_area_id=3')==1
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_availability')==0
    assert scalar(add_engine,'SELECT name FROM services WHERE service_id=1')=='Demo service'


@pytest.mark.parametrize('change',[
    dict(status='paused'),dict(referral_limit=6),
])
def test_conflicting_duplicate_preserves_saved_settings(add_engine,change):
    with LocalSession(add_engine) as database:
        add(database)
        with pytest.raises(OfferingError) as error:
            add(database,**change)
        assert error.value.status==409
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services WHERE service_area_id=3')==1
    assert scalar(add_engine,'SELECT active_referral_limit FROM organization_services WHERE service_area_id=3')==5


@pytest.mark.parametrize('changes',[
    dict(service_id=2),dict(service_id=999),dict(area_id=4),dict(area_id=999),
    dict(referral_limit=0),dict(referral_limit=1001),
    dict(referral_limit=True),dict(status='approved'),dict(service_id=True),
])
def test_invalid_selection_never_creates_offering(add_engine,changes):
    with LocalSession(add_engine) as database,pytest.raises(OfferingError) as error:
        add(database,**changes)
    assert error.value.status==400
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services')==3


@pytest.mark.parametrize('sql',[
    "UPDATE organizations SET status='pending' WHERE organization_id=1",
    "UPDATE organizations SET status='suspended' WHERE organization_id=1",
    'UPDATE users SET is_active=FALSE WHERE user_id=4',
    'UPDATE users SET role_id=1 WHERE user_id=4',
])
def test_permission_rechecked_in_transaction(add_engine,sql):
    with add_engine.begin() as connection:
        connection.execute(text(sql))
    with LocalSession(add_engine) as database,pytest.raises(OfferingError) as error:
        add(database)
    assert error.value.status==403
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services')==3


@pytest.mark.parametrize('priority',[1,2,3])
def test_paused_excluded_but_active_supports_every_priority(add_engine,priority):
    with LocalSession(add_engine) as database:
        add(database,status='paused')
    with add_engine.begin() as connection:
        connection.execute(text('''INSERT INTO service_requests
            (request_id,member_id,service_id,service_area_id,priority_id,title,status,attendance_deadline)
            VALUES(20,9,1,3,:priority,'Paused offering','submitted','2099-01-01'),
                  (21,9,1,3,:priority,'Active offering','submitted','2099-01-01')'''),{'priority':priority})
    with LocalSession(add_engine) as database:
        assert handle_request_created(database,{'request_id':20})=='unmatched'
    with add_engine.begin() as connection:
        connection.execute(text("UPDATE organization_services SET status='active' WHERE service_area_id=3"))
    with LocalSession(add_engine) as database:
        assert handle_request_created(database,{'request_id':21})=='matched'


def test_rollback_when_second_priority_insert_fails(add_engine):
    with LocalSession(add_engine) as database:
        original=database.execute
        def fail(statement,params=None,**kwargs):
            result=original(statement,params,**kwargs)
            if str(statement).startswith('INSERT INTO service_priority_support') and params['priority']==2:
                raise OperationalError('Synthetic insert failure',{},Exception())
            return result
        with patch.object(database,'execute',side_effect=fail),pytest.raises(OperationalError):
            add(database)
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services')==3
    assert scalar(add_engine,'SELECT COUNT(*) FROM service_priority_support')==2


def test_native_route_csrf_tampering_duplicate_and_errors(client,add_engine):
    url='/organization/services/add'
    assert client.post(url).status_code==302
    data=payload(client)
    assert client.post(url,data=dict(data,csrf_token='wrong')).status_code==403
    for extra in [dict(organization_id=2),dict(description='Overwrite shared description'),dict(response_hours=24)]:
        assert client.post(url,data=dict(data,**extra)).status_code==400
    repeated=MultiDict(data);repeated.add('service_id','2')
    assert client.post(url,data=repeated).status_code==400
    assert client.post(url,data=dict(data,max_referrals='bad')).status_code==400
    assert client.post(url,data=dict(data,priority_ids=['1'])).status_code==400
    assert client.post(url,data=data).status_code==303
    assert client.post(url,data=data).status_code==303
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services WHERE service_area_id=3')==1
    conflict=client.post(url,data=dict(data,max_referrals='6'))
    assert conflict.status_code==409 and b'already exist' in conflict.data
    assert b'value="6"' in conflict.data
    for failure,code in [(IntegrityError('synthetic',{},Exception()),409),(OperationalError('synthetic',{},Exception()),503)]:
        with patch('app.organization.add_offering',side_effect=failure):
            assert client.post(url,data=data).status_code==code


def test_pending_org_cannot_post_or_bypass_role(client,add_engine):
    data=payload(client)
    with add_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET status='pending' WHERE organization_id=1"))
    assert client.post('/organization/services/add',data=data).status_code==403
    with patch('app.organization.cookie_claims',return_value={'uid':'synthetic-member','email_verified':True}):
        assert client.post('/organization/services/add',data=data).status_code==302
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services')==3


def test_browser_add_service_catalog_details_without_priority_selection(client,add_engine,login_browser):
    from playwright.sync_api import expect
    from app.organization import COOKIE
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':390,'height':844})
    context.add_cookies([{'name':COOKIE,'value':'synthetic-org-cookie','url':base}])
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(base+'/organization/services')
        add_form=page.locator('#add-service-form')
        add_form.locator('[name="service_id"]').select_option('1')
        add_form.locator('[name="service_area_id"]').select_option('3')
        expect(add_form.locator('#description_new')).to_have_value('Shared catalog description')
        expect(add_form.locator('#description_new')).to_be_disabled()
        expect(add_form.locator('#category_new')).to_have_value('Food Assistance')
        assert add_form.locator('[name="delivery_methods"][value="In person"]').is_checked()
        add_form.locator('[name="max_referrals"]').fill('5')
        assert add_form.locator('[name="priority_ids"]').count()==0
        add_form.get_by_role('button',name='Add Service',exact=True).click()
        expect(page.locator('#page-messages')).to_contain_text('Service added.')
        assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services')==4
        assert scalar(add_engine,'SELECT COUNT(*) FROM service_priority_support WHERE organization_service_id=(SELECT MAX(organization_service_id) FROM organization_services) AND is_supported=TRUE')==3
        page.wait_for_load_state('load')
        # The existing table overflows at this viewport even before adding. Check
        # the new form's bounds; table styling is outside this functional phase.
        assert add_form.evaluate('e=>e.getBoundingClientRect().right <= window.innerWidth')
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()


def test_missing_priority_configuration_fails_without_partial_creation(add_engine):
    with add_engine.begin() as connection:
        connection.execute(text("DELETE FROM priority_levels WHERE level_name='Low'"))
    with LocalSession(add_engine) as database,pytest.raises(OfferingError) as error:
        add(database)
    assert error.value.status==503
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services')==3
    assert scalar(add_engine,'SELECT COUNT(*) FROM service_priority_support')==2


def test_existing_partial_priority_offering_preserved(add_engine):
    with LocalSession(add_engine) as database,pytest.raises(OfferingError) as error:
        add(database,area_id=1,referral_limit=10)
    assert error.value.status==409
    assert scalar(add_engine,'SELECT COUNT(*) FROM service_priority_support WHERE organization_service_id=1')==1
    assert scalar(add_engine,'SELECT COUNT(*) FROM organization_services')==3
