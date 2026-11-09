"""Read the authenticated SQL account for client-side Firebase reauthentication."""
from sqlalchemy import text


def password_identity(database,user_id,role):
    if role not in {'member','representative'}:
        return None
    row=database.execute(text('''SELECT u.firebase_uid AS uid,u.email FROM users u
        JOIN roles r ON r.role_id=u.role_id WHERE u.user_id=:id
        AND u.is_active=TRUE AND r.role_name=:role'''),{'id':user_id,'role':role}).mappings().one_or_none()
    if row is None or not row['uid'] or not row['email']:
        return None
    return dict(row)
