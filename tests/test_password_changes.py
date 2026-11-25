"""Firebase password changes mocked in browser; no live passwords are changed."""
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from werkzeug.serving import make_server

from conftest import LocalSession
from test_navigation_audit import audit_app,audit_engine,make_client,ROLE_COOKIES
from test_coordinator_workflow import coordinator_engine
from test_organization_workflow import org_engine
from test_member_workflow import member_engine
from test_login_ui import login_browser
from app.services.password_sessions import password_identity


@pytest.mark.parametrize('role,uid,email',[
    ('member','synthetic-member','member@example.test'),
    ('organization','synthetic-representative','rep@example.test'),
])
def test_context_is_own_login_not_shared_org_email(audit_app,role,uid,email):
    path='/member/password-context' if role=='member' else '/organization/password-context'
    assert make_client(audit_app,'guest').get(path).status_code==302
    response=make_client(audit_app,role).get(path)
    assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
    assert response.json==dict(uid=uid,email=email)
    with patch('app.'+('member' if role=='member' else 'organization')+'.password_identity',return_value=None):
        assert make_client(audit_app,role).get(path).status_code==403


def test_context_role_activity_and_database_failure(audit_app,audit_engine):
    with LocalSession(audit_engine) as database:
        assert password_identity(database,1,'member') is None
        assert password_identity(database,4,'member') is None
        assert password_identity(database,9,'coordinator') is None
    with audit_engine.begin() as connection:
        connection.execute(text('UPDATE users SET is_active=FALSE WHERE user_id=9'))
    assert make_client(audit_app,'member').get('/member/password-context').status_code==302
    with patch('app.organization.password_identity',side_effect=OperationalError('private',{},Exception())):
        response=make_client(audit_app,'organization').get('/organization/password-context')
    assert response.status_code==503 and 'private' not in response.get_data(as_text=True)


@pytest.mark.parametrize('role',['member','organization'])
def test_logout_csrf_clear_cookies_without_valid_firebase_cookie(audit_app,role):
    client=make_client(audit_app,role)
    prefix='/member' if role=='member' else '/organization'
    page=client.get(prefix+'/profile')
    assert page.status_code==200
    with client.session_transaction() as session:
        csrf=session[role+'_csrf']
    assert client.post('/api/auth/logout-browser').status_code==403
    assert client.post('/api/auth/logout-browser',headers={'X-CSRF-Token':csrf},json={'password':'not-accepted'}).status_code==400
    with patch('app.member.cookie_claims',side_effect=ValueError('revoked')),patch('app.organization.cookie_claims',side_effect=ValueError('revoked')):
        response=client.post('/api/auth/logout-browser',headers={'X-CSRF-Token':csrf})
    assert response.status_code==200 and response.json['redirect_url']=='/login'
    assert response.headers['Cache-Control']=='no-store'
    assert all(name in str(response.headers.getlist('Set-Cookie')) for name in
               ('careconnect_member','careconnect_organization','careconnect_coordinator'))
    with client.session_transaction() as session:
        assert not session
    assert client.get(prefix).status_code==302


@pytest.fixture(params=['member','organization'])
def password_ui(request,audit_app,audit_engine,login_browser):
    role=request.param
    tables=('users','member_profiles','organizations','organization_representatives','service_requests','event_outbox')
    def snapshot():
        with audit_engine.connect() as connection:
            return {table:connection.execute(text('SELECT * FROM '+table)).all() for table in tables}
    before=snapshot()
    uid='synthetic-member' if role=='member' else 'synthetic-representative'
    email='member@example.test' if role=='member' else 'rep@example.test'
    server=make_server('127.0.0.1',0,audit_app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':1280,'height':900})
    name,value=ROLE_COOKIES[role]
    context.add_cookies([dict(name=name,value=value,url=base)])
    page=context.new_page()
    state=SimpleNamespace(page=page,url=base,role=role,calls=[],requests=[],errors=[])
    page.expose_function('recordSdk',lambda event:state.calls.append(event))
    page.on('pageerror',lambda error:state.errors.append(str(error)))
    page.on('request',lambda event:state.requests.append((event.url,event.post_data)) if event.url.startswith(base) else None)
    def sdk(route):
        if 'firebase-app.js' in route.request.url:
            source='export const initializeApp = config => ({});'
        else:
            source='''
export const getAuth = () => ({});
export const inMemoryPersistence = {};
export const setPersistence = async () => {await window.recordSdk({kind:'memory'});};
export const signInWithEmailAndPassword = async (auth,email,password) => {
 await window.recordSdk({kind:'signin',email});
 if(window.wrongPassword || password!=='synthetic-current-password') throw {code:'auth/invalid-credential'};
 return {user:{uid:window.wrongUid ? 'different-uid' : EXPECTED_UID}};
};
export const updatePassword = async (user,password) => {
 if(window.weakPassword) throw {code:'auth/weak-password'};
 if(window.networkFailure) throw {code:'auth/network-request-failed'};
 if(password!=='synthetic-new-password') throw new Error('Unexpected synthetic new password');
 await window.recordSdk({kind:'update',uid:user.uid});
};
export const signOut = async () => {await window.recordSdk({kind:'signout'});};
'''.replace('EXPECTED_UID',repr(uid))
        route.fulfill(body=source,content_type='application/javascript',headers={'Access-Control-Allow-Origin':'*'})
    page.route('https://www.gstatic.com/firebasejs/**',sdk)
    page.goto(base+('/member/profile' if role=='member' else '/organization/profile'))
    state.expected_uid=uid;state.expected_email=email
    yield state
    context.close();server.shutdown();thread.join(timeout=3);server.server_close()
    assert snapshot()==before,'Password handling must not edit SQL accounts, profiles or workflows'


def fill(ui,new='synthetic-new-password',confirm=None):
    ui.page.locator('#old_password').fill('synthetic-current-password')
    ui.page.locator('#password').fill(new)
    ui.page.locator('#confirm_password').fill(confirm if confirm is not None else new)


def test_success_uid_binding_no_password_post_and_signout(password_ui):
    from playwright.sync_api import expect
    ui=password_ui;fill(ui)
    serialized=ui.page.locator('#password-change-form').evaluate('f=>Object.fromEntries(new FormData(f))')
    assert set(serialized)=={'form_type','csrf_token'}
    ui.page.get_by_role('button',name='Change password',exact=True).evaluate('b=>{b.click();b.click();}')
    expect(ui.page).to_have_url(ui.url+'/login')
    assert [call for call in ui.calls if call['kind']=='update']==[dict(kind='update',uid=ui.expected_uid)]
    assert [call['email'] for call in ui.calls if call['kind']=='signin']==[ui.expected_email]
    assert any(call['kind']=='memory' for call in ui.calls) and any(call['kind']=='signout' for call in ui.calls)
    assert ui.page.evaluate('Object.keys(localStorage).length')==0
    assert all('synthetic-current-password' not in (body or '') and 'synthetic-new-password' not in (body or '') for url,body in ui.requests)
    assert any('/api/auth/logout-browser' in url for url,body in ui.requests)
    assert not ui.errors


@pytest.mark.parametrize('failure,expected',[
    ('wrongPassword','Current password is incorrect.'),
    ('wrongUid','Account changed.'),('weakPassword','Choose a stronger new password.'),
    ('networkFailure','Unable to connect.'),
])
def test_failures_do_not_update_or_logout_and_clear_fields(password_ui,failure,expected):
    from playwright.sync_api import expect
    ui=password_ui;ui.page.evaluate('key=>window[key]=true',failure);fill(ui)
    ui.page.get_by_role('button',name='Change password',exact=True).click()
    expect(ui.page.locator('#page-messages')).to_contain_text(expected)
    expect(ui.page.get_by_role('button',name='Change password',exact=True)).to_be_enabled()
    assert not any(call['kind']=='update' for call in ui.calls)
    assert not any('/api/auth/logout-browser' in url for url,body in ui.requests)
    assert all(ui.page.locator('#'+key).input_value()=='' for key in ('old_password','password','confirm_password'))
    assert not ui.errors


def test_mismatch_or_same_password_stops_before_firebase(password_ui):
    from playwright.sync_api import expect
    ui=password_ui;fill(ui,confirm='different-password')
    ui.page.get_by_role('button',name='Change password',exact=True).click()
    expect(ui.page.locator('#page-messages')).to_contain_text('Passwords do not match.')
    fill(ui,new='synthetic-current-password')
    ui.page.get_by_role('button',name='Change password',exact=True).click()
    expect(ui.page.locator('#page-messages')).to_contain_text('different from your current password')
    assert not ui.calls


def test_context_failure_stops_before_firebase(password_ui):
    from playwright.sync_api import expect
    ui=password_ui
    prefix='member' if ui.role=='member' else 'organization'
    ui.page.route('**/'+prefix+'/password-context',lambda route:route.fulfill(status=503,json={'error':'Account service unavailable. Please retry.'}))
    fill(ui);ui.page.get_by_role('button',name='Change password',exact=True).click()
    expect(ui.page.locator('#page-messages')).to_contain_text('Account service unavailable.')
    expect(ui.page.get_by_role('button',name='Change password',exact=True)).to_be_enabled()
    assert not ui.calls


def test_success_with_logout_network_failure_does_not_repeat_password_update(password_ui):
    from playwright.sync_api import expect
    ui=password_ui
    ui.page.route('**/api/auth/logout-browser',lambda route:route.abort())
    fill(ui);ui.page.get_by_role('button',name='Change password',exact=True).click()
    expect(ui.page).to_have_url(ui.url+'/login')
    assert len([call for call in ui.calls if call['kind']=='update'])==1
    assert any(call['kind']=='signout' for call in ui.calls)
