"""Acceptance timeout tests: disposable SQL and controlled UTC, no live scanner."""
from datetime import datetime,timedelta
from types import SimpleNamespace
from unittest.mock import patch, Mock
import pytest
from sqlalchemy import text
from conftest import LocalSession
from app import create_app
from app.services.matching import handle_request_created,handle_acceptance_timed_out,handle_referral_rejected
from app.services.timeouts import expired_referral_ids,timeout_referral,scan_once
from app.services.referrals import reject_referral,RejectionError


@pytest.fixture(autouse=True)
def clock():
    clock=SimpleNamespace(now=datetime(2030,1,1,12))
    with patch('app.services.timeouts.utcnow',side_effect=lambda:clock.now), \
         patch('app.services.matching.utcnow',side_effect=lambda:clock.now), \
         patch('app.services.referrals.utcnow',side_effect=lambda:clock.now):
        yield clock


def scalar(engine,sql):
    with engine.connect() as c:return c.execute(text(sql)).scalar()


def change(engine,sql):
    with engine.begin() as c:c.execute(text(sql))


def match(session,engine,event):
    handle_request_created(session,event)
    return scalar(engine,'SELECT referral_id FROM referrals WHERE request_id=1 ORDER BY attempt_number DESC LIMIT 1')


def timeout_event(engine,rid):
    with engine.connect() as c:
        row=c.execute(text('SELECT request_id,organization_id,attempt_number FROM referrals WHERE referral_id=:id'),{'id':rid}).mappings().one()
    return {'event_id':'timeout-event','event_type':'AcceptanceTimedOut','request_id':row['request_id'],
            'payload':{'referral_id':rid,'organization_id':row['organization_id'],'attempt_number':row['attempt_number']}}


def test_atomic_timeout_and_repeated_scan(session,engine,event,clock):
    rid=match(session,engine,event);clock.now+=timedelta(hours=2)
    assert expired_referral_ids(session)==[rid];session.rollback()
    assert timeout_referral(session,rid)
    assert scalar(engine,'SELECT status FROM referrals')=='timed_out'
    assert scalar(engine,'SELECT responded_at FROM referrals') is None
    assert scalar(engine,'SELECT rejection_reason FROM referrals') is None
    assert scalar(engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=1')==0
    assert scalar(engine,"SELECT COUNT(*) FROM referral_status_history WHERE new_status='timed_out'")==1
    assert scalar(engine,"SELECT changed_by_user_id FROM referral_status_history WHERE new_status='timed_out'") is None
    assert scalar(engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='AcceptanceTimedOut'")==1
    assert not timeout_referral(session,rid)
    assert scan_once(lambda:LocalSession(engine))=={'examined':0,'timed_out':0,'skipped':0,'failed':0}
    assert scalar(engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='AcceptanceTimedOut'")==1


def test_future_deadline_is_not_timed_out(session,engine,event,clock):
    rid=match(session,engine,event);clock.now+=timedelta(hours=2)-timedelta(microseconds=1)
    assert not timeout_referral(session,rid)
    assert scalar(engine,'SELECT status FROM referrals')=='sent'
    assert scalar(engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=1')==1


@pytest.mark.parametrize('status',['accepted','attended','completed','rejected','timed_out'])
def test_stale_candidate_rechecks_status(session,engine,event,clock,status):
    rid=match(session,engine,event);clock.now+=timedelta(hours=3)
    candidates=expired_referral_ids(session);session.rollback()
    assert candidates==[rid]
    change(engine,f"UPDATE referrals SET status='{status}'")
    assert not timeout_referral(session,rid)
    assert scalar(engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=1')==1
    assert scalar(engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='AcceptanceTimedOut'")==0


@pytest.mark.parametrize('status',['cancelled','completed','in_progress','unmatched'])
def test_terminal_or_unrelated_request_state_is_not_overwritten(session,engine,event,clock,status):
    rid=match(session,engine,event);clock.now+=timedelta(hours=3)
    change(engine,f"UPDATE service_requests SET status='{status}' WHERE request_id=1")
    assert not timeout_referral(session,rid)
    assert scalar(engine,'SELECT status FROM referrals')=='sent'


def test_outbox_failure_rolls_back_timeout(session,engine,event,clock):
    rid=match(session,engine,event);clock.now+=timedelta(hours=3)
    with patch('app.services.timeouts.enqueue',side_effect=RuntimeError('injected')):
        with pytest.raises(RuntimeError):timeout_referral(session,rid)
    assert scalar(engine,'SELECT status FROM referrals')=='sent'
    assert scalar(engine,'SELECT status FROM service_requests WHERE request_id=1')=='matched'
    assert scalar(engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=1')==1
    assert scalar(engine,"SELECT COUNT(*) FROM referral_status_history WHERE new_status='timed_out'")==0
    assert timeout_referral(session,rid)


@pytest.mark.parametrize('sql',[
    'UPDATE organization_services SET current_active_referrals=0 WHERE organization_id=1',
    'UPDATE organization_services SET service_id=999 WHERE organization_id=1',
    "UPDATE referrals SET responded_at='2029-01-01 00:00:00'",
])
def test_inconsistent_data_fails_closed(session,engine,event,clock,sql):
    rid=match(session,engine,event);clock.now+=timedelta(hours=3);change(engine,sql)
    with pytest.raises(RuntimeError):timeout_referral(session,rid)
    assert scalar(engine,'SELECT status FROM referrals')=='sent'
    assert scalar(engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='AcceptanceTimedOut'")==0


def test_timeout_backup_preserves_original_sla_and_duplicate_event(session,engine,event,clock):
    rid=match(session,engine,event)
    deadline=scalar(engine,'SELECT attendance_deadline FROM service_requests WHERE request_id=1')
    clock.now+=timedelta(hours=3);timeout_referral(session,rid)
    followup=timeout_event(engine,rid)
    assert handle_acceptance_timed_out(session,followup)=='matched'
    assert scalar(engine,'SELECT organization_id FROM referrals WHERE attempt_number=2')==2
    assert scalar(engine,'SELECT is_backup FROM referrals WHERE attempt_number=2')==1
    assert scalar(engine,'SELECT priority_id FROM service_requests WHERE request_id=1')==1
    assert scalar(engine,'SELECT attendance_deadline FROM service_requests WHERE request_id=1')==deadline
    assert scalar(engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=2')==2
    followup['event_id']='new-id-same-failure'
    assert handle_acceptance_timed_out(session,followup)=='already_processed'
    assert scalar(engine,'SELECT COUNT(*) FROM referrals')==2


def test_expired_original_sla_escalates_without_new_referral(session,engine,event,clock):
    rid=match(session,engine,event)
    change(engine,"UPDATE service_requests SET attendance_deadline='2030-01-01 13:00:00' WHERE request_id=1")
    clock.now+=timedelta(hours=3);timeout_referral(session,rid)
    assert handle_acceptance_timed_out(session,timeout_event(engine,rid))=='unmatched'
    assert scalar(engine,'SELECT COUNT(*) FROM referrals')==1
    assert scalar(engine,'SELECT user_id FROM notifications')==1


def test_no_eligible_partner_escalates(session,engine,event,clock):
    rid=match(session,engine,event);clock.now+=timedelta(hours=3);timeout_referral(session,rid)
    change(engine,"UPDATE organizations SET status='suspended' WHERE organization_id=2")
    assert handle_acceptance_timed_out(session,timeout_event(engine,rid))=='unmatched'
    assert scalar(engine,'SELECT COUNT(*) FROM referrals')==1
    assert scalar(engine,'SELECT COUNT(*) FROM notifications')==1


def test_three_timeouts_and_old_event_never_create_fourth(session,engine,event,clock):
    change(engine,"INSERT INTO organizations VALUES(3,'approved')")
    change(engine,"INSERT INTO organization_services VALUES(3,3,1,1,'active',10,2)")
    change(engine,"INSERT INTO service_priority_support VALUES(3,1,1)")
    rid=match(session,engine,event)
    first=None
    for attempt in [1,2,3]:
        clock.now+=timedelta(hours=3)
        assert timeout_referral(session,rid)
        followup=timeout_event(engine,rid)
        if first is None:first=followup
        if attempt>1:
            assert handle_acceptance_timed_out(session,first)=='already_processed'
        outcome=handle_acceptance_timed_out(session,followup)
        assert outcome==('matched' if attempt<3 else 'unmatched')
        if attempt<3:rid=scalar(engine,f'SELECT referral_id FROM referrals WHERE attempt_number={attempt+1}')
    assert scalar(engine,'SELECT COUNT(*) FROM referrals')==3
    assert scalar(engine,'SELECT COUNT(*) FROM notifications')==1


def test_rejection_and_timeout_share_state_guards(session,engine,event,clock):
    rid=match(session,engine,event)
    reject_referral(session,rid,4,'Synthetic rejection')
    clock.now+=timedelta(hours=3)
    assert not timeout_referral(session,rid)
    rejected=timeout_event(engine,rid);rejected['event_type']='ReferralRejected'
    assert handle_referral_rejected(session,rejected)=='matched'
    rid2=scalar(engine,'SELECT referral_id FROM referrals WHERE attempt_number=2')
    clock.now+=timedelta(hours=3);timeout_referral(session,rid2)
    with pytest.raises(RejectionError):reject_referral(session,rid2,4,'Wrong organization')
    assert scalar(engine,"SELECT COUNT(*) FROM event_outbox WHERE event_type='AcceptanceTimedOut'")==1


def test_scan_once_isolates_failed_records(session,engine,event,clock):
    match(session,engine,event)
    change(engine,'UPDATE organization_services SET service_id=999 WHERE organization_id=1')
    change(engine,"INSERT INTO service_requests(request_id,member_id,service_id,service_area_id,priority_id,title,description,status,attendance_deadline) VALUES(2,9,1,1,1,'Demo','Demo','submitted','2099-01-01 12:00:00')")
    handle_request_created(session,dict(event,request_id=2))
    clock.now+=timedelta(hours=3)
    result=scan_once(lambda:LocalSession(engine))
    assert result=={'examined':2,'timed_out':1,'skipped':0,'failed':1}
    assert scalar(engine,"SELECT status FROM referrals WHERE request_id=1")=='sent'
    assert scalar(engine,"SELECT status FROM referrals WHERE request_id=2")=='timed_out'


def test_scanner_filter_and_missing_candidate_are_safe(session,engine,event,clock):
    rid=match(session,engine,event);clock.now+=timedelta(hours=3)
    assert scan_once(lambda:LocalSession(engine),referral_ids=[999])['examined']==0
    assert not timeout_referral(session,999)
    assert scan_once(lambda:LocalSession(engine),referral_ids=[rid])['timed_out']==1


def test_backup_failure_can_retry_after_timeout(session,engine,event,clock):
    rid=match(session,engine,event);clock.now+=timedelta(hours=3);timeout_referral(session,rid)
    followup=timeout_event(engine,rid)
    with patch('app.services.matching.enqueue',side_effect=RuntimeError('injected')):
        with pytest.raises(RuntimeError):handle_acceptance_timed_out(session,followup)
    assert scalar(engine,'SELECT COUNT(*) FROM referrals')==1
    assert scalar(engine,'SELECT current_active_referrals FROM organization_services WHERE organization_id=2')==1
    assert handle_acceptance_timed_out(session,followup)=='matched'


def test_missing_coordinator_leaves_event_retryable(session,engine,event,clock):
    rid=match(session,engine,event);clock.now+=timedelta(hours=3);timeout_referral(session,rid)
    change(engine,"UPDATE organizations SET status='pending'")
    change(engine,'UPDATE users SET is_active=0 WHERE user_id=1')
    with pytest.raises(RuntimeError,match='coordinator'):
        handle_acceptance_timed_out(session,timeout_event(engine,rid))
    assert scalar(engine,'SELECT status FROM service_requests WHERE request_id=1')=='submitted'


def test_forged_timeout_state_and_payload_rejected(session,engine,event,clock):
    rid=match(session,engine,event)
    with pytest.raises(RuntimeError):handle_acceptance_timed_out(session,timeout_event(engine,rid))
    clock.now+=timedelta(hours=3);timeout_referral(session,rid)
    followup=timeout_event(engine,rid);followup['payload']['organization_id']=999
    with pytest.raises(ValueError):handle_acceptance_timed_out(session,followup)
    assert scalar(engine,'SELECT COUNT(*) FROM referrals')==1


def test_backup_notification_reuses_existing_flow(session,engine,event,clock):
    from app.services.notifications import handle_referral_created
    change(engine,"INSERT INTO users VALUES(5,2,'rep2@example.test','demo',1)")
    change(engine,'INSERT INTO organization_representatives VALUES(5,2,1)')
    rid=match(session,engine,event);clock.now+=timedelta(hours=3);timeout_referral(session,rid)
    handle_acceptance_timed_out(session,timeout_event(engine,rid))
    backup=scalar(engine,'SELECT referral_id FROM referrals WHERE attempt_number=2')
    handle_referral_created(session,dict(event,event_type='ReferralCreated',payload={'referral_id':backup}))
    assert scalar(engine,'SELECT user_id FROM notifications')==5


def test_cli_is_preview_by_default_and_apply_is_explicit():
    import deadline_checker
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    with patch.object(deadline_checker,'create_app',return_value=app), \
         patch.object(deadline_checker,'expired_referral_ids',return_value=[1]) as discover, \
         patch.object(deadline_checker,'scan_once',return_value={'failed':0}) as scan:
        assert deadline_checker.main(['--once'])==0
        discover.assert_called_once();scan.assert_not_called()
        assert deadline_checker.main(['--apply','--once','--referral-id','1'])==0
        scan.assert_called_once()
        assert scan.call_args.args[2]==[1]
