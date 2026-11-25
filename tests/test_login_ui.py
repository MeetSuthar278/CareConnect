"""Latest-team login template + JS; Firebase and identity API are mocked in Edge."""
import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from werkzeug.serving import make_server
from app import create_app


@pytest.fixture(scope="module")
def login_browser():
    playwright=pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser=p.chromium.launch(channel="msedge",headless=True)
        yield browser
        browser.close()


@pytest.fixture
def login_ui(login_browser,monkeypatch):
    monkeypatch.setenv("SECRET_KEY","isolated-login-tests")
    monkeypatch.setenv("DATABASE_URL","sqlite:///:memory:")
    app=create_app({"TESTING":True})
    server=make_server("127.0.0.1",0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    context=login_browser.new_context(viewport={"width":1280,"height":900})
    page=context.new_page()
    state=SimpleNamespace(page=page,url=f"http://127.0.0.1:{server.server_port}",calls=[],session_calls=[],role='member',fail=None,errors=[])
    page.on("pageerror",lambda error:state.errors.append(str(error)))
    def sdk(route):
        if "firebase-app.js" in route.request.url:
            source="export const initializeApp = config => ({config});"
        else:
            source="""
export const getAuth = app => ({});
export const inMemoryPersistence = {};
export const setPersistence = async () => {};
export const signOut = async () => { window.testSignedOut = true; };
export const signInWithEmailAndPassword = async (auth,email,password) => {
 window.testLoginCount = (window.testLoginCount || 0) + 1;
 if(window.testWrongPassword) throw {code:'auth/invalid-credential'};
 return {user:{emailVerified:!window.testUnverified,getIdToken:async()=> 'synthetic-test-token'}};
};
"""
        route.fulfill(body=source,content_type="application/javascript",headers={"Access-Control-Allow-Origin":"*"})
    page.route("https://www.gstatic.com/firebasejs/**",sdk)
    def me(route):
        state.calls.append(route.request)
        if state.fail=="network": route.abort(); return
        if state.fail=="backend": route.fulfill(status=503,json={"error":"Account service unavailable"}); return
        if state.fail=='unverified-role':
            route.fulfill(status=403,json={'error':'Verify your email before accessing CareConnect'})
            return
        route.fulfill(json={"user_id":12,"email":"synthetic@example.test","role":state.role,"organization_id":None})
    page.route("**/api/auth/me",me)
    def member_session(route):
        state.session_calls.append(route.request)
        if state.fail=='session':
            route.fulfill(status=503,json={'error':'Could not start your session. Please retry.'})
            return
        destination='/coordinator' if 'coordinator-session' in route.request.url else '/organization' if 'organization-session' in route.request.url else '/member'
        route.fulfill(json={"redirect_url":destination})
    page.route("**/api/auth/session",member_session)
    page.route("**/api/auth/organization-session",member_session)
    page.route("**/api/auth/coordinator-session",member_session)
    page.route("**/member",lambda route:route.fulfill(body='<h1>Member dashboard</h1>',content_type='text/html'))
    page.route("**/organization",lambda route:route.fulfill(body='<h1>Organization dashboard</h1>',content_type='text/html'))
    page.route("**/coordinator",lambda route:route.fulfill(body='<h1>Coordinator dashboard</h1>',content_type='text/html'))
    page.goto(state.url+"/login")
    yield state
    context.close(); server.shutdown(); thread.join(timeout=3); server.server_close()


def fill(ui):
    ui.page.locator("#email").fill("synthetic@example.test")
    ui.page.locator("#password").fill("synthetic-password")


def test_latest_login_design_and_assets(login_ui):
    p=login_ui.page
    assert p.locator("h1").inner_text()=="Log in"
    assert p.locator(".form-box .box form").count()==1
    assert p.locator("#login-form input").count()==2
    assert p.locator("#login-form button").inner_text()=="Log In"
    assert p.locator(".site-nav .brand").inner_text()=="CareConnect"
    assert p.locator("link[rel=stylesheet]").first.get_attribute("href").startswith("/team-static/")
    p.set_viewport_size({"width":390,"height":844})
    assert p.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not login_ui.errors


def test_success_and_repeated_clicks(login_ui):
    from playwright.sync_api import expect
    fill(login_ui)
    login_ui.page.locator("#login-form button").evaluate("b => {b.click();b.click();}")
    expect(login_ui.page).to_have_url(login_ui.url+'/member')
    assert len(login_ui.calls)==1
    assert login_ui.calls[0].headers.get("authorization")=="Bearer synthetic-test-token"
    assert len(login_ui.session_calls)==1
    assert login_ui.session_calls[0].headers.get('x-csrf-token')
    assert not login_ui.errors


def test_wrong_password_does_not_call_backend(login_ui):
    from playwright.sync_api import expect
    fill(login_ui); login_ui.page.evaluate("window.testWrongPassword=true")
    login_ui.page.locator("#login-form button").click()
    expect(login_ui.page.locator("#page-messages .alert-danger")).to_have_text("Email or password is incorrect.")
    assert not login_ui.calls


def test_member_session_failure_does_not_redirect(login_ui):
    from playwright.sync_api import expect
    login_ui.fail='session'; fill(login_ui)
    login_ui.page.locator('#login-form button').click()
    expect(login_ui.page.locator('#page-messages .alert-danger')).to_contain_text('Could not start your session')
    assert login_ui.page.url.endswith('/login')
    expect(login_ui.page.locator('#login-form button')).to_be_enabled()
    assert login_ui.page.evaluate('window.testSignedOut')


def test_representative_login_redirects_to_organization(login_ui):
    from playwright.sync_api import expect
    login_ui.role='representative'; fill(login_ui)
    login_ui.page.locator('#login-form button').click()
    expect(login_ui.page).to_have_url(login_ui.url+'/organization')
    assert len(login_ui.session_calls)==1
    assert login_ui.session_calls[0].url.endswith('/api/auth/organization-session')


def test_coordinator_login_redirects_to_dashboard(login_ui):
    from playwright.sync_api import expect
    login_ui.role='coordinator'; fill(login_ui)
    login_ui.page.locator('#login-form button').click()
    expect(login_ui.page).to_have_url(login_ui.url+'/coordinator')
    assert login_ui.session_calls[0].url.endswith('/api/auth/coordinator-session')


def test_unverified_member_login_reaches_dashboard(login_ui):
    from playwright.sync_api import expect
    fill(login_ui); login_ui.page.evaluate("window.testUnverified=true")
    login_ui.page.locator("#login-form button").click()
    expect(login_ui.page).to_have_url(login_ui.url+'/member')
    assert len(login_ui.calls)==1 and len(login_ui.session_calls)==1


def test_unverified_privileged_login_respects_backend_rejection(login_ui):
    from playwright.sync_api import expect
    login_ui.fail='unverified-role';login_ui.role='representative'
    fill(login_ui);login_ui.page.evaluate('window.testUnverified=true')
    login_ui.page.locator('#login-form button').click()
    expect(login_ui.page.locator('#page-messages .alert-danger')).to_contain_text('Verify your email')
    assert not login_ui.session_calls


@pytest.mark.parametrize("failure",["backend","network"])
def test_backend_and_network_errors(login_ui,failure):
    from playwright.sync_api import expect
    login_ui.fail=failure; fill(login_ui)
    login_ui.page.locator("#login-form button").click()
    expect(login_ui.page.locator("#page-messages .alert-danger")).to_be_visible()
    expect(login_ui.page.locator("#login-form button")).to_be_enabled()
    assert len(login_ui.calls)==1


def test_login_get_does_not_contact_firebase_or_create_account(monkeypatch):
    monkeypatch.setenv("SECRET_KEY","isolated-login-tests")
    monkeypatch.setenv("DATABASE_URL","sqlite:///:memory:")
    app=create_app({"TESTING":True})
    with patch("app.auth.verify_token") as verify, patch("app.auth.resolve_identity") as identity:
        response=app.test_client().get("/login")
    assert response.status_code==200
    assert b'/team-static/css/style.css' in response.data
    assert b'/team-static/js/login.js' in response.data
    assert b'How CareConnect Works' not in response.data
    verify.assert_not_called(); identity.assert_not_called()
