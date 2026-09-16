"""Unix Domain Socket IPC Server Interface (Invariant 12: App does not direct connect to DB)."""
from typing import Protocol


class IPCServerProtocol(Protocol):
    """IPC transport listener serving NDJSON / length-prefixed requests to macOS App."""
