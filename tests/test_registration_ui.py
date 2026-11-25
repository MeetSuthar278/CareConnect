"""Existing registration UI with mocked Firebase; no real accounts or email."""
import threading
from types import SimpleNamespace

import pytest
from werkzeug.serving import make_server

from app import create_app
from test_login_ui import login_browser


@pytest.fixture
def registration_ui(login_browser, monkeypatch):
    monkeypatch.setenv('SECRET_KEY','isolated-signup')
    monkeypatch.setenv('DATABASE_URL','sqlite:///:memory:')
    app=create_app({'TESTING':True})
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    context=login_browser.new_context(viewport={'width':1280,'height':900})
    page=context.new_page()
    ui=SimpleNamespace(page=page,url=f'http://127.0.0.1:{server.server_port}',calls=[],errors=[],fail=False)
    page.on('pageerror',lambda error:ui.errors.append(str(error)))
    def sdk(route):
        if 'firebase-app.js' in route.request.url:
            source='export const initializeApp = config => ({config});'
        else:
            source='''
export const getAuth = app => ({});
export const inMemoryPersistence = {};
export const setPersistence = async () => {};
export const signOut = async () => {window.signedOut=true;};
const credential = () => ({user:{emailVerified:!!window.verified,getIdToken:async()=> 'synthetic-token'}});
export const createUserWithEmailAndPassword = async (auth,email,password) => {
 window.createCalls=(window.createCalls||0)+1;
 if(window.weakPassword) throw {code:'auth/weak-password'};
 if(window.created) throw {code:'auth/email-already-in-use'};
 window.created=true;return credential();
};
export const signInWithEmailAndPassword = async () => {
 window.recoveryCalls=(window.recoveryCalls||0)+1;
 if(window.wrongPassword) throw {code:'auth/invalid-credential'};
 return credential();
};
export const sendEmailVerification = async () => {
 window.mailCalls=(window.mailCalls||0)+1;
 if(window.mailFailure) throw {code:'auth/too-many-requests'};
};
'''
        route.fulfill(body=source,content_type='application/javascript',headers={'Access-Control-Allow-Origin':'*'})
    page.route('https://www.gstatic.com/firebasejs/**',sdk)
    def profile(route):
        ui.calls.append(route.request)
        route.fulfill(status=503 if ui.fail else 200,json={'error':'Could not save your profile; please retry.'} if ui.fail else {'status':'registered','already_processed':False})
    page.route('**/api/auth/register/profile',profile)
    page.goto(ui.url+'/login')
    page.get_by_role('link',name='Create an account',exact=True).click()
    page.get_by_role('link',name='Sign up as Individual',exact=True).click()
    yield ui
    context.close()
    server.shutdown()
    thread.join(timeout=3)
    server.server_close()


def fill(ui):
    for key,value in dict(full_name='Synthetic Member',email='synthetic@example.test',phone='4035550100',
        address='123 Demo Street',city='Calgary',password='synthetic-password',confirm_password='synthetic-password').items():
        ui.page.locator('#'+key).fill(value)


def test_navigation_original_design_and_mobile(registration_ui):
    ui=registration_ui
    assert ui.page.url.endswith('/register/individual')
    assert ui.page.locator('h1').inner_text() == 'Sign up as an Individual'
    assert ui.page.locator('#registration-form input').count() == 7
    assert ui.page.locator('#registration-form button').inner_text() == 'Validate signup details'
    ui.page.set_viewport_size({'width':390,'height':844})
    assert ui.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert not ui.errors


def test_create_member_and_profile_without_verification(registration_ui):
    from playwright.sync_api import expect
    ui=registration_ui;fill(ui)
    ui.page.locator('#registration-form button').evaluate('b=>{b.click();b.click();}')
    expect(ui.page.locator('#page-messages .alert-success')).to_have_text('Registration complete. You can now log in.')
    assert ui.page.evaluate('window.createCalls') == 1
    assert ui.page.evaluate('window.mailCalls||0') == 0
    assert ui.page.locator('#password').input_value() == ''
    assert ui.page.evaluate('window.signedOut')
    ui.page.evaluate('window.verified=true')
    fill(ui);ui.page.locator('#registration-form button').click()
    expect(ui.page.locator('#page-messages .alert-success')).to_have_text('Registration complete. You can now log in.')
    assert ui.page.evaluate('window.recoveryCalls') == 1
    assert len(ui.calls) == 2
    assert ui.calls[0].headers['authorization'] == 'Bearer synthetic-token'
    assert ui.calls[0].post_data_json == dict(full_name='Synthetic Member',phone='4035550100',address='123 Demo Street',city='Calgary')
    assert ui.page.evaluate('Object.keys(localStorage).length') == 0
    assert not ui.errors


def test_password_mismatch_never_creates_account(registration_ui):
    from playwright.sync_api import expect
    ui=registration_ui;fill(ui)
    ui.page.locator('#confirm_password').fill('different-password')
    ui.page.locator('#registration-form button').click()
    expect(ui.page.locator('#confirm_password_error')).to_have_text('Passwords do not match.')
    assert ui.page.evaluate('window.createCalls||0') == 0
    assert ui.calls == []


def test_existing_unverified_account_recovers_without_sending_mail(registration_ui):
    from playwright.sync_api import expect
    ui=registration_ui;fill(ui)
    ui.page.evaluate('window.created=true;window.mailFailure=true')
    ui.page.locator('#registration-form button').click()
    expect(ui.page.locator('#page-messages .alert-success')).to_contain_text('Registration complete')
    assert ui.page.evaluate('window.recoveryCalls') == 1
    assert len(ui.calls)==1 and ui.page.evaluate('window.mailCalls||0')==0


def test_verified_profile_failure_and_retry(registration_ui):
    from playwright.sync_api import expect
    ui=registration_ui;fill(ui)
    ui.page.evaluate('window.created=true;window.verified=true')
    ui.fail=True
    ui.page.locator('#registration-form button').click()
    expect(ui.page.locator('#page-messages .alert-danger')).to_contain_text('Could not save your profile')
    assert ui.page.locator('#password').input_value() == ''
    ui.fail=False;fill(ui)
    ui.page.locator('#registration-form button').click()
    expect(ui.page.locator('#page-messages .alert-success')).to_contain_text('Registration complete')
    assert len(ui.calls) == 2


def test_existing_account_wrong_password_does_not_save_profile(registration_ui):
    from playwright.sync_api import expect
    ui=registration_ui;fill(ui)
    ui.page.evaluate('window.created=true;window.wrongPassword=true')
    ui.page.locator('#registration-form button').click()
    expect(ui.page.locator('#page-messages .alert-danger')).to_have_text('Email or password is incorrect.')
    assert ui.calls == []
