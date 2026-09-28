"""Pure Domain policy for facts eligible to enter a gameplay context.

The input facts must be materialized from a trusted committed snapshot. Their
audience metadata is source data, not a caller or model assertion. This module
does not retrieve facts or access persistence; callers issue eligibility before
retrieval and use ``authorize_candidates`` only to narrow retrieved candidates.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class ContextVisibilityError(ValueError):
    """A context fact or authorization boundary is invalid."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ContextConsumer(StrEnum):
    ADVICE_INTERPRETER = "advice_interpreter"
    CHARACTER_REASONER = "character_reasoner"
    NARRATIVE_COMPILER = "narrative_compiler"


def _identifier(value: str | None, field: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ContextVisibilityError(f"invalid_{field}")


def _natural(value: int, field: str) -> None:
    if type(value) is not int or value < 0:
        raise ContextVisibilityError(f"invalid_{field}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"nonfinite_json_number:{value}")


def _canonical_json(text: str) -> str:
    if not isinstance(text, str):
        raise ContextVisibilityError("invalid_content_json")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (ValueError, TypeError, RecursionError):
        raise ContextVisibilityError("invalid_content_json") from None


@dataclass(frozen=True, slots=True)
class ContextIdentity:
    """The trusted caller scope and read boundary for one context decision."""

    owner_id: str
    world_id: str
    worldline_id: str
    subject_id: str | None
    session_id: str | None
    consumer: ContextConsumer
    world_revision: int
    world_tick: int
    ancestor_limits: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        for field in ("owner_id", "world_id", "worldline_id"):
            _identifier(getattr(self, field), field)
        _identifier(self.subject_id, "subject_id", optional=True)
        _identifier(self.session_id, "session_id", optional=True)
        try:
            consumer = ContextConsumer(self.consumer)
        except (TypeError, ValueError):
            raise ContextVisibilityError("invalid_consumer") from None
        object.__setattr__(self, "consumer", consumer)
        if consumer == ContextConsumer.CHARACTER_REASONER and self.subject_id is None:
            raise ContextVisibilityError("character_subject_required")
        _natural(self.world_revision, "world_revision")
        _natural(self.world_tick, "world_tick")

        limits: list[tuple[str, int]] = []
        seen: set[str] = set()
        for worldline_id, revision in self.ancestor_limits:
            _identifier(worldline_id, "ancestor_worldline_id")
            _natural(revision, "ancestor_revision")
            if worldline_id == self.worldline_id or worldline_id in seen:
                raise ContextVisibilityError("invalid_ancestor_limits")
            seen.add(worldline_id)
            limits.append((worldline_id, revision))
        object.__setattr__(self, "ancestor_limits", tuple(sorted(limits)))


@dataclass(frozen=True, slots=True)
class ContextFact:
    """One trusted source projection from a committed read snapshot.

    ``known_by_subject_ids`` and ``disclosed_to_owner`` must come from
    Domain-owned knowledge/disclosure state. They must never be copied from a
    prompt, model proposal, or arbitrary retrieval candidate.
    """

    source_id: str
    source_revision: int
    owner_id: str
    world_id: str
    worldline_id: str
    session_id: str | None
    subject_id: str | None
    committed_world_revision: int | None
    available_at_tick: int
    content_json: str
    known_by_subject_ids: tuple[str, ...] = ()
    public: bool = False
    disclosed_to_owner: bool = False
    hidden: bool = False

    def __post_init__(self) -> None:
        for field in ("source_id", "owner_id", "world_id", "worldline_id"):
            _identifier(getattr(self, field), field)
        _identifier(self.session_id, "session_id", optional=True)
        _identifier(self.subject_id, "subject_id", optional=True)
        _natural(self.source_revision, "source_revision")
        _natural(self.available_at_tick, "available_at_tick")
        if self.committed_world_revision is not None:
            _natural(self.committed_world_revision, "committed_world_revision")
        if any(type(value) is not bool for value in (self.public, self.disclosed_to_owner, self.hidden)):
            raise ContextVisibilityError("invalid_visibility_metadata")

        known_by: list[str] = []
        for subject_id in self.known_by_subject_ids:
            _identifier(subject_id, "known_by_subject_id")
            known_by.append(subject_id)
        if len(set(known_by)) != len(known_by):
            raise ContextVisibilityError("duplicate_known_by_subject")
        object.__setattr__(self, "known_by_subject_ids", tuple(sorted(known_by)))
        object.__setattr__(self, "content_json", _canonical_json(self.content_json))

    @property
    def fingerprint(self) -> str:
        """Hash all source content, provenance, and trusted visibility inputs."""
        payload = {
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "owner_id": self.owner_id,
            "world_id": self.world_id,
            "worldline_id": self.worldline_id,
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "committed_world_revision": self.committed_world_revision,
            "available_at_tick": self.available_at_tick,
            "content_json": self.content_json,
            "known_by_subject_ids": self.known_by_subject_ids,
            "public": self.public,
            "disclosed_to_owner": self.disclosed_to_owner,
            "hidden": self.hidden,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorizedSource:
    source_id: str
    source_revision: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ContextEligibility:
    """Domain-issued pre-retrieval eligible set for one immutable caller scope."""

    identity: ContextIdentity
    sources: tuple[AuthorizedSource, ...]

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(source.source_id for source in self.sources)


@dataclass(frozen=True, slots=True)
class ContextAuthorization:
    """Candidate subset authorized by an earlier eligibility decision."""

    identity: ContextIdentity
    sources: tuple[AuthorizedSource, ...]

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(source.source_id for source in self.sources)

    @property
    def grants(self) -> frozenset[str]:
        return frozenset(source.fingerprint for source in self.sources)


def _fact_is_eligible(fact: ContextFact, identity: ContextIdentity) -> bool:
    if fact.owner_id != identity.owner_id or fact.world_id != identity.world_id:
        return False
    if fact.hidden or fact.committed_world_revision is None:
        return False
    if fact.available_at_tick > identity.world_tick:
        return False
    if fact.session_id is not None and fact.session_id != identity.session_id:
        return False
    if fact.subject_id is not None and fact.subject_id != identity.subject_id:
        return False

    if fact.worldline_id == identity.worldline_id:
        if fact.committed_world_revision > identity.world_revision:
            return False
    else:
        ancestor_limit = dict(identity.ancestor_limits).get(fact.worldline_id)
        if ancestor_limit is None or fact.committed_world_revision > ancestor_limit:
            return False

    if identity.consumer == ContextConsumer.CHARACTER_REASONER:
        return identity.subject_id in fact.known_by_subject_ids
    return fact.public or fact.disclosed_to_owner


def issue_eligibility(
    identity: ContextIdentity,
    facts: Iterable[ContextFact],
) -> ContextEligibility:
    """Issue eligibility using only trusted snapshot facts and caller identity.

    Retrieval output is intentionally not an input: this decision can therefore
    be made before any facet reads or candidate collection.
    """
    if not isinstance(identity, ContextIdentity):
        raise ContextVisibilityError("invalid_context_identity")
    materialized = tuple(facts)
    if any(not isinstance(fact, ContextFact) for fact in materialized):
        raise ContextVisibilityError("invalid_context_fact")
    source_ids = [fact.source_id for fact in materialized]
    if len(set(source_ids)) != len(source_ids):
        raise ContextVisibilityError("duplicate_context_source")

    eligible = (
        AuthorizedSource(fact.source_id, fact.source_revision, fact.fingerprint)
        for fact in materialized
        if _fact_is_eligible(fact, identity)
    )
    return ContextEligibility(
        identity=identity,
        sources=tuple(sorted(eligible, key=lambda source: source.source_id)),
    )


def authorize_candidates(
    eligibility: ContextEligibility,
    candidates: Iterable[ContextFact],
) -> ContextAuthorization:
    """Authorize only candidates matching an eligible source's full fingerprint.

    A candidate with an eligible source id but changed content or provenance
    invalidates the old decision and must be re-materialized/re-authorized.
    Candidates absent from the pre-retrieval eligible set are simply excluded.
    """
    if not isinstance(eligibility, ContextEligibility):
        raise ContextVisibilityError("invalid_context_eligibility")
    materialized = tuple(candidates)
    if any(not isinstance(candidate, ContextFact) for candidate in materialized):
        raise ContextVisibilityError("invalid_context_candidate")
    source_ids = [candidate.source_id for candidate in materialized]
    if len(set(source_ids)) != len(source_ids):
        raise ContextVisibilityError("duplicate_context_candidate")

    eligible_by_id = {source.source_id: source for source in eligibility.sources}
    authorized: list[AuthorizedSource] = []
    for candidate in materialized:
        eligible = eligible_by_id.get(candidate.source_id)
        if eligible is None:
            continue
        if candidate.fingerprint != eligible.fingerprint:
            raise ContextVisibilityError("context_source_changed")
        authorized.append(eligible)

    return ContextAuthorization(
        identity=eligibility.identity,
        sources=tuple(sorted(authorized, key=lambda source: source.source_id)),
    )
