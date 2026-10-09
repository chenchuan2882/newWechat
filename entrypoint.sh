#!/bin/sh
set -eu
# Only creates missing tables; all changes to existing schema require a migration.
python -m flask --app wxcloudrun init-db
exec gunicorn --bind 0.0.0.0:80 --workers 2 --threads 4 --timeout 60 wxcloudrun:app
