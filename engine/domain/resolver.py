"""Outcome Resolver Interface (Invariant 5 & 9: Deterministic core resolver, commit is fate)."""
from typing import Protocol


class OutcomeResolverProtocol(Protocol):
    """Abstract protocol for resolving AI proposals against domain rules and producing state deltas."""
