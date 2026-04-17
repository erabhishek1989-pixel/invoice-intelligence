import os
import sys

from app import create_app, db
from app.models import User

username = os.environ["ADMIN_USERNAME"]
password = os.environ["ADMIN_PASSWORD"]

app = create_app()
with app.app_context():
    db.create_all()
    existing = User.query.filter_by(username=username).first()
    if existing:
        existing.set_password(password)
        print(f"Password updated for user: {username}")
    else:
        u = User(username=username, role="admin")
        u.set_password(password)
        db.session.add(u)
        print(f"Admin user created: {username}")
    db.session.commit()
    print("Done")
