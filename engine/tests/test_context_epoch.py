from dataclasses import replace
import pytest

from engine.application.context_compiler import CacheAwareContextCompiler
from engine.application.context_epoch import ContextEpochRegistry
from engine.application.context_plan import ContextError, Evidence, Layer
from engine.tests.test_context_compiler import sample


def plan_with_history(count=1):
    request, view, profile = sample()
    history = tuple(Evidence(f"event{i}", 1, "observation", Layer.HISTORY,
        '{"observed":"bell"}', world_id="world", worldline_id="line",
        committed_revision=i, sequence=i) for i in range(count))
    request = replace(request, world_revision=max(10, count), evidence=request.evidence + history)
    view = replace(view, world_revision=request.world_revision, grants=frozenset(e.fingerprint for e in request.evidence))
    return CacheAwareContextCompiler().compile(request, view, profile)


def test_context_epoch_append_only_and_idempotent():
    registry = ContextEpochRegistry()
    registry.observe(plan_with_history(1))
    registry.observe(plan_with_history(2))
    registry.observe(plan_with_history(2))
    assert len(registry) == 1


@pytest.mark.parametrize("change", ["remove", "rewrite", "baseline"])
def test_context_epoch_rewrite_requires_new_epoch(change):
    registry = ContextEpochRegistry()
    plan = plan_with_history(2)
    registry.observe(plan)
    if change == "remove":
        changed = plan_with_history(1)
    else:
        evidence = list(plan.ordered_evidence)
        index = 0 if change == "baseline" else 1
        evidence[index] = replace(evidence[index], content_json='{"observed":"different"}')
        changed = replace(plan, ordered_evidence=tuple(evidence))
    with pytest.raises(ContextError, match="epoch_rebuild_required"):
        registry.observe(changed)
    registry.observe(replace(changed, context=replace(changed.context, epoch_id="epoch2")))


def test_context_epoch_lru_is_bounded_and_clearable():
    registry = ContextEpochRegistry(max_epochs=2)
    plan = plan_with_history()
    for n in range(5):
        registry.observe(replace(plan, context=replace(plan.context, epoch_id=str(n))))
    assert len(registry) == 2
    registry.clear()
    assert len(registry) == 0


def test_context_epoch_record_budget_not_silent_truncation():
    with pytest.raises(ContextError, match="epoch_record_budget_exceeded"):
        ContextEpochRegistry(max_records=1).observe(plan_with_history(2))


def test_context_epoch_does_not_store_evidence_text():
    registry = ContextEpochRegistry()
    registry.observe(plan_with_history())
    assert "investigator" not in repr(registry._entries)
    assert "observed" not in repr(registry._entries)
