#!/bin/bash
# Apply all SQL migrations in order after the base schema.
# Mounted into docker-entrypoint-initdb.d/ as 03_migrations.sh so it runs
# after 01_schema.sql and 02_app_user.sh.
set -e

MIGRATIONS_DIR="/docker-entrypoint-initdb.d/migrations"

if [ ! -d "$MIGRATIONS_DIR" ]; then
  echo "No migrations directory found — skipping"
  exit 0
fi

for f in $(ls "$MIGRATIONS_DIR"/*.sql 2>/dev/null | sort); do
  echo "Applying migration: $f"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$f"
done

echo "All migrations applied successfully."
