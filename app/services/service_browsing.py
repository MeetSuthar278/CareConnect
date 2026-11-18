"""Read-only public catalog aligned with the existing single-area request form."""
from sqlalchemy import text

from app.services.guest_requests import DELIVERY, service_choices
from app.services.offerings import RESPONSE_HOURS


def public_services(database):
    # Reuse request-form eligibility, including its one-distinct-active-area rule.
    choices = service_choices(database)
    providers = database.execute(text('''
        SELECT os.service_id,o.name AS org_name,s.description,
               os.current_active_referrals,os.active_referral_limit
        FROM organization_services os
        JOIN organizations o ON o.organization_id=os.organization_id
        JOIN services s ON s.service_id=os.service_id
        JOIN service_areas a ON a.area_id=os.service_area_id
        WHERE o.status='approved' AND os.status='active' AND a.is_active=TRUE
          AND s.is_active=TRUE
        ORDER BY os.service_id,o.name,o.organization_id
    ''')).mappings().all()
    grouped = {}
    for provider in providers:
        grouped.setdefault(provider['service_id'], []).append(provider)
    result = []
    for choice in choices:
        rows = grouped.get(choice['service_id'], [])
        if not rows:
            continue
        result.append(dict(choice,
            org_name=', '.join(sorted({row['org_name'] for row in rows})),
            description=rows[0]['description'] or '', eligibility='-',
            delivery_method=DELIVERY[choice['delivery_mode']], response_hours=RESPONSE_HOURS,
            availability='Capacity available' if any(
                row['current_active_referrals'] < row['active_referral_limit'] for row in rows)
                else 'Currently at capacity'))
    return result
