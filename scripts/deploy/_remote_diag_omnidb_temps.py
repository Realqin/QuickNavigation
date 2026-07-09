#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.6.189")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "firefly")

SCRIPT = """from app.console_temp import is_temp_external_alias
from app.database import SessionLocal
from app.embed_session_service import (
    CONSOLE_DATABASE,
    SESSION_STATUS_ACTIVE,
    purge_temporary_connections_for_connection_method_menu,
)
from app.models import EmbedConsoleSession
from app.omnidb_service import _extract_csrf_token, _login_omnidb
from app.config import settings
import httpx
import json

with httpx.Client(base_url=settings.omnidb_internal_url.rstrip('/'), follow_redirects=True, timeout=30) as c:
    _login_omnidb(c)
    csrf = _extract_csrf_token(c)
    response = c.post(
        '/get_connections/',
        data={'data': json.dumps({'p_conn_id_list': []})},
        headers={'X-CSRFToken': csrf, 'Referer': settings.omnidb_internal_url},
    )
    response.raise_for_status()
    payload = response.json()
    print('v_error', payload.get('v_error'))
    v_data = payload.get('v_data') or {}
    if isinstance(v_data, dict):
        print('v_data_keys', list(v_data.keys()))
    items = list(v_data.get('v_conn_list', []) if isinstance(v_data, dict) else [])
    tmp = [i for i in items if is_temp_external_alias(str(i.get('alias') or ''))]
    print('omnidb_total', len(items))
    print('omnidb_tmp', len(tmp))
    for item in items[:10]:
        print('CONN', item.get('id'), item.get('alias'))
    for item in tmp[:20]:
        print('TMP', item.get('id'), item.get('alias'))
    if len(tmp) > 20:
        print('... and', len(tmp) - 20, 'more')

db = SessionLocal()
active = db.query(EmbedConsoleSession).filter(
    EmbedConsoleSession.status == SESSION_STATUS_ACTIVE,
    EmbedConsoleSession.is_temporary.is_(True),
    EmbedConsoleSession.console_type == CONSOLE_DATABASE,
).count()
print('active_tmp_db_sessions', active)
purge_temporary_connections_for_connection_method_menu(db, CONSOLE_DATABASE)
db.close()
print('purge_done')
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
    f.write(SCRIPT)
    local_path = f.name
sftp = ssh.open_sftp()
remote_path = "/tmp/qn_diag_omnidb.py"
sftp.put(local_path, remote_path)
sftp.close()
os.unlink(local_path)
i, o, e = ssh.exec_command(
    f"docker cp {remote_path} quicknav-backend:/tmp/qn_diag_omnidb.py && "
    "docker exec -e PYTHONPATH=/app quicknav-backend python /tmp/qn_diag_omnidb.py",
    timeout=120,
)
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace")
if err.strip():
    print("STDERR:", err)
ssh.close()
