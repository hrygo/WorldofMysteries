"""Mysterious AI Gateway Interface. Bounded model dispatch and credential isolation."""
from typing import Protocol


class AIGatewayProtocol(Protocol):
    """Abstract model router and provider switcher."""
