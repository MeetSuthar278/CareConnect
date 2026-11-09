"""Read-only hosted preflight. Never create or migrate database tables."""
import os
from sqlalchemy import create_engine,inspect


def verify(engine):
    inspector=inspect(engine)
    required={
        'users':{'user_id','firebase_uid','password_hash'},
        'service_requests':{'request_id','status','attendance_deadline'},
        'referrals':{'referral_id','attempt_number','active_slot'},
        'organization_services':{'current_active_referrals','active_referral_limit'},
        'organization_applications':{'application_id','submitted_by_user_id'},
        'organization_availability':{'availability_id','recorded_by_user_id'},
        'notifications':{'notification_id','deduplication_key'},
        'event_outbox':{'event_id','published_at','available_at','attempts'},
        'attendance_records':{'attendance_id','request_id'},
        'service_completions':{'completion_id','request_id'},
        'feedback':{'feedback_id','is_helpful'},
    }
    for table,columns in required.items():
        if not inspector.has_table(table) or not columns<={row['name'] for row in inspector.get_columns(table)}:
            raise RuntimeError('Database schema is not ready; restore the reviewed schema/data before starting the app.')
    for table,columns in [('users',{'firebase_uid'}),('referrals',{'request_id','active_slot'}),
                          ('notifications',{'user_id','deduplication_key'})]:
        unique=inspector.get_unique_constraints(table)+[row for row in inspector.get_indexes(table) if row.get('unique')]
        if not any(set(row['column_names'])==columns for row in unique):
            raise RuntimeError('Required database uniqueness protection is missing.')
    if not any(row['nullable'] for row in inspector.get_columns('users') if row['name']=='password_hash'):
        raise RuntimeError('Firebase schema changes are missing.')
    if not any(row['name']=='ck_org_service_capacity' for row in inspector.get_check_constraints('organization_services')):
        raise RuntimeError('Capacity constraints are missing.')
    if not any(row.get('computed') for row in inspector.get_columns('referrals') if row['name']=='active_slot'):
        raise RuntimeError('The active-referral uniqueness column must be generated.')


if __name__=='__main__':
    try:
        verify(create_engine(os.environ['DATABASE_URL'],pool_pre_ping=True))
    except Exception as error:
        # Database driver errors may contain credentials; report only the class.
        raise SystemExit('Read-only database preflight failed ('+type(error).__name__+'). Review schema/import and private database configuration.')
    print('Read-only database preflight passed.')
