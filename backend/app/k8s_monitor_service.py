import math
import time
import base64
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import K8sClusterConfig
from app.schemas import K8sClusterConfigCreate, K8sClusterConfigUpdate, K8sScaleRequest


K8S_TIMEOUT = httpx.Timeout(connect=8.0, read=45.0, write=10.0, pool=10.0)
K8S_HTTP_LIMITS = httpx.Limits(max_connections=32, max_keepalive_connections=16)
K8S_CONNECT_RETRY_ATTEMPTS = 5
K8S_CONNECT_RETRY_DELAYS = (0.4, 0.8, 1.2, 1.6)
FLINK_REST_TIMEOUT = httpx.Timeout(connect=6.0, read=20.0, write=10.0, pool=10.0)
FLINK_WATERMARK_DELAY_MS = 2 * 60 * 60 * 1000
MAX_WATERMARK_TIMESTAMP_MS = 253402300799999
KUBESPHERE_TOKEN_TTL_SECONDS = 10 * 60
_KUBESPHERE_AUTH_CACHE: dict[int, tuple[dict[str, str], float]] = {}


class K8sClusterHttpSession:
    """复用与 K8s/KubeSphere 的 HTTP 连接，避免批量请求时短连接过多被拒绝。"""

    def __init__(self, cluster: K8sClusterConfig):
        self.cluster = cluster
        self._client: httpx.Client | None = None

    def __enter__(self) -> "K8sClusterHttpSession":
        self._client = httpx.Client(
            timeout=K8S_TIMEOUT,
            verify=bool(self.cluster.verify_ssl),
            limits=K8S_HTTP_LIMITS,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            raise RuntimeError("K8sClusterHttpSession is not active")
        return self._client


class FlinkHttpClientPool:
    """复用与 Flink REST 的 HTTP 连接，按 NodePort base_url 缓存。"""

    def __init__(self, cluster: K8sClusterConfig):
        self._cluster = cluster
        self._clients: dict[str, httpx.Client] = {}

    def client_for_port(self, port: int) -> httpx.Client:
        base_url = _node_port_base_url(self._cluster, port)
        existing = self._clients.get(base_url)
        if existing is not None:
            return existing
        client = httpx.Client(
            timeout=FLINK_REST_TIMEOUT,
            verify=bool(self._cluster.verify_ssl),
            follow_redirects=True,
            limits=K8S_HTTP_LIMITS,
        )
        self._clients[base_url] = client
        return client

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    def __enter__(self) -> "FlinkHttpClientPool":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


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


def _is_no_buffer_space_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    while current is not None:
        text = f"{type(current).__name__}: {current}".lower()
        if "no buffer space" in text or "enobufs" in text or "10055" in text:
            return True
        current = current.__cause__  # type: ignore[assignment]
    return False


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
    http_client: httpx.Client | None = None,
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

    def _send_request(client: httpx.Client) -> httpx.Response:
        return client.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=headers,
            auth=auth,
        )

    response: httpx.Response | None = None
    last_connect_error: httpx.ConnectError | None = None
    for attempt in range(K8S_CONNECT_RETRY_ATTEMPTS):
        try:
            if http_client is not None:
                response = _send_request(http_client)
            else:
                with httpx.Client(
                    timeout=K8S_TIMEOUT,
                    verify=bool(cluster.verify_ssl),
                    limits=K8S_HTTP_LIMITS,
                ) as client:
                    response = _send_request(client)
            last_connect_error = None
            break
        except httpx.ConnectError as exc:
            last_connect_error = exc
            if _is_no_buffer_space_error(exc):
                raise HTTPException(
                    status_code=503,
                    detail=f"系统网络缓冲区不足，已停止重试 Kubernetes 连接：{exc}",
                ) from exc
            if attempt < K8S_CONNECT_RETRY_ATTEMPTS - 1:
                time.sleep(K8S_CONNECT_RETRY_DELAYS[attempt])
                continue
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="连接 Kubernetes 集群超时") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Kubernetes 请求失败：{exc}") from exc

    if last_connect_error is not None:
        raise HTTPException(
            status_code=502,
            detail=f"无法连接集群：{last_connect_error}",
        ) from last_connect_error
    if response is None:
        raise HTTPException(status_code=502, detail="无法连接集群")

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
            http_client=http_client,
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
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    response = _request(
        cluster,
        "GET",
        path,
        params=params,
        force_kubesphere_login=force_kubesphere_login,
        http_client=http_client,
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


def _projects_from_namespace_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
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


def test_k8s_cluster_connection(db: Session, cluster: K8sClusterConfig) -> dict[str, Any]:
    started = time.perf_counter()
    with K8sClusterHttpSession(cluster) as session:
        namespace_payload = _get_json(
            cluster,
            "/api/v1/namespaces",
            force_kubesphere_login=_uses_kubesphere_password_auth(cluster),
            http_client=session.client,
        )
        version_payload: dict[str, Any] = {}
        try:
            version_path = (
                "/kapis/version" if (cluster.provider or "native") == "kubesphere" else "/version"
            )
            version_payload = _get_json(cluster, version_path, http_client=session.client)
        except HTTPException:
            if (cluster.provider or "native") != "kubesphere":
                raise
    projects = _projects_from_namespace_payload(namespace_payload)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    connected_at = datetime.utcnow()
    cluster.last_connected_at = connected_at
    db.commit()
    git_version = str(version_payload.get("gitVersion") or "")
    return {
        "ok": True,
        "message": "连接成功",
        "cluster_id": cluster.id,
        "version": git_version,
        "namespace_count": len(projects),
        "projects": projects,
        "latency_ms": latency_ms,
        "last_connected_at": connected_at,
    }


def list_k8s_projects(
    cluster: K8sClusterConfig,
    *,
    http_client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    payload = _get_json(cluster, "/api/v1/namespaces", http_client=http_client)
    return _projects_from_namespace_payload(payload)


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


def _load_namespace_payloads(
    cluster: K8sClusterConfig,
    namespace: str,
    *,
    http_client: httpx.Client | None = None,
    include_pods: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    ns = _q(namespace)
    payloads: dict[str, list[dict[str, Any]]] = {
        "services": _items(_get_json(cluster, f"/api/v1/namespaces/{ns}/services", http_client=http_client)),
        "deployments": _items(
            _get_json(cluster, f"/apis/apps/v1/namespaces/{ns}/deployments", http_client=http_client)
        ),
        "statefulsets": _items(
            _get_json(cluster, f"/apis/apps/v1/namespaces/{ns}/statefulsets", http_client=http_client)
        ),
        "daemonsets": _items(
            _get_json(cluster, f"/apis/apps/v1/namespaces/{ns}/daemonsets", http_client=http_client)
        ),
    }
    if include_pods:
        payloads["pods"] = _items(
            _get_json(cluster, f"/api/v1/namespaces/{ns}/pods", http_client=http_client)
        )
    else:
        payloads["pods"] = []
    return payloads


def _list_k8s_services_impl(
    cluster: K8sClusterConfig,
    namespace: str,
    *,
    http_client: httpx.Client,
    include_pods: bool = True,
) -> list[dict[str, Any]]:
    payloads = _load_namespace_payloads(
        cluster,
        namespace,
        http_client=http_client,
        include_pods=include_pods,
    )
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


def _try_get_json(
    cluster: K8sClusterConfig,
    path: str,
    params: dict[str, Any] | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    try:
        return _get_json(cluster, path, params=params, http_client=http_client)
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise


def _workload_kind_name(resource: dict[str, Any]) -> tuple[str | None, str | None]:
    kind = str(resource.get("kind") or "")
    if kind not in {"Deployment", "StatefulSet", "DaemonSet"}:
        return None, None
    name = str(((resource.get("metadata") or {}).get("name") or "")) or None
    return kind, name


def _resolve_workload_link_meta(
    cluster: K8sClusterConfig,
    namespace: str,
    service_name: str,
    resource: dict[str, Any] | None,
    *,
    http_client: httpx.Client,
) -> tuple[str | None, str | None]:
    """解析 KubeSphere 控制台链接所需的工作负载类型与名称。"""
    if resource:
        kind, name = _workload_kind_name(resource)
        if kind and name:
            return kind, name

    ns = _q(namespace)
    sn = _q(service_name)

    for resource_path, kind in (
        ("deployments", "Deployment"),
        ("statefulsets", "StatefulSet"),
        ("daemonsets", "DaemonSet"),
    ):
        item = _try_get_json(
            cluster,
            f"/apis/apps/v1/namespaces/{ns}/{resource_path}/{sn}",
            http_client=http_client,
        )
        if item:
            return kind, str(((item.get("metadata") or {}).get("name") or "")) or None

    service_obj = resource if resource and str(resource.get("kind") or "") == "Service" else None
    if not service_obj:
        service_obj = _try_get_json(
            cluster,
            f"/api/v1/namespaces/{ns}/services/{sn}",
            http_client=http_client,
        )
    service_selector = ((service_obj or {}).get("spec") or {}).get("selector") or {}
    if not service_selector:
        return None, None

    for resource_path, kind in (
        ("deployments", "Deployment"),
        ("statefulsets", "StatefulSet"),
        ("daemonsets", "DaemonSet"),
    ):
        payload = _try_get_json(
            cluster,
            f"/apis/apps/v1/namespaces/{ns}/{resource_path}",
            http_client=http_client,
        )
        if not payload:
            continue
        for workload in _items(payload):
            workload_selector = ((workload.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
            if _selector_matches(service_selector, workload_selector):
                name = str(((workload.get("metadata") or {}).get("name") or "")) or None
                if name:
                    return kind, name

    return None, None


def _resolve_service_selector_and_resource(
    cluster: K8sClusterConfig,
    namespace: str,
    service_name: str,
    *,
    http_client: httpx.Client,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    ns = _q(namespace)
    sn = _q(service_name)
    service = _try_get_json(
        cluster,
        f"/api/v1/namespaces/{ns}/services/{sn}",
        http_client=http_client,
    )
    if service:
        selector = (service.get("spec") or {}).get("selector") or {}
        return selector, service

    workload: dict[str, Any] | None = None
    selector: dict[str, Any] = {}
    for resource in ("deployments", "statefulsets", "daemonsets"):
        item = _try_get_json(
            cluster,
            f"/apis/apps/v1/namespaces/{ns}/{resource}/{sn}",
            http_client=http_client,
        )
        if not item:
            continue
        workload = item
        selector = ((item.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
        break

    if not selector:
        return {}, service or workload

    services_payload = _get_json(
        cluster,
        f"/api/v1/namespaces/{ns}/services",
        http_client=http_client,
    )
    matched_service = _service_for_workload(selector, _items(services_payload))
    return selector, matched_service or workload


def _pod_restart_total(pods: list[dict[str, Any]]) -> int:
    return sum(_pod_container_restart_map(pods).values())


def _active_alarm_pods(pods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """仅统计仍在运行或启动中的 Pod，排除 Terminating/Succeeded/Failed 等。"""
    active: list[dict[str, Any]] = []
    for pod in pods:
        phase = str((pod.get("status") or {}).get("phase") or "")
        if phase in {"Running", "Pending"}:
            active.append(pod)
    return active


def _pod_container_restart_map(pods: list[dict[str, Any]]) -> dict[str, int]:
    """按 pod/container 维度收集 restartCount，key 形如 my-pod-abc/app。"""
    counts: dict[str, int] = {}
    for pod in _active_alarm_pods(pods):
        pod_name = str((pod.get("metadata") or {}).get("name") or "")
        if not pod_name:
            continue
        status = pod.get("status") or {}
        for container_status in status.get("containerStatuses") or []:
            container_name = str(container_status.get("name") or "")
            if not container_name:
                continue
            key = f"{pod_name}/{container_name}"
            counts[key] = int(container_status.get("restartCount") or 0)
    return counts


def probe_k8s_service_for_alarm(
    cluster: K8sClusterConfig,
    namespace: str,
    service_name: str,
    *,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """单服务轻量探测，供后台巡检顺序检查使用。"""

    def _probe(client: httpx.Client) -> dict[str, Any]:
        selector, resource = _resolve_service_selector_and_resource(
            cluster,
            namespace,
            service_name,
            http_client=client,
        )
        pods: list[dict[str, Any]] = []
        if selector:
            label_selector = ",".join(f"{key}={value}" for key, value in selector.items())
            pods_payload = _get_json(
                cluster,
                f"/api/v1/namespaces/{_q(namespace)}/pods",
                params={"labelSelector": label_selector},
                http_client=client,
            )
            pods = _items(pods_payload)
        service_obj = resource if resource and str(resource.get("kind") or "") == "Service" else None
        external_ports = _service_external_ports(service_obj or {})
        workload_kind, workload_name = _resolve_workload_link_meta(
            cluster,
            namespace,
            service_name,
            resource,
            http_client=client,
        )
        return {
            "restart_count": _pod_restart_total(pods),
            "restart_map": _pod_container_restart_map(pods),
            "external_ports": external_ports,
            "workload_kind": workload_kind,
            "workload_name": workload_name,
            "pods": pods,
        }

    if http_client is not None:
        return _probe(http_client)
    with K8sClusterHttpSession(cluster) as session:
        return _probe(session.client)


def list_k8s_services(
    cluster: K8sClusterConfig,
    namespace: str,
    *,
    http_client: httpx.Client | None = None,
    include_pods: bool = True,
) -> list[dict[str, Any]]:
    if http_client is not None:
        return _list_k8s_services_impl(
            cluster,
            namespace,
            http_client=http_client,
            include_pods=include_pods,
        )
    with K8sClusterHttpSession(cluster) as session:
        return _list_k8s_services_impl(
            cluster,
            namespace,
            http_client=session.client,
            include_pods=include_pods,
        )


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


def _node_port_base_url(cluster: K8sClusterConfig, port: int) -> str:
    try:
        port_value = int(port)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="外部访问端口不合法") from exc
    if port_value < 1 or port_value > 65535:
        raise HTTPException(status_code=400, detail="外部访问端口不合法")

    parsed = urlsplit(cluster.api_server)
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="K8s 集群地址缺少主机名")
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    scheme = parsed.scheme or "http"
    return f"{scheme}://{host}:{port_value}"


def _get_flink_json(
    cluster: K8sClusterConfig,
    base_url: str,
    path: str,
    *,
    http_client: httpx.Client | None = None,
) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        if http_client is not None:
            response = http_client.get(url, headers={"Accept": "application/json"})
        else:
            with httpx.Client(
                timeout=FLINK_REST_TIMEOUT,
                verify=bool(cluster.verify_ssl),
                follow_redirects=True,
            ) as client:
                response = client.get(url, headers={"Accept": "application/json"})
    except httpx.ConnectError as exc:
        if _is_no_buffer_space_error(exc):
            raise HTTPException(
                status_code=503,
                detail=f"系统网络缓冲区不足，已停止 Flink 请求：{exc}",
            ) from exc
        raise HTTPException(status_code=502, detail=f"无法连接 Flink REST 服务：{base_url}") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="访问 Flink REST 服务超时") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Flink REST 请求失败：{exc}") from exc

    if not 200 <= response.status_code < 300:
        preview = _response_preview(response, 300)
        raise HTTPException(
            status_code=502,
            detail=f"Flink REST 返回 {response.status_code}：{preview or response.reason_phrase}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        preview = _response_preview(response, 300)
        raise HTTPException(
            status_code=502,
            detail=f"Flink REST 未返回 JSON：{path}；响应预览：{preview or '-'}",
        ) from exc
    return payload


def _extract_flink_jobs(payload: dict[str, Any]) -> list[dict[str, str]]:
    jobs_payload = payload.get("jobs")
    candidates: list[dict[str, Any]] = []
    if isinstance(jobs_payload, list):
        candidates.extend(item for item in jobs_payload if isinstance(item, dict))
    if not candidates:
        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("jid"):
                    candidates.append(node)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)

    jobs: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in candidates:
        jid = str(item.get("jid") or item.get("id") or "").strip()
        if not jid or jid in seen:
            continue
        seen.add(jid)
        jobs.append(
            {
                "jid": jid,
                "name": str(item.get("name") or item.get("job-name") or "").strip(),
                "state": str(item.get("state") or item.get("status") or "").strip(),
            }
        )
    running = [job for job in jobs if job["state"].upper() == "RUNNING"]
    return running or jobs


def _extract_flink_vertices(payload: dict[str, Any]) -> list[dict[str, str]]:
    vertices_payload = payload.get("vertices")
    if not isinstance(vertices_payload, list):
        return []
    vertices: list[dict[str, str]] = []
    for item in vertices_payload:
        if not isinstance(item, dict):
            continue
        vertex_id = str(item.get("id") or "").strip()
        if not vertex_id:
            continue
        vertices.append(
            {
                "id": vertex_id,
                "name": str(item.get("name") or item.get("description") or vertex_id).strip(),
            }
        )
    return vertices


def _extract_watermark_candidates(payload: Any) -> list[Any]:
    result: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                normalized_key = key.replace("_", "").replace("-", "").lower()
                if normalized_key in {"value", "watermark", "lowwatermark"}:
                    result.append(value)
                else:
                    walk(value)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return result


def _coerce_watermark_timestamp(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    raw_number: float
    if isinstance(value, (int, float)):
        raw_number = float(value)
    else:
        text = str(value).strip().replace(",", "")
        if text.lower() in {"", "-", "--", "none", "null", "nan"}:
            return None
        try:
            raw_number = float(text)
        except ValueError:
            return None
    if not math.isfinite(raw_number) or raw_number <= 0:
        return None
    if 1_000_000_000 <= raw_number < 10_000_000_000:
        raw_number *= 1000
    if raw_number > MAX_WATERMARK_TIMESTAMP_MS:
        return None
    return int(raw_number)


def _watermark_value_out(raw: Any, timestamp: int, now_ms: int) -> dict[str, Any]:
    lag_ms = max(0, now_ms - timestamp)
    return {
        "raw": str(raw),
        "timestamp": timestamp,
        "formatted_at": datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc),
        "lag_ms": lag_ms,
        "lag_hours": round(lag_ms / 3600000, 3),
        "delayed": lag_ms > FLINK_WATERMARK_DELAY_MS,
    }


def _read_k8s_service_watermarks_with_client(
    cluster: K8sClusterConfig,
    *,
    namespace: str,
    service_name: str,
    port: int,
    base_url: str,
    http_client: httpx.Client,
) -> dict[str, Any]:
    overview = _get_flink_json(cluster, base_url, "/jobs/overview", http_client=http_client)
    if not isinstance(overview, dict):
        raise HTTPException(status_code=502, detail="Flink REST 返回格式异常：/jobs/overview")
    jobs = _extract_flink_jobs(overview)
    now_ms = int(time.time() * 1000)
    rows: list[dict[str, Any]] = []

    for job in jobs:
        job_id = job["jid"]
        job_name = job.get("name") or ""
        detail = _get_flink_json(
            cluster,
            base_url,
            f"/jobs/{_q(job_id)}",
            http_client=http_client,
        )
        if not isinstance(detail, dict):
            raise HTTPException(status_code=502, detail=f"Flink REST 返回格式异常：/jobs/{job_id}")
        for vertex in _extract_flink_vertices(detail):
            row = {
                "job_id": job_id,
                "job_name": job_name,
                "vertex_id": vertex["id"],
                "operator_name": vertex["name"],
                "watermarks": [],
                "error": "",
            }
            try:
                watermark_payload = _get_flink_json(
                    cluster,
                    base_url,
                    f"/jobs/{_q(job_id)}/vertices/{_q(vertex['id'])}/watermarks",
                    http_client=http_client,
                )
                for raw_value in _extract_watermark_candidates(watermark_payload):
                    timestamp = _coerce_watermark_timestamp(raw_value)
                    if timestamp is None:
                        continue
                    row["watermarks"].append(_watermark_value_out(raw_value, timestamp, now_ms))
            except HTTPException as exc:
                row["error"] = str(exc.detail)
            rows.append(row)

    return {
        "cluster_id": cluster.id,
        "namespace": namespace,
        "service_name": service_name,
        "port": int(port),
        "flink_url": f"{base_url}/#/overview",
        "generated_at": datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc),
        "jobs_count": len(jobs),
        "items": rows,
    }


def read_k8s_service_watermarks(
    cluster: K8sClusterConfig,
    *,
    namespace: str,
    service_name: str,
    port: int,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    base_url = _node_port_base_url(cluster, port)
    if http_client is not None:
        return _read_k8s_service_watermarks_with_client(
            cluster,
            namespace=namespace,
            service_name=service_name,
            port=port,
            base_url=base_url,
            http_client=http_client,
        )
    with httpx.Client(
        timeout=FLINK_REST_TIMEOUT,
        verify=bool(cluster.verify_ssl),
        follow_redirects=True,
        limits=K8S_HTTP_LIMITS,
    ) as client:
        return _read_k8s_service_watermarks_with_client(
            cluster,
            namespace=namespace,
            service_name=service_name,
            port=port,
            base_url=base_url,
            http_client=client,
        )


FLINK_EXCEPTION_MAX_ENTRIES = 10


def _truncate_exception_stacktrace(text: Any, limit: int = 2000) -> str:
    if text is None:
        return ""
    raw = str(text)
    if len(raw) <= limit:
        return raw
    return raw[:limit] + f"\n... (已截断，共 {len(raw)} 字符)"


def _parse_flink_exceptions_payload(payload: Any) -> tuple[str, int, list[dict[str, Any]]]:
    """从 Flink /jobs/{jid}/exceptions 响应中解析异常信息。

    兼容新版 exceptionHistory.entries 与旧版 root-exception/timestamp/all-exceptions。
    返回 (root_exception, latest_timestamp_ms, exceptions_list)。
    """
    if not isinstance(payload, dict):
        return "", 0, []

    entries: list[dict[str, Any]] = []

    history = payload.get("exceptionHistory")
    if isinstance(history, dict):
        raw_entries = history.get("entries")
        if isinstance(raw_entries, list):
            for item in raw_entries:
                if not isinstance(item, dict):
                    continue
                timestamp = _coerce_watermark_timestamp(item.get("timestamp")) or 0
                entries.append(
                    {
                        "exception_name": str(item.get("exceptionName") or "").strip(),
                        "stacktrace": _truncate_exception_stacktrace(item.get("stacktrace")),
                        "timestamp": timestamp,
                        "task_name": str(item.get("taskName") or "").strip(),
                        "location": str(item.get("location") or "").strip(),
                    }
                )

    if not entries:
        legacy = payload.get("all-exceptions")
        if isinstance(legacy, list):
            for item in legacy:
                if not isinstance(item, dict):
                    continue
                timestamp = _coerce_watermark_timestamp(item.get("timestamp")) or 0
                entries.append(
                    {
                        "exception_name": str(item.get("exception") or "").strip(),
                        "stacktrace": _truncate_exception_stacktrace(item.get("exception")),
                        "timestamp": timestamp,
                        "task_name": str(item.get("task") or "").strip(),
                        "location": str(item.get("location") or "").strip(),
                    }
                )

    root_exception = ""
    root_timestamp = 0
    if entries:
        latest = max(entries, key=lambda item: item.get("timestamp") or 0)
        root_exception = latest.get("exception_name") or latest.get("stacktrace") or ""
        root_timestamp = latest.get("timestamp") or 0
    else:
        root_exception = str(payload.get("root-exception") or "").strip()
        root_exception = _truncate_exception_stacktrace(root_exception)
        root_timestamp = _coerce_watermark_timestamp(payload.get("timestamp")) or 0

    return root_exception, root_timestamp, entries


def _read_k8s_service_exceptions_with_client(
    cluster: K8sClusterConfig,
    *,
    namespace: str,
    service_name: str,
    port: int,
    base_url: str,
    http_client: httpx.Client,
) -> dict[str, Any]:
    overview = _get_flink_json(cluster, base_url, "/jobs/overview", http_client=http_client)
    if not isinstance(overview, dict):
        raise HTTPException(status_code=502, detail="Flink REST 返回格式异常：/jobs/overview")
    jobs = _extract_flink_jobs(overview)

    job_exceptions: list[dict[str, Any]] = []
    for job in jobs:
        job_id = job["jid"]
        job_name = job.get("name") or ""
        payload = _get_flink_json(
            cluster,
            base_url,
            f"/jobs/{_q(job_id)}/exceptions?maxExceptions={FLINK_EXCEPTION_MAX_ENTRIES}",
            http_client=http_client,
        )
        root_exception, latest_timestamp, entries = _parse_flink_exceptions_payload(payload)
        job_exceptions.append(
            {
                "job_id": job_id,
                "job_name": job_name,
                "root_exception": root_exception,
                "latest_timestamp": latest_timestamp,
                "exception_count": len(entries),
                "exceptions": entries,
            }
        )

    return {
        "cluster_id": cluster.id,
        "namespace": namespace,
        "service_name": service_name,
        "port": int(port),
        "items": job_exceptions,
    }


def read_k8s_service_exceptions(
    cluster: K8sClusterConfig,
    *,
    namespace: str,
    service_name: str,
    port: int,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    base_url = _node_port_base_url(cluster, port)
    if http_client is not None:
        return _read_k8s_service_exceptions_with_client(
            cluster,
            namespace=namespace,
            service_name=service_name,
            port=port,
            base_url=base_url,
            http_client=http_client,
        )
    with httpx.Client(
        timeout=FLINK_REST_TIMEOUT,
        verify=bool(cluster.verify_ssl),
        follow_redirects=True,
        limits=K8S_HTTP_LIMITS,
    ) as client:
        return _read_k8s_service_exceptions_with_client(
            cluster,
            namespace=namespace,
            service_name=service_name,
            port=port,
            base_url=base_url,
            http_client=client,
        )


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
