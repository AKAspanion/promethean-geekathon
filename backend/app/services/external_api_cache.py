"""
Simple in-memory cache for external API requests (e.g. news, weather).
Same URL returns cached result for 1 hour, and logs requests/responses
to the database for observability.
"""

import asyncio
import logging
import time
from typing import Any
from urllib.parse import urlencode

import anyio
import httpx

from app.database import SessionLocal
from app.models.external_api_log import ExternalApiLog

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 600  # 10 minutes

# key -> (expiry_ts, status_code, body)
_cache: dict[str, tuple[float, int, dict | list]] = {}
_lock = asyncio.Lock()


def _make_cache_key(url: str, params: dict | None) -> str:
    """Build a deterministic cache key from URL and query params."""
    if not params:
        return url
    # Sort keys so same params in different order yield same key
    encoded = urlencode(sorted(params.items()), doseq=True)
    return f"{url}?{encoded}"


class _CachedResponse:
    """Minimal response-like object for cached data."""

    def __init__(self, status_code: int, data: dict | list):
        self.status_code = status_code
        self._data = data

    def json(self) -> dict | list:
        return self._data


async def _log_external_api_call(
    *,
    service: str | None,
    method: str,
    url: str,
    params: dict | None,
    status_code: int | None,
    from_cache: bool,
    elapsed_ms: int | None,
    request_headers: dict | None,
    response_body: dict | list | None,
    error_message: str | None,
) -> None:
    """Persist a single external API call (or cache hit) to the database."""

    def _sync_log() -> None:
        db = SessionLocal()
        try:
            log = ExternalApiLog(
                service=service,
                method=method,
                url=url,
                params=params,
                statusCode=status_code,
                fromCache=from_cache,
                elapsedMs=elapsed_ms,
                requestHeaders=request_headers,
                responseBody=response_body,
                errorMessage=error_message,
            )
            db.add(log)
            db.commit()
        except Exception:
            logger.exception("Failed to log external API call")
            db.rollback()
        finally:
            db.close()

    try:
        await anyio.to_thread.run_sync(_sync_log)
    except Exception:
        # Never break the main flow because of logging issues
        logger.exception("Failed to schedule external API log")


async def cached_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    service: str | None = None,
    **kwargs: Any,
) -> httpx.Response | _CachedResponse:
    """
    GET the URL with optional params; return cached result if the same URL
    was requested within the last hour, and log the request/response.
    """
    key = _make_cache_key(url, params)
    request_headers = kwargs.get("headers")
    if request_headers is not None and not isinstance(request_headers, dict):
        request_headers = None

    async with _lock:
        if key in _cache:
            expiry_ts, status_code, body = _cache[key]
            if time.monotonic() < expiry_ts:
                logger.debug("Cache hit for %s", key[:80])
                await _log_external_api_call(
                    service=service,
                    method="GET",
                    url=url,
                    params=params,
                    status_code=status_code,
                    from_cache=True,
                    elapsed_ms=None,
                    request_headers=request_headers,
                    response_body=body,
                    error_message=None,
                )
                return _CachedResponse(status_code, body)
            del _cache[key]

    # Cache miss: perform request
    start = time.monotonic()
    try:
        response = await client.get(url, params=params, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive logging
        elapsed_ms = int((time.monotonic() - start) * 1000)
        await _log_external_api_call(
            service=service,
            method="GET",
            url=url,
            params=params,
            status_code=None,
            from_cache=False,
            elapsed_ms=elapsed_ms,
            request_headers=request_headers,
            response_body=None,
            error_message=str(exc),
        )
        raise

    elapsed_ms = int((time.monotonic() - start) * 1000)

    try:
        body = response.json()
    except Exception:
        # Don't cache non-JSON responses, but still log them
        await _log_external_api_call(
            service=service,
            method="GET",
            url=url,
            params=params,
            status_code=response.status_code,
            from_cache=False,
            elapsed_ms=elapsed_ms,
            request_headers=request_headers,
            response_body=None,
            error_message=None,
        )
        return response

    # Only cache successful responses — never cache 4xx/5xx errors
    if response.status_code < 400:
        expiry_ts = time.monotonic() + CACHE_TTL_SECONDS
        async with _lock:
            _cache[key] = (expiry_ts, response.status_code, body)

    await _log_external_api_call(
        service=service,
        method="GET",
        url=url,
        params=params,
        status_code=response.status_code,
        from_cache=False,
        elapsed_ms=elapsed_ms,
        request_headers=request_headers,
        response_body=body,
        error_message=None,
    )

    return response
