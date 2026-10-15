#!/bin/bash
set -e

PG_VERSION="${PG_VERSION:-18}"
PG_CLUSTER="${PG_CLUSTER:-main}"

# Start (or restart) the selected PostgreSQL cluster. Only this cluster is
# touched, so several major versions can live in the same image.
start_postgres() {
    if command -v pg_ctlcluster >/dev/null 2>&1; then
        pg_ctlcluster "${PG_VERSION}" "${PG_CLUSTER}" start 2>/dev/null || \
            pg_ctlcluster "${PG_VERSION}" "${PG_CLUSTER}" restart 2>/dev/null
    else
        service postgresql start
    fi
}

echo "Starting PostgreSQL ${PG_VERSION}/${PG_CLUSTER}..."
max=5
for i in $(seq 1 $max); do
    echo "Starting PostgreSQL (attempt $i/$max)..."
    start_postgres || true
    if command -v pg_isready >/dev/null 2>&1 && pg_isready -q; then
        echo "PostgreSQL is ready."
        break
    fi
    echo "Postgres failed to start, retrying..."
    sleep 3
done

# Start CVV Web UI in the foreground so the container keeps running.
echo "[CVV] Starting CVV Web Interface..."
cd /cvv
exec python3 /cvv/web/manage.py runserver 0.0.0.0:8989
