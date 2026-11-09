"""Firebase session cookies and ownership-scoped member pages."""
from datetime import timedelta
import hashlib
import hmac
import secrets
import time

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, request, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import db
from app.auth import roles_required
from app.services.guest_requests import DISPLAY_STATUS, GuestRequestError, create_guest_request, owned_request
from app.services.feedback import FeedbackError, submit_feedback
from app.services.member_profiles import ProfileError, update_profile
from app.services.cancellations import CancellationError,cancel_request
from app.services.password_sessions import password_identity

member_bp = Blueprint('member', __name__)
COOKIE = 'careconnect_member'
SESSION_SECONDS = 3600


def firebase_app():
    import firebase_admin
    project = current_app.config['FIREBASE_PROJECT_ID']
    try:
        return firebase_admin.get_app(project)
    except ValueError:
        try:
            return firebase_admin.initialize_app(options={'projectId': project}, name=project)
        except ValueError:
            return firebase_admin.get_app(project)


def mint_cookie(token):
    from firebase_admin import auth
    result = auth.create_session_cookie(token, expires_in=timedelta(seconds=SESSION_SECONDS), app=firebase_app())
    return result.decode() if isinstance(result, bytes) else result


def cookie_claims(cookie):
    from firebase_admin import auth
    return auth.verify_session_cookie(cookie, check_revoked=True, app=firebase_app())


def csrf_valid(key, value):
    expected = session.get(key)
    return (isinstance(expected, str) and isinstance(value, str)
            and hmac.compare_digest(expected.encode(), value.encode()))


def member_profile(database, member_id):
    row = database.execute(text('''
        SELECT u.user_id,u.email,p.first_name,p.last_name,p.phone,p.address,p.city
        FROM users u JOIN roles r ON r.role_id=u.role_id
        JOIN member_profiles p ON p.user_id=u.user_id
        WHERE u.user_id=:id AND u.is_active=TRUE AND r.role_name='member'
    '''), {'id': member_id}).mappings().one_or_none()
    return dict(row, full_name=(row['first_name']+' '+row['last_name']).strip()) if row else None


@member_bp.post('/api/auth/session')
@roles_required('member')
def establish_session():
    if not csrf_valid('login_csrf', request.headers.get('X-CSRF-Token')):
        return jsonify(error='Reload the login page and retry.'), 403
    authenticated_at = g.firebase_claims.get('auth_time')
    if (type(authenticated_at) not in (int, float)
            or not 0 <= time.time() - authenticated_at <= 300):
        return jsonify(error='Sign in again to start a member session.'), 401
    try:
        with Session(db.engine) as database:
            profile = member_profile(database, g.current_user.user_id)
        if profile is None:
            return jsonify(error='Finish individual registration before opening your dashboard.'), 409
        cookie = mint_cookie(request.headers['Authorization'].split()[1])
    except Exception as error:
        current_app.logger.error('Member session unavailable (%s)', type(error).__name__)
        return jsonify(error='Could not start your session. Please retry.'), 503
    # Rotate browser state; guest ownership is never transferred to this account.
    session.clear()
    session['member_csrf'] = secrets.token_urlsafe(32)
    response = jsonify(redirect_url='/member')
    response.set_cookie(COOKIE, cookie, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.is_secure, samesite='Lax', path='/')
    response.delete_cookie('careconnect_organization', path='/')
    response.delete_cookie('careconnect_coordinator', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return response


def load_member():
    # Template role/name are presentation state only, never authentication evidence.
    session.pop('role', None)
    session.pop('name', None)
    g.member = None
    protected = request.path.startswith(('/member', '/api/member'))
    if request.path.startswith(('/team-static/', '/static/')):
        return None
    if request.path.startswith('/api/') and not protected:
        return None  # Existing bearer-only APIs keep their authorization contract.
    cookie = request.cookies.get(COOKIE)
    if cookie:
        try:
            claims = cookie_claims(cookie)
            if not isinstance(claims.get('uid'), str):
                raise ValueError('Invalid member claims')
            with Session(db.engine) as database:
                member_id = database.execute(text('''
                    SELECT u.user_id FROM users u JOIN roles r ON r.role_id=u.role_id
                    WHERE u.firebase_uid=:uid AND u.is_active=TRUE AND r.role_name='member'
                '''), {'uid': claims['uid']}).scalar_one_or_none()
                profile = member_profile(database, member_id) if member_id else None
            if profile is None:
                raise ValueError('Member profile unavailable')
            g.member = profile
            session['role'] = 'individual'
            session['name'] = profile['first_name']
            session.setdefault('member_csrf', secrets.token_urlsafe(32))
        except Exception as error:
            current_app.logger.warning('Member cookie unavailable (%s)', type(error).__name__)
            g.clear_member_cookie = True
            # Fail closed on the form: an expired login cannot create a guest request.
            if protected or request.path.startswith('/get-connected'):
                return (jsonify(error='Sign in again'), 401) if request.path.startswith('/api/') else redirect('/login')
    if protected and g.member is None:
        return (jsonify(error='Authentication required'), 401) if request.path.startswith('/api/') else redirect('/login')


def private_response(response):
    if getattr(g, 'clear_member_cookie', False):
        response.delete_cookie(COOKIE, path='/')
    if (getattr(g, 'member', None) or request.path.startswith(('/member', '/api/member', '/api/auth/session', '/login', '/logout'))):
        response.headers['Cache-Control'] = 'no-store'
    return response


@member_bp.get('/member')
def dashboard():
    from app.frontend import render_team
    rows = member_requests()
    with Session(db.engine) as database:
        notes=database.execute(text('''SELECT message,created_at AS time FROM notifications
            WHERE user_id=:id AND is_read=FALSE ORDER BY notification_id DESC LIMIT 10'''),
            {'id':g.member['user_id']}).mappings().all()
    return render_team('individual/dashboard.html', requests=rows[:5],
                       active_count=sum(r['raw_status'] not in {'completed', 'cancelled', 'unmatched'} for r in rows),
                       completed_count=sum(r['raw_status']=='completed' for r in rows),notifications=notes)


def render_profile(error=None,status=200):
    from app.frontend import render_team,firebase_web_config
    profile=dict(g.member)
    if request.method=='POST':
        for key in ('full_name','phone','address','city'):
            profile[key]=request.form.get(key,profile[key])
    try:
        with Session(db.engine) as database:
            notes=database.execute(text('''SELECT message,created_at AS time FROM notifications
                WHERE user_id=:id AND is_read=FALSE ORDER BY notification_id DESC LIMIT 10'''),
                {'id':g.member['user_id']}).mappings().all()
    except SQLAlchemyError:
        notes=[]
        error,status='Profile could not be loaded. Please retry.',503
        current_app.logger.error('Member profile view unavailable')
    return render_team('individual/profile.html',user=profile,member_csrf=session['member_csrf'],
                       notifications=notes,form_error=error,firebase_web_config=firebase_web_config()),status


@member_bp.get('/member/password-context')
def password_context():
    try:
        with Session(db.engine) as database:
            identity=password_identity(database,g.member['user_id'],'member')
    except SQLAlchemyError:
        current_app.logger.error('Password account lookup unavailable')
        return jsonify(error='Account service unavailable. Please retry.'),503
    if identity is None:
        return jsonify(error='Sign in again before changing your password.'),403
    return jsonify(identity)


@member_bp.route('/member/profile',methods=['GET','POST'])
def profile_page():
    if request.method=='GET':
        return render_profile()
    if not csrf_valid('member_csrf',request.form.get('csrf_token')):
        abort(403)
    allowed={'csrf_token','form_type','full_name','phone','address','city'}
    if (request.form.get('form_type')!='details' or set(request.form)-allowed
            or any(len(request.form.getlist(key))!=1 for key in request.form)):
        abort(400)
    try:
        values={key:request.form.get(key) for key in ('full_name','phone','address','city')}
        with Session(db.engine) as database:
            update_profile(database,g.member['user_id'],values)
    except ProfileError as error:
        if error.status in {403,404}:
            abort(error.status)
        return render_profile(str(error),error.status)
    except SQLAlchemyError:
        current_app.logger.error('Member profile update failed')
        return render_profile('Could not save your profile. Please retry.',503)
    flash('Profile saved.','success')
    return redirect(url_for('member.profile_page'),code=303)


def member_requests():
    with Session(db.engine) as database:
        rows = database.execute(text('''
            SELECT sr.request_id,sr.status,sr.created_at,s.name AS service_name,
                   p.level_name AS priority,p.deadline_hours AS priority_hours,
                   (SELECT r.response_deadline FROM referrals r WHERE r.request_id=sr.request_id
                    ORDER BY r.attempt_number DESC LIMIT 1) AS response_deadline,
                   (SELECT o.name FROM referrals r JOIN organizations o ON o.organization_id=r.organization_id
                    WHERE r.request_id=sr.request_id ORDER BY r.attempt_number DESC LIMIT 1) AS org_name
            FROM service_requests sr JOIN services s ON s.service_id=sr.service_id
            JOIN priority_levels p ON p.priority_id=sr.priority_id
            WHERE sr.member_id=:owner ORDER BY sr.created_at DESC,sr.request_id DESC
        '''), {'owner': g.member['user_id']}).mappings().all()
    return [dict(row, reference=f"CC-{row['request_id']}", raw_status=row['status'],
                 status=DISPLAY_STATUS.get(row['status'], row['status'])) for row in rows]


@member_bp.get('/member/requests')
def my_requests():
    from app.frontend import render_team
    selected = request.args.get('status', '')
    rows = member_requests()
    return render_team('individual/my_requests.html', requests=[r for r in rows if not selected or r['status']==selected],
                       selected_status=selected, request_statuses=list(DISPLAY_STATUS.values()))


@member_bp.get('/member/requests/<int:request_id>')
def details(request_id):
    from app.frontend import render_team
    with Session(db.engine) as database:
        record = owned_request(database, request_id, g.member['user_id'])
        if record is None:
            abort(404)
        extra = database.execute(text('''
            SELECT sr.created_at,sr.description,s.delivery_mode FROM service_requests sr
            JOIN services s ON s.service_id=sr.service_id WHERE sr.request_id=:id
        '''), {'id': request_id}).mappings().one()
        history = database.execute(text('''
            SELECT h.new_status AS text,h.changed_at AS time FROM referral_status_history h
            JOIN referrals r ON r.referral_id=h.referral_id WHERE r.request_id=:id
            ORDER BY h.changed_at,h.history_id
        '''), {'id': request_id}).mappings().all()
        organization = database.execute(text('''
            SELECT o.name,o.contact_email AS email,o.contact_phone AS phone,r.status
            FROM referrals r JOIN organizations o ON o.organization_id=r.organization_id
            WHERE r.request_id=:id ORDER BY r.attempt_number DESC LIMIT 1
        '''), {'id': request_id}).mappings().one_or_none()
        feedback = saved_feedback(database,request_id) if record['status']=='completed' else None
    from app.services.guest_requests import DELIVERY
    can_cancel=record['status'] in {'submitted','unmatched'} and (organization is None or organization['status'] in {'rejected','timed_out'})
    record.update(status=record['display_status'],details=extra['description'],created_at=extra['created_at'],
                  delivery_method=DELIVERY.get(extra['delivery_mode'],extra['delivery_mode']),
                  org_name=organization['name'] if organization else None,history=history,
                  assigned_service_name=record['service_name'],feedback=feedback)
    return render_team('individual/request_details.html',req=record,
                       member_csrf=session['member_csrf'],can_cancel=can_cancel,
                       assigned_org=organization if organization and organization['status'] in {'accepted','attended','completed'} else None)


@member_bp.post('/member/requests/<int:request_id>/cancel')
def cancel(request_id):
    if not csrf_valid('member_csrf',request.form.get('csrf_token')):
        abort(403)
    if set(request.form)!={'csrf_token'} or len(request.form.getlist('csrf_token'))!=1:
        abort(400)
    try:
        with Session(db.engine) as database:
            cancel_request(database,request_id,g.member['user_id'])
        flash('Request cancelled.','success')
    except CancellationError as error:
        if error.status in {403,404}:
            abort(error.status)
        flash(str(error),'error')
    except SQLAlchemyError:
        current_app.logger.error('Request cancellation transaction failed')
        flash('Could not cancel the request. Please retry.','error')
    return redirect(url_for('member.details',request_id=request_id),code=303)


def saved_feedback(database,request_id):
    return database.execute(text('''
        SELECT feedback_id,is_helpful,comment FROM feedback WHERE request_id=:id AND member_id=:member
    '''),{'id':request_id,'member':g.member['user_id']}).mappings().one_or_none()


@member_bp.route('/member/requests/<int:request_id>/feedback',methods=['GET','POST'])
def feedback_page(request_id):
    from app.frontend import render_team
    with Session(db.engine) as database:
        record=owned_request(database,request_id,g.member['user_id'])
        if record is None:
            abort(404)
        if record['status']!='completed':
            abort(409)
        existing=saved_feedback(database,request_id)
    if request.method=='GET':
        if existing is not None:
            return redirect(url_for('member.details',request_id=request_id))
        return render_team('individual/feedback.html',req=record,member_csrf=session['member_csrf'])
    if not csrf_valid('member_csrf',request.form.get('csrf_token')):
        abort(403)
    choice=request.form.get('is_helpful')
    if 'rating' in request.form or choice not in {'yes','no'}:
        return render_team('individual/feedback.html',req=record,member_csrf=session['member_csrf'],
                           form_error='Choose Yes or No.'),400
    try:
        with Session(db.engine) as database:
            submit_feedback(database,request_id,g.member['user_id'],choice=='yes',request.form.get('comment'))
    except FeedbackError as error:
        if error.status==404:
            abort(404)
        return render_team('individual/feedback.html',req=record,member_csrf=session['member_csrf'],
                           form_error=str(error)),error.status
    except SQLAlchemyError:
        current_app.logger.error('Member feedback transaction failed')
        return render_team('individual/feedback.html',req=record,member_csrf=session['member_csrf'],
                           form_error='Could not save feedback. Please retry.'),503
    flash('Feedback saved.','success')
    return redirect(url_for('member.details',request_id=request_id),code=303)


@member_bp.post('/api/member/requests')
def submit_request():
    from app.frontend import request_page
    if not csrf_valid('member_csrf', request.form.get('csrf_token')):
        return request_page('Reload the form and retry.', 403)
    nonce = request.form.get('submission_nonce', '')
    if len(nonce) != 32 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in nonce):
        return request_page('Reload the form and retry.', 400)
    owner = g.member['user_id']
    key = 'member-request:' + hashlib.sha256(f"{owner}|{session['member_csrf']}|{nonce}".encode()).hexdigest()
    # Contact identity is server-owned; ignore every client-supplied contact/owner field.
    values = request.form.to_dict()
    values.update(contact_name=g.member['full_name'], contact_email=g.member['email'],
                  contact_phone=g.member['phone'], contact_address=g.member['address'], contact_city=g.member['city'])
    try:
        with Session(db.engine) as database:
            request_id, _ = create_guest_request(database, values, owner, key)
    except GuestRequestError as error:
        return request_page(str(error), error.status)
    except SQLAlchemyError:
        # Retry safely using the same form nonce; no profile or ownership fallback.
        return request_page('Request could not be saved. Please retry.', 503)
    return redirect(url_for('request_confirmation', reference=f'CC-{request_id}'), code=303)


@member_bp.get('/api/member/requests/<int:request_id>')
def request_status(request_id):
    with Session(db.engine) as database:
        record = owned_request(database, request_id, g.member['user_id'])
    if record is None:
        abort(404)
    from app.requests import _iso_utc
    return jsonify(request_id=request_id,status=record['status'],display_status=record['display_status'],
                   response_deadline=_iso_utc(record['response_deadline']),
                   attendance_deadline=_iso_utc(record['attendance_deadline']))


@member_bp.get('/logout')
def logout():
    if not csrf_valid('member_csrf', request.args.get('csrf')):
        abort(403)
    session.clear()
    response = redirect('/login')
    response.delete_cookie(COOKIE, path='/')
    return response


def register_member(app):
    app.register_blueprint(member_bp)
    app.before_request(load_member)
    app.after_request(private_response)
