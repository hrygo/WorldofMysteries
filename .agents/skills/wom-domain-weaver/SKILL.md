---
name: wom-domain-weaver
description: >-
  《诡秘世界》核心领域业务编织技能。指导专精 Agent 实现 World Engine、Character Engine、Story State 状态机、
  确定性 Outcome Resolver 纯函数 Reducer 模式以及 28 项跨语言 Schema 同构映射。
---

# 《诡秘世界》核心领域业务编织技能 (wom-domain-weaver)

本技能用于指导 `AGT-DOM` (Domain Weaver) 及其他专精角色在 `engine/domain/` 目录下构建纯粹、健壮、可重放的领域逻辑。

---

## 1. 核心边界与纯粹性约束 (Fan-in: 6, Fan-out: 0)

领域核心层处于整洁架构的最内层：
- **严禁**：import `sqlite3`, `aiosqlite`, `agentscope`, `openai`, `httpx` 或任何第三方基础设施 SDK。
- **允许**：标准库（`dataclasses`, `enum`, `typing`, `math`, `uuid` 等）与 `engine/contracts/` 下的强类型模型。
- **依赖倒置**：任何持久化或外部通信需求，必须在 `engine/domain/` 声明 `Protocol` 抽象接口，由 `engine/infrastructure/` 提供实现。

---

## 2. 核心领域子系统实现模式

### 2.1 确定性 Outcome Resolver (纯函数 Reducer 模式)
为了保障世界线演进 100% 确定且具备**历史可重放性 (Deterministic Replay)**，`OutcomeResolver` 必须实现为无副作用的状态折叠函数：
```python
def resolve(
    current_world: WorldSnapshot,
    character: Character,
    proposal: Proposal
) -> StateDelta:
    """
    输入：当前世界快照、角色实体、AI 产出的建议提案
    输出：确定的状态变更增量 StateDelta
    原则：相同输入必须产出 100% 相同输出；杜绝隐式系统随机数或外部 I/O。
    """
```

### 2.2 充血领域实体 (Rich Domain Model)
杜绝贫血实体 + 面向过程服务：
- 实体应内聚包含其自身的生命周期与行为断言：
  - `Character.evaluate_advice(advice: PlayerAdvice) -> AdviceEvaluation`
  - `Character.absorb_knowledge(knowledge_item: CharacterKnowledge) -> None`
  - `WorldState.apply_delta(delta: StateDelta) -> WorldSnapshot`

---

## 3. 契约同步与单测验证工作流

1. **图谱调用链检索**：在修改或新增领域符号前，调用 `codebase-memory-mcp` 分析：
   ```json
   call_mcp_tool(ServerName="codebase-memory-mcp", ToolName="trace_path", Arguments={"project": "Users-hrygo-Documents-WorldofMysteries", "function_name": "<SYMBOL>", "direction": "both"})
   ```
2. **验证契约单测**：
   ```bash
   uv run --directory engine pytest tests/test_contracts_pydantic.py -v
   uv run --directory engine pytest tests/test_scaffolding.py -v
   ```
3. **架构适应度自检**：
   ```bash
   python3 scripts/check_architecture_fitness.py
   ```
