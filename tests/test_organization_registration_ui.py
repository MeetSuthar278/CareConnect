"""Original team organization form; mocked Firebase and API, no emails sent."""
from test_registration_ui import registration_ui
from test_login_ui import login_browser


def organization_form(ui):
    ui.page.goto(ui.url+'/signup')
    ui.page.get_by_role('link',name='Sign up as Organization',exact=True).click()


def fill(ui):
    for key,value in dict(org_name='Synthetic New Partner',address='123 Demo Street',service_area='Calgary NW',
                          city='Calgary',contact_name='Demo Representative',phone='4035550100',
                          email='new-partner@example.test',password='synthetic-password',
                          confirm_password='synthetic-password').items():
        ui.page.locator('#'+key).fill(value)


def test_verification_then_submit_same_account(registration_ui):
    from playwright.sync_api import expect
    ui=registration_ui;organization_form(ui)
    calls=[]
    ui.page.route('**/api/auth/register/organization',lambda route:(calls.append(route.request),
                   route.fulfill(json={'status':'submitted','already_processed':False})))
    assert ui.page.locator('h1').inner_text()=='Sign up as an Organization'
    assert ui.page.locator('#organization-registration-form input').count()==9
    ui.page.set_viewport_size({'width':390,'height':844})
    assert ui.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    fill(ui)
    ui.page.locator('#organization-registration-form button').evaluate('b=>{b.click();b.click();}')
    expect(ui.page.locator('#page-messages')).to_contain_text('Verification email sent.')
    assert not calls and ui.page.evaluate('window.mailCalls')==1
    assert ui.page.evaluate('window.createCalls')==1
    assert ui.page.locator('#password').input_value()==''
    ui.page.evaluate('window.verified=true')
    fill(ui);ui.page.locator('#organization-registration-form button').click()
    expect(ui.page.locator('#page-messages')).to_contain_text('Application submitted.')
    assert ui.page.evaluate('window.recoveryCalls')==1
    assert len(calls)==1
    assert calls[0].headers['authorization']=='Bearer synthetic-token'
    assert 'password' not in calls[0].post_data_json and 'email' not in calls[0].post_data_json
    assert ui.page.evaluate('window.signedOut')
    assert ui.page.evaluate('Object.keys(localStorage).length')==0
    assert not ui.errors


def test_failure_retry_and_password_mismatch(registration_ui):
    from playwright.sync_api import expect
    ui=registration_ui;organization_form(ui);fill(ui)
    ui.page.locator('#confirm_password').fill('different')
    ui.page.locator('#organization-registration-form button').click()
    # The shared team script reports mismatch inline before native form submission.
    expect(ui.page.locator('main')).to_contain_text('Passwords do not match.')
    assert ui.page.evaluate('window.createCalls||0')==0
    ui.page.route('**/api/auth/register/organization',lambda route:route.fulfill(status=409,json={'error':'Existing account preserved.'}))
    ui.page.evaluate('window.verified=true')
    fill(ui);ui.page.locator('#organization-registration-form button').click()
    expect(ui.page.locator('#page-messages')).to_contain_text('Existing account preserved.')
    expect(ui.page.locator('#organization-registration-form button')).to_be_enabled()
    assert ui.page.locator('#org_name').input_value()=='Synthetic New Partner'
    assert ui.page.locator('#password').input_value()==''
    assert not ui.errors
