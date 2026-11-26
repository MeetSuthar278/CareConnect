"""Filter and page public services before loading their provider summaries."""
from sqlalchemy import bindparam, text

from app.pagination import like_pattern, page_rows
from app.services.guest_requests import DELIVERY, ELIGIBLE_AREAS
from app.services.offerings import RESPONSE_HOURS

SERVICE_SORTS = {
    'name': ('Service name: A to Z', 's.name ASC,s.service_id ASC'),
    'name_desc': ('Service name: Z to A', 's.name DESC,s.service_id DESC'),
    'category': ('Category: A to Z', 'c.name ASC,s.name ASC,s.service_id ASC'),
    'category_desc': ('Category: Z to A', 'c.name DESC,s.name ASC,s.service_id ASC'),
}
SERVICE_FROM = ''' FROM services s JOIN service_categories c ON c.category_id=s.category_id
    JOIN (''' + ELIGIBLE_AREAS + ''') eligible ON eligible.service_id=s.service_id
    JOIN service_areas a ON a.area_id=eligible.area_id
    WHERE s.is_active=TRUE AND c.is_active=TRUE
      AND s.delivery_mode IN ('in-person','phone','online')'''


def public_categories(database):
    return database.execute(text('SELECT DISTINCT c.name' + SERVICE_FROM + ' ORDER BY c.name')).scalars().all()


def public_services(database, *, pagination=None, service_id=None, search='', category='', delivery=''):
    sql = '''SELECT s.service_id,s.name AS service_name,s.description,c.name AS category,
        s.delivery_mode,a.region_name,a.city''' + SERVICE_FROM
    params = {}
    if service_id is not None:
        sql += ' AND s.service_id=:service_id'
        params['service_id'] = service_id
    if category:
        sql += ' AND c.name=:category'
        params['category'] = category
    if delivery:
        sql += ' AND s.delivery_mode=:delivery'
        params['delivery'] = next((key for key, value in DELIVERY.items() if value == delivery), '')
    if search:
        sql += ''' AND (LOWER(s.name) LIKE :search ESCAPE '!'
            OR LOWER(COALESCE(s.description,'')) LIKE :search ESCAPE '!'
            OR LOWER(c.name) LIKE :search ESCAPE '!'
            OR LOWER(a.region_name) LIKE :search ESCAPE '!'
            OR LOWER(a.city) LIKE :search ESCAPE '!'
            OR EXISTS(SELECT 1 FROM organization_services os JOIN organizations o ON o.organization_id=os.organization_id
                WHERE os.service_id=s.service_id AND os.status='active' AND o.status='approved'
                  AND os.service_area_id=a.area_id AND LOWER(o.name) LIKE :search ESCAPE '!'))'''
        params['search'] = like_pattern(search)
    if pagination:
        choices = page_rows(database, sql, params, pagination)
    else:
        if service_id is None:
            raise ValueError('A service ID or pagination is required')
        choices = database.execute(text(sql), params).mappings().all()
    if not choices:
        return []
    providers = database.execute(text('''SELECT os.service_id,o.name AS org_name,
        os.current_active_referrals,os.active_referral_limit
        FROM organization_services os JOIN organizations o ON o.organization_id=os.organization_id
        JOIN service_areas a ON a.area_id=os.service_area_id
        WHERE os.service_id IN :ids AND os.status='active' AND o.status='approved' AND a.is_active=TRUE
        ORDER BY os.service_id,o.name,o.organization_id''').bindparams(bindparam('ids', expanding=True)),
        {'ids': [row['service_id'] for row in choices]}).mappings().all()
    grouped = {}
    for provider in providers:
        grouped.setdefault(provider['service_id'], []).append(provider)
    result = []
    for choice in choices:
        rows = grouped.get(choice['service_id'], [])
        result.append(dict(choice, org_name=', '.join(sorted({row['org_name'] for row in rows})),
            description=choice['description'] or '', eligibility='-',
            area=f"{choice['region_name']}, {choice['city']}",
            delivery_method=DELIVERY[choice['delivery_mode']], response_hours=RESPONSE_HOURS,
            availability='Capacity available' if any(row['current_active_referrals'] < row['active_referral_limit'] for row in rows)
            else 'Currently at capacity'))
    return result
