"""Local process supervisor. Never provisions SQL, broker topology or Firebase users."""
import argparse
from contextlib import contextmanager
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WORKERS = [('matching', ['worker.py']), ('notifications', ['notification_worker.py']),
           ('sla', ['sla_worker.py']), ('coordinator', ['coordinator_worker.py']),
           ('feedback', ['feedback_worker.py']), ('outbox', ['outbox_dispatcher.py']),
           ('acceptance', ['deadline_checker.py', '--kind', 'acceptance', '--apply']),
           ('attendance', ['deadline_checker.py', '--kind', 'attendance', '--apply'])]


@contextmanager
def exclusive_lock(path):
    stream = path.open('a+b')
    try:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        stream.close()  # OS releases the lock even after an interrupted process.


def control(state_dir, action='status'):
    state = json.loads((state_dir / 'runtime.json').read_text(encoding='utf-8'))
    request = Request(f'http://127.0.0.1:{int(state["control_port"])}/{action}',
                      headers={'Authorization': 'Bearer ' + state['token']},
                      method='POST' if action == 'stop' else 'GET')
    with urlopen(request, timeout=3) as response:
        return json.load(response)


def preflight(port, process_pending=False):
    from app import create_app, db
    from app.frontend import firebase_web_config
    from app.member import firebase_app
    from app.messaging.rabbitmq_config import EXCHANGE_NAME, QUEUE_BINDINGS
    from app.messaging.rabbitmq_connection import get_rabbitmq_connection
    from deploy.check_schema import verify
    from sqlalchemy import text
    for name in ('SECRET_KEY', 'DATABASE_URL', 'FIREBASE_PROJECT_ID', 'RABBITMQ_HOST',
                 'RABBITMQ_PORT', 'RABBITMQ_USER', 'RABBITMQ_PASSWORD'):
        if not os.getenv(name):
            raise RuntimeError('Missing environment variable: ' + name)
    result = subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Docker is unavailable; start Docker Desktop and check access')
    print('PASS Docker running; existing containers: ' + str(len(result.stdout.splitlines())), flush=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))  # Never replace a listener occupying this port.
    app = create_app()
    with app.app_context():
        with app.test_request_context('/login'):
            config = firebase_web_config()
        if config['projectId'] != app.config['FIREBASE_PROJECT_ID']:
            raise RuntimeError('Firebase project mismatch')
        if firebase_app().project_id != config['projectId']:
            raise RuntimeError('Firebase Admin project mismatch')
        verify(db.engine)
        with db.engine.connect() as connection:
            pending = connection.execute(text('SELECT COUNT(*) FROM event_outbox WHERE published_at IS NULL')).scalar_one()
        from sqlalchemy.orm import Session
        from app.services.timeouts import expired_referral_ids
        from app.services.overdue import overdue_request_ids
        with Session(db.engine) as session:
            deadlines = len(expired_referral_ids(session, 1000)) + len(overdue_request_ids(session, 1000))
        print(f'Deadline candidates awaiting processing: {deadlines}', flush=True)
        pending += deadlines
        print('PASS MySQL schema and Firebase configuration', flush=True)
    connection = get_rabbitmq_connection()
    try:
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE_NAME, passive=True)
        for name in QUEUE_BINDINGS:
            method = channel.queue_declare(queue=name, passive=True).method
            print(f'PASS {name}: {method.consumer_count} consumers, {method.message_count} ready messages', flush=True)
            if method.consumer_count:
                raise RuntimeError('An existing consumer is active; preserve it and avoid duplicate workers')
            pending += method.message_count
    finally:
        connection.close()
    if pending and not process_pending:
        raise RuntimeError('Pending work exists. Review it, then use -ProcessPending to authorize normal processing')
    # An external scheduler/outbox has no consumer subscription. Inspect commands
    # without printing any command lines, env values or unrelated process details.
    if os.name == 'nt':
        command = "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?(.exe)?$' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
        result = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Cannot verify scheduler processes; inspect Windows process permissions')
        processes = json.loads(result.stdout or '[]')
        if isinstance(processes, dict):
            processes = [processes]
        for process in processes:
            line = (process.get('CommandLine') or '').lower()
            if any(name in line for name in ('outbox_dispatcher.py', 'deadline_checker.py')):
                raise RuntimeError('Existing outbox/deadline process detected; no duplicate launched')


def serve(args):
    state_dir = args.state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    children, handles = {}, []
    stopping = threading.Event()
    token = secrets.token_urlsafe(32)
    server = None
    with exclusive_lock(state_dir / 'runtime.lock'):
        try:
            preflight(args.port, args.process_pending)
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *unused):
                    pass

                def authorized(self):
                    return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)

                def do_GET(self):
                    if not self.authorized() or self.path != '/status':
                        self.send_error(403)
                        return
                    body = json.dumps({'running': not stopping.is_set(), 'web_port': args.port,
                                       'processes': {name: child.poll() is None for name, child in children.items()}}).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def do_POST(self):
                    if not self.authorized() or self.path != '/stop':
                        self.send_error(403)
                        return
                    stopping.set()
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"stopping":true}')

            jobs = [('web', ['-m', 'flask', '--app', 'app:create_app', 'run', '--host', '127.0.0.1',
                             '--port', str(args.port), '--no-reload', '--no-debugger']), *WORKERS]
            environment = os.environ.copy()
            environment.update(FLASK_DEBUG='0', PYTHONUNBUFFERED='1')
            for name, command in jobs:
                handle = (state_dir / (name + '.log')).open('a', encoding='utf-8')
                handles.append(handle)
                children[name] = subprocess.Popen([sys.executable, *command], cwd=ROOT, env=environment,
                    stdout=handle, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            (state_dir / 'runtime.json').write_text(json.dumps({'control_port': server.server_port,
                                                               'token': token}), encoding='utf-8')
            while not stopping.wait(.5):
                if any(child.poll() is not None for child in children.values()):
                    raise RuntimeError('A managed process exited; review .local logs')
        finally:
            # Popen handles belong to this invocation, never PID-based global kills.
            for child in reversed(list(children.values())):
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
            if server:
                server.shutdown()
                server.server_close()
            for handle in handles:
                handle.close()
            (state_dir / 'runtime.json').unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'serve', 'stop', 'health'))
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--state-dir', type=Path, default=ROOT / '.local')
    parser.add_argument('--process-pending', action='store_true')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be from 1 to 65535')
    args.state_dir = args.state_dir.resolve()
    try:
        if args.action == 'serve':
            serve(args)
        elif args.action == 'health':
            # Full read-only checks first; no worker starts in a health command.
            result = subprocess.run([sys.executable, 'tools/check_submission_readiness.py', '--database', '--rabbitmq'], cwd=ROOT)
            if result.returncode:
                return result.returncode
            try:
                status = control(args.state_dir)
                print('Managed processes: ' + str(sum(status['processes'].values())) + '/9')
                with urlopen(f'http://127.0.0.1:{int(status["web_port"])}/health/db', timeout=5) as response:
                    assert response.status == 200
                return 0 if all(status['processes'].values()) and status['running'] else 1
            except (FileNotFoundError, ConnectionError, OSError):
                print('NOT RUNNING: start with scripts/start_local.ps1')
                return 1
        elif args.action == 'stop':
            try:
                control(args.state_dir, 'stop')
            except (FileNotFoundError, ConnectionError, OSError):
                print('No reachable managed runtime; unrelated processes were not touched')
                return 1
            for _ in range(150):
                if not (args.state_dir / 'runtime.json').exists():
                    print('Stopped managed application processes; database/broker containers preserved')
                    return 0
                time.sleep(.2)
            raise RuntimeError('Managed shutdown is still in progress; inspect logs')
        else:
            args.state_dir.mkdir(parents=True, exist_ok=True)
            try:
                control(args.state_dir)
                print('Already running; no duplicate processes started')
                return 0
            except (FileNotFoundError, ConnectionError, OSError):
                pass
            log = (args.state_dir / 'supervisor.log').open('a', encoding='utf-8')
            command = [sys.executable, str(Path(__file__).resolve()), 'serve', '--port', str(args.port),
                       '--state-dir', str(args.state_dir)]
            if args.process_pending:
                command.append('--process-pending')
            supervisor = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            log.close()
            for _ in range(150):
                if supervisor.poll() is not None:
                    raise RuntimeError('Startup failed; review .local/supervisor.log (no reset attempted)')
                try:
                    status = control(args.state_dir)
                    with urlopen(f'http://127.0.0.1:{args.port}/health/db', timeout=1) as response:
                        if response.status == 200 and len(status['processes']) == 9 and all(status['processes'].values()):
                            print(f'CareConnect running at http://127.0.0.1:{args.port}; 9 managed processes')
                            return 0
                except (FileNotFoundError, ConnectionError, OSError):
                    pass
                time.sleep(.2)
            try:
                control(args.state_dir, 'stop')
            except Exception:
                pass
            raise RuntimeError('Startup timed out; review supervisor log')
        return 0
    except Exception as error:
        # Fixed RuntimeError descriptions are safe; unexpected library exceptions
        # can contain credentials/URLs and must be reduced to their class name.
        print('FAIL: ' + (str(error) if isinstance(error, RuntimeError) else type(error).__name__))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
