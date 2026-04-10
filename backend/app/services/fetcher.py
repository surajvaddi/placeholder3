from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional, Union

import httpx

from .policy import PolicyRegistry


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    text: str = ""
    json_data: Optional[Union[Dict, list]] = None


class Fetcher:
    def __init__(
        self,
        policy_registry: PolicyRegistry,
        connector_name: str,
        timeout: Optional[httpx.Timeout] = None,
        retries: int = 2,
    ):
        self.policy_registry = policy_registry
        self.connector_name = connector_name
        self.timeout = timeout or httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=20.0)
        self.retries = retries
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_at: Dict[str, float] = {}
        self._request_counts: Dict[str, int] = {}

    async def __aenter__(self) -> "Fetcher":
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": "collegiate-prospecting/0.1"},
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_text(self, url: str, policy_tag: str) -> FetchResult:
        response = await self._request("GET", url, policy_tag)
        return FetchResult(
            url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            text=response.text,
        )

    async def get_json(self, url: str, policy_tag: str) -> FetchResult:
        response = await self._request("GET", url, policy_tag)
        return FetchResult(
            url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            json_data=response.json(),
            text=response.text,
        )

    async def head(self, url: str, policy_tag: str) -> FetchResult:
        response = await self._request("HEAD", url, policy_tag)
        return FetchResult(
            url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
        )

    async def _request(self, method: str, url: str, policy_tag: str) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("Fetcher must be used as an async context manager.")

        policy = self.policy_registry.resolve(url, self.connector_name, policy_tag)
        host = httpx.URL(url).host or ""
        count = self._request_counts.get(host, 0)
        if count >= policy.max_requests_per_run:
            raise RuntimeError(f"Request budget exceeded for host={host}.")
        await self._respect_rate_limit(host, policy.min_delay_seconds)

        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                response = await self._client.request(method, url)
                self._request_counts[host] = count + 1
                self._validate_content_type(response, policy)
                response.raise_for_status()
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.retries:
                    break
                await asyncio.sleep(0.25 * (2**attempt))
        assert last_error is not None
        raise last_error

    async def _respect_rate_limit(self, host: str, min_delay_seconds: float) -> None:
        if min_delay_seconds <= 0:
            return
        last_at = self._last_request_at.get(host)
        now = time.monotonic()
        if last_at is not None:
            sleep_for = min_delay_seconds - (now - last_at)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        self._last_request_at[host] = time.monotonic()

    def _validate_content_type(self, response: httpx.Response, policy) -> None:
        content_type = response.headers.get("content-type", "").lower()
        if "json" in content_type and not policy.allow_json:
            raise RuntimeError(f"JSON content not allowed by policy tag={policy.tag}.")
        if "html" in content_type and not policy.allow_html:
            raise RuntimeError(f"HTML content not allowed by policy tag={policy.tag}.")
