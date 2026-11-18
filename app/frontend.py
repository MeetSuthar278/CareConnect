"""Latest team templates; existing legacy demo files remain intact."""
from pathlib import Path
from datetime import datetime, timezone
import secrets

from flask import Blueprint, abort, current_app, g, render_template, request, session, url_for
from jinja2 import FileSystemLoader
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.services.guest_requests import owned_request, service_choices
from app.services.service_browsing import public_services


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
frontend_bp = Blueprint("team_frontend", __name__,
                        static_folder=str(FRONTEND / "static"),
                        static_url_path="/team-static")

# These are existing team navigation destinations, not implemented API handlers.
# Generating their URLs must not manufacture authentication/dashboard behavior.
PENDING_LINKS = {}


def team_url_for(endpoint, **values):
    if endpoint == "static":
        return url_for("team_frontend.static", **values)
    if endpoint in PENDING_LINKS:
        return PENDING_LINKS[endpoint]
    org_routes = {'org_dashboard':'dashboard','org_requests':'requests_page',
                  'org_request_details':'details','org_respond':'act','org_update_status':'act',
                  'org_services':'services_page','org_toggle_service':'service_availability',
                  'org_profile':'profile_page'}
    if endpoint in org_routes:
        return url_for('organization.' + org_routes[endpoint], **values)
    coordinator_routes={'coord_dashboard':'dashboard','coord_requests':'requests_page',
                        'coord_approvals':'approvals','coord_org_action':'organization_decision',
                        'coord_organizations':'organizations_page','coord_org_status':'organization_status',
                        'coord_reassign':'manual_assign','coord_reports':'reports_page'}
    if endpoint in coordinator_routes:
        return url_for('coordinator.'+coordinator_routes[endpoint],**values)
    if endpoint == 'logout' and session.get('role') == 'coordinator':
        return url_for('coordinator.logout',csrf=session.get('coordinator_csrf',''))
    if endpoint == 'logout' and session.get('role') == 'organization':
        return url_for('organization.logout',csrf=session.get('organization_csrf',''))
    if endpoint in {'ind_dashboard', 'my_requests', 'request_details', 'logout'}:
        mapped = {'ind_dashboard':'dashboard', 'my_requests':'my_requests',
                  'request_details':'details', 'logout':'logout'}[endpoint]
        if endpoint == 'logout':
            values['csrf'] = session.get('member_csrf', '')
        return url_for('member.' + mapped, **values)
    if endpoint == 'feedback':
        return url_for('member.feedback_page',**values)
    if endpoint == 'profile':
        return url_for('member.profile_page',**values)
    if endpoint == 'cancel_request':
        return url_for('member.cancel',**values)
    return url_for(endpoint, **values)


def render_team(template_name, **context):
    environment = current_app.jinja_env.overlay(
        loader=FileSystemLoader(str(FRONTEND / "templates")))
    environment.filters = dict(environment.filters, display_time=display_time)
    template = environment.get_template(template_name)
    return render_template(template, url_for=team_url_for, **context)


def display_time(value):
    if value is None:
        return "Time not recorded"
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def firebase_web_config():
    # Firebase web configuration is public, not an Admin credential or password.
    # Values come from the teammate's reviewed client configuration.
    return {
        "apiKey": "AIzaSyC7ZQpLZmwCIoBo7cCGQPDPjFytildgrZc",
        "authDomain": "careconnect-7132c.firebaseapp.com",
        "projectId": "careconnect-7132c",
        "appId": "1:57056102914:web:c4700cd8164e7b1538b51b",
    }


def login_page():
    session.setdefault('login_csrf', secrets.token_urlsafe(32))
    return render_team("auth/login.html", firebase_web_config=firebase_web_config(),
                       login_csrf=session['login_csrf'])


def signup_page():
    return render_team("auth/signup.html")


def individual_registration_page():
    return render_team("auth/register_individual.html", firebase_web_config=firebase_web_config())


def organization_registration_page():
    return render_team("auth/register_organization.html", firebase_web_config=firebase_web_config())


def home_page():
    return render_team("public/home.html")


def render_browse(services, *, error=None, status=200):
    from app.services.guest_requests import DELIVERY
    search=request.args.get('search','').strip()
    category=request.args.get('category','')
    delivery=request.args.get('delivery','')
    filtered=[row for row in services if
              (not category or row['category']==category) and
              (not delivery or row['delivery_method']==delivery) and
              (not search or search.casefold() in ' '.join(
                  str(row[key]) for key in ('service_name','category','description','org_name','area')).casefold())]
    return render_team('public/browse_services.html',services=filtered,
                       categories=sorted({row['category'] for row in services}),
                       delivery_methods=list(DELIVERY.values()),search=search,
                       selected_category=category,selected_delivery=delivery,form_error=error),status


def browse_services_page():
    try:
        with Session(db.engine) as database:
            services=public_services(database)
    except SQLAlchemyError:
        current_app.logger.error('Public service catalog unavailable')
        return render_browse([],error='Services could not be loaded. Please try again later.',status=503)
    return render_browse(services)


def service_details_page(service_id):
    try:
        with Session(db.engine) as database:
            services=public_services(database)
    except SQLAlchemyError:
        current_app.logger.error('Public service details unavailable')
        return render_browse([],error='Services could not be loaded. Please try again later.',status=503)
    service=next((row for row in services if row['service_id']==service_id),None)
    if service is None:
        abort(404)
    return render_team('public/service_details.html',service=service)


def request_page(error=None, status=200):
    member = getattr(g, 'member', None)
    csrf_key = 'member_csrf' if member else 'guest_csrf'
    session.setdefault(csrf_key, secrets.token_urlsafe(32))
    # POST validation errors retain their nonce; a new GET offers a new submission.
    nonce = request.form.get("submission_nonce") if request.method == "POST" else None
    nonce = nonce or secrets.token_urlsafe(24)
    try:
        with Session(db.engine) as database:
            services = service_choices(database)
            priorities = database.execute(text(
                "SELECT level_name,deadline_hours FROM priority_levels ORDER BY priority_id"
            )).all()
    except SQLAlchemyError:
        services, priorities = [], []
        error, status = "Services could not be loaded. Please try again later.", 503
    selected = request.form.get("service_id") or request.args.get("service_id")
    selected = int(selected) if selected and selected.isdecimal() else None
    return render_team("individual/request_form.html", services=services,
                       selected_service_id=selected, user=member,
                       priority_hours=dict(priorities), form_error=error,
                       csrf_token=session[csrf_key], submission_nonce=nonce), status


def confirmation_page(reference):
    if not reference.startswith("CC-") or not reference[3:].isdigit():
        abort(404)
    with Session(db.engine) as database:
        member = getattr(g, 'member', None)
        owner = member['user_id'] if member else session.get('guest_member_id')
        record = owned_request(database, int(reference[3:]), owner)
    if record is None:
        abort(404)
    return render_team("individual/request_confirmation.html",
                       req=dict(record, status=record["display_status"]),
                       status_url=url_for('member.request_status' if member else 'requests.guest_request_status',
                                          request_id=record['request_id']))


def register_frontend(app):
    app.register_blueprint(frontend_bp)
    app.add_url_rule("/login", endpoint="login", view_func=login_page)
    app.add_url_rule("/signup", endpoint="signup", view_func=signup_page)
    app.add_url_rule("/register/individual", endpoint="register_individual",
                     view_func=individual_registration_page)
    app.add_url_rule("/register/organization", endpoint="register_organization",
                     view_func=organization_registration_page)
    app.add_url_rule("/", endpoint="home", view_func=home_page)
    app.add_url_rule("/services", endpoint="browse_services", view_func=browse_services_page)
    app.add_url_rule("/services/<int:service_id>", endpoint="service_details", view_func=service_details_page)
    app.add_url_rule("/get-connected", endpoint="request_form", view_func=request_page)
    app.add_url_rule("/get-connected/done/<reference>", endpoint="request_confirmation",
                     view_func=confirmation_page)

    @app.after_request
    def private_guest_pages(response):
        if request.path.startswith(("/services", "/get-connected", "/api/guest/requests", "/register/individual", "/register/organization")):
            response.headers["Cache-Control"] = "no-store"
        return response
