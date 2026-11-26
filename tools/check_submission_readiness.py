"""Read-only startup checks. Service checks are explicit; no setup or migrations.

    python tools/check_submission_readiness.py
    python tools/check_submission_readiness.py --database --rabbitmq

Never prints environment values, credentials, ID tokens, email addresses or UIDs.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', action='store_true', help='Read schema and aggregate UID-mapping counts')
    parser.add_argument('--rabbitmq', action='store_true', help='Passively check existing exchange and queues')
    args = parser.parse_args(argv)
    failures = []

    def check(name, action):
        try:
            detail = action()
            print(f'PASS {name}' + (f': {detail}' if detail else ''))
        except Exception as error:
            failures.append(name)
            print(f'FAIL {name} ({type(error).__name__}); review private configuration and running services.')

    try:
        from app import create_app, db
        app = create_app()
    except Exception as error:
        print(f'FAIL Flask startup ({type(error).__name__}); set SECRET_KEY, DATABASE_URL and FIREBASE_PROJECT_ID.')
        return 1
    print('PASS Flask application creation')

    def runtime_imports():
        modules = ('worker', 'notification_worker', 'sla_worker', 'coordinator_worker',
                   'feedback_worker', 'outbox_dispatcher', 'deadline_checker')
        for module in modules:
            importlib.import_module(module)
        return f'{len(modules)} worker entry points'

    def templates():
        from jinja2 import FileSystemLoader
        from app.frontend import FRONTEND, display_label, display_time
        environment = app.jinja_env.overlay(loader=FileSystemLoader(str(FRONTEND / 'templates')))
        environment.filters.update(display_label=display_label, display_time=display_time)
        names = environment.list_templates()
        for name in names:
            environment.get_template(name)
        return f'{len(names)} templates compiled'

    def hosting_sources():
        paths = ('Dockerfile.hosting', 'requirements.txt', 'requirements-hosting.txt', 'deploy/check_schema.py',
                 'worker.py', 'notification_worker.py', 'sla_worker.py', 'coordinator_worker.py',
                 'feedback_worker.py', 'outbox_dispatcher.py', 'deadline_checker.py')
        if any(not (ROOT / path).is_file() for path in paths):
            raise FileNotFoundError('A hosting runtime file is missing')

    def firebase_configuration():
        from app.frontend import firebase_web_config
        with app.test_request_context('/login'):
            config = firebase_web_config()
        if config['projectId'] != app.config['FIREBASE_PROJECT_ID']:
            raise ValueError('Frontend/backend project mismatch')
        credential_file = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if credential_file:
            with open(credential_file, encoding='utf-8') as stream:
                metadata = json.load(stream)
            if metadata.get('project_id') != app.config['FIREBASE_PROJECT_ID']:
                raise ValueError('Admin credential project mismatch')
            return 'web, backend and supplied Admin credential project IDs match; Console policy and live sign-in still require verification'
        return 'web/backend project IDs match; verify Application Default Credentials and Console settings separately'

    check('Required imports', runtime_imports)
    check('Jinja templates', templates)
    check('Hosting source files', hosting_sources)
    check('Firebase configuration', firebase_configuration)

    if args.database:
        def database_check():
            from sqlalchemy import create_engine, text
            from deploy.check_schema import verify
            uri = app.config['SQLALCHEMY_DATABASE_URI']
            engine = create_engine(uri, pool_pre_ping=True,
                                   connect_args={'connect_timeout': 3} if uri.startswith('mysql') else {})
            try:
                verify(engine)
                with engine.connect() as connection:
                    row = connection.execute(text('''SELECT COUNT(*) AS total,
                        COALESCE(SUM(CASE WHEN firebase_uid IS NOT NULL THEN 1 ELSE 0 END),0) AS mapped,
                        COALESCE(SUM(CASE WHEN firebase_uid IS NULL THEN 1 ELSE 0 END),0) AS unmapped FROM users''')).mappings().one()
                return f"schema validated; {row['total']} users, {row['mapped']} with UIDs, {row['unmapped']} without UIDs (no accounts linked)"
            finally:
                engine.dispose()
        check('Database schema and mapping counts', database_check)

    if args.rabbitmq:
        def rabbitmq_check():
            from app.messaging.rabbitmq_connection import get_rabbitmq_connection
            from app.messaging.rabbitmq_config import EXCHANGE_NAME, QUEUE_BINDINGS
            connection = get_rabbitmq_connection()
            try:
                channel = connection.channel()
                channel.exchange_declare(exchange=EXCHANGE_NAME, passive=True)
                for queue in QUEUE_BINDINGS:
                    channel.queue_declare(queue=queue, passive=True)
            finally:
                if connection.is_open:
                    connection.close()
            return 'existing exchange and queues found; no topology changes'
        check('RabbitMQ topology', rabbitmq_check)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
