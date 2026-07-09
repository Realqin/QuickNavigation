#!/bin/bash
set -euo pipefail

HOMEDIR=/home/omnidb/.omnidb/omnidb-server
export HOME=/home/omnidb
OMNIDB_DIR=/home/omnidb/OmniDB/OmniDB
OMNIDB_USER_NAME="${OMNIDB_ADMIN_USER:-admin}"
OMNIDB_USER_PASSWORD="${OMNIDB_ADMIN_PASSWORD:-admin@123}"

mkdir -p "$HOMEDIR"
touch "$HOMEDIR/omnidb.log" "$HOMEDIR/omnidb.db" 2>/dev/null || true
chown -R omnidb:omnidb /home/omnidb/.omnidb 2>/dev/null || true

run_as_omnidb() {
  su -s /bin/bash omnidb -c "cd '$OMNIDB_DIR' && $*"
}

echo "[omnidb] initializing admin user: ${OMNIDB_USER_NAME}"
run_as_omnidb "python omnidb-server.py -d '$HOMEDIR' -s '$OMNIDB_USER_NAME' '$OMNIDB_USER_PASSWORD'" 2>/dev/null || \
run_as_omnidb "python omnidb-server.py -d '$HOMEDIR' --createsuperuser='$OMNIDB_USER_NAME' '$OMNIDB_USER_PASSWORD'" 2>/dev/null || \
echo "[omnidb] admin user already exists"

echo "[omnidb] starting server on 0.0.0.0:8000"
exec su -s /bin/bash omnidb -c "cd '$OMNIDB_DIR' && exec python omnidb-server.py -d '$HOMEDIR' -H 0.0.0.0 -p 8000"
