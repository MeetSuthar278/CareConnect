"""Organization directory and lifecycle controls with coordinator authentication."""
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import text
from werkzeug.serving import make_server

from app.coordinator import COOKIE
from test_coordinator_workflow import coordinator_engine,client,sign_in
from test_organization_workflow import org_engine
from test_member_workflow import member_engine
from test_login_ui import login_browser


@pytest.fixture
def directory_engine(coordinator_engine):
    with coordinator_engine.begin() as connection:
        for sql in [
            'ALTER TABLE organizations ADD COLUMN address TEXT',
            'ALTER TABLE organizations ADD COLUMN created_at DATETIME',
            "UPDATE organizations SET name='Partner A' WHERE organization_id=1",
            "UPDATE organizations SET name='Partner B' WHERE organization_id=2",
            """INSERT INTO organizations(organization_id,name,status,contact_email,contact_phone,city)
                VALUES(3,'Demo Approval Test','approved','approval@example.test','4035550101','Calgary'),
                      (4,'Demo Rejection Test','pending','rejection@example.test','4035550102','Calgary'),
                      (5,'Suspended Test','suspended','suspended@example.test','4035550103','Calgary')""",
            """INSERT INTO organization_applications(application_id,organization_id,submitted_by_user_id,status,decision_notes,decided_at)
                VALUES(2,4,9,'rejected','Synthetic rejection','2000-01-01')""",
            "INSERT INTO service_areas VALUES(2,'Calgary','Second area',1)",
            "INSERT INTO organization_services VALUES(3,1,1,2,'paused',10,0)",
        ]:
            connection.execute(text(sql))
    return coordinator_engine


def scalar(engine,sql):
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar()


def test_directory_real_details_status_and_distinct_service_count(client,directory_engine):
    sign_in(client)
    page=client.get('/coordinator/organizations')
    assert page.status_code==200 and page.headers['Cache-Control']=='no-store'
    html=page.get_data(as_text=True)
    assert all(name in html for name in ['Partner A','Partner B','Demo Approval Test','Demo Rejection Test','Suspended Test'])
    assert 'Downtown, Calgary' in html and 'Second area, Calgary' in html
    assert 'Synthetic Representative' in html
    assert 'Representative private message' not in html
    assert '/coordinator/organizations/1/status' in html
    assert '>Rejected</span>' in html
    # One shared service offered across two areas counts as one service.
    first=html.split('Partner A',1)[1].split('</tr>',1)[0]
    assert '<td>1</td>' in first
    assert scalar(directory_engine,'SELECT status FROM organizations WHERE organization_id=4')=='pending'


@pytest.mark.parametrize('status,present,absent',[
    ('Active','Partner A','Partner B'),
    ('Pending','Partner B','Demo Rejection Test'),
    ('Rejected','Demo Rejection Test','Partner A'),
    ('Suspended','Suspended Test','Demo Rejection Test'),
])
def test_existing_status_filter(client,directory_engine,status,present,absent):
    sign_in(client)
    page=client.get('/coordinator/organizations',query_string={'status':status})
    assert page.status_code==200
    html=page.get_data(as_text=True)
    assert present in html and absent not in html


def test_rejected_filter_uses_latest_application_and_no_mutations(client,directory_engine):
    sign_in(client)
    before={table:scalar(directory_engine,'SELECT COUNT(*) FROM '+table) for table in
            ('organizations','organization_applications','organization_services','notifications','event_outbox','users')}
    response=client.get('/coordinator/organizations?status=Rejected')
    assert b'Demo Rejection Test' in response.data
    assert client.post('/coordinator/organizations',data={'action':'suspend','org_id':1}).status_code==405
    assert before=={table:scalar(directory_engine,'SELECT COUNT(*) FROM '+table) for table in before}
    assert scalar(directory_engine,'SELECT status FROM organizations WHERE organization_id=1')=='approved'
    with directory_engine.begin() as connection:
        connection.execute(text("INSERT INTO organization_applications(application_id,organization_id,submitted_by_user_id,status) VALUES(3,4,9,'submitted')"))
    assert b'Demo Rejection Test' not in client.get('/coordinator/organizations?status=Rejected').data
    assert b'Demo Rejection Test' in client.get('/coordinator/organizations?status=Pending').data


def test_directory_requires_verified_current_coordinator(client,directory_engine):
    assert client.get('/coordinator/organizations').status_code==302
    sign_in(client)
    with patch('app.coordinator.cookie_claims',return_value={'uid':'synthetic-member','email_verified':True}):
        assert client.get('/coordinator/organizations').status_code==302
    sign_in(client)
    with patch('app.coordinator.cookie_claims',return_value={'uid':'synthetic-coordinator','email_verified':False}):
        assert client.get('/coordinator/organizations').status_code==302


def test_browser_navigation_filters_details_and_status_actions(client,directory_engine,login_browser):
    from playwright.sync_api import expect
    server=make_server('127.0.0.1',0,client.application,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':1280,'height':1000})
    context.add_cookies([{'name':COOKIE,'value':'synthetic-coordinator-cookie','url':base}])
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto(base+'/coordinator')
        page.get_by_role('link',name='Organizations',exact=True).click()
        expect(page.locator('h1')).to_have_text('Organizations')
        expect(page.get_by_role('button',name='Suspend',exact=True).first).to_be_enabled()
        expect(page.get_by_role('button',name='Reactivate',exact=True)).to_be_enabled()
        page.on('dialog',lambda dialog:dialog.accept())
        partner=page.locator('tr').filter(has_text='Partner A')
        partner.get_by_role('button',name='Suspend',exact=True).click()
        expect(partner.get_by_role('button',name='Reactivate',exact=True)).to_be_visible()
        assert scalar(directory_engine,'SELECT status FROM organizations WHERE organization_id=1')=='suspended'
        partner.get_by_role('button',name='Reactivate',exact=True).click()
        expect(partner.get_by_role('button',name='Suspend',exact=True)).to_be_visible()
        page.locator('summary').first.focus()
        page.locator('summary').first.press('Enter')
        assert page.locator('details[open]').count()==1
        page.locator('#status').select_option('Rejected')
        page.get_by_role('button',name='Filter',exact=True).click()
        expect(page.locator('main')).to_contain_text('Demo Rejection Test')
        assert 'Partner A' not in page.locator('main').inner_text()
        assert not errors
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()
