#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"
PROJECT_DIR = "/opt/hlx/QuickNavigation"

script = f"""set -e
cd {PROJECT_DIR}
export COMPOSE_PROJECT_NAME=quicknav
COMPOSE='docker-compose -f docker-compose.yml -f docker-compose.offline.yml -f docker-compose.prod.yml'

echo '=== build sshwifty (TLS) ==='
$COMPOSE build sshwifty

echo '=== recreate sshwifty ==='
$COMPOSE up -d --no-build --force-recreate sshwifty

sleep 3
echo '=== logs ==='
docker logs quicknav-sshwifty 2>&1 | tail -10

echo '=== https probe ==='
python3 - <<'PY'
import ssl, urllib.request
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
for url in ('https://127.0.0.1:8182/', 'http://127.0.0.1:8182/'):
    try:
        r = urllib.request.urlopen(url, context=ctx, timeout=8)
        print(url, '->', r.status)
    except Exception as e:
        print(url, '->', type(e).__name__, e)
PY

echo '=== backend base ==='
docker exec quicknav-backend python -c "from app.sshwifty_service import build_sshwifty_public_base; print(build_sshwifty_public_base('192.168.6.189'))"

echo DEPLOY_OK
"""

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=30)
i, o, e = ssh.exec_command("bash -s", timeout=300)
i.write(script)
i.channel.shutdown_write()
out = o.read().decode(errors="replace")
err = e.read().decode(errors="replace")
print(out)
if err.strip():
    print("STDERR:", err)
if "DEPLOY_OK" not in out:
    raise SystemExit(1)
