"""Read-only live evidence. No tokens, UIDs, emails or credentials in output."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from app import create_app, db
    from app.member import firebase_app
    from app.messaging.rabbitmq_connection import get_rabbitmq_connection
    from app.messaging.rabbitmq_config import EXCHANGE_NAME, QUEUE_BINDINGS
    from sqlalchemy import text
    from firebase_admin import auth
    report = {'mode': 'read-only; no consumers started and no Firebase users modified'}
    app = create_app()
    with app.app_context():
        try:
            with db.engine.connect() as connection:
                rows = [dict(row) for row in connection.execute(text('''SELECT u.user_id,u.role_id,u.email,u.firebase_uid,
                    u.is_active,u.created_at,u.updated_at,r.role_name FROM users u JOIN roles r USING(role_id)
                    ORDER BY u.user_id''')).mappings()]
                report['users'] = {'total': len(rows), 'mapped': sum(bool(row['firebase_uid']) for row in rows),
                    'coordinators': sum(row['role_name'] == 'coordinator' for row in rows),
                    'coordinator_mapped': sum(row['role_name'] == 'coordinator' and bool(row['firebase_uid']) for row in rows),
                    'identity_snapshot_sha256': hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()}
                report['demo_organization'] = dict(connection.execute(text('''SELECT o.organization_id,o.status AS organization_status,
                    a.application_id,a.status AS application_status FROM organizations o
                    LEFT JOIN organization_applications a ON a.organization_id=o.organization_id AND a.application_id=6
                    WHERE o.organization_id=7''')).mappings().one())
                report['pending_outbox'] = connection.execute(text('SELECT COUNT(*) FROM event_outbox WHERE published_at IS NULL')).scalar_one()
                report['database_version'] = connection.execute(text('SELECT VERSION()')).scalar_one()
                report['table_counts'] = {row[0]: row[1] for row in connection.execute(text('''SELECT TABLE_NAME,TABLE_ROWS
                    FROM information_schema.tables WHERE table_schema=DATABASE() ORDER BY TABLE_NAME'''))}
                # Exact counts for safety comparison; identifiers come from server metadata.
                report['table_counts'] = {name: connection.execute(text('SELECT COUNT(*) FROM `' + name.replace('`','``') + '`')).scalar_one()
                                          for name in report['table_counts']}
                report['live_constraints'] = {kind: count for kind, count in connection.execute(text('''SELECT CONSTRAINT_TYPE,COUNT(*)
                    FROM information_schema.table_constraints WHERE constraint_schema=DATABASE() GROUP BY CONSTRAINT_TYPE'''))}
                report['index_count'] = connection.execute(text('''SELECT COUNT(DISTINCT TABLE_NAME,INDEX_NAME)
                    FROM information_schema.statistics WHERE table_schema=DATABASE()''')).scalar_one()
                report['uid_columns'] = [dict(row) for row in connection.execute(text('''SELECT COLUMN_NAME,IS_NULLABLE,
                    CHARACTER_SET_NAME,COLLATION_NAME,CHARACTER_MAXIMUM_LENGTH FROM information_schema.columns
                    WHERE table_schema=DATABASE() AND table_name='users' AND column_name IN ('firebase_uid','password_hash')''')).mappings()]
                references = connection.execute(text('''SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME
                    FROM information_schema.key_column_usage WHERE table_schema=DATABASE() AND referenced_table_name IS NOT NULL''')).all()
                orphan_counts = []
                for child, column, parent, target in references:
                    quote = lambda value: '`' + value.replace('`', '``') + '`'
                    sql = f'SELECT COUNT(*) FROM {quote(child)} c LEFT JOIN {quote(parent)} p ON c.{quote(column)}=p.{quote(target)} WHERE c.{quote(column)} IS NOT NULL AND p.{quote(target)} IS NULL'
                    orphan_counts.append(connection.execute(text(sql)).scalar_one())
                report['foreign_keys_checked_for_orphans'] = len(references)
                report['foreign_key_orphans'] = sum(orphan_counts)
                legacy_backup_flag = connection.execute(text("""SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema=DATABASE() AND table_name='referrals' AND column_name='is_backup'""")).scalar_one()
                report['referral_backup_storage'] = 'legacy column' if legacy_backup_flag else 'derived'
                report['data_invariants'] = {
                    'capacity_cache_mismatches': connection.execute(text('''SELECT COUNT(*) FROM organization_services os LEFT JOIN
                        (SELECT r.organization_id,s.service_id,s.service_area_id,COUNT(*) n FROM referrals r
                         JOIN service_requests s USING(request_id) WHERE r.status IN ('sent','accepted','attended')
                         GROUP BY r.organization_id,s.service_id,s.service_area_id) actual
                        ON actual.organization_id=os.organization_id AND actual.service_id=os.service_id
                        AND actual.service_area_id=os.service_area_id
                        WHERE os.current_active_referrals<>COALESCE(actual.n,0)''')).scalar_one(),
                    'backup_flag_mismatches': connection.execute(text(
                        'SELECT COUNT(*) FROM referrals WHERE NOT (is_backup <=> (attempt_number>1))'
                    )).scalar_one() if legacy_backup_flag else None,
                    'invalid_attempt_sequences': connection.execute(text('''SELECT COUNT(*) FROM (
                        SELECT request_id FROM referrals GROUP BY request_id
                        HAVING MIN(attempt_number)<>1 OR MAX(attempt_number)<>COUNT(*)
                            OR COUNT(DISTINCT attempt_number)<>COUNT(*) OR MAX(attempt_number)>3
                    ) invalid''')).scalar_one(),
                    'attendance_parent_mismatches': connection.execute(text('''SELECT COUNT(*) FROM attendance_records a
                        JOIN referrals r USING(referral_id) WHERE a.request_id<>r.request_id''')).scalar_one(),
                    'completion_parent_mismatches': connection.execute(text('''SELECT COUNT(*) FROM service_completions c
                        JOIN referrals r USING(referral_id) WHERE c.request_id<>r.request_id''')).scalar_one(),
                    'feedback_owner_mismatches': connection.execute(text('''SELECT COUNT(*) FROM feedback f
                        JOIN service_requests s USING(request_id) WHERE f.member_id<>s.member_id''')).scalar_one(),
                }
            report['database_status'] = 'PASS'
        except Exception as error:
            report['database_status'] = 'FAIL: ' + type(error).__name__
            rows = []
        try:
            connection = get_rabbitmq_connection()
            try:
                channel = connection.channel()
                channel.exchange_declare(exchange=EXCHANGE_NAME, passive=True)
                report['queues'] = {}
                for name, bindings in QUEUE_BINDINGS.items():
                    method = channel.queue_declare(queue=name, passive=True).method
                    report['queues'][name] = dict(ready_messages=method.message_count, consumers=method.consumer_count,
                                                 declared_bindings_in_source=bindings)
            finally:
                connection.close()
            report['rabbitmq_status'] = 'PASS'
        except Exception as error:
            report['rabbitmq_status'] = 'FAIL: ' + type(error).__name__
        try:
            admin = firebase_app()
            result = {'mapped_users_read': 0, 'verified': 0, 'disabled': 0}
            for row in rows:
                if row['firebase_uid']:
                    user = auth.get_user(row['firebase_uid'], app=admin)
                    result['mapped_users_read'] += 1
                    result['verified'] += bool(user.email_verified)
                    result['disabled'] += bool(user.disabled)
            report['firebase_admin_read'] = dict(status='PASS', **result)
            try:
                from google.auth.transport.requests import AuthorizedSession
                session = AuthorizedSession(admin.credential.get_credential())
                response = session.get('https://identitytoolkit.googleapis.com/admin/v2/projects/' + app.config['FIREBASE_PROJECT_ID'] + '/config', timeout=15)
                if response.status_code == 200:
                    config = response.json()
                    report['firebase_project_config'] = {'status': 'PASS',
                        'email_password_enabled': config.get('signIn', {}).get('email', {}).get('enabled'),
                        'localhost_authorized': 'localhost' in config.get('authorizedDomains', []),
                        'password_policy': config.get('passwordPolicyConfig', {}),
                        'email_enumeration_protection': config.get('emailPrivacyConfig', {}).get('enableImprovedEmailPrivacy')}
                else:
                    report['firebase_project_config'] = {'status': 'BLOCKED', 'http_status': response.status_code}
                session.close()
            except Exception as error:
                report['firebase_project_config'] = {'status': 'BLOCKED', 'error_type': type(error).__name__}
        except Exception as error:
            report['firebase_admin_read'] = {'status': 'BLOCKED', 'error_type': type(error).__name__}
    path = ROOT / 'docs/testing/live_environment.json'
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
