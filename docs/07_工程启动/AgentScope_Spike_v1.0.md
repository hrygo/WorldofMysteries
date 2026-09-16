# AgentScope Integration Spike v1.0

> **状态**：P0 技术验证规格  
> **目标**：证明 AgentScope 可作为受 Domain 边界约束的 AI Execution Framework，而不成为事实源或事务控制器。

## 1. 固定 Runtime Profile

工程锁定：

```text
python_version = 3.14.7
agentscope_version = 2.0.8
provider_sdk_versions
prompt_registry_version
schema_registry_version
```

这些值进入 dependency lock 和 Runtime Trace。

## 2. 最小 Worker

### Advice Interpreter
输入：
- final transcript；
- current StoryState minimal context。

输出：
- `PlayerAdvice`。

### Character Reasoner
输入：
- Character ContextPacket；
- PlayerAdvice。

输出：
- `ActionIntent`。

### Story Director
Bounded Agent。

输出：
- `BeatPlan`。

### Narrative Compiler
输入：
- committed StateDelta；
- BeatPlan；
- disclosure context。

输出：
- `NarrativeBlock`。

## 3. Story Director Tool Scope

允许：

```text
read_story_state
read_open_threads
read_pressure
read_authorized_world_context
read_action_intent
propose_beat_plan
```

禁止：

```text
SQL
write_world
write_character
write_memory
write_knowledge
commit
fork_worldline
change_canon
```

## 4. Bounded Policy

```text
max_steps = 3
max_tool_calls = 5
timeout = ModelPolicy-defined
```

达到 limit 必须返回受控 failure，不允许无限 Loop。

## 5. Structured Output

每个 Worker：

```text
JSON Schema
→ Pydantic model
→ AgentScope structured output
→ Domain Validator
```

测试：

- valid；
- missing field；
- unknown field；
- invalid enum；
- malformed output；
- provider refusal；
- timeout。

## 6. Provider Abstraction

Engine Worker 不引用具体模型名。

只引用：

```text
fast_structured
strong_reasoning
narrative_quality
local_private
```

Router 将策略映射到 provider/model。

Spike 至少证明：
- MockProvider；
- 一个真实 provider adapter；
- fallback path。

## 7. Context Boundary

构造包含 Hidden Truth 的 world。

Character Reasoner 的 ContextPacket 不含 Hidden Truth。

断言：
- AgentScope 无独立数据库 tool 可自行获取；
- runtime message history 不补回 Hidden Truth；
- Agent output 不出现禁止事实。

## 8. Runtime Memory

允许：
- transient messages；
- compaction；
- tool outputs。

测试关闭/重启 AgentScope Runtime 后：
- Character Domain Memory 仍由 world.db 恢复；
- Runtime memory 丢失不影响事实。

## 9. Retry Semantics

### AI01 Advice invalid
只重试 Advice。

### AI02 Character timeout
Story revision 不变；重试 Character。

### AI03 Director timeout after Commit
Outcome 不回滚；只重试 Director。

### AI04 Narrative invalid after Commit
State 不回滚；只重试 Narrative。

## 10. Trace

每次调用必须记录：

```text
trace_id
request_id
task_type
context hash / packet id
prompt revision
schema revision
AgentScope version
provider
model
latency
usage
attempt
result status
```

Release 默认不记录完整 Hidden Truth prompt。

## 11. PASS

`GATE-AI = PASS`：

1. 所有 AI Worker 只输出 typed proposal/presentation。
2. Agent 无 Domain write tool。
3. Story Director 在 bounded policy 内结束。
4. Schema invalid 能被捕获和局部重试。
5. Provider 可替换。
6. Context authorization leak = 0。
7. AgentScope crash/failure 不破坏 Domain Commit。
8. Mock Runtime 可以确定性运行 Golden 001。
