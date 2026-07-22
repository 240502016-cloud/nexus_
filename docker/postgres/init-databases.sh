#!/bin/sh
set -eu

: "${APP_POSTGRES_USER:?APP_POSTGRES_USER is required}"
: "${APP_POSTGRES_PASSWORD:?APP_POSTGRES_PASSWORD is required}"
: "${APP_POSTGRES_DB:?APP_POSTGRES_DB is required}"
: "${SYNAPSE_POSTGRES_USER:?SYNAPSE_POSTGRES_USER is required}"
: "${SYNAPSE_POSTGRES_PASSWORD:?SYNAPSE_POSTGRES_PASSWORD is required}"
: "${SYNAPSE_POSTGRES_DB:?SYNAPSE_POSTGRES_DB is required}"

bootstrap_user="${POSTGRES_BOOTSTRAP_USER:-$POSTGRES_USER}"

psql --set ON_ERROR_STOP=1 \
  --username "$bootstrap_user" \
  --dbname "$POSTGRES_DB" \
  --set app_user="$APP_POSTGRES_USER" \
  --set app_password="$APP_POSTGRES_PASSWORD" \
  --set app_db="$APP_POSTGRES_DB" \
  --set synapse_user="$SYNAPSE_POSTGRES_USER" \
  --set synapse_password="$SYNAPSE_POSTGRES_PASSWORD" \
  --set synapse_db="$SYNAPSE_POSTGRES_DB" <<'EOSQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'app_user', :'app_password') \gexec

SELECT format(
  'CREATE DATABASE %I OWNER %I ENCODING %L LC_COLLATE %L LC_CTYPE %L TEMPLATE template0',
  :'app_db', :'app_user', 'UTF8', 'C', 'C'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db') \gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'app_db', :'app_user') \gexec

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'synapse_user', :'synapse_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'synapse_user') \gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'synapse_user', :'synapse_password') \gexec

SELECT format(
  'CREATE DATABASE %I OWNER %I ENCODING %L LC_COLLATE %L LC_CTYPE %L TEMPLATE template0',
  :'synapse_db', :'synapse_user', 'UTF8', 'C', 'C'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'synapse_db') \gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'synapse_db', :'synapse_user') \gexec
EOSQL
