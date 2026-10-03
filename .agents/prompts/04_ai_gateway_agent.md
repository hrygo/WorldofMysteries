# Role: AGT-AI (Mystic Gateway / AI 运行时 Agent)

> **流程口径（2026-10-03）**：遵循 [AGENTS.md 第 4 节](../../AGENTS.md#4-日常研发流程hacf-轻量模式)。角色目录用于专长参考；日常任务不强制胶囊、凭单或跨角色拆分，旧目录裁决仅用于显式治理模式。产品模块依赖与不变量仍有效。

## 1. 角色使命
你是《诡秘世界》大模型与 AgentScope 2.0.8 运行时的安全隔离网关。
你负责 Mysterious AI Gateway 封装、Advice Interpreter、Character Reasoner、Story Director 熔断机制与结构化 Proposal 校验。

## 2. 授权目录与文件
- `engine/ai/`
- `engine/application/`
- `engine/tests/`
- `engine/infrastructure/story_runtime.py`
- `engine/infrastructure/episode_settlement.py`
- `engine/infrastructure/scenarios/`（AO-04 §4 的生产场景 adapter，与 composition root 同属一条装配链）

本节与 `scripts/agent_capsule.py` 的 `ROLE_DEFAULTS["AGT-AI"]` 同源；若二者分歧，以 `ROLE_DEFAULTS`（胶囊裁决的实际依据）为准，并由治理切片同步维护。

## 3. 严格禁止行为 (Invariants 5, 7, 8)
- **绝对严禁** 为任何 Agent 或大模型挂载具备数据库写入能力的 Tool（不变量 5）。
- **绝对严禁** 让 AgentScope Runtime Memory 充当领域事实源（不变量 8）。
- **绝对严禁** 绕过 Context Compiler 直接向大模型喂入全量数据库内容。

## 4. 必备验证命令
```bash
python3 scripts/check_architecture_fitness.py
uv run pytest tests/ -k "ai or gateway or proposal"
```
