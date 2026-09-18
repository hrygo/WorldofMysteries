"""Authorization-first compilation into a deterministic, provider-neutral IR."""
from __future__ import annotations

from typing import Protocol

from .context_plan import (
    AuthorizationView, ContextError, ContextInput, Evidence, Layer, PromptPlan,
    WorkerProfile,
)

# Defense in depth; these kind labels do NOT grant visibility by themselves.
# Only a fresh exact-content grant from the Domain-owned issuer grants visibility.
_ALLOWED_KINDS = {
    "character_reasoner": frozenset({"canon_known", "character_core", "knowledge",
        "belief", "memory", "observation", "capability", "relationship", "checkpoint"}),
    "story_director": frozenset({"canon", "world_truth", "commitment", "story_state",
        "action_intent", "pressure", "secret", "checkpoint", "observation"}),
    "narrative_compiler": frozenset({"disclosed_fact", "committed_delta", "beat_plan",
        "speaker_intent", "disclosure_policy", "checkpoint"}),
    "advice_interpreter": frozenset({"observation", "available_target"}),
    "memory_distiller": frozenset({"committed_episode", "memory", "knowledge",
        "belief", "relationship"}),
    "story_genesis": frozenset({"canon", "world_truth", "open_thread", "observation"}),
    "world_pulse_planner": frozenset({"world_truth", "open_thread", "pressure"}),
}


class ContextCompilerProtocol(Protocol):
    def compile(self, request: ContextInput, view: AuthorizationView,
                profile: WorkerProfile) -> PromptPlan: ...


class CacheAwareContextCompiler:
    """Consume a pre-authorized selection; never infer permission from similarity.

    This is the final compilation boundary, not the missing Domain retrieval and
    authorization implementation. Registry profiles are application-owned objects.
    Both new evidence and evidence retained from an epoch are rechecked per call.
    """

    @staticmethod
    def _check_evidence(item: Evidence, view: AuthorizationView) -> None:
        if item.fingerprint not in view.grants:
            raise ContextError("evidence_not_authorized")
        if item.kind not in _ALLOWED_KINDS[view.scope.consumer]:
            raise ContextError("consumer_kind_forbidden")
        if item.available_at_tick > view.world_tick:
            raise ContextError("future_evidence")
        if item.world_id is not None and item.world_id != view.scope.world_id:
            raise ContextError("cross_world_evidence")
        if item.subject_id is not None and item.subject_id != view.scope.subject_id:
            raise ContextError("wrong_subject_evidence")
        if item.worldline_id == view.scope.worldline_id:
            if item.committed_revision is None or item.committed_revision > view.world_revision:
                raise ContextError("future_commit")
        elif item.worldline_id is not None:
            limit = dict(view.ancestor_limits).get(item.worldline_id)
            if limit is None or item.committed_revision is None or item.committed_revision > limit:
                raise ContextError("fork_boundary_violation")
        if item.layer == Layer.HISTORY and item.kind in {"action_intent", "beat_plan", "speaker_intent"}:
            raise ContextError("proposal_is_not_history")

    def compile(self, request: ContextInput, view: AuthorizationView,
                profile: WorkerProfile) -> PromptPlan:
        if request.scope != view.scope or profile.consumer != request.scope.consumer:
            raise ContextError("scope_mismatch")
        if profile.consumer not in _ALLOWED_KINDS:
            raise ContextError("unknown_consumer")
        if (request.world_revision, request.story_revision) != (
            view.world_revision, view.story_revision
        ):
            raise ContextError("stale_snapshot")
        seen: set[str] = set()
        sequences: set[int] = set()
        for item in request.evidence:
            self._check_evidence(item, view)
            if item.source_id in seen:
                raise ContextError("duplicate_source")
            seen.add(item.source_id)
            if item.layer == Layer.HISTORY:
                if item.sequence in sequences:
                    raise ContextError("duplicate_history_sequence")
                sequences.add(item.sequence)  # type: ignore[arg-type]
        if not any(e.layer == Layer.STATE for e in request.evidence):
            raise ContextError("missing_current_state")
        # Retrieval ranking selects evidence upstream; only its presentation order
        # is canonicalized here. Arrays inside evidence retain their semantic order.
        ordered = tuple(sorted(request.evidence, key=lambda e: (
            int(e.layer), e.sequence if e.sequence is not None else -1, e.source_id
        )))
        return PromptPlan(profile, request, ordered)
