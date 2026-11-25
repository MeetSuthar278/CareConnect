"""No real Firebase calls, verification emails, credentials or SQL."""
from unittest.mock import patch

import pytest

from tools.verify_coordinator_email import main


@pytest.mark.parametrize('scenario,expected_calls,exit_code',[
    ('send',3,0),('verified',2,0),('wrong_uid',1,1),('wrong_lookup',2,1),('missing_token',1,1),
])
def test_helper_is_bound_to_expected_uid(scenario,expected_calls,exit_code,capsys):
    uid='synthetic-coordinator-uid'
    account={'localId':uid,'idToken':'synthetic-token'}
    user={'localId':uid,'emailVerified':scenario=='verified'}
    if scenario=='wrong_uid': account['localId']='other-member'
    if scenario=='wrong_lookup': user['localId']='other-member'
    if scenario=='missing_token': account.pop('idToken')
    with patch('tools.verify_coordinator_email.sys.stdin.isatty',return_value=True), \
         patch('builtins.input',return_value='coordinator@example.test'), \
         patch('tools.verify_coordinator_email.getpass.getpass',return_value='synthetic-password'), \
         patch('tools.verify_coordinator_email.post',side_effect=[account,{'users':[user]},{}]) as post:
        assert main([uid])==exit_code
        assert post.call_count==expected_calls
        if scenario=='send':
            assert post.call_args.args==('sendOobCode',{'requestType':'VERIFY_EMAIL','idToken':'synthetic-token'})
    output=capsys.readouterr().out
    assert 'synthetic-password' not in output and 'synthetic-token' not in output
