"""Acceptance deadline processing using the existing timeout event contract."""
import logging

from sqlalchemy import bindparam, text

from app.models import ReferralStatusHistory
from app.services.outbox import enqueue, utcnow

logger = logging.getLogger(__name__)


def candidate_ids(database, sql, batch_size, selected_ids=None):
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError('Batch size must be from 1 to 1000')
    params = {'now': utcnow(), 'limit': batch_size}
    sql = 'SELECT candidate_id FROM (' + sql + ') candidates WHERE 1=1'
    if selected_ids is not None:
        if any(type(value) is not int or value <= 0 for value in selected_ids):
            raise ValueError('Candidate IDs must be positive integers')
        sql += ' AND candidate_id IN :ids'
        params['ids'] = sorted(set(selected_ids))
    statement = text(sql + ' ORDER BY candidate_id LIMIT :limit')
    if selected_ids is not None:
        statement = statement.bindparams(bindparam('ids', expanding=True))
    return database.execute(statement, params).scalars().all()


def expired_referral_ids(database, batch_size=100, selected_ids=None):
    return candidate_ids(database, '''SELECT r.referral_id AS candidate_id FROM referrals r
        JOIN service_requests sr ON sr.request_id=r.request_id
        WHERE r.status='sent' AND r.response_deadline <= :now AND sr.status='matched' ''',
        batch_size, selected_ids)


def expire_referral(database, referral_id):
    with database.begin():
        request_id = database.execute(text('SELECT request_id FROM referrals WHERE referral_id=:id'),
                                      {'id': referral_id}).scalar_one_or_none()
        if request_id is None:
            return False
        # Keep the request-first lock order used by matching and responses.
        request = database.execute(text('SELECT status FROM service_requests WHERE request_id=:id FOR UPDATE'),
                                   {'id': request_id}).scalar_one_or_none()
        referral = database.execute(text('''SELECT status,response_deadline,organization_id,attempt_number
            FROM referrals WHERE referral_id=:id AND request_id=:request FOR UPDATE'''),
            {'id': referral_id, 'request': request_id}).mappings().one_or_none()
        if not referral or referral['status'] != 'sent' or request != 'matched':
            return False
        expired = database.execute(text('SELECT response_deadline <= :now FROM referrals WHERE referral_id=:id'),
                                   {'now': utcnow(), 'id': referral_id}).scalar_one()
        if not expired:
            return False
        offering = database.execute(text('''SELECT os.organization_service_id
            FROM organization_services os JOIN service_requests sr ON sr.service_id=os.service_id
                AND sr.service_area_id=os.service_area_id
            WHERE sr.request_id=:request AND os.organization_id=:org FOR UPDATE'''),
            {'request': request_id, 'org': referral['organization_id']}).scalar_one_or_none()
        if offering is None:
            raise RuntimeError('Timeout offering is missing; coordinator review required')
        released = database.execute(text('''UPDATE organization_services
            SET current_active_referrals=current_active_referrals-1
            WHERE organization_service_id=:id AND current_active_referrals>0'''), {'id': offering})
        if released.rowcount != 1:
            raise RuntimeError('Timeout capacity is inconsistent; coordinator review required')
        database.execute(text("UPDATE referrals SET status='timed_out' WHERE referral_id=:id"), {'id': referral_id})
        database.execute(text("UPDATE service_requests SET status='submitted' WHERE request_id=:id"), {'id': request_id})
        database.add(ReferralStatusHistory(referral_id=referral_id, old_status='sent', new_status='timed_out',
                                          notes='Organization response window expired'))
        enqueue(database, 'AcceptanceTimedOut', request_id,
                {'referral_id': referral_id, 'organization_id': referral['organization_id'],
                 'attempt_number': referral['attempt_number']}, f'acceptance-timeout:{referral_id}')
        return True


def scan_candidates(session_factory, discover, process, batch_size, selected_ids):
    with session_factory() as database:
        ids = discover(database, batch_size, selected_ids)
    result = {'processed': 0, 'skipped': 0, 'failed': 0}
    for candidate in ids:
        try:
            with session_factory() as database:
                changed = process(database, candidate)
            result['processed' if changed else 'skipped'] += 1
        except Exception as error:
            logger.error('Deadline action failed for ID %s (%s)', candidate, type(error).__name__)
            result['failed'] += 1
    return result


def scan_once(session_factory, batch_size=100, selected_ids=None):
    return scan_candidates(session_factory, expired_referral_ids, expire_referral, batch_size, selected_ids)
