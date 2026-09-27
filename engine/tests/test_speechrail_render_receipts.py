"""Bounded render-receipt reader behaviour (T04).

The receipt is the only terminal evidence for a completed render, so the
reader must be strict about what it accepts and honest about what it
tolerates: one bounded retry for a transient transport or 5xx failure, and an
immediate failure for anything semantic.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from infrastructure.audio import (
    AudioProviderConfig,
    HttpRenderReceiptReader,
    RenderReceiptError,
    create_render_receipt_reader,
)
from infrastructure.audio import render_receipts as module
from infrastructure.audio.render_receipts import _NoRedirect, _sync_get, receipt_url

BASE_URL = "http://127.0.0.1:8201/v1"
REQUEST_ID = "wom-tts-abc123"


class _Result:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.payload = payload


def _config(api_key: str = "") -> AudioProviderConfig:
    return AudioProviderConfig(
        provider_name="speechrail",
        base_url=BASE_URL,
        api_key=api_key,
    )


def _reader(calls: list[Any], statuses: list[int], payload: object = None):
    """Build a reader whose fetch replays ``statuses`` then repeats the last."""

    return HttpRenderReceiptReader(_config(), fetch=_fetch(calls, statuses, payload))


def _fetch(calls: list[Any], statuses: list[int], payload: object = None):
    """A fetch stub that replays ``statuses`` and then repeats the last one."""

    async def fetch(url, timeout, headers, max_bytes):
        index = min(len(calls), len(statuses) - 1)
        calls.append((url, dict(headers), timeout, max_bytes))
        if isinstance(statuses[index], Exception):
            raise statuses[index]
        return _Result(statuses[index], payload if payload is not None else {})

    return fetch


def test_receipt_url_encodes_the_request_id_segment():
    url = receipt_url(BASE_URL, "wom tts/../x")
    assert url == (
        "http://127.0.0.1:8201/v1/speechrail/audio/receipts/"
        "by-request/wom%20tts%2F..%2Fx"
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:8201",
        "ftp://127.0.0.1:8201/v1",
        "http://user:pw@127.0.0.1:8201/v1",
        "http://127.0.0.1:8201/v1?x=1",
    ],
)
def test_receipt_url_rejects_ambiguous_configuration(base_url: str):
    with pytest.raises(RenderReceiptError, match="render_receipt_invalid_configuration"):
        receipt_url(base_url, REQUEST_ID)


@pytest.mark.parametrize("request_id", ["", "x" * 201])
def test_receipt_url_rejects_an_unusable_request_id(request_id: str):
    with pytest.raises(RenderReceiptError, match="render_receipt_invalid_request"):
        receipt_url(BASE_URL, request_id)


@pytest.mark.asyncio
async def test_reader_sends_bearer_only_when_a_key_is_configured():
    calls: list[Any] = []
    reader = _reader(calls, [200], {"status": "completed"})
    reader._config = _config("sr-key")  # noqa: SLF001 - wiring under test
    assert (await reader.read_by_request(REQUEST_ID))["status"] == "completed"
    assert calls[0][1]["Authorization"] == "Bearer sr-key"
    assert calls[0][0].endswith(f"by-request/{REQUEST_ID}")

    anonymous: list[Any] = []
    plain = _reader(anonymous, [200], {"status": "completed"})
    await plain.read_by_request(REQUEST_ID)
    assert "Authorization" not in anonymous[0][1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "render_receipt_unauthorized"),
        (403, "render_receipt_forbidden"),
        (404, "render_receipt_missing"),
        (429, "render_receipt_busy"),
        (418, "render_receipt_http_418"),
    ],
)
async def test_reader_fails_immediately_on_a_semantic_status(status_code, expected):
    calls: list[Any] = []
    reader = _reader(calls, [status_code])
    with pytest.raises(RenderReceiptError, match=expected):
        await reader.read_by_request(REQUEST_ID)
    assert len(calls) == 1, "a semantic rejection must not be retried"


@pytest.mark.asyncio
async def test_reader_retries_once_on_a_transient_5xx_then_succeeds():
    calls: list[Any] = []
    reader = _reader(calls, [503, 200], {"status": "completed"})
    assert (await reader.read_by_request(REQUEST_ID))["status"] == "completed"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_reader_gives_up_after_the_bounded_retry_budget():
    calls: list[Any] = []
    reader = HttpRenderReceiptReader(_config(), fetch=_fetch(calls, [500]))
    with pytest.raises(RenderReceiptError, match="render_receipt_transient"):
        await reader.read_by_request(REQUEST_ID)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_reader_retries_a_transport_failure_once():
    calls: list[Any] = []
    reader = _reader(
        calls, [RenderReceiptError("render_receipt_transient"), 200], {"status": "ok"}
    )
    assert (await reader.read_by_request(REQUEST_ID))["status"] == "ok"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_reader_does_not_retry_a_non_transient_reader_error():
    calls: list[Any] = []
    reader = _reader(calls, [RenderReceiptError("render_receipt_too_large")])
    with pytest.raises(RenderReceiptError, match="render_receipt_too_large"):
        await reader.read_by_request(REQUEST_ID)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_reader_rejects_a_non_object_payload():
    calls: list[Any] = []
    reader = _reader(calls, [200], [1, 2, 3])
    with pytest.raises(RenderReceiptError, match="render_receipt_invalid"):
        await reader.read_by_request(REQUEST_ID)


def test_sync_get_never_follows_a_redirect():
    assert _NoRedirect().redirect_request(None, None, 302, "", {}, "http://x") is None


def test_sync_get_rejects_an_oversized_body(monkeypatch):
    class _TooLarge:
        status = 200

        def read(self, size):
            return b"{" * (size + 1)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

    monkeypatch.setattr(
        module,
        "build_opener",
        lambda *a: type("_O", (), {"open": lambda self, *a, **k: _TooLarge()})(),
    )
    with pytest.raises(RenderReceiptError, match="render_receipt_too_large"):
        _sync_get("http://127.0.0.1:8201/v1/x", 1.0, {}, 16)


def test_sync_get_rejects_undecodable_json(monkeypatch):
    class _Body:
        status = 200

        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self, size):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

    monkeypatch.setattr(
        module,
        "build_opener",
        lambda *a: type("_O", (), {"open": lambda self, *a, **k: _Body(b"not json")})(),
    )
    with pytest.raises(RenderReceiptError, match="render_receipt_invalid_json"):
        _sync_get("http://127.0.0.1:8201/v1/x", 1.0, {}, 1024)


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, 401),
        (429, 429),
        # A redirect surfaces here as an HTTPError; it must be a semantic
        # failure, never a silent second hop across the trust boundary.
        (302, 302),
    ],
)
def test_sync_get_maps_an_http_error_to_a_status(monkeypatch, status_code, expected):
    from urllib.error import HTTPError

    def _raise(_self, request, timeout):
        raise HTTPError(request.full_url, status_code, "boom", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(
        module,
        "build_opener",
        lambda *a: type("_O", (), {"open": _raise})(),
    )
    result = _sync_get("http://127.0.0.1:8201/v1/x", 1.0, {}, 1024)
    assert result.status_code == expected
    assert result.payload == {}


def test_sync_get_rejects_a_not_modified_receipt(monkeypatch):
    from urllib.error import HTTPError

    def _raise(_self, request, timeout):
        raise HTTPError(request.full_url, 304, "cached", {}, io.BytesIO(b""))

    monkeypatch.setattr(
        module,
        "build_opener",
        lambda *a: type("_O", (), {"open": _raise})(),
    )
    with pytest.raises(RenderReceiptError, match="render_receipt_not_modified"):
        _sync_get("http://127.0.0.1:8201/v1/x", 1.0, {}, 1024)


def test_sync_get_reports_a_transport_failure_as_retryable(monkeypatch):
    from urllib.error import URLError

    def _raise(_self, request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(
        module,
        "build_opener",
        lambda *a: type("_O", (), {"open": _raise})(),
    )
    with pytest.raises(RenderReceiptError, match="render_receipt_transient"):
        _sync_get("http://127.0.0.1:8201/v1/x", 1.0, {}, 1024)


def test_default_factory_returns_the_http_reader():
    assert isinstance(create_render_receipt_reader(_config()), HttpRenderReceiptReader)


@pytest.mark.parametrize("kwargs", [{"attempts": 0}, {"max_bytes": 0}])
def test_reader_rejects_nonsensical_limits(kwargs):
    with pytest.raises(ValueError):
        HttpRenderReceiptReader(_config(), **kwargs)
