"""Public browsing uses disposable SQL; no live requests, accounts or workers."""
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.serving import make_server

from app import create_app
from app.services.service_browsing import public_services
from conftest import LocalSession
from test_guest_requests import guest_engine
from test_login_ui import login_browser


@pytest.fixture
def browse_engine(guest_engine):
    with guest_engine.begin() as connection:
        for sql in [
            'ALTER TABLE users ADD COLUMN firebase_uid TEXT',
            "UPDATE users SET firebase_uid='browse-member' WHERE user_id=9",
            "UPDATE users SET firebase_uid='browse-representative' WHERE user_id=4",
            "INSERT INTO member_profiles(user_id,first_name,last_name,phone,address,city) VALUES(9,'Demo','Member','4035550100','Synthetic street','Calgary')",
            'ALTER TABLE services ADD COLUMN description TEXT',
            'ALTER TABLE organizations ADD COLUMN name TEXT',
            'ALTER TABLE organizations ADD COLUMN contact_email TEXT',
            "UPDATE organizations SET name='Alpha Partner',contact_email='private-alpha@example.test' WHERE organization_id=1",
            "UPDATE organizations SET name='Beta Partner',contact_email='private-beta@example.test' WHERE organization_id=2",
            "INSERT INTO organizations(organization_id,status,name) VALUES(3,'pending','Pending Partner'),(4,'suspended','Suspended Partner')",
            "UPDATE services SET description='Synthetic grocery support' WHERE service_id=1",
            "INSERT INTO service_categories VALUES(2,'Peer Support',1),(3,'Inactive Category',0)",
            "INSERT INTO service_areas VALUES(2,'Calgary','Second area',1),(3,'Calgary','Inactive area',0)",
            """INSERT INTO services(service_id,category_id,name,is_active,delivery_mode,description) VALUES
                (2,2,'Phone companionship',1,'phone','Call for company'),
                (3,3,'Hidden category service',1,'online','Hidden'),
                (4,1,'No offering service',1,'in-person','Hidden'),
                (5,1,'Inactive catalog service',0,'in-person','Hidden'),
                (6,1,'Pending-only service',1,'online','Hidden'),
                (7,1,'Suspended-only service',1,'online','Hidden'),
                (8,1,'Paused-only service',1,'online','Hidden'),
                (9,1,'Inactive area service',1,'online','Hidden'),
                (10,1,'Multiple area service',1,'in-person','Ambiguous')""",
            """INSERT INTO organization_services VALUES
                (3,1,2,1,'active',5,5),(4,1,3,1,'active',5,0),
                (5,1,5,1,'active',5,0),(6,3,6,1,'active',5,0),
                (7,4,7,1,'active',5,0),(8,1,8,1,'paused',5,0),
                (9,1,9,3,'active',5,0),(10,1,10,1,'active',5,0),
                (11,2,10,2,'active',5,0)""",
        ]:
            connection.execute(text(sql))
    return guest_engine


@pytest.fixture
def browse_client(browse_engine):
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with patch('app.frontend.Session',side_effect=lambda unused:LocalSession(browse_engine)), \
         patch('app.member.Session',side_effect=lambda unused:LocalSession(browse_engine)), \
         patch('app.organization.Session',side_effect=lambda unused:LocalSession(browse_engine)), \
         patch('app.member.cookie_claims',return_value={'uid':'browse-member'}), \
         patch('app.organization.cookie_claims',return_value={'uid':'browse-representative','email_verified':True}):
        yield app.test_client()


def test_eligible_services_aggregate_providers_and_single_area(browse_engine):
    with LocalSession(browse_engine) as database:
        rows=public_services(database)
    assert [row['service_id'] for row in rows]==[1,2]
    assert rows[0]['org_name']=='Alpha Partner, Beta Partner'
    assert rows[0]['area']=='Downtown, Calgary'
    assert rows[0]['availability']=='Capacity available'
    assert rows[1]['availability']=='Currently at capacity'
    assert rows[1]['delivery_method']=='Phone'
    assert rows[0]['response_hours']==2 and rows[0]['eligibility']=='-'


def test_browse_details_privacy_request_link_and_read_only(browse_client,browse_engine):
    tables=('organization_services','service_priority_support','service_requests','referrals',
            'event_outbox','notifications','users')
    def snapshot():
        with browse_engine.connect() as connection:
            return {table:connection.execute(text('SELECT * FROM '+table)).all() for table in tables}
    before=snapshot()
    page=browse_client.get('/services')
    assert page.status_code==200 and page.headers['Cache-Control']=='no-store'
    html=page.get_data(as_text=True)
    assert html.count('<h3>Demo service</h3>')==1
    assert 'Alpha Partner, Beta Partner' in html and 'Phone companionship' in html
    assert '/services/1' in html and 'private-alpha@example.test' not in html
    details=browse_client.get('/services/1')
    assert details.status_code==200 and details.headers['Cache-Control']=='no-store'
    assert b'/get-connected?service_id=1' in details.data
    assert b'Synthetic grocery support' in details.data
    assert b'Alpha Partner, Beta Partner' in details.data
    assert b'private-beta@example.test' not in details.data
    form=browse_client.get('/get-connected?service_id=1')
    assert form.status_code==200 and b'Service' in form.data
    assert b'data-area="Downtown, Calgary" selected' in form.data
    assert snapshot()==before
    assert browse_client.post('/services',data={}).status_code==405


@pytest.mark.parametrize('query,present,absent',[
    ({'search':'GROCERY'},'Demo service','Phone companionship'),
    ({'search':'Beta Partner'},'Demo service','Phone companionship'),
    ({'category':'Peer Support'},'Phone companionship','Demo service'),
    ({'delivery':'Phone'},'Phone companionship','Demo service'),
    ({'search':'company','category':'Peer Support','delivery':'Phone'},'Phone companionship','Demo service'),
])
def test_filters(browse_client,query,present,absent):
    response=browse_client.get('/services',query_string=query)
    assert response.status_code==200
    html=response.get_data(as_text=True)
    assert '<h3>'+present+'</h3>' in html
    assert '<h3>'+absent+'</h3>' not in html
    assert 'Clear filters' in html


@pytest.mark.parametrize('query',[{'search':'%_'},{'category':'Unknown'},{'delivery':'Not a delivery mode'}])
def test_empty_results_do_not_relax_filters(browse_client,query):
    response=browse_client.get('/services',query_string=query)
    assert response.status_code==200 and b'No services found.' in response.data


@pytest.mark.parametrize('service_id',[3,4,5,6,7,8,9,10,999])
def test_hidden_and_ambiguous_services_have_no_details(browse_client,service_id):
    assert browse_client.get(f'/services/{service_id}').status_code==404


def test_live_eligibility_changes_rechecked_each_get(browse_client,browse_engine):
    with browse_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET status='suspended' WHERE organization_id=1"))
    page=browse_client.get('/services/1')
    assert page.status_code==200
    assert b'Beta Partner' in page.data and b'Alpha Partner' not in page.data
    assert browse_client.get('/services/2').status_code==404
    with browse_engine.begin() as connection:
        connection.execute(text("UPDATE organization_services SET status='paused' WHERE organization_id=2"))
    assert browse_client.get('/services/1').status_code==404


def test_empty_catalog_failure_and_escaped_content(browse_client,browse_engine):
    with browse_engine.begin() as connection:
        connection.execute(text("UPDATE services SET description='<script>alert(1)</script>' WHERE service_id=1"))
    response=browse_client.get('/services/1')
    assert b'&lt;script&gt;alert(1)&lt;/script&gt;' in response.data
    assert b'<script>alert(1)</script>' not in response.data
    for url in ('/services','/services/1'):
        with patch('app.frontend.Session',side_effect=OperationalError('synthetic',{},Exception())):
            response=browse_client.get(url)
            assert response.status_code==503
            assert b'Services could not be loaded.' in response.data
            assert b'synthetic' not in response.data
    with browse_engine.begin() as connection:
        connection.execute(text("UPDATE organization_services SET status='paused'"))
    assert b'No services found.' in browse_client.get('/services').data


def test_existing_role_presentation_and_member_request_link(browse_client):
    browse_client.set_cookie('careconnect_member','synthetic-member-cookie')
    assert b'Request this service' in browse_client.get('/services/1').data
    browse_client.delete_cookie('careconnect_member')
    browse_client.set_cookie('careconnect_organization','synthetic-representative-cookie')
    assert b'Request this service' not in browse_client.get('/services/1').data


def test_browser_home_browse_filters_details_to_preselected_form(browse_client,login_browser):
    from playwright.sync_api import expect
    server=make_server('127.0.0.1',0,browse_client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':390,'height':844})
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(base+'/')
        page.get_by_role('link',name='Continue as Guest',exact=True).click()
        page.get_by_role('link',name='Browse Services',exact=True).first.click()
        expect(page.locator('h1')).to_have_text('Services')
        page.locator('#search').fill('company')
        page.locator('#category').select_option('Peer Support')
        page.locator('#delivery').select_option('Phone')
        page.get_by_role('button',name='Search',exact=True).click()
        expect(page.locator('h3')).to_have_text('Phone companionship')
        page.get_by_role('link',name='View details',exact=True).click()
        expect(page.locator('h1')).to_have_text('Phone companionship')
        expect(page.locator('main')).to_contain_text('Currently at capacity')
        page.get_by_role('link',name='Request this service',exact=True).click()
        expect(page.locator('#service_id')).to_have_value('2')
        expect(page.locator('#delivery_method')).to_have_value('Phone')
        page.wait_for_load_state('load')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()
