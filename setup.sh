#!/usr/bin/env bash
# =============================================================================
# setup.sh — build the database and install the Python packages, in one step.
#
#   ./setup.sh          build everything (refuses if the database exists)
#   ./setup.sh --reset  DROP the database and rebuild it from scratch
#
# Everything this does is also written out step by step in README.md, so you can
# run the pieces by hand instead if you prefer.
# =============================================================================
set -euo pipefail

DB="${SMARTPARK_DB:-smartpark}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# Homebrew installs psql outside the default PATH on Apple Silicon.
if ! command -v psql >/dev/null 2>&1; then
  for d in /opt/homebrew/opt/postgresql@17/bin /usr/local/opt/postgresql@17/bin \
           /opt/homebrew/bin /usr/local/bin; do
    [ -x "$d/psql" ] && export PATH="$d:$PATH" && break
  done
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found. Install PostgreSQL first:" >&2
  echo "    brew install postgresql@17" >&2
  exit 1
fi

if ! pg_isready -q 2>/dev/null; then
  echo "PostgreSQL is not accepting connections. Start it with:" >&2
  echo "    brew services start postgresql@17" >&2
  exit 1
fi

echo "==> PostgreSQL $(psql -V | awk '{print $3}') is running"

if [ "${1:-}" = "--reset" ]; then
  echo "==> Dropping the existing '$DB' database"
  psql -d postgres -qc \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB';" \
    >/dev/null 2>&1 || true
  dropdb --if-exists "$DB"
elif psql -lqt | cut -d'|' -f1 | grep -qw "$DB"; then
  echo "The database '$DB' already exists." >&2
  echo "Run  ./setup.sh --reset  to rebuild it from scratch." >&2
  exit 1
fi

echo "==> Creating the '$DB' database"
createdb "$DB"

echo "==> Applying migrations"
for f in db/migrations/*.sql; do
  printf '    %s\n' "$(basename "$f")"
  psql -q -v ON_ERROR_STOP=1 -d "$DB" -f "$f"
done

echo "==> Installing Python packages into .venv"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip -q install --upgrade pip
./.venv/bin/pip -q install -r requirements.txt

SLOTS=$(psql -d "$DB" -tAc "SELECT count(*) FROM slot")
SESS=$(psql -d "$DB" -tAc "SELECT count(*) FROM parking_session")
BILLS=$(psql -d "$DB" -tAc "SELECT count(*) FROM bill")

cat <<EOF

==> Done.
    $SLOTS bays, $SESS parking sessions, $BILLS bills.

    Start the application:

        ./.venv/bin/uvicorn api.main:app --port 8077

    Then open  http://127.0.0.1:8077

    Sign in as  admin@smartpark.in  with the password  Parking@123
EOF
