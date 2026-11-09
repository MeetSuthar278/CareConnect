
from flask import Blueprint, jsonify
from app import db
from app.models import Service, ServiceArea, PriorityLevel

catalog_bp = Blueprint("catalog", __name__)


@catalog_bp.get("/api/services")
def get_services():
    services = (
        db.session.query(Service)
        .filter_by(is_active=True)
        .order_by(Service.service_id)
        .all()
    )

    return jsonify([
        {"id": s.service_id, "name": s.name}
        for s in services
    ])


@catalog_bp.get("/api/service-areas")
def get_areas():
    areas = (
        db.session.query(ServiceArea)
        .filter_by(is_active=True)
        .order_by(ServiceArea.area_id)
        .all()
    )

    return jsonify([
        {
            "id": a.area_id,
            "city": a.city,
            "region": a.region_name
        }
        for a in areas
    ])


@catalog_bp.get("/api/priorities")
def get_priorities():
    priorities = (
        db.session.query(PriorityLevel)
        .order_by(PriorityLevel.priority_id)
        .all()
    )

    return jsonify([
        {
            "id": p.priority_id,
            "name": p.level_name,
            "deadline_hours": p.deadline_hours
        }
        for p in priorities
    ])
