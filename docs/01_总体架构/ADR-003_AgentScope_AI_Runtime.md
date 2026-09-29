# ADR-003：AgentScope 作为 AI Runtime 基座

> **决策**：AgentScope 2.0.8 是首发 AI execution framework。  
> **状态**：Accepted  

> **当前实现状态（2026-09-28 核对）**：本 ADR 决策为**目标**，当前生产实现**尚未接入 AgentScope SDK**。两者此前混称，现予分离：
> - `engine/pyproject.toml` 已固定 `agentscope==2.0.8` 版本，但 Engine 源码**无任何 `import agentscope`**；
> - `engine/ai/agentscope_adapter.py` 是**预留 seam**（`PreparedAgentScopeAdapter`）：不创建 Agent、memory、tool 或 provider session，且**无生产调用方**（仅自身与 `test_ai_gateway.py` 引用）；
> - 生产 live 路径使用 `OpenAICompatibleChatTransport`（见 `engine/ai/openai_compatible.py`），经 AO-05 的授权执行边界调用。
>
> 接入真实 SDK 需另行交付：固定版本 wire-capture 集成测试、bounded tool 边界验收与运行内存隔离验收。在这些证据到位前，**不得宣称生产 AgentScope 已接入**。本节不改变本 ADR 的决策与状态。

## Decision

AgentScope 负责：

- Model integration；
- structured output；
- Toolkit；
- bounded agent loop；
- middleware；
- context-window handling；
- interruption / event stream；
- provider adapters。

《诡秘世界》自身负责：

- Lore / Canon；
- World Truth；
- Character State；
- Domain Memory / Knowledge；
- Story Transaction；
- Outcome Resolution；
- Validation；
- Commit；
- Data ownership。

## Worker Mapping

| Worker | Runtime |
|---|---|
| Advice Interpreter | structured model call |
| Character Reasoner | structured model call |
| Outcome Resolver | Domain code |
| Story Director | bounded AgentScope Agent |
| Narrative Compiler | structured model call |
| Memory Distiller | structured model call |
| Canon / Capability Guard | deterministic rules first |
| World Pulse Planner | explicit invocation only |

Story Director 的默认限制：

```text
max_steps = 3
read/proposal tools only
no direct DB write
no worldline fork tool
no Canon mutation
```

## AgentScope Memory

AgentScope Runtime Memory 只承担 AI execution 辅助。Character Memory、Knowledge、Belief、Relationship、World Event 均由 Domain Database 持有。

## Context

Context Compiler 先完成语义授权；AgentScope 只处理已授权内容的模型上下文装载、压缩和 offload。

## Agent Service / Pipeline / Realtime

- Agent Service 不进入 MVP 核心部署路径；
- Pipeline 不拥有 Domain transaction；
- RealtimeAgent 不进入 MVP 正确性关键路径；
- 上述能力均通过 Adapter 隔离，不影响 Domain Contract。

## Version Policy

- 使用 2.x 精确版本 pin；
- 代码只依赖已选版本 stable API；
- 不依赖 `main` 分支未发布行为；
- Framework upgrade 必须重跑 Golden Scenario 与 AI Eval。

## Rejected

- 所有模块全部 Agent 化；
- Agent-to-Agent 自由聊天；
- AgentScope memory 作为人物记忆源；
- AgentScope Agent 直接 SQL；
- Agent 自主决定 Commit。
