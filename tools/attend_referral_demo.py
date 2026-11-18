"""Accept then attend an approved synthetic referral through authenticated APIs."""
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
        print('Accept and attend referral', args.referral_id, 'for request', args.request_id)
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
        for action in ('accept', 'attend', 'attend'):
            status, result = local_api(f'/api/referrals/{args.referral_id}/{action}', token, {})
            print(action, 'response:', status, json.dumps(result))
            if status != 200:
                return 1
            if result.get('request_id') != args.request_id:
                raise SetupError('Response request differs from expected request; stop and inspect')
        print('Verify attendance, capacity, history, outbox and SLA consumer in the database.')
        return 0
    except SetupError as error:
        print('Test stopped:', error)
        return 1
    except KeyboardInterrupt:
        print('\nStopped. Check saved state before retrying.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
