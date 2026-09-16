"""IPC Protocol Envelope Models (Pydantic v2)."""

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class IPCErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class EngineIPCEnvelope(BaseModel):
    """Standard Envelope for Unix Domain Socket IPC between macOS App and Local Engine."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["request", "response", "event"]
    protocol_version: Literal["1.0"] = "1.0"
    trace_id: str = Field(min_length=1)
    request_id: Optional[str] = None
    stream_id: Optional[str] = None
    sequence: Optional[int] = None
    idempotency_key: Optional[str] = None
    method: Optional[str] = None
    event: Optional[str] = None
    status: Optional[Literal["ok", "error"]] = None
    error: Optional[IPCErrorPayload] = None
    payload: dict[str, Any] = Field(default_factory=dict)
