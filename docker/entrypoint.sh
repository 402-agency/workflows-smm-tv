#!/bin/sh
set -e

# Wait for the database to be reachable (both app and worker need it).
if [ "${WAIT_FOR_DB:-true}" = "true" ]; then
  python -m app.scripts.wait_for_db
fi

# Only one service should run migrations (the app service sets RUN_MIGRATIONS=true).
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  echo "Applying database migrations..."
  alembic upgrade head
fi

exec "$@"
