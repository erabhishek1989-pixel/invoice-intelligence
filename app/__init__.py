import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.chat import chat_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(chat_bp)

    from app import models  # noqa: F401 — ensure models are registered before create_all
    with app.app_context():
        try:
            db.create_all()
            _create_admin_if_configured()
        except Exception:
            pass

    return app


def _create_admin_if_configured():
    """Create admin user from env vars ADMIN_USERNAME / ADMIN_PASSWORD if set."""
    import os
    from app.models import User

    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        return
    existing = User.query.filter_by(username=username).first()
    if existing:
        existing.set_password(password)
    else:
        u = User(username=username, role="admin")
        u.set_password(password)
        db.session.add(u)
    db.session.commit()
