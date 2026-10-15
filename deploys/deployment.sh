#!/bin/bash
#
# CVV is a continuous verification visualizer.
# Copyright (c) 2019-2023 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

set -euo pipefail

DEFAULT_DB_NAME="${1:-}"
ADMIN_USER="${2:-admin}"
ADMIN_PASS="${3:-admin}"
CV_DIR="$(pwd)"

# Environment variables:
#   PG_VERSION   Local cluster major version to configure (e.g. 12 or 18).
#                Defaults to the newest installed cluster.
#   PG_CLUSTER   Local cluster name (default: main).
#   DB_HOST      Connect to an external PostgreSQL server instead of touching
#                a local cluster.
#   DB_PORT      External server port.
#   DB_USER      Database superuser (default: postgres).
#   DB_PASSWORD  Password for DB_USER (external servers).
PG_CLUSTER="${PG_CLUSTER:-main}"
PG_CONF_ROOT="${PG_CONF_ROOT:-/etc/postgresql}"
export DB_USER="${DB_USER:-postgres}"
export DB_PASSWORD="${DB_PASSWORD:-}"
export DB_HOST="${DB_HOST:-}"
export DB_PORT="${DB_PORT:-}"

usage() {
    echo "Usage: $0 <database name> [<user> <password>]"
    echo
    echo "Environment variables:"
    echo "  PG_VERSION   PostgreSQL cluster version to configure (e.g. 12 or 18)."
    echo "               Defaults to the newest installed cluster."
    echo "  PG_CLUSTER   Cluster name (default: main)."
    echo "  DB_HOST      Use an external PostgreSQL server instead of a local cluster."
    echo "  DB_PORT      External server port."
    echo "  DB_USER      Database superuser (default: postgres)."
    echo "  DB_PASSWORD  Password for DB_USER (external servers)."
}

if [ -z "${DEFAULT_DB_NAME}" ]; then
    usage
    exit 1
fi

# List installed clusters as "<version> <name> <port>".
list_clusters() {
    if command -v pg_lsclusters >/dev/null 2>&1; then
        pg_lsclusters -h 2>/dev/null
        return
    fi
    local conf ver cluster port
    for conf in "${PG_CONF_ROOT}"/*/*/postgresql.conf; do
        [ -f "${conf}" ] || continue
        cluster="$(basename "$(dirname "${conf}")")"
        ver="$(basename "$(dirname "$(dirname "${conf}")")")"
        port="$(sed -nE 's/^[[:space:]]*port[[:space:]]*=[[:space:]]*([0-9]+).*/\1/p' "${conf}" | head -n1)"
        echo "${ver} ${cluster} ${port:-5432}"
    done
}

# ---------------------------------------------------------------------------
# Resolve the target PostgreSQL server
# ---------------------------------------------------------------------------
if [ -z "${DB_HOST}" ]; then
    # ---- Local cluster: may coexist with other major versions ----
    if [ -z "${PG_VERSION:-}" ]; then
        PG_VERSION="$(list_clusters | awk '{print $1}' | sort -n | tail -n1)"
    fi
    if [ -z "${PG_VERSION:-}" ]; then
        echo "No PostgreSQL cluster found; set PG_VERSION or DB_HOST." >&2
        exit 1
    fi
    export PG_VERSION

    PG_HBA_PATH="${PG_CONF_ROOT}/${PG_VERSION}/${PG_CLUSTER}/pg_hba.conf"
    if [ ! -f "${PG_HBA_PATH}" ]; then
        echo "PostgreSQL pg_hba.conf not found at ${PG_HBA_PATH}!" >&2
        exit 1
    fi

    # Port of the selected cluster (so multiple versions can run together).
    CLUSTER_PORT="$(list_clusters | awk -v v="${PG_VERSION}" -v c="${PG_CLUSTER}" \
        '$1==v && $2==c {print $3}' | head -n1)"
    export PGPORT="${CLUSTER_PORT:-5432}"

    echo "Configuring local PostgreSQL ${PG_VERSION}/${PG_CLUSTER} on port ${PGPORT}"

    # Update pg_hba.conf to "trust" for local connections
    sed -i 's/^local .*/local   all             all                                     trust/' "${PG_HBA_PATH}"

    if command -v pg_ctlcluster >/dev/null 2>&1; then
        pg_ctlcluster "${PG_VERSION}" "${PG_CLUSTER}" restart || {
            echo "Cannot restart PostgreSQL ${PG_VERSION}/${PG_CLUSTER}" >&2
            exit 1
        }
    else
        service postgresql restart || { echo "Cannot restart postgresql" >&2; exit 1; }
    fi
else
    # ---- External server (CI service container, remote host, ...) ----
    export PGHOST="${DB_HOST}"
    if [ -n "${DB_PORT}" ]; then
        export PGPORT="${DB_PORT}"
    fi
fi

export PGUSER="${DB_USER}"
if [ -n "${DB_PASSWORD}" ]; then
    export PGPASSWORD="${DB_PASSWORD}"
fi

# ---------------------------------------------------------------------------
# Create the CVV database
# ---------------------------------------------------------------------------
echo "Creating database: ${DEFAULT_DB_NAME}"

DB_EXISTS="$(psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DEFAULT_DB_NAME}'")"
if [ "${DB_EXISTS}" = "1" ]; then
    echo "Dropping existing database: ${DEFAULT_DB_NAME}"
    dropdb "${DEFAULT_DB_NAME}"
fi

createdb -T template0 -E UTF8 -O "${DB_USER}" "${DEFAULT_DB_NAME}" || {
    echo "Cannot create new database" >&2
    exit 1
}

echo "Setting up CV web-interface"

# db.json is generated; optional fields are only written when set.
DB_NAME="${DEFAULT_DB_NAME}" python3 - "${CV_DIR}/web/web/db.json" <<'PY'
import json
import os
import sys

config = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ["DB_NAME"],
    "USER": os.environ.get("DB_USER", "postgres"),
}
for key, env in (("PASSWORD", "DB_PASSWORD"), ("HOST", "DB_HOST"), ("PORT", "DB_PORT")):
    if os.environ.get(env):
        config[key] = os.environ[env]

with open(sys.argv[1], "w", encoding="utf8") as fp:
    json.dump(config, fp, indent=4)
    fp.write("\n")
PY

cat > "${CV_DIR}/web/web/settings.py" <<EOF
from web.development import *
PERFORM_AUTO_SAVE = False
EOF

python3 "${CV_DIR}/web/manage.py" compilemessages || { echo "Cannot compile messages"; exit 1; }
python3 "${CV_DIR}/web/manage.py" makemigrations jobs marks reports service tools users || \
    { echo "Cannot create migrations"; exit 1; }
python3 "${CV_DIR}/web/manage.py" migrate || { echo "Cannot update database"; exit 1; }

# Create superuser if not exists
python3 "${CV_DIR}/web/manage.py" shell <<EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username="${ADMIN_USER}").exists():
    User.objects.create_superuser("${ADMIN_USER}", "", "${ADMIN_PASS}")
EOF

# Extend user
python3 "${CV_DIR}/web/manage.py" shell <<EOF
from django.contrib.auth.models import User
from web.populate import Population, extend_user
user = User.objects.first()
extend_user(user, 2)
Population(user=user)
EOF

echo "Launch web interface using:"
echo "./start.sh --host <host> --port <port> &"
