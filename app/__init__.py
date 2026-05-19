import logging
import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import text

logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()

DEMO_USER_ID = 1  # all uploads/queries use this user — no auth for demo

# Every new column added to a model goes here.
# Uses SQL Server's COL_LENGTH — returns NULL if column is missing.
# Safe to run on every startup: no-op if column already exists.
_COLUMN_MIGRATIONS = [
    "IF COL_LENGTH('documents', 'blob_name') IS NULL "
    "ALTER TABLE documents ADD blob_name VARCHAR(500)",
]


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
            # create_all is safe to call repeatedly — only creates missing tables
            db.create_all()
            _apply_column_migrations()
            _ensure_demo_user()
        except Exception as e:
            logger.warning("Startup DB init skipped: %s", e)

    return app


def _apply_column_migrations():
    """Add any columns that exist in models but are missing from the DB.

    create_all() never alters existing tables, so new columns added after
    first deploy must be patched here. COL_LENGTH returns NULL when the
    column is absent — safe to run on every startup.
    """
    with db.engine.connect() as conn:
        for stmt in _COLUMN_MIGRATIONS:
            try:
                conn.execute(text(stmt))
                conn.commit()
                logger.info("Column migration applied: %s", stmt[:60])
            except Exception as exc:
                logger.warning("Column migration skipped (%s): %s", stmt[:60], exc)


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
