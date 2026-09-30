"""The silent half of the two entry points (VF-51).

There are two ways a voice gets asked for, and they are deliberately not
alternatives:

* the App's **铸造音色** button — a person saying "cast this", and
* **first appearance** — a character opening their mouth in a scene with no
  voice bound.

The second one used to end in silence: the audio job reported
``voice_binding_not_reviewed`` and the character simply had no voice, until
somebody thought to press Retry. This is the piece that notices.

**Automatic does not mean interrupting.** The whole design rests on keeping
those two apart, because a player who is mid-conversation does not want a
dialogue about casting every time a new NPC clears their throat. So this
module never surfaces anything on its own. It opens a task and returns; the
background driver (VF-48) advances it; the text has already been delivered by
then. Whether a person is *owed* something is a separate question with a
separate answer, and it is read from the durable record rather than decided
here — ``awaiting_person`` is true only when ``required_actions`` is
non-empty, because whoever last moved the task decided what a person owes
next, and a second opinion at this level could contradict the very buttons the
App is already rendering.

**It cannot fail the turn.** This runs inside an audio job whose text has
already been published. A casting that could not start is a supply problem,
not a story problem, so every failure collapses to a reason code and the
audio outcome is exactly what it would have been without this call.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from domain.voice_identity import VoiceBindingScope
from infrastructure.voice_foundry_repository import VoiceFoundryTaskSpec

from .voice_foundry_service import VoiceSupplyOutcome, VoiceSupplyResult


class VoiceDesignLookup(Protocol):
    """The catalog, by identity.

    Injected rather than imported so the policy here can be exercised against
    a two-identity catalog in a unit test and against the shipped
    five-identity one in production, without either pretending to be the other.
    """

    def __contains__(self, presentation_identity: object) -> bool: ...

    def get(self, presentation_identity: str) -> object: ...


class VoiceSupplyPort(Protocol):
    """The two supply verbs this needs, and nothing else."""

    async def precheck(self, scope: VoiceBindingScope) -> VoiceSupplyResult: ...

    async def request(self, spec: VoiceFoundryTaskSpec) -> VoiceSupplyResult: ...


@dataclass(frozen=True, slots=True)
class VoiceSupplyTriggerResult:
    """What one silent check did, and whether a person is now owed a decision."""

    #: A casting task was opened by this call. False means there was nothing to
    #: open — the voice already exists, a task is already in flight, or this
    #: identity has no design.
    requested: bool
    #: ``required_actions`` is non-empty: somebody must choose a candidate or
    #: sign a review before supply can continue. This is the *only* condition
    #: under which interrupting the player is justified.
    awaiting_person: bool
    reason_code: str | None = None


class VoiceSupplyTrigger:
    """Notice a voiceless first appearance, and quietly start casting for it."""

    def __init__(
        self,
        *,
        supply: VoiceSupplyPort,
        designs: VoiceDesignLookup,
        provider_instance: str,
        authorization_ref: str = "auto:voice-supply",
    ) -> None:
        self._supply = supply
        self._designs = designs
        self._provider_instance = provider_instance
        self._authorization_ref = authorization_ref

    async def ensure(
        self, scope: VoiceBindingScope, *, request_id: str | None = None
    ) -> VoiceSupplyTriggerResult:
        """Open a casting for ``scope`` if one is needed. Never raises.

        The pre-check runs first because it is the only step with no side
        effects: it answers, from the binding and the task history, whether
        anything is already under way. Only a scope that has never been asked
        for reaches the write, which is what keeps a character who speaks every
        turn from registering a task per turn.
        """
        if scope.presentation_identity not in self._designs:
            # Not an error. A world holds identities nobody has designed a
            # voice for, and inventing a brief for one here would be the
            # supply chain deciding what a character sounds like.
            return VoiceSupplyTriggerResult(False, False, "voice_design_absent")
        try:
            existing = await self._supply.precheck(scope)
            if existing.outcome is VoiceSupplyOutcome.READY:
                return VoiceSupplyTriggerResult(False, False)
            if existing.state is not None:
                # Already asked. The driver owns it now; a second request
                # would spend provider budget putting a duplicate candidate in
                # front of the same listener.
                return VoiceSupplyTriggerResult(
                    False, bool(existing.state.required_actions)
                )
            design = self._designs.get(scope.presentation_identity)
            result = await self._supply.request(
                design.task_spec(  # type: ignore[attr-defined]
                    scope=scope,
                    request_id=request_id or _automatic_request_id(scope, design),  # type: ignore[arg-type]
                    persona_revision=f"persona-{design.design_revision}",  # type: ignore[attr-defined]
                    authorization_ref=self._authorization_ref,
                    provider_instance=self._provider_instance,
                )
            )
        except Exception:  # noqa: BLE001 - an audio job must not fail for this
            return VoiceSupplyTriggerResult(
                False, False, "voice_supply_trigger_failed"
            )
        return VoiceSupplyTriggerResult(
            requested=True,
            awaiting_person=bool(
                result.state is not None and result.state.required_actions
            ),
        )


def _automatic_request_id(
    scope: VoiceBindingScope, design: object
) -> str:
    """A request id that is the same every time this cast is warranted.

    Derived from what the casting *is* — this world, this worldline, this
    identity, this phase, this persona revision — rather than from a clock or a
    counter. Two turns that each discover the same voiceless character
    therefore address one task, so a character who speaks often cannot open a
    queue of near-identical candidates, and a retry after a crash resumes the
    same row instead of starting a second one.
    """
    seed = "|".join(
        (
            scope.world_id,
            scope.worldline_id,
            scope.presentation_identity,
            scope.phase,
            f"persona-{design.design_revision}",  # type: ignore[attr-defined]
        )
    )
    return "auto-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


__all__ = [
    "VoiceDesignLookup",
    "VoiceSupplyPort",
    "VoiceSupplyTrigger",
    "VoiceSupplyTriggerResult",
]
