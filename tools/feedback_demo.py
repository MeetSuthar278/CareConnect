"""Submit and repeat feedback for an approved synthetic completed request."""
import argparse
import getpass
import json
import sys

from tools.create_firebase_test_user import PROJECT_ID, SetupError, post
from tools.reject_referral_demo import local_api


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request_id', type=int)
    parser.add_argument('--helpful', choices=('yes', 'no'), required=True)
    args = parser.parse_args(argv)
    if args.request_id <= 0:
        parser.error('Request ID must be positive')
    if not sys.stdin.isatty():
        print('Run interactively in CMD; do not pipe credentials.')
        return 1
    try:
        print('Synthetic test only. Firebase project:', PROJECT_ID)
        print('Feedback for request', args.request_id, '- helpful:', args.helpful)
        email = input('Firebase MEMBER email: ').strip()
        password = getpass.getpass('Firebase password (hidden): ')
        account = post('signInWithPassword', dict(email=email, password=password, returnSecureToken=True))
        password = None
        token = account.get('idToken')
        if not isinstance(token, str) or not token:
            raise SetupError('Firebase did not return an ID token')
        status, identity = local_api('/api/auth/me', token)
        if status != 200:
            print('Identity check:', status, identity.get('error', 'Failed'))
            return 1
        if identity.get('role') != 'member':
            raise SetupError('Use the owning MEMBER login, not a representative account')
        from app import create_app, db
        from sqlalchemy import text
        with create_app().app_context():
            row = db.session.execute(text('SELECT member_id,status FROM service_requests WHERE request_id=:id'),
                                     {'id': args.request_id}).mappings().one_or_none()
            db.session.rollback()
        if row is None or row['member_id'] != identity.get('user_id') or row['status'] != 'completed':
            raise SetupError('No feedback sent: request must be completed and owned by this member')
        payload = {'is_helpful': args.helpful == 'yes', 'comment': 'Synthetic feedback test only.'}
        for label in ('feedback', 'repeat feedback'):
            status, result = local_api(f'/api/requests/{args.request_id}/feedback', token, payload)
            print(label, 'response:', status, json.dumps(result))
            if status != 200:
                return 1
            if result.get('request_id') != args.request_id:
                raise SetupError('Unexpected request response; stop and inspect')
        print('Verify one feedback/event and expected partner/coordinator notifications in MySQL.')
        return 0
    except SetupError as error:
        print('Test stopped:', error)
        return 1
    except KeyboardInterrupt:
        print('\nStopped. Check saved state before retrying.')
        return 1
    except Exception as error:
        print('Test unavailable:', type(error).__name__, '- check saved state before retrying.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
