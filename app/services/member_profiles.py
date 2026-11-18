"""Validated updates to the authenticated member's existing contact profile."""
import re

from sqlalchemy import text


class ProfileError(Exception):
    def __init__(self,message,status=400):
        super().__init__(message)
        self.status=status


def update_profile(database,member_id,data):
    limits={'full_name':101,'phone':25,'address':255,'city':100}
    if not isinstance(data,dict) or set(data)!=set(limits):
        raise ProfileError('Check your name, phone, address and city.')
    fields={}
    for key,limit in limits.items():
        value=data[key]
        if not isinstance(value,str) or not 1<=len(value.strip())<=limit:
            raise ProfileError('Check your name, phone, address and city.')
        fields[key]=value.strip()
    names=' '.join(fields.pop('full_name').split()).split(maxsplit=1)
    fields['first_name']=names[0]
    fields['last_name']=names[1] if len(names)>1 else ''
    if len(fields['first_name'])>50 or len(fields['last_name'])>50:
        raise ProfileError('First and last names must each contain at most 50 characters.')
    if (not re.fullmatch(r'[+0-9() .\-]{7,25}',fields['phone'])
            or not 7<=sum(c.isdigit() for c in fields['phone'])<=15):
        raise ProfileError('Enter a valid phone number.')
    with database.begin():
        user=database.execute(text('''SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
            WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='member' FOR UPDATE'''),
            {'id':member_id}).scalar_one_or_none()
        if user is None:
            raise ProfileError('Member account unavailable.',403)
        saved=database.execute(text('''SELECT first_name,last_name,phone,address,city
            FROM member_profiles WHERE user_id=:id FOR UPDATE'''),{'id':member_id}).mappings().one_or_none()
        if saved is None:
            raise ProfileError('Member profile not found.',404)
        if all(saved[key]==value for key,value in fields.items()):
            return dict(already_processed=True)
        database.execute(text('''UPDATE member_profiles SET first_name=:first_name,last_name=:last_name,
            phone=:phone,address=:address,city=:city WHERE user_id=:id'''),dict(fields,id=member_id))
        return dict(already_processed=False)
