#!/bin/sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${APP_POSTGRES_USER:?APP_POSTGRES_USER is required}"
: "${APP_POSTGRES_PASSWORD:?APP_POSTGRES_PASSWORD is required}"
: "${SYNAPSE_POSTGRES_USER:?SYNAPSE_POSTGRES_USER is required}"
: "${SYNAPSE_POSTGRES_PASSWORD:?SYNAPSE_POSTGRES_PASSWORD is required}"

run_as_superuser() {
  candidate="$1"
  candidate_password="$2"

  is_superuser="$(PGPASSWORD="$candidate_password" psql \
    --username "$candidate" \
    --dbname postgres \
    --tuples-only \
    --no-align \
    --command 'SELECT rolsuper FROM pg_roles WHERE rolname = current_user' \
    2>/dev/null || true)"

  if [ "$is_superuser" = "t" ]; then
    echo "Repairing Nexus databases with PostgreSQL superuser '$candidate'."
    export POSTGRES_BOOTSTRAP_USER="$candidate"
    export PGPASSWORD="$candidate_password"
    exec /bin/sh /usr/local/bin/init-nexus-databases.sh
  fi
}

# POSTGRES_USER is the current admin setting. APP_POSTGRES_USER covers volumes
# created by the legacy Compose file, where the application user was superuser.
run_as_superuser "$POSTGRES_USER" "$POSTGRES_PASSWORD"
run_as_superuser "$APP_POSTGRES_USER" "$APP_POSTGRES_PASSWORD"
run_as_superuser postgres "$POSTGRES_PASSWORD"
run_as_superuser "$SYNAPSE_POSTGRES_USER" "$SYNAPSE_POSTGRES_PASSWORD"

echo >&2 "Could not find an accessible PostgreSQL superuser in the existing volume."
echo >&2 "Set POSTGRES_ADMIN_USER and POSTGRES_ADMIN_PASSWORD to the credentials used when the volume was created."
exit 1
