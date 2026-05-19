import logging
import os
import socket

from flask import Blueprint, jsonify
from sqlalchemy import text

from app import db

logger = logging.getLogger(__name__)
health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    result = {"app": "ok", "db": {}, "dns": {}}

    try:
        db.session.execute(text("SELECT 1"))
        db.session.remove()
        result["db"] = {"connected": True}
    except Exception as exc:
        result["db"] = {"connected": False, "error": str(exc)[:300]}

    try:
        from sqlalchemy.engine import make_url
        host = make_url(os.environ.get("DATABASE_URL", "")).host or "unknown"
        ips = list({r[4][0] for r in socket.getaddrinfo(host, 1433, proto=socket.IPPROTO_TCP)})
        result["dns"] = {"host": host, "resolved_ips": ips}
    except Exception as exc:
        result["dns"] = {"error": str(exc)[:200]}

    status = 200 if result["db"].get("connected") else 503
    return jsonify(result), status
