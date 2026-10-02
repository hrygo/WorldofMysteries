"""Where a casting request's *content* comes from (VF-50).

Everything the supply chain needs to open a task already existed and was
already exercised — ``VoiceFoundryTaskSpec``, the digest the control surface
recomputes, the driver that advances the stages. What did not exist was the
one input none of them can invent: **what this character should sound like**.
The five casting inputs lived in a Markdown document and a ``scratch/``
directory, so the two entry points now being built — the App button and the
silent first-appearance trigger — would each have had to ask a human to type
the same prose, or ship with nothing to cast.

So the prose moves here, once, as content the engine loads at runtime.

**What may go in this file, and what may not.** A design is *only* what a
voice actor needs to be told: timbre, pitch, pace, and two lines to read. It
is not a character dossier. Hidden identity, canon anchors, and anything about
unplayed plot are refused at load time rather than merely left out — see
``_ALLOWED_KEYS`` and ``canon_anchor``. A preview, a prompt and a log line all
read from this record, so a field that carries a secret would leak it three
ways at once, and "we did not think to use it" is not a control.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from domain.voice_identity import VoiceBindingScope

from .voice_foundry_repository import (
    DEFAULT_CAST_BUDGET,
    DEFAULT_EXECUTION_SCOPE,
    VoiceCastBudget,
    VoiceExecutionScope,
    VoiceFoundryTaskSpec,
)

#: Module-relative, for the same reason the five-turn catalog is: a shipped
#: engine resolves its content next to the installed module, never from a
#: repository directory, a fixture path or the current working directory.
CATALOG_PATH = Path(__file__).resolve().parent / "voice_designs" / "catalog.json"

#: Exactly the keys one design may carry. A design that grows a field the
#: loader does not understand is rejected instead of ignored: an unrecognized
#: key is either a typo that silently casts the wrong voice, or — worse —
#: dossier data that reached a surface a listener and a log both read.
_ALLOWED_KEYS = frozenset(
    {
        "design_id",
        "display_name",
        "presentation_identity",
        "usage",
        "locale",
        "kind",
        "canon_anchor",
        "design_revision",
        "public_traits",
        "voice_description",
        "reference_text",
        "validation_text",
    }
)

_CATALOG_KEYS = frozenset({"catalog_version", "identities"})


class VoiceDesignError(ValueError):
    """The catalog cannot be trusted well enough to cast from."""


@dataclass(frozen=True, slots=True)
class VoiceDesign:
    """One identity's public casting brief."""

    design_id: str
    display_name: str
    presentation_identity: str
    usage: str
    locale: str
    design_revision: int
    public_traits: tuple[str, ...]
    voice_description: str
    reference_text: str
    validation_text: str

    def request_body(
        self,
        *,
        scope: VoiceBindingScope,
        request_id: str,
        persona_revision: str,
        authorization_ref: str,
        provider_instance: str,
        execution_scope: VoiceExecutionScope = DEFAULT_EXECUTION_SCOPE,
        budget: VoiceCastBudget = DEFAULT_CAST_BUDGET,
    ) -> dict[str, object]:
        """The exact ``voice.foundry.request`` payload this design casts with.

        One builder, two callers: the App button posts this verbatim, and the
        silent trigger hands it to the same supply service in-process. If the
        two grew their own bodies they would drift, and the drift would show
        up as a button that casts a subtly different voice from the automatic
        path — for the same character, in the same world.

        The digest is computed here rather than trusted from the caller, over
        the same canonical form the control surface recomputes, so a payload
        edited in transit is a rejection rather than a second casting.
        """
        body: dict[str, object] = {
            "schema_version": "1.0",
            "request_id": request_id,
            "authorization_ref": authorization_ref,
            "scope": {
                "owner_id": scope.owner_id,
                "world_id": scope.world_id,
                "worldline_id": scope.worldline_id,
                "presentation_identity": scope.presentation_identity,
                "phase": scope.phase,
                "locale": scope.locale,
            },
            "persona_revision": persona_revision,
            "usage": self.usage,
            "locale": self.locale,
            "public_traits": list(self.public_traits),
            "voice_description": self.voice_description,
            "reference_text": self.reference_text,
            "validation_text": self.validation_text,
            "provider_instance": provider_instance,
            "requested_execution_scope": {
                "model_id": execution_scope.model_id,
                "model_artifact_revision": execution_scope.model_artifact_revision,
                "variant": execution_scope.variant,
            },
            "budget": {
                "candidate_count": budget.candidate_count,
                "timeout_ms": budget.timeout_ms,
                "max_audio_bytes": budget.max_audio_bytes,
            },
            "origin": {
                "kind": "content",
                "source_ref": f"voice_design:{self.design_id}",
                "source_revision": self.design_revision,
            },
        }
        body["request_digest"] = _digest(body)
        return body

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
        """The durable form of :meth:`request_body`, for the in-process path."""
        body = self.request_body(
            scope=scope,
            request_id=request_id,
            persona_revision=persona_revision,
            authorization_ref=authorization_ref,
            provider_instance=provider_instance,
            execution_scope=execution_scope,
            budget=budget,
        )
        origin = body["origin"]
        execution = body["requested_execution_scope"]
        limits = body["budget"]
        assert isinstance(origin, dict) and isinstance(execution, dict)
        assert isinstance(limits, dict)
        return VoiceFoundryTaskSpec(
            # Derived, exactly as the control surface derives it: one request
            # id addresses one task row, with nothing for a caller to remember.
            task_id="task-"
            + hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24],
            request_id=request_id,
            request_digest=str(body["request_digest"]),
            authorization_ref=authorization_ref,
            scope=scope,
            persona_revision=persona_revision,
            usage=self.usage,
            provider_instance=provider_instance,
            public_traits=tuple(self.public_traits),
            voice_description=self.voice_description,
            reference_text=self.reference_text,
            validation_text=self.validation_text,
            origin_kind=str(origin["kind"]),
            origin_ref=str(origin["source_ref"]),
            origin_revision=self.design_revision,
            execution_scope=VoiceExecutionScope(
                variant=str(execution["variant"]),
                model_id=execution["model_id"],
                model_artifact_revision=execution["model_artifact_revision"],
            ),
            budget=VoiceCastBudget(
                candidate_count=int(limits["candidate_count"]),  # type: ignore[arg-type]
                timeout_ms=int(limits["timeout_ms"]),  # type: ignore[arg-type]
                max_audio_bytes=int(limits["max_audio_bytes"]),  # type: ignore[arg-type]
            ),
        )


@dataclass(frozen=True, slots=True)
class VoiceDesignCatalog:
    """The loaded designs, addressable by the identity a scope names."""

    catalog_version: str
    designs: tuple[VoiceDesign, ...]

    def get(self, presentation_identity: str) -> VoiceDesign:
        for design in self.designs:
            if design.presentation_identity == presentation_identity:
                return design
        raise VoiceDesignError("voice_design_not_found")

    def __contains__(self, presentation_identity: object) -> bool:
        return any(
            design.presentation_identity == presentation_identity
            for design in self.designs
        )


def _digest(payload: dict[str, object]) -> str:
    """Canonical digest, byte-identical to the control surface's recomputation."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VoiceDesignError(f"voice_design_field_invalid:{field}")
    return value.strip()


def _design_from(entry: object) -> VoiceDesign:
    if not isinstance(entry, dict):
        raise VoiceDesignError("voice_design_entry_invalid")
    unknown = sorted(set(entry) - _ALLOWED_KEYS)
    if unknown:
        raise VoiceDesignError(f"voice_design_unknown_field:{unknown[0]}")
    missing = sorted(_ALLOWED_KEYS - set(entry))
    if missing:
        raise VoiceDesignError(f"voice_design_missing_field:{missing[0]}")
    # Invariant 10 at the point it would otherwise be violated. These five are
    # user-world originals; a design that grew a canon anchor would make a
    # preview, a prompt and a publication record carry canon identity into a
    # world that must never write back to it.
    if entry["canon_anchor"] is not None:
        raise VoiceDesignError("voice_design_must_not_anchor_canon")
    if entry["kind"] != "original":
        raise VoiceDesignError("voice_design_kind_unsupported")
    usage = _text(entry["usage"], "usage").casefold()
    if usage not in {"dialogue", "narration"}:
        raise VoiceDesignError("voice_design_usage_invalid")
    traits = entry["public_traits"]
    if not isinstance(traits, list) or not all(
        isinstance(item, str) and item.strip() for item in traits
    ):
        raise VoiceDesignError("voice_design_traits_invalid")
    revision = entry["design_revision"]
    if type(revision) is not int or revision < 1:
        raise VoiceDesignError("voice_design_revision_invalid")
    reference = _text(entry["reference_text"], "reference_text")
    validation = _text(entry["validation_text"], "validation_text")
    # A cross-text check against the same sentence proves nothing, and would
    # be accepted silently: the catalog is content, and content is edited by
    # hand long after the tests that justify this were written.
    if reference == validation:
        raise VoiceDesignError("voice_design_validation_text_repeats_reference")
    return VoiceDesign(
        design_id=_text(entry["design_id"], "design_id"),
        display_name=_text(entry["display_name"], "display_name"),
        presentation_identity=_text(
            entry["presentation_identity"], "presentation_identity"
        ),
        usage=usage,
        locale=_text(entry["locale"], "locale"),
        design_revision=revision,
        public_traits=tuple(item.strip() for item in traits),
        voice_description=_text(entry["voice_description"], "voice_description"),
        reference_text=reference,
        validation_text=validation,
    )


def load_voice_design_catalog(
    path: Path | None = None,
) -> VoiceDesignCatalog:
    """Read and refuse anything this engine will not cast from."""
    source = CATALOG_PATH if path is None else Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise VoiceDesignError("voice_design_catalog_unreadable") from error
    if not isinstance(payload, dict) or set(payload) != _CATALOG_KEYS:
        raise VoiceDesignError("voice_design_catalog_shape_invalid")
    entries = payload["identities"]
    if not isinstance(entries, list) or not entries:
        raise VoiceDesignError("voice_design_catalog_empty")
    designs = tuple(_design_from(entry) for entry in entries)
    identities = [design.presentation_identity for design in designs]
    if len(set(identities)) != len(identities):
        # Two designs for one identity would make "which voice does this
        # character have" depend on file order.
        raise VoiceDesignError("voice_design_identity_duplicated")
    if sum(1 for design in designs if design.usage == "narration") > 1:
        # Acceptance 1 asks for one narrator voice that is nobody else's. Two
        # narrator designs make "the narrator" ambiguous at render time.
        raise VoiceDesignError("voice_design_narrator_ambiguous")
    return VoiceDesignCatalog(
        catalog_version=_text(payload["catalog_version"], "catalog_version"),
        designs=designs,
    )


__all__ = [
    "CATALOG_PATH",
    "VoiceDesign",
    "VoiceDesignCatalog",
    "VoiceDesignError",
    "load_voice_design_catalog",
]
