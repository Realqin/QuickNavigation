import time
import base64
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import K8sClusterConfig
from app.schemas import K8sClusterConfigCreate, K8sClusterConfigUpdate, K8sScaleRequest


K8S_TIMEOUT = httpx.Timeout(connect=8.0, read=30.0, write=10.0, pool=10.0)
KUBESPHERE_TOKEN_TTL_SECONDS = 10 * 60
_KUBESPHERE_AUTH_CACHE: dict[int, tuple[dict[str, str], float]] = {}


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _max_datetime(values: list[datetime | None]) -> datetime | None:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    return max(cleaned)


def _q(value: str) -> str:
    return quote(value, safe="")


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    return items if isinstance(items, list) else []


def _normalize_api_server(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="集群地址不能为空")
    if not text.startswith(("http://", "https://")):
        text = f"https://{text}"
    return text.rstrip("/")


def _normalize_provider(value: str | None) -> str:
    text = (value or "native").strip().lower()
    return text if text in {"native", "kubesphere", "kuboard"} else "native"


def _normalize_auth_type(value: str | None) -> str:
    text = (value or "password").strip().lower()
    return text if text in {"password", "token"} else "password"


def _response_preview(response: httpx.Response, limit: int = 160) -> str:
    return (
        response.content[: max(limit * 2, limit)]
        .decode(response.encoding or "utf-8", errors="replace")
        .strip()
        .replace("\n", " ")[:limit]
    )


def _base64_encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _kubesphere_encrypt(password: str, encrypt_key: str = "kubesphere") -> str:
    encoded_password = _base64_encode(password)
    key = encrypt_key
    if len(encoded_password) > len(key):
        key = f"{key}{encoded_password[: len(encoded_password) - len(key)]}"
    bits: list[str] = []
    chars: list[str] = []
    for index, key_char in enumerate(key):
        password_code = ord(encoded_password[index]) if len(encoded_password) > index else 64
        total = ord(key_char) + password_code
        bits.append("0" if total % 2 == 0 else "1")
        chars.append(chr(total // 2))
    return f"{_base64_encode(''.join(bits))}@{''.join(chars)}"


def cluster_to_out_dict(cluster: K8sClusterConfig) -> dict[str, Any]:
    return {
        "id": cluster.id,
        "name": cluster.name,
        "api_server": cluster.api_server,
        "provider": cluster.provider or "native",
        "auth_type": cluster.auth_type or "password",
        "username": cluster.username,
        "verify_ssl": bool(cluster.verify_ssl),
        "password_set": bool(cluster.password),
        "sort_order": cluster.sort_order,
        "last_connected_at": cluster.last_connected_at,
        "created_at": cluster.created_at,
        "updated_at": cluster.updated_at,
    }


def list_k8s_clusters(db: Session) -> list[dict[str, Any]]:
    clusters = (
        db.query(K8sClusterConfig)
        .order_by(K8sClusterConfig.sort_order.asc(), K8sClusterConfig.id.asc())
        .all()
    )
    return [cluster_to_out_dict(cluster) for cluster in clusters]


def get_k8s_cluster(db: Session, cluster_id: int) -> K8sClusterConfig:
    cluster = db.query(K8sClusterConfig).filter(K8sClusterConfig.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="K8s 集群配置不存在")
    return cluster


def create_k8s_cluster(db: Session, data: K8sClusterConfigCreate) -> dict[str, Any]:
    payload = data.model_dump()
    password = str(payload.pop("password") or "").strip() or None
    max_order = db.query(func.max(K8sClusterConfig.sort_order)).scalar() or 0
    cluster = K8sClusterConfig(
        name=payload["name"].strip(),
        api_server=_normalize_api_server(payload["api_server"]),
        provider=_normalize_provider(payload.get("provider")),
        auth_type=_normalize_auth_type(payload.get("auth_type")),
        username=str(payload.get("username") or "").strip() or None,
        password=password,
        verify_ssl=bool(payload.get("verify_ssl")),
        sort_order=max_order + 1,
    )
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    return cluster_to_out_dict(cluster)


def update_k8s_cluster(
    db: Session, cluster: K8sClusterConfig, data: K8sClusterConfigUpdate
) -> dict[str, Any]:
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        if key == "password":
            password = str(value or "").strip()
            if password:
                cluster.password = password
            continue
        if key == "api_server" and value is not None:
            setattr(cluster, key, _normalize_api_server(value))
            continue
        if key == "provider":
            setattr(cluster, key, _normalize_provider(value))
            continue
        if key == "auth_type":
            setattr(cluster, key, _normalize_auth_type(value))
            continue
        if key == "username":
            setattr(cluster, key, str(value or "").strip() or None)
            continue
        if key == "name" and value is not None:
            setattr(cluster, key, str(value).strip())
            continue
        setattr(cluster, key, value)
    db.commit()
    db.refresh(cluster)
    _KUBESPHERE_AUTH_CACHE.pop(cluster.id, None)
    return cluster_to_out_dict(cluster)


def delete_k8s_cluster(db: Session, cluster: K8sClusterConfig) -> None:
    _KUBESPHERE_AUTH_CACHE.pop(cluster.id, None)
    db.delete(cluster)
    db.commit()


def _uses_kubesphere_password_auth(cluster: K8sClusterConfig) -> bool:
    return (cluster.provider or "native") == "kubesphere" and (cluster.auth_type or "password") == "password"


def _response_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return _response_preview(response, 500)
    if isinstance(payload, dict):
        for key in ("detail", "message", "reason", "error", "body"):
            value = payload.get(key)
            if value:
                return str(value)
    return _response_preview(response, 500)


def _is_kubesphere_auth_cache_error(response: httpx.Response, detail: str) -> bool:
    if response.status_code == 401:
        return True
    if response.status_code != 403:
        return False
    text = detail.lower()
    return any(
        marker in text
        for marker in (
            "token not found",
            "token is invalid",
            "invalid token",
            "unauthorized",
        )
    )


def _request(
    cluster: K8sClusterConfig,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    force_kubesphere_login: bool = False,
    retry_kubesphere_login: bool = True,
) -> httpx.Response:
    headers = {"Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)

    auth: httpx.BasicAuth | None = None
    use_kubesphere_password_auth = _uses_kubesphere_password_auth(cluster)
    if use_kubesphere_password_auth:
        headers.update(_get_kubesphere_auth_headers(cluster, force_refresh=force_kubesphere_login))
    elif (cluster.auth_type or "password") == "token":
        token = str(cluster.password or "").strip()
        if not token:
            raise HTTPException(status_code=400, detail="Token 未配置")
        headers["Authorization"] = f"Bearer {token}"
    else:
        username = str(cluster.username or "").strip()
        password = str(cluster.password or "").strip()
        if not username or not password:
            raise HTTPException(status_code=400, detail="账号或密码未配置")
        auth = httpx.BasicAuth(username, password)

    url = f"{cluster.api_server.rstrip('/')}{path}"
    try:
        with httpx.Client(timeout=K8S_TIMEOUT, verify=bool(cluster.verify_ssl)) as client:
            response = client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
                auth=auth,
            )
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=502, detail=f"无法连接集群：{exc}") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="连接 Kubernetes 集群超时") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Kubernetes 请求失败：{exc}") from exc

    if 200 <= response.status_code < 300:
        return response
    if 300 <= response.status_code < 400:
        location = response.headers.get("location") or ""
        raise HTTPException(
            status_code=502,
            detail=f"Kubernetes API 被重定向到 {location or '其他页面'}，请确认认证方式和 API 地址",
        )

    detail = _response_error_detail(response)
    if (
        use_kubesphere_password_auth
        and retry_kubesphere_login
        and _is_kubesphere_auth_cache_error(response, detail)
    ):
        _KUBESPHERE_AUTH_CACHE.pop(cluster.id, None)
        return _request(
            cluster,
            method,
            path,
            params=params,
            json_body=json_body,
            extra_headers=extra_headers,
            force_kubesphere_login=True,
            retry_kubesphere_login=False,
        )
    if response.status_code in {401, 403}:
        detail = detail or "认证失败或权限不足"
    raise HTTPException(status_code=response.status_code, detail=detail or "Kubernetes API 返回错误")


def _parse_token_payload(response: httpx.Response, login_path: str) -> dict[str, str]:
    if response.status_code >= 400:
        detail = _response_preview(response, 300)
        raise HTTPException(
            status_code=response.status_code,
            detail=f"KubeSphere 登录失败：{login_path}；{detail or response.reason_phrase}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"KubeSphere 登录接口未返回 JSON：{login_path}；"
                f"Content-Type：{response.headers.get('content-type') or '-'}；"
                f"响应预览：{_response_preview(response)}"
            ),
        ) from exc
    token = str(payload.get("access_token") or payload.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=502, detail=f"KubeSphere 登录响应缺少 access_token：{login_path}")
    return {"Authorization": f"Bearer {token}"}


def _cookie_header(cookies: httpx.Cookies) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def _parse_console_login_payload(response: httpx.Response, login_path: str) -> dict[str, str]:
    if 300 <= response.status_code < 400:
        cookie = _cookie_header(response.cookies)
        if cookie:
            return {"Cookie": cookie}
        location = response.headers.get("location") or ""
        raise HTTPException(
            status_code=502,
            detail=f"KubeSphere 登录跳转到 {location or '其他页面'}，但未返回会话 Cookie",
        )
    if response.status_code >= 400:
        detail = _response_preview(response, 300)
        raise HTTPException(
            status_code=response.status_code,
            detail=f"KubeSphere 登录失败：{login_path}；{detail or response.reason_phrase}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"KubeSphere 登录接口未返回 JSON：{login_path}；"
                f"Content-Type：{response.headers.get('content-type') or '-'}；"
                f"响应预览：{_response_preview(response)}"
            ),
        ) from exc
    status = int(payload.get("status") or 0)
    if status != 200:
        message = payload.get("message") or payload.get("reason") or payload.get("body") or "登录失败"
        raise HTTPException(status_code=401, detail=f"KubeSphere 登录失败：{message}")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    token = str(data.get("access_token") or data.get("token") or payload.get("access_token") or "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    cookie = _cookie_header(response.cookies)
    if cookie:
        return {"Cookie": cookie}
    raise HTTPException(status_code=502, detail="KubeSphere 登录成功但未返回 token 或 cookie")


def _get_kubesphere_auth_headers(
    cluster: K8sClusterConfig,
    *,
    force_refresh: bool = False,
) -> dict[str, str]:
    now = time.time()
    if force_refresh:
        _KUBESPHERE_AUTH_CACHE.pop(cluster.id, None)
    else:
        cached = _KUBESPHERE_AUTH_CACHE.get(cluster.id)
        if cached and cached[1] > now:
            return cached[0]

    username = str(cluster.username or "").strip()
    password = str(cluster.password or "").strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="KubeSphere 账号或密码未配置")

    base = cluster.api_server.rstrip("/")
    verify_ssl = bool(cluster.verify_ssl)
    auth_headers: dict[str, str] = {}
    with httpx.Client(timeout=K8S_TIMEOUT, verify=verify_ssl, follow_redirects=False) as client:
        login_attempts = [
            (
                "/login",
                lambda: client.post(
                    f"{base}/login",
                    json={"username": username, "encrypt": _kubesphere_encrypt(password)},
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                ),
                _parse_console_login_payload,
            ),
            (
                "/kapis/iam.kubesphere.io/v1alpha2/login",
                lambda: client.post(
                    f"{base}/kapis/iam.kubesphere.io/v1alpha2/login",
                    json={"username": username, "password": password},
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                ),
                _parse_token_payload,
            ),
            (
                "/oauth/token",
                lambda: client.post(
                    f"{base}/oauth/token",
                    data={
                        "grant_type": "password",
                        "username": username,
                        "password": password,
                        "client_id": "kubesphere",
                        "client_secret": "kubesphere",
                    },
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                ),
                _parse_token_payload,
            ),
        ]
        errors: list[str] = []
        for login_path, request_login, parse_login in login_attempts:
            try:
                response = request_login()
                auth_headers = parse_login(response, login_path)
                break
            except HTTPException as exc:
                errors.append(str(exc.detail))
            except httpx.HTTPError as exc:
                errors.append(f"{login_path}: {exc}")
        if not auth_headers:
            raise HTTPException(
                status_code=502,
                detail=(
                    "KubeSphere 自动登录失败。请确认地址是 ks-apiserver 或 console 已代理 KubeSphere API；"
                    + "；".join(errors[:2])
                ),
            )

    _KUBESPHERE_AUTH_CACHE[cluster.id] = (
        auth_headers,
        time.time() + KUBESPHERE_TOKEN_TTL_SECONDS,
    )
    return auth_headers


def _get_json(
    cluster: K8sClusterConfig,
    path: str,
    params: dict[str, Any] | None = None,
    *,
    force_kubesphere_login: bool = False,
) -> dict[str, Any]:
    response = _request(
        cluster,
        "GET",
        path,
        params=params,
        force_kubesphere_login=force_kubesphere_login,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        content_type = response.headers.get("content-type", "")
        body_preview = _response_preview(response)
        hint = (
            "集群地址没有返回 Kubernetes JSON，请确认填写的是 kube-apiserver 地址，"
            "或 KubeSphere/Kuboard 已开启 Kubernetes API 代理。"
        )
        detail = f"{hint} 请求路径：{path}；Content-Type：{content_type or '-'}"
        if body_preview:
            detail = f"{detail}；响应预览：{body_preview}"
        raise HTTPException(status_code=502, detail=detail) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail=f"Kubernetes API 返回格式异常：{path}")
    return payload


def test_k8s_cluster_connection(db: Session, cluster: K8sClusterConfig) -> dict[str, Any]:
    started = time.perf_counter()
    namespace_payload = _get_json(
        cluster,
        "/api/v1/namespaces",
        force_kubesphere_login=_uses_kubesphere_password_auth(cluster),
    )
    version_payload: dict[str, Any] = {}
    try:
        version_path = "/kapis/version" if (cluster.provider or "native") == "kubesphere" else "/version"
        version_payload = _get_json(cluster, version_path)
    except HTTPException:
        if (cluster.provider or "native") != "kubesphere":
            raise
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    cluster.last_connected_at = datetime.utcnow()
    db.commit()
    git_version = str(version_payload.get("gitVersion") or "")
    return {
        "ok": True,
        "message": "连接成功",
        "cluster_id": cluster.id,
        "version": git_version,
        "namespace_count": len(_items(namespace_payload)),
        "latency_ms": latency_ms,
    }


def list_k8s_projects(cluster: K8sClusterConfig) -> list[dict[str, Any]]:
    payload = _get_json(cluster, "/api/v1/namespaces")
    projects: list[dict[str, Any]] = []
    for item in _items(payload):
        metadata = item.get("metadata") or {}
        status = item.get("status") or {}
        name = str(metadata.get("name") or "")
        if not name:
            continue
        projects.append(
            {
                "name": name,
                "status": str(status.get("phase") or ""),
                "created_at": _parse_datetime(metadata.get("creationTimestamp")),
            }
        )
    return sorted(projects, key=lambda item: item["name"])


def _selector_matches(selector: dict[str, Any], labels: dict[str, Any]) -> bool:
    if not selector:
        return False
    return all(str(labels.get(key)) == str(value) for key, value in selector.items())


def _pod_ready(pod: dict[str, Any]) -> bool:
    status = pod.get("status") or {}
    if status.get("phase") != "Running":
        return False
    for condition in status.get("conditions") or []:
        if condition.get("type") == "Ready":
            return condition.get("status") == "True"
    return False


def _pod_updated_at(pod: dict[str, Any]) -> datetime | None:
    metadata = pod.get("metadata") or {}
    status = pod.get("status") or {}
    values = [_parse_datetime(metadata.get("creationTimestamp"))]
    for condition in status.get("conditions") or []:
        values.append(_parse_datetime(condition.get("lastTransitionTime")))
    for container_status in status.get("containerStatuses") or []:
        state = container_status.get("state") or {}
        for state_payload in state.values():
            if isinstance(state_payload, dict):
                values.append(_parse_datetime(state_payload.get("startedAt")))
                values.append(_parse_datetime(state_payload.get("finishedAt")))
    return _max_datetime(values)


def _pod_out(pod: dict[str, Any], namespace: str) -> dict[str, Any]:
    metadata = pod.get("metadata") or {}
    status = pod.get("status") or {}
    spec = pod.get("spec") or {}
    container_statuses = {
        item.get("name"): item for item in status.get("containerStatuses") or []
    }
    containers: list[dict[str, Any]] = []
    for container in spec.get("containers") or []:
        name = str(container.get("name") or "")
        container_status = container_statuses.get(name) or {}
        containers.append(
            {
                "name": name,
                "image": str(container.get("image") or ""),
                "ready": bool(container_status.get("ready")),
                "restart_count": int(container_status.get("restartCount") or 0),
            }
        )
    restart_count = sum(item["restart_count"] for item in containers)
    phase = str(status.get("phase") or "")
    status_text = "Running" if _pod_ready(pod) else phase
    return {
        "name": str(metadata.get("name") or ""),
        "namespace": namespace,
        "status": status_text,
        "phase": phase,
        "node": str(spec.get("nodeName") or ""),
        "pod_ip": str(status.get("podIP") or ""),
        "host_ip": str(status.get("hostIP") or ""),
        "containers": containers,
        "restart_count": restart_count,
        "created_at": _parse_datetime(metadata.get("creationTimestamp")),
        "updated_at": _pod_updated_at(pod),
    }


def _workload_updated_at(workload: dict[str, Any]) -> datetime | None:
    metadata = workload.get("metadata") or {}
    status = workload.get("status") or {}
    values = [_parse_datetime(metadata.get("creationTimestamp"))]
    for condition in status.get("conditions") or []:
        values.append(_parse_datetime(condition.get("lastUpdateTime")))
        values.append(_parse_datetime(condition.get("lastTransitionTime")))
    return _max_datetime(values)


def _service_ports(service: dict[str, Any]) -> list[str]:
    spec = service.get("spec") or {}
    result: list[str] = []
    for port in spec.get("ports") or []:
        port_value = port.get("port")
        target = port.get("targetPort")
        protocol = port.get("protocol") or "TCP"
        if target and target != port_value:
            result.append(f"{port_value}->{target}/{protocol}")
        else:
            result.append(f"{port_value}/{protocol}")
    return result


def _service_external_ports(service: dict[str, Any]) -> list[int]:
    spec = service.get("spec") or {}
    result: list[int] = []
    for port in spec.get("ports") or []:
        node_port = port.get("nodePort")
        if node_port is None:
            continue
        try:
            value = int(node_port)
        except (TypeError, ValueError):
            continue
        if value not in result:
            result.append(value)
    return result


def _service_for_workload(
    workload_selector: dict[str, Any],
    services: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for service in services:
        selector = (service.get("spec") or {}).get("selector") or {}
        if _selector_matches(selector, workload_selector):
            return service
    return None


def _service_row(
    *,
    namespace: str,
    service_name: str,
    service: dict[str, Any] | None,
    pods: list[dict[str, Any]],
    workload: dict[str, Any] | None = None,
    workload_kind: str | None = None,
) -> dict[str, Any]:
    pod_rows = [_pod_out(pod, namespace) for pod in pods]
    ready = sum(1 for pod in pods if _pod_ready(pod))
    spec = (workload or {}).get("spec") or {}
    status = (workload or {}).get("status") or {}
    if workload_kind == "DaemonSet":
        replicas = int(status.get("desiredNumberScheduled") or len(pods))
    else:
        replicas = int(spec.get("replicas") if spec.get("replicas") is not None else len(pods))
    service_spec = (service or {}).get("spec") or {}
    metadata = (service or workload or {}).get("metadata") or {}
    workload_name = str(((workload or {}).get("metadata") or {}).get("name") or "") or None
    updated_at = _max_datetime(
        [_workload_updated_at(workload or {})]
        + [pod.get("updated_at") for pod in pod_rows]
        + [_parse_datetime(metadata.get("creationTimestamp"))]
    )
    nodes = sorted({pod["node"] for pod in pod_rows if pod.get("node")})
    pod_ips = sorted({pod["pod_ip"] for pod in pod_rows if pod.get("pod_ip")})
    health = "running" if replicas > 0 and ready >= replicas else "warning" if ready > 0 else "stopped"
    row_kind = workload_kind or "Service"
    row_name = workload_name or service_name
    return {
        "id": f"{namespace}:{row_kind}:{row_name}",
        "project": namespace,
        "namespace": namespace,
        "service_name": service_name,
        "service_type": str(service_spec.get("type") or ""),
        "cluster_ip": str(service_spec.get("clusterIP") or ""),
        "ports": _service_ports(service or {}),
        "external_ports": _service_external_ports(service or {}),
        "workload_kind": workload_kind,
        "workload_name": workload_name,
        "status": health,
        "ready_replicas": ready,
        "replicas": replicas,
        "nodes": nodes,
        "pod_ips": pod_ips,
        "updated_at": updated_at,
        "pods": pod_rows,
        "scalable": workload_kind in {"Deployment", "StatefulSet"},
    }


def _load_namespace_payloads(cluster: K8sClusterConfig, namespace: str) -> dict[str, list[dict[str, Any]]]:
    ns = _q(namespace)
    return {
        "services": _items(_get_json(cluster, f"/api/v1/namespaces/{ns}/services")),
        "pods": _items(_get_json(cluster, f"/api/v1/namespaces/{ns}/pods")),
        "deployments": _items(_get_json(cluster, f"/apis/apps/v1/namespaces/{ns}/deployments")),
        "statefulsets": _items(_get_json(cluster, f"/apis/apps/v1/namespaces/{ns}/statefulsets")),
        "daemonsets": _items(_get_json(cluster, f"/apis/apps/v1/namespaces/{ns}/daemonsets")),
    }


def list_k8s_services(cluster: K8sClusterConfig, namespace: str) -> list[dict[str, Any]]:
    payloads = _load_namespace_payloads(cluster, namespace)
    services = payloads["services"]
    pods = payloads["pods"]
    rows: list[dict[str, Any]] = []
    matched_service_names: set[str] = set()

    workload_groups = [
        ("Deployment", payloads["deployments"]),
        ("StatefulSet", payloads["statefulsets"]),
        ("DaemonSet", payloads["daemonsets"]),
    ]
    for workload_kind, workloads in workload_groups:
        for workload in workloads:
            metadata = workload.get("metadata") or {}
            spec = workload.get("spec") or {}
            selector = ((spec.get("selector") or {}).get("matchLabels")) or {}
            matched_pods = [
                pod
                for pod in pods
                if _selector_matches(selector, (pod.get("metadata") or {}).get("labels") or {})
            ]
            service = _service_for_workload(selector, services)
            service_name = str((service or {}).get("metadata", {}).get("name") or metadata.get("name") or "")
            if service:
                matched_service_names.add(service_name)
            if not service_name:
                continue
            rows.append(
                _service_row(
                    namespace=namespace,
                    service_name=service_name,
                    service=service,
                    pods=matched_pods,
                    workload=workload,
                    workload_kind=workload_kind,
                )
            )

    for service in services:
        metadata = service.get("metadata") or {}
        service_name = str(metadata.get("name") or "")
        if not service_name or service_name in matched_service_names:
            continue
        selector = (service.get("spec") or {}).get("selector") or {}
        matched_pods = [
            pod
            for pod in pods
            if _selector_matches(selector, (pod.get("metadata") or {}).get("labels") or {})
        ]
        rows.append(
            _service_row(
                namespace=namespace,
                service_name=service_name,
                service=service,
                pods=matched_pods,
            )
        )

    return sorted(rows, key=lambda item: item["service_name"])


def scale_k8s_workload(cluster: K8sClusterConfig, data: K8sScaleRequest) -> dict[str, Any]:
    kind = data.workload_kind.lower()
    resource = {"deployment": "deployments", "statefulset": "statefulsets"}.get(kind)
    if not resource:
        raise HTTPException(status_code=400, detail="仅支持 Deployment / StatefulSet 扩缩容")
    path = (
        f"/apis/apps/v1/namespaces/{_q(data.namespace)}/{resource}/"
        f"{_q(data.workload_name)}/scale"
    )
    current = _get_json(cluster, path)
    replicas = int(((current.get("spec") or {}).get("replicas")) or 0)
    next_replicas = max(0, replicas + data.delta)
    _request(
        cluster,
        "PATCH",
        path,
        json_body={"spec": {"replicas": next_replicas}},
        extra_headers={"Content-Type": "application/merge-patch+json"},
    )
    return {
        "namespace": data.namespace,
        "workload_kind": data.workload_kind,
        "workload_name": data.workload_name,
        "replicas": next_replicas,
        "message": f"副本数已调整为 {next_replicas}",
    }


def read_k8s_pod_logs(
    cluster: K8sClusterConfig,
    *,
    namespace: str,
    pod_name: str,
    container: str | None = None,
    tail_lines: int = 500,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "tailLines": max(1, min(int(tail_lines or 500), 5000)),
        "timestamps": "true",
    }
    if container:
        params["container"] = container
    response = _request(
        cluster,
        "GET",
        f"/api/v1/namespaces/{_q(namespace)}/pods/{_q(pod_name)}/log",
        params=params,
        extra_headers={"Accept": "text/plain, application/json"},
    )
    return {
        "namespace": namespace,
        "pod_name": pod_name,
        "container": container or "",
        "logs": response.text,
    }
