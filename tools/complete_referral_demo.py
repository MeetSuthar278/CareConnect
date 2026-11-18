"""Complete an approved synthetic referral using the real authorized API."""
import argparse
import getpass
import json
import sys

from tools.create_firebase_test_user import PROJECT_ID, SetupError, post
from tools.reject_referral_demo import local_api


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('referral_id', type=int)
    parser.add_argument('--request-id', type=int, required=True)
    parser.add_argument('--organization-id', type=int, required=True)
    args = parser.parse_args(argv)
    if min(args.referral_id, args.request_id, args.organization_id) <= 0:
        parser.error('IDs must be positive')
    if not sys.stdin.isatty():
        print('Run interactively in CMD; do not pipe credentials.')
        return 1
    try:
        print('Synthetic test only. Firebase project:', PROJECT_ID)
        print('Complete referral', args.referral_id, 'for request', args.request_id)
        email = input('Firebase representative email: ').strip()
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
        if identity.get('role') != 'representative' or identity.get('organization_id') != args.organization_id:
            raise SetupError('Use a representative account for the expected organization')
        # Validate the expected parent before sending either mutation.
        from app import create_app, db
        from sqlalchemy import text
        with create_app().app_context():
            parent = db.session.execute(text('SELECT request_id FROM referrals WHERE referral_id=:id'),
                                        {'id': args.referral_id}).scalar_one_or_none()
            db.session.rollback()
        if parent != args.request_id:
            raise SetupError('Referral does not belong to the expected request; no completion sent')
        payload = {'outcome': 'successful', 'summary_notes': 'Synthetic completion test only.'}
        for label in ('complete', 'repeat complete'):
            status, result = local_api(f'/api/referrals/{args.referral_id}/complete', token, payload)
            print(label, 'response:', status, json.dumps(result))
            if status != 200:
                return 1
            if result.get('request_id') != args.request_id:
                raise SetupError('Response differs from expected request; stop and inspect')
        print('Verify one completion/history row and one capacity release in the database.')
        return 0
    except SetupError as error:
        print('Test stopped:', error)
        return 1
    except KeyboardInterrupt:
        print('\nStopped. Check saved state before retrying.')
        return 1
    except Exception as error:
        # Never print raw authentication responses or potentially sensitive configuration.
        print('Test unavailable:', type(error).__name__, '- check saved state before retrying.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
