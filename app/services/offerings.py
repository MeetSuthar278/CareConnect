"""Organization-owned availability and capacity settings; never edit the catalog."""
from sqlalchemy import text

from app.services.outbox import utcnow
from app.pagination import like_pattern, page_rows

OFFERING_SORTS = {
    'name': ('Service: A to Z', 's.name ASC,os.organization_service_id ASC'),
    'name_desc': ('Service: Z to A', 's.name DESC,os.organization_service_id ASC'),
    'newest': ('Newest first', 'os.organization_service_id DESC'),
    'oldest': ('Oldest first', 'os.organization_service_id ASC'),
}

RESPONSE_HOURS = 2  # Existing matching response window, capped by attendance SLA.


class OfferingError(Exception):
    def __init__(self,message,status=409):
        super().__init__(message)
        self.status=status


def add_offering(database,user_id,*,service_id,area_id,status,referral_limit):
    """Create only an owned offering; catalog and geography remain shared/read-only."""
    if (type(service_id) is not int or service_id<=0 or type(area_id) is not int or area_id<=0
            or status not in {'active','paused'} or type(referral_limit) is not int
            or not 1<=referral_limit<=1000):
        raise OfferingError('Choose a service, area, status and referral limit from 1 to 1000.',400)
    with database.begin():
        organization=database.execute(text('''SELECT rep.organization_id
            FROM organization_representatives rep JOIN users u ON u.user_id=rep.user_id
            JOIN roles r ON r.role_id=u.role_id WHERE u.user_id=:id
            AND u.is_active=TRUE AND r.role_name='representative' FOR UPDATE'''),
            {'id':user_id}).scalar_one_or_none()
        if organization is None:
            raise OfferingError('Representative permission required.',403)
        org_status=database.execute(text('''SELECT status FROM organizations
            WHERE organization_id=:org FOR UPDATE'''),{'org':organization}).scalar_one_or_none()
        if org_status!='approved':
            raise OfferingError('Organization approval is required to manage services.',403)
        service=database.execute(text('''SELECT s.service_id FROM services s
            JOIN service_categories c ON c.category_id=s.category_id
            WHERE s.service_id=:id AND s.is_active=TRUE AND c.is_active=TRUE FOR UPDATE'''),
            {'id':service_id}).scalar_one_or_none()
        area=database.execute(text('''SELECT area_id FROM service_areas
            WHERE area_id=:id AND is_active=TRUE FOR UPDATE'''),{'id':area_id}).scalar_one_or_none()
        priorities=database.execute(text('''SELECT priority_id,level_name FROM priority_levels
            ORDER BY priority_id FOR UPDATE''')).mappings().all()
        if {row['level_name'] for row in priorities}!={'High','Medium','Low'}:
            raise OfferingError('Time-frame settings are unavailable. Please contact the coordinator.',503)
        priority_ids={row['priority_id'] for row in priorities}
        if service is None or area is None:
            raise OfferingError('Selected service or area is unavailable. Reload and retry.',400)
        existing=database.execute(text('''SELECT organization_service_id,status,active_referral_limit
            FROM organization_services WHERE organization_id=:org AND service_id=:service
            AND service_area_id=:area FOR UPDATE'''),
            dict(org=organization,service=service_id,area=area_id)).mappings().one_or_none()
        if existing:
            supported=set(database.execute(text('''SELECT priority_id FROM service_priority_support
                WHERE organization_service_id=:id AND is_supported=TRUE FOR UPDATE'''),
                {'id':existing['organization_service_id']}).scalars())
            if (existing['status']==status and existing['active_referral_limit']==referral_limit
                    and supported==set(priority_ids)):
                return dict(organization_service_id=existing['organization_service_id'],already_processed=True)
            raise OfferingError('This service and area already exist. Existing settings were preserved; use Edit settings.')
        offering_id=database.execute(text('''INSERT INTO organization_services
            (organization_id,service_id,service_area_id,status,active_referral_limit,current_active_referrals)
            VALUES(:org,:service,:area,:status,:limit,0)'''),
            dict(org=organization,service=service_id,area=area_id,status=status,limit=referral_limit)).lastrowid
        for priority in sorted(priority_ids):
            database.execute(text('''INSERT INTO service_priority_support
                (organization_service_id,priority_id,is_supported) VALUES(:id,:priority,TRUE)'''),
                {'id':offering_id,'priority':priority})
        return dict(organization_service_id=offering_id,already_processed=False)


def organization_offerings(database,organization_id,*,pagination,search='',status=''):
    sql='''
        SELECT os.organization_service_id,os.service_id,os.status AS raw_status,
               os.active_referral_limit AS max_referrals,os.current_active_referrals,
               s.name AS service_name,s.description,s.delivery_mode,c.name AS category,
               a.region_name,a.city,
               COALESCE((SELECT MAX(av.availability_id) FROM organization_availability av
                   WHERE av.organization_service_id=os.organization_service_id),0) AS availability_version
        FROM organization_services os JOIN services s ON s.service_id=os.service_id
        JOIN service_categories c ON c.category_id=s.category_id
        JOIN service_areas a ON a.area_id=os.service_area_id
        WHERE os.organization_id=:org
    '''
    params={'org':organization_id}
    if search:
        sql+=" AND (LOWER(s.name) LIKE :search ESCAPE '!' OR LOWER(c.name) LIKE :search ESCAPE '!')"
        params['search']=like_pattern(search)
    if status:
        sql+=' AND os.status=:status'
        params['status']={'Active':'active','Paused':'paused'}.get(status,'')
    rows=page_rows(database,sql,params,pagination)
    from app.services.guest_requests import DELIVERY
    return [dict(row,status=row['raw_status'].title(),area=f"{row['region_name']}, {row['city']}",
                 response_hours=RESPONSE_HOURS,eligibility='-',availability='-',
                 delivery_method=DELIVERY[row['delivery_mode']],delivery_methods=[DELIVERY[row['delivery_mode']]]) for row in rows]


def update_offering(database,offering_id,user_id,*,status,expected_status,availability_version,
                    referral_limit=None,expected_limit=None):
    if status not in {'active','paused'} or expected_status not in {'active','paused'}:
        raise OfferingError('Choose Active or Paused.',400)
    if type(availability_version) is not int or availability_version<0:
        raise OfferingError('Reload service settings and retry.',400)
    if referral_limit is not None and (type(referral_limit) is not int or not 1<=referral_limit<=1000):
        raise OfferingError('Referral limit must be an integer from 1 to 1000.',400)
    if referral_limit is not None and (type(expected_limit) is not int or expected_limit<0):
        raise OfferingError('Reload service settings and retry.',400)
    with database.begin():
        # Match existing referral services' user/representative-before-offering order.
        organization=database.execute(text('''
            SELECT rep.organization_id FROM organization_representatives rep
            JOIN users u ON u.user_id=rep.user_id JOIN roles r ON r.role_id=u.role_id
            WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='representative' FOR UPDATE
        '''),{'id':user_id}).scalar_one_or_none()
        if organization is None:
            raise OfferingError('Offering not found',404)
        organization_status=database.execute(text('''SELECT status FROM organizations
            WHERE organization_id=:org FOR UPDATE'''),{'org':organization}).scalar_one_or_none()
        if organization_status!='approved':
            raise OfferingError('Organization approval is required to manage services.',403)
        offering=database.execute(text('''
            SELECT status,active_referral_limit,current_active_referrals FROM organization_services
            WHERE organization_service_id=:id AND organization_id=:org FOR UPDATE
        '''),{'id':offering_id,'org':organization}).mappings().one_or_none()
        if offering is None:
            raise OfferingError('Offering not found',404)
        limit=offering['active_referral_limit'] if referral_limit is None else referral_limit
        if (offering['current_active_referrals']<0 or
                offering['current_active_referrals']>offering['active_referral_limit']):
            raise OfferingError('Capacity data is inconsistent; coordinator review required.')
        if offering['status']==status and offering['active_referral_limit']==limit:
            return dict(already_processed=True,status=status,active_referral_limit=limit)
        version=database.execute(text('''SELECT availability_id FROM organization_availability
            WHERE organization_service_id=:id ORDER BY availability_id DESC LIMIT 1 FOR UPDATE'''),
            {'id':offering_id}).scalar_one_or_none() or 0
        if (offering['status']!=expected_status or version!=availability_version or
                (referral_limit is not None and offering['active_referral_limit']!=expected_limit)):
            raise OfferingError('Service settings changed. Reload the page and retry.')
        if limit<offering['current_active_referrals']:
            raise OfferingError('Referral limit cannot be below current active reservations.')
        changed=database.execute(text('''
            UPDATE organization_services SET status=:status,active_referral_limit=:limit
            WHERE organization_service_id=:id AND organization_id=:org
              AND current_active_referrals<=:limit
        '''),{'status':status,'limit':limit,'id':offering_id,'org':organization})
        if changed.rowcount!=1:
            raise OfferingError('Capacity changed. Reload the page and retry.')
        if status!=offering['status']:
            database.execute(text('''
                INSERT INTO organization_availability(organization_service_id,action,recorded_at,recorded_by_user_id)
                VALUES(:id,:action,:now,:actor)
            '''),{'id':offering_id,'action':'pause' if status=='paused' else 'resume',
                    'now':utcnow().replace(microsecond=0),'actor':user_id})
        return dict(already_processed=False,status=status,active_referral_limit=limit)
