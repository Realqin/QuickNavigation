#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.6.189", username="root", password="firefly", timeout=30)
script = r"""
echo '=== resolvectl ==='
resolvectl status 2>&1 | head -40
echo
echo '=== systemd-resolved ==='
systemctl is-active systemd-resolved
ss -lunp | grep -E ':53|:5353' || true
echo
echo '=== dig/host ==='
which dig host nslookup 2>/dev/null || true
resolvectl query www.baidu.com 2>&1 || true
resolvectl query registry-1.docker.io 2>&1 || true
echo
echo '=== docker daemon dns ==='
cat /etc/docker/daemon.json 2>/dev/null || echo no daemon.json
echo
echo '=== /etc/nsswitch hosts ==='
grep hosts /etc/nsswitch.conf
echo DONE
"""
i,o,e=ssh.exec_command("bash -s",timeout=60)
i.write(script); i.channel.shutdown_write()
print(o.read().decode(errors='replace'))
ssh.close()
