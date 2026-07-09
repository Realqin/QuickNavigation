#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=30)
script = r"""
python3 - <<'PY'
import httpx
for url in [
    'http://127.0.0.1:8080/proxy/omnidb/',
    'http://127.0.0.1:8080/proxy/kafka/',
    'http://127.0.0.1:8080/api/auth/login',
]:
    try:
        if 'login' in url:
            r = httpx.post(url, json={'username':'admin','password':'admin123'}, timeout=15)
        else:
            r = httpx.get(url, timeout=15, follow_redirects=True)
        print(url, r.status_code, len(r.content))
    except Exception as e:
        print(url, 'FAIL', e)
PY
echo DONE
"""
i,o,e=ssh.exec_command("bash -s",timeout=60)
i.write(script); i.channel.shutdown_write()
print(o.read().decode(errors='replace'))
ssh.close()
