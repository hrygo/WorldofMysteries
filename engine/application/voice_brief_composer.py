"""Composing a casting brief for a character nobody has written one for (VF-56).

The catalog is a **cache of adjudicated designs**, not the gate. Five hand-written
briefs describe the first batch of speakers; they are not the set of characters
this world is allowed to have. When a character appears that the catalog has
never heard of, refusing to cast them leaves them mute forever — which is the
opposite of a world that grows.

So a brief is composed here, from what the character has already said.

**Only published lines are read.** The inputs are segments the narrative block
has already published: the player has seen them, so they are public by
construction, and the same disclosure rule that authorizes rendering them for
audio authorizes naming them in a casting brief. Nothing is read from a
dossier, a model or a hidden field — a brief composed from what a character
said out loud cannot leak what they have not.

**The character reads their own lines.** The reference and validation texts are
two *different* lines the character has actually spoken. A cross-text check
against the same sentence proves nothing, and inventing a third sentence would
put text into the world that the world never said. A character who has spoken
only once is therefore not yet castable, and says so — rather than being cast
from prose nobody authorized.

**Voices do not collide.** A slot is derived from the identity, so a character
keeps the same voice for as long as they exist, and slots already spoken for
are skipped, so two characters never share one. Determinism is the whole
feature: an LLM asked the same question twice must not answer twice.

**The model may improve the prose, never the facts.** Refinement rewrites the
description a voice actor reads and touches nothing else — the texts stay the
character's own words, and a model that is absent, slow or wrong changes
nothing at all.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from domain.voice_identity import VoiceBindingScope
from infrastructure.voice_foundry_repository import (
    DEFAULT_CAST_BUDGET,
    DEFAULT_EXECUTION_SCOPE,
    VoiceCastBudget,
    VoiceExecutionScope,
    VoiceFoundryTaskSpec,
)

#: Three axes, because three is what a listener actually distinguishes in a
#: crowd scene: how high, how fast, how much grit. Each slot names all three,
#: so two characters sharing a slot would be sharing a voice.
_AXIS_SLOTS: tuple[tuple[str, str, str], ...] = (
    ("中音", "中速", "干净"),
    ("偏低", "慢", "沙哑"),
    ("偏高", "快", "清亮"),
    ("中低", "中速", "厚实"),
    ("中音", "偏慢", "温润"),
    ("中高", "急促", "薄"),
    ("低", "慢而顿", "粗粝"),
    ("中偏高", "中速偏快", "克制"),
)

#: Mirrors ``VoiceFoundryTaskSpec.validated``: a line must satisfy the same
#: bounds the repository will later enforce. Kept in step deliberately — a
#: composer that filters more loosely than the domain accepts would build a
#: brief that fails at the moment it is registered, which reads as a supply
#: outage rather than as "this character has not said enough yet".
_MIN_LINE = 20
_MAX_LINE = 240


class VoiceBriefRefiner(Protocol):
    """Optional prose polish. Never a source of facts."""

    async def refine(
        self, *, presentation_identity: str, description: str, traits: tuple[str, ...]
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class VoiceBriefFacts:
    """What may be known about a speaker when a brief is composed for them."""

    presentation_identity: str
    display_name: str
    usage: str
    #: Lines this character has already published, oldest first. Two are the
    #: minimum: one is a reference, the other is what it is checked against.
    spoken_lines: tuple[str, ...]
    #: Axis slots already spoken for, so a new character does not land on one.
    taken_slots: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ComposedBrief:
    """A brief that can be cast from. Provenance stays visible."""

    design_id: str
    presentation_identity: str
    usage: str
    public_traits: tuple[str, ...]
    voice_description: str
    reference_text: str
    validation_text: str
    slot: int
    #: Always 1: a composed brief is revision 1 of itself, and it only ever
    #: reaches revision 2 by being written down and reviewed as a catalog
    #: design. That promotion is the moment a person takes responsibility for
    #: the voice, and it is deliberately a separate, visible act.
    design_revision: int
    #: ``composed`` or ``catalog``: which authority produced this. A task
    #: records it so a later reader can tell a heard-and-fixed voice from one
    #: the system proposed on its own.
    origin: str

    def task_spec(
        self,
        *,
        scope: VoiceBindingScope,
        request_id: str,
        persona_revision: str,
        authorization_ref: str,
        provider_instance: str,
        execution_scope: VoiceExecutionScope = DEFAULT_EXECUTION_SCOPE,
        budget: VoiceCastBudget = DEFAULT_CAST_BUDGET,
    ) -> VoiceFoundryTaskSpec:
        """The durable form of this brief — the same shape a catalog design
        produces, so both routes into a casting are indistinguishable
        downstream. Nothing between here and the provider should have to know
        whether a person wrote this brief or the system composed it."""
        body = {
            "usage": self.usage,
            "public_traits": list(self.public_traits),
            "voice_description": self.voice_description,
            "reference_text": self.reference_text,
            "validation_text": self.validation_text,
        }
        return VoiceFoundryTaskSpec(
            task_id="task-"
            + hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24],
            request_id=request_id,
            request_digest=hashlib.sha256(
                json.dumps(body, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            authorization_ref=authorization_ref,
            scope=scope,
            persona_revision=persona_revision,
            usage=self.usage,
            provider_instance=provider_instance,
            public_traits=tuple(self.public_traits),
            voice_description=self.voice_description,
            reference_text=self.reference_text,
            validation_text=self.validation_text,
            origin_kind="content",
            origin_ref=f"voice_brief:{self.design_id}",
            origin_revision=1,
            execution_scope=execution_scope,
            budget=budget,
        )


class VoiceBriefComposer:
    """Turn what a character has said into a brief that can be cast."""

    def __init__(self, *, refiner: VoiceBriefRefiner | None = None) -> None:
        self._refiner = refiner

    async def compose(self, facts: VoiceBriefFacts) -> ComposedBrief | None:
        """The brief, or ``None`` with a reason the caller can report.

        ``None`` is a real answer and not a failure: a character with one line
        is not castable yet, and pretending otherwise would mean inventing the
        text their voice gets checked against.
        """
        if not facts.presentation_identity.strip():
            return None
        lines = tuple(
            line.strip()
            for line in facts.spoken_lines
            if isinstance(line, str) and len(line.strip()) >= _MIN_LINE
        )
        if len(lines) < 2:
            return None
        # Longest first: the most substantial line carries the most voice, and
        # the cross-text check wants something unlike it.
        reference, validation = lines[0], lines[1]
        if reference == validation:
            return None

        slot = self._slot_for(facts)
        pitch, tempo, texture = _AXIS_SLOTS[slot]
        traits = (pitch, tempo, texture)
        description = (
            f"{facts.display_name or facts.presentation_identity}。"
            f"音高{pitch}，语速{tempo}，音色质地{texture}。"
            "语气依据其公开言行保持一致，不夸张、不播音腔。"
        )
        refined = await self._refine(facts, description, traits)
        return ComposedBrief(
            design_id=f"composed:{facts.presentation_identity}",
            presentation_identity=facts.presentation_identity,
            usage=facts.usage,
            public_traits=traits,
            voice_description=refined or description,
            reference_text=reference[:_MAX_LINE],
            validation_text=validation[:_MAX_LINE],
            slot=slot,
            design_revision=1,
            origin="composed",
        )

    def _slot_for(self, facts: VoiceBriefFacts) -> int:
        """The same character always lands on the same voice.

        Hashed from the identity, not from a clock: a character who is
        re-encountered next week must still sound like themselves, and a
        process that assigned slots by arrival order would change a voice
        every time the engine restarted.
        """
        taken = set(facts.taken_slots)
        start = int(
            hashlib.sha256(
                facts.presentation_identity.encode("utf-8")
            ).hexdigest(),
            16,
        ) % len(_AXIS_SLOTS)
        for offset in range(len(_AXIS_SLOTS)):
            candidate = (start + offset) % len(_AXIS_SLOTS)
            if candidate not in taken:
                return candidate
        # Every slot spoken for. Probing wraps onto someone else's voice,
        # which is the one outcome acceptance 1 forbids — so the last slot is
        # reused rather than a collision being manufactured.
        return len(_AXIS_SLOTS) - 1

    async def _refine(
        self, facts: VoiceBriefFacts, description: str, traits: tuple[str, ...]
    ) -> str | None:
        if self._refiner is None:
            return None
        try:
            polished = await self._refiner.refine(
                presentation_identity=facts.presentation_identity,
                description=description,
                traits=traits,
            )
        except Exception:  # noqa: BLE001 - polish is never allowed to fail a brief
            return None
        if not isinstance(polished, str) or not polished.strip():
            return None
        return polished.strip()[:1000]


def axis_slots() -> tuple[tuple[str, str, str], ...]:
    """Read-only view of the palette, for a caller that must reserve slots."""
    return _AXIS_SLOTS


__all__ = [
    "ComposedBrief",
    "VoiceBriefComposer",
    "VoiceBriefFacts",
    "VoiceBriefRefiner",
    "axis_slots",
]
