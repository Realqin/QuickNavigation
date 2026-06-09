import asyncio
from datetime import datetime
from urllib.parse import urlparse

import httpx

PING_TIMEOUT = 8.0
PING_CONCURRENCY = 10


async def check_url_reachable(url: str) -> bool:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return False

    headers = {"User-Agent": "QuickNavigation-Ping/1.0"}
    async with httpx.AsyncClient(
        timeout=PING_TIMEOUT,
        follow_redirects=True,
        verify=False,
    ) as client:
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


async def ping_urls(urls: list[str]) -> list[bool]:
    semaphore = asyncio.Semaphore(PING_CONCURRENCY)

    async def run(url: str) -> bool:
        async with semaphore:
            return await check_url_reachable(url)

    return await asyncio.gather(*(run(url) for url in urls))
