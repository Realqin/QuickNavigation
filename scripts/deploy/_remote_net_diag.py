#!/usr/bin/env python3
import paramiko

HOST = "192.168.6.189"
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="root", password="firefly", timeout=30)

script = r"""
echo '=== interfaces ==='
ip -br addr
echo
echo '=== routes ==='
ip route
echo
echo '=== resolv.conf ==='
cat /etc/resolv.conf 2>/dev/null || true
echo
echo '=== default gw ping ==='
GW=$(ip route | awk '/default/ {print $3; exit}')
echo "gateway=$GW"
ping -c 2 -W 2 "$GW" 2>&1 | tail -3
echo
echo '=== ping public ip 223.5.5.5 ==='
ping -c 2 -W 3 223.5.5.5 2>&1 | tail -4
echo
echo '=== ping baidu ip 110.242.68.66 ==='
ping -c 2 -W 3 110.242.68.66 2>&1 | tail -4
echo
echo '=== dns lookup registry-1.docker.io ==='
getent hosts registry-1.docker.io 2>&1 || nslookup registry-1.docker.io 2>&1 | tail -5
echo
echo '=== curl docker hub ==='
curl -sS -o /dev/null -w 'docker.io HTTP %{http_code} time=%{time_total}s\n' --connect-timeout 8 https://registry-1.docker.io/v2/ 2>&1
echo
echo '=== curl baidu ==='
curl -sS -o /dev/null -w 'baidu HTTP %{http_code}\n' --connect-timeout 8 https://www.baidu.com 2>&1
echo
echo '=== iptables/nft ==='
iptables -L OUTPUT -n 2>/dev/null | head -8 || true
nft list ruleset 2>/dev/null | head -15 || true
echo
echo '=== network manager / conn ==='
nmcli dev status 2>/dev/null || true
nmcli con show 2>/dev/null | head -10 || true
echo DONE
"""
i, o, e = ssh.exec_command("bash -s", timeout=120)
i.write(script)
i.channel.shutdown_write()
print(o.read().decode(errors="replace"))
err = e.read().decode(errors="replace")
if err.strip():
    print("ERR:", err)
ssh.close()
