"""Request email verification only for the expected coordinator Firebase UID."""
import argparse
import getpass
import sys

from tools.create_firebase_test_user import PROJECT_ID, SetupError, post


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected_uid',help='UID of the separately created coordinator account')
    args=parser.parse_args(argv)
    if not args.expected_uid.isascii() or not 1<=len(args.expected_uid)<=128:
        parser.error('Enter a valid Firebase UID')
    if not sys.stdin.isatty():
        print('Run interactively in CMD; do not pipe credentials.')
        return 1
    try:
        print('Coordinator verification only. Firebase project:',PROJECT_ID)
        print('No member policy, MySQL record, role or account password will be changed.')
        email=input('New coordinator email: ').strip()
        password=getpass.getpass('Firebase password (hidden): ')
        account=post('signInWithPassword',dict(email=email,password=password,returnSecureToken=True))
        password=None
        if account.get('localId')!=args.expected_uid:
            raise SetupError('Account UID does not match the intended coordinator. No email sent.')
        token=account.get('idToken')
        if not isinstance(token,str) or not token:
            raise SetupError('Firebase did not return an ID token. No email sent.')
        users=post('lookup',{'idToken':token}).get('users',[])
        if len(users)!=1 or users[0].get('localId')!=args.expected_uid:
            raise SetupError('Could not confirm the intended account. No email sent.')
        if users[0].get('emailVerified') is True:
            print('Coordinator email is already verified. No email sent; MySQL remains unchanged.')
            return 0
        post('sendOobCode',{'requestType':'VERIFY_EMAIL','idToken':token})
        print('Verification email requested. Check inbox/spam and open its link.')
        print('MySQL is unchanged. Coordinator linking still requires separate approval.')
        return 0
    except SetupError as error:
        print('Verification stopped:',error)
        return 1
    except KeyboardInterrupt:
        print('\nStopped. No database changes made.')
        return 1


if __name__=='__main__':
    raise SystemExit(main())
