"""Read-only HTTP smoke of a separate local hosting image against existing MySQL.

No workers, migrations, credential mounts or public interfaces are started.
Private env values are passed by variable name and never printed.
"""
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    from dotenv import load_dotenv
    from sqlalchemy.engine import make_url
    load_dotenv(ROOT / '.env')
    env = os.environ.copy()
    uri = make_url(env['DATABASE_URL'])
    if uri.host in ('127.0.0.1', 'localhost'):
        uri = uri.set(host='host.docker.internal')
    env.update(DATABASE_URL=uri.render_as_string(hide_password=False), HOSTED_MODE='1', FLASK_DEBUG='0')
    names = ['SECRET_KEY', 'DATABASE_URL', 'HOSTED_MODE', 'FLASK_DEBUG', 'FIREBASE_PROJECT_ID',
             'FIREBASE_WEB_API_KEY', 'FIREBASE_AUTH_DOMAIN', 'FIREBASE_STORAGE_BUCKET',
             'FIREBASE_MESSAGING_SENDER_ID', 'FIREBASE_APP_ID', 'RABBITMQ_PASSWORD']
    image = 'careconnect-submission-test:local'
    token = uuid.uuid4().hex
    container = None
    report = {'image': image, 'scope': 'Local Gunicorn/non-root/read-only HTTP image smoke; existing MySQL SELECTs only; no auth writes/workers/public deployment', 'checks': []}
    def docker(*args):
        return subprocess.run(['docker', *args], capture_output=True, text=True, check=True, env=env).stdout.strip()
    try:
        command = ['run', '-d', '--pull=never', '--read-only', '--tmpfs', '/tmp', '--cap-drop=ALL',
                   '--label', 'careconnect.smoke=' + token, '--name', 'careconnect-image-test-' + token[:12],
                   '-p', '127.0.0.1::8000']
        for name in names:
            command += ['-e', name]
        container = docker(*command, image)
        metadata = json.loads(docker('inspect', container))[0]
        port = metadata['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort']
        assert metadata['Config']['User'] == '10001:10001'
        report['checks'].append({'name': 'non-root UID 10001 with read-only root', 'status': 'PASS'})
        for _ in range(100):
            try:
                with urlopen(f'http://127.0.0.1:{port}/health', timeout=2) as response:
                    assert response.status == 200
                break
            except Exception:
                time.sleep(.2)
        for path, expected in [('/health',200),('/health/db',200),('/services',200),('/login',200),
                               ('/team-static/css/style.css',200),('/demo/request',404)]:
            try:
                with urlopen(f'http://127.0.0.1:{port}' + path, timeout=10) as response:
                    code = response.status
            except HTTPError as error:
                code = error.code
            assert code == expected, path + ': unexpected status ' + str(code)
            report['checks'].append({'name': path + ' HTTP ' + str(expected), 'status': 'PASS'})
        report['image_id'] = metadata['Image']
        report['status'] = 'PASS'
        return 0
    except Exception as error:
        report.update(status='FAIL', error_type=type(error).__name__)
        return 1
    finally:
        if container:
            metadata = json.loads(docker('inspect', container))[0]
            assert metadata['Config']['Labels'].get('careconnect.smoke') == token
            docker('rm', '-f', '-v', container)
        report['cleanup'] = True
        (ROOT / 'docs/testing/container_smoke.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
