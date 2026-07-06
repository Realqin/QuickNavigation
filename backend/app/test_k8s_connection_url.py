from app.k8s_connection_service import parse_k8s_connection_url


def test_parse_kubesphere_console_url():
    parsed = parse_k8s_connection_url("http://10.100.0.11:30880")
    assert parsed.visit_url == "http://10.100.0.11:30880"
    assert parsed.hostname == "10.100.0.11"
    assert parsed.port == 30880
    assert parsed.provider == "kubesphere"
    assert parsed.api_server == "http://10.100.0.11:30880"


def test_parse_native_api_url():
    parsed = parse_k8s_connection_url("https://192.168.1.10:6443")
    assert parsed.visit_url == "https://192.168.1.10:6443"
    assert parsed.provider == "native"
    assert parsed.api_server == "https://192.168.1.10:6443"


def test_parse_host_without_port_defaults_api_6443():
    parsed = parse_k8s_connection_url("http://192.168.1.10")
    assert parsed.visit_url == "http://192.168.1.10"
    assert parsed.provider == "native"
    assert parsed.api_server == "https://192.168.1.10:6443"


def test_parse_kuboard_url_keeps_path():
    parsed = parse_k8s_connection_url("http://10.0.0.8:30080/kuboard/cluster/test")
    assert parsed.visit_url == "http://10.0.0.8:30080/kuboard/cluster/test"
    assert parsed.provider == "kuboard"
    assert parsed.api_server == "http://10.0.0.8:30080"


def test_parse_kubesphere_deployments_path():
    url = "http://10.100.0.11:30880/clusters/default/deployments"
    parsed = parse_k8s_connection_url(url)
    assert parsed.visit_url == url
    assert parsed.hostname == "10.100.0.11"
    assert parsed.port == 30880
    assert parsed.provider == "kubesphere"
    assert parsed.api_server == "http://10.100.0.11:30880"


def test_apply_k8s_keeps_user_url():
    from app.k8s_connection_service import apply_k8s_connection_fields

    url = "http://10.100.0.11:30880/clusters/default/deployments"
    out = apply_k8s_connection_fields({"url": url})
    assert out["url"] == url
    assert out["host"] == "10.100.0.11"
    assert out["port"] == 30880
