"""Where the execution identity of a voice foundry comes from (VF-57).

``FoundryExecutionPolicy`` is a declaration, and a declaration has to come
from somewhere. Until this module it came from nowhere: ``_open_foundry``
built the adapter without one, so every publish died at
``provider_contract_unsupported`` and no voice could ever reach a player.
That is the right failure for a *missing* declaration and the wrong outcome
for a *working* provider — the process was refusing to say what it was,
not refusing to do the work.

The values split three ways, and keeping the split straight is the point of
this module:

**Declared by the deployment.** ``model_id`` is the SpeechRail model
catalog key the cast is rendered by (``tts-1.7b-design-bf16`` and
friends). It cannot be derived from ``AudioProviderConfig.tts_model``, which
is an OpenAI-compatible alias rather than a catalog key, and it cannot be
read back off the provider either — evidence naming whatever the service
just said names nothing. It is declared here and *checked* against the
service's own report when evidence is assembled, which is what turns a
string into a verification.

**Computed from what this build enforces.** ``variant`` and
``validation_policy_revision`` are facts about the pipeline, so they are
constants of the build an operator can override, rather than blanks
somebody has to remember to fill in. ``processing_fingerprint`` is a digest
over the enforced configuration: change the speaking model, the variant, the
policy or the pronunciation revision and the fingerprint changes with it,
so evidence minted under one pipeline cannot be presented as evidence about
another.

**Refused when absent.** ``scope_ref`` is a rights scope — under what grant
these voices may be used. It is not a fact this repository can derive, and
inventing one would put an unearned rights claim into the evidence of every
voice the game ever publishes. A deployment that has not declared it gets no
foundry at all, rather than a foundry that asserts rights nobody granted.
That is the one value here with no default, and the omission is the design.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Mapping

from .config import AudioProviderConfig
from .voice_foundry_adapter import FoundryExecutionPolicy


#: A foundry voice is a clone of a designed recipe, so it renders through
#: SpeechRail's ``custom_voice`` variant. Overridable because a deployment
#: may legitimately move the render path; the default is the true one
#: because a wrong default is a worse failure than a missing value.
DEFAULT_VARIANT = "custom_voice"

#: Names the validation policy this build enforces. Bump it when the rules a
#: cross-text check applies change; evidence minted under an older policy
#: keeps the revision it was minted with, which is the point of carrying it.
DEFAULT_VALIDATION_POLICY_REVISION = "wom-voice-validation-v1"

#: The pronunciation dictionary the sealing path normalizes text against. It
#: changes what the model is asked to say, so it belongs in the fingerprint.
DEFAULT_DICTIONARY_REVISION = "wom-zh-cn-v1"

_ABSENT = ""


def _allowed_usages(raw: str) -> frozenset[str]:
    if not raw:
        return frozenset({"dialogue", "narration"})
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def processing_fingerprint(
    *,
    provider_name: str,
    model_id: str,
    variant: str,
    validation_policy_revision: str,
    dictionary_revision: str,
) -> str:
    """Digest the configuration this build actually enforces.

    A digest rather than a version string because the inputs are several and
    only the combination matters: bumping the dictionary and the model in
    one release must not be able to reuse a fingerprint that either change
    would have invalidated on its own.
    """
    payload = json.dumps(
        {
            "provider": provider_name,
            "model_id": model_id,
            "variant": variant,
            "validation_policy_revision": validation_policy_revision,
            "dictionary_revision": dictionary_revision,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def execution_policy(
    config: AudioProviderConfig,
    *,
    env: Mapping[str, str] | None = None,
    dictionary_revision: str = DEFAULT_DICTIONARY_REVISION,
) -> FoundryExecutionPolicy | None:
    """The policy this deployment enforces, or ``None`` when it has not said.

    ``None`` is the answer for a deployment missing its rights scope or its
    model, and the caller is expected to read it as "no foundry" rather than
    "a foundry with a blank field". The adapter accepts a missing policy and
    refuses at publish; declining to advertise the surface at all is the
    same decision made earlier and more legibly.
    """
    read = env if env is not None else os.environ
    scope_ref = (read.get("WOM_FOUNDRY_SCOPE_REF") or _ABSENT).strip()
    model_id = (read.get("WOM_FOUNDRY_MODEL_ID") or _ABSENT).strip()
    if not scope_ref or not model_id:
        return None
    variant = (
        (read.get("WOM_FOUNDRY_VARIANT") or _ABSENT).strip() or DEFAULT_VARIANT
    )
    policy_revision = (
        (read.get("WOM_FOUNDRY_VALIDATION_POLICY") or _ABSENT).strip()
        or DEFAULT_VALIDATION_POLICY_REVISION
    )
    revision = dictionary_revision or DEFAULT_DICTIONARY_REVISION
    return FoundryExecutionPolicy(
        model_id=model_id,
        variant=variant,
        validation_policy_revision=policy_revision,
        processing_fingerprint=processing_fingerprint(
            provider_name=config.provider_name,
            model_id=model_id,
            variant=variant,
            validation_policy_revision=policy_revision,
            dictionary_revision=revision,
        ),
        allowed_usages=_allowed_usages(
            (read.get("WOM_FOUNDRY_ALLOWED_USAGES") or _ABSENT).strip()
        ),
        scope_ref=scope_ref,
    )


__all__ = [
    "DEFAULT_DICTIONARY_REVISION",
    "DEFAULT_VALIDATION_POLICY_REVISION",
    "DEFAULT_VARIANT",
    "execution_policy",
    "processing_fingerprint",
]
