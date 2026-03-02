import httpx
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import structlog

log = structlog.get_logger()


class BaseAPIClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
        )

    def _capture_quota_headers(self, response: httpx.Response) -> None:
        """Subclass override to capture provider-specific quota headers from responses.

        Default: no-op. Override in provider-specific clients to extract and store
        quota data (remaining calls, used calls, limits) in Redis with TTL.
        """
        pass

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=4),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _get(self, path: str, **kwargs) -> dict | list:
        response = await self._client.get(path, **kwargs)
        response.raise_for_status()
        self._capture_quota_headers(response)
        return response.json()

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=4),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _post(self, path: str, **kwargs) -> dict | list:
        response = await self._client.post(path, **kwargs)
        response.raise_for_status()
        self._capture_quota_headers(response)
        return response.json()

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
