from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120))
    role = db.Column(db.String(20), default="user")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    blob_url = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending/processing/processed/failed
    doc_type = db.Column(db.String(50))
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)

    invoice = db.relationship("Invoice", backref="document", uselist=False)


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), nullable=False)
    vendor_name = db.Column(db.String(200))
    vendor_address = db.Column(db.Text)
    invoice_number = db.Column(db.String(100))
    invoice_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    subtotal = db.Column(db.Numeric(12, 2))
    tax_amount = db.Column(db.Numeric(12, 2))
    total_amount = db.Column(db.Numeric(12, 2))
    currency = db.Column(db.String(10), default="INR")
    payment_status = db.Column(db.String(20), default="unpaid")  # paid/unpaid/partial
    doc_type = db.Column(db.String(20))  # purchase / sale
    notes = db.Column(db.Text)
    raw_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    line_items = db.relationship("LineItem", backref="invoice", lazy=True)


class LineItem(db.Model):
    __tablename__ = "line_items"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    description = db.Column(db.String(500))
    quantity = db.Column(db.Numeric(10, 2))
    unit_price = db.Column(db.Numeric(12, 2))
    line_total = db.Column(db.Numeric(12, 2))


class QueryLog(db.Model):
    __tablename__ = "query_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    sql_generated = db.Column(db.Text)
    answer = db.Column(db.Text)
    was_voice = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
