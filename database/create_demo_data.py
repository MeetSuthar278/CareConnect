"""Add synthetic check-in data to an EMPTY migrated database. Never resets data.
Run from repository root: python -m database.create_demo_data
"""
import secrets
from sqlalchemy import text
from werkzeug.security import generate_password_hash
from app import create_app, db


def main():
    app = create_app()
    with app.app_context(), db.engine.begin() as c:
        c.execute(text("SET time_zone = '+00:00'"))
        tables = c.execute(text("SHOW TABLES")).scalars().all()
        if "event_outbox" not in tables:
            raise RuntimeError("Apply migration 001 before adding demo data")
        if any(c.execute(text("SELECT COUNT(*) FROM `" + t + "`")).scalar() for t in tables):
            raise RuntimeError("Database is not empty; stopped without changing existing records")
        c.execute(text("INSERT INTO roles(role_id,role_name) VALUES(1,'member'),(2,'representative'),(3,'coordinator')"))
        # No login feature yet: random passwords are hashed and not exposed.
        for uid, role, email in [(9,1,"member@careconnect.example.test"),
                                 (1,3,"coordinator@careconnect.example.test"),
                                 (4,2,"partner-a@careconnect.example.test"),
                                 (5,2,"partner-b@careconnect.example.test")]:
            c.execute(text("INSERT INTO users(user_id,role_id,email,password_hash,is_active) VALUES(:id,:role,:email,:hash,TRUE)"),
                      {"id":uid,"role":role,"email":email,"hash":generate_password_hash(secrets.token_urlsafe(32))})
        c.execute(text("INSERT INTO member_profiles(user_id,first_name,last_name,phone,city) VALUES(9,'Demo','Member','403-555-0100','Calgary')"))
        c.execute(text("INSERT INTO service_categories(category_id,name,description) VALUES(1,'Demo Food Assistance','Synthetic non-medical demo catalog')"))
        c.execute(text("INSERT INTO services(service_id,category_id,name,description) VALUES(1,1,'Demo Food Support','Synthetic check-in service; no real assistance')"))
        c.execute(text("INSERT INTO service_areas(area_id,city,region_name) VALUES(1,'Calgary','Demo Downtown')"))
        c.execute(text("INSERT INTO priority_levels(priority_id,level_name,deadline_hours) VALUES(1,'High',6),(2,'Medium',12),(3,'Low',24)"))
        for oid, uid, label, phone in [(1,4,"A","403-555-0101"),(2,5,"B","403-555-0102")]:
            c.execute(text("INSERT INTO organizations(organization_id,name,contact_email,contact_phone,status) VALUES(:id,:name,:email,:phone,'approved')"),
                      {"id":oid,"name":"Demo Partner " + label,"email":"partner-" + label.lower() + "@careconnect.example.test","phone":phone})
            c.execute(text("INSERT INTO organization_representatives(user_id,organization_id,full_name,is_primary_contact) VALUES(:user,:org,:name,TRUE)"),
                      {"user":uid,"org":oid,"name":"Demo Representative " + label})
            c.execute(text("INSERT INTO organization_services(organization_service_id,organization_id,service_id,service_area_id,active_referral_limit,current_active_referrals) VALUES(:id,:id,1,1,5,0)"), {"id":oid})
            for priority in [1,2,3]:
                c.execute(text("INSERT INTO service_priority_support(organization_service_id,priority_id,is_supported) VALUES(:org,:priority,TRUE)"), {"org":oid,"priority":priority})
    print("Committed synthetic demo data: member 9, coordinator 1, representatives 4/5, partners 1/2.")
    print("Service 1, area 1, priorities High=1 / Medium=2 / Low=3. Capacity 0/5 each.")
    print("No requests, referrals, notifications or outbox events were created.")


if __name__ == "__main__":
    main()
