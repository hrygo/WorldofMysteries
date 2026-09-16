# AgentScope Integration v1.0

> **状态**：AI Runtime 实现基线  
> **框架角色**：AgentScope 负责 AI execution；Domain Engines 负责 truth、rules、transaction 与 persistence。

## 1. 集成边界

```text
Domain Engines
   ↓
Mysterious AI Gateway
   ├─ Domain AI Contracts
   ├─ Context Compiler
   ├─ Model Policy
   ├─ Domain Tool Registry
   └─ Trace / Version metadata
   ↓
AgentScope Adapter
   ├─ Model calls
   ├─ Structured output
   ├─ Bounded Agents
   ├─ Tool runtime
   ├─ Middleware
   └─ Context-window handling
   ↓
Local / Cloud Models
```

AgentScope 类型不得泄漏到 Swift IPC 和 Domain public API。

## 2. Worker Mapping

| Worker | v1.0 实现 |
|---|---|
| Advice Interpreter | structured model call |
| Character Reasoner | structured model call |
| Outcome Resolver | deterministic code |
| Story Director | bounded Agent |
| Narrative Compiler | structured model call |
| Memory Distiller | structured model call |
| Canon / Capability Guard | rules first |
| World Pulse Planner | MVP 为显式调用的 structured planning；不运行持续自主 Agent |

## 3. Story Director Agent

Story Director 是唯一进入 Golden 001 关键路径的 Bounded Agent。

硬限制：

```text
max_steps = 3
max_tool_calls = 5
wall_time budget = runtime policy
```

允许工具：

- read_story_state
- read_open_threads
- read_pressure
- read_authorized_world_context
- read_character_action_intent
- propose_beat_plan

禁止工具：

- direct_sql
- write_world
- write_character
- write_memory
- mutate_canon
- fork_worldline
- commit_state

输出必须是 `BeatPlan` Contract。

## 4. Structured Output

所有模型工作单元先确定 Schema，再定义 prompt。

```text
Model
  ↓
AgentScope structured output
  ↓
Pydantic validation
  ↓
Domain validation
  ↓
Domain object / proposal
```

Schema failure 只重试当前 AI stage，不重跑已经成功的前序 stage。

## 5. Runtime Memory

AgentScope 可管理：

- 当前调用 message state；
- context compaction；
- 临时 Agent state；
- tool result offload；
- execution trace metadata。

AgentScope 不管理：

- Character Memory Truth；
- Knowledge / Belief；
- Relationship；
- World Event；
- Story history；
- Worldline。

## 6. Context

```text
Domain Data
  ↓
Context Compiler
  ↓  authorization / knowledge / spoiler / time
Authorized ContextPacket
  ↓
AgentScope
  ↓  formatting / token-window / compaction
Model-ready Context
```

AgentScope 的上下文压缩不能改变 Domain permission。

## 7. Model Policy

Domain 不指定厂商模型，只指定能力策略：

- fast_structured
- strong_reasoning
- narrative_quality
- local_private
- validation_assist

Model Router 决定：

- provider
- model
- reasoning effort
- token limit
- timeout
- fallback

## 8. Tool Policy

所有 Agent tools 是 MysteriousWorld-owned adapters。

Tool 输出：
- 带 source ids；
- 带 world/story revision；
- 只返回经过授权的数据；
- read/proposal only。

## 9. Pipeline

AgentScope Pipeline 可用于 AI-side 顺序和事件流，但不得拥有：

- Domain transaction；
- revision increment；
- worldline mutation；
- crash recovery；
- idempotency commit。

Session Orchestrator 始终是控制平面。

## 10. Versioning

发布构建必须：

- AgentScope 固定为 `2.0.8`；
- Python runtime 固定为 `3.14.7`；
- pin provider SDK；
- 记录 prompt/schema/model revision；
- 不依赖 AgentScope main branch；
- 实验性 realtime agent 不进入事实正确性路径。

## 11. Trace

每次 AI call 记录：

```text
request_id
trace_id
task_type
context_packet_id / hash
prompt_revision
schema_revision
agentscope_version
provider
model_revision
latency
token usage
result status
```

生产日志不保存不必要的完整 Hidden Truth prompt。

## 12. Failure Semantics

- Advice failure：当前 stage retry / fallback。
- Character Reasoner failure：当前 stage retry；不产生 ActionIntent 就不进入 Resolver。
- Director failure：基于已提交状态 retry；不得 rollback outcome。
- Narrative failure：只重生成 Narrative。
- AgentScope runtime crash：Domain transaction 由 world.db 状态决定恢复点。

## 13. 验收

Golden 001 必须证明：

1. Pydantic structured output 可稳定解析。
2. Story Director 在 bounded limits 内结束。
3. Agent 无 Domain write capability。
4. Provider 替换不改变 Domain Contract。
5. 同一 committed State 可独立重生成 Narrative。
