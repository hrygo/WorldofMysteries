"""Live SpeechRail integration for the path the App actually takes (VF-40).

``test_voice_foundry_live_integration.py`` drives the adapter directly, and
``test_voice_foundry_control_surface.py`` drives the control surface against a
stand-in provider. Neither is the path a player walks: the App resolves the
surface through ``StoryRuntime._open_foundry`` and then calls four of the
methods it registers — ``list``, ``get``, ``asset.get``, and ``command`` with
``review`` or ``publish``. This is the only test that walks that path against
a real service, which is what acceptance criterion 6 asks for and what the
four contract mismatches fixed this round all shared: each one made a broken
assembly look like a working one.

Intake goes through ``voice.foundry.cast_design``, which is the method the
App's 铸造音色 button sends and the one the silent first-appearance trigger
resolves to the same task. That is the whole point of the walk: the button and
the automatic path must arrive at one casting, and only a real run against a
real provider can say whether they do.

The unattended stages between intake and selection are still driven through
the worker, and the reason is stated rather than hidden. The driver is
constructed by ``_open_foundry`` and runs for the engine's lifetime, but it
polls on an interval; a test that wants the chain to reach a human stage now
would otherwise wait on a timer. Selection and everything after it — the
audition, the review, the publish — goes through the registered handlers
exactly as the App calls them.

The deployment must have declared what it casts with. ``WOM_FOUNDRY_MODEL_ID``
names the SpeechRail model catalog key the cast renders with and
``WOM_FOUNDRY_SCOPE_REF`` the rights scope the evidence claims; without both
``_open_foundry`` returns nothing at all, which this test asserts rather than
works around.

Opt-in, never in CI:

    WOM_LIVE_SPEECHRAIL=1 uv run --locked --extra dev pytest -q \
        tests/test_voice_foundry_app_path_live.py -v

**This run publishes a voice.** It casts the shipped ``tingen.narrator``
design through the whole chain and binds the result, so a green run leaves
a real narrator voice registered with the provider and a real binding in
the database. That is the point: acceptance wants the narrator cast and
listened to for real, and a test that only pretended to would prove
nothing. It is opt-in for exactly that reason.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path

import pytest

from application.voice_foundry import HUMAN_STAGES, VoiceFoundryWorker
from application.voice_foundry_ports import VoiceFoundryPortError
from application.voice_foundry_service import VoiceSupplyService
from domain.voice_identity import VoiceBindingScope
from infrastructure.audio.config import AudioProviderConfig
from infrastructure.audio.foundry_policy import execution_policy
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.story_runtime import StoryRuntime
from infrastructure.voice_design_catalog import load_voice_design_catalog
from infrastructure.voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("WOM_LIVE_SPEECHRAIL") != "1",
    reason="live SpeechRail integration is opt-in (WOM_LIVE_SPEECHRAIL=1)",
)

SESSION_ID = "live-app-path-session"


def _selected_designs() -> tuple[str, ...]:
    """Which catalog identities this run casts.

    Defaults to the whole shipped roster rather than one character, because
    acceptance asks for the narrator and the first three to five people to be
    cast and listened to for real; a file that only ever proves the first one
    leaves the rest of the claim untested. ``WOM_LIVE_DESIGNS`` narrows it to
    one identity when a brief has just been revised.
    """
    raw = (os.environ.get("WOM_LIVE_DESIGNS") or "").strip()
    if raw:
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    return tuple(item.design_id for item in load_voice_design_catalog().designs)


#: Where the audition clips are written for a person to actually listen to.
#: Acceptance wants the listening recorded, and a machine verdict is nobody
#: hearing anything — so a run leaves the two WAVs and the facts about them on
#: disk, including which text each one speaks. Empty means the run asserts
#: only, which is what CI and an ordinary re-run should do.
AUDITION_DIR = (os.environ.get("WOM_LIVE_AUDITION_DIR") or "").strip()


#: What ``_open_foundry`` advertises. The App probes this before it offers the
#: audition console, so a surface missing a method is a capability the client
#: is entitled to see absent.
APP_METHODS = frozenset(
    {
        "voice.foundry.get",
        "voice.foundry.list",
        "voice.foundry.asset.get",
        "voice.foundry.cast_design",
        "voice.foundry.list_designs",
        "voice.foundry.select",
        "voice.foundry.confirm_reference",
        "voice.foundry.validate",
        "voice.foundry.review",
        "voice.foundry.publish",
        "voice.foundry.retry",
        "voice.foundry.cancel",
    }
)


def _discover_key() -> None:
    """Put SpeechRail's own key in the environment without revealing it."""
    if os.environ.get("SPEECHRAIL_API_KEY", "").strip():
        return
    home = os.environ.get("SPEECHRAIL_APP_HOME")
    base = (
        Path(home).expanduser()
        if home and home.strip()
        else Path.home() / "Library" / "Application Support" / "SpeechRail"
    )
    try:
        lines = (base / "config" / ".env").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return
    for raw in lines:
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if separator and name.strip() == "SPEECHRAIL_API_KEY":
            parsed = value.strip()
            if len(parsed) >= 2 and parsed[0] in "'\"" and parsed[-1] == parsed[0]:
                parsed = parsed[1:-1]
            if parsed:
                os.environ["SPEECHRAIL_API_KEY"] = parsed
            return


def _digest(payload) -> str:
    """The wire digest, recomputed rather than imported."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _command(task_id, revision, action, payload, *, command_id):
    return {
        "schema_version": "1.0",
        "command_id": command_id,
        "payload_digest": _digest(payload),
        "task_id": task_id,
        "expected_task_revision": revision,
        "action": action,
        "payload": payload,
    }


async def _advance_to_a_human_stage(worker: VoiceFoundryWorker, task_id: str):
    """Run the unattended steps the product has no driver for."""
    for _ in range(8):
        step = await worker.advance(task_id)
        if not step.slot_consumed or step.record.stage in HUMAN_STAGES:
            return step.record
    raise AssertionError("the supply chain never reached a human stage")


def _record_for_listening(
    design_id: str,
    *,
    heard: dict,
    candidate_id: str,
) -> None:
    """Leave the two clips and the facts a listener needs, on disk.

    Written from the bytes the engine handed the App rather than re-read from
    the provider, so what a person hears is exactly what the App would have
    played — including the digests the review was signed against, which is
    what makes a later verdict about these files a verdict about *this*
    casting rather than a fresh one that happens to sound similar.

    No-ops unless ``WOM_LIVE_AUDITION_DIR`` names a directory, so an ordinary
    run and CI leave nothing behind.
    """
    if not AUDITION_DIR:
        return
    design = next(
        item
        for item in load_voice_design_catalog().designs
        if item.design_id == design_id
    )
    out = Path(AUDITION_DIR) / design_id.replace(".", "_")
    out.mkdir(parents=True, exist_ok=True)
    record = {
        "design_id": design.design_id,
        "display_name": design.display_name,
        "public_traits": list(design.public_traits),
        "voice_description": design.voice_description,
        "candidate_id": candidate_id,
        "published": True,
        "human_review": "NOT YET SIGNED — a machine pass is not a person",
    }
    for kind, text in (
        ("reference", design.reference_text),
        ("validation", design.validation_text),
    ):
        audio = base64.b64decode(heard[kind]["audio_base64"], validate=True)
        name = f"{kind}.wav"
        (out / name).write_bytes(audio)
        record[kind] = {
            "file": name,
            "text": text,
            "audio_digest": heard[kind]["audio_digest"],
            "audio_bytes": heard[kind]["audio_bytes"],
        }
    record["validation_id"] = heard["validation"]["validation_id"]
    (out / "acceptance.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("design_id", _selected_designs())
async def test_the_assembled_product_path_auditions_against_a_real_speechrail(
    tmp_path,
    design_id,
):
    """Walk the four methods the App calls, over the real assembly.

    The assertion that matters is on the audition response: the App decodes
    ``audio_base64`` and checks the byte count against ``audio_bytes`` before
    it will play anything. A response carrying a digest and a length with no
    playable audio behind it passes every other check in this file, and is
    exactly what a preview that reports a summary instead of a waveform looks
    like from the client's side.
    """
    _discover_key()
    audio_config = AudioProviderConfig.from_env()
    assert audio_config.provider_name.casefold() == "speechrail", (
        "the assembly only registers the surface for SpeechRail; "
        f"got {audio_config.provider_name!r}"
    )
    # The deployment has to have said what it casts with. Asserted rather
    # than worked around: a run that quietly supplied its own policy would be
    # evidence about a configuration nobody deploys.
    policy = execution_policy(audio_config)
    assert policy is not None, (
        "WOM_FOUNDRY_MODEL_ID and WOM_FOUNDRY_SCOPE_REF must be set — the "
        "foundry is withheld from the handshake without them"
    )

    layout = DatabasePaths.for_world(tmp_path, "live-app-path-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        layout, expected_sqlite_version=sqlite3.sqlite_version
    )
    try:
        # The production assembly, not a hand-built copy of it: if this
        # returns nothing there is no audition console to test.
        foundry = StoryRuntime._open_foundry(
            database, audio_config, _FixedScope()
        )
        assert foundry is not None
        handlers = foundry.handlers
        assert APP_METHODS <= set(handlers)
        assert "voice.foundry.cast_design" in handlers
        assert "voice.foundry.list_designs" in handlers

        repository = SQLiteVoiceFoundryRepository(database)
        supply = VoiceSupplyService(repository=repository, bindings=_NoBindings())
        adapter = _real_port(audio_config, policy)
        worker = VoiceFoundryWorker(repository, adapter, policy=None)

        # The App's own door. The scope, the authorization and the request
        # digest are all the engine's to derive, exactly as they are when a
        # person presses the button or a character opens their mouth for the
        # first time.
        cast_body, code = await handlers["voice.foundry.cast_design"](
            {
                "schema_version": "1.0",
                "session_id": SESSION_ID,
                "design_id": design_id,
            }
        )
        assert code is None, cast_body
        opened = cast_body["task"]
        # The engine resolved the scope from the session, not from the
        # request: a client that could have named the world would also have
        # been able to lie about it.
        assert opened["scope"]["world_id"] == "live-app-path-world"
        assert opened["scope"]["owner_id"] == "player"
        assert opened["required_actions"] == []
        task_id = opened["task_id"]
        candidate_id = None
        provider_candidate_id = None
        try:
            task = await _advance_to_a_human_stage(worker, task_id)
            assert task.stage == "awaiting_selection"

            candidate = await repository.load_candidate(
                task_id, f"{task_id}:candidate:0"
            )
            candidate_id = candidate.candidate_id

            # Selection is the one command in this file the App does not send
            # either. Everything below it is the App's own path.
            body, code = await handlers["voice.foundry.select"](
                _command(
                    task_id,
                    task.task_revision,
                    "select",
                    {
                        "candidate_id": candidate_id,
                        "preview_audio_digest": candidate.preview_audio_digest,
                    },
                    command_id="cmd-select",
                )
            )
            assert code is None, code
            task = await _advance_to_a_human_stage(worker, task_id)
            assert task.stage == "awaiting_review"
            provider_candidate_id = (
                await repository.load_candidate(task_id, candidate_id)
            ).provider_candidate_id

            # --- the App's four methods, from here down ---
            task_body, code = await handlers["voice.foundry.get"](
                {"schema_version": "1.0", "task_id": task_id}
            )
            assert code is None, code
            projection = task_body["task"]
            auditioned = [
                item
                for item in projection["candidates"]
                if item["candidate_id"] == candidate_id
            ]
            assert auditioned, "the selected candidate is not in the projection"
            assert auditioned[0]["provider_candidate_revision"]

            heard = {}
            for kind in ("reference", "validation"):
                asset, code = await handlers["voice.foundry.asset.get"](
                    {
                        "schema_version": "1.0",
                        "task_id": task_id,
                        "candidate_id": candidate_id,
                        "kind": kind,
                    }
                )
                assert code is None, code
                audio = base64.b64decode(asset["audio_base64"], validate=True)
                # The client's own two checks, in the client's own order.
                assert len(audio) == asset["audio_bytes"]
                assert hashlib.sha256(audio).hexdigest() == asset["audio_digest"]
                assert audio[:4] == b"RIFF" and audio[8:12] == b"WAVE", (
                    f"the {kind} audition carried no playable audio"
                )
                assert asset["candidate_revision"] == auditioned[0][
                    "provider_candidate_revision"
                ]
                heard[kind] = asset

            assert heard["validation"]["validation_id"]
            assert (
                heard["reference"]["validation_id"] is None
            ), "the reference asset must not claim a cross-text validation"

            task = await repository.load_task(task_id)
            review_body, code = await handlers["voice.foundry.review"](
                _command(
                    task_id,
                    task.task_revision,
                    "review",
                    {
                        "human_review": {
                            "validation_id": heard["validation"]["validation_id"],
                            "reference_audio_digest": heard["reference"][
                                "audio_digest"
                            ],
                            "validation_audio_digest": heard["validation"][
                                "audio_digest"
                            ],
                            # A probe, not a person. The product refuses to
                            # invent this judgement, so the test states it and
                            # the acceptance record says a human has not.
                            "identity": "pass",
                            "naturalness": "pass",
                        }
                    },
                    command_id="cmd-review",
                )
            )
            assert code is None, code

            task = await repository.load_task(task_id)
            publish_body, code = await handlers["voice.foundry.publish"](
                _command(
                    task_id,
                    task.task_revision,
                    "publish",
                    {
                        "provider_candidate_revision": heard["reference"][
                            "candidate_revision"
                        ]
                    },
                    command_id="cmd-publish",
                )
            )
            assert code is None, code
            assert publish_body["task"]["stage"] in {"binding", "ready"}
            _record_for_listening(
                design_id,
                heard=heard,
                candidate_id=candidate_id,
            )
            candidate_id = None
            provider_candidate_id = None
        finally:
            if provider_candidate_id is not None:
                await _cancel_candidate(adapter, provider_candidate_id)
    finally:
        await database.close()


class _NoBindings:
    async def load_scope(self, _scope):
        return None


class _FixedScope:
    """The scope the engine would derive from a session it already owns.

    Standing in for the story session lookup only. The point of
    ``cast_design`` is that the client cannot supply any of this, so the
    resolver is where the world id comes from — replacing it with a constant
    removes nothing that the request was not already forbidden to send.
    """

    async def scope_for(
        self, session_id: str, presentation_identity: str
    ) -> VoiceBindingScope | None:
        if session_id != SESSION_ID:
            return None
        # The provider reserves a target voice id for the life of a candidate,
        # so a run that cannot cancel its candidate must not reuse an id
        # either — a conflict there would look like a contract failure rather
        # than the leftover it is.
        return VoiceBindingScope(
            owner_id="player",
            world_id="live-app-path-world",
            worldline_id="line-live",
            presentation_identity=presentation_identity,
            phase="narration",
            locale="zh-CN",
        )


def _real_port(audio_config: AudioProviderConfig, policy):
    """The adapter the production assembly builds, policy and all."""
    from infrastructure.audio.voice_foundry_adapter import (
        SpeechRailVoiceFoundryAdapter,
    )

    return SpeechRailVoiceFoundryAdapter(
        audio_config,
        preview_model=audio_config.tts_model,
        execution_policy=policy,
    )


async def _cancel_candidate(adapter, provider_candidate_id: str) -> None:
    """Best-effort cleanup: a probe must not leave a live candidate behind.

    A candidate reserves its target voice id for as long as it exists, so
    cancelling only this engine's own task record leaves the provider holding
    a reservation that makes the next run fail as a contract violation.
    """
    try:
        await adapter._fetch(
            "POST",
            adapter._url(f"voice-designs/{provider_candidate_id}/cancel"),
            # A JSON body has to declare that it is JSON or the provider
            # rejects it before it ever reaches the cancel route.
            adapter._headers({"Content-Type": "application/json"}),
            b'{"reason_code": "live_app_path_cleanup"}',
            1 << 20,
            30.0,
        )
    except (VoiceFoundryPortError, OSError, asyncio.TimeoutError):
        pass
