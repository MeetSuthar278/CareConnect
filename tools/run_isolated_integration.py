"""Run opt-in integration tests on disposable Docker services, never on .env data.

Requires cached mysql:8.0 and rabbitmq:3.13-management images. Only containers
created by this invocation are removed. No named volumes or existing queues used.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def docker(*args, **kwargs):
    return subprocess.run(['docker', *args], check=True, capture_output=True,
                          text=True, **kwargs).stdout.strip()


def main():
    token = uuid.uuid4().hex[:12]
    owned = []
    report = {'isolation': 'New Docker containers; random localhost ports; no existing volumes/data/queues',
              'steps': [], 'cleanup': False}
    env = os.environ.copy()
    env['MYSQL_ROOT_PASSWORD'] = secrets.token_urlsafe(32)
    env['RABBITMQ_DEFAULT_USER'] = 'integration'
    env['RABBITMQ_DEFAULT_PASS'] = secrets.token_urlsafe(32)
    try:
        for image, suffix, port, variables in (
            ('mysql:8.0', 'mysql', '3306', ['MYSQL_ROOT_PASSWORD', 'MYSQL_ROOT_HOST=%']),
            ('rabbitmq:3.13-management', 'rabbit', '5672',
             ['RABBITMQ_DEFAULT_USER', 'RABBITMQ_DEFAULT_PASS'])):
            docker('image', 'inspect', image)  # Do not pull or change installed versions.
            args = ['run', '-d', '--pull=never', '--label', f'careconnect.test={token}',
                    '--name', f'careconnect-test-{token}-{suffix}',
                    '-p', f'127.0.0.1::{port}']
            for variable in variables:
                args.extend(['-e', variable])
            container = docker(*args, image, env=env)
            owned.append(container)
        mysql_id, rabbit_id = owned
        mysql_port = json.loads(docker('inspect', mysql_id))[0]['NetworkSettings']['Ports']['3306/tcp'][0]['HostPort']
        rabbit_port = json.loads(docker('inspect', rabbit_id))[0]['NetworkSettings']['Ports']['5672/tcp'][0]['HostPort']
        env.update(CC_ISOLATED_INTEGRATION='1', CC_TEST_MYSQL_CONTAINER=mysql_id,
                   DATABASE_URL=f'mysql+pymysql://root:{env["MYSQL_ROOT_PASSWORD"]}@127.0.0.1:{mysql_port}/careconnect_db',
                   RABBITMQ_HOST='127.0.0.1', RABBITMQ_PORT=rabbit_port,
                   RABBITMQ_USER='integration', RABBITMQ_PASSWORD=env['RABBITMQ_DEFAULT_PASS'],
                   RABBITMQ_VHOST='/', SECRET_KEY=secrets.token_urlsafe(32),
                   HOSTED_MODE='0', FLASK_DEBUG='0', PYTHONUNBUFFERED='1')
        import pymysql
        import pika
        for service in ('mysql', 'rabbitmq'):
            deadline = time.monotonic() + 120
            while True:
                try:
                    if service == 'mysql':
                        connection = pymysql.connect(host='127.0.0.1', port=int(mysql_port), user='root',
                                                     password=env['MYSQL_ROOT_PASSWORD'], connect_timeout=2)
                    else:
                        connection = pika.BlockingConnection(pika.ConnectionParameters(
                            host='127.0.0.1', port=int(rabbit_port),
                            credentials=pika.PlainCredentials('integration', env['RABBITMQ_DEFAULT_PASS']),
                            socket_timeout=2, stack_timeout=3))
                    connection.close()
                    break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(service + ' startup') from None
                    time.sleep(2)
            report['steps'].append({'name': service + ' isolated readiness', 'status': 'PASS'})
            print('PASS isolated ' + service + ' ready', flush=True)
        result = subprocess.run([sys.executable, '-m', 'pytest', 'tests/integration', '-q',
                                 '--junitxml=docs/testing/isolated_integration.junit.xml'],
                                cwd=ROOT, env=env)
        report['pytest_exit_code'] = result.returncode
        report['status'] = 'PASS' if result.returncode == 0 else 'FAIL'
        return result.returncode
    except Exception as error:
        # Docker errors may contain private env strings: only print their type.
        report.update(status='FAIL', error_type=type(error).__name__)
        print('FAIL isolated integration infrastructure (' + type(error).__name__ + ')', flush=True)
        return 1
    finally:
        removed = []
        for container in reversed(owned):
            try:
                # Full IDs returned by this run, plus its ownership label.
                metadata = json.loads(docker('inspect', container))[0]
                if metadata['Config']['Labels'].get('careconnect.test') != token:
                    raise RuntimeError('Container ownership mismatch')
                docker('rm', '-f', '-v', container)
                removed.append(container)
            except Exception as error:
                print('FAIL test-container cleanup (' + type(error).__name__ + ')', flush=True)
        report['cleanup'] = len(removed) == len(owned)
        (ROOT / 'docs/testing/isolated_integration.json').write_text(
            json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
