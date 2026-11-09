"""Organization pages and CSRF-protected adapters to existing referral services."""
import secrets
import time

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, request, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import db
from app.auth import roles_required
from app.member import cookie_claims, csrf_valid, mint_cookie, SESSION_SECONDS
from app.services.attendance import AttendanceError, record_attendance
from app.services.completions import CompletionError, complete_referral
from app.services.referrals import RejectionError, accept_referral, reject_referral
from app.services.outbox import utcnow
from app.services.offerings import OfferingError, organization_offerings, update_offering, add_offering
from app.services.organization_profiles import OrganizationProfileError, organization_profile, update_organization_profile
from app.services.password_sessions import password_identity

organization_bp = Blueprint('organization', __name__)
COOKIE = 'careconnect_organization'
STATUSES = {'sent':'Assigned','accepted':'Accepted','attended':'Accepted',
            'rejected':'Rejected','timed_out':'Expired','completed':'Completed'}


def representative(database, *, uid=None, user_id=None):
    selector = 'u.firebase_uid=:id' if uid is not None else 'u.user_id=:id'
    row = database.execute(text('''
        SELECT u.user_id,rep.organization_id,o.name AS org_name,o.status AS raw_status
        FROM users u JOIN roles role ON role.role_id=u.role_id
        JOIN organization_representatives rep ON rep.user_id=u.user_id
        JOIN organizations o ON o.organization_id=rep.organization_id
        WHERE ''' + selector + ''' AND u.is_active=TRUE AND role.role_name='representative'
    '''), {'id':uid if uid is not None else user_id}).mappings().one_or_none()
    return dict(row,status=row['raw_status'].title()) if row else None


@organization_bp.post('/api/auth/organization-session')
@roles_required('representative')
def establish_session():
    if not csrf_valid('login_csrf',request.headers.get('X-CSRF-Token')):
        return jsonify(error='Reload the login page and retry.'),403
    auth_time=g.firebase_claims.get('auth_time')
    if type(auth_time) not in (int,float) or not 0 <= time.time()-auth_time <= 300:
        return jsonify(error='Sign in again to start your session.'),401
    try:
        with Session(db.engine) as database:
            org=representative(database,user_id=g.current_user.user_id)
        if org is None:
            return jsonify(error='Representative account unavailable'),403
        cookie=mint_cookie(request.headers['Authorization'].split()[1])
    except Exception as error:
        current_app.logger.error('Organization session unavailable (%s)',type(error).__name__)
        return jsonify(error='Could not start your session. Please retry.'),503
    session.clear()
    session['organization_csrf']=secrets.token_urlsafe(32)
    response=jsonify(redirect_url='/organization')
    response.set_cookie(COOKIE,cookie,max_age=SESSION_SECONDS,httponly=True,
                        secure=request.is_secure,samesite='Lax',path='/')
    response.delete_cookie('careconnect_member',path='/')
    response.delete_cookie('careconnect_coordinator',path='/')
    return response


def load_organization():
    g.organization=None
    protected=request.path.startswith('/organization')
    if request.path.startswith(('/team-static/','/static/','/api/')):
        return
    cookie=request.cookies.get(COOKIE)
    if cookie:
        try:
            claims=cookie_claims(cookie)
            if claims.get('email_verified') is not True or not isinstance(claims.get('uid'),str):
                raise ValueError('Invalid organization claims')
            with Session(db.engine) as database:
                org=representative(database,uid=claims['uid'])
            if org is None:
                raise ValueError('Representative unavailable')
            g.organization=org
            session['role']='organization'
            session.setdefault('organization_csrf',secrets.token_urlsafe(32))
        except Exception as error:
            current_app.logger.warning('Organization cookie unavailable (%s)',type(error).__name__)
            g.clear_organization_cookie=True
            if protected:
                return redirect('/login')
    if protected and g.organization is None:
        return redirect('/login')


def private_response(response):
    if getattr(g,'clear_organization_cookie',False):
        response.delete_cookie(COOKIE,path='/')
    if getattr(g,'organization',None) or request.path.startswith(('/organization','/api/auth/organization-session')):
        response.headers['Cache-Control']='no-store'
    return response


def rows(database,request_id=None):
    filters='r.organization_id=:org'
    if request_id is not None:
        filters+=' AND sr.request_id=:request'
    records=database.execute(text('''
        SELECT r.referral_id,r.request_id,r.status AS raw_status,r.response_deadline,
               (r.response_deadline <= :now) AS is_overdue,
               sr.status AS request_status,sr.created_at,sr.description AS details,
               s.name AS service_name,s.delivery_mode,p.level_name AS priority,
               p.deadline_hours AS priority_hours
        FROM referrals r JOIN service_requests sr ON sr.request_id=r.request_id
        JOIN services s ON s.service_id=sr.service_id
        JOIN priority_levels p ON p.priority_id=sr.priority_id
        WHERE '''+filters+''' ORDER BY r.referral_id DESC
    '''),{'org':g.organization['organization_id'],'request':request_id,'now':utcnow()}).mappings().all()
    from app.services.guest_requests import DELIVERY
    return [dict(row,reference=f"CC-{row['request_id']}",
                 status='Cancelled' if row['request_status']=='cancelled' else STATUSES[row['raw_status']],
                 is_overdue=bool(row['is_overdue']),
                 delivery_method=DELIVERY.get(row['delivery_mode'],row['delivery_mode']),
                 assigned_service_name=row['service_name']) for row in records]


def notifications(database):
    return database.execute(text('''SELECT message,created_at AS time FROM notifications
        WHERE user_id=:id AND is_read=FALSE ORDER BY notification_id DESC LIMIT 10'''),
        {'id':g.organization['user_id']}).mappings().all()


@organization_bp.get('/organization')
def dashboard():
    from app.frontend import render_team
    with Session(db.engine) as database:
        requests=rows(database)
        services=database.execute(text('SELECT COUNT(DISTINCT service_id) FROM organization_services WHERE organization_id=:org'),
                                  {'org':g.organization['organization_id']}).scalar_one()
        notes=notifications(database)
    incoming=[row for row in requests if row['raw_status']=='sent' and row['request_status']=='matched']
    counts=dict(incoming=len(incoming),active=sum(row['raw_status'] in {'accepted','attended'} for row in requests),
                completed=sum(row['raw_status']=='completed' for row in requests),services=services)
    return render_team('organization/dashboard.html',org=g.organization,counts=counts,requests=incoming[:5],notifications=notes)


@organization_bp.get('/organization/requests')
def requests_page():
    from app.frontend import render_team
    selected=request.args.get('status','')
    with Session(db.engine) as database:
        requests=rows(database)
        notes=notifications(database)
    return render_team('organization/requests.html',requests=[row for row in requests if not selected or row['status']==selected],
                       selected_status=selected,org_active=g.organization['raw_status']=='approved',
                       organization_csrf=session['organization_csrf'],notifications=notes)


def render_organization_profile(profile,notes,error=None,status=200):
    from app.frontend import render_team,firebase_web_config
    values=dict(profile)
    if request.method=='POST':
        for key in ('contact_name','phone','address','city'):
            values[key]=request.form.get(key,values[key])
    return render_team('organization/profile.html',org=values,notifications=notes,
                       organization_csrf=session['organization_csrf'],form_error=error,
                       firebase_web_config=firebase_web_config()),status


@organization_bp.get('/organization/password-context')
def password_context():
    try:
        with Session(db.engine) as database:
            identity=password_identity(database,g.organization['user_id'],'representative')
    except SQLAlchemyError:
        current_app.logger.error('Password account lookup unavailable')
        return jsonify(error='Account service unavailable. Please retry.'),503
    if identity is None:
        return jsonify(error='Sign in again before changing your password.'),403
    return jsonify(identity)


@organization_bp.route('/organization/profile',methods=['GET','POST'])
def profile_page():
    if request.method=='POST':
        if not csrf_valid('organization_csrf',request.form.get('csrf_token')):
            abort(403)
        allowed={'csrf_token','form_type','contact_name','phone','address','city'}
        if (request.form.get('form_type')!='details' or set(request.form)-allowed
                or any(len(request.form.getlist(key))!=1 for key in request.form)):
            abort(400)
    try:
        with Session(db.engine) as database:
            profile=organization_profile(database,g.organization['user_id'],g.organization['organization_id'])
            notes=notifications(database)
    except SQLAlchemyError:
        current_app.logger.error('Organization profile view unavailable')
        fallback=dict(g.organization,contact_name='',phone='',address='',city='',email='',service_area='-')
        return render_organization_profile(fallback,[],'Profile could not be loaded. Please retry.',503)
    if profile is None:
        abort(404)
    if request.method=='GET':
        return render_organization_profile(profile,notes)
    try:
        values={key:request.form.get(key) for key in ('contact_name','phone','address','city')}
        with Session(db.engine) as database:
            update_organization_profile(database,g.organization['user_id'],g.organization['organization_id'],values)
    except OrganizationProfileError as error:
        if error.status in {403,404}:
            abort(error.status)
        return render_organization_profile(profile,notes,str(error),error.status)
    except SQLAlchemyError:
        current_app.logger.error('Organization profile update failed')
        return render_organization_profile(profile,notes,'Could not save your profile. Please retry.',503)
    flash('Profile saved.','success')
    return redirect(url_for('organization.profile_page'),code=303)


def render_services(error=None,status=200):
    from app.frontend import render_team
    from app.services.guest_requests import DELIVERY
    with Session(db.engine) as database:
        offerings=organization_offerings(database,g.organization['organization_id'])
        categories=database.execute(text('SELECT name FROM service_categories ORDER BY name')).scalars().all()
        catalog=database.execute(text('''SELECT s.service_id,s.name,s.description,s.delivery_mode,c.name AS category
            FROM services s JOIN service_categories c ON c.category_id=s.category_id
            WHERE s.is_active=TRUE AND c.is_active=TRUE ORDER BY s.name,s.service_id''')).mappings().all()
        areas=database.execute(text('''SELECT area_id,region_name,city FROM service_areas
            WHERE is_active=TRUE ORDER BY city,region_name,area_id''')).mappings().all()
        notes=notifications(database)
    return render_team('organization/services.html',services=offerings,categories=categories,
                       delivery_methods=list(DELIVERY.values()),organization_csrf=session['organization_csrf'],
                       form_error=error,notifications=notes,catalog=catalog,areas=areas),status


@organization_bp.post('/organization/services/add')
def add_service():
    if g.organization['raw_status']!='approved':
        abort(403)
    if not csrf_valid('organization_csrf',request.form.get('csrf_token')):
        abort(403)
    allowed={'csrf_token','service_id','service_area_id','status','max_referrals'}
    if (set(request.form)-allowed or
            any(len(request.form.getlist(key))!=1 for key in request.form)):
        abort(400)
    try:
        service_id=int(request.form.get('service_id',''))
        area_id=int(request.form.get('service_area_id',''))
        limit=int(request.form.get('max_referrals',''))
    except (ValueError,TypeError):
        return render_services('Choose a service, area and a valid referral limit.',400)
    try:
        with Session(db.engine) as database:
            result=add_offering(database,g.organization['user_id'],service_id=service_id,area_id=area_id,
                                status={'Active':'active','Paused':'paused'}.get(request.form.get('status')),
                                referral_limit=limit)
    except OfferingError as error:
        if error.status==403:
            abort(403)
        return render_services(str(error),error.status)
    except IntegrityError:
        return render_services('This offering changed during submission. Reload and retry with the same details.',409)
    except SQLAlchemyError:
        current_app.logger.error('Add service transaction failed')
        return render_services('Could not add the service. Please retry.',503)
    flash('Service already added.' if result['already_processed'] else 'Service added.','success')
    return redirect(url_for('organization.services_page'),code=303)


@organization_bp.route('/organization/services',methods=['GET','POST'])
def services_page():
    if g.organization['raw_status']!='approved':
        if request.method=='POST':
            abort(403)
        flash('My Services is available only while your organization is approved.','error')
        return redirect(url_for('organization.dashboard'))
    if request.method=='GET':
        return render_services()
    if not csrf_valid('organization_csrf',request.form.get('csrf_token')):
        abort(403)
    allowed={'csrf_token','organization_service_id','status','max_referrals','expected_status',
             'expected_limit','availability_version'}
    if set(request.form)-allowed:
        return render_services('Only availability and referral limit can be changed here.',400)
    try:
        offering_id=int(request.form.get('organization_service_id',''))
        limit=int(request.form.get('max_referrals',''))
        expected_limit=int(request.form.get('expected_limit',''))
        version=int(request.form.get('availability_version',''))
    except (ValueError,TypeError):
        return render_services('Choose an existing offering and a valid referral limit.',400)
    target={'Active':'active','Paused':'paused'}.get(request.form.get('status'))
    return save_offering(offering_id,target,version,referral_limit=limit,expected_limit=expected_limit)


@organization_bp.post('/organization/services/<int:offering_id>/availability')
def service_availability(offering_id):
    if g.organization['raw_status']!='approved':
        abort(403)
    if not csrf_valid('organization_csrf',request.form.get('csrf_token')):
        abort(403)
    if set(request.form)-{'csrf_token','target_status','expected_status','availability_version'}:
        abort(400)
    try:
        version=int(request.form.get('availability_version',''))
    except (ValueError,TypeError):
        abort(400)
    return save_offering(offering_id,request.form.get('target_status'),version)


def save_offering(offering_id,target,version,**settings):
    try:
        with Session(db.engine) as database:
            update_offering(database,offering_id,g.organization['user_id'],status=target,
                            expected_status=request.form.get('expected_status'),availability_version=version,**settings)
    except OfferingError as error:
        if error.status in {403,404}:
            abort(error.status)
        return render_services(str(error),error.status)
    except SQLAlchemyError:
        current_app.logger.error('Organization offering transaction failed')
        return render_services('Could not save service settings. Please retry.',503)
    flash('Service settings saved.','success')
    return redirect(url_for('organization.services_page'),code=303)


@organization_bp.get('/organization/requests/<int:request_id>')
def details(request_id):
    from app.frontend import render_team
    with Session(db.engine) as database:
        requests=rows(database,request_id)
        if not requests:
            abort(404)
        record=requests[0]
        record['history']=database.execute(text('''SELECT new_status AS text,changed_at AS time
            FROM referral_status_history WHERE referral_id=:id ORDER BY history_id'''),
            {'id':record['referral_id']}).mappings().all()
        # Never fetch or serialize member contact fields before this org accepts.
        if record['raw_status'] in {'accepted','attended','completed'}:
            contact=database.execute(text('''
                SELECT u.email AS contact_email,p.phone AS contact_phone,p.address AS contact_address,
                       p.first_name,p.last_name FROM service_requests sr JOIN users u ON u.user_id=sr.member_id
                JOIN member_profiles p ON p.user_id=u.user_id WHERE sr.request_id=:id
            '''),{'id':request_id}).mappings().one_or_none()
            if contact:
                record.update(contact,contact_name=(contact['first_name']+' '+contact['last_name']).strip())
        notes=notifications(database)
    return render_team('organization/request_details.html',req=record,
                       org_active=g.organization['raw_status']=='approved',
                       organization_csrf=session['organization_csrf'],notifications=notes)


@organization_bp.post('/organization/requests/<int:request_id>/action')
def act(request_id):
    if not csrf_valid('organization_csrf',request.form.get('csrf_token')):
        abort(403)
    try:
        referral_id=int(request.form.get('referral_id',''))
    except (ValueError,TypeError):
        abort(400)
    action=request.form.get('action') or ('complete' if request.form.get('status')=='Completed' else None)
    if action not in {'accept','reject','attend','complete'}:
        abort(400)
    reason=request.form.get('reason','').strip()
    if action=='reject' and not 1<=len(reason)<=255:
        flash('Enter a rejection reason containing 1 to 255 characters.','error')
        return redirect(url_for('organization.details',request_id=request_id),code=303)
    try:
        with Session(db.engine) as database:
            owned=database.execute(text('''SELECT referral_id FROM referrals WHERE referral_id=:referral
                AND request_id=:request AND organization_id=:org'''),
                {'referral':referral_id,'request':request_id,'org':g.organization['organization_id']}).first()
        if not owned:
            abort(404)
        with Session(db.engine) as database:
            if action=='accept':
                if g.organization['raw_status']!='approved':
                    abort(403)
                accept_referral(database,referral_id,g.organization['user_id'])
            elif action=='reject':
                reject_referral(database,referral_id,g.organization['user_id'],reason)
            elif action=='attend':
                record_attendance(database,referral_id,g.organization['user_id'])
            else:
                complete_referral(database,referral_id,g.organization['user_id'])
        flash('Update saved.','success')
    except (RejectionError,AttendanceError,CompletionError) as error:
        if error.status==404:
            abort(404)
        flash(str(error),'error')
    except SQLAlchemyError:
        current_app.logger.error('Organization referral update failed')
        flash('Could not save this update. Please retry.','error')
    return redirect(url_for('organization.details',request_id=request_id),code=303)


@organization_bp.get('/organization/logout')
def logout():
    if not csrf_valid('organization_csrf',request.args.get('csrf')):
        abort(403)
    session.clear()
    response=redirect('/login')
    response.delete_cookie(COOKIE,path='/')
    return response


def register_organization(app):
    app.register_blueprint(organization_bp)
    app.before_request(load_organization)
    app.after_request(private_response)
