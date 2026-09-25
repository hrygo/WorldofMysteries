"""W-V07 authorization-aware AudioTake single-flight tests."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from infrastructure.audio_take_coordinator import (
    AudioTakeRenderCoordinator,
    AudioTakeRenderCoordinatorError,
    RenderedPCM,
)
from infrastructure.audio_take_store import (
    DryRenderRecipe,
    PublishedAudioTake,
    RenderOutcome,
)


def recipe(*, text_hash: str = "a" * 64) -> DryRenderRecipe:
    return DryRenderRecipe(
        provider_instance="speechrail-local",
        model_id="qwen3-tts-base",
        model_revision="b" * 40,
        voice_id="klein-approved",
        voice_revision="voice-" + "c" * 40,
        spoken_text_sha256=text_hash,
        pronunciation_revision="pron-v1",
        backend_fingerprint="d" * 64,
    )


def outcome() -> RenderOutcome:
    return RenderOutcome(
        provider_instance="speechrail-local",
        model_id="qwen3-tts-base",
        model_revision="b" * 40,
        voice_id="klein-approved",
        voice_revision="voice-" + "c" * 40,
        receipt_id="receipt-1",
    )


def take(render_key: str, *, replayed: bool = True) -> PublishedAudioTake:
    return PublishedAudioTake(
        take_id="take-1",
        render_key=render_key,
        relative_path="Takes/" + "e" * 64 + ".pcm",
        file_sha256="e" * 64,
        manifest={"render_key": render_key},
        manifest_hmac="f" * 64,
        replayed=replayed,
    )


class FakeStore:
    def __init__(self) -> None:
        self.cached: PublishedAudioTake | None = None
        self.load_calls = 0
        self.publish_calls = 0
        self.key = "1" * 64

    def render_key(self, value: DryRenderRecipe) -> str:
        assert isinstance(value, DryRenderRecipe)
        return self.key

    async def load(self, render_key: str):
        assert render_key == self.key
        self.load_calls += 1
        return self.cached

    async def publish_pcm(self, recipe, rendered_outcome, pcm16):
        assert recipe.canonical_json()
        assert rendered_outcome == outcome()
        assert pcm16 == b"\x01\x00\x02\x00"
        self.publish_calls += 1
        self.cached = take(self.key, replayed=False)
        return self.cached


def authorization_log(*, delivery_allowed: bool = True):
    calls = []

    async def check(stage):
        calls.append(stage)
        if stage == "before_delivery":
            return delivery_allowed
        return True

    return calls, check


async def test_cache_hit_checks_authorization_before_lookup_and_before_delivery():
    store = FakeStore()
    store.cached = take(store.key)
    coordinator = AudioTakeRenderCoordinator(store)
    calls, authorize = authorization_log()
    render_calls = 0

    async def render():
        nonlocal render_calls
        render_calls += 1
        return RenderedPCM(outcome(), b"\x01\x00\x02\x00")

    result = await coordinator.acquire(
        subscriber_id="turn-1:generation-1",
        recipe=recipe(),
        authorize=authorize,
        render=render,
    )

    assert result == store.cached
    assert calls == ["before_lookup", "before_delivery"]
    assert store.load_calls == 1
    assert render_calls == 0


async def test_revocation_after_cache_lookup_denies_delivery_without_render():
    store = FakeStore()
    store.cached = take(store.key)
    coordinator = AudioTakeRenderCoordinator(store)
    calls, authorize = authorization_log(delivery_allowed=False)

    with pytest.raises(AudioTakeRenderCoordinatorError, match="audio_take_not_authorized"):
        await coordinator.acquire(
            subscriber_id="turn-1:generation-2",
            recipe=recipe(),
            authorize=authorize,
            render=lambda: None,  # type: ignore[arg-type]
        )

    assert calls == ["before_lookup", "before_delivery"]
    assert store.load_calls == 1


async def test_same_key_shares_render_but_one_cancel_does_not_cancel_other_waiter():
    store = FakeStore()
    coordinator = AudioTakeRenderCoordinator(store)
    started = asyncio.Event()
    release = asyncio.Event()
    render_calls = 0
    render_cancelled = False

    async def render():
        nonlocal render_calls, render_cancelled
        render_calls += 1
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            render_cancelled = True
            raise
        return RenderedPCM(outcome(), b"\x01\x00\x02\x00")

    calls_a, auth_a = authorization_log()
    calls_b, auth_b = authorization_log()
    waiter_a = asyncio.create_task(
        coordinator.acquire(
            subscriber_id="turn-a:generation-1",
            recipe=recipe(),
            authorize=auth_a,
            render=render,
        )
    )
    await started.wait()
    waiter_b = asyncio.create_task(
        coordinator.acquire(
            subscriber_id="turn-b:generation-9",
            recipe=recipe(),
            authorize=auth_b,
            render=render,
        )
    )
    await asyncio.sleep(0)

    waiter_a.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_a
    assert not render_cancelled

    release.set()
    result_b = await waiter_b
    assert result_b.file_sha256 == "e" * 64
    assert render_calls == 1
    assert store.publish_calls == 1
    assert calls_a == ["before_lookup"]
    assert calls_b == ["before_lookup", "before_delivery"]
    assert await coordinator.snapshot() == {
        "active_flights": 0,
        "active_waiters": 0,
        "max_flights": 32,
        "max_waiters_per_flight": 16,
    }


async def test_last_waiter_cancellation_cancels_shared_provider_render():
    store = FakeStore()
    coordinator = AudioTakeRenderCoordinator(store)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def render():
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    _, authorize = authorization_log()
    waiter = asyncio.create_task(
        coordinator.acquire(
            subscriber_id="turn-only:generation-3",
            recipe=recipe(),
            authorize=authorize,
            render=render,  # type: ignore[arg-type]
        )
    )
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert (await coordinator.snapshot())["active_flights"] == 0


async def test_two_domain_subscribers_share_only_render_not_authorization():
    store = FakeStore()
    coordinator = AudioTakeRenderCoordinator(store)
    release = asyncio.Event()
    started = asyncio.Event()
    authorization = {"a": [], "b": []}

    async def render():
        started.set()
        await release.wait()
        return RenderedPCM(outcome(), b"\x01\x00\x02\x00")

    def check(name):
        async def authorize(stage):
            authorization[name].append(stage)
            return True
        return authorize

    one = asyncio.create_task(
        coordinator.acquire(
            subscriber_id="turn-a:generation-1",
            recipe=recipe(),
            authorize=check("a"),
            render=render,
        )
    )
    await started.wait()
    two = asyncio.create_task(
        coordinator.acquire(
            subscriber_id="turn-b:generation-4",
            recipe=recipe(),
            authorize=check("b"),
            render=render,
        )
    )
    await asyncio.sleep(0)
    release.set()
    assert (await one).render_key == store.key
    assert (await two).render_key == store.key
    assert authorization == {
        "a": ["before_lookup", "before_delivery"],
        "b": ["before_lookup", "before_delivery"],
    }
    assert store.publish_calls == 1


async def test_singleflight_is_bounded_and_duplicate_subscriber_fails_closed():
    store = FakeStore()
    coordinator = AudioTakeRenderCoordinator(
        store,
        max_flights=1,
        max_waiters_per_flight=1,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def render():
        started.set()
        await release.wait()
        return RenderedPCM(outcome(), b"\x01\x00\x02\x00")

    _, auth = authorization_log()
    first = asyncio.create_task(
        coordinator.acquire(
            subscriber_id="same-subscriber",
            recipe=recipe(),
            authorize=auth,
            render=render,
        )
    )
    await started.wait()

    with pytest.raises(
        AudioTakeRenderCoordinatorError,
        match="duplicate_audio_take_subscriber|waiter_capacity",
    ):
        await coordinator.acquire(
            subscriber_id="same-subscriber",
            recipe=recipe(),
            authorize=auth,
            render=render,
        )

    other_store_key = store.key
    store.key = "2" * 64
    with pytest.raises(
        AudioTakeRenderCoordinatorError,
        match="audio_take_singleflight_capacity",
    ):
        await coordinator.acquire(
            subscriber_id="other-render",
            recipe=recipe(text_hash="2" * 64),
            authorize=auth,
            render=render,
        )
    store.key = other_store_key

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first


async def test_denied_authorization_happens_before_any_cache_lookup():
    store = FakeStore()
    store.cached = take(store.key)
    coordinator = AudioTakeRenderCoordinator(store)
    calls = []

    async def denied(stage):
        calls.append(stage)
        return False

    with pytest.raises(
        AudioTakeRenderCoordinatorError,
        match="audio_take_not_authorized",
    ):
        await coordinator.acquire(
            subscriber_id="revoked-turn:generation-1",
            recipe=recipe(),
            authorize=denied,
            render=lambda: None,  # type: ignore[arg-type]
        )

    assert calls == ["before_lookup"]
    assert store.load_calls == 0


async def test_authorization_service_failure_is_fail_closed_before_cache_lookup():
    store = FakeStore()
    store.cached = take(store.key)
    coordinator = AudioTakeRenderCoordinator(store)

    async def unavailable(stage):
        assert stage == "before_lookup"
        raise RuntimeError("authorization backend unavailable")

    with pytest.raises(
        AudioTakeRenderCoordinatorError,
        match="audio_take_authorization_unavailable",
    ):
        await coordinator.acquire(
            subscriber_id="turn-auth-down:generation-1",
            recipe=recipe(),
            authorize=unavailable,
            render=lambda: None,  # type: ignore[arg-type]
        )

    assert store.load_calls == 0
