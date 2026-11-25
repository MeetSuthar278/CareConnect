"""In-memory SQL tests. SQLite adapters do NOT test MySQL locks or migration DDL."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.dialects.mysql.dml import Insert as MySQLInsert
from sqlalchemy.dialects.sqlite import insert
from app.models import Notification


class LocalSession(Session):
    def execute(self, statement, params=None, **kwargs):
        if isinstance(statement, TextClause):
            sql = statement.text.replace(" FOR UPDATE", "")
            # SQLite divides integers differently from MySQL.
            sql = sql.replace("END) /", "END) * 1.0 /")
            statement = text(sql)
        elif isinstance(statement, MySQLInsert):
            values = statement.compile().params
            statement = insert(Notification).values(**values).on_conflict_do_nothing(
                index_elements=["user_id", "deduplication_key"])
        return super().execute(statement, params, **kwargs)


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    ddl = [
        "CREATE TABLE roles(role_id INTEGER PRIMARY KEY, role_name TEXT)",
        "CREATE TABLE users(user_id INTEGER PRIMARY KEY, role_id INTEGER, email TEXT, password_hash TEXT, is_active BOOLEAN)",
        "CREATE TABLE services(service_id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, is_active BOOLEAN)",
        "CREATE TABLE service_areas(area_id INTEGER PRIMARY KEY, city TEXT, region_name TEXT, is_active BOOLEAN)",
        "CREATE TABLE priority_levels(priority_id INTEGER PRIMARY KEY, level_name TEXT, deadline_hours INTEGER)",
        "CREATE TABLE organizations(organization_id INTEGER PRIMARY KEY, status TEXT)",
        "CREATE TABLE organization_services(organization_service_id INTEGER PRIMARY KEY, organization_id INTEGER, service_id INTEGER, service_area_id INTEGER, status TEXT, active_referral_limit INTEGER, current_active_referrals INTEGER CHECK(current_active_referrals >= 0 AND current_active_referrals <= active_referral_limit))",
        "CREATE TABLE service_priority_support(organization_service_id INTEGER, priority_id INTEGER, is_supported BOOLEAN)",
        "CREATE TABLE service_requests(request_id INTEGER PRIMARY KEY, member_id INTEGER, service_id INTEGER, service_area_id INTEGER, priority_id INTEGER, title TEXT, description TEXT, status TEXT, attendance_deadline DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE referrals(referral_id INTEGER PRIMARY KEY, request_id INTEGER, organization_id INTEGER, attempt_number INTEGER, is_backup BOOLEAN, status TEXT, response_deadline DATETIME, responded_at DATETIME, rejection_reason TEXT, active_slot INTEGER GENERATED ALWAYS AS (CASE WHEN status IN ('sent','accepted','attended') THEN 1 ELSE NULL END) VIRTUAL, UNIQUE(request_id,attempt_number), UNIQUE(request_id,active_slot))",
        "CREATE TABLE referral_status_history(history_id INTEGER PRIMARY KEY, referral_id INTEGER, old_status TEXT, new_status TEXT, changed_by_user_id INTEGER, notes TEXT)",
        "CREATE TABLE attendance_records(attendance_id INTEGER PRIMARY KEY, referral_id INTEGER, first_attended_at DATETIME)",
        "CREATE TABLE organization_representatives(user_id INTEGER, organization_id INTEGER, is_primary_contact BOOLEAN)",
        "CREATE TABLE notifications(notification_id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, title TEXT, message TEXT, is_read BOOLEAN DEFAULT 0, related_request_id INTEGER, deduplication_key TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,deduplication_key))",
        "CREATE TABLE event_outbox(event_id TEXT PRIMARY KEY, deduplication_key TEXT UNIQUE, event_type TEXT, event_version INTEGER, request_id INTEGER, payload JSON, created_at DATETIME, available_at DATETIME, published_at DATETIME, attempts INTEGER, last_error TEXT)",
    ]
    with engine.begin() as c:
        for sql in ddl:
            c.execute(text(sql))
        for sql in [
            "INSERT INTO roles VALUES(1,'member'),(2,'representative'),(3,'coordinator')",
            "INSERT INTO users VALUES(9,1,'member@example.test','demo',1),(4,2,'rep@example.test','demo',1),(1,3,'coord@example.test','demo',1)",
            "INSERT INTO services VALUES(1,1,'Demo service',1)",
            "INSERT INTO service_areas VALUES(1,'Calgary','Downtown',1)",
            "INSERT INTO priority_levels VALUES(1,'High',6)",
            "INSERT INTO organizations VALUES(1,'approved'),(2,'approved')",
            "INSERT INTO organization_services VALUES(1,1,1,1,'active',10,0),(2,2,1,1,'active',10,1)",
            "INSERT INTO service_priority_support VALUES(1,1,1),(2,1,1)",
            "INSERT INTO organization_representatives VALUES(4,1,1)",
            "INSERT INTO service_requests(request_id,member_id,service_id,service_area_id,priority_id,title,description,status,attendance_deadline) VALUES(1,9,1,1,1,'Demo','Synthetic request','submitted','2099-01-01 12:00:00')",
        ]:
            c.execute(text(sql))
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with LocalSession(engine) as session:
        yield session


@pytest.fixture
def event():
    return {"event_id":"test-request-event", "event_type":"ServiceRequestCreated",
            "event_version":1, "timestamp":"2026-10-27T12:00:00Z",
            "request_id":1, "payload":{}}
