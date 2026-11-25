"""All current team pages: render and follow navigation without business POSTs."""
from contextlib import ExitStack
from html.parser import HTMLParser
from pathlib import Path
import threading
from urllib.parse import urlsplit,unquote
from unittest.mock import patch

import pytest
from flask import template_rendered,session
from sqlalchemy import text
from werkzeug.exceptions import MethodNotAllowed
from werkzeug.serving import make_server

from app import create_app
from conftest import LocalSession
from test_coordinator_workflow import coordinator_engine
from test_organization_workflow import org_engine
from test_member_workflow import member_engine
from test_login_ui import login_browser


class PageLinks(HTMLParser):
    def __init__(self,html):
        super().__init__()
        self.links=[];self.assets=[];self.forms=[];self.ids=set();self.active=[]
        self.feed(html)

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if attrs.get('id'):
            self.ids.add(attrs['id'])
        if tag=='a' and attrs.get('href'):
            self.links.append(attrs['href'])
            if attrs.get('aria-current')=='page':
                self.active.append(attrs['href'])
        if tag in {'script','link'}:
            src=attrs.get('src') if tag=='script' else attrs.get('href')
            if src:
                self.assets.append(src)
        if tag=='form':
            self.forms.append((attrs.get('action',''),attrs.get('method','get').upper()))


ROLE_COOKIES={'member':('careconnect_member','audit-member'),
              'organization':('careconnect_organization','audit-rep'),
              'coordinator':('careconnect_coordinator','audit-coordinator')}
PAGES={
    'guest':['/','/?guest=1','/login','/signup','/register/individual','/register/organization',
             '/services','/services/1','/get-connected','/get-connected/done/CC-19'],
    'member':['/','/member','/member/requests','/member/requests/1','/member/requests/15',
              '/member/requests/17','/member/requests/17/feedback','/member/profile',
              '/services','/services/1','/get-connected','/get-connected/done/CC-1'],
    'organization':['/','/organization','/organization/requests','/organization/requests/1',
                    '/organization/requests/16','/organization/requests/17','/organization/services',
                    '/organization/profile','/services','/services/1'],
    'coordinator':['/','/coordinator','/coordinator/approvals','/coordinator/organizations',
                   '/coordinator/requests','/coordinator/reports','/services','/services/1'],
}


@pytest.fixture
def audit_engine(coordinator_engine):
    with coordinator_engine.begin() as connection:
        for sql in [
            "ALTER TABLE organizations ADD COLUMN address TEXT DEFAULT 'Synthetic street'",
            'ALTER TABLE organizations ADD COLUMN created_at DATETIME',
            "ALTER TABLE organization_representatives ADD COLUMN phone TEXT DEFAULT '4035550100'",
            "ALTER TABLE services ADD COLUMN description TEXT DEFAULT 'Synthetic support'",
            'ALTER TABLE feedback ADD COLUMN member_id INTEGER DEFAULT 9',
            'ALTER TABLE feedback ADD COLUMN comment TEXT',
            '''CREATE TABLE organization_availability(availability_id INTEGER PRIMARY KEY,
                organization_service_id INTEGER,action TEXT,recorded_at DATETIME,recorded_by_user_id INTEGER)''',
            "UPDATE service_requests SET attendance_deadline='2099-01-01' WHERE request_id=14",
            "INSERT INTO users(user_id,role_id,email,is_active) VALUES(12,1,'guest-audit@example.test',1)",
            "INSERT INTO member_profiles(user_id,first_name,last_name,phone,address,city) VALUES(12,'Synthetic','Guest','4035550100','Demo street','Calgary')",
            """INSERT INTO service_requests(request_id,member_id,service_id,service_area_id,priority_id,title,status,attendance_deadline)
                VALUES(17,9,1,1,1,'Completed for feedback','completed','2099-01-01'),
                      (19,12,1,1,1,'Guest receipt','submitted','2099-01-01')""",
            """INSERT INTO referrals(referral_id,request_id,organization_id,attempt_number,is_backup,status,response_deadline)
                VALUES(17,17,1,1,0,'completed','2099-01-01')""",
            """INSERT INTO service_completions(completion_id,request_id,referral_id,completed_at,outcome)
                VALUES(17,17,17,'2000-01-01','successful')""",
        ]:
            connection.execute(text(sql))
    return coordinator_engine


@pytest.fixture
def audit_app(audit_engine):
    app=create_app({'TESTING':True,'HOSTED_MODE':False,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with ExitStack() as stack:
        for module in ('frontend','member','organization','coordinator','requests'):
            stack.enter_context(patch('app.'+module+'.Session',side_effect=lambda unused:LocalSession(audit_engine)))
        stack.enter_context(patch('app.member.cookie_claims',return_value={'uid':'synthetic-member'}))
        stack.enter_context(patch('app.organization.cookie_claims',return_value={'uid':'synthetic-representative','email_verified':True}))
        stack.enter_context(patch('app.coordinator.cookie_claims',return_value={'uid':'synthetic-coordinator','email_verified':True}))
        yield app


def make_client(app,role):
    client=app.test_client()
    if role in ROLE_COOKIES:
        client.set_cookie(*ROLE_COOKIES[role])
    else:
        with client.session_transaction() as session:
            session['guest_member_id']=12
    return client


@pytest.mark.parametrize('role',list(PAGES))
def test_every_rendered_page_link_asset_anchor_and_form(audit_app,audit_engine,role):
    client=make_client(audit_app,role)
    adapter=audit_app.url_map.bind('localhost')
    rendered=set();urls=set();assets=set();forms=set();missing_active=[]
    def track(sender,template,context,**extra):
        rendered.add(template.name)
    tables=('users','member_profiles','organizations','organization_services','referrals',
            'service_requests','feedback','notifications','event_outbox')
    def snapshot():
        with audit_engine.connect() as connection:
            return {table:connection.execute(text('SELECT * FROM '+table)).all() for table in tables}
    before=snapshot()
    template_rendered.connect(track,audit_app,weak=False)
    try:
        for origin in PAGES[role]:
            response=client.get(origin)
            assert response.status_code==200,(role,origin,response.status_code)
            html=response.get_data(as_text=True);page=PageLinks(html)
            path=urlsplit(origin).path
            expected=None
            for prefix in ('/member/requests','/organization/requests','/coordinator/requests','/services'):
                if path==prefix or path.startswith(prefix+'/'):
                    expected=prefix
                    break
            if path.startswith('/get-connected') and role=='member':
                expected='/get-connected'
            if expected is None and path.startswith(('/member','/organization','/coordinator')):
                expected=path
            # Organization/coordinator menus do not contain public Services links.
            if expected=='/services' and role in {'organization','coordinator'}:
                expected=None
            if role=='guest' and path=='/':
                expected=None if origin=='/' else '/'
            assert page.active==([expected] if expected else []),(role,origin,page.active,expected)
            for href in page.links:
                parsed=urlsplit(href)
                if parsed.scheme or parsed.netloc:
                    continue
                if not parsed.path:
                    assert not parsed.fragment or unquote(parsed.fragment) in page.ids,(origin,href)
                    continue
                target=parsed.path+('?' + parsed.query if parsed.query else '')
                # These links log out synthetic users; exercise them separately.
                if parsed.path.endswith('/logout') or parsed.path=='/logout':
                    assert adapter.match(parsed.path,method='GET')
                    continue
                linked=client.get(target)
                assert linked.status_code==200,(role,origin,href,linked.status_code)
                if parsed.fragment:
                    assert unquote(parsed.fragment) in PageLinks(linked.get_data(as_text=True)).ids,(origin,href)
                urls.add(target)
            for asset in page.assets:
                parsed=urlsplit(asset)
                if parsed.scheme or parsed.netloc:
                    continue
                assert client.get(asset).status_code==200,(origin,asset)
                assets.add(asset)
            for action,method in page.forms:
                target=urlsplit(action or origin).path
                try:
                    adapter.match(target,method=method)
                except MethodNotAllowed:
                    # These existing forms are intentionally intercepted by their
                    # Firebase JS modules; native credential POST is not accepted.
                    js={'/login':'js/login.js','/register/individual':'js/register.js',
                        '/register/organization':'js/register-organization.js'}
                    assert method=='POST' and target in js and js[target] in html,(origin,action,method)
                forms.add((target,method))
        assert snapshot()==before,'Navigation must not mutate business data'
        print(f'\nAUDIT {role}: {len(PAGES[role])} page states, {len(urls)} linked URLs, '
              f'{len(assets)} local assets, {len(forms)} form destinations; templates={sorted(rendered)}; '
              f'active-menu markers missing={missing_active}')
    finally:
        template_rendered.disconnect(track,audit_app)


@pytest.mark.parametrize('role',['member','organization','coordinator'])
def test_each_role_logout_link(audit_app,role):
    client=make_client(audit_app,role)
    home={'member':'/member','organization':'/organization','coordinator':'/coordinator'}[role]
    links=PageLinks(client.get(home).get_data(as_text=True)).links
    logout=next(url for url in links if '/logout?' in url)
    response=client.get(logout)
    assert response.status_code==302 and response.location=='/login'
    assert client.get(home).status_code==302


def test_guest_cannot_open_role_pages(audit_app):
    client=make_client(audit_app,'guest')
    for page in ['/member','/member/profile','/member/requests','/organization','/organization/profile',
                 '/organization/requests','/organization/services','/coordinator','/coordinator/approvals',
                 '/coordinator/organizations','/coordinator/requests','/coordinator/reports']:
        response=client.get(page)
        assert response.status_code==302 and response.location=='/login',page


def test_auth_javascript_destinations_registered(audit_app):
    adapter=audit_app.url_map.bind('localhost')
    for path,method in [('/api/auth/me','GET'),('/api/auth/session','POST'),
                        ('/api/auth/organization-session','POST'),('/api/auth/coordinator-session','POST'),
                        ('/api/auth/register/profile','POST'),('/api/auth/register/organization','POST')]:
        assert adapter.match(path,method=method)
    assert len(list(Path('frontend/templates').glob('auth/*.html')))==4


def test_role_boundaries_and_unapproved_service_redirect(audit_app,audit_engine):
    roots={'member':'/member','organization':'/organization','coordinator':'/coordinator'}
    for role in roots:
        client=make_client(audit_app,role)
        for other,path in roots.items():
            if other!=role:
                assert client.get(path).status_code==302,(role,path)
    for status in ('pending','suspended'):
        with audit_engine.begin() as connection:
            connection.execute(text('UPDATE organizations SET status=:status WHERE organization_id=1'),{'status':status})
        client=make_client(audit_app,'organization')
        for path in ('/organization','/organization/requests','/organization/profile'):
            assert client.get(path).status_code==200
        blocked=client.get('/organization/services')
        assert blocked.status_code==302 and blocked.location=='/organization'


@pytest.mark.parametrize('role',list(PAGES))
def test_mobile_navbar_links_in_real_browser(audit_app,login_browser,role):
    from playwright.sync_api import expect
    server=make_server('127.0.0.1',0,audit_app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    context=login_browser.new_context(viewport={'width':390,'height':844})
    if role in ROLE_COOKIES:
        name,value=ROLE_COOKIES[role]
        context.add_cookies([dict(name=name,value=value,url=base)])
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    start={'guest':'/?guest=1','member':'/member','organization':'/organization','coordinator':'/coordinator'}[role]
    try:
        page.goto(base+start)
        targets=page.locator('nav a.nav-link').evaluate_all('links=>links.map(a=>({label:a.textContent.trim(),href:a.getAttribute("href")}))')
        assert targets
        for target in targets:
            # Home intentionally returns a guest to the entry landing page;
            # start each independent menu click from the chosen guest/role entry.
            page.goto(base+start)
            toggle=page.get_by_role('button',name='Toggle navigation')
            toggle.click()
            link=page.locator('nav').get_by_role('link',name=target['label'],exact=True)
            expect(link).to_be_visible()
            link.click()
            expect(page).to_have_url(base+target['href'])
            assert page.locator('main h1').count()==1
            if not (role=='guest' and target['href']=='/'):
                expect(page.locator('nav a[aria-current="page"]')).to_have_count(1)
                expect(page.locator('nav a[aria-current="page"]')).to_have_attribute('href',target['href'])
        assert not errors
        print(f'\nBROWSER {role}: clicked {len(targets)} mobile navbar links, no JavaScript errors')
    finally:
        context.close();server.shutdown();thread.join(timeout=3);server.server_close()


@pytest.mark.parametrize('path,role,expected',[
    ('/api/member/requests','individual','/get-connected'),
    ('/organization/services/add','organization','/organization/services'),
    ('/organization/services/1/availability','organization','/organization/services'),
])
def test_error_form_urls_keep_parent_menu(audit_app,path,role,expected):
    from app.frontend import render_team
    # Render only navigation under its POST request context; submit no business form.
    with audit_app.test_request_context(path,method='POST'):
        session['role']=role
        assert PageLinks(render_team('components/navbar.html')).active==[expected]
