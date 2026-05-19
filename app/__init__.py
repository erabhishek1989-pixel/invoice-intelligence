import logging
import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()

DEMO_USER_ID = 1  # all uploads/queries use this user — no auth for demo


def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    db.init_app(app)
    migrate.init_app(app, db)

    from app.routes.dashboard import dashboard_bp
    from app.routes.chat import chat_bp
    from app.routes.health import health_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(health_bp)

    from app import models  # noqa: ensure models registered
    with app.app_context():
        try:
            # Run pending Alembic migrations (adds new columns, etc.)
            # Falls back to create_all for brand-new databases with no
            # migration history (e.g. fresh Azure SQL after terraform apply).
            from flask_migrate import upgrade as db_upgrade
            try:
                db_upgrade()
                logger.info("DB migrations applied")
            except Exception as migrate_err:
                logger.warning("flask db upgrade failed (%s) — falling back to create_all", migrate_err)
                db.create_all()
            _ensure_demo_user()
        except Exception as e:
            logger.warning("Startup DB init skipped: %s", e)

    return app


def _ensure_demo_user():
    """Create a demo user (id=1) used for all uploads in no-auth mode."""
    from app.models import User
    existing = User.query.get(DEMO_USER_ID)
    if not existing:
        u = User(username="demo", role="admin")
        u.set_password("demo")
        db.session.add(u)
        db.session.commit()
        logger.info("Demo user created (id=1)")
