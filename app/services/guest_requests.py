"""Team-form data adapter and atomic guest/profile/request/outbox creation."""
import secrets
from datetime import timedelta

from sqlalchemy import select, text
from werkzeug.security import generate_password_hash

from app.models import EventOutbox, ServiceRequest
from app.services.outbox import enqueue, utcnow


DELIVERY = {"in-person": "In person", "phone": "Phone", "online": "Online"}
DISPLAY_STATUS = {"submitted": "Pending", "matched": "Assigned", "unmatched": "Unmatched",
                  "in_progress": "In progress", "completed": "Completed", "cancelled": "Cancelled"}


class GuestRequestError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def service_choices(session):
    services = session.execute(text("""
        SELECT s.service_id,s.name AS service_name,c.name AS category,s.delivery_mode
        FROM services s JOIN service_categories c ON c.category_id=s.category_id
        WHERE s.is_active=TRUE AND c.is_active=TRUE ORDER BY s.service_id
    """)).mappings().all()
    result = []
    for row in services:
        areas = _areas(session, row["service_id"])
        if len(areas) != 1 or row["delivery_mode"] not in DELIVERY:
            # No area selector exists in this team design. Do not guess an area.
            continue
        area = areas[0]
        result.append(dict(row, area=f"{area.region_name}, {area.city}",
                           delivery_methods=[DELIVERY[row["delivery_mode"]]]))
    return result


def _areas(session, service_id):
    return session.execute(text("""
        SELECT DISTINCT a.area_id,a.region_name,a.city
        FROM organization_services os JOIN organizations o ON o.organization_id=os.organization_id
        JOIN service_areas a ON a.area_id=os.service_area_id
        WHERE os.service_id=:service AND os.status='active'
          AND o.status='approved' AND a.is_active=TRUE ORDER BY a.area_id
    """), {"service": service_id}).all()


def _validate(data):
    fields = {key: str(data.get(key, "")).strip() for key in (
        "contact_name", "contact_email", "contact_phone", "contact_city", "contact_address", "details")}
    if any(not value for value in fields.values()):
        raise GuestRequestError("Complete all required fields.")
    fields["contact_name"] = " ".join(fields["contact_name"].split())
    first, _, last = fields["contact_name"].partition(" ")
    if len(first) > 50 or len(last) > 50:
        raise GuestRequestError("Name is too long.")
    fields["contact_email"] = fields["contact_email"].lower()
    email = fields["contact_email"]
    if len(email) > 120 or email.count("@") != 1 or any(c.isspace() for c in email) or "." not in email.rsplit("@", 1)[-1]:
        raise GuestRequestError("Enter a valid contact email.")
    phone = fields["contact_phone"]
    if len(phone) > 25 or not 7 <= sum(c.isdigit() for c in phone) <= 15 or any(
            c not in "+0123456789 ().-" for c in phone):
        raise GuestRequestError("Enter a phone number with 7 to 15 digits.")
    if len(fields["contact_city"]) > 100 or len(fields["contact_address"]) > 255:
        raise GuestRequestError("City or address is too long.")
    if len(fields["details"].encode("utf-8")) > 65535:
        raise GuestRequestError("Request description is too long.")
    try:
        service_id = int(data.get("service_id", ""))
    except (ValueError, TypeError):
        raise GuestRequestError("Choose a valid service.") from None
    if service_id <= 0:
        raise GuestRequestError("Choose a valid service.")
    return fields, first, last, service_id


def create_guest_request(session, data, owner_id, business_key):
    with session.begin():
        previous = session.execute(select(EventOutbox).where(
            EventOutbox.deduplication_key == business_key).with_for_update()).scalar_one_or_none()
        if previous is not None:
            # Key derives from session CSRF secret + form nonce, not client identity.
            saved_owner = previous.payload["member_id"]
            if owner_id is not None and owner_id != saved_owner:
                raise GuestRequestError("Request not found.", 404)
            active = session.execute(text("""
                SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
                WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='member'
            """), {"id": saved_owner}).first()
            if active is None:
                raise GuestRequestError("Request not found.", 404)
            return previous.request_id, saved_owner
        fields, first, last, service_id = _validate(data)
        service = session.execute(text("""
            SELECT s.name,s.delivery_mode FROM services s
            JOIN service_categories c ON c.category_id=s.category_id
            WHERE s.service_id=:id AND s.is_active=TRUE AND c.is_active=TRUE FOR UPDATE
        """), {"id": service_id}).first()
        if service is None:
            raise GuestRequestError("Choose an available service.")
        areas = _areas(session, service_id)
        if len(areas) != 1:
            raise GuestRequestError("The service area cannot be determined. Choose another service.")
        if fields["contact_city"].casefold() != areas[0].city.casefold():
            raise GuestRequestError("The selected service does not cover your contact city.")
        if data.get("delivery_method") != DELIVERY.get(service.delivery_mode):
            raise GuestRequestError("Choose a delivery method supported by the service.")
        priority = session.execute(text("""
            SELECT priority_id,level_name,deadline_hours FROM priority_levels WHERE level_name=:name
        """), {"name": data.get("priority")}).first()
        if priority is None or priority.deadline_hours != {"High": 6, "Medium": 12, "Low": 24}.get(priority.level_name):
            raise GuestRequestError("Choose a valid priority.")
        if owner_id is None:
            if session.execute(text("SELECT user_id FROM users WHERE email=:email"),
                               {"email": fields["contact_email"]}).first():
                raise GuestRequestError("This email cannot be used for a new guest request. Use your existing guest session or sign in.", 409)
            role = session.execute(text("SELECT role_id FROM roles WHERE role_name='member'")).scalar_one_or_none()
            if role is None:
                raise GuestRequestError("Request submission is temporarily unavailable.", 503)
            created = session.execute(text("""
                INSERT INTO users(role_id,email,password_hash,is_active)
                VALUES(:role,:email,:password,TRUE)
            """), {"role": role, "email": fields["contact_email"],
                    "password": generate_password_hash(secrets.token_urlsafe(32))})
            owner_id = created.lastrowid
            session.execute(text("""
                INSERT INTO member_profiles(user_id,first_name,last_name,phone,address,city)
                VALUES(:id,:first,:last,:phone,:address,:city)
            """), {"id": owner_id, "first": first, "last": last,
                    "phone": fields["contact_phone"], "address": fields["contact_address"],
                    "city": fields["contact_city"]})
        else:
            saved = session.execute(text("""
                SELECT u.email,p.first_name,p.last_name,p.phone,p.address,p.city
                FROM users u JOIN roles r ON r.role_id=u.role_id
                JOIN member_profiles p ON p.user_id=u.user_id
                WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='member' FOR UPDATE
            """), {"id": owner_id}).first()
            if saved is None or tuple(saved) != (fields["contact_email"], first, last,
                                                fields["contact_phone"], fields["contact_address"], fields["contact_city"]):
                raise GuestRequestError("Use the same contact details for this guest session. Existing profiles are not overwritten.", 409)
        now = utcnow()
        deadline = now + timedelta(hours=priority.deadline_hours)
        request = ServiceRequest(member_id=owner_id, service_id=service_id,
                                 service_area_id=areas[0].area_id, priority_id=priority.priority_id,
                                 title=fields["details"].splitlines()[0][:150], description=fields["details"],
                                 status="submitted", attendance_deadline=deadline)
        session.add(request)
        session.flush()
        enqueue(session, "ServiceRequestCreated", request.request_id,
                {"member_id": owner_id, "service_id": service_id, "area_id": areas[0].area_id,
                 "priority": priority.level_name, "attendance_deadline": deadline.isoformat() + "Z"},
                business_key)
        return request.request_id, owner_id


def owned_request(session, request_id, owner_id):
    if owner_id is None:
        return None
    row = session.execute(text("""
        SELECT sr.request_id,sr.status,sr.priority_id,sr.attendance_deadline,
               s.name AS service_name,p.level_name AS priority,p.deadline_hours AS priority_hours,
               mp.first_name,mp.last_name
        FROM service_requests sr JOIN services s ON s.service_id=sr.service_id
        JOIN users u ON u.user_id=sr.member_id JOIN roles role ON role.role_id=u.role_id
        JOIN priority_levels p ON p.priority_id=sr.priority_id
        JOIN member_profiles mp ON mp.user_id=sr.member_id
        WHERE sr.request_id=:id AND sr.member_id=:owner
          AND u.is_active=TRUE AND role.role_name='member'
    """), {"id": request_id, "owner": owner_id}).mappings().first()
    if row is None:
        return None
    referral = session.execute(text("""
        SELECT response_deadline FROM referrals WHERE request_id=:id ORDER BY attempt_number DESC LIMIT 1
    """), {"id": request_id}).first()
    result = dict(row)
    result.update(reference=f"CC-{request_id}", display_status=DISPLAY_STATUS.get(row["status"], row["status"]),
                  contact_name=(row["first_name"] + " " + row["last_name"]).strip(),
                  response_deadline=referral.response_deadline if referral else None)
    return result
