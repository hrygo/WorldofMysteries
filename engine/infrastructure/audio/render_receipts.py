"""Bounded reader for the SpeechRail render receipt.

The Realtime success terminal carries only ``task_id``, ``request_id`` and
``generated_samples``.  The render evidence lives behind a REST endpoint and
is completed by the service *before* the terminal is emitted, so one read is
normally enough; this reader adds a single bounded retry for transient
transport or 5xx failures and never retries a semantic rejection.

The receipt is metadata only.  It proves what the service handed to the
transport, not what a speaker played; the DeliveryCursor evidence levels stay
independent of it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import AudioProviderConfig

MAX_RECEIPT_BYTES = 256 * 1024
RECEIPT_PHASE_BUDGET_SECONDS = 3.0
_RETRY_STATUS = frozenset({500, 502, 503, 504})


class RenderReceiptError(RuntimeError):
    """The render receipt could not be read or proved the delivered audio."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@runtime_checkable
class RenderReceiptReader(Protocol):
    """Read one receipt by the public request id the caller submitted."""

    async def read_by_request(self, request_id: str) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class _HttpResult:
    status_code: int
    payload: object


class _NoRedirect(HTTPRedirectHandler):
    """A redirect could move the receipt read across a trust boundary."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        del req, fp, code, msg, headers, newurl
        return None


def receipt_url(base_url: str, request_id: str) -> str:
    """Build the by-request receipt URL from the configured base URL."""
    parts = urlsplit(base_url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise RenderReceiptError("render_receipt_invalid_configuration")
    path = parts.path.rstrip("/")
    if not path.endswith("/v1"):
        raise RenderReceiptError("render_receipt_invalid_configuration")
    if not request_id or len(request_id) > 200:
        raise RenderReceiptError("render_receipt_invalid_request")
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        f"{path}/speechrail/audio/receipts/by-request/{quote(request_id, safe='')}",
        "",
        "",
    ))


def _decode(payload: bytes) -> object:
    if not payload:
        return {}
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RenderReceiptError("render_receipt_invalid_json") from exc


def _status_code(error: HTTPError) -> int:
    return int(error.code)


def _classify(status_code: int) -> str:
    if status_code == 401:
        return "render_receipt_unauthorized"
    if status_code == 403:
        return "render_receipt_forbidden"
    if status_code == 404:
        # The service completed the receipt before the terminal, so a miss here
        # is eviction or a restart, never a "try again later" signal.
        return "render_receipt_missing"
    if status_code == 429:
        return "render_receipt_busy"
    if status_code in _RETRY_STATUS:
        return "render_receipt_transient"
    return f"render_receipt_http_{status_code}"


def _sync_get(
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str],
    max_bytes: int,
) -> _HttpResult:
    opener = build_opener(_NoRedirect)
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "WorldOfMysteries-RenderReceipt/1",
            **dict(headers),
        },
        method="GET",
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise RenderReceiptError("render_receipt_too_large")
            return _HttpResult(status_code=int(response.status), payload=_decode(body))
    except HTTPError as exc:
        body = exc.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise RenderReceiptError("render_receipt_too_large") from exc
        status_code = _status_code(exc)
        if status_code == 304:
            raise RenderReceiptError("render_receipt_not_modified") from exc
        return _HttpResult(status_code=status_code, payload=_decode(body))
    except (URLError, TimeoutError, OSError) as exc:
        raise RenderReceiptError("render_receipt_transient") from exc


ReceiptFetcher = Callable[[str, float, Mapping[str, str], int], Awaitable[_HttpResult]]


class HttpRenderReceiptReader:
    """Read render receipts over the same authenticated base URL as the wire."""

    def __init__(
        self,
        config: AudioProviderConfig,
        *,
        fetch: ReceiptFetcher | None = None,
        max_bytes: int = MAX_RECEIPT_BYTES,
        attempts: int = 2,
    ) -> None:
        if max_bytes < 1 or attempts < 1:
            raise ValueError("invalid render receipt reader limits")
        self._config = config
        self._max_bytes = max_bytes
        self._attempts = attempts
        self._fetch = fetch or self._default_fetch

    async def _default_fetch(
        self,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str],
        max_bytes: int,
    ) -> _HttpResult:
        return await asyncio.to_thread(
            _sync_get, url, timeout_seconds, headers, max_bytes
        )

    async def read_by_request(self, request_id: str) -> Mapping[str, object]:
        url = receipt_url(self._config.base_url, request_id)
        headers: dict[str, str] = {}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        per_attempt = min(
            self._config.timeout_seconds, RECEIPT_PHASE_BUDGET_SECONDS
        )
        last: RenderReceiptError | None = None
        for _ in range(self._attempts):
            try:
                result = await self._fetch(url, per_attempt, headers, self._max_bytes)
            except RenderReceiptError as exc:
                last = exc
                # Only a transport-level failure is worth one more attempt; a
                # semantic rejection must fail immediately.
                if exc.code != "render_receipt_transient":
                    raise
                continue
            if result.status_code != 200:
                code = _classify(result.status_code)
                if code == "render_receipt_transient":
                    last = RenderReceiptError(code)
                    continue
                raise RenderReceiptError(code)
            if not isinstance(result.payload, Mapping):
                raise RenderReceiptError("render_receipt_invalid")
            return dict(result.payload)
        raise last or RenderReceiptError("render_receipt_transient")


def create_render_receipt_reader(
    config: AudioProviderConfig,
) -> RenderReceiptReader:
    """Factory for the default authenticated REST receipt reader."""
    return HttpRenderReceiptReader(config)
