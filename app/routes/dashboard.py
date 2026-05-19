import os
import logging
from datetime import datetime

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from sqlalchemy import func

from app import db, DEMO_USER_ID
from app.models import Document, Invoice
from app.services.blob_service import upload_to_blob
from app.services.invoice_service import process_document

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@dashboard_bp.route("/")
def index():
    docs = (
        Document.query
        .order_by(Document.uploaded_at.desc())
        .limit(50)
        .all()
    )

    # Stats
    total = Document.query.count()
    processed = Document.query.filter_by(status="processed").count()
    failed = Document.query.filter_by(status="failed").count()
    pending = total - processed - failed

    total_spend = db.session.query(func.sum(Invoice.total_amount)).scalar() or 0

    return render_template(
        "dashboard.html",
        documents=docs,
        stats={
            "total": total,
            "processed": processed,
            "pending": pending,
            "failed": failed,
            "total_spend": float(total_spend),
        },
    )


@dashboard_bp.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")

    if not file or file.filename == "":
        flash("No file selected.", "warning")
        return redirect(url_for("dashboard.index"))

    if not _allowed_file(file.filename):
        flash("Only PDF, JPG, JPEG and PNG files are allowed.", "danger")
        return redirect(url_for("dashboard.index"))

    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > MAX_FILE_BYTES:
        flash("File is too large. Maximum size is 10 MB.", "danger")
        return redirect(url_for("dashboard.index"))

    doc = None
    try:
        blob_url = upload_to_blob(file)

        doc = Document(
            filename=os.path.basename(file.filename),
            blob_url=blob_url,
            status="pending",
            uploaded_by=DEMO_USER_ID,
        )
        db.session.add(doc)
        db.session.commit()

        # Process synchronously — takes 5-15 seconds
        invoice = process_document(doc)
        flash(
            f"✓ Invoice processed — {invoice.vendor_name or 'Unknown vendor'} | "
            f"{invoice.currency} {invoice.total_amount or '?'}",
            "success"
        )
        return redirect(url_for("dashboard.document", doc_id=doc.id))

    except Exception as exc:
        logger.error("Upload/processing failed: %s", exc)
        if doc and doc.id:
            doc.status = "failed"
            doc.error_message = str(exc)[:500]
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        flash(f"Processing failed: {str(exc)[:200]}", "danger")
        return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/document/<int:doc_id>")
def document(doc_id: int):
    doc = Document.query.get_or_404(doc_id)
    return render_template("document.html", doc=doc)


@dashboard_bp.route("/document/<int:doc_id>/delete", methods=["POST"])
def delete_document(doc_id: int):
    doc = Document.query.get_or_404(doc_id)
    db.session.delete(doc)
    db.session.commit()
    flash("Document deleted.", "info")
    return redirect(url_for("dashboard.index"))
