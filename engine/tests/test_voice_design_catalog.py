"""The casting brief the engine loads instead of asking a human for (VF-50)."""

from __future__ import annotations

import json
import sqlite3

from pathlib import Path

import pytest
import pytest_asyncio

from domain.voice_identity import VoiceBindingScope
from application.voice_foundry_service import VoiceSupplyService
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.voice_binding_repository import SQLiteVoiceBindingRepository
from infrastructure.voice_foundry_control import voice_foundry_control_handlers
from infrastructure.voice_design_catalog import (
    VoiceDesignError,
    load_voice_design_catalog,
)
from infrastructure.voice_foundry_repository import SQLiteVoiceFoundryRepository

CATALOG = Path(__file__).resolve().parent.parent / "infrastructure" / "voice_designs" / "catalog.json"


@pytest.fixture
def paths(tmp_path):
    layout = DatabasePaths.for_world(tmp_path, "voice-design-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return layout


@pytest_asyncio.fixture
async def database(paths):
    return await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )


@pytest_asyncio.fixture
async def repository(database):
    try:
        yield SQLiteVoiceFoundryRepository(database)
    finally:
        await database.close()


def scope(identity: str = "victor-osborn") -> VoiceBindingScope:
    return VoiceBindingScope(
        owner_id="player",
        world_id="voice-design-world",
        worldline_id="line-1",
        presentation_identity=identity,
        phase="narrative",
        locale="zh-CN",
    )


def write(tmp_path: Path, payload: object) -> Path:
    target = tmp_path / "catalog.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target


def raw() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_the_shipped_catalog_casts_five_distinguishable_identities():
    """Acceptance 1 asks for one narrator plus 3-5 people, none sharing a voice."""
    catalog = load_voice_design_catalog()

    assert len(catalog.designs) == 5
    assert sum(1 for item in catalog.designs if item.usage == "narration") == 1
    traits = [item.public_traits for item in catalog.designs]
    assert len(set(traits)) == len(traits), "public traits must not be copy-pasted"


def test_every_design_says_something_and_reads_something():
    catalog = load_voice_design_catalog()
    for design in catalog.designs:
        assert len(design.voice_description) > 20, design.design_id
        assert design.reference_text.strip()
        assert design.validation_text.strip()
        assert design.reference_text != design.validation_text


def test_the_casting_input_never_carries_a_dossier():
    """Hidden identity and unplayed plot have no business in a prompt or a log."""
    catalog = load_voice_design_catalog()
    text = CATALOG.read_text(encoding="utf-8")
    for leaked in ("杀死", "阴谋", "其实是", "真实身份", "秘密"):
        assert leaked not in text, leaked
    for design in catalog.designs:
        assert "canon_anchor" not in design.__slots__


@pytest.mark.parametrize(
    "mutation,code",
    [
        (
            lambda d: d["identities"][0].__setitem__("canon_anchor", "lotm:kleins"),
            "voice_design_must_not_anchor_canon",
        ),
        (
            lambda d: d["identities"][0].__setitem__("hidden_identity", "audrey"),
            "voice_design_unknown_field:hidden_identity",
        ),
        (
            lambda d: d["identities"][0].__setitem__(
                "validation_text", d["identities"][0]["reference_text"]
            ),
            "voice_design_validation_text_repeats_reference",
        ),
        (
            lambda d: d["identities"][0].pop("reference_text"),
            "voice_design_missing_field:reference_text",
        ),
        (
            lambda d: d["identities"][1].__setitem__("kind", "canon"),
            "voice_design_kind_unsupported",
        ),
    ],
)
def test_content_that_cannot_be_cast_safely_is_refused(tmp_path, mutation, code):
    payload = raw()
    mutation(payload)
    with pytest.raises(VoiceDesignError) as failure:
        load_voice_design_catalog(write(tmp_path, payload))
    assert failure.value.args[0] == code


def test_two_designs_for_one_identity_are_refused(tmp_path):
    payload = raw()
    payload["identities"][1]["presentation_identity"] = payload["identities"][0][
        "presentation_identity"
    ]
    with pytest.raises(VoiceDesignError) as failure:
        load_voice_design_catalog(write(tmp_path, payload))
    assert failure.value.args[0] == "voice_design_identity_duplicated"


def test_two_narrators_are_refused(tmp_path):
    payload = raw()
    payload["identities"][1]["usage"] = "narration"
    payload["identities"][1]["presentation_identity"] = "narrator-two"
    with pytest.raises(VoiceDesignError) as failure:
        load_voice_design_catalog(write(tmp_path, payload))
    assert failure.value.args[0] == "voice_design_narrator_ambiguous"


def test_a_missing_or_empty_catalog_is_refused(tmp_path):
    with pytest.raises(VoiceDesignError) as unreadable:
        load_voice_design_catalog(tmp_path / "absent.json")
    assert unreadable.value.args[0] == "voice_design_catalog_unreadable"

    empty = write(tmp_path, {"catalog_version": "1.0", "identities": []})
    with pytest.raises(VoiceDesignError) as failure:
        load_voice_design_catalog(empty)
    assert failure.value.args[0] == "voice_design_catalog_empty"


async def test_a_design_opens_a_task_the_repository_accepts(repository):
    """The catalog is not a document: it produces a durable, validated task."""
    catalog = load_voice_design_catalog()
    design = catalog.get("victor-osborn")

    task = await repository.register_task(
        design.task_spec(
            scope=scope(),
            request_id="req-victor-1",
            persona_revision="persona-1",
            authorization_ref="authz-1",
            provider_instance="speechrail-local",
        )
    )

    assert task.stage.value == "requested"
    assert task.voice_description == design.voice_description
    assert task.origin_ref == "voice_design:tingen.victor-osborn"
    # The digest is over the same canonical body the control surface
    # recomputes, so the in-process path and the IPC path agree by construction.
    assert task.request_digest == design.request_body(
        scope=scope(),
        request_id="req-victor-1",
        persona_revision="persona-1",
        authorization_ref="authz-1",
        provider_instance="speechrail-local",
    )["request_digest"]


def test_the_request_body_is_exactly_the_wire_envelope():
    """One builder feeds both entry points, so they cannot drift apart."""
    body = load_voice_design_catalog().get("narrator").request_body(
        scope=scope("narrator"),
        request_id="req-narrator-1",
        persona_revision="persona-narrator",
        authorization_ref="authz-1",
        provider_instance="speechrail-local",
    )
    assert set(body) == {
        "schema_version",
        "request_id",
        "request_digest",
        "authorization_ref",
        "scope",
        "persona_revision",
        "usage",
        "locale",
        "public_traits",
        "voice_description",
        "reference_text",
        "validation_text",
        "provider_instance",
        "requested_execution_scope",
        "budget",
        "origin",
    }
    assert body["usage"] == "narration"


async def test_the_catalog_body_is_accepted_by_the_real_control_surface(
    repository, database
):
    """The one test that would catch the two entry points drifting apart.

    The catalog builds a request body in process; the App button posts the
    same body over IPC. Both land in this handler, which recomputes the
    digest and rejects a mismatch — so if the builder's canonical form ever
    stopped matching the reader's, the button would break while every unit
    test on the builder stayed green.
    """
    handlers = voice_foundry_control_handlers(
        repository=repository,
        supply=VoiceSupplyService(
            repository=repository,
            bindings=SQLiteVoiceBindingRepository(database),
        ),
        commands=None,
        worker=None,
    )
    body = load_voice_design_catalog().get("ida-finch").request_body(
        scope=scope("ida-finch"),
        request_id="req-ida-1",
        persona_revision="persona-1",
        authorization_ref="authz-1",
        provider_instance="speechrail-local",
    )

    payload, code = await handlers["voice.foundry.request"](
        {"schema_version": "1.0", "request": body}
    )

    assert code is None
    assert payload is not None
    assert payload["task"]["stage"] == "requested"
    assert payload["task"]["required_actions"] == []
