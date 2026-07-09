#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
USER = "root"
PASSWORD = "firefly"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)

script = r"""
echo '=== backend env (connection related) ==='
docker exec quicknav-backend printenv | grep -E 'OMNIDB|REDPANDA|SSHWIFTY|REDIS|DATABASE|GITLAB|host' | sort

echo
echo '=== connection hosts in DB ==='
docker exec quicknav-mysql mysql -uroot -proot123456 -N quicknavigation -e "
SELECT c.id, c.name, d.name AS label, c.host, c.port, c.database_name, c.url
FROM connections c
LEFT JOIN dict_items d ON d.id = c.type
WHERE c.host IS NOT NULL OR c.url IS NOT NULL
ORDER BY c.id
LIMIT 30;
" 2>/dev/null

echo
echo '=== kafka console connections ==='
docker exec quicknav-mysql mysql -uroot -proot123456 -N quicknavigation -e "
SELECT id, name, host, port FROM kafka_console_connections LIMIT 10;
" 2>/dev/null

echo
echo '=== container status ==='
docker ps --format '{{.Names}} {{.Status}}' | grep quicknav

echo
echo '=== backend recent errors ==='
docker logs quicknav-backend --tail 40 2>&1 | grep -iE 'error|fail|omnidb|redpanda|kafka|mysql|connect' | tail -20

echo
echo '=== host.docker.internal from backend ==='
docker exec quicknav-backend getent hosts host.docker.internal 2>&1 || docker exec quicknav-backend ping -c1 -W2 host.docker.internal 2>&1 | head -3

echo
echo '=== test omnidb internal ==='
docker exec quicknav-backend wget -q -S -O /dev/null http://omnidb-app:8000 2>&1 | head -5 || true
docker exec quicknav-backend wget -q -S -O /dev/null http://omnidb:8081 2>&1 | head -5 || true
"""

i, o, e = ssh.exec_command("bash -s", timeout=120)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace")
if err.strip():
    print("ERR:", err)
ssh.close()
