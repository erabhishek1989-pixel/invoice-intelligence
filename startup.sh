#!/bin/bash
cd /home/site/wwwroot
source /home/site/wwwroot/antenv/bin/activate 2>/dev/null || true
flask db upgrade
gunicorn --bind=0.0.0.0:8000 --workers=2 --timeout=60 wsgi:app
