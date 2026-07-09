import urllib.request
import socket

proxies = ["http://127.0.0.1:10808", "http://127.0.0.1:7890", "http://127.0.0.1:10809"]
test_url = "https://registry-1.docker.io/v2/"

for p in proxies:
    try:
        proxy_handler = urllib.request.ProxyHandler({"http": p, "https": p})
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(test_url)
        resp = opener.open(req, timeout=10)
        print(f"OK {p} -> {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"TEST {p} -> HTTP {e.code} (proxy works, registry responded)")
    except Exception as e:
        print(f"FAIL {p} -> {type(e).__name__}: {e}")

# Also test direct
try:
    resp = urllib.request.urlopen(test_url, timeout=10)
    print(f"DIRECT -> {resp.status}")
except urllib.error.HTTPError as e:
    print(f"DIRECT -> HTTP {e.code}")
except Exception as e:
    print(f"DIRECT FAIL -> {type(e).__name__}: {e}")
