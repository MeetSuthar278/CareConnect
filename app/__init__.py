import os
from flask import Flask, jsonify, render_template, abort
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv


load_dotenv()

db = SQLAlchemy()


def create_app(test_config=None):
    app = Flask(__name__)

    # Flask configuration
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["FIREBASE_PROJECT_ID"] = os.getenv("FIREBASE_PROJECT_ID", "careconnect-7132c")
    app.config['HOSTED_MODE'] = os.getenv('HOSTED_MODE','0')=='1'
    if test_config:
        app.config.update(test_config)
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
        except Exception:
            app.logger.exception("Database connection failed")
            return jsonify({"database": "disconnected"}), 503

        # Register Requests Blueprint
    from app.requests import requests_bp
    app.register_blueprint(requests_bp)

    # Register Catalog Blueprint
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
