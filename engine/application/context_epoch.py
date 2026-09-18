"""Bounded, process-local prefix continuity checks; never an authorization cache."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict
from threading import Lock

from .context_plan import ContextError, Layer, PromptPlan, digest


class ContextEpochRegistry:
    """Store fingerprints only. Call only after fresh authorization has succeeded.

    Eviction removes a performance/continuity hint, not Domain truth. The trusted
    caller remains responsible for allocating a new epoch after reconstruction.
    One session/policy/lineage/epoch cannot silently rewrite its frozen baseline.
    """
    def __init__(self, max_epochs: int = 64, max_records: int = 4096):
        if type(max_epochs) is not int or type(max_records) is not int or min(max_epochs, max_records) < 1:
            raise ValueError("invalid_epoch_limits")
        self._max_epochs, self._max_records = max_epochs, max_records
        self._entries: OrderedDict[str, tuple[tuple[str, ...], tuple[str, ...]]] = OrderedDict()
        self._lock = Lock()

    def observe(self, plan: PromptPlan) -> None:
        context, profile = plan.context, plan.profile
        key = digest({"scope": asdict(context.scope), "epoch": context.epoch_id,
                      "prompt": profile.prompt_revision, "instructions": profile.instructions,
                      "schema": profile.schema_json, "tools": profile.tools_json,
                      "compiler": plan.compiler_revision})
        frozen = tuple(e.fingerprint for e in plan.stable_evidence if e.layer != Layer.HISTORY)
        history = tuple(e.fingerprint for e in plan.stable_evidence if e.layer == Layer.HISTORY)
        if len(frozen) + len(history) > self._max_records:
            raise ContextError("epoch_record_budget_exceeded")
        with self._lock:
            previous = self._entries.get(key)
            if previous is not None:
                old_frozen, old_history = previous
                if frozen != old_frozen or history[:len(old_history)] != old_history:
                    raise ContextError("epoch_rebuild_required")
            self._entries[key] = (frozen, history)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_epochs:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        """Use on world deletion/logout; no source content is retained here."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
