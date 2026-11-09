"""Verified coordinator sessions, request views and organization decisions."""
import secrets
import time

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, request, session, url_for
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.auth import roles_required
from app.member import cookie_claims, csrf_valid, mint_cookie, SESSION_SECONDS
from app.services.guest_requests import DISPLAY_STATUS, DELIVERY
from app.services.outbox import utcnow
from app.services.organization_approvals import ApprovalError, decide_application, pending_applications
from app.services.organization_status import change_organization_status
from app.services.manual_assignment import AssignmentError,assignment_choices,assign_request
from app.services.reports import report_data

coordinator_bp = Blueprint('coordinator', __name__)
COOKIE = 'careconnect_coordinator'


def coordinator_identity(database, *, uid=None, user_id=None):
    selector = 'u.firebase_uid=:id' if uid is not None else 'u.user_id=:id'
    row = database.execute(text('''SELECT u.user_id FROM users u
        JOIN roles r ON r.role_id=u.role_id WHERE '''+selector+'''
        AND u.is_active=TRUE AND r.role_name='coordinator'
    '''), {'id':uid if uid is not None else user_id}).mappings().one_or_none()
    return dict(row) if row else None


@coordinator_bp.post('/api/auth/coordinator-session')
@roles_required('coordinator')
def establish_session():
    if not csrf_valid('login_csrf',request.headers.get('X-CSRF-Token')):
        return jsonify(error='Reload the login page and retry.'),403
    auth_time=g.firebase_claims.get('auth_time')
    if type(auth_time) not in (int,float) or not 0<=time.time()-auth_time<=300:
        return jsonify(error='Sign in again to start your session.'),401
    try:
        with Session(db.engine) as database:
            identity=coordinator_identity(database,user_id=g.current_user.user_id)
        if identity is None:
            return jsonify(error='Coordinator account unavailable'),403
        cookie=mint_cookie(request.headers['Authorization'].split()[1])
    except Exception as error:
        current_app.logger.error('Coordinator session unavailable (%s)',type(error).__name__)
        return jsonify(error='Could not start your session. Please retry.'),503
    session.clear()
    session['coordinator_csrf']=secrets.token_urlsafe(32)
    response=jsonify(redirect_url='/coordinator')
    response.set_cookie(COOKIE,cookie,max_age=SESSION_SECONDS,httponly=True,
                        secure=request.is_secure,samesite='Lax',path='/')
    response.delete_cookie('careconnect_member',path='/')
    response.delete_cookie('careconnect_organization',path='/')
    return response


def load_coordinator():
    g.coordinator=None
    protected=request.path.startswith('/coordinator')
    if request.path.startswith(('/team-static/','/static/','/api/')):
        return
    cookie=request.cookies.get(COOKIE)
    if cookie:
        try:
            claims=cookie_claims(cookie)
            if claims.get('email_verified') is not True or not isinstance(claims.get('uid'),str):
                raise ValueError('Invalid coordinator claims')
            with Session(db.engine) as database:
                identity=coordinator_identity(database,uid=claims['uid'])
            if identity is None:
                raise ValueError('Coordinator unavailable')
            g.coordinator=identity
            session['role']='coordinator'
            session.setdefault('coordinator_csrf',secrets.token_urlsafe(32))
        except Exception as error:
            current_app.logger.warning('Coordinator cookie unavailable (%s)',type(error).__name__)
            g.clear_coordinator_cookie=True
            if protected:
                return redirect('/login')
    if protected and g.coordinator is None:
        return redirect('/login')


def private_response(response):
    if getattr(g,'clear_coordinator_cookie',False):
        response.delete_cookie(COOKIE,path='/')
    if getattr(g,'coordinator',None) or request.path.startswith(('/coordinator','/api/auth/coordinator-session')):
        response.headers['Cache-Control']='no-store'
    return response


def request_rows(database):
    records=database.execute(text('''
        SELECT sr.request_id,sr.status AS raw_status,sr.created_at,sr.description AS details,
               sr.attendance_deadline,s.name AS service_name,s.delivery_mode,c.name AS category,
               p.level_name AS priority,p.deadline_hours AS priority_hours,
               r.response_deadline,r.status AS referral_status,r.organization_id AS org_id,o.name AS org_name,
               u.email AS contact_email,(u.firebase_uid IS NULL) AS is_guest,
               mp.first_name,mp.last_name,mp.phone AS contact_phone,mp.address AS contact_address,mp.city AS contact_city,
               (sr.attendance_deadline < :now AND a.attendance_id IS NULL
                 AND sr.status NOT IN ('completed','cancelled')) AS overdue,
               EXISTS(SELECT 1 FROM feedback f WHERE f.request_id=sr.request_id AND f.is_helpful=FALSE) AS negative_feedback
        FROM service_requests sr JOIN services s ON s.service_id=sr.service_id
        LEFT JOIN service_categories c ON c.category_id=s.category_id
        JOIN priority_levels p ON p.priority_id=sr.priority_id
        JOIN users u ON u.user_id=sr.member_id LEFT JOIN member_profiles mp ON mp.user_id=u.user_id
        LEFT JOIN referrals r ON r.referral_id=(SELECT latest.referral_id FROM referrals latest
            WHERE latest.request_id=sr.request_id ORDER BY latest.attempt_number DESC LIMIT 1)
        LEFT JOIN organizations o ON o.organization_id=r.organization_id
        LEFT JOIN attendance_records a ON a.request_id=sr.request_id
        ORDER BY sr.request_id DESC
    '''),{'now':utcnow()}).mappings().all()
    history=database.execute(text('''
        SELECT r.request_id,h.new_status AS text,h.changed_at AS time
        FROM referral_status_history h JOIN referrals r ON r.referral_id=h.referral_id
        ORDER BY h.changed_at,h.history_id
    ''')).mappings().all()
    grouped={}
    for step in history:
        grouped.setdefault(step['request_id'],[]).append(dict(step))
    result=[]
    for row in records:
        reasons=[]
        if row['raw_status']=='unmatched': reasons.append('Unmatched')
        if row['raw_status'] not in {'completed','cancelled'}:
            if row['referral_status']=='rejected': reasons.append('Rejected referral')
            if row['referral_status']=='timed_out': reasons.append('Expired referral')
        if row['overdue']: reasons.append('Overdue')
        if row['negative_feedback']: reasons.append('Manual review')
        name=((row['first_name'] or '')+' '+(row['last_name'] or '')).strip()
        result.append(dict(row,reference=f"CC-{row['request_id']}",status=DISPLAY_STATUS.get(row['raw_status'],row['raw_status']),
                           attention_reasons=reasons,contact_name=name or '-',
                           delivery_method=DELIVERY.get(row['delivery_mode'],row['delivery_mode']),
                           assigned_service_name=row['service_name'],eligible_orgs=[],
                           history=[dict(text='submitted',time=row['created_at'])]+grouped.get(row['request_id'],[])))
    return result


def notifications(database):
    return database.execute(text('''SELECT message,created_at AS time FROM notifications
        WHERE user_id=:id AND is_read=FALSE ORDER BY notification_id DESC LIMIT 20'''),
        {'id':g.coordinator['user_id']}).mappings().all()


@coordinator_bp.get('/coordinator')
def dashboard():
    from app.frontend import render_team
    with Session(db.engine) as database:
        requests=request_rows(database)
        pending=pending_applications(database)
        notes=notifications(database)
    counts=dict(pending_orgs=len(pending),total=len(requests),
                unmatched=sum(row['raw_status']=='unmatched' for row in requests),
                overdue=sum(bool(row['overdue']) for row in requests))
    return render_team('coordinator/dashboard.html',counts=counts,pending_orgs=pending,
                       attention_requests=[row for row in requests if row['attention_reasons']],notifications=notes)


@coordinator_bp.get('/coordinator/approvals')
def approvals():
    from app.frontend import render_team
    with Session(db.engine) as database:
        applications=pending_applications(database)
        notes=notifications(database)
    return render_team('coordinator/approvals.html',orgs=applications,notifications=notes,
                       coordinator_csrf=session['coordinator_csrf'])


@coordinator_bp.get('/coordinator/organizations')
def organizations_page():
    from app.frontend import render_team
    selected=request.args.get('status','')
    with Session(db.engine) as database:
        organizations=database.execute(text('''
            SELECT o.organization_id AS org_id,o.name AS org_name,o.status AS raw_status,
                   o.contact_email AS email,o.contact_phone AS phone,o.address,o.city,
                   COALESCE(a.created_at,o.created_at) AS created_at,a.status AS application_status,
                   mp.first_name,mp.last_name
            FROM organizations o LEFT JOIN organization_applications a ON a.application_id=(
                SELECT latest.application_id FROM organization_applications latest
                WHERE latest.organization_id=o.organization_id ORDER BY latest.application_id DESC LIMIT 1)
            LEFT JOIN member_profiles mp ON mp.user_id=a.submitted_by_user_id
            ORDER BY o.name,o.organization_id
        ''')).mappings().all()
        offerings=database.execute(text('''
            SELECT os.organization_id,os.service_id,sa.region_name,sa.city
            FROM organization_services os JOIN service_areas sa ON sa.area_id=os.service_area_id
            ORDER BY os.organization_id,sa.region_name,sa.city
        ''')).mappings().all()
        representatives=database.execute(text('''
            SELECT rep.organization_id,rep.full_name FROM organization_representatives rep
            JOIN users u ON u.user_id=rep.user_id JOIN roles r ON r.role_id=u.role_id
            WHERE u.is_active=TRUE AND r.role_name='representative'
            ORDER BY rep.organization_id,rep.is_primary_contact DESC,rep.user_id
        ''')).mappings().all()
        notes=notifications(database)
    contacts={}
    for rep in representatives:
        contacts.setdefault(rep['organization_id'],rep['full_name'])
    services,areas={},{}
    for offering in offerings:
        org_id=offering['organization_id']
        services.setdefault(org_id,set()).add(offering['service_id'])
        areas.setdefault(org_id,set()).add(f"{offering['region_name']}, {offering['city']}")
    result=[]
    for row in organizations:
        status={'approved':'Active','pending':'Pending','suspended':'Suspended'}[row['raw_status']]
        if row['raw_status']=='pending' and row['application_status']=='rejected':
            status='Rejected'  # Application outcome; never write a nonexistent organization enum.
        name=contacts.get(row['org_id']) or ((row['first_name'] or '')+' '+(row['last_name'] or '')).strip() or '-'
        result.append(dict(row,status=status,contact_name=name,address=row['address'] or '-',
                           service_count=len(services.get(row['org_id'],set())),
                           service_area='; '.join(sorted(areas.get(row['org_id'],set()))) or '-',
                           reviewable=row['raw_status']=='pending' and row['application_status'] in {'submitted','under_review'}))
    return render_team('coordinator/organizations.html',orgs=[row for row in result if not selected or row['status']==selected],
                       selected_status=selected,organizations_read_only=False,notifications=notes,
                       coordinator_csrf=session['coordinator_csrf'])


@coordinator_bp.post('/coordinator/organizations/<int:org_id>/status')
def organization_status(org_id):
    if not csrf_valid('coordinator_csrf',request.form.get('csrf_token')):
        abort(403)
    if set(request.form)-{'csrf_token','action'} or any(len(request.form.getlist(key))!=1 for key in request.form):
        abort(400)
    try:
        with Session(db.engine) as database:
            change_organization_status(database,org_id,g.coordinator['user_id'],request.form.get('action'))
        flash('Organization status saved.','success')
    except ApprovalError as error:
        if error.status in {400,403,404}:
            abort(error.status)
        flash(str(error),'error')
    except SQLAlchemyError:
        current_app.logger.error('Organization status transaction failed')
        flash('Could not save the organization status. Please retry.','error')
    return redirect(url_for('coordinator.organizations_page'),code=303)


@coordinator_bp.post('/coordinator/organizations/<int:org_id>/decision')
def organization_decision(org_id):
    if not csrf_valid('coordinator_csrf',request.form.get('csrf_token')):
        abort(403)
    try:
        application_id=int(request.form.get('application_id',''))
    except (ValueError,TypeError):
        abort(400)
    try:
        with Session(db.engine) as database:
            decide_application(database,org_id,application_id,g.coordinator['user_id'],
                               request.form.get('action'),request.form.get('reason'))
        flash('Application decision saved.','success')
    except ApprovalError as error:
        if error.status in {403,404}:
            abort(error.status)
        flash(str(error),'error')
    except SQLAlchemyError:
        current_app.logger.error('Organization approval transaction failed')
        flash('Could not save the decision. Please retry.','error')
    # Never redirect to a client-supplied return_to URL.
    return redirect(url_for('coordinator.approvals'),code=303)


@coordinator_bp.get('/coordinator/requests')
def requests_page():
    from app.frontend import render_team
    selected={key:request.args.get(key,'') for key in ('status','priority','org_id','attention')}
    with Session(db.engine) as database:
        requests=request_rows(database)
        orgs=database.execute(text('SELECT organization_id AS org_id,name AS org_name FROM organizations ORDER BY name')).mappings().all()
        priorities=database.execute(text('SELECT level_name,deadline_hours FROM priority_levels ORDER BY priority_id')).all()
        notes=notifications(database)
        for row in requests:
            row['eligible_orgs'],row['expected_referral_id']=assignment_choices(database,row['request_id'])
    filtered=[row for row in requests if
              (not selected['status'] or row['status']==selected['status']) and
              (not selected['priority'] or row['priority']==selected['priority']) and
              (not selected['org_id'] or str(row['org_id'])==selected['org_id']) and
              (not selected['attention'] or selected['attention'] in row['attention_reasons'])]
    return render_team('coordinator/requests.html',requests=filtered,orgs=orgs,priority_hours=dict(priorities),
                       request_statuses=list(DISPLAY_STATUS.values()),selected_status=selected['status'],
                       selected_priority=selected['priority'],selected_org=selected['org_id'],
                       selected_attention=selected['attention'],coordinator_read_only=False,notifications=notes,
                       coordinator_csrf=session['coordinator_csrf'])


@coordinator_bp.post('/coordinator/requests/<int:request_id>/assign')
def manual_assign(request_id):
    if not csrf_valid('coordinator_csrf',request.form.get('csrf_token')):
        abort(403)
    if set(request.form)-{'csrf_token','org_id','expected_referral_id'} or any(len(request.form.getlist(key))!=1 for key in request.form):
        abort(400)
    try:
        organization_id=int(request.form.get('org_id',''))
        source=int(request.form.get('expected_referral_id',''))
    except (ValueError,TypeError):
        abort(400)
    try:
        with Session(db.engine) as database:
            assign_request(database,request_id,organization_id,g.coordinator['user_id'],source)
        flash('Referral assigned.','success')
    except AssignmentError as error:
        if error.status in {400,403,404}:
            abort(error.status)
        flash(str(error),'error')
    except SQLAlchemyError:
        current_app.logger.error('Manual assignment transaction failed')
        flash('Could not assign the referral. Please reload and retry.','error')
    return redirect(url_for('coordinator.requests_page')+f'#request-{request_id}',code=303)


@coordinator_bp.get('/coordinator/logout')
def logout():
    from flask import abort
    if not csrf_valid('coordinator_csrf',request.args.get('csrf')):
        abort(403)
    session.clear()
    response=redirect('/login')
    response.delete_cookie(COOKIE,path='/')
    return response


@coordinator_bp.get('/coordinator/reports')
def reports_page():
    from app.frontend import render_team
    try:
        with Session(db.engine) as database:
            data=report_data(database)
            notes=notifications(database)
    except SQLAlchemyError:
        current_app.logger.error('Coordinator reports unavailable')
        return render_team('coordinator/reports.html',totals=dict(requests='-',completed='-',organizations='-',
                           helpful_percentage=None,feedback_count=0),by_status=[],by_category=[],notifications=[],
                           form_error='Reports could not be loaded. Please retry.'),503
    return render_team('coordinator/reports.html',notifications=notes,**data)


def register_coordinator(app):
    app.register_blueprint(coordinator_bp)
    app.before_request(load_coordinator)
    app.after_request(private_response)
