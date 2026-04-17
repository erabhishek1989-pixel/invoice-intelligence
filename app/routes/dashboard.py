import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.models import Document, db
from app.services.blob_service import upload_to_blob

dashboard_bp = Blueprint("dashboard", __name__)

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@dashboard_bp.route("/")
@login_required
def index():
    docs = (
        Document.query
        .filter_by(uploaded_by=current_user.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return render_template("dashboard.html", documents=docs)


@dashboard_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("No file selected", "warning")
        return redirect(url_for("dashboard.index"))

    if not _allowed_file(file.filename):
        flash("Only PDF, JPG, JPEG, PNG files are allowed", "danger")
        return redirect(url_for("dashboard.index"))

    try:
        blob_url = upload_to_blob(file)
        doc = Document(
            filename=file.filename,
            blob_url=blob_url,
            status="pending",
            uploaded_by=current_user.id,
        )
        db.session.add(doc)
        db.session.commit()
        flash("File uploaded — processing will begin shortly", "success")
    except Exception as exc:
        current_app.logger.error("Upload failed: %s", exc)
        flash("Upload failed. Please try again.", "danger")

    return redirect(url_for("dashboard.index"))
