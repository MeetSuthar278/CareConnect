"""Headless Edge checks on synthetic SQLite fixtures and a local fake Firebase SDK.

No real accounts/emails/tokens or live SQL/broker writes. Requires websocket-client
and project Python dependencies. --venv-site-packages supports system Python.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--venv-site-packages', type=Path)
    args = parser.parse_args()
    if args.venv_site_packages:
        sys.path.insert(0, str(args.venv_site_packages.resolve()))
    sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
    import pytest
    import websocket
    from flask import Response, jsonify, request
    from werkzeug.serving import make_server, WSGIRequestHandler
    from test_list_queries import listing_app
    patch = pytest.MonkeyPatch()
    fixture = listing_app.__wrapped__(patch)
    app = next(fixture)
    calls = []
    @app.before_request
    def fake_backend():
        if request.path.startswith('/api/auth/'):
            calls.append(request.path)
            if request.path.endswith('/profile'):
                return jsonify(status='registered')
            if request.path.endswith('/organization'):
                return jsonify(status='submitted')
            return jsonify(error='Synthetic backend; no account exists', code='registration-required'), 409
    @app.after_request
    def fake_sdk(response):
        if request.path.endswith('/firebase-client.js'):
            response.direct_passthrough = False
            response.set_data(response.get_data(as_text=True).replace(
                'https://www.gstatic.com/firebasejs/12.0.0/', '/synthetic-sdk/'))
        return response
    @app.get('/synthetic-sdk/<name>')
    def sdk(name):
        if name == 'firebase-app.js':
            return Response('export function initializeApp(){return {}}', mimetype='text/javascript')
        return Response('''
const m = globalThis.__mock ||= {created:0, reset:0, sent:0, verified:false, error:null};
const user={email:'synthetic@example.invalid',get emailVerified(){return m.verified},getIdToken:async()=> 'synthetic-token'};
export const inMemoryPersistence={};
export function getAuth(){return {currentUser:user}}
export async function setPersistence(){}
export async function createUserWithEmailAndPassword(){m.created++;if(m.error)throw {code:m.error};return {user}}
export async function signInWithEmailAndPassword(){return {user}}
export async function sendEmailVerification(){m.sent++}
export async function sendPasswordResetEmail(){m.reset++;if(m.error)throw {code:m.error}}
export async function signOut(){}
export async function reload(){}
''', mimetype='text/javascript')
    class QuietHandler(WSGIRequestHandler):
        def log(self, *unused):
            pass
    server = make_server('127.0.0.1', 0, app, request_handler=QuietHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    profile = Path(tempfile.mkdtemp(prefix='careconnect-final-browser-'))
    edge = Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
    child = subprocess.Popen([str(edge), '--headless=new', '--disable-gpu', '--no-first-run',
        '--no-default-browser-check', '--remote-debugging-port=0', '--remote-allow-origins=*',
        '--user-data-dir=' + str(profile), 'about:blank'], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    ws = None
    report = {'environment': 'Headless Edge; synthetic SQLite; fake Firebase SDK; no external email/account mutations',
              'checks': [], 'screenshots': []}
    serial = 0
    errors = []
    def check(label, condition):
        report['checks'].append({'name': label, 'status': 'PASS' if condition else 'FAIL'})
        assert condition, label
    try:
        for _ in range(100):
            if (profile / 'DevToolsActivePort').exists():
                break
            if child.poll() is not None:
                raise RuntimeError('Edge exited before debugger startup')
            time.sleep(.1)
        port = (profile / 'DevToolsActivePort').read_text().splitlines()[0]
        pages = json.load(urlopen(f'http://127.0.0.1:{port}/json'))
        target = next(page for page in pages if page.get('type') == 'page')
        ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=10)
        def cdp(method, **params):
            nonlocal serial
            serial += 1
            message_id = serial
            ws.send(json.dumps({'id': message_id, 'method': method, 'params': params}))
            while True:
                result = json.loads(ws.recv())
                if result.get('method') == 'Runtime.exceptionThrown':
                    errors.append(result['params']['exceptionDetails'].get('text', 'Runtime exception'))
                if result.get('id') == message_id:
                    if 'error' in result:
                        raise RuntimeError(result['error']['message'])
                    return result.get('result', {})
        def js(source):
            if source.startswith('await '):
                source = '(async()=>{' + source + '})()'
            result = cdp('Runtime.evaluate', expression=source, returnByValue=True, awaitPromise=True)
            if result.get('exceptionDetails'):
                raise RuntimeError(str(result['exceptionDetails'].get('exception', {}).get('description', result['exceptionDetails'].get('text'))))
            return result.get('result', {}).get('value')
        def navigate(path):
            # Surface HTTP failures separately from CDP renderer failures.
            if path.startswith('/register/'):
                with urlopen(base + path, timeout=3) as probe:
                    assert probe.status == 200, 'Synthetic server not ready'
            navigation = cdp('Page.navigate', url=base + path)
            if navigation.get('errorText'):
                raise RuntimeError('Navigation failed: ' + navigation['errorText'])
            for _ in range(100):
                time.sleep(.05)
                if js('location.pathname === ' + json.dumps(path.split('?')[0]) + ' && document.readyState === "complete"'):
                    time.sleep(.1)
                    return
            raise RuntimeError('Navigation timeout: ' + path + ' ' + str(js('({url:location.href,state:document.readyState,title:document.title})')))
        cdp('Page.enable')
        cdp('Runtime.enable')
        cdp('Network.enable')
        cases = [('Abc@123', False), ('password123', False), ('Password123', False),
                 ('password@123', False), ('Password@123', True), ('Password@', True),
                 ('PASSWORD@', True), ('', False)]
        for kind in ('individual', 'organization'):
            for password, valid in cases + [('Password@123', False)]:
                navigate('/register/' + kind)
                mismatch = password == 'Password@123' and not valid
                confirmation = 'Different@123' if mismatch else password
                js('''(() => {const values={full_name:'Synthetic Person',contact_name:'Synthetic Person',
org_name:'Synthetic organization',email:'synthetic@example.invalid',phone:'4035550101',address:'Synthetic address',city:'Calgary',service_area:'Calgary'};
const f=document.querySelector('form[id$="registration-form"]');for(const [name,value] of Object.entries(values)){if(f.elements[name])f.elements[name].value=value;}
f.elements.password.value=''' + json.dumps(password) + ';f.elements.confirm_password.value=' + json.dumps(confirmation) + ''';
f.dispatchEvent(new Event('input',{bubbles:true}));f.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));})()''')
                time.sleep(.2)
                created = js('globalThis.__mock?.created || 0')
                check(kind + ' password ' + ('empty' if not password else password) + (' mismatched' if mismatch else ''), created == int(valid))
                if valid:
                    check(kind + ' verification gate', js("!document.getElementById('verification-screen').hidden && document.getElementById('resend-verification').disabled"))
                    before = len(calls)
                    js("document.getElementById('check-verification').click()")
                    time.sleep(.1)
                    check(kind + ' unverified account cannot reach backend', len(calls) == before)
                    check(kind + ' no credential storage', js('localStorage.length === 0 && sessionStorage.length === 0'))
            for code in ('auth/weak-password', 'auth/password-does-not-meet-requirements'):
                navigate('/register/' + kind)
                js("await import('/synthetic-sdk/firebase-auth.js'); __mock.error=" + json.dumps(code))
                js("for(const f of document.querySelectorAll('form[id$=\"registration-form\"] input[required]')) {f.value=f.name.includes('password')?'Password@123':f.type==='email'?'synthetic@example.invalid':f.type==='tel'?'4035550101':'Synthetic Person'};document.querySelector('form[id$=\"registration-form\"]').dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}))")
                time.sleep(.2)
                check(kind + ' friendly Firebase policy rejection ' + code, js("document.getElementById('page-messages').textContent.includes('password was not accepted')"))
        navigate('/login')
        js("document.getElementById('email').value='synthetic@example.invalid';document.getElementById('password-reset').click()")
        time.sleep(.2)
        check('password reset request and non-enumerating message', js("__mock.reset===1 && document.getElementById('page-messages').textContent.includes('If an account')"))
        js("document.getElementById('password-reset').click()")
        check('password reset cooldown', js('__mock.reset===1'))
        navigate('/login')
        js("await import('/synthetic-sdk/firebase-auth.js');__mock.error='auth/user-not-found';document.getElementById('email').value='unknown@example.invalid';document.getElementById('password-reset').click()")
        time.sleep(.1)
        check('unknown reset account receives same result', js("document.getElementById('page-messages').textContent.includes('If an account')"))
        syntax = 0
        for file in sorted((ROOT / 'frontend/static/js').glob('*.js')):
            source = re.sub(r'^import\s+.*?;\s*$', '', file.read_text(encoding='utf-8'), flags=re.M)
            source = re.sub(r'\bexport\s+(?=(?:async\s+)?function|const|let|class)', '', source)
            result = cdp('Runtime.compileScript', expression=source, sourceURL=file.name, persistScript=False)
            check('JavaScript syntax ' + file.name, not result.get('exceptionDetails'))
            syntax += 1
        report['javascript_files_parsed'] = syntax
        role_paths = {'public': ['/', '/services', '/register/individual', '/register/organization', '/login', '/register/verify', '/get-connected'],
                      'member': ['/member', '/member/requests', '/member/profile'],
                      'organization': ['/organization', '/organization/requests', '/organization/services', '/organization/profile'],
                      'coordinator': ['/coordinator', '/coordinator/requests', '/coordinator/organizations', '/coordinator/approvals', '/coordinator/reports']}
        for width in (390, 1280):
            cdp('Emulation.setDeviceMetricsOverride', width=width, height=900, deviceScaleFactor=1, mobile=width<600)
            for role, paths in role_paths.items():
                cdp('Network.clearBrowserCookies')
                if role != 'public':
                    cdp('Network.setCookie', name='careconnect_' + role, value=role, url=base)
                for path in paths:
                    navigate(path)
                    check(f'{role} {path} viewport {width}', js('document.documentElement.scrollWidth <= innerWidth && !!document.querySelector("h1")'))
                if role in ('public', 'coordinator'):
                    screenshot = cdp('Page.captureScreenshot', format='png')['data']
                    path = profile / f'{role}-{width}.png'
                    path.write_bytes(base64.b64decode(screenshot))
                    report['screenshots'].append(str(path))
        check('no uncaught browser exceptions', not errors)
        report['status'] = 'PASS'
    except Exception as error:
        report['status'] = 'FAIL'
        report['error'] = str(error)
        raise
    finally:
        if ws:
            ws.close()
        child.terminate()
        child.wait(timeout=10)
        server.shutdown()
        try:
            next(fixture)
        except StopIteration:
            pass
        patch.undo()
        report['passed'] = sum(item['status']=='PASS' for item in report['checks'])
        (ROOT / 'docs/testing/browser_smoke.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'status': report.get('status'), 'passed': report['passed'], 'screenshots': report['screenshots']}))


if __name__ == '__main__':
    main()
