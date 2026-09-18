"""Strict IPC v1.0 models; kept in parity with contracts/protocol/engine_ipc.schema.json."""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


class IPCErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: str = Field(min_length=1)
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class EngineIPCEnvelope(BaseModel):
    """A kind-checked envelope. Absent fields are omitted, never serialized as null."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["request", "response", "event"]
    protocol_version: Literal["1.0"]
    trace_id: str = Field(min_length=1)
    request_id: str | None = Field(default=None, min_length=1)
    stream_id: str | None = Field(default=None, min_length=1)
    sequence: int | None = Field(default=None, ge=0, le=9223372036854775807)
    story_revision: int | None = Field(default=None, ge=0, le=9223372036854775807)
    turn_id: str | None = Field(default=None, min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=1)
    method: str | None = Field(default=None, min_length=1)
    event: str | None = Field(default=None, min_length=1)
    status: Literal["ok", "error"] | None = None
    error: IPCErrorPayload | None = None
    payload: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_wire_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        common = {"kind", "protocol_version", "trace_id"}
        required = {
            "request": common | {"request_id", "method", "payload"},
            "response": common | {"request_id", "status"},
            "event": common | {"stream_id", "sequence", "event", "payload"},
        }
        allowed = {
            "request": required["request"] | {"idempotency_key"},
            "response": required["response"] | {"payload", "error"},
            "event": required["event"] | {"story_revision", "turn_id"},
        }
        kind = value.get("kind")
        if not isinstance(kind, str) or kind not in required:
            raise ValueError("Invalid IPC kind")
        if required[kind] - value.keys() or value.keys() - allowed[kind]:
            raise ValueError("Missing or forbidden IPC fields for message kind")
        if any(v is None for v in value.values()):
            raise ValueError("Omit optional IPC fields instead of sending null")
        return value

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if self.kind == "response":
            if self.status == "ok" and (self.payload is None or self.error is not None):
                raise ValueError("Successful responses require payload and forbid error")
            if self.status == "error" and (self.error is None or self.payload is not None):
                raise ValueError("Failed responses require error and forbid payload")
        return self

    @model_serializer(mode="wrap")
    def serialize_wire(self, handler: Any) -> dict[str, Any]:
        return {k: v for k, v in handler(self).items() if v is not None}


class HandshakeRequest(BaseModel):
    """Sensitive payload. Validation exceptions must not be logged with input values."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    app_version: str = Field(min_length=1)
    app_build: str = Field(min_length=1)
    supported_protocols: list[str] = Field(min_length=1)
    session_token: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    @model_validator(mode="after")
    def protocols_are_nonempty(self) -> Self:
        if any(not item for item in self.supported_protocols):
            raise ValueError("Protocol names must be nonempty")
        return self


class HandshakeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    engine_version: str = Field(min_length=1)
    engine_build: str = Field(min_length=1)
    python_version: str = Field(min_length=1)
    protocol_version: Literal["1.0"]
    capabilities: list[str]
