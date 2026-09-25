"""W-V07 bounded sealed-unit prefetch tests."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from application.performance_compiler import (
    DesiredPerformance,
    EffectiveBackendPerformance,
    EffectivePlaybackPerformance,
)
from application.speech_unit import SealedSpeechUnit
from infrastructure.audio_prefetch import (
    AudioTakePrefetchError,
    AudioTakePrefetchQueue,
)
from infrastructure.audio_take_coordinator import (
    AudioTakeRenderCoordinator,
    RenderedPCM,
)
from infrastructure.audio_take_store import PublishedAudioTake, RenderOutcome


def unit(
    *,
    unit_id: str = "speech-a",
    model_revision: str | None = "b" * 40,
    spoken_text: str = "克莱恩没有开门。",
) -> SealedSpeechUnit:
    return SealedSpeechUnit(
        unit_id=unit_id,
        turn_id="turn-1",
        story_session_id="session-1",
        story_revision=7,
        narrative_block_id="narrative-1",
        segment_index=0,
        presentation_identity="klein-visible",
        binding_id="binding-1",
        binding_revision=2,
        logical_voice_id="voice-klein",
        persona_revision="persona-r1",
        provider_instance="speechrail-local",
        voice_id="klein-approved",
        voice_revision="voice-" + "c" * 40,
        model_id="qwen3-tts-base",
        model_revision=model_revision,
        language="zh-CN",
        performance_plan_id="perf-1",
        display_text=spoken_text,
        spoken_text=spoken_text,
        pronunciation_revision="pron-v1",
        pronunciation_mappings=(),
        desired=DesiredPerformance(),
        backend=EffectiveBackendPerformance(speed=1.0),
        playback=EffectivePlaybackPerformance(
            volume="normal",
            pause_before_ms=0,
        ),
        unsupported=(),
        degradation=(),
    )


class FakeStore:
    def __init__(self):
        self.cached = {}
        self.rendered_recipes = []

    def render_key(self, recipe):
        self.rendered_recipes.append(recipe)
        # Test deliberately makes equivalent recipes share the same dry key.
        return recipe.spoken_text_sha256

    async def load(self, render_key):
        return self.cached.get(render_key)

    async def publish_pcm(self, recipe, outcome, pcm16):
        key = recipe.spoken_text_sha256
        value = PublishedAudioTake(
            take_id="take-" + key[:8],
            render_key=key,
            relative_path="Takes/" + "e" * 64 + ".pcm",
            file_sha256="e" * 64,
            manifest={"render_key": key},
            manifest_hmac="f" * 64,
            replayed=False,
        )
        self.cached[key] = value
        return value


def rendered():
    return RenderedPCM(
        RenderOutcome(
            provider_instance="speechrail-local",
            model_id="qwen3-tts-base",
            model_revision="b" * 40,
            voice_id="klein-approved",
            voice_revision="voice-" + "c" * 40,
            receipt_id="receipt-prefetch",
        ),
        b"\x01\x00\x02\x00",
    )


async def allow(_stage):
    return True


def test_prefetch_recipe_uses_only_sealed_dry_execution_identity():
    value = unit()
    recipe = AudioTakePrefetchQueue.recipe_for(value)
    assert recipe.provider_instance == value.provider_instance
    assert recipe.model_id == value.model_id
    assert recipe.model_revision == value.model_revision
    assert recipe.voice_id == value.voice_id
    assert recipe.voice_revision == value.voice_revision
    assert recipe.pronunciation_revision == value.pronunciation_revision
    assert recipe.backend_fingerprint
    payload = recipe.payload()
    assert "turn_id" not in payload
    assert "story_revision" not in payload
    assert "binding_id" not in payload
    assert "display_text" not in payload


async def test_unverified_model_or_unsealed_input_is_rejected_before_render():
    store = FakeStore()
    queue = AudioTakePrefetchQueue(AudioTakeRenderCoordinator(store))
    render_calls = 0
    auth_calls = 0

    async def auth(_stage):
        nonlocal auth_calls
        auth_calls += 1
        return True

    async def render():
        nonlocal render_calls
        render_calls += 1
        return rendered()

    with pytest.raises(
        AudioTakePrefetchError,
        match="model_revision_unverified",
    ):
        await queue.prefetch(
            subscriber_id="next-1",
            unit=unit(model_revision=None),
            authorize=auth,
            render=render,
        )
    assert auth_calls == 0
    assert render_calls == 0

    with pytest.raises(
        AudioTakePrefetchError,
        match="requires_sealed_unit",
    ):
        await queue.prefetch(
            subscriber_id="next-2",
            unit=object(),  # type: ignore[arg-type]
            authorize=auth,
            render=render,
        )
    assert render_calls == 0


async def test_uncommitted_or_revoked_prefetch_authorization_denies_before_synthesis():
    store = FakeStore()
    queue = AudioTakePrefetchQueue(AudioTakeRenderCoordinator(store))
    calls = []
    render_calls = 0

    async def denied(stage):
        calls.append(stage)
        return False

    async def render():
        nonlocal render_calls
        render_calls += 1
        return rendered()

    with pytest.raises(Exception, match="audio_take_not_authorized"):
        await queue.prefetch(
            subscriber_id="uncommitted-branch",
            unit=unit(),
            authorize=denied,
            render=render,
        )

    assert calls == ["before_lookup"]
    assert render_calls == 0
    assert store.rendered_recipes == []


async def test_prefetch_queue_is_hard_bounded_to_two_units():
    store = FakeStore()
    queue = AudioTakePrefetchQueue(
        AudioTakeRenderCoordinator(store),
        max_pending_units=2,
    )
    release = asyncio.Event()
    started = 0
    both_started = asyncio.Event()

    async def render():
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await release.wait()
        return rendered()

    one = asyncio.create_task(
        queue.prefetch(
            subscriber_id="s1",
            unit=unit(unit_id="speech-1", spoken_text="第一句"),
            authorize=allow,
            render=render,
        )
    )
    two = asyncio.create_task(
        queue.prefetch(
            subscriber_id="s2",
            unit=unit(unit_id="speech-2", spoken_text="第二句"),
            authorize=allow,
            render=render,
        )
    )
    await asyncio.wait_for(both_started.wait(), timeout=1)

    with pytest.raises(AudioTakePrefetchError, match="prefetch_capacity"):
        await queue.prefetch(
            subscriber_id="s3",
            unit=unit(unit_id="speech-3", spoken_text="第三句"),
            authorize=allow,
            render=render,
        )

    snap = await queue.snapshot()
    assert snap.pending_units == 2
    assert snap.max_pending_units == 2
    release.set()
    await one
    await two
    assert (await queue.snapshot()).pending_units == 0

    with pytest.raises(ValueError, match="prefetch limit"):
        AudioTakePrefetchQueue(
            AudioTakeRenderCoordinator(store),
            max_pending_units=3,
        )


async def test_equivalent_dry_units_can_share_render_without_merging_unit_authorization():
    store = FakeStore()
    coordinator = AudioTakeRenderCoordinator(store)
    queue = AudioTakePrefetchQueue(coordinator)
    release = asyncio.Event()
    started = asyncio.Event()
    render_calls = 0
    auth = {"a": [], "b": []}

    async def render():
        nonlocal render_calls
        render_calls += 1
        started.set()
        await release.wait()
        return rendered()

    def checker(name):
        async def check(stage):
            auth[name].append(stage)
            return True
        return check

    first_unit = unit(unit_id="speech-turn-a")
    second_unit = replace(
        first_unit,
        unit_id="speech-turn-b",
        turn_id="turn-2",
        narrative_block_id="narrative-2",
    )
    first = asyncio.create_task(
        queue.prefetch(
            subscriber_id="turn-a",
            unit=first_unit,
            authorize=checker("a"),
            render=render,
        )
    )
    await started.wait()
    second = asyncio.create_task(
        queue.prefetch(
            subscriber_id="turn-b",
            unit=second_unit,
            authorize=checker("b"),
            render=render,
        )
    )
    await asyncio.sleep(0)
    release.set()
    await first
    await second

    assert render_calls == 1
    assert auth == {
        "a": ["before_lookup", "before_delivery"],
        "b": ["before_lookup", "before_delivery"],
    }


async def test_prefetch_rejects_backend_fields_not_representable_by_current_render_control():
    store = FakeStore()
    queue = AudioTakePrefetchQueue(AudioTakeRenderCoordinator(store))
    invalid = replace(
        unit(),
        backend=EffectiveBackendPerformance(
            speed=1.0,
            instructions="unsupported-on-current-wire",
        ),
    )
    render_calls = 0

    async def render():
        nonlocal render_calls
        render_calls += 1
        return rendered()

    with pytest.raises(
        AudioTakePrefetchError,
        match="backend_unrepresentable",
    ):
        await queue.prefetch(
            subscriber_id="bad-backend",
            unit=invalid,
            authorize=allow,
            render=render,
        )
    assert render_calls == 0
