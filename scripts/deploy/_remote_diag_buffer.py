#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=30)
script = r"""
echo '=== kernel network / memory ==='
sysctl net.ipv4.ip_local_port_range net.core.somaxconn net.core.netdev_max_backlog net.ipv4.tcp_max_syn_backlog 2>/dev/null
free -h
echo
echo '=== socket summary ==='
ss -s
echo
echo '=== ESTAB counts by port ==='
ss -tan state established | awk 'NR>1{print $4}' | sed 's/.*://' | sort | uniq -c | sort -rn | head -15
echo
echo '=== TIME-WAIT count ==='
ss -tan state time-wait | wc -l
echo
echo '=== container stats ==='
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>/dev/null | head -12
echo
echo '=== backend/nginx logs ==='
docker logs quicknav-backend --tail 30 2>&1 | tail -20
docker logs quicknav-frontend --tail 20 2>&1 | tail -15
echo
echo '=== test api from host ==='
python3 - <<'PY'
import httpx
try:
    r = httpx.post('http://127.0.0.1:8080/api/auth/login', json={'username':'admin','password':'admin123'}, timeout=15)
    print('login', r.status_code)
    token = r.json().get('access_token','')
    for path in ['/api/dict','/api/connections/home?project=1&environment=1']:
        h = httpx.get(f'http://127.0.0.1:8080{path}', headers={'Authorization': f'Bearer {token}'}, timeout=15)
        print(path, h.status_code, len(h.content))
except Exception as e:
    print('API FAIL', e)
PY
echo DONE
"""
i,o,e=ssh.exec_command("bash -s",timeout=120)
i.write(script); i.channel.shutdown_write()
print(o.read().decode(errors='replace'))
ssh.close()
