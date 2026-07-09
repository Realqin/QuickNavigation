#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=30)
script = r"""
python3 - <<'PY'
import socket, ssl, urllib.request

def test_tls(host, timeout=10):
    try:
        ip = socket.gethostbyname(host)
        s = socket.create_connection((ip, 443), timeout=timeout)
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(s, server_hostname=host)
        print(f'TLS OK {host} {ip} {ss.version()}')
        ss.close()
        return True
    except Exception as e:
        print(f'TLS FAIL {host}: {e}')
        return False

for h in [
    'www.baidu.com',
    'registry-1.docker.io',
    'docker.m.daocloud.io',
    'pypi.tuna.tsinghua.edu.cn',
    'github.com',
]:
    test_tls(h)

for url in [
    'https://www.baidu.com',
    'https://docker.m.daocloud.io/v2/',
    'https://pypi.tuna.tsinghua.edu.cn/simple/',
]:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            print('HTTP', url, r.status)
    except Exception as e:
        print('HTTP FAIL', url, e)
PY
echo DONE
"""
i,o,e=ssh.exec_command("bash -s",timeout=180)
i.write(script); i.channel.shutdown_write()
print(o.read().decode(errors='replace'))
print(e.read().decode(errors='replace'))
ssh.close()
