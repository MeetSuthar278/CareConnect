from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app.services.reports import report_data
from conftest import LocalSession
from test_coordinator_workflow import coordinator_engine,client,sign_in,scalar
from test_organization_workflow import org_engine
from test_member_workflow import member_engine


def test_totals_yes_no_percentage_and_zero_feedback(coordinator_engine):
    with coordinator_engine.begin() as connection:
        connection.execute(text('INSERT INTO feedback VALUES(2,1,1)'))
    with LocalSession(coordinator_engine) as database:
        data=report_data(database)
    assert data['totals']['helpful_percentage']==50
    assert data['totals']['feedback_count']==2
    assert data['totals']['completed']==1
    assert sum(row['count'] for row in data['by_status'])==data['totals']['requests']
    assert sum(row['count'] for row in data['by_category'])==data['totals']['requests']
    with coordinator_engine.begin() as connection:
        connection.execute(text('DELETE FROM feedback'))
    with LocalSession(coordinator_engine) as database:
        assert report_data(database)['totals']['helpful_percentage'] is None


def test_report_auth_privacy_zero_percent_and_safe_errors(client,coordinator_engine):
    assert client.get('/coordinator/reports').status_code==302
    sign_in(client)
    before=scalar(coordinator_engine,'SELECT COUNT(*) FROM notifications')
    response=client.get('/coordinator/reports')
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    assert b'0.0%' in response.data and b'Helpful feedback' in response.data
    assert b'/5' not in response.data and b'member@example.test' not in response.data
    assert b'Representative private message' not in response.data
    assert scalar(coordinator_engine,'SELECT COUNT(*) FROM notifications')==before
    with patch('app.coordinator.report_data',side_effect=OperationalError('private',{},Exception())):
        response=client.get('/coordinator/reports')
    assert response.status_code==503 and b'Reports could not be loaded.' in response.data
