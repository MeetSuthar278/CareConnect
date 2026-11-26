import os
from flask import Flask, jsonify, render_template, abort, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException


load_dotenv()

db = SQLAlchemy()


def create_app(test_config=None):
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["FIREBASE_PROJECT_ID"] = os.getenv("FIREBASE_PROJECT_ID")
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
    app.config['HOSTED_MODE'] = os.getenv('HOSTED_MODE','0')=='1'
    if test_config:
        app.config.update(test_config)
    missing = [environment for config, environment in (
        ('SECRET_KEY', 'SECRET_KEY'), ('SQLALCHEMY_DATABASE_URI', 'DATABASE_URL'),
        ('FIREBASE_PROJECT_ID', 'FIREBASE_PROJECT_ID')) if not app.config.get(config)]
    if missing:
        raise RuntimeError('Missing required configuration: ' + ', '.join(missing))
    if app.config['HOSTED_MODE']:
        from werkzeug.middleware.proxy_fix import ProxyFix
        # Only Caddy is exposed; trust exactly that one proxy's scheme/address.
        app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
        app.config.update(DEBUG=False,SESSION_COOKIE_SECURE=True)

    db.init_app(app)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.frontend import register_frontend
    register_frontend(app)

    def error_response(status, message):
        if request.path.startswith('/api/'):
            response = jsonify(error=message)
        else:
            from app.frontend import render_team
            response = app.make_response(render_team('errors/error.html', status=status, message=message))
        response.status_code = status
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error_response(error.code, error.description)
        for name, value in error.get_headers():
            if name.lower() not in {'content-type', 'content-length'}:
                response.headers[name] = value
        return response

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        app.logger.error('Database operation unavailable (%s)', type(error).__name__)
        return error_response(503, 'This information is temporarily unavailable. Please try again later.')

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if app.testing:
            raise error
        app.logger.error('Unexpected request failure (%s)', type(error).__name__)
        return error_response(500, 'Something went wrong. Please try again or return to the home page.')

    @app.get("/demo/request")
    def legacy_request_demo():
        if app.config['HOSTED_MODE']:
            abort(404)
        return render_template("individual/request_form.html",
                               demo_mode=app.debug or app.testing)

    @app.get("/health")
    def health():
        return jsonify({
            "status": "healthy",
            "service": "CareConnect Backend"
        }), 200

    @app.get("/health/db")
    def database_health():
        try:
            db.session.execute(db.text("SELECT 1"))
            return jsonify({"database": "connected"}), 200
        except Exception as error:
            app.logger.error("Database health check unavailable (%s)", type(error).__name__)
            return jsonify({"database": "disconnected"}), 503

    from app.requests import requests_bp
    app.register_blueprint(requests_bp)

    from app.catalog import catalog_bp
    app.register_blueprint(catalog_bp)

    from app.referrals import referrals_bp
    app.register_blueprint(referrals_bp)

    from app.feedback import feedback_bp
    app.register_blueprint(feedback_bp)

    from app.registration import registration_bp
    app.register_blueprint(registration_bp)

    from app.member import register_member
    register_member(app)

    from app.organization import register_organization
    register_organization(app)

    from app.coordinator import register_coordinator
    register_coordinator(app)

    return app
