#!/usr/bin/env bash
# Creates the least-privilege app_user login role.
# Runs as the postgres superuser via docker-entrypoint-initdb.d (after 01_schema.sql).
#
# app_user is a member of app_role and can only SELECT/INSERT/UPDATE/DELETE
# on public tables — it cannot create roles, drop tables, or bypass RLS.
# The FastAPI app and scheduler connect as this user, not as the superuser.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  -- Create the login role if it doesn't exist (idempotent for re-init)
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
      CREATE ROLE app_user
        LOGIN
        PASSWORD '${APP_DB_PASSWORD}'
        NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    ELSE
      -- Update password on every boot so a rotate in .env takes effect
      ALTER ROLE app_user PASSWORD '${APP_DB_PASSWORD}';
    END IF;
  END
  \$\$;

  -- Inherit app_role grants (SELECT/INSERT/UPDATE/DELETE + sequences + function)
  GRANT app_role TO app_user;

  -- Allow the login user to connect to the database
  GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO app_user;
EOSQL
