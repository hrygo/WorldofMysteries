from dataclasses import replace

import pytest

from domain.context_visibility import (
    ContextConsumer,
    ContextFact,
    ContextIdentity,
    ContextVisibilityError,
    authorize_candidates,
    issue_eligibility,
)


def identity(subject_id: str, *, world_revision: int = 7) -> ContextIdentity:
    return ContextIdentity(
        owner_id="owner",
        world_id="world",
        worldline_id="line",
        subject_id=subject_id,
        session_id="session",
        consumer=ContextConsumer.CHARACTER_REASONER,
        world_revision=world_revision,
        world_tick=12,
    )


def fact(
    source_id: str,
    *,
    subject_id: str | None = None,
    known_by: tuple[str, ...] = (),
    public: bool = False,
    disclosed_to_owner: bool = False,
    hidden: bool = False,
    committed_world_revision: int | None = 3,
    content_json: str = '{"proposition":"the door is open"}',
) -> ContextFact:
    return ContextFact(
        source_id=source_id,
        source_revision=1,
        owner_id="owner",
        world_id="world",
        worldline_id="line",
        session_id="session",
        subject_id=subject_id,
        committed_world_revision=committed_world_revision,
        available_at_tick=4,
        content_json=content_json,
        known_by_subject_ids=known_by,
        public=public,
        disclosed_to_owner=disclosed_to_owner,
        hidden=hidden,
    )


def test_character_eligibility_isolated_by_subject() -> None:
    facts = (
        fact("private-a", subject_id="character-a", known_by=("character-a",)),
        fact("private-b", subject_id="character-b", known_by=("character-b",)),
        fact("public-but-unknown-to-a", public=True, known_by=("character-b",)),
    )

    eligible_a = issue_eligibility(identity("character-a"), facts)
    eligible_b = issue_eligibility(identity("character-b"), facts)

    assert eligible_a.source_ids == frozenset({"private-a"})
    assert eligible_b.source_ids == frozenset({"private-b", "public-but-unknown-to-a"})


def test_hidden_and_uncommitted_facts_are_not_eligible() -> None:
    facts = (
        fact("visible", subject_id="character-a", known_by=("character-a",)),
        fact(
            "hidden",
            subject_id="character-a",
            known_by=("character-a",),
            public=True,
            disclosed_to_owner=True,
            hidden=True,
        ),
        fact(
            "pending-candidate",
            subject_id="character-a",
            known_by=("character-a",),
            committed_world_revision=None,
        ),
    )

    eligible = issue_eligibility(identity("character-a"), facts)

    assert eligible.source_ids == frozenset({"visible"})


@pytest.mark.parametrize(
    "consumer",
    (ContextConsumer.ADVICE_INTERPRETER, ContextConsumer.NARRATIVE_COMPILER),
)
def test_player_consumers_require_public_or_owner_disclosure(
    consumer: ContextConsumer,
) -> None:
    caller = replace(identity("character-a"), subject_id=None, consumer=consumer)
    facts = (
        fact("public", public=True),
        fact("disclosed", disclosed_to_owner=True),
        fact("private-character-knowledge", known_by=("character-a",)),
    )

    eligibility = issue_eligibility(caller, facts)

    assert eligibility.source_ids == frozenset({"public", "disclosed"})


def test_eligibility_is_derived_before_candidate_selection() -> None:
    trusted_snapshot = (fact("known-to-a", known_by=("character-a",)),)

    eligibility = issue_eligibility(identity("character-a"), trusted_snapshot)

    assert eligibility.source_ids == frozenset({"known-to-a"})
    # Retrieval candidates are a separate, later input and can only be filtered
    # through the eligibility result.
    authorization = authorize_candidates(
        eligibility,
        (fact("known-to-a", known_by=("character-a",)),),
    )
    assert authorization.source_ids == frozenset({"known-to-a"})


def test_authorization_is_only_a_subset_of_retrieval_candidates() -> None:
    eligible = fact("eligible", known_by=("character-a",))
    not_eligible = fact("outside", known_by=("character-b",))
    eligibility = issue_eligibility(
        identity("character-a"),
        (eligible,),
    )

    authorization = authorize_candidates(
        eligibility,
        (eligible, not_eligible),
    )

    assert authorization.source_ids == frozenset({"eligible"})
    assert authorization.grants == frozenset({eligible.fingerprint})

    no_eligible_candidates = authorize_candidates(eligibility, (not_eligible,))

    assert no_eligible_candidates.source_ids == frozenset()
    assert no_eligible_candidates.grants == frozenset()


def test_changed_content_invalidates_an_existing_eligibility() -> None:
    original = fact("knowledge", known_by=("character-a",))
    eligibility = issue_eligibility(identity("character-a"), (original,))
    changed = replace(
        original,
        content_json='{"proposition":"the door is locked"}',
    )

    with pytest.raises(ContextVisibilityError, match="context_source_changed"):
        authorize_candidates(eligibility, (changed,))


def test_future_commit_and_cross_scope_facts_are_not_eligible() -> None:
    identity_a = identity("character-a", world_revision=7)
    facts = (
        fact("future", known_by=("character-a",), committed_world_revision=8),
        replace(fact("other-world", known_by=("character-a",)), world_id="other"),
        replace(fact("other-owner", known_by=("character-a",)), owner_id="other"),
        replace(fact("future-tick", known_by=("character-a",)), available_at_tick=13),
    )

    eligibility = issue_eligibility(identity_a, facts)

    assert eligibility.source_ids == frozenset()
