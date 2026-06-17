import asyncio
from urllib.parse import urlparse

import httpx

PING_TIMEOUT = 8.0
PING_CONCURRENCY = 8


def is_valid_ping_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        return False
    return True


async def _request_reachable(client: httpx.AsyncClient, url: str) -> bool:
    headers = {"User-Agent": "QuickNavigation-Ping/1.0"}
    for method in ("HEAD", "GET"):
        try:
            response = await client.request(method, url, headers=headers)
            if response.status_code < 500:
                return True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                return True
        except httpx.RequestError:
            continue
    return False


async def check_url_reachable(url: str) -> bool:
    if not is_valid_ping_url(url):
        return False

    async with httpx.AsyncClient(
        timeout=PING_TIMEOUT,
        follow_redirects=True,
        verify=False,
        limits=httpx.Limits(max_connections=PING_CONCURRENCY, max_keepalive_connections=4),
    ) as client:
        return await _request_reachable(client, url.strip())


async def ping_urls(urls: list[str]) -> list[bool]:
    normalized = [(url or "").strip() for url in urls]
    results: list[bool] = [False] * len(normalized)
    unique_valid: list[str] = []
    index_by_url: dict[str, list[int]] = {}

    for index, url in enumerate(normalized):
        if not is_valid_ping_url(url):
            continue
        index_by_url.setdefault(url, []).append(index)
        if url not in unique_valid:
            unique_valid.append(url)

    if not unique_valid:
        return results

    semaphore = asyncio.Semaphore(PING_CONCURRENCY)
    async with httpx.AsyncClient(
        timeout=PING_TIMEOUT,
        follow_redirects=True,
        verify=False,
        limits=httpx.Limits(max_connections=PING_CONCURRENCY, max_keepalive_connections=4),
    ) as client:

        async def run(url: str) -> tuple[str, bool]:
            async with semaphore:
                return url, await _request_reachable(client, url)

        ping_results = await asyncio.gather(*(run(url) for url in unique_valid), return_exceptions=True)
        for item in ping_results:
            if isinstance(item, Exception):
                continue
            url, reachable = item
            for index in index_by_url.get(url, []):
                results[index] = reachable

    return results
