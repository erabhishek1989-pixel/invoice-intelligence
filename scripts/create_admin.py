import base64
import os
import sys

from app import create_app, db
from app.models import User

# Accept base64-encoded args to avoid shell quoting issues with special chars
if len(sys.argv) == 3:
    username = base64.b64decode(sys.argv[1]).decode("utf-8")
    password = base64.b64decode(sys.argv[2]).decode("utf-8")
else:
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
