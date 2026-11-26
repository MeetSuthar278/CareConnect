"""Read the live policy with the actual browser SDK; never create/sign in users.

Requires Edge, websocket-client and the application dependencies. System Python
can use --venv-site-packages .venv/Lib/site-packages. Only known sample passwords
are evaluated in browser memory. Firebase mutation requests are blocked by CDP.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
CASES = [('Abc@123', False), ('password123', False), ('Password123', False),
         ('password@123', False), ('Password@123', True), ('Password@', True),
         ('PASSWORD@', True), ('PASSWORD-', True), ('PASSWORD`', True), ('', False)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--venv-site-packages', type=Path)
    args = parser.parse_args()
    if args.venv_site_packages:
        sys.path.insert(0, str(args.venv_site_packages.resolve()))
    sys.path.insert(0, str(ROOT))
    import websocket
    from app import create_app
    from werkzeug.serving import make_server, WSGIRequestHandler
    app = create_app()
    class QuietHandler(WSGIRequestHandler):
        def log(self, *unused):
            pass
    server = make_server('127.0.0.1', 0, app, request_handler=QuietHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    profile = Path(tempfile.mkdtemp(prefix='careconnect-live-policy-'))
    edge = Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
    child = subprocess.Popen([str(edge), '--headless=new', '--disable-gpu', '--no-first-run',
        '--no-default-browser-check', '--remote-debugging-port=0', '--remote-allow-origins=*',
        '--user-data-dir=' + str(profile), 'about:blank'], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    ws = None
    report = {'project': app.config['FIREBASE_PROJECT_ID'],
              'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'method': 'Firebase Web SDK 12.0.0 validatePassword against live project policy; no sign-up/sign-in/password mutation',
              'account_write_requests_blocked': 0, 'policy_requests': [], 'cases': []}
    serial = 0
    def send(method, params):
        nonlocal serial
        serial += 1
        ws.send(json.dumps({'id': serial, 'method': method, 'params': params}))
        return serial
    def cdp(method, **params):
        message_id = send(method, params)
        while True:
            result = json.loads(ws.recv())
            if result.get('method') == 'Fetch.requestPaused':
                event = result['params']
                request = event['request']
                parsed = urlsplit(request['url'])
                if request['method'] not in ('GET', 'OPTIONS') or parsed.path != '/v2/passwordPolicy':
                    report['account_write_requests_blocked'] += 1
                    report.setdefault('blocked_requests', []).append({'method': request['method'], 'host': parsed.hostname, 'path': parsed.path})
                    send('Fetch.failRequest', {'requestId': event['requestId'], 'errorReason': 'BlockedByClient'})
                else:
                    report['policy_requests'].append({'method': request['method'], 'host': parsed.hostname, 'path': parsed.path})
                    send('Fetch.continueRequest', {'requestId': event['requestId']})
            if result.get('id') == message_id:
                if 'error' in result:
                    raise RuntimeError('Browser protocol failure')
                return result.get('result', {})
    def js(source):
        result = cdp('Runtime.evaluate', expression=source, returnByValue=True, awaitPromise=True)
        if result.get('exceptionDetails'):
            # SDK exception descriptions may contain API-key URLs: never print.
            raise RuntimeError('Browser SDK policy validation failed')
        return result.get('result', {}).get('value')
    try:
        for _ in range(150):
            if (profile / 'DevToolsActivePort').exists():
                break
            if child.poll() is not None:
                raise RuntimeError('Edge exited before debugger startup')
            time.sleep(.1)
        port = (profile / 'DevToolsActivePort').read_text().splitlines()[0]
        pages = json.load(urlopen(f'http://127.0.0.1:{port}/json'))
        target = next(page for page in pages if page.get('type') == 'page')
        ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=45)
        cdp('Page.enable')
        cdp('Runtime.enable')
        cdp('Fetch.enable', patterns=[
            {'urlPattern': '*identitytoolkit.googleapis.com/*', 'requestStage': 'Request'},
            {'urlPattern': '*securetoken.googleapis.com/*', 'requestStage': 'Request'}])
        with urlopen(base + '/register/individual', timeout=5) as probe:
            assert probe.status == 200
        navigation = cdp('Page.navigate', url=base + '/register/individual')
        if navigation.get('errorText'):
            raise RuntimeError('Local page navigation failed')
        for _ in range(100):
            if js("location.pathname==='/register/individual' && document.readyState==='complete'"):
                break
            time.sleep(.1)
        result = js('''(async()=>{
const {firebase}=await import('/team-static/js/firebase-client.js');
const {passwordValidationMessage}=await import('/team-static/js/registration-password.js');
const {auth,sdk}=await firebase();
const output=[];
for(const [password,expected] of ''' + json.dumps(CASES) + '''){
 const status=await sdk.validatePassword(auth,password);
 output.push({sample:password||'(empty)',expected,sdk_is_valid:status.isValid,
  app_is_valid:!passwordValidationMessage(password,password),policy:status.passwordPolicy});
}
return {cases:output,signed_in:auth.currentUser!==null,
 mismatch_rejected:!!passwordValidationMessage('Password@123','Different@123'),
 empty_confirmation_rejected:!!passwordValidationMessage('Password@123','')};})()''')
        assert result['signed_in'] is False
        assert result['mismatch_rejected'] and result['empty_confirmation_rejected']
        for row in result['cases']:
            policy = row.pop('policy')
            report['sdk_policy'] = policy
            row['status'] = 'PASS' if row['sdk_is_valid'] == row['expected'] == row['app_is_valid'] else 'FAIL'
            report['cases'].append(row)
        report.update(mismatch_rejected=True, empty_confirmation_rejected=True, signed_in=False)
        assert report['account_write_requests_blocked'] == 0
        assert any(row['path'] == '/v2/passwordPolicy' for row in report['policy_requests'])
        assert all(row['status'] == 'PASS' for row in report['cases'])
        report['status'] = 'PASS'
        return 0
    except Exception as error:
        report.update(status='FAIL', error_type=type(error).__name__)
        return 1
    finally:
        if ws:
            ws.close()
        child.terminate()
        child.wait(timeout=10)
        server.shutdown()
        (ROOT / 'docs/testing/firebase_password_policy.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
