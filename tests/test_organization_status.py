"""Organization status changes against disposable SQL, never live partner records."""
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.services.organization_status import change_organization_status
from app.services.organization_approvals import ApprovalError
from app.services.matching import handle_request_created
from conftest import LocalSession
from test_coordinator_organizations import directory_engine,scalar
from test_coordinator_workflow import coordinator_engine,client,sign_in
from test_organization_workflow import org_engine
from test_member_workflow import member_engine


def test_status_cycle_duplicates_and_preserved_data(directory_engine):
    tables=('organization_services','referrals','organization_applications','event_outbox')
    def snapshot():
        with directory_engine.connect() as connection:
            return {table:connection.execute(text('SELECT * FROM '+table)).all() for table in tables}
    before=snapshot()
    with LocalSession(directory_engine) as database:
        assert change_organization_status(database,1,1,'suspend')=={'status':'suspended','already_processed':False}
        assert change_organization_status(database,1,1,'suspend')['already_processed']
        assert snapshot()==before
        assert change_organization_status(database,1,1,'reactivate')['status']=='approved'
        assert change_organization_status(database,1,1,'reactivate')['already_processed']
    assert snapshot()==before


@pytest.mark.parametrize('org,actor,action,code',[
    (2,1,'suspend',409),(4,1,'reactivate',409),(999,1,'suspend',404),
    (1,4,'suspend',403),(1,9,'suspend',403),(1,1,'approve',400),
])
def test_invalid_transitions_and_roles(directory_engine,org,actor,action,code):
    with LocalSession(directory_engine) as database,pytest.raises(ApprovalError) as error:
        change_organization_status(database,org,actor,action)
    assert error.value.status==code
    assert scalar(directory_engine,'SELECT status FROM organizations WHERE organization_id=1')=='approved'


def test_inactive_coordinator_rechecked(directory_engine):
    with directory_engine.begin() as connection:
        connection.execute(text('UPDATE users SET is_active=FALSE WHERE user_id=1'))
    with LocalSession(directory_engine) as database,pytest.raises(ApprovalError) as error:
        change_organization_status(database,1,1,'suspend')
    assert error.value.status==403


def test_route_csrf_tampering_and_fixed_redirect(client,directory_engine):
    url='/coordinator/organizations/1/status'
    assert client.post(url,data={'action':'suspend'}).status_code==302
    sign_in(client)
    client.get('/coordinator/organizations')
    assert client.post(url,data={'action':'suspend'}).status_code==403
    with client.session_transaction() as session:
        csrf=session['coordinator_csrf']
    data={'csrf_token':csrf,'action':'suspend'}
    assert client.post(url,data=dict(data,return_to='https://example.test')).status_code==400
    assert client.post(url,data=dict(data,action='approve')).status_code==400
    response=client.post(url,data=data)
    assert response.status_code==303 and response.location=='/coordinator/organizations'
    assert scalar(directory_engine,'SELECT status FROM organizations WHERE organization_id=1')=='suspended'
    assert client.post(url,data=data).status_code==303
    assert client.post('/coordinator/organizations/999/status',data=data).status_code==404


def test_failed_update_rolls_back(directory_engine):
    with LocalSession(directory_engine) as database:
        execute=database.execute
        def fail(statement,*args,**kwargs):
            result=execute(statement,*args,**kwargs)
            if str(statement).startswith('UPDATE organizations'):
                raise RuntimeError('Synthetic failure before commit')
            return result
        with patch.object(database,'execute',side_effect=fail),pytest.raises(RuntimeError):
            change_organization_status(database,1,1,'suspend')
    assert scalar(directory_engine,'SELECT status FROM organizations WHERE organization_id=1')=='approved'


def test_suspended_partner_excluded_from_new_matching(directory_engine,event):
    with directory_engine.begin() as connection:
        connection.execute(text('''INSERT INTO service_requests
            (request_id,member_id,service_id,service_area_id,priority_id,title,status,attendance_deadline)
            VALUES(20,9,1,1,1,'Fresh synthetic request','submitted','2099-01-01')'''))
    event=dict(event,request_id=20)
    with LocalSession(directory_engine) as database:
        change_organization_status(database,1,1,'suspend')
        assert handle_request_created(database,event)=='unmatched'
    assert scalar(directory_engine,'SELECT COUNT(*) FROM referrals WHERE request_id=20')==0
    assert scalar(directory_engine,'SELECT status FROM organization_services WHERE organization_service_id=1')=='active'
