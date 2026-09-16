# IPC Protocol v1.0

> **状态**：SwiftUI App ↔ Local Engine 通信基线  
> **Transport**：Unix Domain Socket  
> **Encoding**：UTF-8 JSON  
> **Framing**：32-bit big-endian length prefix + JSON payload

---

## 1. 设计目标

协议必须：

- 位置透明；
- 与 AgentScope 解耦；
- 支持 request/response；
- 支持 server event stream；
- 支持 cancellation；
- 支持 reconnect；
- 支持 version negotiation；
- 支持 idempotency；
- 支持 trace；
- 不暴露数据库和 Python 内部类型。

---

## 2. Handshake

App 建立 UDS 后第一个消息必须是：

```json
{
  "kind": "request",
  "protocol_version": "1.0",
  "request_id": "req_001",
  "trace_id": "trace_001",
  "method": "system.handshake",
  "payload": {
    "app_version": "0.1.0",
    "app_build": "100",
    "supported_protocols": ["1.0"]
  }
}
```

Engine 返回：

```json
{
  "kind": "response",
  "protocol_version": "1.0",
  "request_id": "req_001",
  "trace_id": "trace_001",
  "status": "ok",
  "payload": {
    "engine_version": "0.1.0",
    "engine_build": "100",
    "python_version": "3.11.x",
    "protocol_version": "1.0",
    "capabilities": [
      "world.open",
      "story.start",
      "story.submit_advice",
      "story.stream",
      "episode.get"
    ]
  }
}
```

版本不兼容时返回 `protocol_version_mismatch`，不继续打开世界。

---

## 3. Envelope

### Request

```json
{
  "kind": "request",
  "protocol_version": "1.0",
  "request_id": "req_x",
  "trace_id": "trace_x",
  "idempotency_key": "optional",
  "method": "story.submit_advice",
  "payload": {}
}
```

### Response

```json
{
  "kind": "response",
  "protocol_version": "1.0",
  "request_id": "req_x",
  "trace_id": "trace_x",
  "status": "ok",
  "payload": {}
}
```

### Event

```json
{
  "kind": "event",
  "protocol_version": "1.0",
  "trace_id": "trace_x",
  "stream_id": "story_session_x",
  "sequence": 7,
  "event": "story.narrative_ready",
  "payload": {}
}
```

### Error

```json
{
  "kind": "response",
  "protocol_version": "1.0",
  "request_id": "req_x",
  "trace_id": "trace_x",
  "status": "error",
  "error": {
    "code": "revision_conflict",
    "message": "Story revision changed.",
    "retryable": false,
    "details": {}
  }
}
```

---

## 4. Method Namespace

```text
system.*
world.*
character.*
fate.*
story.*
episode.*
asset.*
settings.*
diagnostics.*
```

v1.0 核心方法：

```text
system.handshake
system.health
system.shutdown

world.open
world.home
world.close

character.get_view

story.start
story.submit_advice
story.suspend
story.resume
story.request_closure
story.cancel_pending_turn
story.get_state

episode.get
episode.list

asset.resolve
```

---

## 5. Streaming Story Events

`story.submit_advice` 接收后立即返回 accepted，并通过 stream 发送：

```text
turn.accepted
turn.interpreting
turn.deciding
turn.resolved
turn.committed
story.beat_ready
story.narrative_ready
audio.ready
turn.delivered
```

UI 不直接把这些内部名展示给用户。

每个事件包含：

- stream id；
- monotonic sequence；
- story revision（适用时）；
- turn id；
- payload schema version。

断线重连可通过最后已接收 sequence 请求 replay 非临时 event。

---

## 6. Cancellation

### PRE_COMMIT

`story.cancel_pending_turn` 可以取消未提交 Turn。

### POST_COMMIT

返回：

```text
already_committed
```

UI 可以停止 Narrative/Audio，但不能取消事实。

---

## 7. Idempotency

所有 mutation request 必须带：

```text
idempotency_key
```

Engine 持久化至少覆盖：

- story.start；
- story.submit_advice；
- story.request_closure；
- worldline mutation；
- Episode finalization-triggering command。

重复 key：

- 已成功 → 返回同一 committed result；
- processing → 返回 existing operation status；
- payload 不同 → `idempotency_conflict`。

---

## 8. Error Taxonomy

至少：

```text
protocol_version_mismatch
invalid_request
schema_invalid
method_not_supported
engine_not_ready
world_not_open
revision_conflict
idempotency_conflict
authorization_denied
knowledge_violation
canon_violation
capability_violation
continuity_violation
model_timeout
model_invalid_output
storage_failure
projection_unavailable
recovery_required
cancelled
```

---

## 9. Security

- Socket 位于当前用户 Application Support Runtime 目录。
- 权限只允许当前用户。
- 不监听外部 TCP。
- Engine 验证 App 启动会话 token。
- token 每次 Engine launch 生成，只存在内存/受保护启动参数或父子进程 channel。
- IPC payload 不默认写入普通日志。

---

## 10. Protocol Versioning

```text
protocol_version = MAJOR.MINOR
```

- Major：breaking。
- Minor：向后兼容增加。
- Envelope unknown required semantics → fail。
- Payload `schema_version` 独立于 IPC protocol version。

---

## 11. Swift / Python Contract

JSON Schema 是协议规范来源。

Python：
- Pydantic validation。

Swift：
- Codable DTO + generated/validated fixtures。

CI 必须执行：
- Python encode → Swift decode；
- Swift encode → Python decode；
- canonical fixture roundtrip；
- unknown/invalid fixture rejection。
