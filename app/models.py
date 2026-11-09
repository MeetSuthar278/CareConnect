
from app import db
from sqlalchemy.dialects.mysql import DATETIME, TINYINT, VARCHAR


class Role(db.Model):
    __tablename__ = "roles"

    role_id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(50), nullable=False)


class User(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.role_id"),
        nullable=False
    )
    email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class Service(db.Model):
    __tablename__ = "services"

    service_id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class ServiceArea(db.Model):
    __tablename__ = "service_areas"

    area_id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100))
    region_name = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)


class PriorityLevel(db.Model):
    __tablename__ = "priority_levels"

    priority_id = db.Column(db.Integer, primary_key=True)
    level_name = db.Column(db.String(20), nullable=False)
    deadline_hours = db.Column(db.Integer, nullable=False)


class ServiceRequest(db.Model):
    __tablename__ = "service_requests"

    request_id = db.Column(db.Integer, primary_key=True)

    member_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id"),
        nullable=False
    )

    service_id = db.Column(
        db.Integer,
        db.ForeignKey("services.service_id"),
        nullable=False
    )

    service_area_id = db.Column(
        db.Integer,
        db.ForeignKey("service_areas.area_id"),
        nullable=False
    )

    priority_id = db.Column(
        db.Integer,
        db.ForeignKey("priority_levels.priority_id"),
        nullable=False
    )

    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default="submitted")
    attendance_deadline = db.Column(db.DateTime, nullable=False)

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp()
    )


class Referral(db.Model):
    __tablename__ = "referrals"
    __table_args__ = (
        db.UniqueConstraint("request_id", "attempt_number", name="uq_request_attempt"),
        db.UniqueConstraint("request_id", "active_slot", name="uq_referral_active_request"),
    )

    referral_id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey("service_requests.request_id"),
        nullable=False
    )
    organization_id = db.Column(db.Integer, nullable=False)
    attempt_number = db.Column(db.Integer, nullable=False)
    is_backup = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(30), default="sent")
    response_deadline = db.Column(db.DateTime, nullable=False)
    responded_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.String(255))
    active_slot = db.Column(TINYINT, db.Computed(
        "CASE WHEN status IN ('sent', 'accepted', 'attended') THEN 1 ELSE NULL END",
        persisted=False,
    ))


class ReferralStatusHistory(db.Model):
    __tablename__ = "referral_status_history"

    history_id = db.Column(db.Integer, primary_key=True)
    referral_id = db.Column(
        db.Integer,
        db.ForeignKey("referrals.referral_id"),
        nullable=False
    )
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50), nullable=False)
    changed_by_user_id = db.Column(db.Integer)
    notes = db.Column(db.String(255))


# SQL baselines + migrations are authoritative; do not use create_all() to
# provision this partially mapped database. These additions require migration 001.
class OrganizationService(db.Model):
    __tablename__ = "organization_services"
    __table_args__ = (
        db.CheckConstraint(
            "active_referral_limit >= 0 AND current_active_referrals >= 0 "
            "AND current_active_referrals <= active_referral_limit",
            name="ck_org_service_capacity",
        ),
    )
    organization_service_id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.service_id"), nullable=False)
    service_area_id = db.Column(db.Integer, db.ForeignKey("service_areas.area_id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, server_default="active")
    active_referral_limit = db.Column(db.Integer, nullable=False, server_default="10")
    current_active_referrals = db.Column(db.Integer, nullable=False, server_default="0")


class Notification(db.Model):
    __tablename__ = "notifications"
    __table_args__ = (
        db.UniqueConstraint("user_id", "deduplication_key", name="uq_notification_delivery"),
    )
    notification_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    type = db.Column(db.String(30), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, server_default=db.false())
    related_request_id = db.Column(db.Integer, db.ForeignKey("service_requests.request_id"))
    deduplication_key = db.Column(VARCHAR(100, charset="ascii", collation="ascii_bin"))
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())


class EventOutbox(db.Model):
    __tablename__ = "event_outbox"
    __table_args__ = (
        db.UniqueConstraint("deduplication_key", name="uq_outbox_business_event"),
        db.Index("idx_outbox_pending", "published_at", "available_at"),
        db.CheckConstraint("attempts >= 0", name="ck_outbox_attempts"),
    )
    event_id = db.Column(VARCHAR(36, charset="ascii", collation="ascii_bin"), primary_key=True)
    deduplication_key = db.Column(VARCHAR(100, charset="ascii", collation="ascii_bin"), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    event_version = db.Column(db.Integer, nullable=False, server_default="1")
    request_id = db.Column(db.Integer, db.ForeignKey(
        "service_requests.request_id", name="fk_outbox_request",
        ondelete="RESTRICT", onupdate="CASCADE",
    ), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(DATETIME(fsp=6), nullable=False, server_default=db.text("CURRENT_TIMESTAMP(6)"))
    available_at = db.Column(DATETIME(fsp=6), nullable=False, server_default=db.text("CURRENT_TIMESTAMP(6)"))
    published_at = db.Column(DATETIME(fsp=6))
    attempts = db.Column(db.Integer, nullable=False, server_default="0")
    last_error = db.Column(db.Text)
