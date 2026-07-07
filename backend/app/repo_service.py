import asyncio
import logging
import os
import re
import subprocess
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.database import SessionLocal
from app.repo_access_config import (
    get_github_token,
    get_gitlab_base_url,
    get_gitlab_ssh_command,
    get_gitlab_token,
)

logger = logging.getLogger(__name__)

GITHUB_HOSTS = {"github.com", "www.github.com"}
SCP_GIT_PATTERN = re.compile(r"^git@([^:/]+):(?P<path>.+)$")


@dataclass
class ParsedRepo:
    provider: str | None = None
    repo_path: str | None = None
    branch: str | None = None
    base_url: str | None = None
    web_url: str | None = None


def _strip_git_suffix(segment: str) -> str:
    value = segment.strip()
    if value.lower().endswith(".git"):
        return value[:-4]
    return value


def _build_base_url(scheme: str, netloc: str) -> str:
    return f"{scheme}://{netloc}"


def detect_provider_from_url(url: str) -> str | None:
    parsed = parse_repo_url(url)
    return parsed.provider


def parse_scp_git_url(url: str) -> ParsedRepo | None:
    match = SCP_GIT_PATTERN.match(url.strip())
    if not match:
        return None
    host = match.group(1)
    path = _strip_git_suffix(match.group("path").strip("/"))
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return None
    repo_path = "/".join(parts)
    base_url = f"https://{host}"
    return ParsedRepo(
        provider="gitlab",
        repo_path=repo_path,
        branch=None,
        base_url=base_url,
        web_url=f"{base_url}/{repo_path}",
    )


def parse_ssh_git_url(url: str) -> ParsedRepo | None:
    raw = url.strip()
    if not raw.startswith("ssh://"):
        return None
    parsed = urlparse(raw)
    path = _strip_git_suffix(parsed.path.strip("/"))
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return None
    repo_path = "/".join(parts)
    host = parsed.hostname or parsed.netloc
    if not host:
        return None
    port = f":{parsed.port}" if parsed.port else ""
    base_url = f"https://{host}{port}"
    return ParsedRepo(
        provider="gitlab",
        repo_path=repo_path,
        branch=None,
        base_url=base_url,
        web_url=f"{base_url}/{repo_path}",
    )


def _extract_branch_from_gitlab_rest(rest: list[str]) -> str | None:
    if len(rest) < 2:
        return None
    kind = rest[0]
    if kind in {"tree", "blob", "commits"}:
        branch = unquote("/".join(rest[1:]))
        return branch or None
    if kind == "tags":
        tag = unquote("/".join(rest[1:]))
        return tag or None
    return None


def parse_gitlab_http_url(url: str) -> ParsedRepo | None:
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() in GITHUB_HOSTS:
        return None

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None

    branch = None
    repo_parts = parts
    if "-" in parts:
        dash_idx = parts.index("-")
        repo_parts = parts[:dash_idx]
        branch = _extract_branch_from_gitlab_rest(parts[dash_idx + 1 :])

    if repo_parts:
        repo_parts = list(repo_parts)
        repo_parts[-1] = _strip_git_suffix(repo_parts[-1])

    if len(repo_parts) < 2:
        return None

    repo_path = "/".join(repo_parts)
    base_url = _build_base_url(parsed.scheme, parsed.netloc)
    return ParsedRepo(
        provider="gitlab",
        repo_path=repo_path,
        branch=branch,
        base_url=base_url,
        web_url=f"{base_url}/{repo_path}",
    )


def parse_github_http_url(url: str) -> ParsedRepo | None:
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None
    if parsed.netloc.lower() not in GITHUB_HOSTS:
        return None
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None

    branch = None
    repo_parts = parts[:2]
    repo_parts[1] = _strip_git_suffix(repo_parts[1])
    if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        branch = unquote("/".join(parts[3:])) or None

    repo_path = f"{repo_parts[0]}/{repo_parts[1]}"
    base_url = _build_base_url(parsed.scheme, parsed.netloc)
    return ParsedRepo(
        provider="github",
        repo_path=repo_path,
        branch=branch,
        base_url=base_url,
        web_url=f"{base_url}/{repo_path}",
    )


def parse_repo_url(url: str) -> ParsedRepo:
    raw = (url or "").strip()
    if not raw:
        return ParsedRepo()

    for parser in (parse_scp_git_url, parse_ssh_git_url):
        parsed = parser(raw)
        if parsed:
            return parsed

    if raw.startswith("http://") or raw.startswith("https://"):
        host = urlparse(raw).netloc.lower()
        if host in GITHUB_HOSTS:
            return parse_github_http_url(raw) or ParsedRepo()
        return parse_gitlab_http_url(raw) or ParsedRepo()

    return ParsedRepo()


def _clone_scheme_for_host(host: str) -> str:
    base = get_gitlab_base_url().strip()
    if base:
        parsed = urlparse(base)
        if parsed.hostname and parsed.hostname.lower() == host.lower():
            return parsed.scheme or "https"
    return "https"


def _embed_gitlab_token_in_url(url: str, token: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return url
    if parsed.username or "@" in (parsed.netloc or ""):
        return url
    encoded = urllib.parse.quote(token, safe="")
    netloc = f"oauth2:{encoded}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


def git_ssh_url_to_https(clone_url: str) -> str | None:
    raw = (clone_url or "").strip()
    if not raw:
        return None

    scp = parse_scp_git_url(raw)
    if scp and scp.repo_path:
        match = SCP_GIT_PATTERN.match(raw)
        host = match.group(1) if match else ""
        if host:
            scheme = _clone_scheme_for_host(host)
            return f"{scheme}://{host}/{scp.repo_path}.git"

    if raw.startswith("ssh://"):
        ssh = parse_ssh_git_url(raw)
        if ssh and ssh.repo_path:
            parsed = urlparse(raw)
            host = parsed.hostname or ""
            if not host:
                return None
            port = f":{parsed.port}" if parsed.port else ""
            scheme = _clone_scheme_for_host(host)
            return f"{scheme}://{host}{port}/{ssh.repo_path}.git"

    return None


def _strip_url_credentials(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return url
    netloc = parsed.hostname
    if parsed.port:
        netloc += f":{parsed.port}"
    return urllib.parse.urlunparse(parsed._replace(netloc=netloc))


def git_auth_config_args() -> list[str]:
    token = get_gitlab_token()
    if not token:
        return []
    return ["-c", f"http.extraHeader=PRIVATE-TOKEN: {token}"]


def _humanize_gitlab_access_error(status_code: int, body: str) -> str:
    text = body.strip()
    if not text:
        if status_code == 404:
            return "GitLab 仓库不存在或无访问权限，请检查 Clone 地址与 Token"
        if status_code in {401, 403}:
            return "GitLab Token 无效或权限不足，请在「仓库访问配置」中更新 Token"
        if status_code >= 500:
            return f"GitLab 服务异常（HTTP {status_code}），请稍后重试或联系 GitLab 管理员"
        return f"GitLab 访问失败（HTTP {status_code}）"

    token = get_gitlab_token()
    if token:
        text = text.replace(token, "****")

    lowered = text.lower()
    if status_code >= 500:
        return (
            f"GitLab 接口异常（HTTP {status_code}）：{text[:300]}。"
            "若 HTTP 不可用，可在「仓库访问配置」中填写 GitLab SSH 私钥（Deploy Key）后重试。"
        )
    return text[:240]


def verify_gitlab_repo_access(clone_url: str) -> None:
    normalized = normalize_git_clone_url(clone_url)
    parsed = parse_repo_url(normalized) or parse_scp_git_url(clone_url)
    if not parsed or not parsed.repo_path:
        return

    token = get_gitlab_token()
    if not token:
        return

    encoded = urllib.parse.quote(parsed.repo_path, safe="")
    base = get_gitlab_base_url().rstrip("/")
    url = f"{base}/api/v4/projects/{encoded}"
    try:
        response = httpx.get(
            url,
            headers={"PRIVATE-TOKEN": token, "User-Agent": "QuickNavigation/1.0"},
            timeout=20.0,
            trust_env=False,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"无法连接 GitLab：{exc}") from exc

    if response.status_code == 200:
        return
    raise RuntimeError(_humanize_gitlab_access_error(response.status_code, response.text))


def prepare_git_clone_url(clone_url: str) -> str:
    """Normalize clone URL and embed GitLab Token for git HTTP operations."""
    normalized = normalize_git_clone_url(clone_url)
    if not normalized:
        return normalized
    token = get_gitlab_token()
    if token and normalized.startswith(("http://", "https://")):
        return _embed_gitlab_token_in_url(normalized, token)
    return normalized


def normalize_git_clone_url(clone_url: str) -> str:
    """将 git@ / ssh:// / https:// 等 Clone 地址统一为 git 可拉取的 URL（不在 URL 内嵌 Token）。"""
    raw = (clone_url or "").strip().rstrip("/")
    if not raw:
        return raw

    if raw.startswith("http://") or raw.startswith("https://"):
        return _strip_url_credentials(raw).rstrip("/")

    https_url = git_ssh_url_to_https(raw)
    if https_url:
        return https_url.rstrip("/")

    return raw


def is_ssh_style_clone_url(clone_url: str) -> bool:
    raw = (clone_url or "").strip()
    return bool(SCP_GIT_PATTERN.match(raw) or raw.startswith("ssh://"))


def describe_clone_url_format(clone_url: str) -> str:
    raw = (clone_url or "").strip()
    if not raw:
        return "empty"
    if raw.startswith("http://") or raw.startswith("https://"):
        return "https"
    if is_ssh_style_clone_url(raw):
        return "ssh"
    return "other"


def has_gitlab_tree_branch(url: str) -> bool:
    return "/-/tree/" in unquote((url or "").strip()).lower()


def parse_gitlab_tree_branch(url: str) -> ParsedRepo | None:
    if not has_gitlab_tree_branch(url):
        return None
    parsed = parse_repo_url(url)
    if not parsed.branch or not parsed.repo_path:
        return None
    return parsed


def normalize_repo_path(repo: str | None) -> str | None:
    if not repo:
        return None
    value = repo.strip().strip("/")
    value = _strip_git_suffix(value)
    return value.lower()


def repos_match(expected: str | None, actual: str | None) -> bool:
    left = normalize_repo_path(expected)
    right = normalize_repo_path(actual)
    if not left or not right:
        return False
    return left == right


def subscription_repo(sub) -> str | None:
    if sub.github_repo:
        return sub.github_repo
    if sub.connection:
        return parse_repo_url(sub.connection.url).repo_path
    return None


def subscription_repo_candidates(sub) -> list[str]:
    candidates: list[str] = []
    if sub.github_repo:
        candidates.append(sub.github_repo)
    if sub.connection:
        repo = parse_repo_url(sub.connection.url).repo_path
        if repo:
            candidates.append(repo)
    seen: set[str] = set()
    ordered: list[str] = []
    for repo in candidates:
        key = normalize_repo_path(repo)
        if key and key not in seen:
            seen.add(key)
            ordered.append(repo)
    return ordered


def subscription_provider(sub) -> str | None:
    if sub.connection:
        return parse_repo_url(sub.connection.url).provider
    return None


def subscription_branch(sub) -> str | None:
    if sub.github_branch:
        return sub.github_branch
    if sub.connection:
        return parse_repo_url(sub.connection.url).branch
    return None


def push_branch(payload: dict[str, Any]) -> str:
    ref = payload.get("ref") or ""
    if ref.startswith("refs/heads/"):
        return ref[len("refs/heads/") :]
    return ref.split("/")[-1] if ref else "unknown"


def gitlab_repo_path(payload: dict[str, Any]) -> str | None:
    project = payload.get("project") or {}
    return project.get("path_with_namespace")


@dataclass(frozen=True)
class CommitDiffResult:
    diff: str
    error: str | None = None


def build_gitlab_clone_url(repo_path: str) -> str:
    base = get_gitlab_base_url().rstrip("/")
    path = repo_path.strip("/")
    return f"{base}/{path}.git"


def build_gitlab_ssh_clone_url(repo_path: str) -> str:
    parsed = urlparse(get_gitlab_base_url())
    host = parsed.hostname or parsed.netloc.split(":")[0]
    if not host:
        host = "gitlab.local"
    path = repo_path.strip("/")
    return f"git@{host}:{path}.git"


def git_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    ssh_command = get_gitlab_ssh_command()
    if ssh_command:
        env["GIT_SSH_COMMAND"] = ssh_command
    return env


def _subscription_cache_dirs(subscription_id: int) -> list[Path]:
    base = Path(settings.api_repo_cache_dir)
    if not base.is_dir():
        return []
    prefix = f"{subscription_id}_"
    return sorted(
        item
        for item in base.iterdir()
        if item.is_dir() and (item.name.startswith(prefix) or item.name == str(subscription_id))
    )


def _try_git_show_in_cache(cache_dir: Path, sha: str) -> CommitDiffResult | None:
    if not (cache_dir / ".git").exists():
        return None
    config_args = git_auth_config_args()
    fetch = subprocess.run(
        ["git", *config_args, "fetch", "--depth", "1", "origin", sha],
        cwd=str(cache_dir),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=git_subprocess_env(),
    )
    if fetch.returncode != 0:
        return None
    show = subprocess.run(
        ["git", "show", sha, "-p", "--format="],
        cwd=str(cache_dir),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=git_subprocess_env(),
    )
    if show.returncode != 0 or not show.stdout.strip():
        return None
    return CommitDiffResult(show.stdout, None)


def _fetch_gitlab_diff_via_git_sync(
    clone_url: str,
    sha: str,
    branch: str | None,
    *,
    subscription_id: int | None = None,
) -> CommitDiffResult:
    if subscription_id is not None:
        for cache_dir in _subscription_cache_dirs(subscription_id):
            cached = _try_git_show_in_cache(cache_dir, sha)
            if cached is not None:
                return cached

    effective = clone_url.strip()
    if not (get_gitlab_ssh_command() and is_ssh_style_clone_url(effective)):
        effective = prepare_git_clone_url(clone_url)
    config_args = git_auth_config_args()

    def git_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *config_args, *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=git_subprocess_env(),
        )

    with tempfile.TemporaryDirectory(prefix="qn-diff-") as tmp:
        cwd = Path(tmp)
        git_run(["init"], cwd)
        git_run(["remote", "add", "origin", effective], cwd)
        fetch = git_run(["fetch", "--depth", "1", "origin", sha], cwd)
        if fetch.returncode != 0 and branch:
            fetch = git_run(["fetch", "--depth", "50", "origin", branch], cwd)
        if fetch.returncode != 0:
            detail = (fetch.stderr or fetch.stdout or "git fetch 失败").strip()
            if "returned error: 500" in detail.lower():
                return CommitDiffResult("", _humanize_gitlab_access_error(500, detail))
            return CommitDiffResult("", f"Git 拉取提交失败：{detail[:240]}")
        show = git_run(["show", sha, "-p", "--format="], cwd)
        if show.returncode != 0:
            detail = (show.stderr or show.stdout or "git show 失败").strip()
            return CommitDiffResult("", detail[:240])
        return CommitDiffResult(show.stdout, None)


async def fetch_commit_diff(
    provider: str,
    repo: str,
    sha: str,
    *,
    clone_url: str | None = None,
    branch: str | None = None,
    subscription_id: int | None = None,
) -> CommitDiffResult:
    if provider == "gitlab":
        use_ssh = bool(get_gitlab_ssh_command())
        resolved_clone = clone_url or (build_gitlab_clone_url(repo) if repo else None)
        if use_ssh and repo:
            if not resolved_clone or not is_ssh_style_clone_url(resolved_clone):
                resolved_clone = build_gitlab_ssh_clone_url(repo)

        async def _git_fetch() -> CommitDiffResult | None:
            if not resolved_clone:
                return None
            return await asyncio.to_thread(
                _fetch_gitlab_diff_via_git_sync,
                resolved_clone,
                sha,
                branch,
                subscription_id=subscription_id,
            )

        if use_ssh:
            git_result = await _git_fetch()
            if git_result and git_result.diff:
                return git_result
            api_result = await _fetch_gitlab_diff(repo, sha)
            if api_result.diff:
                return api_result
            if git_result is not None:
                return CommitDiffResult("", git_result.error or api_result.error)
            return api_result

        api_result = await _fetch_gitlab_diff(repo, sha)
        if api_result.diff:
            return api_result
        git_result = await _git_fetch()
        if git_result and git_result.diff:
            return git_result
        if git_result is not None:
            return CommitDiffResult("", api_result.error or git_result.error)
        return api_result
    diff = await _fetch_github_diff(repo, sha)
    if diff:
        return CommitDiffResult(diff, None)
    return CommitDiffResult("", "GitHub 未返回 diff 内容")


async def fetch_commit_time(provider: str, repo: str, sha: str) -> str | None:
    if provider == "gitlab":
        return await _fetch_gitlab_commit_time(repo, sha)
    if provider == "github":
        return await _fetch_github_commit_time(repo, sha)
    return None


def fetch_commit_time_sync(provider: str, repo: str, sha: str) -> str | None:
    """同步版本的 fetch_commit_time，供 def 路由在线程池内调用，避免阻塞事件循环。"""
    if provider == "gitlab":
        return _fetch_gitlab_commit_time_sync(repo, sha)
    if provider == "github":
        return _fetch_github_commit_time_sync(repo, sha)
    return None


async def _fetch_github_commit_time(repo: str, sha: str) -> str | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "QuickNavigation/1.0",
    }
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{repo}/commits/{sha}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, trust_env=False) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return None
            data = response.json()
            commit = data.get("commit") if isinstance(data, dict) else None
            if not isinstance(commit, dict):
                return None
            committer = commit.get("committer")
            if isinstance(committer, dict):
                ts = committer.get("date")
                if isinstance(ts, str) and ts.strip():
                    return ts.strip()
            author = commit.get("author")
            if isinstance(author, dict):
                ts = author.get("date")
                if isinstance(ts, str) and ts.strip():
                    return ts.strip()
    except httpx.HTTPError:
        logger.exception("GitHub commit time fetch failed for %s@%s", repo, sha)
    return None


def _fetch_github_commit_time_sync(repo: str, sha: str) -> str | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "QuickNavigation/1.0",
    }
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{repo}/commits/{sha}"
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, trust_env=False) as client:
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                return None
            data = response.json()
            commit = data.get("commit") if isinstance(data, dict) else None
            if not isinstance(commit, dict):
                return None
            committer = commit.get("committer")
            if isinstance(committer, dict):
                ts = committer.get("date")
                if isinstance(ts, str) and ts.strip():
                    return ts.strip()
            author = commit.get("author")
            if isinstance(author, dict):
                ts = author.get("date")
                if isinstance(ts, str) and ts.strip():
                    return ts.strip()
    except httpx.HTTPError:
        logger.exception("GitHub commit time fetch failed for %s@%s", repo, sha)
    return None


async def _fetch_gitlab_commit_time(project_path: str, sha: str) -> str | None:
    encoded = urllib.parse.quote(project_path, safe="")
    base = get_gitlab_base_url().rstrip("/")
    url = f"{base}/api/v4/projects/{encoded}/repository/commits/{sha}"
    headers = {"User-Agent": "QuickNavigation/1.0"}
    token = get_gitlab_token()
    if token:
        headers["PRIVATE-TOKEN"] = token
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, trust_env=False) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return None
            data = response.json()
            if not isinstance(data, dict):
                return None
            for key in ("committed_date", "authored_date", "created_at"):
                ts = data.get(key)
                if isinstance(ts, str) and ts.strip():
                    return ts.strip()
    except httpx.HTTPError:
        logger.exception("GitLab commit time fetch failed for %s@%s", project_path, sha)
    return None


def _fetch_gitlab_commit_time_sync(project_path: str, sha: str) -> str | None:
    encoded = urllib.parse.quote(project_path, safe="")
    base = get_gitlab_base_url().rstrip("/")
    url = f"{base}/api/v4/projects/{encoded}/repository/commits/{sha}"
    headers = {"User-Agent": "QuickNavigation/1.0"}
    token = get_gitlab_token()
    if token:
        headers["PRIVATE-TOKEN"] = token
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, trust_env=False) as client:
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                return None
            data = response.json()
            if not isinstance(data, dict):
                return None
            for key in ("committed_date", "authored_date", "created_at"):
                ts = data.get(key)
                if isinstance(ts, str) and ts.strip():
                    return ts.strip()
    except httpx.HTTPError:
        logger.exception("GitLab commit time fetch failed for %s@%s", project_path, sha)
    return None


async def _fetch_github_diff(repo: str, sha: str) -> str:
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "QuickNavigation/1.0",
    }
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{repo}/commits/{sha}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, trust_env=False) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return response.text
    except httpx.HTTPError:
        logger.exception("GitHub diff fetch failed for %s@%s", repo, sha)
    return ""


async def _fetch_gitlab_diff(project_path: str, sha: str) -> CommitDiffResult:
    encoded = urllib.parse.quote(project_path, safe="")
    base = get_gitlab_base_url().rstrip("/")
    url = f"{base}/api/v4/projects/{encoded}/repository/commits/{sha}/diff"
    headers = {"User-Agent": "QuickNavigation/1.0"}
    token = get_gitlab_token()
    if token:
        headers["PRIVATE-TOKEN"] = token
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, trust_env=False) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.warning(
                    "GitLab diff API failed for %s@%s: HTTP %s %s",
                    project_path,
                    sha,
                    response.status_code,
                    response.text[:200],
                )
                return CommitDiffResult(
                    "",
                    _humanize_gitlab_access_error(response.status_code, response.text),
                )
            chunks = response.json()
            if not isinstance(chunks, list):
                return CommitDiffResult("", "GitLab diff 响应格式无效")
            parts: list[str] = []
            for item in chunks:
                old_path = item.get("old_path") or item.get("new_path") or "file"
                new_path = item.get("new_path") or old_path
                parts.append(f"diff --git a/{old_path} b/{new_path}")
                parts.append(item.get("diff") or "")
            diff = "\n".join(parts).strip()
            if not diff:
                return CommitDiffResult("", "GitLab 未返回 diff 内容")
            return CommitDiffResult(diff, None)
    except httpx.HTTPError as exc:
        logger.exception("GitLab diff fetch failed for %s@%s", project_path, sha)
        return CommitDiffResult("", f"无法连接 GitLab：{exc}")


def short_sha(sha: str | None) -> str:
    if not sha:
        return ""
    return sha[:7] if len(sha) >= 7 else sha


def extract_commit_sha(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    sha = payload.get("commit_sha")
    if isinstance(sha, str) and sha:
        return sha
    return None


def _find_sub_link_clone_url(conn, repo_path: str) -> str | None:
    repo_path = repo_path.strip().lower()
    repo_name = repo_path.rsplit("/", 1)[-1]
    for item in conn.sub_links or []:
        if not isinstance(item, dict):
            continue
        clone_url = str(item.get("clone_url") or "").strip()
        url = str(item.get("url") or "").strip().lower()
        if clone_url and repo_path in clone_url.lower():
            return clone_url
        if clone_url and repo_name and repo_name in url:
            return clone_url
    return None


def _resolve_log_clone_url(db, log, repo: str, provider: str) -> str | None:
    if provider != "gitlab":
        return None
    payload = dict(log.payload or {})
    clone_url = str(payload.get("clone_url") or "").strip()
    if clone_url:
        return clone_url
    from app.models import Connection

    if log.connection_id:
        conn = db.query(Connection).filter(Connection.id == log.connection_id).first()
        if conn:
            if str(conn.host or "").strip():
                return str(conn.host).strip()
            matched = _find_sub_link_clone_url(conn, str(repo))
            if matched:
                return matched
    if repo:
        if get_gitlab_ssh_command():
            return build_gitlab_ssh_clone_url(repo)
        return build_gitlab_clone_url(repo)
    return None


_BACKGROUND_DIFF_SEMAPHORE: asyncio.Semaphore | None = None
_BACKGROUND_DIFF_CONCURRENCY = 4


def _get_diff_semaphore() -> asyncio.Semaphore:
    global _BACKGROUND_DIFF_SEMAPHORE
    if _BACKGROUND_DIFF_SEMAPHORE is None:
        _BACKGROUND_DIFF_SEMAPHORE = asyncio.Semaphore(_BACKGROUND_DIFF_CONCURRENCY)
    return _BACKGROUND_DIFF_SEMAPHORE


async def fetch_log_diff_background(log_id: int, provider: str, repo: str, sha: str) -> None:
    from app.models import ActivityLog
    from app.schemas import ActivityLogOut
    from app.websocket_manager import ws_manager

    async with _get_diff_semaphore():
        try:
            db = SessionLocal()
            try:
                log = db.query(ActivityLog).filter(ActivityLog.id == log_id).first()
                if not log:
                    return
                payload = dict(log.payload or {})
                clone_url = _resolve_log_clone_url(db, log, str(repo), provider)
                branch = str(payload.get("branch") or "").strip() or None
                result = await fetch_commit_diff(
                    provider,
                    repo,
                    sha,
                    clone_url=clone_url,
                    branch=branch,
                    subscription_id=log.subscription_id,
                )
                if not result.diff:
                    return
                payload["diff"] = result.diff
                payload.pop("diff_error", None)
                log.payload = payload
                flag_modified(log, "payload")
                db.commit()
                db.refresh(log)
                data = ActivityLogOut.model_validate(log).model_dump(mode="json")
                await ws_manager.broadcast({"type": "log:new", "data": data})
            finally:
                db.close()
        except Exception:
            logger.exception("Background diff fetch failed for log %s", log_id)


def schedule_log_diff(log_id: int, provider: str, repo: str, sha: str) -> None:
    asyncio.create_task(fetch_log_diff_background(log_id, provider, repo, sha))
