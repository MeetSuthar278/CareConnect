"""Read/update only the representative's own organization contact details."""
import re

from sqlalchemy import text


class OrganizationProfileError(Exception):
    def __init__(self,message,status=400):
        super().__init__(message)
        self.status=status


def organization_profile(database,user_id,organization_id):
    row=database.execute(text('''SELECT o.organization_id,o.name AS org_name,o.status,
        o.contact_email AS email,o.contact_phone AS phone,o.address,o.city,
        rep.full_name AS contact_name
        FROM organization_representatives rep JOIN users u ON u.user_id=rep.user_id
        JOIN roles r ON r.role_id=u.role_id JOIN organizations o ON o.organization_id=rep.organization_id
        WHERE rep.user_id=:user AND rep.organization_id=:org
        AND u.is_active=TRUE AND r.role_name='representative'
    '''),{'user':user_id,'org':organization_id}).mappings().one_or_none()
    if row is None:
        return None
    areas=database.execute(text('''SELECT DISTINCT a.region_name,a.city
        FROM organization_services os JOIN service_areas a ON a.area_id=os.service_area_id
        WHERE os.organization_id=:org ORDER BY a.city,a.region_name'''),{'org':organization_id}).all()
    return dict(row,status=row['status'].title(),address=row['address'] or '',
                service_area='; '.join(f'{area.region_name}, {area.city}' for area in areas) or '-')


def update_organization_profile(database,user_id,organization_id,data):
    limits={'contact_name':100,'phone':25,'address':255,'city':100}
    if not isinstance(data,dict) or set(data)!=set(limits):
        raise OrganizationProfileError('Check the contact name, phone, address and city.')
    fields={}
    for key,limit in limits.items():
        value=data[key]
        if not isinstance(value,str) or not 1<=len(value.strip())<=limit:
            raise OrganizationProfileError('Check the contact name, phone, address and city.')
        fields[key]=value.strip()
    fields['contact_name']=' '.join(fields['contact_name'].split())
    if (not re.fullmatch(r'[+0-9() .\-]{7,25}',fields['phone'])
            or not 7<=sum(c.isdigit() for c in fields['phone'])<=15):
        raise OrganizationProfileError('Enter a valid phone number.')
    with database.begin():
        # Same representative -> organization lock order as offering updates.
        rep=database.execute(text('''SELECT rep.full_name,rep.phone FROM organization_representatives rep
            JOIN users u ON u.user_id=rep.user_id JOIN roles r ON r.role_id=u.role_id
            WHERE rep.user_id=:user AND rep.organization_id=:org
            AND u.is_active=TRUE AND r.role_name='representative' FOR UPDATE'''),
            {'user':user_id,'org':organization_id}).mappings().one_or_none()
        if rep is None:
            raise OrganizationProfileError('Representative permission required.',403)
        org=database.execute(text('''SELECT contact_phone,address,city FROM organizations
            WHERE organization_id=:org FOR UPDATE'''),{'org':organization_id}).mappings().one_or_none()
        if org is None:
            raise OrganizationProfileError('Organization not found.',404)
        org_changed=any(org[key]!=fields[field] for key,field in
                        [('contact_phone','phone'),('address','address'),('city','city')])
        rep_changed=rep['full_name']!=fields['contact_name'] or rep['phone']!=fields['phone']
        if org_changed:
            database.execute(text('''UPDATE organizations SET contact_phone=:phone,address=:address,city=:city
                WHERE organization_id=:org'''),dict(fields,org=organization_id))
        if rep_changed:
            database.execute(text('''UPDATE organization_representatives SET full_name=:contact_name,phone=:phone
                WHERE user_id=:user AND organization_id=:org'''),dict(fields,user=user_id,org=organization_id))
        return dict(already_processed=not org_changed and not rep_changed)
